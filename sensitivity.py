import argparse
import math
from dataclasses import dataclass, replace
from inputs import G0, PAYLOAD_LBS, DV_BUDGET, MASS_MARGIN
from models import calc_boost_phase_eff_ISP, calc_boost_phase_dV
from physics import (
    calc_k, calc_MR, calc_m_prop, calc_m_inert, calc_m_stage,
    calc_m0, calc_boost_phase_m_burn, calc_core_only_dv, calc_s1_dV
)

G0_FPS2: float = G0 # ft/s^2


@dataclass
class VehicleParams:
    m_payload_lb: float = PAYLOAD_LBS
    stage1_mf: float = 0.94
    stage2_mf: float = 0.91
    booster_mf: float = 0.88
    stage1_isp_s: float = 300.0
    stage1_isp_vac_s: float = 315.0
    stage2_isp_s: float = 450.0
    booster_isp_s: float = 280.0
    n_boosters: int = 2
    m_booster_prop_lb: float = 97500.0
    m_booster_inert_lb: float = 11100.0
    t_burn_booster_s: float = 90.0
    stage1_core_mdot_lb_s: float = 2500.0
    mass_margin: float = MASS_MARGIN
    dv_required_fps: float = DV_BUDGET
    stage1_dv_split: float = 0.45
    current_glow_lb: float | None = None


@dataclass
class SensitivityDriver:
    name: str
    param_attr: str
    delta_rel_pct: float
    unit_str: str
    category_group: str
    is_absolute_delta: bool = False
    # Which fixed-hardware metrics are physically meaningful for this driver.
    # Payload: perturbing payload is the input, so "payload lost" is n/a.
    # dV split: only changes how the vehicle is SIZED, so a fixed vehicle sees nothing.
    reports_dv: bool = True
    reports_payload: bool = True


def has_boosters(params: VehicleParams) -> bool:
    return params.n_boosters > 0 and params.m_booster_prop_lb > 0.0


def params_with_hardware_boosters(params: VehicleParams, masses: dict[str, float]) -> VehicleParams:
    # The booster inert mass used by the dV equations MUST be the margined hardware mass
    # that is actually in the GLOW. params.m_booster_inert_lb is only the raw user input.
    if not has_boosters(params):
        return params
    inert_unit_lb = masses["m_booster_inert_tot_lb"] / params.n_boosters
    return replace(params, m_booster_inert_lb=inert_unit_lb)


def calc_stage1_delivered_dv(
    glow_lb: float,
    m_s1_prop_lb: float,
    m_s1_inert_lb: float,
    m_above_lb: float,
    params: VehicleParams,
    g0_fps2: float = G0_FPS2
) -> tuple[float, float, float]:
    # Stage 1 delta-V using physics and models functions
    use_boosters = has_boosters(params)
    if not use_boosters:
        m_burnout_lb = m_above_lb + m_s1_inert_lb
        mass_ratio_term = glow_lb / m_burnout_lb
        eff_c = g0_fps2 * params.stage1_isp_s
        dv_s1_fps = eff_c * math.log(mass_ratio_term)
        return dv_s1_fps, 0.0, dv_s1_fps

    mdot_strap_tot = params.n_boosters * (params.m_booster_prop_lb / params.t_burn_booster_s)
    isp_eff_s = calc_boost_phase_eff_ISP(
        params.booster_isp_s, params.stage1_isp_s, mdot_strap_tot, params.stage1_core_mdot_lb_s
    )
    m_strap_prop_tot_lb = params.n_boosters * params.m_booster_prop_lb
    m_strap_inert_tot_lb = params.n_boosters * params.m_booster_inert_lb
    m_strap_tot_lb = m_strap_prop_tot_lb + m_strap_inert_tot_lb

    m_liq_boost_lb = calc_boost_phase_m_burn(params.stage1_core_mdot_lb_s, params.t_burn_booster_s)
    dv_boost_fps = calc_boost_phase_dV(
        glow_lb, m_strap_prop_tot_lb, m_liq_boost_lb, isp_eff_s, g0=g0_fps2
    )

    dv_core_fps = calc_core_only_dv(
        params.stage1_isp_vac_s, glow_lb, m_strap_tot_lb, m_liq_boost_lb, m_s1_prop_lb, g0=g0_fps2
    )
    dv_s1_fps = calc_s1_dV(dv_boost_fps, dv_core_fps)
    return dv_s1_fps, dv_boost_fps, dv_core_fps


def calc_stage2_delivered_dv(
    m_payload_lb: float,
    m_s2_prop_lb: float,
    m_s2_inert_lb: float,
    s2_isp_s: float,
    g0_fps2: float = G0_FPS2
) -> tuple[float, float]:
    # Stage 2 delivered delta-V and burnout mass
    m0_s2_lb = m_payload_lb + m_s2_prop_lb + m_s2_inert_lb
    mf_s2_lb = m_payload_lb + m_s2_inert_lb
    ratio = m0_s2_lb / mf_s2_lb
    eff_c = g0_fps2 * s2_isp_s
    dv_s2_fps = eff_c * math.log(ratio)
    return dv_s2_fps, mf_s2_lb


