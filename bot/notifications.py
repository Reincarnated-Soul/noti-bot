import os, asyncio
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.storage import storage, save_website_data
from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, debug_print, DEV_MODE
from bot.utils import get_base_url, format_phone_number

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
    
    debug_print(f"[DEBUG] create_unified_keyboard - initial values: site_id={site_id}, type={website_type}, updated={updated}")
    
    # If website object is provided, use it for fallback values and prioritize its attributes
    if website:
        debug_print(f"[DEBUG] create_unified_keyboard - website object provided for site_id: {site_id}")
        # Get button_updated state from website object
        button_updated = getattr(website, 'button_updated', False)
        debug_print(f"[DEBUG] create_unified_keyboard - website object provided with button_updated: {button_updated}")
        
        # Prioritize the website object's button_updated state over the passed updated parameter
        if button_updated:
            updated = True
            debug_print(f"[DEBUG] create_unified_keyboard - using website's button_updated state: {updated}")
        
        # Prioritize the website's type over the passed type
        if hasattr(website, "type") and website.type:
            if website_type != website.type:
                debug_print(f"[DEBUG] create_unified_keyboard - overriding type from {website_type} to {website.type}")
                website_type = website.type
        
        if not website_type and hasattr(website, "type"):
            website_type = website.type
            debug_print(f"[DEBUG] create_unified_keyboard - using website's type: {website_type}")
            
        if not url and hasattr(website, "url"):
            url = website.url
            debug_print(f"[DEBUG] create_unified_keyboard - using website's url: {url}")
    else:
        debug_print(f"[DEBUG] create_unified_keyboard - no website object provided")
    
    debug_print(f"[DEBUG] create_unified_keyboard - after website processing: site_id={site_id}, updated={updated}, type={website_type}")
    
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
        formatted_number = format_phone_number(number)
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
            
            formatted_number = format_phone_number(display_number)
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
            # Subsequent run - arrange buttons 2 per row from latest_numbers
            debug_print(f"[DEBUG] create_unified_keyboard - using regular layout for multiple type with {len(numbers)} numbers")
            buttons = []
            
            # Create buttons for numbers, 2 per row
            current_row = []
            for raw_number in numbers:
                formatted_number = format_phone_number(raw_number)
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

    data = {
        "type": "multiple",
        "numbers": numbers,
        "site_id": site_id,
        "updated": False,  # Default to not updated
        "url": getattr(website, 'url', get_base_url() or ""),
        "is_initial_run": getattr(website, 'first_run', False)
    }

    # Try to determine if this is an initial run if the attribute is not present
    if not hasattr(website, 'first_run'):
        if (not hasattr(website, 'latest_numbers') or 
            not website.latest_numbers or 
            len(website.latest_numbers) == 0):
            data["is_initial_run"] = True
            debug_print(f"[DEBUG] get_multiple_buttons - determining this is an initial run based on missing latest_numbers")
    
    debug_print(f"[DEBUG] get_multiple_buttons - created data: {data}")
    keyboard = create_unified_keyboard(data, website)
    debug_print(f"[DEBUG] get_multiple_buttons - returning keyboard with {len(keyboard.inline_keyboard) if keyboard else 0} rows")
    return keyboard

