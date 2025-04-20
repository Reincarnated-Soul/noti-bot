import os, asyncio
from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from bot.config import CHAT_ID, ENABLE_REPEAT_NOTIFICATION, DEFAULT_REPEAT_INTERVAL, debug_print, DEV_MODE
from bot.notifications import get_buttons, update_message_with_countdown, create_unified_keyboard
from bot.storage import storage, save_website_data, save_last_number
from bot.utils import format_time, delete_message_after_delay, get_base_url, extract_website_name, remove_country_code

def register_handlers(dp: Dispatcher):
    """Register all handlers with the dispatcher"""
    # Button callbacks
    dp.callback_query.register(copy_number,
                               lambda c: c.data.startswith("copy_"))
    dp.callback_query.register(
        update_number, lambda c: c.data.startswith("update_") and not c.data.
        startswith("update_multi_"))
    dp.callback_query.register(update_multi_numbers,
                               lambda c: c.data.startswith("update_multi_"))
    dp.callback_query.register(
        handle_settings, lambda c: c.data.startswith("settings_") and not c.
        data.startswith("settings_monitoring_"))
    dp.callback_query.register(
        handle_monitoring_settings,
        lambda c: c.data.startswith("settings_monitoring_"))
    dp.callback_query.register(toggle_site_monitoring,
                               lambda c: c.data.startswith("toggle_site_"))
    dp.callback_query.register(toggle_repeat_notification,
                               lambda c: c.data.startswith("toggle_repeat_"))
    dp.callback_query.register(back_to_main,
                               lambda c: c.data.startswith("back_to_main_"))
    dp.callback_query.register(
        split_number,
        lambda c: c.data.startswith("split_") or c.data.startswith("number_"))

    # Commands
    dp.message.register(send_ping_reply, Command("ping"))
    dp.message.register(set_repeat_interval, Command("set_repeat"))
    dp.message.register(stop_repeat_notification, Command("stop_repeat"))


