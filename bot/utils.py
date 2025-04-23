import os
import asyncio
import aiohttp
from typing import Tuple, Optional, List, Union
from bs4 import BeautifulSoup, SoupStrainer
from bot.config import debug_print, DEV_MODE

# Global dictionary of country codes [length, ISO code]
# Arranged in ascending order by country code
COUNTRY_CODES = {
    '1':    [1, 'ca', 'us'],  # USA, Canada
    '7':    [1, 'ru', 'kz'],  # Russia, Kazakhstan
    '31':   [2, 'nl'],        # Netherlands
    '32':   [2, 'be'],        # Belgium
    '33':   [2, 'fr'],        # France
    '34':   [2, 'es'],        # Spain
    '39':   [2, 'it'],        # Italy
    '40':   [2, 'ro'],        # Romania
    '41':   [2, 'ch'],        # Switzerland
    '43':   [2, 'at'],        # Austria
    '44':   [2, 'gb'],        # UK (United Kingdom)
    '45':   [2, 'dk'],        # Denmark
    '46':   [2, 'se'],        # Sweden
    '48':   [2, 'pl'],        # Poland
    '49':   [2, 'de'],        # Germany
    '52':   [2, 'mx'],        # Mexico
    '55':   [2, 'br'],        # Brazil
    '60':   [2, 'my'],        # Malaysia
    '61':   [2, 'au'],        # Australia
    '62':   [2, 'id'],        # Indonesia
    '63':   [2, 'ph'],        # Philippines
    '66':   [2, 'th'],        # Thailand
    '91':   [2, 'in'],        # India
    '212':  [3, 'ma'],        # Morocco
    '230':  [3, 'mu'],        # Mauritius
    '234':  [3, 'ng'],        # Nigeria
    '351':  [3, 'pt'],        # Portugal
    '353':  [3, 'ie'],        # Ireland
    '354':  [3, 'is'],        # Iceland
    '358':  [3, 'fi'],        # Finland
    '359':  [3, 'bg'],        # Bulgaria
    '370':  [3, 'lt'],        # Lithuania
    '371':  [3, 'lv'],        # Latvia
    '372':  [3, 'ee'],        # Estonia
    '380':  [3, 'ua'],        # Ukraine
    '381':  [3, 'rs'],        # Serbia
    '385':  [3, 'hr'],        # Croatia
    '386':  [3, 'si'],        # Slovenia
    '420':  [3, 'cz'],        # Czech Republic
    '421':  [3, 'sk'],        # Slovakia
    '670':  [3, 'tl'],        # Timor-Leste
    '852':  [3, 'hk'],        # Hong Kong
    '972':  [3, 'il'],        # Israel
    '995':  [3, 'ge'],        # Georgia
    '1787': [4, 'pr'],        # Puerto Rico
}

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
        if website_type == "single":
            # Extract domain name for single type websites
            # Remove http:// or https:// prefix
            domain = url.split("//")[-1].split("/")[0]
            # Remove www. if present
            if domain.startswith("www."):
                domain = domain[4:]
            # Extract the main domain name (before the first dot)
            main_domain = domain.split(".")[0]
            # Capitalize the first letter
            return main_domain.capitalize()
        else:
            # For multiple type websites, extract the country name from the path
            path_parts = url.split("/")
            # Filter out empty parts (like trailing slashes)
            path_parts = [part for part in path_parts if part]
            if path_parts:
                country_code = path_parts[-1].lower()
                
                # If the country code is in our dictionary, return the country name
                # Search by both potential phone code and ISO code
                if country_code.isdigit() and country_code in COUNTRY_CODES:
                    iso_code = COUNTRY_CODES[country_code][1]
                    return iso_code.upper()
                elif len(country_code) == 2:
                    # It might be an ISO code directly
                    return country_code.upper()
                
                # If not found, just return the original path component
                if len(country_code) <= 3:
                    return country_code.upper()
                else:
                    return country_code.capitalize()

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
                }) as head_response:
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
                return None

