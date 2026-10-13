"""Fritz!Box DOCSIS integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import FritzBoxCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up the FRITZ!Box DOCSIS integration from a config entry."""
	coordinator = FritzBoxCoordinator(hass, entry.data)
	await coordinator.async_config_entry_first_refresh()

	hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
	await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
	return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload the integration platforms."""
	if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
		return False

	hass.data[DOMAIN].pop(entry.entry_id, None)
	return True
