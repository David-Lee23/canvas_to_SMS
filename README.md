# Assignment Notifier Script

This script connects to the Canvas LMS API to fetch upcoming assignments and sends SMS notifications via an email-to-SMS gateway. It includes AI-based time estimation for assignments using the Mistral model via Ollama.

## Features
- Fetches assignments due within a configurable number of days (default: 7).
- Uses timezone-aware datetime handling (EST) for accurate due date comparisons.
- Estimates completion time for each assignment using AI (Mistral via Ollama).
- Sends SMS notifications with smart chunking for longer messages.
- Schedules daily checks using APScheduler.
- Includes robust error handling and logging.

## Prerequisites
1. **Python 3.9+**: Required for `zoneinfo` and other features.
2. **Canvas API Token**: Obtain from your Canvas account settings.
3. **SMTP Credentials**: An email account with SMTP access (e.g., Gmail).
4. **SMS Gateway Email**: Your phone number's SMS gateway (e.g., `1234567890@vtext.com` for Verizon).
5. **Ollama**: Install Ollama and the Mistral model for AI time estimation (see [Ollama Setup](#ollama-setup)).

## Setup

### 1. Clone the Repository
```bash
git clone <repository-url>
cd <repository-directory>
