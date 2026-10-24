"""Tests for surf_logic.py. Run them with:  python -m pytest

Each test calls a function with an input where we know the right answer
and checks ("asserts") that the function gives exactly that answer.
"""
import pandas as pd
import pytest

from surf_logic import degrees_to_compass, find_best_window, next_turning_point, rate_conditions


# ---------- degrees_to_compass ----------
# @pytest.mark.parametrize runs the same test once for every (degrees, expected) pair.
@pytest.mark.parametrize("degrees, expected", [
    (0, "N"), (22, "N"), (23, "NE"), (45, "NE"), (90, "E"), (135, "SE"),
    (180, "S"), (200, "S"), (270, "W"), (337, "NW"),
    (338, "N"), (359, "N"), (360, "N"),    # the compass wraps around at 360
])
def test_degrees_to_compass(degrees, expected):
    assert degrees_to_compass(degrees) == expected


# ---------- rate_conditions ----------
@pytest.mark.parametrize("period, wind, expected", [
    (12, 5, "Good"),
    (10, 10, "Good"),     # exactly on the limits still counts as Good
    (12, 12, "Okay"),     # wind a bit too strong for Good
    (9, 5, "Okay"),       # swell period a bit too short for Good
    (9, 12, "Okay"),
    (8, 15, "Okay"),      # exactly on the limits of Okay
    (12, 20, "Poor"),     # wind too strong
    (6, 5, "Poor"),       # swell period too short
    (6, 20, "Poor"),
    (9, 16, "Poor"),
])
def test_rate_conditions_rating(period, wind, expected):
    rating, reason = rate_conditions(period, wind)
    assert rating == expected
    assert isinstance(reason, str) and reason       # there is always a non-empty reason


def test_rate_conditions_reason_names_the_problem():
    assert "wind" in rate_conditions(12, 12)[1]
    assert "period" in rate_conditions(9, 5)[1]
    reason_both = rate_conditions(9, 12)[1]
    assert "period" in reason_both and "wind" in reason_both


# ---------- find_best_window ----------
def hours_table(ratings, start="2026-10-24 06:00"):
    """Builds a table with one row per hour and the given ratings, e.g. ["Poor", "Good", "Good"]."""
    index = pd.date_range(start, periods=len(ratings), freq="h")
    return pd.DataFrame({"rating": ratings}, index=index)


def test_best_window_prefers_the_best_rating_over_a_longer_block():
    table = hours_table(["Okay", "Okay", "Okay", "Poor", "Good"])
    level, start, end = find_best_window(table)
    assert level == "Good"
    assert start == pd.Timestamp("2026-10-24 10:00")
    assert end == pd.Timestamp("2026-10-24 11:00")     # the last hour lasts until the next full hour


def test_best_window_takes_the_longest_block():
    table = hours_table(["Good", "Poor", "Good", "Good", "Good", "Poor", "Good", "Good"])
    level, start, end = find_best_window(table)
    assert (level, start, end) == ("Good", pd.Timestamp("2026-10-24 08:00"), pd.Timestamp("2026-10-24 11:00"))


def test_best_window_on_a_tie_takes_the_earliest_block():
    table = hours_table(["Good", "Good", "Poor", "Good", "Good"])
    level, start, end = find_best_window(table)
    assert start == pd.Timestamp("2026-10-24 06:00")
    assert end == pd.Timestamp("2026-10-24 08:00")


def test_best_window_when_everything_is_poor():
    table = hours_table(["Poor", "Poor", "Poor"])
    level, start, end = find_best_window(table)
    assert level == "Poor"
    assert (start, end) == (pd.Timestamp("2026-10-24 06:00"), pd.Timestamp("2026-10-24 09:00"))


def test_best_window_with_a_single_hour():
    level, start, end = find_best_window(hours_table(["Okay"]))
    assert (level, start, end) == ("Okay", pd.Timestamp("2026-10-24 06:00"), pd.Timestamp("2026-10-24 07:00"))


# ---------- next_turning_point ----------
def tide_series(values):
    index = pd.date_range("2026-10-24 00:00", periods=len(values), freq="h")
    return pd.Series(values, index=index)


def test_next_turning_point_finds_the_next_high_tide():
    tide = tide_series([0, 1, 2, 1, 0, -1, 0])          # rises to a peak at 02:00
    kind, when = next_turning_point(tide, pd.Timestamp("2026-10-24 00:00"))
    assert (kind, when) == ("High", pd.Timestamp("2026-10-24 02:00"))


