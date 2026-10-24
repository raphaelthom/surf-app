import streamlit as st
import requests 
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import plotly.graph_objects as go   # Plotly: interactive charts

# The surf logic (compass labels, rating, best time, next tide) lives in surf_logic.py
from surf_logic import (degrees_to_compass, rate_for_spot, rate_hours, find_best_time, best_per_day, next_turning_point, make_sun_times, daylight_only,
                        HEIGHT_FACTORS, WIND_FACTORS, convert_temp, wind_text, week_score, best_day, wetsuit_for, swell_trend, wind_warning,
                        wind_type, swell_in_window, wave_power, SPOT_INFO, SKILL_LEVELS)

SPOTS = {
    "Lisbon": (38.65, -9.40),
    "San Diego": (32.70, -117.30),
    "Siargao": (9.80, 126.20),
    "Lombok": (-8.90, 116.30),
    "Taghazout": (30.55, -9.80)
}

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
                    "hourly": "wind_speed_10m,wind_direction_10m",
                    "wind_speed_unit": "kn",   # knots instead of km/h
                    "timezone": "auto",        # local time, same as the marine data
                    "forecast_days": 7},
                    timeout=(3, 5))   # give up connecting after 3 s and waiting for the answer after 5 s (then the session retries)
    response.raise_for_status()
    wind_data = response.json()
    return wind_data["hourly"]

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
# factor and unit convert the speed from knots to what the user picked (e.g. 1.852 and "km/h").
def make_wind_chart(wind_df, now, factor, unit):
    fig = make_line_chart(wind_df["wind_speed_10m"] * factor, now, unit)
    every_3h = wind_df.iloc[::3]
    fig.add_trace(go.Scatter(
        x=every_3h.index, y=every_3h["wind_speed_10m"] * factor, mode="markers",
        marker=dict(symbol="arrow", size=18, color="#d95f02",   # big and orange so the arrows stand out from the line
                    angle=(every_3h["wind_direction_10m"] + 180) % 360, angleref="up"),
        text=every_3h["wind_direction_10m"].apply(degrees_to_compass),
        hovertemplate="%{x|%a %H:%M}<br>%{y:.0f} " + unit + " from %{text}<extra></extra>",
    ))
    return fig

