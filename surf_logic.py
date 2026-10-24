"""The surf logic: small functions that turn numbers into compass labels, ratings and best times.

They live in their own file (and not in app.py) so tests can import them without
starting the whole Streamlit page.
"""
import pandas as pd

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Unit conversion. All data is stored in metres, knots and °C; only what the user SEES is converted.
# The factors say how much of the new unit one metre / one knot is.
HEIGHT_FACTORS = {"m": 1.0, "ft": 3.28084}
WIND_FACTORS = {"kn": 1.0, "km/h": 1.852, "mph": 1.15078}

def convert_temp(celsius, unit):
    return celsius * 9 / 5 + 32 if unit == "°F" else celsius   # works for a single number and for a whole column

# A wind speed given in knots as text in the chosen unit, e.g. 10 -> "10 knots" or "19 km/h"
def wind_text(knots, unit="kn"):
    return f"{knots * WIND_FACTORS[unit]:.0f} {'knots' if unit == 'kn' else unit}"

def degrees_to_compass(degrees):
    index = round(degrees / 45) % 8 # degrees / 45 says how many 45° steps fit, and round(...) picks the nearest one. % 8 (modulo) is the remainder after dividing by 8. It makes 360° wrap around to 0, which is "N". For example, 350° / 45 ≈ 7.8 → rounds to 8 → 8 % 8 = 0 → "N".
    label = DIRECTIONS[index] # looks up the label by position. Positions start at 0.
    return label

# Rates surf conditions as "Good", "Okay" or "Poor": long swell periods and light wind
# (in knots) are better. Python checks the conditions top to bottom and uses the first true one.
# Returns two values (a tuple): the rating and a short reason for it.
# wind_unit only changes how the wind limits are written in the reason (the numbers are always knots).
# The four limits can be changed (the sliders in the app do that). If you don't pass them,
# the default values after the = signs are used, which are the original rules.
def rate_conditions(swell_wave_period, wind_speed_10m, good_period=10, good_wind=10, okay_period=8, okay_wind=15, wind_unit="kn"):
    if swell_wave_period >= good_period and wind_speed_10m <= good_wind:
        return "Good", "long swell period and light wind"
    elif swell_wave_period >= okay_period and wind_speed_10m <= okay_wind:
        # "Good" failed, so the period is under the good limit, the wind is over it, or both
        if swell_wave_period < good_period and wind_speed_10m > good_wind:
            return "Okay", "swell period is a bit short and wind is a bit strong"
        elif swell_wave_period < good_period:
            return "Okay", f"swell period is a bit short (under {good_period:g} s)"
        else:
            return "Okay", f"wind is a bit strong (over {wind_text(good_wind, wind_unit)})"
    else:
        # the "Okay" test failed too, so the period is under the okay limit, the wind is over it, or both
        if swell_wave_period < okay_period and wind_speed_10m > okay_wind:
            return "Poor", "swell period is too short and wind is too strong"
        elif swell_wave_period < okay_period:
            return "Poor", f"swell period is too short (under {okay_period:g} s)"
        else:
            return "Poor", f"wind is too strong (over {wind_text(okay_wind, wind_unit)})"

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

# ---------- Spot-specific rules ----------
# Rough defaults per spot, the values are my best guess and can be corrected:
#   "faces": the compass direction (in degrees) you look when you stand on the beach facing the sea.
#            Wind coming FROM that direction blows onto the beach (onshore); wind from the
#            opposite direction blows off the land (offshore).
#   "swell_window": the range of swell directions (from, to) in degrees that works at this spot.
SPOT_INFO = {
    "Lisbon": {"faces": 230, "swell_window": (240, 330)},
    "San Diego": {"faces": 260, "swell_window": (200, 300)},
    "Siargao": {"faces": 90, "swell_window": (60, 160)},
    "Lombok": {"faces": 200, "swell_window": (160, 240)},
    "Taghazout": {"faces": 280, "swell_window": (250, 350)},
}

# Comfortable wave height range in metres for each skill level: (too small below, too big above)
SKILL_LEVELS = {
    "Beginner": (0.3, 1.2),
    "Intermediate": (0.6, 2.0),
    "Advanced": (1.0, 4.0),
}

# The ratings from worst to best, so a position in this list can be moved up or down
LEVELS = ["Poor", "Okay", "Good"]

# How far apart are two directions? 350° and 10° are only 20° apart, not 340°.
# The result is always between 0 and 180.
def angle_between(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)