def test_next_turning_point_finds_the_next_low_tide():
    tide = tide_series([0, 1, 2, 1, 0, -1, 0])          # after 03:00 it falls to a low at 05:00
    kind, when = next_turning_point(tide, pd.Timestamp("2026-10-24 03:00"))
    assert (kind, when) == ("Low", pd.Timestamp("2026-10-24 05:00"))


def test_next_turning_point_ignores_the_past():
    tide = tide_series([0, 1, 2, 1, 0, -1, 0])
    kind, when = next_turning_point(tide, pd.Timestamp("2026-10-24 03:00"))
    assert when >= pd.Timestamp("2026-10-24 03:00")      # the peak at 02:00 is already over


def test_next_turning_point_when_there_is_none():
    tide = tide_series([0, 1, 2, 3, 4])                  # keeps rising, no peak in sight
    assert next_turning_point(tide, pd.Timestamp("2026-10-24 00:00")) == (None, None)


# ---------- rate_conditions with custom limits ----------
def test_rate_conditions_defaults_are_the_original_rules():
    # passing the default limits explicitly must give the same answers as passing none
    for period, wind in [(12, 5), (9, 12), (6, 20), (10, 10), (8, 15)]:
        assert rate_conditions(period, wind) == rate_conditions(period, wind, 10, 10, 8, 15)


def test_rate_conditions_stricter_limits_downgrade_the_rating():
    assert rate_conditions(11, 8)[0] == "Good"
    assert rate_conditions(11, 8, good_period=12, good_wind=6, okay_period=10, okay_wind=11)[0] == "Okay"


def test_rate_conditions_reason_uses_the_custom_limits():
    reason = rate_conditions(12, 20, good_period=10, good_wind=10, okay_period=8, okay_wind=18)[1]
    assert "18" in reason          # "wind is too strong (over 18 knots)"


# ---------- rate_hours and find_best_time ----------
from surf_logic import find_best_time, rate_hours


def test_rate_hours_rates_every_hour():
    index = pd.date_range("2026-10-24 06:00", periods=3, freq="h")
    marine = pd.DataFrame({"swell_wave_period": [12, 9, 6]}, index=index)
    wind = pd.DataFrame({"wind_speed_10m": [5, 5, 5]}, index=index)
    hours = rate_hours(marine, wind)
    assert list(hours["rating"]) == ["Good", "Okay", "Poor"]
    assert list(hours.columns) == ["period", "wind", "rating"]


def test_rate_hours_passes_the_limits_on():
    index = pd.date_range("2026-10-24 06:00", periods=1, freq="h")
    marine = pd.DataFrame({"swell_wave_period": [11]}, index=index)
    wind = pd.DataFrame({"wind_speed_10m": [5]}, index=index)
    assert rate_hours(marine, wind)["rating"].iloc[0] == "Good"
    assert rate_hours(marine, wind, good_period=13, good_wind=10, okay_period=8, okay_wind=15)["rating"].iloc[0] == "Okay"


def two_days(today_ratings, tomorrow_ratings):
    """Daylight table: today from 06:00 and tomorrow from 06:00, with the given ratings."""
    today = hours_table(today_ratings, "2026-10-24 06:00")
    tomorrow = hours_table(tomorrow_ratings, "2026-10-25 06:00")
    return pd.concat([today, tomorrow])


def test_find_best_time_only_looks_at_hours_still_ahead_today():
    table = two_days(["Good", "Good", "Poor", "Okay", "Okay"], ["Good"] * 3)
    # it is 08:00: the morning Good hours are over, so the Okay block from 09:00 is the best that is left
    day_label, level, start, end = find_best_time(table, pd.Timestamp("2026-10-24 08:00"))
    assert (day_label, level) == ("today", "Okay")
    assert (start, end) == (pd.Timestamp("2026-10-24 09:00"), pd.Timestamp("2026-10-24 11:00"))


def test_find_best_time_switches_to_tomorrow_when_daylight_is_over():
    table = two_days(["Good"] * 5, ["Poor", "Okay", "Okay"])
    day_label, level, start, end = find_best_time(table, pd.Timestamp("2026-10-24 20:00"))
    assert (day_label, level) == ("tomorrow", "Okay")
    assert (start, end) == (pd.Timestamp("2026-10-25 07:00"), pd.Timestamp("2026-10-25 09:00"))


# ---------- spot rules: wind type, swell window, wave power, rate_for_spot ----------
from surf_logic import angle_between, wind_type, swell_in_window, wave_power, rate_for_spot


