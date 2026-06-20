import os
import json
from textwrap import dedent

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from bridge_links import render_bridge_banner, render_dashboard_switcher


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGO_PATH = os.path.join(ROOT, "assets", "larzacqua_logo.svg")


SITES = [
    {"nom": "STEP Saint-Jean-de-la-Blaquière", "surface": 11160, "secteur": "Sud", "puissance_kwc": None},
    {"nom": "STEP La Vacquerie", "surface": 8426, "secteur": "Nord", "puissance_kwc": 1748},
    {"nom": "STEP Le Caylar", "surface": 8072, "secteur": "Nord", "puissance_kwc": None},
    {"nom": "STEP Mas Lavayre (Le Bosc)", "surface": 7535, "secteur": "Sud", "puissance_kwc": None},
    {"nom": "Réservoir Soubès", "surface": 970, "secteur": "Sud", "puissance_kwc": 200},
    {"nom": "STEP Loiras / Le Bosc", "surface": 4080, "secteur": "Sud", "puissance_kwc": None},
]

SITE_PVSYST = {
    "STEP Le Caylar": {
        "projet": "STEP la Caylar",
        "localisation": "Le Caylar, France",
        "latitude": 43.8667,
        "longitude": 3.3083,
        "altitude_m": 713,
        "meteo": "Meteonorm 9.0, Sat=66%, Synthétique",
        "nb_modules": 3349,
        "puissance_stc_kwp": 1675,
        "strings": "197 strings × 17 modules en série",
        "nb_onduleurs": 13,
        "puissance_onduleurs_kwac": 1300,
        "ratio_dc_ac": 1.29,
        "energie_kwh_an": 2515822,
        "production_specifique": 1502,
        "pr_pct": 89.37,
        "surface_modules_m2": 8071,
        "irr_horiz_kwh_m2_an": 1457,
        "irr_plane_kwh_m2_an": 1681,
        "irr_gain_pct": 15.4,
        "perte_temperature_pct": -5.01,
        "perte_cablage_dc_pct": -1.02,
        "perte_cablage_dc_mohm": 4.5,
        "perte_mismatch_pct": -2.05,
        "perte_qualite_module_pct": 0.75,
        "mensuel_kwh": [113411, 152215, 215154, 241046, 269698, 290958, 305441, 290570, 240062, 171276, 118950, 107041],
    },
    "STEP La Vacquerie": {
        "projet": "Nouveau Projet",
        "localisation": "La Vacquerie-et-Saint-Martin-de-Castries, France",
        "latitude": 43.7965,
        "longitude": 3.4553,
        "altitude_m": 604,
        "meteo": "Meteonorm 9.0, Sat=100%, Synthétique",
        "nb_modules": 3496,
        "puissance_stc_kwp": 1748,
        "strings": "184 strings × 19 modules en série",
        "nb_onduleurs": 14,
        "puissance_onduleurs_kwac": 1400,
        "ratio_dc_ac": 1.25,
        "energie_kwh_an": 2714144,
        "production_specifique": 1553,
        "pr_pct": 89.54,
        "surface_modules_m2": 8426,
        "irr_horiz_kwh_m2_an": 1493,
        "irr_plane_kwh_m2_an": 1734,
        "irr_gain_pct": 16.1,
        "perte_temperature_pct": -5.35,
        "perte_cablage_dc_pct": -1.04,
        "perte_cablage_dc_mohm": 5.3,
        "perte_mismatch_pct": -2.00,
        "perte_qualite_module_pct": 0.75,
        "mensuel_kwh": [135838, 170367, 227145, 256149, 295103, 309578, 326611, 304172, 256673, 186601, 132572, 113334],
    },
    "STEP Loiras / Le Bosc": {
        "projet": "Le Bosc",
        "localisation": "Loiras/Le Bosc, France",
        "latitude": 43.7019,
        "longitude": 3.3997,
        "altitude_m": 130,
        "meteo": "Meteonorm 9.0, Sat=98%, Synthétique",
        "nb_modules": 1692,
        "puissance_stc_kwp": 846,
        "strings": "94 strings × 18 modules en série",
        "nb_onduleurs": 7,
        "puissance_onduleurs_kwac": 700,
        "ratio_dc_ac": 1.21,
        "energie_kwh_an": 1296316,
        "production_specifique": 1532,
        "pr_pct": 89.01,
        "surface_modules_m2": 4078,
        "irr_horiz_kwh_m2_an": 1484,
        "irr_plane_kwh_m2_an": 1722,
        "irr_gain_pct": 16.0,
        "perte_temperature_pct": -6.07,
        "perte_cablage_dc_pct": -1.02,
        "perte_cablage_dc_mohm": 9.9,
        "perte_mismatch_pct": -2.00,
        "perte_qualite_module_pct": 0.75,
        "mensuel_kwh": [62493, 80269, 111086, 121282, 142726, 150461, 156979, 146005, 120213, 87225, 63072, 54503],
    },
    "STEP Mas Lavayre (Le Bosc)": {
        "projet": "STEP Mas Lavayre",
        "localisation": "Mas Lavayre, France",
        "latitude": 43.6887,
        "longitude": 3.3520,
        "altitude_m": 108,
        "meteo": "Meteonorm 9.0, Sat=100%, Synthétique",
        "nb_modules": 2074,
        "puissance_stc_kwp": 1037,
        "strings": "122 strings × 17 modules en série",
        "nb_onduleurs": 8,
        "puissance_onduleurs_kwac": 800,
        "ratio_dc_ac": 1.30,
        "energie_kwh_an": 1577877,
        "production_specifique": 1522,
        "pr_pct": 88.96,
        "surface_modules_m2": 4998,
        "irr_horiz_kwh_m2_an": 1479,
        "irr_plane_kwh_m2_an": 1710,
        "irr_gain_pct": 15.7,
        "perte_temperature_pct": -5.94,
        "perte_cablage_dc_pct": -1.00,
        "perte_cablage_dc_mohm": 7.2,
        "perte_mismatch_pct": -2.05,
        "perte_qualite_module_pct": 0.75,
        "mensuel_kwh": [75708, 97636, 135146, 148528, 174602, 182534, 192304, 177754, 148248, 102839, 75321, 67260],
    },
    "STEP Saint-Jean-de-la-Blaquière": {
        "projet": "STEP saint Jean de la Blaquière",
        "localisation": "Saint-Jean-de-la-Blaquière, France",
        "latitude": 43.7065,
        "longitude": 3.4200,
        "altitude_m": 141,
        "meteo": "Meteonorm 9.0, Sat=95%, Synthétique",
        "nb_modules": 3180,
        "puissance_stc_kwp": 1590,
        "strings": "212 strings × 15 modules en série",
        "nb_onduleurs": 13,
        "puissance_onduleurs_kwac": 1300,
        "ratio_dc_ac": 1.22,
        "energie_kwh_an": 2440451,
        "production_specifique": 1535,
        "pr_pct": 89.06,
        "surface_modules_m2": 7664,
        "irr_horiz_kwh_m2_an": 1487,
        "irr_plane_kwh_m2_an": 1724,
        "irr_gain_pct": 15.9,
        "perte_temperature_pct": -6.10,
        "perte_cablage_dc_pct": -1.03,
        "perte_cablage_dc_mohm": 3.7,
        "perte_mismatch_pct": -2.05,
        "perte_qualite_module_pct": 0.75,
        "mensuel_kwh": [118335, 151755, 208677, 230272, 268832, 281924, 294660, 273612, 227233, 163308, 117004, 104837],
    },
    "Réservoir Soubès": {
        "projet": "soubes",
        "localisation": "Soubès, France",
        "latitude": 43.77,
        "longitude": 3.35,
        "altitude_m": 329,
        "meteo": "Meteonorm 8.2 (2001-2020), Sat=100%, Synthétique",
        "nb_modules": 400,
        "puissance_stc_kwp": 200,
        "strings": "25 strings × 16 modules en série",
        "nb_onduleurs": 1.6,
        "nb_onduleurs_physiques": 2,
        "puissance_onduleurs_kwac": 160,
        "ratio_dc_ac": 1.25,
        "energie_kwh_an": 291610,
        "production_specifique": 1458,
        "pr_pct": 87.05,
        "surface_modules_m2": 964,
        "irr_horiz_kwh_m2_an": 1494,
        "irr_plane_kwh_m2_an": 1675,
        "irr_gain_pct": 12.1,
        "perte_temperature_pct": -5.7,
        "perte_cablage_dc_pct": -1.0,
        "perte_cablage_dc_mohm": 33.0,
        "perte_mismatch_pct": -2.0,
        "perte_qualite_module_pct": 0.8,
        "perte_onduleur_surpuisance_pct": -2.5,
        "mensuel_kwh": [12620, 15950, 25170, 28760, 33060, 34280, 36180, 34080, 26830, 19780, 13220, 11670],
    },
}

MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]

BILAN = {
    "productible_total_mwh": 10836,
    "autoconsommation_siell_mwh": 2420,
    "surplus_acc_mwh": 8416,
    "consommation_siell_mwh": 2420,
    "taux_couverture_pct": 100,
}

ECONOMIE = {
    "capex_construction": 6741200,
    "capex_infra_reseau": 600000,
    "capex_raccordement": 240000,
    "capex_total": 7581200,
    "opex_annuel": 127728,
    "opex_maintenance_pct": 35,
    "opex_renouvellement_pct": 15,
    "opex_fiscalite_pct": 30,
    "opex_turpe_pct": 20,
    "prix_autoconso_eur_mwh": 180,
    "prix_ppa_eur_mwh": 80,
    "revenu_autoconso_an": 435600,
    "revenu_ppa_an": 673280,
    "revenu_total_an": 1108880,
    "revenu_net_an": 981150,
}

MODULE = {
    "nom": "Trina Solar TSM-DEG18MC.20(II)",
    "puissance_wc": 500,
    "technologie": "Bifacial",
    "coef_temp": "-0,34 %/°C",
    "quantite": 14191,
}

ONDULEUR = {
    "nom": "Huawei SUN2000-100KTL-M2",
    "puissance_kva": 100,
    "mppt": 16,
    "rendement": "98,8 %",
    "quantite": 57,
}

