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
from typing import List, Dict, Optional, Any, cast
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
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes,
    CallbackContext,
    MessageHandler, 
    filters
) # Bot framework
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
logging.getLogger("httpx") .setLevel(logging.WARNING)
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

# --- Custom Context Class ---
class CanvasContext(CallbackContext):
    """Custom context class with Canvas configuration."""
    def __init__(self, application, chat_id=None, user_id=None):
        super().__init__(application, chat_id, user_id)
        # These will be accessed from bot_data

# --- Helper Functions ---

def load_configuration() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    config = {}
    missing_vars = []
    for var_name, default_value in ENV_VARS.items():
        value = os.environ.get(var_name, default_value)
        if value is None and default_value is None:
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
        error_msg = f"Invalid numeric configuration: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Configuration loaded successfully: {config}")  # Add debug logging
    return config

def escape_markdown_v2(text: str) -> str:
    """
    Escapes characters for Telegram MarkdownV2 parse mode.
    All characters that need escaping in MarkdownV2 are properly handled.
    """
    if not text:
        return ""
        
    # Characters that need escaping in MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    
    # Escape backslash first to avoid double escaping
    text = text.replace('\\', '\\\\')
    
    # Escape all other special characters
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
        
    return text

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
    message_parts = [f"*Upcoming Assignments \\(Next {days_ahead} Days\\):*"]

    for a in assignments:
        due_date = a['due_date_local']
        assignment_name = escape_markdown_v2(a['assignment_name'])
        course_name_full = escape_markdown_v2(a['course_name'])
        # Try to shorten course name intelligently
        course_parts = course_name_full.split(' \\- ')
        course_short = course_parts[-1][:25] if len(course_parts) > 1 else course_name_full[:25]

        # Format day: Today, Tomorrow, DayName
        if due_date.date() == now_local.date():
            day_str = "*Today*"
        elif due_date.date() == (now_local + timedelta(days=1)).date():
            day_str = "*Tomorrow*"
        else:
            day_str = escape_markdown_v2(due_date.strftime("%A")) # Monday, Tuesday...

        # Format time: 5:00PM (no leading zero)
        # Use '#' for no padding on Windows, '-' for Unix-like systems
        format_spec = "%-I:%M%p" if os.name != 'nt' else "%#I:%M%p"
        time_str = escape_markdown_v2(due_date.strftime(format_spec).lower())

        # Add estimate if available
        est_str = ""
        if a.get('estimated_hours') is not None:
            rounded_hours = int(round(a['estimated_hours']))
            est_str = f" \\| Est: *{rounded_hours} hrs*" # Rounded to integer

        # Create link if URL exists
        link_text = "Link"
        if a['html_url']:
            link = f"[{link_text}]({a['html_url']})"
        else:
            link = "No Link"

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

async def start_command(update: Update, context: CanvasContext) -> None:
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

async def help_command(update: Update, context: CanvasContext) -> None:
    """Sends a help message when the /help command is issued."""
    logger.info(f"Received /help command from user {update.effective_user.username}")
    await update.message.reply_html(
        "Available commands:\n"
        "/start - Welcome message & show your Chat ID.\n"
        "/check - Manually check for assignments due soon.\n"
        "/help - Show this help message.\n\n"
        "I will also send a scheduled summary every morning if configured."
    )

