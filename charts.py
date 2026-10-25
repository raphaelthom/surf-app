"""The Plotly charts. Like forecast_data.py, they are shared by the surf and the windsurf page."""
import plotly.graph_objects as go   # Plotly: interactive charts

from surf_logic import degrees_to_compass

# Colours for the three ratings, used in the hourly quality chart
RATING_COLORS = {"Good": "#1b9e77", "Okay": "#e6a117", "Poor": "#9aa0a6"}

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
    # The gusts as a dotted line above the wind speed
    fig.add_trace(go.Scatter(
        x=wind_df.index, y=wind_df["wind_gusts_10m"] * factor, mode="lines",
        line=dict(dash="dot", width=1.5, color="#9aa0a6"),
        hovertemplate="%{x|%a %H:%M}<br>gusts up to %{y:.0f} " + unit + "<extra></extra>",
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

# Windsurf version of the quality chart: one bar per daylight hour, as high as the wind is strong
# and coloured by the rating, plus a dotted line for the gusts. A bar needs wind to be tall,
# so "no wind" is visible at a glance. factor and unit convert from knots to the chosen unit.
def make_windsurf_chart(hours, now, factor, unit):
    fig = go.Figure()
    for level, color in RATING_COLORS.items():
        part = hours[hours["rating"] == level]
        fig.add_trace(go.Bar(
            x=part.index, y=part["wind"] * factor, name=level, marker_color=color,
            customdata=part[["gust"]] * factor,
            hovertemplate="%{x|%a %H:%M}<br>" + level + ": %{y:.0f} " + unit + " wind, gusts %{customdata[0]:.0f} " + unit + "<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=hours.index, y=hours["gust"] * factor, mode="lines", name="Gusts",
        line=dict(dash="dot", width=1.5, color="#d95f02"),
        hoverinfo="skip",   # the bars already show the gust value in their hover text
    ))
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper", line=dict(dash="dash", width=1))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=unit,
                      bargap=0.1, legend=dict(orientation="h", y=1.1))
    return fig
