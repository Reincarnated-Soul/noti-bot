import os
import asyncio
import aiohttp
from typing import Tuple, Optional, List, Union
from bs4 import BeautifulSoup, SoupStrainer
from bot.api import APIClient
from bot.config import debug_print, DEV_MODE
from dataclasses import dataclass
from aiogram.types import InlineKeyboardButton

# Global dictionary of country codes [ISO code(s)]
# Arranged in ascending order by country code
COUNTRY_CODES = {
    '1':    ['us', 'ca'],     # USA, Canada
    '7':    'ru',             # Russia
    '30':   'gr',             # Greece
    '31':   'nl',             # Netherlands
    '32':   'be',             # Belgium
    '33':   'fr',             # France
    '34':   'es',             # Spain
    '39':   'it',             # Italy
    '40':   'ro',             # Romania
    '41':   'ch',             # Switzerland
    '43':   'at',             # Austria
    '44':   'gb',             # UK (United Kingdom)
    '45':   'dk',             # Denmark
    '46':   'se',             # Sweden
    '48':   'pl',             # Poland
    '49':   'de',             # Germany
    '52':   'mx',             # Mexico
    '55':   'br',             # Brazil
    '60':   'my',             # Malaysia
    '61':   'au',             # Australia
    '62':   'id',             # Indonesia
    '63':   'ph',             # Philippines
    '65':   'sg',             # Singapore'
    '66':   'th',             # Thailand
    '77':   'kz',             # Kazakhstan
    '81':   'jp',             # Japan
    '82':   'kr',             # South Korea
    '84':   'vn',             # Vietnam
    '86':   'cn',             # China
    '91':   'in',             # India
    '212':  'ma',             # Morocco
    '225':  'ci',             # Ivory Coast
    '230':  'mu',             # Mauritius
    '234':  'ng',             # Nigeria
    '351':  'pt',             # Portugal
    '353':  'ie',             # Ireland
    '354':  'is',             # Iceland
    '358':  'fi',             # Finland
    '359':  'bg',             # Bulgaria
    '370':  'lt',             # Lithuania
    '371':  'lv',             # Latvia
    '372':  'ee',             # Estonia
    '380':  'ua',             # Ukraine
    '381':  'rs',             # Serbia
    '385':  'hr',             # Croatia
    '386':  'si',             # Slovenia
    '387':  'ba',             # Bosnia
    '420':  'cz',             # Czech Republic
    '421':  'sk',             # Slovakia
    '670':  'tl',             # Timor-Leste
    '852':  'hk',             # Hong Kong
    '886':  'tw',             # Taiwan'
    '972':  'il',             # Israel
    '995':  'ge',             # Georgia
    '1787': 'pr'              # Puerto Rico
}

@dataclass
class KeyboardData:
    """Standardized keyboard data structure for all keyboard types"""
    site_id: str
    type: str  # "single" or "multiple"
    url: str
    is_initial_run: bool = True
    numbers: List[str] = None
    single_mode: bool = False

    def __post_init__(self):
        # Ensure numbers is always a list
        if self.numbers is None:
            self.numbers = []
        
        # For single type, ensure we have exactly one number
        if self.type == "single" and len(self.numbers) > 0:
            self.numbers = [self.numbers[0]]
        
        # For multiple type in single mode, ensure we have at most one number
        if self.type == "multiple" and self.single_mode and len(self.numbers) > 0:
            self.numbers = [self.numbers[0]]

@dataclass
class NotificationState:
    """Represents the state of an individual notification"""
    notification_id: str  # Unique identifier for this notification
    site_id: str
    numbers: List[str]  # The numbers associated with this notification
    type: str  # 'single' or 'multiple'
    is_initial_run: bool = True
    single_mode: bool = False
    message_id: Optional[int] = None
    
    def to_keyboard_data(self, website_url: str) -> 'KeyboardData':
        """Convert notification state to keyboard data"""
        return KeyboardData(
            site_id=self.site_id,
            type=self.type,
            url=website_url,
            numbers=self.numbers,
            is_initial_run=self.is_initial_run,
            single_mode=self.single_mode
        )
    
    def set_message_id(self, message_id: int):
        """Set the message ID for this notification"""
        self.message_id = message_id

