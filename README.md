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
6. Search for a station by name or station ID.
7. Pick the desired parameter and resolution.

## Notes

- You need an API key from NVE HydAPI. Create or find it at <https://hydapi.nve.no/Users>.
- The default update interval is 15 minutes.
- The minimum update interval in the UI is 10 minutes.
- The integration stores one sensor per selected HydAPI series.
- Data source and license: NVE HydAPI, NLOD.

## Examples

Station searches can be names like:

- Grunnfossen
- Torrisdal
- Bjornstad
- Hegra bru
- Samlop Funna

Station IDs also work directly, for example `6.10.0`.

## Files

- `config_flow.py`: setup and options flow in the UI
- `api.py`: HydAPI client
- `coordinator.py`: one shared polling coordinator
- `sensor.py`: Home Assistant sensor entities
