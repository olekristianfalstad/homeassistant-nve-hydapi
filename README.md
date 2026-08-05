# NVE HydAPI for Home Assistant

Custom component for Home Assistant that creates sensors from NVE HydAPI/Sildre time series.

Maintainer: [Ole Kristian Falstad](https://github.com/olekristianfalstad/)

The integration uses one coordinated HydAPI POST request for all selected series on each update. This is kinder to HydAPI than many separate REST sensors or Node-RED calls.

## Install

1. Copy `custom_components/nve_hydapi` into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.
3. Go to Settings -> Devices & services -> Add integration.
4. Search for `NVE HydAPI`.
5. Enter your HydAPI API key.
6. Select an active station from the searchable station list.
7. Pick one or more desired parameters and resolutions for that station.

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
