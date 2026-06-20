import pandas as pd
from modules.loader import load_data

def test_loader():
    # Données fictives
    prv_data = pd.DataFrame([
        {'id': 1, 'pressure_up': 60, 'pressure_down': 30, 'diameter': 100, 'x': 1000, 'y': 2000},
        {'id': 2, 'pressure_up': 80, 'pressure_down': 40, 'diameter': 120, 'x': 1100, 'y': 2100},
    ])
    hydrants_data = pd.DataFrame([
        {'id': 101, 'flow': 10, 'x': 1005, 'y': 2005},
        {'id': 102, 'flow': 12, 'x': 1105, 'y': 2105},
    ])
    prv_data.to_csv('prv_test.csv', index=False)
    hydrants_data.to_csv('hydrants_test.csv', index=False)
    dfs = load_data({'prv': 'prv_test.csv', 'hydrants': 'hydrants_test.csv'})
    assert 'id' in dfs['prv'].columns
    assert 'flow' in dfs['hydrants'].columns
    print("Loader OK")

if __name__ == "__main__":
    test_loader()