async def copy_number(callback_query: CallbackQuery):
    try:
        debug_print("[DEBUG] copy_number - function started")
        # Extract data from callback query
        callback_data = callback_query.data
        parts = callback_data.split("_")
        debug_print(f"[DEBUG] copy_number - callback_data: {callback_data}, parts: {parts}")
        
        # Handle both old and new formats
        if len(parts) >= 3:  # New format: copy_{number}_{site_id}
            number = parts[1]
            site_id = parts[2]
            debug_print(f"[DEBUG] copy_number - using new format, number: {number}, site_id: {site_id}")
        elif len(parts) == 2:  # Old format: copy_number
            # For old format, extract from the layout
            debug_print("[DEBUG] copy_number - using old format, extracting from button layout")
            current_buttons = callback_query.message.reply_markup.inline_keyboard
            debug_print(f"[DEBUG] copy_number - current_buttons rows: {len(current_buttons)}")
            
            # Save original keyboard for restoration if needed
            original_keyboard = callback_query.message.reply_markup
            debug_print(f"[DEBUG] copy_number - saved original keyboard")
            
            if len(current_buttons) > 0 and len(current_buttons[0]) > 1:
                update_button = current_buttons[0][1]
                debug_print(f"[DEBUG] copy_number - update button text: {update_button.text}")
                debug_print(f"[DEBUG] copy_number - update button callback: {update_button.callback_data}")
                is_updated = update_button.text == "✅ Updated Number"
                update_data = update_button.callback_data.split("_")
                
                if len(update_data) > 1:
                    number = update_data[1]
                    debug_print(f"[DEBUG] copy_number - extracted number: {number}")
                else:
                    debug_print(f"[DEBUG] copy_number - could not extract number from update button")
                    number = "unknown"
                
                # Try to extract site_id from other buttons
                site_id = None
                if len(update_data) >= 3:
                    site_id = update_data[2]
                    debug_print(f"[DEBUG] copy_number - extracted site_id from update button: {site_id}")
            else:
                debug_print(f"[DEBUG] copy_number - update button not found, using fallback")
                number = "unknown"
                is_updated = False
            
            # If site_id still not found, look at other buttons
            if not site_id and len(current_buttons) > 1:
                debug_print(f"[DEBUG] copy_number - searching for site_id in other buttons")
                for i, row in enumerate(current_buttons):
                    debug_print(f"[DEBUG] copy_number - checking row {i}, buttons: {len(row)}")
                    for j, button in enumerate(row):
                        debug_print(f"[DEBUG] copy_number - checking button {j}, callback: {button.callback_data}")
                        if button.callback_data and button.callback_data.startswith("settings_"):
                            site_id = button.callback_data.split("_")[1]
                            debug_print(f"[DEBUG] copy_number - found site_id in settings button: {site_id}")
                            break
        else:
            # Invalid format
            debug_print(f"[DEBUG] copy_number - invalid format, parts: {parts}")
            await callback_query.answer("Error copying number: invalid format")
            return
        
        # Final check if site_id is still None, try to get it from storage
        if not site_id:
            debug_print(f"[DEBUG] copy_number - site_id still not found, checking websites in storage")
            if storage["websites"]:
                site_id = next(iter(storage["websites"]))
                debug_print(f"[DEBUG] copy_number - using first available site_id from storage: {site_id}")
        
        debug_print(f"[DEBUG] copy_number - final number: {number}, site_id: {site_id}")
        
        # Get update button state
        is_updated = False
        if len(callback_query.message.reply_markup.inline_keyboard) > 0 and len(callback_query.message.reply_markup.inline_keyboard[0]) > 1:
            update_button = callback_query.message.reply_markup.inline_keyboard[0][1]
            is_updated = update_button.text == "✅ Updated Number"
            debug_print(f"[DEBUG] copy_number - determined is_updated: {is_updated}")

        # Show copy animation
        debug_print(f"[DEBUG] copy_number - showing copy animation")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Copied", callback_data="none")
        ]])

        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await asyncio.sleep(2)  # Reduced from 4 seconds to 2 for better UX
        
        # Make sure we have a valid site_id before restoring
        if not site_id:
            debug_print(f"[DEBUG] copy_number - WARNING: site_id is still None before restoring keyboard")
            # Extract from any valid settings button as last resort
            for row in callback_query.message.reply_markup.inline_keyboard:
                for button in row:
                    if button.callback_data and "settings_" in button.callback_data:
                        site_id = button.callback_data.split("_")[1]
                        debug_print(f"[DEBUG] copy_number - extracted site_id from settings button: {site_id}")
                        break
        
        # Get the website object to properly restore the keyboard
        website = None
        if site_id:
            website = storage["websites"].get(site_id)
            debug_print(f"[DEBUG] copy_number - found website for site_id {site_id}: {website is not None}")
        
        # Restore the full keyboard with the extracted site_id
        debug_print(f"[DEBUG] copy_number - restoring keyboard with number: {number}, is_updated: {is_updated}, site_id: {site_id}")
        final_keyboard = get_buttons(number, updated=is_updated, site_id=site_id)
        
        # Make sure the final keyboard isn't None
        if final_keyboard is None:
            debug_print(f"[DEBUG] copy_number - get_buttons returned None, using fallback keyboard")
            # Fallback to generate a basic keyboard
            final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📋 Copy Number",
                                         callback_data=f"copy_{number}_{site_id}"),
                    InlineKeyboardButton(
                        text=("✅ Updated Number" if is_updated else "🔄 Update Number"),
                        callback_data=f"update_{number}_{site_id}")
                ],
                [
                    InlineKeyboardButton(text="🔪 Split",
                                         callback_data=f"split_{number}_{site_id}"),
                    InlineKeyboardButton(text="⚙️ Settings",
                                         callback_data=f"settings_{site_id}")
                ],
                [
                    InlineKeyboardButton(
                        text="🌐 Visit Webpage",
                        url=f"{get_base_url()}/number/{number}" if get_base_url() else "")
                ]
            ])
        
        # Apply the restored keyboard
        try:
            debug_print(f"[DEBUG] copy_number - applying restored keyboard")
            await callback_query.message.edit_reply_markup(reply_markup=final_keyboard)
            debug_print(f"[DEBUG] copy_number - keyboard restored successfully")
        except Exception as e:
            debug_print(f"[DEBUG] copy_number - error applying restored keyboard: {e}")
            # Try to use the original keyboard as fallback
            try:
                if 'original_keyboard' in locals():
                    debug_print(f"[DEBUG] copy_number - trying to restore original keyboard")
                    await callback_query.message.edit_reply_markup(reply_markup=original_keyboard)
            except Exception as orig_e:
                debug_print(f"[DEBUG] copy_number - error restoring original keyboard: {orig_e}")
        
        # Show success message
        await callback_query.answer("Number copied!")
        debug_print(f"[DEBUG] copy_number - completed successfully")
        
    except Exception as e:
        debug_print(f"[DEBUG] copy_number - error in function: {e}")
        await callback_query.answer("Error copying number")
        
        # Try to restore the original keyboard layout if possible
        try:
            parts = callback_query.data.split("_")
            if len(parts) >= 3:
                number = parts[1]
                site_id = parts[2]
                is_updated = False
                debug_print(f"[DEBUG] copy_number - attempting emergency restoration with number: {number}, site_id: {site_id}")
                await callback_query.message.edit_reply_markup(
                    reply_markup=get_buttons(number, updated=is_updated, site_id=site_id))
        except Exception as restore_error:
            debug_print(f"[DEBUG] copy_number - error restoring keyboard: {restore_error}")
            # Last resort fallback
            try:
                if 'original_keyboard' in locals() and original_keyboard:
                    debug_print(f"[DEBUG] copy_number - last resort: trying to restore original keyboard")
                    await callback_query.message.edit_reply_markup(reply_markup=original_keyboard)
            except:
                debug_print(f"[DEBUG] copy_number - all restoration attempts failed")
                pass


