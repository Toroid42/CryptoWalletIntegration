import logging
import requests
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.util import Throttle

from .const import (
    CONF_CRYPTO_API_ACCESS_TOKEN,
    CONF_BASE_CURRENCY,
    CONF_CRYPTO_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_AMOUNTS
)

from .helpers import Currency

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Crypto Wallet sensors."""
    _LOGGER.debug("async_setup_entry: Setting up the sensor")
    tokens = config_entry.data.get(CONF_CRYPTO_TOKEN, [])
    scan_interval = config_entry.data.get(CONF_SCAN_INTERVAL, 60)
    currency = config_entry.data.get(CONF_BASE_CURRENCY, "usd")
    token_amounts = config_entry.data.get(CONF_TOKEN_AMOUNTS, {})
    _LOGGER.debug(f"async_setup_entry: scan_interval={scan_interval}")
    _LOGGER.debug(f"async_setup_entry: tokens={tokens}")
    _LOGGER.debug(f"async_setup_entry: token_amounts={token_amounts}")

    token_sensors = {}
    total_sensor = CryptoWalletTotalSensor(hass, config_entry, tokens, token_amounts, currency, token_sensors,
                                           timedelta(seconds=scan_interval), async_add_entities)

    # Add individual token sensors with the correct amounts
    for token in tokens:
        token_amount = token_amounts.get(token, 1)  # Default to 1 if not specified
        token_sensor = CryptoWalletTokenSensor(token, token_amount, currency, total_sensor)
        token_sensors[token] = token_sensor

    # Add the sensors to Home Assistant
    async_add_entities([total_sensor] + list(token_sensors.values()), True)


class CryptoWalletTotalSensor(SensorEntity):
    """Representation of the total Crypto Wallet value sensor."""

    def __init__(self, hass, config_entry, tokens, token_amounts, currency_symbol, token_sensors, scan_interval,
                 async_add_entities):
        """Initialize the sensor."""
        _LOGGER.debug("Construction of CryptoWalletTotalSensor")
        self._hass = hass
        self._config_entry = config_entry
        self._tokens = tokens
        self._token_amounts = token_amounts
        self._token_sensors = token_sensors
        self._state = None
        self._name = "Crypto Wallet Total"
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
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return Currency.get_currency_symbol(self._unit_of_measurement)

    def update_config(self, entry):
        """Update the sensor with new configuration."""
        self._tokens = entry.data.get(CONF_CRYPTO_TOKEN, [])
        self._token_amounts = entry.data.get(CONF_TOKEN_AMOUNTS, {})

    def _update(self, now=None):
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
                    self._hass.async_add_job(self._token_sensors[token].async_remove())
                    del self._token_sensors[token]

            # Add new tokens
            new_sensors = []
            for token in new_tokens:
                if token not in self._token_sensors:
                    new_sensor = CryptoWalletTokenSensor(token, new_token_amounts.get(token, 1), currency, self)
                    self._token_sensors[token] = new_sensor
                    new_sensors.append(new_sensor)
            if new_sensors:
                self._async_add_entities(new_sensors)

        self._prices = self.get_token_prices()
        if self._prices:
            total_value = self.calculate_wallet_value()
            self._state = total_value
            _LOGGER.info(f"Updated Crypto Wallet total value: {total_value:.2f} {currency_symbol}")
            for sensor in self._token_sensors.values():
                sensor.update_from_total_sensor()
        else:
            _LOGGER.error("Failed to update Crypto Wallet total value.")

    def get_token_prices(self):
        """Fetch the token prices from the API."""
        _LOGGER.debug("Fetching tokens prices from API")
        access_token = self._config_entry.data.get(CONF_CRYPTO_API_ACCESS_TOKEN, None)
        selected_currency = self._config_entry.data.get(CONF_BASE_CURRENCY, "usd")
        url = "https://api.coingecko.com/api/v3/simple/price"
        # TODO: do we need to ensure that the configured tokens still exist at coingecko?
        #  If non existing token specified is the response missing or only the single token?
        params = {
            "ids": ",".join(self._tokens),
            "vs_currencies": f"{selected_currency}"
        }
        if access_token:
            headers = {'x-cg-demo-api-key': f'{access_token}'}
        else:
            headers = None
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            _LOGGER.debug(f"Fetched tokens: {response.json()}")
            return response.json()
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error fetching token prices: {e}")
            return None

    def calculate_wallet_value(self):
        """Calculate the total wallet value based on token prices and amounts."""
        selected_currency = self._config_entry.data.get(CONF_BASE_CURRENCY, "usd")
        currency_symbol = Currency.get_currency_symbol(selected_currency)
        total_value = 0
        for token in self._tokens:
            amount = self._token_amounts.get(token, 1)  # Use the specified amount or default to 1
            price = self._prices.get(token, {}).get(selected_currency, 0)
            token_value = price * amount
            _LOGGER.debug(f"{token.upper()} ({amount}): {token_value:.2f} {currency_symbol}")
            total_value += token_value
        _LOGGER.debug(f"Total wallet value: {total_value:.2f} {currency_symbol}")
        return total_value


def format_number(number):
    """Format a number and return as string"""
    if number:
        return f"{number:.8f}".rstrip('0').rstrip('.')
    else:
        return number

class CryptoWalletTokenSensor(SensorEntity):
    """Representation of an individual Crypto Wallet token sensor."""

    def __init__(self, token, amount, currency, total_sensor):
        """Initialize the sensor."""
        _LOGGER.debug("Construction of CryptoWalletTokenSensor")
        self._token = token
        self._amount = amount
        self._total_sensor = total_sensor
        self._state = None
        self._name = f"Crypto Wallet {token.upper()}"
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
            "token_value": f"{format_number(self._state)}"
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
            _LOGGER.info(f"Updated Crypto Wallet {self._token} value: {token_value:.2f} {self.unit_of_measurement}")
        else:
            _LOGGER.error(f"Failed to update Crypto Wallet {self._token} value.")
