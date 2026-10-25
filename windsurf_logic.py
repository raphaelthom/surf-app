"""The windsurf logic: rating, sail size and warnings for flat-water and freestyle windsurfing.

Like surf_logic.py, this file has no Streamlit in it, so the tests can import it directly.
It reuses a few helpers from surf_logic.py (angles, "one level down", the best-time search).
"""
import pandas as pd

from surf_logic import angle_between, one_level_down, wind_text

# Rough defaults per windsurf spot, my best guess:
#   "faces": the direction you look when you stand on the beach facing the water.
#            Wind coming FROM there blows onto the beach (onshore), wind from the opposite side blows out to sea.
WINDSURF_SPOT_INFO = {
    "La Linière (Noirmoutier)": {
        "faces": 0,   # the beach lies on the north shore of the island and faces north
        "note": "La Linière is a beach on the north shore of the island of Noirmoutier in the Vendée (France), "
                "facing north towards the bay. The forecast point is the nearest point the weather data covers, "
                "so it describes the area, not the exact beach. "
                "The tides are big here, so the sea changes a lot between low and high tide.",
    },
}

# The wind (in knots) that works at each level: (okay from, good from, good up to, okay up to).
# Below "okay from" there is too little wind to get going, above "okay up to" it is too much for that level.
WIND_RANGES = {
    "Beginner": (8, 10, 16, 20),
    "Intermediate": (11, 14, 22, 27),
    "Advanced": (14, 18, 30, 35),
}

# Gusts: if they are this many knots above the average wind, the wind is too uneven (one level worse)
GUST_LIMITS = {"Beginner": 6, "Intermediate": 9, "Advanced": 12}

# Where does the wind blow from, compared with the beach? Same idea as wind_type for surfing,
# but with finer steps, because for windsurfing the direction is also a safety question.
# angle_between is 0 for wind straight onto the beach and 180 for wind straight off the land.
def windsurf_wind_side(wind_direction, coast_faces):
    diff = angle_between(wind_direction, coast_faces)
    if diff < 30:
        return "Onshore"
    elif diff < 60:
        return "Side-onshore"
    elif diff <= 120:
        return "Cross-shore"
    elif diff < 150:
        return "Side-offshore"
    else:
        return "Offshore"

# Is the wind speed right for your level? Returns a short label for the pill on the dashboard.
def wind_fit(wind, skill):
    okay_from, good_from, good_to, okay_to = WIND_RANGES[skill]
    if wind < okay_from:
        return "too light"
    elif wind < good_from:
        return "a bit light"
    elif wind <= good_to:
        return "good wind"
    elif wind <= okay_to:
        return "a bit strong"
    else:
        return "too strong"

# How uneven is the wind? The spread is the difference between the gusts and the average wind.
def gust_label(wind, gust, skill):
    spread = gust - wind
    if spread <= GUST_LIMITS[skill]:
        return "steady"
    elif spread <= GUST_LIMITS[skill] * 1.5:
        return "gusty"
    else:
        return "very gusty"

# Rates the wind speed alone as "Good", "Okay" or "Poor" for your level.
# Returns (rating, reason) like rate_conditions does for surfing. wind_unit only changes how the limits are written.
def rate_wind_speed(wind, skill, wind_unit="kn"):
    okay_from, good_from, good_to, okay_to = WIND_RANGES[skill]
    fit = wind_fit(wind, skill)
    if fit == "good wind":
        return "Good", f"wind is right for {skill.lower()} level"
    elif fit == "a bit light":
        return "Okay", f"wind is a bit light (under {wind_text(good_from, wind_unit)})"
    elif fit == "a bit strong":
        return "Okay", f"wind is a bit strong (over {wind_text(good_to, wind_unit)})"
    elif fit == "too light":
        return "Poor", f"wind is too light (under {wind_text(okay_from, wind_unit)})"
    else:
        return "Poor", f"wind is too strong for {skill.lower()} level (over {wind_text(okay_to, wind_unit)})"

