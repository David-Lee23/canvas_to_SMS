# canvas_telegram_bot.py

"""
Canvas Assignment Notifier Bot (Telegram Version)

Connects to the Canvas API to fetch upcoming assignments, uses AI to estimate
completion times, and delivers notifications via a Telegram bot. Allows for
both scheduled daily summaries and on-demand checks via commands.
"""
import ollama
import os
import logging
from datetime import datetime, timedelta, timezone, time  # Added time import
from typing import List, Dict, Optional, Any
import re
import asyncio # Needed for async operations with the bot library
from asyncio import WindowsSelectorEventLoopPolicy
import html # Needed for escaping HTML in descriptions

# --- Third-Party Libraries ---
from canvasapi import Canvas
from canvasapi.exceptions import CanvasException
from dotenv import load_dotenv
from zoneinfo import ZoneInfo # Modern timezone handling
from telegram import Update, Bot # Core Telegram bot components
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters # Bot framework
from telegram.error import TelegramError
from telegram.constants import ParseMode # Import ParseMode constant

# --- Configuration ---

# Load environment variables from .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Set higher logging level for httpx used by telegram-python-bot
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__) # Use a specific logger for this module

# Environment variable names and defaults
ENV_VARS = {
    "CANVAS_API_URL": None,
    "CANVAS_API_TOKEN": None,
    "TELEGRAM_BOT_TOKEN": None,
    "TELEGRAM_CHAT_ID": None, # Required for scheduled messages
    "DAYS_AHEAD": "7",
    "CHECK_HOUR": "8",
    "CHECK_MINUTE": "0",
    "APP_TIMEZONE": "America/New_York", # Default timezone
    "OLLAMA_MODEL": "mistral", # Default Ollama model
}

# --- Helper Functions ---

def load_configuration() -> Dict[str, str]:
    """Load configuration from environment variables."""
    config = {}
    missing_vars = []
    for var_name, default_value in ENV_VARS.items():
        value = os.environ.get(var_name, default_value)
        if value is None and default_value is None: # Only error if no default is set
             missing_vars.append(var_name)
        else:
            config[var_name] = value if value is not None else default_value

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise EnvironmentError(error_msg)

    # Validate numeric values
    try:
        config["DAYS_AHEAD"] = int(config["DAYS_AHEAD"])
        config["CHECK_HOUR"] = int(config["CHECK_HOUR"])
        config["CHECK_MINUTE"] = int(config["CHECK_MINUTE"])
        if not (0 <= config["CHECK_HOUR"] <= 23 and 0 <= config["CHECK_MINUTE"] <= 59):
            raise ValueError("Invalid hour or minute")
    except ValueError as e:
        error_msg = f"Invalid numeric configuration (DAYS_AHEAD, CHECK_HOUR, CHECK_MINUTE): {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate timezone
    try:
        ZoneInfo(config["APP_TIMEZONE"])
    except Exception as e:
        error_msg = f"Invalid APP_TIMEZONE: {config['APP_TIMEZONE']}. Error: {e}"
        logger.error(error_msg)
        # Fallback to UTC if invalid timezone provided
        logger.warning(f"Falling back to UTC timezone.")
        config["APP_TIMEZONE"] = "UTC"


    # Validate TELEGRAM_CHAT_ID (basic check)
    if not config["TELEGRAM_CHAT_ID"].lstrip('-').isdigit():
         logger.warning(f"TELEGRAM_CHAT_ID ('{config['TELEGRAM_CHAT_ID']}') doesn't look like a standard chat ID. Scheduled messages might fail if incorrect.")


    logger.info("Configuration loaded successfully.")
    return config

def escape_markdown_v2(text: str) -> str:
    """Escapes characters for Telegram MarkdownV2 parse mode."""
    # Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def parse_iso_datetime(date_string: Optional[str], target_tz: ZoneInfo) -> Optional[datetime]:
    """
    Parse an ISO 8601 formatted string into a timezone-aware datetime object
    in the target timezone. Handles 'Z' suffix and naive datetimes (assuming UTC).
    """
    if not date_string:
        return None
    try:
        # Handle 'Z' for UTC indication
        if (date_string.endswith('Z')):
            date_string = date_string[:-1] + '+00:00'

        dt = datetime.fromisoformat(date_string)

        # If datetime object is naive (no timezone), assume it's UTC
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to the target timezone
        return dt.astimezone(target_tz)
    except ValueError:
        logger.warning(f"Could not parse date string: {date_string}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing date string '{date_string}': {e}")
        return None

