.PHONY: api frontend app test

api:
	python3 -m tradebruv.api

frontend:
	cd frontend && npm run dev

app:
	@printf "Run these in separate terminals:\n  make api\n  make frontend\n"

test:
	python3 -m pytest