async def send_notification(bot, data):
    try:
        chat_id = os.getenv("CHAT_ID")
        # print(f"[DEBUG] send_notification - chat_id: {chat_id}")
        # print(f"[DEBUG] send_notification - data: {data}")
        
        if not chat_id and website:
            return

        site_id = data.get("site_id")
        website = storage["websites"].get(site_id)

        # Determine if this is a single or multiple number notification based on website type
        is_multiple = website.type == "multiple"
        flag_url = data.get("flag_url")

        if not is_multiple:
            # Single number notification
            number = data.get("number")

            if not number or not flag_url:
                # print(f"[ERROR] send_notification - missing number or flag_url for site_id: {site_id}")
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
                # print(f"[DEBUG] send_notification - sent message to {chat_id}")
            except Exception as e:
                # print(f"[ERROR] send_notification - failed to send message to {chat_id}: {e}")
                return

            # Store notification data
            storage["latest_notification"] = {
                "message_id": sent_message.message_id,
                "number": number,
                "flag_url": flag_url,
                "site_id": site_id,
                "multiple": False,
                "is_first_run": False
            }

            # Handle repeat notification if enabled
            if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None:
                await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id)

        else:
            # Multiple numbers notification
            numbers = data.get("numbers", [])

            if not numbers:
                # print(f"[ERROR] send_notification - missing numbers for site_id: {site_id}")
                return

            # Check if this is the first run 
            is_first_run = (not website.latest_numbers) or (
                any(num == f"+{website.last_number}" for num in website.latest_numbers) and len(website.latest_numbers) == len(numbers)
            )
            
            debug_print(f"[DEBUG] send_notification - multiple type, is_first_run: {is_first_run}")

            if is_first_run or len(numbers) == 1:
                # On first run or single number, send notification with the last_number
                # Make sure we have a last_number
                if not hasattr(website, 'last_number') or website.last_number is None:
                    if numbers and len(numbers) > 0:
                        # Extract from the first number if available
                        first_num = numbers[0]
                        if isinstance(first_num, str) and first_num.startswith('+'):
                            first_num = first_num[1:]
                        try:
                            website.last_number = int(first_num)
                            debug_print(f"[DEBUG] send_notification - setting last_number from first number: {website.last_number}")
                            await save_website_data(site_id)
                        except (ValueError, TypeError):
                            debug_print(f"[DEBUG] send_notification - could not convert {first_num} to last_number")
                            # Use the first number as-is if conversion fails
                            website.last_number = first_num
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

                # Create data for keyboard with single number (last_number or first number)
                keyboard_data = {
                    "type": "multiple",
                    "numbers": [f"+{display_number}"],  # Use the display number for the button
                    "site_id": site_id,
                    "updated": False,
                    "url": website.url,
                    "is_initial_run": True
                }
                
                keyboard = create_unified_keyboard(keyboard_data, website)
            else:
                notification_message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(numbers)}` numbers, check them out! 💖"
                debug_print(f"[DEBUG] send_notification - using all {len(numbers)} numbers for subsequent run")
                
                # Create data for keyboard with all numbers (2 per row)
                keyboard_data = {
                    "type": "multiple",
                    "numbers": numbers,
                    "site_id": site_id,
                    "updated": False,
                    "url": website.url,
                    "is_initial_run": False
                }
                
                keyboard = create_unified_keyboard(keyboard_data, website)

            try:
                if flag_url:
                    sent_message = await bot.send_photo(
                        chat_id,
                        photo=flag_url,
                        caption=notification_message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                else:
                    sent_message = await bot.send_message(
                        chat_id,
                        text=notification_message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                # print(f"[DEBUG] send_notification - sent message to {chat_id}")
            except Exception as e:
                # print(f"[ERROR] send_notification - failed to send message to {chat_id}: {e}")
                return

            # Store notification data
            storage["latest_notification"] = {
                "message_id": sent_message.message_id,
                "numbers": numbers,
                "flag_url": flag_url,
                "site_id": site_id,
                "multiple": True,
                "is_first_run": is_first_run
            }

            # Handle repeat notification if enabled
            if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is not None:
                await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id)
    except Exception as e:
        # print(f"[ERROR] send_notification - unexpected error: {e}")
        pass

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

    while countdown_active:
        try:
            current_time = time.time()
            time_left = int(interval - (current_time - last_update_time))
            if time_left < 0:
                time_left = 0
            formatted_time = format_time(time_left)

            if is_multiple:
                # Multiple numbers message
                numbers = number_or_numbers if isinstance(number_or_numbers, list) else website.latest_numbers
                notification_message = f"🎁 *New Numbers Added* 🎁\n\nFound `{len(numbers)}` numbers, check them out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
                keyboard = get_multiple_buttons(numbers, site_id=site_id)
            else:
                # Single number message
                number = number_or_numbers if isinstance(number_or_numbers, str) else website.last_number
                notification_message = f"🎁 *New Number Added* 🎁\n\n`{number}` check it out! 💖\n\n⏱ Next notification in: *{formatted_time}*"
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
            # print(f"[ERROR] update_message_with_countdown - error: {e}")
            countdown_active = False

async def add_countdown_to_latest_notification(bot, interval_seconds, site_id):
    try:
        latest = storage["latest_notification"]
        if latest["message_id"] and latest["site_id"] == site_id:
            message_id = latest["message_id"]
            flag_url = latest.get("flag_url")
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
        # print(f"[ERROR] add_countdown_to_latest_notification - error: {e}")
        pass

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
            await add_countdown_to_latest_notification(bot, storage["repeat_interval"], site_id)
    
    except Exception as e:
        # print(f"[ERROR] repeat_notification - error: {e}")
        pass
