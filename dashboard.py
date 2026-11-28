"""
Nabeel Weather Dashboard — beautiful layout with full function documentation.

FUNCTION MAP
────────────────────────────────────────────────────────────────────────────────
_inject_css()               → Injects teal/mint custom CSS for cards, gradients,
                              badges, and responsive layout.

_get(url, params)           → Low-level HTTP GET wrapper; raises ValueError on
                              API error codes.

_search_cities(query, key)  → Calls WeatherAPI autocomplete /search.json and
                              returns up to 10 city candidates. Never raises.

_city_label(candidate)      → Formats "Name, Region, Country" for the dropdown.

_fetch_weather(lat, lon, k) → Fetches 2-day forecast by coordinates from
                              WeatherAPI /forecast.json.

_parse_weather(raw)         → Extracts all dashboard fields from the raw API
                              dict: current conditions, 24-hour hourly array,
                              timezone offset, storm indicators.

_storm_analysis(hourly)     → Derives factual storm indicators from an hourly
                              list: thunder hours, peak gust, pressure fall,
                              first rain/thunder time. Never invents scores.

_chart_data(hourly, offset) → Builds a pandas DataFrame with local-time index
                              for the four 24-hour charts.

_na(value, fmt)             → Returns "N/A" for None/"", otherwise formats value.

_epoch_to_local(epoch, tz)  → Converts a Unix epoch to a naive local datetime
                              using a float UTC offset.

_weather_card(label, value, icon, unit, delta)
                            → Renders a styled HTML metric card.

_badge(text, color)         → Returns an inline HTML coloured badge span.

_make_briefing_pdf(w, text) → Generates a downloadable PDF from weather data +
                              briefing text using fpdf2 with DejaVu font.

_gemini_briefing(w, key)    → Calls Gemini to write a 100-150 word city
                              weather briefing. Falls back gracefully.

_render_current(w)          → Renders the city header + 8 metric cards row.

_render_storm_outlook(w)    → Renders the ⛈ 12-Hour Storm Outlook panel with
                              5 KPI tiles and optional CAPE.

_render_alerts(alerts)      → Renders active weather alerts or a green ✅ banner.

_render_charts(hourly, tz)  → Renders the 4-tab 24-hour chart panel.

_render_briefing(w, gkey)   → Renders the City Briefing expander with AI text,
                              fallback summary, and PDF download button.

show_dashboard(api_key)     → Entry point called from main.py. Orchestrates city
                              search, weather fetch, caching, and all render
                              functions. Injects CSS first.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import datetime
import io
from typing import Any

import requests
import streamlit as st

_API_BASE = "https://api.weatherapi.com/v1"
_FORECAST_URL = f"{_API_BASE}/forecast.json"
_SEARCH_URL = f"{_API_BASE}/search.json"

# ── Teal/mint brand colours ────────────────────────────────────────────────────
_PRIMARY = "#09716C"
_PRIMARY_LIGHT = "#0a9b94"
_BG = "#FAFCFB"
_SECONDARY_BG = "#EAF3F1"
_TEXT = "#183436"
_BORDER = "#CBDDD9"
_ALERT = "#c0392b"
_SUCCESS = "#27ae60"


# ══════════════════════════════════════════════════════════════════════════════
# CSS INJECTION
# ══════════════════════════════════════════════════════════════════════════════

def _inject_css() -> None:
    """
    _inject_css()
    Injects custom CSS into the Streamlit page for the teal/mint theme.
    Covers: metric cards, storm KPI tiles, alert banners, chart container,
    quick-prompt buttons, section headings, and responsive mobile layout.
    Called once at the top of show_dashboard().
    """
    st.markdown(
        f"""
<style>
/* ── Global ─────────────────────────────────────── */
[data-testid="stAppViewContainer"] {{
    background: {_BG};
}}
[data-testid="stSidebar"] {{
    background: {_SECONDARY_BG};
}}

/* ── Dashboard header ───────────────────────────── */
.dash-header {{
    background: linear-gradient(135deg, {_PRIMARY} 0%, {_PRIMARY_LIGHT} 100%);
    border-radius: 1rem;
    padding: 1.4rem 1.8rem;
    color: #fff;
    margin-bottom: 1.2rem;
}}
.dash-header h2 {{
    margin: 0 0 .25rem 0;
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -.01em;
}}
.dash-header .meta {{
    font-size: .82rem;
    opacity: .88;
    display: flex;
    gap: 1.4rem;
    flex-wrap: wrap;
}}

