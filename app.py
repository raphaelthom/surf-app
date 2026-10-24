import streamlit as st
import requests 
import pandas as pd
import plotly.graph_objects as go   # Plotly: interactive charts

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
                    "hourly": "wave_height,swell_wave_height,swell_wave_period,sea_level_height_msl,sea_surface_temperature", 
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

# Colours for the three ratings, used in the hourly quality chart
RATING_COLORS = {"Good": "#1b9e77", "Okay": "#e6a117", "Poor": "#9aa0a6"}

# Finds the best stretch of hours in a table with one row per hour and a "rating" column.
# Step 1: take the best rating that occurs at all ("Good" if there is any, else "Okay", else "Poor").
# Step 2: collect blocks of consecutive hours with that rating.
# Step 3: return the longest block as (rating, start time, end time).
def find_best_window(day_hours):
    for level in ["Good", "Okay", "Poor"]:
        if (day_hours["rating"] == level).any():
            break                      # stop at the first (= best) level that exists

    blocks = []     # a list of blocks, each block is a list of consecutive times
    current = []
    for time, rating in day_hours["rating"].items():
        if rating == level:
            current.append(time)       # this hour continues the current block
        else:
            if current:                # the block just ended, so save it
                blocks.append(current)
                current = []
    if current:                        # don't forget the last block
        blocks.append(current)

    longest = max(blocks, key=len)     # on a tie, max keeps the first (= earliest) block
    return level, longest[0], longest[-1] + pd.Timedelta(hours=1)   # the last hour lasts until the next full hour

# Looks at the sea level from "now" on and returns the next turning point:
# ("High", time) if the level peaks first, ("Low", time) if it bottoms out first.
def next_turning_point(levels, now):
    future = levels[levels.index >= now]
    for i in range(1, len(future) - 1):
        before, here, after = future.iloc[i - 1], future.iloc[i], future.iloc[i + 1]
        if here > before and here >= after:
            return "High", future.index[i]
        if here < before and here <= after:
            return "Low", future.index[i]
    return None, None

# A Plotly line chart for one column, with a dashed vertical line at "now".
def make_line_chart(series, now, unit):
    fig = go.Figure(go.Scatter(
        x=series.index, y=series.values, mode="lines",
        hovertemplate="%{x|%a %H:%M}<br>%{y:.1f} " + unit + "<extra></extra>",
    ))
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper",
                  line=dict(dash="dash", width=1))   # yref="paper" = from the bottom (0) to the top (1) of the chart
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=unit, showlegend=False)
    return fig

# Wind chart: speed as a line, plus an arrow every 3 hours showing where the wind blows TO.
# The data gives the direction the wind comes FROM, so the arrow is turned by 180 degrees.
def make_wind_chart(wind_df, now):
    fig = make_line_chart(wind_df["wind_speed_10m"], now, "knots")
    every_3h = wind_df.iloc[::3]
    fig.add_trace(go.Scatter(
        x=every_3h.index, y=every_3h["wind_speed_10m"], mode="markers",
        marker=dict(symbol="arrow", size=14, angle=(every_3h["wind_direction_10m"] + 180) % 360, angleref="up"),
        text=every_3h["wind_direction_10m"].apply(degrees_to_compass),
        hovertemplate="%{x|%a %H:%M}<br>%{y:.0f} knots from %{text}<extra></extra>",
    ))
    return fig

# One bar per daylight hour, coloured by rating. A higher bar means better conditions.
def make_quality_chart(hours, now):
    heights = {"Poor": 1, "Okay": 2, "Good": 3}
    fig = go.Figure()
    for level, color in RATING_COLORS.items():
        part = hours[hours["rating"] == level]
        fig.add_trace(go.Bar(
            x=part.index, y=[heights[level]] * len(part), name=level, marker_color=color,
            customdata=part[["period", "wind"]],
            hovertemplate="%{x|%a %H:%M}<br>" + level + ": %{customdata[0]:.1f} s swell, %{customdata[1]:.0f} kn wind<extra></extra>",
        ))
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper", line=dict(dash="dash", width=1))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(visible=False),
                      bargap=0.1, legend=dict(orientation="h", y=1.1))
    return fig

# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

# layout="wide" uses the full browser width instead of a narrow column.
# (set_page_config has to be the first Streamlit command that draws something.)
st.set_page_config(page_title="Surf Forecast", page_icon="🏄", layout="wide")

st.title("🏄 Surf Forecast")

spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()))
coords = SPOTS[spot_name]
lat, lon = coords

# ---------- 1. Load and prepare all the data ----------
# The page needs every table before it can show anything,
# so all loading happens first and the display comes afterwards.

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

current_period = marine_df.loc[now, "swell_wave_period"]   # .loc picks the row by its time label
current_wave = marine_df.loc[now, "wave_height"]
current_wind = wind_df.loc[now, "wind_speed_10m"]
current_direction = wind_df.loc[now, "wind_direction_10m"]
rating, reason = rate_conditions(current_period, current_wind)  # unpack the two returned values

# Wind table with a compass label, one row every 3 hours
table = wind_df.iloc[::3]
table["compass"] = table["wind_direction_10m"].apply(degrees_to_compass)

# Daily summary: one row per day instead of 24 hourly rows.
# groupby puts all rows with the same date into one group; .agg then
# calculates the smallest (min), largest (max) and average (mean) value of each group.
days = marine_df.index.date   # the calendar date of every hourly row
daily_waves = marine_df.groupby(days)["wave_height"].agg(["min", "max", "mean"]).round(1)
daily_wind = wind_df.groupby(days)["wind_speed_10m"].agg(["min", "max", "mean"]).round(1)

