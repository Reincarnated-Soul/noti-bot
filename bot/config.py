import os
from typing import Dict, Any
from dotenv import load_dotenv

# Configuration
CONFIG_FILE = "config_file.env"
if os.path.exists(CONFIG_FILE):
    load_dotenv(CONFIG_FILE)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
URL = os.getenv("URL")  # Can be a single URL or an array of URLs

# Optional secret configuration
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))
ENABLE_REPEAT_NOTIFICATION = os.getenv("ENABLE_REPEAT_NOTIFICATION",
                                       "False").lower() == "true"
DEFAULT_REPEAT_INTERVAL = 900  # Default: 15 minutes
SINGLE_MODE = os.getenv("SINGLE_MODE", "false").lower() == "true"
API_KEY = os.getenv("API_KEY")

# Development mode - controls whether debug messages are printed
# Set to True via environment variable to enable debug prints
DEV_MODE = os.getenv("DEV_MODE", "False").lower() == "true"

# Custom debug print function that only prints when DEV_MODE is True
def debug_print(*args, **kwargs):
    """Print debug messages only when DEV_MODE is enabled"""
    if DEV_MODE:
        print(*args, **kwargs)

# Function to parse array-formatted URL string
def parse_url_array(url_str):
    """Parse a string that might be a JSON array of URLs"""
    if not url_str:
        return []

    url_str = url_str.strip()

    # Check if it looks like an array
    if url_str.startswith('[') and url_str.endswith(']'):
        # First try: direct parsing with ast.literal_eval (for quoted URLs)
        try:
            import ast
            # Ensure proper quotes for string literals
            cleaned_str = url_str.replace("'", "'").replace("'", "'")
            urls = ast.literal_eval(cleaned_str)
            if isinstance(urls, list):
                return urls
        except (SyntaxError, ValueError) as e:
            print(f"Standard parsing failed, trying alternative: {e}")

        # Second try: manual parsing (for unquoted URLs like [https://example.com, https://example2.com])
        try:
            # Remove brackets and split by comma
            content = url_str[1:-1].strip()
            parts = [p.strip() for p in content.split(',')]
            # Filter out empty parts and remove any quotes
            urls = [p.strip("'").strip('"') for p in parts if p.strip()]
            if urls:
                return urls
        except Exception as e2:
            print(f"Alternative parsing also failed: {e2}")

    # If not an array or parsing failed, treat as single URL
    return [url_str]


def load_website_configs() -> Dict[str, Dict[str, Any]]:
    """Load website configurations from environment variables"""
    WEBSITE_CONFIGS = {}

    # First check for URL array format
    urls = []
    url_env = os.getenv("URL")
    if url_env:
        urls = parse_url_array(url_env)

        # Create config for each URL in the array
        for i, url in enumerate(urls, 1):
            config = {
                "url": url,
                "enabled": True,
                "position": i
            }
            url_type = os.getenv(f"URL_{i}_TYPE")
            if url_type:
                config["type"] = url_type
            WEBSITE_CONFIGS[f"site_{i}"] = config

    # If no URLs found in array format, try numbered URL variables
    if not WEBSITE_CONFIGS:
        i = 1
        while True:
            url_key = f"URL_{i}"
            url = os.getenv(url_key)
            if not url:
                # No more URLs found
                break
            else:
                url_type = os.getenv(f"{url_key}_TYPE")

            config = {
                "url": url,
                "enabled": True,
                "position": i
            }
            if url_type:
                config["type"] = url_type
            WEBSITE_CONFIGS[f"site_{i}"] = config
            i += 1

    # Fallback for legacy URL2 variable
    if not WEBSITE_CONFIGS and os.getenv("URL2"):
        config1 = {
            "url": os.getenv("URL"),
            "enabled": True,
            "position": 1
        }
        config2 = {
            "url": os.getenv("URL2"),
            "enabled": True,
            "position": 2
        }
        url1_type = os.getenv("URL_TYPE")
        url2_type = os.getenv("URL2_TYPE")
        if url1_type:
            config1["type"] = url1_type
        if url2_type:
            config2["type"] = url2_type
        WEBSITE_CONFIGS["site_1"] = config1
        WEBSITE_CONFIGS["site_2"] = config2

    # Final fallback if still no URLs configured
    if not WEBSITE_CONFIGS and os.getenv("URL"):
        config1 = {
            "url": os.getenv("URL"),
            "enabled": True,
            "position": 1
        }
        url1_type = os.getenv("URL_TYPE")
        if url1_type:
            config1["type"] = url1_type
        WEBSITE_CONFIGS["site_1"] = config1

    return WEBSITE_CONFIGS
