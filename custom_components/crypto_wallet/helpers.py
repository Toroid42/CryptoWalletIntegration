import aiohttp
import logging
from enum import Enum
from homeassistant.components.sensor import SensorEntity

from homeassistant.util import Throttle

from .const import (
    CONF_CRYPTO_API_ACCESS_TOKEN,
    CONF_BASE_CURRENCY,
    CONF_CRYPTO_TOKEN,
    CONF_TOKEN_AMOUNTS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Initialize an empty list to store the available tokens
available_tokens = []


class Currency(Enum):
    usd = "$"
    eur = "€"
    gbp = "£"
    jpy = "¥"
    cny = "¥"

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


class CryptoWalletTotalSensor(SensorEntity):
    """Representation of the total Crypto Wallet value sensor."""

    def __init__(
        self,
        hass,
        config_entry,
        tokens,
        token_amounts,
        currency_symbol,
        token_sensors,
        scan_interval,
        async_add_entities,
    ):
        """Initialize the sensor."""
        _LOGGER.debug("Construction of CryptoWalletTotalSensor")
        self._hass = hass
        self._config_entry = config_entry
        self._tokens = tokens
        self._token_amounts = token_amounts
        self._token_sensors = token_sensors
        self._state = None
        self._name = "Crypto Wallet Total"
        self._attr_unique_id = f"{DOMAIN}_total"
        self._unit_of_measurement = currency_symbol
        self._prices = {}
        self._async_add_entities = async_add_entities
        self.update = Throttle(scan_interval)(self._update)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._state:
            return round(self._state, 2)
        else:
            return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return {
            "total_value": f"{format_number(self._state)} {Currency.get_currency_symbol(self._unit_of_measurement)}",
        }

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return Currency.get_currency_symbol(self._unit_of_measurement)

    def update_config(self, entry):
        """Update the sensor with new configuration."""
        self._tokens = entry.data.get(CONF_CRYPTO_TOKEN, [])
        self._token_amounts = entry.data.get(CONF_TOKEN_AMOUNTS, {})

    def _update(self, now=None):
        self.async_update()

    async def get_token_prices(self):
        """Fetch the token prices from the API asynchronously."""
        _LOGGER.debug("Fetching tokens prices from API")
        access_token = self._config_entry.data.get(CONF_CRYPTO_API_ACCESS_TOKEN, None)
        selected_currency = self._config_entry.data.get(CONF_BASE_CURRENCY, "usd")
        url = "https://api.coingecko.com/api/v3/simple/price"

        params = {
            "ids": ",".join(self._tokens),
            "vs_currencies": f"{selected_currency}",
        }
        if access_token:
            headers = {"x-cg-demo-api-key": f"{access_token}"}
        else:
            headers = None

        try:
            # Use aiohttp for asynchronous requests
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    response.raise_for_status()  # Ensure status code is OK
                    json_data = await response.json()  # Read JSON asynchronously
                    _LOGGER.debug(f"Fetched tokens: {json_data}")
                    return json_data
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Error fetching token prices: {e}")
            return None

    def calculate_wallet_value(self):
        """Calculate the total wallet value based on token prices and amounts."""
        selected_currency = self._config_entry.data.get(CONF_BASE_CURRENCY, "usd")
        currency_symbol = Currency.get_currency_symbol(selected_currency)
        total_value = 0
        for token in self._tokens:
            amount = self._token_amounts.get(
                token, 1
            )  # Use the specified amount or default to 1
            price = self._prices.get(token, {}).get(selected_currency, 0)
            token_value = price * amount
            _LOGGER.debug(f"{token} ({amount}): {token_value:.2f} {currency_symbol}")
            total_value += token_value
        _LOGGER.debug(f"Total wallet value: {total_value:.2f} {currency_symbol}")
        return total_value

    async def async_update(self):
        """Fetch the token prices and calculate the wallet value."""
        _LOGGER.debug("Updating the Crypto Wallet total value sensor.")
        new_tokens = self._config_entry.data.get(CONF_CRYPTO_TOKEN, [])
        new_token_amounts = self._config_entry.data.get(CONF_TOKEN_AMOUNTS, {})
        currency = self._config_entry.data.get(CONF_BASE_CURRENCY, "usd")
        currency_symbol = Currency.get_currency_symbol(currency)

        if self._unit_of_measurement != currency:
            self._unit_of_measurement = currency
            for token in self._token_sensors:
                self._token_sensors[token].unit_of_measurement = currency

        # Check if tokens or token amounts have changed
        if self._tokens != new_tokens or self._token_amounts != new_token_amounts:
            _LOGGER.debug("Detected change in tokens or token amounts.")
            self._tokens = new_tokens
            self._token_amounts = new_token_amounts

            # Update existing tokens' amounts
            for token in self._token_sensors:
                if token in new_tokens:
                    self._token_sensors[token].amount = new_token_amounts.get(token, 1)

            # Remove tokens that are no longer selected
            for token in list(self._token_sensors.keys()):
                if token not in new_tokens:
                    # FIXME: this only removes the provision of data, but the entity history remains
                    self._hass.async_create_task(
                        self._token_sensors[token].async_remove()
                    )
                    del self._token_sensors[token]

            # Add new tokens
            new_sensors = []
            for token in new_tokens:
                if token not in self._token_sensors:
                    new_sensor = CryptoWalletTokenSensor(
                        token, new_token_amounts.get(token, 1), currency, self
                    )
                    self._token_sensors[token] = new_sensor
                    new_sensors.append(new_sensor)
            if new_sensors:
                self._async_add_entities(new_sensors)

        self._prices = await self.get_token_prices()
        if self._prices:
            total_value = self.calculate_wallet_value()
            self._state = total_value
            _LOGGER.info(
                f"Updated Crypto Wallet total value: {total_value:.2f} {currency_symbol}"
            )
            for sensor in self._token_sensors.values():
                sensor.update_from_total_sensor()
        else:
            _LOGGER.error("Failed to update Crypto Wallet total value.")

    def update_scan_interval(self, scan_interval):
        """Update the scan interval for the sensor."""
        _LOGGER.debug(f"Updating scan interval to {scan_interval}")
        self.update = Throttle(scan_interval)(self._update)


class CryptoWalletTokenSensor(SensorEntity):
    """Representation of an individual Crypto Wallet token sensor."""

    def __init__(self, token, amount, currency, total_sensor):
        """Initialize the sensor."""
        _LOGGER.debug("Construction of CryptoWalletTokenSensor")
        self._token = token
        self._amount = amount
        self._total_sensor = total_sensor
        self._state = None
        self._name = f"Crypto Wallet {token}"
        self._attr_unique_id = f"{DOMAIN}_{token}"
        self._unit_of_measurement = currency
        self._price = 0

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._state:
            return round(self._state, 2)
        else:
            return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return Currency.get_currency_symbol(self._unit_of_measurement)

    @unit_of_measurement.setter
    def unit_of_measurement(self, new_unit):
        """Set the measurement unit of the token."""
        self._unit_of_measurement = new_unit

    @property
    def amount(self):
        """Return the amount of the token."""
        return self._amount

    @amount.setter
    def amount(self, new_amount):
        """Set the amount of the token."""
        self._amount = new_amount
        self.update_from_total_sensor()

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return {
            "token_price": f"{format_number(self._price)} {Currency.get_currency_symbol(self._unit_of_measurement)}",
            "token_amount": f"{format_number(self._amount)}",
            "token_value": f"{format_number(self._state)} {Currency.get_currency_symbol(self._unit_of_measurement)}",
        }

    async def async_remove(self):
        """Remove the sensor entity."""
        await super().async_remove()

    def update_from_total_sensor(self):
        """Update the token value based on the prices fetched by the total sensor."""
        prices = self._total_sensor._prices
        if prices:
            self._price = prices.get(self._token, {}).get(self._unit_of_measurement, 0)
            token_value = self._price * self._amount
            self._state = token_value
            _LOGGER.info(
                f"Updated Crypto Wallet {self._token} value: {token_value:.2f} {self.unit_of_measurement}"
            )
        else:
            _LOGGER.error(f"Failed to update Crypto Wallet {self._token} value.")


def format_number(number):
    """Format a number and return as string"""
    if number:
        return f"{number:.8f}".rstrip("0").rstrip(".")
    else:
        return number
