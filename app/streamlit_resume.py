import os
import re
import sys
import inspect
import numpy as np
import urllib.parse
from datetime import datetime

# Ajout dynamique du chemin racine du projet pour les imports
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

try:
    import openai
except ImportError:
    openai = None

try:
    from bridge_links import render_bridge_banner, render_dashboard_switcher
except Exception:
    def render_bridge_banner(*args, **kwargs):
        return None

    def render_dashboard_switcher(*args, **kwargs):
        return None

from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power
import modules.turbine_selector as turbine_selector

load_turbine_db = turbine_selector.load_turbine_db
select_turbine = turbine_selector.select_turbine

if hasattr(turbine_selector, "rank_compatible_turbines"):
    rank_compatible_turbines = turbine_selector.rank_compatible_turbines
else:
    def rank_compatible_turbines(site_row, turbine_db, max_results=2, second_score_ratio=1.1):
        pressure = pd.to_numeric(site_row.get("delta_p"), errors="coerce")
        flow = pd.to_numeric(site_row.get("estimated_flow_obs"), errors="coerce")

        if pd.isna(pressure) or pd.isna(flow) or pressure <= 0 or flow <= 0:
            return turbine_db.iloc[0:0].copy()

        working_db = turbine_db.copy()
        for column in ["debit_min_m3h", "debit_max_m3h", "pression_min_bar", "pression_max_bar", "puissance_min_kw", "puissance_max_kw", "diametre_mm", "rendement_typique"]:
            if column in working_db.columns:
                working_db[column] = pd.to_numeric(working_db[column], errors="coerce")

        if any(column not in working_db.columns for column in ["debit_min_m3h", "debit_max_m3h", "pression_min_bar", "pression_max_bar", "puissance_min_kw", "puissance_max_kw"]):
            return working_db.iloc[0:0].copy()

        compatible = working_db[
            (working_db["debit_min_m3h"].notna())
            & (working_db["debit_max_m3h"].notna())
            & (working_db["pression_min_bar"].notna())
            & (working_db["pression_max_bar"].notna())
            & (working_db["puissance_min_kw"].notna())
            & (working_db["puissance_max_kw"].notna())
            & (working_db["debit_min_m3h"] <= flow)
            & (working_db["debit_max_m3h"] >= flow)
            & (working_db["pression_min_bar"] <= pressure)
            & (working_db["pression_max_bar"] >= pressure)
        ].copy()

        site_power_kw = turbine_selector.compute_pe(pressure, flow, eta=0.75)
        if pd.isna(site_power_kw) or site_power_kw <= 0:
            return compatible.iloc[0:0].copy()

        compatible = compatible[
            (compatible["puissance_min_kw"] <= site_power_kw)
            & (compatible["puissance_max_kw"] >= site_power_kw)
        ].copy()

        if compatible.empty:
            return compatible

        compatible["_power_gap"] = (
            (compatible["puissance_min_kw"] - site_power_kw).abs()
            + (compatible["puissance_max_kw"] - site_power_kw).abs()
        )
        compatible = compatible.sort_values(
            by=["_power_gap", "rendement_typique"],
            ascending=[True, False],
            na_position="last",
        ).reset_index(drop=True)
        ranked = compatible.head(max(int(max_results), 1)).drop(columns=["_power_gap"], errors="ignore")

        if len(ranked) > 1:
            first_score = ranked.iloc[0].get("_power_gap", 0)
            second_score = ranked.iloc[1].get("_power_gap", 0)
            if pd.notna(first_score) and pd.notna(second_score) and second_score > first_score * float(second_score_ratio):
                ranked = ranked.head(1).reset_index(drop=True)

        return ranked
try:
    import modules.pdf_report as pdf_report
except ImportError:
    pdf_report = None

if pdf_report is not None:
    try:
        # optional: WeasyPrint renderer may not be installed on all environments
        generate_site_pdf_weasy = pdf_report.generate_site_pdf_weasy
        weasy_available = True
    except Exception:
        generate_site_pdf_weasy = None
        weasy_available = False
else:
    generate_site_pdf_weasy = None
    weasy_available = False
try:
    from app.acteurs import render_acteurs_dashboard
except Exception:
    def render_acteurs_dashboard():
        st.info("Le module Acteurs n'est pas disponible dans cette version du projet.")


def call_generate_site_pdf(**kwargs):
    if pdf_report is None:
        raise RuntimeError("Le module PDF n'est pas disponible dans cet environnement.")
    signature = inspect.signature(pdf_report.generate_site_pdf)
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in signature.parameters}
    return pdf_report.generate_site_pdf(**filtered_kwargs)


generate_site_simulation_report = getattr(pdf_report, "generate_site_simulation_report", None) if pdf_report is not None else None


load_dotenv()


def get_groq_api_key():
    """Return the Groq API key from Streamlit secrets or environment variables."""
    try:
        if "GROQ_API_KEY" in st.secrets:
            secret_value = st.secrets["GROQ_API_KEY"]
            if secret_value:
                return str(secret_value).strip()
    except Exception:
        pass

    env_value = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if env_value:
        return env_value.strip()

    return None


def ensure_openai_available():
    if openai is None:
        raise RuntimeError(
            "Le package 'openai' n'est pas installé dans cet environnement. "
            "Installez les dépendances du projet avant d'utiliser le chatbot."
        )


@st.cache_data(show_spinner=False)
def load_pressure_reducers(csv_path):
    df = pd.read_csv(csv_path)
    df_valid = df.dropna(subset=["latitude", "longitude", "NOM"]).copy()
    from pyproj import Transformer
    transformer = Transformer.from_crs("epsg:3943", "epsg:4326", always_xy=True)
    converted = df_valid.apply(
        lambda row: transformer.transform(row['longitude'], row['latitude']),
        axis=1
    )
    df_valid['lat_wgs84'] = [lat for lon, lat in converted]
    df_valid['lon_wgs84'] = [lon for lon, lat in converted]
    df_valid = df_valid.reset_index(drop=True)
    df_valid['id'] = df_valid.index
    return df_valid


def build_popup_html(row):
    def safe_value(key, default="N/A"):
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return value

    name = safe_value("NOM")
    return f"<b>{name}</b>"


def color_for_type(value):
    if pd.isna(value):
        return "gray"
    value = str(value).strip().lower()
    if "fixe" in value:
        return "green"
    if "variable" in value:
        return "orange"
    if "regulateur" in value or "regulator" in value:
        return "blue"
    return "cadetblue"


def create_pressure_reducer_map(df, center=None, zoom_start=12, fit_bounds=True):
    if center is None:
        center = [43.73, 3.32]
    import folium
    from folium.plugins import MarkerCluster
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="CartoDB positron")
    cluster = MarkerCluster().add_to(m)
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['lat_wgs84'], row['lon_wgs84']],
            popup=build_popup_html(row),
            tooltip=str(row['NOM']),
            icon=folium.Icon(color=color_for_type(row.get("TYPE")), icon='tint', prefix='fa')
        ).add_to(cluster)
    if fit_bounds and not df.empty:
        bounds = df[['lat_wgs84', 'lon_wgs84']].to_numpy().tolist()
        m.fit_bounds(bounds)
    return m


