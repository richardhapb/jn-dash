import sys
from dash import Dash, html, dcc, callback, Output, Input
import pytz
import plotly.express as px
import pandas as pd
import dotenv
import os
from sqlalchemy import create_engine

dotenv.load_dotenv()

conn_str = os.getenv("CONN")

if not conn_str:
    print("There is no connection string")
    sys.exit(1)

conn = create_engine(conn_str)

# Initial empty DataFrame structures
data = pd.DataFrame()
category_totals = pd.DataFrame()


def load_data():
    """Load fresh data from the database"""
    df = pd.read_sql("select * from logs", conn)

    # Print check to ensure categories are loaded
    print(f"Data loaded: {len(df)} rows, Categories found: {df['category'].unique()}")

    df["minutes"] = (df["end_time_ms"] - df["init_time_ms"]) / 60_000
    # Convert timestamp to datetime for better plotting
    df["date"] = (
        pd.to_datetime(df["init_time_ms"], unit="ms")
        .dt.tz_localize("UTC")
        .dt.tz_convert(pytz.timezone("America/Santiago"))
    )
    return df


app = Dash(__name__)

# Use dark template for all plots
template = "plotly_dark"

app.layout = html.Div(
    style={
        "backgroundColor": "#111111",
        "color": "#FFFFFF",
        "padding": "20px",
        "minHeight": "100vh",
    },
    children=[
        html.H1(
            children="Time Usage Dashboard", style={"textAlign": "center", "marginBottom": "30px"}
        ),
        html.Div([
            html.H2("Overall Time Distribution"),
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Graph(id="pie-chart"),
                        ],
                        style={"width": "50%"},
                    ),
                    html.Div(
                        [
                            dcc.Graph(id="bar-chart"),
                        ],
                        style={"width": "50%"},
                    ),
                ],
                style={"display": "flex"},
            ),
        ]),
        html.H2("Time Usage Trends", style={"marginTop": "30px"}),
        html.Div(
            [
                html.Div([
                    dcc.Dropdown(
                        id="category-filter",
                        options=[],  # Will be populated when data loads
                        value=[],  # Will be populated when data loads
                        multi=True,
                        style={"backgroundColor": "#222222", "color": "#000000"},
                    ),
                    dcc.Graph(id="time-series"),
                ]),
                html.H2("Daily Breakdown", style={"marginTop": "30px"}),
                dcc.Graph(id="heatmap"),
                dcc.Store(id="store", data={"refresh": True}),
                dcc.Interval(
                    id="interval-component",
                    interval=1000,  # refresh every second (when page is loaded)
                    n_intervals=0,
                    max_intervals=1,  # run once only when page loads
                ),
            ],
        ),
    ],
)


@callback(Output("store", "data"), Input("interval-component", "n_intervals"))
def refresh_data(_):
    """Refresh data from database"""
    global data, category_totals
    data = load_data()
    # Calculate total time spent per category
    category_totals = data.groupby("category")["minutes"].sum().reset_index()
    return {"refresh": True, "timestamp": pd.Timestamp.now().isoformat()}


@callback(Output("pie-chart", "figure"), Input("store", "data"))
def update_pie_chart(_):
    fig = px.pie(
        category_totals,
        values="minutes",
        names="category",
        title="Total Time by Category",
        template=template,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label", textfont_color="white")
    fig.update_layout(font_color="white", title_font_color="white")
    return fig


@callback(Output("bar-chart", "figure"), Input("store", "data"))
def update_bar_chart(_):
    sorted_data = category_totals.sort_values("minutes", ascending=False)
    fig = px.bar(
        sorted_data,
        x="category",
        y="minutes",
        title="Total Minutes by Category",
        template=template,
        color="category",
    )
    return fig


@callback(
    [Output("category-filter", "options"), Output("category-filter", "value")],
    Input("store", "data"),
)
def update_dropdown(_):
    """Update dropdown options and values when data refreshes"""
    categories = data["category"].unique().tolist()
    options = [{"label": cat, "value": cat} for cat in categories]
    print(options)
    return options, categories


@callback(
    Output("time-series", "figure"), [Input("category-filter", "value"), Input("store", "data")]
)
def update_time_series(selected_categories, _):
    filtered_data = (
        data[data["category"].isin(selected_categories)] if selected_categories else data
    )
    # Group by date and category to show daily trends
    daily_data = (
        filtered_data.groupby([pd.Grouper(key="date", freq="D"), "category"])["minutes"]
        .sum()
        .reset_index()
    )

    fig = px.line(
        daily_data,
        x="date",
        y="minutes",
        color="category",
        title="Daily Time Usage by Category",
        template=template,
    )
    return fig


@callback(Output("heatmap", "figure"), Input("store", "data"))
def update_heatmap(_):
    # Create heatmap of activity by day of week and hour
    # These calculations need to happen each time to ensure fresh data
    day_data = data.copy()
    day_data["day_of_week"] = day_data["date"].dt.day_name()
    day_data["hour"] = day_data["date"].dt.hour

    day_data = day_data[day_data["category"] != "sleep"]
    heatmap_data = day_data.groupby(["day_of_week", "hour", "category"])["minutes"].sum().reset_index()

    fig = px.density_heatmap(
        heatmap_data,
        x="hour",
        y="day_of_week",
        z="minutes",
        facet_col="category",
        title="Activity Patterns by Day and Hour",
        template=template,
        category_orders={
            "day_of_week": [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        },
    )
    fig.update_layout(height=600)
    return fig


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=7050)
