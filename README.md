# NVE HydAPI for Home Assistant

Custom component for Home Assistant that creates sensors from NVE HydAPI/Sildre time series.

Maintainer: [Ole Kristian Falstad](https://github.com/olekristianfalstad/)

The integration groups selected series into as few HydAPI POST requests as possible. Different stations and parameters share a request. Multiple resolutions or versions of the same parameter at one station require separate requests because HydAPI does not return the requested resolution in its response.

## Install

Requires Home Assistant **2025.3.0 or newer**.

1. Copy `custom_components/nve_hydapi` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.
3. Go to Settings -> Devices & services -> Add integration.
4. Search for `NVE HydAPI`.
5. Enter your HydAPI API key.
6. Start typing in the station search field and select an active station from the live suggestions.
7. Pick one or more desired parameters and resolutions for that station.

After updating through HACS, restart Home Assistant before opening the integration options. If old labels are still visible, refresh the Home Assistant page so the browser loads the updated translations.

## Change API key

Open Settings -> Devices & services, find the NVE HydAPI entry, and choose Reconfigure from its three-dot menu. Enter the new key and submit. If HydAPI rejects the stored key, Home Assistant will request reauthentication automatically.

The new key is validated before it replaces the old one. Cancelling or entering an invalid key leaves the existing configuration intact. Stations, selected series, sensor IDs and history are preserved.

## Tests

GitHub Actions runs the tests against Home Assistant 2025.3.0 and 2026.9.1 on Linux. With the matching Home Assistant package installed, run:

```sh
python -m unittest discover -s tests -v
```

## Notes

- You need an API key from NVE HydAPI. Create or find it at <https://hydapi.nve.no/Users>.
- The default update interval is 15 minutes.
- The minimum update interval in the UI is 10 minutes.
- The integration stores one sensor per selected HydAPI series.
- Data source and license: NVE HydAPI, NLOD.

## Examples

Start typing a station name or ID to filter the active station list. Examples include:

- Grunnfossen
- Torrisdal
- Bjornstad
- Hegra bru
- Samlop Funna

The list labels include both station name and station ID, for example `6.10.0`.

## Files

- `config_flow.py`: setup and options flow in the UI
- `api.py`: HydAPI client
- `coordinator.py`: one shared polling coordinator
- `sensor.py`: Home Assistant sensor entities
