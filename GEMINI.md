# Project AM Muse

## Project Overview

This repository contains the code for **Project AM Muse**, a simple and cost-effective system for managing and displaying a catalog of handmade brooches. The project is designed to be run with zero monthly costs, leveraging free tiers of services.

The system consists of two main components:

1.  **A Telegram Bot:** Built with Python and the `aiogram` library, the bot serves as the administrative backend. It allows the administrator to manage the product catalog (add, edit, delete items) and receive order notifications.
2.  **A Static Website:** Built with HTML, Tailwind CSS, and vanilla JavaScript, the website serves as the customer-facing storefront. It dynamically loads product information from a JSON file and displays it in a clean, responsive grid.

The entire system is orchestrated around a single source of truth: `docs/catalog/catalog.json`.

### Key Technologies

*   **Backend (Bot):** Python, `aiogram`
*   **Frontend (Site):** HTML, Tailwind CSS, JavaScript
*   **Data:** JSON
*   **Hosting:**
    *   Bot: Intended for PythonAnywhere (free tier).
    *   Site: GitHub Pages.

### Architecture

The project follows a simple, file-based architecture:

*   The Telegram bot modifies the `docs/catalog/catalog.json` file and saves product images to `docs/catalog/images/`.
*   The static website reads the `docs/catalog/catalog.json` file to display the products.
*   When a customer clicks "Order" on the website, it generates a deep link to the Telegram bot to initiate the order process.
*   The bot handles the order, updates the stock in `catalog.json`, and sends a notification to the administrator.

## Building and Running

A `Makefile` is provided for easy project management.

### Installation

To install the Python dependencies for the bot, run:

```sh
make install
```

This will create a virtual environment in `bot/.venv` and install the required packages from `bot/requirements.txt`.

### Running the Project

To run both the Telegram bot and the local web server simultaneously, use:

```sh
make run
```

This will:
1.  Start a local web server for the static site at `http://localhost:8000`.
2.  Start the Telegram bot.

You can also run the services individually:

*   **Run the website only:**
    ```sh
    make run-site
    ```
*   **Run the bot only:**
    ```sh
    make run-bot
    ```

### Environment Variables

The bot requires the following environment variables to be set in `bot/.env`:

*   `BOT_TOKEN`: Your Telegram bot token.
*   `ADMIN_USER_ID`: The Telegram user ID of the administrator.
*   `ORDER_CHAT_ID`: The ID of the Telegram chat where order notifications will be sent.
*   `ORDER_TOPIC_ID`: The ID of the topic within the order chat.

## Development Conventions

### Code Style

The Python code in `bot/bot.py` and the JavaScript in `docs/script.js` follow standard conventions for their respective languages.

### Data Management

*   All product data is stored in `docs/catalog/catalog.json`. This file is the single source of truth.
*   Product images are stored in `docs/catalog/images/`.
*   The `data/orders.json` file appears to be a log of past orders, but the primary order notification mechanism is via Telegram messages.

### Contribution Guidelines

While there are no formal contribution guidelines, the `README.md` and existing code suggest a focus on simplicity, minimalism, and zero-cost operation. Any changes or new features should adhere to these principles.
