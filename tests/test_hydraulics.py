
from modules.loader import load_data
from modules.hydraulics import compute_hydraulics

def test_hydraulics():
	# Chargement du CSV PRV
	dfs = load_data({'prv': 'CSV/aep_organe_pression.csv'})
	prv_df = dfs['prv']
	# Ajout colonne mean_flow fictive si absente
	if 'mean_flow' not in prv_df.columns:
		prv_df['mean_flow'] = 10  # valeur fictive pour test
	result = compute_hydraulics(prv_df)
	print(result.head())


def test_hydraulics_keeps_existing_observed_flow_value():
	dfs = load_data({'prv': 'CSV/aep_organe_pression.csv'})
	prv_df = dfs['prv']
	result = compute_hydraulics(prv_df)
	toss_row = result[result['site_name'] == 'TOS vers Mayres'].iloc[0]
	assert round(float(toss_row['estimated_flow_obs']), 3) == 76.954

if __name__ == "__main__":
	test_hydraulics()
	test_hydraulics_keeps_existing_observed_flow_value()
