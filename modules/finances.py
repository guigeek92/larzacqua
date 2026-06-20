"""
Module de calcul des indicateurs financiers complets suivant la méthodologie.

Contient:
- Calcul de l'OPEX (4% du CAPEX équipement par an)
- Calcul des revenus annuels (OA et autoconsommation)
- Calcul des indicateurs de rentabilité (VAN, payback, TRI)
- Analyse de sensibilité sur prix, débit, disponibilité
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional


# Constantes méthodologiques
OPEX_RATE = 0.04  # 4% du CAPEX équipement par an
ANNUAL_OPERATING_HOURS = 7000  # Réseau eau potable quasi-continu
TARIF_OA = 0.12  # €/kWh (Obligation d'Achat haute chute ΔP > 3 bar)
TARIF_AUTOCONSO = 0.20  # €/kWh (autoconsommation valorisée)
DISCOUNT_RATE = 0.04  # 4% taux actualisation
PROJECT_LIFE = 20  # ans
CAPEX_FIXE_MIN = 2800.0  # €
CAPEX_FIXE_MAX = 7500.0  # €
CAPEX_FIXE_NOMINAL = 2800.0  # Valeur minimale pour installation simple


def compute_opex(capex_equipement: float) -> Dict[str, float]:
    """
    Calcule l'OPEX annuel comme 4% du coût des équipements.
    
    Args:
        capex_equipement: Coût des équipements (turbine, génératrice, armoire, capteurs)
    
    Returns:
        Dict avec opex annuel et détails
    """
    opex_annual = capex_equipement * OPEX_RATE
    
    return {
        "opex_annual": opex_annual,
        "opex_rate": OPEX_RATE,
        "opex_percentage": f"{OPEX_RATE*100:.1f}%"
    }


def compute_production_annual(power_kw: float, efficiency: float = 1.0) -> Dict[str, float]:
    """
    Calcule la production énergétique annuelle.
    
    Production = Pe (kW) × 7000 (h/an) × rendement
    
    Args:
        power_kw: Puissance électrique (kW)
        efficiency: Rendement global (0-1)
    
    Returns:
        Dict avec production annuelle (kWh)
    """
    production = power_kw * ANNUAL_OPERATING_HOURS * efficiency
    
    return {
        "production_annual_kwh": production,
        "operating_hours_annual": ANNUAL_OPERATING_HOURS,
        "efficiency": efficiency
    }


def compute_revenues(power_kw: float, scenario: str = "OA", efficiency: float = 1.0) -> Dict[str, float]:
    """
    Calcule les revenus annuels selon scénario.
    
    Deux scénarios:
    - OA (Obligation d'Achat): 0,12 €/kWh (haute chute ΔP > 3 bar)
    - Autoconso: 0,20 €/kWh
    
    Args:
        power_kw: Puissance électrique (kW)
        scenario: "OA" ou "autoconso"
        efficiency: Rendement global
    
    Returns:
        Dict avec revenus annuels
    """
    production = compute_production_annual(power_kw, efficiency)
    prod_kwh = production["production_annual_kwh"]
    
    if scenario.lower() == "oa":
        tarif = TARIF_OA
        scenario_name = "Obligation d'Achat (OA)"
    elif scenario.lower() == "autoconso":
        tarif = TARIF_AUTOCONSO
        scenario_name = "Autoconsommation"
    else:
        tarif = TARIF_OA
        scenario_name = "Obligation d'Achat (OA)"
    
    revenue_annual = prod_kwh * tarif
    
    return {
        "scenario": scenario_name,
        "revenue_annual": revenue_annual,
        "tarif": tarif,
        "production_kwh": prod_kwh
    }


def compute_net_revenue(power_kw: float, capex_equipement: float, scenario: str = "OA", 
                       efficiency: float = 1.0) -> Dict[str, float]:
    """
    Calcule le revenu net annuel (revenu brut - OPEX).
    
    Revenu net = Revenu - OPEX
    
    Args:
        power_kw: Puissance électrique (kW)
        capex_equipement: Coût des équipements
        scenario: "OA" ou "autoconso"
        efficiency: Rendement global
    
    Returns:
        Dict avec revenu net et détails
    """
    revenue_data = compute_revenues(power_kw, scenario, efficiency)
    opex_data = compute_opex(capex_equipement)
    
    revenue_net = revenue_data["revenue_annual"] - opex_data["opex_annual"]
    
    return {
        "revenue_gross_annual": revenue_data["revenue_annual"],
        "opex_annual": opex_data["opex_annual"],
        "revenue_net_annual": revenue_net,
        "scenario": revenue_data["scenario"],
        "tarif": revenue_data["tarif"]
    }


def compute_payback_period(capex_total: float, revenue_net_annual: float) -> Dict[str, Any]:
    """
    Calcule la période de retour sur investissement simple.
    
    Payback (ans) = CAPEX / Revenu net annuel
    
    Args:
        capex_total: CAPEX total (€)
        revenue_net_annual: Revenu net annuel (€/an)
    
    Returns:
        Dict avec payback period
    """
    if revenue_net_annual <= 0:
        payback_period = float('inf')
        status = "Non rentable (revenu net négatif)"
    else:
        payback_period = capex_total / revenue_net_annual
        if payback_period <= 5:
            status = "Excellent (< 5 ans)"
        elif payback_period <= 10:
            status = "Bon (5-10 ans)"
        elif payback_period <= 20:
            status = "Acceptable (10-20 ans)"
        else:
            status = "Faible (> 20 ans)"
    
    return {
        "payback_years": payback_period,
        "payback_status": status,
        "payback_readable": f"{payback_period:.1f} ans" if payback_period != float('inf') else "N/A"
    }


def compute_npv(capex_total: float, revenue_net_annual: float, 
               discount_rate: float = DISCOUNT_RATE, project_life: int = PROJECT_LIFE) -> Dict[str, float]:
    """
    Calcule la Valeur Actuelle Nette (VAN) sur la durée de vie du projet.
    
    VAN = Σ(Revenu net annuel / (1 + taux_actualisation)^année) - CAPEX
    
    Args:
        capex_total: CAPEX total (€)
        revenue_net_annual: Revenu net annuel constant (€/an)
        discount_rate: Taux d'actualisation (ex: 4%)
        project_life: Durée de vie du projet (ex: 20 ans)
    
    Returns:
        Dict avec VAN et indicateurs
    """
    # Calcul VAN
    pv_revenues = 0
    for year in range(1, project_life + 1):
        pv_revenues += revenue_net_annual / ((1 + discount_rate) ** year)
    
    van = pv_revenues - capex_total
    
    # Détermine la viabilité
    if van > 0:
        viability = "Projet viable"
    elif van > -5000:
        viability = "Projet borderline (marginal)"
    else:
        viability = "Projet non viable"
    
    return {
        "npv": van,
        "pv_revenues": pv_revenues,
        "capex_initial": capex_total,
        "discount_rate": discount_rate,
        "project_life": project_life,
        "viability": viability
    }


def compute_profitability_indicators(site_row: pd.Series, capex_nominal: float) -> Dict[str, Any]:
    """
    Calcule tous les indicateurs de profitabilité pour un site.
    
    Args:
        site_row: Ligne du DataFrame avec données du site (puissance, delta_p, etc.)
        capex_nominal: CAPEX nominal (€)
    
    Returns:
        Dict complet avec tous les indicateurs
    """
    power_kw = site_row.get("power_kW", 0.0)
    delta_p = site_row.get("delta_p", 0.0)
    
    # Extraire cost des équipements (nominalement)
    capex_equipement = capex_nominal * 0.7  # Estimation: 70% du total
    
    results = {
        "site_name": site_row.get("site_name", "Unknown"),
        "power_kw": power_kw,
        "delta_p": delta_p,
        "capex_nominal": capex_nominal
    }
    
    # OPEX
    opex_data = compute_opex(capex_equipement)
    results.update({
        f"opex_annual": opex_data["opex_annual"]
    })
    
    # Revenus OA
    revenue_oa = compute_net_revenue(power_kw, capex_equipement, scenario="OA")
    results.update({
        f"revenue_net_oa_annual": revenue_oa["revenue_net_annual"],
        f"revenue_gross_oa_annual": revenue_oa["revenue_gross_annual"],
        f"production_kwh_annual": revenue_oa.get("revenue_annual", 0) / TARIF_OA if revenue_oa.get("revenue_annual", 0) > 0 else 0
    })
    
    # Revenus Autoconso
    revenue_autoconso = compute_net_revenue(power_kw, capex_equipement, scenario="autoconso")
    results.update({
        f"revenue_net_autoconso_annual": revenue_autoconso["revenue_net_annual"],
        f"revenue_gross_autoconso_annual": revenue_autoconso["revenue_gross_annual"]
    })
    
    # Payback periods
    payback_oa = compute_payback_period(capex_nominal, revenue_oa["revenue_net_annual"])
    results.update({
        f"payback_oa_years": payback_oa["payback_years"],
        f"payback_oa_status": payback_oa["payback_status"]
    })
    
    payback_autoconso = compute_payback_period(capex_nominal, revenue_autoconso["revenue_net_annual"])
    results.update({
        f"payback_autoconso_years": payback_autoconso["payback_years"],
        f"payback_autoconso_status": payback_autoconso["payback_status"]
    })
    
    # VAN OA
    npv_oa = compute_npv(capex_nominal, revenue_oa["revenue_net_annual"])
    results.update({
        f"npv_oa_20years": npv_oa["npv"],
        f"viability_oa": npv_oa["viability"]
    })
    
    # VAN Autoconso
    npv_autoconso = compute_npv(capex_nominal, revenue_autoconso["revenue_net_annual"])
    results.update({
        f"npv_autoconso_20years": npv_autoconso["npv"],
        f"viability_autoconso": npv_autoconso["viability"]
    })
    
    # Déterminer priorité
    if results["npv_oa_20years"] > 50000:
        priority = "★★★★ Prioritaire"
    elif results["npv_oa_20years"] > 10000:
        priority = "★★★ Viable"
    elif results["npv_oa_20years"] > 0:
        priority = "★★ Viable avec aide"
    elif results["npv_oa_20years"] > -5000:
        priority = "★ Sous conditions"
    else:
        priority = "★ Non rentable seul"
    
    results["priority"] = priority
    
    return results


def sensitivity_analysis(capex_nominal: float, power_kw: float, capex_equipement: float,
                        variations: Optional[Dict[str, List[float]]] = None) -> pd.DataFrame:
    """
    Analyse de sensibilité sur les variables clés.
    
    Variables: prix (OA → autoconso), débit (-20% à +20%), disponibilité (-10%)
    
    Args:
        capex_nominal: CAPEX nominal
        power_kw: Puissance nominale
        capex_equipement: Coût équipement
        variations: Dict avec clés et listes de variations
    
    Returns:
        DataFrame avec résultats sensibilité
    """
    if variations is None:
        variations = {
            "price": [TARIF_OA, TARIF_AUTOCONSO],
            "flow": [0.8, 1.0, 1.2],  # -20%, nominal, +20%
            "availability": [0.9, 1.0]  # -10%, nominal
        }
    
    results = []
    
    # Sensibilité prix
    for tarif in variations.get("price", [TARIF_OA, TARIF_AUTOCONSO]):
        prod_kwh = power_kw * ANNUAL_OPERATING_HOURS
        revenue = prod_kwh * tarif
        opex = capex_equipement * OPEX_RATE
        revenue_net = revenue - opex
        payback = capex_nominal / revenue_net if revenue_net > 0 else float('inf')
        results.append({
            "variable": "Prix électricité",
            "scenario": f"{tarif:.2f} €/kWh",
            "impact_revenu_annuel": revenue,
            "payback_years": payback,
            "npv_20ans": compute_npv(capex_nominal, revenue_net)["npv"]
        })
    
    # Sensibilité débit
    for flow_factor in variations.get("flow", [0.8, 1.0, 1.2]):
        power_adjusted = power_kw * flow_factor
        prod_kwh = power_adjusted * ANNUAL_OPERATING_HOURS
        revenue = prod_kwh * TARIF_OA
        opex = capex_equipement * OPEX_RATE
        revenue_net = revenue - opex
        payback = capex_nominal / revenue_net if revenue_net > 0 else float('inf')
        
        variation_pct = (flow_factor - 1.0) * 100
        results.append({
            "variable": "Débit réel",
            "scenario": f"{variation_pct:+.0f}%",
            "impact_revenu_annuel": revenue,
            "payback_years": payback,
            "npv_20ans": compute_npv(capex_nominal, revenue_net)["npv"]
        })
    
    # Sensibilité disponibilité turbine
    for avail_factor in variations.get("availability", [0.9, 1.0]):
        prod_kwh = power_kw * ANNUAL_OPERATING_HOURS * avail_factor
        revenue = prod_kwh * TARIF_OA
        opex = capex_equipement * OPEX_RATE
        revenue_net = revenue - opex
        payback = capex_nominal / revenue_net if revenue_net > 0 else float('inf')
        
        variation_pct = (avail_factor - 1.0) * 100
        results.append({
            "variable": "Disponibilité turbine",
            "scenario": f"{variation_pct:+.0f}%",
            "impact_revenu_annuel": revenue,
            "payback_years": payback,
            "npv_20ans": compute_npv(capex_nominal, revenue_net)["npv"]
        })
    
    # Subvention CAPEX
    capex_with_subsidy = capex_nominal * 0.7  # -30%
    prod_kwh = power_kw * ANNUAL_OPERATING_HOURS
    revenue = prod_kwh * TARIF_OA
    opex = capex_equipement * OPEX_RATE
    revenue_net = revenue - opex
    payback = capex_with_subsidy / revenue_net if revenue_net > 0 else float('inf')
    results.append({
        "variable": "Subvention CAPEX",
        "scenario": "-30%",
        "impact_revenu_annuel": revenue,
        "payback_years": payback,
        "npv_20ans": compute_npv(capex_with_subsidy, revenue_net)["npv"]
    })
    
    return pd.DataFrame(results)


def format_financial_summary(indicators: Dict[str, Any]) -> Dict[str, str]:
    """
    Formate les indicateurs financiers pour affichage lisible.
    
    Args:
        indicators: Dict avec indicateurs bruts
    
    Returns:
        Dict avec valeurs formatées
    """
    return {
        "Site": indicators.get("site_name", ""),
        "CAPEX (€)": f"{indicators.get('capex_nominal', 0):,.0f}",
        "Rev. net OA (€/an)": f"{indicators.get('revenue_net_oa_annual', 0):,.0f}",
        "Retour OA (ans)": f"{indicators.get('payback_oa_years', 0):.1f}" 
            if indicators.get('payback_oa_years', 0) != float('inf') else "N/A",
        "Retour autoconso (ans)": f"{indicators.get('payback_autoconso_years', 0):.1f}"
            if indicators.get('payback_autoconso_years', 0) != float('inf') else "N/A",
        "VAN 20 ans (€)": f"{indicators.get('npv_oa_20years', 0):+,.0f}",
        "Priorité": indicators.get("priority", "")
    }
