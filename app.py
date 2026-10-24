import streamlit as st
import requests 
import pandas as pd
import plotly.graph_objects as go   # Plotly: interactive charts

# The surf logic (compass labels, rating, best time, next tide) lives in surf_logic.py
from surf_logic import (degrees_to_compass, rate_for_spot, rate_hours, find_best_time, next_turning_point,
                        wind_type, swell_in_window, wave_power, SPOT_INFO, SKILL_LEVELS)

SPOTS = {
    "Lisbon": (38.65, -9.40),
    "San Diego": (32.70, -117.30),
    "Siargao": (9.80, 126.20),
    "Lombok": (-8.90, 116.30),
    "Taghazout": (30.55, -9.80)
}

# st.cache_data remembers the result for each input (lat, lon), so picking
# the same spot again doesn't call the API again. ttl=3600: forget after 1 hour.
@st.cache_data(ttl=3600)

def get_marine_data(lat, lon):
    response = requests.get("https://marine-api.open-meteo.com/v1/marine", 
                    params={
                    "latitude": lat, 
                    "longitude": lon, 
                    "hourly": "wave_height,swell_wave_height,swell_wave_period,sea_level_height_msl,sea_surface_temperature,wave_direction,swell_wave_direction", 
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

# Colours for the three ratings, used in the hourly quality chart
RATING_COLORS = {"Good": "#1b9e77", "Okay": "#e6a117", "Poor": "#9aa0a6"}
RATING_ICONS = {"Good": "🟢", "Okay": "🟡", "Poor": "⚪"}   # for the "All spots" table

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
        marker=dict(symbol="arrow", size=18, color="#d95f02",   # big and orange so the arrows stand out from the line
                    angle=(every_3h["wind_direction_10m"] + 180) % 360, angleref="up"),
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

# Turns the dict of lists from the API into a table with the time as row labels
# (the same steps as in the main part below, packed into one function).
def to_table(hourly):
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time")

# One row of the "All spots" table: loads a spot's data (cached, so spots that were loaded
# before are instant) and picks out the current values, the rating and the best time.
def summarize_spot(spot, rules, skill):
    lat, lon = SPOTS[spot]
    marine_data, timezone = get_marine_data(lat, lon)
    marine = to_table(marine_data)
    wind = to_table(get_wind_data(lat, lon))
    now = pd.Timestamp.now(tz=timezone).floor("h").tz_localize(None)   # the current hour AT THE SPOT

    period = marine.loc[now, "swell_wave_period"]
    wind_speed = wind.loc[now, "wind_speed_10m"]
    rating, reason = rate_for_spot(period, wind_speed, wind.loc[now, "wind_direction_10m"],
                                   marine.loc[now, "swell_wave_direction"], marine.loc[now, "wave_height"],
                                   spot, skill, **rules)
    daylight = rate_hours(marine, wind, spot, skill, **rules).between_time("06:00", "18:00")
    day_label, best_level, start, end = find_best_time(daylight, now)

    return {
        "Spot": spot,
        "Local time": f"{now:%H:%M}",
        "Now": f"{RATING_ICONS[rating]} {rating}",
        "Best time": "–" if best_level == "Poor" else f"{day_label} {start:%H:%M}–{end:%H:%M}",
        "Wave height": f"{marine.loc[now, 'wave_height']:.1f} m",
        "Swell": f"{period:.1f} s from {degrees_to_compass(marine.loc[now, 'swell_wave_direction'])}",
        "Wind": f"{wind_speed:.0f} kn {degrees_to_compass(wind.loc[now, 'wind_direction_10m'])}",
        # these two are only used for sorting and are removed before the table is shown
        "_rank": {"Good": 3, "Okay": 2, "Poor": 1}[rating],
        "_period": period,
    }

# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

# layout="wide" uses the full browser width instead of a narrow column.
# (set_page_config has to be the first Streamlit command that draws something.)
st.set_page_config(page_title="Surf Forecast", page_icon="🏄", layout="wide")

st.title("🏄 Surf Forecast")

# Two dropdowns side by side: [2, 1] makes the first column twice as wide as the second
pick_col1, pick_col2 = st.columns([2, 1])
with pick_col1:
    spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()))