MONTAGE_FINANCIER = [
    "Tiers-investisseur finance 100 % du CAPEX (7,58 M€).",
    "Le SIELL met à disposition le foncier via un bail emphytéotique ou une COT.",
    "PPA de 20 ans avec prix fixe de 80 €/MWh pour la CCLL.",
    "Loyer foncier reversé au SIELL comme recette nouvelle.",
    "Rétrocession des installations à terme.",
]

SITE_SHORT_NAMES = {
    "STEP Saint-Jean-de-la-Blaquière": "Saint-Jean-de-la-Blaquière",
    "STEP La Vacquerie": "La Vacquerie",
    "STEP Le Caylar": "Le Caylar",
    "STEP Mas Lavayre (Le Bosc)": "Mas Lavayre",
    "Réservoir Soubès": "Réservoir Soubès",
    "STEP Loiras / Le Bosc": "Loiras / Le Bosc",
}


def format_int(value):
    return f"{int(round(value)):,}".replace(",", " ")


def format_kw(value):
    return f"{float(value):,.0f}".replace(",", " ")


def format_eur(value):
    return f"{float(value):,.0f}".replace(",", " ") + " €"


def format_mwh(value):
    return f"{float(value):,.0f}".replace(",", " ") + " MWh/an"


def build_sites_df():
    df = pd.DataFrame(SITES)
    if "puissance_kwc" in df.columns:
        df["puissance_kwc"] = df.apply(
            lambda row: row["puissance_kwc"]
            if pd.notna(row["puissance_kwc"])
            else get_site_profile(row["nom"]).get("puissance_stc_kwp"),
            axis=1,
        )
    total_surface = df["surface"].sum()
    df["surface_share_pct"] = df["surface"] / total_surface * 100.0
    return df


def get_selected_site(df, selected_name):
    if selected_name == "Tous les sites":
        return None
    row = df.loc[df["nom"] == selected_name]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def get_site_profile(site_name):
    return SITE_PVSYST.get(site_name, {})


def site_metric_pairs(profile):
    return [
        ("Projet", profile.get("projet", "N/A")),
        ("Localisation", profile.get("localisation", "N/A")),
        ("Latitude / Longitude", f"{profile.get('latitude', 'N/A')} / {profile.get('longitude', 'N/A')}"),
        ("Altitude", f"{profile.get('altitude_m', 'N/A')} m"),
        ("Données météo", profile.get("meteo", "N/A")),
        ("Nb. modules", format_int(profile.get("nb_modules", 0)) if profile.get("nb_modules") is not None else "N/A"),
        ("Puissance totale (STC)", f"{format_kw(profile.get('puissance_stc_kwp', 0))} kWp" if profile.get("puissance_stc_kwp") is not None else "N/A"),
        ("Câblage", profile.get("strings", "N/A")),
        ("Nb. onduleurs", str(profile.get("nb_onduleurs", "N/A"))),
        ("Puissance onduleurs", f"{format_kw(profile.get('puissance_onduleurs_kwac', 0))} kWac" if profile.get("puissance_onduleurs_kwac") is not None else "N/A"),
        ("Rapport Pnom (DC:AC)", f"{profile.get('ratio_dc_ac', 'N/A'):.2f}" if profile.get("ratio_dc_ac") is not None else "N/A"),
        ("Énergie produite", f"{format_int(profile.get('energie_kwh_an', 0))} kWh/an" if profile.get("energie_kwh_an") is not None else "N/A"),
        ("Production spécifique", f"{format_int(profile.get('production_specifique', 0))} kWh/kWp/an" if profile.get("production_specifique") is not None else "N/A"),
        ("Performance Ratio (PR)", f"{profile.get('pr_pct', 'N/A'):.2f} %" if profile.get("pr_pct") is not None else "N/A"),
        ("Surface modules", f"{format_int(profile.get('surface_modules_m2', 0))} m²" if profile.get("surface_modules_m2") is not None else "N/A"),
        ("Irradiation horizontale", f"{format_int(profile.get('irr_horiz_kwh_m2_an', 0))} kWh/m²/an" if profile.get("irr_horiz_kwh_m2_an") is not None else "N/A"),
        ("Irradiation plan incliné", f"{format_int(profile.get('irr_plane_kwh_m2_an', 0))} kWh/m²/an (+{profile.get('irr_gain_pct', 0):.1f}%)" if profile.get("irr_plane_kwh_m2_an") is not None else "N/A"),
        ("Perte température", f"{profile.get('perte_temperature_pct', 'N/A'):.2f}%" if profile.get("perte_temperature_pct") is not None else "N/A"),
        ("Perte câblage DC", f"{profile.get('perte_cablage_dc_pct', 'N/A'):.2f}% ({profile.get('perte_cablage_dc_mohm', 'N/A')} mΩ)" if profile.get("perte_cablage_dc_pct") is not None else "N/A"),
        ("Perte mismatch", f"{profile.get('perte_mismatch_pct', 'N/A'):.2f}%" if profile.get("perte_mismatch_pct") is not None else "N/A"),
        ("Perte qualité module", f"{profile.get('perte_qualite_module_pct', 'N/A'):.2f}%" if profile.get("perte_qualite_module_pct") is not None else "N/A"),
    ]


def monthly_profile_series(profile):
    values = profile.get("mensuel_kwh", [])
    return pd.DataFrame({"Mois": MONTHS[:len(values)], "Production kWh": values})


