from __future__ import annotations

import asyncio
import socket
import json
import datetime
import logging
from dataclasses import dataclass
from importlib import metadata
from typing import Any
from .models import Status, System

import async_timeout
from aiohttp.client import ClientError, ClientResponseError, ClientSession
from aiohttp.hdrs import METH_GET, METH_POST
from yarl import URL
import jwt
from datetime import datetime
from .const import DOMAIN

_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


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


@dataclass
class Afore:
    access_token: str | None

    request_timeout: float = 30.0
    session: ClientSession | None = None

    async def _request(
        self,
        uri: str,
        *,
        params: params,
        jsonData: jsonData,
        method: str = METH_POST,
        data: dict[str, Any] | None = None,
    ) -> str:
        url = URL("https://hom.aforenergy.com").join(URL(uri))
        if params is not None:
            url = url.with_query(params)

        self.access_token = "" # TODO add getting the token from the addon config

        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": f"Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
            "Authorization": "Bearer " + self.access_token,
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

        if self.session is None:
            self.session = ClientSession()
            self._close_session = True

        try:
            async with async_timeout.timeout(self.request_timeout):
                response = await self.session.request(
                    method,
                    url,
                    json=jsonData,
                    headers=headers,
                )
                response.raise_for_status()
        except asyncio.TimeoutError as exception:
            msg = "Timeout occurred while connecting to the Afore API"
            raise AforeConnectionError(msg) from exception
        except ClientResponseError as exception:
            if exception.status == 400:
                msg = "Afore has no status data available for this system"
                raise AforeNoDataError(msg) from exception
            if exception.status in [401, 403]:
                msg = "Authentication to the Afore API failed"
                raise AforeAuthenticationError(msg) from exception
            msg = "Error occurred while connecting to the Afore API"
            raise AforeError(msg) from exception
        except (ClientError, socket.gaierror) as exception:
            msg = "Error occurred while communicating with the Afore API"
            raise AforeConnectionError(msg) from exception

        return await response.text()

    async def status(self) -> Status:
        data = json.loads(
            await self._request(
                "/maintain-s/operating/station/search",
                method=METH_POST,
                jsonData={},
                params="order.direction=DESC&order.property=id&page=1&size=20",
            )
        )
        try:
            decoded_token = jwt.decode(
                self.access_token, options={"verify_signature": False}
            )
            date = datetime.fromtimestamp(decoded_token["exp"])
            data["data"][0]["expirationDate"] = date
            systemData = Status(**data["data"][0])
            systemData.expirationDate = date
        except jwt.ExpiredSignatureError:
            print("Token has expired")
        except jwt.InvalidTokenError:
            print("Invalid token")

        self.station_id = systemData.id
        return systemData

    async def system(self) -> System:
        data = json.loads(
            await self._request(
                "/maintain-s/operating/station/search",
                method=METH_POST,
                jsonData={},
                params="order.direction=DESC&order.property=id&page=1&size=20",
            )
        )
        try:                                                                   
            decoded_token = jwt.decode(                                        
                self.access_token, options={"verify_signature": False}         
            )                                                                  
            date = datetime.fromtimestamp(decoded_token["exp"])                
            data["data"][0]["expirationDate"] = date                           
            systemData = System(**data["data"][0])                             
            systemData.expirationDate = date                                               
        except jwt.ExpiredSignatureError:                                                  
            print("Token has expired")                                                     
        except jwt.InvalidTokenError:                                                      
            print("Invalid token")                                                         

        return systemData

    async def close(self) -> None:
        """Close open client session."""
        if self.session and self._close_session:
            await self.session.close()

    async def __aenter__(self) -> Afore:
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.close()
