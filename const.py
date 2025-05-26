"""Constants for the Afore integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "afore3"
PLATFORMS = [Platform.SENSOR]

LOGGER = logging.getLogger(__package__)
SCAN_INTERVAL = timedelta(minutes=10)
