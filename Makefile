.PHONY: all install run-bot run-site bust-cache run clean audit-images restore-images

# ==============================================================================
# Project AM Muse Makefile
#
# Available commands:
#   make all        - Install dependencies and run all services (default).
#   make install    - Create virtual environment and install dependencies.
#   make run-bot    - Run the Telegram bot server.
#   make run-site   - Run the static site server (with cache busting).
#   make bust-cache - Manually update the CSS cache buster version.
#   make clean      - Remove virtual environment and temporary files.
# ==============================================================================

# --- Setup ---

# Define SED_INPLACE for cross-platform compatibility (macOS vs Linux)
ifeq ($(shell uname), Darwin)
	SED_INPLACE = sed -i ''
else
	SED_INPLACE = sed -i
endif

# --- Main Targets ---

# Default target
all: install run

# Install python dependencies for the bot
install:
	@echo ">>> Creating Python virtual environment in bot/.venv..."
	python3 -m venv bot/.venv
	@echo ">>> Installing dependencies from bot/requirements.txt..."
	bot/.venv/bin/python -m pip install -r bot/requirements.txt
	@echo "✅ Installation complete."

# Run the telegram bot
run-bot:
	@echo "🤖 Starting Telegram bot server (Refactored)..."
	@if [ -f bot/.env ]; then cp bot/.env .env; fi
	bot/.venv/bin/python3 main.py

run-bot-in-docker:
	docker build -t am-muse-bot .
	-docker rm -f am-muse-instance
	docker run --name am-muse-instance --env-file .env am-muse-bot

# Run the static site server (now with cache busting)
run-site: bust-cache
	@echo "🌐 Starting static site server on http://localhost:8000..."
	python3 -m http.server --directory docs 8000

# Run both bot and site in parallel
run:
	@echo "🚀 Starting all services in parallel..."
	@bash -c ' 
		(make run-site) & PIDS="$!"; 
		(make run-bot) & PIDS="$! $PIDS"; 
		
		echo "Started PIDS: $PIDS" ; 
		trap "kill -9 $$PIDS 2>/dev/null" SIGINT ; 
		wait 
	'

# Clean up generated files
clean:
	@echo "🧹 Cleaning up..."
	rm -rf bot/.venv
	@echo "✅ Cleanup complete."

# --- Helper Targets ---

# Updates the cache buster for style.css in the HTML file
bust-cache:
	@echo "--- Обновление метки кэша для CSS ---"
	@if [ -f docs/index.html ]; then \
		TIMESTAMP=$$(date +%s); \
		$(SED_INPLACE) "s/style\.css?v=[0-9.]*/style.css?v=$${TIMESTAMP}/g" docs/index.html; \
		echo "✅ Кэш обновлен: $${TIMESTAMP}"; \
	else \
		echo "⚠️  Файл docs/index.html не найден, пропуск."; \
	fi
	@echo "------------------------------------"

# --- Integrity helpers ---

audit-images:
	@echo "🔍 Проверяю целостность каталога..."
	python3 -m tools.catalog_guard audit

restore-images:
	@echo "♻️ Пытаюсь восстановить отсутствующие изображения..."
	python3 -m tools.catalog_guard restore