async def update_number(callback_query: CallbackQuery):
    """Update number for a website"""
    try:
        # Extract number and site_id from callback data
        parts = callback_query.data.split('_')
        if len(parts) >= 3:
            number = parts[1]
            site_id = extract_valid_site_id(callback_query)
        elif len(parts) > 1:
            number = parts[1]
            site_id = extract_valid_site_id(callback_query)
        else:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
        
        debug_print(f"[DEBUG] update_number - site_id: {site_id}, number: {number}")
        
        # Try to find the website in storage
        website = storage["websites"].get(site_id)
        debug_print(f"[DEBUG] update_number - website found: {website is not None}")
        
        await save_last_number(int(number), site_id)
        
        # Store the updated state in the website object
        if website:
            debug_print(f"[DEBUG] update_number - before setting button_updated: {getattr(website, 'button_updated', False)}")
            website.button_updated = True
            debug_print(f"[DEBUG] update_number - after setting button_updated: {website.button_updated}")
            # Save the updated website data to persist the button_updated state
            await save_website_data(site_id)
            debug_print(f"[DEBUG] update_number - saved website data with button_updated=True")

        try:
            has_countdown = False
            message_text = callback_query.message.caption
            if message_text and "⏱ Next notification in:" in message_text:
                has_countdown = True
                new_message = message_text.split("\n\n⏱")[0]

            # Store the original buttons to restore if needed
            original_keyboard = callback_query.message.reply_markup

            # Show updating animation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Updating to:", callback_data="none")
            ]])
            await callback_query.message.edit_reply_markup(reply_markup=keyboard)
            await asyncio.sleep(2)

            updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"{number}", callback_data="none")
            ]])
            await callback_query.message.edit_reply_markup(
                reply_markup=updated_keyboard)
            await asyncio.sleep(2)

            # Get the final keyboard with updated=True
            final_keyboard = get_buttons(number, updated=True, site_id=site_id)

            # Make sure the final keyboard isn't None
            if final_keyboard is None:
                # Fallback to generate a basic keyboard
                final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📋 Copy Number",
                                             callback_data="copy_number"),
                        InlineKeyboardButton(
                            text="✅ Updated Number",
                            callback_data=f"update_{number}_{site_id}")
                    ],
                    [
                        InlineKeyboardButton(text="🔪 Split",
                                             callback_data=f"split_{number}_{site_id}"),
                        InlineKeyboardButton(text="⚙️ Settings",
                                             callback_data=f"settings_{site_id}")
                    ],
                    [
                        InlineKeyboardButton(
                            text="🌐 Visit Webpage",
                            url=f"{get_base_url()}/number/{number}" if get_base_url() else "")
                    ]
                ])

            if has_countdown:
                try:
                    await callback_query.bot.edit_message_caption(
                        chat_id=callback_query.message.chat.id,
                        message_id=callback_query.message.message_id,
                        caption=new_message,
                        parse_mode="Markdown",
                        reply_markup=final_keyboard)
                except Exception as e:
                    if "message is not modified" not in str(e):
                        debug_print(f"Error updating message caption: {e}")
                        # Try to restore original keyboard
                        try:
                            await callback_query.message.edit_reply_markup(
                                reply_markup=original_keyboard)
                        except:
                            pass
            else:
                try:
                    await callback_query.message.edit_reply_markup(
                        reply_markup=final_keyboard)
                except Exception as e:
                    if "message is not modified" not in str(e):
                        debug_print(f"Error updating reply markup: {e}")
                        # Try to restore original keyboard
                        try:
                            await callback_query.message.edit_reply_markup(
                                reply_markup=original_keyboard)
                        except:
                            pass


            if CHAT_ID in storage["active_countdown_tasks"]:
                storage["active_countdown_tasks"][CHAT_ID].cancel()
                del storage["active_countdown_tasks"][CHAT_ID]

            await callback_query.answer("Number updated successfully!")

        except Exception as e:
            debug_print(f"Error in update_number: {e}")
            await callback_query.answer("Error updating number")
            # Try to restore the buttons in case of error
            try:
                website = storage["websites"].get(site_id)
                if website and website.last_number:
                    await callback_query.message.edit_reply_markup(
                        reply_markup=get_buttons(website.last_number,
                                                 site_id=site_id))
            except:
                pass

    except:
        pass


