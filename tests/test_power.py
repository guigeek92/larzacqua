from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power

def test_power():
    dfs = load_data({'prv': 'CSV/aep_organe_pression.csv'})
    hydro = compute_hydraulics(dfs['prv'])
    power = compute_power(hydro)
    # Affichage formaté puissance en kW
    for _, row in power.iterrows():
        print(f"{row['site_name']:<30} | {row['delta_p']:.2f} bar | {row['diameter']:.0f} mm | {row['estimated_flow']:.0f} m³/h | {row['power']/1000:.2f} kW")

if __name__ == "__main__":
    test_power()
