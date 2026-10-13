"""Sensors for FRITZ!Box DOCSIS channel measurements."""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FritzBoxCoordinator

_WRAPPER_KEYS = {"data", "channels"}
_IDENTIFIER_KEYS = {"channel", "channelid", "channelnumber", "id"}
_CHANNEL_GROUPS = {"channelds": "DOWN", "channelus": "UP"}
_MEASUREMENT_RE = re.compile(
    r"\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*"
)


def _parse_measurement(value: Any) -> tuple[float | int, str | None] | None:
    """Parse numeric API values while retaining a supplied unit."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value, None
    if not isinstance(value, str):
        return None

    match = _MEASUREMENT_RE.fullmatch(value)
    if match is None:
        return None
    number = float(match.group(1).replace(",", "."))
    if not math.isfinite(number):
        return None
    unit = match.group(2).strip() or None
    return number, unit


def _iter_measurements(
    value: Any, path: tuple[str | int, ...] = ()
) -> Iterator[tuple[tuple[str | int, ...], float | int, str | None]]:
    """Walk channel records and yield paths to numeric measurements."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_normalized = key_text.casefold().replace("_", "")
            if key_normalized in _IDENTIFIER_KEYS:
                continue
            child_path = path if key_normalized in _WRAPPER_KEYS else path + (key_text,)
            yield from _iter_measurements(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_measurements(child, path + (index,))
    else:
        parsed = _parse_measurement(value)
        if parsed is not None and path:
            yield path, parsed[0], parsed[1]


def _value_at_path(data: Any, path: tuple[str | int, ...]) -> Any:
    """Read a measurement from the coordinator's latest payload."""
    value = data
    for part in path:
        if isinstance(value, Mapping):
            value = value[part]
        elif isinstance(value, list) and isinstance(part, int):
            value = value[part]
        else:
            return None
    return value


def _path_label(path: tuple[str | int, ...]) -> str:
    direction = _CHANNEL_GROUPS.get(str(path[0]).casefold()) if path else None
    channel_path = path[1:] if direction else path
    channel_label = " ".join(
        str(part + 1 if isinstance(part, int) else part) for part in channel_path
    )
    if direction:
        return f"{direction} Channel {channel_label}"
    return channel_label


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create an entity for every numeric channel measurement."""
    coordinator: FritzBoxCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_paths: set[tuple[str | int, ...]] = set()

    def add_new_entities() -> None:
        new_entities = []
        for path, _, _ in _iter_measurements(coordinator.data):
            if path not in known_paths:
                known_paths.add(path)
                new_entities.append(FritzBoxChannelSensor(coordinator, entry, path))
        if new_entities:
            async_add_entities(new_entities)

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


class FritzBoxChannelSensor(CoordinatorEntity[FritzBoxCoordinator], SensorEntity):
    """Represent one numeric value reported by a DOCSIS channel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FritzBoxCoordinator,
        entry: ConfigEntry,
        path: tuple[str | int, ...],
    ) -> None:
        super().__init__(coordinator)
        self._path = path
        label = _path_label(path)
        slug = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
        self._attr_unique_id = f"{entry.entry_id}_{slug}"
        self._attr_name = label
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="AVM",
            name="FRITZ!Box DOCSIS Fork",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the latest measurement value."""
        parsed = _parse_measurement(_value_at_path(self.coordinator.data, self._path))
        return parsed[0] if parsed is not None else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit supplied by the router, when available."""
        parsed = _parse_measurement(_value_at_path(self.coordinator.data, self._path))
        return parsed[1] if parsed is not None else None

