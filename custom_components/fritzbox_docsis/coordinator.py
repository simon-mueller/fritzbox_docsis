"""FRITZ!Box API client and update coordinator."""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_REQUEST_TIMEOUT = ClientTimeout(total=10)
_INVALID_SID = "0000000000000000"


class FritzBoxApiError(Exception):
    """Base exception for FRITZ!Box API errors."""


class FritzBoxAuthError(FritzBoxApiError):
    """Raised when the FRITZ!Box rejects the credentials."""


class FritzBoxConnectionError(FritzBoxApiError):
    """Raised when the FRITZ!Box cannot be reached or parsed."""


class FritzBoxApi:
    """Async client for the FRITZ!Box DOCSIS page."""

    def __init__(
        self,
        session: ClientSession,
        url: str,
        username: str,
        password: str,
    ) -> None:
        self.session = session
        self.url = url.rstrip("/")
        self.username = username
        self.password = password

    @staticmethod
    def _create_response(challenge: str, password: str) -> str:
        """Create a response for legacy and current FRITZ!Box challenges."""
        if challenge.startswith("2$"):
            try:
                _, first_iterations, first_salt, second_iterations, second_salt = (
                    challenge.split("$")
                )
                first_hash = hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode(),
                    bytes.fromhex(first_salt),
                    int(first_iterations),
                )
                second_hash = hashlib.pbkdf2_hmac(
                    "sha256",
                    first_hash,
                    bytes.fromhex(second_salt),
                    int(second_iterations),
                )
            except (ValueError, TypeError) as err:
                raise FritzBoxConnectionError("Invalid challenge format") from err
            return f"{challenge}${second_hash.hex()}"

        digest = hashlib.md5(
            f"{challenge}-{password}".encode("utf-16le")
        ).hexdigest()
        return f"{challenge}-{digest}"

    async def _get_text(self, url: str, **kwargs: Any) -> str:
        async with self.session.get(url, timeout=_REQUEST_TIMEOUT, **kwargs) as response:
            response.raise_for_status()
            return await response.text()

    async def async_get_channels(self) -> Any:
        """Authenticate and return the FRITZ!Box downstream channel data."""
        try:
            login_url = f"{self.url}/login_sid.lua"
            challenge_xml = ET.fromstring(await self._get_text(login_url))
            challenge = challenge_xml.findtext("Challenge")
            if not challenge:
                raise FritzBoxConnectionError("FRITZ!Box returned no login challenge")

            response = self._create_response(challenge, self.password)
            login_xml = ET.fromstring(
                await self._get_text(
                    login_url,
                    params={"username": self.username, "response": response},
                )
            )
            sid = login_xml.findtext("SID")
            if not sid or sid == _INVALID_SID:
                raise FritzBoxAuthError("FRITZ!Box rejected the credentials")

            async with self.session.post(
                f"{self.url}/data.lua",
                data={
                    "xhr": 1,
                    "sid": sid,
                    "lang": "de",
                    "page": "docInfo",
                    "xhrId": "all",
                    "no_sidrenew": "",
                },
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()
                payload = await response.json()

            if not isinstance(payload, dict):
                raise FritzBoxConnectionError("FRITZ!Box returned invalid JSON data")
            data = payload.get("data", {})
            channels = data.get("channelDs") if isinstance(data, dict) else None
            if not isinstance(channels, (dict, list)):
                raise FritzBoxConnectionError(
                    "FRITZ!Box response did not contain downstream channels"
                )
            return channels
        except FritzBoxApiError:
            raise
        except (ClientError, TimeoutError, ET.ParseError, ValueError, TypeError) as err:
            raise FritzBoxConnectionError(
                "Unable to retrieve DOCSIS channel data"
            ) from err


class FritzBoxCoordinator(DataUpdateCoordinator[Any]):
    """Fetch channel measurements on a regular interval."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        self.api = FritzBoxApi(
            async_get_clientsession(hass),
            config[CONF_URL],
            config[CONF_USERNAME],
            config[CONF_PASSWORD],
        )

    async def _async_update_data(self) -> Any:
        try:
            return await self.api.async_get_channels()
        except FritzBoxApiError as err:
            raise UpdateFailed(str(err)) from err