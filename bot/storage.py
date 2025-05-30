import os
import json
from bot.config import debug_print, DEV_MODE
from typing import Dict, Optional
from uuid import uuid4
from bot.utils import NotificationState


# Storage
storage = {
    "file": "website_data.json",
    "websites": {},  # Will store WebsiteMonitor instances
    "repeat_interval": None,
    "latest_notification": {"message_id": None, "number": None, "flag_url": None, "site_id": None, "multiple": False, "is_initial_run": False},
    "active_countdown_tasks": {},
    "notifications": {},  # Store notification states by notification_id
}

async def load_website_data():
    """Load website data from file"""
    data = {}
    if os.path.exists(storage["file"]):
        try:
            with open(storage["file"], "r") as f:
                data = json.load(f)
                debug_print(f"[DEBUG] load_website_data - loaded data from file: {data}")

                # Load data for each website
                for site_id, website in storage["websites"].items():
                    if site_id in data:
                        debug_print(f"[DEBUG] load_website_data - loading data for {site_id}")
                        # Load last_number from the file for all website types
                        website.last_number = data[site_id].get("last_number")

                        # For multiple numbers website, also load latest_numbers
                        if website.type == "multiple":
                            # Load previous_last_number if it exists
                            if "previous_last_number" in data[site_id]:
                                website.previous_last_number = data[site_id]["previous_last_number"]
                            else:
                                website.previous_last_number = website.last_number
                                
                            latest_numbers = data[site_id].get("latest_numbers", [])
                            if latest_numbers:
                                website.latest_numbers = latest_numbers

                                # If last_number is not set, extract it from first element
                                if website.last_number is None and latest_numbers:
                                    first_num = latest_numbers[0]
                                    if isinstance(first_num, str) and first_num.startswith("+"):
                                        first_num = first_num[1:]
                                    try:
                                        website.last_number = int(first_num)
                                    except (ValueError, TypeError):
                                        website.last_number = None

                        # Load button_updated state if it exists
                        if "button_updated" in data[site_id]:
                            website.button_updated = data[site_id]["button_updated"]
                            debug_print(f"[DEBUG] load_website_data - loaded button_updated={website.button_updated} for {site_id}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading website data: {e}")

    return data

async def save_website_data(site_id=None):
    # Load existing data
    data = {}
    if os.path.exists(storage["file"]):
        try:
            with open(storage["file"], "r") as f:
                data = json.load(f)
                # Print only site-specific data if site_id is specified
                if site_id and site_id in data:
                    # Format just the specific site data nicely
                    site_data = {site_id: data[site_id]}
                    formatted_data = json.dumps(site_data)
                    debug_print(f"[DEBUG] save_website_data - loaded existing data:\n{formatted_data}")
                else:
                    # Just mention how many sites were loaded
                    debug_print(f"[DEBUG] save_website_data - loaded existing data for {len(data)} sites")
        except (json.JSONDecodeError, IOError) as e:
            debug_print(f"[DEBUG] save_website_data - error loading existing data: {e}")

    # Update data
    if site_id:
        # Update just one website
        if site_id in storage["websites"]:
            website = storage["websites"][site_id]
            
            # For multiple numbers websites, save last_number and always include latest_numbers (empty if not set)
            if website.type == "multiple":
                # Store previous_last_number before updating, if it doesn't exist yet
                if not hasattr(website, "previous_last_number"):
                    website.previous_last_number = website.last_number
                    
                data[site_id] = {
                    "last_number": website.last_number,
                    "previous_last_number": website.previous_last_number if hasattr(website, "previous_last_number") else website.last_number,
                    "latest_numbers": website.latest_numbers if hasattr(website, "latest_numbers") else []
                }
                # Ensure latest_numbers is always an array
                if data[site_id]["latest_numbers"] is None:
                    data[site_id]["latest_numbers"] = []
            else:
                # For all other websites, just save the last_number
                data[site_id] = {
                    "last_number": website.last_number
                }

            # Save button_updated state if it exists
            if hasattr(website, "button_updated"):
                data[site_id]["button_updated"] = website.button_updated
                # print(f"[DEBUG] save_website_data - saving button_updated={website.button_updated} for {site_id}")
    else:
        # Update all websites
        for site_id, website in storage["websites"].items():
            if website.type == "multiple":
                # Store previous_last_number before updating, if it doesn't exist yet
                if not hasattr(website, "previous_last_number"):
                    website.previous_last_number = website.last_number
                    
                data[site_id] = {
                    "last_number": website.last_number,
                    "previous_last_number": website.previous_last_number if hasattr(website, "previous_last_number") else website.last_number,
                    "latest_numbers": website.latest_numbers if hasattr(website, "latest_numbers") else []
                }
                if data[site_id]["latest_numbers"] is None:
                    data[site_id]["latest_numbers"] = []
            else:
                data[site_id] = {
                    "last_number": website.last_number
                }
            if hasattr(website, "button_updated"):
                data[site_id]["button_updated"] = website.button_updated

    # Save to file
    try:
        with open(storage["file"], "w") as f:
            json.dump(data, f)
            
            # For debug output, only show relevant site data if a specific site_id is provided
            if site_id and site_id in data:
                # Format just the specific site data nicely
                site_data = {site_id: data[site_id]}
                formatted_data = json.dumps(site_data, indent=2)
                debug_print(f"[DEBUG] save_website_data - saved for {site_id}:\n{formatted_data}")
            else:
                # Just mention how many sites were saved
                debug_print(f"[DEBUG] save_website_data - saved data for {len(data)} sites")
    except IOError as e:
        print(f"Error saving website data: {e}")

async def save_last_number(number, site_id):
    """Save last number for a specific website"""
    if site_id in storage["websites"]:
        website = storage["websites"][site_id]
        website.last_number = number
        await save_website_data(site_id)

def create_notification_state(site_id: str, numbers: list, type: str, is_initial_run: bool = True) -> NotificationState:
    """Create a new notification state with a unique ID"""
    notification_id = str(uuid4())
    state = NotificationState(
        notification_id=notification_id,
        site_id=site_id,
        numbers=numbers,
        type=type,
        is_initial_run=is_initial_run
    )
    storage["notifications"][notification_id] = state
    return state

def get_notification_state(notification_id: str) -> Optional[NotificationState]:
    """Get a notification state by its ID"""
    return storage["notifications"].get(notification_id)

def update_notification_state(notification_id: str, **kwargs) -> Optional[NotificationState]:
    """Update a notification state with new values"""
    state = get_notification_state(notification_id)
    if state:
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
    return state