# Is the wind onshore, offshore or in between? Compare where the wind comes FROM
# with the direction the beach faces: within 60° = it blows onto the beach.
def wind_type(wind_direction, coast_faces):
    diff = angle_between(wind_direction, coast_faces)
    if diff <= 60:
        return "Onshore"
    elif diff >= 120:
        return "Offshore"
    else:
        return "Cross-shore"

# Does the swell come from a direction that works at this spot? window = (from, to) in degrees.
# (direction - low) % 360 is "how many degrees past the start of the window", which also works
# for windows that cross north, like 340° to 40°.
def swell_in_window(swell_direction, window):
    low, high = window
    return (swell_direction - low) % 360 <= (high - low) % 360

# Rough power of the waves in kilowatts per metre of wave front: 0.49 * height² * period.
# Height counts squared, so a 2 m wave carries four times the power of a 1 m wave.
def wave_power(height, period):
    return 0.49 * height ** 2 * period

# One step down the ratings: Good -> Okay -> Poor (Poor stays Poor)
def one_level_down(rating):
    return LEVELS[max(LEVELS.index(rating) - 1, 0)]

# The full rating for a spot. It starts with the period/wind rating from rate_conditions
# and then adjusts it with what only this spot and this surfer know:
#   offshore wind: counted as 5 knots lighter (it grooms the waves)
#   onshore wind: one level worse
#   swell from a direction that doesn't work here: one level worse
#   waves too small for your level: one level worse; too big: Poor
# Returns (rating, reason) just like rate_conditions.
def rate_for_spot(swell_wave_period, wind_speed_10m, wind_direction, swell_direction, wave_height,
                  spot, skill="Intermediate", wind_unit="kn", **rules):
    info = SPOT_INFO[spot]
    kind = wind_type(wind_direction, info["faces"])

    wind = wind_speed_10m
    if kind == "Offshore":
        wind = max(wind_speed_10m - 5, 0)   # max(..., 0) so the wind can't become negative
    rating, reason = rate_conditions(swell_wave_period, wind, wind_unit=wind_unit, **rules)

    notes = []   # short remarks collected while adjusting, added to the reason at the end
    if kind == "Offshore":
        notes.append("offshore wind")
    elif kind == "Onshore":
        rating = one_level_down(rating)
        notes.append("onshore wind")

    if not swell_in_window(swell_direction, info["swell_window"]):
        rating = one_level_down(rating)
        notes.append("swell direction doesn't suit this spot")

    too_small, too_big = SKILL_LEVELS[skill]
    if wave_height > too_big:
        rating = "Poor"
        notes.append(f"waves too big for {skill.lower()} level")
    elif wave_height < too_small:
        rating = one_level_down(rating)
        notes.append(f"waves a bit small for {skill.lower()} level")

    if notes:
        reason = reason + "; " + ", ".join(notes)
    return rating, reason

# Rates every single hour. Returns a table with one row per hour and the columns
# "period", "wind" and "rating". The **rules are the optional limits of rate_conditions.
# If a spot is given, the spot rules and the skill level are used too (rate_for_spot).
def rate_hours(marine_df, wind_df, spot=None, skill="Intermediate", **rules):
    hours = pd.DataFrame({"period": marine_df["swell_wave_period"], "wind": wind_df["wind_speed_10m"]})
    if spot is None:
        # rate_conditions returns (rating, reason), so [0] takes just the rating
        hours["rating"] = [rate_conditions(p, w, **rules)[0] for p, w in zip(hours["period"], hours["wind"])]
    else:
        hours["wind_direction"] = wind_df["wind_direction_10m"]
        hours["swell_direction"] = marine_df["swell_wave_direction"]
        hours["height"] = marine_df["wave_height"]
        # itertuples gives one row at a time; row.period etc. read the columns of that row
        hours["rating"] = [
            rate_for_spot(row.period, row.wind, row.wind_direction, row.swell_direction, row.height,
                          spot, skill, **rules)[0]
            for row in hours.itertuples()
        ]
    return hours

# Best time to surf: the best stretch of daylight hours still ahead today, or tomorrow
# once today's daylight is over. daylight_hours is a table made by rate_hours, reduced to daylight.
# Returns (day_label, rating, start, end) where day_label is "today" or "tomorrow".
def find_best_time(daylight_hours, now):
    target_day = now.date()
    day_hours = daylight_hours[(daylight_hours.index.date == target_day) & (daylight_hours.index >= now)]
    day_label = "today"
    if day_hours.empty:
        target_day = (now + pd.Timedelta(days=1)).date()
        day_hours = daylight_hours[daylight_hours.index.date == target_day]
        day_label = "tomorrow"
    level, start, end = find_best_window(day_hours)
    return day_label, level, start, end

