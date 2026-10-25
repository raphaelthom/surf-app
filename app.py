import streamlit as st
import requests 
import pandas as pd

# Loading the data from the API and drawing the charts moved into their own files,
# because the windsurf page needs them too.
from forecast_data import get_marine_data, get_wind_data, get_sun_data, get_load_time, to_table
from charts import make_line_chart, make_wind_chart, make_quality_chart

# The surf logic (compass labels, rating, best time, next tide) lives in surf_logic.py
from surf_logic import (degrees_to_compass, rate_for_spot, rate_hours, find_best_time, best_per_day, next_turning_point, make_sun_times, daylight_only,
                        HEIGHT_FACTORS, WIND_FACTORS, convert_temp, wind_text, week_score, best_day, wetsuit_for, swell_trend, wind_warning,
                        wind_type, swell_in_window, wave_power, SPOT_INFO, SKILL_LEVELS, day_range, range_text, SPOT_BREAKS, rate_breaks)

# The windsurf page: everything it draws is in windsurf_view.py (its rating rules are in windsurf_logic.py)
from windsurf_view import show_windsurf

SPOTS = {
    "Lisbon": (38.65, -9.40),
    "San Diego": (32.70, -117.30),
    "Siargao": (9.80, 126.20),
    "Lombok": (-8.90, 116.30),
    "Taghazout": (30.55, -9.80)
}

# The windsurf spots are their own list (a windsurf spot is not the same as a surf spot)
WINDSURF_SPOTS = {
    "La Linière (Noirmoutier)": (47.025, -2.283),
}

RATING_ICONS = {"Good": "🟢", "Okay": "🟡", "Poor": "⚪"}   # for the "All spots" table


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
st.set_page_config(page_title="Surf & Windsurf Forecast", page_icon="🏄", layout="wide")

# Remember the choices in the page address (e.g. ?spot=Lombok&level=Beginner), so a bookmark or a shared link
# opens the same setup. Streamlit keeps each widget's value in st.session_state under its key.
# On the first run of a visit that value is empty, so it is filled from the address if the address has a valid one.
st.session_state.setdefault("level", "Intermediate")   # the default surf level
st.session_state.setdefault("mode", "Surf")            # "Surf" or "Windsurf"
st.session_state.setdefault("weight", 75)              # the default weight in kg, for the windsurf sail size
choices = {   # key of the widget: its allowed values
    "mode": ["Surf", "Windsurf"], "spot": list(SPOTS), "wspot": list(WINDSURF_SPOTS), "level": list(SKILL_LEVELS),
    "height": list(HEIGHT_FACTORS), "wind": list(WIND_FACTORS), "temp": ["°C", "°F"],
}
for key, options in choices.items():
    if st.query_params.get(key) in options and key not in st.session_state.get("restored", set()):
        st.session_state[key] = st.query_params[key]
st.session_state["restored"] = set(choices)   # only restore once per visit, so later clicks win

# Streamlit forgets a widget's value when the widget is not drawn in a run. The surf spot is not drawn in
# windsurf mode (and the other way round), so copying each value onto itself keeps it until you switch back.
for key in ["spot", "wspot", "weight"]:
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]

# Which mode is on? The radio below stores its value under the key "mode". At the start of a run that value
# is already there (restored from the address or from your last click), so the title can use it before the radio is drawn.
st.title("🏄 Surf Forecast" if st.session_state["mode"] == "Surf" else "🌬️ Windsurf Forecast")

# The mode switch: one click swaps the whole dashboard. format_func only changes the label that is shown,
# the value stays "Surf" or "Windsurf" (which keeps the page address short).
mode = st.radio("Mode", ["Surf", "Windsurf"], horizontal=True, key="mode", label_visibility="collapsed",
                format_func=lambda m: {"Surf": "🏄 Surf", "Windsurf": "🌬️ Windsurf"}[m])

# Dropdowns side by side: [2, 1] makes the first column twice as wide as the second
if mode == "Surf":
    pick_col1, pick_col2 = st.columns([2, 1])
    with pick_col1:
        spot_name = st.selectbox("Choose a surf spot", list(SPOTS.keys()), key="spot")
    with pick_col2:
        skill = st.selectbox("Your surf level", list(SKILL_LEVELS.keys()), key="level")
    too_small, too_big = SKILL_LEVELS[skill]   # the wave height range that is comfortable at your level
    coords = SPOTS[spot_name]
    lat, lon = coords
