import os

import numpy as np
import pandas as pd


def _fallback_turbine_db():
    return pd.DataFrame(
        [
            {
                "type_turbine": "pico_inline",
                "diametre_mm": 25,
                "pression_min_bar": 0.1,
                "pression_max_bar": 2.0,
                "debit_min_m3h": 1.0,
                "debit_max_m3h": 6.0,
                "puissance_min_kw": 0.1,
                "puissance_max_kw": 1.0,
                "rendement_typique": 0.55,
                "prix_estime_eur": 3500,
                "description": "Micro turbine inline a tres faible debit.",
                "source": "fallback",
            },
            {
                "type_turbine": "micro_inline",
                "diametre_mm": 80,
                "pression_min_bar": 0.5,
                "pression_max_bar": 8.0,
                "debit_min_m3h": 5.0,
                "debit_max_m3h": 40.0,
                "puissance_min_kw": 1.0,
                "puissance_max_kw": 10.0,
                "rendement_typique": 0.68,
                "prix_estime_eur": 8500,
                "description": "Turbine inline pour reseaux AEP.",
                "source": "fallback",
            },
            {
                "type_turbine": "pat_pump_as_turbine",
                "diametre_mm": 100,
                "pression_min_bar": 1.0,
                "pression_max_bar": 12.0,
                "debit_min_m3h": 20.0,
                "debit_max_m3h": 100.0,
                "puissance_min_kw": 5.0,
                "puissance_max_kw": 30.0,
                "rendement_typique": 0.74,
                "prix_estime_eur": 12400,
                "description": "PAT polyvalente reseaux AEP.",
                "source": "fallback",
            },
            {
                "type_turbine": "pat_industrial",
                "diametre_mm": 150,
                "pression_min_bar": 3.0,
                "pression_max_bar": 15.0,
                "debit_min_m3h": 40.0,
                "debit_max_m3h": 180.0,
                "puissance_min_kw": 10.0,
                "puissance_max_kw": 40.0,
                "rendement_typique": 0.76,
                "prix_estime_eur": 16200,
                "description": "PAT industrielle optimise.",
                "source": "fallback",
            },
        ]
    )


def load_turbine_db(path=None):
    if path:
        candidates = [path]

        if not os.path.isabs(path):
            module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            candidates.append(os.path.join(module_root, path))

        for candidate in candidates:
            if os.path.exists(candidate):
                return pd.read_csv(candidate)

    return _fallback_turbine_db()


def compute_pe(delta_p_bar, flow_m3h, eta=0.75):
    """Estimate the electric power in kW from pressure and flow."""

    delta_p_bar = pd.to_numeric(delta_p_bar, errors="coerce")
    flow_m3h = pd.to_numeric(flow_m3h, errors="coerce")
    eta = pd.to_numeric(eta, errors="coerce")

    if pd.isna(delta_p_bar) or pd.isna(flow_m3h) or pd.isna(eta):
        return np.nan
    if delta_p_bar <= 0 or flow_m3h <= 0 or eta <= 0:
        return np.nan

    delta_p_pa = delta_p_bar * 1e5
    flow_m3s = flow_m3h / 3600.0
    pe_watts = delta_p_pa * flow_m3s * eta
    return pe_watts / 1000.0


def _first_numeric(row, candidates):
    for key in candidates:
        if key not in row:
            continue
        value = pd.to_numeric(row.get(key), errors="coerce")
        if pd.notna(value):
            return float(value)
    return np.nan


def _interval_score(value, minimum, maximum):
    if pd.isna(value) or pd.isna(minimum) or pd.isna(maximum):
        return np.inf

    if minimum > maximum:
        minimum, maximum = maximum, minimum

    if minimum <= value <= maximum:
        center = 0.5 * (minimum + maximum)
        half_span = max(0.5 * (maximum - minimum), 1e-6)
        return abs(value - center) / half_span

    distance = minimum - value if value < minimum else value - maximum
    scale = max(abs(value), abs(minimum), abs(maximum), 1.0)
    return 1.0 + distance / scale


