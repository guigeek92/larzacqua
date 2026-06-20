import numpy as np
import pandas as pd

# =========================
# PHYSIQUE HYDRO
# =========================

def compute_productible(site, turbine):
    """
    Calcule puissance et énergie annuelle (physiquement cohérent).
    """

    pressure = float(site.get('delta_p', 0))  # bar
    flow = float(site.get('estimated_flow_obs', 0))  # m3/h
    rendement = float(turbine.get('rendement_typique', 0.7))
    hours = float(turbine.get('heures_fonctionnement', 6500))
    availability = float(turbine.get('availability', 0.93))

    # conversions
    flow_m3s = flow / 3600
    head_m = pressure * 10.2

    # limites turbine
    flow_min = float(turbine.get('debit_min_m3h', 0) or 0)
    flow_max = float(turbine.get('debit_max_m3h', flow) or flow)

    if not np.isfinite(flow_min):
        flow_min = 0

    if not np.isfinite(flow_max) or flow_max <= 0:
        flow_max = flow

    if flow < flow_min:
        power_kw = 0

    else:
        flow_effective = min(flow, flow_max)
        flow_m3s = flow_effective / 3600

        # puissance hydraulique
        power_kw_theoretical = 9.81 * flow_m3s * head_m * rendement

        power_max = float(
            turbine.get('puissance_max_kw', power_kw_theoretical)
            or power_kw_theoretical
        )

        if not np.isfinite(power_max) or power_max <= 0:
            power_max = power_kw_theoretical

        power_kw = min(power_kw_theoretical, power_max)

    # énergie annuelle
    energy_kwh = power_kw * hours * availability

    # facteur de charge
    capacity_factor = (hours * availability) / 8760 if power_kw > 0 else 0

    return {
        'puissance_kw': power_kw,
        'energie_kwh': energy_kwh,
        'puissance_max_kw': turbine.get('puissance_max_kw', power_kw),
        'facteur_de_charge': capacity_factor,
        'heures': hours,
        'availability': availability
    }


# =========================
# ECONOMIQUE
# =========================

def _npv(rate, cashflows):
    return sum(cf / ((1 + rate) ** idx) for idx, cf in enumerate(cashflows))


def _irr(cashflows, low=-0.99, high=1.0, max_iter=100):
    npv_low = _npv(low, cashflows)
    npv_high = _npv(high, cashflows)

    while npv_low * npv_high > 0 and high < 10:
        high *= 2
        npv_high = _npv(high, cashflows)

    if npv_low * npv_high > 0:
        return None

    for _ in range(max_iter):
        mid = (low + high) / 2
        npv_mid = _npv(mid, cashflows)

        if abs(npv_mid) < 1e-6:
            return mid

        if npv_low * npv_mid <= 0:
            high = mid
            npv_high = npv_mid
        else:
            low = mid
            npv_low = npv_mid

    return (low + high) / 2


