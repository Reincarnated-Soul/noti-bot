import os
import asyncio
import time
import aiohttp

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.storage import storage, save_website_data
from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, debug_print, DEV_MODE, SINGLE_MODE
from bot.utils import get_base_url, format_phone_number, format_time, get_selected_numbers_for_buttons

def create_unified_keyboard(data, website=None):
    """
    Create a unified keyboard layout based on website type and state

    Parameters:
    - data: Dictionary containing:
        - site_id: The site ID
        - updated: Boolean indicating if the numbers were just updated
        - type: 'single' or 'multiple'
        - is_initial_run: Boolean for multiple type sites
        - number: For single type sites
        - numbers: List of numbers for multiple type sites
        - url: Website URL
    - website: Website object (optional, used for fallback)

    Returns:
    - InlineKeyboardMarkup with appropriate buttons
    """
    debug_print(f"[DEBUG] create_unified_keyboard - received data: {data}")

    site_id = data.get("site_id")
    updated = data.get("updated", False)
    website_type = data.get("type")
    is_initial_run = data.get("is_initial_run", False)
    url = data.get("url", "")

    debug_print(f"[DEBUG] create_unified_keyboard - initial values: site_id: {site_id}, type: {website_type}, updated: {updated}, is_initial_run: {is_initial_run}")

    # If website object is provided, use it for fallback values for everything EXCEPT the updated state
    # The updated state should be determined by the caller
    if website:
        debug_print(f"[DEBUG] create_unified_keyboard - website object provided for site_id: {site_id}")

        # Get button_updated state from website object (for logging only)
        button_updated = getattr(website, 'button_updated', False)
        debug_print(f"[DEBUG] create_unified_keyboard - website object has button_updated: {button_updated}")
        debug_print(f"[DEBUG] create_unified_keyboard - using caller-provided updated state: {updated}")

        # If is_initial_run not provided in data, use website.is_initial_run
        if "is_initial_run" not in data and hasattr(website, 'is_initial_run'):
            is_initial_run = website.is_initial_run
            debug_print(f"[DEBUG] create_unified_keyboard - using website's is_initial_run: {is_initial_run}")

        # Only use website's type if no type was provided in data
        if not website_type and hasattr(website, "type"):
            website_type = website.type
            debug_print(f"[DEBUG] create_unified_keyboard - using website's type: {website_type}")

        if not url and hasattr(website, "url"):
            url = website.url
            debug_print(f"[DEBUG] create_unified_keyboard - using website's url: {url}")
    else:
        debug_print(f"[DEBUG] create_unified_keyboard - no website object provided")

    debug_print(f"[DEBUG] create_unified_keyboard - after website processing: site_id: {site_id}, type: {website_type}, updated: {updated}, is_initial_run: {is_initial_run}")

    # Ensure we have a valid URL
    if not url:
        url = get_base_url() or ""
        debug_print(f"[DEBUG] create_unified_keyboard - using base_url: {url}")

    # Create buttons based on website type
    if website_type == "single":
        debug_print(f"[DEBUG] create_unified_keyboard - creating single type keyboard")
        number = data.get("number", "")
        debug_print(f"[DEBUG] create_unified_keyboard - initial number: {number}")
        if not number and website and hasattr(website, "last_number"):
            number = website.last_number
            debug_print(f"[DEBUG] create_unified_keyboard - using website's last_number: {number}")
        # Format the phone number - only use the formatted number, not the flag info
        formatted_number = format_phone_number(number)
        if isinstance(formatted_number, tuple):
            formatted_number = formatted_number[0]
        update_text = "✅ Updated Number" if updated else "🔄 Update Number"
        debug_print(f"[DEBUG] create_unified_keyboard - update_text: {update_text}, callback_data: update_{number}_{site_id}")
        # Always restore the full layout after animation
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_{number}_{site_id}"),
                    InlineKeyboardButton(text=update_text, callback_data=f"update_{number}_{site_id}")
                ],
                [
                    InlineKeyboardButton(text="🔪 Split Number", callback_data=f"split_{number}_{site_id}"),
                    InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{site_id}")
                ],
                [
                    InlineKeyboardButton(text="🌐 Visit Webpage", url=f"{url}/number/{number}" if number else url)
                ]
            ]
        )
        debug_print(f"[DEBUG] create_unified_keyboard - created single type keyboard with {len(keyboard.inline_keyboard)} rows")
        return keyboard
    else:  # Multiple type
        debug_print(f"[DEBUG] create_unified_keyboard - creating multiple type keyboard")
        numbers = data.get("numbers", [])
        if not numbers and website:
            if hasattr(website, "latest_numbers") and website.latest_numbers:
                numbers = website.latest_numbers
                debug_print(f"[DEBUG] create_unified_keyboard - using website's latest_numbers: {len(numbers)} numbers")
            elif hasattr(website, "last_number") and website.last_number:
                numbers = [website.last_number]
                debug_print(f"[DEBUG] create_unified_keyboard - using website's last_number as single item: {numbers}")
        update_text = "✅ Updated Numbers" if updated else "🔄 Update Numbers"

        # Initial run layout - always use last_number
        if is_initial_run:
            debug_print(f"[DEBUG] create_unified_keyboard - using initial run layout for multiple type")
            # For initial run, we specifically want to use last_number, not latest_numbers
            display_number = None

            # First priority: Use last_number if available
            if website and hasattr(website, "last_number") and website.last_number is not None:
                display_number = website.last_number
                debug_print(f"[DEBUG] create_unified_keyboard - using website.last_number for initial run: {display_number}")

            # Second priority: Use first number from numbers array (passed in data)
            elif numbers and len(numbers) > 0:
                first_number = numbers[0]
                if isinstance(first_number, str) and first_number.startswith('+'):
                    first_number = first_number[1:]
                display_number = first_number
                debug_print(f"[DEBUG] create_unified_keyboard - using first number from numbers array: {display_number}")

            # Third priority: Use first number from website.latest_numbers if available
            elif website and hasattr(website, "latest_numbers") and website.latest_numbers and len(website.latest_numbers) > 0:
                first_number = website.latest_numbers[0]
                if isinstance(first_number, str) and first_number.startswith('+'):
                    first_number = first_number[1:]
                display_number = first_number
                debug_print(f"[DEBUG] create_unified_keyboard - using first number from website.latest_numbers: {display_number}")

            # Fallback if no number is available
            else:
                display_number = "unknown"
                debug_print(f"[DEBUG] create_unified_keyboard - no number available, using 'unknown'")

            # Format the phone number - only use the formatted number, not the flag info
            formatted_number = format_phone_number(display_number)
            if isinstance(formatted_number, tuple):
                formatted_number = formatted_number[0]
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=formatted_number, callback_data=f"number_{display_number}_{site_id}")],
                    [InlineKeyboardButton(text=update_text, callback_data=f"update_multi_{site_id}"),
                     InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{site_id}")],
                    [InlineKeyboardButton(text="🌐 Visit Webpage", url=url)]
                ]
            )
            debug_print(f"[DEBUG] create_unified_keyboard - created initial run multiple type keyboard with {len(keyboard.inline_keyboard)} rows")
            return keyboard
        else:
            # Subsequent run - arrange buttons 2 per row from selected_numbers
            debug_print(f"[DEBUG] create_unified_keyboard - using regular layout for multiple type with {len(numbers)} numbers")
            buttons = []

            # Create buttons for numbers, 2 per row
            current_row = []
            for raw_number in numbers:
                # Format the phone number - only use the formatted number, not the flag info
                formatted_number = format_phone_number(raw_number)
                if isinstance(formatted_number, tuple):
                    formatted_number = formatted_number[0]
                current_row.append(InlineKeyboardButton(text=formatted_number, callback_data=f"number_{raw_number}_{site_id}"))

                # When we have 2 buttons in a row, add it to buttons and start a new row
                if len(current_row) == 2:
                    buttons.append(current_row)
                    current_row = []

            # Add any remaining buttons (if we have an odd number)
            if current_row:
                buttons.append(current_row)

            # Add control buttons
            buttons.append([
                InlineKeyboardButton(text=update_text, callback_data=f"update_multi_{site_id}"),
                InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{site_id}")
            ])

            # Add website link button
            buttons.append([InlineKeyboardButton(text="🌐 Visit Webpage", url=url)])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            debug_print(f"[DEBUG] create_unified_keyboard - created multiple type keyboard with {len(keyboard.inline_keyboard)} rows and {len(numbers)} numbers, 2 per row")
            return keyboard

