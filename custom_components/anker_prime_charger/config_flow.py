"""Config flow for the Anker Prime Charger integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_COUNTRY,
    CONF_DEVICE_SN,
    CONF_FAST_UPDATES_MINUTES,
    CONF_SCAN_INTERVAL,
    CONF_SERVER,
    DEFAULT_FAST_UPDATES_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_FAST_UPDATES_MINUTES,
    MAX_SCAN_INTERVAL,
    MIN_FAST_UPDATES_MINUTES,
    MIN_SCAN_INTERVAL,
    MODEL,
    MODEL_NAME,
)
from .library import create_api
from .solixapi import errors
from .solixapi.api import AnkerSolixApi
from .solixapi.apitypes import API_SERVERS


class PrimeChargerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in to the Anker cloud and pick the Prime Charger."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._credentials: dict[str, Any] = {}
        self._chargers: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for Anker account credentials."""
        errors_: dict[str, str] = {}
        if user_input is not None:
            # Only a login hint: the login returns the account's real country,
            # which then picks the server, so the user isn't asked for it.
            user_input[CONF_COUNTRY] = (self.hass.config.country or "US").upper()
            try:
                self._chargers = await self._async_find_chargers(user_input)
            except (errors.AuthorizationError, errors.InvalidCredentialsError):
                errors_["base"] = "invalid_auth"
            except (ClientError, errors.AnkerSolixError):
                errors_["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error during Anker login")
                errors_["base"] = "unknown"
            else:
                if not self._chargers:
                    errors_["base"] = "no_devices"
                else:
                    self._credentials = user_input
                    if len(self._chargers) == 1:
                        return await self._async_create(next(iter(self._chargers)))
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_EMAIL): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.EMAIL)
                        ),
                        vol.Required(CONF_PASSWORD): TextSelector(
                            TextSelectorConfig(type=TextSelectorType.PASSWORD)
                        ),
                    }
                ),
                user_input,
            ),
            errors=errors_,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one charger when the account has several."""
        if user_input is not None:
            return await self._async_create(user_input[CONF_DEVICE_SN])
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_SN): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=sn, label=f"{name} ({sn})")
                                for sn, name in self._chargers.items()
                            ]
                        )
                    )
                }
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start re-authentication when the stored login stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password and check the charger is still on the account."""
        entry = self._get_reauth_entry()
        errors_: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                chargers = await self._async_find_chargers(data)
            except (errors.AuthorizationError, errors.InvalidCredentialsError):
                errors_["base"] = "invalid_auth"
            except (ClientError, errors.AnkerSolixError):
                errors_["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error during Anker login")
                errors_["base"] = "unknown"
            else:
                if entry.data[CONF_DEVICE_SN] not in chargers:
                    errors_["base"] = "no_devices"
                else:
                    return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors_,
        )

    async def _async_create(self, device_sn: str) -> ConfigFlowResult:
        await self.async_set_unique_id(device_sn)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._chargers[device_sn],
            data={**self._credentials, CONF_DEVICE_SN: device_sn},
        )

    async def _async_find_chargers(self, data: dict[str, Any]) -> dict[str, str]:
        """Log in and return {serial: name} of the supported chargers the account owns.

        The login works on either server and returns the account's country,
        which replaces the hint in data[CONF_COUNTRY]. The server implied by
        that country is tried first, then the other one; the server that has
        the charger is stored in data[CONF_SERVER].
        """
        api = await self._async_login(data)
        if country := api.apisession.get_login_info("country_code"):
            data[CONF_COUNTRY] = country.upper()

        default = create_api(self.hass, data).apisession.region
        servers = [default, *(s for s in API_SERVERS if s != default)]
        for server in servers:
            session = api.apisession
            if session.region != server or session.countryId != data[CONF_COUNTRY]:
                api = await self._async_login(data, server)
            await api.get_bind_devices()
            LOGGER.debug(
                "Anker server %s lists devices: %s",
                server,
                {sn: d.get("device_pn") for sn, d in api.devices.items()},
            )
            if chargers := {
                sn: dev.get("alias") or dev.get("name") or MODEL_NAME
                for sn, dev in api.devices.items()
                if dev.get("device_pn") == MODEL
            }:
                data[CONF_SERVER] = server
                return chargers
        return {}

    async def _async_login(
        self, data: dict[str, Any], server: str | None = None
    ) -> AnkerSolixApi:
        """Create an API client for the server and log in."""
        api = create_api(self.hass, data, server)
        # restart=True: do not reuse a cached token from the other server
        if not await api.async_authenticate(restart=True):
            raise errors.AuthorizationError("Login failed")
        return api

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow."""
        return PrimeChargerOptionsFlow()


class PrimeChargerOptionsFlow(OptionsFlow):
    """Status request interval and fast updates duration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): _number(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, 5, "s"),
                    vol.Required(
                        CONF_FAST_UPDATES_MINUTES,
                        default=options.get(
                            CONF_FAST_UPDATES_MINUTES, DEFAULT_FAST_UPDATES_MINUTES
                        ),
                    ): _number(
                        MIN_FAST_UPDATES_MINUTES, MAX_FAST_UPDATES_MINUTES, 1, "min"
                    ),
                }
            ),
        )


def _number(minimum: int, maximum: int, step: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )
