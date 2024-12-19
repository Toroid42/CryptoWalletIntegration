import logging
from datetime import timedelta

from .const import (
    CONF_BASE_CURRENCY,
    CONF_CRYPTO_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_AMOUNTS,
    DOMAIN,
)

from .helpers import CryptoWalletTotalSensor, CryptoWalletTokenSensor

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
    total_sensor = CryptoWalletTotalSensor(
        hass,
        config_entry,
        tokens,
        token_amounts,
        currency,
        token_sensors,
        timedelta(seconds=scan_interval),
        async_add_entities,
    )

    # Add individual token sensors with the correct amounts
    for token in tokens:
        token_amount = token_amounts.get(token, 1)  # Default to 1 if not specified
        token_sensor = CryptoWalletTokenSensor(
            token, token_amount, currency, total_sensor
        )
        token_sensors[token] = token_sensor

    all_sensors = [total_sensor] + list(token_sensors.values())
    async_add_entities(all_sensors, True)

    # Register sensors in hass.data for later reference
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][config_entry.entry_id] = all_sensors