def calc_stage1_core_prop_for_dv(
    dv1_target_fps: float,
    m_above_lb: float,
    k1: float,
    params: VehicleParams,
    g0_fps2: float = G0_FPS2
) -> float:
    # Solve core stage propellant required to meet target stage 1 delta-V
    use_boosters = has_boosters(params)
    if not use_boosters:
        mr1 = calc_MR(dv1_target_fps, params.stage1_isp_s, g0=g0_fps2)
        m_prop1_lb = calc_m_prop(mr1, m_above_lb, k1)
        return m_prop1_lb

    m_liq_boost_lb = calc_boost_phase_m_burn(params.stage1_core_mdot_lb_s, params.t_burn_booster_s)
    m_strap_prop_tot_lb = params.n_boosters * params.m_booster_prop_lb
    m_strap_inert_tot_lb = params.n_boosters * params.m_booster_inert_lb

    lo_lb = m_liq_boost_lb * 1.05
    hi_lb = max(lo_lb * 10.0, 8.0e6)

    def calc_test_dv(mp_core_lb: float) -> float:
        m_inert_core_lb = calc_m_inert(k1, mp_core_lb)
        glow_test_lb = m_above_lb + mp_core_lb + m_inert_core_lb + m_strap_prop_tot_lb + m_strap_inert_tot_lb
        dv_del, _, _ = calc_stage1_delivered_dv(glow_test_lb, mp_core_lb, m_inert_core_lb, m_above_lb, params, g0_fps2=g0_fps2)
        return dv_del

    if calc_test_dv(hi_lb) < dv1_target_fps:
        raise ValueError(
            f"Stage 1 cannot reach {dv1_target_fps:,.0f} ft/s even with {hi_lb:,.0f} lb core propellant; "
            "check mass fraction / ISP inputs."
        )

    for _ in range(60):
        mid_lb = 0.5 * (lo_lb + hi_lb)
        dv_mid = calc_test_dv(mid_lb)
        if dv_mid < dv1_target_fps:
            lo_lb = mid_lb
        else:
            hi_lb = mid_lb
    return hi_lb


def calc_sized_vehicle(params: VehicleParams, g0_fps2: float = G0_FPS2) -> dict[str, float]:
    # Size full vehicle stages to satisfy mission delta-V budget
    dv2_target_fps = params.dv_required_fps * (1.0 - params.stage1_dv_split)
    dv1_target_fps = params.dv_required_fps * params.stage1_dv_split

    multiplier_s2 = 1.0 + params.mass_margin
    k2 = calc_k(params.stage2_mf, multiplier=multiplier_s2)
    mr2 = calc_MR(dv2_target_fps, params.stage2_isp_s, g0=g0_fps2)
    m_s2_prop_lb = calc_m_prop(mr2, params.m_payload_lb, k2)
    m_s2_inert_lb = calc_m_inert(k2, m_s2_prop_lb)
    m_s2_total_lb = calc_m_stage(m_s2_prop_lb, m_s2_inert_lb)
    m_above_s1_lb = params.m_payload_lb + m_s2_total_lb

    use_boosters = has_boosters(params)
    if use_boosters:
        multiplier_b = 1.0 + params.mass_margin
        kb = calc_k(params.booster_mf, multiplier=multiplier_b)
        m_booster_inert_unit_lb = calc_m_inert(kb, params.m_booster_prop_lb)
        m_strap_prop_tot_lb = params.n_boosters * params.m_booster_prop_lb
        m_strap_inert_tot_lb = params.n_boosters * m_booster_inert_unit_lb
        vehicle_eval_params = replace(params, m_booster_inert_lb=m_booster_inert_unit_lb)
    else:
        kb = 0.0
        m_strap_prop_tot_lb = 0.0
        m_strap_inert_tot_lb = 0.0
        vehicle_eval_params = params
    m_boosters_tot_lb = m_strap_prop_tot_lb + m_strap_inert_tot_lb

    multiplier_s1 = 1.0 + params.mass_margin
    k1 = calc_k(params.stage1_mf, multiplier=multiplier_s1)
    m_s1_prop_lb = calc_stage1_core_prop_for_dv(dv1_target_fps, m_above_s1_lb, k1, vehicle_eval_params, g0_fps2=g0_fps2)
    m_s1_inert_lb = calc_m_inert(k1, m_s1_prop_lb)
    m_s1_total_lb = calc_m_stage(m_s1_prop_lb, m_s1_inert_lb)

    glow_lb = calc_m0(params.m_payload_lb, [m_s2_total_lb, m_s1_total_lb, m_boosters_tot_lb])

    dv1_del_fps, dv_boost_fps, dv_core_fps = calc_stage1_delivered_dv(
        glow_lb, m_s1_prop_lb, m_s1_inert_lb, m_above_s1_lb, vehicle_eval_params, g0_fps2=g0_fps2
    )
    dv2_del_fps, _ = calc_stage2_delivered_dv(
        params.m_payload_lb, m_s2_prop_lb, m_s2_inert_lb, params.stage2_isp_s, g0_fps2=g0_fps2
    )
    dv_tot_fps = dv1_del_fps + dv2_del_fps

    return {
        "glow_lb": glow_lb,
        "m_payload_lb": params.m_payload_lb,
        "m_s2_prop_lb": m_s2_prop_lb,
        "m_s2_inert_lb": m_s2_inert_lb,
        "m_s2_total_lb": m_s2_total_lb,
        "m_s1_prop_lb": m_s1_prop_lb,
        "m_s1_inert_lb": m_s1_inert_lb,
        "m_s1_total_lb": m_s1_total_lb,
        "m_booster_prop_tot_lb": m_strap_prop_tot_lb,
        "m_booster_inert_tot_lb": m_strap_inert_tot_lb,
        "m_boosters_tot_lb": m_boosters_tot_lb,
        "dv1_fps": dv1_del_fps,
        "dv2_fps": dv2_del_fps,
        "dv_boost_fps": dv_boost_fps,
        "dv_core_fps": dv_core_fps,
        "dv_total_fps": dv_tot_fps,
        "k1": k1,
        "k2": k2,
        "kb": kb,
    }


