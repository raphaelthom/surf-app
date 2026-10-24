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

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# st.cache_data remembers the result for each input (lat, lon), so picking
# the same spot again doesn't call the API again. ttl=3600: forget after 1 hour.
@st.cache_data(ttl=3600)

def get_marine_data(lat, lon):
    response = requests.get("https://marine-api.open-meteo.com/v1/marine", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wave_height,swell_wave_height,swell_wave_period", 
                    "timezone": "auto",   # times in the spot's local time instead of GMT
                    "forecast_days": 7})
    response.raise_for_status()  # raises an error if the API replied with an error code
    marine_data = response.json()
    # return two values: the data and the spot's timezone name, e.g. "Europe/Lisbon"
    return marine_data["hourly"], marine_data["timezone"]

@st.cache_data(ttl=3600)  # same caching as above

def get_wind_data(lat, lon):
    response = requests.get("https://api.open-meteo.com/v1/forecast", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wind_speed_10m,wind_direction_10m",
                    "wind_speed_unit": "kn",   # knots instead of km/h
                    "timezone": "auto",        # local time, same as the marine data
                    "forecast_days": 7})
    response.raise_for_status()
    wind_data = response.json()
    return wind_data["hourly"]

def degrees_to_compass(degrees):
    index = round(degrees / 45) % 8 # degrees / 45 says how many 45° steps fit, and round(...) picks the nearest one. % 8 (modulo) is the remainder after dividing by 8. It makes 360° wrap around to 0, which is "N". For example, 350° / 45 ≈ 7.8 → rounds to 8 → 8 % 8 = 0 → "N".
    label = DIRECTIONS[index] # looks up the label by position. Positions start at 0.
    return label

# Rates surf conditions as "Good", "Okay" or "Poor": long swell periods and light wind
# (in knots) are better. Python checks the conditions top to bottom and uses the first true one.
# Returns two values (a tuple): the rating and a short reason for it.
def rate_conditions(swell_wave_period, wind_speed_10m):
    if swell_wave_period >= 10 and wind_speed_10m <= 10:
        return "Good", "long swell period and light wind"
    elif swell_wave_period >= 8 and wind_speed_10m <= 15:
        # "Good" failed, so the period is under 10 s, the wind is over 10 kn, or both
        if swell_wave_period < 10 and wind_speed_10m > 10:
            return "Okay", "swell period is a bit short and wind is a bit strong"
        elif swell_wave_period < 10:
            return "Okay", "swell period is a bit short (under 10 s)"
        else:
            return "Okay", "wind is a bit strong (over 10 knots)"
    else:
        # the "Okay" test failed too, so the period is under 8 s, the wind is over 15 kn, or both
        if swell_wave_period < 8 and wind_speed_10m > 15:
            return "Poor", "swell period is too short and wind is too strong"
        elif swell_wave_period < 8:
            return "Poor", "swell period is too short (under 8 s)"
        else:
            return "Poor", "wind is too strong (over 15 knots)"

# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

st.title("🏄 Surf Forecast")

spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()))
coords = SPOTS[spot_name]
lat, lon = coords

# try/except: Python tries the code under "try". If the network or API fails,
# it jumps to "except" and shows a message instead of crashing with a red traceback.
try:
    marine_data, timezone = get_marine_data(lat, lon)   # catch what the function returns: a dict of lists and the timezone
except (requests.RequestException, KeyError) as error:
    st.error(f"Couldn't load the wave data. (Details: {error!r})")
    st.stop()  # stop the script here, since everything below needs this data

marine_df = pd.DataFrame(marine_data)           # turn the dict of lists into a table; made a table with one column per key
marine_df["time"] = pd.to_datetime(marine_df["time"]) # converts text to date objects
marine_df = marine_df.set_index("time") # makes that column the row labels instead of 0, 1, 2…

st.write(spot_name, coords)
st.subheader("Wave height (m)")
st.line_chart(marine_df["wave_height"])
st.subheader("Swell wave height (m)")
st.line_chart(marine_df["swell_wave_height"])
st.subheader("Swell wave period (seconds)")
st.line_chart(marine_df["swell_wave_period"])
st.dataframe(marine_df)                   # show the table


try:
    wind_data = get_wind_data(lat, lon)   # catch what the function returns; returns a dict of lists
except (requests.RequestException, KeyError) as error:
    st.error(f"Couldn't load the wind data. (Details: {error!r})")
    st.stop()
    
wind_df = pd.DataFrame(wind_data)           # turn the dict of lists into a table; made a table with one column per key
wind_df["time"] = pd.to_datetime(wind_df["time"]) # converts text to date objects
wind_df = wind_df.set_index("time") # makes that column the row labels instead of 0, 1, 2…

# What time is it at the spot right now? Ask the clock for the current time in that timezone,
# round down to the full hour (the forecast has one row per hour) and drop the timezone label
# so it can be compared with the table's row labels.
now = pd.Timestamp.now(tz=timezone).floor("h").tz_localize(None)
st.write(f"Local time at {spot_name}: {now:%a %d %b, %H:%M}")

current_period = marine_df.loc[now, "swell_wave_period"]   # .loc picks the row by its time label
current_wind = wind_df.loc[now, "wind_speed_10m"]
rating, reason = rate_conditions(current_period, current_wind)  # unpack the two returned values
st.write(f"Conditions right now: {rating} – {reason}")

st.subheader("Wind speed (knots)")
st.line_chart(wind_df["wind_speed_10m"])
st.subheader("Wind direction (degrees)")
st.line_chart(wind_df["wind_direction_10m"])

table = wind_df.iloc[::3]
table["compass"] = table["wind_direction_10m"].apply(degrees_to_compass)
st.dataframe(table)

# Daily summary: one row per day instead of 24 hourly rows.
# groupby puts all rows with the same date into one group; .agg then
# calculates the smallest (min), largest (max) and average (mean) value of each group.
st.subheader("Daily summary")
days = marine_df.index.date   # the calendar date of every hourly row
daily_waves = marine_df.groupby(days)["wave_height"].agg(["min", "max", "mean"]).round(1)
daily_wind = wind_df.groupby(days)["wind_speed_10m"].agg(["min", "max", "mean"]).round(1)

st.write("Wave height (m)")
st.dataframe(daily_waves)
st.write("Wind speed (knots)")
st.dataframe(daily_wind)