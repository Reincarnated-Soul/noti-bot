import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple
from bot.storage import storage, save_website_data, load_website_data
from bot.utils import parse_website_content, fetch_url_content
from bot.config import CHECK_INTERVAL

class WebsiteMonitor:
    def __init__(self, site_id: str, config: Dict[str, Any]):
        self.site_id = site_id
        self.url = config["url"]
        self.type = config.get("type")
        self.enabled = config["enabled"]
        self.first_run = True
        self.position = config.get("position", 1)  # Position determines UI layout
        self.latest_numbers = []
        self.last_number = None
        self.flag_url = None

    async def fetch_content(self) -> Optional[str]:
        """Fetch content from the website"""
        return await fetch_url_content(self.url)

    async def check_for_updates(self) -> Tuple[Optional[Union[int, List[str]]], Optional[str]]:
        """Check for updates based on website type"""
        if not self.enabled or not self.url:
            return None, None

        # Use the unified parsing function
        return await parse_website_content(self.url, self.type)

    async def process_update(self, new_data: Union[int, List[str]], flag_url: Optional[str]) -> bool:
        """Process updates and return True if notification should be sent"""
        if not new_data:
            return False

        # Dynamic type detection
        if self.type is None:
            if isinstance(new_data, list) and len(new_data) > 1:
                self.type = "multiple"
            elif (isinstance(new_data, list) and len(new_data) == 1) or isinstance(new_data, str):
                self.type = "single"
            else:
                self.type = "single"  # Fallback for empty or unknown
            # print(f"[DEBUG] WebsiteMonitor - dynamically set type for {self.site_id}: {self.type}")

        if self.type == "single":
            new_number = new_data
            # Remove leading + if present
            if isinstance(new_number, str) and new_number.startswith('+'):
                new_number = new_number[1:]
            # Convert to int if possible
            try:
                new_number_int = int(new_number)
                new_number = new_number_int
            except (ValueError, TypeError):
                pass
            # First time initialization or number has changed
            if self.last_number is None:
                # First run - save number and notify
                self.last_number = new_number
                self.flag_url = flag_url
                await save_website_data(self.site_id)
                return True  # Send notification on first run
            elif new_number != self.last_number:
                # Number has changed - update and notify
                self.last_number = new_number
                self.flag_url = flag_url
                await save_website_data(self.site_id)
                return True
            return False
        else:
            # For multiple numbers website
            if not self.latest_numbers:
                # First run - 1. Get all numbers from website
                if new_data:
                    # 2. Pick the first (0th index) element to be the last_number for comparison
                    first_num = new_data[0]
                    if isinstance(first_num, str) and first_num.startswith("+"):
                        first_num = first_num[1:]
                    try:
                        self.last_number = int(first_num)
                        self.flag_url = flag_url
                        # Save all numbers but mark as initial notification
                        self.latest_numbers = new_data.copy()
                        await save_website_data(self.site_id)
                        # 3. Return True to send initial notification with last_number
                        return True
                    except (ValueError, TypeError):
                        self.last_number = None
                        return False
            elif new_data and new_data != self.latest_numbers:
                # Numbers have changed - check if last_number has moved from 0th position
                if new_data and self.last_number is not None:
                    # Current last_number (as string with + prefix for comparison)
                    last_number_str = f"+{self.last_number}"

                    # 4. Find the position of the last_number in the new array
                    last_number_position = -1
                    for i, num in enumerate(new_data):
                        if num == last_number_str:
                            last_number_position = i
                            break

                    # 5. If last_number found and moved from position 0
                    if last_number_position > 0:
                        # Create array of numbers that come before last_number
                        new_numbers = new_data[:last_number_position]
                        # Pick the newest number (0th index) as the new last_number
                        first_num = new_data[0]
                        if isinstance(first_num, str) and first_num.startswith("+"):
                            first_num = first_num[1:]
                        try:
                            self.last_number = int(first_num)
                        except (ValueError, TypeError):
                            pass
                    # If last_number not found or already at position 0
                    else:
                        # Update last_number to the new first element
                        first_num = new_data[0]
                        if isinstance(first_num, str) and first_num.startswith("+"):
                            first_num = first_num[1:]
                        try:
                            self.last_number = int(first_num)
                        except (ValueError, TypeError):
                            pass

                # 6. Update latest_numbers with full array
                self.latest_numbers = new_data
                self.flag_url = flag_url
                await save_website_data(self.site_id)
                # 7. Send notification with latest_numbers array
                return True

        return False

    def get_notification_data(self) -> Dict[str, Any]:
        """Get data needed for notification"""
        if self.type == "single":
            return {
                "is_initial_run": self.first_run,
                "number": self.last_number,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "url": self.url

            }
        else:
            return {
                "is_initial_run": self.first_run,
                "numbers": self.latest_numbers,
                "flag_url": self.flag_url,
                "site_id": self.site_id,
                "first_run": self.first_run,
                "url": self.url
            }

async def monitor_websites(bot, send_notification_func):
    """Monitor all configured websites for updates"""
    # Load saved data for all websites
    await load_website_data()

    consecutive_failures = {site_id: 0 for site_id in storage["websites"]}
    max_consecutive_failures = 5

    # First run check - if any website has no saved data, initialize it
    first_run = False
    for site_id, website in storage["websites"].items():
        # Set website as first run.
        website.first_run = True

        if website.enabled and website.last_number is None and website.type == "single":
            first_run = True
        elif website.enabled and not website.latest_numbers and website.type == "multiple":
            first_run = True

    # For first run, initialize all websites
    if first_run:
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
            except Exception as e:
                print(f"Error initializing {site_id}: {e}")

    # Main monitoring loop
    while True:
        for site_id, website in storage["websites"].items():
            if website.enabled and website.url:
                # print(f"[DEBUG] monitor_websites - checking {site_id} ({website.url}) type={website.type}")
                try:
                    new_data, flag_url = await website.check_for_updates()
                    # print(f"[DEBUG] monitor_websites - parsed new_data for {site_id}: {new_data}, flag_url: {flag_url}")
                    consecutive_failures[site_id] = 0

                    # Process the update and send notification if needed
                    should_notify = await website.process_update(new_data, flag_url)
                    if should_notify:
                        await send_notification_func(website.get_notification_data())

                except Exception as e:
                    print(f"Error monitoring {site_id}: {e}")
                    consecutive_failures[site_id] += 1

        # Wait before next check cycle
        await asyncio.sleep(CHECK_INTERVAL)
