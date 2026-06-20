import os
import base64
from textwrap import dedent

import streamlit as st


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGO_PATH = os.path.join(PROJECT_ROOT, "data", "logo.png")


HERO_STYLE = """
<style>
:root {
    --larzacqua-blue: #2e75cf;
    --larzacqua-blue-dark: #2458b8;
    --larzacqua-cyan: #34b6d0;
    --larzacqua-green: #59d0a6;
}
.enr-nav {
    position: relative;
    background: linear-gradient(135deg, rgba(10, 20, 36, 0.97) 0%, rgba(22, 36, 60, 0.95) 100%);
    border: 1px solid rgba(52, 182, 208, 0.18);
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
    color: #d5e8f2;
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
    border: 1px solid rgba(52, 182, 208, 0.22);
    background: rgba(15, 27, 48, 0.78);
    color: #E2E8F0 !important;
    font-size: 0.95rem;
    font-weight: 700;
    text-decoration: none !important;
    transition: transform 120ms ease, box-shadow 120ms ease, background 120ms ease, border-color 120ms ease;
}
.enr-nav-link:hover {
    transform: translateY(-1px);
    border-color: rgba(89, 208, 166, 0.45);
}
.enr-nav-link.active {
    background: linear-gradient(135deg, var(--larzacqua-blue) 0%, var(--larzacqua-cyan) 55%, var(--larzacqua-green) 100%);
    border-color: rgba(89, 208, 166, 0.85);
    color: #FFFFFF !important;
    box-shadow: 0 12px 24px rgba(46, 117, 207, 0.25);
}
.enr-nav-link.inactive {
    background: rgba(15, 27, 48, 0.84);
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
    logo_data_uri = ""
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as logo_file:
            logo_ext = os.path.splitext(LOGO_PATH)[1].lower()
            mime_type = "image/png" if logo_ext == ".png" else "image/jpeg" if logo_ext in {".jpg", ".jpeg"} else "image/svg+xml"
            logo_data_uri = f"data:{mime_type};base64," + base64.b64encode(logo_file.read()).decode("ascii")

    st.markdown(
        dedent(
            f"""
            <div class="enr-nav">
                <div class="enr-nav-header">
                    {f'<img class="enr-nav-logo" src="{logo_data_uri}" alt="Larzacqua" />' if logo_data_uri else ''}
                    <div class="enr-nav-copy">
                        <div class="enr-nav-title">Plateforme Larzacqua</div>
                        <div class="enr-nav-subtitle">
                            Estimation du potentiel hydroélectrique et photovoltaïque du réseau d'eau pour le Lodévois et Larzac.
                        </div>
                    </div>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    
    # Navigation buttons using st.query_params (no page reload)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Hydro", key="nav_hydro", use_container_width=True, type="primary" if active_mode == "hydro" else "secondary"):
            st.query_params.mode = "hydro"
            st.rerun()
    with col2:
        if st.button("PV", key="nav_pv", use_container_width=True, type="primary" if active_mode == "pv" else "secondary"):
            st.query_params.mode = "pv"
            st.rerun()


def render_dashboard_switcher(active_mode):
    return None