async def parse_website_content(url, website_type):
    """Unified function to parse website content based on type"""
    page_content = await fetch_url_content(url)
    if not page_content:
        return None, None
        
    # Create BeautifulSoup object once
    soup = BeautifulSoup(page_content, "lxml")
    
    # Helper function to convert SVG to PNG (using URL approach)
    async def get_flag_from_country_code(country_code):
        """Get flag PNG URL from country code using a conversion service"""
        if not country_code:
            return None

        # Try to determine if this is a numeric country code (phone code) or ISO code
        if country_code.isdigit():
            # It's a numeric code, look up the ISO code
            if country_code in COUNTRY_CODES:
                # For entries with multiple ISO codes (like '1'), use the first one after the length
                iso_code = COUNTRY_CODES[country_code][1]
            else:
                print(f"Unknown phone country code: {country_code}")
                return None
        else:
            # It's already a text code, ensure it's 2 characters
            iso_code = country_code.lower()
            if len(iso_code) > 2:
                iso_code = iso_code[:2]

        # Use a more reliable service that provides flat-style PNG flags
        # Using Flagpedia which is known to be reliable
        return f"https://flagpedia.net/data/flags/w580/{iso_code.lower()}.png"
        
        # Alternative options if needed:
        # return f"https://raw.githubusercontent.com/hampusborgos/country-flags/main/png1000px/{iso_code.lower()}.png"
        
    # Helper functions to parse different website types
    def parse_single_website():
        try:
            latest_title_a = soup.select_one(".latest-added__title a")
            flag_url = None
            # First, try to find a .png flag with alt containing 'country flag'
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
                        
            if latest_title_a:
                number = latest_title_a.get_text(strip=True)
                return number, flag_url
            return None, None
        except Exception as e:
            print(f"Error parsing single number website: {e}")
            return None, None
            
    async def parse_multiple_website():
        try:
            # Try different parsers if one fails
            all_numbers = [button.text.strip() for button in soup.select('.numbutton')]
            second_site = [numbers.text.strip() for numbers in soup.select('.card-title')]
            all_types = [select.text.strip() for select in soup.select('.card-header')]
            
            # Look for country code in page (could be in meta tags, classes, or data attributes)
            country_code = None
            meta_country = soup.find('meta', {'name': 'country'}) or soup.find('meta', {'property': 'og:country'})
            if meta_country:
                country_code = meta_country.get('content')
            
            # If no country code found, try to extract from URL
            if not country_code and url:
                path_parts = url.split("/")
                if path_parts and len(path_parts) > 1:
                    potential_code = path_parts[-1].lower()
                    if len(potential_code) <= 3:
                        country_code = potential_code
            
            flag_url = None
            # If we found a country code, try to get a flag image
            if country_code:
                flag_url = await get_flag_from_country_code(country_code)
            
            # Fallback to image extraction if no country code
            if not flag_url:
                images = soup.select('img')
                if len(images) > 1:
                    flag_img = images[1]
                    flag_url = flag_img.get('data-lazy-src') or flag_img.get('src')
                    if flag_url and not flag_url.startswith(('http://', 'https://')):
                        base_url = url.rsplit('/', 2)[0]
                        flag_url = f"{base_url}{flag_url}"
                    
            if all_numbers:
                return all_numbers, flag_url
            elif second_site:
                return second_site, flag_url
            elif all_types:
                return all_types, flag_url
            return None, None
        except Exception as e:
            print(f"Error parsing multiple numbers website: {e}")
            return None, None

    # If website_type is None, try single first, then multiple
    if website_type is None:
        # Try single
        result, flag_url = parse_single_website()
        if result is not None:
            return result, flag_url
            
        # Try multiple
        result, flag_url = await parse_multiple_website()
        if result is not None:
            return result, flag_url
            
        return None, None
        
    # Process based on specified website type
    if website_type == "single":
        return parse_single_website()
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

def format_phone_number(number, remove_code=False, get_flag=False, website_url=None):
    # Convert to string if it's an integer
    if isinstance(number, int):
        number_str = str(number)
    else:
        # Remove + if present
        number_str = number.lstrip('+')
    
    # Try to determine the country code using our global COUNTRY_CODES dictionary
    country_code_length = None
    country_code_value = None
    
    # Check if the number starts with any known country code
    for code, info in COUNTRY_CODES.items():
        if number_str.startswith(code):
            country_code_length = len(code)
            country_code_value = code
            break
    
    # If we couldn't determine the country code
    if country_code_length is None:
        if get_flag:
            return number_str if remove_code else f"+{number_str}", None
        return number_str if remove_code else f"+{number_str}"
    
    # Split the number
    country_code = country_code_value
    rest_of_number = number_str[country_code_length:]
    
    # Get flag URL if requested
    if get_flag:
        flag_url = None
        if country_code in COUNTRY_CODES:
            # For entries with multiple ISO codes (like '1' for USA/Canada or '7' for Russia/Kazakhstan)
            # Check if we can determine the specific country from the website URL
            iso_code = None
            
            if website_url:
                # Try to determine specific country from URL if it's a shared country code
                country_from_url = None
                if '/' in website_url:
                    # Extract country name from URL
                    path_parts = website_url.split('/')
                    # Extract last part of URL and convert to lowercase
                    country_from_url = path_parts[-1].lower() if path_parts else None
                
                # For country code '1' (USA/Canada)
                if country_code == '1' and len(COUNTRY_CODES[country_code]) > 2:
                    if country_from_url:
                        if 'canada' in country_from_url or country_from_url == 'ca':
                            iso_code = 'ca'  # Canada
                        elif 'states' in country_from_url or 'usa' in country_from_url or country_from_url == 'us':
                            iso_code = 'us'  # USA
                
                # For country code '7' (Russia/Kazakhstan)
                elif country_code == '7' and len(COUNTRY_CODES[country_code]) > 2:
                    if country_from_url:
                        if 'kazakhstan' in country_from_url or country_from_url == 'kz':
                            iso_code = 'kz'  # Kazakhstan
                        elif 'russia' in country_from_url or country_from_url == 'ru':
                            iso_code = 'ru'  # Russia
            
            # If we couldn't determine the specific country, use the first one in the list
            if not iso_code:
                iso_code = COUNTRY_CODES[country_code][1]
            
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