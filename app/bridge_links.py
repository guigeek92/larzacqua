import os
import base64
from textwrap import dedent

import streamlit as st


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGO_PATH = os.path.join(PROJECT_ROOT, "assets", "larzacqua_logo.svg")


HERO_STYLE = """
<style>
.enr-nav {
    position: relative;
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.94) 100%);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 18px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
}
.enr-nav-header {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    min-height: 64px;
}
.enr-nav-logo {
    width: 4.9rem;
    height: auto;
    flex: 0 0 auto;
}
.enr-nav-copy {
    flex: 1 1 auto;
    min-width: 0;
}
.enr-nav-title {
    color: #F8FAFC;
    font-size: 1rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}
.enr-nav-subtitle {
    color: #CBD5E1;
    line-height: 1.45;
    font-size: 1rem;
}
.enr-nav-links {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    margin-top: 0.85rem;
}
.enr-nav-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 9rem;
    padding: 0.48rem 0.95rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    background: rgba(15, 23, 42, 0.72);
    color: #E2E8F0 !important;
    font-size: 0.95rem;
    font-weight: 700;
    text-decoration: none !important;
    transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease, border-color 120ms ease;
}
.enr-nav-link:hover {
    transform: translateY(-1px);
    border-color: rgba(255, 255, 255, 0.28);
}
.enr-nav-link.active {
    background: linear-gradient(135deg, #1d68ff 0%, #33c0ff 100%);
    border-color: rgba(109, 188, 255, 0.85);
    color: #FFFFFF !important;
    box-shadow: 0 12px 24px rgba(29, 104, 255, 0.25);
}
.enr-nav-link.inactive {
    background: rgba(15, 23, 42, 0.84);
}
.enr-nav-text, .hydro-bridge-text {
    color: #CBD5E1;
    line-height: 1.45;
    font-size: 0.92rem;
}
</style>
"""


def get_dashboard_mode_from_query():
    try:
        mode = st.query_params.get("mode")
        if isinstance(mode, list):
            mode = mode[0] if mode else None
        if mode in {"hydro", "pv"}:
            return mode
    except Exception:
        pass

    try:
        query_params = st.experimental_get_query_params()
        mode = query_params.get("mode", [None])[0]
        if mode in {"hydro", "pv"}:
            return mode
    except Exception:
        pass

    return None


def render_bridge_banner(active_label, other_label, active_mode):
    st.markdown(HERO_STYLE, unsafe_allow_html=True)
    target_mode = "pv" if active_mode == "hydro" else "hydro"
    logo_data_uri = ""
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as logo_file:
            logo_data_uri = "data:image/svg+xml;base64," + base64.b64encode(logo_file.read()).decode("ascii")

    st.markdown(
        dedent(
            f"""
            <div class="enr-nav">
                <div class="enr-nav-header">
                    {f'<img class="enr-nav-logo" src="{logo_data_uri}" alt="Larzacqua" />' if logo_data_uri else ''}
                    <div class="enr-nav-copy">
                        <div class="enr-nav-title">Plateforme de solution ENR</div>
                        <div class="enr-nav-subtitle">
                            Une navigation commune pour comparer les solutions hydroélectriques et photovoltaïques.
                        </div>
                    </div>
                </div>
                <div class="enr-nav-links">
                    <a class="enr-nav-link {'active' if active_mode == 'hydro' else 'inactive'}" href="?mode=hydro">Hydro</a>
                    <a class="enr-nav-link {'active' if active_mode == 'pv' else 'inactive'}" href="?mode=pv">PV</a>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    st.session_state["dashboard_mode"] = active_mode


def render_dashboard_switcher(active_mode):
    return None
