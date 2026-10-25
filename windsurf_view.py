"""The windsurf page: everything that is drawn when the mode switch is on "Windsurf".

It is built like the surf page in app.py (verdict card, key numbers, week at a glance, charts, guide),
but the numbers and the rating are about wind: speed, gusts, direction, and which sail fits.
app.py calls show_windsurf() once per page run, after the choices at the top were made.
"""
import requests
import pandas as pd
import streamlit as st

from forecast_data import get_marine_data, get_wind_data, get_sun_data, get_load_time, to_table
from charts import make_line_chart, make_wind_chart, make_windsurf_chart
from surf_logic import (degrees_to_compass, find_best_time, best_per_day, make_sun_times, daylight_only,
                        next_turning_point, wetsuit_for, convert_temp, wind_text, day_range, range_text, HEIGHT_FACTORS, WIND_FACTORS)
from windsurf_logic import (WINDSURF_SPOT_INFO, WIND_RANGES, GUST_LIMITS, windsurf_wind_side, wind_fit,
                            gust_label, rate_for_windsurf, rate_windsurf_hours, sail_size, windsurf_warning)

# Colours and texts for the verdict card and the week tiles
TILE_COLORS = {"Good": "#1b9e77", "Okay": "#d68a00", "Poor": "#6b7280"}
VERDICTS = {"Good": "Good – go windsurfing!", "Okay": "Okay – sailable", "Poor": "Poor – skip it"}

# Colours of the status pills on the key-number cards
FIT_COLORS = {"good wind": "green", "a bit light": "orange", "a bit strong": "orange", "too light": "red", "too strong": "red"}
GUST_COLORS = {"steady": "green", "gusty": "orange", "very gusty": "red"}
# For each wind direction: the pill text, the pill colour and a short note
SIDE_INFO = {
    "Onshore": ("safe", "green", "blows you back to the beach"),
    "Side-onshore": ("safe", "green", "safe and great for freestyle"),
    "Cross-shore": ("good", "green", "along the beach, the classic"),
    "Side-offshore": ("caution", "orange", "can push you away from the beach"),
    "Offshore": ("dangerous", "red", "can blow you out to sea"),
}


