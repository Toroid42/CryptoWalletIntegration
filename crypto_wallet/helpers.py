import aiohttp
import logging
from enum import Enum

_LOGGER = logging.getLogger(__name__)

# Initialize an empty list to store the available tokens
available_tokens = []


class Currency(Enum):
    usd = '$'
    eur = '€'
    gbp = '£'
    jpy = '¥'
    cny = '¥'

    @classmethod
    def get_currency_symbol(cls, currency_code: str) -> str:
        try:
            return cls[currency_code].value
        except KeyError:
            return currency_code

    @classmethod
    def get_all_currency_codes(cls) -> list:
        return [currency.name for currency in cls]


async def fetch_available_crypto_tokens(hass):
    global available_tokens

    # If the list is already populated, return it
    if available_tokens:
        _LOGGER.debug("Reuse available tokens from API")
        return available_tokens
    _LOGGER.debug("Fetching available tokens from API")

    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                coins = await response.json()
                # Extract the IDs of the coins
                available_tokens = [coin["id"] for coin in coins]
                return available_tokens
    except aiohttp.ClientError as e:
        _LOGGER.error(f"Error fetching available crypto tokens: {e}")
        return []
