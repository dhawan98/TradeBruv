from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .providers import MarketDataProvider


DEFAULT_PORTFOLIO_PATH = Path("data/portfolio.csv")

DECISION_STATUSES = (
    "Hold",
    "Buy More / Add",
    "Trim",
    "Sell / Exit",
    "Watch Closely",
    "Research More",
    "Avoid Adding",
    "Data Insufficient",
)

PORTFOLIO_FIELDS = [
    "account_name",
    "ticker",
    "company_name",
    "quantity",
    "average_cost",
    "current_price",
    "market_value",
    "cost_basis",
    "unrealized_gain_loss",
    "unrealized_gain_loss_pct",
    "realized_gain_loss",
    "position_weight_pct",
    "sector",
    "theme_tags",
    "purchase_date",
    "intended_holding_period",
    "thesis",
    "risk_notes",
    "user_notes",
    "stop_or_invalidation",
    "target_price",
    "decision_status",
    "last_reviewed_at",
]

ALIASES = {
    "account": "account_name",
    "account name": "account_name",
    "symbol": "ticker",
    "security": "ticker",
    "description": "company_name",
    "name": "company_name",
    "shares": "quantity",
    "qty": "quantity",
    "cost basis total": "cost_basis",
    "cost basis": "cost_basis",
    "avg cost": "average_cost",
    "average cost": "average_cost",
    "last price": "current_price",
    "price": "current_price",
    "market value": "market_value",
    "gain/loss": "unrealized_gain_loss",
    "unrealized gain/loss": "unrealized_gain_loss",
    "% gain/loss": "unrealized_gain_loss_pct",
    "gain/loss %": "unrealized_gain_loss_pct",
    "realized gain/loss": "realized_gain_loss",
}


@dataclass
class PortfolioPosition:
    account_name: str = "Personal"
    ticker: str = ""
    company_name: str = ""
    quantity: float = 0.0
    average_cost: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealized_gain_loss: float = 0.0
    unrealized_gain_loss_pct: float = 0.0
    realized_gain_loss: float = 0.0
    position_weight_pct: float = 0.0
    sector: str = ""
    theme_tags: str = ""
    purchase_date: str = ""
    intended_holding_period: str = ""
    thesis: str = ""
    risk_notes: str = ""
    user_notes: str = ""
    stop_or_invalidation: str = ""
    target_price: str = ""
    decision_status: str = "Research More"
    last_reviewed_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PortfolioPosition":
        normalized = {_canonical_key(key): value for key, value in row.items()}
        payload = {field_name: normalized.get(field_name, "") for field_name in PORTFOLIO_FIELDS}
        position = cls(
            account_name=str(payload["account_name"] or "Personal"),
            ticker=str(payload["ticker"] or "").strip().upper(),
            company_name=str(payload["company_name"] or ""),
            quantity=_to_float(payload["quantity"]),
            average_cost=_to_float(payload["average_cost"]),
            current_price=_to_float(payload["current_price"]),
            market_value=_to_float(payload["market_value"]),
            cost_basis=_to_float(payload["cost_basis"]),
            unrealized_gain_loss=_to_float(payload["unrealized_gain_loss"]),
            unrealized_gain_loss_pct=_to_float(payload["unrealized_gain_loss_pct"]),
            realized_gain_loss=_to_float(payload["realized_gain_loss"]),
            position_weight_pct=_to_float(payload["position_weight_pct"]),
            sector=str(payload["sector"] or ""),
            theme_tags=str(payload["theme_tags"] or ""),
            purchase_date=str(payload["purchase_date"] or ""),
            intended_holding_period=str(payload["intended_holding_period"] or ""),
            thesis=str(payload["thesis"] or ""),
            risk_notes=str(payload["risk_notes"] or ""),
            user_notes=str(payload["user_notes"] or ""),
            stop_or_invalidation=str(payload["stop_or_invalidation"] or ""),
            target_price=str(payload["target_price"] or ""),
            decision_status=_normalize_decision(str(payload["decision_status"] or "")),
            last_reviewed_at=str(payload["last_reviewed_at"] or ""),
        )
        position.recalculate()
        return position

    def recalculate(self) -> None:
        if not self.cost_basis and self.quantity and self.average_cost:
            self.cost_basis = self.quantity * self.average_cost
        if not self.average_cost and self.quantity and self.cost_basis:
            self.average_cost = self.cost_basis / self.quantity
        if not self.market_value and self.quantity and self.current_price:
            self.market_value = self.quantity * self.current_price
        if self.market_value and self.cost_basis:
            self.unrealized_gain_loss = self.market_value - self.cost_basis
            self.unrealized_gain_loss_pct = (self.unrealized_gain_loss / self.cost_basis) * 100

    def to_dict(self) -> dict[str, Any]:
        self.recalculate()
        return {
            "account_name": self.account_name,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "quantity": _round(self.quantity),
            "average_cost": _round(self.average_cost),
            "current_price": _round(self.current_price),
            "market_value": _round(self.market_value),
            "cost_basis": _round(self.cost_basis),
            "unrealized_gain_loss": _round(self.unrealized_gain_loss),
            "unrealized_gain_loss_pct": _round(self.unrealized_gain_loss_pct),
            "realized_gain_loss": _round(self.realized_gain_loss),
            "position_weight_pct": _round(self.position_weight_pct),
            "sector": self.sector,
            "theme_tags": self.theme_tags,
            "purchase_date": self.purchase_date,
            "intended_holding_period": self.intended_holding_period,
            "thesis": self.thesis,
            "risk_notes": self.risk_notes,
            "user_notes": self.user_notes,
            "stop_or_invalidation": self.stop_or_invalidation,
            "target_price": self.target_price,
            "decision_status": self.decision_status,
            "last_reviewed_at": self.last_reviewed_at,
        }


