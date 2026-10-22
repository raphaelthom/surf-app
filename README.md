# 🏄 Surf Forecast

A small Streamlit app that shows the 7-day surf forecast for five spots:
Lisbon, San Diego, Siargao, Lombok and Taghazout.

For the selected spot it charts:

- wave height, swell wave height and swell wave period
  ([Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api))
- wind speed (knots) and wind direction
  ([Open-Meteo Weather API](https://open-meteo.com/en/docs))

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
