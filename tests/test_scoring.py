
import pandas as pd
from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power
from modules.scoring import score_sites

def test_scoring():
    dfs = load_data({'prv': 'CSV/aep_organe_pression.csv'})
    hydro = compute_hydraulics(dfs['prv'])
    scored = score_sites(hydro)
    # Affichage formaté
    for _, row in scored.iterrows():
        print(f"{row['site_name']:<30} | {row['delta_p']:.2f} | {row['diameter']:.0f} | {row['flow_min']:.0f} – {row['flow_max']:.0f} m³/h | Score: {row['score']:.2f}")


def test_score_sites_penalizes_missing_observed_flow():
    df = pd.DataFrame([
        {
            'site_name': 'ObservedFlow',
            'delta_p': 3.0,
            'diameter': 120.0,
            'estimated_flow': 25.0,
            'estimated_flow_obs': 25.0,
            'estimated_flow_calc': 25.0,
        },
        {
            'site_name': 'EstimatedFlow',
            'delta_p': 3.0,
            'diameter': 120.0,
            'estimated_flow': 25.0,
            'estimated_flow_obs': float('nan'),
            'estimated_flow_calc': 25.0,
        },
        {
            'site_name': 'LowerFlow',
            'delta_p': 3.0,
            'diameter': 120.0,
            'estimated_flow': 15.0,
            'estimated_flow_obs': float('nan'),
            'estimated_flow_calc': 15.0,
        },
    ])
    scored = score_sites(df)
    observed_score = scored.loc[scored['site_name'] == 'ObservedFlow', 'score'].iloc[0]
    estimated_score = scored.loc[scored['site_name'] == 'EstimatedFlow', 'score'].iloc[0]
    assert observed_score > estimated_score

if __name__ == "__main__":
    test_scoring()
    test_score_sites_penalizes_missing_observed_flow()
