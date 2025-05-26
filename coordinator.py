"""DataUpdateCoordinator for the Afore integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER, SCAN_INTERVAL
from .models import Status

from .afore import AforeNoDataError, AforeAuthenticationError, Afore


class AforeDataUpdateCoordinator(DataUpdateCoordinator[Status]):
    """The Afore Data Update Coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Afore coordinator."""
        self.config_entry = entry
        self.Afore = Afore(
            access_token=entry.data[CONF_ACCESS_TOKEN],
            session=async_get_clientsession(hass),
        )

        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> Status:
        """Fetch system status from Afore."""
        try:
            return await self.Afore.status()
        except AforeNoDataError as err:
            raise UpdateFailed("Afore has no data available") from err
        except AforeAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