def _build_candidate_scores(candidates, flow, pressure, pe, diameter):
    if candidates.empty:
        return candidates

    scored = candidates.copy()
    for column in ["debit_min_m3h", "debit_max_m3h", "pression_min_bar", "pression_max_bar", "puissance_min_kw", "puissance_max_kw", "diametre_mm", "rendement_typique"]:
        if column in scored.columns:
            scored[column] = pd.to_numeric(scored[column], errors="coerce")

    flow_scores = []
    pressure_scores = []
    power_scores = []
    diameter_scores = []
    efficiency_scores = []

    for _, candidate in scored.iterrows():
        flow_scores.append(_interval_score(flow, candidate.get("debit_min_m3h"), candidate.get("debit_max_m3h")))
        pressure_scores.append(_interval_score(pressure, candidate.get("pression_min_bar"), candidate.get("pression_max_bar")))

        power_min = candidate.get("puissance_min_kw")
        power_max = candidate.get("puissance_max_kw")
        if pd.notna(pe) and pd.notna(power_min) and pd.notna(power_max):
            power_scores.append(_interval_score(pe, power_min, power_max))
        else:
            power_scores.append(0.0)

        if pd.notna(diameter) and pd.notna(candidate.get("diametre_mm")):
            site_diameter = max(abs(diameter), 1.0)
            diameter_scores.append(abs(candidate.get("diametre_mm") - diameter) / site_diameter)
        else:
            diameter_scores.append(0.0)

        rendement = pd.to_numeric(candidate.get("rendement_typique"), errors="coerce")
        efficiency_scores.append(0.0 if pd.isna(rendement) else max(0.0, 1.0 - float(rendement)))

    scored["score"] = (
        0.38 * np.asarray(flow_scores)
        + 0.38 * np.asarray(pressure_scores)
        + 0.16 * np.asarray(power_scores)
        + 0.04 * np.asarray(diameter_scores)
        + 0.04 * np.asarray(efficiency_scores)
    )

    if "rendement_typique" in scored.columns:
        scored["rendement_typique"] = pd.to_numeric(scored["rendement_typique"], errors="coerce")

    return scored.sort_values(
        by=["score", "rendement_typique"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)


def rank_compatible_turbines(site_row, turbine_db, max_results=2, second_score_ratio=1.1):
    """Return the best physically compatible turbines for a site row."""

    pressure = _first_numeric(site_row, ["delta_p", "pressure_bar", "hauteur_charge_bar", "head_bar"])
    flow = _first_numeric(site_row, ["estimated_flow_obs"])
    diameter = _first_numeric(site_row, ["diameter", "diametre_mm"])
    pe = compute_pe(pressure, flow, eta=0.75)

    if pd.isna(pressure) or pd.isna(flow) or pressure <= 0 or flow <= 0:
        return turbine_db.iloc[0:0].copy()

    working_db = turbine_db.copy()
    for column in ["debit_min_m3h", "debit_max_m3h", "pression_min_bar", "pression_max_bar", "puissance_min_kw", "puissance_max_kw", "diametre_mm", "rendement_typique"]:
        if column in working_db.columns:
            working_db[column] = pd.to_numeric(working_db[column], errors="coerce")

    required_columns = ["debit_min_m3h", "debit_max_m3h", "pression_min_bar", "pression_max_bar"]
    if any(column not in working_db.columns for column in required_columns):
        return working_db.iloc[0:0].copy()

    compatible = working_db[
        (working_db["debit_min_m3h"].notna())
        & (working_db["debit_max_m3h"].notna())
        & (working_db["pression_min_bar"].notna())
        & (working_db["pression_max_bar"].notna())
        & (working_db["debit_min_m3h"] <= flow)
        & (working_db["debit_max_m3h"] >= flow)
        & (working_db["pression_min_bar"] <= pressure)
        & (working_db["pression_max_bar"] >= pressure)
    ].copy()

    if compatible.empty:
        return compatible

    site_power_kw = pe
    if pd.isna(site_power_kw) or site_power_kw <= 0:
        return compatible.iloc[0:0].copy()

    # Keep only turbines whose nominal power range really fits the site power.
    compatible = compatible[
        (compatible["puissance_min_kw"].notna())
        & (compatible["puissance_max_kw"].notna())
        & (compatible["puissance_min_kw"] <= site_power_kw)
        & (compatible["puissance_max_kw"] >= site_power_kw)
    ].copy()

    if compatible.empty:
        return compatible

    ranked = _build_candidate_scores(compatible, flow, pressure, pe, diameter)
    ranked = ranked.head(max(int(max_results), 1)).reset_index(drop=True)

    if len(ranked) > 1:
        first_score = ranked.iloc[0].get("score")
        second_score = ranked.iloc[1].get("score")
        if pd.notna(first_score) and pd.notna(second_score) and second_score > first_score * float(second_score_ratio):
            ranked = ranked.head(1).reset_index(drop=True)

    return ranked


def select_turbine(prv_df, turbine_db, top_n=2):
    """Filter turbines by hydraulic compatibility and keep the best matches.

    The filter is strict on the site constraints first: flow and pressure/head must
    fit inside the turbine operating envelope. Ranking is only applied after the
    physically compatible subset has been built.
    """

    prv_df = prv_df.copy()
    turbine_db = turbine_db.copy()

    results = {
        "Pe_kw": [],
        "turbine_type_1": [],
        "turbine_diameter_mm_1": [],
        "turbine_type_2": [],
        "turbine_diameter_mm_2": [],
        "turbine_type_3": [],
        "turbine_diameter_mm_3": [],
        "rendement_typique": [],
    }

    for _, row in prv_df.iterrows():
        ranked = rank_compatible_turbines(row, turbine_db, max_results=top_n)
        pressure = _first_numeric(row, ["delta_p", "pressure_bar", "hauteur_charge_bar", "head_bar"])
        flow = _first_numeric(row, ["estimated_flow_obs"])
        diameter = _first_numeric(row, ["diameter", "diametre_mm"])

        pe = compute_pe(pressure, flow, eta=0.75)
        results["Pe_kw"].append(pe if pd.notna(pe) else np.nan)

        if ranked.empty:
            for key in [
                "turbine_type_1",
                "turbine_diameter_mm_1",
                "turbine_type_2",
                "turbine_diameter_mm_2",
                "turbine_type_3",
                "turbine_diameter_mm_3",
            ]:
                results[key].append(None if "diameter" in key else "None")
            results["rendement_typique"].append(0.75)  # Default rendement
            continue

        selected_rows = [ranked.iloc[i] if i < len(ranked) else None for i in range(min(len(ranked), 2))]

        # Récupérer le rendement de la première turbine sélectionnée
        first_turbine = selected_rows[0] if len(selected_rows) > 0 and selected_rows[0] is not None else None
        if first_turbine is not None and pd.notna(first_turbine.get("rendement_typique")):
            results["rendement_typique"].append(float(first_turbine.get("rendement_typique")))
        else:
            results["rendement_typique"].append(0.75)

        for idx, tkey, dkey in [
            (0, "turbine_type_1", "turbine_diameter_mm_1"),
            (1, "turbine_type_2", "turbine_diameter_mm_2"),
        ]:
            candidate = selected_rows[idx] if idx < len(selected_rows) else None
            if candidate is not None and pd.notna(candidate.get("type_turbine")):
                results[tkey].append(candidate.get("type_turbine"))
                results[dkey].append(candidate.get("diametre_mm"))
            else:
                results[tkey].append("None")
                results[dkey].append(None)

        # Third slot kept for backward compatibility, but left empty by design.
        results["turbine_type_3"].append("None")
        results["turbine_diameter_mm_3"].append(None)

    for key, values in results.items():
        prv_df[key] = values

    return prv_df