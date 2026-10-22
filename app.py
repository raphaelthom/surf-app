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

def get_marine_data(lat, lon):
    response = requests.get("https://marine-api.open-meteo.com/v1/marine", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wave_height,swell_wave_height,swell_wave_period", 
                    "forecast_days": 7})
    data = response.json()
    return data["hourly"]

# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

st.title("🏄 Surf Forecast")

spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()))
coords = SPOTS[spot_name]
lat, lon = coords
data = get_marine_data(lat, lon)   # catch what the function returns; returns a dict of lists
df = pd.DataFrame(data)           # turn the dict of lists into a table; made a table with one column per key
df["time"] = pd.to_datetime(df["time"]) # converts text to date objects
df = df.set_index("time") # makes that column the row labels instead of 0, 1, 2…

st.write(spot_name, coords)
st.subheader("Wave height (m)")
st.line_chart(df["wave_height"])
st.subheader("Swell Wave height (m)")
st.line_chart(df["swell_wave_height"])
st.subheader("swell wave period (in seconds))")
st.line_chart(df["swell_wave_period"])
st.dataframe(df)                   # show the table

