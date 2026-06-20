import pandas as pd
import os




def load_data(file_paths):
    """
    Charge des fichiers CSV ou JSON et retourne un dict de DataFrames standardisés.
    Args:
        file_paths (dict): {'prv': path, 'hydrants': path}
    Returns:
        dict: {'prv': DataFrame, 'hydrants': DataFrame}
    Raises:
        ValueError: si colonnes manquantes
    """
    dfs = {}
    for key, path in file_paths.items():
        ext = os.path.splitext(path)[1].lower()
        if ext == '.csv':
            df = pd.read_csv(path)
        elif ext == '.json':
            df = pd.read_json(path)
        else:
            raise ValueError(f"Format non supporté: {ext}")
        df = standardize_columns(df, key)
        dfs[key] = df
    return dfs

def standardize_columns(df, key):
    if key == 'prv':
        # Mapping pour aep_organe_pression.csv
        col_map = {
            'IDENT': 'id',
            'PRES_AMONT': 'pressure_up',
            'PRESS_AVAL': 'pressure_down',
            'DIAMETRE': 'diameter',
            'latitude': 'x',
            'longitude': 'y'
        }
        optional_map = {
            'DEBIT_INSTANTANE': 'flow_inst_m3h',
            'DEBIT_NUIT': 'flow_night_m3h',
            'DEBIT_MIN': 'flow_min_m3h',
            'DEBIT_MAX': 'flow_max_m3h',
            'COMPTEUR': 'meter_id'
        }
        # Si les colonnes standards existent déjà, on les garde
        for std_col in ['id', 'pressure_up', 'pressure_down', 'diameter', 'x', 'y',
                        'flow_inst_m3h', 'flow_night_m3h', 'flow_min_m3h', 'flow_max_m3h',
                        'meter_id']:
            if std_col in df.columns:
                col_map[std_col] = std_col
        for raw_col, std_col in optional_map.items():
            if raw_col in df.columns:
                col_map[raw_col] = std_col
    elif key == 'hydrants':
        col_map = {
            'id': 'id',
            'flow': 'flow',
            'x': 'x',
            'y': 'y'
        }
    else:
        raise ValueError(f"Type inconnu: {key}")
    df = df.rename(columns=col_map)
    missing = [c for c in col_map.values() if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes pour {key}: {missing}")
    return df