# Helper function to get base URL from environment variable
def get_base_url():
    """Get the base URL from environment variable without hardcoding any URL"""
    url = os.getenv('URL', '')
    if not url:
        return ""

    # Handle array format if URL is in JSON array format
    if url.startswith('[') and url.endswith(']'):
        try:
            # Simple parsing for array format
            urls = [u.strip().strip('"').strip("'") for u in url[1:-1].split(',')]
            if urls and urls[0]:
                return urls[0]
        except Exception:
            pass

    return url

# Helper function to extract website name from URL
def extract_website_name(url, website_type, use_domain_only=False, button_format=False, status=None):
    if not url:
        return "Unknown"

    try:
        # Remove http:// or https:// prefix
        domain = url.split("//")[-1].split("/")[0]
        # Remove www. if present
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Get main domain and capitalize once
        main_domain = domain.split(".")[0].capitalize() 
        
        # Get display name - either from path or domain
        display_name = main_domain
        first_letter = main_domain[0]
        
        # Check if URL has a path with country name
        path_parts = url.split("/")
        has_country = False
        
        # Look for country name in path
        if len(path_parts) > 3:  # Has some path
            if any(p in ("country", "countries") for p in path_parts):
                last_part = None
                for part in reversed(path_parts):
                    if part and part not in ("country", "countries"):
                        last_part = part
                        break
                
                if last_part:
                    if len(last_part) <= 3:
                        display_name = last_part.upper()
                    else:
                        display_name = last_part.capitalize()
                    has_country = True
        
        # Format the name based on parameters
        if use_domain_only and not button_format:
            # Just return domain name for non-button use_domain_only case
            return main_domain
        
        
        if button_format:
            # Only show status if it's "Disabled" (when monitoring is disabled)
            if status and status.lower() == "disabled":
                if has_country:
                    return f"{first_letter} : {display_name} : {status}"
                return f"{display_name} : {status}"
            else:
                if has_country:
                    return f"{first_letter} : {display_name}"
                return display_name
            
        return display_name

    except Exception as e:
        print(f"Error extracting website name from {url}: {e}")
        return "Unknown"

# Network operations
async def fetch_url_content(url):
    """Fetch content from a URL with optimized headers and retry logic"""
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html, application/xhtml+xml, application/xml",
        "Accept-Encoding": "gzip, deflate",
        "Range": "bytes=0-60000"  # Only get first 50KB which likely contains what we need
    }
    
    max_retries = 3
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=15, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    return await response.text()
                        
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"⚠️ Request failed for {url} (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print(f"⚠️ Max retries reached for {url}. Giving up.")
                return ""

# Helper function to get country code and flag from phone number
async def get_country_info_from_number(number):
    """Get country code and flag URL from a phone number"""
    if not number:
        return None, None
        
    # Convert to string and remove any '+' prefix
    number_str = str(number).lstrip('+')
    
    # Try to match with country codes (try longer codes first)
    for code in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
        if number_str.startswith(code):
            # Get ISO code (handle both single string and list cases)
            iso_code = COUNTRY_CODES[code]
            if isinstance(iso_code, list):
                iso_code = iso_code[0]  # Use first code for shared codes
            
            # Get flag URL from Flagpedia
            flag_url = f"https://flagpedia.net/data/flags/w580/{iso_code.lower()}.png"
            return iso_code, flag_url
            
    return None, None

