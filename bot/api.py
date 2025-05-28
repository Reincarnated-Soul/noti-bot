import aiohttp
from typing import Dict, Optional, List, Tuple
from bot.config import API_KEY, debug_print

class APIClient:
    def __init__(self, base_url: str, api_key: str = API_KEY):
        self.base_url = base_url
        self.api_key = api_key
    
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