def site_comparison_df():
    rows = []
    for site in SITES:
        profile = get_site_profile(site["nom"])
        rows.append(
            {
                "Site": site["nom"],
                "Puissance (kWp)": profile.get("puissance_stc_kwp"),
                "Modules": profile.get("nb_modules"),
                "Onduleurs (kWac)": profile.get("puissance_onduleurs_kwac"),
                "DC:AC": profile.get("ratio_dc_ac"),
                "Production (MWh/an)": round(profile.get("energie_kwh_an", 0) / 1000, 1) if profile.get("energie_kwh_an") else None,
                "Spécifique (kWh/kWp/an)": profile.get("production_specifique"),
                "PR (%)": profile.get("pr_pct"),
            }
        )
    return pd.DataFrame(rows)


def site_losses_df(profile):
    rows = [
        ("Perte température", profile.get("perte_temperature_pct")),
        ("Perte câblage DC", profile.get("perte_cablage_dc_pct")),
        ("Perte mismatch", profile.get("perte_mismatch_pct")),
        ("Perte qualité module", profile.get("perte_qualite_module_pct")),
    ]
    if profile.get("perte_onduleur_surpuisance_pct") is not None:
        rows.append(("Perte onduleur surpuissance", profile.get("perte_onduleur_surpuisance_pct")))
    return pd.DataFrame(rows, columns=["Type de perte", "Valeur (%)"])


def card_html(title, body, accent="amber"):
    return dedent(
        f"""
        <div class="pv-card pv-accent-{accent}">
            <div class="pv-card-title">{title}</div>
            <div class="pv-card-body">{body}</div>
        </div>
        """
    )


def kpi_html(label, value, detail="", accent="amber"):
    detail_html = f'<div class="pv-kpi-detail">{detail}</div>' if detail else ""
    return dedent(
        f"""
        <div class="pv-kpi pv-accent-{accent}">
            <div class="pv-kpi-label">{label}</div>
            <div class="pv-kpi-value">{value}</div>
            {detail_html}
        </div>
        """
    )


def render_chart_panel(title, subtitle, canvas_id, chart_config, height=320):
    chart_json = json.dumps(chart_config, ensure_ascii=False)
    html = dedent(
        f"""
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
            <style>
                :root {{
                    --color-primary: #F59E0B;
                    --color-secondary: #10B981;
                    --color-bg: #0F172A;
                    --color-card: #1E293B;
                    --color-text: #F1F5F9;
                    --color-muted: #94A3B8;
                }}
                body {{
                    margin: 0;
                    background: transparent;
                    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: var(--color-text);
                }}
                .panel {{
                    background: linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.96) 100%);
                    border: 1px solid rgba(148, 163, 184, 0.16);
                    border-radius: 18px;
                    padding: 1rem 1rem 0.8rem;
                    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
                    height: {height + 40}px;
                }}
                .panel h4 {{
                    margin: 0;
                    font-size: 1rem;
                    letter-spacing: 0.02em;
                }}
                .panel p {{
                    margin: 0.2rem 0 0.8rem;
                    color: var(--color-muted);
                    font-size: 0.88rem;
                }}
                canvas {{
                    width: 100% !important;
                    height: {height}px !important;
                }}
            </style>
        </head>
        <body>
            <div class="panel">
                <h4>{title}</h4>
                <p>{subtitle}</p>
                <canvas id="{canvas_id}"></canvas>
            </div>
            <script>
                const config = {chart_json};
                const canvas = document.getElementById("{canvas_id}");
                if (canvas) {{
                    new Chart(canvas, config);
                }}
            </script>
        </body>
        </html>
        """
    )
    components.html(html, height=height + 70, scrolling=False)


def chart_theme():
    return {
        "responsive": True,
        "maintainAspectRatio": False,
        "plugins": {
            "legend": {
                "labels": {"color": "#F1F5F9", "font": {"size": 12}},
            },
            "tooltip": {
                "enabled": True,
                "backgroundColor": "rgba(15, 23, 42, 0.95)",
                "titleColor": "#F1F5F9",
                "bodyColor": "#E2E8F0",
                "borderColor": "rgba(245, 158, 11, 0.35)",
                "borderWidth": 1,
            },
        },
        "scales": {
            "x": {
                "ticks": {"color": "#CBD5E1"},
                "grid": {"color": "rgba(148, 163, 184, 0.12)"},
            },
            "y": {
                "ticks": {"color": "#CBD5E1"},
                "grid": {"color": "rgba(148, 163, 184, 0.12)"},
            },
        },
    }


