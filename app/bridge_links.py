from textwrap import dedent

import streamlit as st


HERO_STYLE = """
<style>
.pv-bridge, .hydro-bridge {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.94) 100%);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 18px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
}
.pv-bridge-title, .hydro-bridge-title {
    color: #F8FAFC;
    font-size: 0.92rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
}
.pv-bridge-text, .hydro-bridge-text {
    color: #CBD5E1;
    line-height: 1.45;
    font-size: 0.92rem;
}
.pv-bridge-actions, .hydro-bridge-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.7rem;
}
.pv-bridge-pill, .hydro-bridge-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.42rem 0.8rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: rgba(15, 23, 42, 0.84);
    color: #E2E8F0;
    font-size: 0.82rem;
    font-weight: 600;
    text-decoration: none;
}
.pv-bridge-pill:hover, .hydro-bridge-pill:hover {
    border-color: rgba(245, 158, 11, 0.45);
    color: #FFFFFF;
}
</style>
"""


def render_bridge_banner(active_label, other_label, active_mode):
    st.markdown(HERO_STYLE, unsafe_allow_html=True)
    current_badge = f"<span class='pv-bridge-pill'>{active_label}</span>"
    target_mode = "pv" if active_mode == "hydro" else "hydro"

    def switch_mode():
        st.session_state["dashboard_mode"] = target_mode

    other_badge = None
    st.markdown(
        dedent(
            f"""
            <div class="pv-bridge">
                <div class="pv-bridge-title">Pont inter-interfaces</div>
                <div class="pv-bridge-text">
                    Les deux tableaux de bord partagent le même langage visuel et peuvent être consultés côte à côte.
                    Utilise le bouton ci-dessous pour passer de l’un à l’autre sans quitter la session.
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='pv-bridge-actions'>{current_badge}</div>", unsafe_allow_html=True)
    st.button(
        f"Ouvrir {other_label}",
        key=f"bridge_switch_{target_mode}",
        on_click=switch_mode,
        use_container_width=False,
    )


def render_dashboard_switcher(active_mode):
    target_mode = "pv" if active_mode == "hydro" else "hydro"
    target_label = "interface PV" if active_mode == "hydro" else "interface hydro"
    button_key = f"switch_to_{target_mode}"

    def switch_mode():
        st.session_state["dashboard_mode"] = target_mode

    st.button(
        f"Ouvrir {target_label}",
        key=button_key,
        on_click=switch_mode,
        use_container_width=True,
    )