def calc_vehicle_performance(
    params: VehicleParams,
    masses: dict[str, float],
    payload_override_lb: float | None = None,
    g0_fps2: float = G0_FPS2
) -> dict[str, float]:
    # Evaluate delivered delta-V for fixed hardware mass state
    m_pl_lb = payload_override_lb if payload_override_lb is not None else params.m_payload_lb
    m_s2_prop_lb = masses["m_s2_prop_lb"]
    m_s2_inert_lb = masses["m_s2_inert_lb"]
    m_s2_total_lb = calc_m_stage(m_s2_prop_lb, m_s2_inert_lb)
    m_above_s1_lb = m_pl_lb + m_s2_total_lb

    m_s1_prop_lb = masses["m_s1_prop_lb"]
    m_s1_inert_lb = masses["m_s1_inert_lb"]
    m_s1_total_lb = calc_m_stage(m_s1_prop_lb, m_s1_inert_lb)

    m_strap_prop_tot_lb = masses.get("m_booster_prop_tot_lb", 0.0)
    m_strap_inert_tot_lb = masses.get("m_booster_inert_tot_lb", 0.0)
    m_boosters_tot_lb = m_strap_prop_tot_lb + m_strap_inert_tot_lb

    glow_lb = calc_m0(m_pl_lb, [m_s2_total_lb, m_s1_total_lb, m_boosters_tot_lb])

    eval_params = params_with_hardware_boosters(
        params, {"m_booster_inert_tot_lb": m_strap_inert_tot_lb}
    )
    dv1_del_fps, dv_boost_fps, dv_core_fps = calc_stage1_delivered_dv(
        glow_lb, m_s1_prop_lb, m_s1_inert_lb, m_above_s1_lb, eval_params, g0_fps2=g0_fps2
    )
    dv2_del_fps, _ = calc_stage2_delivered_dv(
        m_pl_lb, m_s2_prop_lb, m_s2_inert_lb, params.stage2_isp_s, g0_fps2=g0_fps2
    )
    dv_tot_fps = dv1_del_fps + dv2_del_fps

    return {
        "glow_lb": glow_lb,
        "dv1_fps": dv1_del_fps,
        "dv2_fps": dv2_del_fps,
        "dv_boost_fps": dv_boost_fps,
        "dv_core_fps": dv_core_fps,
        "dv_total_fps": dv_tot_fps,
    }


def calc_max_payload_fixed_vehicle(
    params: VehicleParams,
    masses: dict[str, float],
    target_dv_fps: float,
    nominal_payload_lb: float,
    g0_fps2: float = G0_FPS2
) -> float:
    # Largest payload a FIXED vehicle can carry while still delivering target_dv_fps
    lo_pl_lb = 0.0
    hi_pl_lb = nominal_payload_lb * 2.0

    def dv_at(pl_lb: float) -> float:
        return calc_vehicle_performance(params, masses, payload_override_lb=pl_lb, g0_fps2=g0_fps2)["dv_total_fps"]

    if dv_at(lo_pl_lb) < target_dv_fps:
        return float("nan")  # vehicle cannot make the dV even with zero payload
    if dv_at(hi_pl_lb) > target_dv_fps:
        return float("nan")  # bracket too small, do not report a clipped number

    for _ in range(60):
        mid_pl_lb = 0.5 * (lo_pl_lb + hi_pl_lb)
        if dv_at(mid_pl_lb) > target_dv_fps:
            lo_pl_lb = mid_pl_lb
        else:
            hi_pl_lb = mid_pl_lb
    return 0.5 * (lo_pl_lb + hi_pl_lb)


def calc_fixed_hardware_masses(
    pert_params: VehicleParams,
    base_sized: dict[str, float]
) -> dict[str, float]:
    # Hold propellant loads fixed, but recompute inert masses from the perturbed mass
    # fractions AND margin. Unperturbed stages reproduce their baseline values exactly.
    fixed = dict(base_sized)
    mult = 1.0 + pert_params.mass_margin

    k1 = calc_k(pert_params.stage1_mf, multiplier=mult)
    fixed["m_s1_inert_lb"] = calc_m_inert(k1, fixed["m_s1_prop_lb"])
    fixed["m_s1_total_lb"] = calc_m_stage(fixed["m_s1_prop_lb"], fixed["m_s1_inert_lb"])

    k2 = calc_k(pert_params.stage2_mf, multiplier=mult)
    fixed["m_s2_inert_lb"] = calc_m_inert(k2, fixed["m_s2_prop_lb"])
    fixed["m_s2_total_lb"] = calc_m_stage(fixed["m_s2_prop_lb"], fixed["m_s2_inert_lb"])

    if has_boosters(pert_params):
        kb = calc_k(pert_params.booster_mf, multiplier=mult)
        fixed["m_booster_inert_tot_lb"] = pert_params.n_boosters * calc_m_inert(kb, pert_params.m_booster_prop_lb)
        fixed["m_boosters_tot_lb"] = fixed["m_booster_prop_tot_lb"] + fixed["m_booster_inert_tot_lb"]
    return fixed