def compute_economics(energy_kwh, site, finance):
    """
    Calcule autoconsommation, revenus, VAN et TRI.
    """

    consommation = float(site.get('consommation_kwh', 0))

    price = float(finance.get('electricity_price', 0.18))
    injection_tariff = float(finance.get('injection_tariff', 0.12))

    capex = float(finance.get('capex', 30000))
    opex = float(finance.get('opex', 1000))

    if not np.isfinite(capex):
        capex = 30000

    if not np.isfinite(opex):
        opex = 1000

    subsidy_rate = float(finance.get('subsidy_rate', 0))

    if subsidy_rate > 1:
        subsidy_rate = subsidy_rate / 100

    discount_rate = float(finance.get('discount_rate', 0.05))

    if not np.isfinite(discount_rate):
        discount_rate = 0.05

    project_life = int(finance.get('project_life_years', 20))

    mode = site.get('mode', 'mixte')

    # Répartition autoconsommation / injection
    if mode == "autoconsommation":
        autoconsumed = min(energy_kwh, consommation)
        injected = 0

    elif mode == "injection":
        autoconsumed = 0
        injected = energy_kwh

    else:  # mixte
        autoconsumed = min(energy_kwh, consommation)
        injected = max(0, energy_kwh - consommation)

    # Revenus
    economies = autoconsumed * price
    revenus_injection = injected * injection_tariff

    total_revenue = economies + revenus_injection

    # Subventions
    subsidy_rate = min(max(subsidy_rate, 0), 1)
    subvention_eur = capex * subsidy_rate
    capex_net = capex - subvention_eur

    # Cashflow annuel
    cashflow = total_revenue - opex

    # Temps de retour
    payback = capex_net / cashflow if cashflow > 0 else np.inf

    # VAN et TRI
    cashflows = [-capex_net] + [cashflow] * max(project_life, 0)

    van = (
        _npv(discount_rate, cashflows)
        if project_life > 0
        else -capex_net
    )

    tri = (
        _irr(cashflows)
        if project_life > 0
        else None
    )

    taux_auto = autoconsumed / energy_kwh if energy_kwh > 0 else 0

    return {
        'autoconsommation_kwh': autoconsumed,
        'injection_kwh': injected,
        'economies_eur': economies,
        'revenus_injection_eur': revenus_injection,
        'revenu_total_eur': total_revenue,
        'opex_eur': opex,
        'cashflow_eur': cashflow,
        'temps_retour_ans': payback,
        'taux_autoconsommation': taux_auto,
        'subvention_rate': subsidy_rate,
        'subvention_eur': subvention_eur,
        'capex_net_eur': capex_net,
        'discount_rate': discount_rate,
        'project_life_years': project_life,
        'van_eur': van,
        'tri': tri
    }


# =========================
# WRAPPER GLOBAL
# =========================

def run_full_model(site, turbine, finance):
    """
    Pipeline complet : physique + économique
    """
    prod = compute_productible(site, turbine)
    eco = compute_economics(prod['energie_kwh'], site, finance)

    return {**prod, **eco}


# =========================
# BATCH CSV
# =========================

def run_batch(selection_csv, turbine_db_csv, finance, output_csv="results.csv"):

    df = pd.read_csv(selection_csv)
    from modules.turbine import load_turbine_db
    turbines = load_turbine_db(turbine_db_csv)

    results = []

    for _, row in df.iterrows():

        site = {
            'delta_p': row.get('delta_p', 0),
            'estimated_flow_obs': row.get('estimated_flow_obs', 0),
            'consommation_kwh': row.get('consommation_kwh', 0),
            'mode': row.get('mode', 'mixte')
        }

        for i in [1, 2, 3]:

            t_type = row.get(f'turbine_type_{i}')
            t_diam = row.get(f'turbine_diameter_mm_{i}')

            match = turbines[
                (turbines['type_turbine'] == t_type) &
                (turbines['diametre_mm'] == t_diam)
            ]

            if match.empty:
                continue

            turbine = match.iloc[0].to_dict()

            res = run_full_model(site, turbine, finance)

            res['site'] = row.get('site_name', '')
            res['turbine'] = f"{t_type}_{t_diam}"

            results.append(res)

    df_out = pd.DataFrame(results)

    df_out.to_csv(output_csv, index=False)

    return df_out


# =========================
# TEST
# =========================

if __name__ == "__main__":

    site = {
        "delta_p": 11.79,
        "estimated_flow_obs": 61.5,   # débit moyen observé (m3/h)
        "consommation_kwh": 10000,
        "mode": "mixte"
    }

    turbine = {
        "rendement_typique": 0.7,
        "puissance_max_kw": 10,
        "heures_fonctionnement": 4000,
        "availability": 0.9
    }

    finance = {
        "electricity_price": 0.18,
        "injection_tariff": 0.12,
        "capex": 30000,
        "opex": 1000,
        "subsidy_rate": 0,
        "discount_rate": 0.05,
        "project_life_years": 20
    }

    result = run_full_model(site, turbine, finance)

    print("\n=== RESULTATS ===")

    for k, v in result.items():
        if isinstance(v, (int, float)):
            print(f"{k}: {round(v, 2)}")
        else:
            print(f"{k}: {v}")