def show_windsurf(spot_name, lat, lon, skill, weight, h_unit, w_unit, t_unit):
    h_factor = HEIGHT_FACTORS[h_unit]   # how many ft in one metre (or 1 for metres)
    w_factor = WIND_FACTORS[w_unit]     # how many km/h or mph in one knot (or 1 for knots)
    spot_info = WINDSURF_SPOT_INFO[spot_name]

    # ---------- 1. Load and prepare all the data ----------
    # The same steps as on the surf page: load, turn into tables, stop with a message if something fails.
    try:
        marine_data, timezone = get_marine_data(lat, lon)   # tide and water temperature (the waves are not used)
        wind_data = get_wind_data(lat, lon)                 # wind speed, direction and gusts
        sun_times = make_sun_times(get_sun_data(lat, lon))  # {date: (sunrise, sunset)}
    except (requests.RequestException, KeyError) as error:
        st.error(f"Couldn't load the forecast data. (Details: {error!r})")
        st.stop()   # stop the script here, since everything below needs this data
    marine_df = to_table(marine_data)   # only used for the tide and the water temperature
    wind_df = to_table(wind_data)
    loaded_at = get_load_time(lat, lon).tz_convert(timezone)

    # The current hour at the spot (see the surf page for how this works)
    now = pd.Timestamp.now(tz=timezone).floor("h").tz_localize(None)

    current_wind = wind_df.loc[now, "wind_speed_10m"]
    current_gust = wind_df.loc[now, "wind_gusts_10m"]
    current_direction = wind_df.loc[now, "wind_direction_10m"]
    current_side = windsurf_wind_side(current_direction, spot_info["faces"])
    rating, reason = rate_for_windsurf(current_wind, current_gust, current_direction, spot_name, skill, wind_unit=w_unit)

    # Rating for every single hour, then only the daylight hours, then the best stretch
    hours = rate_windsurf_hours(wind_df, spot_name, skill)
    daylight_hours = daylight_only(hours, sun_times)
    day_label, best_level, best_start, best_end = find_best_time(daylight_hours, now)

    # Tide and water temperature right now
    tide = marine_df["sea_level_height_msl"]
    tide_now = tide.loc[now]
    tide_trend = "rising" if tide.loc[now + pd.Timedelta(hours=1)] > tide_now else "falling"
    tide_kind, tide_time = next_turning_point(tide, now)
    water_temp = marine_df.loc[now, "sea_surface_temperature"]

    # ---------- 2. Display ----------
    view_spot, view_guide = st.tabs(["🌬️ Spot forecast", "📖 Windsurf guide"])

    with view_spot:
        sunrise_today, sunset_today = sun_times[now.date()]
        st.caption(f"{spot_name} ({lat}, {lon}) · local time {now:%a %d %b, %H:%M} · "
                   f"sunrise {sunrise_today:%H:%M}, sunset {sunset_today:%H:%M}")

        if best_level == "Poor":   # if even the best hours are poor, don't call it a "best time"
            best_line = f"No good window {day_label}"
        else:
            best_line = f"Best time {day_label}: {best_start:%H:%M}–{best_end:%H:%M} ({best_level.lower()} conditions)"

        # Warnings for the verdict card: offshore wind right now, and why the best window ends
        warnings = []
        if current_side in ("Offshore", "Side-offshore"):
            warnings.append("The wind blows away from the beach. It can push you out to sea, so only go out with a rescue plan.")
        if best_level != "Poor":
            end_warning = windsurf_warning(wind_df, spot_name, skill, best_end)
            if end_warning:
                warnings.append(end_warning)
        warning_line = "".join(f'<div style="font-size:0.95rem; margin-top:0.5rem;">⚠️ {text}</div>' for text in warnings)

        # The verdict card: one big coloured box with the answer to "should I go?"
        st.markdown(
            f'<div style="background:{TILE_COLORS[rating]}; color:white; padding:1.2rem 1.6rem; border-radius:12px; margin:0.5rem 0 1rem 0;">'
            f'<div style="font-size:0.9rem; opacity:0.9;">Right now at {spot_name}</div>'
            f'<div style="font-size:2.4rem; font-weight:700; line-height:1.2;">{VERDICTS[rating]}</div>'
            f'<div style="font-size:1rem; margin-top:0.3rem;">{reason[0].upper() + reason[1:]}</div>'
            f'<div style="font-size:1.1rem; font-weight:600; margin-top:0.6rem;">{best_line}</div>'
            f'{warning_line}'
            f'</div>',
            unsafe_allow_html=True)

        # The four numbers that matter most. Same build as on the surf page: a big number,
        # a coloured pill (the "delta" of st.metric) and one grey caption line.
        spread = current_gust - current_wind
        side_pill, side_color, side_note = SIDE_INFO[current_side]
        sail = sail_size(weight, current_wind, current_gust)

        key1, key2, key3, key4 = st.columns(4)
        with key1:
            fit = wind_fit(current_wind, skill)
            st.metric("Wind", f"{current_wind * w_factor:.0f} {w_unit} {degrees_to_compass(current_direction)}",
                      delta=fit, delta_color=FIT_COLORS[fit], delta_arrow="off",
                      help="How strong the wind is and where it blows from. Windsurfing needs wind, but how much depends on your level.")
            st.caption(f"for {skill.lower()} level")
        with key2:
            gusts = gust_label(current_wind, current_gust, skill)
            st.metric("Gusts", f"{current_gust * w_factor:.0f} {w_unit}",
                      delta=gusts, delta_color=GUST_COLORS[gusts], delta_arrow="off",
                      help="Short bursts of stronger wind. The more they differ from the average wind, the harder it is to stay on the board.")
            st.caption(f"+{spread * w_factor:.0f} {w_unit} above the average")
        with key3:
            st.metric("Wind direction", current_side, delta=side_pill, delta_color=side_color, delta_arrow="off",
                      help="Where the wind blows from, compared with the beach. Wind that blows towards the beach is safe. Wind that blows away from it can take you out to sea.")
            st.caption(side_note)
        with key4:
            st.metric("Sail size", "–" if sail is None else f"{sail:.1f} m²",
                      delta="too light" if sail is None else f"for {weight:.0f} kg", delta_color="red" if sail is None else "gray", delta_arrow="off",
                      help="A rule of thumb from your weight and the wind. Bigger sails for lighter wind. Gusts make it a bit smaller. Check it against your own gear chart.")
            st.caption("not enough wind to get going" if sail is None else "rough guide")

        # "This week at a glance": one coloured tile per day with that day's best rating and time window
        st.subheader("This week at a glance")
        week = best_per_day(daylight_hours, now)
        for column, (date, level, start, end) in zip(st.columns(len(week)), week):
            day_name = "Today" if date == now.date() else f"{date:%a %d}"
            window = "–" if level == "Poor" else f"{start:%H:%M}–{end:%H:%M}"
            # the core number for windsurfing: how strong the wind is on that day (daylight hours)
            low, high = day_range(wind_df["wind_speed_10m"] * w_factor, daylight_hours, now, date)
            with column:
                st.markdown(
                    f'<div style="background:{TILE_COLORS[level]}; color:white; padding:0.7rem 0.4rem; border-radius:10px; text-align:center; margin-bottom:0.6rem;">'
                    f'<div style="font-size:0.85rem; opacity:0.9;">{day_name}</div>'
                    f'<div style="font-size:1.2rem; font-weight:700;">{level}</div>'
                    f'<div style="font-size:0.8rem;">{window}</div>'
                    f'<div style="font-size:0.8rem; margin-top:0.2rem;">{range_text(low, high, w_unit, decimals=0)}</div>'
                    f'</div>',
                    unsafe_allow_html=True)
        st.caption("Each tile shows the best daylight stretch of that day and the wind range over the daylight hours. "
                   "Further ahead, forecasts get less reliable.")

        # Secondary data hides in an expander until someone wants it
        with st.expander("More conditions: water temperature, tide"):
            more1, more2 = st.columns(2)
            with more1:
                st.metric("Water temperature", f"{convert_temp(water_temp, t_unit):.1f} {t_unit}")
                st.caption(f"wear: {wetsuit_for(water_temp)}")
            with more2:
                st.metric("Tide", f"{tide_now * h_factor:+.1f} {h_unit}", help="Sea level compared with the average. Plus = higher than average.")
                if tide_kind:
                    st.caption(f"{tide_trend}, next {tide_kind.lower()} tide at {tide_time:%H:%M}")
                else:
                    st.caption(tide_trend)
        st.caption("New to windsurfing? The 📖 Windsurf guide tab explains what all of this means.")

        # The charts for this spot, in clickable tabs
        tab_best, tab_wind, tab_water = st.tabs(["Best times", "Wind", "Tide & water"])

        with tab_best:
            okay_from, good_from, good_to, okay_to = WIND_RANGES[skill]
            st.subheader("Windsurf conditions by hour (daylight)")
            st.plotly_chart(make_windsurf_chart(daylight_hours, now, w_factor, w_unit), width="stretch")
            st.caption(f"For {skill.lower()} level: Good is wind from {wind_text(good_from, w_unit)} to {wind_text(good_to, w_unit)}. "
                       f"Okay is {wind_text(okay_from, w_unit)} to {wind_text(okay_to, w_unit)}. Everything else is Poor. "
                       f"On top of that: offshore wind and gusts more than {wind_text(GUST_LIMITS[skill], w_unit)} above the average "
                       "lower the rating one level. "
                       "The dotted line shows the gusts, the dashed line marks the current hour.")

        with tab_wind:
            st.subheader(f"Wind speed ({w_unit}) and direction")
            st.plotly_chart(make_wind_chart(wind_df, now, w_factor, w_unit), width="stretch")
            st.caption("Arrows show where the wind blows towards, every 3 hours. The dotted line shows the gusts.")
            # One row every 3 hours with a compass label, in the chosen unit
            table = wind_df.iloc[::3].copy()
            table["compass"] = table["wind_direction_10m"].apply(degrees_to_compass)
            table[["wind_speed_10m", "wind_gusts_10m"]] = (table[["wind_speed_10m", "wind_gusts_10m"]] * w_factor).round(1)
            table = table[["wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "compass"]]   # the order of the columns
            table = table.rename(columns={"wind_speed_10m": f"Wind speed ({w_unit})", "wind_gusts_10m": f"Gusts ({w_unit})",
                                          "wind_direction_10m": "Direction (°)"})
            st.subheader("Wind every 3 hours")
            st.dataframe(table)

        with tab_water:
            water_col1, water_col2 = st.columns(2)
            with water_col1:
                st.subheader(f"Tide ({h_unit})")   # short, so the title stays on one line next to the water temperature
                st.plotly_chart(make_line_chart(tide * h_factor, now, h_unit), width="stretch")
            with water_col2:
                st.subheader(f"Water temperature ({t_unit})")
                temp = convert_temp(marine_df["sea_surface_temperature"], t_unit)   # a whole column converted at once
                water_fig = make_line_chart(temp, now, t_unit)
                pad = 2.7 if t_unit == "°F" else 1.5   # show at least 3 °C around the data, so small changes don't look dramatic
                water_fig.update_yaxes(range=[temp.min() - pad, temp.max() + pad])
                st.plotly_chart(water_fig, width="stretch")
            st.caption("Tide data comes from a global sea-level model with a coarse grid. "
                       "It shows the rough rhythm of high and low tide, not an exact local tide table.")

        # More about the spot and the tables behind the charts hide in expanders
        with st.expander(f"About {spot_name}"):
            st.write(spot_info["note"])
            st.markdown(
                f"- **The beach faces:** {degrees_to_compass(spot_info['faces'])} ({spot_info['faces']}°). "
                f"Wind from the opposite side blows away from the beach (offshore).\n"
                f"- **Forecast point:** {lat}, {lon}. The data covers a grid of a few kilometres, "
                f"so it describes the area, not one exact spot on the beach."
            )
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=9, size=1500)
            st.caption("The direction is a rough default used by the rating. It can be wrong for the exact stretch of beach.")

        with st.expander("Daily summary and raw data"):
            days = wind_df.index.date   # the calendar date of every hourly row
            daily_col1, daily_col2 = st.columns(2)
            with daily_col1:
                st.subheader(f"Wind speed ({w_unit})")
                st.dataframe((wind_df.groupby(days)["wind_speed_10m"].agg(["min", "max", "mean"]) * w_factor).round(1))
            with daily_col2:
                st.subheader(f"Gusts ({w_unit})")
                st.dataframe((wind_df.groupby(days)["wind_gusts_10m"].agg(["min", "max", "mean"]) * w_factor).round(1))
            st.subheader("Raw hourly wind data")
            st.dataframe(wind_df)

    # A plain-language guide for people who don't windsurf yet. The wind ranges are filled in from WIND_RANGES,
    # so the guide always matches the rating.
    with view_guide:
        range_lines = "\n".join(
            f"- **{level}:** {wind_text(good_from, w_unit)} to {wind_text(good_to, w_unit)} is ideal, "
            f"{wind_text(okay_from, w_unit)} to {wind_text(okay_to, w_unit)} still works"
            for level, (okay_from, good_from, good_to, okay_to) in WIND_RANGES.items()
        )
        st.subheader("How to read this windsurf forecast")
        st.markdown(f"""
The big coloured card at the top is the short answer. These notes explain the numbers behind it.
This page is about flat-water and freestyle windsurfing, where **wind** is what counts. Wave size is not part of the rating.

### Wind speed
Windsurfing needs wind: too little and you just stand there, too much and the gear is hard to control. How much is right depends on your level:
{range_lines}

1 knot is about 1.85 km/h. You can switch units in the sidebar.

### Gusts
Gusts are short bursts of stronger wind. If the gusts are much stronger than the average wind, the sail pulls unevenly and it is easy to be thrown off.
**Steady** wind is easier to sail, especially for beginners. The app lowers the rating if the gusts are far above the average.

### Wind direction: onshore, offshore or in between
For windsurfing the direction is also a **safety** question, because you cannot sail straight into the wind and the wind carries you with it:
- **Onshore / side-onshore** (towards the beach): safe. If something goes wrong, the wind pushes you back to the beach. 🟢
- **Cross-shore** (along the beach): the classic windsurf wind. Good for flat water and freestyle. 🟢
- **Side-offshore** (a bit away from the beach): be careful, it can push you away from the beach. 🟠
- **Offshore** (from the land out to sea): **dangerous**. It can blow you out to sea and it is hard to come back. Beginners should stay on land. 🔴

The compass letter next to the wind speed is where the wind comes **from**: "18 kn W" is a wind from the west.

### Sail size
The bigger the sail, the more power it catches. In light wind you need a big sail, in strong wind a small one, and a heavier sailor can handle a bigger sail.
The app gives a rough guide from your weight and the wind (gusts make it a bit smaller). It is a rule of thumb, so compare it with the chart of your own gear or ask at the surf school.

### Tide
The sea level rises and falls twice a day, and on this coast the difference is large. At low tide the water can be shallow and a long way out. The app shows a rough tide curve from a global model. It is not an exact tide table.

### Water temperature
- **Above 24 °C:** boardshorts or a thin top.
- **20–24 °C:** a thin wetsuit (a 2 mm "shorty" or 3/2).
- **16–20 °C:** a 4/3 wetsuit.
- **Under 16 °C:** a thick wetsuit with boots, maybe gloves and a hood.

The wind makes it feel colder on the water, so if you are unsure, take the thicker suit.

### How the rating works
**Good** means the wind is in the ideal range for your level. **Okay** means it is a bit lighter or stronger. Everything else is **Poor**.
Then it is adjusted: offshore wind and uneven gusts lower the rating by one level (offshore wind is always Poor for beginners).
""")

    # Open-Meteo's free API asks for a credit (data licence: CC BY 4.0).
    st.caption(f"Forecast loaded at {loaded_at:%H:%M} ({spot_name} time). It refreshes about once an hour. "
               "Weather and marine data by [Open-Meteo.com](https://open-meteo.com/) "
               "(CC BY 4.0). Windsurf ratings are a simple rule of thumb, not professional advice.")
