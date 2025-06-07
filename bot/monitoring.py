import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple
from bot.storage import storage, save_website_data, load_website_data
from bot.utils import parse_website_content, fetch_url_content
from bot.config import CHECK_INTERVAL, debug_print, DEV_MODE

class WebsiteMonitor:
    def __init__(self, site_id: str, config: Dict[str, Any]):
        self.site_id = site_id
        self.url = config["url"]
        self.type = config.get("type")
        self.enabled = config["enabled"]
        self.is_initial_run = True
        self.position = config.get("position", 1)  # Position determines UI layout
        self.latest_numbers = []
        self.last_number = None
        self.flag_url = None
        self.previous_last_number = None
        # Initialize keyboard state
        self.keyboard_state = {
            "numbers": [],
            "is_initial_run": True,
            "single_mode": False,
            "buttons": None  # Store the actual keyboard buttons
        }

    def update_keyboard_state(self, numbers=None, is_initial_run=None, single_mode=None):
        """Update keyboard state without recreating the entire keyboard"""
        if numbers is not None:
            self.keyboard_state["numbers"] = numbers
        if is_initial_run is not None:
            self.keyboard_state["is_initial_run"] = is_initial_run
        if single_mode is not None:
            self.keyboard_state["single_mode"] = single_mode

    def get_keyboard_state(self):
        """Get current keyboard state"""
        return self.keyboard_state

    def set_keyboard_buttons(self, buttons):
        """Store the keyboard buttons for reuse"""
        self.keyboard_state["buttons"] = buttons

    async def fetch_content(self) -> Optional[str]:
        """Fetch content from the website"""
        return await fetch_url_content(self.url)

    async def check_for_updates(self) -> Tuple[Optional[Union[int, List[str]]], Optional[str]]:
        """Check for updates based on website type"""
        if not self.enabled or not self.url:
            return None, None

        # Use the unified parsing function
        return await parse_website_content(self.url, self.type)

    async def _update_state(self, new_data: Union[str, List[str]], flag_url: Optional[str], is_initial: bool = False) -> None:
        """Helper method to update state consistently for both single and multiple types"""
        if is_initial:
            # Initial run logic is the same for both types
            self.last_number = new_data[0] if isinstance(new_data, list) else new_data
            self.previous_last_number = self.last_number
            self.is_initial_run = True
        else:
            # Update logic for subsequent runs
            self.previous_last_number = self.last_number
            self.last_number = new_data[0] if isinstance(new_data, list) else new_data
            self.is_initial_run = False

        # Update flag URL
        self.flag_url = flag_url

        # For multiple type, always update latest_numbers
        if self.type == "multiple":
            self.latest_numbers = new_data if isinstance(new_data, list) else [new_data]

        # Save the updated state
        await save_website_data(self.site_id)

    async def process_update(self, new_data: Union[int, List[str]], flag_url: Optional[str]) -> bool:
        """Process updates and return True if notification should be sent"""
        if not new_data:
            # Website temporarily unavailable, don't disrupt monitoring
            debug_print(f"[DEBUG] No data from {self.site_id}, skipping this check")
            return False

        # Dynamic type detection if not set
        if self.type is None:
            self.type = "multiple" if isinstance(new_data, list) and len(new_data) > 1 else "single"

        # Convert new_data to list format for multiple type
        if self.type == "multiple" and not isinstance(new_data, list):
            new_data = [str(new_data)]
        elif self.type == "single" and isinstance(new_data, list):
            new_data = new_data[0]

        # Initial run check
        if self.last_number is None or (self.type == "multiple" and not self.latest_numbers):
            await self._update_state(new_data, flag_url, is_initial=True)
            return True

        # Check for changes
        if self.type == "single":
            if new_data != self.last_number:
                await self._update_state(new_data, flag_url)
                return True
        else:  # multiple type
            current_numbers = set(self.latest_numbers)
            new_numbers = set(new_data if isinstance(new_data, list) else [new_data])
            
            if current_numbers != new_numbers:
                await self._update_state(new_data, flag_url)
                return True

        return False

    def get_notification_data(self) -> Dict[str, Any]:
        """Get data needed for notification"""
        if self.type == "single":
            return {
                "is_initial_run": self.is_initial_run,
                "number": self.last_number,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "url": self.url
            }
        else:
            return {
                "is_initial_run": self.is_initial_run,
                "numbers": self.latest_numbers,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "url": self.url
            }

async def monitor_websites(bot, send_notification_func):
    """Monitor all configured websites for updates"""
    # Load saved data for all websites
    await load_website_data()

    consecutive_failures = {site_id: 0 for site_id in storage["websites"]}
    max_consecutive_failures = 5

    # First run check - if any website has no saved data, initialize it
    initial_run_needed = False
    for site_id, website in storage["websites"].items():
        # Only set is_initial_run to True if the website hasn't been initialized yet
        if website.enabled and website.type == "single" and website.last_number is None:
            website.is_initial_run = True
            initial_run_needed = True
        elif website.enabled and website.type == "multiple" and not website.latest_numbers:
            website.is_initial_run = True
            initial_run_needed = True

    # For first run, initialize all websites
    if initial_run_needed:
        for site_id, website in storage["websites"].items():
            if not website.enabled:
                continue

            try:
                # Get initial data
                new_data, flag_url = await website.check_for_updates()
                if new_data:
                    # Save data and send notification for all websites on first run
                    await website.process_update(new_data, flag_url)
                    # Send notification for all websites
                    await send_notification_func(website.get_notification_data())
                    # Reset consecutive failures on success
                    consecutive_failures[site_id] = 0
            except Exception as e:
                print(f"Error initializing {site_id}: {e}")
                # Don't increase failure count on first run

    # For normal operation, start monitoring loop
    while True:
        try:
            for site_id, website in storage["websites"].items():
                if not website.enabled:
                    # Skip disabled websites
                    continue

                try:
                    # Check for updates
                    new_data, flag_url = await website.check_for_updates()

                    if new_data:
                        # Process update and send notification
                        notify = await website.process_update(new_data, flag_url)

                        if notify:
                            notification_data = website.get_notification_data()
                            await send_notification_func(notification_data)
                        
                        # Reset consecutive failures on any successful response
                        consecutive_failures[site_id] = 0
                    else:
                        consecutive_failures[site_id] += 1                        
                        # Only log errors at specific thresholds to avoid spam
                        # if consecutive_failures[site_id] == 1 or consecutive_failures[site_id] % 5 == 0:
                        #     debug_print(f"⚠️ No data from {site_id} (attempt {consecutive_failures[site_id]}/{max_consecutive_failures})")
                except Exception as e:
                    consecutive_failures[site_id] += 1
                    print(f"Error monitoring {site_id} (attempt {consecutive_failures[site_id]}): {e}")
                    
                # Short pause between websites to prevent overwhelming the network
                await asyncio.sleep(1)

            # Wait for CHECK_INTERVAL seconds before checking again
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"[ERROR] Error in monitor_websites main loop: {e}")
            # Continue monitoring even if there's an error in the main loop
            await asyncio.sleep(5)
