# Optimized Assignment Notifier Script

"""
Assignment Notifier Script (Optimized)

Connects to the Canvas API to fetch upcoming assignments and uses the Twilio
API to send an SMS notification.

Improvements:
- Uses timezone-aware datetime objects for accurate comparisons.
- Parses ISO 8601 date strings robustly.
- Makes the 'days ahead' lookup configurable via environment variable.
- Adds type hints for better readability and maintainability.
- Enhanced error handling and logging.

Setup:
1. Install required libraries:
   pip install twilio canvasapi python-dotenv apscheduler  # Added python-dotenv for easier local dev

2. Create a `.env` file in the same directory with your credentials:
   EMAIL_SENDER=your_email@example.com
   EMAIL_PASSWORD=your_email_password
   SMS_EMAIL=your_phone_number@sms_gateway.com
   SMTP_SERVER=smtp.example.com
   SMTP_PORT=587
   CANVAS_API_URL=https://your.instructure.com
   CANVAS_API_TOKEN=your_canvas_api_token
   DAYS_AHEAD=7  # Optional: default is 7
   CHECK_HOUR=8  # Optional: default is 8 AM
   CHECK_MINUTE=0  # Optional: default is on the hour

3. Run the script:
   python your_script_name.py
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from canvasapi import Canvas
from canvasapi.exceptions import CanvasException
from dotenv import load_dotenv # For easier local development with .env file
from zoneinfo import ZoneInfo  # Add this import for timezone handling
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import smtplib
from email.mime.text import MIMEText

# --- Configuration ---

# Load environment variables from .env file if it exists
load_dotenv()

# Environment variable names
ENV_VARS = {
    "EMAIL_SENDER": None,
    "EMAIL_PASSWORD": None,
    "SMS_EMAIL": None,
    "SMTP_SERVER": None,
    "SMTP_PORT": None,
    "CANVAS_API_URL": None,
    "CANVAS_API_TOKEN": None,
    "DAYS_AHEAD": "7",  # Default value if not set
    "CHECK_HOUR": "8",     # Default to 8 AM
    "CHECK_MINUTE": "0",   # Default to on the hour
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Helper Functions ---

def load_configuration() -> Dict[str, str]:
    """Load configuration from environment variables."""
    config = {}
    missing_vars = []
    for var_name, default_value in ENV_VARS.items():
        value = os.environ.get(var_name, default_value)
        if value is None:
            missing_vars.append(var_name)
        else:
            config[var_name] = value

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(error_msg)
        raise EnvironmentError(error_msg)

    # Validate DAYS_AHEAD is an integer
    try:
        int(config["DAYS_AHEAD"])
    except ValueError:
        error_msg = f"Invalid value for DAYS_AHEAD: '{config['DAYS_AHEAD']}'. Must be an integer."
        logging.error(error_msg)
        raise ValueError(error_msg)

    # Validate time settings
    try:
        hour = int(config.get("CHECK_HOUR", "8"))
        minute = int(config.get("CHECK_MINUTE", "0"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        config["CHECK_HOUR"] = str(hour)
        config["CHECK_MINUTE"] = str(minute)
    except ValueError:
        error_msg = f"Invalid time settings. Hour must be 0-23, minute must be 0-59"
        logging.error(error_msg)
        raise ValueError(error_msg)

    logging.info("Configuration loaded successfully.")
    return config

def parse_iso_datetime(date_string: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 formatted string into a timezone-aware datetime object (EST).
    Handles potential missing 'Z' or other variations if possible.
    Returns None if parsing fails or input is None.
    """
    if not date_string:
        return None
    try:
        # Parse the date string to UTC first
        if (date_string.endswith('Z')):
            date_string = date_string[:-1] + '+00:00'
        dt = datetime.fromisoformat(date_string)
        # If the parsed datetime has no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Convert to EST
        return dt.astimezone(ZoneInfo("America/New_York"))
    except ValueError:
        logging.warning(f"Could not parse date string: {date_string}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error parsing date string '{date_string}': {e}")
        return None


# --- Core Logic ---

