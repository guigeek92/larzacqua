from modules.loader import load_data
from modules.hydraulics import compute_hydraulics
from modules.power import compute_power

def test_power_real():
    dfs = load_data({'prv': 'CSV/aep_organe_pression.csv'})
    hydro = compute_hydraulics(dfs['prv'])
    power = compute_power(hydro)
    print(power.head())

if __name__ == "__main__":
    test_power_real()
