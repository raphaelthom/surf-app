"""The surf logic: small functions that turn numbers into compass labels, ratings and best times.

They live in their own file (and not in app.py) so tests can import them without
starting the whole Streamlit page.
"""
import pandas as pd

DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

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
