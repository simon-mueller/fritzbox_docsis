"""Constants for the FRITZ!Box DOCSIS integration."""

from homeassistant.const import Platform

DOMAIN = "fritzbox_docsis"
PLATFORMS = [Platform.SENSOR]
DEFAULT_URL = "http://192.168.178.1"