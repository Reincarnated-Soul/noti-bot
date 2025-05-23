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
    Create a unified keyboard layout for both single and multiple number notifications
    """
    keyboard = []
    site_id = data.get("site_id")
    updated = data.get("updated", False)
    website_type = data.get("type", "single")
    url = data.get("url")
    
    if website_type == "single":
        # Single type keyboard
        number = data.get("number")
        if not number:
            return None
            
        # Format the number using format_phone_number
        formatted_number, _ = format_phone_number(number, get_flag=True)
            
        # First row - Copy and Update buttons
        row = []
        copy_button = InlineKeyboardButton(
            text="📋 Copy Number",
            callback_data=f"copy_{number}_{site_id}"
        )
        row.append(copy_button)
        
        update_button = InlineKeyboardButton(
            text="✅ Updated Number" if updated else "🔄 Update Number",
            callback_data=f"update_{number}_{site_id}"
        )
        row.append(update_button)
        keyboard.append(row)
        
        # Second row - Split and Settings buttons
        row = []
        split_button = InlineKeyboardButton(
            text="🔢 Split Number",
            callback_data=f"split_{number}_{site_id}"
        )
        row.append(split_button)
        
        settings_button = InlineKeyboardButton(
            text="⚙️ Settings",
            callback_data=f"settings_{site_id}"
        )
        row.append(settings_button)
        keyboard.append(row)
        
        # Third row - Visit Webpage button
        if url:
            keyboard.append([InlineKeyboardButton(text="🌐 Visit Webpage", url=url)])
            
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    else:
        # Multiple type keyboard
        numbers = data.get("numbers", [])
        if not numbers:
            return None
            
        # Format all numbers
        formatted_numbers = []
        for num in numbers:
            formatted_num, _ = format_phone_number(num, get_flag=True)
            formatted_numbers.append(formatted_num)

        # Initial run layout - always use last_number
        if data.get("is_initial_run", False):
            debug_print(f"[DEBUG] create_unified_keyboard - creating initial run keyboard")
            if not numbers:
                return None

            # First row - Last Number button
            keyboard.append([InlineKeyboardButton(
                text=formatted_numbers[0],
                callback_data=f"number_{numbers[0]}_{site_id}"
            )])
            
            # Second row - Update and Settings buttons
            row = []
            update_button = InlineKeyboardButton(
                text="🔄 Update Numbers",  # Always show update, not updated
                callback_data=f"update_multi_{site_id}"
            )
            row.append(update_button)
            
            settings_button = InlineKeyboardButton(
                text="⚙️ Settings",
                callback_data=f"settings_{site_id}"
            )
            row.append(settings_button)
            keyboard.append(row)
            
            # Third row - Visit Webpage button
            if url:
                keyboard.append([InlineKeyboardButton(text="🌐 Visit Webpage", url=url)])
                
            return InlineKeyboardMarkup(inline_keyboard=keyboard)
        else:
            # Subsequent runs layout
            debug_print(f"[DEBUG] create_unified_keyboard - creating subsequent run keyboard")
            if not numbers:
                return None

            # First row - Selected Numbers buttons (2 per row)
            current_row = []
            for i, (number, formatted_number) in enumerate(zip(numbers, formatted_numbers)):
                current_row.append(InlineKeyboardButton(
                    text=formatted_number,
                    callback_data=f"number_{number}_{site_id}"
                ))
                
                # Add row to keyboard when we have 2 numbers or it's the last number
                if len(current_row) == 2 or i == len(numbers) - 1:
                    keyboard.append(current_row)
                    current_row = []
            
            # Second row - Update and Settings buttons
            row = []
            update_button = InlineKeyboardButton(
                text="🔄 Update Numbers",  # Always show update, not updated
                callback_data=f"update_multi_{site_id}"
            )
            row.append(update_button)
            
            settings_button = InlineKeyboardButton(
                text="⚙️ Settings",
                callback_data=f"settings_{site_id}"
            )
            row.append(settings_button)
            keyboard.append(row)
            
            # Third row - Visit Webpage button
            if url:
                keyboard.append([InlineKeyboardButton(text="🌐 Visit Webpage", url=url)])
                
            return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_buttons(number, updated=False, site_id=None):
    """Get buttons for a single number notification"""
    if not site_id:
        # Get site_id from storage if not provided
        latest = storage.get("latest_notification", {})
        site_id = latest.get("site_id", "site_1")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_{number}_{site_id}"),
         InlineKeyboardButton(text="✅ Updated Number" if updated else "🔄 Update Number", 
                            callback_data=f"update_{number}_{site_id}")],
        [InlineKeyboardButton(text="🔢 Split Number", callback_data=f"split_{number}_{site_id}"),
         InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{site_id}")],
        [InlineKeyboardButton(text="🌐 Visit Webpage", url=storage["websites"].get(site_id, "").url)]
    ])

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

    # Create data structure for keyboard
    data = {
        "type": "multiple",
        "numbers": numbers,
        "site_id": site_id,
        "updated": False,  # Default to not updated
        "url": getattr(website, 'url', get_base_url() or ""),
        "is_initial_run": website.is_initial_run  # Use website's is_initial_run state
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
            
            # Create data structure for single type keyboard
            keyboard_data = {
                "type": "single",
                "number": number,
                "site_id": site_id,
                "updated": False,
                "url": website_url,
                "is_initial_run": website.is_initial_run
            }
            
            # Use create_unified_keyboard with the proper data structure
            keyboard = create_unified_keyboard(keyboard_data, website)

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

            # Handle repeat notification if enabled and not initial run
            if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None and not website.is_initial_run:
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
                        individual_message = f"🎁 *New Numbers Added* 🎁\n\n`{number}` check it out! 💖"
                        
                        # Create individual keyboard for this number
                        individual_data = {
                            "type": "multiple",  # Keep as multiple type
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
