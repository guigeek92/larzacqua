
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power
from modules.scoring import score_sites
from modules.turbine import load_turbine_db, select_turbine, export_selected_turbines_to_csv

# Chemin réel des données PRV (organe pression)
file_paths = {'prv': 'CSV/aep_organe_pression.csv'}
dfs = load_data(file_paths)
prv_df = dfs['prv']

# Étape hydraulique
hydro_df = compute_hydraulics(prv_df)

# Étape puissance
power_df = compute_power(hydro_df)

# Étape scoring
scored_df = score_sites(power_df)

# Chargement de la base turbines enrichie
turbine_db = load_turbine_db('CSV/turbine_db.csv')

# Pour chaque site, trouver les turbines compatibles (pression, débit, diamètre)
def propose_turbines(site_row, turbine_db, top_n=3):
    # Marges de tolérance (20% pour pression et débit, 20mm pour diamètre)
    pressure = site_row['delta_p']
    flow = site_row['estimated_flow']
    diameter = site_row['diameter']
    pressure_tol = 0.2 * pressure if pressure > 0 else 0.2
    flow_tol = 0.2 * flow if flow > 0 else 0.2
    diameter_tol = 20
    print(f"    Critères site: pression={pressure:.2f}±{pressure_tol:.2f} bar, débit={flow:.2f}±{flow_tol:.2f} m3/h, diamètre={diameter:.2f}±{diameter_tol} mm")
    details = []
    for idx, t in turbine_db.iterrows():
        compatible = (
            (t['pression_min_bar'] <= pressure + pressure_tol) and
            (t['pression_max_bar'] >= pressure - pressure_tol) and
            (t['debit_min_m3h'] <= flow + flow_tol) and
            (t['debit_max_m3h'] >= flow - flow_tol) and
            (t['diametre_mm'] <= diameter + diameter_tol) and
            (t['diametre_mm'] >= diameter - diameter_tol)
        )
        details.append({
            'type': t['type_turbine'],
            'diam': t['diametre_mm'],
            'pmin': t['pression_min_bar'],
            'pmax': t['pression_max_bar'],
            'qmin': t['debit_min_m3h'],
            'qmax': t['debit_max_m3h'],
            'compatible': compatible
        })
    for d in details:
        print(f"      - {d['type']} Ø{d['diam']}mm, pression {d['pmin']}-{d['pmax']} bar, débit {d['qmin']}-{d['qmax']} m3/h => {'OK' if d['compatible'] else 'NON'}")
    candidates = turbine_db[[d['compatible'] for d in details]].copy()
    return candidates.head(top_n)


# Test : afficher les meilleures turbines pour chaque site réel
for i, row in scored_df.iterrows():
    print(f"\nSite {row['site_name']} (score={row['score']:.2f})")
    turbines = propose_turbines(row, turbine_db)
    if turbines.empty:
        print("    Aucune turbine compatible")
    else:
        for _, t in turbines.iterrows():
            print(f"    - {t['type_turbine']} Ø{t['diametre_mm']}mm, {t['puissance_min_kw']}-{t['puissance_max_kw']}kW, rendement {t['rendement_typique']}, prix {t['prix_estime_eur']}€, {t['description']} (source: {t['source']})")

# Génère un CSV avec la turbine sélectionnée pour chaque site (via select_turbine)
selected_df = select_turbine(scored_df, turbine_db)
export_selected_turbines_to_csv(selected_df, "outputs/turbine_selection_test.csv")
print("\nExport CSV des turbines sélectionnées : outputs/turbine_selection_test.csv")
