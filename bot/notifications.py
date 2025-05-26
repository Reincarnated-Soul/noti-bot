import os
import asyncio
import time
import aiohttp
from typing import Union

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.storage import storage, save_website_data
from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, debug_print, DEV_MODE, SINGLE_MODE
from bot.utils import get_base_url, format_phone_number, format_time, get_selected_numbers_for_buttons, KeyboardData

def create_keyboard(data: Union[dict, KeyboardData], website) -> InlineKeyboardMarkup:
    """Create a keyboard layout based on website type"""
    try:
        debug_print(f"[DEBUG] create_keyboard - Starting keyboard creation with data: {data}")
        
        # If we have stored buttons and only need to update state, reuse them
        keyboard_state = website.get_keyboard_state()
        if keyboard_state["buttons"] is not None:
            # Check if we only need to update button states without changing layout
            if isinstance(data, dict) and len(data) == 2 and "updated" in data and "site_id" in data:
                debug_print("[DEBUG] create_keyboard - Reusing existing keyboard with updated state")
                buttons = keyboard_state["buttons"]
                # Update only the update button state
                for row in buttons:
                    for button in row:
                        if "update" in button.callback_data:
                            button.text = "✅ Updated Number" if data["updated"] else "🔄 Update Number"
                return InlineKeyboardMarkup(inline_keyboard=buttons)

        # Convert dict to KeyboardData if needed
        if isinstance(data, dict):
            # Ensure numbers are properly handled
            numbers = data.get("numbers", keyboard_state["numbers"])
            if not numbers and data.get("number"):
                numbers = [data.get("number")]
            
            data = KeyboardData(
                site_id=data.get("site_id"),
                type=data.get("type", website.type),
                url=data.get("url", website.url),
                updated=data.get("updated", keyboard_state["updated"]),
                is_initial_run=data.get("is_initial_run", keyboard_state["is_initial_run"]),
                numbers=numbers,
                single_mode=data.get("single_mode", keyboard_state["single_mode"])
            )
            debug_print(f"[DEBUG] create_keyboard - Converted dict to KeyboardData: {data}")

        # Update website's keyboard state
        website.update_keyboard_state(
            numbers=data.numbers,
            updated=data.updated,
            is_initial_run=data.is_initial_run,
            single_mode=data.single_mode
        )

        buttons = []
        if data.type == "single":
            # Single type display
            if not data.numbers:
                debug_print("[ERROR] create_keyboard - No numbers provided for single type")
                return None

            number = data.numbers[0]
            formatted_number = format_phone_number(number)
            debug_print(f"[DEBUG] create_keyboard - Creating single type keyboard for number: {formatted_number}")

            buttons = [
                [
                    InlineKeyboardButton(
                        text="📋 Copy Number",
                        callback_data=f"copy_{number}_{data.site_id}"),
                    InlineKeyboardButton(
                        text="✅ Updated Number" if data.updated else "🔄 Update Number",
                        callback_data=f"update_{number}_{data.site_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔢 Split Number",
                        callback_data=f"split_{number}_{data.site_id}"),
                    InlineKeyboardButton(
                        text="⚙️ Settings",
                        callback_data=f"settings_{data.site_id}")
                ],
                [InlineKeyboardButton(text="🌐 Visit Webpage", url=data.url)]
            ]
        else:
            # Multiple type display
            if not data.numbers:
                debug_print("[ERROR] create_keyboard - No numbers provided for multiple type")
                return None

            debug_print(f"[DEBUG] create_keyboard - Creating multiple type keyboard with numbers: {data.numbers}")
            
            # For initial run or SINGLE_MODE, show single number button first
            if data.is_initial_run or data.single_mode:
                number = data.numbers[0]
                formatted_number = format_phone_number(number)
                debug_print(f"[DEBUG] create_keyboard - Adding single number button: {formatted_number}")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{formatted_number}",
                        callback_data=f"number_{number}_{data.site_id}"
                    )
                ])
            else:
                # For subsequent runs without SINGLE_MODE, show numbers in pairs
                current_row = []
                for i, number in enumerate(data.numbers):
                    formatted_number = format_phone_number(number)
                    debug_print(f"[DEBUG] create_keyboard - Adding number to row: {formatted_number}")
                    current_row.append(
                        InlineKeyboardButton(
                            text=f"{formatted_number}",
                            callback_data=f"number_{number}_{data.site_id}"
                        )
                    )
                    
                    # If we have 2 numbers in the row or it's the last number
                    if len(current_row) == 2 or i == len(data.numbers) - 1:
                        buttons.append(current_row)
                        current_row = []
                        debug_print(f"[DEBUG] create_keyboard - Added row to buttons: {current_row}")

            # Add common buttons
            debug_print("[DEBUG] create_keyboard - Adding common buttons")
            buttons.extend([
                [
                    InlineKeyboardButton(
                        text="✅ Updated Number" if data.updated else "🔄 Update Number",
                        callback_data=f"update_multi_{data.site_id}"
                    ),
                    InlineKeyboardButton(text="⚙️ Settings", callback_data=f"settings_{data.site_id}")
                ],
                [InlineKeyboardButton(text="🌐 Visit Webpage", url=data.url)]
            ])

        # Store the buttons for future reuse
        website.set_keyboard_buttons(buttons)
        debug_print(f"[DEBUG] create_keyboard - Stored keyboard buttons for future use")

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        debug_print(f"[DEBUG] create_keyboard - Keyboard created: {keyboard}")
        return keyboard

    except Exception as e:
        debug_print(f"[ERROR] create_keyboard - error creating keyboard: {e}")
        return None

