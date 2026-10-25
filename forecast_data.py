"""Loading the forecast data from Open-Meteo (the free weather and marine APIs).

These functions used to live in app.py. They are in their own file now, because both
the surf page (app.py) and the windsurf page (windsurf_view.py) need the same data.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import streamlit as st

# The free API sometimes stalls for a request. A session with a retry rule asks again (up to 2 more times,
# with a short pause in between) instead of failing right away. If it still fails, the error is caught below.
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])))

# st.cache_data remembers the result for each input (lat, lon), so picking
# the same spot again doesn't call the API again. ttl=3600: forget after 1 hour.
@st.cache_data(ttl=3600)

def get_marine_data(lat, lon):
    response = session.get("https://marine-api.open-meteo.com/v1/marine", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wave_height,swell_wave_height,swell_wave_period,sea_level_height_msl,sea_surface_temperature,wave_direction,swell_wave_direction", 
                    "timezone": "auto",   # times in the spot's local time instead of GMT
                    "forecast_days": 7},
                    timeout=(3, 5))   # give up connecting after 3 s and waiting for the answer after 5 s (then the session retries)
    response.raise_for_status()  # raises an error if the API replied with an error code
    marine_data = response.json()
    # return two values: the data and the spot's timezone name, e.g. "Europe/Lisbon"
    return marine_data["hourly"], marine_data["timezone"]

@st.cache_data(ttl=3600)  # same caching as above

def get_wind_data(lat, lon):
    response = session.get("https://api.open-meteo.com/v1/forecast", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",   # gusts = the short, stronger bursts of wind
                    "wind_speed_unit": "kn",   # knots instead of km/h
                    "timezone": "auto",        # local time, same as the marine data
                    "forecast_days": 7},
                    timeout=(3, 5))   # give up connecting after 3 s and waiting for the answer after 5 s (then the session retries)
    response.raise_for_status()
    wind_data = response.json()
    return wind_data["hourly"]

# When was this spot's data loaded? The function just returns the current time, and because it is cached
# with the same one-hour limit as the fetch functions, the time stays the same until the data is fetched again.
@st.cache_data(ttl=3600)
def get_load_time(lat, lon):
    return pd.Timestamp.now(tz="UTC")

# Sunrise and sunset for each forecast day (local time at the spot), used to find the daylight hours.
# Same caching as the other fetch functions.
@st.cache_data(ttl=3600)
def get_sun_data(lat, lon):
    response = session.get("https://api.open-meteo.com/v1/forecast",
                    params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "sunrise,sunset",   # "daily" = one value per day instead of per hour
                    "timezone": "auto",
                    "forecast_days": 7},
                    timeout=(3, 5))   # give up connecting after 3 s and waiting for the answer after 5 s (then the session retries)
    response.raise_for_status()
    return response.json()["daily"]

# Turns the dict of lists from the API into a table with the time as row labels
# (the same steps as in the main part below, packed into one function).
def to_table(hourly):
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time")
