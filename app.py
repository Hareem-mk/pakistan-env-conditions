"""
Pakistan Environmental Conditions App (Streamlit) - v2
---------------------------------------------------------
Air quality: LIVE data from the OpenAQ v3 API (real reference/research-grade
             sensors; Pakistan has ~180 reporting PM2.5 stations).
Effluent:    read from data/processed/effluent_readings.json, which is filled
             in manually after verifying periodic PDF reports dropped into
             data/ingest/ (no API exists for this data - see project notes).
Standards:   NEQS and WHO limits stay hardcoded - they are fixed regulatory
             reference values, not something that needs live fetching.

Data integrity rule followed throughout: every value shown is either
(a) a live reading from a named source/station, or (b) explicitly logged as
a data gap. Nothing is estimated, interpolated, or guessed.

Setup required before running:
  1. Create .streamlit/secrets.toml in this folder with:
         OPENAQ_API_KEY = "your-key-here"
  2. On Streamlit Community Cloud: add the same key under
     App settings -> Secrets (same TOML format).
  3. Never commit secrets.toml to GitHub - add it to .gitignore.

Run locally with: streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Pakistan Environmental Conditions", layout="centered")

OPENAQ_BASE = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2

# ---------------------------------------------------------------------------
# 1. VERIFIED REFERENCE STANDARDS (static - fixed regulatory values)
# ---------------------------------------------------------------------------

NEQS_AIR = {
    "PM2.5":   {"annual": 15,  "24h": 35,   "unit": "ug/m3"},
    "PM10":    {"annual": 120, "24h": 150,  "unit": "ug/m3"},
    "SO2":     {"annual": 80,  "24h": 120,  "unit": "ug/m3"},
    "NOx (as NO2)": {"annual": 40, "24h": 80, "unit": "ug/m3"},
    "O3":      {"annual": None, "1h": 130,  "unit": "ug/m3"},
    "Lead":    {"annual": 1,   "24h": 1.5,  "unit": "ug/m3"},
    "CO":      {"annual": None, "8h": 5,    "unit": "mg/m3"},
}

WHO_AIR = {
    "PM2.5":   {"annual": 5,  "24h": 15},
    "PM10":    {"annual": 15, "24h": 45},
    "SO2":     {"annual": None, "24h": 40},
    "NOx (as NO2)": {"annual": 10, "24h": 25},
    "O3":      {"annual": None, "peak_season": 60},
    "Lead":    {"annual": None, "24h": None},
    "CO":      {"annual": None, "24h": 4, "unit": "mg/m3"},
}

NEQS_EFFLUENT = {
    "BOD5": 80,
    "COD": 150,
    "TSS": 200,
    "TDS": 3500,
    "Oil & Grease": 10,
    "Ammonia": 40,
    "Chromium (total)": 1.0,
    "Lead": 0.5,
    "Cadmium": 0.1,
    "Mercury": 0.01,
    "Cyanide": 1.0,
    "Total toxic metals": 2.0,
}

# City coordinates (fixed geography, not a "current state" fact)
CITY_COORDS = {
    "Lahore":    (31.5204, 74.3587),
    "Karachi":   (24.8607, 67.0011),
    "Islamabad": (33.6844, 73.0479),
}

# Manually-confirmed 2024 baseline, kept as a fallback ONLY if the live API
# returns nothing for a city - always labelled as such, never blended in
# silently with a live reading.
VERIFIED_2024_FALLBACK = {
    "Lahore":    {"value": 99.5, "source": "WWF-Pakistan / EP&CCD Punjab compilation (2024 report)"},
    "Karachi":   {"value": 47.1, "source": "IQAir World Air Quality Report (2024)"},
    "Islamabad": {"value": 52.4, "source": "IQAir World Air Quality Report (2024)"},
}

DATA_DIR = Path(__file__).parent / "data"
EFFLUENT_FILE = DATA_DIR / "processed" / "effluent_readings.json"

# ---------------------------------------------------------------------------
# 2. LIVE AIR QUALITY - OpenAQ v3 API
# ---------------------------------------------------------------------------

def get_api_key():
    return st.secrets.get("OPENAQ_API_KEY", None)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_live_pm25(city: str):
    """
    Returns dict with value, station name, datetime, and source - or a dict
    with status='gap' if no live reading could be found. Never fabricates a
    number.
    """
    api_key = get_api_key()
    if not api_key:
        return {"status": "error", "message": "No OpenAQ API key configured in secrets."}

    lat, lon = CITY_COORDS[city]
    headers = {"X-API-Key": api_key}

    try:
        loc_resp = requests.get(
            f"{OPENAQ_BASE}/locations",
            params={
                "coordinates": f"{lat},{lon}",
                "radius": 25000,
                "parameters_id": PM25_PARAMETER_ID,
                "limit": 5,
            },
            headers=headers,
            timeout=10,
        )
        loc_resp.raise_for_status()
        locations = loc_resp.json().get("results", [])
    except requests.RequestException as e:
        return {"status": "error", "message": f"OpenAQ locations request failed: {e}"}

    if not locations:
        return {"status": "gap", "message": "No OpenAQ PM2.5 station found within 25km of city center."}

    location_id = locations[0]["id"]
    location_name = locations[0].get("name", "Unknown station")

    try:
        latest_resp = requests.get(
            f"{OPENAQ_BASE}/locations/{location_id}/latest",
            headers=headers,
            timeout=10,
        )
        latest_resp.raise_for_status()
        readings = latest_resp.json().get("results", [])
    except requests.RequestException as e:
        return {"status": "error", "message": f"OpenAQ latest-reading request failed: {e}"}

    if not readings:
        return {"status": "gap", "message": f"Station '{location_name}' found but has no recent readings."}

    reading = readings[0]
    return {
        "status": "ok",
        "value": reading["value"],
        "datetime": reading.get("datetime", {}).get("local", "unknown time"),
        "station": location_name,
        "source": f"OpenAQ live station: {location_name}",
    }


# ---------------------------------------------------------------------------
# 3. EFFLUENT DATA - read from manually-verified processed file
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def load_effluent_readings():
    if not EFFLUENT_FILE.exists():
        return []
    try:
        with open(EFFLUENT_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# 4. REFERENCE TABLES
# ---------------------------------------------------------------------------

@st.cache_data
def neqs_air_table():
    rows = []
    for param, vals in NEQS_AIR.items():
        who_vals = WHO_AIR.get(param, {})
        rows.append({
            "Parameter": param,
            "NEQS annual": vals.get("annual") or "-",
            "NEQS 24h": vals.get("24h") or "-",
            "WHO annual": who_vals.get("annual") or "-",
            "WHO 24h": who_vals.get("24h") or "-",
            "Unit": vals.get("unit", "ug/m3"),
        })
    return pd.DataFrame(rows)


@st.cache_data
def neqs_effluent_table():
    rows = [{"Parameter": k, "NEQS limit (mg/L)": v} for k, v in NEQS_EFFLUENT.items()]
    return pd.DataFrame(rows)


def gap_log_table(effluent_readings):
    gaps = [
        {"Parameter": "PM2.5", "Location": "any city", "Period": "live",
         "Reason": "Shown only when the OpenAQ API returns no station/reading within 25km - see Air quality tab warnings."},
        {"Parameter": "PM10, SO2, NOx, O3, CO", "Location": "all", "Period": "live",
         "Reason": "Confirmed near-zero OpenAQ sensor coverage in Pakistan for these parameters at time of setup; PM2.5 is the only pollutant with reliable live coverage."},
    ]
    if not effluent_readings:
        gaps.append({
            "Parameter": "Industrial effluent (BOD/COD/etc.)", "Location": "National", "Period": "2024-2025",
            "Reason": "No processed readings yet. No live API exists for this data - Punjab EPA/Sindh EPA/PCRWR "
                      "publish periodic PDF reports only. Drop a verified report into data/ingest/ and transcribe "
                      "confirmed values into data/processed/effluent_readings.json.",
        })
    return pd.DataFrame(gaps)


# ---------------------------------------------------------------------------
# 5. STREAMLIT APP
# ---------------------------------------------------------------------------

st.title("Pakistan Environmental Conditions")
st.caption(
    "Live air quality (OpenAQ) compared against NEQS and WHO. "
    "Effluent data is manually verified from official reports. Gaps are logged, never estimated."
)

if not get_api_key():
    st.error(
        "No OpenAQ API key found. Add one to `.streamlit/secrets.toml` as "
        "`OPENAQ_API_KEY = \"your-key\"` (locally) or under App settings > Secrets (on Streamlit Cloud)."
    )

tab_air, tab_effluent, tab_gaps, tab_about = st.tabs(
    ["Air quality (live)", "Industrial effluent", "Data gaps", "About"]
)

with tab_air:
    city = st.selectbox("City", list(CITY_COORDS.keys()))

    if get_api_key():
        with st.spinner(f"Fetching live PM2.5 for {city} from OpenAQ..."):
            result = fetch_live_pm25(city)

        neqs_annual = NEQS_AIR["PM2.5"]["annual"]
        who_annual = WHO_AIR["PM2.5"]["annual"]

        if result["status"] == "ok":
            value = result["value"]
            ratio_neqs = value / neqs_annual
            ratio_who = value / who_annual
            status = "Exceeds NEQS" if ratio_neqs > 1 else "Within NEQS"
            status_icon = "\U0001F534" if ratio_neqs > 1 else "\U0001F7E2"

            st.metric(label=f"{city} — PM2.5 (live)", value=f"{value:.1f} ug/m3")
            st.write(f"{status_icon} **{status}** — {ratio_neqs:.1f}x NEQS annual limit ({neqs_annual} ug/m3)")
            st.write(f"vs WHO: {ratio_who:.1f}x guideline ({who_annual} ug/m3)")
            st.caption(f"Source: {result['source']} | Reading time: {result['datetime']}")

        elif result["status"] == "gap":
            st.warning(f"No live reading available for {city}: {result['message']}")
            fallback = VERIFIED_2024_FALLBACK.get(city)
            if fallback:
                st.info(
                    f"Last verified figure on record: {fallback['value']} ug/m3 "
                    f"(annual average, {fallback['source']}) — shown for context only, not live."
                )
        else:
            st.error(result["message"])

    st.divider()
    st.subheader("NEQS vs WHO — ambient air standards (full reference)")
    st.dataframe(neqs_air_table(), use_container_width=True, hide_index=True)

with tab_effluent:
    st.subheader("NEQS — liquid industrial effluent limits")
    st.caption("Discharge into inland waters, mg/L unless noted.")

    effluent_readings = load_effluent_readings()
    if effluent_readings:
        st.markdown("### Verified monitoring readings on file")
        st.dataframe(pd.DataFrame(effluent_readings), use_container_width=True, hide_index=True)
    else:
        st.info(
            "No verified quantitative effluent readings on file yet. Standards below are shown for "
            "reference. See the Data gaps tab and the About tab for how readings get added."
        )

    st.divider()
    st.dataframe(neqs_effluent_table(), use_container_width=True, hide_index=True)

with tab_gaps:
    st.subheader("What is NOT verified / live")
    st.caption("Recorded explicitly instead of filled in with estimates, per project data-integrity rule.")
    st.dataframe(gap_log_table(load_effluent_readings()), use_container_width=True, hide_index=True)

with tab_about:
    st.markdown(
        """
**Air quality — live**
Sourced on every page load from the [OpenAQ v3 API](https://openaq.org), which aggregates
government reference monitors and research-grade sensors. Pakistan has meaningful PM2.5
coverage; other pollutants (PM10, SO2, NOx, O3, CO) currently have little to no reliable
sensor coverage in-country, so only PM2.5 is shown live.

**Industrial effluent — manually verified**
No live API exists for this data. Workflow:
1. Download a new official report (Punjab EPA / Sindh EPA / PCRWR) into `data/ingest/`.
2. Verify the actual numbers by hand (these PDFs are often scanned tables, not clean text).
3. Add confirmed readings to `data/processed/effluent_readings.json`.
4. The app reads only from that processed file - never guesses at the raw PDF.

**Standards — static by design**
NEQS and WHO limits are fixed regulatory reference values and are hardcoded rather than
fetched, since there is no benefit to querying them live.
        """
    )