def get_buttons(number, updated=False, site_id=None):
    """Legacy function for backward compatibility"""
    debug_print(f"[DEBUG] get_buttons - called with number: {number}, updated: {updated}, site_id: {site_id}")

    website = storage["websites"].get(site_id)
    if not website:
        debug_print(f"[DEBUG] get_buttons - website not found for site_id: {site_id}, returning None")
        return None

    debug_print(f"[DEBUG] get_buttons - found website for site_id: {site_id}, type: {getattr(website, 'type', 'unknown')}")

    data = {
        "type": "single",
        "number": number,
        "site_id": site_id,
        "updated": updated,
        "url": getattr(website, 'url', get_base_url() or "")
    }

    debug_print(f"[DEBUG] get_buttons - created data: {data}")
    keyboard = create_unified_keyboard(data, website)
    debug_print(f"[DEBUG] get_buttons - returning keyboard with {len(keyboard.inline_keyboard) if keyboard else 0} rows")
    return keyboard

def get_multiple_buttons(numbers, site_id=None):
    """Legacy function for backward compatibility"""
    debug_print(f"[DEBUG] get_multiple_buttons - called with numbers: {numbers}, site_id: {site_id}")

    website = storage["websites"].get(site_id)
    if not website:
        debug_print(f"[DEBUG] get_multiple_buttons - website not found for site_id: {site_id}, returning None")
        return None

    debug_print(f"[DEBUG] get_multiple_buttons - found website for site_id: {site_id}, type: {getattr(website, 'type', 'unknown')}")
    debug_print(f"[DEBUG] get_multiple_buttons - using website.is_initial_run: {website.is_initial_run}")

    # Reset the button_updated state for new notifications only on subsequent runs
    # This ensures that each notification starts with a fresh state
    if not website.is_initial_run:
        # Only reset for subsequent runs (not initial run)
        website.button_updated = False
        debug_print(f"[DEBUG] get_multiple_buttons - reset button_updated state to False for subsequent run")

    data = {
        "type": "multiple",
        "numbers": numbers,
        "site_id": site_id,
        "updated": False,  # Default to not updated
        "url": getattr(website, 'url', get_base_url() or ""),
        "is_initial_run": website.is_initial_run  # Use website.is_initial_run directly
    }

    debug_print(f"[DEBUG] get_multiple_buttons - created data: {data}")
    keyboard = create_unified_keyboard(data, website)
    debug_print(f"[DEBUG] get_multiple_buttons - returning keyboard with {len(keyboard.inline_keyboard) if keyboard else 0} rows")
    return keyboard

