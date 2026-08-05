# Changelog

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