# One bar per daylight hour, coloured by rating. A higher bar means better conditions.
def make_quality_chart(hours, now, wind_factor, wind_unit):
    heights = {"Poor": 1, "Okay": 2, "Good": 3}
    fig = go.Figure()
    for level, color in RATING_COLORS.items():
        part = hours[hours["rating"] == level]
        fig.add_trace(go.Bar(
            x=part.index, y=[heights[level]] * len(part), name=level, marker_color=color,
            customdata=part[["period", "wind"]] * [1, wind_factor],   # multiplies only the wind column
            hovertemplate="%{x|%a %H:%M}<br>" + level + ": %{customdata[0]:.1f} s swell, %{customdata[1]:.0f} " + wind_unit + " wind<extra></extra>",
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
def summarize_spot(spot, rules, skill, height_unit, wind_unit):
    lat, lon = SPOTS[spot]
    marine_data, timezone = get_marine_data(lat, lon)
    marine = to_table(marine_data)
    wind = to_table(get_wind_data(lat, lon))
    now = pd.Timestamp.now(tz=timezone).floor("h").tz_localize(None)   # the current hour AT THE SPOT

    period = marine.loc[now, "swell_wave_period"]
    wind_speed = wind.loc[now, "wind_speed_10m"]
    rating, reason = rate_for_spot(period, wind_speed, wind.loc[now, "wind_direction_10m"],
                                   marine.loc[now, "swell_wave_direction"], marine.loc[now, "wave_height"],
                                   spot, skill, wind_unit=wind_unit, **rules)
    daylight = daylight_only(rate_hours(marine, wind, spot, skill, **rules), make_sun_times(get_sun_data(lat, lon)))
    day_label, best_level, start, end = find_best_time(daylight, now)
    top_date, top_level, _, _ = best_day(best_per_day(daylight, now))   # the best day of the coming week

    return {
        "Spot": spot,
        "Local time": f"{now:%H:%M}",
        "Now": f"{RATING_ICONS[rating]} {rating}",
        "Best time": "–" if best_level == "Poor" else f"{day_label} {start:%H:%M}–{end:%H:%M}",
        "Wave height": f"{marine.loc[now, 'wave_height'] * HEIGHT_FACTORS[height_unit]:.1f} {height_unit}",
        "Swell": f"{period:.1f} s from {degrees_to_compass(marine.loc[now, 'swell_wave_direction'])}",
        "Wind": f"{wind_speed * WIND_FACTORS[wind_unit]:.0f} {wind_unit} {degrees_to_compass(wind.loc[now, 'wind_direction_10m'])}",
        "Best day": "–" if top_level == "Poor" else f"{top_date:%a %d} · {top_level}",
        "Week score": round(week_score(daylight, now)),
        # these are only used for sorting and are removed before the table is shown
        "_week": week_score(daylight, now),
        "_rank": {"Good": 3, "Okay": 2, "Poor": 1}[rating],
        "_period": period,
    }

# Streamlit re-runs this whole file from top to bottom
# every time the user interacts with the page.

# layout="wide" uses the full browser width instead of a narrow column.
# (set_page_config has to be the first Streamlit command that draws something.)
st.set_page_config(page_title="Surf Forecast", page_icon="🏄", layout="wide")

st.title("🏄 Surf Forecast")

# Remember the choices in the page address (e.g. ?spot=Lombok&level=Beginner), so a bookmark or a shared link
# opens the same setup. Streamlit keeps each widget's value in st.session_state under its key.
# On the first run of a visit that value is empty, so it is filled from the address if the address has a valid one.
st.session_state.setdefault("level", "Intermediate")   # the default surf level
choices = {   # key of the widget: its allowed values
    "spot": list(SPOTS), "level": list(SKILL_LEVELS), "height": list(HEIGHT_FACTORS),
    "wind": list(WIND_FACTORS), "temp": ["°C", "°F"],
}
for key, options in choices.items():
    if st.query_params.get(key) in options and key not in st.session_state.get("restored", set()):
        st.session_state[key] = st.query_params[key]
st.session_state["restored"] = set(choices)   # only restore once per visit, so later clicks win

# Two dropdowns side by side: [2, 1] makes the first column twice as wide as the second
pick_col1, pick_col2 = st.columns([2, 1])
with pick_col1:
    spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()), key="spot")
with pick_col2:
    skill = st.selectbox("Your surf level", list(SKILL_LEVELS.keys()), key="level")
too_small, too_big = SKILL_LEVELS[skill]   # the wave height range that is comfortable at your level
coords = SPOTS[spot_name]
lat, lon = coords

# The sidebar is a panel on the left. The sliders let you set what "Good" means to you;
# "Okay" is derived from them: 2 s less swell period and 5 knots more wind are still okay.
# They sit inside an expander because most people never need to change them.
with st.sidebar:
    st.header("Units")
    # st.radio shows all options at once; horizontal=True puts them in one row
    h_unit = st.radio("Wave height", list(HEIGHT_FACTORS), horizontal=True, key="height")
    w_unit = st.radio("Wind speed", list(WIND_FACTORS), horizontal=True, key="wind")
    t_unit = st.radio("Temperature", ["°C", "°F"], horizontal=True, key="temp")
    with st.expander("Advanced: rating limits"):
        good_period = st.slider("Good: swell period at least (s)", 6, 16, 10)   # (label, min, max, start value)
        good_wind = st.slider("Good: wind at most (knots)", 0, 25, 10)   # the limits are always in knots
        st.caption(f"Okay: swell period at least {good_period - 2} s and wind up to {good_wind + 5} knots. "
                   "Everything else is Poor.")
# A dictionary with the four limits. Writing **rules in a function call hands over every entry
# as a separate argument, like good_period=..., good_wind=..., okay_period=..., okay_wind=...
rules = dict(good_period=good_period, good_wind=good_wind, okay_period=good_period - 2, okay_wind=good_wind + 5)
# Write the current choices into the page address (after all widgets exist, so these are the final values)
st.query_params.update(spot=spot_name, level=skill, height=h_unit, wind=w_unit, temp=t_unit)
st.sidebar.caption("Your choices are saved in the page address: bookmark or share the link to keep them.")