# The full rating for a windsurf spot. It starts with the wind speed and then adjusts it:
#   offshore wind: Poor for beginners, one level worse for everyone else (you can be blown out to sea)
#   side-offshore wind: one level worse for beginners
#   gusts too uneven for your level: one level worse
# Wave size is not part of the rating: for flat-water windsurfing it hardly matters, and the wave data
# only describes the open sea near the spot, not the beach.
# Returns (rating, reason).
def rate_for_windsurf(wind, gust, wind_direction, spot, skill="Intermediate", wind_unit="kn"):
    rating, reason = rate_wind_speed(wind, skill, wind_unit)
    side = windsurf_wind_side(wind_direction, WINDSURF_SPOT_INFO[spot]["faces"])

    notes = []   # short remarks collected while adjusting, added to the reason at the end
    if side == "Offshore":
        rating = "Poor" if skill == "Beginner" else one_level_down(rating)
        notes.append("offshore wind, you can be blown out to sea")
    elif side == "Side-offshore" and skill == "Beginner":
        rating = one_level_down(rating)
        notes.append("side-offshore wind is risky for beginners")

    if gust - wind > GUST_LIMITS[skill]:
        rating = one_level_down(rating)
        notes.append("gusty")

    if notes:
        reason = reason + "; " + ", ".join(notes)
    return rating, reason

# Rates every single hour. Returns a table with one row per hour and the columns
# "wind", "gust" and "rating" (the same idea as rate_hours for surfing).
def rate_windsurf_hours(wind_df, spot, skill="Intermediate"):
    hours = pd.DataFrame({
        "wind": wind_df["wind_speed_10m"],
        "gust": wind_df["wind_gusts_10m"],
        "wind_direction": wind_df["wind_direction_10m"],
    })
    # itertuples gives one row at a time; [0] takes the rating out of (rating, reason)
    hours["rating"] = [
        rate_for_windsurf(row.wind, row.gust, row.wind_direction, spot, skill)[0]
        for row in hours.itertuples()
    ]
    return hours

# Which sail size (in m²) fits? A common rule of thumb: sail area is about 1.45 x your weight (kg)
# divided by the wind (knots). Gusts count a quarter, because you have to hold the sail in the strong bits too.
# Returns None if there is too little wind to get going. The result is rounded to half a square metre.
def sail_size(weight, wind, gust):
    effective_wind = wind + 0.25 * (gust - wind)
    if effective_wind < 8:
        return None
    size = 1.45 * weight / effective_wind
    size = min(max(size, 3.0), 9.5)   # keep it between the smallest and the biggest normal sail
    return round(size * 2) / 2

# Why does the best window end? If the wind turns offshore, drops too low or gets too strong
# right at the end of the window, this returns a warning text, otherwise None.
# `end` is the first hour after the window; wind_df has the wind columns from the API.
def windsurf_warning(wind_df, spot, skill, end):
    before_time = end - pd.Timedelta(hours=1)
    if end not in wind_df.index or before_time not in wind_df.index:
        return None
    faces = WINDSURF_SPOT_INFO[spot]["faces"]
    offshore_sides = ("Side-offshore", "Offshore")
    before_side = windsurf_wind_side(wind_df.loc[before_time, "wind_direction_10m"], faces)
    after_side = windsurf_wind_side(wind_df.loc[end, "wind_direction_10m"], faces)
    if after_side in offshore_sides and before_side not in offshore_sides:
        return f"The wind turns offshore around {end:%H:%M}, so be back on the beach before then."

    okay_from, _, _, okay_to = WIND_RANGES[skill]
    before_wind = wind_df.loc[before_time, "wind_speed_10m"]
    after_wind = wind_df.loc[end, "wind_speed_10m"]
    if after_wind < okay_from <= before_wind:
        return f"The wind drops around {end:%H:%M}, so there may not be enough wind after that."
    if after_wind > okay_to >= before_wind:
        return f"The wind gets too strong around {end:%H:%M}, so be careful after that."
    return None
