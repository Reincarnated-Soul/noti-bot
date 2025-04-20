from typing import Tuple, Optional, List, Union
import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup, SoupStrainer

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
                country_name = path_parts[-1]
                # For short country names (like USA, UK), use uppercase
                if len(country_name) <= 3:
                    return country_name.upper()
                else:
                    return country_name.capitalize()

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

    # If website_type is None, try single first, then multiple
    if website_type is None:
        # Try single
        try:
            soup = BeautifulSoup(page_content, "lxml")
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
                # print(f"[DEBUG] parse_website_content - extracted number for single: {number}")
                # print(f"[DEBUG] parse_website_content - extracted flag_url for single: {flag_url}")
                return number, flag_url
            else:
                # print(f"[DEBUG] parse_website_content - no .latest-added__title a found for single")
                pass
        except Exception as e:
            print(f"Error parsing single number website: {e}")
        # Try multiple
        try:
            soup = BeautifulSoup(page_content, 'html.parser')
            all_numbers = [button.text.strip() for button in soup.select('.numbutton')]
            images = soup.select('img')
            flag_url = None
            if len(images) > 1:
                flag_img = images[1]
                flag_url = flag_img.get('data-lazy-src') or flag_img.get('src')
                if flag_url and not flag_url.startswith(('http://', 'https://')):
                    base_url = url.rsplit('/', 2)[0]
                    flag_url = f"{base_url}{flag_url}"
            if all_numbers:
                # print(f"[DEBUG] parse_website_content - extracted numbers for multiple: {all_numbers}")
                # print(f"[DEBUG] parse_website_content - extracted flag_url for multiple: {flag_url}")
                return all_numbers, flag_url
        except Exception as e:
            print(f"Error parsing multiple numbers website: {e}")
        return None, None

    if website_type == "single":
        # Parse for single number website
        try:
            soup = BeautifulSoup(page_content, "lxml")
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
                # print(f"[DEBUG] parse_website_content - extracted number for single: {number}")
                # print(f"[DEBUG] parse_website_content - extracted flag_url for single: {flag_url}")
                return number, flag_url
            else:
                # print(f"[DEBUG] parse_website_content - no .latest-added__title a found for single")
                pass
                return None, None
        except Exception as e:
            print(f"Error parsing single number website: {e}")
            return None, None
    else:
        # Parse for multiple numbers website
        try:
            soup = BeautifulSoup(page_content, 'html.parser')
            all_numbers = [button.text.strip() for button in soup.select('.numbutton')]
            images = soup.select('img')
            flag_url = None
            if len(images) > 1:
                flag_img = images[1]
                flag_url = flag_img.get('data-lazy-src') or flag_img.get('src')
                if flag_url and not flag_url.startswith(('http://', 'https://')):
                    base_url = url.rsplit('/', 2)[0]
                    flag_url = f"{base_url}{flag_url}"
            if all_numbers:
                # print(f"[DEBUG] parse_website_content - extracted numbers for multiple: {all_numbers}")
                # print(f"[DEBUG] parse_website_content - extracted flag_url for multiple: {flag_url}")
                return all_numbers, flag_url
        except Exception as e:
            print(f"Error parsing multiple numbers website: {e}")
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

def format_phone_number(number, remove_code=False):
    # Convert to string if it's an integer
    if isinstance(number, int):
        number_str = str(number)
    else:
        # Remove + if present
        number_str = number.lstrip('+')
    
    # Common country code lengths
    country_codes = {
        '1': 1,    # USA, Canada
        '44': 2,   # UK
        '46': 2,   # Sweden
        '43': 2,   # Austria
        '358': 3,  # Finland
        '386': 3,  # Slovenia
        # Add more as needed
    }
    
    # Try to determine the country code
    country_code_length = None
    
    # Check if the number starts with any known country code
    for code, length in country_codes.items():
        if number_str.startswith(code):
            country_code_length = length
            break
    
    # If we couldn't determine the country code
    if country_code_length is None:
        return number_str if remove_code else f"+{number_str}"
    
    # Split the number
    country_code = number_str[:country_code_length]
    rest_of_number = number_str[country_code_length:]
    
    # Return based on the remove_code flag
    if remove_code:
        return rest_of_number
    else:
        return f"+{country_code} {rest_of_number}"

# For backward compatibility
remove_country_code = lambda number: format_phone_number(number, remove_code=True)