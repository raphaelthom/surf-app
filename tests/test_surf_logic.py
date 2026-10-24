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
