"""
Module de génération de PDF récapitulatif pour SimuWatter
Sections :
1) Analyse comparative
2) Estimation par site (avec dimensionnement)
"""
import os
import math
import tempfile
import urllib.request
import json
import subprocess
import sys
from fpdf import FPDF
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime


class SimuWatterPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # sensible defaults
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(15, 15, 15)
        self.alias_nb_pages()

    def colored_box(self, x, y, w, h, color, text, text_color=(255,255,255)):
        self.set_fill_color(*color)
        self.set_text_color(*text_color)
        self.rect(x, y, w, h, 'F')
        self.set_xy(x, y+2)
        self.set_font('Arial', 'B', 11)
        self.cell(w, h-4, text, 0, 0, 'C')
        self.set_text_color(0,0,0)

    def header(self):
        # Ajout du logo
        logo_path = os.path.join(os.path.dirname(__file__), '../Image1.png')
        y = 8
        if os.path.exists(logo_path):
            self.image(logo_path, x=15, y=y, w=24)
        # Title left area
        self.set_xy(44, y)
        self.set_font('Arial', 'B', 10)
        self.set_text_color(13, 43, 74)
        self.cell(0, 6, 'SimuWatter - Analyse potentiel hydroélectrique', ln=1)
        # Right: page number
        self.set_xy(-40, y)
        self.set_font('Arial', '', 9)
        self.set_text_color(100)
        # Use FPDF alias for total pages
        self.cell(30, 6, f'Page {self.page_no()}/{{nb}}', 0, 0, 'R')

    def section_title(self, title):
        self.ln(4)
        self.set_font('Arial', 'B', 12)
        title_s = sanitize_for_latin1(title)
        self.cell(0, 8, title_s, 0, 1, 'L')
        self.ln(2)

    def section_body(self, text):
        self.set_font('Arial', '', 11)
        # Normalize and sanitize for latin-1
        safe = sanitize_for_latin1(text)
        self.multi_cell(0, 8, safe)
        self.ln(2)

    def add_table(self, dataframe, title=None, col_widths=None, max_col_width=40, truncate=30):
        if title:
            self.section_title(title)
        self.set_font('Arial', '', 9)
        ncols = len(dataframe.columns)
        if col_widths is None:
            # Ajuste la largeur pour chaque colonne (max_col_width px)
            usable = self.w - self.l_margin - self.r_margin
            col_width = min(usable / ncols, max_col_width)
            col_widths = [col_width] * ncols
        th = self.font_size + 2
        # Header
        self.set_font('Arial', 'B', 9)
        for i, col in enumerate(dataframe.columns):
            h = sanitize_for_latin1(str(col)[:truncate])
            self.cell(col_widths[i], th, h, border=1, align='L')
        self.ln(th)
        # Rows
        self.set_font('Arial', '', 9)
        for _, row in dataframe.iterrows():
            for i, item in enumerate(row):
                val = str(item)
                if len(val) > truncate:
                    val = val[:truncate-3] + '...'
                # align numbers to right
                align = 'R' if isinstance(item, (int, float)) or (isinstance(val, str) and val.replace('.', '', 1).isdigit()) else 'L'
                self.cell(col_widths[i], th, sanitize_for_latin1(val), border=1, align=align)
            self.ln(th)
        self.ln(2)


def build_cover(pdf: SimuWatterPDF, site_name: str, author: str = "SimuWatter"):
    pdf.add_page()
    pdf.set_font('Arial', 'B', 26)
    pdf.set_text_color(13, 43, 74)
    pdf.cell(0, 40, '', 0, 1, 'C')
    pdf.cell(0, 14, sanitize_for_latin1('Analyse potentiel hydroélectrique'), 0, 1, 'C')
    pdf.set_font('Arial', '', 18)
    pdf.cell(0, 10, sanitize_for_latin1(f'Rapport site: {site_name}'), 0, 1, 'C')
    pdf.ln(18)
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(0)
    pdf.cell(0, 8, sanitize_for_latin1(f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}'), 0, 1, 'C')
    pdf.cell(0, 8, sanitize_for_latin1(f'Auteur: {author}'), 0, 1, 'C')


def build_toc(pdf: SimuWatterPDF, entries=None):
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Sommaire', 0, 1)
    pdf.ln(4)
    pdf.set_font('Arial', '', 12)
    if not entries:
        entries = [
            ('Synthèse exécutive', 3),
            ('Caractéristiques du site', 4),
            ('Sélection turbine', 6),
            ('Estimations économiques', 8),
            ('Graphiques', 10),
            ('Recommandations', 12),
            ('Annexes', 14),
        ]
    for title, page in entries:
        line = f'{title} ........................................ {page}'
        pdf.cell(0, 8, sanitize_for_latin1(line), 0, 1)


def build_synthesis(pdf: SimuWatterPDF, summary_text: str, kpis: dict = None):
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Synthèse exécutive', 0, 1)
    pdf.ln(4)
    pdf.set_font('Arial', '', 11)
    pdf.multi_cell(0, 7, sanitize_for_latin1(summary_text))
    pdf.ln(6)
    if kpis:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'KPIs clés', 0, 1)
        pdf.ln(2)
        pdf.set_font('Arial', '', 11)
        for name, val in kpis.items():
            pdf.cell(60, 7, sanitize_for_latin1(name), 0)
            pdf.cell(0, 7, sanitize_for_latin1(str(val)), 0, 1)