# One entry per day for the "week at a glance" strip: the best daylight stretch of each day.
# For today only the hours still ahead count; a day with no hours left is skipped.
# Returns a list of (date, rating, start, end), earliest day first.
def best_per_day(daylight_hours, now):
    days = []
    for date in sorted(set(daylight_hours.index.date)):   # set() removes duplicates: one entry per calendar date
        day_hours = daylight_hours[daylight_hours.index.date == date]
        if date == now.date():
            day_hours = day_hours[day_hours.index >= now]
        if day_hours.empty:
            continue
        level, start, end = find_best_window(day_hours)
        days.append((date, level, start, end))
    return days

# Turns the API's daily sunrise/sunset lists into a dict: {date: (sunrise, sunset)}.
# daily looks like {"time": ["2026-10-24", ...], "sunrise": ["2026-10-24T07:41", ...], "sunset": [...]}.
def make_sun_times(daily):
    return {
        pd.Timestamp(day).date(): (pd.Timestamp(rise), pd.Timestamp(set_))
        for day, rise, set_ in zip(daily["time"], daily["sunrise"], daily["sunset"])
    }

# Keeps only the hours with daylight. An hour counts if its middle (xx:30) lies between
# sunrise and sunset of that day. sun_times is the dict made by make_sun_times.
def daylight_only(hours, sun_times):
    keep = []   # one True/False per hour
    for time in hours.index:
        sunrise, sunset = sun_times[time.date()]
        middle = time + pd.Timedelta(minutes=30)
        keep.append(sunrise <= middle <= sunset)
    return hours[keep]   # a list of True/False picks the rows marked True

# ---------- ranking spots ----------
# Points per rating, used to turn a list of hourly ratings into one number
SCORES = {"Good": 2, "Okay": 1, "Poor": 0}

# How good is the coming week at a spot? A score from 0 to 100: the average rating of all
# daylight hours still ahead (all Poor = 0, all Okay = 50, all Good = 100).
def week_score(daylight_hours, now):
    ahead = daylight_hours[daylight_hours.index >= now]
    if ahead.empty:
        return 0.0
    return ahead["rating"].map(SCORES).mean() * 50   # .map swaps each rating for its points; the mean is between 0 and 2

# The best day out of the list made by best_per_day: the best rating wins,
# then the longer window, and on a tie the earlier day (max keeps the first of equals).
def best_day(days):
    return max(days, key=lambda day: (LEVELS.index(day[1]), day[3] - day[2]))

# What to wear for a given water temperature in °C (the same thresholds as in the guide tab).
def wetsuit_for(celsius):
    if celsius > 24:
        return "boardshorts are fine"
    elif celsius >= 20:
        return "thin wetsuit (shorty or 3/2)"
    elif celsius >= 16:
        return "4/3 wetsuit"
    else:
        return "thick wetsuit (5/4) with boots, maybe gloves"

# ---------- trends and warnings ----------
# Is the swell getting bigger or smaller in the next few hours? It compares the swell height now
# with the height `hours` later: a change of more than 10% counts as building or dropping.
# Returns (trend, change in percent). heights is a column with one value per hour.
def swell_trend(heights, now, hours=6):
    later = now + pd.Timedelta(hours=hours)
    ahead = heights[(heights.index >= now) & (heights.index <= later)]   # the hours from now until `later`
    if len(ahead) < 2 or ahead.iloc[0] == 0:
        return "steady", 0.0   # not enough data (end of the forecast), so say nothing dramatic
    change = (ahead.iloc[-1] - ahead.iloc[0]) / ahead.iloc[0] * 100
    if change > 10:
        return "building", change
    elif change < -10:
        return "dropping", change
    return "steady", change

# Why does the best window end? If the wind turns onshore, or picks up by 4 knots or more,
# right at the end of the window, this returns a warning text, otherwise None.
# `end` is the first hour after the window; wind_df has the columns wind_speed_10m and wind_direction_10m.
def wind_warning(wind_df, spot, end):
    before_time = end - pd.Timedelta(hours=1)
    if end not in wind_df.index or before_time not in wind_df.index:
        return None
    faces = SPOT_INFO[spot]["faces"]
    before_type = wind_type(wind_df.loc[before_time, "wind_direction_10m"], faces)
    after_type = wind_type(wind_df.loc[end, "wind_direction_10m"], faces)
    if after_type == "Onshore" and before_type != "Onshore":
        return f"The wind turns onshore around {end:%H:%M}, so expect the wave quality to drop after that."
    if wind_df.loc[end, "wind_speed_10m"] - wind_df.loc[before_time, "wind_speed_10m"] >= 4:
        return f"The wind picks up around {end:%H:%M}, so the surface gets bumpier after that."
    return None
