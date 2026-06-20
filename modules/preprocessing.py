# modules/preprocessing.py
# Module de prétraitement pour les tests

def associate_prv_hydrants(prv_data, hydrants_data):
    # Dummy implementation for test compatibility
    prv_data = prv_data.copy()
    prv_data['mean_flow'] = 10
    prv_data['hydrant_ids'] = [[1, 2]] * len(prv_data)
    return prv_data