def estimate_time_via_ai(
    course_name: str,
    assignment_name: str,
    due_date: datetime,
    description: Optional[str],
    url: Optional[str],
    ollama_model: str
) -> Optional[float]:
    """Use AI (Ollama) to estimate assignment completion time."""
    if not description: # Cannot estimate without description
        logger.debug(f"Skipping AI estimate for '{assignment_name}': No description provided.")
        return None

    # Basic HTML stripping and cleaning for the AI prompt
    clean_description = re.sub('<[^<]+?>', '', description) # Remove HTML tags
    clean_description = html.unescape(clean_description) # Decode HTML entities
    clean_description = clean_description.strip()

    # Limit description length to avoid overly long prompts
    max_desc_len = 1000
    if len(clean_description) > max_desc_len:
         clean_description = clean_description[:max_desc_len] + "..."

    if not clean_description: # If description was only HTML/empty after cleaning
        logger.debug(f"Skipping AI estimate for '{assignment_name}': Cleaned description is empty.")
        return None

    try:
        prompt = (
            f"You are an AI assistant helping a college student estimate assignment completion time.\n\n"
            f"Assignment Details:\n"
            f"- Course: {course_name}\n"
            f"- Title: {assignment_name}\n"
            f"- Due: {due_date.strftime('%A, %b %d, %Y at %I:%M %p %Z')}\n"
        )
        if url:
            prompt += f"- URL: {url}\n"
        prompt += f"\nDescription:\n{clean_description}\n\n"
        prompt += "Estimate the hours needed to complete this assignment. Consider typical college student workload. "
        prompt += "Respond ONLY with a single number (e.g., '2', '3.5', '0.5')."

        logger.debug(f"Sending prompt to Ollama for '{assignment_name}'")
        response = ollama.chat(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response['message']['content'].strip()
        logger.debug(f"AI raw response for '{assignment_name}': {text}")

        # More robust number extraction
        match = re.search(r"(\d+(\.\d+)?)", text)
        if match:
            estimated_hours = float(match.group(1))
            logger.info(f"AI estimated {estimated_hours:.1f} hrs for '{assignment_name}'")
            return round(estimated_hours, 1)
        else:
            logger.warning(f"Could not extract numeric estimate from AI response for '{assignment_name}': '{text}'")
            return None

    except Exception as e:
        logger.error(f"AI time estimation failed for '{assignment_name}': {e}", exc_info=False) # exc_info=False to avoid huge tracebacks for common API errors
        return None

# --- Canvas Interaction ---

async def fetch_upcoming_assignments(
    config: Dict[str, Any], target_tz: ZoneInfo
) -> List[Dict[str, Any]]:
    """Fetch assignments from Canvas due within the configured days_ahead."""
    canvas_api_url = config["CANVAS_API_URL"]
    canvas_api_token = config["CANVAS_API_TOKEN"]
    days_ahead = config["DAYS_AHEAD"]
    ollama_model = config["OLLAMA_MODEL"]

    try:
        # Run Canvas API calls in a separate thread to avoid blocking asyncio event loop
        canvas = await asyncio.to_thread(Canvas, canvas_api_url, canvas_api_token)
        # Test connection by getting user profile
        await asyncio.to_thread(canvas.get_current_user)
        logger.info(f"Connected to Canvas instance at {canvas_api_url}")
    except CanvasException as e:
        logger.error(f"Failed to connect to Canvas API: {e}")
        raise # Re-raise critical error
    except Exception as e:
        logger.error(f"Unexpected error during Canvas setup: {e}")
        raise

    upcoming_assignments: List[Dict[str, Any]] = []
    now_local = datetime.now(target_tz)
    due_threshold_local = now_local + timedelta(days=days_ahead)

    try:
        # Get active courses in a non-blocking way
        courses_paginated = await asyncio.to_thread(
            canvas.get_courses,
            enrollment_state='active',
            include=['term']
        )
        # Convert paginated list to a simple list for easier iteration
        courses = await asyncio.to_thread(list, courses_paginated)
        logger.info(f"Found {len(courses)} active courses.")

    except CanvasException as e:
        logger.error(f"Failed to retrieve courses from Canvas: {e}")
        return [] # Return empty list if courses fail

    # Process courses concurrently (optional, depends on number of courses)
    # For simplicity, we'll process sequentially using asyncio.to_thread for API calls
    for course in courses:
        course_name = getattr(course, 'name', f'Unknown Course {course.id}')
        try:
            logger.debug(f"Processing course: {course_name}")
            # Fetch assignments for the course in a non-blocking way
            assignments_paginated = await asyncio.to_thread(
                course.get_assignments,
                 bucket='upcoming' # More efficient filter if API supports it well
                 # Alternatively, filter manually after fetching all
            )
            assignments = await asyncio.to_thread(list, assignments_paginated)

            for assignment in assignments:
                assignment_name = getattr(assignment, 'name', 'Unnamed Assignment')
                due_datetime_local = parse_iso_datetime(getattr(assignment, 'due_at', None), target_tz)

                # Check if assignment is due within the desired window
                # Use lock_at if due_at is missing? Optional.
                if due_datetime_local and now_local <= due_datetime_local <= due_threshold_local:
                    logger.debug(f"Found relevant assignment: '{assignment_name}' in '{course_name}' due {due_datetime_local}")
                    description_html = getattr(assignment, 'description', None)
                    html_url = getattr(assignment, 'html_url', None)

                    # Run AI estimation in non-blocking way
                    estimated_hours = await asyncio.to_thread(
                         estimate_time_via_ai,
                         course_name=course_name,
                         assignment_name=assignment_name,
                         due_date=due_datetime_local,
                         description=description_html,
                         url=html_url,
                         ollama_model=ollama_model
                    )

                    upcoming_assignments.append({
                        'course_name': course_name,
                        'assignment_name': assignment_name,
                        'due_date_local': due_datetime_local, # Store localized datetime
                        'description': description_html, # Keep original description if needed elsewhere
                        'html_url': html_url,
                        'estimated_hours': estimated_hours
                    })
        except CanvasException as e:
            logger.error(f"Canvas API error fetching assignments for course '{course_name}': {e}")
            # Continue with the next course
        except Exception as e:
            logger.error(f"Unexpected error processing course '{course_name}': {e}", exc_info=True)
            # Continue with the next course

    # Sort assignments by due date
    upcoming_assignments.sort(key=lambda x: x['due_date_local'])

    logger.info(f"Found {len(upcoming_assignments)} assignments due within the next {days_ahead} days.")
    return upcoming_assignments


# --- Message Formatting ---

def format_assignment_message(
    assignments: List[Dict[str, Any]], days_ahead: int, target_tz: ZoneInfo
) -> str:
    """Format the list of assignments into a MarkdownV2 message for Telegram."""
    if not assignments:
        return f"✅ No assignments due in the next {days_ahead} days\\." # Escape the period

    now_local = datetime.now(target_tz)
    message_parts = [f"*Upcoming Assignments (Next {days_ahead} Days):*"]

    for a in assignments:
        due_date = a['due_date_local']
        assignment_name = escape_markdown_v2(a['assignment_name'])
        course_name_full = escape_markdown_v2(a['course_name'])
        # Try to shorten course name intelligently
        course_parts = course_name_full.split(' - ')
        course_short = escape_markdown_v2(course_parts[-1][:25]) # Take last part, limit length


        # Format day: Today, Tomorrow, DayName
        if due_date.date() == now_local.date():
            day_str = "*Today*"
        elif due_date.date() == (now_local + timedelta(days=1)).date():
            day_str = "*Tomorrow*"
        else:
            day_str = escape_markdown_v2(due_date.strftime("%A")) # Monday, Tuesday...

        # Format time: 5:00PM (no leading zero)
        time_str = escape_markdown_v2(due_date.strftime("%-I:%M%p").lower()) # Use '-' for no padding on Linux/macOS

        # Add estimate if available
        est_str = ""
        if a.get('estimated_hours') is not None:
            est_str = f" \\| Est: *{a['estimated_hours']:.1f} hrs*" # Bold estimate

        # Create link if URL exists
        link = f"[Link]({escape_markdown_v2(a['html_url'])})" if a['html_url'] else "No Link"
        link = escape_markdown_v2(link) if not a['html_url'] else link # Escape "No Link" text only


        # Combine parts
        # Using MarkdownV2 requires escaping ., -, etc.
        line = (
            f"📝 *{assignment_name}*\n"
            f"   ↳ Course: _{course_short}_\n"
            f"   ↳ Due: {day_str} at {time_str}{est_str}\n"
            f"   ↳ {link}"
        )
        message_parts.append(line)

    # Join with double newline, respecting Telegram's message length limits implicitly
    # Telegram bot library handles splitting if needed, but good practice to keep reasonable
    return "\n\n".join(message_parts)


# --- Telegram Bot Commands and Logic ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"Received /start command from user {user.username} (ID: {user.id}) in chat {chat_id}")

    # Log the chat ID - useful for setting TELEGRAM_CHAT_ID in .env
    print(f"--- User {user.username} started bot in Chat ID: {chat_id} ---")

    await update.message.reply_html(
        f"Hello {user.mention_html()}! 👋\n\n"
        f"I'm your Canvas Assignment Notifier Bot.\n\n"
        f"I can send you daily summaries of upcoming assignments with AI time estimates.\n\n"
        f"Available commands:\n"
        f"/check - Manually check for assignments due soon.\n"
        f"/help - Show this help message again.\n\n"
        f"Your Chat ID for scheduled messages is: `{chat_id}` (add this to your `.env` file if needed)."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    logger.info(f"Received /help command from user {update.effective_user.username}")
    await update.message.reply_html(
        "Available commands:\n"
        "/start - Welcome message & show your Chat ID.\n"
        "/check - Manually check for assignments due soon.\n"
        "/help - Show this help message.\n\n"
        "I will also send a scheduled summary every morning if configured."
    )

async def check_assignments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /check command to manually fetch and send assignments."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    logger.info(f"Received /check command from user {user.username} in chat {chat_id}")
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        config = context.application.user_data['config']
        target_tz = context.application.user_data['target_tz']
        days_ahead = config['DAYS_AHEAD']

        await update.message.reply_text(f"🔍 Checking Canvas for assignments due in the next {days_ahead} days...", parse_mode=ParseMode.MARKDOWN_V2)
        await context.bot.send_chat_action(chat_id=chat_id, action='typing') # Keep typing indicator

        assignments = await fetch_upcoming_assignments(config, target_tz)
        message_text = format_assignment_message(assignments, days_ahead, target_tz)

        await context.bot.send_message(
             chat_id=chat_id,
             text=message_text,
             parse_mode=ParseMode.MARKDOWN_V2,
             disable_web_page_preview=True # Avoid large link previews
        )
        logger.info(f"Sent assignment list to chat {chat_id} via /check command.")

    except (CanvasException, ConnectionError) as e:
         logger.error(f"Canvas API or connection error during /check: {e}")
         await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error connecting to Canvas: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)
    except TelegramError as e:
         logger.error(f"Telegram error sending /check response: {e}")
         # Don't try to send another message if the first one failed potentially
    except Exception as e:
        logger.exception("Unhandled error during /check command") # Log full traceback
        await context.bot.send_message(chat_id=chat_id, text=" Bummer, something went wrong while checking assignments\\. Please try again later or check the logs\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def scheduled_assignment_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job function for the scheduler to send the daily summary."""
    job = context.job
    config = context.application.user_data['config']
    target_tz = context.application.user_data['target_tz']
    chat_id = config['TELEGRAM_CHAT_ID'] # Get configured chat ID for scheduled messages
    days_ahead = config['DAYS_AHEAD']

    logger.info(f"Running scheduled assignment check for chat ID {chat_id}...")

    try:
        assignments = await fetch_upcoming_assignments(config, target_tz)

        # Only send if there are assignments, or customize message
        if assignments:
            message_text = format_assignment_message(assignments, days_ahead, target_tz)
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
            logger.info(f"Sent scheduled assignment summary to chat ID {chat_id}.")
        else:
            # Optional: Send a "nothing due" message or just log
            logger.info(f"No assignments due in the next {days_ahead} days. No scheduled message sent to {chat_id}.")
            # Example: Send confirmation message (uncomment if desired)
            # await context.bot.send_message(
            #     chat_id=chat_id,
            #     text=f"✅ Good news\\! No assignments due in the next {days_ahead} days\\.",
            #     parse_mode=ParseMode.MARKDOWN_V2
            # )

    except (CanvasException, ConnectionError) as e:
         logger.error(f"Canvas API or connection error during scheduled check: {e}")
         # Optionally send an error message to the chat
         try:
             await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Scheduled check failed: Error connecting to Canvas\\.", parse_mode=ParseMode.MARKDOWN_V2)
         except Exception as send_e:
             logger.error(f"Failed to send Canvas error notification to Telegram: {send_e}")
    except TelegramError as e:
        logger.error(f"Telegram error during scheduled check: {e}")
        # Cannot notify user via Telegram if Telegram itself fails
    except Exception as e:
        logger.exception("Unhandled error during scheduled assignment check")
        # Optionally send an error message to the chat
        try:
             await context.bot.send_message(chat_id=chat_id, text=" Bummer, the scheduled assignment check failed unexpectedly\\. Check the logs\\.", parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as send_e:
             logger.error(f"Failed to send general error notification to Telegram: {send_e}")

async def post_init(application: Application) -> None:
    """Initialize application with configuration and timezone after creation.
    
    Args:
        application: The telegram bot application instance to initialize
    """
    try:
        # Load and validate configuration
        config = load_configuration()
        target_tz = ZoneInfo(config['APP_TIMEZONE'])
        
        # Store config and timezone in application context
        application.user_data['config'] = config
        application.user_data['target_tz'] = target_tz
        
        logger.info(f"Application initialized with timezone {config['APP_TIMEZONE']}")
    
    except (EnvironmentError, ValueError) as e:
        logger.error(f"Configuration error during post_init: {e}", exc_info=True)
        raise RuntimeError(f"Failed to load configuration in post_init: {e}") from e
    
    except Exception as e:
        logger.error(f"Unexpected error during post_init: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error in post_init: {e}") from e

# --- Main Execution Logic ---

async def main() -> None:
    """Sets up the application, starts polling, and handles graceful shutdown."""
    logger.info("Starting bot setup...")
    application: Optional[Application] = None  # Define application here for broader scope in try/except/finally

    try:
        # 1. Load initial configuration (use this directly in main)
        temp_config = load_configuration()
        bot_token = temp_config['TELEGRAM_BOT_TOKEN']
        logger.info("Initial configuration loaded for setup.")

        # 2. Validate bot token
        logger.info("Validating Telegram Bot Token...")
        temp_bot = Bot(token=bot_token)
        await temp_bot.get_me()
        logger.info("Telegram Bot Token is valid.")

        # 3. Build the application
        logger.info("Building application instance...")
        application = Application.builder().token(bot_token).post_init(post_init).build()
        logger.info("Application instance built successfully.")

        # 4. Use temp_config directly instead of retrieving from user_data
        check_hour = temp_config['CHECK_HOUR']
        check_minute = temp_config['CHECK_MINUTE']
        app_timezone_str = temp_config['APP_TIMEZONE']
        target_chat_id = temp_config['TELEGRAM_CHAT_ID']
        target_tz = ZoneInfo(app_timezone_str)
        logger.info("Configuration for scheduling retrieved.")

        # 5. Register Command Handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check", check_assignments_command))
        logger.info("Command handlers registered.")

        # 6. Schedule daily check
        if target_chat_id and target_chat_id.lstrip('-').isdigit():
            logger.info("Setting up scheduled job...")
            application.job_queue.run_daily(
                scheduled_assignment_check,
                time=time(hour=check_hour, minute=check_minute, tzinfo=target_tz),
                name="daily_assignment_check",
                job_kwargs={"misfire_grace_time": 3600}
            )
            logger.info(f"Scheduled assignment check for chat ID {target_chat_id} daily at {check_hour:02d}:{check_minute:02d} ({app_timezone_str}).")
        else:
            logger.warning("TELEGRAM_CHAT_ID not set or invalid - Scheduled daily notifications are DISABLED.")

        # --- Explicit Initialization and Start ---
        logger.info("Initializing application components...")
        await application.initialize()

        logger.info("Starting application components (handlers, job queue)...")
        await application.start()

        logger.info("Starting polling...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        logger.info("Bot is now running. Press Ctrl+C to stop.")

        # Keep the main coroutine alive until interrupted
        stop_event = asyncio.Event()
        await stop_event.wait()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Received stop signal (KeyboardInterrupt/SystemExit). Initiating shutdown...")

    except (EnvironmentError, ValueError, RuntimeError, KeyError) as e:
        logger.critical(f"Initialization or configuration error: {e}", exc_info=True)

    except Exception as e:
        logger.critical(f"Unhandled error during bot execution: {e}", exc_info=True)

    finally:
        logger.info("Shutdown sequence starting...")
        if application:
            # Check if updater exists before trying to stop it
            if application.updater:
                logger.info("Stopping polling...")
                await application.updater.stop()

            # Check if application components are running before stopping them
            if application.running:
                logger.info("Stopping application components...")
                await application.stop()

            logger.info("Shutting down application...")
            await application.shutdown()
            logger.info("Application shutdown complete.")
        else:
            logger.info("Application object not created, skipping shutdown steps.")

# --- Main execution block ---
if os.name == 'nt':
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    logger.info("Windows event loop policy set.")

try:
    asyncio.run(main())
except KeyboardInterrupt:
    logger.info("KeyboardInterrupt caught in outer block (likely during early setup).")
except Exception as e:
    logger.critical(f"Fatal error at top level: {e}", exc_info=True)
finally:
    logger.info("Script execution finished.")