async def update_multi_numbers(callback_query: CallbackQuery):
    """Update multiple numbers for a website"""
    try:
        # Extract site_id more reliably by removing the 'update_multi_' prefix
        callback_data = callback_query.data
        if callback_data.startswith("update_multi_"):
            site_id = extract_valid_site_id(callback_query)
        else:
            site_id = extract_valid_site_id(callback_query)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
            
        debug_print(f"Extracted site_id: {site_id}")  # Debug log
        
        # Try to find the website in storage
        website = storage["websites"].get(site_id)
        debug_print(f"[DEBUG] update_multi_numbers - website found: {website is not None}")
        
        # Store the updated state in the website object
        if website:
            debug_print(f"[DEBUG] update_multi_numbers - before setting button_updated: {getattr(website, 'button_updated', False)}")
            website.button_updated = True
            debug_print(f"[DEBUG] update_multi_numbers - after setting button_updated: {website.button_updated}")
            # Save the updated website data to persist the button_updated state
            await save_website_data(site_id)
            debug_print(f"[DEBUG] update_multi_numbers - saved website data with button_updated=True")
        
        # Store the original keyboard to restore if needed
        original_keyboard = callback_query.message.reply_markup
        
        # Check if this is an initial run notification by examining the original keyboard
        is_initial_run = False
        
        # First, check if the current layout is an initial run layout (single button in first row)
        if callback_query.message and callback_query.message.reply_markup:
            # Check if the first row has only one button (initial run layout)
            if (len(callback_query.message.reply_markup.inline_keyboard) > 0 and 
                len(callback_query.message.reply_markup.inline_keyboard[0]) == 1):
                is_initial_run = True
                debug_print(f"[DEBUG] update_multi_numbers - detected initial run layout from current keyboard")
        
        # If not determined from keyboard, use other detection methods
        if not is_initial_run:
            # For site_2, we need special detection logic
            if site_id == "site_2":
                # Check if this is the first time we're showing numbers for site_2
                if (hasattr(website, 'last_number') and website.last_number and 
                    (not hasattr(website, 'latest_numbers') or len(website.latest_numbers) <= 1)):
                    is_initial_run = True
                    debug_print(f"Determined initial run for site_2 based on last_number only or single latest_number")
                # If we have both last_number and latest_numbers, check if they match
                elif (hasattr(website, 'last_number') and website.last_number and 
                      hasattr(website, 'latest_numbers') and website.latest_numbers):
                    # If the first number in latest_numbers matches last_number, it's likely an initial run
                    if str(website.last_number) in str(website.latest_numbers[0]):
                        is_initial_run = True
                        debug_print(f"Determined initial run for site_2 based on matching last_number and latest_numbers[0]")
                    else:
                        is_initial_run = False
                        debug_print(f"Determined non-initial run for site_2 based on non-matching last_number and latest_numbers")
            # For other sites or if above checks don't determine, use fallback methods
            else:
                # Check if website_data.json exists - if not, it's an initial run
                website_data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'website_data.json')
                if not os.path.exists(website_data_path):
                    is_initial_run = True
                    debug_print(f"Determined initial run based on missing website_data.json file: {website_data_path}")
                # If file exists, check if we have a flag indicating initial run
                elif hasattr(website, 'first_run'):
                    is_initial_run = website.first_run
                    debug_print(f"Using first_run flag: {is_initial_run}")
                # If no clear indicators, fall back to checking latest_numbers
                elif (not hasattr(website, 'latest_numbers') or 
                      not website.latest_numbers or 
                      len(website.latest_numbers) == 0):
                    is_initial_run = True
                    debug_print("Determined initial run based on missing latest_numbers")
        
        debug_print(f"[DEBUG] update_multi_numbers - is_initial_run: {is_initial_run}")

        # Show updating animation similar to single type
        try:
            has_countdown = False
            message_text = callback_query.message.caption
            if message_text and "⏱ Next notification in:" in message_text:
                has_countdown = True
                new_message = message_text.split("\n\n⏱")[0]

            # Show updating animation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Updating to:", callback_data="none")
            ]])
            await callback_query.message.edit_reply_markup(reply_markup=keyboard)
            await asyncio.sleep(2)
            
            # If we have numbers to display in the animation, show the first one
            display_number = ""
            if website and hasattr(website, 'latest_numbers') and website.latest_numbers:
                display_number = website.latest_numbers[0]
            elif website and hasattr(website, 'last_number') and website.last_number:
                display_number = f"+{website.last_number}"
                
            if display_number:
                updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=f"{display_number}", callback_data="none")
                ]])
                await callback_query.message.edit_reply_markup(reply_markup=updated_keyboard)
                await asyncio.sleep(2)
        except Exception as e:
            debug_print(f"Error during animation: {e}")
            # Continue with the update even if animation fails

        # Create a unified data structure for the keyboard
        keyboard_data = {
            "site_id": site_id,
            "updated": True,  # Always set to True since we're updating
            "type": getattr(website, 'type', 'multiple'),
            "is_initial_run": is_initial_run,  # Pass the detected initial run state
            "url": getattr(website, 'url', get_base_url() or "")
        }
        
        # Add type-specific data
        if keyboard_data["type"] == "single":
            keyboard_data["number"] = getattr(website, 'last_number', "")
        else:  # multiple type
            if is_initial_run:
                # For initial run, use last_number to maintain single button layout
                if hasattr(website, 'last_number') and website.last_number:
                    keyboard_data["numbers"] = [f"+{website.last_number}"]
                elif hasattr(website, 'latest_numbers') and website.latest_numbers:
                    # If we don't have last_number, use the first number from latest_numbers
                    keyboard_data["numbers"] = [website.latest_numbers[0]]
                else:
                    keyboard_data["numbers"] = []
            else:
                # For non-initial run, use the full latest_numbers array
                keyboard_data["numbers"] = getattr(website, 'latest_numbers', [])
                if not keyboard_data["numbers"] and hasattr(website, 'last_number'):
                    keyboard_data["numbers"] = [f"+{website.last_number}"]
        
        debug_print(f"[DEBUG] update_multi_numbers - keyboard_data: {keyboard_data}")
        
        # Create the unified keyboard
        final_keyboard = create_unified_keyboard(keyboard_data, website)
        
        # If keyboard creation failed, log the error and return
        if final_keyboard is None:
            debug_print(f"ERROR: Failed to create keyboard with unified function for site_id: {site_id}")
            debug_print(f"Keyboard data: {keyboard_data}")
            return
        
        try:
            await callback_query.message.edit_reply_markup(
                reply_markup=final_keyboard)
        except Exception as e:
            if "message is not modified" not in str(e):
                debug_print(f"ERROR updating reply markup: {e}")

        # Show success message or error message depending on whether website was found
        if site_id not in storage["websites"]:
            await callback_query.answer("Website configuration not found, but animation completed")
        else:
            await callback_query.answer("Numbers updated successfully!")
    except Exception as e:
        debug_print(f"ERROR in update_multi_numbers: {e}")
        await callback_query.answer("Error updating numbers")