h_factor = HEIGHT_FACTORS[h_unit]   # how many ft in one metre (or 1 for metres)
w_factor = WIND_FACTORS[w_unit]     # how many km/h or mph in one knot (or 1 for knots)

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

try:
    sun_times = make_sun_times(get_sun_data(lat, lon))   # {date: (sunrise, sunset)}
except (requests.RequestException, KeyError) as error:
    st.error(f"Couldn't load the sunrise and sunset times. (Details: {error!r})")
    st.stop()

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
                               current_wave, spot_name, skill, wind_unit=w_unit, **rules)   # unpack the two returned values

# Wind table with a compass label, one row every 3 hours
table = wind_df.iloc[::3]
table["compass"] = table["wind_direction_10m"].apply(degrees_to_compass)
table["wind_speed_10m"] = (table["wind_speed_10m"] * w_factor).round(1)   # show the speed in the chosen unit
table = table.rename(columns={"wind_speed_10m": f"Wind speed ({w_unit})", "wind_direction_10m": "Direction (°)"})

# Swell table with compass labels, one row every 3 hours
swell_table = marine_df.iloc[::3][["wave_height", "swell_wave_height", "swell_wave_period"]].copy()
swell_table[["wave_height", "swell_wave_height"]] *= h_factor   # heights in the chosen unit
swell_table = swell_table.round(1)
swell_table.columns = [f"Wave height ({h_unit})", f"Swell height ({h_unit})", "Swell period (s)"]   # readable column names
swell_table["Swell from"] = marine_df.iloc[::3]["swell_wave_direction"].apply(degrees_to_compass)
swell_table["Waves from"] = marine_df.iloc[::3]["wave_direction"].apply(degrees_to_compass)
swell_table.index = swell_table.index.strftime("%a %d %b %H:%M")   # e.g. "Sat 24 Oct 15:00"

# Daily summary: one row per day instead of 24 hourly rows.
# groupby puts all rows with the same date into one group; .agg then
# calculates the smallest (min), largest (max) and average (mean) value of each group.
days = marine_df.index.date   # the calendar date of every hourly row
daily_waves = (marine_df.groupby(days)["wave_height"].agg(["min", "max", "mean"]) * h_factor).round(1)
daily_wind = (wind_df.groupby(days)["wind_speed_10m"].agg(["min", "max", "mean"]) * w_factor).round(1)

# Rating for every single hour, then only the daylight hours
hours = rate_hours(marine_df, wind_df, spot_name, skill, **rules)
daylight_hours = daylight_only(hours, sun_times)   # only the hours between sunrise and sunset at this spot

# Best time to surf: the hours still ahead today, or tomorrow if the daylight is over
day_label, best_level, best_start, best_end = find_best_time(daylight_hours, now)

# Is the swell building or dropping over the next 6 hours?
trend, trend_change = swell_trend(marine_df["swell_wave_height"], now)

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
sunrise_today, sunset_today = sun_times[now.date()]
st.caption(f"{spot_name} ({lat}, {lon}) · local time {now:%a %d %b, %H:%M} · "
           f"sunrise {sunrise_today:%H:%M}, sunset {sunset_today:%H:%M}")

# Colours and texts for the big verdict card
TILE_COLORS = {"Good": "#1b9e77", "Okay": "#d68a00", "Poor": "#6b7280"}
VERDICTS = {"Good": "Good – go surf!", "Okay": "Okay – surfable", "Poor": "Poor – skip it"}
if best_level == "Poor":   # if even the best hours are poor, don't call it a "best time"
    best_line = f"No good window {day_label}"
else:
    best_line = f"Best time {day_label}: {best_start:%H:%M}–{best_end:%H:%M} ({best_level.lower()} conditions)"

# If the best window ends because of the wind, add a warning line to the card
warning_line = ""
if best_level != "Poor":
    warning = wind_warning(wind_df, spot_name, best_end)
    if warning:
        warning_line = f'<div style="font-size:0.95rem; margin-top:0.5rem;">⚠️ {warning}</div>'

