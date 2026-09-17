"""
Pakistan Environmental Conditions App (Streamlit)
--------------------------------------------------
Shows NEQS (National Environmental Quality Standards) limits, WHO benchmarks,
and verified 2024-2025 monitoring data for air quality and industrial effluent
in Pakistan.

Data integrity rule followed throughout: every value shown is either
(a) a verified figure from an official regulator, academic study, or credible
international aggregator, tagged with its source, or (b) explicitly logged as
a data gap. No values are estimated, interpolated, or guessed.

Run locally / in Colab with: streamlit run app.py
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Pakistan Environmental Conditions", layout="centered")

# ---------------------------------------------------------------------------
# 1. VERIFIED REFERENCE STANDARDS
# ---------------------------------------------------------------------------

# NEQS - Ambient Air (Pak-EPA notification, values in ug/m3 unless noted)
NEQS_AIR = {
    "PM2.5":   {"annual": 15,  "24h": 35,   "unit": "ug/m3"},
    "PM10":    {"annual": 120, "24h": 150,  "unit": "ug/m3"},
    "SO2":     {"annual": 80,  "24h": 120,  "unit": "ug/m3"},
    "NOx (as NO2)": {"annual": 40, "24h": 80, "unit": "ug/m3"},
    "O3":      {"annual": None, "1h": 130,  "unit": "ug/m3"},
    "Lead":    {"annual": 1,   "24h": 1.5,  "unit": "ug/m3"},
    "CO":      {"annual": None, "8h": 5,    "unit": "mg/m3"},
}

# WHO 2021 Global Air Quality Guidelines (ug/m3 unless noted)
WHO_AIR = {
    "PM2.5":   {"annual": 5,  "24h": 15},
    "PM10":    {"annual": 15, "24h": 45},
    "SO2":     {"annual": None, "24h": 40},
    "NOx (as NO2)": {"annual": 10, "24h": 25},
    "O3":      {"annual": None, "peak_season": 60},
    "Lead":    {"annual": None, "24h": None},   # WHO has no formal AQG value for lead
    "CO":      {"annual": None, "24h": 4, "unit": "mg/m3"},
}

# NEQS - Municipal & Liquid Industrial Effluents, discharge into inland waters (mg/L)
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

# ---------------------------------------------------------------------------
# 2. VERIFIED HISTORICAL READINGS (2024-2025 window only, per project scope)
# ---------------------------------------------------------------------------

# Annual PM2.5 averages (ug/m3). Value of None = verified gap, not an estimate.
AIR_READINGS = {
    "Lahore":    {"2024": 99.5, "2025": None},
    "Karachi":   {"2024": 47.1, "2025": None},
    "Islamabad": {"2024": 52.4, "2025": None},
}

AIR_READING_SOURCES = {
    "Lahore":    "WWF-Pakistan / EP&CCD Punjab compilation (2024 report)",
    "Karachi":   "IQAir World Air Quality Report",
    "Islamabad": "IQAir World Air Quality Report",
}

PAKISTAN_NATIONAL_PM25 = {
    "2024": None,   # not confirmed at national-average level in sources checked
    "2025": 67.3,   # IQAir World Air Quality Report - ranked world's most polluted country
}

# ---------------------------------------------------------------------------
# 3. DATA GAP LOG - explicit, not hidden
# ---------------------------------------------------------------------------

GAP_LOG = [
    {"Parameter": "PM2.5", "Location": "Lahore", "Period": "2025",
     "Reason": "No verified annual average found; only episodic smog-day AQI spikes (e.g. Oct 2025) located"},
    {"Parameter": "PM2.5", "Location": "Karachi", "Period": "2025",
     "Reason": "City-level 2025 annual average not found in accessible IQAir report tables"},
    {"Parameter": "PM2.5", "Location": "Islamabad", "Period": "2025",
     "Reason": "City-level 2025 annual average not found in accessible IQAir report tables"},
    {"Parameter": "Industrial effluent (BOD/COD/etc.)", "Location": "National", "Period": "2024-2025",
     "Reason": "No published quantitative NEQS-compliance results found. Confirmed instead: Punjab EPA "
               "deployed wastewater monitoring squads (May 2025) and a dedicated effluent-monitoring unit; "
               "Sindh EPA confirmed ongoing oversight (Dec 2025 assembly record). No results dataset published yet."},
    {"Parameter": "Drinking water quality", "Location": "Karachi, Lahore", "Period": "2024-2025",
     "Reason": "PCRWR published a full assessment for Islamabad only (Jun/Oct 2024) in the sources checked; "
               "no equivalent city-specific report found for Karachi or Lahore"},
]

# ---------------------------------------------------------------------------
# 4. HELPER FUNCTIONS
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


@st.cache_data
def gap_log_table():
    return pd.DataFrame(GAP_LOG)


def compare_air(parameter, city, year):
    neqs = NEQS_AIR.get(parameter, {})
    who = WHO_AIR.get(parameter, {})
    reading = AIR_READINGS.get(city, {}).get(year)
    source = AIR_READING_SOURCES.get(city, "-")

    neqs_annual = neqs.get("annual")
    who_annual = who.get("annual")

    if reading is None:
        return {
            "status": "gap",
            "value_str": "Not available",
            "message": "No verified reading for this city/year. See the Data gaps tab.",
        }

    result = {"status": "ok", "value_str": f"{reading} ug/m3", "source": source}

    if neqs_annual:
        ratio_neqs = reading / neqs_annual
        result["neqs_status"] = "Exceeds NEQS" if ratio_neqs > 1 else "Within NEQS"
        result["vs_neqs"] = f"{ratio_neqs:.1f}x NEQS limit ({neqs_annual} ug/m3)"
    else:
        result["neqs_status"] = "-"
        result["vs_neqs"] = "No annual NEQS value for this parameter"

    if who_annual:
        ratio_who = reading / who_annual
        result["vs_who"] = f"{ratio_who:.1f}x WHO guideline ({who_annual} ug/m3)"
    else:
        result["vs_who"] = "No annual WHO guideline for this parameter"

    return result


# ---------------------------------------------------------------------------
# 5. STREAMLIT APP
# ---------------------------------------------------------------------------

st.title("Pakistan Environmental Conditions")
st.caption(
    "NEQS vs WHO comparison and verified 2024-2025 monitoring data. "
    "Every figure is source-tagged; missing data is logged as a gap, never estimated."
)

tab_air, tab_effluent, tab_gaps, tab_about = st.tabs(
    ["Air quality", "Industrial effluent", "Data gaps", "About"]
)

with tab_air:
    col1, col2, col3 = st.columns(3)
    with col1:
        city = st.selectbox("City", list(AIR_READINGS.keys()))
    with col2:
        parameter = st.selectbox("Parameter", list(NEQS_AIR.keys()))
    with col3:
        year = st.selectbox("Year", ["2024", "2025"])

    result = compare_air(parameter, city, year)

    if result["status"] == "gap":
        st.warning(f"**{city}, {year}, {parameter}** — {result['message']}")
    else:
        status_color = "🔴" if result["neqs_status"] == "Exceeds NEQS" else "🟢"
        st.metric(label=f"{city} — {parameter} ({year})", value=result["value_str"])
        st.write(f"{status_color} **{result['neqs_status']}** — {result['vs_neqs']}")
        st.write(f"vs WHO: {result['vs_who']}")
        st.caption(f"Source: {result['source']}")

    st.divider()
    st.subheader("NEQS vs WHO — ambient air standards (full reference)")
    st.dataframe(neqs_air_table(), use_container_width=True, hide_index=True)

with tab_effluent:
    st.subheader("NEQS — liquid industrial effluent limits")
    st.caption("Discharge into inland waters, mg/L unless noted.")
    st.info(
        "No verified quantitative monitoring results (actual measured BOD/COD/etc.) were found "
        "for 2024-2025 — see the Data gaps tab. Standards below are shown for reference only."
    )
    st.dataframe(neqs_effluent_table(), use_container_width=True, hide_index=True)

with tab_gaps:
    st.subheader("What is NOT verified")
    st.caption("Recorded explicitly instead of filled in with estimates, per project data-integrity rule.")
    st.dataframe(gap_log_table(), use_container_width=True, hide_index=True)

with tab_about:
    st.markdown(
        """
**Sources used:**
- Pak-EPA / Punjab EPD — NEQS Ambient Air and Liquid Effluent standards
- WHO Global Air Quality Guidelines (2021)
- WWF-Pakistan / EP&CCD Punjab — Lahore air quality compilation (2024)
- IQAir World Air Quality Report — Karachi, Islamabad, national PM2.5
- Punjab EPA / Sindh EPA — effluent monitoring regulatory actions (2025)

This build covers the last 2 years (2024-2025) only, per current project scope.
        """
    )
