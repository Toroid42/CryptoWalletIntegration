"""Crypto Wallet Integration for Home Assistant."""
from homeassistant.const import Platform
import logging
_LOGGER = logging.getLogger(__name__)

from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]

async def async_unload_entry(hass, entry) -> bool:
    """Unload Crypto Wallet config entry."""
    _LOGGER.debug(f"Unload Crypto Wallet config entry: {entry.entry_id}")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_setup_entry(hass, entry):
    """Set up Crypto Wallet from a config entry."""
    _LOGGER.debug(f"Set up Crypto Wallet from a config entry: {entry.entry_id}")
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