async def check_assignments_command(update: Update, context: CanvasContext) -> None:
    """Handles the /check command to manually fetch and send assignments."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Add detailed logging at entry point
    logger.info(f"check_assignments_command started for user {user.username} in chat {chat_id}")
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        # Get config from bot_data
        config = context.application.bot_data.get('config')
        logger.info(f"Retrieved config from bot_data: {config is not None}")
        
        target_tz = context.application.bot_data.get('target_tz')
        logger.info(f"Retrieved timezone from bot_data: {target_tz is not None}")

        # Debug logging and validation
        if config is None:
            logger.error("Config missing from bot_data!")
            logger.error(f"Available keys in bot_data: {list(context.application.bot_data.keys())}")
            await context.bot.send_message(
                chat_id=chat_id, 
                text="⚠️ Internal error: Bot configuration missing\\. Please contact admin\\.", 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if target_tz is None:
            logger.error("Target timezone not found in application context!")
            await context.bot.send_message(
                chat_id=chat_id, 
                text="⚠️ Internal error: Bot timezone missing\\. Please contact admin\\.", 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        logger.debug(f"Config retrieved in check_assignments_command: {config}")

        # Safely get DAYS_AHEAD with fallback
        days_ahead = config.get('DAYS_AHEAD')
        if days_ahead is None:
            logger.error("'DAYS_AHEAD' key missing from config in bot_data! Using fallback.")
            days_ahead = 7
            await context.bot.send_message(
                chat_id=chat_id, 
                text="⚠️ Configuration warning: Using default 7 days ahead\\.", 
                parse_mode=ParseMode.MARKDOWN_V2
            )

        # Ensure integer type
        try:
            days_ahead = int(days_ahead)
        except (ValueError, TypeError):
            logger.error(f"Invalid non-integer value for DAYS_AHEAD in config: {days_ahead}")
            await context.bot.send_message(
                chat_id=chat_id, 
                text="⚠️ Configuration error\\. Using default 7 days ahead\\.", 
                parse_mode=ParseMode.MARKDOWN_V2
            )
            days_ahead = 7

        await update.message.reply_text(
            f"🔍 Checking Canvas for assignments due in the next {days_ahead} days\\.\\.\\.", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await context.bot.send_chat_action(chat_id=chat_id, action='typing')

        assignments = await fetch_upcoming_assignments(config, target_tz)
        message_text = format_assignment_message(assignments, days_ahead, target_tz)

        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
        logger.info(f"Sent assignment list to chat {chat_id} via /check command.")

    except (CanvasException, ConnectionError) as e:
        error_msg = escape_markdown_v2(str(e))
        logger.error(f"Canvas API or connection error during /check: {e}")
        await context.bot.send_message(
            chat_id=chat_id, 
            text=f"⚠️ Error connecting to Canvas: {error_msg}", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except TelegramError as e:
        logger.error(f"Telegram error sending /check response: {e}")
        # Try to send a simpler message if there was a formatting error
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Error formatting message\\. Please try again\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except:
            # If even that fails, try plain text
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Error formatting message. Please try again."
            )
    except Exception as e:
        logger.exception("Unhandled error during /check command")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Something went wrong\\. Please try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
async def scheduled_assignment_check(context: CanvasContext) -> None:
    """Job function for the scheduler to send the daily summary."""
    job = context.job
    config = context.application.bot_data['config']
    target_tz = context.application.bot_data['target_tz']
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

def run_bot():
    """
    Main function to run the bot. This is a non-async wrapper around the async main function
    to properly handle event loops, especially on Windows.
    """
    # Set Windows event loop policy if on Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
        logger.info("Windows event loop policy set.")
    
    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the main function in the event loop
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught. Shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        # Clean up
        loop.close()
        logger.info("Event loop closed. Script execution finished.")

async def main() -> None:
    """Sets up the application and runs the bot using run_polling."""
    logger.info("Starting bot setup...")
    application: Optional[Application] = None

    try:
        # 1. Load config needed for token
        config = load_configuration()
        bot_token = config['TELEGRAM_BOT_TOKEN']
        logger.info("Initial configuration loaded.")

        # 2. Validate bot token
        logger.info("Validating Telegram Bot Token...")
        temp_bot = Bot(token=bot_token)
        await temp_bot.get_me()
        logger.info("Telegram Bot Token is valid.")

        # 3. Create custom context types
        logger.info("Setting up custom context types...")
        canvas_context_types = ContextTypes(context=CanvasContext)

        # 4. Build the application with custom context types
        logger.info("Building application instance with custom context types...")
        application = Application.builder().token(bot_token).context_types(canvas_context_types).build()
        logger.info(f"Application instance built (id: {id(application)})")

        # 5. Store configuration in bot_data (which is mutable)
        try:
            target_tz = ZoneInfo(config['APP_TIMEZONE'])
            application.bot_data['config'] = config
            application.bot_data['target_tz'] = target_tz
            logger.info("Populated application.bot_data with config and timezone.")
            logger.info(f"Current application bot_data keys: {list(application.bot_data.keys())}")
        except Exception as e:
             logger.critical(f"Failed to populate bot_data: {e}", exc_info=True)
             raise RuntimeError("Failed to set up application context") from e

        # 6. Get scheduling info from config
        check_hour = config['CHECK_HOUR']
        check_minute = config['CHECK_MINUTE']
        app_timezone_str = config['APP_TIMEZONE']
        target_chat_id = config['TELEGRAM_CHAT_ID']
        target_tz = application.bot_data['target_tz']
        logger.info("Configuration for scheduling retrieved.")

        # 7. Register Command Handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check", check_assignments_command))
        logger.info("Command handlers registered.")

        # 8. Schedule daily check
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

        # 9. Run the bot using run_polling
        logger.info("Starting bot polling using application.run_polling()...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Bot is running. Press Ctrl+C to stop.")
        # Keep the bot running until interrupted
        # This is a simple way to keep the main task alive
        while True:
            await asyncio.sleep(1)
            
    except (EnvironmentError, ValueError, RuntimeError, KeyError) as e:
        logger.critical(f"Setup or configuration error: {e}", exc_info=True)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt. Shutting down...")
    except Exception as e:
        logger.critical(f"Unhandled error during bot execution: {e}", exc_info=True)
    finally:
        # Proper shutdown sequence
        if application:
            logger.info("Shutting down application...")
            try:
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                logger.info("Application shutdown complete.")
            except Exception as e:
                logger.error(f"Error during application shutdown: {e}")

# --- Main execution block ---
if __name__ == "__main__":
    run_bot()
