"""Async client for the Enterprise Car Club / CarShare API.

Reverse-engineered from the Android app (``com.ehi.csma`` v3.29.0); see
``docs/reverse-engineering.md`` for the endpoint map. The iOS app speaks the
same API with its own key/platform values.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientSession

from .exceptions import AuthError, ClientError, NoReservationError

_LOGGER = logging.getLogger(__name__)

#: Production API root observed in the Android app (com.ehi.csma v3.29.0).
DEFAULT_BASE_URL = "https://www-carshare-msi.ecs.ehiaws.com/carshare-msi"

#: Static app key sent as ``Ehi-API-Key`` by the Android app.
ANDROID_API_KEY = "lJYwDM2diKuwPPnCK+tq4U84xgNtHuwCmoYs19RBF/k"
APP_PLATFORM = "Android"
APP_VERSION = "v3.29.0.2296-release"

#: ``Ehi-CSMA-Instance`` for United Kingdom / Enterprise Car Club
#: (``countryId:brandId`` from the app's bundled ``AVInstanceInfo.json``).
INSTANCE_GB_ENTERPRISE = "GB:EnterpriseCarClub"


@dataclass(frozen=True)
class LoginResult:
    """Outcome of a successful ``login()`` call."""

    authorization_token: str
    member_id: str
    driver_name: str | None
    market_id: int | None


def _error_code(payload: Any) -> str | None:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                code = first.get("error_code")
                return str(code) if code is not None else None
    return None


class Client:
    """Async client.

    Parameters
    ----------
    session:
        Shared ``aiohttp.ClientSession`` (HA integrations should pass the one from
        ``async_get_clientsession(hass)``).
    base_url:
        API root without trailing slash.
    token:
        ``Ehi-Auth-Token`` from a previous login; ``login()`` refreshes it.
    instance:
        ``Ehi-CSMA-Instance`` header (``countryId:brandId``).
    install_id:
        ``Em-Install-Id`` header; generated once per client by default.
    language:
        ``Accept-Language`` header.
    """

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        instance: str = INSTANCE_GB_ENTERPRISE,
        install_id: str | None = None,
        language: str = "en_GB",
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._instance = instance
        self._install_id = install_id or str(uuid.uuid4())
        self._language = language

    @property
    def token(self) -> str | None:
        """Current auth token, if logged in."""
        return self._token

    def set_token(self, token: str | None) -> None:
        """Update the auth token after a refresh."""
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Ehi-API-Key": ANDROID_API_KEY,
            "appPlatform": APP_PLATFORM,
            "appVersion": APP_VERSION,
            "Em-Install-Id": self._install_id,
            "Accept-Language": self._language,
            "Ehi-CSMA-Request-Id": str(uuid.uuid4()),
            "Ehi-CSMA-Instance": self._instance,
        }
        if self._token:
            headers["Ehi-Auth-Token"] = self._token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            async with self._session.request(
                method, url, headers=self._headers(), params=params, json=json_body
            ) as resp:
                data: Any = None
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                if resp.status in (401, 403):
                    raise AuthError(f"Unauthorized ({resp.status})", code=str(resp.status))
                if resp.status >= 400:
                    code = _error_code(data)
                    if code in ("INVALID_CREDENTIALS", "MISSING_AUTH_TOKEN"):
                        raise AuthError(f"Authentication failed ({code})", code=code)
                    if code == "8001" or (isinstance(data, dict) and "No Such Reservation" in str(data.get("errors"))):
                        raise NoReservationError("No such reservation", code=code or "8001")
                    detail = str(data)[:200] if data is not None else f"HTTP {resp.status}"
                    raise ClientError(f"HTTP {resp.status}: {detail}", code=code or str(resp.status))
        except (AuthError, ClientError):
            raise
        except Exception as err:
            raise ClientError(f"Request failed: {err}") from err
        return data

    async def async_get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET JSON from ``path``; returns the decoded object (dict expected)."""
        data = await self._request("GET", path, params=params)
        if not isinstance(data, dict):
            raise ClientError("Expected a JSON object response")
        return data

    async def async_login(self, username: str, password: str) -> LoginResult:
        """Log in with member ID (username) + password.

        Stores the ``authorization_token`` on the client and returns it with
        profile details.
        """
        data = await self._request(
            "POST",
            "api/autovera/login",
            json_body={"username": username, "password": password, "rememberMe": True},
        )
        if not isinstance(data, dict) or not data.get("authorization_token"):
            raise AuthError("Login did not return an authorization token")
        token = str(data["authorization_token"])
        self._token = token
        profile = data.get("profile") or {}
        markets = data.get("markets") or []
        market_id = data.get("default_market_id")
        if market_id is None and markets:
            first = markets[0]
            market_id = first.get("id") if isinstance(first, dict) else None
        return LoginResult(
            authorization_token=token,
            member_id=str(data.get("requested_user_name") or username),
            driver_name=profile.get("driver_name") if isinstance(profile, dict) else None,
            market_id=int(market_id) if market_id is not None else None,
        )

    async def async_logout(self) -> None:
        """Log out; clears the stored token whatever the server says."""
        try:
            await self._request("POST", "api/autovera/logout")
        finally:
            self._token = None

    async def async_get_current_and_future(self) -> list[dict[str, Any]]:
        """Return future reservations (empty list when none booked)."""
        data = await self.async_get_json("api/autovera/reservations/currentAndFutureWithoutDriverMessages")
        reservations = data.get("future_reservations")
        if not isinstance(reservations, list):
            return []
        return [item for item in reservations if isinstance(item, dict)]

    async def async_get_current_reservation(self) -> dict[str, Any]:
        """Return the active reservation; raises NoReservationError when none."""
        data = await self.async_get_json("api/autovera/reservations/current")
        return data

    async def async_search_stacks(
        self,
        *,
        latitude: float,
        longitude: float,
        start_time: int,
        end_time: int,
        market_id: int,
    ) -> list[dict[str, Any]]:
        """Search vehicle stacks near a point for an epoch-seconds window."""
        data = await self._request(
            "GET",
            "api/autovera/vehicleStacks",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "marketId": market_id,
                "startTime": start_time,
                "endTime": end_time,
            },
        )
        if not isinstance(data, dict):
            raise ClientError("Unexpected vehicle search response")
        stacks = data.get("vehicle_stack_availability")
        if not isinstance(stacks, list):
            raise ClientError("Unexpected vehicle search response")
        return [item for item in stacks if isinstance(item, dict)]

    async def async_get_trip_estimates(
        self, stack_ids: list[str], *, start_time: int, end_time: int
    ) -> list[dict[str, Any]]:
        """Batch trip estimates for stack IDs (epoch-seconds window)."""
        data = await self._request(
            "POST",
            "api/autovera/vehicleStacks/tripEstimatesForVehicleStacks",
            params={"startTime": start_time, "endTime": end_time},
            json_body={"stack_ids": stack_ids},
        )
        if not isinstance(data, dict):
            raise ClientError("Unexpected trip estimates response")
        estimates = data.get("trip_estimates")
        if not isinstance(estimates, list):
            raise ClientError("Unexpected trip estimates response")
        return [item for item in estimates if isinstance(item, dict)]

    async def async_get_estimate(self, stack_id: str, *, start_time: int, end_time: int) -> dict[str, Any]:
        """Priced estimate for one stack and window."""
        return await self.async_get_json(
            "api/autovera/reservations/estimate",
            params={"stackId": stack_id, "startTime": start_time, "endTime": end_time},
        )

    async def async_get_stack_timeslots(self, stack_id: str, *, start_time: int, end_time: int) -> list[dict[str, Any]]:
        """Availability timeslots for one stack in an epoch-seconds window."""
        data = await self._request(
            "GET",
            f"api/autovera/vehicleStackAvailability/timeslots/{stack_id}",
            params={"stackId": stack_id, "startTime": start_time, "endTime": end_time},
        )
        if isinstance(data, dict):
            slots = data.get("timeslots")
        elif isinstance(data, list):
            slots = data
        else:
            slots = None
        if not isinstance(slots, list):
            raise ClientError("Unexpected timeslots response")
        return [item for item in slots if isinstance(item, dict)]

    async def async_get_reservation(self, reservation_id: str) -> dict[str, Any]:
        """Full details for one reservation; raises NoReservationError when unknown."""
        return await self.async_get_json(f"api/autovera/reservations/{reservation_id}")

    async def async_get_stack_availability(self, stack_id: str, *, start_time: int, end_time: int) -> dict[str, Any]:
        """Availability summary for one stack in an epoch-seconds window."""
        return await self.async_get_json(
            f"api/autovera/vehicleStackAvailability/{stack_id}",
            params={"stackId": stack_id, "startTime": start_time, "endTime": end_time},
        )

    async def async_get_branch_details(self, people_soft_id: str) -> dict[str, Any]:
        """Branch details for a peopleSoftId (as seen on reservations)."""
        return await self.async_get_json("api/branch", params={"peopleSoftId": people_soft_id})

    async def async_get_contract_terms(self) -> dict[str, Any]:
        """Contract terms and job items for the current program."""
        return await self.async_get_json("api/autovera/contractTerms")

    async def async_make_reservation(
        self,
        stack_id: str,
        *,
        start_time: int,
        end_time: int,
        memo: str = "",
        job_item: str = "",
        optional_adjustment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a real reservation.

        Times are epoch seconds in 15-minute increments. Returns the created
        ``reservation`` object (id, status, estimate, vehicle stack).
        """
        data = await self._request(
            "POST",
            "api/autovera/reservations",
            json_body={
                "stack_id": stack_id,
                "start_timestamp": start_time,
                "end_timestamp": end_time,
                "memo": memo,
                "job_item": job_item,
                "optional_adjustment_ids": optional_adjustment_ids or [],
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("reservation"), dict):
            raise ClientError("Unexpected reservation response")
        reservation = data["reservation"]
        assert isinstance(reservation, dict)
        return reservation

    async def async_get_driver_messages(self) -> list[dict[str, Any]]:
        """Driver inbox messages."""
        data = await self.async_get_json("api/autovera/messages/driver")
        messages = data.get("messages")
        if not isinstance(messages, list):
            return []
        return [item for item in messages if isinstance(item, dict)]

    async def async_get_vehicle_filters(self) -> dict[str, Any]:
        """Amenities and vehicle types for search filters."""
        return await self.async_get_json("api/autovera/vehicleStacks/filters")

    async def async_get_client_configuration(self) -> dict[str, Any]:
        """Server-driven client configuration flags."""
        return await self.async_get_json("api/autovera/reservations/clientConfiguration")