def calc_sensitivity_driver(
    driver: SensitivityDriver,
    base_params: VehicleParams,
    base_sized: dict[str, float],
    g0_fps2: float = G0_FPS2
) -> dict[str, float | str]:
    # Evaluate sizing and performance sensitivities for a single perturbed driver
    nan = float("nan")
    val_nom = getattr(base_params, driver.param_attr)
    if driver.is_absolute_delta:
        val_pert = val_nom + driver.delta_rel_pct
        delta_x = driver.delta_rel_pct
        pct_x = (delta_x / val_nom) * 100.0 if val_nom != 0.0 else 0.0
    else:
        factor = 1.0 + driver.delta_rel_pct / 100.0
        val_pert = val_nom * factor
        delta_x = val_pert - val_nom
        pct_x = driver.delta_rel_pct

    pert_dict = {driver.param_attr: val_pert}
    if driver.param_attr == "stage1_isp_s":
        pert_dict["stage1_isp_vac_s"] = base_params.stage1_isp_vac_s * (1.0 + driver.delta_rel_pct / 100.0)

    pert_params = replace(base_params, **pert_dict)

    # --- (1) RESIZED vehicle: how much does GLOW grow to still close the mission?
    sized_pert = calc_sized_vehicle(pert_params, g0_fps2=g0_fps2)
    glow_nom_lb = base_sized["glow_lb"]
    delta_glow_lb = sized_pert["glow_lb"] - glow_nom_lb
    pct_glow = (delta_glow_lb / glow_nom_lb) * 100.0
    d_glow_d_x = delta_glow_lb / delta_x if delta_x != 0.0 else 0.0

    # --- (2) FIXED vehicle: same hardware, perturbed physics -> delivered dV and payload
    # Nominal reference is the SAME fixed-hardware evaluator, so any baseline mismatch cancels.
    perf_nom = calc_vehicle_performance(base_params, base_sized, g0_fps2=g0_fps2)
    fixed_masses = calc_fixed_hardware_masses(pert_params, base_sized)
    perf_pert = calc_vehicle_performance(pert_params, fixed_masses, g0_fps2=g0_fps2)

    delta_dv_fps = perf_pert["dv_total_fps"] - perf_nom["dv_total_fps"]
    pct_dv = (delta_dv_fps / perf_nom["dv_total_fps"]) * 100.0

    # Payload that the degraded fixed vehicle can carry against the (possibly perturbed)
    # dV requirement, relative to what the nominal fixed vehicle can carry.
    pl_nom_lb = calc_max_payload_fixed_vehicle(
        base_params, base_sized, base_params.dv_required_fps, base_params.m_payload_lb, g0_fps2=g0_fps2
    )
    pl_pert_lb = calc_max_payload_fixed_vehicle(
        pert_params, fixed_masses, pert_params.dv_required_fps, base_params.m_payload_lb, g0_fps2=g0_fps2
    )
    delta_payload_lb = pl_pert_lb - pl_nom_lb
    pct_payload = (delta_payload_lb / base_params.m_payload_lb) * 100.0

    if not driver.reports_dv:
        delta_dv_fps, pct_dv = nan, nan
    if not driver.reports_payload:
        delta_payload_lb, pct_payload = nan, nan

    return {
        "name": driver.name,
        "group": driver.category_group,
        "param_attr": driver.param_attr,
        "unit": driver.unit_str,
        "val_nom": val_nom,
        "val_pert": val_pert,
        "delta_x": delta_x,
        "pct_x": pct_x,
        "delta_glow_lb": delta_glow_lb,
        "pct_glow": pct_glow,
        "delta_dv_fps": delta_dv_fps,
        "pct_dv": pct_dv,
        "delta_payload_lb": delta_payload_lb,
        "pct_payload": pct_payload,
        "d_glow_d_x": d_glow_d_x,
    }


def build_default_drivers() -> list[SensitivityDriver]:
    # Construct extensible list of standard sensitivity study categories
    drivers = [
        SensitivityDriver("Stage 1 Mass Fraction", "stage1_mf", -1.0, "fraction", "Mass Fractions"),
        SensitivityDriver("Stage 2 Mass Fraction", "stage2_mf", -1.0, "fraction", "Mass Fractions"),
        SensitivityDriver("Booster Mass Fraction", "booster_mf", -1.0, "fraction", "Mass Fractions"),
        SensitivityDriver("Booster ISP", "booster_isp_s", -1.0, "s", "Engine ISP"),
        SensitivityDriver("Stage 1 Engine ISP", "stage1_isp_s", -1.0, "s", "Engine ISP"),
        SensitivityDriver("Stage 2 Engine ISP", "stage2_isp_s", -1.0, "s", "Engine ISP"),
        SensitivityDriver("Required Delta-V", "dv_required_fps", +1.0, "ft/s", "Mission Requirements"),
        SensitivityDriver("Payload Weight", "m_payload_lb", +1.0, "lb", "Mission Requirements", reports_payload=False),
        SensitivityDriver("Mass Margin (+1% abs)", "mass_margin", +0.01, "fraction", "Margins", is_absolute_delta=True),
        SensitivityDriver("Stage 1 Delta-V Split", "stage1_dv_split", +1.0, "fraction", "Trajectory", reports_dv=False, reports_payload=False),
    ]
    return drivers


def check_baseline(
    params: VehicleParams,
    base_sized: dict[str, float],
    glow_tol: float = 0.025,
    g0_fps2: float = G0_FPS2
) -> list[str]:
    # Sanity checks that catch a sensitivity study run on the wrong baseline vehicle
    warnings: list[str] = []

    replay = calc_vehicle_performance(params, base_sized, g0_fps2=g0_fps2)
    if abs(replay["dv_total_fps"] - base_sized["dv_total_fps"]) > 1.0:
        warnings.append(
            f"Fixed-hardware replay dV ({replay['dv_total_fps']:,.1f}) != sizing dV "
            f"({base_sized['dv_total_fps']:,.1f}) ft/s. Sizing and performance models disagree."
        )
    if abs(base_sized["dv_total_fps"] - params.dv_required_fps) > 1.0:
        warnings.append(
            f"Sized vehicle delivers {base_sized['dv_total_fps']:,.1f} ft/s vs "
            f"{params.dv_required_fps:,.1f} ft/s required."
        )
    if params.current_glow_lb:
        err = (base_sized["glow_lb"] - params.current_glow_lb) / params.current_glow_lb
        if abs(err) > glow_tol:
            warnings.append(
                f"Sized baseline GLOW {base_sized['glow_lb']:,.0f} lb is {err * 100.0:+.1f}% off the "
                f"design GLOW {params.current_glow_lb:,.0f} lb. These sensitivities describe a DIFFERENT "
                "vehicle (stale inputs, or margin applied twice)."
            )
    return warnings


def print_baseline_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print("\n" + "!" * 105)
    print(" BASELINE CHECK FAILED - DO NOT QUOTE THE TABLES BELOW UNTIL THIS IS RESOLVED")
    for w in warnings:
        print(f"  * {w}")
    print("!" * 105)


