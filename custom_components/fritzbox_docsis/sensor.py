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
_CHANNEL_GROUPS = {"channelds": "DOWN", "channelus": "UP"}
_NUMERIC_FIELD_UNITS = {
    "powerlevel": "dBmV",
    "correrrors": None,
    "noncorrerrors": None,
    "mse": "dB",
    "mer": "dB",
    "latency": "ms",
}
_INTEGER_FIELDS = {"correrrors", "noncorrerrors"}
_MEASUREMENT_PRECISION = {
    "powerlevel": 2,
    "mse": 2,
    "mer": 2,
    "latency": 2,
}
_MEASUREMENT_RE = re.compile(
    r"\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*"
)


def _field_name(path: tuple[str | int, ...]) -> str:
    """Return a normalized payload field name."""
    return str(path[-1]).casefold().replace("_", "") if path else ""


def _parse_measurement(
    value: Any, path: tuple[str | int, ...]
) -> tuple[float | int | str, str | None] | None:
    """Convert known numeric fields and retain every other value as text."""
    if value is None:
        return None

    field = _field_name(path)
    if field not in _NUMERIC_FIELD_UNITS:
        return str(value), None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = _MEASUREMENT_RE.fullmatch(value)
        if match is None:
            return None
        number = float(match.group(1).replace(",", "."))
    else:
        return None
    if not math.isfinite(number):
        return None
    if field in _INTEGER_FIELDS:
        if not number.is_integer():
            return None
        return int(number), None
    return number, _NUMERIC_FIELD_UNITS[field]


def _iter_measurements(
    value: Any, path: tuple[str | int, ...] = ()
) -> Iterator[tuple[tuple[str | int, ...], float | int | str, str | None]]:
    """Walk channel records and yield available channel values."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_normalized = key_text.casefold().replace("_", "")
            child_path = path if key_normalized in _WRAPPER_KEYS else path + (key_text,)
            yield from _iter_measurements(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_measurements(child, path + (index,))
    else:
        parsed = _parse_measurement(value, path)
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
    """Create an entity for every available channel field."""
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
    """Represent one value reported by a DOCSIS channel."""

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
        self._attr_suggested_display_precision = _MEASUREMENT_PRECISION.get(
            _field_name(path)
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="AVM",
            name="FRITZ!Box DOCSIS Fork",
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the latest value using its DOCSIS field type."""
        parsed = _parse_measurement(
            _value_at_path(self.coordinator.data, self._path), self._path
        )
        return parsed[0] if parsed is not None else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit defined for this DOCSIS measurement."""
        parsed = _parse_measurement(
            _value_at_path(self.coordinator.data, self._path), self._path
        )
        return parsed[1] if parsed is not None else None