else:
    # Windsurf mode: the spot, your level (the same three levels) and your weight, which decides the sail size
    pick_col1, pick_col2, pick_col3 = st.columns([2, 1, 1])
    with pick_col1:
        windsurf_spot = st.selectbox("Choose a windsurf spot", list(WINDSURF_SPOTS.keys()), key="wspot")
    with pick_col2:
        windsurf_level = st.selectbox("Your windsurf level", list(SKILL_LEVELS.keys()), key="level")
    with pick_col3:
        weight = st.number_input("Your weight (kg)", min_value=40, max_value=150, step=1, key="weight")

# A short description for the "About" section of the spot view. The forecast point is a spot in the water near the named place.
SPOT_NOTES = {
    "Lisbon": "The forecast point lies off the coast west of Lisbon, near Cascais and Carcavelos. "
              "These beaches catch Atlantic swell, and the coast is known for beach breaks close to the city.",
    "San Diego": "The forecast point lies off Point Loma and Ocean Beach in San Diego. "
                 "It catches Pacific swell, and the water is cooler than the sunny weather suggests.",
    "Siargao": "The forecast point lies off the east coast of Siargao Island near General Luna, "
               "the island famous for Cloud 9 and its reef breaks facing the Pacific.",
    "Lombok": "The forecast point lies off the south coast of Lombok, near Kuta and Mawi. "
              "The south coast catches Indian Ocean swell and has beach and reef breaks.",
    # The text is shown with st.write, so the list in it is drawn as bullet points
    "Taghazout": "The forecast point lies off Taghazout on Morocco's Atlantic coast, a stretch of right-hand point breaks. "
                 "The weather data covers an area of several kilometres, so it is the same for all the breaks below. "
                 "What differs is which swell and wind each one likes:\n"
                 "- **Anchor Point:** a long right over sand and rock. Best on mid-sized to big NW swell with east wind, "
                 "mostly low to mid tide. Intermediate and advanced.\n"
                 "- **Killer Point:** a heavy, hollow right below a cliff, a bit north-west of Anchor Point. Likes W to NW swell "
                 "and east wind, most tides. Experienced surfers, often crowded.\n"
                 "- **Hash Point:** a mellow, fast right in the middle of the village, partly sheltered by Cap Ghir. Likes NW swell "
                 "and NE wind, all tides. All levels.\n"
                 "- **Panorama:** rights over sand and reef south of the village. Works from small waves up to mid-sized NW swell, "
                 "most tides. Friendly for beginners and intermediates.\n\n"
                 "The section \"Which break fits best?\" on the forecast page ranks them for the best time of the day. "
                 "These notes come from public surf guides, so check them with a local surf school.",
}

# The sidebar is a panel on the left. The sliders let you set what "Good" means to you;
# "Okay" is derived from them: 2 s less swell period and 5 knots more wind are still okay.
# They sit inside an expander because most people never need to change them.
with st.sidebar:
    st.header("Units")
    # st.radio shows all options at once; horizontal=True puts them in one row
    h_unit = st.radio("Wave height", list(HEIGHT_FACTORS), horizontal=True, key="height")
    w_unit = st.radio("Wind speed", list(WIND_FACTORS), horizontal=True, key="wind")
    t_unit = st.radio("Temperature", ["°C", "°F"], horizontal=True, key="temp")
    if mode == "Surf":   # these limits are about swell, so they only belong to the surf mode
        with st.expander("Advanced: rating limits"):
            good_period = st.slider("Good: swell period at least (s)", 6, 16, 10)   # (label, min, max, start value)
            good_wind = st.slider("Good: wind at most (knots)", 0, 25, 10)   # the limits are always in knots
            st.caption(f"Okay: swell period at least {good_period - 2} s and wind up to {good_wind + 5} knots. "
                       "Everything else is Poor.")
# Write the choices into the page address (after all widgets exist, so these are the final values).
# Only choices that differ from the defaults are written, so the default view keeps a clean address
# and a link only carries what you changed.
# The values come from st.session_state, where every widget keeps its current value under its key.
defaults = {"mode": "Surf", "spot": list(SPOTS)[0], "wspot": list(WINDSURF_SPOTS)[0], "level": "Intermediate",
            "height": "m", "wind": "kn", "temp": "°C"}
for key, default in defaults.items():
    value = st.session_state.get(key, default)   # a choice that was never drawn counts as the default
    if value != default:
        st.query_params[key] = value
    elif key in st.query_params:
        del st.query_params[key]   # back to the default: remove it from the address again

