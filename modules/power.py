import pandas as pd

def compute_power(prv_df, efficiency=0.75):
    """
    Calcule la puissance hydroélectrique potentielle.
    Args:
        prv_df (DataFrame): PRV enrichi
        efficiency (float): rendement par défaut. Si colonne 'rendement_typique' existe, l'utilise.
    Returns:
        DataFrame: PRV avec puissance
    """

    df = prv_df.copy()

    # Conversion pression -> hauteur (m)
    df['height'] = df['delta_p'] * 10.2

    rho = 1000
    g = 9.81

    # =========================
    # Rendement: utiliser colonne si elle existe, sinon paramètre
    # =========================
    if 'rendement_typique' in df.columns:
        eta = df['rendement_typique'].fillna(efficiency)
    else:
        eta = efficiency

    # =========================
    # Débits (UNIQUEMENT obs)
    # =========================
    flow_m3s = df['estimated_flow_obs'] / 3600
    flow_min_m3s = df['flow_min'] / 3600
    flow_max_m3s = df['flow_max'] / 3600

    # =========================
    # Puissance (W)
    # =========================
    df['power'] = rho * g * flow_m3s * df['height'] * eta
    df['power_min'] = rho * g * flow_min_m3s * df['height'] * eta
    df['power_max'] = rho * g * flow_max_m3s * df['height'] * eta

    # =========================
    # OUTPUT FINAL
    # =========================
    out = df[
        [
            'site_name',
            'delta_p',
            'diameter',
            'estimated_flow_obs',
            'estimated_flow_calc',
            'flow_min',
            'flow_max',
            'estimated_flow',
            'height',
            'power',
            'power_min',
            'power_max'
        ]
    ].copy()

    return out
