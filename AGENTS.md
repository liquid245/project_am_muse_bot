# Repository Guidelines

## Project Structure & Module Organization
- `bot/` hosts the aiogram Telegram bot (`bot.py` plus `.env` template and dependencies); keep automation-specific helpers alongside bot code.
- `docs/` serves the GitHub Pages site (HTML + Tailwind + vanilla JS). `docs/catalog/catalog.json` and `docs/catalog/images/` are the single sources of catalog data for both site and bot.
- `data/orders.json` stores exported order events; treat it as an append-only audit history.

## Build, Test, and Development Commands
- `make install` creates `bot/.venv` and installs `bot/requirements.txt`.
- `make run-bot` loads `.env` via `python-dotenv` and starts the Telegram bot.
- `make run-site` runs cache busting and serves `docs/` with `python3 -m http.server`.
- `make run` launches site and bot together for manual end-to-end verification.
- `make clean` removes the virtualenv; rerun `make install` afterward before development.
- Document new CLI workflows inside the Makefile to keep onboarding simple.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indents in Python; prefer descriptive async handler names (e.g., `handle_order_submit`).
- Keep HTML semantic and reuse Tailwind utility patterns from `docs/index.html`; limit inline styles.
- JavaScript in `docs/script.js` should stay framework-free ES modules with camelCase functions and early returns for guard clauses.
- JSON assets (catalog/orders) must remain machine-editable: double quotes, two-space indents, deterministic key ordering.

## Testing Guidelines
- There is no automated suite yet—validate every change manually.
  - Bot: run `make run-bot`, exercise flows in a Telegram sandbox, and confirm stock/status diffs land in `docs/catalog/catalog.json`.
  - Site: run `make run-site`, verify gallery controls, responsive layout, and the cache-busting timestamp.
- Describe repro steps, expected vs. actual results, and any data edits in each PR until automated tests exist.

## Commit & Pull Request Guidelines
- Commits follow the existing short, imperative style (`Обновлен сайт.`, `Добавлен режим заказов`). Keep the summary under ~72 characters and scope to one logical change.
- Reference issues in either the commit body or PR description (`Fixes #12`) and list environment or data migrations explicitly.
- Pull requests need: a concise summary, test evidence (commands + outcomes), screenshots for UI changes, and confirmation that catalog/order JSON diffs are intentional.

## Security & Configuration Tips
- Never commit secrets; store `BOT_TOKEN`, `GITHUB_TOKEN`, `ADMIN_USER_ID`, `MANAGER_USER_ID`, and `REPO_NAME` in `.env` loaded via `python-dotenv`.
- When editing catalog or order data, follow the GitHub API workflow in `README.md` and guard concurrent writes with `asyncio.Lock`.
