.PHONY: app
app:
	@test -f .env || { echo 'Run cp .env.example .env, add JEV_API_KEY and at least one provider API key, then rerun make app.'; exit 1; }
	@command -v uv >/dev/null || { echo 'Install uv, then rerun make app.'; exit 1; }
	@command -v npm >/dev/null || { echo 'Install Node.js 24 (including npm), then rerun make app.'; exit 1; }
	cd backend && uv sync --locked
	cd backend && uv run --frozen python ../scripts/app.py
