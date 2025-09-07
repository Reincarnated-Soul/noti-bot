import os
import re
import asyncio
import aiohttp
from typing import Tuple, Optional, List, Union, Dict
from bs4 import BeautifulSoup, SoupStrainer
from bot.api import APIClient
from bot.config import debug_print, DEV_MODE
from dataclasses import dataclass
from aiogram.types import InlineKeyboardButton

# Pre-compile regex patterns for better performance
CLEAN_NUMBER = re.compile(r'[\s\-+]')
CLEAN_URL = re.compile(r'^https?://(www\.)?')   # Remove http:// or https:// or www. prefix

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

# Singleton class for country detection 
# Try to match with country codes (try longer codes first)
class CountryDetector:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._sorted_codes = sorted(COUNTRY_CODES.keys(), key=len, reverse=True)
        return cls._instance
    
    def detect_country(self, number_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Single method to detect country code, ISO code, and flag URL"""
        for code in self._sorted_codes:
            if number_str.startswith(code):
                iso_code = COUNTRY_CODES[code]
                if isinstance(iso_code, list):
                    iso_code = iso_code[0]
                flag_url = f"https://flagpedia.net/data/flags/w580/{iso_code.lower()}.png"
                return code, iso_code, flag_url
        return None, None, None

# Centralized network configuration
class NetworkConfig:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html, application/xhtml+xml, application/xml",
        "Accept-Encoding": "gzip, deflate",
        "Range": "bytes=0-60000"
    }
    TIMEOUT = aiohttp.ClientTimeout(total=15, connect=10)
    MAX_RETRIES = 3
    RETRY_DELAY = 5

# Dynamic strategy caching class (NO @dataclass - complex logic with caching)
class ParsingStrategyCache:
    """Cache successful parsing strategies per URL domain for performance optimization"""
    
    def __init__(self):
        """Custom __init__ with complex initialization - @dataclass not suitable"""
        self._domain_strategies: Dict[str, str] = {}  # domain -> strategy_type
        self._selector_cache: Dict[str, str] = {}     # domain -> successful_selector
        self._failure_count: Dict[str, int] = {}      # domain -> failure_count for cache invalidation
        
    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        return url.split("//")[-1].split("/")[0].replace("www.", "")
    
    def get_strategy(self, url: str) -> Optional[str]:
        """Get cached strategy for domain"""
        domain = self.get_domain(url)
        # Invalidate cache if too many failures
        if self._failure_count.get(domain, 0) > 3:
            self._domain_strategies.pop(domain, None)
            self._selector_cache.pop(domain, None)
            self._failure_count[domain] = 0
            return None
        return self._domain_strategies.get(domain)
    
    def cache_strategy(self, url: str, strategy_type: str, selector: Optional[str] = None):
        """Cache successful strategy for domain"""
        domain = self.get_domain(url)
        self._domain_strategies[domain] = strategy_type
        self._failure_count[domain] = 0  # Reset failure count on success
        if selector:
            self._selector_cache[domain] = selector
    
    def get_cached_selector(self, url: str) -> Optional[str]:
        """Get cached selector for domain"""
        domain = self.get_domain(url)
        return self._selector_cache.get(domain)
    
    def mark_failure(self, url: str):
        """Mark a failure for cache invalidation"""
        domain = self.get_domain(url)
        self._failure_count[domain] = self._failure_count.get(domain, 0) + 1

# Global strategy cache instance
_strategy_cache = ParsingStrategyCache()

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
        
        # Apply type-specific constraints
        if self.numbers:
            if self.type == "single" or (self.type == "multiple" and self.single_mode):
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
def get_base_url() -> str:
    """Get the base URL from environment variable without hardcoding any URL"""
    url = os.getenv('URL', '')
    if not url:
        return ""

    # Handle array format if URL is in JSON array format
    if url.startswith('[') and url.endswith(']'):
        try:
            # Simple parsing for array format
            urls = [u.strip().strip('"').strip("'") for u in url[1:-1].split(',')]
            return urls[0] if urls and urls[0] else ""
        except Exception:
            pass

    return url

# Helper function to extract website name from URL
def extract_website_name(url: str, website_type: str, use_domain_only: bool = False, 
                        button_format: bool = False, status: Optional[str] = None) -> str:
    if not url:
        return "Unknown"

    try:
        domain = CLEAN_URL.sub('', url).split("/")[0]
        
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
                for part in reversed(path_parts):
                    if part and part not in ("country", "countries"):
                        display_name = part.upper() if len(part) <= 3 else part.capitalize()
                        has_country = True
                        break
        
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

    for attempt in range(NetworkConfig.MAX_RETRIES):
        try:
            async with aiohttp.ClientSession(timeout=NetworkConfig.TIMEOUT) as session:
                async with session.get(url, headers=NetworkConfig.HEADERS, allow_redirects=True) as response:
                    return await response.text()
                        
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            debug_print(f"⚠️ Request failed for {url} (attempt {attempt+1}/{NetworkConfig.MAX_RETRIES}): {e}")
            if attempt < NetworkConfig.MAX_RETRIES - 1:
                await asyncio.sleep(NetworkConfig.RETRY_DELAY)
            else:
                debug_print(f"⚠️ Max retries reached for {url}. Giving up.")
    return ""
    

async def parse_website_content(url, website_type):
    """Unified function to parse website content based on type"""
    # ===== PHASE 1: INTELLIGENT CACHE LOOKUP =====
    cached_strategy = _strategy_cache.get_strategy(url)
    detector = CountryDetector()
    
    # ===== PHASE 2: TRY CACHED STRATEGY FIRST =====
    if cached_strategy == "html":
        cached_selector = _strategy_cache.get_cached_selector(url)
        if cached_selector:
            debug_print(f"[CACHE HIT] Using cached HTML selector '{cached_selector}' for {url}")
            
            page_content = await fetch_url_content(url)
            if page_content:
                soup = BeautifulSoup(page_content, "lxml")
                elements = soup.select(cached_selector)
                
                if elements:
                    numbers = [elem.get_text(strip=True) for elem in elements]
                    first_number_str = CLEAN_NUMBER.sub('', str(numbers[0]))
                    _, _, flag_url = detector.detect_country(first_number_str)
                    return (numbers[0] if len(numbers) == 1 else numbers), flag_url
    
    elif cached_strategy == "json":
        debug_print(f"[CACHE HIT] Using cached JSON API strategy for {url}")
        try:
            api_client = APIClient(url)
            json_numbers = await api_client.fetch_json_numbers()
            
            if json_numbers:
                first_number_str = CLEAN_NUMBER.sub('', str(json_numbers[0]))
                _, _, flag_url = detector.detect_country(first_number_str)
                return (json_numbers[0] if len(json_numbers) == 1 else json_numbers), flag_url
        except Exception as e:
            debug_print(f"Cached JSON API failed: {e}")
            
    elif cached_strategy == "api_keys":
        debug_print(f"[CACHE HIT] Using cached API Keys strategy for {url}")
        try:
            api_client = APIClient(url)
            active_numbers = await api_client.get_active_numbers_by_country()
            
            if active_numbers:
                numbers = [number for number, _, _ in active_numbers]
                first_number_str = CLEAN_NUMBER.sub('', str(numbers[0]))
                _, _, flag_url = detector.detect_country(first_number_str)
                _strategy_cache.cache_strategy(url, "api_keys")
                return (numbers[0] if len(numbers) == 1 else numbers), flag_url
        except Exception as e:
            debug_print(f"Cached API Keys failed: {e}")
    
    # ===== PHASE 3: CACHE MISS - TRY ALL STRATEGIES =====
    debug_print(f"[CACHE MISS] Trying all strategies for {url}")
    
    # Strategy 1: HTML Selectors
    page_content = await fetch_url_content(url)
    if page_content:
        soup = BeautifulSoup(page_content, "lxml")
        
        selector_patterns = [
            '.latest-added__title a', 
            '.numbutton', 
            '.styles_number__jQoac',
            '.card-title'
        ]
        
        for selector in selector_patterns:
            elements = soup.select(selector)
            if elements:
                numbers = [elem.get_text(strip=True) for elem in elements]
                first_number_str = CLEAN_NUMBER.sub('', str(numbers[0]))
                _, _, flag_url = detector.detect_country(first_number_str)
                
                # 🎯 CACHE THE SUCCESSFUL STRATEGY
                _strategy_cache.cache_strategy(url, "html", selector)
                debug_print(f"[CACHE SAVE] Cached HTML selector '{selector}' for {url}")
                
                return (numbers[0] if len(numbers) == 1 else numbers), flag_url
    
    # Strategy 2: JSON API
    try:
        debug_print("[DEBUG] HTML parsing failed, attempting JSON API endpoint")
        api_client = APIClient(url)
        json_numbers = await api_client.fetch_json_numbers()
        
        if json_numbers:
            first_number_str = CLEAN_NUMBER.sub('', str(json_numbers[0]))
            _, _, flag_url = detector.detect_country(first_number_str)
            
            # 🎯 CACHE THE SUCCESSFUL STRATEGY
            _strategy_cache.cache_strategy(url, "json")
            debug_print(f"[CACHE SAVE] Cached JSON API strategy for {url}")
            
            return (json_numbers[0] if len(json_numbers) == 1 else json_numbers), flag_url
            
    except Exception as api_error:
        debug_print(f"[ERROR] JSON API failed: {api_error}")
    
    # Strategy 3: API Keys (Final Fallback)
    try:
        debug_print("[DEBUG] JSON API failed, attempting API Keys fallback")
        api_client = APIClient(url)
        active_numbers = await api_client.get_active_numbers_by_country()
        
        if active_numbers:
            numbers = [number for number, _, _ in active_numbers]
            first_number_str = CLEAN_NUMBER.sub('', str(numbers[0]))
            _, _, flag_url = detector.detect_country(first_number_str)
            
            # 🎯 CACHE THE SUCCESSFUL STRATEGY
            _strategy_cache.cache_strategy(url, "api_keys")
            debug_print(f"[CACHE SAVE] Cached API Keys strategy for {url}")
            
            return (numbers[0] if len(numbers) == 1 else numbers), flag_url
            
    except Exception as api_error:
        debug_print(f"[ERROR] API Keys failed: {api_error}")
    
    # ===== PHASE 4: ALL STRATEGIES FAILED =====
    _strategy_cache.mark_failure(url)
    debug_print(f"[FAILURE] All parsing strategies failed for {url}")
    return None, None


async def format_phone_number(number: Union[str, int], remove_code: bool = False, 
                             get_flag: bool = False, website_url: Optional[str] = None) -> Union[str, Tuple[str, Optional[dict]]]:
    """Optimized phone number formatting with centralized country detection"""
    if not number:
        return (None, None) if get_flag else None
        
    # Clean and normalize input number (removes spaces, dashes, and +)
    number_str = CLEAN_NUMBER.sub('', str(number))
    detector = CountryDetector()
    country_code, iso_code, flag_url = detector.detect_country(number_str)
    
    if not country_code:
        formatted = number_str if remove_code else f"+{number_str}"
        return (formatted, None) if get_flag else formatted
    
    rest_of_number = number_str[len(country_code):]
    formatted = rest_of_number if remove_code else f"+{country_code} {rest_of_number}"
    
    if get_flag:
        flag_data = {"primary": flag_url, "iso_code": iso_code.lower()} if iso_code else None
        return formatted, flag_data
    
    return formatted


def get_selected_numbers_for_buttons(numbers, previous_last_number):
    """
    Helper function to return only numbers newer than previous_last_number.
    If no new numbers found, return empty list (NOT all numbers).
    """
    if not numbers:
        return []

    if not previous_last_number:
        return numbers  # No previous number, all are new

    # Determine last_number_position using previous_last_number
    # Only select numbers that are newer than the previous last_number
    try:
        last_position = numbers.index(previous_last_number)
        return numbers[:last_position]  # Only numbers before the previous last number
    except ValueError:
        # previous_last_number not found in current list, all numbers are new
        return numbers


# Helper function to get country code and flag from phone number
async def get_country_info_from_number(number: Union[str, int]) -> Tuple[Optional[str], Optional[str]]:
    """Get country code and flag URL from a phone number"""
    if not number:
        return None, None
        
    # Convert to string and remove any '+' prefix
    number_str = CLEAN_NUMBER.sub('', str(number))
    detector = CountryDetector()
    _, iso_code, flag_url = detector.detect_country(number_str)

    return iso_code, flag_url
            

async def delete_message_after_delay(bot, message, delay_seconds):
    """Delete a message after a specified delay"""
    try:
        await asyncio.sleep(delay_seconds)
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Error deleting message: {e}")


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