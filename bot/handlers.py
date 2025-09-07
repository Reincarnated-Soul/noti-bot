import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import (
    CHAT_ID, DEV_MODE, SINGLE_MODE, debug_print
)
from bot.notifications import create_keyboard, caption_message
from bot.storage import (
    save_last_number, save_website_data, storage, get_notification_state,
    update_notification_state
)
from bot.utils import (
    KeyboardData, delete_message_after_delay, extract_website_name, format_phone_number,
    get_base_url, get_selected_numbers_for_buttons, parse_callback_data
)

def register_handlers(dp: Dispatcher):
    """Register all handlers"""
    # Callback queries
    dp.callback_query.register(
        handle_settings,
        lambda c: c.data.startswith("settings_") and not c.
        data.startswith("settings_monitoring_"))
    dp.callback_query.register(
        handle_monitoring_settings,
        lambda c: c.data.startswith("settings_monitoring_"))
    dp.callback_query.register(
        toggle_site_monitoring,
        lambda c: c.data.startswith("toggle_monitoring_"))
    dp.callback_query.register(
        toggle_single_mode,
        lambda c: c.data.startswith("toggle_single_mode_"))
    dp.callback_query.register(
        back_to_main,
        lambda c: c.data.startswith("back_to_main_"))
    dp.callback_query.register(
        split_number,
        lambda c: c.data.startswith("split_") or c.data.startswith("number_"))

    # Commands
    dp.message.register(send_log, Command("log"))
    dp.message.register(show_ping, Command("ping"))


async def handle_settings(callback_query: CallbackQuery):
    try:
        # Extract site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid. Please try again.")
            return

        debug_print(f"[DEBUG] Settings - extracted site_id: {site_id}")

        # Get website configuration
        website = storage["websites"].get(site_id)
        debug_print(f"[INFO] handle_settings - website found: {website is not None}")

        if not website:
            await callback_query.answer("Website not found.")
            return

        # Determine if repeat notification is enabled
        single_mode_status = "Disable" if SINGLE_MODE else "Enable"

        # Define base buttons that are common for all types
        base_buttons = [
            [InlineKeyboardButton(
                text="Stop Monitoring",
                callback_data=f"settings_monitoring_{site_id}")
            ],
            [InlineKeyboardButton(
                text="« Back",
                callback_data=f"back_to_main_{site_id}")
            ]
        ]

        # Add single mode button only for multiple type websites
        if website.type == "multiple":
            base_buttons.insert(1, [InlineKeyboardButton(
                text=f"Single Mode : {single_mode_status}",
                callback_data=f"toggle_single_mode_{site_id}")
            ])

        # Create settings keyboard
        settings_keyboard = InlineKeyboardMarkup(inline_keyboard=base_buttons)

        # Update message with settings menu
        await callback_query.message.edit_reply_markup(
            reply_markup=settings_keyboard)

    except Exception as e:
        debug_print(f"[ERROR] Error in handle_settings: {e}")


