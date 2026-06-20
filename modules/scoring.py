import pandas as pd

def score_sites(prv_df, weights=None, observed_penalty_factor=0.7):
    """
    Score multi-critères des sites hydrauliques.
    Utilise uniquement estimated_flow_obs comme débit de référence.
    """

    df = prv_df.copy()

    if weights is None:
        weights = {'pressure': 0.4, 'flow': 0.4, 'diameter': 0.2}

    def _normalize(series):
        min_val = series.min()
        max_val = series.max()

        if pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
            return pd.Series(0.0, index=series.index)

        return (series - min_val) / (max_val - min_val)

    # =========================
    # Flag données observées
    # =========================
    df['_has_observed_flow'] = df['estimated_flow_obs'].notna()

    # =========================
    # Débit utilisé pour scoring (UNIQUEMENT OBS + fallback calc)
    # =========================
    df['flow_for_score'] = df['estimated_flow_obs']

    if 'estimated_flow_calc' in df.columns:
        df['flow_for_score'] = df['flow_for_score'].where(
            df['flow_for_score'].notna(),
            df['estimated_flow_calc']
        )

    # =========================
    # Normalisation
    # =========================
    df['norm_pressure'] = _normalize(df['delta_p'])
    df['norm_flow'] = _normalize(df['flow_for_score'])
    df['norm_diameter'] = _normalize(df['diameter'])

    # pénalité si pas de données observées
    if observed_penalty_factor is not None and observed_penalty_factor < 1.0:
        df.loc[~df['_has_observed_flow'], 'norm_flow'] *= observed_penalty_factor

    # =========================
    # SCORE FINAL
    # =========================
    df['score'] = (
        weights['pressure'] * df['norm_pressure'] +
        weights['flow'] * df['norm_flow'] +
        weights['diameter'] * df['norm_diameter']
    )

    return df
