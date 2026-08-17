from __future__ import annotations

import asyncio
import socket
import json
import logging
from typing import Any

from .models import Status, System

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN

import async_timeout
from aiohttp.client import ClientError, ClientResponseError, ClientSession
from aiohttp.hdrs import METH_GET, METH_POST
from yarl import URL
import jwt
from datetime import datetime, timezone

from homeassistant.components import persistent_notification

from .const import (
    DOMAIN,
    CONF_REFRESH_TOKEN,
    OAUTH_TOKEN_URL,
    OAUTH_CLIENT_ID,
    TOKEN_REFRESH_MARGIN,
    NOTIFY_REAUTH_ID,
)

_LOGGER = logging.getLogger(DOMAIN)

_BASE_URL = "https://hom.aforenergy.com"


class AforeNoDataError(Exception):
    pass


class AforeAuthenticationError(Exception):
    pass


class AforeConnectionError(Exception):
    pass


class AforeError(Exception):
    pass


class AforeOutputAuthenticationError(Exception):
    pass


class Afore:
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        request_timeout: float = 30.0,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize Afore."""
        self._hass = hass
        self._config_entry = config_entry
        self.request_timeout = request_timeout
        self.session = session
        self._close_session = session is None
        # Serialise token refreshes so concurrent requests don't refresh in parallel.
        self._refresh_lock = asyncio.Lock()

    # --- token helpers ----------------------------------------------------

    @staticmethod
    def _token_expiry(token: str | None) -> datetime | None:
        """Return the UTC expiry of a JWT, or None if it can't be read."""
        if not token:
            return None
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        except (jwt.InvalidTokenError, KeyError, ValueError):
            return None

    def _access_token_valid(self) -> bool:
        """True if we hold an access token that isn't about to expire."""
        expiry = self._token_expiry(self._config_entry.data.get(CONF_ACCESS_TOKEN))
        if expiry is None:
            return False
        return datetime.now(timezone.utc) < (expiry - TOKEN_REFRESH_MARGIN)

    async def _async_persist_tokens(self, access_token: str, refresh_token: str | None) -> None:
        """Save new tokens to the config entry (no reload; there is no update listener)."""
        data = {**self._config_entry.data, CONF_ACCESS_TOKEN: access_token}
        if refresh_token:
            data[CONF_REFRESH_TOKEN] = refresh_token

        # The config flow tries credentials against a stand-in rather than a
        # registered entry; there is nothing for HA to update in that case, so
        # hand the tokens back through its `data` mapping instead.
        if not isinstance(self._config_entry, ConfigEntry):
            self._config_entry.data = data
            return

        self._hass.config_entries.async_update_entry(self._config_entry, data=data)

    async def _async_refresh_token(self) -> None:
        """Exchange the stored refresh token for a fresh access token."""
        refresh_token = self._config_entry.data.get(CONF_REFRESH_TOKEN)
        if not refresh_token:
            raise AforeAuthenticationError("No refresh token stored")

        async with self._refresh_lock:
            # Another coroutine may have refreshed while we waited for the lock.
            if self._access_token_valid():
                return

            if self.session is None:
                self.session = ClientSession()
                self._close_session = True

            url = URL(_BASE_URL).join(URL(OAUTH_TOKEN_URL))
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
                "Origin": _BASE_URL,
                "Referer": f"{_BASE_URL}/login",
            }
            # This portal authenticates the client with a client_id field only.
            body = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": OAUTH_CLIENT_ID,
            }

            try:
                async with async_timeout.timeout(self.request_timeout):
                    response = await self.session.request(
                        METH_POST, url, headers=headers, data=body
                    )
                    text = await response.text()
                    response.raise_for_status()
            except asyncio.TimeoutError as exc:
                raise AforeConnectionError("Timeout while refreshing Afore token") from exc
            except ClientResponseError as exc:
                # 400/401 here means the refresh token is dead -> needs manual re-login.
                _LOGGER.error("Afore token refresh rejected (%s): %s", exc.status, text)
                self._notify_reauth_required()
                raise AforeAuthenticationError("Refresh token rejected") from exc
            except (ClientError, socket.gaierror) as exc:
                raise AforeConnectionError("Error refreshing Afore token") from exc

            try:
                payload = json.loads(text)
                new_access = payload["access_token"]
            except (ValueError, KeyError) as exc:
                raise AforeAuthenticationError("Unexpected token response") from exc

            # Spring may rotate the refresh token; keep the new one if present.
            new_refresh = payload.get("refresh_token") or refresh_token
            await self._async_persist_tokens(new_access, new_refresh)
            # A successful refresh clears any prior "re-login required" alert.
            persistent_notification.async_dismiss(self._hass, NOTIFY_REAUTH_ID)
            _LOGGER.debug(
                "Afore access token refreshed, new expiry %s",
                self._token_expiry(new_access),
            )

    def _notify_reauth_required(self) -> None:
        """Raise a loud, persistent alert that a manual portal re-login is needed."""
        persistent_notification.async_create(
            self._hass,
            (
                "Home Assistant can no longer refresh the Afore access token - the "
                "refresh token has expired (this happens roughly every 6 months). "
                "Solar production data will stop updating until you log in at "
                "https://hom.aforenergy.com and paste a fresh access token and "
                "refresh token into the Afore integration (Settings > Devices & "
                "Services > Afore > Reconfigure)."
            ),
            title="Afore: re-login required",
            notification_id=NOTIFY_REAUTH_ID,
        )

    async def _async_ensure_token(self) -> None:
        """Refresh proactively if the access token is missing or about to expire."""
        if not self._access_token_valid():
            await self._async_refresh_token()

    # --- request ----------------------------------------------------------

    async def _request(
        self,
        uri: str,
        *,
        params: Any,
        jsonData: Any,
        method: str = METH_POST,
        data: dict[str, Any] | None = None,
    ) -> str:
        # Refresh before the call if needed (cheap: just decodes a JWT locally).
        await self._async_ensure_token()

        url = URL(_BASE_URL).join(URL(uri))
        if params is not None:
            url = url.with_query(params)

        if self.session is None:
            self.session = ClientSession()
            self._close_session = True

        # One retry: if the token is rejected mid-flight, refresh once and retry.
        for attempt in (1, 2):
            access_token = self._config_entry.data.get(CONF_ACCESS_TOKEN)
            headers = {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
                "Authorization": "Bearer " + (access_token or ""),
                "Accept-Language": "en-US,en;q=0.7,pl;q=0.3",
                "Content-Type": "application/json;charset=UTF-8",
                "Accept-Encoding": "gzip, deflate",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "DNT": "1",
                "Sec-GPC": "1",
                "Connection": "keep-alive",
                "Referer": "https://hom.aforenergy.com/plant/infos/data",
            }

            try:
                async with async_timeout.timeout(self.request_timeout):
                    response = await self.session.request(
                        method, url, json=jsonData, headers=headers
                    )
                    response.raise_for_status()
                return await response.text()
            except asyncio.TimeoutError as exception:
                raise AforeConnectionError(
                    "Timeout occurred while connecting to the Afore API"
                ) from exception
            except ClientResponseError as exception:
                if exception.status == 400:
                    raise AforeNoDataError(
                        "Afore has no status data available for this system"
                    ) from exception
                if exception.status in (401, 403):
                    # Token expired/invalid: refresh once and retry, else give up.
                    if attempt == 1:
                        _LOGGER.debug("Afore API returned %s, refreshing token", exception.status)
                        await self._async_refresh_token()
                        continue
                    raise AforeAuthenticationError(
                        "Authentication to the Afore API failed"
                    ) from exception
                raise AforeError(
                    "Error occurred while connecting to the Afore API"
                ) from exception
            except (ClientError, socket.gaierror) as exception:
                raise AforeConnectionError(
                    "Error occurred while communicating with the Afore API"
                ) from exception

    async def _station(self) -> dict[str, Any]:
        """Fetch the raw station record, stamped with the access-token expiry."""
        data = json.loads(
            await self._request(
                "/maintain-s/operating/station/search",
                method=METH_POST,
                jsonData={},
                params="order.direction=DESC&order.property=id&page=1&size=20",
            )
        )
        if not data.get("data"):
            raise AforeNoDataError("Afore returned no stations for this account")

        station = data["data"][0]
        station["expirationDate"] = self._token_expiry(
            self._config_entry.data.get(CONF_ACCESS_TOKEN)
        )
        return station

    async def status(self) -> Status:
        status = Status(**await self._station())
        self.station_id = status.id
        return status

    async def system(self) -> System:
        return System(**await self._station())

    async def close(self) -> None:
        """Close open client session."""
        if self.session and self._close_session:
            await self.session.close()

    async def __aenter__(self) -> Afore:
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.close()