async def handle_settings(callback_query: CallbackQuery):
    try:
        site_id = extract_valid_site_id(callback_query)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
        debug_print(f"Settings - extracted site_id: {site_id}")
        
        # Get website configuration
        website = storage["websites"].get(site_id)
        debug_print(f"[DEBUG] handle_settings - website found: {website is not None}")
        
        # Determine if repeat notification is enabled
        repeat_status = "Disable" if ENABLE_REPEAT_NOTIFICATION else "Enable"
        
        # Create settings keyboard
        settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{repeat_status} Repeat Notification",
                    callback_data=f"toggle_repeat_{site_id}")
            ],
            [
                InlineKeyboardButton(
                    text="Stop Monitoring",
                    callback_data=f"settings_monitoring_{site_id}")
            ],
            [
                InlineKeyboardButton(text="« Back",
                                     callback_data=f"back_to_main_{site_id}")
            ]
        ])

        # Update the message with new keyboard - always replace all buttons
        await callback_query.message.edit_reply_markup(
            reply_markup=settings_keyboard)

    except Exception as e:
        debug_print(f"Error in handle_settings: {e}")


async def handle_monitoring_settings(callback_query: CallbackQuery):
    try:
        # Extract the original site_id from the callback data
        parts = callback_query.data.split("_")
        if len(parts) >= 4:  # settings_monitoring_site_X
            original_site_id = "_".join(parts[2:])  # Join all parts after "settings_monitoring"
        else:
            await callback_query.answer("Invalid monitoring settings request")
            return

        debug_print(f"Monitoring settings - original site_id: {original_site_id}")
        
        # Create buttons for each website, displaying 2 per row
        buttons = []
        current_row = []

        # Add a button for each website with status indicator for the toggled site
        for s_id, website in storage["websites"].items():
            # Extract website name from URL
            website_name = extract_website_name(website.url, website.type)

            # Show "Disabled" text for disabled sites
            if not website.enabled:
                display_name = f"{website_name} : Disabled"
            else:
                display_name = website_name

            # Extract just the numeric part of the site_id for cleaner callback data
            s_num = s_id.split("_")[1] if "_" in s_id else "1"
            
            current_row.append(
                InlineKeyboardButton(
                    text=display_name,
                    callback_data=f"toggle_site_{s_num}_{original_site_id}"))  # Pass original_site_id in callback

            # When we have 2 buttons in the row, add it to buttons and start a new row
            if len(current_row) == 2:
                buttons.append(current_row)
                current_row = []

        # Add any remaining buttons if we have an odd number
        if current_row:
            buttons.append(current_row)

        # Add back button with original site_id
        buttons.append([
            InlineKeyboardButton(text="« Back to Settings",
                                 callback_data=f"settings_{original_site_id}")
        ])

        # Create monitoring settings keyboard
        monitoring_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        # Update the message with new keyboard
        await callback_query.message.edit_reply_markup(
            reply_markup=monitoring_keyboard)

    except Exception as e:
        debug_print(f"Error in monitoring settings: {e}")


async def toggle_site_monitoring(callback_query: CallbackQuery):
    """Toggle monitoring for a specific site"""
    try:
        # Extract both the target site to toggle and the original site_id
        parts = callback_query.data.split("_")
        if len(parts) >= 4:  # toggle_site_X_site_Y
            target_site_num = parts[2]
            original_site_id = "_".join(parts[3:])  # Join all parts after "toggle_site_X"
            target_site_id = f"site_{target_site_num}"
        else:
            await callback_query.answer("Invalid toggle request")
            return
            
        debug_print(f"Toggle site monitoring - target_site_id: {target_site_id}, original_site_id: {original_site_id}")
        
        # Toggle the site's enabled status
        if target_site_id in storage["websites"]:
            website = storage["websites"][target_site_id]
            website.enabled = not website.enabled

            # Log the monitoring status change
            status = "started" if website.enabled else "stopped"
            website_name = extract_website_name(website.url, website.type)
            debug_print(f"Monitoring {status} for {website_name} Website")

            # We're in the monitoring settings menu, update it with the new status
            # Create buttons for each website, displaying 2 per row
            buttons = []
            current_row = []

            # Add a button for each website with status indicator for the toggled site
            for s_id, site in storage["websites"].items():
                # Extract website name from URL
                site_name = extract_website_name(site.url, site.type)

                # Show "Disabled" text for disabled sites
                if not site.enabled:
                    display_name = f"{site_name} : Disabled"
                else:
                    display_name = site_name

                # Extract just the numeric part of the site_id for cleaner callback data
                s_num = s_id.split("_")[1] if "_" in s_id else "1"
                
                current_row.append(
                    InlineKeyboardButton(
                        text=display_name,
                        callback_data=f"toggle_site_{s_num}_{original_site_id}"))  # Pass original_site_id in callback

                # When we have 2 buttons in the row, add it to buttons and start a new row
                if len(current_row) == 2:
                    buttons.append(current_row)
                    current_row = []

            # Add any remaining buttons if we have an odd number
            if current_row:
                buttons.append(current_row)

            # Add back button with original site_id
            buttons.append([
                InlineKeyboardButton(
                    text="« Back to Settings",
                    callback_data=f"settings_{original_site_id}")
            ])

            # Update the keyboard
            monitoring_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback_query.message.edit_reply_markup(
                reply_markup=monitoring_keyboard)

            # Save the updated website data
            await save_website_data(target_site_id)

            status = "enabled" if website.enabled else "disabled"
            await callback_query.answer(
                f"Monitoring {status} for {website_name} Website")
        else:
            await callback_query.answer(
                f"Error: Website {target_site_id} not found")
    except Exception as e:
        debug_print(f"Error in toggle_site_monitoring: {e}")
        await callback_query.answer("Error toggling site monitoring")


