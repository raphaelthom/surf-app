# 🏄 Surf Forecast

A small Streamlit app that shows the 7-day surf forecast for five spots:
Lisbon, San Diego, Siargao, Lombok and Taghazout.

For the selected spot it charts:

- wave height, swell wave height and swell wave period
  ([Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api))
- wind speed (knots) and wind direction
  ([Open-Meteo Weather API](https://open-meteo.com/en/docs))

**Live app:** https://surf-app-rt.streamlit.app/

No API key is needed. Forecasts are cached for one hour.

## Run it

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Notes

- The marine API only has data over the ocean, so the coordinates in `SPOTS`
  point slightly offshore. The API snaps them to its own grid (a few km wide),
  so the forecast is regional, not exact for one break.
- Wind direction is in degrees, where 0 means wind coming *from* the north.

## Development: screenshots of the app

To check how the app looks without opening a browser by hand (also used when Claude
helps with the layout), install the development extras once and run the script:

```
pip install -r requirements-dev.txt
python tools/screenshot.py                 # every tab, first spot, desktop size
python tools/screenshot.py --spot Lombok   # another spot
python tools/screenshot.py --phone         # phone-sized window
```

It starts the app, opens it in your installed Google Chrome in the background
and saves one PNG per tab into `screenshots/` (not committed to Git).
`requirements-dev.txt` is separate from `requirements.txt`, so the deployed app
doesn't install these extras.

## Tests

The surf logic (compass labels, rating, best time, next tide) lives in `surf_logic.py`
and is covered by tests:

```
pip install -r requirements-dev.txt   # once
python -m pytest
```
