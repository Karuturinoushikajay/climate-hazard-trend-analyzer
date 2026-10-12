.PHONY: test api web

test:
	cd backend && .venv/bin/pytest

api:
	cd backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload

web:
	cd frontend && npm run dev
