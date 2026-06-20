def estimate_power_kw(flow_ls, delta_p_bar, efficiency=0.65):
    """
    Estime la puissance hydraulique (kW) a partir du debit moyen et de la chute de pression.
    """
    flow_ls = float(flow_ls or 0)
    delta_p_bar = float(delta_p_bar or 0)
    efficiency = float(efficiency or 0)

    return 0.098 * flow_ls * delta_p_bar * efficiency


def _integration_factor_range(level):
    level = (level or "").strip().lower()
    if level in {"simple", "prv_simple"}:
        return 1.0, 1.0
    if level in {"moyen", "moyenne", "medium", "adaptation"}:
        return 1.2, 1.2
    if level in {"complexe", "complex", "chantier"}:
        return 1.5, 2.0
    return 1.0, 1.0


def _electrical_cost_range(level):
    level = (level or "").strip().lower()
    if level in {"simple", "bt", "basse_tension"}:
        return 0.0, 5000.0
    if level in {"complexe", "complex", "hta", "longue_distance"}:
        return 5000.0, 20000.0
    return 0.0, 5000.0


def compute_capex(
    flow_ls,
    delta_p_bar,
    integration_level="simple",
    electrical_level="simple",
    efficiency=0.65,
    turbine_cost_eur=0.0,
    **kwargs,
):
    """
    Calcule un CAPEX simplifie (PRV -> micro-turbine) avec une estimation nominale et une fourchette.
    """
    power_kw = estimate_power_kw(flow_ls, delta_p_bar, efficiency=efficiency)

    capex_fixe_min = 2800.0
    capex_fixe_max = 7500.0
    capex_fixe_nominal = 2800.0  # Valeur minimale pour installation simple

    capex_fixe = capex_fixe_nominal
    capex_variable = 0.0
    if "turbine_cost_eur" in kwargs and turbine_cost_eur == 0.0:
        turbine_cost_eur = kwargs.get("turbine_cost_eur")
    turbine_cost_eur = float(turbine_cost_eur or 0.0)
    capex_base = 12000.0 + turbine_cost_eur

    int_min, int_max = _integration_factor_range(integration_level)
    elec_min, elec_max = _electrical_cost_range(electrical_level)

    int_nominal = (int_min + int_max) / 2.0
    elec_nominal = (elec_min + elec_max) / 2.0

    capex_integre_min = capex_base * int_min
    capex_integre_max = capex_base * int_max
    capex_integre_nominal = capex_base * int_nominal

    capex_total_min = capex_fixe_min + capex_integre_min + elec_min
    capex_total_max = capex_fixe_max + capex_integre_max + elec_max
    capex_total_nominal = capex_fixe_nominal + capex_integre_nominal + elec_nominal

    return {
        "power_kw": power_kw,
        "capex_fixe": capex_fixe,
        "capex_fixe_min": capex_fixe_min,
        "capex_fixe_max": capex_fixe_max,
        "capex_fixe_nominal": capex_fixe_nominal,
        "capex_variable": capex_variable,
        "capex_base": capex_base,
        "turbine_cost_eur": turbine_cost_eur,
        "capex_fixe_eur": capex_fixe,
        "capex_fixe_min_eur": capex_fixe_min,
        "capex_fixe_max_eur": capex_fixe_max,
        "capex_fixe_nominal_eur": capex_fixe_nominal,
        "capex_variable_eur": capex_variable,
        "capex_base_eur": capex_base,
        "base_cost_eur": capex_base,
        "integration_level": integration_level,
        "integration_factor_min": int_min,
        "integration_factor_max": int_max,
        "capex_integre": capex_integre_nominal,
        "capex_integre_min_eur": capex_integre_min,
        "capex_integre_nominal_eur": capex_integre_nominal,
        "capex_integre_max_eur": capex_integre_max,
        "electrical_level": electrical_level,
        "capex_elec": elec_nominal,
        "electrical_cost_min_eur": elec_min,
        "electrical_cost_max_eur": elec_max,
        "electrical_cost_nominal_eur": elec_nominal,
        "capex_total_min": capex_total_min,
        "capex_total_nominal": capex_total_nominal,
        "capex_total_max": capex_total_max,
        "capex_total_min_eur": capex_total_min,
        "capex_total_max_eur": capex_total_max,
        "capex_total_nominal_eur": capex_total_nominal,
        "capex_min_eur": capex_total_min,
        "capex_max_eur": capex_total_max,
        "capex_nominal_eur": capex_total_nominal,
    }
