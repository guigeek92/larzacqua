
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.productible import compute_productible, estimate_productible
import pandas as pd


def test_productible_from_csv():
    df = pd.read_csv('outputs/turbine_selection_test.csv')
    turbines = pd.read_csv('CSV/turbine_db.csv')
    # On teste les 3 premières lignes et les 3 turbines proposées
    for idx, row in df.head(3).iterrows():
        print(f"\nSite: {row['site_name']} (delta_p={row['delta_p']}, flow={row['estimated_flow']})")
        for i in range(1, 4):
            t_type = row.get(f'turbine_type_{i}')
            t_diam = row.get(f'turbine_diameter_mm_{i}')
            if pd.isna(t_type) or t_type == 'None' or pd.isna(t_diam):
                continue
            match = turbines[(turbines['type_turbine'] == t_type) & (turbines['diametre_mm'] == float(t_diam))]
            if not match.empty:
                turbine = match.iloc[0].to_dict()
                site = {
                    'site_name': row.get('site_name', ''),
                    'delta_p': row.get('delta_p', None),
                    'estimated_flow': row.get('estimated_flow', None)
                }
                res = estimate_productible(site, turbine)
                print(f"  Turbine {i}: {t_type} {t_diam}mm")
                print(f"    Puissance estimée (kW): {res['puissance_kW']:.2f}")
                print(f"    Énergie annuelle (kWh): {res['energie_kWh']:.0f}")
                print(f"    Facteur de charge: {res['facteur_de_charge']:.2f}")
                print(f"    Coût estimé (€): {res['cout_eur']}")

if __name__ == '__main__':
    test_productible_from_csv()

def test_compute_productible_zero_flow():
    site = {'site_name': 'ZeroFlow', 'delta_p': 4.0, 'estimated_flow': 0.0}
    turbine = {'puissance_max_kw': 10, 'rendement_typique': 0.7}
    res = compute_productible(site, turbine)
    assert res['puissance_instantanee_kw'] == 0
    assert res['production_annuelle_kwh'] == 0
    assert res['facteur_de_charge'] == 0
