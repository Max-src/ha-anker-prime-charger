"""Config, reauth and options flow tests."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.anker_prime_charger.const import (
    CONF_COUNTRY,
    CONF_DEVICE_SN,
    CONF_FAST_UPDATES_MINUTES,
    CONF_SCAN_INTERVAL,
    CONF_SERVER,
    DOMAIN,
)
from custom_components.anker_prime_charger.solixapi import errors
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import DEVICE, EMAIL, PASSWORD, SN, FakeCloud

USER_INPUT = {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_user_flow_single_charger(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """One charger on the default server creates the entry directly."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert set(result["data_schema"].schema) == {CONF_EMAIL, CONF_PASSWORD}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "250W Prime Charger"
    assert result["result"].unique_id == SN
    assert result["data"] == {
        CONF_EMAIL: EMAIL,
        CONF_PASSWORD: PASSWORD,
        CONF_COUNTRY: "SG",  # from the login response, not asked
        CONF_SERVER: "eu",  # the account's country (SG) decides, not the US hint
        CONF_DEVICE_SN: SN,
    }


async def test_user_flow_falls_back_to_other_server(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """The first server tried has no charger; it is found on the other one."""
    cloud.charger_servers = {"com"}
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERVER] == "com"


async def test_user_flow_server_from_account_country(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """The HA country is only a login hint; the account's country picks the server."""
    hass.config.country = "DE"  # hint -> eu
    cloud.account_country = "US"  # account -> com
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["data"][CONF_COUNTRY] == "US"
    assert result["data"][CONF_SERVER] == "com"
    # First login used the hint's server; the charger came from the account's.
    assert cloud.apis[0].apisession.region == "eu"
    assert cloud.api.apisession.region == "com"


async def test_user_flow_invalid_auth_then_recover(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """A login error shows invalid_auth and the user can retry."""
    cloud.auth_error = errors.AuthorizationError("bad")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    cloud.auth_error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_connect(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """Cloud errors show cannot_connect."""
    cloud.bind_error = errors.ConnectError("down")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_no_charger(hass: HomeAssistant, cloud: FakeCloud) -> None:
    """No A2345 on either server shows no_devices."""
    cloud.charger_servers = set()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "no_devices"}


async def test_user_flow_ignores_other_models(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Only A2345 devices are offered."""
    cloud.devices = [{**DEVICE, "device_sn": "OTHER", "device_pn": "A1761"}]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "no_devices"}


async def test_user_flow_multiple_chargers(
    hass: HomeAssistant, cloud: FakeCloud
) -> None:
    """Several chargers show a picker."""
    cloud.devices = [dict(DEVICE), {**DEVICE, "device_sn": "SECOND", "alias": "Desk"}]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SN: "SECOND"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desk"
    assert result["data"][CONF_DEVICE_SN] == "SECOND"


async def test_user_flow_already_configured(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """The same charger cannot be added twice."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Re-authentication stores the new password and keeps the rest."""
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    cloud.auth_error = errors.InvalidCredentialsError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    cloud.auth_error = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_DEVICE_SN] == SN
    assert entry.data[CONF_EMAIL] == EMAIL

    # Success reloads the entry in the background; let it finish, then unload
    # so the coordinator's refresh timer doesn't linger past the test.
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reauth_charger_missing(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Reauth is refused if the account no longer has this charger."""
    cloud.devices = [{**DEVICE, "device_sn": "SOMEONE_ELSE"}]
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["errors"] == {"base": "no_devices"}
    assert entry.data[CONF_PASSWORD] == PASSWORD


async def test_reconfigure(
    hass: HomeAssistant, cloud: FakeCloud, entry: MockConfigEntry
) -> None:
    """Reconfigure changes the login, keeping the charger; another account is refused."""
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    cloud.auth_error = errors.InvalidCredentialsError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    cloud.auth_error = None
    cloud.devices = [{**DEVICE, "device_sn": "SOMEONE_ELSE"}]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "other@example.com", CONF_PASSWORD: "x"}
    )
    assert result["errors"] == {"base": "charger_not_in_account"}

    cloud.devices = [DEVICE]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "new@example.com", CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_EMAIL] == "new@example.com"
    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_DEVICE_SN] == SN

    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_flow(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """The status interval and fast updates duration apply after reload."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_FAST_UPDATES_MINUTES: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert setup_entry.options == {
        CONF_SCAN_INTERVAL: 60,
        CONF_FAST_UPDATES_MINUTES: 15,
    }
    assert setup_entry.runtime_data.update_interval.total_seconds() == 60