def load_portfolio(path: Path = DEFAULT_PORTFOLIO_PATH) -> list[PortfolioPosition]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return _finalize_weights([PortfolioPosition.from_row(row) for row in csv.DictReader(handle)])


def save_portfolio(positions: Iterable[PortfolioPosition | dict[str, Any]], path: Path = DEFAULT_PORTFOLIO_PATH) -> Path:
    rows = _finalize_weights([_as_position(position) for position in positions if _as_position(position).ticker])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PORTFOLIO_FIELDS)
        writer.writeheader()
        writer.writerows([position.to_dict() for position in rows])
    return path


def import_portfolio_csv(import_path: Path, portfolio_path: Path = DEFAULT_PORTFOLIO_PATH) -> list[PortfolioPosition]:
    with import_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = [PortfolioPosition.from_row(row) for row in csv.DictReader(handle)]
    rows = [row for row in rows if row.ticker]
    save_portfolio(rows, portfolio_path)
    return rows


def export_portfolio_csv(positions: Iterable[PortfolioPosition | dict[str, Any]], output_path: Path) -> Path:
    return save_portfolio(positions, output_path)


def upsert_position(
    *,
    position: PortfolioPosition | dict[str, Any],
    portfolio_path: Path = DEFAULT_PORTFOLIO_PATH,
) -> PortfolioPosition:
    new_position = _as_position(position)
    if not new_position.ticker:
        raise ValueError("ticker is required")
    rows = load_portfolio(portfolio_path)
    updated = False
    for index, existing in enumerate(rows):
        if existing.account_name == new_position.account_name and existing.ticker == new_position.ticker:
            rows[index] = new_position
            updated = True
            break
    if not updated:
        rows.append(new_position)
    save_portfolio(rows, portfolio_path)
    return new_position


def delete_position(*, ticker: str, account_name: str | None = None, portfolio_path: Path = DEFAULT_PORTFOLIO_PATH) -> bool:
    ticker = ticker.upper()
    rows = load_portfolio(portfolio_path)
    kept = [
        row
        for row in rows
        if not (row.ticker == ticker and (account_name is None or row.account_name == account_name))
    ]
    removed = len(kept) != len(rows)
    if removed:
        save_portfolio(kept, portfolio_path)
    return removed


def refresh_portfolio_prices(
    *,
    positions: Iterable[PortfolioPosition | dict[str, Any]],
    provider: MarketDataProvider,
) -> list[PortfolioPosition]:
    refreshed: list[PortfolioPosition] = []
    for item in positions:
        position = _as_position(item)
        try:
            security = provider.get_security_data(position.ticker)
        except Exception as exc:
            position.risk_notes = _append_note(position.risk_notes, f"Price refresh failed: {exc}")
        else:
            latest = security.bars[-1].close if security.bars else 0
            position.current_price = latest
            position.company_name = position.company_name or security.company_name or ""
            position.sector = position.sector or security.sector or ""
            if not position.theme_tags and security.theme_tags:
                position.theme_tags = " | ".join(security.theme_tags)
            position.market_value = 0
            position.last_reviewed_at = datetime.utcnow().isoformat() + "Z"
            position.recalculate()
        refreshed.append(position)
    return _finalize_weights(refreshed)


