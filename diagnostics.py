"""Diagnostics support for Afore."""
from __future__ import annotations

import json
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import AforeDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: AforeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Round-trip via JSON to trigger serialization
    data: dict[str, Any] = json.loads(coordinator.data.json())
    return data
