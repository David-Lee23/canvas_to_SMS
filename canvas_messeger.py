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
import ollama 
import re  # Add this with other imports at the top
import time  # Add with other imports


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

def estimate_time_via_ai(
    course_name: str,
    assignment_name: str,
    due_date: datetime,
    description: str,
    url: Optional[str] = None
) -> Optional[float]:
    """
    Use AI (Mistral via Ollama) to estimate assignment completion time with full context.
    Returns estimated hours as float, or None if estimation fails.
    """
    if not description:
        return None
        
    try:
        # Build rich context prompt
        prompt = (
            f"You're an AI assistant helping a college student estimate how long each assignment will take.\n\n"
            f"Here is an assignment:\n"
            f"Course: {course_name}\n"
            f"Title: {assignment_name}\n"
            f"Due Date: {due_date.strftime('%A, %B %d, %Y at %I:%M %p')}\n"
        )

        if url:
            prompt += f"Assignment URL: {url}\n"

        prompt += f"\nDescription:\n{description}\n\n"
        prompt += "Based on this, estimate how many hours the student will likely need to complete it. "
        prompt += "Respond with only a single number like '2' or '3.5'."

        response = ollama.chat(
            model="mistral",
            messages=[{"role": "user", "content": prompt}]
        )

        text = response['message']['content'].strip()
        logging.debug(f"AI response for time estimate: {text}")

        match = re.search(r"(\d+(\.\d+)?)", text)
        if match:
            estimated_hours = float(match.group(1))
            return round(estimated_hours, 1)

        logging.warning(f"No valid number found in AI response: {text}")
        return None

    except Exception as e:
        logging.warning(f"AI time estimate failed: {e}")
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
            assignments = course.get_assignments()
            for assignment in assignments:
                due_datetime_utc = parse_iso_datetime(getattr(assignment, 'due_at', None))

                if due_datetime_utc and now_est <= due_datetime_utc <= due_threshold_est:
                    description = getattr(assignment, 'description', assignment.name)
                    estimated_hours = estimate_time_via_ai(
                        course_name=getattr(course, 'name', 'Unknown Course'),
                        assignment_name=getattr(assignment, 'name', 'Unnamed Assignment'),
                        due_date=due_datetime_utc,
                        description=description,
                        url=getattr(assignment, 'html_url', None)
                    )
                    
                    upcoming_assignments.append({
                        'course_name': getattr(course, 'name', 'Unknown Course'),
                        'assignment_name': getattr(assignment, 'name', 'Unnamed Assignment'),
                        'due_date_utc': due_datetime_utc,
                        'description': description,
                        'html_url': getattr(assignment, 'html_url', '#'),
                        'estimated_hours': estimated_hours
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
    Create a plain-text SMS-safe message listing upcoming assignments with time estimates.
    Days are shown as: Today, Tomorrow, Monday, Tuesday, etc.
    """
    if not assignments:
        return f"No assignments due in next {days_ahead} days"

    message_lines = [f"Due in next {days_ahead} days:"]
    
    now_est = datetime.now(ZoneInfo("America/New_York"))

    for a in assignments:
        due_date = a['due_date_utc']
        
        # Format the day
        if due_date.date() == now_est.date():
            day_str = "Today"
        elif due_date.date() == (now_est + timedelta(days=1)).date():
            day_str = "Tomorrow"
        else:
            day_str = due_date.strftime("%A")  # Full day name (Monday, Tuesday, etc.)
            
        # Format the time
        time_str = due_date.strftime("%I:%M%p").lower().lstrip('0')
        
        # Get course name
        course = a['course_name'].split(" - ")[-1][:20]
        
        # Add time estimate if available
        est_str = f" | Est: {a['estimated_hours']}hrs" if a.get('estimated_hours') else ""
        
        # Combine into final format
        line = f"{a['assignment_name']}\n{course} - {day_str} @ {time_str}{est_str}"
        message_lines.append(line)

    full_message = "\n\n".join(message_lines)
    
    # Truncate if needed
    max_len = 1000
    if len(full_message) > max_len:
        truncated = full_message[:max_len]
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
    Sends SMS notifications via email gateway with smart chunking.
    - Splits messages into SMS-safe chunks (~150 chars)
    - Keeps header with first assignments
    - Preserves assignment formatting
    """
    if not message_body:
        logging.warning("Message body is empty. Skipping email.")
        return False

    # Split on double newlines to keep assignments together
    assignments = message_body.split("\n\n")
    header = assignments[0]  # "Due in next X days:"
    assignment_chunks = assignments[1:] if len(assignments) > 1 else []
    
    # Start first chunk with header
    chunks = []
    current_chunk = [header]  # Initialize with header
    current_length = len(header)
    
    for assignment in assignment_chunks:
        # Calculate length including newlines
        assignment_len = len(assignment) + 2  # +2 for "\n\n"
        
        # If this assignment would exceed SMS limit, start new chunk
        if current_length + assignment_len > 150:  # Leave room for (1/N) prefix
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            current_chunk = [assignment]
            current_length = len(assignment)
        else:
            current_chunk.append(assignment)
            current_length += assignment_len
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    try:
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(sender_email, password)

            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                # Add part number if multiple chunks
                if total_chunks > 1:
                    chunk = f"({i}/{total_chunks})\n{chunk}"

                msg = MIMEText(chunk)
                msg["From"] = sender_email
                msg["To"] = sms_email
                msg["Subject"] = ""  # Empty subject for SMS gateways

                # Debug logging to see chunk contents
                logging.debug(f"Chunk {i}/{total_chunks} content:\n{chunk}")

                server.sendmail(sender_email, sms_email, msg.as_string())
                logging.info(f"Sent SMS part {i}/{total_chunks} to {sms_email}")
                
                # Add slight delay between chunks to avoid carrier throttling
                if i < total_chunks:
                    time.sleep(1)

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