with pick_col2:
    skill = st.selectbox("Your surf level", list(SKILL_LEVELS.keys()), index=1)   # index=1 -> "Intermediate" is pre-selected
too_small, too_big = SKILL_LEVELS[skill]   # the wave height range that is comfortable at your level
coords = SPOTS[spot_name]
lat, lon = coords

# The sidebar is a panel on the left. The sliders let you set what "Good" means to you;
# "Okay" is derived from them: 2 s less swell period and 5 knots more wind are still okay.
# They sit inside an expander because most people never need to change them.
with st.sidebar:
    with st.expander("Advanced: rating limits"):
        good_period = st.slider("Good: swell period at least (s)", 6, 16, 10)   # (label, min, max, start value)
        good_wind = st.slider("Good: wind at most (knots)", 0, 25, 10)
        st.caption(f"Okay: swell period at least {good_period - 2} s and wind up to {good_wind + 5} knots. "
                   "Everything else is Poor.")
# A dictionary with the four limits. Writing **rules in a function call hands over every entry
# as a separate argument, like good_period=..., good_wind=..., okay_period=..., okay_wind=...
rules = dict(good_period=good_period, good_wind=good_wind, okay_period=good_period - 2, okay_wind=good_wind + 5)

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
current_swell_direction = marine_df.loc[now, "swell_wave_direction"]   # directions are where it comes FROM, in degrees
current_wave_direction = marine_df.loc[now, "wave_direction"]
# rate_for_spot uses period and wind plus the spot's rules (wind direction, swell window) and your level
rating, reason = rate_for_spot(current_period, current_wind, current_direction, current_swell_direction,
                               current_wave, spot_name, skill, **rules)   # unpack the two returned values

# Wind table with a compass label, one row every 3 hours
table = wind_df.iloc[::3]
table["compass"] = table["wind_direction_10m"].apply(degrees_to_compass)

# Swell table with compass labels, one row every 3 hours
swell_table = marine_df.iloc[::3][["wave_height", "swell_wave_height", "swell_wave_period"]].round(1)
swell_table.columns = ["Wave height (m)", "Swell height (m)", "Swell period (s)"]   # readable column names
swell_table["Swell from"] = marine_df.iloc[::3]["swell_wave_direction"].apply(degrees_to_compass)
swell_table["Waves from"] = marine_df.iloc[::3]["wave_direction"].apply(degrees_to_compass)
swell_table.index = swell_table.index.strftime("%a %d %b %H:%M")   # e.g. "Sat 24 Oct 15:00"

# Daily summary: one row per day instead of 24 hourly rows.
# groupby puts all rows with the same date into one group; .agg then
# calculates the smallest (min), largest (max) and average (mean) value of each group.
days = marine_df.index.date   # the calendar date of every hourly row
daily_waves = marine_df.groupby(days)["wave_height"].agg(["min", "max", "mean"]).round(1)
daily_wind = wind_df.groupby(days)["wind_speed_10m"].agg(["min", "max", "mean"]).round(1)

# Rating for every single hour, then only the daylight hours
hours = rate_hours(marine_df, wind_df, spot_name, skill, **rules)
daylight_hours = hours.between_time("06:00", "18:00")   # hours that start between 06:00 and 18:00 local time, so daylight until 19:00

# Best time to surf: the hours still ahead today, or tomorrow if the daylight is over
day_label, best_level, best_start, best_end = find_best_time(daylight_hours, now)

# Tide and water temperature right now
tide = marine_df["sea_level_height_msl"]
tide_now = tide.loc[now]
tide_trend = "rising" if tide.loc[now + pd.Timedelta(hours=1)] > tide_now else "falling"
tide_kind, tide_time = next_turning_point(tide, now)
water_temp = marine_df.loc[now, "sea_surface_temperature"]

