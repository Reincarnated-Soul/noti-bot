import os
import asyncio
import aiohttp
from typing import Tuple, Optional, List, Union
from bs4 import BeautifulSoup, SoupStrainer
from bot.api import APIClient
from bot.config import debug_print, DEV_MODE
from dataclasses import dataclass

# Global dictionary of country codes [ISO code(s)]
# Arranged in ascending order by country code
COUNTRY_CODES = {
    '1':    ['us', 'ca'],     # USA, Canada
    '7':    'ru',             # Russia
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
    '66':   'th',             # Thailand
    '77':   'kz',             # Kazakhstan
    '86':   'cn',             # China
    '91':   'in',             # India
    '212':  'ma',             # Morocco
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
    '420':  'cz',             # Czech Republic
    '421':  'sk',             # Slovakia
    '670':  'tl',             # Timor-Leste
    '852':  'hk',             # Hong Kong
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
    updated: bool = False
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
        if self.type == "multiple" and self.single_mode and len(self.numbers) > 1:
            self.numbers = [self.numbers[0]]

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
def extract_website_name(url, website_type):
    if not url:
        return "Unknown"

    try:
        # Remove http:// or https:// prefix
        domain = url.split("//")[-1].split("/")[0]
        # Remove www. if present
        if domain.startswith("www."):
            domain = domain[4:]
        
        # Check if there's a path after the domain
        path_parts = url.split("/")
        if len(path_parts) > 3:  # Has path after domain
            # Get the last part of the path
            last_part = path_parts[-1].lower()
            # If it's a short code (2-3 chars), return it in uppercase
            if len(last_part) <= 3:
                return last_part.upper()
            # Otherwise capitalize the first letter
            return last_part.capitalize()
        
        # No path, just return the main domain name
        main_domain = domain.split(".")[0]
        return main_domain.capitalize()

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
            async with aiohttp.ClientSession() as session:
                # First make a HEAD request to get cookies and session info if needed
                async with session.head(url, headers={
                    "User-Agent": headers["User-Agent"],
                    "Accept-Language": headers["Accept-Language"]
                }, timeout=15) as head_response:
                    # Now make the actual request with limited data
                    async with session.get(url, headers=headers, timeout=15) as response:
                        return await response.text()

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"⚠️ Request failed for {url} (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                print("Max retries reached. Giving up.")
                # Return empty string instead of None to prevent stopping monitoring
                return ""

# Define parsing strategies
PARSING_STRATEGIES = {
    "single": [
        {
            "selector": ".latest-added__title a",
            "extract": lambda element: element.get_text(strip=True) if element else None,
            "is_single": True
        }
    ],
    "multiple": [
        {
            "selector": ".numbutton",
            "extract": lambda elements: [btn.text.strip() for btn in elements]
        },
        {
            "selector": ".font-weight-bold",
            "extract": lambda elements: [n.text.strip() for n in elements]
        },
        {
            "selector": ".number_head__phone a",
            "extract": lambda elements: [num.text.strip() for num in elements]
        },
        {
            "selector": ".card-title",
            "extract": lambda elements: [numbers.text.strip() for numbers in elements]
        },
        {
            "selector": ".card-header",
            "extract": lambda elements: [select.text.strip() for select in elements]
        }
    ]
}

async def parse_website_content(url, website_type):
    """Unified function to parse website content based on type"""
    debug_print(f"Attempting to parse content from {url}")
    
    # First try web scraping
    page_content = await fetch_url_content(url)
    if page_content:
        # Create BeautifulSoup object once
        soup = BeautifulSoup(page_content, "lxml")
        
        # Get strategies for this website type
        strategies = PARSING_STRATEGIES.get(website_type, PARSING_STRATEGIES["multiple"])
        
        # Try each strategy
        for strategy in strategies:
            try:
                selector = strategy["selector"]
                extract_func = strategy["extract"]
                is_single = strategy.get("is_single", False)
                
                # Find elements using selector
                elements = soup.select_one(selector) if is_single else soup.select(selector)
                if elements:
                    # Extract numbers using the strategy's extract function
                    result = extract_func(elements)
                    if result:
                        # For single type, wrap in list if not already
                        numbers = [result] if is_single and not isinstance(result, list) else result
                        if numbers:
                            debug_print(f"Successfully parsed using {selector}")
                            # Get flag URL
                            flag_url = None
                            images = soup.find_all("img")
                            for img in images:
                                alt = img.get("alt", "")
                                src = img.get("data-lazy-src") or img.get("src") or ""
                                if "country flag" in alt.lower() and src.endswith(".png"):
                                    flag_url = src
                                    break
                            return numbers, flag_url
            except Exception as e:
                debug_print(f"Parser strategy failed for {selector}: {e}")
                continue

    # If web scraping fails or returns no results, try API
    try:
        debug_print("Web scraping unsuccessful, attempting API")
        api_client = APIClient(url)
        active_numbers = api_client.get_active_numbers_by_country()
        if active_numbers:
            first_number, country_code, _ = active_numbers[0]
            # Get flag URL using existing function
            _, flag_info = format_phone_number(first_number, get_flag=True, website_url=url)
            flag_url = flag_info["primary"] if flag_info else None
            # Extract just the numbers
            numbers = [number for number, _, _ in active_numbers]
            debug_print(f"Successfully fetched from API: {len(numbers)} numbers")
            return numbers, flag_url
    except Exception as e:
        debug_print(f"API attempt failed: {e}")

    debug_print("All parsing methods failed")
    return None, None

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

def format_phone_number(number, remove_code=False, get_flag=False, website_url=None):
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
        flag_url = None
        if country_code in COUNTRY_CODES:
            iso_code = None
            codes = COUNTRY_CODES[country_code]
            
            # Handle both single string and list of codes
            if isinstance(codes, list):
                # For shared codes like US/Canada, try to determine from URL
                if website_url:
                    country_from_url = website_url.split('/')[-1].lower() if '/' in website_url else None
                    if country_from_url:
                        for code in codes:
                            if code in country_from_url:
                                iso_code = code
                                break
                if not iso_code:
                    iso_code = codes[0]  # Use first code as default
            else:
                iso_code = codes  # Single country code

            # Use Flagpedia for flat-style flags at 580px width
            flag_url = f"https://flagpedia.net/data/flags/w580/{iso_code.lower()}.png"

            # Return both the formatted number and flag URL
            return (f"+{country_code} {rest_of_number}" if not remove_code else rest_of_number), {
                "primary": flag_url,
                "iso_code": iso_code.lower()
            }

    # Return based on the remove_code flag
    if remove_code:
        return rest_of_number
    else:
        return f"+{country_code} {rest_of_number}"

# For backward compatibility
remove_country_code = lambda number: format_phone_number(number, remove_code=True) if not isinstance(format_phone_number(number, remove_code=True), tuple) else format_phone_number(number, remove_code=True)[0]

def get_selected_numbers_for_buttons(numbers, previous_last_number):
    """
    Helper function to compute selected numbers for buttons based on previous_last_number.
    This is used for multiple type websites in subsequent runs.

    Args:
        numbers: List of numbers from website.latest_numbers
        previous_last_number: The previous last number to compare against

    Returns:
        List of selected numbers for buttons
    """
    if not numbers:
        return []

    # Determine last_number_position using previous_last_number
    last_number_position = -1
    if previous_last_number is not None:
        # Convert previous_last_number to string if it's not already
        prev_number_str = str(previous_last_number)
        # Check both with and without + prefix
        for i, num in enumerate(numbers):
            num_str = str(num)
            # Remove + if present for comparison
            if num_str.startswith('+'):
                num_str = num_str[1:]
            if prev_number_str == num_str or f"+{prev_number_str}" == num_str:
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
    
    # Find the site_id part
    site_id = None
    for i, part in enumerate(parts):
        if part == "site" and i + 1 < len(parts):
            # Found "site" followed by a number
            site_id = f"site_{parts[i + 1]}"
            # Return all parts before "site" and the site_id
            return parts[:i], site_id
        elif part.startswith("site_"):
            # Found a complete site_id
            site_id = part
            # Return all parts except the site_id
            return parts[:i] + parts[i+1:], site_id
    
    return parts, None

def extract_site_id(callback_data: str) -> Optional[str]:
    """
    Extract site ID from callback data.
    Expected format: 'action_site_id' or 'action_site_id_other_data'
    
    Args:
        callback_data (str): The callback data string
        
    Returns:
        Optional[str]: The extracted site ID if valid, None otherwise
    """
    _, site_id = parse_callback_data(callback_data)
    return site_id