@pytest.mark.parametrize("a, b, expected", [(10, 350, 20), (0, 180, 180), (90, 90, 0), (270, 10, 100)])
def test_angle_between_takes_the_short_way_round(a, b, expected):
    assert angle_between(a, b) == expected


# a beach facing west (270°): wind from the west blows onto it, wind from the east blows off it
@pytest.mark.parametrize("wind_direction, expected", [
    (270, "Onshore"), (220, "Onshore"), (90, "Offshore"), (150, "Offshore"), (180, "Cross-shore"), (0, "Cross-shore"),
])
def test_wind_type(wind_direction, expected):
    assert wind_type(wind_direction, 270) == expected


@pytest.mark.parametrize("direction, window, expected", [
    (270, (240, 330), True), (240, (240, 330), True), (330, (240, 330), True),
    (200, (240, 330), False), (340, (240, 330), False),
    (350, (340, 40), True), (10, (340, 40), True), (90, (340, 40), False),   # window across north
])
def test_swell_in_window(direction, window, expected):
    assert swell_in_window(direction, window) == expected


def test_wave_power_grows_with_height_squared():
    assert wave_power(2, 10) == pytest.approx(4 * wave_power(1, 10))
    assert wave_power(1, 10) == pytest.approx(4.9)


# Taghazout: beach faces west (280°), swell window 250–350°. These conditions are Good by period/wind alone.
GOOD = dict(swell_wave_period=12, wind_speed_10m=5, wave_height=1.5, spot="Taghazout")

def test_rate_for_spot_good_with_cross_shore_wind_and_right_swell():
    assert rate_for_spot(wind_direction=10, swell_direction=300, **GOOD)[0] == "Good"

def test_rate_for_spot_onshore_wind_is_one_level_worse():
    assert rate_for_spot(wind_direction=280, swell_direction=300, **GOOD)[0] == "Okay"

def test_rate_for_spot_wrong_swell_direction_is_one_level_worse():
    rating, reason = rate_for_spot(wind_direction=10, swell_direction=150, **GOOD)
    assert rating == "Okay" and "swell direction" in reason

def test_rate_for_spot_two_problems_are_two_levels_worse():
    assert rate_for_spot(wind_direction=280, swell_direction=150, **GOOD)[0] == "Poor"

def test_rate_for_spot_offshore_wind_counts_as_lighter():
    strong = dict(GOOD, wind_speed_10m=14)   # 14 kn is only Okay normally, offshore it counts as 9 kn
    assert rate_for_spot(wind_direction=100, swell_direction=300, **strong)[0] == "Good"
    assert rate_for_spot(wind_direction=10, swell_direction=300, **strong)[0] == "Okay"

def test_rate_for_spot_skill_level_wave_height():
    big = dict(GOOD, wave_height=3.0)
    assert rate_for_spot(wind_direction=10, swell_direction=300, skill="Intermediate", **big)[0] == "Poor"   # too big
    assert rate_for_spot(wind_direction=10, swell_direction=300, skill="Advanced", **big)[0] == "Good"
    small = dict(GOOD, wave_height=0.4)
    assert rate_for_spot(wind_direction=10, swell_direction=300, skill="Intermediate", **small)[0] == "Okay"   # a bit small
    assert rate_for_spot(wind_direction=10, swell_direction=300, skill="Beginner", **small)[0] == "Good"

def test_rate_for_spot_poor_never_goes_below_poor():
    poor = dict(GOOD, swell_wave_period=5)
    assert rate_for_spot(wind_direction=280, swell_direction=150, **poor)[0] == "Poor"

def test_rate_hours_with_a_spot_uses_the_spot_rules():
    idx = pd.date_range("2026-10-24 06:00", periods=2, freq="h")
    marine = pd.DataFrame({"swell_wave_period": [12, 12], "swell_wave_direction": [300, 150], "wave_height": [1.5, 1.5]}, index=idx)
    wind = pd.DataFrame({"wind_speed_10m": [5, 5], "wind_direction_10m": [10, 10]}, index=idx)
    assert list(rate_hours(marine, wind, "Taghazout")["rating"]) == ["Good", "Okay"]
    assert list(rate_hours(marine, wind)["rating"]) == ["Good", "Good"]   # without a spot: only period and wind


# ---------- best_per_day ----------
from surf_logic import best_per_day

