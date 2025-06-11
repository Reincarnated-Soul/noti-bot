import aiohttp
import time
from typing import Dict, Optional, List, Tuple
from bot.config import API_KEY, URL, debug_print, parse_url_array

class APIClient:
    def __init__(self, base_url: str = None, api_key: str = API_KEY):
        """
        Initialize API client with base URL and API key
        Args:
            base_url: Optional base URL. If not provided, will use URL from environment
            api_key: API key for authentication. Defaults to API_KEY from config
        """
        # Get URL from environment if not provided
        if not base_url:
            base_url = URL

        # Handle array of URLs
        urls = parse_url_array(base_url) if isinstance(base_url, str) else [base_url]
        self.base_url = urls[0] if urls else ""  # Use first URL by default
        
        # Transform URL from www to static if needed
        self.base_url = self._transform_url(self.base_url)
        
        # Store the JSON API URL separately (without /api)
        self.json_api_url = self.base_url
        
        # Ensure base URL ends with /api for regular API calls
        if self.base_url and not self.base_url.endswith("/api"):
            self.base_url = f"{self.base_url}/api"

        self.api_key = api_key
    
    def _transform_url(self, url: str) -> str:
        """ Transform URL by replacing 'www.' with 'static.' """
        if url and 'www.' in url:
            return url.replace('www.', 'static.')
        return url
    
    async def _make_request(self, endpoint: str, method: str = "GET", params: Dict = None) -> Optional[Dict]:
        """Make a request to the API"""
        try:
            url = f"{self.base_url}/{endpoint}"
            if params is None:
                params = {}
            if self.api_key:
                params['apikey'] = self.api_key
            
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    params=params
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            debug_print(f"Error making request: {e}")
            return None

    async def get_numbers(self, country: int = None) -> Dict:
        """Get available phone numbers"""
        params = {'lang': 'en'}
        if country:
            params['country'] = country
            
        return await self._make_request("getFreeList", params=params)

    async def get_active_numbers_by_country(self) -> List[Tuple[str, str, str]]:
        """Get active numbers for each country with country codes
        Returns a list of tuples: (number, country_code, country_name)
        """
        response = await self.get_numbers()
        if not response or "countries" not in response:
            return []

        active_numbers = []
        
        for country_info in response["countries"]:
            country_code = str(country_info["country"])
            country_name = country_info["country_text"]
            
            country_response = await self.get_numbers(country=int(country_code))
            if country_response and "numbers" in country_response:
                for number, details in country_response["numbers"].items():
                    if not details.get('is_archive', True):
                        full_number = details.get('full_number', f'+{number}')
                        active_numbers.append((full_number, country_code, country_name))
        
        return active_numbers
        
    async def fetch_json_numbers(self, url: str = None) -> List[str]:
        """
        Fetch phone numbers from a JSON API endpoint
        Returns a list of phone numbers
        """
        try:
            # Use provided URL or construct URL from json_api_url
            if url:
                target_url = url
            else:
                # Use the json_api_url (without /api) and append /latest.json
                target_url = f"{self.json_api_url}/latest.json"
                
            params = {
                'z': int(time.time() * 1000)  # Current timestamp in milliseconds
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return [item['number'] for item in data if 'number' in item]
                    
        except Exception as e:
            debug_print(f"Error fetching numbers from JSON API: {e}")
            return [] 