async def toggle_repeat_notification(callback_query: CallbackQuery):
    site_id = extract_valid_site_id(callback_query)
    if not site_id:
        await callback_query.answer("Site ID missing or invalid. Please try again.")
        return

    try:
        global ENABLE_REPEAT_NOTIFICATION
        # Log previous state before toggling
        previous_state = ENABLE_REPEAT_NOTIFICATION

        # Toggle the state
        ENABLE_REPEAT_NOTIFICATION = not ENABLE_REPEAT_NOTIFICATION
        print(
            f"Repeat notification state: {'Enabled' if ENABLE_REPEAT_NOTIFICATION else 'Disabled'}"
        )

        # Update repeat interval if needed
        if ENABLE_REPEAT_NOTIFICATION and storage["repeat_interval"] is None:
            storage["repeat_interval"] = DEFAULT_REPEAT_INTERVAL
            print(
                f"Repeat interval set to default: {DEFAULT_REPEAT_INTERVAL} seconds ({format_time(DEFAULT_REPEAT_INTERVAL)})"
            )

        # Log the current interval
        if not DEFAULT_REPEAT_INTERVAL:
            print(
                f"Current repeat interval: {storage['repeat_interval']} seconds"
            )

        # Update the settings keyboard with new status
        repeat_status = "Disable" if ENABLE_REPEAT_NOTIFICATION else "Enable"

        # Check if the site is enabled to determine the button text
        site_enabled = True
        if site_id in storage["websites"]:
            site_enabled = storage["websites"][site_id].enabled

        monitoring_status = "Disable" if site_enabled else "Enable"
        site_display = site_id.replace("_", " ")

        settings_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{repeat_status} Repeat Notification",
                    callback_data=f"toggle_repeat_{site_id}")
            ],
            [
                InlineKeyboardButton(
                    text="Stop Monitoring",
                    callback_data=f"settings_monitoring_{site_id}")
            ],
            [
                InlineKeyboardButton(text="« Back",
                                     callback_data=f"back_to_main_{site_id}")
            ]
        ])

        # Update the message with new keyboard
        await callback_query.message.edit_reply_markup(
            reply_markup=settings_keyboard)

        status = "enabled" if ENABLE_REPEAT_NOTIFICATION else "disabled"
        await callback_query.answer(f"Repeat notification {status}")

    except Exception as e:
        pass


