"""Client unit tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from enterprise_carclub import (
    AuthError,
    Client,
    ClientError,
    LoginResult,
    NoReservationError,
)


def _mock_response(*, status: int = 200, json_data: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)
    resp.json = AsyncMock(return_value=json_data if json_data is not None else {})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


def _client(json_data: Any, *, status: int = 200) -> tuple[Client, MagicMock]:
    session = MagicMock()
    session.request = MagicMock(return_value=_mock_response(status=status, json_data=json_data))
    return Client(session), session


def test_headers_include_app_identity() -> None:
    client, session = _client({})
    assert client.token is None
    assert "Ehi-API-Key" in client._headers()
    assert client._headers()["Ehi-CSMA-Instance"] == "GB:EnterpriseCarClub"
    assert session.request is not None


@pytest.mark.asyncio
async def test_get_json_ok() -> None:
    client, session = _client({"ok": True})
    data = await client.async_get_json("/v1/ping")
    assert data == {"ok": True}
    session.request.assert_called_once()
    _, kwargs = session.request.call_args
    assert kwargs["headers"]["Ehi-API-Key"]


@pytest.mark.asyncio
async def test_get_json_auth_error() -> None:
    client, _ = _client({"error": True}, status=401)
    with pytest.raises(AuthError):
        await client.async_get_json("/v1/ping")


@pytest.mark.asyncio
async def test_get_json_client_error() -> None:
    client, _ = _client({"errors": [{"error_code": "B0RKED"}]}, status=500)
    with pytest.raises(ClientError):
        await client.async_get_json("/v1/ping")


@pytest.mark.asyncio
async def test_invalid_credentials_maps_to_auth_error() -> None:
    body = {"errors": [{"error_code": "INVALID_CREDENTIALS"}]}
    client, _ = _client(body, status=400)
    with pytest.raises(AuthError):
        await client.async_login("user", "wrong")


@pytest.mark.asyncio
async def test_login_stores_token() -> None:
    body = {
        "authorization_token": "tok123",
        "requested_user_name": "10379619",
        "profile": {"driver_name": "Test Driver"},
        "default_market_id": 8,
        "markets": [{"id": 8}],
    }
    client, session = _client(body)
    result = await client.async_login("10379619", "secret")
    assert isinstance(result, LoginResult)
    assert result.authorization_token == "tok123"
    assert result.market_id == 8
    assert client.token == "tok123"
    _, kwargs = session.request.call_args
    assert kwargs["json"] == {"username": "10379619", "password": "secret", "rememberMe": True}
    assert "Ehi-Auth-Token" not in kwargs["headers"]  # login itself is unauthenticated


@pytest.mark.asyncio
async def test_login_without_token_raises() -> None:
    client, _ = _client({"status": True})
    with pytest.raises(AuthError):
        await client.async_login("user", "pw")


@pytest.mark.asyncio
async def test_no_such_reservation() -> None:
    body = {"errors": [{"error_code": "8001", "error_message": "No Such Reservation"}]}
    client, _ = _client(body, status=400)
    with pytest.raises(NoReservationError):
        await client.async_get_current_reservation()


@pytest.mark.asyncio
async def test_current_and_future_empty() -> None:
    client, _ = _client({"future_reservations": []})
    assert await client.async_get_current_and_future() == []


@pytest.mark.asyncio
async def test_search_stacks_params() -> None:
    body = {"vehicle_stack_availability": [{"vehicle_stack": {"id": "1"}}]}
    client, session = _client(body)
    stacks = await client.async_search_stacks(
        latitude=53.4, longitude=-2.2, start_time=1795026600, end_time=1795041000, market_id=8
    )
    assert len(stacks) == 1
    _, kwargs = session.request.call_args
    assert kwargs["params"]["marketId"] == 8
    assert kwargs["params"]["startTime"] == 1795026600


@pytest.mark.asyncio
async def test_trip_estimates_shape() -> None:
    body = {"trip_estimates": [{"stack_id": "1"}]}
    client, _ = _client(body)
    estimates = await client.async_get_trip_estimates(["1"], start_time=1, end_time=2)
    assert estimates == [{"stack_id": "1"}]


@pytest.mark.asyncio
async def test_make_reservation_posts_expected_body() -> None:
    """Booking posts stack/window payload and returns the reservation."""
    body = {"reservation": {"id": "14566233", "status": "normal"}, "messages": []}
    client, session = _client(body)
    reservation = await client.async_make_reservation("54978", start_time=1795107600, end_time=1795122000)
    assert reservation["id"] == "14566233"
    _, kwargs = session.request.call_args
    assert kwargs["json"] == {
        "stack_id": "54978",
        "start_timestamp": 1795107600,
        "end_timestamp": 1795122000,
        "memo": "",
        "job_item": "",
        "optional_adjustment_ids": [],
    }


async def test_stack_timeslots_shape() -> None:
    """Timeslot lookup returns the slot list."""
    body = {"timeslots": [{"time": 1795026600, "available": True}]}
    client, session = _client(body)
    slots = await client.async_get_stack_timeslots("53237", start_time=1, end_time=2)
    assert slots == [{"time": 1795026600, "available": True}]
    args, _ = session.request.call_args
    assert args[0] == "GET"
    assert "timeslots/53237" in args[1]


async def test_make_reservation_rejects_bad_shape() -> None:
    """A missing reservation object raises ClientError."""
    client, _ = _client({"status": True})
    with pytest.raises(ClientError):
        await client.async_make_reservation("1", start_time=1, end_time=2)


async def test_logout_clears_token() -> None:
    client, _ = _client({"status": True})
    client.set_token("tok123")
    await client.async_logout()
    assert client.token is None
