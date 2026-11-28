"""Nabeel weather dashboard: search, current conditions, storm outlook, charts."""

from __future__ import annotations

import datetime
import io
from typing import Any

import requests
import streamlit as st

_API_BASE = "https://api.weatherapi.com/v1"
_FORECAST_URL = f"{_API_BASE}/forecast.json"
_SEARCH_URL = f"{_API_BASE}/search.json"


# ── helpers ────────────────────────────────────────────────────────────────────

def _get(url: str, params: dict, timeout: int = 20) -> dict:
    r = requests.get(url, params=params, timeout=timeout)
    data = r.json()
    if "error" in data:
        raise ValueError(data["error"]["message"])
    r.raise_for_status()
    return data


def _na(value: Any, fmt: str = "") -> str:
    """Format a value or return 'N/A'."""
    if value is None or value == "":
        return "N/A"
    return format(value, fmt) if fmt else str(value)


def _epoch_to_local(epoch: int, tz_offset_hours: float) -> datetime.datetime:
    utc = datetime.datetime.utcfromtimestamp(epoch)
    return utc + datetime.timedelta(hours=tz_offset_hours)


# ── city search ────────────────────────────────────────────────────────────────

def _search_cities(query: str, api_key: str) -> list[dict]:
    """Return up to 10 city candidates from WeatherAPI autocomplete."""
    try:
        results = _get(_SEARCH_URL, {"key": api_key, "q": query})
    except Exception:
        return []
    return results[:10] if isinstance(results, list) else []


def _city_label(candidate: dict) -> str:
    parts = [candidate.get("name", "")]
    if candidate.get("region"):
        parts.append(candidate["region"])
    parts.append(candidate.get("country", ""))
    return ", ".join(p for p in parts if p)


# ── weather fetch ──────────────────────────────────────────────────────────────

def _fetch_weather(lat: float, lon: float, api_key: str) -> dict:
    """Fetch current + 2-day forecast by coordinates."""
    return _get(
        _FORECAST_URL,
        {"key": api_key, "q": f"{lat},{lon}", "days": 2, "alerts": "yes"},
    )


def _parse_weather(raw: dict) -> dict:
    """Extract the data the dashboard needs from a raw API response."""
    loc = raw["location"]
    cur = raw["current"]

    # Timezone offset for local time math
    # WeatherAPI gives localtime_epoch and localtime string; derive offset
    local_epoch = loc["localtime_epoch"]
    utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    local_dt_str = loc["localtime"]          # "2025-01-01 14:30"
    try:
        local_dt = datetime.datetime.strptime(local_dt_str, "%Y-%m-%d %H:%M")
        tz_offset = (local_dt - utc_now).total_seconds() / 3600
    except Exception:
        tz_offset = 0.0

    # Build 24-hour hourly array starting from local now
    hourly: list[dict] = []
    for day in raw["forecast"]["forecastday"]:
        for h in day["hour"]:
            epoch = h["time_epoch"]
            if epoch > local_epoch:
                hourly.append(h)
    hourly = sorted(hourly, key=lambda h: h["time_epoch"])[:24]

    # 12-hour storm outlook
    storm_hours: list[dict] = []
    for h in hourly[:12]:
        storm_hours.append(h)

    thunder_hours = sum(
        1 for h in storm_hours
        if h.get("will_it_thunder") or h.get("chance_of_thunder", 0) >= 40
    )
    peak_gust = max((h.get("gust_kph") or 0 for h in storm_hours), default=None)
    precip_total = sum(h.get("precip_mm") or 0 for h in storm_hours)
    # Pressure fall: difference between first and minimum pressure in 12h
    pressures = [h.get("pressure_mb") for h in storm_hours if h.get("pressure_mb")]
    pressure_fall = None
    if len(pressures) >= 2:
        pressure_fall = round(pressures[0] - min(pressures), 1)
    # First wet hour
    first_wet = next(
        (h["time"] for h in storm_hours if (h.get("precip_mm") or 0) > 0.1),
        None,
    )
    # CAPE — only if provider supplies it
    cape_values = [h.get("cape") for h in storm_hours if h.get("cape") is not None]
    cape = max(cape_values) if cape_values else None

    alerts = raw.get("alerts", {}).get("alert", [])

    return {
        "city": f"{loc['name']}, {loc.get('region', '')}, {loc['country']}".replace(", , ", ", "),
        "local_time": local_dt_str,
        "timezone": loc["tz_id"],
        "lat": loc["lat"],
        "lon": loc["lon"],
        "tz_offset": tz_offset,
        # Current
        "temp_c": cur.get("temp_c"),
        "condition": cur["condition"]["text"],
        "feelslike_c": cur.get("feelslike_c"),
        "wind_kph": cur.get("wind_kph"),
        "wind_dir": cur.get("wind_dir"),
        "gust_kph": cur.get("gust_kph"),
        "humidity": cur.get("humidity"),
        "pressure_mb": cur.get("pressure_mb"),
        "precip_mm": cur.get("precip_mm"),
        # Storm outlook (12-hour)
        "storm_thunder_hours": thunder_hours,
        "storm_peak_gust_kph": peak_gust,
        "storm_precip_total_mm": round(precip_total, 1),
        "storm_pressure_fall_mb": pressure_fall,
        "storm_first_wet_hour": first_wet,
        "storm_cape": cape,
        # Hourly (24h for charts)
        "hourly": hourly,
        # Alerts
        "alerts": alerts,
    }


