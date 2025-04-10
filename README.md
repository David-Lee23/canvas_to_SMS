# Canvas Assignment Notifier Bot (Telegram Version)

This script connects to the Canvas LMS API to fetch upcoming assignments, uses a local AI model (via Ollama) to estimate completion times and summarize descriptions, and delivers notifications via a Telegram bot. It supports both scheduled daily summaries and on-demand checks using bot commands, including the ability to request detailed information about specific assignments.

## Features

*   **Fetches Upcoming Assignments:** Retrieves assignments due within a configurable number of days from the Canvas API using asynchronous calls.
*   **AI Assistance:** Uses a configured Ollama model (default: `mistral`) for:
    *   **Time Estimation:** Analyzes assignment details to estimate completion time (shown in the `/check` list).
    *   **Summarization:** Generates concise AI summaries for assignment descriptions (shown in the detailed view).
*   **Telegram Bot Interface:**
    *   Provides commands (`/start`, `/help`, `/check`) for user interaction.
    *   Handles text messages (e.g., `details N`) to provide specific assignment details after a `/check`.
    *   Sends well-formatted summaries and details using Telegram's MarkdownV2.
    *   Handles `/start` to welcome users and provide their chat ID.
*   **Detailed Assignment View:** Fetches and displays comprehensive details for a specific assignment (requested by index after `/check`), including:
    *   Full description
    *   Attachments (with clickable links)
    *   Due/Unlock/Lock dates
    *   Points possible
    *   Submission types
    *   Allowed file extensions (if specified)
    *   AI-generated summary
    *   Direct link to the assignment on Canvas
*   **Scheduled Daily Notifications:** Sends a summary list of upcoming assignments daily at a configured time to a specific chat ID.
*   **Timezone Aware:** Correctly handles due dates and scheduling using configurable timezones (defaults to `America/New_York`).
*   **Asynchronous:** Built using `asyncio` and `python-telegram-bot`'s async capabilities for efficient operation.
*   **Configurable:** Uses environment variables for all sensitive information and settings (API keys, bot token, chat ID, schedule, model, etc.).
*   **Robust:** Includes error handling for Canvas API, Telegram API, AI calls, and configuration issues, with detailed logging.
*   **MarkdownV2 Formatting:** Properly escapes text for reliable Markdown rendering in Telegram messages.

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
    # If using Git
    git clone <your-repo-url>
    cd <your-repo-directory>
    # Or just save the script as agentic_bot_test_manus.py (or your preferred name)
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    Create a `requirements.txt` file with the following content:
    ```txt
    python-dotenv
    canvasapi
    python-telegram-bot[ext] # Get extensions like JobQueue
    ollama
    tzdata # Required by zoneinfo on some systems
    ```
    Then install:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Create a `.env` file in the same directory as the script (you can copy `.env.example` if you have one, or create it from scratch).
    *   **Edit the `.env` file** with your actual credentials and settings:
        ```dotenv
        # .env file
        # Canvas API settings
        CANVAS_API_URL="https://yourschool.instructure.com" # Replace with your Canvas URL
        CANVAS_API_TOKEN="YOUR_CANVAS_API_TOKEN"          # Replace with your token

        # Telegram Bot settings
        TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"      # Replace with your bot token
        TELEGRAM_CHAT_ID=""                               # OPTIONAL: Chat ID for scheduled messages (e.g., your user ID or a group ID)

        # Notification settings
        DAYS_AHEAD="7"                                    # Days ahead to check for assignments (default: 7)
        CHECK_HOUR="8"                                    # Hour (0-23) for scheduled check (default: 8)
        CHECK_MINUTE="0"                                  # Minute (0-59) for scheduled check (default: 0)
        APP_TIMEZONE="America/New_York"                   # Your local timezone (see https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

        # AI settings
        OLLAMA_MODEL="mistral"                            # Ollama model for estimation/summarization (default: mistral)
        ```
        *   Replace placeholders with your actual values.
        *   `TELEGRAM_CHAT_ID` is only required if you want the scheduled daily summaries.

    **Important:** Never commit your actual `.env` file to version control. Add `.env` to your `.gitignore` file if using Git.

