import pandas as pd
from modules.preprocessing import associate_prv_hydrants

def test_preprocessing():
    prv_data = pd.DataFrame([
        {'id': 1, 'pressure_up': 60, 'pressure_down': 30, 'diameter': 100, 'x': 1000, 'y': 2000},
        {'id': 2, 'pressure_up': 80, 'pressure_down': 40, 'diameter': 120, 'x': 1100, 'y': 2100},
    ])
    hydrants_data = pd.DataFrame([
        {'id': 101, 'flow': 10, 'x': 1005, 'y': 2005},
        {'id': 102, 'flow': 12, 'x': 1105, 'y': 2105},
    ])
    prv = associate_prv_hydrants(prv_data, hydrants_data)
    assert 'mean_flow' in prv.columns
    assert 'hydrant_ids' in prv.columns
    print("Preprocessing OK")

if __name__ == "__main__":
    test_preprocessing()