# ── city briefing PDF ──────────────────────────────────────────────────────────

def _make_briefing_pdf(weather: dict, briefing_text: str) -> bytes:
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
        raise ValueError("No compatible font found for the city briefing PDF.")

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

    line("City Weather Briefing", 18, align)
    line(f"{weather['city']}  |  {weather['local_time']}  |  {weather['timezone']}", 10)
    pdf.ln(3)
    line(briefing_text, 12, align)
    return bytes(pdf.output())


# ── Gemini city briefing ───────────────────────────────────────────────────────

def _gemini_briefing(weather: dict, google_api_key: str) -> str:
    """Generate a 150-word city weather briefing via Gemini."""
    from google import genai

    client = genai.Client(api_key=google_api_key)
    prompt = (
        f"Write a concise 100-150 word weather briefing for {weather['city']}. "
        f"Current: {weather['temp_c']}°C, {weather['condition']}, "
        f"feels like {weather['feelslike_c']}°C, wind {weather['wind_kph']} kph {weather['wind_dir']}, "
        f"humidity {weather['humidity']}%, pressure {weather['pressure_mb']} mb. "
        f"12-hour outlook: {weather['storm_thunder_hours']} thunder hour(s), "
        f"peak gust {weather['storm_peak_gust_kph']} kph, "
        f"total precip {weather['storm_precip_total_mm']} mm. "
        "Be factual and concise. Do not invent data."
    )
    response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
    return (response.text or "").strip()


# ── chart helpers ──────────────────────────────────────────────────────────────

def _chart_data(hourly: list[dict], tz_offset: float) -> dict:
    """Build chart series from hourly data, using local time labels."""
    import pandas as pd

    rows = []
    for h in hourly:
        local_dt = _epoch_to_local(h["time_epoch"], tz_offset)
        rows.append(
            {
                "Time": local_dt.strftime("%H:%M"),
                "Rain chance (%)": h.get("chance_of_rain"),
                "Precipitation (mm)": h.get("precip_mm"),
                "Gust (kph)": h.get("gust_kph"),
                "Temperature (°C)": h.get("temp_c"),
            }
        )
    return pd.DataFrame(rows).set_index("Time") if rows else None


# ── main dashboard ─────────────────────────────────────────────────────────────

