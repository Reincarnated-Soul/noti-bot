import os
import re
import asyncio
import time
import aiohttp
from typing import Union, List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.storage import (
    storage, save_website_data, create_notification_state, get_notification_state, update_notification_state
)

from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, debug_print, DEV_MODE, SINGLE_MODE
from bot.utils import get_base_url, format_phone_number, format_time, get_selected_numbers_for_buttons, KeyboardData, extract_website_name

def caption_message(number: Union[str, List[str]], include_time: bool = False, formatted_time: str = None, is_single: bool = True) -> str:
    # Filter spaces and dashes if included
    number = re.sub(r'[\s\-]', '', str(number))

    if is_single:
        message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖"
    else:
        numbers = number if isinstance(number, list) else [number]
        message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(numbers)}` numbers, check them out! 💖"
    
    if include_time and formatted_time:
        return f"{message}\n\n⏱ Next notification in: *{formatted_time}*"
    
    return message

async def create_keyboard(data: Union[dict, KeyboardData], website) -> InlineKeyboardMarkup:
    """Create a keyboard layout based on website type"""
    try:
        # Convert dict to KeyboardData if needed
        if isinstance(data, dict):
            data = KeyboardData(**data)

        # Validate required fields
        if not all([data.site_id, data.type, data.url]):
            debug_print("[ERROR] create_keyboard - Missing required fields")
            return None

        # Update website's keyboard state
        website.update_keyboard_state(
            numbers=data.numbers,
            is_initial_run=data.is_initial_run,
            single_mode=data.single_mode
        )

        buttons = []
        
        # Common layout for both single and multiple types
        if data.numbers:
            if data.type == "single" or data.is_initial_run or data.single_mode:
                # Single number display
                number = data.numbers[0]
                formatted_number = await format_phone_number(number, website_url=website.url)
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{formatted_number}",
                        callback_data=f"split_{number}_{data.site_id}"
                    )
                ])
            else:
                # For subsequent runs without SINGLE_MODE, show numbers in pairs
                current_row = []
                for i, number in enumerate(data.numbers):
                    formatted_number = await format_phone_number(number, website_url=website.url)
                    current_row.append(
                        InlineKeyboardButton(
                            text=f"{formatted_number}",
                            callback_data=f"split_{number}_{data.site_id}"
                        )
                    )
                    
                    if len(current_row) == 2 or i == len(data.numbers) - 1:
                        buttons.append(current_row)
                        current_row = []

        # Get website name for visit webpage button (always use domain name)
        website_name = extract_website_name(data.url, data.type, use_domain_only=True)

        # Common buttons for all types
        buttons.extend([
            [InlineKeyboardButton(
                text="⚙️ Settings",
                callback_data=f"settings_{data.site_id}")],
            [InlineKeyboardButton(
                text=f"🌐 Visit Webpage : {website_name}",
                url=data.url)]
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    except Exception as e:
        debug_print(f"[ERROR] create_keyboard - Error creating keyboard: {e}")
        return None

async def send_notification(bot, data):
    """Send notification with appropriate layout based on website type"""
    try:
        chat_id = os.getenv("CHAT_ID")
        if not chat_id:
            debug_print("[ERROR] send_notification - No chat ID found")
            return

        site_id = data.get("site_id")
        website = storage["websites"].get(site_id)
        if not website:
            debug_print("[ERROR] send_notification - Website not found")
            return

        # Create notification state
        is_multiple = website.type == "multiple"
        numbers = data.get("numbers", []) if is_multiple else [data.get("number")]
        
        # Get country code and flag information for the first number
        country_code = None
        flag_url = data.get("flag_url")  # Get flag URL from the data parameter

        # Format the first number for flag info
        if numbers:
            formatted_number, flag_info = await format_phone_number(numbers[0], get_flag=True, website_url=website.url)
            if flag_info:  # If we got flag info, we definitely got country code
                country_code = formatted_number.split(' ')[0] if formatted_number else None

        # Prepare notification details for logging
        button_created_using = (
            "last_number (initial run)" if website.is_initial_run 
            else "selected_numbers_for_buttons (subsequent run)" if is_multiple 
            else "last_number"
        )
        
        debug_print(f"[DEBUG] send_notification - Creating notification state for site: {site_id}")

        async def send_notification_message(number, is_initial=False):
            """Helper function to send a notification message with a number"""
            notification_state = create_notification_state(
                site_id=site_id,
                numbers=[number],
                type=website.type,
                is_initial_run=is_initial
            )
            
            caption = caption_message(number)
            keyboard = await create_keyboard(notification_state.to_keyboard_data(website.url), website)
            debug_print(f"[DEBUG] send_notification - Created keyboard for number: {number}")

            try:
                sent_message = await bot.send_photo(
                    chat_id,
                    photo=flag_url,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                notification_state.set_message_id(sent_message.message_id)
                debug_print(f"[DEBUG] send_notification - Successfully sent notification with message_id: {sent_message.message_id}")
                return sent_message.message_id
            except Exception as e:
                debug_print(f"[ERROR] send_notification - Error sending message: {e}")
                return None

        if not is_multiple:
            # Single number notification
            if not numbers:
                debug_print("[ERROR] send_notification - No number provided for single type")
                return

            message_id = await send_notification_message(numbers[0], website.is_initial_run)

        else:
            # Multiple numbers notification
            if not numbers:
                debug_print("[ERROR] send_notification - No numbers provided for multiple type notification")
                return

            if website.is_initial_run:
                debug_print(f"[DEBUG] send_notification - Initial run. is_initial_run: {website.is_initial_run}")
                # Display single number in initial run
                message_id = await send_notification_message(numbers[0], True)
            else:
                debug_print("[DEBUG] send_notification - Processing subsequent run for multiple numbers")
                # For subsequent runs, use selected numbers
                selected_numbers = get_selected_numbers_for_buttons(numbers, website.previous_last_number)
                debug_print(f"[DEBUG] send_notification - Selected numbers for buttons: {selected_numbers}")

                # Send notification for each number if SINGLE_MODE is enabled
                if SINGLE_MODE and selected_numbers:
                    debug_print("[DEBUG] send_notification - Sending individual notifications in SINGLE_MODE")
                    last_message_id = None
                    for number in selected_numbers:
                        last_message_id = await send_notification_message(number, False)
                        # Add a small delay between notifications to prevent rate limiting
                        await asyncio.sleep(0.5)
                    message_id = last_message_id
                else:
                    # Send one notification with all numbers
                    notification_state = create_notification_state(
                        site_id=site_id,
                        numbers=selected_numbers,
                        type=website.type,
                        is_initial_run=False
                    )
                    
                    caption = caption_message(selected_numbers, is_single=False)
                    keyboard = await create_keyboard(notification_state.to_keyboard_data(website.url), website)
                    debug_print("[DEBUG] send_notification - Created keyboard for subsequent run")

                    try:
                        debug_print("[DEBUG] send_notification - Attempting to send subsequent run notification")
                        sent_message = await bot.send_photo(
                            chat_id,
                            photo=flag_url,
                            caption=caption,
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                        notification_state.set_message_id(sent_message.message_id)
                        message_id = sent_message.message_id
                        debug_print(f"[DEBUG] send_notification - Successfully sent subsequent notification with message_id: {message_id}")
                    except Exception as e:
                        debug_print(f"[ERROR] send_notification - Error sending message: {e}")
                        return

        # Log notification details after successful sending
        if message_id:
            print("🎯 Notification Send Successfully 📧")
            print(f"{{ Notification Message - initial values:\n  [\n"
                  f"    site_id = {site_id},\n"
                  f"    message_id = {message_id},\n"
                  f"    website_type = {website.type if website else None},\n"
                  f"    country_code = {country_code},\n"
                  f"    numbers = {numbers},\n"
                  f"    Flag_URL = {flag_url},\n"
                  f"    button_count = {len(numbers)},\n"
                  f"    button_created_using = '{button_created_using}',\n"
                  f"    settings = {website.settings if website and hasattr(website,'settings') else None},\n"
                  f"    updated = {data.get('updated', False)},\n"
                  f"    is_initial_run = {website.is_initial_run},\n"
                  f"    single_mode = {SINGLE_MODE},\n"
                  f"    visit_url = {website.url}\n  ]\n}}")

        # Handle repeat notification if enabled
        if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None and message_id:
            debug_print("[DEBUG] send_notification - Setting up repeat notification")
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

    # Get the current update state from storage
    is_updated = False
    if "latest_notification" in storage and storage["latest_notification"].get("site_id") == site_id:
        is_updated = storage["latest_notification"].get("updated", False)

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

                    caption = caption_message(numbers[0] if numbers else 'Unknown', include_time=True, formatted_time=formatted_time)
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

                    caption = caption_message(selected_numbers[0], include_time=True, formatted_time=formatted_time)
                    numbers = selected_numbers

                # Create keyboard data
                keyboard_data = {
                    "type": "multiple",
                    "numbers": numbers,
                    "site_id": site_id,
                    "updated": is_updated,
                    "url": website_url,
                    "is_initial_run": is_initial_run
                }
                keyboard = await create_keyboard(keyboard_data, website)
            else:
                # Single number message
                number = number_or_numbers if isinstance(number_or_numbers, str) else website.last_number

                caption = caption_message(number, include_time=True, formatted_time=formatted_time)
                
                # Create keyboard data
                keyboard_data = {
                    "type": "single",
                    "number": number,
                    "site_id": site_id,
                    "updated": is_updated,
                    "url": website_url,
                    "is_initial_run": True
                }
                keyboard = await create_keyboard(keyboard_data, website)

            await bot.edit_message_caption(
                chat_id=CHAT_ID,
                message_id=message_id,
                caption=caption,
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
            await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id, storage["latest_notification"].get("flag_url"))

    except Exception as e:
        debug_print(f"[ERROR] repeat_notification - error: {e}")