async def create_monitoring_keyboard(current_page: int, total_sites: int, all_sites: list, site_id: str) -> InlineKeyboardMarkup:
    """Create monitoring settings keyboard with pagination and site toggles"""
    # Constants for pagination
    SITES_PER_PAGE = 12
    SITES_PER_ROW = 2

    # Only use pagination if we have more than 14 sites
    use_pagination = total_sites > 14

    # Calculate total pages
    total_pages = (total_sites + SITES_PER_PAGE - 1) // SITES_PER_PAGE if use_pagination else 1

    # Calculate start and end indices for current page
    start_idx = current_page * SITES_PER_PAGE
    end_idx = min(start_idx + SITES_PER_PAGE, total_sites)

    # Get sites for current page
    current_page_sites = all_sites[start_idx:end_idx]

    debug_print(f"[DEBUG] create_monitoring_keyboard - displaying page {current_page+1}/{total_pages}, sites {start_idx+1}-{end_idx} of {total_sites}")

    # Create buttons for each website
    buttons = []
    current_row = []

    for target_id, site in current_page_sites:
        # Extract website name from URL and format with status
        status = "Disabled" if not site.enabled else "Enable"
        site_name = extract_website_name(site.url, site.type, button_format=True, status=status)
        debug_print(f"[DEBUG] create_monitoring_keyboard - site_name: {site_name}, enabled: {site.enabled}")

        # Create callback data with consistent format - always use original site_id for state
        if use_pagination:
            callback_data = f"toggle_monitoring_page_{current_page}_{target_id}_{site_id}"
        else:
            callback_data = f"toggle_monitoring_{target_id}_{site_id}"

        current_row.append(
            InlineKeyboardButton(
                text=site_name,
                callback_data=callback_data))

        if len(current_row) == SITES_PER_ROW:
            buttons.append(current_row)
            current_row = []

    # Add any remaining buttons if we have an odd number
    if current_row:
        buttons.append(current_row)

    # Add pagination navigation
    if use_pagination:
        nav_row = []

        if current_page > 0:
            nav_row.append(InlineKeyboardButton(
                text="« Back",
                callback_data=f"settings_monitoring_page_{current_page-1}_{site_id}"
            ))

        if current_page < total_pages - 1:
            if len(nav_row) == 0:
                nav_row.append(InlineKeyboardButton(
                    text="⤜ Next Page »",
                    callback_data=f"settings_monitoring_page_{current_page+1}_{site_id}"
                ))
            else:
                nav_row.append(InlineKeyboardButton(
                    text="⤜ Next Page »",
                    callback_data=f"settings_monitoring_page_{current_page+1}_{site_id}"
                ))

        if nav_row:
            buttons.append(nav_row)

    # Always use the original site_id for back navigation
    buttons.append([
        InlineKeyboardButton(
            text="« Back to Settings",
            callback_data=f"settings_{site_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def handle_monitoring_settings(callback_query: CallbackQuery):
    try:
        # Extract the site_id from the callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Invalid monitoring settings request")
            return

        debug_print(f"[INFO] Monitoring settings - site_id: {site_id}")

        # Get all websites
        all_sites = list(storage["websites"].items())
        total_sites = len(all_sites)

        if total_sites == 0:
            await callback_query.answer("No websites configured for monitoring")
            return

        # Calculate current page
        current_page = 0
        if "page" in callback_query.data:
            page_index = parts.index("page")
            if page_index + 1 < len(parts):
                try:
                    current_page = int(parts[page_index + 1])
                except ValueError:
                    current_page = 0

        # Create monitoring settings keyboard
        monitoring_keyboard = await create_monitoring_keyboard(current_page, total_sites, all_sites, site_id)

        # Update the message with new keyboard
        await callback_query.message.edit_reply_markup(reply_markup=monitoring_keyboard)

    except Exception as e:
        debug_print(f"[ERROR] Error in monitoring settings: {e}")
        print(f"[ERROR] Error in monitoring settings: {e}")


async def toggle_site_monitoring(callback_query: CallbackQuery):
    """Toggle monitoring for a specific site"""
    try:
        # Extract both target and original site_ids from callback data
        parts = callback_query.data.split('_')
        debug_print(f"[DEBUG] toggle_site_monitoring - callback data parts: {parts}")
        
        # Handle both page and non-page formats
        if "page" in callback_query.data:
            # Format: toggle_monitoring_page_[page_num]_site_[id]_site_[id]
            if len(parts) < 6:
                await callback_query.answer("Invalid toggle request")
                return
            target_id = f"site_{parts[-3]}"  # Combine 'site' and id
            site_id = f"site_{parts[-1]}"    # Combine 'site' and id
        else:
            # Format: toggle_monitoring_site_[id]_site_[id]
            if len(parts) < 4:
                await callback_query.answer("Invalid toggle request")
                return
            target_id = f"site_{parts[3]}"   # Combine 'site' and id
            site_id = f"site_{parts[-1]}"    # Combine 'site' and id
        
        debug_print(f"[INFO] Toggle site monitoring - toggling site: {target_id}")

        # Toggle the site's enabled status
        if target_id in storage["websites"]:
            website = storage["websites"][target_id]
            website.enabled = not website.enabled

            # Log the monitoring status change
            status = "started" if website.enabled else "stopped"
            website_name = extract_website_name(website.url, website.type)
            print(f"Monitoring {status} for {website_name} Website")

            # Get all websites
            all_sites = list(storage["websites"].items())
            total_sites = len(all_sites)

            # Calculate current page
            current_page = 0
            if "page" in callback_query.data:
                page_index = parts.index("page")
                if page_index + 1 < len(parts):
                    try:
                        current_page = int(parts[page_index + 1])
                    except ValueError:
                        current_page = 0

            # Create monitoring settings keyboard using original site_id
            monitoring_keyboard = await create_monitoring_keyboard(current_page, total_sites, all_sites, site_id)

            # Update the keyboard
            await callback_query.message.edit_reply_markup(reply_markup=monitoring_keyboard)

            # Save the updated website data
            await save_website_data(target_id)

            status = "enabled" if website.enabled else "disabled"
            await callback_query.answer(f"Monitoring {status} for {website_name} Website")
        else:
            await callback_query.answer(f"Error: Website {target_id} not found")
    except Exception as e:
        debug_print(f"[ERROR] Error in toggle_site_monitoring: {e}")
        await callback_query.answer("Error toggling site monitoring")


async def back_to_main(callback_query: CallbackQuery):
    try:
        # Extract site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if not site_id:
            await callback_query.answer("Site ID missing or invalid.")
            return

        debug_print(f"[DEBUG] back_to_main - site_id: {site_id}")
        
        # Get website data
        website = storage["websites"].get(site_id)
        if not website:
            await callback_query.answer("Website not found.")
            return

        # Find notification state by message_id
        message_id = callback_query.message.message_id
        notification_state = next(
            (state for state in storage["notifications"].values() 
             if state.message_id == message_id and state.site_id == site_id),
            None
        )
                
        if not notification_state:
            debug_print("[ERROR] back_to_main - No notification state found for this message")
            await callback_query.answer("Error: State not found")
            return
            
        debug_print(f"[DEBUG] back_to_main - Using notification state: {notification_state}")
        
        # Create and update keyboard
        keyboard = await create_keyboard(notification_state.to_keyboard_data(website.url), website)
        if not keyboard:
            debug_print("[ERROR] back_to_main - Failed to create keyboard")
            await callback_query.answer("Error: Could not create keyboard")
            return

        await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await callback_query.answer("Returned to main view.")
        
    except Exception as e:
        debug_print(f"[ERROR] back_to_main - error: {e}")
        await callback_query.answer("An error occurred while returning to main view")


async def split_number(callback_query: CallbackQuery):
    try:
        # Extract number and site_id from callback data
        parts, site_id = parse_callback_data(callback_query.data)
        if len(parts) != 2 or not site_id:  # split_number or number_number
            debug_print(f"[ERROR] split_number - invalid format, parts: {parts}, site_id: {site_id}")
            await callback_query.answer("Invalid format")
            return

        number = parts[1]
        debug_print(f"[DEBUG] split_number - extracted number: {number}, site_id: {site_id}")

        # Remove country code from the number
        number_without_country_code = await format_phone_number(number, remove_code=True)
        split_message = f"`{number_without_country_code}`"

        # Send the split number message
        temp_message = await callback_query.bot.send_message(
            chat_id=callback_query.message.chat.id,
            text=split_message,
            parse_mode="Markdown")

        # Create a task to delete the message after 30 seconds
        asyncio.create_task(
            delete_message_after_delay(callback_query.bot, temp_message, 30))

        await callback_query.answer("Number split!")  # Show feedback to user

    except Exception as e:
        debug_print(f"Error in split_number: {e}")
        await callback_query.answer("Error splitting number")

async def send_log(message: Message):
    await message.bot.send_message(chat_id=message.from_user.id)

async def show_ping(message: Message):
    await message.bot.send_message(chat_id=message.from_user.id,
                                   text="I am now online 🌐")
    await message.delete()


async def send_startup_message(bot):
    if CHAT_ID:
        try:
            await bot.send_message(CHAT_ID, text="At Your Service 🍒🍄")
        except Exception as e:
            debug_print(f"⚠️ Failed to send startup message: {e}")


async def toggle_single_mode(callback_query: CallbackQuery):
    """Toggle SINGLE_MODE setting"""
    try:
        site_id = parse_callback_data(callback_query.data)
        if site_id is None:
            await callback_query.answer("Invalid site ID")
            return

        # Toggle SINGLE_MODE in config
        global SINGLE_MODE
        SINGLE_MODE = not SINGLE_MODE

        # Try to update config file if it exists
        config_file = "config_file.env"
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    lines = f.readlines()

                with open(config_file, "w") as f:
                    for line in lines:
                        if line.startswith("SINGLE_MODE="):
                            f.write(f"SINGLE_MODE={str(SINGLE_MODE).lower()}\n")
                        else:
                            f.write(line)
            except Exception as e:
                debug_print(f"[WARNING] Could not update config file: {e}")
                # Continue execution even if config file update fails
        else:
            debug_print("[INFO] No config file found, using environment variable only")

        # Return to settings menu to show updated state
        await handle_settings(callback_query)
        await callback_query.answer(f"Single Mode {'Enabled' if SINGLE_MODE else 'Disabled'}")

    except Exception as e:
        debug_print(f"[ERROR] Error in toggle_single_mode: {e}")
        await callback_query.answer("Failed to toggle Single Mode")