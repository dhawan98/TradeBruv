from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from streamlit.web import cli as streamlit_cli
    except ImportError:
        print(
            "The dashboard dependency is not installed. "
            "Install it with: python3 -m pip install '.[dashboard]'"
        )
        return 2

    app_path = Path(__file__).with_name("dashboard_app.py")
    sys.argv = ["streamlit", "run", str(app_path), *sys.argv[1:]]
    streamlit_cli.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
