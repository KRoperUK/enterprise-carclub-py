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
import aiohttp
from enterprise_carclub import Client, DEFAULT_BASE_URL

async with aiohttp.ClientSession() as session:
    client = Client(session, base_url=DEFAULT_BASE_URL)
    data = await client.async_get_json("api/autovera/reservations/current")
```

Auth (login + token) helpers land with the first `feat:` commit; the skeleton
already maps HTTP 401/403 to `AuthError` and other failures to `ClientError`.

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
