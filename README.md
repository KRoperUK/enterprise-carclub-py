# enterprise-carclub-py

Unofficial async Python client for the **Enterprise Car Club / CarShare** API
(`com.ehi.csma`, EHI AWS backend). Powers the
[enterprise-carclub-hass](https://github.com/KRoperUK/enterprise-carclub-hass)
Home Assistant integration. No Home Assistant dependency — any asyncio app can
use it.

> Unofficial library, not affiliated with or endorsed by Enterprise Holdings /
> EAN Services. Use at your own risk.

## API basis

Reverse-engineered from the Android app v3.29.0 (`com.ehi.csma`):

- Base URL: `https://www-carshare-msi.ecs.ehiaws.com/carshare-msi/`
- Auth: `POST api/autovera/login` → session via `Ehi-Auth-Token` header;
  every request also sends `Ehi-API-Key`, `Ehi-CSMA-Instance`,
  `Ehi-CSMA-Request-Id`, `Em-Install-Id`, `appPlatform`/`appVersion`.
- Core surface: `api/autovera/reservations/current`,
  `api/autovera/reservations/{id}`, vehicle-stack search
  (`api/autovera/vehicleStacks*`), make/extend/cancel reservation,
  trip start/end (incl. Bluetooth), lock/unlock doors, driver messages.
- Full endpoint map lives in `docs/reverse-engineering.md` (to be added with
  the first implementation PR).

## Install

```bash
pip install enterprise-carclub
```

## Use

```python
import asyncio
import time

import aiohttp
from enterprise_carclub import Client

async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = Client(session)  # defaults to the production base URL
        result = await client.async_login("member-id", "password")
        print(result.member_id, result.market_id)
        futures = await client.async_get_current_and_future()
        print(len(futures), "upcoming reservations")
        start = (int(time.time()) // 900 + 8) * 900
        stacks = await client.async_search_stacks(
            latitude=53.47, longitude=-2.28,
            start_time=start, end_time=start + 4 * 3600, market_id=8,
        )
        print(len(stacks), "stacks nearby")

asyncio.run(main())
```

Implemented against the live API: `login()` (member ID + password →
`Ehi-Auth-Token`), reservations (current, by id, future list), vehicle search
with 15-minute timeslots, batch + single trip estimates, per-stack future
timeslots, booking creation, driver messages, filters, client configuration,
branch details and contract terms. HTTP 401/403 and `INVALID_CREDENTIALS`
map to `AuthError`; code `8001` ("No Such Reservation") maps to
`NoReservationError`; everything else to `ClientError`.

## Develop

```bash
pip install -e ".[dev]"
pytest
ruff check src tests && ruff format --check src tests
mypy
```

Releases use release-please with conventional commits (`feat:`, `fix:`) —
push to `main`, merge the release PR, publish to PyPI via Trusted Publishing.

## License

MIT.
