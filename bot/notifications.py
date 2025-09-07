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
from bot.utils import get_base_url, format_phone_number, get_selected_numbers_for_buttons, KeyboardData, extract_website_name

def caption_message(number: Union[str, List[str]], include_time: bool = False, is_single: bool = True) -> str:
    # Filter spaces and dashes if included
    number = re.sub(r'[\s\-]', '', str(number))

    if is_single:
        message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖"
    else:
        numbers = number if isinstance(number, list) else [number]
        message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(numbers)}` numbers, check them out! 💖"
    
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

    except Exception as e:
        debug_print(f"[ERROR] send_notification - error: {e}")
        return