def show_dashboard(weather_api_key: str | None) -> None:
    """Render the full weather dashboard. Called from main.py."""
    if not weather_api_key:
        st.info("Add WEATHER_API_KEY in Streamlit Secrets or .env to enable the dashboard.")
        return

    # ── City search ────────────────────────────────────────────────────────────
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        query = st.text_input(
            "Search city",
            value=st.session_state.get("dashboard_city_query", "Lahore"),
            label_visibility="collapsed",
            placeholder="Search a city…",
            key="dashboard_city_query_input",
        )
    with col_btn:
        do_search = st.button("🔍 Search", use_container_width=True)

    # Trigger search on button click or first load
    if do_search or "dashboard_candidates" not in st.session_state:
        q = query.strip() or "Lahore"
        candidates = _search_cities(q, weather_api_key)
        if not candidates:
            # Fall back to Lahore
            candidates = _search_cities("Lahore, Pakistan", weather_api_key)
        st.session_state["dashboard_candidates"] = candidates
        # Reset selection when query changes
        if do_search:
            st.session_state.pop("dashboard_selected_idx", None)
            st.session_state.pop("dashboard_weather", None)

    candidates: list[dict] = st.session_state.get("dashboard_candidates", [])

    if candidates:
        labels = [_city_label(c) for c in candidates]
        prev_idx = st.session_state.get("dashboard_selected_idx", 0)
        selected_idx = st.selectbox(
            "Select city",
            range(len(labels)),
            format_func=lambda i: labels[i],
            index=min(prev_idx, len(labels) - 1),
            label_visibility="collapsed",
            key="dashboard_city_select",
        )
        selected = candidates[selected_idx]
        lat, lon = selected["lat"], selected["lon"]

        # Only re-fetch when the selected coordinates change
        cached = st.session_state.get("dashboard_weather", {})
        if (
            cached.get("lat") != lat
            or cached.get("lon") != lon
            or "dashboard_weather" not in st.session_state
        ):
            with st.spinner("Fetching weather…"):
                try:
                    raw = _fetch_weather(lat, lon, weather_api_key)
                    weather = _parse_weather(raw)
                    st.session_state["dashboard_weather"] = weather
                    st.session_state["dashboard_selected_idx"] = selected_idx
                except (ValueError, requests.RequestException) as err:
                    st.warning(f"Could not fetch weather: {err}")
                    return
        else:
            weather = cached
    else:
        st.warning("No cities found. Try a different search term.")
        return

    w = weather

    # ── Current conditions ─────────────────────────────────────────────────────
    st.markdown(f"### 🌍 {w['city']}")
    meta_cols = st.columns(3)
    meta_cols[0].caption(f"🕐 Local time: **{w['local_time']}**")
    meta_cols[1].caption(f"🌐 Timezone: **{w['timezone']}**")
    meta_cols[2].caption(f"📍 {w['lat']:.4f}°N, {w['lon']:.4f}°E")

    cond_cols = st.columns(4)
    cond_cols[0].metric("🌡 Temperature", f"{_na(w['temp_c'])} °C")
    cond_cols[1].metric("🤔 Feels like", f"{_na(w['feelslike_c'])} °C")
    cond_cols[2].metric("☁ Condition", w["condition"])
    cond_cols[3].metric("💧 Humidity", f"{_na(w['humidity'])} %")

    wind_cols = st.columns(4)
    wind_label = f"{_na(w['wind_kph'])} kph {w.get('wind_dir', '')}".strip()
    wind_cols[0].metric("🌬 Wind", wind_label)
    wind_cols[1].metric("💨 Gusts", f"{_na(w['gust_kph'])} kph")
    wind_cols[2].metric("🔵 Pressure", f"{_na(w['pressure_mb'])} mb")
    wind_cols[3].metric("🌧 Precipitation", f"{_na(w['precip_mm'])} mm")

    st.divider()

    # ── 12-hour storm outlook ──────────────────────────────────────────────────
    with st.expander("⛈ 12-Hour Storm Outlook", expanded=True):
        s_cols = st.columns(5)
        s_cols[0].metric("⚡ Thunder hours", w["storm_thunder_hours"])
        s_cols[1].metric("💨 Peak gust", f"{_na(w['storm_peak_gust_kph'])} kph")
        s_cols[2].metric("🌧 Precip total", f"{_na(w['storm_precip_total_mm'])} mm")

        pf = w["storm_pressure_fall_mb"]
        s_cols[3].metric("📉 Pressure fall", f"{_na(pf)} mb" if pf is not None else "N/A")

        fw = w["storm_first_wet_hour"]
        if fw:
            # Reformat to HH:MM only
            try:
                fw_disp = datetime.datetime.strptime(fw, "%Y-%m-%d %H:%M").strftime("%H:%M")
            except Exception:
                fw_disp = fw
        else:
            fw_disp = "None forecast"
        s_cols[4].metric("🕐 First wet hour", fw_disp)

        if w["storm_cape"] is not None:
            st.caption(f"CAPE (max): {w['storm_cape']} J/kg")

    # ── Weather alerts ─────────────────────────────────────────────────────────
    alerts = w.get("alerts", [])
    if alerts:
        with st.expander(f"🚨 Weather Alerts ({len(alerts)})", expanded=True):
            for alert in alerts:
                st.warning(
                    f"**{alert.get('event', 'Alert')}**  \n"
                    f"{alert.get('desc', '').strip()[:500]}"
                )
    else:
        st.caption("✅ No active weather alerts.")

    st.divider()

    # ── 24-hour charts ─────────────────────────────────────────────────────────
    try:
        import pandas as pd
        df = _chart_data(w["hourly"], w["tz_offset"])
    except ImportError:
        df = None

    if df is not None and not df.empty:
        tab_rain, tab_precip, tab_gust, tab_temp = st.tabs(
            ["🌧 Rain chance", "💧 Precipitation", "💨 Gusts", "🌡 Temperature"]
        )
        with tab_rain:
            st.markdown("**Rain chance (%) — next 24 h (local time)**")
            st.bar_chart(df[["Rain chance (%)"]])
        with tab_precip:
            st.markdown("**Precipitation (mm) — next 24 h (local time)**")
            st.bar_chart(df[["Precipitation (mm)"]])
        with tab_gust:
            st.markdown("**Gust speed (kph) — next 24 h (local time)**")
            st.line_chart(df[["Gust (kph)"]])
        with tab_temp:
            st.markdown("**Temperature (°C) — next 24 h (local time)**")
            st.line_chart(df[["Temperature (°C)"]])
    else:
        st.info("Hourly chart data is unavailable for this location.")

    st.divider()

    # ── City briefing ──────────────────────────────────────────────────────────
    with st.expander("📋 City Briefing", expanded=False):
        # Cache the briefing so it isn't regenerated on tab switches
        briefing_key = f"briefing_{w['lat']}_{w['lon']}_{w['local_time']}"
        briefing = st.session_state.get(briefing_key)

        if briefing is None:
            # Try Gemini; fall back to a plain-text summary
            google_key = st.session_state.get("_google_api_key_for_briefing")
            if google_key:
                try:
                    with st.spinner("Generating city briefing…"):
                        briefing = _gemini_briefing(w, google_key)
                        st.session_state[briefing_key] = briefing
                except Exception:
                    briefing = None

        if briefing is None:
            # Build a simple fallback briefing from raw data
            briefing = (
                f"{w['city']} — {w['local_time']}\n\n"
                f"Temperature: {_na(w['temp_c'])} °C (feels like {_na(w['feelslike_c'])} °C)\n"
                f"Condition: {w['condition']}\n"
                f"Wind: {_na(w['wind_kph'])} kph {w.get('wind_dir','')}, gusts {_na(w['gust_kph'])} kph\n"
                f"Humidity: {_na(w['humidity'])} %  |  Pressure: {_na(w['pressure_mb'])} mb\n"
                f"Precipitation: {_na(w['precip_mm'])} mm\n\n"
                f"12-Hour Storm Outlook:\n"
                f"  Thunder hours: {w['storm_thunder_hours']}\n"
                f"  Peak gust: {_na(w['storm_peak_gust_kph'])} kph\n"
                f"  Total precipitation: {_na(w['storm_precip_total_mm'])} mm\n"
                f"  Pressure fall: {_na(w['storm_pressure_fall_mb'])} mb\n"
                f"  First wet hour: {fw_disp}\n"
            )
            st.session_state[briefing_key] = briefing

        st.markdown(briefing)

        try:
            pdf_bytes = _make_briefing_pdf(w, briefing)
            safe_city = "".join(c for c in w["city"].split(",")[0] if c.isalnum() or c == " ").strip().replace(" ", "_")
            st.download_button(
                "⬇ Download PDF",
                data=pdf_bytes,
                file_name=f"weather_briefing_{safe_city}.pdf",
                mime="application/pdf",
                key=f"briefing-pdf-{briefing_key}",
            )
        except ValueError as err:
            st.caption(f"PDF not available: {err}")
