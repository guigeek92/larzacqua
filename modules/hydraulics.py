import pandas as pd
import numpy as np


def get_reducteur_stats(df):
    """
    Statistiques des réducteurs de pression.
    """
    reducteurs = df[df['TYPE'].str.contains('réducteur', case=False, na=False)]

    return {
        'nb_reducteurs': len(reducteurs),
        'marques': reducteurs['MARQUE'].value_counts(),
        'diam_moyen': pd.to_numeric(reducteurs['DIAMETRE'], errors='coerce').mean(),
        'pres_amont_moy': pd.to_numeric(reducteurs['PRES_AMONT'], errors='coerce').mean()
    }


def _coerce_numeric(series):
    if series is None:
        return None
    return pd.to_numeric(
        series.astype(str).str.replace(',', '.', regex=False),
        errors='coerce'
    )


def _get_flow_series(df, std_col, raw_col):
    if std_col in df.columns:
        return df[std_col]
    if raw_col in df.columns:
        return df[raw_col]
    return None


def compute_hydraulics(prv_df):
    """
    Hydraulique PRV + débit observé STRICT.
    ⚠️ estimated_flow_obs = valeur brute externe uniquement
    """

    df = prv_df.copy()

    raw_observed_flow = None
    if 'estimated_flow_obs' in df.columns:
        raw_observed_flow = _coerce_numeric(df['estimated_flow_obs'])

    # =========================
    # Pressions
    # =========================
    if df['pressure_up'].max() > 1000:
        df['pressure_up_bar'] = df['pressure_up'] / 1e5
        df['pressure_down_bar'] = df['pressure_down'] / 1e5
    else:
        df['pressure_up_bar'] = df['pressure_up']
        df['pressure_down_bar'] = df['pressure_down']

    df['delta_p_bar'] = df['pressure_up_bar'] - df['pressure_down_bar']

    # =========================
    # Géométrie
    # =========================
    df['diameter_m'] = df['diameter'] / 1000
    df['section_m2'] = np.pi * (df['diameter_m'] ** 2) / 4

    # =========================
    # Débit théorique
    # =========================
    rho = 1000
    df['delta_p_pa'] = df['delta_p_bar'] * 1e5

    k = 0.07
    df['estimated_flow_calc'] = (
        df['section_m2'] * np.sqrt(2 * df['delta_p_pa'] / rho)
    ) * 3600 * k

    # =========================
    # Débits mesurés
    # =========================
    flow_inst = _coerce_numeric(_get_flow_series(df, 'flow_inst_m3h', 'DEBIT_INSTANTANE'))
    flow_night = _coerce_numeric(_get_flow_series(df, 'flow_night_m3h', 'DEBIT_NUIT'))
    flow_max_measured = _coerce_numeric(_get_flow_series(df, 'flow_max_m3h', 'DEBIT_MAX'))

    flow_measured = None
    if any(x is not None for x in [flow_inst, flow_night, flow_max_measured]):
        parts = []
        if flow_inst is not None:
            parts.append(flow_inst)
        if flow_night is not None:
            parts.append(flow_night)
        if flow_max_measured is not None:
            parts.append(flow_max_measured)

        flow_measured = pd.concat(parts, axis=1).mean(axis=1, skipna=True)

    # =========================
    # Débits réels externes
    # =========================
    try:
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)

        path = os.path.join(project_root, 'CSV', 'reducteurs_debit_reel.csv')

        if os.path.exists(path):
            ref = pd.read_csv(path)

            mapping = {}
            for _, r in ref.iterrows():
                nom = str(r.get('NOM', '')).strip()
                debit = r.get('Débit_réel_moyen_m3h')

                # ⚠️ NE MODIFIE JAMAIS LA VALEUR
                if isinstance(debit, (int, float)) and not pd.isna(debit):
                    mapping[nom] = debit

            df['debit_reel_applique'] = df['NOM'].map(
                lambda x: mapping.get(str(x).strip(), np.nan)
            )
        else:
            df['debit_reel_applique'] = np.nan

    except Exception as e:
        print(f"Avertissement débit réel: {e}")
        df['debit_reel_applique'] = np.nan

    # =========================
    # 🔥 VARIABLE UNIQUE (STRICTE)
    # =========================
    if raw_observed_flow is not None:
        df['estimated_flow_obs'] = raw_observed_flow
    else:
        df['estimated_flow_obs'] = df['debit_reel_applique']

    df['estimated_flow_obs'] = df['estimated_flow_obs'].where(
        df['estimated_flow_obs'].notna(),
        df['debit_reel_applique']
    )

    # fallback uniquement si ABSENT (jamais modifié sinon)
    df.loc[df['estimated_flow_obs'].isna(), 'estimated_flow_obs'] = (
        flow_measured if flow_measured is not None else df['estimated_flow_calc']
    )

    # =========================
    # Bornes hydrauliques
    # =========================
    df['flow_min'] = df['estimated_flow_obs'] * 0.8
    df['flow_max'] = df['estimated_flow_obs'] * 1.2

    # =========================
    # OUTPUT FINAL
    # =========================
    df['estimated_flow'] = df['estimated_flow_obs']
    out = df[
        [
            'NOM',
            'delta_p_bar',
            'diameter',
            'estimated_flow_obs',
            'estimated_flow_calc',
            'flow_min',
            'flow_max',
            'estimated_flow'
        ]
      
    ].copy()

    out = out.rename(columns={
        'NOM': 'site_name',
        'delta_p_bar': 'delta_p'
    })

    return out