# Rating for every single hour (rate_conditions returns (rating, reason), so [0] takes the rating)
hours = pd.DataFrame({"period": marine_df["swell_wave_period"], "wind": wind_df["wind_speed_10m"]})
hours["rating"] = [rate_conditions(p, w)[0] for p, w in zip(hours["period"], hours["wind"])]
daylight_hours = hours.between_time("06:00", "18:00")   # hours that start between 06:00 and 18:00 local time, so daylight until 19:00

# Best time to surf: the hours still ahead today, or tomorrow if the daylight is over
target_day = now.date()
day_hours = daylight_hours[(daylight_hours.index.date == target_day) & (daylight_hours.index >= now)]
day_label = "today"
if day_hours.empty:
    target_day = (now + pd.Timedelta(days=1)).date()
    day_hours = daylight_hours[daylight_hours.index.date == target_day]
    day_label = "tomorrow"
best_level, best_start, best_end = find_best_window(day_hours)

# Tide and water temperature right now
tide = marine_df["sea_level_height_msl"]
tide_now = tide.loc[now]
tide_trend = "rising" if tide.loc[now + pd.Timedelta(hours=1)] > tide_now else "falling"
tide_kind, tide_time = next_turning_point(tide, now)
water_temp = marine_df.loc[now, "sea_surface_temperature"]

# ---------- 2. Display ----------
st.caption(f"{spot_name} ({lat}, {lon}) · local time {now:%a %d %b, %H:%M}")

# Top rows: the answer at a glance. st.columns(4) makes four equal columns side by side.
# "with col1:" means "everything indented below goes into column 1".
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Conditions right now", rating)   # st.metric = a big number/label card
    st.caption(reason)
with col2:
    if best_level == "Poor":   # if even the best hours are poor, don't call it a "best time"
        st.metric(f"Best time {day_label}", "–")
        st.caption(f"Only poor conditions {day_label}")
    else:
        st.metric(f"Best time {day_label}", f"{best_start:%H:%M}–{best_end:%H:%M}")
        st.caption(f"{best_level} conditions (daylight hours)")
with col3:
    st.metric("Wave height", f"{current_wave:.1f} m")
with col4:
    st.metric("Swell period", f"{current_period:.1f} s")

col5, col6, col7, col8 = st.columns(4)
with col5:
    st.metric("Wind", f"{current_wind:.0f} kn {degrees_to_compass(current_direction)}")
with col6:
    st.metric("Water temperature", f"{water_temp:.1f} °C")
with col7:
    st.metric("Tide", f"{tide_now:+.1f} m")
    st.caption(f"{tide_trend} (relative to mean sea level)")
with col8:
    if tide_kind:
        st.metric(f"Next {tide_kind.lower()} tide", f"{tide_time:%H:%M}")
    else:
        st.metric("Next tide", "–")

# st.tabs puts the details into clickable tabs, so the page doesn't become one long scroll.
tab_best, tab_waves, tab_wind, tab_tide, tab_daily = st.tabs(
    ["Best times", "Waves", "Wind", "Tides & water", "Daily summary"])

# st.plotly_chart shows a Plotly figure; width="stretch" makes it fill the column.
with tab_best:
    st.subheader("Surf quality by hour (daylight)")
    st.plotly_chart(make_quality_chart(daylight_hours, now), width="stretch")
    st.caption("Good: swell period of 10 s or more and wind up to 10 kn. "
               "Okay: period of 8 s or more and wind up to 15 kn. Poor: everything else. "
               "The dashed line marks the current hour.")

with tab_waves:
    wave_col1, wave_col2, wave_col3 = st.columns(3)
    with wave_col1:
        st.subheader("Wave height (m)")
        st.plotly_chart(make_line_chart(marine_df["wave_height"], now, "m"), width="stretch")
    with wave_col2:
        st.subheader("Swell wave height (m)")
        st.plotly_chart(make_line_chart(marine_df["swell_wave_height"], now, "m"), width="stretch")
    with wave_col3:
        st.subheader("Swell wave period (seconds)")
        st.plotly_chart(make_line_chart(marine_df["swell_wave_period"], now, "s"), width="stretch")

with tab_wind:
    st.subheader("Wind speed (knots) and direction")
    st.plotly_chart(make_wind_chart(wind_df, now), width="stretch")
    st.caption("Arrows show where the wind blows towards, every 3 hours.")
    st.subheader("Wind every 3 hours")
    st.dataframe(table)

with tab_tide:
    tide_col1, tide_col2 = st.columns(2)
    with tide_col1:
        st.subheader("Tide (m above/below mean sea level)")
        st.plotly_chart(make_line_chart(tide, now, "m"), width="stretch")
    with tide_col2:
        st.subheader("Water temperature (°C)")
        st.plotly_chart(make_line_chart(marine_df["sea_surface_temperature"], now, "°C"), width="stretch")
    st.caption("Tide data comes from a global sea-level model with a coarse grid. "
               "It shows the rough rhythm of high and low tide, not an exact local tide table.")

with tab_daily:
    daily_col1, daily_col2 = st.columns(2)
    with daily_col1:
        st.subheader("Wave height (m)")
        st.dataframe(daily_waves)
    with daily_col2:
        st.subheader("Wind speed (knots)")
        st.dataframe(daily_wind)

# An expander hides its content until the user clicks it.
with st.expander("Raw hourly data"):
    st.dataframe(marine_df)
