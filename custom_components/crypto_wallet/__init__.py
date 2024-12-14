"""Crypto Wallet Integration for Home Assistant."""

from homeassistant.const import Platform
import logging

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    """Set up Crypto Wallet from a config entry."""
    _LOGGER.debug(f"Setting up Crypto Wallet config entry: {entry.entry_id}")
    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setup(entry, platform)
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload Crypto Wallet config entry."""
    _LOGGER.debug(f"Unloading Crypto Wallet config entry: {entry.entry_id}")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