def fetch_upcoming_assignments(
    canvas_api_url: str, canvas_api_token: str, days_ahead: int
) -> List[Dict[str, Any]]:
    """
    Connect to Canvas and fetch assignments due within the next 'days_ahead' days.
    Returns a list of dictionaries, each containing details about an assignment.
    """
    try:
        canvas = Canvas(canvas_api_url, canvas_api_token)
        logging.info(f"Connected to Canvas instance at {canvas_api_url}")
    except CanvasException as e:
        logging.error(f"Failed to connect to Canvas API: {e}")
        raise  # Re-raise the exception to stop the script

    upcoming_assignments: List[Dict[str, Any]] = []
    now_est = datetime.now(ZoneInfo("America/New_York"))
    due_threshold_est = now_est + timedelta(days=days_ahead)

    try:
        # Using include[]=submission retrieves submission status which might be useful later
        # Adjust parameters as needed (e.g., enrollment_type='student')
        courses = canvas.get_courses(enrollment_state='active', include=['term'])
        logging.info(f"Found {len(list(courses))} active courses.")
    except CanvasException as e:
        logging.error(f"Failed to retrieve courses from Canvas: {e}")
        return [] # Return empty list if courses can't be fetched

    for course in courses:
        try:
            logging.debug(f"Processing course: {getattr(course, 'name', 'N/A')} (ID: {course.id})")
            # Fetch assignments for the course. Consider using parameters like 'bucket=upcoming'
            # if it suits your needs, but manual filtering gives more date control.
            assignments = course.get_assignments()
            for assignment in assignments:
                due_datetime_utc = parse_iso_datetime(getattr(assignment, 'due_at', None))

                # Consider only assignments with valid due dates within the threshold
                if due_datetime_utc and now_est <= due_datetime_utc <= due_threshold_est:
                    upcoming_assignments.append({
                        'course_name': getattr(course, 'name', 'Unknown Course'),
                        'assignment_name': getattr(assignment, 'name', 'Unnamed Assignment'),
                        'due_date_utc': due_datetime_utc,
                        'description': getattr(assignment, 'description', "No description."),
                        'html_url': getattr(assignment, 'html_url', '#') # Link to assignment
                    })
        except CanvasException as e:
            # Log error for specific course but continue with others
            logging.error(f"Error fetching assignments for course '{getattr(course, 'name', course.id)}': {e}")
        except Exception as e:
            # Catch unexpected errors during course processing
            logging.error(f"Unexpected error processing course '{getattr(course, 'name', course.id)}': {e}")


    # Sort assignments by due date
    upcoming_assignments.sort(key=lambda x: x['due_date_utc'])

    logging.info(f"Found {len(upcoming_assignments)} assignments due within the next {days_ahead} days.")
    return upcoming_assignments


def format_notification_message(assignments: List[Dict[str, Any]], days_ahead: int) -> str:
    """
    Create a plain-text SMS-safe message listing upcoming assignments.
    """
    if not assignments:
        return f"No assignments due in next {days_ahead} days"

    message_lines = [f"Due in next {days_ahead} days:"]

    for a in assignments:
        # Format date more concisely
        due_str = a['due_date_utc'].strftime("%m/%d %I:%M%p").lower()
        
        # Shorten course name to make it more compact
        course = a['course_name'].split(" - ")[-1][:20]
        
        # Format each assignment on two lines for clarity
        line = f"{a['assignment_name']}\n{course} - Due {due_str}"
        message_lines.append(line)

    # Join with double newlines for better readability on mobile
    full_message = "\n\n".join(message_lines)

    # Conservative SMS length limit
    max_len = 1000
    if len(full_message) > max_len:
        truncated = full_message[:max_len]
        # Find last complete assignment entry
        last_break = truncated.rstrip().rfind("\n\n")
        if last_break > 0:
            full_message = truncated[:last_break] + "\n\n[More assignments not shown]"
        else:
            full_message = truncated + "\n[Truncated]"

    return full_message


def send_sms_via_email(
    smtp_server: str,
    port: int,
    sender_email: str,
    password: str,
    sms_email: str,
    message_body: str
) -> bool:
    """
    Sends an SMS via email-to-text gateway with SMS-safe formatting.
    """
    if not message_body:
        logging.warning("Message body is empty. Skipping email.")
        return False

    try:
        msg = MIMEText(message_body)
        msg["From"] = sender_email
        msg["To"] = sms_email
        # Subject removed to prevent formatting issues

        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(sender_email, password)
            server.sendmail(sender_email, sms_email, msg.as_string())

        logging.info(f"SMS email sent successfully to {sms_email}")
        return True

    except Exception as e:
        logging.error(f"Failed to send SMS via email: {e}")
        return False


# --- Main Execution ---

def check_assignments() -> None:
    """Wrapper function for the assignment checking logic"""
    try:
        config = load_configuration()
        days_ahead = int(config["DAYS_AHEAD"])

        logging.info("Starting scheduled assignment check...")

        assignments = fetch_upcoming_assignments(
            config["CANVAS_API_URL"], 
            config["CANVAS_API_TOKEN"], 
            days_ahead
        )

        if assignments is None:
            logging.error("Could not retrieve assignments. Skipping notification.")
            return

        message_body = format_notification_message(assignments, days_ahead)
        if not message_body.startswith("✅"):
            success = send_sms_via_email(
                smtp_server=config["SMTP_SERVER"],
                port=int(config["SMTP_PORT"]),
                sender_email=config["EMAIL_SENDER"],
                password=config["EMAIL_PASSWORD"],
                sms_email=config["SMS_EMAIL"],
                message_body=message_body
            )
            if not success:
                logging.warning("SMS notification failed to send.")
        else:
            logging.info("No upcoming assignments to notify about.")

    except Exception as e:
        logging.exception("Error during scheduled check")

def main() -> None:
    """Set up and run the scheduler"""
    try:
        config = load_configuration()
        hour = int(config["CHECK_HOUR"])
        minute = int(config["CHECK_MINUTE"])
        
        scheduler = BlockingScheduler()
        scheduler.add_job(
            check_assignments,
            trigger=CronTrigger(
                hour=hour,
                minute=minute,
                timezone=ZoneInfo("America/New_York")
            ),
            id='assignment_check',
            name='Daily Assignment Check',
            misfire_grace_time=3600  # Allow job to run up to 1 hour late if system was down
        )

        logging.info(f"Scheduler started. Will check assignments daily at {hour:02d}:{minute:02d} EST")
        
        # Run once immediately on startup
        check_assignments()
        
        # Start the scheduler
        scheduler.start()

    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped by user")
    except Exception as e:
        logging.exception("Fatal error in scheduler")
        raise

if __name__ == "__main__":
    main()