async def send_notification(bot, data):
    """Send notification with appropriate layout based on website type"""
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
        is_updated = data.get("updated", False)

        debug_print(f"[DEBUG] send_notification - Starting notification for site_id: {site_id}, type: {website.type}, is_multiple: {is_multiple}")

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
                "updated": is_updated,
                "url": website_url,
                "is_initial_run": website.is_initial_run
            }
            
            # Use create_keyboard with the proper data structure
            keyboard = create_keyboard(keyboard_data, website)
            debug_print(f"[DEBUG] send_notification - Single type keyboard created: {keyboard}")

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
                "is_initial_run": website.is_initial_run,
                "updated": is_updated
            }

            # Handle repeat notification if enabled and not initial run
            if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None and not website.is_initial_run:
                await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id, flag_url)

        else:
            # Multiple numbers notification
            numbers = data.get("numbers", [])

            if not numbers:
                debug_print("[ERROR] send_notification - No numbers provided for multiple type notification")
                return

            debug_print(f"[DEBUG] send_notification - Type: {website.type}, is_initial_run: {website.is_initial_run}, numbers count: {len(numbers)}")

            if website.is_initial_run:
                # On first run, send notification with the last_number
                display_number = website.last_number if hasattr(website, 'last_number') and website.last_number is not None else numbers[0]
                notification_message = f"🎁 *New Numbers Added* 🎁\n\n`+{display_number}` check it out! 💖"

                # Create keyboard data for initial run
                keyboard_data = {
                    "type": "multiple",
                    "numbers": [f"+{display_number}"],
                    "site_id": site_id,
                    "updated": is_updated,
                    "url": website_url,
                    "is_initial_run": True,
                    "single_mode": SINGLE_MODE
                }
                debug_print(f"[DEBUG] send_notification - Creating keyboard with data: {keyboard_data}")
                keyboard = create_keyboard(keyboard_data, website)
                debug_print(f"[DEBUG] send_notification - Multiple type initial run keyboard created: {keyboard}")

                try:
                    sent_message = await bot.send_photo(
                        chat_id,
                        photo=flag_url,
                        caption=notification_message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    debug_print(f"[DEBUG] send_notification - Message sent successfully with keyboard")

                except Exception as e:
                    debug_print(f"[ERROR] send_notification - error sending message: {e}")
                    return

                # Store notification data
                storage["latest_notification"] = {
                    "message_id": sent_message.message_id,
                    "numbers": numbers,
                    "flag_url": flag_url,
                    "site_id": site_id,
                    "multiple": True,
                    "is_initial_run": website.is_initial_run,
                    "updated": is_updated
                }
            else:
                # For subsequent runs, use selected numbers
                selected_numbers = get_selected_numbers_for_buttons(numbers, website.previous_last_number)
                debug_print(f"[DEBUG] send_notification - Selected numbers for buttons: {selected_numbers}")
                
                # Check if SINGLE_MODE is enabled
                if SINGLE_MODE and selected_numbers:
                    # Send individual notifications for each number
                    for number in selected_numbers:
                        individual_message = f"🎁 *New Numbers Added* 🎁\n\n`{number}` check it out! 💖"
                        
                        # Create individual keyboard for this number
                        individual_data = {
                            "type": "multiple",  # Keep as multiple type
                            "numbers": [number],  # Pass single number in numbers array
                            "site_id": site_id,
                            "updated": is_updated,
                            "url": website_url,
                            "single_mode": True
                        }
                        debug_print(f"[DEBUG] send_notification - Creating individual keyboard with data: {individual_data}")
                        individual_keyboard = create_keyboard(individual_data, website)
                        debug_print(f"[DEBUG] send_notification - Individual keyboard created: {individual_keyboard}")
                        
                        # Send individual notification
                        await bot.send_photo(
                            chat_id=CHAT_ID,
                            photo=flag_url,
                            caption=individual_message,
                            parse_mode="Markdown",
                            reply_markup=individual_keyboard
                        )
                        debug_print(f"[DEBUG] send_notification - Individual message sent successfully with keyboard")
                        
                        # Add a small delay between notifications
                        await asyncio.sleep(1)
                    
                    return  # Exit after sending individual notifications
                    
                else:
                    # Group all selected numbers in single notification
                    notification_message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(selected_numbers)}` numbers, check them out! 💖"

                    # Create keyboard data for subsequent run
                    keyboard_data = {
                        "type": "multiple",
                        "numbers": selected_numbers,
                        "site_id": site_id,
                        "updated": is_updated,
                        "url": website_url,
                        "is_initial_run": False,
                        "single_mode": SINGLE_MODE
                    }
                    debug_print(f"[DEBUG] send_notification - Creating keyboard with data: {keyboard_data}")
                    keyboard = create_keyboard(keyboard_data, website)
                    debug_print(f"[DEBUG] send_notification - Multiple type subsequent run keyboard created: {keyboard}")

                    try:
                        sent_message = await bot.send_photo(
                            chat_id,
                            photo=flag_url,
                            caption=notification_message,
                            parse_mode="Markdown",
                            reply_markup=keyboard
                        )
                        debug_print(f"[DEBUG] send_notification - Message sent successfully with keyboard")

                    except Exception as e:
                        debug_print(f"[ERROR] send_notification - error sending message: {e}")
                        return

                    # Store notification data
                    storage["latest_notification"] = {
                        "message_id": sent_message.message_id,
                        "numbers": numbers,
                        "flag_url": flag_url,
                        "site_id": site_id,
                        "multiple": True,
                        "is_initial_run": website.is_initial_run,
                        "updated": is_updated
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

                # Create keyboard data
                keyboard_data = {
                    "type": "multiple",
                    "numbers": numbers,
                    "site_id": site_id,
                    "updated": is_updated,
                    "url": website_url,
                    "is_initial_run": is_initial_run
                }
                keyboard = create_keyboard(keyboard_data, website)
            else:
                # Single number message
                number = number_or_numbers if isinstance(number_or_numbers, str) else website.last_number

                notification_message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
                
                # Create keyboard data
                keyboard_data = {
                    "type": "single",
                    "number": number,
                    "site_id": site_id,
                    "updated": is_updated,
                    "url": website_url,
                    "is_initial_run": True
                }
                keyboard = create_keyboard(keyboard_data, website)

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
            await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id, storage["latest_notification"].get("flag_url"))

    except Exception as e:
        debug_print(f"[ERROR] repeat_notification - error: {e}")