/* ── Metric cards ───────────────────────────────── */
.metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: .75rem;
    margin-bottom: 1rem;
}}
.metric-card {{
    background: #fff;
    border: 1px solid {_BORDER};
    border-radius: .85rem;
    padding: .9rem 1rem;
    text-align: center;
    box-shadow: 0 1px 4px rgba(9,113,108,.07);
    transition: box-shadow .18s;
}}
.metric-card:hover {{
    box-shadow: 0 4px 14px rgba(9,113,108,.13);
}}
.metric-card .icon {{
    font-size: 1.5rem;
    margin-bottom: .3rem;
}}
.metric-card .label {{
    font-size: .72rem;
    color: #6b8c8a;
    text-transform: uppercase;
    letter-spacing: .05em;
    font-weight: 600;
}}
.metric-card .value {{
    font-size: 1.25rem;
    font-weight: 700;
    color: {_TEXT};
    margin-top: .15rem;
}}
.metric-card .unit {{
    font-size: .78rem;
    color: #6b8c8a;
}}

/* ── Storm KPI tiles ────────────────────────────── */
.storm-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: .75rem;
    margin: .8rem 0;
}}
.storm-tile {{
    background: linear-gradient(145deg, #fff 70%, {_SECONDARY_BG});
    border: 1px solid {_BORDER};
    border-left: 4px solid {_PRIMARY};
    border-radius: .85rem;
    padding: .85rem 1rem;
    box-shadow: 0 1px 4px rgba(9,113,108,.06);
}}
.storm-tile .kpi-label {{
    font-size: .7rem;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #6b8c8a;
    font-weight: 600;
}}
.storm-tile .kpi-value {{
    font-size: 1.4rem;
    font-weight: 800;
    color: {_TEXT};
    margin: .2rem 0 0;
}}
.storm-tile .kpi-unit {{
    font-size: .75rem;
    color: {_PRIMARY};
    font-weight: 600;
}}

/* ── Alert banners ──────────────────────────────── */
.alert-banner {{
    background: #fdf2f2;
    border: 1px solid #f5c6c6;
    border-left: 4px solid {_ALERT};
    border-radius: .7rem;
    padding: .8rem 1rem;
    margin: .4rem 0;
    color: #6b1a1a;
    font-size: .88rem;
}}
.no-alert-banner {{
    background: #f0faf3;
    border: 1px solid #b7e4c7;
    border-left: 4px solid {_SUCCESS};
    border-radius: .7rem;
    padding: .65rem 1rem;
    color: #1b5e37;
    font-size: .85rem;
    font-weight: 600;
}}

/* ── Section headers ────────────────────────────── */
.section-title {{
    font-size: 1rem;
    font-weight: 700;
    color: {_TEXT};
    padding: .3rem 0 .6rem;
    border-bottom: 2px solid {_SECONDARY_BG};
    margin-bottom: .8rem;
}}

/* ── Badge ──────────────────────────────────────── */
.badge {{
    display: inline-block;
    padding: .18em .65em;
    border-radius: 999px;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .03em;
}}

/* ── Chart wrapper ──────────────────────────────── */
.chart-wrap {{
    background: #fff;
    border: 1px solid {_BORDER};
    border-radius: .85rem;
    padding: 1rem;
    box-shadow: 0 1px 4px rgba(9,113,108,.05);
}}

/* ── Quick prompts ──────────────────────────────── */
div[data-testid="stHorizontalBlock"] button[kind="secondary"] {{
    border-radius: 999px !important;
    border-color: {_BORDER} !important;
    font-size: .82rem !important;
}}
div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {{
    border-color: {_PRIMARY} !important;
    color: {_PRIMARY} !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# HTML COMPONENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _na(value: Any, fmt: str = "") -> str:
    """
    _na(value, fmt)
    Returns "N/A" when value is None or empty string.
    Otherwise formats with fmt (e.g. ".1f") or returns str(value).
    Used throughout rendering to avoid crashing on missing API fields.
    """
    if value is None or value == "":
        return "N/A"
    return format(value, fmt) if fmt else str(value)


def _badge(text: str, color: str = "#09716C", bg: str = "#EAF3F1") -> str:
    """
    _badge(text, color, bg)
    Returns an inline HTML <span> styled as a coloured pill badge.
    Used in the storm outlook and alert panels.
    """
    return (
        f'<span class="badge" style="background:{bg};color:{color};">{text}</span>'
    )


def _weather_card(label: str, value: str, icon: str, unit: str = "") -> str:
    """
    _weather_card(label, value, icon, unit)
    Returns the HTML string for one metric card in the current-conditions grid.
    Eight cards are assembled into a .metric-grid div and rendered together.
    """
    return f"""
<div class="metric-card">
  <div class="icon">{icon}</div>
  <div class="label">{label}</div>
  <div class="value">{value}<span class="unit"> {unit}</span></div>
</div>"""


def _storm_tile(label: str, value: str, unit: str = "") -> str:
    """
    _storm_tile(label, value, unit)
    Returns HTML for one KPI tile in the 12-hour storm outlook grid.
    Five tiles are assembled into a .storm-grid div.
    """
    return f"""
<div class="storm-tile">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-unit">{unit}</div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# API HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get(url: str, params: dict, timeout: int = 20) -> dict:
    """
    _get(url, params, timeout)
    Low-level HTTP GET with error normalisation.
    Raises ValueError for WeatherAPI error messages.
    Raises requests.HTTPError for non-2xx HTTP responses.
    """
    r = requests.get(url, params=params, timeout=timeout)
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"]["message"])
    r.raise_for_status()
    return data


def _search_cities(query: str, api_key: str) -> list[dict]:
    """
    _search_cities(query, api_key)
    Calls WeatherAPI /search.json autocomplete endpoint.
    Returns up to 10 candidate dicts [{name, region, country, lat, lon}, ...].
    Returns [] on any error — never raises, so the UI degrades gracefully.
    """
    try:
        results = _get(_SEARCH_URL, {"key": api_key, "q": query})
    except Exception:
        return []
    return results[:10] if isinstance(results, list) else []


def _city_label(candidate: dict) -> str:
    """
    _city_label(candidate)
    Formats a WeatherAPI search candidate as "Name, Region, Country".
    Skips empty region to avoid "City,  , Country" artefacts.
    """
    parts = [candidate.get("name", "")]
    if candidate.get("region"):
        parts.append(candidate["region"])
    parts.append(candidate.get("country", ""))
    return ", ".join(p for p in parts if p)


# ══════════════════════════════════════════════════════════════════════════════
# WEATHER DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_weather(lat: float, lon: float, api_key: str) -> dict:
    """
    _fetch_weather(lat, lon, api_key)
    Fetches 2-day forecast from WeatherAPI /forecast.json using coordinates.
    Coordinates are used (not city name) to prevent same-name city confusion.
    Returns the raw API dict for _parse_weather().
    """
    return _get(
        _FORECAST_URL,
        {"key": api_key, "q": f"{lat},{lon}", "days": 2, "alerts": "yes"},
    )


def _epoch_to_local(epoch: int, tz_offset_hours: float) -> datetime.datetime:
    """
    _epoch_to_local(epoch, tz_offset_hours)
    Converts a Unix epoch int to a naive local datetime using a float UTC offset.
    Used to build local-time X-axis labels for the 24-hour charts.
    """
    utc = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).replace(tzinfo=None)
    return utc + datetime.timedelta(hours=tz_offset_hours)


def _parse_weather(raw: dict) -> dict:
    """
    _parse_weather(raw)
    Extracts all dashboard fields from a raw WeatherAPI response dict.
    Returns a flat dict with:
      - City metadata (name, lat, lon, timezone, local_time, tz_offset)
      - Current conditions (temp, feelslike, condition, wind, gusts, humidity, pressure, precip, uv, vis)
      - 24-hour hourly list (sorted, up to 24 entries after local now)
      - Storm indicators (delegated to _storm_analysis)
      - Alerts list
    """
    loc = raw["location"]
    cur = raw["current"]
    local_epoch = loc["localtime_epoch"]
    local_dt_str = loc["localtime"]

    # Derive float UTC offset from API's local time string vs UTC now
    try:
        local_dt = datetime.datetime.strptime(local_dt_str, "%Y-%m-%d %H:%M")
        utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        tz_offset = (local_dt - utc_now).total_seconds() / 3600
    except Exception:
        tz_offset = 0.0

    # Collect next 24 hours from both forecast days
    hourly: list[dict] = []
    for day in raw["forecast"]["forecastday"]:
        for h in day["hour"]:
            if h["time_epoch"] > local_epoch:
                hourly.append(h)
    hourly = sorted(hourly, key=lambda h: h["time_epoch"])[:24]

    storm = _storm_analysis(hourly[:12])
    alerts = raw.get("alerts", {}).get("alert", [])

    return {
        "city": (
            f"{loc['name']}, {loc.get('region', '')}, {loc['country']}"
            .replace(", , ", ", ")
        ),
        "local_time": local_dt_str,
        "timezone": loc["tz_id"],
        "lat": loc["lat"],
        "lon": loc["lon"],
        "tz_offset": tz_offset,
        # Current conditions
        "temp_c": cur.get("temp_c"),
        "feelslike_c": cur.get("feelslike_c"),
        "condition": cur["condition"]["text"],
        "condition_icon": cur["condition"].get("icon", ""),
        "wind_kph": cur.get("wind_kph"),
        "wind_dir": cur.get("wind_dir", ""),
        "gust_kph": cur.get("gust_kph"),
        "humidity": cur.get("humidity"),
        "pressure_mb": cur.get("pressure_mb"),
        "precip_mm": cur.get("precip_mm"),
        "uv": cur.get("uv"),
        "vis_km": cur.get("vis_km"),
        # Storm (12-hour)
        **{f"storm_{k}": v for k, v in storm.items()},
        # Forecast
        "hourly": hourly,
        "alerts": alerts,
    }


def _storm_analysis(hourly: list[dict]) -> dict:
    """
    _storm_analysis(hourly)
    Derives factual storm risk indicators from a list of hourly forecast dicts.
    Returns:
      thunder_hours        – count + list of times with will_it_thunder or >=40% chance
      rain_hours           – count of hours with precip > 0.1 mm
      heavy_rain_hours     – count of hours with precip >= 2.5 mm
      first_rain_at        – local time string of first rain hour
      first_thunder_at     – local time string of first thunder hour
      peak_gust_kph        – maximum gust across the window
      total_precip_mm      – sum of all precipitation
      pressure_fall_mb     – drop from first to minimum pressure
      max_humidity_pct     – peak humidity across the window
    Never returns a storm score or converts probabilities to severity levels.
    """
    if not hourly:
        return {}

    thunder = [h for h in hourly if h.get("will_it_thunder") or (h.get("chance_of_thunder") or 0) >= 40]
    rain = [h for h in hourly if (h.get("precip_mm") or 0) > 0.1]
    heavy = [h for h in hourly if (h.get("precip_mm") or 0) >= 2.5]

    peak_gust = max((h.get("gust_kph") or 0 for h in hourly), default=0)
    total = round(sum(h.get("precip_mm") or 0 for h in hourly), 2)

    pressures = [h["pressure_mb"] for h in hourly if h.get("pressure_mb")]
    pfall = round(pressures[0] - min(pressures), 1) if len(pressures) >= 2 else None

    return {
        "thunder_hour_count": len(thunder),
        "thunder_hours": [h["time"] for h in thunder],
        "rain_hour_count": len(rain),
        "heavy_rain_hour_count": len(heavy),
        "first_rain_at": rain[0]["time"] if rain else None,
        "first_thunder_at": thunder[0]["time"] if thunder else None,
        "peak_gust_kph": round(peak_gust, 1) if peak_gust else None,
        "total_precip_mm": total,
        "pressure_fall_mb": pfall,
        "max_humidity_pct": max((h.get("humidity") or 0 for h in hourly), default=0),
    }


def _chart_data(hourly: list[dict], tz_offset: float):
    """
    _chart_data(hourly, tz_offset)
    Builds a pandas DataFrame indexed by local-time strings (HH:MM) with columns:
      "Rain chance (%)", "Precipitation (mm)", "Gust (kph)", "Temperature (°C)"
    Returns None if pandas is unavailable or hourly is empty.
    Used by _render_charts() to feed Streamlit's native bar/line charts.
    """
    try:
        import pandas as pd
    except ImportError:
        return None
    if not hourly:
        return None

    rows = []
    for h in hourly:
        rows.append({
            "Time": _epoch_to_local(h["time_epoch"], tz_offset).strftime("%H:%M"),
            "Rain chance (%)": h.get("chance_of_rain"),
            "Precipitation (mm)": h.get("precip_mm"),
            "Gust (kph)": h.get("gust_kph"),
            "Temperature (°C)": h.get("temp_c"),
        })
    df = pd.DataFrame(rows)
    return df.set_index("Time") if not df.empty else None


# ══════════════════════════════════════════════════════════════════════════════
# RENDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _render_current(w: dict) -> None:
    """
    _render_current(w)
    Renders the city header card (gradient banner) and 8 metric cards in a
    responsive CSS grid. Cards: Temperature, Feels like, Condition, Humidity,
    Wind, Gusts, Pressure, Precipitation.
    Uses _weather_card() and _na() helpers.
    """
    wind_val = f"{_na(w['wind_kph'])} {w.get('wind_dir', '')}".strip()

    # Gradient header
    st.markdown(
        f"""<div class="dash-header">
  <h2>🌍 {w['city']}</h2>
  <div class="meta">
    <span>🕐 {w['local_time']}</span>
    <span>🌐 {w['timezone']}</span>
    <span>📍 {w['lat']:.4f}°N, {w['lon']:.4f}°E</span>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # 8-card metric grid
    cards_html = "".join([
        _weather_card("Temperature",   _na(w["temp_c"]),     "🌡", "°C"),
        _weather_card("Feels like",    _na(w["feelslike_c"]), "🤔", "°C"),
        _weather_card("Condition",     w["condition"],        "☁️"),
        _weather_card("Humidity",      _na(w["humidity"]),   "💧", "%"),
        _weather_card("Wind",          wind_val,              "🌬", "kph"),
        _weather_card("Gusts",         _na(w["gust_kph"]),   "💨", "kph"),
        _weather_card("Pressure",      _na(w["pressure_mb"]),"🔵", "mb"),
        _weather_card("Precipitation", _na(w["precip_mm"]),  "🌧", "mm"),
    ])
    st.markdown(
        f'<div class="metric-grid">{cards_html}</div>',
        unsafe_allow_html=True,
    )


def _render_storm_outlook(w: dict) -> None:
    """
    _render_storm_outlook(w)
    Renders the ⛈ 12-Hour Storm Outlook panel inside a Streamlit expander.
    Five KPI storm tiles: Thunder hours, Peak gust, Precip total, Pressure
    fall, First wet hour.
    Shows CAPE only if the API provides it (never added manually).
    Uses _storm_tile() helper. Displays all data from _storm_analysis().
    """
    with st.expander("⛈ 12-Hour Storm Outlook", expanded=True):
        st.markdown('<div class="section-title">Storm Indicators — next 12 hours</div>', unsafe_allow_html=True)

        # First wet hour label
        fw = w.get("storm_first_rain_at")
        if fw:
            try:
                fw_disp = datetime.datetime.strptime(fw, "%Y-%m-%d %H:%M").strftime("%H:%M")
            except Exception:
                fw_disp = fw
        else:
            fw_disp = "None forecast"

        pfall = w.get("storm_pressure_fall_mb")
        pfall_str = f"{pfall}" if pfall is not None else "N/A"

        tiles_html = "".join([
            _storm_tile("⚡ Thunder hours",  str(w.get("storm_thunder_hour_count", 0)), "hours"),
            _storm_tile("💨 Peak gust",      _na(w.get("storm_peak_gust_kph")),          "kph"),
            _storm_tile("🌧 Precip total",   _na(w.get("storm_total_precip_mm")),         "mm"),
            _storm_tile("📉 Pressure fall",  pfall_str,                                   "mb"),
            _storm_tile("🕐 First wet hour", fw_disp,                                     ""),
        ])
        st.markdown(
            f'<div class="storm-grid">{tiles_html}</div>',
            unsafe_allow_html=True,
        )

        # Optional extra stats
        extra_cols = st.columns(3)
        rain_h = w.get("storm_rain_hour_count", 0)
        heavy_h = w.get("storm_heavy_rain_hour_count", 0)
        max_hum = w.get("storm_max_humidity_pct", 0)

        extra_cols[0].caption(f"🌦 Rain hours: **{rain_h}** / 12")
        extra_cols[1].caption(f"⛈ Heavy rain hours: **{heavy_h}** / 12  (≥2.5 mm)")
        extra_cols[2].caption(f"💧 Peak humidity: **{max_hum}** %")

        cape = w.get("storm_cape")
        if cape is not None:
            st.caption(f"🌪 CAPE (max): **{cape} J/kg**")


def _render_alerts(alerts: list[dict]) -> None:
    """
    _render_alerts(alerts)
    Renders all active WeatherAPI weather alerts as styled red banner cards.
    Shows a green ✅ "No active weather alerts" banner when the list is empty.
    Limited to the first 10 alerts to avoid overflow.
    """
    if not alerts:
        st.markdown(
            '<div class="no-alert-banner">✅ No active weather alerts for this location.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="section-title">🚨 Active Weather Alerts ({len(alerts)})</div>',
        unsafe_allow_html=True,
    )
    for alert in alerts[:10]:
        event = alert.get("event", "Alert")
        desc = (alert.get("desc") or alert.get("headline") or "").strip()[:400]
        st.markdown(
            f'<div class="alert-banner"><strong>⚠ {event}</strong><br>{desc}</div>',
            unsafe_allow_html=True,
        )


def _render_charts(hourly: list[dict], tz_offset: float) -> None:
    """
    _render_charts(hourly, tz_offset)
    Renders a 4-tab chart panel: Rain chance (bar), Precipitation (bar),
    Gust speed (line), Temperature (line). All charts use city local time on
    the X-axis including forecasts that cross midnight.
    Calls _chart_data() to build the DataFrame. Shows an info message if
    pandas is unavailable or data is empty.
    """
    df = _chart_data(hourly, tz_offset)
    if df is None or df.empty:
        st.info("📊 Hourly chart data is unavailable for this location.")
        return

    st.markdown('<div class="section-title">📈 24-Hour Forecast Charts (local time)</div>', unsafe_allow_html=True)

    tab_rain, tab_precip, tab_gust, tab_temp = st.tabs(
        ["🌧 Rain chance", "💧 Precipitation", "💨 Gusts", "🌡 Temperature"]
    )
    with tab_rain:
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.caption("Rain chance (%) — next 24 hours")
        st.bar_chart(df[["Rain chance (%)"]], color=_PRIMARY)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_precip:
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.caption("Precipitation (mm) — next 24 hours")
        st.bar_chart(df[["Precipitation (mm)"]], color=_PRIMARY_LIGHT)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_gust:
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.caption("Gust speed (kph) — next 24 hours")
        st.line_chart(df[["Gust (kph)"]], color=["#e67e22"])
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_temp:
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.caption("Temperature (°C) — next 24 hours")
        st.line_chart(df[["Temperature (°C)"]], color=["#2980b9"])
        st.markdown('</div>', unsafe_allow_html=True)


def _make_briefing_pdf(weather: dict, briefing_text: str) -> bytes:
    """
    _make_briefing_pdf(weather, briefing_text)
    Generates a downloadable PDF from weather data and briefing text.
    Uses fpdf2 with DejaVu font (supports Urdu/Arabic right-to-left text).
    Searches for font at: repo root, Windows Fonts, Linux dejavu path.
    Raises ValueError if no compatible font is found.
    Returns raw PDF bytes for st.download_button.
    """
    from pathlib import Path
    import os
    from fpdf import FPDF

    fonts = [
        Path(__file__).resolve().parent / "DejaVuSans.ttf",
        Path(os.getenv("WINDIR", r"C:\Windows")) / "Fonts" / "tahoma.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font_path = next((p for p in fonts if p.is_file()), None)
    if font_path is None:
        raise ValueError("No compatible font found for PDF.")

    pdf = FPDF()
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    pdf.add_font("Report", fname=str(font_path))
    pdf.set_text_shaping(True)

    urdu = any("\u0600" <= ch <= "\u06ff" for ch in briefing_text)
    align = "R" if urdu else "L"

    def line(text: str, size: int = 11, a: str = "L") -> None:
        pdf.set_font("Report", size=size)
        pdf.multi_cell(0, 8, text, align=a, new_x="LMARGIN", new_y="NEXT")

    line("موسم کی رپورٹ" if urdu else "Weather & Storm Briefing", 18, align)
    line(f"{weather['city']}  |  {weather['local_time']}  |  {weather['timezone']}", 10)
    pdf.ln(3)

    # Current conditions summary
    line(
        f"Temp: {_na(weather['temp_c'])}°C  |  Feels like: {_na(weather['feelslike_c'])}°C  "
        f"|  {weather['condition']}  |  Humidity: {_na(weather['humidity'])}%",
        9,
    )
    line(
        f"Wind: {_na(weather['wind_kph'])} kph {weather.get('wind_dir','')}  "
        f"|  Gusts: {_na(weather['gust_kph'])} kph  "
        f"|  Pressure: {_na(weather['pressure_mb'])} mb",
        9,
    )
    pdf.ln(3)

    # Storm outlook
    line("12-Hour Storm Outlook:", 11, align)
    line(
        f"  Thunder hours: {weather.get('storm_thunder_hour_count', 0)}  |  "
        f"Peak gust: {_na(weather.get('storm_peak_gust_kph'))} kph  |  "
        f"Precip: {_na(weather.get('storm_total_precip_mm'))} mm  |  "
        f"Pressure fall: {_na(weather.get('storm_pressure_fall_mb'))} mb",
        9,
    )
    pdf.ln(3)

    line(briefing_text, 12, align)
    return bytes(pdf.output())


def _gemini_briefing(weather: dict, google_api_key: str) -> str:
    """
    _gemini_briefing(weather, google_api_key)
    Calls Gemini (gemini-3.1-flash-lite) to generate a 100-150 word city
    weather briefing from current conditions and storm indicators.
    Returns the stripped text string.
    Raises on API error — caller catches and falls back to plain text.
    """
    from google import genai

    client = genai.Client(api_key=google_api_key)
    prompt = (
        f"Write a concise 100-150 word weather briefing for {weather['city']}. "
        f"Current: {weather['temp_c']}°C, {weather['condition']}, "
        f"feels like {weather['feelslike_c']}°C, wind {weather['wind_kph']} kph {weather.get('wind_dir','')}, "
        f"humidity {weather['humidity']}%, pressure {weather['pressure_mb']} mb. "
        f"12-hour outlook: {weather.get('storm_thunder_hour_count',0)} thunder hour(s), "
        f"peak gust {weather.get('storm_peak_gust_kph','N/A')} kph, "
        f"precip {weather.get('storm_total_precip_mm',0)} mm. "
        "Be factual. Do not invent data or add unasked forecasts."
    )
    response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
    return (response.text or "").strip()


def _render_briefing(w: dict, google_api_key: str | None) -> None:
    """
    _render_briefing(w, google_api_key)
    Renders the City Briefing expander with either:
      - A Gemini AI-generated 150-word briefing (when GOOGLE_API_KEY is set)
      - A plain-text structured fallback (when Gemini is unavailable)
    Caches the briefing in st.session_state keyed by lat/lon/time so it isn't
    regenerated when the user switches chart tabs.
    Provides a "⬇ Download PDF" button via _make_briefing_pdf().
    """
    with st.expander("📋 City Briefing & PDF Download", expanded=False):
        briefing_key = f"briefing_{w['lat']}_{w['lon']}_{w['local_time']}"
        briefing = st.session_state.get(briefing_key)

        if briefing is None:
            if google_api_key:
                try:
                    with st.spinner("Generating city briefing…"):
                        briefing = _gemini_briefing(w, google_api_key)
                        st.session_state[briefing_key] = briefing
                except Exception:
                    briefing = None

        if briefing is None:
            fw = w.get("storm_first_rain_at")
            fw_disp = "None forecast"
            if fw:
                try:
                    fw_disp = datetime.datetime.strptime(fw, "%Y-%m-%d %H:%M").strftime("%H:%M")
                except Exception:
                    fw_disp = fw

            briefing = (
                f"{w['city']} — {w['local_time']}\n\n"
                f"Temperature: {_na(w['temp_c'])} °C (feels like {_na(w['feelslike_c'])} °C)\n"
                f"Condition: {w['condition']}\n"
                f"Wind: {_na(w['wind_kph'])} kph {w.get('wind_dir','')}, gusts {_na(w['gust_kph'])} kph\n"
                f"Humidity: {_na(w['humidity'])} %  |  Pressure: {_na(w['pressure_mb'])} mb\n"
                f"Precipitation: {_na(w['precip_mm'])} mm\n\n"
                f"12-Hour Storm Outlook:\n"
                f"  Thunder hours: {w.get('storm_thunder_hour_count', 0)}\n"
                f"  Peak gust: {_na(w.get('storm_peak_gust_kph'))} kph\n"
                f"  Total precipitation: {_na(w.get('storm_total_precip_mm'))} mm\n"
                f"  Pressure fall: {_na(w.get('storm_pressure_fall_mb'))} mb\n"
                f"  First wet hour: {fw_disp}\n"
            )
            st.session_state[briefing_key] = briefing

        st.markdown(briefing)

        try:
            pdf_bytes = _make_briefing_pdf(w, briefing)
            safe = "".join(c for c in w["city"].split(",")[0] if c.isalnum() or c == " ").strip().replace(" ", "_")
            st.download_button(
                "⬇ Download Weather Briefing PDF",
                data=pdf_bytes,
                file_name=f"weather_{safe}.pdf",
                mime="application/pdf",
                key=f"pdf-{briefing_key}",
            )
        except ValueError as e:
            st.caption(f"PDF not available: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def show_dashboard(weather_api_key: str | None) -> None:
    """
    show_dashboard(weather_api_key)
    ─────────────────────────────
    Entry point called from main.py immediately after st.set_page_config().

    Orchestration order:
      1. _inject_css()          — inject teal/mint theme styles
      2. City search UI         — text input + 🔍 button (no selectbox widget,
                                  uses st.selectbox only for city list)
      3. _search_cities()       — autocomplete candidates
      4. City selectbox         — user picks the exact city
      5. _fetch_weather()       — coordinates-based API call
      6. _parse_weather()       — normalise raw response
      7. Session-state cache    — skip re-fetch when only a chart tab changes
      8. _render_current()      — gradient header + 8 metric cards
      9. _render_storm_outlook() — ⛈ 12-hour storm KPI tiles
     10. _render_alerts()       — weather alert banners
     11. _render_charts()       — 4-tab 24-hour chart panel
     12. _render_briefing()     — city briefing expander + PDF download

    Shows st.info if WEATHER_API_KEY is missing.
    Shows st.warning on network/API errors, then returns without crashing.
    """
    _inject_css()

    if not weather_api_key:
        st.info(
            "🔑 Add **WEATHER_API_KEY** in Streamlit Secrets or your `.env` file to enable the dashboard."
        )
        return

    # ── City search ────────────────────────────────────────────────────────────
    col_q, col_btn = st.columns([5, 1])
    with col_q:
        query = st.text_input(
            "Search city",
            value=st.session_state.get("dashboard_city_query", "Lahore"),
            placeholder="Search a city worldwide…",
            label_visibility="collapsed",
            key="dashboard_city_query_input",
        )
    with col_btn:
        do_search = st.button("🔍 Search", use_container_width=True)

    # Trigger on button press or first load
    if do_search or "dashboard_candidates" not in st.session_state:
        q = query.strip() or "Lahore"
        candidates = _search_cities(q, weather_api_key)
        if not candidates:
            candidates = _search_cities("Lahore, Pakistan", weather_api_key)
        st.session_state["dashboard_candidates"] = candidates
        if do_search:
            st.session_state.pop("dashboard_selected_idx", None)
            st.session_state.pop("dashboard_weather", None)

    candidates: list[dict] = st.session_state.get("dashboard_candidates", [])
    if not candidates:
        st.warning("⚠ No cities found. Try a different search term.")
        return

    labels = [_city_label(c) for c in candidates]
    prev_idx = st.session_state.get("dashboard_selected_idx", 0)
    selected_idx = st.selectbox(
        "Select the correct city",
        range(len(labels)),
        format_func=lambda i: labels[i],
        index=min(prev_idx, len(labels) - 1),
        label_visibility="collapsed",
    )
    selected = candidates[selected_idx]
    lat, lon = selected["lat"], selected["lon"]

    # ── Fetch & cache ──────────────────────────────────────────────────────────
    cached = st.session_state.get("dashboard_weather", {})
    if cached.get("lat") != lat or cached.get("lon") != lon:
        with st.spinner("🌍 Fetching live weather…"):
            try:
                raw = _fetch_weather(lat, lon, weather_api_key)
                weather = _parse_weather(raw)
                st.session_state["dashboard_weather"] = weather
                st.session_state["dashboard_selected_idx"] = selected_idx
            except (ValueError, requests.RequestException) as err:
                st.warning(f"⚠ Could not fetch weather data: {err}")
                return
    else:
        weather = cached

    w = weather
    st.markdown("---")

    # ── Render sections ────────────────────────────────────────────────────────
    _render_current(w)
    _render_storm_outlook(w)
    _render_alerts(w.get("alerts", []))
    st.markdown("---")
    _render_charts(w.get("hourly", []), w.get("tz_offset", 0))
    st.markdown("---")
    _render_briefing(w, st.session_state.get("_google_api_key_for_briefing"))