async def send_notification(bot, data):
    try:
        chat_id = os.getenv("CHAT_ID")

        if not chat_id:
            return

        site_id = data.get("site_id")
        website = storage["websites"].get(site_id)
        
        if not website:
            return

        # Determine if this is a single or multiple number notification based on website type
        is_multiple = website.type == "multiple"
        flag_url = data.get("flag_url")
        website_url = website.url if website else None

        # Use website's is_initial_run property as the single source of truth
        debug_print(f"[DEBUG] send_notification - website.is_initial_run: {website.is_initial_run}")

        # More descriptive button_created_using value
        button_created_using = "none" if not website else ("last_number (initial run)" if website.is_initial_run else "selected_numbers_for_buttons (subsequent run)") if is_multiple else "last_number"
        
        # Attempt to fetch the flag from the Flagpedia API first
        country_code = None
        flag_info = None

        if website and hasattr(website, 'last_number') and website.last_number:
            # Use last_number directly - simpler approach without type checking
            number_to_check = website.last_number
            
            formatted_number, flag_info = format_phone_number(number_to_check, get_flag=True, website_url=website_url)
            if flag_info and "iso_code" in flag_info:
                iso_code = flag_info["iso_code"].lower()
                flagpedia_url = f"https://flagcdn.com/w320/{iso_code}.png"
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        async with session.get(flagpedia_url) as response:
                            response.raise_for_status()
                            flag_url = flagpedia_url
                            debug_print(f"[DEBUG] send_notification - Flag fetched from Flagpedia API: {flagpedia_url}")
                except aiohttp.ClientError as e:
                    debug_print(f"[ERROR] send_notification - Flagpedia API request failed: {e}")

            if formatted_number and formatted_number.startswith("+"):
                country_code = formatted_number.split(" ")[0].replace("+", "")
                
        # Use flag from flag_info as fallback
        if not flag_url and flag_info:
            flag_url = flag_info["primary"]
        
        print(f"🎯 Notification Send Successfully 📧")
        print(f"{{ Notification Message - initial values:\n  [\n    site_id = {site_id},\n    website_type = {website.type if website else None},\n    country_code = +{country_code},\n    Flag_URL = {flag_url},\n    button_count = {len(website.latest_numbers) if website and hasattr(website,'latest_numbers') else 0},\n    button_created_using = {button_created_using},\n    settings = {website.settings if website and hasattr(website,'settings') else None},\n    updated = {data.get('updated', False)},\n    visit_url = {website_url}\n  ]\n}}")

        if not is_multiple:
            # Single number notification
            number = data.get("number")

            if not number:
                return

            message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖"
            keyboard = get_buttons(number, site_id=site_id)

            try:
                sent_message = await bot.send_photo(
                    chat_id,
                    photo=flag_url,
                    caption=message,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

            except Exception as e:
                debug_print(f"[ERROR] send_notification - failed to send message to {chat_id}: {e}")
                return

            # Store notification data
            storage["latest_notification"] = {
                "message_id": sent_message.message_id,
                "number": number,
                "flag_url": flag_url,
                "site_id": site_id,
                "multiple": False,
                "is_initial_run": website.is_initial_run  # Use website.is_initial_run directly
            }

            # Handle repeat notification if enabled
            if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None:
                await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id, flag_url)

        else:
            # Multiple numbers notification
            numbers = data.get("numbers", [])

            if not numbers:
                return

            debug_print(f"[DEBUG] send_notification - Type: {website.type}, is_initial_run: {website.is_initial_run}, numbers count: {len(numbers)}")

            if website.is_initial_run:
                # On first run, send notification with the last_number
                # Make sure we have a last_number
                if not hasattr(website, 'last_number') or website.last_number is None:
                    if numbers and len(numbers) > 0:                        
                        first_num = numbers[0]
                        if isinstance(first_num, str) and first_num.startswith('+'):
                            first_num = first_num[1:]
                        try:
                            website.last_number = int(first_num)
                            # Initialize previous_last_number to match last_number on first run
                            website.previous_last_number = website.last_number
                            debug_print(f"[DEBUG] send_notification - setting last_number from first number: {website.last_number}")
                            await save_website_data(site_id)
                        except (ValueError, TypeError):
                            debug_print(f"[DEBUG] send_notification - could not convert {first_num} to last_number")
                            # Use the first number as-is if conversion fails
                            website.last_number = first_num
                            # Initialize previous_last_number to match last_number on first run
                            website.previous_last_number = website.last_number
                            await save_website_data(site_id)

                # Get display number - either last_number or first number from latest_numbers
                display_number = None
                if hasattr(website, 'last_number') and website.last_number is not None:
                    display_number = website.last_number
                    debug_print(f"[DEBUG] send_notification - using last_number: {display_number}")
                elif hasattr(website, 'latest_numbers') and website.latest_numbers:
                    # Extract from the first element of latest_numbers
                    first_num = website.latest_numbers[0]
                    if isinstance(first_num, str) and first_num.startswith('+'):
                        first_num = first_num[1:]
                    display_number = first_num
                    debug_print(f"[DEBUG] send_notification - using first element from latest_numbers: {display_number}")
                else:
                    display_number = "unknown"
                    debug_print(f"[DEBUG] send_notification - no number available, using 'unknown'")

                notification_message = f"🎁 *New Numbers Added* 🎁\n\n`+{display_number}` check it out! 💖"
                debug_print(f"[DEBUG] send_notification - sending notification with display_number: {display_number}")

                # Use get_multiple_buttons with website.is_initial_run
                keyboard = get_multiple_buttons([f"+{display_number}"], site_id=site_id)
                
                try:
                    sent_message = await bot.send_photo(
                        chat_id,
                        photo=flag_url,
                        caption=notification_message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )

                except Exception as e:
                    debug_print(f"[ERROR] send_notification - error sending message: {e}")
                    return  # Exit early since we can't proceed without a sent message

                # Store notification data
                storage["latest_notification"] = {
                    "message_id": sent_message.message_id,
                    "numbers": numbers,
                    "flag_url": flag_url,
                    "site_id": site_id,
                    "multiple": True,
                    "is_initial_run": website.is_initial_run  # Use website.is_initial_run directly
                }
            else:
                # For subsequent runs, always use selected numbers 
                previous_last_number = website.previous_last_number if hasattr(website, "previous_last_number") else website.last_number  # Use previous_last_number if available
                print(f"[INFO] send_notification - For subsequent runs, previous_last_number: {previous_last_number}")

                # Use the helper function to get selected numbers
                selected_numbers_for_buttons = get_selected_numbers_for_buttons(numbers, previous_last_number)
                print(f"[INFO] send_notification - selected_numbers_for_buttons: {selected_numbers_for_buttons}")

                # Update last_number with the new first number
                if numbers and len(numbers) > 0:
                    # Store the current last_number as previous_last_number before updating
                    website.previous_last_number = website.last_number

                    first_num = numbers[0]
                    if isinstance(first_num, str) and first_num.startswith('+'):
                        first_num = first_num[1:]
                    try:
                        website.last_number = int(first_num)
                    except (ValueError, TypeError):
                        website.last_number = first_num
                
                # Check if SINGLE_MODE is enabled
                if SINGLE_MODE and selected_numbers_for_buttons:
                    debug_print(f"[DEBUG] send_notification - SINGLE_MODE enabled, sending {len(selected_numbers_for_buttons)} individual notifications")
                    
                    # Send individual notifications for each number
                    for idx, number in enumerate(selected_numbers_for_buttons):
                        individual_message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖"
                        
                        # Create individual keyboard for this number
                        individual_data = {
                            "type": website.type,  # Use website's type
                            "numbers": [number],  # Pass single number in numbers array
                            "site_id": site_id,
                            "updated": False,
                            "url": website_url
                        }
                        
                        individual_keyboard = create_unified_keyboard(individual_data, website)
                        
                        # Send individual notification
                        await bot.send_photo(
                            chat_id=CHAT_ID,
                            photo=flag_url,
                            caption=individual_message,
                            parse_mode="Markdown",
                            reply_markup=individual_keyboard
                        )
                        
                        # Add a small delay between notifications
                        await asyncio.sleep(1)
                    
                    return  # Exit after sending individual notifications
                    
                else:
                    #Group all selected numbers in single notification
                    notification_message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(selected_numbers_for_buttons)}` numbers, check them out! 💖"
                    debug_print(f"[DEBUG] send_notification - using {len(selected_numbers_for_buttons)} numbers for subsequent run: {selected_numbers_for_buttons}")

                    # Use get_multiple_buttons with website.is_initial_run
                    keyboard = get_multiple_buttons(selected_numbers_for_buttons, site_id=site_id)

                    try:
                        sent_message = await bot.send_photo(
                            chat_id,
                            photo=flag_url,
                            caption=notification_message,
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )

                    except Exception as e:
                        debug_print(f"[ERROR] send_notification - error sending message: {e}")
                        return  # Exit early since we can't proceed without a sent message

                    # Store notification data
                    storage["latest_notification"] = {
                        "message_id": sent_message.message_id,
                        "numbers": numbers,
                        "flag_url": flag_url,
                        "site_id": site_id,
                        "multiple": True,
                        "is_initial_run": website.is_initial_run  # Use website.is_initial_run directly
                    }

                    # Handle repeat notification if enabled
                    if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None:
                        await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id, flag_url)

    except Exception as e:
        debug_print(f"[ERROR] send_notification - error: {e}")
        return

async def update_message_with_countdown(bot, message_id, number_or_numbers, flag_url, site_id):
    """
    Update the notification message with a countdown for the given site_id (works for both single and multiple numbers)
    """
    interval = storage["repeat_interval"]
    if interval is None:
        return

    website = storage["websites"].get(site_id)
    if not website:
        return

    # Determine if this is a multiple or single type site
    is_multiple = website.type == "multiple"
    last_update_time = time.time()
    current_message = None
    countdown_active = True
    website_url = website.url if website else None

    while countdown_active:
        try:
            current_time = time.time()
            time_left = int(interval - (current_time - last_update_time))
            if time_left < 0:
                time_left = 0
            formatted_time = format_time(time_left)

            if is_multiple:
                # Multiple numbers message
                # Get is_initial_run state from website or latest_notification
                is_initial_run = website.is_initial_run
                if not is_initial_run and "latest_notification" in storage and storage["latest_notification"]:
                    if storage["latest_notification"].get("site_id") == site_id:
                        is_initial_run = storage["latest_notification"].get("is_initial_run", False)

                if is_initial_run:
                    # For initial run, display one number (last_number or latest_numbers[0])
                    display_number = None
                    if hasattr(website, 'last_number') and website.last_number is not None:
                        display_number = f"+{website.last_number}"
                        numbers = [display_number]
                    elif hasattr(website, 'latest_numbers') and website.latest_numbers:
                        numbers = [website.latest_numbers[0]]
                    else:
                        numbers = []

                    notification_message = f"🎁 *New Numbers Added* 🎁\n\n`{numbers[0] if numbers else 'Unknown'}` check it out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
                else:
                    # For subsequent runs, use selected_numbers_for_buttons approach
                    numbers = number_or_numbers if isinstance(number_or_numbers, list) else (website.latest_numbers or [])

                    # Get selected numbers using the shared helper function
                    if numbers:
                        # Get previous_last_number for comparison
                        previous_last_number = getattr(website, 'previous_last_number', website.last_number)

                        # Use the helper function to get selected numbers
                        selected_numbers = get_selected_numbers_for_buttons(numbers, previous_last_number)
                    else:
                        selected_numbers = []

                    notification_message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(selected_numbers)}` numbers, check them out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
                    numbers = selected_numbers

                # Use get_multiple_buttons which will use website.is_initial_run
                keyboard = get_multiple_buttons(numbers, site_id=site_id)
            else:
                # Single number message
                number = number_or_numbers if isinstance(number_or_numbers, str) else website.last_number

                notification_message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
                # Use get_buttons instead of creating keyboard data manually
                keyboard = get_buttons(number, site_id=site_id)

            await bot.edit_message_caption(
                chat_id=CHAT_ID,
                message_id=message_id,
                caption=notification_message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            await asyncio.sleep(1)
            # Check if repeat_interval changed or task cancelled
            if storage["repeat_interval"] != interval or not storage["active_countdown_tasks"].get(site_id):
                countdown_active = False
        except Exception as e:
            countdown_active = False

async def add_countdown_to_latest_notification(bot, interval_seconds, site_id,flag_url):
    try:
        latest = storage["latest_notification"]
        if latest["message_id"] and latest["site_id"] == site_id:
            message_id = latest["message_id"]
            if latest.get("multiple"):
                number_or_numbers = latest.get("numbers")
            else:
                number_or_numbers = latest.get("number")

            # Cancel any previous countdown for this site
            if site_id in storage["active_countdown_tasks"]:
                storage["active_countdown_tasks"][site_id].cancel()

            countdown_task = asyncio.create_task(
                update_message_with_countdown(bot, message_id, number_or_numbers, flag_url, site_id)
            )
            storage["active_countdown_tasks"][site_id] = countdown_task

    except Exception as e:
        print(f"[ERROR] add_countdown_to_latest_notification - error: {e}")


async def repeat_notification(bot):
    """Send a repeat notification if enabled"""
    try:
        # Check if we have an active notification
        if "latest_notification" in storage and storage["latest_notification"]:
            # Get the notification details
            message_id = storage["latest_notification"].get("message_id")
            site_id = storage["latest_notification"].get("site_id", "site_1")
            multiple = storage["latest_notification"].get("multiple", False)

            # Update the message with the new countdown
            await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id,storage["latest_notification"].get("flag_url"))

    except Exception as e:
        debug_print(f"[ERROR] repeat_notification - error: {e}")
