"""
Composants Streamlit pour l'affichage des analyses financières et de sensibilité.
"""

import streamlit as st
import pandas as pd
import numpy as np
from modules.finances import (
    compute_opex, compute_production_annual, compute_revenues,
    compute_net_revenue, compute_payback_period, compute_npv,
    compute_profitability_indicators, sensitivity_analysis,
    format_financial_summary
)


def clean_dataframe_for_streamlit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie un DataFrame pour le rendre compatible avec Streamlit.
    - Remplace NaN/None par 0.0
    - Convertit tous les types en types sérialisables
    - Réinitialise les indices
    """
    df = df.copy().reset_index(drop=True)
    
    for col in df.columns:
        if col == 'site_name':
            # Pour site_name, remplace NaN par une chaîne vide
            df[col] = df[col].fillna('').astype(str)
        elif df[col].dtype == 'object':
            # Pour les colonnes objet, convertis en str ou float si possible
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            except:
                df[col] = df[col].fillna('').astype(str)
        else:
            # Pour les colonnes numériques, remplace NaN par 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    
    return df


def render_opex_section(results_with_power: pd.DataFrame):
    """
    Affiche la section OPEX (8. Coûts d'exploitation annuels).
    
    Méthodologie: OPEX = 4% × Coût équipements
    """
    st.subheader("8. Coûts d'exploitation annuels (OPEX)")
    st.caption("OPEX = 4% × Coût des équipements par an (turbine, génératrice, armoire, capteurs)")
    
    # Nettoyer le DataFrame
    df = clean_dataframe_for_streamlit(results_with_power)
    
    opex_rows = []
    for _, row in df.iterrows():
        # Estimation: 70% du CAPEX nominal pour les équipements
        capex_equipement = float(row.get('capex_nominal', 0)) * 0.7
        opex_data = compute_opex(capex_equipement)
        
        opex_rows.append({
            "Site": str(row.get('site_name', '')),
            "Coût équip. (€)": f"{capex_equipement:,.0f}",
            "OPEX annuel (€/an)": f"{opex_data['opex_annual']:,.0f}",
            "Taux": opex_data['opex_percentage']
        })
    
    if opex_rows:
        st.dataframe(pd.DataFrame(opex_rows), use_container_width=True, hide_index=True)


def render_production_revenue_section(results_with_power: pd.DataFrame):
    """
    Affiche la section Production et Revenus (9. Production annuelle et revenus).
    
    Méthodologie:
    - Production = Pe (kW) × 7000 h/an
    - Deux scénarios: OA (0,12 €/kWh) et autoconso (0,20 €/kWh)
    """
    st.subheader("9. Production annuelle et revenus")
    st.caption("Production = Puissance (kW) × 7000 h/an | OA: 0,12 €/kWh | Autoconso: 0,20 €/kWh")
    
    # Nettoyer le DataFrame
    df = clean_dataframe_for_streamlit(results_with_power)
    
    col1, col2 = st.columns([1.2, 1], gap="large")
    
    production_rows = []
    for _, row in df.iterrows():
        power_kw = float(row.get('power_kW', 0.0))
        
        # Production
        prod_data = compute_production_annual(power_kw)
        production = prod_data['production_annual_kwh']
        
        # Revenus OA
        revenue_oa = compute_revenues(power_kw, scenario="OA")
        revenue_oa_value = revenue_oa['revenue_annual']
        
        # Revenus Autoconso
        revenue_autoconso = compute_revenues(power_kw, scenario="autoconso")
        revenue_autoconso_value = revenue_autoconso['revenue_annual']
        
        production_rows.append({
            "Site": str(row.get('site_name', '')),
            "Débit (m³/h)": f"{float(row.get('estimated_flow_obs', 0)):.2f}",
            "Pe (kW)": f"{power_kw:.2f}",
            "Production (kWh/an)": f"{production:,.0f}",
            "Revenu OA (€/an)": f"{revenue_oa_value:,.0f}",
            "Revenu autoconso (€/an)": f"{revenue_autoconso_value:,.0f}"
        })
    
    with col1:
        with st.expander("Détails de production et revenus", expanded=True):
            st.dataframe(pd.DataFrame(production_rows), use_container_width=True, height=400)
    
    with col2:
        with st.container(border=True):
            if production_rows:
                df_prod = pd.DataFrame(production_rows)
                # Conversion pour graphique
                try:
                    df_prod['Production'] = df_prod['Production (kWh/an)'].str.replace(',', '').astype(float)
                    df_prod['Revenue_OA'] = df_prod['Revenu OA (€/an)'].str.replace(',', '').astype(float)
                    
                    kpi_cols = st.columns(3, gap="medium")
                    kpi_cols[0].metric("Prod. moy. (kWh/an)", f"{df_prod['Production'].mean():,.0f}")
                    kpi_cols[1].metric("Prod. max (kWh/an)", f"{df_prod['Production'].max():,.0f}")
                    kpi_cols[2].metric("Prod. min (kWh/an)", f"{df_prod['Production'].min():,.0f}")
                    
                    st.write("Production annuelle par site")
                    st.bar_chart(df_prod.set_index('Site')['Production'])
                except:
                    st.info("Graphique en préparation...")


def render_profitability_section(results_with_power: pd.DataFrame):
    """
    Affiche la section Indicateurs de rentabilité (10. VAN, Payback, Priorité).
    
    Méthodologie:
    - Payback = CAPEX / Revenu net annuel
    - VAN = Σ(Revenu net / (1+4%)^année) - CAPEX (20 ans)
    - Priorité selon VAN OA
    """
    st.subheader("10. Indicateurs de rentabilité (VAN, Payback, Priorité)")
    st.caption("Scénario nominal: CAPEX milieu fourchette, revenus OA, 4% actualisation, 20 ans")
    
    # Nettoyer le DataFrame
    df = clean_dataframe_for_streamlit(results_with_power)
    
    profitability_rows = []
    for _, row in df.iterrows():
        power_kw = float(row.get('power_kW', 0.0))
        capex_nominal = float(row.get('capex_nominal', 0.0))
        capex_equipement = capex_nominal * 0.7
        
        # Revenue net OA
        revenue_net_oa = compute_net_revenue(power_kw, capex_equipement, scenario="OA")
        
        # Revenue net Autoconso
        revenue_net_autoconso = compute_net_revenue(power_kw, capex_equipement, scenario="autoconso")
        
        # Payback OA
        payback_oa = compute_payback_period(capex_nominal, revenue_net_oa['revenue_net_annual'])
        
        # Payback Autoconso
        payback_autoconso = compute_payback_period(capex_nominal, revenue_net_autoconso['revenue_net_annual'])
        
        # VAN OA
        npv_oa = compute_npv(capex_nominal, revenue_net_oa['revenue_net_annual'])
        
        # Determine priority
        if npv_oa['npv'] > 50000:
            priority = "★★★★ Prioritaire"
        elif npv_oa['npv'] > 10000:
            priority = "★★★ Viable"
        elif npv_oa['npv'] > 0:
            priority = "★★ Viable avec aide"
        elif npv_oa['npv'] > -5000:
            priority = "★ Sous conditions"
        else:
            priority = "★ Non rentable seul"
        
        profitability_rows.append({
            "Site": str(row.get('site_name', '')),
            "CAPEX (€)": f"{capex_nominal:,.0f}",
            "Rev. net OA (€/an)": f"{revenue_net_oa['revenue_net_annual']:,.0f}",
            "Retour OA (ans)": f"{payback_oa['payback_years']:.1f}" 
                if payback_oa['payback_years'] != float('inf') else "N/A",
            "Retour autoconso (ans)": f"{payback_autoconso['payback_years']:.1f}"
                if payback_autoconso['payback_years'] != float('inf') else "N/A",
            "VAN 20 ans (€)": f"{npv_oa['npv']:+,.0f}",
            "Priorité": priority
        })
    
    if profitability_rows:
        st.dataframe(pd.DataFrame(profitability_rows), use_container_width=True, height=400)
        
        # Synthèse commentée
        with st.expander("Interprétation des résultats", expanded=False):
            st.markdown("""
            **Payback Period (Retour sur investissement):**
            - < 5 ans: Excellent
            - 5-10 ans: Bon
            - 10-20 ans: Acceptable
            - > 20 ans: Faible
            
            **VAN 20 ans (Valeur Actuelle Nette):**
            - > 50 000 €: Projet prioritaire (★★★★)
            - 10 000-50 000 €: Projet viable (★★★)
            - 0-10 000 €: Viable avec aide (★★)
            - -5 000-0 €: Sous conditions (★)
            - < -5 000 €: Non rentable seul
            
            **Scénarios:**
            - **OA** (Obligation d'Achat): 0,12 €/kWh - Tarif régulé, sûr
            - **Autoconso**: 0,20 €/kWh - Plus lucratif si faisable
            """)


def render_sensitivity_section(results_with_power: pd.DataFrame):
    """
    Affiche l'analyse de sensibilité (11. Variations sur paramètres clés).
    
    Variables: prix électricité, débit, disponibilité turbine, subventions
    """
    st.subheader("11. Analyse de sensibilité")
    st.caption("Impact des variations clés sur les revenus et indicateurs")
    
    if len(results_with_power) == 0:
        st.warning("Aucun site à analyser")
        return
    
    # Nettoyer le DataFrame pour Streamlit
    results_clean = clean_dataframe_for_streamlit(results_with_power)
    
    # Filtrer les lignes avec site_name valide
    valid_mask = results_clean['site_name'].astype(str).str.strip() != ''
    valid_rows = results_clean[valid_mask].copy()
    
    if len(valid_rows) == 0:
        st.warning("Aucun site avec nom valide à analyser")
        return
    
    site_names = valid_rows['site_name'].astype(str).tolist()
    
    # Sélectionner un site
    selected_site_name = st.selectbox(
        "Sélectionner un site pour analyse détaillée",
        site_names,
        key="sensitivity_selectbox"
    )
    
    # Récupérer l'index du site sélectionné
    selected_site_idx = valid_rows[valid_rows['site_name'] == selected_site_name].index[0]
    row = results_clean.loc[selected_site_idx]
    
    power_kw = float(row.get('power_kW', 0.0))
    capex_nominal = float(row.get('capex_nominal', 0.0))
    capex_equipement = capex_nominal * 0.7
    
    # Exécuter analyse sensibilité
    sensitivity_df = sensitivity_analysis(capex_nominal, power_kw, capex_equipement)
    
    # Afficher résultats par variable
    col1, col2 = st.columns(2, gap="medium")
    
    with col1:
        st.write("**Sensibilité au prix de l'électricité:**")
        price_sens = sensitivity_df[sensitivity_df['variable'] == 'Prix électricité']
        st.dataframe(price_sens[['scenario', 'impact_revenu_annuel', 'payback_years']].rename(
            columns={
                'scenario': 'Tarif',
                'impact_revenu_annuel': 'Revenu (€/an)',
                'payback_years': 'Payback (ans)'
            }
        ), use_container_width=True, hide_index=True)
        
        st.write("**Sensibilité au débit réel:**")
        flow_sens = sensitivity_df[sensitivity_df['variable'] == 'Débit réel']
        st.dataframe(flow_sens[['scenario', 'impact_revenu_annuel', 'payback_years']].rename(
            columns={
                'scenario': 'Variation',
                'impact_revenu_annuel': 'Revenu (€/an)',
                'payback_years': 'Payback (ans)'
            }
        ), use_container_width=True, hide_index=True)
    
    with col2:
        st.write("**Sensibilité à la disponibilité turbine:**")
        avail_sens = sensitivity_df[sensitivity_df['variable'] == 'Disponibilité turbine']
        st.dataframe(avail_sens[['scenario', 'impact_revenu_annuel', 'payback_years']].rename(
            columns={
                'scenario': 'Disponibilité',
                'impact_revenu_annuel': 'Revenu (€/an)',
                'payback_years': 'Payback (ans)'
            }
        ), use_container_width=True, hide_index=True)
        
        st.write("**Impact d'une subvention CAPEX (-30%):**")
        subsidy_sens = sensitivity_df[sensitivity_df['variable'] == 'Subvention CAPEX']
        st.dataframe(subsidy_sens[['scenario', 'impact_revenu_annuel', 'payback_years', 'npv_20ans']].rename(
            columns={
                'scenario': 'Subvention',
                'impact_revenu_annuel': 'Revenu (€/an)',
                'payback_years': 'Payback (ans)',
                'npv_20ans': 'VAN 20 ans (€)'
            }
        ), use_container_width=True, hide_index=True)


def render_comparative_summary(results_with_power: pd.DataFrame):
    """
    Affiche le tableau synthèse comparative final (12. Synthèse comparative).
    
    Méthodologie: Tableau multi-critères pour classement des PRV
    """
    st.subheader("12. Synthèse comparative multi-critères")
    st.caption("Tableau complet de comparaison homogène permettant le classement des réducteurs de pression")
    
    # Nettoyer le DataFrame
    df = clean_dataframe_for_streamlit(results_with_power)
    
    summary_rows = []
    for _, row in df.iterrows():
        power_kw = float(row.get('power_kW', 0.0))
        delta_p = float(row.get('delta_p', 0.0))
        estimated_flow = float(row.get('estimated_flow_obs', 0.0))
        capex_nominal = float(row.get('capex_nominal', 0.0))
        capex_equipement = capex_nominal * 0.7
        
        # Revenus
        prod_kwh = power_kw * 7000
        revenue_oa = prod_kwh * 0.12
        
        # Payback
        revenue_net = revenue_oa - (capex_equipement * 0.04)
        payback_oa = capex_nominal / revenue_net if revenue_net > 0 else float('inf')
        payback_autoconso = capex_nominal / (prod_kwh * 0.20 - capex_equipement * 0.04) \
            if (prod_kwh * 0.20 - capex_equipement * 0.04) > 0 else float('inf')
        
        # VAN
        npv_oa = compute_npv(capex_nominal, revenue_net)['npv']
        
        # Priority
        if npv_oa > 50000:
            priority = "★★★★"
        elif npv_oa > 10000:
            priority = "★★★"
        elif npv_oa > 0:
            priority = "★★"
        elif npv_oa > -5000:
            priority = "★"
        else:
            priority = "★"
        
        summary_rows.append({
            "Site": str(row.get('site_name', '')),
            "ΔP (bar)": f"{delta_p:.2f}",
            "Débit (m³/h)": f"{estimated_flow:.2f}",
            "Pe (kW)": f"{power_kw:.2f}",
            "Prod. (kWh/an)": f"{prod_kwh:,.0f}",
            "CAPEX (€)": f"{capex_nominal:,.0f}",
            "Rev. OA (€/an)": f"{revenue_oa:,.0f}",
            "Retour (ans)": f"{payback_oa:.1f}" if payback_oa != float('inf') else "N/A",
            "VAN 20ans (€)": f"{npv_oa:+,.0f}",
            "Priorité": priority
        })
    
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, height=450)


def render_financial_export(results_with_power: pd.DataFrame):
    """
    Affiche la section d'export (13. Export des résultats financiers complets).
    """
    st.subheader("13. Export des résultats financiers complets")
    
    if st.button("Générer rapport financier complet (CSV)", key="export_button"):
        # Nettoyer le DataFrame
        df = clean_dataframe_for_streamlit(results_with_power)
        export_df = df.copy()
        
        # Ajouter colonnes financières
        for idx, row in df.iterrows():
            power_kw = float(row.get('power_kW', 0.0))
            capex_nominal = float(row.get('capex_nominal', 0.0))
            capex_equipement = capex_nominal * 0.7
            
            opex = capex_equipement * 0.04
            prod_kwh = power_kw * 7000
            revenue_oa = prod_kwh * 0.12
            revenue_net = revenue_oa - opex
            payback = capex_nominal / revenue_net if revenue_net > 0 else float('inf')
            npv = compute_npv(capex_nominal, revenue_net)['npv']
            
            export_df.at[idx, 'OPEX_annual_eur'] = opex
            export_df.at[idx, 'Production_annual_kwh'] = prod_kwh
            export_df.at[idx, 'Revenue_OA_annual_eur'] = revenue_oa
            export_df.at[idx, 'Revenue_net_annual_eur'] = revenue_net
            export_df.at[idx, 'Payback_years'] = payback
            export_df.at[idx, 'NPV_20years_eur'] = npv
        
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="Télécharger rapport financier (CSV)",
            data=csv,
            file_name="rapport_financier_complet.csv",
            mime="text/csv"
        )
        st.success("Rapport financier prêt à télécharger !")
