# Canvas Assignment Notifier Bot (Telegram Version)

## Overview

The Canvas Assignment Notifier is a Python script that connects to the Canvas API to fetch upcoming assignments, uses AI (via Ollama) to estimate completion times, and delivers notifications via a Telegram bot. It supports both scheduled daily summaries and on-demand checks using bot commands.

## Features

- Fetches upcoming assignments from the Canvas LMS API.
- Uses a local AI model (e.g., Mistral via Ollama) to estimate assignment completion times.
- Sends summaries via Telegram with Markdown formatting (bold text, links).
- **Interactive:** Check assignments anytime using the `/check` command.
- **Scheduled Notifications:** Receive a daily summary at a configured time.
- Configurable lookahead period (`DAYS_AHEAD`), check time (`CHECK_HOUR`, `CHECK_MINUTE`), and timezone (`APP_TIMEZONE`).
- Handles Canvas API errors and provides informative feedback.
- Asynchronous design using `asyncio` and `python-telegram-bot`.

## Requirements

- Python 3.9+
- Canvas API Access Token
- Ollama installed and running with a model (e.g., `ollama run mistral`)
- Telegram Account and a Telegram Bot Token

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/canvas-assignment-notifier.git # Replace with your repo URL
    cd canvas-assignment-notifier
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a Telegram Bot:**
    *   Open Telegram and search for `@BotFather`.
    *   Start a chat with BotFather and send `/newbot`.
    *   Follow the instructions to choose a name and username for your bot (e.g., `MyCanvasNotifierBot`).
    *   BotFather will give you an **HTTP API token**. Copy this token.

5.  **Set up Environment Variables:**
    *   Create a `.env` file in the root directory of the project.
    *   Copy the contents of `.env.example` (if provided) or add the following, replacing placeholder values:

    ```dotenv
    # --- Canvas Settings ---
    CANVAS_API_URL=https://your.instructure.com # Your Canvas instance URL
    CANVAS_API_TOKEN=your_canvas_api_token # Generate this in Canvas Account Settings

    # --- Telegram Settings ---
    TELEGRAM_BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE # From BotFather
    TELEGRAM_CHAT_ID= # Leave blank initially

    # --- Scheduling & Logic Settings ---
    DAYS_AHEAD=7          # Optional: default is 7
    CHECK_HOUR=8          # Optional: default is 8 AM (in APP_TIMEZONE)
    CHECK_MINUTE=0        # Optional: default is on the hour
    APP_TIMEZONE=America/New_York # Your local timezone (see list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

    # --- Optional: AI Settings ---
    # OLLAMA_MODEL=mistral # Default model used for estimation
    ```

6.  **Run the Bot (Initial Run to get Chat ID):**
    *   Ensure Ollama is running (`ollama serve` or the Ollama desktop app).
    *   Run the script:
        ```bash
        python canvas_telegram_bot.py # Or python src/canvas_telegram_bot.py if you have a src layout
        ```
    *   Open Telegram and find the bot you created.
    *   Send the `/start` command to your bot.
    *   **Check the console output** where you ran the Python script. It should print a line like:
        `--- User YourUsername started bot in Chat ID: 123456789 ---`
    *   Copy this numeric Chat ID.
    *   Stop the script (Ctrl+C).

7.  **Update `.env` with Chat ID:**
    *   Open your `.env` file again.
    *   Paste the copied Chat ID into the `TELEGRAM_CHAT_ID` variable:
        ```dotenv
        TELEGRAM_CHAT_ID=123456789
        ```
    *   Save the `.env` file. This ID is needed for the bot to send you *scheduled* messages.

8.  **Run the Bot Permanently:**
    *   Now run the script again:
        ```bash
        python canvas_telegram_bot.py
        ```
    *   The bot is now running, listening for commands, and will send scheduled notifications. You'll likely want to run this using a process manager like `systemd`, `supervisor`, `docker`, or a screen/tmux session for long-term operation.

## Usage

Interact with your bot on Telegram:

-   `/start`: Get a welcome message and confirm the bot is working. Displays your Chat ID.
-   `/check`: Manually trigger a check for upcoming assignments. The bot will reply with the current list.
-   `/help`: Show the list of available commands.

The bot will automatically send a summary of upcoming assignments daily at the time specified by `CHECK_HOUR` and `CHECK_MINUTE` in your `APP_TIMEZONE`.

## AI Time Estimation Notes

-   The quality of the time estimate depends heavily on the AI model (Mistral is generally decent) and the quality/detail of the assignment description in Canvas.
-   Estimates are approximate and intended as a planning aid.
-   If Ollama is unreachable or the AI fails to provide a valid number, the estimate will be omitted for that assignment.

## Deployment (Optional)

To run the bot 24/7 without keeping your local machine on, consider deploying it to:

-   **Cloud Virtual Machine:** (AWS EC2, Google Cloud Compute Engine, Azure VM, Oracle Cloud Free Tier)
-   **Platform-as-a-Service (PaaS):** (Heroku, Render, Fly.io, Railway.app)
-   **Raspberry Pi:** A low-power device you can run at home.
-   **Containerization:** Use Docker for consistent deployment across environments.

Ensure Ollama is accessible to the deployed bot (either running on the same machine or accessible over a network).

## Contributing

Contributions, issues, and feature requests are welcome! Feel free to check [issues page](https://github.com/yourusername/canvas-assignment-notifier/issues).

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.