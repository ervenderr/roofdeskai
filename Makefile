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
	docker compose exec -e GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) api python -m evals.runner $(ARGS)
eval-outreach:
	docker compose exec api python -m evals.outreach_runner
scraper:
	docker compose --profile scraper up -d scraper

GCOMPOSE = docker compose -p roofdesk-global -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.global.yml
g-up:
	$(GCOMPOSE) up -d --build
g-down:
	$(GCOMPOSE) down
g-reset:
	$(GCOMPOSE) down -v
g-logs:
	$(GCOMPOSE) logs -f api
g-test:
	$(GCOMPOSE) exec api python -m pytest -q --ignore=api $(ARGS)
check-n8n:
	$(GCOMPOSE) exec -T api python -m pytest -q app/test_n8n_workflows.py
run-flows:
	$(GCOMPOSE) exec -T api python -m scripts.run_flows
g-eval-modules:
	$(GCOMPOSE) exec -T api python -m evals.modules $(ARGS)
g-eval:
	$(GCOMPOSE) exec -e GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) $(if $(BASELINE_PATH),-e BASELINE_PATH=$(BASELINE_PATH)) api python -m evals.runner $(ARGS)
eval-gate:
	$(MAKE) g-eval ARGS="--gate $(ARGS)"
new-business:
	@test -n "$(PACK)" || (echo "usage: make new-business PACK=<slug>"; exit 2)
	$(GCOMPOSE) exec -T api python -m scripts.new_business $(PACK)
check-shared:
	$(GCOMPOSE) exec -T api python -m scripts.check_shared
