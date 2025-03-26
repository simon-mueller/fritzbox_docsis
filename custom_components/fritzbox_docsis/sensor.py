"""
Sensors displaying the DOCSIS channels and their properties

For more details about this platform, please refer to the documentation at
https://github.com/simon-mueller/fritzbox_docsis
"""

import logging
import requests
import voluptuous as vol
import xml.etree.ElementTree as ET
import hashlib
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import Entity
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv

DOMAIN = "fritzbox_channels"

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    })
}, extra=vol.ALLOW_EXTRA)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    coordinator = FritzBoxCoordinator(hass, entry.data)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

class FritzBoxCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=30)
        self.config = config

    async def _async_update_data(self):
        return await self.hass.async_add_executor_job(self.fetch_data)

    def fetch_data(self):
        FRITZBOX_URL = f"https://{self.config[CONF_HOST]}"
        USERNAME = self.config[CONF_USERNAME]
        PASSWORD = self.config[CONF_PASSWORD]

        session = requests.Session()

        def get_challenge():
            url = f"{FRITZBOX_URL}/login_sid.lua"
            response = session.get(url, verify=False)
            xml_data = ET.fromstring(response.text)
            sid = xml_data.find("SID").text
            challenge = xml_data.find("Challenge").text
            return sid, challenge

        def create_response(challenge, password):
            if challenge and challenge != "0000000000000000":
                challenge_response = f"{challenge}-{password}".encode("utf-16le")
                hash_value = hashlib.md5(challenge_response).hexdigest()
                return f"{challenge}-{hash_value}"
            return None

        def login():
            sid, challenge = get_challenge()
            response_hash = create_response(challenge, PASSWORD)
            if response_hash:
                login_data = {"username": USERNAME, "response": response_hash}
                login_response = session.get(f"{FRITZBOX_URL}/login_sid.lua", params=login_data, verify=False)
                xml_data = ET.fromstring(login_response.text)
                sid = xml_data.find("SID").text
                return sid
            return None

        def get_cable_channels():
            sid = login()
            if not sid or sid == "0000000000000000":
                _LOGGER.error("Login failed!")
                return None

            url = f"{FRITZBOX_URL}/data.lua"
            params = {
                "xhr": 1,
                "sid": sid,
                "lang": "de",
                "page": "docInfo",
                "xhrId": "all",
                "no_sidrenew": "",
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = session.post(url, data=params, headers=headers, verify=False)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("channelDs", {})
            else:
                _LOGGER.error("Error retrieving cable channel info: %s", response.text)
                return None

        return get_cable_channels()