def generate_analysis_global_report(output_path, results_df):
    """
    Génère un rapport PDF global d'analyse avec statistiques, classement et recommandations.
    
    Args:
        output_path: Chemin de sortie du PDF
        results_df: DataFrame avec les résultats de l'analyse (colonnes: site_name, power_kW, delta_p, estimated_flow_obs, estimated_flow_calc, score)
    
    Returns:
        Chemin du fichier généré
    """
    pdf = SimuWatterPDF()
    
    # Calculs des statistiques globales
    power_total_kw = results_df['power_kW'].sum() if 'power_kW' in results_df.columns else 0
    num_sites = len(results_df)
    annual_energy_kwh = power_total_kw * 8760  # Approximation: heures par an
    
    # Page de couverture
    pdf.add_page()
    pdf.set_font('Arial', 'B', 26)
    pdf.set_text_color(13, 43, 74)
    pdf.cell(0, 40, '', 0, 1, 'C')
    pdf.cell(0, 14, 'Résumé Global de l\'Analyse', 0, 1, 'C')
    pdf.set_font('Arial', '', 18)
    pdf.cell(0, 10, f'Potentiel hydroélectrique - {num_sites} sites', 0, 1, 'C')
    pdf.ln(18)
    pdf.set_font('Arial', '', 11)
    pdf.set_text_color(0)
    pdf.cell(0, 8, f'Date: {datetime.utcnow().strftime("%Y-%m-%d")}', 0, 1, 'C')
    pdf.cell(0, 8, 'Auteur: SimuWatter', 0, 1, 'C')
    
    # Table des matières
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Sommaire', 0, 1)
    pdf.ln(4)
    pdf.set_font('Arial', '', 12)
    toc_entries = [
        ('Synthèse exécutive', 3),
        ('1. Vue d\'ensemble', 4),
        ('2. Statistiques hydrauliques', 4),
        ('3. Classement des sites', 5),
        ('4. Contribution énergétique', 5),
        ('5. Recommandations', 6),
    ]
    for title, page in toc_entries:
        line = f'{title} ........................................ {page}'
        pdf.cell(0, 8, sanitize_for_latin1(line), 0, 1)
    
    # Synthèse exécutive
    summary_text = (
        f"Analyse globale de {num_sites} sites hydroélectriques. "
        f"Puissance cumulée: {power_total_kw:.2f} kW, soit {annual_energy_kwh:,.0f} kWh/an estimés. "
        f"Ce rapport synthétise les résultats d'analyse: statistiques clés, classement des sites par potentiel, "
        f"et recommandations pour les étapes suivantes."
    )
    build_synthesis(pdf, summary_text, {
        'Nombre de sites': str(num_sites),
        'Puissance cumulée (kW)': f'{power_total_kw:.2f}',
        'Énergie annuelle (kWh)': f'{annual_energy_kwh:,.0f}',
    })
    
    # Vue d'ensemble
    pdf.add_page()
    pdf.section_title('1. Vue d\'ensemble')
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Statistiques globales', 0, 1)
    pdf.ln(2)
    
    avg_pressure = results_df['delta_p'].mean() if 'delta_p' in results_df.columns else 0
    overview_rows = [
        ['Nombre de sites', str(num_sites)],
        ['Puissance cumulée (kW)', f'{power_total_kw:.2f}'],
        ['Énergie annuelle estimée (kWh)', f'{annual_energy_kwh:,.0f}'],
        ['Pression moyenne (bar)', f'{avg_pressure:.2f}'],
        ['Puissance minimale (kW)', f'{results_df["power_kW"].min():.2f}' if 'power_kW' in results_df.columns else 'N/D'],
        ['Puissance maximale (kW)', f'{results_df["power_kW"].max():.2f}' if 'power_kW' in results_df.columns else 'N/D'],
    ]
    pdf.add_table(pd.DataFrame(overview_rows, columns=['Indicateur', 'Valeur']), max_col_width=80)
    
    # Statistiques hydrauliques
    pdf.add_page()
    pdf.section_title('2. Statistiques hydrauliques')
    
    hydro_rows = [
        ['Paramètre', 'Minimum', 'Moyenne', 'Maximum']
    ]
    
    if 'delta_p' in results_df.columns:
        hydro_rows.append([
            'Pression (bar)',
            f'{results_df["delta_p"].min():.2f}',
            f'{results_df["delta_p"].mean():.2f}',
            f'{results_df["delta_p"].max():.2f}',
        ])
    
    if 'estimated_flow_obs' in results_df.columns and results_df['estimated_flow_obs'].notna().any():
        hydro_rows.append([
            'Débit observé (m³/h)',
            f'{results_df["estimated_flow_obs"].min():.2f}',
            f'{results_df["estimated_flow_obs"].mean():.2f}',
            f'{results_df["estimated_flow_obs"].max():.2f}',
        ])
    
    if 'estimated_flow_calc' in results_df.columns and results_df['estimated_flow_calc'].notna().any():
        hydro_rows.append([
            'Débit calculé (m³/h)',
            f'{results_df["estimated_flow_calc"].min():.2f}',
            f'{results_df["estimated_flow_calc"].mean():.2f}',
            f'{results_df["estimated_flow_calc"].max():.2f}',
        ])
    
    if len(hydro_rows) > 1:
        hydro_df = pd.DataFrame(hydro_rows[1:], columns=hydro_rows[0])
        pdf.add_table(hydro_df, max_col_width=40)
    
    # Classement des sites
    pdf.add_page()
    pdf.section_title('3. Classement des sites par puissance')
    
    ranking = results_df[['site_name', 'power_kW', 'delta_p']].copy() if 'delta_p' in results_df.columns else results_df[['site_name', 'power_kW']].copy()
    ranking.insert(0, 'Rang', range(1, len(ranking) + 1))
    
    display_cols = ['Rang', 'site_name', 'power_kW', 'delta_p'] if 'delta_p' in ranking.columns else ['Rang', 'site_name', 'power_kW']
    ranking_display = ranking[display_cols].copy()
    ranking_display.columns = ['Rang', 'Site', 'Puissance (kW)', 'Pression (bar)'] if 'delta_p' in ranking.columns else ['Rang', 'Site', 'Puissance (kW)']
    
    pdf.add_table(ranking_display, max_col_width=50, truncate=35)
    
    # Contribution énergétique
    pdf.add_page()
    pdf.section_title('4. Contribution énergétique (top 5 sites)')
    
    if power_total_kw > 0:
        top5 = results_df.nlargest(5, 'power_kW')[['site_name', 'power_kW']].copy() if 'power_kW' in results_df.columns else results_df.head(5)
        if len(top5) > 0:
            top5['Contribution (%)'] = (top5['power_kW'] / power_total_kw * 100).round(1)
            contrib_df = top5[['site_name', 'power_kW', 'Contribution (%)']].copy()
            contrib_df.columns = ['Site', 'Puissance (kW)', 'Contribution (%)']
            pdf.add_table(contrib_df, max_col_width=50, truncate=35)
    
    # Recommandations
    pdf.add_page()
    pdf.section_title('5. Recommandations globales')
    
    recommendations = []
    
    # Top site
    if len(results_df) > 0 and 'power_kW' in results_df.columns:
        top_site = results_df.nlargest(1, 'power_kW').iloc[0]
        recommendations.append(
            f"Site prioritaire: {top_site['site_name']} avec {top_site['power_kW']:.2f} kW"
        )
    
    # Potentiel global
    if power_total_kw > 0:
        if power_total_kw >= 50:
            recommendations.append(
                f"Potentiel global important: {power_total_kw:.2f} kW cumulés ({annual_energy_kwh:,.0f} kWh/an)"
            )
        elif power_total_kw >= 10:
            recommendations.append(
                f"Potentiel modéré: {power_total_kw:.2f} kW cumulés ({annual_energy_kwh:,.0f} kWh/an)"
            )
        else:
            recommendations.append(
                f"Potentiel limité: {power_total_kw:.2f} kW cumulés ({annual_energy_kwh:,.0f} kWh/an)"
            )
    
    # Concentration de puissance
    if len(results_df) > 0 and 'power_kW' in results_df.columns:
        top3_power = results_df.nlargest(3, 'power_kW')['power_kW'].sum()
        concentration = (top3_power / power_total_kw * 100) if power_total_kw > 0 else 0
        recommendations.append(
            f"Top 3 sites concentrent {concentration:.1f}% de la puissance totale"
        )
    
    # Réseau haute/basse pression
    if 'delta_p' in results_df.columns:
        avg_pressure = results_df['delta_p'].mean()
        if avg_pressure >= 3:
            recommendations.append(
                f"Réseau haute pression (ΔP moyen = {avg_pressure:.2f} bar) - favorable pour turbines"
            )
        else:
            recommendations.append(
                f"Réseau basse/moyenne pression (ΔP moyen = {avg_pressure:.2f} bar) - à considérer"
            )
    
    # Nombre de sites viables
    if 'power_kW' in results_df.columns:
        viable_sites = len(results_df[results_df['power_kW'] > 0.5])
        recommendations.append(
            f"Sites viables (P > 0.5 kW): {viable_sites}/{len(results_df)}"
        )
    
    pdf.set_font('Arial', '', 11)
    for i, rec in enumerate(recommendations, 1):
        pdf.cell(0, 8, f'{i}. {sanitize_for_latin1(rec)}', 0, 1)
    
    pdf.ln(4)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'Prochaines étapes:', 0, 1)
    
    pdf.set_font('Arial', '', 10)
    next_steps = [
        '1. Approfondir les études sur les 3-5 sites prioritaires',
        '2. Vérifier la faisabilité technique de chaque site',
        '3. Évaluer les coûts CAPEX/OPEX détaillés',
        '4. Engager les stakeholders locaux et collectivités',
        '5. Préparer les démarches administratives',
    ]
    for step in next_steps:
        pdf.cell(0, 7, sanitize_for_latin1(step), 0, 1)
    
    pdf.output(output_path)
    return output_path


def sanitize_for_latin1(text: str) -> str:
    if text is None:
        return ''
    replacements = {
        '\u2014': '-',
        '\u2013': '-',
        '\u00A0': ' ',
        '\u2018': "'",
        '\u2019': "'",
        '\u201C': '"',
        '\u201D': '"',
        '€': 'EUR',
    }
    s = str(text)
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s.encode('latin-1', 'replace').decode('latin-1')


