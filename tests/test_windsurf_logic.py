"""Tests for windsurf_logic.py. Run them with:  python -m pytest

windsurf_wind_side is tested with a beach that faces west (270°). The tests of the real spot use its own
direction: the beach faces north (0°), so wind from 0° is onshore and wind from 180° is offshore.
"""
import pandas as pd
import pytest

from windsurf_logic import (gust_label, rate_for_windsurf, rate_windsurf_hours, rate_wind_speed, sail_size,
                            wind_fit, windsurf_warning, windsurf_wind_side)

SPOT = "La Linière (Noirmoutier)"


# ---------- windsurf_wind_side ----------
@pytest.mark.parametrize("direction, expected", [
    (270, "Onshore"), (250, "Onshore"),            # straight from the water
    (225, "Side-onshore"), (315, "Side-onshore"),
    (180, "Cross-shore"), (360, "Cross-shore"),    # along the beach
    (135, "Side-offshore"), (45, "Side-offshore"),
    (90, "Offshore"), (100, "Offshore"),           # straight off the land
])
def test_windsurf_wind_side(direction, expected):
    assert windsurf_wind_side(direction, 270) == expected


# ---------- wind_fit and rate_wind_speed ----------
@pytest.mark.parametrize("wind, skill, expected", [
    (5, "Intermediate", "too light"),
    (12, "Intermediate", "a bit light"),
    (18, "Intermediate", "good wind"),
    (14, "Intermediate", "good wind"),      # exactly on the limit still counts
    (25, "Intermediate", "a bit strong"),
    (30, "Intermediate", "too strong"),
    (13, "Beginner", "good wind"),
    (25, "Beginner", "too strong"),         # the same wind is too much for a beginner...
    (25, "Advanced", "good wind"),          # ...and just right for an advanced sailor
])
def test_wind_fit(wind, skill, expected):
    assert wind_fit(wind, skill) == expected


@pytest.mark.parametrize("wind, expected", [(5, "Poor"), (12, "Okay"), (18, "Good"), (25, "Okay"), (30, "Poor")])
def test_rate_wind_speed(wind, expected):
    rating, reason = rate_wind_speed(wind, "Intermediate")
    assert rating == expected
    assert reason


def test_rate_wind_speed_writes_limits_in_the_chosen_unit():
    _, reason = rate_wind_speed(30, "Intermediate", wind_unit="km/h")
    assert "km/h" in reason and "knots" not in reason


# ---------- gust_label ----------
@pytest.mark.parametrize("wind, gust, expected", [
    (18, 24, "steady"),        # spread 6, limit for intermediate is 9
    (18, 27, "steady"),        # exactly on the limit
    (18, 30, "gusty"),         # spread 12
    (18, 36, "very gusty"),    # spread 18
])
def test_gust_label(wind, gust, expected):
    assert gust_label(wind, gust, "Intermediate") == expected


# ---------- rate_for_windsurf ----------
def test_good_side_onshore_wind_is_good():
    rating, _ = rate_for_windsurf(18, 22, 315, SPOT, "Intermediate")
    assert rating == "Good"


def test_offshore_wind_is_one_level_worse():
    rating, reason = rate_for_windsurf(18, 22, 180, SPOT, "Intermediate")
    assert rating == "Okay"
    assert "offshore" in reason


def test_offshore_wind_is_poor_for_beginners():
    rating, _ = rate_for_windsurf(13, 15, 180, SPOT, "Beginner")   # wind that would be Good
    assert rating == "Poor"


def test_side_offshore_only_matters_for_beginners():
    assert rate_for_windsurf(13, 15, 225, SPOT, "Beginner")[0] == "Okay"
    assert rate_for_windsurf(18, 22, 225, SPOT, "Intermediate")[0] == "Good"


def test_gusts_lower_the_rating():
    rating, reason = rate_for_windsurf(18, 32, 315, SPOT, "Intermediate")   # spread 14 > 9
    assert rating == "Okay"
    assert "gusty" in reason


def test_too_little_wind_stays_poor():
    assert rate_for_windsurf(4, 5, 180, SPOT, "Intermediate")[0] == "Poor"   # can't go lower than Poor


# ---------- rate_windsurf_hours ----------
def test_rate_windsurf_hours_gives_one_rating_per_hour():
    times = pd.date_range("2026-10-24 10:00", periods=2, freq="h")
    wind_df = pd.DataFrame({"wind_speed_10m": [18, 4], "wind_gusts_10m": [22, 5], "wind_direction_10m": [315, 315]}, index=times)
    hours = rate_windsurf_hours(wind_df, SPOT, "Intermediate")
    assert list(hours["rating"]) == ["Good", "Poor"]
    assert list(hours["gust"]) == [22, 5]


# ---------- sail_size ----------
def test_sail_size_for_a_normal_day():
    assert sail_size(75, 20, 20) == 5.5     # 1.45 * 75 / 20 = 5.4 -> rounded to half a square metre


def test_lighter_wind_means_a_bigger_sail():
    assert sail_size(75, 14, 14) > sail_size(75, 24, 24)


def test_heavier_sailor_means_a_bigger_sail():
    assert sail_size(90, 20, 20) > sail_size(65, 20, 20)


def test_gusts_make_the_sail_a_bit_smaller():
    assert sail_size(75, 20, 32) < sail_size(75, 20, 20)


def test_no_sail_when_there_is_too_little_wind():
    assert sail_size(75, 6, 8) is None


def test_sail_size_stays_in_a_sensible_range():
    assert sail_size(120, 9, 9) == 9.5      # would be about 19 m², capped
    assert sail_size(50, 45, 50) == 3.0     # would be under 2 m², capped


# ---------- windsurf_warning ----------
def make_wind(speeds, directions):
    times = pd.date_range("2026-10-24 10:00", periods=len(speeds), freq="h")
    return pd.DataFrame({"wind_speed_10m": speeds, "wind_direction_10m": directions}, index=times)


def test_warning_when_the_wind_turns_offshore():
    wind = make_wind([18, 18, 18], [315, 315, 180])
    end = pd.Timestamp("2026-10-24 12:00")
    assert "offshore" in windsurf_warning(wind, SPOT, "Intermediate", end)


def test_warning_when_the_wind_drops():
    wind = make_wind([18, 18, 6], [315, 315, 315])
    end = pd.Timestamp("2026-10-24 12:00")
    assert "drops" in windsurf_warning(wind, SPOT, "Intermediate", end)


def test_warning_when_the_wind_gets_too_strong():
    wind = make_wind([18, 25, 35], [315, 315, 315])
    end = pd.Timestamp("2026-10-24 12:00")
    assert "too strong" in windsurf_warning(wind, SPOT, "Intermediate", end)


def test_no_warning_when_nothing_changes():
    wind = make_wind([18, 18, 18], [315, 315, 315])
    assert windsurf_warning(wind, SPOT, "Intermediate", pd.Timestamp("2026-10-24 12:00")) is None


def test_no_warning_at_the_end_of_the_forecast():
    wind = make_wind([18, 18], [315, 315])
    assert windsurf_warning(wind, SPOT, "Intermediate", pd.Timestamp("2026-10-24 13:00")) is None   # no data for that hour
