import os
import pandas as pd


# =========================================================
# 🔧 Fallback database (simplifiée PAT-oriented)
# =========================================================

def _fallback_turbine_db():
    return pd.DataFrame(
        [
            {
                'type_turbine': 'pico_inline',
                'diametre_mm': 25,
                'pression_min_bar': 0.1,
                'pression_max_bar': 2,
                'debit_min_m3h': 1,
                'debit_max_m3h': 6,
                'puissance_min_kw': 0.1,
                'puissance_max_kw': 1.0,
                'rendement_typique': 0.55,
                'prix_estime_eur': 3500,
                'description': 'Micro turbine inline a tres faible debit.',
                'source': 'fallback',
            },
            {
                'type_turbine': 'micro_inline',
                'diametre_mm': 80,
                'pression_min_bar': 0.5,
                'pression_max_bar': 8,
                'debit_min_m3h': 5,
                'debit_max_m3h': 40,
                'puissance_min_kw': 1.0,
                'puissance_max_kw': 10.0,
                'rendement_typique': 0.68,
                'prix_estime_eur': 8500,
                'description': 'Turbine inline pour reseaux AEP.',
                'source': 'fallback',
            },
            {
                'type_turbine': 'pat_pump_as_turbine',
                'diametre_mm': 100,
                'pression_min_bar': 1.0,
                'pression_max_bar': 12.0,
                'debit_min_m3h': 20.0,
                'debit_max_m3h': 100.0,
                'puissance_min_kw': 5.0,
                'puissance_max_kw': 30.0,
                'rendement_typique': 0.74,
                'prix_estime_eur': 12400,
                'description': 'PAT polyvalente reseaux AEP.',
                'source': 'fallback',
            },
            {
                'type_turbine': 'pat_industrial',
                'diametre_mm': 150,
                'pression_min_bar': 3.0,
                'pression_max_bar': 15.0,
                'debit_min_m3h': 40.0,
                'debit_max_m3h': 180.0,
                'puissance_min_kw': 10.0,
                'puissance_max_kw': 40.0,
                'rendement_typique': 0.76,
                'prix_estime_eur': 16200,
                'description': 'PAT industrielle optimise.',
                'source': 'fallback',
            },
        ]
    )


# =========================================================
# 📥 Loader turbine DB
# =========================================================

def load_turbine_db(path=None):
    if path:
        candidates = [path]

        if not os.path.isabs(path):
            module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            candidates.append(os.path.join(module_root, path))

        for c in candidates:
            if os.path.exists(c):
                return pd.read_csv(c)

    return _fallback_turbine_db()


# =========================================================
# ⚡ Calcul puissance hydraulique (IMPORTANT)
# =========================================================

def compute_pe(delta_p_bar, flow_m3h, eta=0.75):
    """
    Puissance électrique estimée (kW)

    P = ΔP * Q * η
    avec conversions SI.
    """

    if delta_p_bar is None or flow_m3h is None:
        return 0

    delta_p_pa = delta_p_bar * 1e5      # bar → Pa
    flow_m3s = flow_m3h / 3600          # m³/h → m³/s

    pe_watts = delta_p_pa * flow_m3s * eta
    return pe_watts / 1000  # kW


# =========================================================
# ⚙️ Sélection turbine (VERSION INGÉNIEUR COMPLÈTE)
# =========================================================

def select_turbine(prv_df, turbine_db):

    prv_df = prv_df.copy()

    results = {
        "Pe_kw": [],
        "turbine_type_1": [],
        "turbine_diameter_mm_1": [],
        "turbine_type_2": [],
        "turbine_diameter_mm_2": [],
        "turbine_type_3": [],
        "turbine_diameter_mm_3": [],
    }

    for _, row in prv_df.iterrows():

        pressure = row.get("delta_p", 0) or 0
        flow = row.get("estimated_flow_obs", 0) or 0
        diameter = row.get("diameter", 0) or 0

        # =====================================================
        # ⚡ calcul puissance réelle du site
        # =====================================================
        Pe = compute_pe(pressure, flow, eta=0.75)
        results["Pe_kw"].append(Pe)

        # =====================================================
        # 🔧 filtre turbines
        # =====================================================
        candidates = turbine_db[
          
            (turbine_db["puissance_min_kw"] <= Pe) &
            (turbine_db["puissance_max_kw"] >= Pe)
        ].copy()

        if len(candidates) == 0:
            for k in list(results.keys())[1:]:
                results[k].append("None")
            continue

        # =====================================================
        # 🔥 SCORE HYBRIDE (hydraulique + énergétique)
        # =====================================================

        candidates["score"] = (
            abs(candidates["debit_max_m3h"] - flow) / (flow + 1e-6) +
            abs(candidates["pression_max_bar"] - pressure) / (pressure + 1e-6) +
            abs(candidates["diametre_mm"] - diameter) / (diameter + 1e-6) +
            abs(candidates["puissance_max_kw"] - Pe) / (Pe + 1e-6)
        )

        candidates = candidates.sort_values("score").reset_index(drop=True)

        # =====================================================
        # 🥇 TOP 3
        # =====================================================

        def safe(i):
            return candidates.iloc[i] if i < len(candidates) else None

        for idx, tkey, dkey in [
            (0, "turbine_type_1", "turbine_diameter_mm_1"),
            (1, "turbine_type_2", "turbine_diameter_mm_2"),
            (2, "turbine_type_3", "turbine_diameter_mm_3"),
        ]:
            c = safe(idx)
            if c is not None:
                results[tkey].append(c["type_turbine"])
                results[dkey].append(c["diametre_mm"])
            else:
                results[tkey].append("None")
                results[dkey].append(None)

    for k, v in results.items():
        prv_df[k] = v

    return prv_df


# =========================================================
# 💾 EXPORT
# =========================================================

def export_selected_turbines_to_csv(df, path):
    df.to_csv(path, index=False)