def render_site_ai_generation(prompt, allow_call, cache_key, title="Synthese", max_tokens=600):
    st.subheader(title)
    with st.container():
        st.caption("Synthese automatique basee sur les parametres du site et les turbines compatibles.")
        result_key = f"{cache_key}_result"
        error_key = f"{cache_key}_error"
        regen_key = f"{cache_key}_regen"
        if allow_call:
            if st.button("Regenerer", key=regen_key):
                st.session_state.pop(result_key, None)
                st.session_state.pop(error_key, None)
        if allow_call and result_key not in st.session_state and error_key not in st.session_state:
            try:
                ensure_openai_available()
                groq_api_key = get_groq_api_key()
                if not groq_api_key:
                    raise RuntimeError(
                        "Missing GROQ_API_KEY. Add it in Streamlit Cloud secrets or in your local environment."
                    )
                client = openai.OpenAI(
                    api_key=groq_api_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                with st.spinner("Generation en cours..."):
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                st.session_state[result_key] = response.choices[0].message.content
            except Exception as e:
                st.session_state[error_key] = str(e)

        st.markdown("#### Resultat")
        if not allow_call:
            st.info("Synthese indisponible pour ce site (aucune turbine compatible).")
        elif error_key in st.session_state:
            st.error(f"Erreur lors de la generation : {st.session_state[error_key]}")
        elif result_key in st.session_state:
            st.success("Synthese terminee !")
            st.markdown(st.session_state[result_key])
        else:
            st.info("Synthese en attente.")

st.set_page_config(page_title="Estimation du potentiel : comparaison des filières | Hydro", layout="wide")
query_mode = None
try:
    query_mode = st.query_params.get("mode")
    if isinstance(query_mode, list):
        query_mode = query_mode[0] if query_mode else None
except Exception:
    query_mode = None
if query_mode not in {"hydro", "pv"}:
    try:
        query_mode = st.experimental_get_query_params().get("mode", [None])[0]
    except Exception:
        query_mode = None

if query_mode in {"hydro", "pv"}:
    st.session_state["dashboard_mode"] = query_mode
elif "dashboard_mode" not in st.session_state:
    st.session_state["dashboard_mode"] = "hydro"

st.session_state.setdefault("chatbot_open", False)
st.session_state.setdefault("chat_history", [])

if st.session_state.get("dashboard_mode") == "pv":
    from streamlit_pv import PVDashboard

    PVDashboard(set_page_config=False)
    st.stop()

render_bridge_banner(
    active_label="Interface hydro active",
    other_label="l’interface PV",
    active_mode="hydro",
)

chatbot_icon_svg = """
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>
  <rect x='4' y='6' width='16' height='12' rx='4' />
  <circle cx='9' cy='12' r='1' fill='white' stroke='none' />
  <circle cx='15' cy='12' r='1' fill='white' stroke='none' />
  <path d='M9 18v2M15 18v2' />
  <path d='M12 3v3' />
  <path d='M9 3h6' />
</svg>
"""
chatbot_icon_data_uri = "data:image/svg+xml;utf8," + urllib.parse.quote(chatbot_icon_svg)

style_block = """
    <style>
    div[data-testid="stContainer"] {
        background: linear-gradient(135deg, rgba(10, 20, 36, 0.96) 0%, rgba(17, 30, 50, 0.94) 60%);
        border: 1px solid rgba(52, 182, 208, 0.16);
        border-radius: 14px;
        padding: 0.75rem 1rem 0.95rem;
        margin-bottom: 0.6rem;
        box-shadow: 0 10px 26px rgba(0, 0, 0, 0.28);
    }
    div[data-testid="stContainer"] h3 {
        margin: 0;
        color: #e5eef9;
        font-weight: 800;
        font-size: 1.18rem;
        letter-spacing: 0.02em;
    }
    div[data-testid="stContainer"] p {
        margin: 0.25rem 0 0;
        color: #94a3b8;
        font-size: 0.9rem;
    }
    .analysis-section {
        background: linear-gradient(135deg, rgba(10, 20, 36, 0.96) 0%, rgba(17, 30, 50, 0.94) 60%);
        border: 1px solid rgba(46, 117, 207, 0.18);
        border-radius: 14px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.6rem;
        box-shadow: 0 10px 26px rgba(0, 0, 0, 0.28);
    }
    .analysis-section h3 {
        margin: 0;
        color: #e5eef9;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .analysis-section p {
        margin: 0.25rem 0 0;
        color: #94a3b8;
        font-size: 0.9rem;
    }
    .analysis-kpi {
        background: rgba(12, 24, 42, 0.94);
        border: 1px solid rgba(89, 208, 166, 0.18);
        border-radius: 12px;
        padding: 0.6rem 0.8rem;
        box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.05);
    }
    [data-testid="stButton"][data-widget-id="chatbot-bubble"] {
        position: fixed;
        left: 18px;
        top: 18px;
        z-index: 1000;
    }
    [data-testid="stButton"][data-widget-id="chatbot-bubble"] > button {
        width: 48px;
        height: 48px;
        padding: 0;
        border-radius: 999px;
        background-color: rgba(10, 20, 36, 0.96);
        background-image: url("__CHATBOT_ICON__");
        background-repeat: no-repeat;
        background-position: center;
        background-size: 24px 24px;
        color: transparent;
        font-size: 0;
        font-weight: 700;
        letter-spacing: 0;
        border: 1px solid rgba(52, 182, 208, 0.3);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0;
        box-shadow: 0 10px 24px rgba(46, 117, 207, 0.24);
        text-transform: none;
    }
    [data-testid="stButton"][data-widget-id="chatbot-bubble"] > button:hover {
        transform: translateY(-2px);
        border-color: rgba(89, 208, 166, 0.55);
        box-shadow: 0 12px 28px rgba(52, 182, 208, 0.22);
    }
    </style>
    """
style_block = style_block.replace("__CHATBOT_ICON__", chatbot_icon_data_uri)
st.markdown(style_block, unsafe_allow_html=True)

def render_section_card(title, subtitle=None):
    section = st.container(border=True)
    with section:
        st.markdown(f"<h3>{title}</h3>", unsafe_allow_html=True)
        if subtitle:
            st.markdown(f"<p>{subtitle}</p>", unsafe_allow_html=True)
    return section

def render_kpi_card():
    """Contexte pour afficher des métriques KPI dans une carte."""
    return st.container()

def render_chatbot_bubble():
    if "chatbot_open" not in st.session_state:
        st.session_state["chatbot_open"] = False
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    if st.button("Chatbot", key="chatbot-bubble", help="Ouvrir le chatbot"):
        st.session_state["chatbot_open"] = not st.session_state["chatbot_open"]
        st.rerun()

def render_analysis_global_summary(results_sorted, power_total_kw, annual_energy_kwh):
    """
    Affiche un résumé global consolidé de l'analyse: statistiques clés, classement, et recommandations.
    """
    section = render_section_card("📊 Résumé Global de l'Analyse")
    with section:
        # Onglets pour navigation
        summary_tab1, summary_tab2, summary_tab3 = st.tabs(["Vue d'ensemble", "Classement complet", "Recommandations"])
        
        with summary_tab1:
            st.markdown("### Statistiques globales")
            col1, col2, col3, col4 = st.columns(4, gap="medium")
            col1.metric("Nombre de sites", len(results_sorted))
            col2.metric("Puissance cumulée (kW)", f"{power_total_kw:.2f}")
            col3.metric("Énergie annuelle (kWh)", f"{annual_energy_kwh:,.0f}".replace(",", " "))
            col4.metric("Pression moyenne (bar)", f"{results_sorted['delta_p'].mean():.2f}" if 'delta_p' in results_sorted.columns else "N/D")
            
            st.markdown("---")
            st.markdown("### Distribution de la puissance par site")
            
            # Préparer les données pour le graphique
            power_by_site = results_sorted[['site_name', 'power_kW']].copy()
            power_by_site = power_by_site.sort_values('power_kW', ascending=True).tail(10)  # Top 10
            st.bar_chart(power_by_site.set_index('site_name')['power_kW'])
            
            st.markdown("---")
            st.markdown("### Synthèse des paramètres hydrauliques")
            hydro_stats = pd.DataFrame({
                "Paramètre": ["Pression (bar)", "Débit obs (m³/h)", "Débit calc (m³/h)"],
                "Minimum": [
                    f"{results_sorted['delta_p'].min():.2f}" if 'delta_p' in results_sorted.columns else "N/D",
                    f"{results_sorted['estimated_flow_obs'].min():.2f}" if 'estimated_flow_obs' in results_sorted.columns and results_sorted['estimated_flow_obs'].notna().any() else "N/D",
                    f"{results_sorted['estimated_flow_calc'].min():.2f}" if 'estimated_flow_calc' in results_sorted.columns and results_sorted['estimated_flow_calc'].notna().any() else "N/D",
                ],
                "Moyenne": [
                    f"{results_sorted['delta_p'].mean():.2f}" if 'delta_p' in results_sorted.columns else "N/D",
                    f"{results_sorted['estimated_flow_obs'].mean():.2f}" if 'estimated_flow_obs' in results_sorted.columns and results_sorted['estimated_flow_obs'].notna().any() else "N/D",
                    f"{results_sorted['estimated_flow_calc'].mean():.2f}" if 'estimated_flow_calc' in results_sorted.columns and results_sorted['estimated_flow_calc'].notna().any() else "N/D",
                ],
                "Maximum": [
                    f"{results_sorted['delta_p'].max():.2f}" if 'delta_p' in results_sorted.columns else "N/D",
                    f"{results_sorted['estimated_flow_obs'].max():.2f}" if 'estimated_flow_obs' in results_sorted.columns and results_sorted['estimated_flow_obs'].notna().any() else "N/D",
                    f"{results_sorted['estimated_flow_calc'].max():.2f}" if 'estimated_flow_calc' in results_sorted.columns and results_sorted['estimated_flow_calc'].notna().any() else "N/D",
                ]
            })
            st.table(hydro_stats)
        
        with summary_tab2:
            st.markdown("### Classement complet des sites")
            
            # Préparer le tableau de classement
            ranking = results_sorted[['site_name', 'power_kW', 'delta_p', 'estimated_flow_obs', 'estimated_flow_calc']].copy() if 'estimated_flow_obs' in results_sorted.columns else results_sorted[['site_name', 'power_kW', 'delta_p']].copy()
            ranking.insert(0, 'Rang', range(1, len(ranking) + 1))
            ranking['Puissance (kW)'] = ranking['power_kW'].round(2)
            ranking['Pression (bar)'] = ranking['delta_p'].round(2) if 'delta_p' in ranking.columns else "N/D"
            
            # Garder les bonnes colonnes
            display_cols = ['Rang', 'site_name', 'Puissance (kW)', 'Pression (bar)']
            if 'estimated_flow_obs' in ranking.columns:
                ranking['Débit obs (m³/h)'] = ranking['estimated_flow_obs'].round(2)
                display_cols.insert(4, 'Débit obs (m³/h)')
            if 'estimated_flow_calc' in ranking.columns:
                ranking['Débit calc (m³/h)'] = ranking['estimated_flow_calc'].round(2)
                display_cols.append('Débit calc (m³/h)')
            
            ranking_display = ranking[display_cols].rename(columns={'site_name': 'Site'})
            st.dataframe(ranking_display, use_container_width=True, hide_index=True)
            
            # Pourcentage d'énergie par site (top 5)
            st.markdown("---")
            st.markdown("### Contribution énergétique (top 5 sites)")
            top5 = results_sorted.head(5).copy()
            top5['contribution_%'] = (top5['power_kW'] / power_total_kw * 100).round(1)
            contrib_df = top5[['site_name', 'power_kW', 'contribution_%']].copy()
            contrib_df.columns = ['Site', 'Puissance (kW)', 'Contribution (%)']
            st.dataframe(contrib_df, use_container_width=True, hide_index=True)
        
        with summary_tab3:
            st.markdown("### Recommandations globales")
            
            # Recommandations basées sur les données
            recommendations = []
            
            # Top site
            if len(results_sorted) > 0:
                top_site = results_sorted.iloc[0]
                recommendations.append(f"🥇 **Site prioritaire** : {top_site['site_name']} avec {top_site['power_kW']:.2f} kW")
            
            # Potentiel global
            if power_total_kw > 0:
                if power_total_kw >= 50:
                    recommendations.append(f"⚡ **Potentiel global important** : {power_total_kw:.2f} kW cumulés, soit {annual_energy_kwh:,.0f} kWh/an")
                elif power_total_kw >= 10:
                    recommendations.append(f"⚡ **Potentiel modéré** : {power_total_kw:.2f} kW cumulés, soit {annual_energy_kwh:,.0f} kWh/an")
                else:
                    recommendations.append(f"⚠️ **Potentiel limité** : {power_total_kw:.2f} kW cumulés, soit {annual_energy_kwh:,.0f} kWh/an")
            
            # Concentration de puissance
            if len(results_sorted) > 0:
                top3_power = results_sorted.head(3)['power_kW'].sum()
                concentration = (top3_power / power_total_kw * 100) if power_total_kw > 0 else 0
                recommendations.append(f"📍 **Concentration de puissance** : Top 3 sites = {concentration:.1f}% de la puissance totale")
            
            # Pression moyenne
            if 'delta_p' in results_sorted.columns:
                avg_pressure = results_sorted['delta_p'].mean()
                if avg_pressure >= 3:
                    recommendations.append(f"💧 **Réseau haute pression** : ΔP moyen = {avg_pressure:.2f} bar (favorable pour turbines)")
                else:
                    recommendations.append(f"💧 **Réseau basse/moyenne pression** : ΔP moyen = {avg_pressure:.2f} bar (à considérer)")
            
            # Nombre de sites viables
            viable_sites = len(results_sorted[results_sorted['power_kW'] > 0.5]) if 'power_kW' in results_sorted.columns else len(results_sorted)
            recommendations.append(f"✅ **Sites viables** : {viable_sites}/{len(results_sorted)} sites avec potentiel > 0.5 kW")
            
            for rec in recommendations:
                st.markdown(f"- {rec}")
            
            st.markdown("---")
            st.markdown("### Prochaines étapes")
            st.markdown("""
            1. **Approfondir les études** : Sélectionner les 3-5 sites prioritaires pour des études détaillées
            2. **Vérifier la faisabilité** : Consulter le tab "Simulation" pour chaque site avec turbines compatibles
            3. **Évaluer les coûts** : Utiliser l'onglet "Simulation" pour estimer CAPEX/OPEX
            4. **Engager stakeholders** : Présenter les résultats aux décideurs et collectivités locales
            5. **Préparer la mise en œuvre** : Démarches administratives et études détaillées
            """)
            
            st.markdown("---")
            st.markdown("### Export du rapport")
            col_pdf, col_space = st.columns([1, 2])
            with col_pdf:
                if st.button("📄 Exporter en PDF", key="export_analysis_pdf"):
                    try:
                        if pdf_report is None:
                            raise RuntimeError("Le module PDF n'est pas disponible dans cet environnement.")
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                            pdf_path = tmp.name
                        pdf_report.generate_analysis_global_report(pdf_path, results_sorted)
                        with open(pdf_path, 'rb') as f:
                            st.download_button(
                                label="Télécharger le PDF",
                                data=f.read(),
                                file_name=f"resume_analyse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                mime="application/pdf",
                                key="download_analysis_pdf"
                            )
                        st.success("PDF généré avec succès!")
                        import os
                        os.remove(pdf_path)
                    except Exception as e:
                        st.error(f"Erreur lors de la génération du PDF: {str(e)}")
    
    return None


def render_chatbot_panel():
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    chat_history = st.session_state["chat_history"]
    groq_model = "openai/gpt-oss-120b"

    with st.sidebar:
        header_cols = st.columns([1, 1])
        with header_cols[0]:
            st.markdown("### Synthèse interactive")
            st.caption("Questions rapides sur l'analyse du projet et la simulation.")
        with header_cols[1]:
            if st.button("Fermer", key="close-chatbot", width='stretch'):
                st.session_state["chatbot_open"] = False
                st.rerun()
        st.markdown("<hr style='border-color:#dbe7f7; margin:0.6rem 0;'>", unsafe_allow_html=True)
        if chat_history and st.button("Effacer l'historique", key="clear-chat", width='stretch'):
            st.session_state["chat_history"] = []
            st.rerun()

        for message in chat_history:
            with st.chat_message(message.get("role", "assistant")):
                st.markdown(str(message.get("content") or ""))

        question = st.chat_input("Posez votre question", key="chat-input")
        if question:
            chat_history.append({"role": "user", "content": question})
            best_sites = st.session_state.get("results_sorted")
            if isinstance(best_sites, pd.DataFrame) and not best_sites.empty and "meilleur" in question.lower():
                top_site = best_sites.iloc[0]
                answer = (
                    f"Meilleur site (score max) : {top_site.get('site_name', 'N/A')} | "
                    f"Score: {top_site.get('score', 'N/A')} | "
                    f"Puissance: {top_site.get('power_kW', 'N/A')} kW | "
                    f"Debit: {top_site.get('estimated_flow', 'N/A')} m3/h | "
                    f"Pression: {top_site.get('delta_p', 'N/A')} bar"
                )
                chat_history.append({"role": "assistant", "content": answer})
                st.session_state["chat_history"] = chat_history
                st.rerun()
            try:
                ensure_openai_available()
                groq_api_key = get_groq_api_key()
                if not groq_api_key:
                    raise RuntimeError(
                        "Missing GROQ_API_KEY. Add it in Streamlit Cloud secrets or in your local environment."
                    )
                client = openai.OpenAI(
                    api_key=groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                with st.spinner("Réponse en cours..."):
                    response = client.chat.completions.create(
                        model=groq_model,
                        messages=[
                            {
                                "role": "system",
                                "content": "Tu es un assistant expert en analyse hydroenergetique et en synthese de resultats d'etude.",
                            },
                            *chat_history,
                        ],
                        max_tokens=600,
                    )
                answer = response.choices[0].message.content
            except Exception as e:
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    fallback_model = "llama-3.1-8b-instant"
                    try:
                        with st.spinner("Limite atteinte, nouvelle tentative..."):
                            response = client.chat.completions.create(
                                model=fallback_model,
                                messages=[
                                    {
                                        "role": "system",
                                        "content": "Tu es un assistant expert en analyse hydroenergetique et en synthese de resultats d'etude.",
                                    },
                                    *chat_history,
                                ],
                                max_tokens=450,
                            )
                        answer = response.choices[0].message.content
                    except Exception as inner:
                        answer = (
                            "Limite temporaire atteinte. "
                            "Réessayez dans quelques minutes ou réduisez la longueur de la question. "
                            f"Détails: {inner}"
                        )
                else:
                    answer = f"Erreur lors de la génération : {e}"
            chat_history.append({"role": "assistant", "content": answer})
            st.session_state["chat_history"] = chat_history
            st.rerun()

if st.session_state.get("chatbot_open"):
    render_chatbot_panel()

tab1, tab_map, tab2, tab_acteurs, tab_chatbot = st.tabs(
    ["Projet", "Cartographie", "Simulation", "Acteurs et gouvernance", "Chatbot projet"]
)

with tab1:
    # Mise en page avec deux colonnes de même taille
    # 1. Chargement des données réelles
    section = render_section_card("1. Données hydrauliques du territoire (issues du CSV)")
    with section:
        csv_path = 'CSV/aep_organe_pression.csv'
        col1, col2 = st.columns([1.2, 1], gap="large")
        try:
            dfs = load_data({'prv': csv_path})
            raw_df = dfs['prv']
            col1.success("Données hydrauliques chargées pour le projet Larzacqua.")
        except Exception as e:
            col1.error(f"Erreur de chargement : {e}")
            st.stop()

        with col1:
            with st.expander("Voir le tableau brut", expanded=True):
                st.dataframe(raw_df, use_container_width=True, height=320)
        with col2:
            with render_kpi_card():
                kpi_cols = st.columns(3, gap="medium")
                kpi_cols[0].metric("Nombre de sites", len(raw_df))
                if 'estimated_flow' in raw_df.columns:
                    kpi_cols[1].metric("Débit moyen (m³/h)", f"{raw_df['estimated_flow'].mean():.1f}")
                    kpi_cols[2].metric("Débit max (m³/h)", f"{raw_df['estimated_flow'].max():.1f}")
                    st.write("Distribution du débit (m³/h)")
                    st.bar_chart(raw_df['estimated_flow'])
                elif 'debit' in raw_df.columns:
                    kpi_cols[1].metric("Débit moyen (m³/h)", f"{raw_df['debit'].mean():.1f}")
                    kpi_cols[2].metric("Débit max (m³/h)", f"{raw_df['debit'].max():.1f}")
                    st.write("Distribution du débit (m³/h)")
                    st.bar_chart(raw_df['debit'])

    # 2. Calcul hydraulique
    section = render_section_card("2. Calcul hydraulique du projet (delta_p, débit, etc.)")
    with section:
        flow_df = compute_hydraulics(raw_df)
        col1, col2 = st.columns([1.2, 1], gap="large")
        with col1:
            with st.expander("Voir les résultats hydrauliques", expanded=True):
                display_cols = [
                    'site_name', 'delta_p', 'diameter', 'estimated_flow',
                    'estimated_flow_obs', 'estimated_flow_calc', 'flow_min', 'flow_max'
                ]
                st.dataframe(flow_df[display_cols], use_container_width=True, height=320)
        with col2:
            with render_kpi_card():
                if 'delta_p' in flow_df.columns:
                    kpi_cols = st.columns(3, gap="medium")
                    kpi_cols[0].metric("ΔP moyen (bar)", f"{flow_df['delta_p'].mean():.2f}")
                    kpi_cols[1].metric("ΔP max (bar)", f"{flow_df['delta_p'].max():.2f}")
                    kpi_cols[2].metric("ΔP min (bar)", f"{flow_df['delta_p'].min():.2f}")
                    st.write("Distribution de la pression (delta_p, bar)")
                    st.bar_chart(flow_df['delta_p'])

    # 3. Fusion des résultats
    section = render_section_card("3. Fusion des résultats hydroélectriques")
    with section:
        power_df = compute_power(flow_df)
        results = flow_df.copy()
        results['power_kW'] = pd.to_numeric(power_df['power'], errors="coerce") / 1000.0
        st.dataframe(results, use_container_width=True, height=360)

    # 4. Indicateurs globaux
    section = render_section_card("4. Indicateurs globaux du territoire")
    with section:
        power_total_kw = pd.to_numeric(results['power_kW'], errors="coerce").fillna(0).sum()
        annual_energy_kwh = power_total_kw * 6132
        with render_kpi_card():
            kpi_cols = st.columns(2, gap="medium")
            kpi_cols[0].metric("Puissance cumulée (kW)", f"{power_total_kw:.2f}")
            kpi_cols[1].metric("Énergie annuelle (kWh/an)", f"{annual_energy_kwh:,.0f}".replace(",", " "))
            st.caption("Hypothèse: 6132 h de fonctionnement par an.")

    # 5. Tri des sites par puissance décroissante
    section = render_section_card("5. Hiérarchisation des sites du territoire")
    with section:
        results_sorted = results.sort_values('power_kW', ascending=False)
        st.session_state["results_sorted"] = results_sorted
        st.dataframe(results_sorted, use_container_width=True, height=360)

    # 6. Synthèse brute (top 3)
    section = render_section_card("6. Synthèse brute des sites prioritaires")
    with section:
        best_sites = results_sorted.head(3)
        synthese_rows = []
        synthese = ""
        for _, row in best_sites.iterrows():
            synthese += (
                f"Site: {row['site_name']} | Puissance: {row['power_kW']:.2f} kW | "
                f"Débit obs: {row.get('estimated_flow_obs', float('nan')):.2f} m³/h | "
                f"Débit calc: {row.get('estimated_flow_calc', float('nan')):.2f} m³/h | "
                f"Pression: {row['delta_p']:.2f} bar\n"
            )
            synthese_rows.append(
                {
                    "Site": row['site_name'],
                    "Puissance (kW)": round(row['power_kW'], 2),
                    "Débit obs (m³/h)": round(row.get('estimated_flow_obs', float('nan')), 2),
                    "Débit calc (m³/h)": round(row.get('estimated_flow_calc', float('nan')), 2),
                    "Pression (bar)": round(row['delta_p'], 2),
                }
            )
        st.dataframe(pd.DataFrame(synthese_rows), use_container_width=True, hide_index=True)
        with st.expander("Synthèse texte brute", expanded=True):
            st.code(synthese, language="text")

    # 7. Résumé global de l'analyse
    render_analysis_global_summary(results_sorted, power_total_kw, annual_energy_kwh)

    # 8. Export CSV (optionnel)
    section = render_section_card("8. Export CSV (analyse_comparative.csv)")
    with section:
        if st.button("Exporter le CSV de l'analyse"):
            results_sorted.to_csv('outputs/analyse_comparative.csv', index=False)
            st.success("Fichier outputs/analyse_comparative.csv exporté !")

with tab_map:
    from streamlit_folium import st_folium
    st.caption("Filtrez, recherchez et explorez les points sur la carte.")
    csv_path = 'CSV/aep_organe_pression.csv'
    try:
        df = load_pressure_reducers(csv_path)
        if "TYPE" not in df.columns:
            df["TYPE"] = ""
        if "COMMUNE" not in df.columns:
            df["COMMUNE"] = ""

        col_filters, col_map, col_info = st.columns([0.65, 2.55, 1.0], gap="large")
        with col_filters:
            st.subheader("Filtres")
            selected_communes = st.multiselect(
                "Communes",
                options=sorted(df["COMMUNE"].dropna().unique().tolist()),
            )
            selected_types = st.multiselect(
                "Types",
                options=sorted(df["TYPE"].dropna().unique().tolist()),
            )

        filtered_df = df.copy()
        if selected_communes:
            filtered_df = filtered_df[filtered_df["COMMUNE"].isin(selected_communes)]
        if selected_types:
            filtered_df = filtered_df[filtered_df["TYPE"].isin(selected_types)]

        if filtered_df.empty:
            st.warning("Aucune donnée géolocalisée exploitable.")
        else:
            with col_filters:
                search_label = st.selectbox(
                    "Rechercher un réducteur",
                    options=[""] + filtered_df["NOM"].astype(str).tolist(),
                    index=0,
                )

            if "map_center" not in st.session_state:
                st.session_state.map_center = None
            if "map_zoom" not in st.session_state:
                st.session_state.map_zoom = 12
            if "last_search_label" not in st.session_state:
                st.session_state.last_search_label = ""
            if st.session_state.map_center is None and not filtered_df.empty:
                st.session_state.map_center = [
                    float(filtered_df["lat_wgs84"].median()),
                    float(filtered_df["lon_wgs84"].median()),
                ]
                st.session_state.map_zoom = 12

            with col_map:
                center = st.session_state.map_center
                zoom_start = st.session_state.map_zoom
                fit_bounds = False
                if search_label and search_label != st.session_state.last_search_label:
                    selected_row = filtered_df[filtered_df["NOM"].astype(str) == search_label].iloc[0]
                    center = [selected_row["lat_wgs84"], selected_row["lon_wgs84"]]
                    zoom_start = 16
                    fit_bounds = False
                    st.session_state.last_search_label = search_label
                elif not search_label:
                    st.session_state.last_search_label = ""
                folium_map = create_pressure_reducer_map(
                    filtered_df,
                    center=center,
                    zoom_start=zoom_start,
                    fit_bounds=fit_bounds,
                )
                map_data = st_folium(
                    folium_map,
                    width='content',
                    height=680,
                    returned_objects=["last_object_clicked", "last_object_clicked_popup"],
                    key="pressure_reducer_map",
                )

                metric_col1, metric_col2 = st.columns(2)
                metric_col1.metric("Total", len(df))
                metric_col2.metric("Affiches", len(filtered_df))

            selected_id = None
            if map_data and map_data.get("last_object_clicked"):
                clicked = map_data["last_object_clicked"]
                if isinstance(clicked, dict) and "lat" in clicked and "lng" in clicked:
                    lat = clicked["lat"]
                    lon = clicked["lng"]
                    candidates = df.copy()
                    candidates["_dist"] = (
                        (candidates["lat_wgs84"] - lat) ** 2 +
                        (candidates["lon_wgs84"] - lon) ** 2
                    )
                    selected_id = int(candidates.sort_values("_dist").iloc[0]["id"])

            with col_info:
                st.subheader("Informations du réducteur")
                if selected_id is not None and selected_id in df['id'].values:
                    row = df[df['id'] == selected_id].iloc[0]
                    st.markdown(f"**Nom :** {row['NOM']}")
                    st.markdown(f"**Commune :** {row.get('COMMUNE', 'N/A')}")
                    st.markdown(f"**Type :** {row.get('TYPE', 'N/A')}")
                    st.markdown(f"**Marque :** {row.get('MARQUE', 'N/A')}")
                    st.markdown(f"**Diamètre :** {row.get('DIAMETRE', 'N/A')}")
                    st.markdown(f"**Pression amont :** {row.get('PRES_AMONT', 'N/A')}")
                    st.markdown(f"**Pression aval :** {row.get('PRESS_AVAL', 'N/A')}")
                    st.markdown(f"**Observations :** {row.get('OBSERVATIONS', 'N/A')}")
                else:
                    st.info("Cliquez sur un réducteur sur la carte pour voir ses informations.")
    except Exception as e:
        st.error(f"Erreur lors du chargement ou de l'affichage : {e}")

with tab2:
    try:
        file_paths = {'prv': 'CSV/aep_organe_pression.csv'}
        dfs = load_data(file_paths)
        prv_df = dfs['prv']

        hydro_df = compute_hydraulics(prv_df)
        if 'estimated_flow_obs' not in hydro_df.columns:
            hydro_df['estimated_flow_obs'] = np.nan
        if 'estimated_flow' not in hydro_df.columns and 'estimated_flow_obs' in hydro_df.columns:
            hydro_df['estimated_flow'] = hydro_df['estimated_flow_obs']
        if 'flow_min' not in hydro_df.columns and 'estimated_flow_obs' in hydro_df.columns:
            hydro_df['flow_min'] = hydro_df['estimated_flow_obs'] * 0.8
        if 'flow_max' not in hydro_df.columns and 'estimated_flow_obs' in hydro_df.columns:
            hydro_df['flow_max'] = hydro_df['estimated_flow_obs'] * 1.2
        power_df = compute_power(hydro_df)
        scored_df = power_df.copy()
        scored_df['score'] = pd.to_numeric(scored_df['power'], errors='coerce') / 1000.0

        scored_df['_has_observed_flow'] = scored_df['estimated_flow_obs'].notna()

        # =========================
        # CAPEX META
        # =========================
        turbine_db = load_turbine_db('CSV/turbine_db.csv')

        capex_meta_cols = [
            'NOM',
            'Distance à l’installation [m]',
            'Type d’installation électrique',
            'Distance au Poste-électrique le plus proche [m]',
        ]

        capex_meta_cols = [col for col in capex_meta_cols if col in prv_df.columns]

        if capex_meta_cols:
            capex_meta = prv_df[capex_meta_cols].copy()

            capex_meta = capex_meta.rename(columns={
                'NOM': 'site_name',
                'Distance à l’installation [m]': 'distance_install_m',
                'Type d’installation électrique': 'electrical_install_type',
                'Distance au Poste-électrique le plus proche [m]': 'distance_grid_m',
            })

            for col in ['distance_install_m', 'distance_grid_m']:
                if col in capex_meta.columns:
                    capex_meta[col] = pd.to_numeric(
                        capex_meta[col].astype(str).str.replace(',', '.', regex=False),
                        errors='coerce'
                    )

            scored_df = scored_df.merge(capex_meta, on='site_name', how='left')

        # ❌ NE PAS remettre le merge ici (redondant)
        # scored_df = scored_df.merge(hydro_df[['site_name', 'estimated_flow_obs']], ...)

    except Exception as e:
        st.error(f"Erreur de chargement : {e}")
        st.stop()

def propose_turbines(site_row, turbine_db, top_n=2):
    def select_candidates(current_row, local_top_n=top_n):
        return rank_compatible_turbines(current_row, turbine_db, max_results=local_top_n)

    candidates = select_candidates(site_row)
    scored_df = scored_df.copy()
    scored_df['_sim_id'] = scored_df.index.astype(str)
    scored_df['_compatible_turbines_obs'] = scored_df.apply(lambda current_row: len(select_candidates(current_row, local_top_n=2)), axis=1)
    scored_df['_is_tos'] = scored_df['site_name'].astype(str).str.contains('tos', case=False, na=False)
    scored_df = scored_df.sort_values(['_is_tos', 'score'], ascending=[False, False]).reset_index(drop=True)
    site_tabs = st.tabs([f"{row['site_name']} (score={row['score']:.2f})" for _, row in scored_df.iterrows()])
    for idx, (tab, (_, row)) in enumerate(zip(site_tabs, scored_df.iterrows())):
        with tab:
            site_key_raw = f"{row.get('_sim_id', row.name)}_{row.get('site_name', 'site')}"
            site_key = re.sub(r"[^A-Za-z0-9_-]+", "_", site_key_raw)
            run_key = f"run_site_simulation_{site_key}"
            if run_key not in st.session_state:
                st.session_state[run_key] = False
            if st.button("Generer la simulation de ce site", key=f"{run_key}_button"):
                st.session_state[run_key] = True
            if not st.session_state[run_key]:
                st.info("Cliquez sur le bouton pour generer la simulation de ce site.")
            else:
                import modules.productible as productible
                turbines = select_candidates(row)
                site_section_key = f"site_section_{site_key}"
                if site_section_key not in st.session_state:
                    st.session_state[site_section_key] = 0

                step_labels = [
                    "Sélection turbine",
                    "Estimation CAPEX/OPEX",
                    "OA / Prix évité",
                    "Estimations",
                    "Recommandation",
                ]
                # Per-site session keys used across steps
                debit_key = f"debit_m3h_{site_key}"
                pression_key = f"pression_amont_{site_key}"
                rendement_key = f"rendement_{site_key}"
                selectbox_key = f"selectbox_productible_{site_key}"
                tarif_oa_key = f"tarif_oa_{site_key}"
                prix_evite_key = f"prix_evite_{site_key}"
                if debit_key not in st.session_state:
                    st.session_state[debit_key] = float(row.get('estimated_flow', 0) or 0)
                if pression_key not in st.session_state:
                    st.session_state[pression_key] = float(row.get('delta_p', 0) or 0)
                if selectbox_key not in st.session_state:
                    st.session_state[selectbox_key] = 0
                if tarif_oa_key not in st.session_state:
                    st.session_state[tarif_oa_key] = 0.12
                if prix_evite_key not in st.session_state:
                    st.session_state[prix_evite_key] = 0.18
                if rendement_key not in st.session_state:
                    default_rendement = 65
                    if not turbines.empty:
                        default_rendement = int(float(turbines.iloc[0]['rendement_typique']) * 100)
                    st.session_state[rendement_key] = default_rendement
                step_classes = []
                for step_index in range(len(step_labels)):
                    if st.session_state[site_section_key] == step_index:
                        step_classes.append("active")
                    elif st.session_state[site_section_key] > step_index:
                        step_classes.append("completed")
                    else:
                        step_classes.append("")

                st.markdown(
                    """
                    <style>
                    .simuwatter-site-process { position: relative; display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1.5rem; }
                    .simuwatter-site-process::before { content:''; position:absolute; top:50%; left:5%; right:5%; height:2px; background:#cbd5e1; transform: translateY(-50%); z-index:0; }
                    .simuwatter-site-process .step { position: relative; z-index:1; flex:1; text-align:center; }
                    .simuwatter-site-step-badge { display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:999px; background:#e2e8f0; color:#0f172a; font-weight:700; margin-bottom:0.4rem; border: 1px solid #cbd5e1; }
                    .simuwatter-site-process .step.completed .simuwatter-site-step-badge,
                    .simuwatter-site-process .step.active .simuwatter-site-step-badge {
                        background: linear-gradient(135deg, rgba(14,165,233,0.95), rgba(56,189,248,0.95));
                        color:#ffffff;
                        border-color: transparent;
                    }
                    .simuwatter-site-process .step.completed .step-label,
                    .simuwatter-site-process .step.active .step-label {
                        color:#0f172a;
                        font-weight:700;
                    }
                    .step-label { display:block; font-size:0.9rem; color:#64748b; margin-top:0.2rem; }
                    .simuwatter-site-button-container { display:flex; gap:1rem; margin-bottom:1.25rem; }
                    .simuwatter-site-button-wrapper { width:100%; }
                    .simuwatter-site-button-wrapper .stButton>button {
                        min-height: 130px;
                        width: 100%;
                        padding: 1rem 1.2rem;
                        border-radius: 22px;
                        border: 1px solid rgba(14,165,233,0.28);
                        background: linear-gradient(135deg, rgba(14,165,233,0.22), rgba(56,189,248,0.10));
                        color: #0b172a;
                        font-size: 0.95rem;
                        font-weight: 700;
                        text-align: left;
                        line-height: 1.4;
                        box-shadow: 0 18px 36px rgba(14,165,233,0.12);
                        transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
                        white-space: pre-wrap;
                    }
                    .simuwatter-site-button-wrapper .stButton>button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 22px 44px rgba(14,165,233,0.14);
                        background: linear-gradient(135deg, rgba(14,165,233,0.34), rgba(56,189,248,0.16));
                    }
                    .simuwatter-site-button-wrapper .stButton>button:focus {
                        outline: 2px solid rgba(56,189,248,0.65);
                        outline-offset: 2px;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"""
                    <div class="simuwatter-site-process">
                      <div class="step {step_classes[0]}"><div class="simuwatter-site-step-badge">1</div><span class="step-label">{step_labels[0]}</span></div>
                      <div class="step {step_classes[1]}"><div class="simuwatter-site-step-badge">2</div><span class="step-label">{step_labels[1]}</span></div>
                      <div class="step {step_classes[2]}"><div class="simuwatter-site-step-badge">3</div><span class="step-label">{step_labels[2]}</span></div>
                      <div class="step {step_classes[3]}"><div class="simuwatter-site-step-badge">4</div><span class="step-label">{step_labels[3]}</span></div>
                      <div class="step {step_classes[4]}"><div class="simuwatter-site-step-badge">5</div><span class="step-label">{step_labels[4]}</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                cols = st.columns([1, 1, 1, 1, 1], gap="small")
                with cols[0]:
                    if st.button("1) Sélection turbine", key=f"tab_selection_{site_key}"):
                        st.session_state[site_section_key] = 0
                with cols[1]:
                    if st.button("2) Estimation CAPEX/OPEX", key=f"tab_capex_{site_key}"):
                        st.session_state[site_section_key] = 1
                with cols[2]:
                    if st.button("3) OA / Prix évité", key=f"tab_oa_{site_key}"):
                        st.session_state[site_section_key] = 2
                with cols[3]:
                    if st.button("4) Estimations", key=f"tab_productible_{site_key}"):
                        st.session_state[site_section_key] = 3
                with cols[4]:
                    if st.button("5) Recommandation", key=f"tab_recommandation_{site_key}"):
                        st.session_state[site_section_key] = 4
                st.markdown("---")
                productible_context = st.session_state.get(f"productible_context_{site_key}", {})
                ai_recommendation = st.session_state.get(f"site_{site_key}_selection_result")
                scenarios_injection = productible_context.get("scenarios_injection", []) if productible_context else []
                scenarios_autoconsommation = productible_context.get("scenarios_autoconsommation", []) if productible_context else []
                if st.session_state[site_section_key] == 0:
                    puissance_kw = row['power'] / 1000 if 'power' in row else 0
                    debit_obs_m3h = row.get('estimated_flow_obs', float('nan'))
                    debit_calc_m3h = row.get('estimated_flow_calc', float('nan'))
                    debit_m3h = row['estimated_flow'] if 'estimated_flow' in row else 0
                    debit_m3s = debit_m3h / 3600 if debit_m3h else 0
                    debit_source = "observé" if pd.notna(debit_obs_m3h) else "calculé"
                    pression_bar = row['delta_p'] if 'delta_p' in row else 0
                    type_reseau = "Alimentation en eau potable (AEP)"
                    gamme_puissance = "petite/ moyenne puissance (1–10 kW)" if puissance_kw <= 10 else "moyenne/haute puissance (>10 kW)"
                    synthese_site = "1. Rappel des paramètres du site\n\n"
                    synthese_site += "| Paramètre | Valeur |\n|---|---|\n"
                    synthese_site += f"| Puissance théorique | {puissance_kw:.2f} kW |\n"
                    if pd.notna(debit_obs_m3h):
                        synthese_site += f"| Débit observé | {debit_obs_m3h:.2f} m³ h⁻¹ |\n"
                    if pd.notna(debit_calc_m3h):
                        synthese_site += f"| Débit calculé | {debit_calc_m3h:.2f} m³ h⁻¹ |\n"
                    synthese_site += f"| Débit utilisé ({debit_source}) | {debit_m3h:.0f} m³ h⁻¹ (≈ {debit_m3s:.2f} m³ s⁻¹) |\n"
                    synthese_site += f"| Pression d’alimentation | {pression_bar:.2f} bar |\n"
                    synthese_site += f"| Type de réseau | {type_reseau} |\n"
                    synthese_site += f"\nCes valeurs placent le site dans la gamme {gamme_puissance} avec un débit suffisant.\n\n"
                    synthese_site += "2. Turbines compatibles\n\n"
                    if not turbines.empty:
                        synthese_site += "| Turbine | Diamètre (Ø) | Puissance nominale (kW) | Intervalle de puissance | Type | Source |\n"
                        synthese_site += "|---|---|---|---|---|---|\n"
                        for _, t in turbines.iterrows():
                            synthese_site += f"| {t['type_turbine']} {t['diametre_mm']} mm | {t['diametre_mm']} mm | {t['puissance_min_kw']} – {t['puissance_max_kw']} | {t['puissance_min_kw']}-{t['puissance_max_kw']} | {t['type_turbine']} | [Source]({t['source']}) |\n"
                        synthese_site += "\n3. Explications pédagogiques et recommandation\n\nPour chaque turbine listée ci-dessus, explique brièvement son principe, ses avantages et inconvénients pour ce site, puis propose la meilleure option avec justification. Utilise strictement les titres fournis, sans emoji ni ajout décoratif. Ne répète pas les tableaux. Sois synthétique et pédagogique."
                    else:
                        synthese_site += "Aucune turbine compatible n'a été trouvée pour ce site."
                    synthese_site += (
                        "\n\nFORMAT DE REPONSE OBLIGATOIRE:\n"
                        "- Commencer par le titre exact: 1. Rappel des paramètres du site\n"
                        "- Puis: 2. Turbines compatibles\n"
                        "- Puis: 3. Explications pédagogiques et recommandation\n"
                        "- Ne pas déplacer ni omettre ces titres\n"
                        "- Ne pas ajouter d'autres sections\n"
                        "- Ne pas commencer par le principe des turbines\n"
                    )
                    render_site_ai_generation(
                        synthese_site,
                        allow_call=not turbines.empty,
                        cache_key=f"site_{site_key}_selection",
                        title="Synthese de selection",
                        max_tokens=600,
                    )
                    display_cols = [
                        'type_turbine', 'diametre_mm', 'pression_min_bar', 'pression_max_bar',
                        'debit_min_m3h', 'debit_max_m3h', 'puissance_min_kw', 'puissance_max_kw',
                        'rendement_typique', 'prix_estime_eur', 'description', 'source'
                    ]
                    selection_report_data = {
                        "site_summary_text": synthese_site,
                        "compatible_turbines_display": turbines[display_cols].reset_index(drop=True).to_dict(orient="records") if not turbines.empty else [],
                        "compatible_turbines_columns": [
                            "type_turbine", "diametre_mm", "pression_min_bar", "pression_max_bar",
                            "debit_min_m3h", "debit_max_m3h", "puissance_min_kw", "puissance_max_kw",
                            "rendement_typique", "prix_estime_eur", "description", "source",
                        ],
                        "selection_prompt": synthese_site,
                        "selection_ai_result": st.session_state.get(f"site_{site_key}_selection_result"),
                    }
                    st.session_state[f"selection_report_data_{site_key}"] = selection_report_data
                    st.subheader("Turbines compatibles (tableau)")
                    if turbines.empty:
                        st.info("Aucune turbine compatible")
                    else:
                        st.dataframe(turbines[display_cols].reset_index(drop=True))
                elif st.session_state[site_section_key] == 1:
                    st.subheader("Estimation CAPEX/OPEX")
                    st.markdown("---")

                    if True:
                        with st.expander("Comment les CAPEX/OPEX sont estimés ?", expanded=False):
                            st.markdown(
                                """
                                **Structure du CAPEX**
                                - **CAPEX fixe (projet)** : etudes, cadrage, ingenierie, demarches, coordination.
                                - **CAPEX de base** : equipements hydrauliques + electriques (inclut la turbine).
                                - **Integration hydraulique** : complexite d'installation sur site.
                                - **Raccordement electrique** : distance au point de connexion et complexite reseau.

                                **1. CAPEX fixe (indépendant des sites)**
                                Le CAPEX fixe correspond aux coûts mutualisés du projet, indépendants des caractéristiques individuelles des sites.
                                Il regroupe les étapes amont nécessaires à la conception et au cadrage global du système.

                                Composition du CAPEX fixe :
                                - études de faisabilité et analyse technico-économique
                                - modélisation hydraulique globale et définition de la méthodologie
                                - ingénierie de conception et dimensionnement initial
                                - démarches administratives et réglementaires
                                - coordination et gestion de projet

                                Estimation du CAPEX fixe :
                                C_fixe = C_etudes + C_administratif
                                avec :
                                - C_etudes ≈ 2 000 - 5 000 €
                                - C_administratif ≈ 800 - 2 500 €
                                soit un ordre de grandeur global :
                                CAPEX fixe total : 2 800 à 7 500 €

                                **2. CAPEX variable (dépendant du site)**
                                Le CAPEX variable regroupe l’ensemble des coûts directement liés à l’installation sur chaque site.

                                2.1 Coût des équipements hydrauliques et électromécaniques
                                Le coût de base correspond à la chaîne de conversion énergétique :
                                C_base = C_turbine + C_equipement
                                Ce coût inclut :
                                - la turbine adaptée au site
                                - la génératrice
                                - l’armoire électrique
                                - les capteurs et dispositifs de contrôle

                                2.2 Facteur d’intégration hydraulique
                                Un facteur correctif est appliqué afin de représenter la complexité d’intégration dans l’ouvrage existant :
                                - installation simple (≤ 50 m) : F_int = 1.0
                                - installation intermédiaire (50–150 m) : F_int = 1.2
                                - installation complexe (> 150 m) : F_int = 1.5 à 2.0
                                Le coût corrigé devient :
                                C_int = C_base ⋅ F_int

                                2.3 Coût de raccordement électrique
                                Le coût de raccordement dépend de la distance au point de connexion et de la complexité du réseau électrique :
                                - raccordement simple : 0 à 5 000 €
                                - raccordement complexe : 5 000 à 20 000 €
                                Ce coût est ajouté au coût d’intégration hydraulique.

                                **3. CAPEX total**
                                Le coût total d’investissement pour chaque site est défini par :
                                C_total = C_fixe + C_int + C_elec
                                où :
                                - C_fixe représente les coûts mutualisés du projet
                                - C_int correspond au coût des équipements et de leur intégration hydraulique
                                - C_elec correspond au raccordement électrique

                                **Parametres utilises**
                                - **Distance a l'installation** : choisit le niveau d'integration.
                                - **Type d'installation electrique + distance poste** : choisit le niveau de raccordement.
                                - **Prix turbine** : ajoute au CAPEX de base.

                                **OPEX (ordre de grandeur)**
                                - **Micro-inline / pico-inline** : 1.5% a 3% de Cequip (≈ 200 a 600 EUR/an).
                                - **PAT (Pump As Turbine)** : 2% a 4% de Cequip (≈ 300 a 900 EUR/an).
                                - **Micro turbine Francis** : 3% a 6% de Cequip (≈ 800 a 2 000 EUR/an).
                                - **Micro turbine Pelton** : 3% a 7% de Cequip (≈ 1 000 a 2 500 EUR/an).

                                **Cout de la maintenance**
                                - **Maintenance preventive** : inspection turbine/generatrice, vannes/clapets/filtres, capteurs, nettoyage.
                                  Ordre de grandeur : 2% a 4% du CAPEX equipements / an.
                                - **Maintenance corrective** : remplacement pieces mecaniques, intervention generatrice/electronique, fuites.
                                  Ordre de grandeur : 1% a 3% du CAPEX equipements / an.
                                - **Wear & tear** : joints, roulements, capteurs pression, elements hydrauliques.
                                  Ordre de grandeur : 1% a 2% du CAPEX equipements / an.
                                - **Synthese maintenance** : Omaintenance = (0.04 a 0.09) ⋅ Cequip.

                                **Couts d'exploitation**
                                - **Supervision + telegestion** : monitoring et transmission des donnees.
                                  Ordre de grandeur : 50 a 300 EUR/an/site.
                                - **Assurance** : equipements + responsabilite civile + risques techniques.
                                  Ordre de grandeur : 0.3% a 1% du CAPEX total (≈ 80 a 400 EUR/an).
                                - **Consommations auxiliaires** : capteurs, automate, telecom, controle.
                                  Ordre de grandeur : 20 a 150 EUR/an.
                                """,
                                unsafe_allow_html=False,
                            )
                            st.markdown("#### Tableau OPEX")
                            opex_table = pd.DataFrame(
                                [
                                    {
                                        "Type de turbine": "Micro-inline / Pico-inline",
                                        "OPEX (% CAPEX equipement)": "1.5 - 3 %",
                                        "Ordre de grandeur": "200 - 600 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "PAT",
                                        "OPEX (% CAPEX equipement)": "2 - 4 %",
                                        "Ordre de grandeur": "300 - 900 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "Francis micro",
                                        "OPEX (% CAPEX equipement)": "3 - 6 %",
                                        "Ordre de grandeur": "800 - 2 000 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "Pelton micro",
                                        "OPEX (% CAPEX equipement)": "3 - 7 %",
                                        "Ordre de grandeur": "1 000 - 2 500 EUR/an",
                                    },
                                ]
                            )
                            st.table(opex_table)

def propose_turbines(site_row, turbine_db, top_n=2):
    import pandas as pd
    import streamlit as st
    import re
    import numpy as np

    def select_candidates(current_row, local_top_n=top_n):
        # Sélection stricte: si rien n'est physiquement compatible, on retourne vide.
        return rank_compatible_turbines(current_row, turbine_db, max_results=local_top_n)

    # =====================================================
    # génération candidats site
    # =====================================================

    candidates = select_candidates(site_row)

    site_tabs = st.tabs([
        f"{row['site_name']} (score={row['score']:.2f})"
        for _, row in scored_df.iterrows()
    ])

    for idx, (tab, (_, row)) in enumerate(zip(site_tabs, scored_df.iterrows())):

        with tab:

            site_key_raw = f"{row.get('site_name', 'site')}_{row.name}_{idx}"
            site_key = re.sub(r"[^A-Za-z0-9_-]+", "_", site_key_raw)

            run_key = f"run_site_simulation_{site_key}"

            if run_key not in st.session_state:
                st.session_state[run_key] = False

            if st.button("Generer la simulation de ce site", key=f"{run_key}_button"):
                st.session_state[run_key] = True

            if not st.session_state[run_key]:
                st.info("Cliquez sur le bouton pour generer la simulation de ce site.")

            else:
                import modules.productible as productible

                turbines = select_candidates(row)

                site_section_key = f"site_section_{site_key}"
                if site_section_key not in st.session_state:
                    st.session_state[site_section_key] = 0

                step_labels = [
                    "Sélection turbine",
                    "Estimation CAPEX/OPEX",
                    "OA / Prix évité",
                    "Estimations",
                    "Recommandation",
                ]

                debit_key = f"debit_m3h_{site_key}"
                pression_key = f"pression_amont_{site_key}"
                rendement_key = f"rendement_{site_key}"
                selectbox_key = f"selectbox_productible_{site_key}"
                tarif_oa_key = f"tarif_oa_{site_key}"
                prix_evite_key = f"prix_evite_{site_key}"

                if debit_key not in st.session_state:
                    observed_flow = row.get('estimated_flow_obs', np.nan)
                    st.session_state[debit_key] = float(observed_flow) if pd.notna(observed_flow) else 0.0

                if pression_key not in st.session_state:
                    st.session_state[pression_key] = float(row.get('delta_p', 0) or 0)

                if selectbox_key not in st.session_state:
                    st.session_state[selectbox_key] = 0

                if tarif_oa_key not in st.session_state:
                    st.session_state[tarif_oa_key] = 0.12

                if prix_evite_key not in st.session_state:
                    st.session_state[prix_evite_key] = 0.18

                if rendement_key not in st.session_state:
                    default_rendement = 65
                    if not turbines.empty:
                        default_rendement = int(
                            float(turbines.iloc[0]['rendement_typique']) * 100
                        )
                    st.session_state[rendement_key] = default_rendement

                step_classes = []
                for step_index in range(len(step_labels)):
                    if st.session_state[site_section_key] == step_index:
                        step_classes.append("active")
                    elif st.session_state[site_section_key] > step_index:
                        step_classes.append("completed")
                    else:
                        step_classes.append("")
                st.markdown(
                    """
                    <style>
                    .simuwatter-site-process { position: relative; display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1.5rem; }
                    .simuwatter-site-process::before { content:''; position:absolute; top:50%; left:5%; right:5%; height:2px; background:#cbd5e1; transform: translateY(-50%); z-index:0; }
                    .simuwatter-site-process .step { position: relative; z-index:1; flex:1; text-align:center; }
                    .simuwatter-site-step-badge { display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:999px; background:#e2e8f0; color:#0f172a; font-weight:700; margin-bottom:0.4rem; border: 1px solid #cbd5e1; }
                    .simuwatter-site-process .step.completed .simuwatter-site-step-badge,
                    .simuwatter-site-process .step.active .simuwatter-site-step-badge {
                        background: linear-gradient(135deg, rgba(14,165,233,0.95), rgba(56,189,248,0.95));
                        color:#ffffff;
                        border-color: transparent;
                    }
                    .simuwatter-site-process .step.completed .step-label,
                    .simuwatter-site-process .step.active .step-label {
                        color:#0f172a;
                        font-weight:700;
                    }
                    .step-label { display:block; font-size:0.9rem; color:#64748b; margin-top:0.2rem; }
                    .simuwatter-site-button-container { display:flex; gap:1rem; margin-bottom:1.25rem; }
                    .simuwatter-site-button-wrapper { width:100%; }
                    .simuwatter-site-button-wrapper .stButton>button {
                        min-height: 130px;
                        width: 100%;
                        padding: 1rem 1.2rem;
                        border-radius: 22px;
                        border: 1px solid rgba(14,165,233,0.28);
                        background: linear-gradient(135deg, rgba(14,165,233,0.22), rgba(56,189,248,0.10));
                        color: #0b172a;
                        font-size: 0.95rem;
                        font-weight: 700;
                        text-align: left;
                        line-height: 1.4;
                        box-shadow: 0 18px 36px rgba(14,165,233,0.12);
                        transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
                        white-space: pre-wrap;
                    }
                    .simuwatter-site-button-wrapper .stButton>button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 22px 44px rgba(14,165,233,0.14);
                        background: linear-gradient(135deg, rgba(14,165,233,0.34), rgba(56,189,248,0.16));
                    }
                    .simuwatter-site-button-wrapper .stButton>button:focus {
                        outline: 2px solid rgba(56,189,248,0.65);
                        outline-offset: 2px;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"""
                    <div class="simuwatter-site-process">
                      <div class="step {step_classes[0]}"><div class="simuwatter-site-step-badge">1</div><span class="step-label">{step_labels[0]}</span></div>
                      <div class="step {step_classes[1]}"><div class="simuwatter-site-step-badge">2</div><span class="step-label">{step_labels[1]}</span></div>
                      <div class="step {step_classes[2]}"><div class="simuwatter-site-step-badge">3</div><span class="step-label">{step_labels[2]}</span></div>
                      <div class="step {step_classes[3]}"><div class="simuwatter-site-step-badge">4</div><span class="step-label">{step_labels[3]}</span></div>
                      <div class="step {step_classes[4]}"><div class="simuwatter-site-step-badge">5</div><span class="step-label">{step_labels[4]}</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                cols = st.columns([1, 1, 1, 1, 1], gap="small")
                with cols[0]:
                    if st.button("1) Sélection turbine", key=f"tab_selection_{site_key}"):
                        st.session_state[site_section_key] = 0
                with cols[1]:
                    if st.button("2) Estimation CAPEX/OPEX", key=f"tab_capex_{site_key}"):
                        st.session_state[site_section_key] = 1
                with cols[2]:
                    if st.button("3) OA / Prix évité", key=f"tab_oa_{site_key}"):
                        st.session_state[site_section_key] = 2
                with cols[3]:
                    if st.button("4) Estimations", key=f"tab_productible_{site_key}"):
                        st.session_state[site_section_key] = 3
                with cols[4]:
                    if st.button("5) Recommandation", key=f"tab_recommandation_{site_key}"):
                        st.session_state[site_section_key] = 4
                st.markdown("---")
                productible_context = st.session_state.get(f"productible_context_{site_key}", {})
                ai_recommendation = st.session_state.get(f"site_{site_key}_selection_result")
                scenarios_injection = productible_context.get("scenarios_injection", []) if productible_context else []
                scenarios_autoconsommation = productible_context.get("scenarios_autoconsommation", []) if productible_context else []
                if st.session_state[site_section_key] == 0:
                    puissance_kw = row['power'] / 1000 if 'power' in row else 0
                    debit_obs_m3h = row.get('estimated_flow_obs', float('nan'))
                    debit_calc_m3h = row.get('estimated_flow_calc', float('nan'))
                    debit_m3h = row.get('estimated_flow_obs', float('nan'))
                    debit_m3s = debit_m3h / 3600 if debit_m3h else 0
                    debit_source = "observé" if pd.notna(debit_obs_m3h) else "indisponible"
                    pression_bar = row['delta_p'] if 'delta_p' in row else 0
                    type_reseau = "Alimentation en eau potable (AEP)"
                    gamme_puissance = "petite/ moyenne puissance (1–10 kW)" if puissance_kw <= 10 else "moyenne/haute puissance (>10 kW)"
                    synthese_site = "1. Rappel des paramètres du site\n\n"
                    synthese_site += "| Paramètre | Valeur |\n|---|---|\n"
                    synthese_site += f"| Puissance théorique | {puissance_kw:.2f} kW |\n"
                    if pd.notna(debit_obs_m3h):
                        synthese_site += f"| Débit observé | {debit_obs_m3h:.2f} m³ h⁻¹ |\n"
                    if pd.notna(debit_calc_m3h):
                        synthese_site += f"| Débit calculé | {debit_calc_m3h:.2f} m³ h⁻¹ |\n"
                    if pd.notna(debit_m3h):
                        synthese_site += f"| Débit utilisé ({debit_source}) | {debit_m3h:.2f} m³ h⁻¹ (≈ {debit_m3s:.2f} m³ s⁻¹) |\n"
                    else:
                        synthese_site += "| Débit utilisé (observé) | non disponible |\n"
                    synthese_site += f"| Pression d’alimentation | {pression_bar:.2f} bar |\n"
                    synthese_site += f"| Type de réseau | {type_reseau} |\n"
                    synthese_site += f"\nCes valeurs placent le site dans la gamme {gamme_puissance} avec un débit suffisant.\n\n"
                    synthese_site += "2. Turbines compatibles\n\n"
                    if not turbines.empty:
                        synthese_site += "| Turbine | Diamètre (Ø) | Puissance nominale (kW) | Intervalle de puissance | Type | Source |\n"
                        synthese_site += "|---|---|---|---|---|---|\n"
                        for _, t in turbines.iterrows():
                            synthese_site += f"| {t['type_turbine']} {t['diametre_mm']} mm | {t['diametre_mm']} mm | {t['puissance_min_kw']} – {t['puissance_max_kw']} | {t['puissance_min_kw']}-{t['puissance_max_kw']} | {t['type_turbine']} | [Source]({t['source']}) |\n"
                        synthese_site += "\n3. Explications pédagogiques et recommandation\n\nPour chaque turbine listée ci-dessus, explique brièvement son principe, ses avantages et inconvénients pour ce site, puis propose la meilleure option avec justification. Utilise strictement les titres fournis, sans emoji ni ajout décoratif. Ne répète pas les tableaux. Sois synthétique et pédagogique."
                    else:
                        synthese_site += "Aucune turbine compatible n'a été trouvée pour ce site."
                    synthese_site += (
                        "\n\nFORMAT DE REPONSE OBLIGATOIRE:\n"
                        "- Commencer par le titre exact: 1. Rappel des paramètres du site\n"
                        "- Puis: 2. Turbines compatibles\n"
                        "- Puis: 3. Explications pédagogiques et recommandation\n"
                        "- Ne pas déplacer ni omettre ces titres\n"
                        "- Ne pas ajouter d'autres sections\n"
                        "- Ne pas commencer par le principe des turbines\n"
                    )
                    render_site_ai_generation(
                        synthese_site,
                        allow_call=not turbines.empty,
                        cache_key=f"site_{site_key}_selection",
                        title="Synthese de selection",
                        max_tokens=600,
                    )
                    st.subheader("Turbines compatibles (tableau)")
                    if turbines.empty:
                        st.info("Aucune turbine compatible")
                    else:
                        display_cols = [
                            'type_turbine', 'diametre_mm', 'pression_min_bar', 'pression_max_bar',
                            'debit_min_m3h', 'debit_max_m3h', 'puissance_min_kw', 'puissance_max_kw',
                            'rendement_typique', 'prix_estime_eur', 'description', 'source'
                        ]
                        st.dataframe(turbines[display_cols].reset_index(drop=True))
                elif st.session_state[site_section_key] == 1:
                    st.subheader("Estimation CAPEX/OPEX")
                    st.markdown("---")

                    if True:
                        with st.expander("Comment les CAPEX/OPEX sont estimés ?", expanded=False):
                            st.markdown(
                                """
                                **Structure du CAPEX**
                                - **CAPEX fixe (projet)** : etudes, cadrage, ingenierie, demarches, coordination.
                                - **CAPEX de base** : equipements hydrauliques + electriques (inclut la turbine).
                                - **Integration hydraulique** : complexite d'installation sur site.
                                - **Raccordement electrique** : distance au point de connexion et complexite reseau.

                                **1. CAPEX fixe (indépendant des sites)**
                                Le CAPEX fixe correspond aux coûts mutualisés du projet, indépendants des caractéristiques individuelles des sites.
                                Il regroupe les étapes amont nécessaires à la conception et au cadrage global du système.

                                Composition du CAPEX fixe :
                                - études de faisabilité et analyse technico-économique
                                - modélisation hydraulique globale et définition de la méthodologie
                                - ingénierie de conception et dimensionnement initial
                                - démarches administratives et réglementaires
                                - coordination et gestion de projet

                                Estimation du CAPEX fixe :
                                C_fixe = C_etudes + C_administratif
                                avec :
                                - C_etudes ≈ 2 000 - 5 000 €
                                - C_administratif ≈ 800 - 2 500 €
                                soit un ordre de grandeur global :
                                CAPEX fixe total : 2 800 à 7 500 €

                                **2. CAPEX variable (dépendant du site)**
                                Le CAPEX variable regroupe l’ensemble des coûts directement liés à l’installation sur chaque site.

                                2.1 Coût des équipements hydrauliques et électromécaniques
                                Le coût de base correspond à la chaîne de conversion énergétique :
                                C_base = C_turbine + C_equipement
                                Ce coût inclut :
                                - la turbine adaptée au site
                                - la génératrice
                                - l’armoire électrique
                                - les capteurs et dispositifs de contrôle

                                2.2 Facteur d’intégration hydraulique
                                Un facteur correctif est appliqué afin de représenter la complexité d’intégration dans l’ouvrage existant :
                                - installation simple (≤ 50 m) : F_int = 1.0
                                - installation intermédiaire (50–150 m) : F_int = 1.2
                                - installation complexe (> 150 m) : F_int = 1.5 à 2.0
                                Le coût corrigé devient :
                                C_int = C_base ⋅ F_int

                                2.3 Coût de raccordement électrique
                                Le coût de raccordement dépend de la distance au point de connexion et de la complexité du réseau électrique :
                                - raccordement simple : 0 à 5 000 €
                                - raccordement complexe : 5 000 à 20 000 €
                                Ce coût est ajouté au coût d’intégration hydraulique.

                                **3. CAPEX total**
                                Le coût total d’investissement pour chaque site est défini par :
                                C_total = C_fixe + C_int + C_elec
                                où :
                                - C_fixe représente les coûts mutualisés du projet
                                - C_int correspond au coût des équipements et de leur intégration hydraulique
                                - C_elec correspond au raccordement électrique

                                **Parametres utilises**
                                - **Distance a l'installation** : choisit le niveau d'integration.
                                - **Type d'installation electrique + distance poste** : choisit le niveau de raccordement.
                                - **Prix turbine** : ajoute au CAPEX de base.

                                **OPEX (ordre de grandeur)**
                                - **Micro-inline / pico-inline** : 1.5% a 3% de Cequip (≈ 200 a 600 EUR/an).
                                - **PAT (Pump As Turbine)** : 2% a 4% de Cequip (≈ 300 a 900 EUR/an).
                                - **Micro turbine Francis** : 3% a 6% de Cequip (≈ 800 a 2 000 EUR/an).
                                - **Micro turbine Pelton** : 3% a 7% de Cequip (≈ 1 000 a 2 500 EUR/an).

                                **Cout de la maintenance**
                                - **Maintenance preventive** : inspection turbine/generatrice, vannes/clapets/filtres, capteurs, nettoyage.
                                  Ordre de grandeur : 2% a 4% du CAPEX equipements / an.
                                - **Maintenance corrective** : remplacement pieces mecaniques, intervention generatrice/electronique, fuites.
                                  Ordre de grandeur : 1% a 3% du CAPEX equipements / an.
                                - **Wear & tear** : joints, roulements, capteurs pression, elements hydrauliques.
                                  Ordre de grandeur : 1% a 2% du CAPEX equipements / an.
                                - **Synthese maintenance** : Omaintenance = (0.04 a 0.09) ⋅ Cequip.

                                **Couts d'exploitation**
                                - **Supervision + telegestion** : monitoring et transmission des donnees.
                                  Ordre de grandeur : 50 a 300 EUR/an/site.
                                - **Assurance** : equipements + responsabilite civile + risques techniques.
                                  Ordre de grandeur : 0.3% a 1% du CAPEX total (≈ 80 a 400 EUR/an).
                                - **Consommations auxiliaires** : capteurs, automate, telecom, controle.
                                  Ordre de grandeur : 20 a 150 EUR/an.
                                """,
                                unsafe_allow_html=False,
                            )
                            st.markdown("#### Tableau OPEX")
                            opex_table = pd.DataFrame(
                                [
                                    {
                                        "Type de turbine": "Micro-inline / Pico-inline",
                                        "OPEX (% CAPEX equipement)": "1.5 - 3 %",
                                        "Ordre de grandeur": "200 - 600 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "PAT",
                                        "OPEX (% CAPEX equipement)": "2 - 4 %",
                                        "Ordre de grandeur": "300 - 900 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "Francis micro",
                                        "OPEX (% CAPEX equipement)": "3 - 6 %",
                                        "Ordre de grandeur": "800 - 2 000 EUR/an",
                                    },
                                    {
                                        "Type de turbine": "Pelton micro",
                                        "OPEX (% CAPEX equipement)": "3 - 7 %",
                                        "Ordre de grandeur": "1 000 - 2 500 EUR/an",
                                    },
                                ]
                            )
                            st.table(opex_table)
                        import modules.capex as capex_module
                        distance_install_m = row.get('distance_install_m')
                        distance_grid_m = row.get('distance_grid_m')
                        electrical_install_type = row.get('electrical_install_type')
                        debit_key = f"debit_m3h_{site_key}"
                        pression_key = f"pression_amont_{site_key}"
                        rendement_key = f"rendement_{site_key}"
                        selectbox_key = f"selectbox_productible_{site_key}"
                        tarif_oa_key = f"tarif_oa_{site_key}"
                        prix_evite_key = f"prix_evite_{site_key}"
                        if debit_key not in st.session_state:
                            st.session_state[debit_key] = float(row.get('estimated_flow', 0) or 0)
                        if pression_key not in st.session_state:
                            st.session_state[pression_key] = float(row.get('delta_p', 0) or 0)
                        if selectbox_key not in st.session_state:
                            st.session_state[selectbox_key] = 0
                        if tarif_oa_key not in st.session_state:
                            st.session_state[tarif_oa_key] = 0.12
                        if prix_evite_key not in st.session_state:
                            st.session_state[prix_evite_key] = 0.18
                        if rendement_key not in st.session_state:
                            default_rendement = 65
                            if not turbines.empty:
                                default_rendement = int(float(turbines.iloc[0]['rendement_typique']) * 100)
                            st.session_state[rendement_key] = default_rendement
                        debit_m3h = float(st.session_state[debit_key])
                        pression_amont = float(st.session_state[pression_key])
                        rendement = float(st.session_state[rendement_key])
                        selected_idx = int(st.session_state.get(selectbox_key, 0)) if not turbines.empty else 0
                        selected_row = turbines.iloc[selected_idx] if not turbines.empty else {}
                        metric_cols = st.columns(3, gap="medium")
                        metric_cols[0].metric(
                            "Distance a l'installation (m)",
                            f"{distance_install_m:.0f}" if pd.notna(distance_install_m) else "-",
                        )
                        metric_cols[1].metric(
                            "Type d'installation electrique",
                            str(electrical_install_type) if pd.notna(electrical_install_type) else "-",
                        )
                        metric_cols[2].metric(
                            "Distance au poste electrique (m)",
                            f"{distance_grid_m:.0f}" if pd.notna(distance_grid_m) else "-",
                        )
                        if turbines.empty:
                            st.info("Aucune turbine compatible pour estimer le CAPEX.")
                        else:
                            capex_flow_ls = debit_m3h * 1000.0 / 3600.0
                            integration_default = "simple"
                            if pd.notna(distance_install_m):
                                if distance_install_m > 150:
                                    integration_default = "complexe"
                                elif distance_install_m > 50:
                                    integration_default = "moyen"
                            electrical_default = "simple"
                            electrical_type_lower = str(electrical_install_type or "").lower()
                            if "poste" in electrical_type_lower or "armoire" in electrical_type_lower:
                                electrical_default = "complexe"
                            if pd.notna(distance_grid_m) and distance_grid_m > 500:
                                electrical_default = "complexe"
                            capex_integration_level = st.selectbox(
                                "Niveau d'integration",
                                options=["simple", "moyen", "complexe"],
                                index=["simple", "moyen", "complexe"].index(integration_default),
                                key=f"capex_integration_{site_key}",
                            )
                            capex_electrical_level = st.selectbox(
                                "Raccordement electrique",
                                options=["simple", "complexe"],
                                index=["simple", "complexe"].index(electrical_default),
                                key=f"capex_elec_{site_key}",
                            )
                            st.markdown("#### Estimation CAPEX par turbine (top 2)")
                            st.caption("CAPEX HT calcule a partir des parametres du site et des deux turbines retenues.")
                            capex_rows = []
                            top_turbines = turbines.head(2)
                            for _, turbine_row in top_turbines.iterrows():
                                turbine_eff = turbine_row.get("rendement_typique")
                                if turbine_eff is None or pd.isna(turbine_eff):
                                    turbine_eff = float(rendement) / 100.0
                                turbine_cost = turbine_row.get("prix_estime_eur")
                                if turbine_cost is None or pd.isna(turbine_cost):
                                    turbine_cost = 0.0
                                capex_calc_turbine = capex_module.compute_capex(
                                    flow_ls=capex_flow_ls,
                                    delta_p_bar=pression_amont,
                                    integration_level=capex_integration_level,
                                    electrical_level=capex_electrical_level,
                                    efficiency=float(turbine_eff),
                                    turbine_cost_eur=float(turbine_cost),
                                )
                                capex_rows.append({
                                    "site_name": row.get("site_name"),
                                    "turbine_type": turbine_row.get("type_turbine"),
                                    "turbine_diameter_mm": turbine_row.get("diametre_mm"),
                                    "rendement_typique": float(turbine_eff),
                                    "turbine_cost_eur": float(turbine_cost),
                                    "debit_m3h": debit_m3h,
                                    "pression_bar": pression_amont,
                                    "distance_install_m": distance_install_m,
                                    "distance_grid_m": distance_grid_m,
                                    "electrical_install_type": electrical_install_type,
                                    "integration_level": capex_integration_level,
                                    "electrical_level": capex_electrical_level,
                                    "power_kw": capex_calc_turbine.get("power_kw"),
                                    "capex_base": capex_calc_turbine.get("capex_base"),
                                    "capex_fixe": capex_calc_turbine.get("capex_fixe"),
                                    "capex_fixe_min": capex_calc_turbine.get("capex_fixe_min"),
                                    "capex_fixe_nominal": capex_calc_turbine.get("capex_fixe_nominal"),
                                    "capex_fixe_max": capex_calc_turbine.get("capex_fixe_max"),
                                    "capex_integre": capex_calc_turbine.get("capex_integre"),
                                    "capex_elec": capex_calc_turbine.get("capex_elec"),
                                    "capex_total_min": capex_calc_turbine.get("capex_total_min"),
                                    "capex_total_nominal": capex_calc_turbine.get("capex_total_nominal"),
                                    "capex_total_max": capex_calc_turbine.get("capex_total_max"),
                                    "capex_fixe_eur": capex_calc_turbine.get("capex_fixe_eur"),
                                    "capex_base_eur": capex_calc_turbine.get("capex_base_eur"),
                                    "capex_integre_nominal_eur": capex_calc_turbine.get("capex_integre_nominal_eur"),
                                    "capex_elec_nominal_eur": capex_calc_turbine.get("electrical_cost_nominal_eur"),
                                    "capex_total_min_eur": capex_calc_turbine.get("capex_total_min_eur"),
                                    "capex_total_nominal_eur": capex_calc_turbine.get("capex_total_nominal_eur"),
                                    "capex_total_max_eur": capex_calc_turbine.get("capex_total_max_eur"),
                                    "capex_min_eur": capex_calc_turbine.get("capex_min_eur"),
                                    "capex_nominal_eur": capex_calc_turbine.get("capex_nominal_eur"),
                                    "capex_max_eur": capex_calc_turbine.get("capex_max_eur"),
                                })
                            capex_turbines_df = pd.DataFrame(capex_rows)
                            if not capex_turbines_df.empty:
                                capex_turbines_df = capex_turbines_df.copy()
                                capex_turbines_df["capex_fixe_interval"] = (
                                    capex_turbines_df["capex_fixe_min"].round(0).astype(int).astype(str)
                                    + " - "
                                    + capex_turbines_df["capex_fixe_max"].round(0).astype(int).astype(str)
                                )
                                capex_turbines_df["capex_total_interval"] = (
                                    capex_turbines_df["capex_total_min"].round(0).astype(int).astype(str)
                                    + " - "
                                    + capex_turbines_df["capex_total_max"].round(0).astype(int).astype(str)
                                )
                                st.dataframe(
                                    capex_turbines_df[[
                                        "turbine_type",
                                        "turbine_diameter_mm",
                                        "rendement_typique",
                                        "turbine_cost_eur",
                                        "power_kw",
                                        "capex_fixe_interval",
                                        "capex_base",
                                        "capex_integre",
                                        "capex_elec",
                                        "capex_total_nominal",
                                        "capex_total_interval",
                                    ]],
                                    use_container_width=True,
                                )
                                export_key = f"export_capex_{site_key}"
                                if st.button("Exporter CAPEX turbines (CSV)", key=export_key):
                                    output_dir = os.path.join(ROOT, "outputs")
                                    os.makedirs(output_dir, exist_ok=True)
                                    raw_name = str(row.get("site_name", "site")).strip() or "site"
                                    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name)
                                    output_path = os.path.join(
                                        output_dir,
                                        f"capex_turbines_{safe_name}_{row.name}.csv",
                                    )
                                    capex_turbines_df.to_csv(output_path, index=False)
                                    st.success(f"Fichier exporte : {output_path}")
                            capex_mode = st.radio(
                                "Mode CAPEX",
                                ["Calcule", "Saisie manuelle"],
                                horizontal=True,
                                key=f"capex_mode_{site_key}",
                            )
                            capex_row_value = selected_row.get('prix_estime_eur', 30000)
                            if capex_row_value is None or pd.isna(capex_row_value):
                                capex_row_value = 30000
                            capex_calc = capex_module.compute_capex(
                                flow_ls=capex_flow_ls,
                                delta_p_bar=pression_amont,
                                integration_level=capex_integration_level,
                                electrical_level=capex_electrical_level,
                                efficiency=float(rendement) / 100.0,
                                turbine_cost_eur=float(capex_row_value),
                            )
                            st.session_state[f"capex_calc_{site_key}_total_min"] = float(capex_calc.get("capex_total_min_eur", capex_row_value))
                            st.session_state[f"capex_calc_{site_key}_total_nominal"] = float(capex_calc.get("capex_total_nominal_eur", capex_row_value))
                            st.session_state[f"capex_calc_{site_key}_total_max"] = float(capex_calc.get("capex_total_max_eur", capex_row_value))
                            capex_default = float(capex_row_value)
                            if capex_mode == "Calcule":
                                capex_default = float(capex_calc.get("capex_total_nominal_eur", capex_default))
                            capex = st.number_input(
                                "CAPEX estime (EUR)",
                                value=capex_default,
                                min_value=0.0,
                                step=1000.0,
                                key=f"capex_{site_key}",
                            )
                            st.caption(
                                "CAPEX calcule : %.0f EUR (%.0f - %.0f)" % (
                                    capex_calc.get("capex_total_nominal_eur", 0.0),
                                    capex_calc.get("capex_total_min_eur", 0.0),
                                    capex_calc.get("capex_total_max_eur", 0.0),
                                )
                            )
                            opex_default = capex * 0.03
                            opex = st.number_input(
                                "OPEX estime (EUR/an)",
                                value=opex_default,
                                min_value=0.0,
                                step=100.0,
                                key=f"opex_{site_key}",
                            )
                            st.markdown("#### Subventions et aides")
                            st.caption("Sources possibles : Agence de l'eau, Region, Banque des Territoires")
                            subsidy_rate = st.number_input(
                                "% subvention / CAPEX",
                                value=0.0,
                                min_value=0.0,
                                max_value=100.0,
                                step=1.0,
                                key=f"subvention_{site_key}",
                            )
                            st.markdown("#### Parametres de financement")
                            discount_rate = st.number_input(
                                "Taux d'actualisation (%)",
                                value=5.0,
                                min_value=0.0,
                                max_value=50.0,
                                step=0.5,
                                key=f"discount_{site_key}",
                            )
                            project_life = st.number_input(
                                "Duree de vie projet (ans)",
                                value=20,
                                min_value=1,
                                max_value=60,
                                step=1,
                                key=f"life_{site_key}",
                            )
                            st.session_state[f"capex_report_data_{site_key}"] = {
                                "distance_install_m": distance_install_m,
                                "distance_grid_m": distance_grid_m,
                                "electrical_install_type": electrical_install_type,
                                "capex_integration_level": capex_integration_level,
                                "capex_electrical_level": capex_electrical_level,
                                "capex_rows": capex_rows,
                                "capex_table": capex_turbines_df.to_dict(orient="records") if not capex_turbines_df.empty else [],
                                "capex_columns": list(capex_turbines_df.columns) if not capex_turbines_df.empty else [],
                                "opex_table_display": opex_table.to_dict(orient="records"),
                                "capex_calc": capex_calc,
                                "capex_mode": capex_mode,
                                "capex_default": capex_default,
                                "capex": float(capex),
                                "opex": float(opex),
                                "subsidy_rate": float(subsidy_rate),
                                "discount_rate": float(discount_rate),
                                "project_life": int(project_life),
                            }
                elif st.session_state[site_section_key] == 2:
                    st.subheader("Tarif OA / Prix évité")
                    st.caption("Choisissez le tarif applicable pour l’injection réseau et le prix évité pour l’autoconsommation.")
                    pression_amont = float(st.session_state.get(pression_key, float(row.get('delta_p', 0) or 0)))
                    head_m = pression_amont * 10.2
                    chute_type = "haute chute" if pression_amont > 3 or head_m > 30 else "basse chute"
                    tarif_recommande = 0.12 if chute_type == "haute chute" else 0.132
                    st.markdown(
                        f"""
                        **Tarif applicable**
                        - Haute chute (> 3 bar / > 30 m) : 120 €/MWh = 0,12 €/kWh
                        - Basse chute (< 30 m) : 132 €/MWh = 0,132 €/kWh

                        Pour ce site, la chute estimée est **{chute_type}** ({head_m:.1f} m) et le tarif recommandé est **{tarif_recommande:.3f} €/kWh**.
                        """
                    )
                    tarif_oa = st.number_input(
                        "Tarif OA applicable (EUR/kWh)",
                        value=float(st.session_state.get(tarif_oa_key, tarif_recommande)),
                        min_value=0.0,
                        step=0.001,
                        key=tarif_oa_key,
                    )
                    prix_evite = st.number_input(
                        "Prix d'électricité économisé pour autoconsommation (EUR/kWh)",
                        value=float(st.session_state.get(prix_evite_key, 0.18)),
                        min_value=0.0,
                        step=0.01,
                        key=prix_evite_key,
                    )
                    prix_elec_economise = prix_evite
                    st.markdown("#### Référence réglementaire")
                    st.markdown(
                        "- Installations hydrauliques neuves (<500 kW) : tarifs de référence définis par arrêté.\n"
                        "- 120 €/MWh pour haute chute (> 3 bar / > 30 m).\n"
                        "- 132 €/MWh pour basse chute (< 30 m)."
                    )
                    oa_report_data = {
                        "tarif_oa": float(tarif_oa),
                        "prix_evite": float(prix_evite),
                        "head_m": float(head_m),
                        "chute_type": chute_type,
                        "tarif_recommande": float(tarif_recommande),
                        "reference_text": (
                            "- Installations hydrauliques neuves (<500 kW) : tarifs de référence définis par arrêté.\n"
                            "- 120 €/MWh pour haute chute (> 3 bar / > 30 m).\n"
                            "- 132 €/MWh pour basse chute (< 30 m)."
                        ),
                        "applicable_text": (
                            f"Pour ce site, la chute estimée est **{chute_type}** ({head_m:.1f} m) et le tarif recommandé est **{tarif_recommande:.3f} €/kWh**."
                        ),
                    }
                    st.session_state[f"oa_report_data_{site_key}"] = oa_report_data
                elif st.session_state[site_section_key] == 3:
                    st.subheader("Estimations")
                    st.caption("Le productible et la rentabilite utilisent le CAPEX defini dans la fenetre precedente.")
                    if turbines.empty:
                        st.info("Aucune turbine compatible pour estimer le productible.")
                    else:
                        import numpy as np
                        st.markdown(
                            """
                            <style>
                            .productible-card {
                                background: rgba(10, 25, 47, 0.72);
                                backdrop-filter: blur(18px);
                                border: 1px solid rgba(14, 165, 233, 0.25);
                                border-radius: 22px;
                                padding: 1rem 1.3rem;
                                box-shadow: 0 20px 50px rgba(14, 165, 233, 0.12);
                            }
                            .productible-kpi {
                                background: rgba(15, 23, 42, 0.94);
                                border: 1px solid rgba(56, 189, 248, 0.18);
                                border-radius: 18px;
                                padding: 0.85rem 1rem;
                                box-shadow: inset 0 0 0 1px rgba(14, 165, 233, 0.08);
                                min-height: 100px;
                                color: #ffffff;
                            }
                            .productible-kpi,
                            .productible-kpi span,
                            .productible-kpi div,
                            .productible-kpi p {
                                color: #ffffff;
                            }
                            .productible-title {
                                font-weight: 700;
                                letter-spacing: 0.04em;
                                color: #e0f2fe;
                            }
                            .productible-pill {
                                display: inline-flex;
                                align-items: center;
                                justify-content: center;
                                background: linear-gradient(135deg, rgba(56, 189, 248, 0.95), rgba(14, 165, 233, 0.95));
                                color: #ffffff;
                                font-weight: 700;
                                padding: 0.35rem 0.85rem;
                                border-radius: 999px;
                                font-size: 0.78rem;
                                box-shadow: 0 10px 30px rgba(14, 165, 233, 0.22);
                            }
                            .productible-card p,
                            .productible-card div {
                                color: #dbeafe;
                            }
                            </style>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            """
                            <div class="productible-card">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <div class="productible-title">Tableau de bord productible</div>
                                    <span class="productible-pill">Simulation interactive</span>
                                </div>
                                <div style="margin-top:0.4rem; color:#dbeafe;">
                                    Ajustez les parametres hydrauliques et economiques pour estimer la production et la valeur annuelle.
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if turbines.empty:
                            st.warning("Aucune turbine compatible pour ce site. La simulation est indisponible.")
                            continue
                        selectbox_key = f"selectbox_productible_{site_key}"
                        if selectbox_key not in st.session_state:
                            st.session_state[selectbox_key] = 0
                        if f"debit_m3h_{row.name}" not in st.session_state:
                            st.session_state[f"debit_m3h_{row.name}"] = float(row['estimated_flow'])
                        if f"pression_amont_{row.name}" not in st.session_state:
                            st.session_state[f"pression_amont_{row.name}"] = float(row['delta_p'])
                        if turbines.empty:
                            st.warning("Aucune turbine compatible pour ce site. La simulation est indisponible.")
                            continue
                        turbine_options = [
                            f"{t['type_turbine']} Ø{t['diametre_mm']}mm ({t['puissance_min_kw']}-{t['puissance_max_kw']}kW)"
                            for _, t in turbines.iterrows()
                        ]
                        selected_idx = int(st.session_state[selectbox_key])
                        selected_idx = max(0, min(selected_idx, len(turbines) - 1))
                        selected_row = turbines.iloc[selected_idx]
                        if f"debit_m3h_{row.name}" not in st.session_state:
                            st.session_state[f"debit_m3h_{row.name}"] = float(row.get('estimated_flow', 0) or 0)
                        if f"pression_amont_{row.name}" not in st.session_state:
                            st.session_state[f"pression_amont_{row.name}"] = float(row.get('delta_p', 0) or 0)
                        if f"rendement_{row.name}" not in st.session_state:
                            st.session_state[f"rendement_{row.name}"] = int(selected_row['rendement_typique'] * 100)
                        if f"heures_fonctionnement_{row.name}" not in st.session_state:
                            st.session_state[f"heures_fonctionnement_{row.name}"] = 6500
                        if f"availability_{row.name}" not in st.session_state:
                            st.session_state[f"availability_{row.name}"] = 93
                        if f"mode_{row.name}" not in st.session_state:
                            st.session_state[f"mode_{row.name}"] = "Autoconsommation"
                        if f"exploitation_{row.name}" not in st.session_state:
                            st.session_state[f"exploitation_{row.name}"] = "Regie (SIELL)"
                        if f"conso_site_{row.name}" not in st.session_state:
                            st.session_state[f"conso_site_{row.name}"] = 10000
                        debit_m3h = float(st.session_state[f"debit_m3h_{row.name}"])
                        pression_amont = float(st.session_state[f"pression_amont_{row.name}"])
                        rendement = int(st.session_state[f"rendement_{row.name}"])
                        heures_fonctionnement = int(st.session_state[f"heures_fonctionnement_{row.name}"])
                        availability = int(st.session_state[f"availability_{row.name}"])
                        mode = st.session_state[f"mode_{row.name}"]
                        exploitation = st.session_state[f"exploitation_{row.name}"]
                        conso_site = st.session_state.get(f"conso_site_{row.name}", 10000)
                        capex_key = f"capex_{site_key}"
                        opex_key = f"opex_{site_key}"
                        subsidy_key = f"subvention_{site_key}"
                        discount_key = f"discount_{site_key}"
                        life_key = f"life_{site_key}"
                        capex = st.session_state.get(capex_key)
                        if capex is None:
                            capex_value = selected_row.get('prix_estime_eur', 30000)
                            if capex_value is None or pd.isna(capex_value):
                                capex_value = 30000
                            capex = float(capex_value)
                            st.session_state[capex_key] = capex
                        else:
                            capex = float(capex)
                        def opex_percent_for_turbine(turbine_type):
                            label = str(turbine_type or "").lower()
                            if "inline" in label or "pico" in label:
                                return 0.0225
                            if "pat" in label:
                                return 0.03
                            if "francis" in label:
                                return 0.045
                            if "pelton" in label:
                                return 0.05
                            return 0.03

                        if opex_key not in st.session_state:
                            turbine_cost = selected_row.get("prix_estime_eur")
                            if turbine_cost is None or pd.isna(turbine_cost):
                                turbine_cost = 0.0
                            capex_equip = 12000.0 + float(turbine_cost)
                            opex_percent = opex_percent_for_turbine(selected_row.get("type_turbine"))
                            st.session_state[opex_key] = capex_equip * opex_percent
                        opex = float(st.session_state.get(opex_key, capex * 0.03))
                        if subsidy_key not in st.session_state:
                            st.session_state[subsidy_key] = 0.0
                        if discount_key not in st.session_state:
                            st.session_state[discount_key] = 5.0
                        if life_key not in st.session_state:
                            st.session_state[life_key] = 20
                        capex = float(st.session_state[capex_key])
                        opex = float(st.session_state[opex_key])
                        subsidy_rate = float(st.session_state[subsidy_key])
                        discount_rate = float(st.session_state[discount_key])
                        project_life = int(st.session_state[life_key])
                        def render_kpi_card(title, metrics):
                            items_html = "".join(
                                (
                                    "<div>"
                                    "<div style=\"font-size:0.75rem;color:#cbd5e1;\">"
                                    f"{label}"
                                    "</div>"
                                    "<div style=\"font-size:1.1rem;font-weight:700;color:#ffffff;\">"
                                    f"{value}"
                                    "</div>"
                                    "</div>"
                                )
                                for label, value in metrics
                            )
                            return (
                                "<div class=\"productible-kpi\">"
                                f"<div style=\"font-weight:700;color:#ffffff;margin-bottom:0.5rem;\">{title}</div>"
                                "<div style=\"display:grid;grid-template-columns:repeat(2, minmax(0,1fr));gap:0.6rem;\">"
                                f"{items_html}"
                                "</div>"
                                "</div>"
                            )

                        def render_scenario_card(title, metrics):
                            items_html = "".join(
                                (
                                    "<div style=\"display:flex;justify-content:space-between;align-items:center;padding:0.25rem 0;\">"
                                    f"<span style=\"color:#93c5fd;\">{label}</span>"
                                    f"<span style=\"color:#ffffff;font-weight:700;\">{value}</span>"
                                    "</div>"
                                )
                                for label, value in metrics
                            )
                            return (
                                "<div class=\"productible-kpi\" style=\"padding:1rem;\">"
                                f"<div style=\"font-weight:700;color:#ffffff;margin-bottom:0.75rem;\">{title}</div>"
                                f"{items_html}"
                                "</div>"
                            )

                        selected_turbine = dict(selected_row)
                        selected_turbine['heures_fonctionnement'] = heures_fonctionnement
                        selected_turbine['availability'] = availability / 100.0
                        selected_turbine['rendement_typique'] = rendement / 100
                        st.session_state[f"selected_turbine_{site_key}"] = selected_turbine
                        site_input = row.copy()
                        site_input['estimated_flow'] = debit_m3h
                        site_input['delta_p'] = pression_amont
                        site_input['consommation_kwh'] = conso_site
                        mode_map = {
                            "Autoconsommation": "autoconsommation",
                            "Injection reseau": "injection",
                            "Mixte": "mixte",
                        }
                        site_input['mode'] = mode_map.get(mode, "mixte")
                        capex = float(st.session_state[capex_key])
                        opex = float(st.session_state[opex_key])
                        subsidy_rate = float(st.session_state[subsidy_key])
                        discount_rate = float(st.session_state[discount_key])
                        project_life = int(st.session_state[life_key])
                        tarif_oa = float(st.session_state.get(tarif_oa_key, 0.12))
                        prix_evite = float(st.session_state.get(prix_evite_key, 0.18))
                        prix_elec_economise = prix_evite
                        finance = {
                            'electricity_price': prix_elec_economise,
                            'injection_tariff': tarif_oa,
                            'capex': capex,
                            'opex': opex,
                            'subsidy_rate': subsidy_rate / 100,
                            'discount_rate': discount_rate / 100,
                            'project_life_years': project_life,
                        }
                        result = productible.compute_productible(site_input, selected_turbine)
                        eco = productible.compute_economics(result['energie_kwh'], site_input, finance)
                        economie = eco['economies_eur']
                        revenus = eco['revenus_injection_eur']
                        autoconsommation = eco['autoconsommation_kwh']
                        taux_auto = eco['taux_autoconsommation'] * 100
                        capex_net = eco.get('capex_net_eur')
                        if capex_net is None:
                            capex_net = capex - (capex * (subsidy_rate / 100))
                        payback = eco['temps_retour_ans']
                        van = eco['van_eur']
                        tri = eco['tri']
                        energy_metrics = [
                            ("Puissance estimee (kW)", f"{result['puissance_kw']:.2f}"),
                            ("Energie annuelle (kWh/an)", f"{result['energie_kwh']:.0f}"),
                            ("Taux d'autoconsommation (%)", f"{taux_auto:.1f}"),
                            ("Energie valorisee localement (kWh/an)", f"{autoconsommation:.0f}"),
                            ("Rendement utilise", f"{rendement/100:.2f}"),
                        ]
                        eco_metrics = [
                            ("Economies estimees (EUR/an)", f"{economie:.0f}"),
                            ("Revenus injection (EUR/an)", f"{revenus:.0f}"),
                            ("CAPEX brut (EUR)", f"{capex:.0f}"),
                            ("Subvention (% CAPEX)", f"{subsidy_rate:.1f}"),
                            ("CAPEX net (EUR)", f"{capex_net:.0f}"),
                            ("OPEX estime (EUR/an)", f"{opex:.0f}"),
                            (
                                "Temps de retour (ans)",
                                f"{payback:.1f}" if payback and np.isfinite(payback) else "-",
                            ),
                            ("VAN (EUR)", f"{van:.0f}" if van is not None and np.isfinite(van) else "-"),
                            (
                                "TRI (%)",
                                f"{tri * 100:.1f}" if tri is not None and np.isfinite(tri) else "-",
                            ),
                        ]

                        site_summary_complete = (
                            f"Le site {row.get('site_name', 'Site')} a été simulé avec un débit moyen de {debit_m3h:.1f} m3/h et une pression amont de {pression_amont:.2f} bar. "
                            f"La turbine retenue est {selected_turbine.get('type_turbine', 'non renseignée')} (Ø {selected_turbine.get('diametre_mm', '-') } mm). "
                            f"La simulation retient une puissance de {result['puissance_kw']:.2f} kW, une production annuelle de {result['energie_kwh']:.0f} kWh/an et {economie:.0f} EUR/an d'économies estimées. "
                            f"Le temps de retour calculé est {payback:.1f} ans, avec une VAN de {van:.0f} EUR et un TRI de {tri * 100:.1f} %."
                        )

                        capex_min = st.session_state.get(f"capex_calc_{site_key}_total_min", capex * 0.90)
                        capex_nominal = st.session_state.get(f"capex_calc_{site_key}_total_nominal", capex)
                        capex_max = st.session_state.get(f"capex_calc_{site_key}_total_max", capex * 1.10)
                        opex_ratio = float(opex / capex) if capex > 0 else 0.03
                        opex_min = capex_min * opex_ratio
                        opex_nominal = capex_nominal * opex_ratio
                        opex_max = capex_max * opex_ratio
                        autoconsommation_capex_factor = 1.20

                        def build_scenario(name, hours_value, capex_value, opex_value, scenario_mode):
                            scenario_input = site_input.copy()
                            scenario_input['estimated_flow'] = debit_m3h
                            scenario_input['mode'] = scenario_mode
                            scenario_turbine = dict(selected_turbine)
                            scenario_turbine['heures_fonctionnement'] = max(min(int(hours_value), 8760), 0)
                            scenario_finance = finance.copy()
                            if scenario_mode == "autoconsommation":
                                scenario_finance['electricity_price'] = prix_elec_economise
                                scenario_finance['injection_tariff'] = 0.0
                                scenario_finance['capex'] = max(capex_value * autoconsommation_capex_factor, 0.0)
                            elif scenario_mode == "injection":
                                scenario_finance['electricity_price'] = 0.0
                                scenario_finance['injection_tariff'] = tarif_oa
                                scenario_finance['capex'] = max(capex_value, 0.0)
                            else:
                                scenario_finance['electricity_price'] = prix_elec_economise
                                scenario_finance['injection_tariff'] = tarif_oa
                                scenario_finance['capex'] = max(capex_value, 0.0)
                            scenario_finance['opex'] = max(opex_value, 0.0)
                            scenario_result = productible.compute_productible(scenario_input, scenario_turbine)
                            scenario_eco = productible.compute_economics(scenario_result['energie_kwh'], scenario_input, scenario_finance)
                            return {
                                'name': name,
                                'mode': scenario_mode,
                                'result': scenario_result,
                                'eco': scenario_eco,
                                'hours': scenario_turbine['heures_fonctionnement'],
                                'capex': scenario_finance['capex'],
                                'opex': scenario_finance['opex'],
                            }

                        scenarios_injection = [
                            build_scenario("Pessimiste", 5000, capex_max, opex_max, "injection"),
                            build_scenario("Central", 6500, capex_nominal, opex_nominal, "injection"),
                            build_scenario("Optimiste", 7500, capex_min, opex_min, "injection"),
                        ]
                        scenarios_autoconsommation = [
                            build_scenario("Pessimiste", 5000, capex_max, opex_max, "autoconsommation"),
                            build_scenario("Central", 6500, capex_nominal, opex_nominal, "autoconsommation"),
                            build_scenario("Optimiste", 7500, capex_min, opex_min, "autoconsommation"),
                        ]

                        def format_scenario_metrics(scenario):
                            scenario_result = scenario['result']
                            scenario_eco = scenario['eco']
                            return [
                                ("Heures/an", f"{scenario['hours']} h/an"),
                                ("CAPEX", f"{scenario['capex']:.0f} €"),
                                ("OPEX", f"{scenario['opex']:.0f} €/an"),
                                ("Energie annuelle", f"{scenario_result['energie_kwh']:.0f} kWh/an"),
                                ("Autoconsommation (kWh)", f"{scenario_eco['autoconsommation_kwh']:.0f}"),
                                ("Injection (kWh)", f"{scenario_eco['injection_kwh']:.0f}"),
                                ("Revenu total (EUR/an)", f"{scenario_eco['revenu_total_eur']:.0f}"),
                                (
                                    "Payback (ans)",
                                    (
                                        "∞ ans" if np.isposinf(scenario_eco['temps_retour_ans']) else
                                        "-∞ ans" if np.isneginf(scenario_eco['temps_retour_ans']) else
                                        f"{scenario_eco['temps_retour_ans']:.1f} ans" if scenario_eco['temps_retour_ans'] is not None else "NaN"
                                    )
                                ),
                                (
                                    "TRI (%)",
                                    (
                                        f"{scenario_eco['tri'] * 100:.1f}" if scenario_eco['tri'] is not None and np.isfinite(scenario_eco['tri']) else
                                        ("∞" if scenario_eco['tri'] is not None and np.isposinf(scenario_eco['tri']) else
                                         ("-∞" if scenario_eco['tri'] is not None and np.isneginf(scenario_eco['tri']) else "NaN"))
                                    )
                                ),
                            ]

                        st.subheader("Scénarios - Injection réseau")
                        st.caption("Résultats calculés en mode injection réseau, avec production entièrement vendue au tarif d’injection.")
                        cards = st.columns(3, gap="large")
                        for idx, scenario in enumerate(scenarios_injection):
                            cards[idx].markdown(
                                render_scenario_card(scenario['name'], format_scenario_metrics(scenario)),
                                unsafe_allow_html=True,
                            )

                        st.subheader("Scénarios - Autoconsommation")
                        st.caption("Résultats calculés en mode autoconsommation, avec prix évité de l’onglet OA/autoconsommation et un CAPEX majoré pour refléter le surcoût d’autoconsommation.")
                        cards = st.columns(3, gap="large")
                        for idx, scenario in enumerate(scenarios_autoconsommation):
                            cards[idx].markdown(
                                render_scenario_card(scenario['name'], format_scenario_metrics(scenario)),
                                unsafe_allow_html=True,
                            )

                        st.divider()
                        st.subheader("Modifie toi-même les paramètres")
                        st.caption("Ajustez manuellement les paramètres hydrauliques, d'exploitation et économiques pour recalculer les scénarios.")
                        col1, col2 = st.columns([1.05, 1.25], gap="large")
                        with col1:
                            st.markdown("#### Parametres hydrauliques")
                            debit_m3h = st.number_input(
                                "Debit moyen (m3/h)",
                                min_value=0.0,
                                step=0.1,
                                key=f"debit_m3h_{row.name}",
                            )
                            pression_amont = st.number_input(
                                "Pression amont (bar)",
                                min_value=0.0,
                                step=0.1,
                                key=f"pression_amont_{row.name}",
                            )
                            turbine_options = [
                                f"{t['type_turbine']} Ø{t['diametre_mm']}mm ({t['puissance_min_kw']}-{t['puissance_max_kw']}kW)"
                                for _, t in turbines.iterrows()
                            ]
                            selected_idx = st.selectbox(
                                "Type de turbine",
                                options=list(range(len(turbines))),
                                format_func=lambda i: turbine_options[i],
                                key=selectbox_key,
                            )
                            selected_row = turbines.iloc[selected_idx]
                            rendement = st.slider(
                                "Rendement turbine (%)",
                                min_value=40,
                                max_value=95,
                                key=f"rendement_{row.name}",
                            )
                            st.markdown("#### Parametres d'exploitation")
                            heures_fonctionnement = st.number_input(
                                "Heures de fonctionnement/an",
                                min_value=0,
                                max_value=8760,
                                key=f"heures_fonctionnement_{row.name}",
                            )
                            availability = st.slider(
                                "Disponibilité turbine (%)",
                                min_value=90,
                                max_value=95,
                                step=1,
                                key=f"availability_{row.name}",
                            )
                            mode = st.radio(
                                "Mode",
                                ["Autoconsommation", "Injection reseau", "Mixte"],
                                horizontal=True,
                                key=f"mode_{row.name}",
                            )
                            exploitation = st.radio(
                                "Exploitation",
                                ["Regie (SIELL)", "Developpeur externe"],
                                horizontal=True,
                                key=f"exploitation_{row.name}",
                            )
                        with col2:
                            st.markdown("#### Parametres economiques")
                            conso_site = st.number_input(
                                "Consommation site (kWh/an)",
                                min_value=0,
                                key=f"conso_site_{row.name}",
                            )
                            st.number_input(
                                "CAPEX estime (EUR)",
                                min_value=0.0,
                                step=1000.0,
                                key=f"capex_{site_key}",
                            )
                            st.number_input(
                                "OPEX estime (EUR/an)",
                                min_value=0.0,
                                step=100.0,
                                key=f"opex_{site_key}",
                            )
                            st.markdown("#### Subventions et aides")
                            st.caption("Sources possibles : Agence de l'eau, Region, Banque des Territoires")
                            st.number_input(
                                "% subvention / CAPEX",
                                min_value=0.0,
                                max_value=100.0,
                                step=1.0,
                                key=f"subvention_{site_key}",
                            )
                            st.markdown("#### Parametres de financement")
                            st.number_input(
                                "Taux d'actualisation (%)",
                                min_value=0.0,
                                max_value=50.0,
                                step=0.5,
                                key=f"discount_{site_key}",
                            )
                            st.number_input(
                                "Duree de vie projet (ans)",
                                min_value=1,
                                max_value=60,
                                step=1,
                                key=f"life_{site_key}",
                            )

                        st.divider()
                        st.subheader("Résultats du calcul")
                        st.caption("Le panneau ci-dessous affiche les indicateurs pour les paramètres définis ci-dessus.")

                        st.markdown(
                            render_kpi_card("Resultats energetiques", energy_metrics),
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            render_kpi_card("Resultats economiques", eco_metrics),
                            unsafe_allow_html=True,
                        )
                        compatible_turbines_columns = [
                            'type_turbine', 'diametre_mm', 'pression_min_bar', 'pression_max_bar',
                            'debit_min_m3h', 'debit_max_m3h', 'puissance_min_kw', 'puissance_max_kw',
                            'rendement_typique', 'prix_estime_eur', 'description', 'source'
                        ]
                        compatible_turbines_display = []
                        if not turbines.empty:
                            for _, turbine_row in turbines[compatible_turbines_columns].reset_index(drop=True).iterrows():
                                compatible_turbines_display.append({
                                    "Type de turbine": turbine_row.get('type_turbine'),
                                    "Diamètre (mm)": turbine_row.get('diametre_mm'),
                                    "Pression min (bar)": turbine_row.get('pression_min_bar'),
                                    "Pression max (bar)": turbine_row.get('pression_max_bar'),
                                    "Débit min (m3/h)": turbine_row.get('debit_min_m3h'),
                                    "Débit max (m3/h)": turbine_row.get('debit_max_m3h'),
                                    "Puissance min (kW)": turbine_row.get('puissance_min_kw'),
                                    "Puissance max (kW)": turbine_row.get('puissance_max_kw'),
                                    "Rendement typique": turbine_row.get('rendement_typique'),
                                    "Prix estimé (EUR)": turbine_row.get('prix_estime_eur'),
                                    "Description": turbine_row.get('description'),
                                    "Source": turbine_row.get('source'),
                                })

                        simulation_report_data = {
                            "site_summary_text": site_summary_complete,
                            "compatible_turbines_display": compatible_turbines_display,
                            "compatible_turbines_columns": [
                                "Type de turbine", "Diamètre (mm)", "Pression min (bar)", "Pression max (bar)",
                                "Débit min (m3/h)", "Débit max (m3/h)", "Puissance min (kW)", "Puissance max (kW)",
                                "Rendement typique", "Prix estimé (EUR)", "Description", "Source",
                            ],
                            "energy_metrics": energy_metrics,
                            "eco_metrics": eco_metrics,
                            "manual_parameters": [
                                ("Débit moyen (m3/h)", f"{debit_m3h:.1f}"),
                                ("Pression amont (bar)", f"{pression_amont:.1f}"),
                                ("Type de turbine", f"{selected_row.get('type_turbine', 'N/A')} Ø{selected_row.get('diametre_mm', '-') }mm ({selected_row.get('puissance_min_kw', '-')}-{selected_row.get('puissance_max_kw', '-')}kW)"),
                                ("Rendement turbine (%)", f"{rendement}"),
                                ("Heures de fonctionnement/an", f"{heures_fonctionnement}"),
                                ("Disponibilité turbine (%)", f"{availability}"),
                                ("Mode", mode),
                                ("Exploitation", exploitation),
                                ("Consommation site (kWh/an)", f"{conso_site}"),
                                ("CAPEX estime (EUR)", f"{capex:.0f}"),
                                ("OPEX estime (EUR/an)", f"{opex:.0f}"),
                                ("% subvention / CAPEX", f"{subsidy_rate:.1f}"),
                                ("Taux d'actualisation (%)", f"{discount_rate:.1f}"),
                                ("Duree de vie projet (ans)", f"{project_life}"),
                            ],
                            "scenario_sections": [
                                {
                                    "title": "Scénarios - Injection réseau",
                                    "caption": "Résultats calculés en mode injection réseau, avec production entièrement vendue au tarif d’injection.",
                                    "scenarios": scenarios_injection,
                                },
                                {
                                    "title": "Scénarios - Autoconsommation",
                                    "caption": "Résultats calculés en mode autoconsommation, avec prix évité de l’onglet OA/autoconsommation et un CAPEX majoré pour refléter le surcoût d’autoconsommation.",
                                    "scenarios": scenarios_autoconsommation,
                                },
                            ],
                            "result_summary": {
                                "power_kw": result['puissance_kw'],
                                "energy_kwh": result['energie_kwh'],
                                "economies_eur": economie,
                                "revenus_eur": revenus,
                                "autoconsommation_kwh": autoconsommation,
                                "taux_auto": taux_auto,
                                "capex": capex,
                                "opex": opex,
                                "capex_net": capex_net,
                                "payback": payback,
                                "van": van,
                                "tri": tri,
                            },
                        }
                        productible_context = {
                            "selected_turbine": selected_turbine,
                            "result": result,
                            "eco": eco,
                            "economie": economie,
                            "revenus": revenus,
                            "autoconsommation": autoconsommation,
                            "taux_auto": taux_auto,
                            "mode": mode,
                            "prix_evite": prix_evite,
                            "prix_elec_economise": prix_elec_economise,
                            "prix_elec": tarif_oa if mode == "Injection reseau" else prix_elec_economise,
                            "tarif_oa": tarif_oa,
                            "heures_fonctionnement": heures_fonctionnement,
                            "conso_site": conso_site,
                            "capex": capex,
                            "opex": opex,
                            "subsidy_rate": subsidy_rate,
                            "subvention_eur": capex * (subsidy_rate / 100.0),
                            "capex_net": capex_net,
                            "payback": payback,
                            "van": van,
                            "tri": tri,
                            "discount_rate": discount_rate,
                            "project_life": project_life,
                            "scenarios_injection": scenarios_injection,
                            "scenarios_autoconsommation": scenarios_autoconsommation,
                            "simulation_report_data": simulation_report_data,
                            "selection_report_data": st.session_state.get(f"selection_report_data_{site_key}", {}),
                            "capex_report_data": st.session_state.get(f"capex_report_data_{site_key}", {
                                "distance_install_m": 100.0,
                                "distance_grid_m": 500.0,
                                "electrical_install_type": "Souterrain",
                                "capex_integration_level": "Standard",
                                "capex_electrical_level": "Standard",
                                "capex_table": [],
                                "capex_columns": [],
                                "opex_table_display": [],
                                "capex": capex,
                                "opex": opex,
                                "subsidy_rate": subsidy_rate,
                                "discount_rate": discount_rate,
                                "project_life": project_life,
                            }),
                            "oa_report_data": st.session_state.get(f"oa_report_data_{site_key}", {
                                "tarif_oa": tarif_oa,
                                "prix_evite": prix_evite,
                                "head_m": float(pression_amont * 10.2),
                                "chute_type": "haute chute" if pression_amont > 3 else "basse chute",
                                "tarif_recommande": 0.12 if pression_amont > 3 else 0.132,
                                "reference_text": "Installations hydrauliques neuves (<500 kW) : tarifs de référence définis par arrêté.",
                                "applicable_text": f"Chute estimée: {float(pression_amont * 10.2):.1f} m.",
                            }),
                            "recommendation_report_data": st.session_state.get(f"recommendation_report_data_{site_key}", {}),
                        }
                        st.session_state[f"productible_context_{site_key}"] = productible_context
                        st.session_state[f"site_summary_complete_{site_key}"] = site_summary_complete

                elif st.session_state[site_section_key] == 4:
                    st.subheader("Recommandation")
                    recommendation_report_data = {
                        "general_recommendation_text": "**Recommandation générale :**\nSur la base des caractéristiques du site, privilégiez des turbines adaptées au régime de débit observé et à la hauteur de chute. Les solutions compactes conviennent aux petites chutes, alors que les turbines adaptées aux hautes chutes offrent de meilleures performances pour des différences de charge importantes. Une étude détaillée (onglet 'Estimations') est nécessaire pour valider le choix final et l'analyse économique.",
                        "recommendation_type": None,
                        "recommendation_detail_text": None,
                        "fallback_text": None,
                    }
                    if turbines.empty:
                        recommendation_report_data["fallback_text"] = "Aucune turbine compatible détectée pour ce site."
                        st.info("Aucune turbine compatible détectée pour ce site.")
                    else:
                        # General pedagogical recommendation (no per-turbine listing here)
                        st.markdown(recommendation_report_data["general_recommendation_text"])

                        # If productible calculations were performed, summarize the recommended turbine
                        if productible_context and "selected_turbine" in productible_context:
                            st.divider()
                            st.subheader("Recommandation basée sur les estimations")
                            rec = productible_context.get("selected_turbine", {})
                            rec_result = productible_context.get("result", {})
                            recommendation_report_data["recommendation_type"] = f"{rec.get('type_turbine','N/A')} (Ø {rec.get('diametre_mm','-')} mm)"
                            recommendation_report_data["recommendation_detail_text"] = (
                                f"**Turbine recommandée :** {recommendation_report_data['recommendation_type']}"
                            )
                            st.markdown(recommendation_report_data["recommendation_detail_text"])
                            if rec_result:
                                try:
                                    recommendation_report_data["recommendation_metrics"] = [
                                        ("Puissance estimée", f"{rec_result.get('puissance_kw','-'):.2f} kW"),
                                        ("Énergie annuelle", f"{rec_result.get('energie_kwh','-'):.0f} kWh/an"),
                                    ]
                                    st.markdown(
                                        f"- Puissance estimée : {rec_result.get('puissance_kw','-'):.2f} kW  \n"
                                        f"- Énergie annuelle : {rec_result.get('energie_kwh','-'):.0f} kWh/an"
                                    )
                                except Exception:
                                    pass
                        elif not productible_context and not turbines.empty:
                            # No detailed estimations yet, but we can suggest the top-compatible turbine
                            top = turbines.iloc[0]
                            st.divider()
                            st.subheader("Suggestion basée sur la compatibilité")
                            try:
                                recommendation_report_data["recommendation_type"] = f"{top.get('type_turbine','N/A')} (Ø {top.get('diametre_mm','-')} mm)"
                                recommendation_report_data["recommendation_detail_text"] = f"**Turbine suggérée :** {recommendation_report_data['recommendation_type']}"
                                recommendation_report_data["recommendation_metrics"] = [
                                    ("Plage de puissance", f"{top.get('puissance_min_kw','-')} - {top.get('puissance_max_kw','-')} kW"),
                                    ("Rendement typique", f"{top.get('rendement_typique','-')}"),
                                ]
                                st.markdown(recommendation_report_data["recommendation_detail_text"])
                                st.markdown(
                                    f"- Plage de puissance : {top.get('puissance_min_kw','-')} - {top.get('puissance_max_kw','-')} kW  \n"
                                    f"- Rendement typique : {top.get('rendement_typique','-')}"
                                )
                                st.info("Exécutez l'onglet 'Estimations' pour obtenir des valeurs chiffrées et la recommandation finale.")
                            except Exception:
                                pass
                            
                        else:
                            # No detailed estimations yet
                            recommendation_report_data["fallback_text"] = "Effectuez les estimations (onglet 'Estimations') pour obtenir une recommandation détaillée et générer le rapport PDF."
                            st.info("Effectuez les estimations (onglet 'Estimations') pour obtenir une recommandation détaillée et générer le rapport PDF.")

                        st.session_state[f"recommendation_report_data_{site_key}"] = recommendation_report_data

                        # Rapport de site basé sur toutes les étapes de simulation
                        st.divider()
                        st.subheader("Rapport de site")
                        report_button_key = f"generate_pdf_{site_key}"
                        if st.button("Générer le rapport de site", key=report_button_key):
                            output_dir = os.path.join(ROOT, "outputs")
                            os.makedirs(output_dir, exist_ok=True)
                            raw_name = str(row.get("site_name", "site")).strip() or "site"
                            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name)
                            output_path = os.path.join(output_dir, f"rapport_site_{safe_name}_{row.name}.pdf")
                            try:
                                stored_productible_context = st.session_state.get(f"productible_context_{site_key}", {}) or {}
                                stored_selected_turbine = st.session_state.get(f"selected_turbine_{site_key}", {}) or {}
                                stored_site_summary = st.session_state.get(f"site_summary_complete_{site_key}")
                                if stored_selected_turbine:
                                    stored_productible_context["selected_turbine"] = stored_selected_turbine
                                if stored_site_summary:
                                    simulation_data = dict(stored_productible_context.get("simulation_report_data", {}))
                                    simulation_data["site_summary_text"] = stored_site_summary
                                    stored_productible_context["simulation_report_data"] = simulation_data
                                if not stored_productible_context or "selected_turbine" not in stored_productible_context:
                                    st.warning("Le rapport sera généré à partir des estimations disponibles, mais la recommandation détaillée est incomplète.")
                                if generate_site_simulation_report is not None:
                                    report_kwargs = {
                                        "output_path": output_path,
                                        "site_row": row,
                                        "productible_context": stored_productible_context,
                                        "scenarios_injection": scenarios_injection,
                                        "scenarios_autoconsommation": scenarios_autoconsommation,
                                        "rank": int(row.name) + 1 if hasattr(row, "name") and isinstance(row.name, int) else None,
                                        "total_sites": len(scored_df) if 'scored_df' in locals() else None,
                                        "ai_recommendation": None,
                                        "recommendation_report_data": st.session_state.get(f"recommendation_report_data_{site_key}", {}),
                                    }
                                    try:
                                        signature = inspect.signature(generate_site_simulation_report)
                                        filtered_report_kwargs = {
                                            key: value for key, value in report_kwargs.items() if key in signature.parameters
                                        }
                                    except Exception:
                                        filtered_report_kwargs = report_kwargs
                                    generate_site_simulation_report(**filtered_report_kwargs)
                                else:
                                    kwargs = dict(
                                        output_path=output_path,
                                        site_row=row,
                                        selected_turbine=stored_productible_context.get("selected_turbine", {}),
                                        productible_result=stored_productible_context.get("result", {}),
                                        economie=stored_productible_context.get("economie", 0),
                                        revenus=stored_productible_context.get("revenus", 0),
                                        autoconsommation=stored_productible_context.get("autoconsommation", 0),
                                        taux_auto=stored_productible_context.get("taux_auto", 0),
                                        mode=stored_productible_context.get("mode", "autoconsommation"),
                                        prix_elec=stored_productible_context.get("prix_elec", 0.18),
                                        heures_fonctionnement=stored_productible_context.get("heures_fonctionnement", 6500),
                                        conso_site=stored_productible_context.get("conso_site", 0),
                                        tarif_oa=stored_productible_context.get("tarif_oa"),
                                        prix_evite=stored_productible_context.get("prix_evite"),
                                        turbines_df=turbines,
                                        ai_recommendation=ai_recommendation,
                                        rank=int(row.name) + 1 if hasattr(row, "name") and isinstance(row.name, int) else None,
                                        total_sites=len(scored_df) if 'scored_df' in locals() else None,
                                        lat=row.get("lat_wgs84"),
                                        lon=row.get("lon_wgs84"),
                                        capex=stored_productible_context.get("capex", 0),
                                        opex=stored_productible_context.get("opex", 0),
                                        payback=stored_productible_context.get("payback"),
                                        subsidy_rate=stored_productible_context.get("subsidy_rate", 0),
                                        subvention_eur=stored_productible_context.get("subvention_eur", 0),
                                        capex_net=stored_productible_context.get("capex_net"),
                                        van=stored_productible_context.get("van"),
                                        tri=stored_productible_context.get("tri"),
                                        discount_rate=stored_productible_context.get("discount_rate"),
                                        project_life_years=stored_productible_context.get("project_life"),
                                        recommendation_report_data=st.session_state.get(f"recommendation_report_data_{site_key}", {}),
                                    )
                                    call_generate_site_pdf(**kwargs)
                            except Exception as e:
                                st.error(f"Erreur lors de la génération du rapport de site : {e}")

                            # If file created, show download button
                            if os.path.exists(output_path):
                                st.success(f"Rapport généré : {output_path}")
                                try:
                                    with open(output_path, "rb") as pdf_file:
                                        st.download_button(
                                            "Télécharger le rapport de site",
                                            data=pdf_file,
                                            file_name=os.path.basename(output_path),
                                            mime="application/pdf",
                                        )
                                except Exception as e:
                                    st.error(f"Impossible d'ouvrir le fichier généré : {e}")
                            else:
                                st.info("Le rapport n'a pas été généré. Vérifiez les estimations ou les logs.")

    return candidates.head(top_n)

with tab2:
    if not scored_df.empty:
        scored_df = scored_df.sort_values('score', ascending=False).reset_index(drop=True)
        propose_turbines(scored_df.iloc[0], turbine_db)
    else:
        st.warning("Aucun site disponible pour la simulation.")

with tab_acteurs:
    try:
        st.info("Chargement de l'onglet Acteurs...")
        render_acteurs_dashboard()
    except Exception as exc:
        st.error("Erreur lors du rendu de l'onglet Acteurs.")
        st.exception(exc)

with tab_chatbot:
    st.markdown("<div class='pv-section-title'>Assistant de projet</div>", unsafe_allow_html=True)
    st.caption(
        "Posez une question sur les sites hydro, les hypothèses de calcul ou la lecture des résultats du projet Larzacqua."
    )
    if st.button("Ouvrir le chatbot", key="open-hydro-chatbot", use_container_width=False):
        st.session_state["chatbot_open"] = True
        st.rerun()