# Spot rules: is the wind onshore/offshore, does the swell direction work, and how much power do the waves have?
spot_info = SPOT_INFO[spot_name]
current_wind_type = wind_type(current_direction, spot_info["faces"])
swell_ok = swell_in_window(current_swell_direction, spot_info["swell_window"])
power_series = wave_power(marine_df["wave_height"], marine_df["swell_wave_period"])   # works on a whole column at once
power_now = power_series.loc[now]

# ---------- 2. Display ----------
st.caption(f"{spot_name} ({lat}, {lon}) · local time {now:%a %d %b, %H:%M}")

# Colours and texts for the big verdict card
TILE_COLORS = {"Good": "#1b9e77", "Okay": "#d68a00", "Poor": "#6b7280"}
VERDICTS = {"Good": "Good – go surf!", "Okay": "Okay – surfable", "Poor": "Poor – skip it"}
if best_level == "Poor":   # if even the best hours are poor, don't call it a "best time"
    best_line = f"No good window {day_label}"
else:
    best_line = f"Best time {day_label}: {best_start:%H:%M}–{best_end:%H:%M} ({best_level.lower()} conditions)"

# The verdict card: one big coloured box with the answer to "should I go?".
# st.markdown can draw plain HTML when unsafe_allow_html=True (safe here: the text is made by our own code).
st.markdown(
    f'<div style="background:{TILE_COLORS[rating]}; color:white; padding:1.2rem 1.6rem; border-radius:12px; margin:0.5rem 0 1rem 0;">'
    f'<div style="font-size:0.9rem; opacity:0.9;">Right now at {spot_name}</div>'
    f'<div style="font-size:2.4rem; font-weight:700; line-height:1.2;">{VERDICTS[rating]}</div>'
    f'<div style="font-size:1rem; margin-top:0.3rem;">{reason[0].upper() + reason[1:]}</div>'
    f'<div style="font-size:1.1rem; font-weight:600; margin-top:0.6rem;">{best_line}</div>'
    f'</div>',
    unsafe_allow_html=True)

# The four numbers that matter most. help="..." adds a small (?) with an explanation on hover.
WIND_NOTES = {"Offshore": "clean, smooth waves", "Cross-shore": "neutral, a bit bumpy", "Onshore": "choppy, messy waves"}
if current_wave < too_small:
    size_note = f"small for {skill.lower()} level"
elif current_wave > too_big:
    size_note = f"big for {skill.lower()} level"
else:
    size_note = f"good size for {skill.lower()} level"

key1, key2, key3, key4 = st.columns(4)
with key1:
    st.metric("Wave height", f"{current_wave:.1f} m", help="How tall the waves are. Bigger is not always better: it has to match your level.")
    st.caption(size_note)
with key2:
    st.metric("Swell", f"{current_period:.1f} s {degrees_to_compass(current_swell_direction)}",
              help="Seconds between waves, and the direction they come from. A longer period means more powerful, better organised waves.")
    st.caption("direction fits this spot" if swell_ok else "direction is off for this spot")
with key3:
    st.metric("Wind", f"{current_wind:.0f} kn {degrees_to_compass(current_direction)}",
              help="Wind speed in knots and where it blows from. Light wind, blowing from land to sea, is best.")
    st.caption(f"{current_wind_type.lower()}: {WIND_NOTES[current_wind_type]}")
with key4:
    st.metric("Water temperature", f"{water_temp:.1f} °C", help="Tells you what to wear: a wetsuit is usually needed below about 22 °C.")

# Secondary data hides in an expander until someone wants it
with st.expander("More conditions: tide, wave power, wave direction"):
    more1, more2, more3, more4 = st.columns(4)
    with more1:
        st.metric("Tide", f"{tide_now:+.1f} m", help="Sea level compared with the average. Plus = higher than average.")
        if tide_kind:
            st.caption(f"{tide_trend}, next {tide_kind.lower()} tide at {tide_time:%H:%M}")
        else:
            st.caption(tide_trend)
    with more2:
        st.metric("Wave power", f"{power_now:.0f} kW/m", help="Roughly how much energy the waves carry. Higher = punchier waves.")
        st.caption("0.49 × height² × period")
    with more3:
        low, high = spot_info["swell_window"]
        st.metric("Swell direction", "Works here" if swell_ok else "Off-angle")
        st.caption(f"{spot_name} likes swell from {degrees_to_compass(low)} to {degrees_to_compass(high)}")
    with more4:
        st.metric("Wind waves from", degrees_to_compass(current_wave_direction))
        st.caption(f"{current_wave_direction:.0f}° · swell from {current_swell_direction:.0f}°")

