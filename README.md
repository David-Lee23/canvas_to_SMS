# Canvas Assignment Notifier Bot (Telegram Version)

This script connects to the Canvas LMS API to fetch upcoming assignments, uses a local AI model (via Ollama) to estimate completion times, and delivers notifications via a Telegram bot. It supports both scheduled daily summaries and on-demand checks using bot commands.

## Features

*   **Fetches Upcoming Assignments:** Retrieves assignments due within a configurable number of days from the Canvas API using asynchronous calls.
*   **AI Time Estimation:** Uses a configured Ollama model (default: `mistral`) to analyze assignment descriptions and estimate completion time.
*   **Telegram Bot Interface:**
    *   Provides commands (`/start`, `/help`, `/check`) for user interaction.
    *   Sends well-formatted summaries using Telegram's MarkdownV2.
    *   Handles `/start` to welcome users and provide their chat ID.
*   **Scheduled Daily Notifications:** Sends a summary of upcoming assignments daily at a configured time to a specific chat ID.
*   **Timezone Aware:** Correctly handles due dates and scheduling using configurable timezones (defaults to `America/New_York`).
*   **Asynchronous:** Built using `asyncio` and `python-telegram-bot`'s async capabilities for efficient operation.
*   **Configurable:** Uses environment variables for all sensitive information and settings (API keys, bot token, chat ID, schedule, model, etc.).
*   **Robust:** Includes error handling for Canvas API, Telegram API, AI estimation, and configuration issues, with detailed logging.
*   **MarkdownV2 Formatting:** Properly escapes text for reliable Markdown rendering in Telegram.

## Prerequisites

*   **Python 3.9+:** Required for the `zoneinfo` module and modern `asyncio` features.
*   **Canvas API Access Token:** Generate an API token from your Canvas account settings.
*   **Telegram Bot Token:** Create a bot using Telegram's @BotFather and get its API token.
*   **Telegram Chat ID:** You need the ID of the chat (user, group, or channel) where the bot will send *scheduled* messages. The bot will print your user chat ID when you first `/start` it. For groups, you might need other methods to find the ID (e.g., adding a raw data bot temporarily).
*   **Ollama Installed and Running:** Ollama must be installed and running on the machine where the script executes.
*   **Ollama Model Pulled:** The AI model specified in the environment variables (default: `mistral`) must be pulled. Run `ollama pull mistral` (or your chosen model name).

## Setup

1.  **Clone the Repository (or download the script):**
    ```bash
    git clone <your-repo-url> # Or just save the script as canvas_telegram_bot.py
    cd <your-repo-directory>
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   **Edit the `.env` file** with your actual credentials and settings. See the comments in `.env.example` for details on each variable.
        *   `CANVAS_API_URL`: Your institution's Canvas base URL.
        *   `CANVAS_API_TOKEN`: Your Canvas API token.
        *   `TELEGRAM_BOT_TOKEN`: Your Telegram bot's API token from @BotFather.
        *   `TELEGRAM_CHAT_ID`: **Required for scheduled messages.** The chat ID where daily summaries will be sent. You can get your *user* chat ID by running the bot and sending `/start`.
        *   `DAYS_AHEAD`: (Optional) How many days ahead to check for assignments (default: 7).
        *   `CHECK_HOUR`: (Optional) Hour (0-23) in your specified `APP_TIMEZONE` to run the *scheduled* check (default: 8).
        *   `CHECK_MINUTE`: (Optional) Minute (0-59) to run the *scheduled* check (default: 0).
        *   `APP_TIMEZONE`: (Optional) Your local timezone name (e.g., `America/New_York`, `Europe/London`). See [List of tz database time zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) (use the 'TZ database name' column). Default: `America/New_York`.
        *   `OLLAMA_MODEL`: (Optional) The Ollama model to use for time estimation (default: `mistral`).

    **Important:** Never commit your actual `.env` file to version control. Add `.env` to your `.gitignore` file.

5.  **Ensure Ollama is Running:**
    Make sure the Ollama service/application is running and the model specified in your `.env` file is available locally.

## Running the Bot

1.  **Activate your virtual environment** (if you created one):
    ```bash
    source venv/bin/activate # Or venv\Scripts\activate on Windows
    ```
2.  **Run the Python script:**
    ```bash
    python canvas_telegram_bot.py
    ```

The script will:
1.  Load configuration and connect to Telegram.
2.  Register command handlers (`/start`, `/help`, `/check`).
3.  If `TELEGRAM_CHAT_ID` is set, schedule the daily check based on `CHECK_HOUR`, `CHECK_MINUTE`, and `APP_TIMEZONE`.
4.  Start polling for updates from Telegram.

The bot needs to remain running in the foreground (or as a background process/service using tools like `screen`, `tmux`, or systemd) to respond to commands and execute the scheduled job.

## Interacting with the Bot

*   Find your bot on Telegram (using the username you set with @BotFather).
*   Send `/start` to initiate interaction. The bot will reply with a welcome message and your chat ID (useful for the `TELEGRAM_CHAT_ID` environment variable if you want scheduled messages sent directly to you).
*   Send `/help` to see available commands.
*   Send `/check` to manually trigger a check for upcoming assignments. The result will be sent to the chat where you issued the command.
*   If configured, the bot will automatically send a summary to the `TELEGRAM_CHAT_ID` at the scheduled time.

## Troubleshooting

*   **Bot unresponsive:** Check script logs for errors. Ensure the script is running. Verify `TELEGRAM_BOT_TOKEN` is correct. Check internet connectivity.
*   **Canvas Errors:** Verify `CANVAS_API_URL` and `CANVAS_API_TOKEN`. Check Canvas status and token permissions.
*   **Ollama Errors:** Ensure Ollama service is running. Verify the `OLLAMA_MODEL` in `.env` is correct and pulled (`ollama list`). Check Ollama logs.
*   **Scheduled Messages Not Sending:** Ensure `TELEGRAM_CHAT_ID` is set correctly in `.env` and the script was restarted after setting it. Verify the bot has permission to send messages in that chat (especially for groups/channels). Check timezone settings (`APP_TIMEZONE`) and scheduled time (`CHECK_HOUR`, `CHECK_MINUTE`).
*   **MarkdownV2 Errors:** The script tries to escape characters, but complex assignment names/descriptions might occasionally cause issues. Check logs for `TelegramError` related to parsing.
*   **`AttributeError: 'NoneType' object has no attribute 'message'` or similar on /check:** This can happen if the bot's internal context isn't set up correctly, often on the very first run or after a restart. Check logs for errors during startup, especially around `bot_data` population. Ensure configuration loads correctly.
*   **Windows Event Loop Policy:** The script includes a fix for `asyncio` on Windows. If you encounter `RuntimeError: Event loop is closed` on Windows, ensure this policy is being set correctly.
