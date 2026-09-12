# Changelog

## 0.1.13

- Handle timeouts, invalid JSON and malformed responses with translated, retryable form errors.
- Confirm series removal before saving, remove its measurement/status registry entries and detach empty station devices without affecting other integrations.
- Reconcile orphaned HydAPI registry entries left by earlier versions; retained sensor IDs, names and disabled preferences remain unchanged.
- Add one diagnostic data-status sensor per series, with observation age, measurement timestamp and original NVE quality/correction codes in attributes.
- Distinguish API connectivity from freshness: use a documented age heuristic, never treat missing values, NaN or invalid timestamps as current measurements.
- Cache active stations in memory for four hours and share rate-limit cooldowns across setup, options and polling for the same API key.
- Respect Retry-After and NVE reset headers without blocking the UI or repeatedly calling the API during the wait.
- Translate resolution labels and sensor names; round temperatures to one decimal and other measurements to two.
- Expand regression tests, add HACS/hassfest validation and real Norwegian frontend checks for fresh installation and upgrade from 0.1.12.
- Document HACS installation, removal consequences, freshness rules and precision.

Restart Home Assistant after updating. Registry entries for previously removed series are cleaned up during setup. No recorder/history purge is requested by this integration. Existing active measurement sensor IDs are preserved; additional diagnostic sensors are created.

## 0.1.12

- Prevent measurements from being assigned to the wrong resolution by separating ambiguous station/parameter combinations into independent batches.
- Match responses by station, parameter and requested version, independent of response order; reject duplicate responses.
- Require Home Assistant 2025.3.0 or newer for the coordinator and credential-update APIs.
- Add automatic reauthentication when HydAPI rejects the stored API key, plus manual key replacement through Reconfigure.
- Validate replacement keys before saving; preserve stations, series, sensor IDs and history.
- Add regression tests against the minimum supported and current Home Assistant versions.

Restart Home Assistant after updating. Multiple resolutions or versions of the same parameter at one station now require separate requests; other series remain batched.

## 0.1.11

- Keep the full station name, station ID, and municipality visible after selecting a live station suggestion.
- Add a translated title to the options dialog and retain the setup summary and interval guidance introduced in 0.1.10.
- Document the required Home Assistant restart and browser refresh after updating translations.

## 0.1.10

- Replace the station dropdown with an editable search field that filters active stations and shows live suggestions.
- Add the current station and measurement-series counts to the options dialog.
- Add clear update-interval guidance and translated measurement-series actions to the options dialog.

## 0.1.9

- Load active HydAPI stations after API key validation and show them in a searchable station selector.
- Fetch all available series only after a station has been selected.
- Use `nb.json` for Norwegian Bokmal translations and align Norwegian and English translation keys.
- Add a genuine 512x512 `icon@2x.png` generated from NVE's official SVG artwork.

## 0.1.8

- Use the official positive and negative NVE main logos for light and dark Home Assistant themes.

## 0.1.7

- Replace the legacy NVE brand artwork with NVE's current official logo.

## 0.1.6

- Resize brand assets to valid Home Assistant dimensions so the icon can be shown in Home Assistant and HACS.

## 0.1.5

- Round sensor states to two decimals before Home Assistant stores them in history.

## 0.1.4

- Show NVE as the manufacturer for HydAPI station devices in Home Assistant.

## 0.1.3

- Allow selecting multiple HydAPI series from the same station search.
- Do not select "add another series" by default.
- Add a confirmation step so an unintended "add another" choice can still be saved.
- Prevent duplicate series when editing integration options.

## 0.1.2

- Add repository-level `brand/icon.png` and `brand/logo.png` so HACS can show the integration logo in repository listings.

## 0.1.1

- Add HACS-ready Home Assistant custom integration structure.
- Add UI setup flow with HydAPI API key, scan interval, station search, and series selection.
- Fetch all selected HydAPI observations in one coordinated API request.
- Add Norwegian and English UI translations.
- Add NVE HydAPI logo assets.