def _safe_float(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _format_value(value, digits=0, suffix=''):
    if value is None:
        return '-'
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return '-'
    if digits <= 0:
        text = f'{number:.0f}'
    else:
        text = f'{number:.{digits}f}'
    return f'{text}{suffix}'


def _scenario_rows(scenarios):
    rows = []
    for scenario in scenarios or []:
        if not scenario:
            continue
        result = scenario.get('result', {}) or {}
        eco = scenario.get('eco', {}) or {}
        payback = eco.get('temps_retour_ans')
        tri = eco.get('tri')
        rows.append({
            'Scenario': scenario.get('name', '-'),
            'Mode': scenario.get('mode', '-'),
            'Heures/an': _format_value(scenario.get('hours')),
            'CAPEX (EUR)': _format_value(scenario.get('capex')),
            'OPEX (EUR/an)': _format_value(scenario.get('opex')),
            'Energie (kWh/an)': _format_value(result.get('energie_kwh')),
            'Autoconsommation (kWh)': _format_value(eco.get('autoconsommation_kwh')),
            'Injection (kWh)': _format_value(eco.get('injection_kwh')),
            'Revenu total (EUR/an)': _format_value(eco.get('revenu_total_eur')),
            'Payback (ans)': _format_value(payback, digits=1),
            'TRI (%)': _format_value(tri * 100 if tri is not None else None, digits=1),
        })
    return pd.DataFrame(rows)


def _metric_rows(metric_pairs):
    rows = []
    for label, value in metric_pairs or []:
        rows.append({'Indicateur': label, 'Valeur': value})
    return pd.DataFrame(rows)


def generate_site_simulation_report(
    output_path,
    site_row,
    productible_context,
    scenarios_injection=None,
    scenarios_autoconsommation=None,
    rank=None,
    total_sites=None,
    ai_recommendation=None,
    recommendation_report_data=None,
):
    pdf = SimuWatterPDF()

    context = dict(productible_context or {})
    report_data = context.get('simulation_report_data', {}) or {}
    selection_report_data = context.get('selection_report_data', {}) or {}
    capex_report_data = context.get('capex_report_data', {}) or {}
    oa_report_data = context.get('oa_report_data', {}) or {}
    recommendation_report_data = recommendation_report_data or context.get('recommendation_report_data', {}) or {}
    site_name = str(site_row.get('site_name', 'Site'))
    result = context.get('result', {}) or {}
    eco = context.get('eco', {}) or {}
    selected_turbine = dict(context.get('selected_turbine', {}) or {})

    if report_data.get('result_summary'):
        summary_result = report_data['result_summary']
        puissance_kw = _safe_float(summary_result.get('power_kw', 0))
        energie_kwh = _safe_float(summary_result.get('energy_kwh', 0))
        economie = _safe_float(summary_result.get('economies_eur', 0))
        revenus = _safe_float(summary_result.get('revenus_eur', 0))
        autoconsommation = _safe_float(summary_result.get('autoconsommation_kwh', 0))
        taux_auto = _safe_float(summary_result.get('taux_auto', 0))
        capex = _safe_float(summary_result.get('capex', 0))
        opex = _safe_float(summary_result.get('opex', 0))
        capex_net = _safe_float(summary_result.get('capex_net', 0))
        payback = summary_result.get('payback')
        van = summary_result.get('van')
        tri = summary_result.get('tri')
    else:
        puissance_kw = _safe_float(result.get('puissance_kw', 0))
        energie_kwh = _safe_float(result.get('energie_kwh', 0))
        economie = _safe_float(context.get('economie', eco.get('economies_eur', 0)))
        revenus = _safe_float(context.get('revenus', eco.get('revenus_injection_eur', 0)))
        autoconsommation = _safe_float(context.get('autoconsommation', eco.get('autoconsommation_kwh', 0)))
        taux_auto = _safe_float(context.get('taux_auto', eco.get('taux_autoconsommation', 0) * 100))
        capex = _safe_float(context.get('capex', 0))
        opex = _safe_float(context.get('opex', 0))
        capex_net = _safe_float(context.get('capex_net', capex - _safe_float(context.get('subvention_eur', 0))))
        payback = context.get('payback')
        van = context.get('van')
        tri = context.get('tri')

    debit_m3h = _safe_float(site_row.get('estimated_flow', 0))
    pression_bar = _safe_float(site_row.get('delta_p', 0))
    subsidy_rate = _safe_float(context.get('subsidy_rate', 0))
    subvention_eur = _safe_float(context.get('subvention_eur', 0))
    discount_rate = _safe_float(context.get('discount_rate', 0))
    project_life = context.get('project_life')
    heures_fonctionnement = int(_safe_float(context.get('heures_fonctionnement', 0)))
    mode = str(context.get('mode', 'Autoconsommation'))
    conso_site = _safe_float(context.get('conso_site', 0))
    prix_elec = _safe_float(context.get('prix_elec', 0))
    tarif_oa = context.get('tarif_oa')
    prix_evite = context.get('prix_evite')
    site_summary_text = report_data.get('site_summary_text') or selection_report_data.get('site_summary_text')
    compatible_turbines_display = report_data.get('compatible_turbines_display') or selection_report_data.get('compatible_turbines_display', [])
    compatible_turbines_columns = report_data.get('compatible_turbines_columns') or selection_report_data.get('compatible_turbines_columns', [])
    manual_parameters = report_data.get('manual_parameters', [])
    if not manual_parameters:
        manual_parameters = [
            ('Débit moyen (m3/h)', f'{debit_m3h:.1f}'),
            ('Pression amont (bar)', f'{pression_bar:.1f}'),
            ('Type de turbine', f"{selected_turbine.get('type_turbine', 'N/A')} Ø{selected_turbine.get('diametre_mm', '-') }mm ({selected_turbine.get('puissance_min_kw', '-')}-{selected_turbine.get('puissance_max_kw', '-')}kW)"),
            ('Rendement turbine (%)', f"{selected_turbine.get('rendement_typique', '-') }"),
            ('Heures de fonctionnement/an', f'{heures_fonctionnement}'),
            ('Disponibilité turbine (%)', f"{selected_turbine.get('availability', '-') }"),
            ('Mode', mode),
            ('Exploitation', str(context.get('exploitation', 'N/A'))),
            ('Consommation site (kWh/an)', f'{conso_site}'),
            ('CAPEX estime (EUR)', f'{capex:.0f}'),
            ('OPEX estime (EUR/an)', f'{opex:.0f}'),
            ('% subvention / CAPEX', f'{subsidy_rate:.1f}'),
            ("Taux d'actualisation (%)", f'{discount_rate:.1f}'),
            ('Duree de vie projet (ans)', f'{project_life}'),
        ]
    scenario_sections = report_data.get('scenario_sections', [])
    if not scenario_sections and (context.get('scenarios_injection') or context.get('scenarios_autoconsommation')):
        scenario_sections = [
            {
                'title': 'Scénarios - Injection réseau',
                'caption': 'Résultats calculés en mode injection réseau, avec production entièrement vendue au tarif d’injection.',
                'scenarios': context.get('scenarios_injection', []),
            },
            {
                'title': 'Scénarios - Autoconsommation',
                'caption': 'Résultats calculés en mode autoconsommation, avec prix évité de l’onglet OA/autoconsommation et un CAPEX majoré pour refléter le surcoût d’autoconsommation.',
                'scenarios': context.get('scenarios_autoconsommation', []),
            },
        ]
    recommendation_detail_text = recommendation_report_data.get('recommendation_detail_text')
    recommendation_type = recommendation_report_data.get('recommendation_type')
    recommendation_metrics = recommendation_report_data.get('recommendation_metrics', [])
    recommendation_fallback_text = recommendation_report_data.get('fallback_text')
    recommendation_general_text = recommendation_report_data.get('general_recommendation_text')

    if not capex_report_data:
        capex_report_data = {
            'distance_install_m': context.get('distance_install_m'),
            'distance_grid_m': context.get('distance_grid_m'),
            'electrical_install_type': context.get('electrical_install_type'),
            'capex_integration_level': context.get('capex_integration_level'),
            'capex_electrical_level': context.get('capex_electrical_level'),
            'capex_table': context.get('capex_table', []),
            'capex_columns': context.get('capex_columns', []),
            'opex_table_display': context.get('opex_table_display', []),
            'capex': capex,
            'opex': opex,
            'subsidy_rate': subsidy_rate,
            'discount_rate': discount_rate,
            'project_life': project_life,
        }

    if not oa_report_data:
        head_m = float(pression_bar * 10.2)
        chute_type = 'haute chute' if pression_bar > 3 or head_m > 30 else 'basse chute'
        tarif_recommande = 0.12 if chute_type == 'haute chute' else 0.132
        oa_report_data = {
            'tarif_oa': tarif_oa,
            'prix_evite': prix_evite,
            'head_m': head_m,
            'chute_type': chute_type,
            'tarif_recommande': tarif_recommande,
            'reference_text': '- Installations hydrauliques neuves (<500 kW) : tarifs de référence définis par arrêté.\n- 120 €/MWh pour haute chute (> 3 bar / > 30 m).\n- 132 €/MWh pour basse chute (< 30 m).',
            'applicable_text': f'Pour ce site, la chute estimée est **{chute_type}** ({head_m:.1f} m) et le tarif recommandé est **{tarif_recommande:.3f} €/kWh**.',
        }

    summary_text = site_summary_text or (
        f"Le site {site_name} a été simulé avec un débit moyen de {debit_m3h:.1f} m3/h et une pression amont de {pression_bar:.2f} bar. "
        f"La turbine retenue est {selected_turbine.get('type_turbine', 'non renseignée')} (Ø {selected_turbine.get('diametre_mm', '-') } mm). "
        f"La simulation retient une puissance de {puissance_kw:.2f} kW, une production annuelle de {energie_kwh:.0f} kWh/an et {economie:.0f} EUR/an d'économies estimées. "
        f"Le temps de retour calculé est {_format_value(payback, digits=1)} ans, avec une VAN de {_format_value(van)} EUR et un TRI de {_format_value(tri * 100 if tri is not None else None, digits=1)} %."
    )

    build_cover(pdf, site_name)
    build_toc(pdf, entries=[
        ('Synthèse exécutive', 3),
        ('1. Caractéristiques du site', 4),
        ('2. Turbines compatibles', 4),
        ('3. Estimation CAPEX/OPEX', 5),
        ('4. Tarif OA / Prix évité', 5),
        ('5. Paramètres de simulation', 6),
        ('6. Résultats énergétiques', 6),
        ('7. Résultats économiques', 7),
        ('8. Scénarios comparés', 8),
        ('9. Recommandation', 9),
        ('10. Conclusion', 9),
    ])
    build_synthesis(
        pdf,
        summary_text,
        {
            'Puissance (kW)': f'{puissance_kw:.2f}',
            'Énergie (kWh/an)': f'{energie_kwh:.0f}',
            'Économies (EUR/an)': f'{economie:.0f}',
            'Payback (ans)': _format_value(payback, digits=1),
        },
    )

    pdf.add_page()
    pdf.section_title('1. Caractéristiques du site')
    pdf.section_body(summary_text)
    
    site_context_rows = [
        ['Site', site_name],
        ['Débit moyen', f'{debit_m3h:.1f} m³/h'],
        ['Pression amont', f'{pression_bar:.2f} bar'],
        ['Mode', mode],
        ['Heures de fonctionnement', f'{heures_fonctionnement} h/an'],
        ['Consommation du site', f'{conso_site:.0f} kWh/an'],
        ['Prix électricité', f'{prix_elec:.3f} EUR/kWh'],
    ]
    if tarif_oa is not None:
        site_context_rows.append(['Tarif OA', f'{tarif_oa:.3f} EUR/kWh'])
    if prix_evite is not None:
        site_context_rows.append(['Prix évité', f'{prix_evite:.3f} EUR/kWh'])
    pdf.add_table(pd.DataFrame(site_context_rows, columns=['Paramètre', 'Valeur']), title='Données du site', max_col_width=70, truncate=46)

    pdf.section_title('2. Turbines compatibles')
    if compatible_turbines_display:
        pdf.add_table(pd.DataFrame(compatible_turbines_display, columns=compatible_turbines_columns), title='Tableau des turbines compatibles', max_col_width=38, truncate=26)
    else:
        pdf.section_body('Aucune turbine compatible détectée pour ce site.')

    if capex_report_data:
        pdf.section_title('3. Estimation CAPEX/OPEX')
        capex_summary_rows = []
        if capex_report_data.get('distance_install_m') is not None:
            capex_summary_rows.append(['Distance a l\'installation (m)', f"{capex_report_data.get('distance_install_m'):.0f}"])
        if capex_report_data.get('distance_grid_m') is not None:
            capex_summary_rows.append(['Distance au poste electrique (m)', f"{capex_report_data.get('distance_grid_m'):.0f}"])
        if capex_report_data.get('electrical_install_type') is not None:
            capex_summary_rows.append(['Type d\'installation electrique', str(capex_report_data.get('electrical_install_type'))])
        if capex_report_data.get('capex_integration_level') is not None:
            capex_summary_rows.append(['Niveau d\'integration', str(capex_report_data.get('capex_integration_level'))])
        if capex_report_data.get('capex_electrical_level') is not None:
            capex_summary_rows.append(['Raccordement electrique', str(capex_report_data.get('capex_electrical_level'))])
        if capex_report_data.get('capex') is not None:
            capex_summary_rows.append(['CAPEX estime (EUR)', _format_value(capex_report_data.get('capex'))])
        if capex_report_data.get('opex') is not None:
            capex_summary_rows.append(['OPEX estime (EUR/an)', _format_value(capex_report_data.get('opex'))])
        if capex_report_data.get('subsidy_rate') is not None:
            capex_summary_rows.append(['Subvention (% CAPEX)', _format_value(capex_report_data.get('subsidy_rate'), digits=1)])
        if capex_report_data.get('discount_rate') is not None:
            capex_summary_rows.append(['Taux d\'actualisation (%)', _format_value(capex_report_data.get('discount_rate'), digits=1)])
        if capex_report_data.get('project_life') is not None:
            capex_summary_rows.append(['Duree de vie projet (ans)', _format_value(capex_report_data.get('project_life'))])
        if capex_summary_rows:
            pdf.add_table(pd.DataFrame(capex_summary_rows, columns=['Indicateur', 'Valeur']), title='Synthese CAPEX/OPEX affichee', max_col_width=70, truncate=46)
        if capex_report_data.get('capex_table'):
            capex_columns = capex_report_data.get('capex_columns') or list(capex_report_data['capex_table'][0].keys())
            pdf.add_table(pd.DataFrame(capex_report_data['capex_table'], columns=capex_columns), title='Tableau CAPEX turbines', max_col_width=38, truncate=26)
        if capex_report_data.get('opex_table_display'):
            pdf.add_table(pd.DataFrame(capex_report_data['opex_table_display']), title='Tableau OPEX', max_col_width=38, truncate=26)

    if oa_report_data:
        pdf.section_title('4. Tarif OA / Prix évité')
        oa_rows = []
        if oa_report_data.get('chute_type') is not None:
            oa_rows.append(['Type de chute', str(oa_report_data.get('chute_type'))])
        if oa_report_data.get('head_m') is not None:
            oa_rows.append(['Hauteur de chute estimee (m)', _format_value(oa_report_data.get('head_m'), digits=1)])
        if oa_report_data.get('tarif_recommande') is not None:
            oa_rows.append(['Tarif recommande (EUR/kWh)', _format_value(oa_report_data.get('tarif_recommande'), digits=3)])
        if oa_report_data.get('tarif_oa') is not None:
            oa_rows.append(['Tarif OA applique (EUR/kWh)', _format_value(oa_report_data.get('tarif_oa'), digits=3)])
        if oa_report_data.get('prix_evite') is not None:
            oa_rows.append(['Prix evite (EUR/kWh)', _format_value(oa_report_data.get('prix_evite'), digits=3)])
        if oa_rows:
            pdf.add_table(pd.DataFrame(oa_rows, columns=['Indicateur', 'Valeur']), title='Synthese OA / prix evite', max_col_width=70, truncate=46)
        if oa_report_data.get('applicable_text'):
            pdf.section_body(oa_report_data.get('applicable_text'))
        if oa_report_data.get('reference_text'):
            pdf.section_body(str(oa_report_data.get('reference_text')))

    if manual_parameters:
        pdf.section_title('5. Paramètres de simulation')
        pdf.add_table(_metric_rows(manual_parameters), title='Paramètres saisis dans Streamlit', max_col_width=70, truncate=46)

    pdf.add_page()
    if report_data.get('energy_metrics'):
        pdf.section_title('6. Résultats énergétiques')
        pdf.add_table(_metric_rows(report_data.get('energy_metrics')), title='Résultats énergétiques affichés', max_col_width=70, truncate=40)
    elif report_data.get('result_summary'):
        pdf.section_title('6. Résultats énergétiques')
        energy_df = pd.DataFrame([
            ['Puissance estimée', f'{puissance_kw:.2f} kW'],
            ['Énergie annuelle', f'{energie_kwh:.0f} kWh/an'],
            ['Autoconsommation', f'{autoconsommation:.0f} kWh/an'],
            ['Taux d autoconsommation', f'{taux_auto:.1f} %'],
        ], columns=['Indicateur', 'Valeur'])
        pdf.add_table(energy_df, title='Bilan énergétique', max_col_width=70, truncate=40)
    else:
        pdf.section_title('6. Résultats énergétiques')
        energy_df = pd.DataFrame([
            ['Puissance estimée', f'{puissance_kw:.2f} kW'],
            ['Énergie annuelle', f'{energie_kwh:.0f} kWh/an'],
            ['Autoconsommation', f'{autoconsommation:.0f} kWh/an'],
            ['Taux d autoconsommation', f'{taux_auto:.1f} %'],
        ], columns=['Indicateur', 'Valeur'])
        pdf.add_table(energy_df, title='Bilan énergétique', max_col_width=70, truncate=40)

    pdf.section_title('7. Résultats économiques')
    if report_data.get('eco_metrics'):
        pdf.add_table(_metric_rows(report_data.get('eco_metrics')), title='Résultats économiques affichés', max_col_width=70, truncate=40)
    else:
        econ_df = pd.DataFrame([
            ['Économies estimées', f'{economie:.0f} EUR/an'],
            ['Revenus injection', f'{revenus:.0f} EUR/an'],
            ['CAPEX brut', f'{capex:.0f} EUR'],
            ['Subvention', f'{subvention_eur:.0f} EUR'],
            ['Subvention (% CAPEX)', f'{subsidy_rate:.1f} %'],
            ['CAPEX net', f'{capex_net:.0f} EUR'],
            ['OPEX', f'{opex:.0f} EUR/an'],
            ['Temps de retour', f'{_format_value(payback, digits=1)} ans'],
            ['VAN', f'{_format_value(van, digits=0)} EUR'],
            ['TRI', f'{_format_value(tri * 100 if tri is not None else None, digits=1)} %'],
            ['Taux d actualisation', f'{discount_rate:.1f} %'],
            ['Durée de vie projet', f'{project_life} ans' if project_life is not None else '-'],
        ], columns=['Indicateur', 'Valeur'])
        pdf.add_table(econ_df, title='Bilan économique', max_col_width=70, truncate=40)

    pdf.add_page()

    if scenario_sections:
        pdf.section_title('8. Scénarios comparés')
        for section in scenario_sections:
            title = section.get('title', 'Scénarios')
            caption = section.get('caption', '')
            scenarios = section.get('scenarios', [])
            pdf.section_body(caption)
            scenario_df = _scenario_rows(scenarios)
            if not scenario_df.empty:
                pdf.add_table(scenario_df, title=title, max_col_width=36, truncate=24)
            else:
                pdf.section_body('Aucun scénario disponible.')
    elif scenarios_injection or scenarios_autoconsommation:
        pdf.section_title('8. Scénarios comparés')
        injection_df = _scenario_rows(scenarios_injection)
        autoconsommation_df = _scenario_rows(scenarios_autoconsommation)
        if not injection_df.empty:
            pdf.add_table(injection_df, title='Scénarios injection réseau', max_col_width=36, truncate=24)
        else:
            pdf.section_body('Aucun scénario injection réseau disponible.')
        if not autoconsommation_df.empty:
            pdf.add_table(autoconsommation_df, title='Scénarios autoconsommation', max_col_width=36, truncate=24)
        else:
            pdf.section_body('Aucun scénario autoconsommation disponible.')

    pdf.add_page()
    if recommendation_general_text:
        pdf.section_title('9. Recommandation')
        pdf.section_body(str(recommendation_general_text))
        if recommendation_detail_text:
            pdf.section_body(str(recommendation_detail_text))
        if recommendation_type:
            detail_rows = [['Turbine', str(recommendation_type)]]
            if recommendation_metrics:
                for label, value in recommendation_metrics:
                    detail_rows.append([label, value])
            pdf.add_table(pd.DataFrame(detail_rows, columns=['Indicateur', 'Valeur']), title='Synthese recommandation', max_col_width=70, truncate=46)
        elif recommendation_fallback_text:
            pdf.section_body(str(recommendation_fallback_text))
    elif ai_recommendation:
        pdf.section_title('9. Recommandation')
        pdf.section_body(str(ai_recommendation))

    pdf.section_title('10. Conclusion')
    pdf.section_body(
        "Le rapport de site consolide les étapes de simulation, de la caractérisation hydraulique à l'évaluation économique. "
        "Il peut servir de base à la validation terrain et au dimensionnement détaillé."
        )

    pdf.output(output_path)
    return output_path


import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power
from modules.scoring import score_sites
from modules.turbine import load_turbine_db
from modules import productible


def propose_turbines(site_row, turbine_db, top_n=3):
    pressure = site_row['delta_p']
    flow = site_row['estimated_flow']
    diameter = site_row.get('diameter', 0)
    pressure_tol = 0.2 * pressure if pressure > 0 else 0.2
    flow_tol = 0.2 * flow if flow > 0 else 0.2
    diameter_tol = 20
    details = []
    for _, t in turbine_db.iterrows():
        compatible = (
            (t['pression_min_bar'] <= pressure + pressure_tol) and
            (t['pression_max_bar'] >= pressure - pressure_tol) and
            (t['debit_min_m3h'] <= flow + flow_tol) and
            (t['debit_max_m3h'] >= flow - flow_tol) and
            (t['diametre_mm'] <= diameter + diameter_tol) and
            (t['diametre_mm'] >= diameter - diameter_tol)
        )
        details.append(compatible)
    candidates = turbine_db[details].copy()
    return candidates.head(top_n)


def add_plot_image(pdf, fig, title):
    pdf.section_body(title)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        fig.savefig(tmp_file.name, dpi=140, bbox_inches="tight")
        plt.close(fig)
        pdf.image(tmp_file.name, w=170)


def generate_site_pdf_weasy(
    output_path,
    site_row,
    selected_turbine,
    productible_result,
    economie=0,
    revenus=0,
    autoconsommation=0,
    taux_auto=0,
    mode='autoconsommation',
    prix_elec=0.18,
    heures_fonctionnement=6500,
    conso_site=0,
    turbines_df=None,
    ai_recommendation=None,
    rank=None,
    total_sites=None,
    lat=None,
    lon=None,
    tarif_oa=None,
    prix_evite=None,
    site_key=None,
    capex=0,
    opex=0,
    payback=None,
    subsidy_rate=0,
    subvention_eur=0,
    capex_net=None,
    van=None,
    tri=None,
    discount_rate=None,
    project_life_years=None,
    streamlit_url=None,
    site_tab_label=None,
):
    try:
        from weasyprint import HTML, CSS
    except Exception:
        raise RuntimeError('WeasyPrint not installed in the environment')

    # Load template
    tpl_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'report_template.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl = f.read()

    site_name = str(site_row.get('site_name', 'Site'))
    date = datetime.utcnow().strftime('%Y-%m-%d')
    author = 'SimuWatter'

    # KPIs blocks
    kpis = {
        'Puissance (kW)': f"{float(productible_result.get('puissance_kw', 0)):.2f}",
        'Énergie (kWh/an)': f"{float(productible_result.get('energie_kwh', 0)):.0f}",
        'VAN (EUR)': f"{van:.0f}" if van is not None else '-',
        'Payback (ans)': f"{payback:.1f}" if payback is not None else '-',
    }
    kpi_blocks = ''
    for name, val in kpis.items():
        kpi_blocks += f"<div class='kpi'><strong>{name}</strong><div>{val}</div></div>"

    summary = ai_recommendation if ai_recommendation else 'Synthèse non disponible.'

    # Site params
    debit_m3h = float(site_row.get('estimated_flow', 0) or 0)
    pression_bar = float(site_row.get('delta_p', 0) or 0)
    site_params = (
        f"Débit moyen: {debit_m3h:.1f} m3/h<br/>"
        f"Pression: {pression_bar:.2f} bar<br/>"
        f"Heures de fonctionnement/an: {heures_fonctionnement}<br/>"
        f"Consommation site: {conso_site} kWh/an<br/>"
    )

    # Map image if available
    map_img = ''
    if lat is not None and lon is not None:
        try:
            map_path = fetch_osm_static_map(lat, lon, zoom=16)
            map_img = f"<div class='figure'><img src='file://{map_path}' style='width:320px'/></div>"
        except Exception:
            map_img = ''

    # Turbine table
    turbine_table = ''
    try:
        if isinstance(selected_turbine, dict) or hasattr(selected_turbine, 'to_dict'):
            df = pd.DataFrame([selected_turbine])
        else:
            df = pd.DataFrame([selected_turbine.to_dict()])
        turbine_table = df.to_html(index=False, classes='table', border=0)
    except Exception:
        turbine_table = ''

    # Figures (productible, power)
    figures_html = ''
    # power curve
    if productible_result is not None and hasattr(productible_result, 'get'):
        power_curve = productible_result.get('power_curve')
        if power_curve is not None and isinstance(power_curve, pd.DataFrame):
            fig, ax = plt.subplots(figsize=(6,3))
            ax.plot(power_curve['flow'], power_curve['power'])
            ax.set_xlabel('Débit (m³/h)')
            ax.set_ylabel('Puissance (kW)')
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            fig.savefig(tmp.name, dpi=140, bbox_inches='tight')
            plt.close(fig)
            figures_html += f"<div class='figure'><img src='file://{tmp.name}' style='width:420px'/></div>"

    # productible curve
    productible_curve = productible_result.get('productible_curve') if productible_result is not None else None
    if productible_curve is not None and isinstance(productible_curve, pd.DataFrame):
        fig, ax = plt.subplots(figsize=(6,3))
        ax.plot(productible_curve['x'], productible_curve['y'])
        ax.set_xlabel('x')
        ax.set_ylabel('Productible')
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        fig.savefig(tmp.name, dpi=140, bbox_inches='tight')
        plt.close(fig)
        figures_html += f"<div class='figure'><img src='file://{tmp.name}' style='width:420px'/></div>"

    economic_summary = (
        f"CAPEX: {capex:.0f} EUR - OPEX: {opex:.0f} EUR/an - Subventions: {subvention_eur:.0f} EUR"
    )

    logo_path = os.path.join(os.path.dirname(__file__), '..', 'Image1.png')
    html = tpl.format(
        site_name=site_name,
        date=date,
        author=author,
        kpi_blocks=kpi_blocks,
        summary=summary,
        site_params=site_params,
        map_img=map_img,
        turbine_table=turbine_table,
        figures=figures_html,
        economic_summary=economic_summary,
        logo_path=logo_path,
    )

    HTML(string=html, base_url=os.path.dirname(tpl_path)).write_pdf(output_path)


def fetch_osm_static_map(lat, lon, zoom=16, size="640x420"):
    url = (
        "https://staticmap.openstreetmap.de/staticmap.php"
        f"?center={lat},{lon}"
        f"&zoom={zoom}"
        f"&size={size}"
        f"&markers={lat},{lon},red"
        "&maptype=mapnik"
    )
    tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_file.close()
    urllib.request.urlretrieve(url, tmp_file.name)
    return tmp_file.name


def capture_streamlit_views(streamlit_url, site_tab_label):
    # Playwright-based UI capture is unsupported in this Windows environment.
    # Return empty dict so PDF generation proceeds without screenshots.
    if os.name == 'nt':
        return {}

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    def click_element(page, role, name):
        try:
            locator = page.get_by_role(role, name=name)
            if locator.count() > 0:
                locator.first.click()
                return True
        except Exception:
            pass
        try:
            locator = page.get_by_text(name, exact=False)
            if locator.count() > 0:
                locator.first.click()
                return True
        except Exception:
            pass
        try:
            locator = page.locator(f'button:has-text("{name}")')
            if locator.count() > 0:
                locator.first.click()
                return True
        except Exception:
            pass
        return False

    def screenshot_app_area(page, path):
        main_area = None
        try:
            candidate = page.locator("main").first
            if candidate.count() > 0:
                main_area = candidate
        except Exception:
            main_area = None
        if main_area is None:
            try:
                candidate = page.locator("div[data-testid='stApp']").first
                if candidate.count() > 0:
                    main_area = candidate
            except Exception:
                main_area = None
        if main_area is not None:
            try:
                main_area.screenshot(path=path)
                return True
            except Exception:
                pass
        try:
            page.screenshot(path=path, full_page=True)
            return True
        except Exception:
            return False

    screenshots = {}
    step_buttons = [
        "1) Sélection turbine",
        "2) Estimation CAPEX/OPEX",
        "3) OA / Prix évité",
        "4) Estimations",
        "5) Recommandation",
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1400})
            page.goto(streamlit_url, wait_until="networkidle", timeout=30000)
            page.wait_for_load_state("networkidle")

            click_element(page, "tab", "Simulation")
            if site_tab_label:
                click_element(page, "tab", site_tab_label)
            page.wait_for_timeout(1400)

            for step in step_buttons:
                if click_element(page, "button", step):
                    page.wait_for_timeout(1400)
                    tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    tmp_file.close()
                    if screenshot_app_area(page, tmp_file.name):
                        screenshots[step] = tmp_file.name

            browser.close()
    except NotImplementedError:
        # Try subprocess fallback below
        pass
    except Exception:
        # Try subprocess fallback below
        pass

    # If in-process capture failed (or Playwright not usable), try running
    # a helper Python subprocess that uses Playwright. This avoids issues
    # with the current asyncio event loop on some Windows installs.
    if not screenshots:
        script = tempfile.NamedTemporaryFile(suffix="_pw_helper.py", delete=False)
        script_path = script.name
        script.close()
        helper_code = """
import sys, json, tempfile
from playwright.sync_api import sync_playwright

streamlit_url = sys.argv[1]
site_tab_label = sys.argv[2] if len(sys.argv) > 2 else ''

def click_element(page, role, name):
    try:
        locator = page.get_by_role(role, name=name)
        if locator.count() > 0:
            locator.first.click()
            return True
    except Exception:
        pass
    try:
        locator = page.get_by_text(name, exact=False)
        if locator.count() > 0:
            locator.first.click()
            return True
    except Exception:
        pass
    try:
        locator = page.locator(f'button:has-text("{{name}}")')
        if locator.count() > 0:
            locator.first.click()
            return True
    except Exception:
        pass
    return False

def screenshot_app_area(page):
    try:
        candidate = page.locator('main').first
        if candidate.count() > 0:
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp.close()
            candidate.screenshot(path=tmp.name)
            return tmp.name
    except Exception:
        pass
    try:
        candidate = page.locator("div[data-testid='stApp']").first
        if candidate.count() > 0:
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp.close()
            candidate.screenshot(path=tmp.name)
            return tmp.name
    except Exception:
        pass
    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp.close()
        page.screenshot(path=tmp.name, full_page=True)
        return tmp.name
    except Exception:
        return None

step_buttons = [
    "1) Sélection turbine",
    "2) Estimation CAPEX/OPEX",
    "3) OA / Prix évité",
    "4) Estimations",
    "5) Recommandation",
]

results = {}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1400})
        page.goto(streamlit_url, wait_until='networkidle', timeout=30000)
        page.wait_for_load_state('networkidle')
        click_element(page, 'tab', 'Simulation')
        if site_tab_label:
            click_element(page, 'tab', site_tab_label)
        page.wait_for_timeout(1400)
        for step in step_buttons:
            if click_element(page, 'button', step):
                page.wait_for_timeout(1400)
                path = screenshot_app_area(page)
                if path:
                    results[step] = path
        browser.close()
except Exception:
    pass

print(json.dumps(results))
"""
        try:
            with open(script_path, 'w', encoding='utf8') as f:
                f.write(helper_code)
            args = [sys.executable, script_path, streamlit_url or '', site_tab_label or '']
            proc = subprocess.run(args, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0 and proc.stdout:
                try:
                    results = json.loads(proc.stdout)
                    # ensure keys map to files
                    for k, v in results.items():
                        if os.path.exists(v):
                            screenshots[k] = v
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                os.remove(script_path)
            except Exception:
                pass

    return screenshots


def add_screenshot_page(pdf, title, image_path):
    pdf.add_page(orientation='L')
    pdf.section_title(title)
    try:
        pdf.image(image_path, x=10, y=pdf.get_y(), w=pdf.w - 20)
    except Exception:
        pass


def generate_site_pdf(
    output_path,
    site_row,
    selected_turbine,
    productible_result,
    economie,
    revenus,
    autoconsommation,
    taux_auto,
    mode,
    prix_elec,
    heures_fonctionnement,
    conso_site,
    tarif_oa=None,
    prix_evite=None,
    turbines_df=None,
    ai_recommendation=None,
    rank=None,
    total_sites=None,
    lat=None,
    lon=None,
    capex=0,
    opex=0,
    payback=None,
    subsidy_rate=0,
    subvention_eur=0,
    capex_net=None,
    van=None,
    tri=None,
    discount_rate=None,
    project_life_years=None,
    streamlit_url=None,
    site_tab_label=None,
    pdf=None,
):
    internal_pdf = pdf is None
    if pdf is None:
        pdf = SimuWatterPDF()
    # Defer building cover/toc until after we compute site-level KPIs

    site_name = str(site_row.get("site_name", "Site"))

    puissance_kw = float(productible_result.get("puissance_kw", 0))
    energie_kwh = float(productible_result.get("energie_kwh", 0))
    debit_m3h = float(site_row.get("estimated_flow", 0))
    pression_bar = float(site_row.get("delta_p", 0))

    # If this is a single-site PDF (no external pdf passed), build the
    # branded cover, TOC and executive synthesis pages first.
    if internal_pdf:
        try:
            build_cover(pdf, site_name)
            build_toc(pdf)
            # small executive summary assembled from key values
            summary = (
                f"Recommandation générale : voir détails. KPI clés - Puissance estimée: {puissance_kw:.2f} kW; "
                f"Énergie annuelle: {energie_kwh:.0f} kWh; VAN: {van if van is not None else '-'}; "
                f"Temps de retour: {payback if payback is not None else '-'} ans."
            )
            kpis = {
                'Puissance (kW)': f"{puissance_kw:.2f}",
                'Énergie (kWh/an)': f"{energie_kwh:.0f}",
                'VAN (EUR)': f"{van:.0f}" if van is not None else '-',
                'Payback (ans)': f"{payback:.1f}" if payback is not None else '-',
            }
            build_synthesis(pdf, summary, kpis)
            # After synthesis page, start a fresh content page
            try:
                pdf.add_page()
            except Exception:
                pass
        except Exception:
            # if any template build fails, create a default page
            try:
                pdf.add_page()
            except Exception:
                pass
    else:
        try:
            pdf.add_page()
        except Exception:
            pass

    # 1. Caractéristiques du site
    pdf.section_title("1. Caractéristiques du site")
    pdf.section_body(
        "Ce rapport présente une estimation du productible hydroélectrique pour un site du réseau.\n"
        "L'objectif est de qualifier le potentiel, les turbines compatibles, et les impacts économiques."
    )
    if lat is not None and lon is not None:
        try:
            map_path = fetch_osm_static_map(lat, lon, zoom=16)
            pdf.image(map_path, w=170)
        except Exception:
            pass
    classement = ""
    if rank is not None and total_sites is not None:
        classement = f"Classement: {rank}/{total_sites}\n"
    tarif_oa_text = f"- Tarif injection OA: {tarif_oa:.3f} EUR/kWh\n" if tarif_oa is not None else ""
    prix_evite_text = f"- Prix évité: {prix_evite:.3f} EUR/kWh\n" if prix_evite is not None else ""
    pdf.section_body(
        classement +
        "Paramètres du site\n"
        f"- Débit moyen: {debit_m3h:.1f} m3/h\n"
        f"- Pression amont: {pression_bar:.2f} bar\n"
        f"- Heures de fonctionnement/an: {heures_fonctionnement}\n"
        f"- Mode: {mode}\n"
        f"- Consommation site: {conso_site} kWh/an\n"
        f"- Prix électricité: {prix_elec} EUR/kWh\n"
        f"{tarif_oa_text}"
        f"{prix_evite_text}"
        f"- Puissance estimée: {puissance_kw:.2f} kW\n"
        f"- Énergie annuelle: {energie_kwh:.0f} kWh/an\n"
    )
    if streamlit_url:
        streamlit_views = capture_streamlit_views(streamlit_url, site_tab_label)
        if streamlit_views:
            for step_name, image_path in streamlit_views.items():
                if image_path:
                    add_screenshot_page(pdf, f"Capture - {step_name}", image_path)


    # 2. Sélection de la turbine (version enrichie)
    pdf.section_title("2. Sélection de la turbine")
    # Tableau détaillé de la turbine sélectionnée
    turbine_df = pd.DataFrame([{
        "Type": selected_turbine.get("type_turbine"),
        "Diamètre (mm)": selected_turbine.get("diametre_mm"),
        "Puissance min (kW)": selected_turbine.get("puissance_min_kw"),
        "Puissance max (kW)": selected_turbine.get("puissance_max_kw"),
        "Rendement typique": selected_turbine.get("rendement_typique"),
        "Source": selected_turbine.get("source"),
    }])
    pdf.add_table(turbine_df, title="Turbine sélectionnée", max_col_width=40, truncate=24)

    # Tableau complet des turbines compatibles
    if turbines_df is not None and not turbines_df.empty:
        display_cols = [
            'type_turbine', 'diametre_mm', 'pression_min_bar', 'pression_max_bar',
            'debit_min_m3h', 'debit_max_m3h', 'puissance_min_kw', 'puissance_max_kw',
            'rendement_typique', 'prix_estime_eur', 'description', 'source'
        ]
        cols = [c for c in display_cols if c in turbines_df.columns]
        if cols:
            pdf.add_table(turbines_df[cols], title="Tableau complet des turbines compatibles", max_col_width=40, truncate=24)

        # Explications pédagogiques pour chaque turbine
        descriptions = []
        for _, t in turbines_df.iterrows():
            desc = str(t.get("description", "")).strip()
            source = str(t.get("source", "")).strip()
            if desc:
                line = f"- {t.get('type_turbine', 'Turbine')} {t.get('diametre_mm', '')}mm: {desc}"
                if source:
                    line += f" (src: {source})"
                descriptions.append(line)
        if descriptions:
            pdf.section_body("Explications pédagogiques sur les turbines compatibles :\n" + "\n".join(descriptions))

    # Synthèse IA/recommandation (si disponible)
    # (IA recommendation will be shown in synthesis section later)

    # Graphique de puissance (si productible_result contient une courbe)
    if productible_result is not None and hasattr(productible_result, 'get'):
        power_curve = productible_result.get('power_curve')
        if power_curve is not None and isinstance(power_curve, pd.DataFrame):
            fig, ax = plt.subplots(figsize=(5,3))
            ax.plot(power_curve['flow'], power_curve['power'], label='Courbe Puissance')
            ax.set_xlabel('Débit (m³/h)')
            ax.set_ylabel('Puissance (kW)')
            ax.set_title('Courbe de puissance de la turbine sélectionnée')
            ax.legend()
            add_plot_image(pdf, fig, "Courbe de puissance de la turbine sélectionnée")


    # 3. Estimation du Capex/Opex (version enrichie)
    pdf.section_title("3. Estimation du Capex/Opex")
    capex_net_value = capex_net if capex_net is not None else capex - subvention_eur
    pdf.section_body(
        "**Structure du CAPEX**\n"
        "- CAPEX fixe (projet) : études, cadrage, ingénierie, démarches, coordination.\n"
        "- CAPEX de base : équipements hydrauliques + électriques (inclut la turbine).\n"
        "- Intégration hydraulique : complexité d'installation sur site.\n"
        "- Raccordement électrique : distance au point de connexion et complexité réseau.\n"
        "\n**Paramètres utilisés**\n"
        f"- Distance à l'installation : voir données site.\n"
        f"- Type d'installation électrique + distance poste : voir données site.\n"
        f"- Prix turbine : inclus dans le tableau turbine.\n"
        "\n**OPEX (ordre de grandeur)**\n"
        "- Micro-inline / pico-inline : 1.5% à 3% de C_equip (≈ 200 à 600 EUR/an).\n"
        "- PAT (Pump As Turbine) : 2% à 4% de C_equip (≈ 300 à 900 EUR/an).\n"
        "\n**Synthèse valeurs**\n"
        f"- CAPEX: {capex:.0f} EUR\n"
        f"- Subventions (taux): {subsidy_rate:.1f} %\n"
        f"- Subventions (montant): {subvention_eur:.0f} EUR\n"
        f"- CAPEX net: {capex_net_value:.0f} EUR\n"
        f"- OPEX: {opex:.0f} EUR/an\n"
    )

    # Graphique de productible (si disponible)
    if productible_result is not None and hasattr(productible_result, 'get'):
        productible_curve = productible_result.get('productible_curve')
        if productible_curve is not None and isinstance(productible_curve, pd.DataFrame):
            fig, ax = plt.subplots(figsize=(5,3))
            ax.plot(productible_curve['x'], productible_curve['y'], label='Courbe Productible')
            ax.set_xlabel('Temps ou débit')
            ax.set_ylabel('Productible (kWh/an)')
            ax.set_title('Courbe de productible estimé')
            ax.legend()
            add_plot_image(pdf, fig, "Courbe de productible estimé")


    # 4. Analyse économique (version enrichie)
    pdf.section_title("4. Analyse économique")
    payback_text = f"{payback:.1f} ans" if payback is not None else "-"
    tri_text = f"{tri * 100:.1f} %" if tri is not None else "-"
    van_text = f"{van:.0f} EUR" if van is not None else "-"
    discount_text = f"{discount_rate:.1f} %" if discount_rate is not None else "-"
    life_text = f"{int(project_life_years)} ans" if project_life_years is not None else "-"
    pdf.section_body(
        "**Synthèse économique**\n"
        f"- Économies estimées: {economie:.0f} EUR/an\n"
        f"- Revenus injection: {revenus:.0f} EUR/an\n"
        f"- Énergie autoconsommée: {autoconsommation:.0f} kWh/an\n"
        f"- Taux autoconsommation: {taux_auto:.1f} %\n"
        f"- Temps de retour: {payback_text}\n"
        f"- VAN: {van_text}\n"
        f"- TRI: {tri_text}\n"
        f"- Taux d'actualisation: {discount_text}\n"
        f"- Durée de vie projet: {life_text}\n"
    )

    # Synthèse IA et recommandation pédagogique (si disponible)
    if ai_recommendation:
        pdf.section_title("Synthèse IA et recommandation pédagogique")
        pdf.section_body(str(ai_recommendation))

    pdf.section_title("5. Conclusion")
    pdf.section_body(
        "Le site présente un potentiel exploitable si les contraintes hydrauliques et d'exploitation sont confirmées. "
        "La turbine sélectionnée est recommandée à titre indicatif, sous réserve de vérification terrain."
    )

    # Force sanitize all pages to latin-1 to avoid encoding errors in FPDF
    for idx, page in enumerate(list(pdf.pages)):
        try:
            if isinstance(page, (bytes, bytearray)):
                s = page.decode('latin-1', 'replace')
            else:
                s = str(page)
            # report any non-latin1 chars for diagnosis
            nonlatin = [(i, ord(ch), ch) for i, ch in enumerate(s) if ord(ch) > 255]
            if nonlatin:
                print(f"[DEBUG] page {idx} has {len(nonlatin)} non-latin chars; sample={nonlatin[:3]}")
                start = max(0, nonlatin[0][0] - 40)
                print(s[start:start+120])
            # replace unencodable chars
            replaced = s.encode('latin-1', 'replace').decode('latin-1')
            pdf.pages[idx] = replaced
        except Exception as exc:
            print(f"[DEBUG] sanitization failed for page {idx}: {exc}")
            try:
                pdf.pages[idx] = str(page).encode('latin-1', 'replace').decode('latin-1')
            except Exception:
                pdf.pages[idx] = ''

    pdf.output(output_path)

def generate_pdf(output_path, csv_path='data/prv.csv', turbine_db_path=None):
    # Génération multi-sites : une page complète par site
    raw_dict = load_data({'prv': csv_path})
    raw_df = raw_dict['prv']
    flow_df = compute_hydraulics(raw_df)
    power_df = compute_power(flow_df)
    score_df = score_sites(flow_df)
    results = flow_df.copy()
    results['power_kW'] = power_df['power'] / 1000
    results['score'] = score_df['score']
    results_sorted = results.sort_values('score', ascending=False)
    turbine_db = load_turbine_db(turbine_db_path)

    pdf = SimuWatterPDF()
    for idx, site_row in results_sorted.iterrows():
        turbines_df = propose_turbines(site_row, turbine_db, top_n=3)
        selected_turbine = turbines_df.iloc[0] if not turbines_df.empty else {}
        pdf = generate_site_pdf(
            output_path=None,
            site_row=site_row,
            selected_turbine=selected_turbine,
            productible_result={},
            economie=0,
            revenus=0,
            autoconsommation=0,
            taux_auto=0,
            mode='autoconsommation',
            prix_elec=0.18,
            heures_fonctionnement=6500,
            conso_site=10000,
            turbines_df=turbines_df,
            ai_recommendation=None,
            rank=idx + 1,
            total_sites=len(results_sorted),
            lat=site_row.get('lat_wgs84'),
            lon=site_row.get('lon_wgs84'),
            capex=9000,
            opex=630,
            payback=0,
            subsidy_rate=0,
            subvention_eur=0,
            capex_net=9000,
            van=0,
            tri=0,
            discount_rate=5.0,
            project_life_years=20,
            streamlit_url=None,
            site_tab_label=None,
            pdf=pdf,
        )

    pdf.output(output_path)
if __name__ == '__main__':
    generate_pdf('outputs/rapport_simu_watter.pdf')