async def back_to_main(callback_query: CallbackQuery):
    """Go back to the main message from settings"""
    try:
        site_id = extract_valid_site_id(callback_query)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
            
        debug_print(f"Back - extracted site_id: {site_id}")
        
        # Get website configuration
        website = storage["websites"].get(site_id)
        debug_print(f"Website found: {website is not None}")
        debug_print(f"[DEBUG] back_to_main - website object: {website}")
        if website:
            debug_print(f"[DEBUG] back_to_main - initial button_updated state: {getattr(website, 'button_updated', False)}")
            debug_print(f"[DEBUG] back_to_main - website type: {getattr(website, 'type', 'single')}")

        # Determine if this is an initial run
        is_initial_run = False
        
        # First, check if this is the first time we're showing this website's data
        # For all multiple type websites, check if this is the first notification
        if website and website.type == "multiple":
            # Check if the first number in latest_numbers matches last_number
            # This is a strong indicator that it's an initial run
            if (hasattr(website, 'last_number') and website.last_number and 
                hasattr(website, 'latest_numbers') and website.latest_numbers):
                first_num = website.latest_numbers[0]
                if isinstance(first_num, str) and first_num.startswith('+'):
                    first_num = first_num[1:]
                if str(website.last_number) == str(first_num):
                    is_initial_run = True
                    debug_print(f"[DEBUG] back_to_main - Determined initial run for {site_id} based on matching last_number and latest_numbers[0]")
            
            # Check if this is the first time we're showing numbers for this website
            if (hasattr(website, 'last_number') and website.last_number and 
                (not hasattr(website, 'latest_numbers') or len(website.latest_numbers) <= 1)):
                is_initial_run = True
                debug_print(f"Determined initial run for {site_id} based on last_number only or single latest_number")
            # If we have both last_number and latest_numbers, check if they match
            elif (hasattr(website, 'last_number') and website.last_number and 
                  hasattr(website, 'latest_numbers') and website.latest_numbers):
                # If the first number in latest_numbers matches last_number, it's likely an initial run
                if str(website.last_number) in str(website.latest_numbers[0]):
                    is_initial_run = True
                    debug_print(f"Determined initial run for {site_id} based on matching last_number and latest_numbers[0]")
                else:
                    is_initial_run = False
                    debug_print(f"Determined non-initial run for {site_id} based on non-matching last_number and latest_numbers")
        
        # For all websites, use fallback methods if initial run not determined
        if not is_initial_run:
            # Check if website_data.json exists - if not, it's an initial run
            website_data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'website_data.json')
            if not os.path.exists(website_data_path):
                is_initial_run = True
                debug_print(f"Determined initial run based on missing website_data.json file: {website_data_path}")
            # If file exists, check if we have a flag indicating initial run
            elif hasattr(website, 'first_run'):
                is_initial_run = website.first_run
                debug_print(f"Using first_run flag: {is_initial_run}")
            # If no clear indicators, fall back to checking latest_numbers
            elif (not hasattr(website, 'latest_numbers') or 
                  not website.latest_numbers or 
                  len(website.latest_numbers) == 0):
                is_initial_run = True
                debug_print("Determined initial run based on missing latest_numbers")
                
        # For all multiple type websites, treat the first time we see them as initial run
        # This ensures consistent behavior across all multiple type websites
        if website and website.type == "multiple":
            # Check if this is the first notification for this website
            # If we don't have a 'first_notification' flag in the website object, assume it's an initial run
            if not hasattr(website, 'first_notification'):
                is_initial_run = True
                # Set the flag to indicate this is no longer the first notification
                website.first_notification = True
                await save_website_data(site_id)
                debug_print(f"[DEBUG] back_to_main - Treating {site_id} as initial run (first notification)")
        
        # Check if the button was in "updated" state by looking at the website object
        was_updated = False
        if hasattr(website, 'button_updated') and website.button_updated:
            was_updated = True
            debug_print(f"[DEBUG] back_to_main - Detected button_updated=True from website object")
        else:
            debug_print(f"[DEBUG] back_to_main - button_updated not found or False in website object")
            # Fallback to checking the current keyboard
            if callback_query.message and callback_query.message.reply_markup:
                debug_print(f"[DEBUG] back_to_main - checking keyboard for updated state")
                for row in callback_query.message.reply_markup.inline_keyboard:
                    for button in row:
                        if button.callback_data and (
                            button.callback_data.startswith(f"update_multi_{site_id}") or
                            button.callback_data.startswith(f"update_number_{site_id}") or
                            (button.callback_data.startswith("update_") and button.callback_data.endswith(f"_{site_id}"))
                        ):
                            debug_print(f"[DEBUG] back_to_main - found update button with text: {button.text}")
                            if "✅" in button.text:
                                was_updated = True
                                debug_print(f"[DEBUG] back_to_main - Detected button_updated=True from keyboard")
                                # Also set it in the website object for future use
                                website.button_updated = True
                                # Save the updated state to persistent storage
                                await save_website_data(site_id)
                                debug_print(f"[DEBUG] back_to_main - saved website data with button_updated=True")
                                break

        # Create a unified data structure for the keyboard
        keyboard_data = {
            "site_id": site_id,
            "updated": was_updated,
            "type": getattr(website, 'type', 'single'),
            "is_initial_run": is_initial_run,
            "url": getattr(website, 'url', get_base_url() or "")
        }
        
        # Add type-specific data
        if keyboard_data["type"] == "single":
            keyboard_data["number"] = getattr(website, 'last_number', "")
        else:  # multiple type
            if is_initial_run:
                # For initial run, use last_number to maintain single button layout
                if hasattr(website, 'last_number') and website.last_number:
                    keyboard_data["numbers"] = [f"+{website.last_number}"]
                elif hasattr(website, 'latest_numbers') and website.latest_numbers:
                    # If we don't have last_number, use the first number from latest_numbers
                    keyboard_data["numbers"] = [website.latest_numbers[0]]
                else:
                    keyboard_data["numbers"] = []
            else:
                # For non-initial run, use the full latest_numbers array
                keyboard_data["numbers"] = getattr(website, 'latest_numbers', [])
                if not keyboard_data["numbers"] and hasattr(website, 'last_number'):
                    keyboard_data["numbers"] = [f"+{website.last_number}"]
        
        debug_print(f"[DEBUG] back_to_main - keyboard_data: {keyboard_data}")
        
        # Create the unified keyboard
        final_keyboard = create_unified_keyboard(keyboard_data, website)
        debug_print(f"[DEBUG] back_to_main - created keyboard with updated={was_updated}")
        
        # If keyboard creation failed, log the error and return
        if final_keyboard is None:
            debug_print(f"ERROR: Failed to create keyboard with unified function for site_id: {site_id}")
            debug_print(f"Keyboard data: {keyboard_data}")
            return
        
        # Update the message with the appropriate keyboard
        await callback_query.message.edit_reply_markup(reply_markup=final_keyboard)

    except Exception as e:
        debug_print(f"ERROR in back_to_main: {e}")
        # Don't create a fallback keyboard, just log the error


async def split_number(callback_query: CallbackQuery):
    try:
        parts = callback_query.data.split("_")
        if len(parts) > 2:
            number_str = parts[1]
            site_id = extract_valid_site_id(callback_query)
        elif len(parts) > 1:
            number_str = parts[1]
            site_id = extract_valid_site_id(callback_query)
        else:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return
        
        # Remove country code from the number
        number_without_country_code = remove_country_code(number_str)
        split_message = f"`{number_without_country_code}`"

        # Send the split number message
        temp_message = await callback_query.bot.send_message(
            chat_id=callback_query.message.chat.id,
            text=split_message,
            parse_mode="Markdown")

        # Create a task to delete the message after 30 seconds
        asyncio.create_task(
            delete_message_after_delay(callback_query.bot, temp_message, 30))

    except Exception as e:
        debug_print(f"Error in split_number: {e}")
        await callback_query.answer("Error splitting number")


async def send_ping_reply(message: Message):
    await message.bot.send_message(chat_id=message.from_user.id,
                                   text="I am now online 🌐")
    await message.delete()