def site_cards_html(df, selected_name):
    cards = []
    for site in df.to_dict(orient="records"):
        selected_class = " pv-selected" if site["nom"] == selected_name else ""
        profile = get_site_profile(site["nom"])
        puissance_value = site.get("puissance_kwc")
        puissance = "non communiqué" if pd.isna(puissance_value) else f"{format_kw(puissance_value)} kWc"
        energie = profile.get("energie_kwh_an")
        pr_value = profile.get("pr_pct")
        production_specifique = profile.get("production_specifique")
        cards.append(
            dedent(
                f"""
                <div class="pv-site-card{selected_class}">
                    <div class="pv-site-head">
                        <div>
                            <div class="pv-site-name">{site['nom']}</div>
                            <div class="pv-site-meta">Secteur {site['secteur']} · {format_int(site['surface'])} m²</div>
                        </div>
                        <div class="pv-badge">{site['secteur']}</div>
                    </div>
                    <div class="pv-site-grid">
                        <div><span>Surface</span><strong>{format_int(site['surface'])} m²</strong></div>
                        <div><span>Puissance</span><strong>{puissance}</strong></div>
                        <div><span>Part de surface</span><strong>{site['surface_share_pct']:.1f} %</strong></div>
                        <div><span>Statut</span><strong>{'Sélectionné' if site['nom'] == selected_name else 'Disponible'}</strong></div>
                        <div><span>Énergie annuelle</span><strong>{format_int(energie)} kWh/an</strong></div>
                        <div><span>PR / spécifique</span><strong>{pr_value:.2f} % · {format_int(production_specifique)} kWh/kWp/an</strong></div>
                    </div>
                </div>
                """
            )
        )
    return "<div class='pv-site-grid-wrap'>" + "".join(cards) + "</div>"


def standardized_equipment_html():
    return dedent(
        f"""
        <div class="pv-equipment-grid">
            <div class="pv-equipment-card pv-accent-amber">
                <div class="pv-card-title">Module standardisé</div>
                <div class="pv-equipment-name">{MODULE['nom']}</div>
                <div class="pv-equipment-line">{MODULE['puissance_wc']} Wc · {MODULE['technologie']}</div>
                <div class="pv-equipment-line">Coefficient température : {MODULE['coef_temp']}</div>
                <div class="pv-equipment-line">Quantité : {format_int(MODULE['quantite'])} modules</div>
            </div>
            <div class="pv-equipment-card pv-accent-green">
                <div class="pv-card-title">Onduleur standardisé</div>
                <div class="pv-equipment-name">{ONDULEUR['nom']}</div>
                <div class="pv-equipment-line">{ONDULEUR['puissance_kva']} kVA · {ONDULEUR['mppt']} MPPT</div>
                <div class="pv-equipment-line">Rendement : {ONDULEUR['rendement']}</div>
                <div class="pv-equipment-line">Quantité : {format_int(ONDULEUR['quantite'])} onduleurs</div>
            </div>
        </div>
        """
    )


def selected_site_detail_html(site_name):
    profile = get_site_profile(site_name)
    if not profile:
        return card_html(
            "Fiche détaillée",
            "Aucune fiche PVsyst n’est disponible pour ce site.",
            "amber",
        )

    metric_cards = []
    for label, value in site_metric_pairs(profile):
        metric_cards.append(
            f"<div><div class='pv-kpi-label'>{label}</div><div class='pv-kpi-value' style='font-size:1rem;'>{value}</div></div>"
        )

    return dedent(
        f"""
        <div class="pv-card pv-accent-green">
            <div class="pv-card-title">Fiche technique détaillée</div>
            <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0.75rem;">
                {''.join(metric_cards)}
            </div>
        </div>
        """
    )


def financing_html():
    step_cards = []
    for index, item in enumerate(MONTAGE_FINANCIER, start=1):
        step_cards.append(
            dedent(
                f"""
                <div class="pv-finance-step">
                    <div class="pv-step-index">{index}</div>
                    <div class="pv-step-text">{item}</div>
                </div>
                """
            )
        )
    return "<div class='pv-finance-flow'>" + "".join(step_cards) + "</div>"


def sensitivity_series(price_autoconso):
    prices = list(range(60, 241, 10))
    values = []
    for price in prices:
        annual_revenue = (
            BILAN["autoconsommation_siell_mwh"] * price
            + BILAN["surplus_acc_mwh"] * ECONOMIE["prix_ppa_eur_mwh"]
        )
        values.append(round(annual_revenue - ECONOMIE["opex_annuel"], 0))
    return prices, values