5.  **Ensure Ollama is Running:**
    Make sure the Ollama service/application is running and the model specified in your `.env` file (`OLLAMA_MODEL`) is available locally (use `ollama list` to check).

## Running the Bot

1.  **Activate your virtual environment** (if you created one):
    ```bash
    source venv/bin/activate # Or venv\Scripts\activate on Windows
    ```
2.  **Run the Python script:**
    ```bash
    python agentic_bot_test_manus.py # Or the name you saved the script as
    ```

The script will:
1.  Load configuration and connect to Telegram.
2.  Register command and message handlers (`/start`, `/help`, `/check`, `details N`).
3.  If `TELEGRAM_CHAT_ID` is set, schedule the daily check based on `CHECK_HOUR`, `CHECK_MINUTE`, and `APP_TIMEZONE`.
4.  Start polling for updates from Telegram.

The bot needs to remain running in the foreground (or as a background process/service using tools like `screen`, `tmux`, or systemd) to respond to commands and execute the scheduled job.

## Interacting with the Bot

*   Find your bot on Telegram (using the username you set with @BotFather).
*   Send `/start` to initiate interaction. The bot will reply with a welcome message and your chat ID (useful for the `TELEGRAM_CHAT_ID` environment variable if you want scheduled messages sent directly to you).
*   Send `/help` to see available commands and usage instructions, including how to get assignment details.
*   Send `/check` to manually trigger a check for upcoming assignments. The result (a list with indices like `[1]`, `[2]`) will be sent to the chat where you issued the command.

### Getting Assignment Details

1.  Run the `/check` command. The bot will list upcoming assignments, each prefixed with an index number like `[1]`, `[2]`, etc.
2.  To see full details for a specific assignment, send a message containing `details N`, `info N`, or `assignment N`, where `N` is the index number from the list.
    *   Example: `details 1` or `info 3`
3.  The bot will reply with a detailed view of that assignment, including description, attachments, due dates, points, AI summary, and a link to Canvas.

**Important Notes on Details:**
*   The `details N` command works based on the **most recent assignment list** fetched by **your user** using `/check` in that specific chat.
*   If the bot restarts (and persistence is not configured), you'll need to run `/check` again before using `details N`.
*   You **cannot** use `details N` based on the list sent by the *scheduled* daily check, as that message is a broadcast and not tied to your user's specific context stored after `/check`.

## Troubleshooting

*   **Bot unresponsive:** Check script logs for errors. Ensure the script is running. Verify `TELEGRAM_BOT_TOKEN` is correct. Check internet connectivity.
*   **Canvas Errors:** Verify `CANVAS_API_URL` and `CANVAS_API_TOKEN`. Check Canvas status and token permissions.
*   **Ollama Errors:** Ensure Ollama service is running. Verify the `OLLAMA_MODEL` in `.env` is correct and pulled (`ollama list`). Check Ollama logs. Is Ollama accessible from where the script runs (e.g., network/firewall if not on the same machine)?
*   **Scheduled Messages Not Sending:** Ensure `TELEGRAM_CHAT_ID` is set correctly in `.env` and the script was restarted after setting it. Verify the bot has permission to send messages in that chat (especially for groups/channels). Check timezone settings (`APP_TIMEZONE`) and scheduled time (`CHECK_HOUR`, `CHECK_MINUTE`).
*   **`details N` command doesn't work:** Ensure you ran `/check` *first* in the same chat. Check if `N` is a valid number from the *most recent* `/check` list for your user. The command won't work with scheduled message lists or if the bot restarted without persistence since your last `/check`.
*   **MarkdownV2 Errors (`Can't parse entities...`):** The script tries to escape characters, but complex assignment names/descriptions might occasionally cause issues, especially in the detailed view. Check logs for `TelegramError` related to parsing. The error message might indicate the problematic character. Ensure the `escape_markdown_v2` function is correctly applied.
*   **`AttributeError: 'NoneType' object has no attribute 'message'` or similar on /check:** This can happen if the bot's internal context isn't set up correctly, often on the very first run or after a restart. Check logs for errors during startup, especially around `bot_data` population. Ensure configuration loads correctly.
*   **Windows Event Loop Policy:** The script includes a fix for `asyncio` on Windows. If you encounter `RuntimeError: Event loop is closed` on Windows, ensure this policy is being set correctly.
