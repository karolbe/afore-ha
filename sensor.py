"""Support for getting collected information from Afore."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfTime,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AforeDataUpdateCoordinator

from .models import Status, System


@dataclass
class AforeSensorEntityDescriptionMixin:
    """Mixin for required keys."""

    value_fn: Callable[[Status], int | float | None]


@dataclass
class AforeSensorEntityDescription(
    SensorEntityDescription, AforeSensorEntityDescriptionMixin
):
    """Describes a Afore sensor entity."""


SENSORS: tuple[AforeSensorEntityDescription, ...] = (
    AforeSensorEntityDescription(
        key="token_expiration",
        name="Token Expiration",
        translation_key="token_expiration",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda status: status.expirationDate,
    ),
    AforeSensorEntityDescription(
        key="network_status",
        name="Network Status",
        translation_key="network_status",
        options=["ALL_OFFLINE", "NORMAL"],
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda status: status.networkStatus,
    ),
    AforeSensorEntityDescription(
        key="generation_power",
        translation_key="generation_power",
        name="Current Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda status: status.generationPower,
    ),
    AforeSensorEntityDescription(
        key="generation_year",
        translation_key="generation_year",
        name="This Year Energy Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda status: status.generationYear,
    ),
    AforeSensorEntityDescription(
        key="generation_month",
        translation_key="generation_month",
        name="This Month Energy Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda status: status.generationMonth,
    ),
    AforeSensorEntityDescription(
        key="generation_value",
        translation_key="generation_value",
        name="Today Energy Generation",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda status: status.generationValue,
    ),
    AforeSensorEntityDescription(
        key="full_power_hours_day",
        translation_key="full_power_hours_day",
        name="Full Power Hours Day",
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda status: status.fullPowerHoursDay,
    ),
    AforeSensorEntityDescription(
        key="generation_total",
        translation_key="generation_total",
        name="Total Energy Generation",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda status: status.generationTotal,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Afore sensors based on a config entry."""
    coordinator: AforeDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    system = await coordinator.Afore.system()

    sensors = (
        AforeSensorEntity(
            coordinator=coordinator,
            description=description,
            system=system,
        )
        for description in SENSORS
    )

    async_add_entities(sensors)


class AforeSensorEntity(CoordinatorEntity[AforeDataUpdateCoordinator], SensorEntity):
    """Representation of a Afore sensor."""

    entity_description: AforeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        *,
        coordinator: AforeDataUpdateCoordinator,
        description: AforeSensorEntityDescription,
        system: System,
    ) -> None:
        """Initialize a Afore sensor."""
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        self.entity_id = (
            "sensor." + str(DOMAIN) + "_" + str(system.id) + "_" + description.key
        )
        self._attr_unique_id = f"{system.id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            configuration_url=f"https://hom.aforenergy.com/",
            identifiers={(DOMAIN, system.id)},
            manufacturer="Afore",
            model=system.id,
        )

    @property
    def native_value(self) -> int | float | None:
        """Return the state of the device."""
        return self.entity_description.value_fn(self.coordinator.data)