# Windsurf mode: the windsurf page draws everything and st.stop() ends the script here,
# so the surf code below only runs in surf mode.
if mode == "Windsurf":
    wlat, wlon = WINDSURF_SPOTS[windsurf_spot]
    show_windsurf(windsurf_spot, wlat, wlon, windsurf_level, weight, h_unit, w_unit, t_unit)
    st.stop()

# A dictionary with the four limits. Writing **rules in a function call hands over every entry
# as a separate argument, like good_period=..., good_wind=..., okay_period=..., okay_wind=...
rules = dict(good_period=good_period, good_wind=good_wind, okay_period=good_period - 2, okay_wind=good_wind + 5)

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

loaded_at = get_load_time(lat, lon).tz_convert(timezone)   # shown in the spot's local time

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
table[["wind_speed_10m", "wind_gusts_10m"]] = (table[["wind_speed_10m", "wind_gusts_10m"]] * w_factor).round(1)   # speed and gusts in the chosen unit
table = table[["wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "compass"]]   # the order of the columns
table = table.rename(columns={"wind_speed_10m": f"Wind speed ({w_unit})", "wind_gusts_10m": f"Gusts ({w_unit})",
                              "wind_direction_10m": "Direction (°)"})

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
# Three views, one for each job: one spot in detail, all spots compared, and a guide for beginners.
# Everything inside "with view_spot:" etc. is drawn inside that tab. The "with" blocks can be entered again later.
view_spot, view_compare, view_guide = st.tabs(["🏄 Spot forecast", "🌍 Compare spots", "📖 Beginner's guide"])

with view_spot:
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
    # Every card has the same three parts: a big number, a small coloured "pill" with the status (the "delta"
    # of st.metric) and one grey caption line. Same parts, same height, so the row looks tidy.
    # delta_color sets the pill colour; delta_arrow="off" hides the little arrow.
    if current_wave < too_small:
        size_pill, size_color = "too small", "orange"
    elif current_wave > too_big:
        size_pill, size_color = "too big", "red"
    else:
        size_pill, size_color = "good size", "green"

    # the swell trend: a grey pill with an arrow up (building) or down (dropping), or just "steady"
    if trend == "steady":
        trend_pill, trend_arrow = "steady", "off"
    else:
        trend_pill = f"{trend}, {trend_change:+.0f}% in 6 h"
        trend_arrow = "up" if trend == "building" else "down"

    # the wind type decides the colour: offshore is the best case, onshore the worst
    wind_colors = {"Offshore": "green", "Cross-shore": "gray", "Onshore": "red"}

    key1, key2, key3, key4 = st.columns(4)
    with key1:
        st.metric("Wave height", f"{current_wave * h_factor:.1f} {h_unit}", delta=size_pill, delta_color=size_color, delta_arrow="off",
                  help="How tall the waves are. Bigger is not always better: it has to match your level.")
        st.caption(f"for {skill.lower()} level")
    with key2:
        st.metric("Swell", f"{current_period:.1f} s {degrees_to_compass(current_swell_direction)}",
                  delta=trend_pill, delta_color="gray", delta_arrow=trend_arrow,
                  help="Seconds between waves, and the direction they come from. A longer period means more powerful, better organised waves. The pill shows whether the swell is building or dropping over the next 6 hours.")
        st.caption("direction fits this spot" if swell_ok else "direction is off for this spot")
    with key3:
        st.metric("Wind", f"{current_wind * w_factor:.0f} {w_unit} {degrees_to_compass(current_direction)}",
                  delta=current_wind_type.lower(), delta_color=wind_colors[current_wind_type], delta_arrow="off",
                  help="Wind speed and where it blows from. Light wind, blowing from land to sea (offshore), is best.")
        st.caption(WIND_NOTES[current_wind_type])
    with key4:
        # wetsuit_for gives e.g. "thin wetsuit (shorty or 3/2)"; the pill shows the part before the bracket
        st.metric("Water temperature", f"{convert_temp(water_temp, t_unit):.1f} {t_unit}",
                  delta=wetsuit_for(water_temp).split(" (")[0], delta_color="gray", delta_arrow="off",
                  help=f"A wetsuit is usually needed below about {convert_temp(22, t_unit):.0f} {t_unit}.")   # water_temp is always in °C here, whatever unit is shown
        st.caption("what to wear")

    # "This week at a glance": one coloured tile per day with that day's best rating and time window.
    # best_per_day returns a list of (date, rating, start, end); one column per day.
    st.subheader("This week at a glance")
    week = best_per_day(daylight_hours, now)
    for column, (date, level, start, end) in zip(st.columns(len(week)), week):
        day_name = "Today" if date == now.date() else f"{date:%a %d}"
        window = "–" if level == "Poor" else f"{start:%H:%M}–{end:%H:%M}"   # no window to show if even the best hours are poor
        # the core number for surfing: how big the waves are on that day (daylight hours)
        low, high = day_range(marine_df["wave_height"] * h_factor, daylight_hours, now, date)
        with column:
            st.markdown(
                f'<div style="background:{TILE_COLORS[level]}; color:white; padding:0.7rem 0.4rem; border-radius:10px; text-align:center; margin-bottom:0.6rem;">'
                f'<div style="font-size:0.85rem; opacity:0.9;">{day_name}</div>'
                f'<div style="font-size:1.2rem; font-weight:700;">{level}</div>'
                f'<div style="font-size:0.8rem;">{window}</div>'
                f'<div style="font-size:0.8rem; margin-top:0.2rem;">{range_text(low, high, h_unit)}</div>'
                f'</div>',
                unsafe_allow_html=True)
    st.caption("Each tile shows the best daylight stretch of that day and the wave height range over the daylight hours. "
               "Further ahead, forecasts get less reliable.")

    # Spots with several breaks (Taghazout): which break fits the conditions best? The weather data is the same
    # for all of them, but each break likes a different swell and wind direction (see SPOT_BREAKS in surf_logic.py).
    if spot_name in SPOT_BREAKS:
        # look at the start of the best window, or at the current hour if there is no good window
        check_time = best_start if best_level != "Poor" else now
        when = f"{day_label} at {check_time:%H:%M}" if best_level != "Poor" else "right now"
        st.subheader("Which break fits best?")
        for break_name, break_rating, break_reason in rate_breaks(
                spot_name, marine_df.loc[check_time, "swell_wave_period"], wind_df.loc[check_time, "wind_speed_10m"],
                wind_df.loc[check_time, "wind_direction_10m"], marine_df.loc[check_time, "swell_wave_direction"],
                marine_df.loc[check_time, "wave_height"], skill, wind_unit=w_unit, **rules):
            st.markdown(f"{RATING_ICONS[break_rating]} **{break_name}**: {break_rating}. {break_reason[0].upper() + break_reason[1:]}")
        st.caption(f"For {when}. The weather data is the same for all breaks, so this only compares which swell and wind "
                   "direction each break likes. It is a guide, not a promise. Details in the \"About\" section below.")

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
    st.caption("New to surfing? The 📖 Beginner's guide tab explains what all of this means.")

    # The charts for this spot: st.tabs puts them into clickable tabs, so the page doesn't become one long scroll.
    tab_best, tab_waves, tab_wind, tab_tide = st.tabs(["Best times", "Waves", "Wind", "Tides & water"])

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

    # More about the spot and the tables behind the charts hide in expanders
    with st.expander(f"About {spot_name}"):
        st.write(SPOT_NOTES[spot_name])
        low, high = spot_info["swell_window"]
        st.markdown(
            f"- **The beach faces:** {degrees_to_compass(spot_info['faces'])} ({spot_info['faces']}°). "
            f"Wind from the opposite side is offshore.\n"
            f"- **Swell that works here:** from {degrees_to_compass(low)} to {degrees_to_compass(high)} ({low}° to {high}°)\n"
            f"- **Forecast point:** {lat}, {lon}, slightly offshore. The wave data covers a grid of a few kilometres, "
            f"so it describes the area, not one exact break."
        )
        # st.map shows a map with a dot for each row of the table (the columns have to be called lat and lon)
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=8, size=1500)
        st.caption("The directions are rough defaults used by the rating. They can be wrong for individual breaks.")


    with st.expander("Daily summary and raw data"):
        daily_col1, daily_col2 = st.columns(2)
        with daily_col1:
            st.subheader(f"Wave height ({h_unit})")
            st.dataframe(daily_waves)
        with daily_col2:
            st.subheader(f"Wind speed ({w_unit})")
            st.dataframe(daily_wind)
        st.subheader("Raw hourly data")
        st.dataframe(marine_df)

with view_compare:
    st.subheader("Where is it good?")
    st.caption(f"Ranked for your surf level: {skill.lower()}. Change it at the top of the page.")
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
with view_guide:
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


# Open-Meteo's free API asks for a credit (data licence: CC BY 4.0).
st.caption(f"Forecast loaded at {loaded_at:%H:%M} ({spot_name} time). It refreshes about once an hour. "
           "Weather and marine data by [Open-Meteo.com](https://open-meteo.com/) "
           "(CC BY 4.0). Surf ratings are a simple rule of thumb, not professional advice.")
