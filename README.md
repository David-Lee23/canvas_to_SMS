# Canvas Assignment Notifier with AI Time Estimation

This script connects to the Canvas LMS API to fetch upcoming assignments for your courses, uses a local AI model (via Ollama) to estimate the time required for each assignment, and sends a consolidated list via SMS (using an email-to-SMS gateway) on a daily schedule.

## Features

*   **Fetches Upcoming Assignments:** Retrieves assignments due within a configurable number of days from the Canvas API.
*   **AI Time Estimation:** Uses Ollama with the `mistral` model (or potentially others) to analyze assignment descriptions and estimate completion time.
*   **Timezone Aware:** Correctly handles due dates using timezone information (defaults to EST/EDT - America/New_York).
*   **Daily Notifications:** Sends an SMS notification at a configurable time each day.
*   **Smart SMS Formatting:** Formats the notification clearly, showing the day (Today, Tomorrow, Weekday), time, course, and estimated hours. Chunks long messages intelligently for SMS delivery.
*   **Configurable:** Uses environment variables for all sensitive information and settings (API keys, email/SMS details, schedule time, lookahead days).
*   **Robust:** Includes error handling and logging.
*   **Scheduled Execution:** Uses `APScheduler` to run automatically at the configured time.

## Prerequisites

*   **Python 3.9+:** Required for the `zoneinfo` module.
*   **Canvas API Access Token:** You need to generate an API token from your Canvas account settings.
*   **Email Account:** An email account (like Gmail, Outlook, etc.) that can be used to send emails via SMTP. You might need an "App Password" if using Gmail with 2FA.
*   **SMS Gateway Address:** You need the email address format for your mobile carrier's email-to-SMS gateway (e.g., `1234567890@vtext.com` for Verizon, `1234567890@txt.att.net` for AT&T). Search online for "[Your Carrier] email to sms gateway".
*   **Ollama Installed and Running:** You need Ollama installed and running locally.
*   **Ollama Model Pulled:** You need to have pulled the AI model specified in the script (default is `mistral`). You can do this with `ollama pull mistral`.

## Setup

1.  **Clone the Repository (or download the script):**
    ```bash
    git clone <your-repo-url> # Or just save the script as e.g., notifier.py
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
        *   `EMAIL_SENDER`: Your sending email address.
        *   `EMAIL_PASSWORD`: Your email account password or App Password.
        *   `SMS_EMAIL`: Your phone number combined with your carrier's SMS gateway (e.g., `phonenumber@carrier.domain`).
        *   `SMTP_SERVER`: Your email provider's SMTP server address.
        *   `SMTP_PORT`: Your email provider's SMTP port (usually 587 for TLS).
        *   `CANVAS_API_URL`: The base URL for your institution's Canvas instance (e.g., `https://canvas.instructure.com` or `https://youruni.instructure.com`).
        *   `CANVAS_API_TOKEN`: Your generated Canvas API token.
        *   `DAYS_AHEAD`: (Optional) How many days ahead to check for assignments (default: 7).
        *   `CHECK_HOUR`: (Optional) The hour (0-23) to run the check in EST/EDT (default: 8 for 8 AM).
        *   `CHECK_MINUTE`: (Optional) The minute (0-59) to run the check (default: 0).

    **Important:** Never commit your actual `.env` file to version control. Add `.env` to your `.gitignore` file.

5.  **Ensure Ollama is Running:**
    Make sure the Ollama service/application is running and the `mistral` model (or your chosen model) is available.

## Running the Script

Simply run the Python script from your terminal (ensure your virtual environment is active if you created one):

```bash
python your_script_name.py # Replace with the actual filename, e.g., notifier.py