async def parse_website_content(url, website_type):
    """Unified function to parse website content based on type"""
    page_content = await fetch_url_content(url)
    if not page_content:
        return None, None

    # Create BeautifulSoup object once
    soup = BeautifulSoup(page_content, "lxml")

    # Helper functions to parse different website types
    async def parse_single_website():
        try:
            latest_title_a = soup.select_one(".latest-added__title a")
            flag_url = None
            
            if latest_title_a:
                number = latest_title_a.get_text(strip=True)
                # Get country info from the phone number
                _, flag_url = await get_country_info_from_number(number)

                # If no flag from country code, fall back to web scraping
                if not flag_url:
                    # Try to find a .png flag with alt containing 'country flag'
                    images = soup.find_all("img")
                    for img in images:
                        alt = img.get("alt", "")
                        src = img.get("data-lazy-src") or img.get("src") or ""
                        if "country flag" in alt.lower() and src.endswith(".png"):
                            flag_url = src
                            break
                    # If not found, fallback to the 18th <img> with .png extension
                    if not flag_url and len(images) > 18:
                        img = images[18]
                        src = img.get("data-lazy-src") or img.get("src") or ""
                        if src.endswith(".png"):
                            flag_url = src
                    # If still not found, fallback to any .png image
                    if not flag_url:
                        for img in images:
                            src = img.get("data-lazy-src") or img.get("src") or ""
                            if src.endswith(".png"):
                                flag_url = src
                                break

                return number, flag_url
            return None, None
        except Exception as e:
            debug_print(f"[ERROR] Error parsing multiple numbers website: {e}")
            return None, None

    async def parse_multiple_website():
        try:
            # First try HTML parsing
            selector_patterns = [
                ('.numbutton', lambda x: x.text.strip()),
                ('.font-weight-bold', lambda x: x.text.strip()),
                ('.number_head__phone a', lambda x: x.text.strip()),
                ('.styles_numberInfo__rhUmJ span', lambda x: x.text.strip()),
                ('.card-title', lambda x: x.text.strip()),
                ('.wpb_child_page_title', lambda x: x.text.strip()),
                ('.card-header', lambda x: x.text.strip())
            ]

            numbers = None
            flag_url = None

            # Try each selector pattern
            for selector, transform_fn in selector_patterns:
                elements = soup.select(selector)
                if elements:
                    numbers = list(map(transform_fn, elements))
                    if numbers:
                        # Get country info from the first number
                        _, flag_url = await get_country_info_from_number(numbers[0])
                        break

            # If HTML parsing fails, try JSON API endpoint first, then fall back to API Keys
            if not numbers:
                try:
                    debug_print("[DEBUG] HTML parsing failed, attempting JSON API endpoint")
                    # Initialize API client with the current URL
                    api_client = APIClient(url)
                    # Try to fetch numbers from JSON API endpoint (latest.json)
                    # Use the APIClient's built-in method to fetch JSON numbers
                    # The APIClient already handles URL transformation and endpoint construction
                    debug_print(f"[DEBUG] Trying JSON API endpoint from {url}")
                    json_numbers = await api_client.fetch_json_numbers()
                    
                    if json_numbers:
                        numbers = json_numbers
                        # Get country info from the first number
                        if numbers:
                            _, flag_url = await get_country_info_from_number(numbers[0])
                        debug_print(f"[DEBUG] Successfully retrieved {len(numbers)} numbers from JSON API")
                        return numbers, flag_url
                    
                    # If JSON API fails, try API Keys endpoint
                    debug_print("[DEBUG] JSON API failed, attempting API Keys fallback")
                    active_numbers = await api_client.get_active_numbers_by_country()
                    if active_numbers:
                        # Extract just the numbers from the tuples
                        numbers = [number for number, _, _ in active_numbers]
                        # Get country info from the first number
                        if numbers:
                            _, flag_url = await get_country_info_from_number(numbers[0])
                        debug_print(f"[DEBUG] Successfully retrieved {len(numbers)} numbers from API Keys")
                        return numbers, flag_url
                except Exception as api_error:
                    debug_print(f"[ERROR] API access failed: {api_error}")
                    numbers = None

            # If still no flag URL, fall back to web scraping
            if not flag_url:
                images = soup.select('img')
                if len(images) > 1:
                    flag_img = images[1]
                    flag_url = flag_img.get('data-lazy-src') or flag_img.get('src')
                    if flag_url and not flag_url.startswith(('http://', 'https://')):
                        base_url = url.rsplit('/', 2)[0]
                        flag_url = f"{base_url}{flag_url}"

            return numbers, flag_url

        except Exception as e:
            debug_print(f"[ERROR] Error parsing multiple numbers website: {e}")
            return None, None

    # If website_type is None, try single first, then multiple
    if website_type is None:
        # Try single
        result, flag_url = await parse_single_website()
        if result is not None:
            return result, flag_url

        # Try multiple
        result, flag_url = await parse_multiple_website()
        if result is not None:
            return result, flag_url

        return None, None

    # Process based on specified website type
    if website_type == "single":
        return await parse_single_website()
    else:
        return await parse_multiple_website()