async def set_repeat_interval(message: Message, command: CommandObject):
    try:
        if command.args:
            args = command.args.lower().strip()

            # Parse the new interval
            new_interval = None

            if args in ["default", "true"]:
                new_interval = DEFAULT_REPEAT_INTERVAL
                global ENABLE_REPEAT_NOTIFICATION
                # Only print the state change if it's actually changing
                if not ENABLE_REPEAT_NOTIFICATION:
                    ENABLE_REPEAT_NOTIFICATION = True
                    print(f"Repeat notification state: Enabled")
                else:
                    ENABLE_REPEAT_NOTIFICATION = True

            # Check for the "x" prefix for minutes
            elif args.startswith("x") and args[1:].isdigit():
                minutes = int(args[1:])
                if minutes <= 0:
                    error_msg = await message.reply(
                        "⚠️ Please provide a positive number of minutes")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    await message.delete()
                    return

                new_interval = minutes * 60  # Convert minutes to seconds

            elif args.isdigit():
                seconds = int(args)
                if seconds <= 0:
                    error_msg = await message.reply(
                        "⚠️ Please provide a positive number of seconds")
                    await asyncio.sleep(5)
                    await error_msg.delete()
                    await message.delete()
                    return

                new_interval = seconds

            else:
                error_msg = await message.reply(
                    "⚠️ Please provide a valid number, 'default', 'true', or use 'x' prefix for minutes (e.g., 'x10' for 10 minutes). Example: `/set_repeat 300`, `/set_repeat x5`, or `/set_repeat default`"
                )
                await asyncio.sleep(5)
                await error_msg.delete()
                await message.delete()
                return

            # Save the new interval and enable repeat notifications
            storage["repeat_interval"] = new_interval
            
            # Only print the state change if repeat notification was disabled
            if not ENABLE_REPEAT_NOTIFICATION:
                ENABLE_REPEAT_NOTIFICATION = True
                print("Repeat notification state: Enabled")
            else:
                ENABLE_REPEAT_NOTIFICATION = True
                
            print(f"Repeat interval set to: {new_interval} seconds ({format_time(new_interval)})")

            # Check if there's an active countdown
            if CHAT_ID in storage["active_countdown_tasks"]:
                # Cancel the existing task
                storage["active_countdown_tasks"][CHAT_ID].cancel()
                storage["active_countdown_tasks"].pop(CHAT_ID, None)

                # Update the current message with the new countdown if there's an active notification
                if storage["latest_notification"]["message_id"]:
                    message_id = storage["latest_notification"]["message_id"]
                    number = storage["latest_notification"]["number"]
                    flag_url = storage["latest_notification"]["flag_url"]
                    site_id = storage["latest_notification"].get(
                        "site_id", "site_1")

                    # Update the message with the new countdown
                    current_message = (
                        f"🎁 *New Number Added* 🎁\n\n"
                        f"`+{number}` check it out! 💖\n\n"
                        f"⏱ Next notification in: *{format_time(new_interval)}*"
                    )

                    try:
                        await message.bot.edit_message_caption(
                            chat_id=CHAT_ID,
                            message_id=message_id,
                            caption=current_message,
                            parse_mode="Markdown",
                            reply_markup=get_buttons(number, site_id=site_id))

                        # Create a new countdown task with the updated interval
                        countdown_task = asyncio.create_task(
                            update_message_with_countdown(
                                message.bot, message_id, number, flag_url,
                                site_id))
                        storage["active_countdown_tasks"][
                            CHAT_ID] = countdown_task
                    except Exception as e:
                        debug_print(
                            f"Error updating message with new countdown: {e}")

            await message.delete()

        else:
            error_msg = await message.reply(
                "⚠️ Please provide a number of seconds, minutes with 'x' prefix (e.g., 'x10'), or 'default'. Example: `/set_repeat 300`, `/set_repeat x5`, or `/set_repeat default`"
            )
            await asyncio.sleep(5)
            await error_msg.delete()
            await message.delete()
    except Exception as e:
        debug_print(f"Error in set_repeat_interval: {e}")
        error_msg = await message.reply(
            "⚠️ An error occurred. Please try again.")
        await asyncio.sleep(5)
        await error_msg.delete()
        await message.delete()


async def stop_repeat_notification(message: Message):
    global ENABLE_REPEAT_NOTIFICATION
    ENABLE_REPEAT_NOTIFICATION = False

    if CHAT_ID in storage["active_countdown_tasks"]:
        storage["active_countdown_tasks"][CHAT_ID].cancel()
        storage["active_countdown_tasks"].pop(CHAT_ID, None)

    try:
        if storage["latest_notification"]["message_id"]:
            number = storage["latest_notification"]["number"]
            basic_message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"

            await message.bot.edit_message_caption(
                chat_id=CHAT_ID,
                message_id=storage["latest_notification"]["message_id"],
                caption=basic_message,
                parse_mode="Markdown",
                reply_markup=get_buttons(number))
    except Exception as e:
        debug_print(f"Error removing countdown from notification: {e}")

    await message.delete()


async def send_startup_message(bot):
    if CHAT_ID:
        try:
            await bot.send_message(CHAT_ID, text="At Your Service 🍒🍄")
        except Exception as e:
            debug_print(f"⚠️ Failed to send startup message: {e}")


# --- Universal Site ID Extraction Helper ---
def extract_valid_site_id(callback_query):
    parts = callback_query.data.split("_")
    debug_print(f"Parts: {parts}")
    # Try to extract a valid site_id from callback data
    for i in range(len(parts)-1, 0, -1):
        candidate = "_".join(parts[i:])
        if candidate in storage["websites"]:
            return candidate
    # Fallback: first available site_id in storage
    if storage["websites"]:
        return next(iter(storage["websites"]))
    return None