def test_best_per_day_gives_one_entry_per_day_with_its_best_window():
    hours = two_days(["Poor", "Okay", "Okay", "Poor"], ["Good", "Good", "Poor", "Poor"])
    days = best_per_day(hours, pd.Timestamp("2026-10-24 00:00"))
    assert [(d[1]) for d in days] == ["Okay", "Good"]
    assert days[1][2] == pd.Timestamp("2026-10-25 06:00")

def test_best_per_day_today_only_counts_hours_still_ahead():
    hours = two_days(["Good", "Poor", "Poor", "Poor"], ["Okay", "Okay", "Okay", "Okay"])
    days = best_per_day(hours, pd.Timestamp("2026-10-24 07:00"))   # the Good hour (06:00) is already over
    assert days[0][1] == "Poor"

def test_best_per_day_skips_a_day_with_no_hours_left():
    hours = two_days(["Good", "Good", "Good", "Good"], ["Okay", "Okay", "Okay", "Okay"])
    days = best_per_day(hours, pd.Timestamp("2026-10-24 23:00"))
    assert len(days) == 1 and days[0][0] == pd.Timestamp("2026-10-25").date()


# ---------- daylight ----------
from surf_logic import make_sun_times, daylight_only

DAILY = {"time": ["2026-10-24", "2026-10-25"],
         "sunrise": ["2026-10-24T07:41", "2026-10-25T07:42"],
         "sunset": ["2026-10-24T18:12", "2026-10-25T18:10"]}

def test_make_sun_times_builds_a_dict_by_date():
    sun = make_sun_times(DAILY)
    assert sun[pd.Timestamp("2026-10-24").date()] == (pd.Timestamp("2026-10-24 07:41"), pd.Timestamp("2026-10-24 18:12"))

def test_daylight_only_keeps_hours_whose_middle_is_in_daylight():
    hours = pd.DataFrame({"rating": "Good"}, index=pd.date_range("2026-10-24 00:00", periods=24, freq="h"))
    kept = daylight_only(hours, make_sun_times(DAILY))
    # 07:00 has its middle (07:30) before sunrise (07:41), 08:00 is the first hour; 17:00 (17:30) is the last, 18:00 (18:30) is after sunset
    assert kept.index[0] == pd.Timestamp("2026-10-24 08:00")
    assert kept.index[-1] == pd.Timestamp("2026-10-24 17:00")


# ---------- units ----------
from surf_logic import convert_temp, wind_text

def test_convert_temp():
    assert convert_temp(20, "°C") == 20
    assert convert_temp(20, "°F") == 68

def test_wind_text_converts_knots():
    assert wind_text(10) == "10 knots"
    assert wind_text(10, "km/h") == "19 km/h"
    assert wind_text(10, "mph") == "12 mph"

def test_rate_conditions_reason_uses_the_chosen_wind_unit():
    reason = rate_conditions(11, 12, wind_unit="km/h")[1]   # a good period, so Okay only because of the wind
    assert "km/h" in reason and "knots" not in reason


# ---------- ranking spots ----------
from surf_logic import week_score, best_day

def test_week_score_runs_from_0_to_100():
    now = pd.Timestamp("2026-10-24 00:00")
    assert week_score(two_days(["Poor"] * 4, ["Poor"] * 4), now) == 0
    assert week_score(two_days(["Okay"] * 4, ["Okay"] * 4), now) == 50
    assert week_score(two_days(["Good"] * 4, ["Good"] * 4), now) == 100
    assert week_score(two_days(["Good"] * 4, ["Poor"] * 4), now) == 50

def test_week_score_ignores_hours_in_the_past():
    hours = two_days(["Good", "Good", "Poor", "Poor"], ["Poor"] * 4)
    assert week_score(hours, pd.Timestamp("2026-10-24 08:00")) == 0   # both Good hours (06:00, 07:00) are over

def test_week_score_with_nothing_ahead_is_zero():
    assert week_score(two_days(["Good"] * 4, ["Good"] * 4), pd.Timestamp("2026-11-01")) == 0

def test_best_day_prefers_rating_then_longer_window_then_earlier_day():
    hours = two_days(["Okay", "Okay", "Okay", "Okay"], ["Good", "Poor", "Poor", "Poor"])
    days = best_per_day(hours, pd.Timestamp("2026-10-24 00:00"))
    assert best_day(days)[0] == pd.Timestamp("2026-10-25").date()   # a Good hour beats a longer Okay block
    same = best_per_day(two_days(["Okay"] * 4, ["Okay"] * 4), pd.Timestamp("2026-10-24 00:00"))
    assert best_day(same)[0] == pd.Timestamp("2026-10-24").date()   # a full tie goes to the earlier day