# The verdict card: one big coloured box with the answer to "should I go?".
# st.markdown can draw plain HTML when unsafe_allow_html=True (safe here: the text is made by our own code).
st.markdown(
    f'<div style="background:{TILE_COLORS[rating]}; color:white; padding:1.2rem 1.6rem; border-radius:12px; margin:0.5rem 0 1rem 0;">'
    f'<div style="font-size:0.9rem; opacity:0.9;">Right now at {spot_name}</div>'
    f'<div style="font-size:2.4rem; font-weight:700; line-height:1.2;">{VERDICTS[rating]}</div>'
    f'<div style="font-size:1rem; margin-top:0.3rem;">{reason[0].upper() + reason[1:]}</div>'
    f'<div style="font-size:1.1rem; font-weight:600; margin-top:0.6rem;">{best_line}</div>'
    f'{warning_line}'
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
    st.metric("Wave height", f"{current_wave * h_factor:.1f} {h_unit}", help="How tall the waves are. Bigger is not always better: it has to match your level.")
    st.caption(size_note)
with key2:
    st.metric("Swell", f"{current_period:.1f} s {degrees_to_compass(current_swell_direction)}",
              help="Seconds between waves, and the direction they come from. A longer period means more powerful, better organised waves.")
    st.caption("direction fits this spot" if swell_ok else "direction is off for this spot")
    TREND_ICONS = {"building": "📈", "dropping": "📉", "steady": "➡️"}
    st.caption(f"{TREND_ICONS[trend]} {trend}" + ("" if trend == "steady" else f" ({trend_change:+.0f}% in 6 h)"))
with key3:
    st.metric("Wind", f"{current_wind * w_factor:.0f} {w_unit} {degrees_to_compass(current_direction)}",
              help="Wind speed and where it blows from. Light wind, blowing from land to sea, is best.")
    st.caption(f"{current_wind_type.lower()}: {WIND_NOTES[current_wind_type]}")
with key4:
    st.metric("Water temperature", f"{convert_temp(water_temp, t_unit):.1f} {t_unit}",
              help=f"Tells you what to wear: a wetsuit is usually needed below about {convert_temp(22, t_unit):.0f} {t_unit}.")
    st.caption(f"Wear: {wetsuit_for(water_temp)}")   # water_temp is always in °C here, whatever unit is shown

# "This week at a glance": one coloured tile per day with that day's best rating and time window.
# best_per_day returns a list of (date, rating, start, end); one column per day.
st.subheader("This week at a glance")
week = best_per_day(daylight_hours, now)
for column, (date, level, start, end) in zip(st.columns(len(week)), week):
    day_name = "Today" if date == now.date() else f"{date:%a %d}"
    window = "–" if level == "Poor" else f"{start:%H:%M}–{end:%H:%M}"   # no window to show if even the best hours are poor
    with column:
        st.markdown(
            f'<div style="background:{TILE_COLORS[level]}; color:white; padding:0.7rem 0.4rem; border-radius:10px; text-align:center; margin-bottom:0.6rem;">'
            f'<div style="font-size:0.85rem; opacity:0.9;">{day_name}</div>'
            f'<div style="font-size:1.2rem; font-weight:700;">{level}</div>'
            f'<div style="font-size:0.8rem;">{window}</div>'
            f'</div>',
            unsafe_allow_html=True)
st.caption("Each tile shows the best daylight stretch of that day. Further ahead, forecasts get less reliable.")

# Secondary data hides in an expander until someone wants it
with st.expander("More conditions: tide, wave power, wave direction"):
    more1, more2, more3, more4 = st.columns(4)
    with more1:
        st.metric("Tide", f"{tide_now * h_factor:+.1f} {h_unit}", help="Sea level compared with the average. Plus = higher than average.")
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
tab_best, tab_waves, tab_wind, tab_tide, tab_daily, tab_all, tab_guide = st.tabs(
    ["Best times", "Waves", "Wind", "Tides & water", "Daily summary", "All spots", "📖 How to read this"])

# st.plotly_chart shows a Plotly figure; width="stretch" makes it fill the column.
with tab_best:
    st.subheader("Surf quality by hour (daylight)")
    st.plotly_chart(make_quality_chart(daylight_hours, now, w_factor, w_unit), width="stretch")
    st.caption(f"Good: swell period of {good_period} s or more and wind up to {wind_text(good_wind, w_unit)}. "
               f"Okay: period of {good_period - 2} s or more and wind up to {wind_text(good_wind + 5, w_unit)}. Poor: everything else. "
               "On top of that: onshore wind and swell from the wrong direction lower the rating one level, "
               f"offshore wind counts as {wind_text(5, w_unit)} lighter, and wave height is checked against your level. "
               "Change the limits in the sidebar. The dashed line marks the current hour.")

with tab_waves:
    wave_col1, wave_col2, wave_col3 = st.columns(3)
    with wave_col1:
        st.subheader(f"Wave height ({h_unit})")
        st.plotly_chart(make_line_chart(marine_df["wave_height"] * h_factor, now, h_unit), width="stretch")
    with wave_col2:
        st.subheader(f"Swell wave height ({h_unit})")
        st.plotly_chart(make_line_chart(marine_df["swell_wave_height"] * h_factor, now, h_unit), width="stretch")
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
    st.subheader(f"Wind speed ({w_unit}) and direction")
    st.plotly_chart(make_wind_chart(wind_df, now, w_factor, w_unit), width="stretch")
    st.caption("Arrows show where the wind blows towards, every 3 hours.")
    st.subheader("Wind every 3 hours")
    st.dataframe(table)

with tab_tide:
    tide_col1, tide_col2 = st.columns(2)
    with tide_col1:
        st.subheader(f"Tide ({h_unit} above/below mean sea level)")
        st.plotly_chart(make_line_chart(tide * h_factor, now, h_unit), width="stretch")
    with tide_col2:
        st.subheader(f"Water temperature ({t_unit})")
        temp = convert_temp(marine_df["sea_surface_temperature"], t_unit)   # a whole column converted at once
        water_fig = make_line_chart(temp, now, t_unit)
        # Plotly zooms in as far as it can, which would make a change of 0.4 °C look dramatic.
        # So the axis shows at least 3 °C (5.4 °F) around the data.
        pad = 2.7 if t_unit == "°F" else 1.5
        water_fig.update_yaxes(range=[temp.min() - pad, temp.max() + pad])
        st.plotly_chart(water_fig, width="stretch")
    st.caption("Tide data comes from a global sea-level model with a coarse grid. "
               "It shows the rough rhythm of high and low tide, not an exact local tide table.")

with tab_daily:
    daily_col1, daily_col2 = st.columns(2)
    with daily_col1:
        st.subheader(f"Wave height ({h_unit})")
        st.dataframe(daily_waves)
    with daily_col2:
        st.subheader(f"Wind speed ({w_unit})")
        st.dataframe(daily_wind)

with tab_all:
    st.subheader("Where is it good?")
    rows = []
    for spot in SPOTS:
        try:
            rows.append(summarize_spot(spot, rules, skill, h_unit, w_unit))
        except (requests.RequestException, KeyError):
            st.warning(f"No data for {spot} right now.")   # one failing spot shouldn't break the whole table
    if rows:
        sort_by = st.radio("Rank spots by", ["This week", "Right now"], horizontal=True)
        overview = pd.DataFrame(rows)
        if sort_by == "This week":
            # highest week score first; ties are decided by the swell period
            overview = overview.sort_values(["_week", "_period"], ascending=False)
        else:
            # best rating right now first; spots with the same rating are sorted by swell period, longest first
            overview = overview.sort_values(["_rank", "_period"], ascending=False)
        winner = overview.iloc[0]   # the first row after sorting is the top spot
        st.markdown(f"🏆 **{winner['Spot']}** is the best spot {'this week' if sort_by == 'This week' else 'right now'}.")
        # column_config can change how a column looks: here the score becomes a small bar from 0 to 100
        st.dataframe(overview.drop(columns=["_rank", "_period", "_week"]), hide_index=True,
                     column_config={"Week score": st.column_config.ProgressColumn("Week score", min_value=0, max_value=100, format="%d")})
    st.caption("Uses the rating rules from the sidebar. Times are local to each spot; "
               "\"Best time\" is the best daylight stretch still ahead today, or tomorrow once the day is over. "
               "\"Week score\" is the average rating of all daylight hours in the next 7 days: 0 means always poor, 100 always good.")

# A plain-language guide for people who don't surf. st.markdown writes text with simple formatting:
# **bold**, bullet lists with "-", and "###" for small headings.
with tab_guide:
    st.subheader("How to read this forecast")
    st.markdown("""
The big coloured card at the top is the short answer. These notes explain the numbers behind it.
(The examples below use metres, knots and °C. You can switch units in the sidebar.)

### Swell period (seconds), the most important number
The time between two waves. **Longer is better.**
- **Under 8 s:** short, choppy waves made by local wind. Weak and messy.
- **8–10 s:** surfable, but not great.
- **10 s and more:** organised waves that have travelled far across the ocean. Powerful and clean.
- **14 s and more:** very powerful, often big. Mostly for experienced surfers.

### Wave height (metres)
How tall the waves are. Bigger is not automatically better. It has to match your level:
beginners are comfortable up to about 1.2 m, intermediates up to about 2 m, and advanced surfers handle 4 m and more.
Very small waves are too weak to ride, and very big ones are dangerous. The app lowers the rating if the size doesn't suit your level.

### Wind speed (knots)
**Lighter is better.** 1 knot is about 1.85 km/h.
- **Under 10 kn:** light, waves stay smooth.
- **10–15 kn:** noticeable, the surface gets bumpy.
- **Over 15 kn:** strong, the waves become messy.

### Wind direction: offshore, onshore or cross-shore
This matters as much as wind speed. The words describe where the wind blows relative to the beach:
- **Offshore** (from the land towards the sea): the best case. It holds the wave face up and smooth, like a clean wall. 🟢
- **Cross-shore** (along the beach): neutral. A bit bumpy, but surfable. 🟡
- **Onshore** (from the sea towards the land): the worst case. It pushes the waves over early and makes the surface choppy and messy. 🔴

The compass letter next to the wind speed is where the wind comes **from**: "6 kn N" is a wind from the north.
Each spot faces a different way, so the same wind can be offshore at one spot and onshore at another.

### Swell direction
Waves come from a certain compass direction, just like wind. Every spot only works well with swell from certain directions,
because other directions are blocked by land or arrive at a bad angle. If the direction doesn't fit, the rating drops.

### Tide
The sea level rises and falls twice a day. Some spots work better at low tide, others at high tide, and many are best in the middle.
The app shows a rough tide curve from a global model. It is not an exact tide table.

### Water temperature
- **Above 24 °C:** boardshorts or a thin top.
- **20–24 °C:** a thin wetsuit (a 2 mm "shorty" or 3/2).
- **16–20 °C:** a 4/3 wetsuit.
- **Under 16 °C:** a thick wetsuit with boots, maybe gloves and a hood.

### Wave power (kW/m)
A rough measure of how much energy the waves carry (0.49 × height² × period). Since height counts squared,
a 2 m wave is four times as powerful as a 1 m wave. Higher means punchier, more forceful waves.

### How the rating works
**Good** means a swell period of 10 s or more and wind of 10 knots or less. **Okay** means 8 s or more and up to 15 knots.
Everything else is **Poor**. Then the spot's rules adjust it: onshore wind or a wrong swell direction lowers it by one level,
offshore wind counts as 5 knots lighter, and the wave height is compared with your level.
You can change the limits in the sidebar under "Advanced: rating limits".
""")

# An expander hides its content until the user clicks it.
with st.expander("Raw hourly data"):
    st.dataframe(marine_df)

# Open-Meteo's free API asks for a credit (data licence: CC BY 4.0).
st.caption("Weather and marine data by [Open-Meteo.com](https://open-meteo.com/) "
           "(CC BY 4.0). Surf ratings are a simple rule of thumb, not professional advice.")