def format_time(seconds):
    """Format seconds into a readable time string"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = ""
    if hours:
        time_str += f"{hours:02} hrs : "
    if minutes or hours:
        time_str += f"{minutes:02} min : "
    time_str += f"{seconds:02} sec"
    return time_str

async def delete_message_after_delay(bot, message, delay_seconds):
    """Delete a message after a specified delay"""
    try:
        await asyncio.sleep(delay_seconds)
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")

async def format_phone_number(number, remove_code=False, get_flag=False, website_url=None):
    # Convert to string if it's an integer
    if isinstance(number, int):
        number_str = str(number)
    else:
        # Remove + if present
        number_str = number.lstrip('+')

    # Try to determine the country code by matching prefixes
    # Sort country codes by length in descending order to match longer codes first
    country_code = None
    for code in sorted(COUNTRY_CODES.keys(), key=len, reverse=True):
        if number_str.startswith(code):
            country_code = code
            break

    # If we couldn't determine the country code
    if country_code is None:
        if get_flag:
            return number_str if remove_code else f"+{number_str}", None
        return number_str if remove_code else f"+{number_str}"

    # Split the number
    rest_of_number = number_str[len(country_code):]

    # Get flag URL if requested
    if get_flag:
        # Use the same function as parse_website_content for consistency
        iso_code, flag_url = await get_country_info_from_number(number_str)
        if iso_code:
            return (f"+{country_code} {rest_of_number}" if not remove_code else rest_of_number), {
                "primary": flag_url,
                "iso_code": iso_code.lower()
            }
        return (f"+{country_code} {rest_of_number}" if not remove_code else rest_of_number), None

    # Return based on the remove_code flag
    if remove_code:
        return rest_of_number
    else:
        return f"+{country_code} {rest_of_number}"

def get_selected_numbers_for_buttons(numbers, previous_last_number):
    """
    Helper function to compute selected numbers for buttons based on previous_last_number.
    This is used for multiple type websites in subsequent runs.
    """
    if not numbers:
        return []

    # Determine last_number_position using previous_last_number
    last_number_position = -1
    if previous_last_number is not None:
        # Simple string comparison
        for i, num in enumerate(numbers):
            if num == previous_last_number:
                last_number_position = i
                break

    # Only select numbers that are newer than the previous last_number
    selected_numbers = numbers[:last_number_position] if last_number_position > 0 else []

    # If no new numbers found, use all numbers
    if not selected_numbers:
        selected_numbers = numbers

    return selected_numbers

def parse_callback_data(callback_data):
    """Parse callback data into parts and site_id"""
    if not callback_data or callback_data == "none":
        return [], None

    # Split the callback data into parts
    parts = callback_data.split('_')
    
    # Find the site_id (it can be in format "site_X" or separate "site" and "X")
    for i, part in enumerate(parts):
        if part == "site" and i + 1 < len(parts):
            # Found "site" followed by the ID number
            site_id = f"site_{parts[i+1]}"
            # Remove both "site" and the ID from parts
            return parts[:i] + parts[i+2:], site_id
        elif part.startswith("site_"):
            # Found the combined "site_X" format
            return parts[:i] + parts[i+1:], part
    
    return parts, None