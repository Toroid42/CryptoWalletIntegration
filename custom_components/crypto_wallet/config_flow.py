"""Config flow for Crypto Wallet integration."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv
from .const import (
    DOMAIN,
    CONF_CRYPTO_API_ACCESS_TOKEN,
    CONF_BASE_CURRENCY,
    CONF_CRYPTO_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN_AMOUNTS,
)
from .helpers import fetch_available_crypto_tokens, Currency, CryptoWalletTotalSensor
import logging

_LOGGER = logging.getLogger(__name__)


class CryptoWalletConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crypto Wallet."""

    VERSION = 1

    def __init__(self):
        _LOGGER.debug("CryptoWalletConfigFlow: init")
        self.config_data = {}
        self.available_tokens = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CryptoWalletOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        _LOGGER.debug("async_step_user: Initial Step")
        if not self.available_tokens:
            self.available_tokens = await fetch_available_crypto_tokens(self.hass)

        if user_input is not None:
            self.config_data.update(user_input)
            return await self.async_step_token_amounts()

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_CRYPTO_API_ACCESS_TOKEN): cv.string,
                vol.Optional(CONF_BASE_CURRENCY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=Currency.get_all_currency_codes(),
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_CRYPTO_TOKEN): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self.available_tokens,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=300): vol.All(
                    vol.Coerce(int), vol.Range(min=60)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_token_amounts(self, user_input=None):
        """Handle the step to specify amounts for each token."""
        _LOGGER.debug("async_step_user: Token amount")
        if user_input is not None:
            # Store token amounts in the config_data
            self.config_data.update({CONF_TOKEN_AMOUNTS: user_input})
            return self.async_create_entry(title="Crypto Wallet", data=self.config_data)

        tokens = self.config_data.get(CONF_CRYPTO_TOKEN, [])
        token_amounts_schema = {
            vol.Required(token): cv.positive_float for token in tokens
        }
        # FIXME: why is the NumberSelector not working properly?
        # token_amounts_schema = {
        #     vol.Required(
        #         token, default=0.0
        #     ): selector.NumberSelector(
        #         selector.NumberSelectorConfig(
        #             min=0.0, step=0.00000000001, mode=selector.NumberSelectorMode.BOX
        #         )
        #     )
        #     for token in tokens
        # }

        return self.async_show_form(
            step_id="token_amounts", data_schema=vol.Schema(token_amounts_schema)
        )


class CryptoWalletOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        _LOGGER.debug("CryptoWalletOptionsFlowHandler: init")
        # Do not explicitly set self.config_entry
        self.config_data = dict(
            config_entry.data
        )  # Initialize with existing config data
        self.available_tokens = []

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _LOGGER.debug(
            f"async_step_init: Init options called with user_input: {user_input}"
        )

        if not self.available_tokens:
            _LOGGER.debug("async_step_init: Fetching available tokens")
            self.available_tokens = await fetch_available_crypto_tokens(self.hass)

        if user_input is not None:
            _LOGGER.debug(f"async_step_init: User input received: {user_input}")
            self.config_data.update(user_input)
            return await self.async_step_token_amounts()

        tokens = self.config_data.get(CONF_CRYPTO_TOKEN, [])
        access_token = self.config_data.get(CONF_CRYPTO_API_ACCESS_TOKEN, "")
        selected_currency = self.config_data.get(CONF_BASE_CURRENCY, "usd")

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CRYPTO_API_ACCESS_TOKEN, default=access_token
                ): cv.string,
                vol.Optional(
                    CONF_BASE_CURRENCY, default=selected_currency
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=Currency.get_all_currency_codes(),
                        multiple=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Optional(
                    CONF_CRYPTO_TOKEN, default=tokens
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self.available_tokens,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }
        )

        _LOGGER.debug("async_step_init: Showing form")
        return self.async_show_form(step_id="init", data_schema=options_schema)

    async def async_step_token_amounts(self, user_input=None):
        """Handle the step to specify amounts for each token in options."""
        _LOGGER.debug(f"async_step_token_amounts: Called with user_input: {user_input}")

        if user_input is not None:
            _LOGGER.debug(
                f"async_step_token_amounts: Updating config data with: {user_input}"
            )
            self.config_data.update({CONF_TOKEN_AMOUNTS: user_input})

            # Update the config entry
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=self.config_data
            )

            # Notify sensors of the configuration change
            for entity in self.hass.data[DOMAIN].get(self.config_entry.entry_id, []):
                if isinstance(entity, CryptoWalletTotalSensor):
                    await entity.async_update()

            return self.async_create_entry(title="Crypto Wallet", data=self.config_data)

        tokens = self.config_data.get(CONF_CRYPTO_TOKEN, [])
        token_amounts = self.config_entry.data.get(CONF_TOKEN_AMOUNTS, {})
        token_amounts_schema = {
            vol.Required(token, default=token_amounts.get(token, 0.0)): vol.All(
                vol.Coerce(float), vol.Range(min=0)
            )
            for token in tokens
        }
        # FIXME: why is the NumberSelector not working properly?
        # token_amounts_schema = {
        #     vol.Required(
        #         token, default=token_amounts.get(token, 0.0)
        #     ): selector.NumberSelector(
        #         selector.NumberSelectorConfig(
        #             min=0.0, step=0.00000000001, mode=selector.NumberSelectorMode.BOX
        #         )
        #     )
        #     for token in tokens
        # }

        _LOGGER.debug("async_step_token_amounts: Showing form for token amounts")
        return self.async_show_form(
            step_id="token_amounts", data_schema=vol.Schema(token_amounts_schema)
        )
