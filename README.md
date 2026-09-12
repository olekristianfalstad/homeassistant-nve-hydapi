# NVE HydAPI for Home Assistant

Custom component for Home Assistant that creates sensors from NVE HydAPI/Sildre time series.

Maintainer: [Ole Kristian Falstad](https://github.com/olekristianfalstad/)

The integration groups selected series into as few HydAPI POST requests as possible. Different stations and parameters share a request. Multiple resolutions or versions of the same parameter at one station require separate requests because HydAPI does not return the requested resolution in its response.

## Install With HACS

Requires Home Assistant **2025.3.0 or newer**.

1. Open HACS and choose **Custom repositories** from the three-dot menu.
2. Add `https://github.com/olekristianfalstad/homeassistant-nve-hydapi` with category **Integration**.
3. Find **NVE HydAPI** in HACS and download the latest stable version.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & services -> Add integration**, search for **NVE HydAPI** and enter your API key.
6. Type a station name or ID and select an active station from the suggestions.
7. Select one or more measurement series. The option to add another station is off by default.

This is an independent community integration maintained by Ole Kristian Falstad, not an official NVE product. NVE provides the public API and measurement data. Adding this custom repository does not submit it to the HACS default store.

For manual installation, copy `custom_components/nve_hydapi` to your Home Assistant `config/custom_components/` directory, restart and continue from step 5.

After updating through HACS, restart Home Assistant before opening the integration options. If old labels are still visible, refresh the Home Assistant page so the browser loads the updated translations.

## Change API key

Open Settings -> Devices & services, find the NVE HydAPI entry, and choose Reconfigure from its three-dot menu. Enter the new key and submit. If HydAPI rejects the stored key, Home Assistant will request reauthentication automatically.

The new key is validated before it replaces the old one. Cancelling or entering an invalid key leaves the existing configuration intact. Stations, selected series, sensor IDs and history are preserved.

## Tests

GitHub Actions runs the tests against Home Assistant 2025.3.0 and 2026.9.1 on Linux. With the matching Home Assistant package installed, run:

```sh
python -m unittest discover -s tests -v
```

The release workflow also runs HACS and hassfest validation. The HACS central-brands check is excluded because this is a custom repository with bundled assets; no central brand submission is implied.

A separate Chromium check runs an isolated real Home Assistant 2026.9.1 frontend in Norwegian Bokmal, on desktop and mobile viewports, both after a fresh install and an upgrade from 0.1.12. Screenshots and server logs are uploaded to the workflow's `norwegian-ui` artifact. Only the HydAPI responses are simulated; no personal API key or production Home Assistant is used. This check does not cover every browser or custom theme.

## Remove Measurement Series

Open the integration options, choose **Remove measurement series**, select a series and review the confirmation. Nothing is removed until the confirmation checkbox is selected and submitted. Leaving it unchecked returns to the options screen.

The measurement and its diagnostic status sensor are removed from the entity registry. After the last series at a station is removed, this integration is detached from the station device. Devices shared with another integration remain. On upgrade, orphaned registry entries from series removed by earlier releases are also cleaned up.

The integration never calls a recorder purge. Home Assistant retention rules still apply, and removing/re-adding a sensor does not guarantee its old history will reconnect. Dashboards and automations referencing a removed entity need updating. Back up Home Assistant before making substantial configuration changes.

## Data Status And Precision

Each measurement has a diagnostic **data status** sensor with the translated states **Current**, **Stale measurement**, **Missing measurement** and **Invalid observation time**. Its attributes include measurement time, age in minutes and NVE's original quality/correction codes when supplied. Those codes are passed through unchanged, not interpreted as a guarantee of quality.

Freshness is an integration heuristic, not an NVE service-level promise: instantaneous and hourly values are stale after **3 hours**, daily values after **72 hours**. A timestamp more than 5 minutes in the future is invalid. Status and age update on each scheduled poll, not every second. A stale numeric measurement remains visible, with its stale status; missing or non-finite values become unknown. On API failure both the measurement and diagnostic status become unavailable. `last_successful_update` is the time of the last successful observation fetch, not the measurement time.

Water/air temperatures (NVE parameters 1003/17) are rounded to **one decimal** before being stored. Water level, discharge and other parameters use **two decimals**. This is a presentation/storage choice, not a claim about measurement accuracy. Existing history is not rewritten; Home Assistant may calculate aggregate statistics with additional decimals.

## API Usage And Troubleshooting

Active station metadata is cached in memory for **four hours**, matching NVE's approximate station metadata update interval. Series are fetched only for the station you select. The station cache and rate-limit state are shared by flows and polling using the same key, and are reset by a Home Assistant restart.

After HTTP 429, new requests are suppressed until the latest valid `Retry-After` or `x-rate-limit-reset` deadline; if neither header is usable the integration waits ten minutes. Polling resumes at the first scheduled poll after that deadline. Other API keys have separate limits. No requests are made just to count down a wait.

Timeout, invalid response and rate-limit errors keep the form open so you can retry. A bad response does not overwrite saved configuration. For diagnostics, download the integration diagnostics from Home Assistant; API keys are redacted. Do not publish unredacted Home Assistant storage files.

Reference: [NVE HydAPI documentation](https://hydapi.nve.no/UserDocumentation/).

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
