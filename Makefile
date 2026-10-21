up:
	docker compose up -d --build
down:
	docker compose down
reset:
	docker compose down -v
logs:
	docker compose logs -f api
test:
	docker compose exec api python -m pytest -q
eval:
	docker compose exec -e GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) api python -m evals.runner
eval-outreach:
	docker compose exec api python -m evals.outreach_runner
scraper:
	docker compose --profile scraper up -d scraper