def render_css():
    st.markdown(
        """
        <style>
        :root {
            --color-primary: #F59E0B;
            --color-secondary: #10B981;
            --color-bg: #0F172A;
            --color-card: #1E293B;
            --color-text: #F1F5F9;
            --color-muted: #94A3B8;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(245, 158, 11, 0.12), transparent 25%),
                radial-gradient(circle at top right, rgba(16, 185, 129, 0.12), transparent 28%),
                linear-gradient(180deg, #0B1220 0%, #0F172A 55%, #0B1220 100%);
            color: var(--color-text);
        }

        .pv-shell {
            color: var(--color-text);
        }

        .pv-hero {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.98) 0%, rgba(30, 41, 59, 0.96) 100%);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 22px;
            padding: 1.4rem 1.5rem;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.26);
            margin-bottom: 1rem;
        }

        .pv-kicker {
            color: #FBBF24;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            margin-bottom: 0.45rem;
        }

        .pv-title {
            margin: 0;
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--color-text);
        }

        .pv-subtitle {
            margin: 0.45rem 0 0;
            color: var(--color-muted);
            max-width: 920px;
            line-height: 1.55;
        }

        .pv-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.9rem;
        }

        .pv-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.16);
            color: #E2E8F0;
            border-radius: 999px;
            padding: 0.45rem 0.85rem;
            font-size: 0.82rem;
            font-weight: 600;
        }

        .pv-section-title {
            margin: 1rem 0 0.6rem;
            color: #E2E8F0;
            font-size: 1.05rem;
            font-weight: 700;
        }

        .pv-kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .pv-kpi {
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 16px;
            padding: 0.9rem 1rem;
            box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.04);
            min-height: 104px;
        }

        .pv-kpi-label {
            color: var(--color-muted);
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .pv-kpi-value {
            margin-top: 0.4rem;
            color: #FFFFFF;
            font-size: 1.45rem;
            font-weight: 800;
        }

        .pv-kpi-detail {
            margin-top: 0.35rem;
            color: #CBD5E1;
            font-size: 0.88rem;
            line-height: 1.45;
        }

        .pv-accent-amber {
            border-left: 4px solid #F59E0B;
        }

        .pv-accent-green {
            border-left: 4px solid #10B981;
        }

        .pv-accent-slate {
            border-left: 4px solid #38BDF8;
        }

        .pv-card, .pv-equipment-card, .pv-finance-step, .pv-site-card {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(30, 41, 59, 0.95) 100%);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 18px;
            padding: 1rem 1rem 0.95rem;
            box-shadow: 0 14px 32px rgba(0, 0, 0, 0.20);
        }

        .pv-card-title {
            color: #F8FAFC;
            font-size: 0.9rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.5rem;
        }

        .pv-card-body {
            color: #CBD5E1;
            line-height: 1.55;
            font-size: 0.94rem;
        }

        .pv-controls {
            display: grid;
            grid-template-columns: 1.3fr 1fr 1fr;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }

        .pv-site-grid-wrap {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }

        .pv-site-card {
            padding: 0.95rem 1rem;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
        }

        .pv-site-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 18px 38px rgba(0, 0, 0, 0.24);
        }

        .pv-selected {
            border-color: rgba(245, 158, 11, 0.45);
            box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.08), 0 18px 38px rgba(0, 0, 0, 0.24);
        }

        .pv-site-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.8rem;
        }

        .pv-site-name {
            color: #F8FAFC;
            font-weight: 700;
            font-size: 1rem;
            line-height: 1.35;
        }

        .pv-site-meta {
            color: #94A3B8;
            font-size: 0.84rem;
            margin-top: 0.25rem;
        }

        .pv-badge {
            color: #E2E8F0;
            border-radius: 999px;
            padding: 0.32rem 0.7rem;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(15, 23, 42, 0.84);
            font-size: 0.78rem;
            font-weight: 700;
        }

        .pv-site-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.65rem;
        }

        .pv-site-grid span, .pv-equipment-line {
            color: #94A3B8;
            font-size: 0.82rem;
        }

        .pv-site-grid strong {
            display: block;
            color: #F8FAFC;
            font-size: 0.92rem;
            margin-top: 0.15rem;
        }

        .pv-equipment-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.8rem;
        }

        .pv-equipment-name {
            color: #F8FAFC;
            font-weight: 800;
            font-size: 1rem;
            margin-bottom: 0.3rem;
        }

        .pv-equipment-line {
            color: #CBD5E1;
            margin-top: 0.25rem;
            line-height: 1.45;
        }

        .pv-finance-flow {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.75rem;
        }

        .pv-finance-step {
            padding: 0.9rem;
            min-height: 138px;
        }

        .pv-step-index {
            width: 2rem;
            height: 2rem;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.95), rgba(16, 185, 129, 0.95));
            color: #0F172A;
            font-weight: 900;
            margin-bottom: 0.6rem;
        }

        .pv-step-text {
            color: #E2E8F0;
            line-height: 1.5;
            font-size: 0.92rem;
        }

        .pv-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.22), transparent);
            margin: 1rem 0;
        }

        @media (max-width: 1100px) {
            .pv-kpi-grid, .pv-controls, .pv-equipment-grid, .pv-finance-flow {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .pv-site-grid-wrap {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 700px) {
            .pv-kpi-grid, .pv-controls, .pv-equipment-grid, .pv-finance-flow {
                grid-template-columns: 1fr;
            }
            .pv-title {
                font-size: 1.55rem;
            }
            .pv-site-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def PVDashboard(set_page_config=True):
    if set_page_config:
        st.set_page_config(page_title="LARZACQUA | Tableau de bord photovoltaïque", layout="wide")
    render_css()

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
        st.session_state["dashboard_mode"] = "pv"

    if "pv_selected_site" not in st.session_state:
        st.session_state["pv_selected_site"] = SITES[0]["nom"]

    sites_df = build_sites_df()
    site_options = ["Tous les sites"] + sites_df["nom"].tolist()

    render_bridge_banner(
        active_label="Interface PV active",
        other_label="l’interface hydro",
        active_mode="pv",
    )

    col_price = st.columns([1])[0]
    with col_price:
        price_autoconso = st.slider(
            "Prix autoconsommation (€ / MWh)",
            min_value=80,
            max_value=240,
            value=int(ECONOMIE["prix_autoconso_eur_mwh"]),
            step=5,
        )

    total_capex = ECONOMIE["capex_total"]
    net_revenue = ECONOMIE["revenu_net_an"]
    payback_years = total_capex / net_revenue

    st.markdown(
        "<div class='pv-kpi-grid'>"
        + kpi_html("Puissance installée", f"{format_kw(7096)} kWc", "7,1 MWc sur 6 sites", "amber")
        + kpi_html("Productible annuel", format_mwh(BILAN["productible_total_mwh"]), "Production annuelle totale", "green")
        + kpi_html("Autoconsommation SIELL", format_mwh(BILAN["autoconsommation_siell_mwh"]), "Couverture de la consommation locale", "slate")
        + kpi_html("Revenu net annuel", format_eur(ECONOMIE["revenu_net_an"]), "Après OPEX", "amber")
        + "</div>",
        unsafe_allow_html=True,
    )

    tab_analyse, tab_site, tab_dimensionnement, tab_economie = st.tabs(
        ["Analyse", "Site", "Dimensionnement", "Simulation économique"]
    )

    with tab_analyse:
        st.markdown("<div class='pv-section-title'>Vue d’ensemble</div>", unsafe_allow_html=True)
        st.markdown(
            card_html(
                "Lecture rapide",
                dedent(
                    """
                    Le projet PV combine une puissance installée de 7,1 MWc, un productible annuel de 10,84 GWh,
                    et une logique de valorisation mixte entre autoconsommation du SIELL et vente locale en ACC.
                    Utilise les onglets suivants pour détailler le dimensionnement puis la simulation économique.
                    """
                ),
                "slate",
            ),
            unsafe_allow_html=True,
        )

        st.markdown("<div class='pv-section-title'>Fiches des 6 sites</div>", unsafe_allow_html=True)
        st.markdown(site_cards_html(sites_df, st.session_state["pv_selected_site"]), unsafe_allow_html=True)

        st.markdown("<div class='pv-section-title'>Comparatif parc</div>", unsafe_allow_html=True)
        st.dataframe(site_comparison_df(), use_container_width=True, hide_index=True)

    with tab_site:
        st.markdown("<div class='pv-section-title'>Sélection du site</div>", unsafe_allow_html=True)
        st.selectbox("Choisir un site", site_options[1:], key="pv_selected_site")

        selected_site = st.session_state["pv_selected_site"]
        selected_row = get_selected_site(sites_df, selected_site)
        selected_profile = get_site_profile(selected_site)
        if selected_row is not None:
            puissance_value = selected_row.get("puissance_kwc")
            puissance = "non communiqué" if pd.isna(puissance_value) else f"{format_kw(puissance_value)} kWc"
            focus_body = dedent(
                f"""
                <strong>{selected_row['nom']}</strong><br>
                Secteur : {selected_row['secteur']}<br>
                Surface : {format_int(selected_row['surface'])} m²<br>
                Puissance communiquée : {puissance}<br>
                Part de surface du projet : {selected_row['surface_share_pct']:.1f} %
                """
            )
            st.markdown(card_html("Site actif", focus_body, "green"), unsafe_allow_html=True)

        st.markdown("<div class='pv-section-title'>Fiche PVsyst complète</div>", unsafe_allow_html=True)
        st.markdown(selected_site_detail_html(selected_site), unsafe_allow_html=True)

        monthly_df = monthly_profile_series(selected_profile)
        render_chart_panel(
            f"Production mensuelle - {selected_site}",
            "Profil mensuel E_Grid issu des simulations PVsyst.",
            "pv_monthly_chart_site",
            {
                "type": "bar",
                "data": {
                    "labels": monthly_df["Mois"].tolist(),
                    "datasets": [
                        {
                            "label": "Production (kWh)",
                            "data": monthly_df["Production kWh"].tolist(),
                            "backgroundColor": "rgba(245, 158, 11, 0.82)",
                            "borderColor": "#F59E0B",
                            "borderWidth": 1,
                            "borderRadius": 8,
                        }
                    ],
                },
                "options": {
                    **chart_theme(),
                    "plugins": {**chart_theme()["plugins"], "legend": {"display": False}},
                },
            },
            height=320,
        )

        st.markdown("<div class='pv-section-title'>Pertes système du site</div>", unsafe_allow_html=True)
        st.dataframe(site_losses_df(selected_profile), use_container_width=True, hide_index=True)

    with tab_dimensionnement:
        st.markdown("<div class='pv-section-title'>Dimensionnement technique</div>", unsafe_allow_html=True)
        st.markdown(
            card_html(
                "Lecture technique du parc",
                dedent(
                    """
                    Les six sites partagent une base technique commune PVsyst, avec des écarts liés à la géométrie,
                    à l’orientation, à l’altitude et au niveau de pertes. Le tableau ci-dessous permet de comparer
                    rapidement les indicateurs de dimensionnement principaux.
                    """
                ),
                "slate",
            ),
            unsafe_allow_html=True,
        )

        comparison_df = site_comparison_df()
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)

        surface_labels = [SITE_SHORT_NAMES.get(site["nom"], site["nom"]) for site in SITES]
        surface_values = [site["surface"] for site in SITES]
        selected_site = st.session_state["pv_selected_site"]
        surface_colors = ["#F59E0B" if site["nom"] == selected_site else "rgba(245, 158, 11, 0.55)" for site in SITES]

        render_chart_panel(
            "Surfaces des sites",
            "La surface utile pilote le gisement disponible à l’échelle de chaque implantation.",
            "pv_surface_chart",
            {
                "type": "bar",
                "data": {
                    "labels": surface_labels,
                    "datasets": [
                        {
                            "label": "Surface (m²)",
                            "data": surface_values,
                            "backgroundColor": surface_colors,
                            "borderColor": "#F59E0B",
                            "borderWidth": 1,
                            "borderRadius": 10,
                        }
                    ],
                },
                "options": {
                    **chart_theme(),
                    "indexAxis": "y",
                    "plugins": {**chart_theme()["plugins"], "legend": {"display": False}},
                },
            },
            height=340,
        )

        render_chart_panel(
            "Bilan énergétique annuel",
            "L’autoconsommation couvre la consommation du SIELL et laisse un surplus valorisable en ACC.",
            "pv_energy_chart",
            {
                "type": "doughnut",
                "data": {
                    "labels": ["Autoconsommation SIELL", "Surplus ACC"],
                    "datasets": [
                        {
                            "data": [BILAN["autoconsommation_siell_mwh"], BILAN["surplus_acc_mwh"]],
                            "backgroundColor": ["#10B981", "#F59E0B"],
                            "borderColor": ["#10B981", "#F59E0B"],
                            "borderWidth": 1,
                        }
                    ],
                },
                "options": {
                    **chart_theme(),
                    "cutout": "66%",
                    "plugins": chart_theme()["plugins"],
                },
            },
            height=340,
        )

        st.markdown("<div class='pv-section-title'>Pertes système communes</div>", unsafe_allow_html=True)
        losses_profile = get_site_profile(selected_site)
        st.dataframe(site_losses_df(losses_profile), use_container_width=True, hide_index=True)

        st.markdown("<div class='pv-section-title'>Équipements standardisés</div>", unsafe_allow_html=True)
        st.markdown(standardized_equipment_html(), unsafe_allow_html=True)

    with tab_economie:
        st.markdown("<div class='pv-section-title'>Simulation économique</div>", unsafe_allow_html=True)
        capex_labels = ["Construction", "Infra réseau", "Raccordement"]
        capex_values = [ECONOMIE["capex_construction"], ECONOMIE["capex_infra_reseau"], ECONOMIE["capex_raccordement"]]

        render_chart_panel(
            "Décomposition du CAPEX",
            "Le modèle économique repose sur un CAPEX majoritairement porté par la construction des centrales.",
            "pv_capex_chart",
            {
                "type": "bar",
                "data": {
                    "labels": capex_labels,
                    "datasets": [
                        {
                            "label": "CAPEX (€HT)",
                            "data": capex_values,
                            "backgroundColor": ["#F59E0B", "#10B981", "#38BDF8"],
                            "borderColor": ["#F59E0B", "#10B981", "#38BDF8"],
                            "borderWidth": 1,
                            "borderRadius": 10,
                        }
                    ],
                },
                "options": {
                    **chart_theme(),
                    "plugins": {**chart_theme()["plugins"], "legend": {"display": False}},
                },
            },
            height=340,
        )

        prices, values = sensitivity_series(price_autoconso)
        render_chart_panel(
            "Sensibilité du revenu net au prix de l’énergie",
            f"Le curseur ajuste le prix d’autoconsommation : ici {price_autoconso} €/MWh en base.",
            "pv_sensitivity_chart",
            {
                "type": "line",
                "data": {
                    "labels": prices,
                    "datasets": [
                        {
                            "label": "Revenu net annuel (€)",
                            "data": values,
                            "borderColor": "#F59E0B",
                            "backgroundColor": "rgba(245, 158, 11, 0.15)",
                            "fill": True,
                            "tension": 0.25,
                            "pointRadius": 3,
                            "pointHoverRadius": 5,
                        }
                    ],
                },
                "options": {
                    **chart_theme(),
                    "plugins": chart_theme()["plugins"],
                },
            },
            height=340,
        )

        st.markdown(
            "<div class='pv-kpi-grid'>"
            + kpi_html("CAPEX total", format_eur(total_capex), "7,58 M€ HT", "amber")
            + kpi_html("OPEX annuel", format_eur(ECONOMIE["opex_annuel"]), "18 €/kWc/an", "green")
            + kpi_html("Revenu brut annuel", format_eur(ECONOMIE["revenu_total_an"]), "Autoconsommation + PPA", "slate")
            + kpi_html("Temps de retour", f"{payback_years:.1f} ans", "Sur base du revenu net", "amber")
            + "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            card_html(
                "Lecture économique",
                dedent(
                    """
                    Les hypothèses du livrable placent le projet dans une trajectoire d’exploitation robuste :
                    CAPEX maîtrisé, OPEX contenue, revenus récurrents issus de l’autoconsommation et du PPA local.
                    La documentation mentionne un LCOE cible inférieur à 50 €/MWh et un TRI proche de 10 %.
                    """
                ),
                "green",
            ),
            unsafe_allow_html=True,
        )

        st.markdown("<div class='pv-section-title'>Montage financier (tiers-investisseur)</div>", unsafe_allow_html=True)
        st.markdown(financing_html(), unsafe_allow_html=True)

    st.markdown("<div class='pv-divider'></div>", unsafe_allow_html=True)
    st.caption(
        "Dashboard PV hardcodé à partir des livrables de dimensionnement et de modélisation économique. "
        "Les tooltips de survol sont fournis par Chart.js, sans appel API ni extraction dynamique."
    )


if __name__ == "__main__":
    PVDashboard()
