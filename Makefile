.PHONY: up down seed test lint sim

up:
	docker compose up --build -d

down:
	docker compose down -v

seed:
	docker compose exec backend python scripts/create_super_admin.py
	docker compose exec backend python scripts/load_demo_data.py

test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend_test

lint:
	cd backend && ruff check . && black --check .
	cd frontend && npm run lint

sim:
	cd simulator && python -m simulator.run --config configs/base.yaml --cycles 20 --seeds 30 --out results/s1

logs:
	docker compose logs -f backend worker