def calc_sensitivity_sweep(
    params: VehicleParams,
    drivers: list[SensitivityDriver] | None = None,
    g0_fps2: float = G0_FPS2
) -> tuple[dict[str, float], list[dict[str, float | str]]]:
    # Run sensitivity evaluations for all registered driver cases
    if drivers is None:
        drivers = build_default_drivers()
    base_sized = calc_sized_vehicle(params, g0_fps2=g0_fps2)
    results: list[dict[str, float | str]] = []
    for driver in drivers:
        case_res = calc_sensitivity_driver(driver, params, base_sized, g0_fps2=g0_fps2)
        results.append(case_res)
    return base_sized, results


def calc_exchange_ratios(
    params: VehicleParams,
    base_sized: dict[str, float],
    g0_fps2: float = G0_FPS2
) -> dict[str, float]:
    # Compute partial derivatives of GLOW with respect to key system parameters
    glow_nom_lb = base_sized["glow_lb"]

    p_pl = replace(params, m_payload_lb=params.m_payload_lb + 1000.0)
    d_glow_d_mpl = (calc_sized_vehicle(p_pl, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 1000.0

    p_dv = replace(params, dv_required_fps=params.dv_required_fps + 100.0)
    d_glow_d_dv = (calc_sized_vehicle(p_dv, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 100.0

    p_s1_isp = replace(params, stage1_isp_s=params.stage1_isp_s + 5.0, stage1_isp_vac_s=params.stage1_isp_vac_s + 5.0)
    d_glow_d_s1_isp = (calc_sized_vehicle(p_s1_isp, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 5.0

    p_s2_isp = replace(params, stage2_isp_s=params.stage2_isp_s + 5.0)
    d_glow_d_s2_isp = (calc_sized_vehicle(p_s2_isp, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 5.0

    p_s1_mf = replace(params, stage1_mf=params.stage1_mf + 0.005)
    d_glow_d_s1_mf = (calc_sized_vehicle(p_s1_mf, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 0.005

    p_s2_mf = replace(params, stage2_mf=params.stage2_mf + 0.005)
    d_glow_d_s2_mf = (calc_sized_vehicle(p_s2_mf, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 0.005

    d_glow_d_b_isp = 0.0
    d_glow_d_b_mf = 0.0
    if params.n_boosters > 0:
        p_b_isp = replace(params, booster_isp_s=params.booster_isp_s + 5.0)
        d_glow_d_b_isp = (calc_sized_vehicle(p_b_isp, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 5.0
        p_b_mf = replace(params, booster_mf=params.booster_mf + 0.005)
        d_glow_d_b_mf = (calc_sized_vehicle(p_b_mf, g0_fps2=g0_fps2)["glow_lb"] - glow_nom_lb) / 0.005

    return {
        "d_glow_d_payload_lb_per_lb": d_glow_d_mpl,
        "d_glow_d_dv_lb_per_fps": d_glow_d_dv,
        "d_glow_d_s1_isp_lb_per_s": d_glow_d_s1_isp,
        "d_glow_d_s2_isp_lb_per_s": d_glow_d_s2_isp,
        "d_glow_d_booster_isp_lb_per_s": d_glow_d_b_isp,
        "d_glow_d_booster_mf_lb_per_point": d_glow_d_b_mf * 0.01,
        "d_glow_d_s1_mf_lb_per_point": d_glow_d_s1_mf * 0.01,
        "d_glow_d_s2_mf_lb_per_point": d_glow_d_s2_mf * 0.01,
    }


def print_vehicle_summary(baseline: dict[str, float], params: VehicleParams) -> None:
    # Print baseline launch vehicle mass budget and mission parameters
    print("=" * 105)
    print(" BASELINE LAUNCH VEHICLE ARCHITECTURE & MASS BUDGET")
    print("=" * 105)
    print(f"  Mission Payload Weight : {params.m_payload_lb:>12,.0f} lb")
    print(f"  Required Mission dV    : {params.dv_required_fps:>12,.0f} ft/s")
    print(f"  Nominal Baseline GLOW  : {baseline['glow_lb']:>12,.0f} lb")
    print(f"  Vehicle Mass Margin    : {params.mass_margin * 100.0:>12.1f} %")
    print("-" * 105)
    print("  STAGE 2 (Upper Stage):")
    print(f"    Propellant Mass      : {baseline['m_s2_prop_lb']:>12,.0f} lb")
    print(f"    Inert Dry Mass       : {baseline['m_s2_inert_lb']:>12,.0f} lb  (k = {baseline['k2']:.4f})")
    print(f"    Total Stage Mass     : {baseline['m_s2_total_lb']:>12,.0f} lb")
    print(f"    Engine Vacuum ISP    : {params.stage2_isp_s:>12.1f} s")
    print(f"    Target Mass Fraction : {params.stage2_mf:>12.4f}")
    print(f"    Delivered dV         : {baseline['dv2_fps']:>12,.1f} ft/s")
    print("-" * 105)
    print("  STAGE 1 (Core Stage):")
    print(f"    Propellant Mass      : {baseline['m_s1_prop_lb']:>12,.0f} lb")
    print(f"    Inert Dry Mass       : {baseline['m_s1_inert_lb']:>12,.0f} lb  (k = {baseline['k1']:.4f})")
    print(f"    Total Core Mass      : {baseline['m_s1_total_lb']:>12,.0f} lb")
    print(f"    Core Avg / Vac ISP   : {params.stage1_isp_s:.1f} / {params.stage1_isp_vac_s:.1f} s")
    print(f"    Target Mass Fraction : {params.stage1_mf:>12.4f}")
    print(f"    Delivered dV         : {baseline['dv1_fps']:>12,.1f} ft/s")
    if params.n_boosters > 0:
        print("-" * 105)
        print(f"  STRAP-ON BOOSTERS ({params.n_boosters} strap-on units):")
        print(f"    Total Propellant Mass: {baseline['m_booster_prop_tot_lb']:>12,.0f} lb")
        print(f"    Total Inert Dry Mass : {baseline['m_booster_inert_tot_lb']:>12,.0f} lb  (k = {baseline['kb']:.4f})")
        print(f"    Booster Avg ISP      : {params.booster_isp_s:>12.1f} s")
        print(f"    Boost Phase Burn Time: {params.t_burn_booster_s:>12.1f} s")
        print(f"    Boost Phase dV       : {baseline['dv_boost_fps']:>12,.1f} ft/s")
        print(f"    Core Alone Phase dV  : {baseline['dv_core_fps']:>12,.1f} ft/s")
    print("=" * 105)


def print_sensitivity_table(results: list[dict[str, float | str]]) -> None:
    # Print formatted sensitivity comparison table with sizing and performance deltas
    print("\n" + "=" * 118)
    print(" SYSTEM MASS SENSITIVITY & PERFORMANCE LOSS MATRIX")
    print("=" * 118)
    hdr = (
        f"{'Category / Perturbation':<28} "
        f"{'Perturb':>9} "
        f"{'dGLOW [lb]':>14} "
        f"{'dGLOW [%]':>10} "
        f"{'ddV [fps]':>11} "
        f"{'ddV [%]':>9} "
        f"{'dPayload [lb]':>15} "
        f"{'dPayload [%]':>13}"
    )
    print(hdr)
    print("-" * 118)

    for r in results:
        name_str = str(r["name"])
        pct_x_val = float(r["pct_x"])
        pert_str = f"{pct_x_val:+.1f}%"
        dglow = float(r["delta_glow_lb"])
        pct_glow = float(r["pct_glow"])
        ddv = float(r["delta_dv_fps"])
        pct_dv = float(r["pct_dv"])
        dpl = float(r["delta_payload_lb"])
        pct_pl = float(r["pct_payload"])

        def na(x: float, fmt: str, width: int, suffix: str = "") -> str:
            return f"{'n/a':>{width}}" if math.isnan(x) else f"{x:{fmt}}{suffix}"

        row_str = (
            f"{name_str:<28} "
            f"{pert_str:>9} "
            f"{dglow:>+14,.0f} "
            f"{pct_glow:>+9.2f}% "
            f"{na(ddv, '>+11,.1f', 11)} "
            f"{na(pct_dv, '>+8.2f', 8, '%')} "
            f"{na(dpl, '>+15,.0f', 15)} "
            f"{na(pct_pl, '>+12.2f', 12, '%')}"
        )
        print(row_str)
    print("=" * 118)


def print_exchange_ratios(ratios: dict[str, float]) -> None:
    # Print partial derivative exchange ratios of GLOW
    print("\n" + "=" * 80)
    print(" SIZING EXCHANGE RATIOS & PARTIAL DERIVATIVES (dGLOW / dx)")
    print("=" * 80)
    print(f"  Payload Growth Factor (dGLOW / dPayload)  : {ratios['d_glow_d_payload_lb_per_lb']:>10.2f} lb / lb")
    print(f"  Delta-V Sizing Cost   (dGLOW / d(dV))     : {ratios['d_glow_d_dv_lb_per_fps']:>10.1f} lb / (ft/s)")
    print(f"  Stage 1 ISP Trade     (dGLOW / d(ISP_1))  : {ratios['d_glow_d_s1_isp_lb_per_s']:>10.1f} lb / s")
    print(f"  Stage 2 ISP Trade     (dGLOW / d(ISP_2))  : {ratios['d_glow_d_s2_isp_lb_per_s']:>10.1f} lb / s")
    if ratios["d_glow_d_booster_isp_lb_per_s"] != 0.0:
        print(f"  Booster ISP Trade     (dGLOW / d(ISP_b))  : {ratios['d_glow_d_booster_isp_lb_per_s']:>10.1f} lb / s")
        print(f"  Booster Mass Fraction (dGLOW / 1% mf_b)   : {ratios['d_glow_d_booster_mf_lb_per_point']:>10.1f} lb / point")
    print(f"  Stage 1 Mass Fraction (dGLOW / 1% mf_1)   : {ratios['d_glow_d_s1_mf_lb_per_point']:>10.1f} lb / point")
    print(f"  Stage 2 Mass Fraction (dGLOW / 1% mf_2)   : {ratios['d_glow_d_s2_mf_lb_per_point']:>10.1f} lb / point")
    print("=" * 80)


def print_sensitivity_rankings(results: list[dict[str, float | str]]) -> None:
    # Rank drivers by impact per 1% relative change (perturbations are NOT all 1%, e.g. margin is +4% rel.)
    print("\n" + "=" * 80)
    print(" KEY SENSITIVITY RANKINGS (IMPACT PER 1% RELATIVE CHANGE, NORMALIZED)")
    print("=" * 80)

    def per_pct(r: dict[str, float | str], key: str) -> float:
        pct_x = abs(float(r["pct_x"]))
        return float(r[key]) / pct_x if pct_x > 0.0 else 0.0

    sorted_glow = sorted(results, key=lambda x: abs(per_pct(x, "delta_glow_lb")), reverse=True)
    print("  Ranked by Sizing Impact (GLOW change per 1%):")
    for idx, r in enumerate(sorted_glow[:5], start=1):
        print(f"    {idx}. {r['name']:<25} : {per_pct(r, 'delta_glow_lb'):>+11,.0f} lb "
              f"({per_pct(r, 'pct_glow'):>+6.2f}%)")

    dv_rows = [r for r in results if not math.isnan(float(r["delta_dv_fps"]))]
    sorted_dv = sorted(dv_rows, key=lambda x: abs(per_pct(x, "delta_dv_fps")), reverse=True)
    print("\n  Ranked by Fixed Vehicle Degradation (dV change per 1%):")
    for idx, r in enumerate(sorted_dv[:5], start=1):
        dpl = per_pct(r, "delta_payload_lb")
        pl_str = "n/a" if math.isnan(dpl) else f"{dpl:>+9,.0f} lb payload"
        print(f"    {idx}. {r['name']:<25} : {per_pct(r, 'delta_dv_fps'):>+8,.1f} ft/s "
              f"({per_pct(r, 'pct_dv'):>+5.2f}%) -> {pl_str}")
    print("=" * 80)


def calc_unmargined_mf(m_prop_lb: float, m_inert_lb: float, margin: float) -> float:
    # calc_sized_vehicle APPLIES the margin to the mass fraction it is given. If the cfg's
    # inert mass already contains the margin, feeding its mf straight back in margins twice.
    k_with_margin = m_inert_lb / m_prop_lb
    k_base = k_with_margin / (1.0 + margin)
    return 1.0 / (1.0 + k_base)


def calc_params_from_working_cfg(
    working_cfg: dict,
    liquid_stages_include_margin: bool = True,
    booster_includes_margin: bool = False
) -> VehicleParams:
    # Extract VehicleParams from sizing2 working_cfg dictionary
    s1 = working_cfg["Stage 1"]
    s2 = working_cfg.get("Stage 2")
    n_strap = getattr(s1, "n_strapons", 0)
    strap_eng = getattr(s1, "strapon_eng", None)
    has_strap = n_strap > 0 and strap_eng is not None

    b_prop = strap_eng.m_prop if has_strap else 97500.0
    b_tot = strap_eng.m_tot if has_strap else 108600.0
    b_inert = strap_eng.m_inert if has_strap else 11100.0
    b_isp = strap_eng.isp_avg if has_strap else 280.0
    b_tburn = strap_eng.t_burn if has_strap else 90.0
    if has_strap:
        b_mf = (calc_unmargined_mf(b_prop, b_tot - b_prop, MASS_MARGIN)
                if booster_includes_margin else b_prop / b_tot)
    else:
        b_mf = 0.88

    core_eng = s1.core_eng
    n_core = getattr(s1, "n_core_eng", 1)
    core_mdot = getattr(core_eng, "mdot", 2500.0) * n_core

    s1_prop = getattr(s1, "m_prop_liquid", s1.m_prop)
    s1_inert = getattr(s1, "m_inert", 0.0)
    s1_strap_inert = getattr(s1, "m_strapon_inert", 0.0) or 0.0
    s1_core_inert = s1_inert - s1_strap_inert
    if s1_prop > 0 and s1_core_inert > 0:
        s1_mf = (calc_unmargined_mf(s1_prop, s1_core_inert, MASS_MARGIN)
                 if liquid_stages_include_margin else s1_prop / (s1_prop + s1_core_inert))
    else:
        s1_mf = 0.94

    s2_prop = getattr(s2, "m_prop", 800000.0) if s2 else 800000.0
    s2_tot = getattr(s2, "m_total", 900000.0) if s2 else 900000.0
    if s2_tot > s2_prop > 0:
        s2_mf = (calc_unmargined_mf(s2_prop, s2_tot - s2_prop, MASS_MARGIN)
                 if liquid_stages_include_margin else s2_prop / s2_tot)
    else:
        s2_mf = 0.91
    s2_isp = getattr(s2, "ISP", 450.0) if s2 else 450.0

    tot_dv_delivered = working_cfg.get("dV_delivered", DV_BUDGET)
    s1_split = (s1.dV_delivered / tot_dv_delivered) if tot_dv_delivered > 0 else 0.45

    return VehicleParams(
        m_payload_lb=PAYLOAD_LBS,
        stage1_mf=s1_mf,
        stage2_mf=s2_mf,
        booster_mf=b_mf,
        stage1_isp_s=getattr(core_eng, "isp_avg", 300.0),
        stage1_isp_vac_s=getattr(core_eng, "isp_vac", 315.0),
        stage2_isp_s=s2_isp,
        booster_isp_s=b_isp,
        n_boosters=n_strap,
        m_booster_prop_lb=b_prop,
        m_booster_inert_lb=b_inert,
        t_burn_booster_s=b_tburn,
        stage1_core_mdot_lb_s=core_mdot,
        mass_margin=MASS_MARGIN,
        dv_required_fps=DV_BUDGET,
        stage1_dv_split=s1_split,
        current_glow_lb=working_cfg.get("GLOW"),
    )


def calc_and_print_cfg_sensitivity(working_cfg: dict) -> None:
    # Run and print sensitivity study for a sized configuration dictionary
    if "Stage 1" not in working_cfg:
        return
    cfg_params = calc_params_from_working_cfg(working_cfg)
    base_sized, results = calc_sensitivity_sweep(cfg_params)
    exchanges = calc_exchange_ratios(cfg_params, base_sized)
    print_vehicle_summary(base_sized, cfg_params)
    print_baseline_warnings(check_baseline(cfg_params, base_sized))
    print_sensitivity_table(results)
    print_exchange_ratios(exchanges)
    print_sensitivity_rankings(results)


def prompt_user_inputs(default_params: VehicleParams) -> VehicleParams:
    # Interactively prompt user for baseline vehicle parameters with defaults
    print("\n" + "=" * 70)
    print(" INTERACTIVE VEHICLE PARAMETER SETUP (Press Enter for default)")
    print("=" * 70)

    def ask_float(prompt_text: str, default_val: float) -> float:
        user_val = input(f"{prompt_text} [{default_val:g}]: ").strip()
        if not user_val:
            return default_val
        return float(user_val)

    def ask_int(prompt_text: str, default_val: int) -> int:
        user_val = input(f"{prompt_text} [{default_val}]: ").strip()
        if not user_val:
            return default_val
        return int(user_val)

    m_pl = ask_float("Payload Weight (lb)", default_params.m_payload_lb)
    dv_req = ask_float("Required Mission dV (ft/s)", default_params.dv_required_fps)
    s1_mf = ask_float("Stage 1 Mass Fraction (e.g. 0.94)", default_params.stage1_mf)
    s2_mf = ask_float("Stage 2 Mass Fraction (e.g. 0.91)", default_params.stage2_mf)
    s1_isp = ask_float("Stage 1 Engine ISP (s)", default_params.stage1_isp_s)
    s1_isp_vac = ask_float("Stage 1 Vacuum ISP (s)", default_params.stage1_isp_vac_s)
    s2_isp = ask_float("Stage 2 Engine ISP (s)", default_params.stage2_isp_s)
    n_b = ask_int("Number of Strap-on Boosters (0 for 2-stage)", default_params.n_boosters)

    b_isp = default_params.booster_isp_s
    b_mf = default_params.booster_mf
    b_prop = default_params.m_booster_prop_lb
    b_inert = default_params.m_booster_inert_lb
    if n_b > 0:
        b_isp = ask_float("Booster ISP (s)", default_params.booster_isp_s)
        b_mf = ask_float("Booster Mass Fraction", default_params.booster_mf)
        b_prop = ask_float("Booster Propellant Mass per Unit (lb)", default_params.m_booster_prop_lb)
        b_inert = ask_float("Booster Inert Dry Mass per Unit (lb)", default_params.m_booster_inert_lb)

    margin = ask_float("Structural Mass Margin fraction (e.g. 0.25)", default_params.mass_margin)
    s1_split = ask_float("Stage 1 dV Allocation Split (e.g. 0.45)", default_params.stage1_dv_split)

    glow_override_str = input("Current GLOW Override [leave blank to auto-size]: ").strip()
    glow_override = float(glow_override_str) if glow_override_str else None

    return VehicleParams(
        m_payload_lb=m_pl,
        stage1_mf=s1_mf,
        stage2_mf=s2_mf,
        booster_mf=b_mf,
        stage1_isp_s=s1_isp,
        stage1_isp_vac_s=s1_isp_vac,
        stage2_isp_s=s2_isp,
        booster_isp_s=b_isp,
        n_boosters=n_b,
        m_booster_prop_lb=b_prop,
        m_booster_inert_lb=b_inert,
        t_burn_booster_s=default_params.t_burn_booster_s,
        stage1_core_mdot_lb_s=default_params.stage1_core_mdot_lb_s,
        mass_margin=margin,
        dv_required_fps=dv_req,
        stage1_dv_split=s1_split,
        current_glow_lb=glow_override,
    )


def main() -> None:
    # Command line entry point for vehicle mass sensitivity analysis
    parser = argparse.ArgumentParser(description="Launch Vehicle Mass Sensitivity & Performance Loss Analysis")
    parser.add_argument("-i", "--interactive", action="store_true", help="Prompt for baseline parameters interactively")
    parser.add_argument("--payload", type=float, default=PAYLOAD_LBS, help="Payload weight in lb")
    parser.add_argument("--dv", type=float, default=DV_BUDGET, help="Required mission delta-V in ft/s")
    parser.add_argument("--s1-mf", type=float, default=0.94, help="Stage 1 propellant mass fraction")
    parser.add_argument("--s2-mf", type=float, default=0.91, help="Stage 2 propellant mass fraction")
    parser.add_argument("--booster-mf", type=float, default=0.88, help="Booster propellant mass fraction")
    parser.add_argument("--s1-isp", type=float, default=300.0, help="Stage 1 ISP in seconds")
    parser.add_argument("--s1-isp-vac", type=float, default=315.0, help="Stage 1 vacuum ISP in seconds")
    parser.add_argument("--s2-isp", type=float, default=450.0, help="Stage 2 vacuum ISP in seconds")
    parser.add_argument("--booster-isp", type=float, default=280.0, help="Booster average ISP in seconds")
    parser.add_argument("--boosters", type=int, default=2, help="Number of strap-on boosters")
    parser.add_argument("--booster-prop", type=float, default=97500.0, help="Propellant per booster in lb")
    parser.add_argument("--booster-inert", type=float, default=11100.0, help="Inert dry mass per booster in lb")
    parser.add_argument("--margin", type=float, default=MASS_MARGIN, help="Structural mass margin")
    parser.add_argument("--s1-dv-split", type=float, default=0.45, help="Fraction of total dV for Stage 1")
    parser.add_argument("--glow", type=float, default=None, help="Current baseline GLOW override in lb")

    args = parser.parse_args()

    default_cfg = VehicleParams(
        m_payload_lb=args.payload,
        stage1_mf=args.s1_mf,
        stage2_mf=args.s2_mf,
        booster_mf=args.booster_mf,
        stage1_isp_s=args.s1_isp,
        stage1_isp_vac_s=args.s1_isp_vac,
        stage2_isp_s=args.s2_isp,
        booster_isp_s=args.booster_isp,
        n_boosters=args.boosters,
        m_booster_prop_lb=args.booster_prop,
        m_booster_inert_lb=args.booster_inert,
        mass_margin=args.margin,
        dv_required_fps=args.dv,
        stage1_dv_split=args.s1_dv_split,
        current_glow_lb=args.glow,
    )

    if args.interactive:
        cfg = prompt_user_inputs(default_cfg)
    else:
        cfg = default_cfg

    base_sized, results = calc_sensitivity_sweep(cfg)
    exchanges = calc_exchange_ratios(cfg, base_sized)

    print_vehicle_summary(base_sized, cfg)
    print_baseline_warnings(check_baseline(cfg, base_sized))
    print_sensitivity_table(results)
    print_exchange_ratios(exchanges)
    print_sensitivity_rankings(results)


if __name__ == "__main__":
    main()
