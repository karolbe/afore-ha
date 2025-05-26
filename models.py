"""Asynchronous client for the Afore API."""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, validator


class Status(BaseModel):
    """Object holding the latest status information and live output data."""

    id: int | None
    name: str | None
    expirationDate: datetime | None
    locationAddress: str | None
    createdDate: datetime | None
    installedCapacity: float | None
    startOperatingTime: datetime | None
    lastUpdateTime: datetime | None
    system: str | None
    incomeMonth: float | None
    generationTotal: float | None
    generationValue: float | None
    generationMonth: float | None
    generationYear: float | None
    generationPower: float | None
    system: str | None
    stationType: str | None
    type: str | None
    consumerWarningStatus: str | None
    temperature: float | None
    fullPowerHoursDay: float | None
    locationLat: float | None
    locationLng: float | None
    operating: bool | None
    networkStatus: str | None
    installationTiltAngle: str | None
    installationAzimuthAngle: str | None

    @validator("createdDate", "startOperatingTime", "lastUpdateTime", pre=True)
    @classmethod
    def preparse_date(cls, value: str) -> str:
        return datetime.utcfromtimestamp(float(value))


class System(BaseModel):
    """Object holding the latest system information."""

    id: int | None
    name: str | None
    expirationDate: datetime | None
    locationAddress: str | None
    createdDate: datetime | None
    installedCapacity: float | None
    startOperatingTime: datetime | None
    lastUpdateTime: datetime | None
    system: str | None
    incomeMonth: float | None
    generationTotal: float | None
    generationValue: float | None
    generationMonth: float | None
    generationYear: float | None
    generationPower: float | None
    system: str | None
    stationType: str | None
    type: str | None
    consumerWarningStatus: str | None
    temperature: float | None
    fullPowerHoursDay: float | None
    locationLat: float | None
    locationLng: float | None
    operating: bool | None
    installationTiltAngle: str | None
    installationAzimuthAngle: str | None

    @validator("createdDate", "startOperatingTime", "lastUpdateTime", pre=True)
    @classmethod
    def preparse_date(cls, value: str) -> str:
        return str(value)
