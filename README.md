# Canvas Assignment Notifier

## Overview

The Canvas Assignment Notifier is a Python script that connects to the Canvas API to fetch upcoming assignments and sends SMS notifications using an email-to-SMS gateway. This project is designed to help students stay informed about their assignments and deadlines.

## Features

- Fetches upcoming assignments from the Canvas API.
- Sends SMS notifications for assignments due within a specified timeframe.
- Configurable settings for notification timing and recipient information.

## Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone https://github.com/yourusername/canvas-assignment-notifier.git
   cd canvas-assignment-notifier
   ```

2. **Create a virtual environment (optional but recommended):**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install the required dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**

   Create a `.env` file in the root directory based on the `.env.example` template and fill in your credentials:

   ```properties
   EMAIL_SENDER=your_email@example.com
   EMAIL_PASSWORD=your_email_password
   SMS_EMAIL=your_phone_number@sms_gateway.com
   SMTP_SERVER=smtp.example.com
   SMTP_PORT=587
   CANVAS_API_URL=https://your.instructure.com
   CANVAS_API_TOKEN=your_canvas_api_token
   DAYS_AHEAD=7
   CHECK_HOUR=8
   CHECK_MINUTE=0
   ```

5. **Run the script:**

   ```bash
   python src/canvas_messenger.py
   ```

## Usage

The script will check for upcoming assignments daily at the specified hour and minute. You will receive SMS notifications for any assignments due within the configured number of days ahead.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.
