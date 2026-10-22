import streamlit as st
import requests
import pandas as pd

SPOTS = {
    "Lisbon": (38.65, -9.40),
    "San Diego": (32.70, -117.30),
    "Siargao": (9.80, 126.20),
    "Lombok": (-8.90, 116.30),
    "Taghazout": (30.55, -9.80)
}

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


# st.cache_data remembers the result for each combination of inputs.
# Picking the same spot again reuses the saved table instead of calling
# the API again. ttl=3600 means "forget it after 1 hour", so the
# forecast doesn't get stale.
@st.cache_data(ttl=3600)
def get_forecast(url, lat, lon, variables, extra_params=None):
    # Both APIs work the same way, so one function handles both.
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": variables,
        "forecast_days": 7,
    }
    if extra_params:
        params.update(extra_params)  # add the extra settings, e.g. wind unit

    response = requests.get(url, params=params)
    hourly = response.json()["hourly"]

    df = pd.DataFrame(hourly)                # dict of lists -> table
    df["time"] = pd.to_datetime(df["time"])  # text -> real dates
    return df.set_index("time")              # dates become the row labels


# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

st.title("🏄 Surf Forecast")

spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()))
lat, lon = SPOTS[spot_name]
st.write(f"{spot_name}: latitude {lat}, longitude {lon}")

marine_df = get_forecast(
    MARINE_URL, lat, lon,
    "wave_height,swell_wave_height,swell_wave_period",
)
# "kn" = knots, the unit surfers usually use for wind
wind_df = get_forecast(
    WEATHER_URL, lat, lon,
    "wind_speed_10m,wind_direction_10m",
    {"wind_speed_unit": "kn"},
)

st.subheader("Wave height (m)")
st.line_chart(marine_df["wave_height"])

st.subheader("Swell wave height (m)")
st.line_chart(marine_df["swell_wave_height"])

st.subheader("Swell wave period (s)")
st.line_chart(marine_df["swell_wave_period"])

st.subheader("Wind speed (knots)")
st.line_chart(wind_df["wind_speed_10m"])

st.subheader("Wind direction (degrees, 0 = from north)")
st.line_chart(wind_df["wind_direction_10m"])

st.subheader("Raw marine data")
st.dataframe(marine_df)
