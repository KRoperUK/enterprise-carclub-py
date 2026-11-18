# Reverse engineering notes — Enterprise Car Club API

Basis: Android APK `com.ehi.csma` v3.29.0 (vcode 2296, APKPure) decoded with
apktool, plus a Charles capture from the iOS app (v3.30.0) doing search,
estimate and login flows. No booking was completed during capture, so
`makeReservation` shapes come from the `MakeReservationRequest` DTO only.

## Transport

- Base URL: `https://www-carshare-msi.ecs.ehiaws.com/carshare-msi/`
- Static headers (Android): `Ehi-API-Key: lJYw…F/k` (see `client.py`
  `ANDROID_API_KEY`), `appPlatform: Android`,
  `appVersion: v3.29.0.2296-release`.
- Per-request: `Ehi-CSMA-Request-Id` (random UUID), `Em-Install-Id` (install
  UUID, empty on first run), `Accept-Language` (device locale).
- `Ehi-CSMA-Instance: GB:EnterpriseCarClub` — format is
  `countryId:brandId` (colon, 0x3A) from the app's bundled
  `assets/AVInstanceInfo.json`. GB programs use brand `EnterpriseCarClub`.
- Authed calls add `Ehi-Auth-Token: <authorization_token from login>`.
- Missing instance → `400 INVALID_CSMA_INSTANCE`; bad creds →
  `400 INVALID_CREDENTIALS`; no active reservation on
  `reservations/current` → `400` code `8001` "No Such Reservation"
  (mapped to `NoReservationError`, a normal empty state).

## Auth

- `POST api/autovera/login` body `{"username","password","rememberMe"}` —
  username is the member ID. Response includes `authorization_token`
  (32 chars, `Ehi-Auth-Token`), `login_token`, `profile` (driver name,
  timezone `Europe/London`, contract), `default_market_id` (GB = 8),
  `markets`, `access_level` permissions.
- `POST api/autovera/logout` → `{"status": true}`.

## Booking (captured live, iOS app)

- `POST api/autovera/reservations` body `{"stack_id", "start_timestamp",
  "end_timestamp", "memo", "job_item", "optional_adjustment_ids"}` (epoch
  seconds, 15-min increments). Response `{"reservation": {...}, "messages":
  [...]}` with `id`, `status` (`normal`), `start/end_timestamp`, `timezone`,
  `estimate` + `estimate_unformatted.currency_amount` (GBP value),
  `vehicle_stack` (id, description, lot, wayfinding, make/model, plate,
  battery_level/range for EVs), `trip_progress_status`.
- Cancel/modify/extend/return-early paths known from Retrofit but not yet
  captured live.

## Endpoints used by the client

| Method | Path | Notes |
| --- | --- | --- |
| GET | `api/autovera/reservations/currentAndFutureWithoutDriverMessages` | `{"future_reservations": [...]}` |
| GET | `api/autovera/reservations/current` | 8001 when nothing active |
| GET | `api/autovera/vehicleStacks` | query `latitude, longitude, marketId, startTime, endTime` (epoch seconds, 15-min increments) |
| POST | `api/autovera/vehicleStacks/tripEstimatesForVehicleStacks` | same window as query params, body `{"stack_ids": [...]}` |
| GET | `api/autovera/reservations/estimate` | query `stackId, startTime, endTime` → `estimated_cost` ("£17.99") |
| GET | `api/autovera/messages/driver` | inbox list |
| GET | `api/autovera/vehicleStacks/filters` | `amenities` + `vehicle_types` (56 GB types) |
| GET | `api/autovera/reservations/clientConfiguration` | feature flags |

Reference (no-auth) endpoints: `api/validCountries` (US/CA/GB/IE/FR/DE/ES),
`api/brandDetails?brandId=&countryCode=`, `api/countryContent`,
`api/contentMessaging`, `api/featureList`, all with `countryCode=GB`.

## Full Retrofit surface (from `CarShareRetrofitApi`)

Reservations: get/create/extend/cancel/return-early, lock/unlock doors,
virtual swipe in/out, trip start/end (incl. Bluetooth + maintenance),
question-answer, reservation messages, estimates, timeslots, stack
availability. Account: change password, username/password recovery, driver
messages, licence renewal, fuel receipts, customer feedback, contract
terms/job items, branch list/details, CloudBoxx bluetooth tokens.