def portfolio_summary(positions: Iterable[PortfolioPosition | dict[str, Any]]) -> dict[str, Any]:
    rows = _finalize_weights([_as_position(row) for row in positions])
    total_value = sum(row.market_value for row in rows)
    total_cost = sum(row.cost_basis for row in rows)
    total_gain = total_value - total_cost if total_cost else sum(row.unrealized_gain_loss for row in rows)
    by_sector = _bucket(rows, "sector")
    by_theme = _theme_bucket(rows)
    top_winners = sorted(rows, key=lambda row: row.unrealized_gain_loss_pct, reverse=True)[:5]
    top_losers = sorted(rows, key=lambda row: row.unrealized_gain_loss_pct)[:5]
    concentration = concentration_risk(rows)
    review_needed = positions_needing_review(rows)
    return {
        "position_count": len(rows),
        "total_market_value": _round(total_value),
        "total_cost_basis": _round(total_cost),
        "total_unrealized_gain_loss": _round(total_gain),
        "total_unrealized_gain_loss_pct": _round((total_gain / total_cost) * 100) if total_cost else 0,
        "allocation_by_sector": by_sector,
        "allocation_by_theme": by_theme,
        "top_winners": [row.to_dict() for row in top_winners],
        "top_losers": [row.to_dict() for row in top_losers],
        "concentration_risk": concentration,
        "positions_needing_review": [row.to_dict() for row in review_needed],
    }


def concentration_risk(positions: Iterable[PortfolioPosition | dict[str, Any]]) -> dict[str, Any]:
    rows = _finalize_weights([_as_position(row) for row in positions])
    high_weight = [row for row in rows if row.position_weight_pct >= 20]
    medium_weight = [row for row in rows if 10 <= row.position_weight_pct < 20]
    theme_buckets = _theme_bucket(rows)
    concentrated_themes = [item for item in theme_buckets if item["weight_pct"] >= 35]
    return {
        "high_concentration_positions": [row.to_dict() for row in high_weight],
        "medium_concentration_positions": [row.to_dict() for row in medium_weight],
        "concentrated_themes": concentrated_themes,
        "max_position_weight_pct": _round(max((row.position_weight_pct for row in rows), default=0)),
        "risk_label": "High" if high_weight or concentrated_themes else ("Medium" if medium_weight else "Low"),
    }


def positions_needing_review(positions: Iterable[PortfolioPosition | dict[str, Any]], today: date | None = None) -> list[PortfolioPosition]:
    today = today or date.today()
    review_rows: list[PortfolioPosition] = []
    for row in [_as_position(item) for item in positions]:
        if row.decision_status in {"Watch Closely", "Research More", "Data Insufficient"}:
            review_rows.append(row)
            continue
        if not row.last_reviewed_at:
            review_rows.append(row)
            continue
        try:
            reviewed = date.fromisoformat(row.last_reviewed_at[:10])
        except ValueError:
            review_rows.append(row)
            continue
        if reviewed <= today - timedelta(days=14):
            review_rows.append(row)
    return review_rows


def broker_execution_supported() -> bool:
    return False


def _finalize_weights(positions: list[PortfolioPosition]) -> list[PortfolioPosition]:
    total = sum(position.market_value for position in positions)
    for position in positions:
        position.recalculate()
        position.position_weight_pct = (position.market_value / total) * 100 if total else 0
    return positions


def _bucket(rows: list[PortfolioPosition], attr: str) -> list[dict[str, Any]]:
    total = sum(row.market_value for row in rows)
    buckets: dict[str, float] = {}
    for row in rows:
        key = getattr(row, attr) or "Unclassified"
        buckets[key] = buckets.get(key, 0) + row.market_value
    return [
        {"name": name, "market_value": _round(value), "weight_pct": _round((value / total) * 100) if total else 0}
        for name, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    ]


def _theme_bucket(rows: list[PortfolioPosition]) -> list[dict[str, Any]]:
    total = sum(row.market_value for row in rows)
    buckets: dict[str, float] = {}
    for row in rows:
        tags = [tag.strip() for tag in row.theme_tags.replace(",", "|").split("|") if tag.strip()]
        if not tags:
            tags = ["Unclassified"]
        for tag in tags:
            buckets[tag] = buckets.get(tag, 0) + row.market_value
    return [
        {"name": name, "market_value": _round(value), "weight_pct": _round((value / total) * 100) if total else 0}
        for name, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    ]


def _as_position(position: PortfolioPosition | dict[str, Any]) -> PortfolioPosition:
    return position if isinstance(position, PortfolioPosition) else PortfolioPosition.from_row(position)


def _canonical_key(key: str) -> str:
    cleaned = key.strip().lower().replace("_", " ")
    return ALIASES.get(cleaned, cleaned.replace(" ", "_"))


def _normalize_decision(value: str) -> str:
    if not value:
        return "Research More"
    lower = value.strip().lower()
    for status in DECISION_STATUSES:
        if lower == status.lower():
            return status
    if lower in {"buy more", "add"}:
        return "Buy More / Add"
    if lower in {"sell", "exit"}:
        return "Sell / Exit"
    return "Research More"


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return 0.0


def _round(value: float) -> float:
    return round(float(value or 0), 4)


def _append_note(existing: str, note: str) -> str:
    return f"{existing} | {note}" if existing else note