# st.tabs puts the details into clickable tabs, so the page doesn't become one long scroll.
tab_best, tab_waves, tab_wind, tab_tide, tab_daily, tab_all = st.tabs(
    ["Best times", "Waves", "Wind", "Tides & water", "Daily summary", "All spots"])

# st.plotly_chart shows a Plotly figure; width="stretch" makes it fill the column.
with tab_best:
    st.subheader("Surf quality by hour (daylight)")
    st.plotly_chart(make_quality_chart(daylight_hours, now), width="stretch")
    st.caption(f"Good: swell period of {good_period} s or more and wind up to {good_wind} kn. "
               f"Okay: period of {good_period - 2} s or more and wind up to {good_wind + 5} kn. Poor: everything else. "
               "On top of that: onshore wind and swell from the wrong direction lower the rating one level, "
               "offshore wind counts as 5 kn lighter, and wave height is checked against your level. "
               "Change the limits in the sidebar. The dashed line marks the current hour.")

with tab_waves:
    wave_col1, wave_col2, wave_col3 = st.columns(3)
    with wave_col1:
        st.subheader("Wave height (m)")
        st.plotly_chart(make_line_chart(marine_df["wave_height"], now, "m"), width="stretch")
    with wave_col2:
        st.subheader("Swell wave height (m)")
        st.plotly_chart(make_line_chart(marine_df["swell_wave_height"], now, "m"), width="stretch")
    with wave_col3:
        st.subheader("Swell period (s)")
        st.plotly_chart(make_line_chart(marine_df["swell_wave_period"], now, "s"), width="stretch")
    st.subheader("Wave power (kW per metre of wave front)")
    st.plotly_chart(make_line_chart(power_series, now, "kW/m"), width="stretch")
    st.caption("A rough measure of how strong the waves are: 0.49 × wave height² × swell period. "
               "Height counts squared, so bigger waves are much more powerful.")
    st.subheader("Swell every 3 hours")
    st.dataframe(swell_table)
    st.caption("\"from\" is the direction the swell or waves come from: NW means they travel towards the south-east.")

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
        water_fig = make_line_chart(marine_df["sea_surface_temperature"], now, "°C")
        # Plotly zooms in as far as it can, which would make a change of 0.4 °C look dramatic.
        # So the axis shows at least 3 °C around the data.
        temp = marine_df["sea_surface_temperature"]
        water_fig.update_yaxes(range=[temp.min() - 1.5, temp.max() + 1.5])
        st.plotly_chart(water_fig, width="stretch")
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

with tab_all:
    st.subheader("Where is it good right now?")
    rows = []
    for spot in SPOTS:
        try:
            rows.append(summarize_spot(spot, rules, skill))
        except (requests.RequestException, KeyError):
            st.warning(f"No data for {spot} right now.")   # one failing spot shouldn't break the whole table
    if rows:
        # best rating first; spots with the same rating are sorted by swell period, longest first
        overview = pd.DataFrame(rows).sort_values(["_rank", "_period"], ascending=False)
        st.dataframe(overview.drop(columns=["_rank", "_period"]), hide_index=True)
    st.caption("Uses the rating rules from the sidebar. Times are local to each spot; "
               "\"Best time\" is the best daylight stretch still ahead today, or tomorrow once the day is over.")

# An expander hides its content until the user clicks it.
with st.expander("Raw hourly data"):
    st.dataframe(marine_df)

# Open-Meteo's free API asks for a credit (data licence: CC BY 4.0).
st.caption("Weather and marine data by [Open-Meteo.com](https://open-meteo.com/) "
           "(CC BY 4.0). Surf ratings are a simple rule of thumb, not professional advice.")
