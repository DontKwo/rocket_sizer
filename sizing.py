import math
import numpy as np
from inputs import (
    G0, G_LIMIT, PAYLOAD_LBS, MIN_VEHICLE_WEIGHT, MAX_VEHICLE_WEIGHT,
    MIN_LIFTOFF_TW0, MAX_LIFTOFF_TW0, MIN_CORE_ONLY_TW0, MAX_CORE_ONLY_TW0,
    DV_BUDGET, STAGE1_DV, STAGE2_DV, MAX_MAIN_ENGINES, MAX_STAGE2_ENGINES,
    MF_PROP_DICT, MASS_MARGIN
)
from engines import LIQUIDS, SOLIDS
from printing_funcs import print_results, StageSpecs
from sensitivity import calc_and_print_cfg_sensitivity
from checks import (
    stage_feasible, stage_dV_positive, hardware_inert_mass,
    glow_in_bounds, glow_improves, engine_count_ok, liftoff_TW_max, liftoff_TW_min,
    core_only_TW_min, core_only_TW_max, g_limit_ok,
    boost_burnout_mass_positive, core_survives_boost, core_burnout_mass_positive,
    stage1_dV_possible, is_better_candidate, upper_stage_TW0, core_prop_positive
)
from sizing import (
    BOOSTERS, STRAPON_COUNTS, CORE_ENG_COUNTS, UPPER_ENG_COUNTS,
    UPPER_TW0_BOUNDS, size_core_stage_masses, size_core_stage_engines
)

# Minimum feasible dry mass of 2 strap-ons used for early pruning
MIN_S1_DRY = min(b.m_tot * 2 for b in BOOSTERS) if BOOSTERS else 0.0


def calc_stage_k(eng: object, stage: int, margin: float = MASS_MARGIN) -> float:
    fuel = getattr(eng, "fuel", None)
    mf_pair = MF_PROP_DICT[fuel]
    mf = mf_pair[0] if stage == 1 else mf_pair[1]
    k_nominal = (1.0 - mf) / mf
    k_margined = k_nominal * (1.0 + margin)
    return k_margined


def calc_struct_k(eng: object, stage: int, margin: float = MASS_MARGIN) -> float:
    """Structural k (excludes engine mass). Margin applied only to structure."""
    fuel = getattr(eng, "fuel", None)
    mf_pair = MF_PROP_DICT[fuel]
    mf = mf_pair[0] if stage == 1 else mf_pair[1]
    k_nominal = (1.0 - mf) / mf
    k_struct = k_nominal * (1.0 + margin)
    return k_struct


def calc_stage_isp(eng: object, stage: int) -> float:
    """Stage 1 uses isp_avg (burns through atmosphere), upper stages use isp_vac."""
    if stage == 1:
        return eng.isp_avg
    return eng.isp_vac


def calc_unmargined_inert(m_inert: float, margin: float) -> float:
    """Compute unmargined inert mass from margined inert mass."""
    if margin <= 0:
        return m_inert
    return m_inert / (1.0 + margin)


def size_upper_stage(
    eng: object,
    n_eng: int,
    dV: float,
    m_above: float,
    k: float,
    tw0_bounds: tuple,
    fails: dict,
    stage: int
) -> StageSpecs | None:
    """Size an upper stage using isp_vac (replaces sizing.size_stage for upper stages)."""
    ISP = calc_stage_isp(eng, stage)
    MR = math.exp(dV / (G0 * ISP))

    if not stage_feasible(k, MR, fails):
        return None

    # Solve for propellant mass: m_prop = (MR - 1) * m_above / (1 + k*(1 - MR))
    denom = 1 + k * (1 - MR)
    if denom <= 0:
        stage_feasible(k, MR, fails)
        return None
    m_prop = (MR - 1) * m_above / denom

    # Split inert: engines (known) + structure (margined via k)
    m_eng_total = eng.m_inert * n_eng
    m_struct = k * m_prop - m_eng_total
    m_inert = m_eng_total + max(0.0, m_struct)
    if not hardware_inert_mass(m_eng_total, m_inert, fails):
        return None

    m_total = m_prop + m_inert
    m0 = m_total + m_above
    thrust_total = eng.thrust_vac * n_eng
    TW0 = thrust_total / m0

    if not upper_stage_TW0(stage, *tw0_bounds, TW0, fails):
        return None

    # g-limit check with unmargined burnout mass (lighter = higher g, non-conservative)
    mf_margined = m0 - m_prop
    m_struct_unmargined = calc_unmargined_inert(max(0.0, m_struct), MASS_MARGIN)
    mf_unmargined = m0 - m_prop - max(0.0, m_struct) + m_struct_unmargined
    g_burnout_unmargined = eng.min_thrust_vac * n_eng / mf_unmargined if mf_unmargined > 0 else 1e10
    if not g_limit_ok(g_burnout_unmargined, G_LIMIT, fails):
        return None

    g_burnout = eng.min_thrust_vac * n_eng / mf_margined
    dV_delivered = ISP * G0 * math.log(m0 / mf_margined)
    tw_bo = thrust_total / mf_margined

    return StageSpecs(
        stage_number=stage, core_eng=eng, n_core_eng=n_eng,
        m0=m0, m_total=m_total, m_prop=m_prop, m_inert=m_inert,
        m_prop_liquid=m_prop,
        k=k, mass_ratio=MR, dV=dV, dV_delivered=dV_delivered,
        ISP=ISP, thrust_core=thrust_total, thrust_total=thrust_total, tw0=TW0,
        accel_core_burnout_min_g=g_burnout, tw_burnout=tw_bo,
    )


def solve_strapon_stage(
    core_eng: object,
    strapon_eng: object,
    n_core_eng: int,
    n_strapons: int,
    dV: float,
    m_above: float,
    max_glow_avail: float,
    fails: dict,
    stage: int = 1,
    mass_margin: float = MASS_MARGIN
) -> StageSpecs | None:
    s1_k = calc_stage_k(core_eng, stage, margin=mass_margin)
    m_burn_liquid = core_eng.mdot * n_core_eng * strapon_eng.t_burn
    m_strapons_prop = strapon_eng.m_prop * n_strapons
    strapon_m_inert = strapon_eng.m_inert * n_strapons
    strapon_m_inert_margined = strapon_m_inert * (1.0 + mass_margin)
    strapon_m_total_margined = m_strapons_prop + strapon_m_inert_margined
    strapon_m_total_real = strapon_eng.m_tot * n_strapons
    core_sl_thrust_total = core_eng.thrust_sl * n_core_eng
    liftoff_thrust = core_sl_thrust_total + strapon_eng.thrust_sl * n_strapons
    m_core_eng_total = core_eng.m_inert * n_core_eng

    # Core inert = n_eng * m_eng + k_struct * mp_core, where k_struct = s1_k
    # but engine mass is already counted in k*mp_core, so we use the full s1_k
    # GLOW = m_above + mp_core + s1_k * mp_core + m_strapons_prop + strapon_inert_margined
    # GLOW = m_above + (1 + s1_k) * mp_core + m_strapons_prop + strapon_inert_margined
    k1 = 1 + s1_k

    lo = m_burn_liquid * 1.0001
    hi = (max_glow_avail - m_above - m_strapons_prop - strapon_m_inert_margined) / k1
    if hi <= lo:
        return None

    mdot_strap_tot = strapon_eng.mdot * n_strapons
    mdot_core_tot = core_eng.mdot * n_core_eng
    ISP_eff = (strapon_eng.isp_avg * mdot_strap_tot + core_eng.isp_avg * mdot_core_tot) / (mdot_strap_tot + mdot_core_tot)
    c1 = ISP_eff * G0
    c2 = core_eng.isp_vac * G0

    def calc_dv_fast(mp_core: float) -> tuple[float, float, float, float, float]:
        m_core_total = k1 * mp_core
        GLOW = m_above + m_core_total + m_strapons_prop + strapon_m_inert_margined
        # Boost burnout: everything minus strap-on prop and liquid burned during boost
        mb = GLOW - m_strapons_prop - m_burn_liquid
        if mb <= 0:
            return -1.0, GLOW, mb, 0.0, 0.0
        # Core-only start: drop real strap-on hardware after boost
        m0c = GLOW - m_burn_liquid - strapon_m_total_real
        mfc = m0c - (mp_core - m_burn_liquid)
        if mfc <= 0 or m0c <= 0:
            return -1.0, GLOW, mb, m0c, mfc
        dv = c1 * math.log(GLOW / mb) + c2 * math.log(m0c / mfc)
        return dv, GLOW, mb, m0c, mfc

    dv_hi, glow_hi, _, _, _ = calc_dv_fast(hi)
    if not stage1_dV_possible(dv_hi, dV, fails):
        return None

    dv_lo, _, _, _, _ = calc_dv_fast(lo)
    if dv_lo >= dV:
        mp_core = lo
    else:
        for _ in range(16):
            mid = 0.5 * (lo + hi)
            dv_mid, _, _, _, _ = calc_dv_fast(mid)
            if dv_mid < dV:
                lo = mid
            else:
                hi = mid
        mp_core = hi

    dV_del, GLOW, m_boost_burnout, m0_core_only, m_core_burnout = calc_dv_fast(mp_core)
    if dV_del < 0:
        return None

    if not glow_in_bounds(MIN_VEHICLE_WEIGHT, MAX_VEHICLE_WEIGHT, GLOW, fails):
        return None

    if not glow_improves(GLOW, max_glow_avail, fails, strict=True):
        return None

    if not boost_burnout_mass_positive(m_boost_burnout, fails):
        return None

    if not core_survives_boost(m_burn_liquid, mp_core, fails):
        return None

    if not core_burnout_mass_positive(m_core_burnout, fails):
        return None

    liftoff_TW = liftoff_thrust / GLOW
    if not liftoff_TW_min(liftoff_TW, MIN_LIFTOFF_TW0, fails):
        return None
    if not liftoff_TW_max(liftoff_TW, MAX_LIFTOFF_TW0, fails):
        return None

    m_core_inert = s1_k * mp_core
    m_prop = mp_core + m_strapons_prop
    m_inert = m_core_inert + strapon_m_inert_margined
    if not hardware_inert_mass(m_core_eng_total + strapon_m_inert, m_inert, fails):
        return None

    thrust_core_vac = core_eng.thrust_vac * n_core_eng
    thrust_strap_vac = strapon_eng.avg_thrust_vac * n_strapons

    # g-limit: use unmargined burnout mass (lighter vehicle = worst case)
    m_core_struct = m_core_inert - m_core_eng_total
    m_core_struct_unmargined = calc_unmargined_inert(m_core_struct, mass_margin)
    strapon_inert_unmargined = strapon_m_inert
    margin_removed_boost = (strapon_m_inert_margined - strapon_inert_unmargined) + (m_core_struct - m_core_struct_unmargined)
    margin_removed_core = m_core_struct - m_core_struct_unmargined

    m_boost_burnout_unmargined = m_boost_burnout - margin_removed_boost
    m_core_burnout_unmargined = m_core_burnout - margin_removed_core

    g_boost_burnout = (thrust_strap_vac + core_eng.min_thrust_vac * n_core_eng) / m_boost_burnout_unmargined if m_boost_burnout_unmargined > 0 else 1e10
    if not g_limit_ok(g_boost_burnout, G_LIMIT, fails):
        return None

    g_core_burnout = core_eng.min_thrust_vac * n_core_eng / m_core_burnout_unmargined if m_core_burnout_unmargined > 0 else 1e10
    if not g_limit_ok(g_core_burnout, G_LIMIT, fails):
        return None

    core_only_tw0 = thrust_core_vac / m0_core_only
    if not core_only_TW_min(core_only_tw0, MIN_CORE_ONLY_TW0, fails):
        return None
    if not core_only_TW_max(core_only_tw0, MAX_CORE_ONLY_TW0, fails):
        return None

    tw_before_booster_sep = (thrust_strap_vac + thrust_core_vac) / m_boost_burnout
    tw_after_booster_sep = core_only_tw0
    tw_burnout = thrust_core_vac / m_core_burnout

    m_total = m_prop + m_inert
    boost_phase_dV = c1 * math.log(GLOW / m_boost_burnout)
    core_only_dV = dV_del - boost_phase_dV
    ISP = (strapon_eng.isp_avg + core_eng.isp_avg) / 2
    return StageSpecs(
        stage_number=stage, core_eng=core_eng, n_core_eng=n_core_eng, strapon_eng=strapon_eng,
        n_strapons=n_strapons, m0=GLOW, m_total=m_total, m_prop=m_prop, m_inert=m_inert,
        m_prop_liquid=mp_core, m_strapon_prop=m_strapons_prop,
        m_strapon_inert=strapon_m_inert_margined, m_liquid_burned_boost=m_burn_liquid,
        m_boost_burnout=m_boost_burnout, m0_core_only=m0_core_only,
        m_core_burnout=m_core_burnout,
        k=s1_k, mass_ratio=GLOW / (GLOW - m_prop), dV=dV, dV_delivered=dV_del,
        ISP=ISP, boost_eff_ISP=ISP_eff, boost_phase_dV=boost_phase_dV,
        core_only_dV=core_only_dV, thrust_core=core_sl_thrust_total,
        thrust_strapon=strapon_eng.thrust_sl * n_strapons, thrust_total=liftoff_thrust,
        tw0=liftoff_TW, accel_boost_burnout_min_g=g_boost_burnout,
        accel_core_burnout_min_g=g_core_burnout,
        tw_burnout=tw_burnout, tw_before_booster_sep=tw_before_booster_sep,
        tw_after_booster_sep=tw_after_booster_sep,
    )


def parse_same_engines(same_engines: object) -> list[set[int]]:
    if not same_engines:
        return []
    if all(isinstance(x, (int, float)) for x in same_engines):
        raw_groups = [set(int(x) for x in same_engines)]
    else:
        raw_groups = []
        for group in same_engines:
            if isinstance(group, (int, float)):
                raw_groups.append({int(group)})
            else:
                raw_groups.append(set(int(x) for x in group))
    merged: list[set[int]] = []
    for g in raw_groups:
        overlapping = [m for m in merged if not g.isdisjoint(m)]
        non_overlapping = [m for m in merged if g.isdisjoint(m)]
        new_set = g
        for m in overlapping:
            new_set = new_set.union(m)
        merged = non_overlapping + [new_set]
    return merged


def get_required_engine(stage_num: int, assigned_stages: dict, groups: list[set[int]]) -> object | None:
    for group in groups:
        if stage_num in group:
            for other_stage, eng in assigned_stages.items():
                if other_stage in group:
                    return eng
    return None


def make_working_cfg(stage1: StageSpecs, upper_stages: list[StageSpecs], total_engine_count: int) -> dict:
    working_cfg = {"Stage 1": stage1}
    for upper_stage in upper_stages:
        working_cfg[f"Stage {upper_stage.stage_number}"] = upper_stage

    working_cfg["GLOW"] = stage1.m0
    working_cfg["payload_frac"] = PAYLOAD_LBS / stage1.m0
    working_cfg["dV_delivered"] = stage1.dV_delivered + sum(
        upper_stage.dV_delivered for upper_stage in upper_stages)
    working_cfg["Total Engine Count"] = total_engine_count

    total_dv = working_cfg["dV_delivered"]
    if total_dv and total_dv > 0:
        stage1.dv_split_frac = stage1.dV_delivered / total_dv
        for upper_stage in upper_stages:
            upper_stage.dv_split_frac = upper_stage.dV_delivered / total_dv

    return working_cfg


def search_strapon_stage(
    upper_stages: list[StageSpecs],
    dV: float,
    working_cfg: dict,
    fails: dict,
    same_engines: object = None,
    mass_margin: float = MASS_MARGIN
) -> dict:
    m_above = PAYLOAD_LBS + sum(u.m_total for u in upper_stages)
    max_glow_avail = min(MAX_VEHICLE_WEIGHT, working_cfg['GLOW'])
    if m_above + MIN_S1_DRY >= max_glow_avail:
        return working_cfg

    n_upper_engines = sum(u.n_core_eng for u in upper_stages)

    assigned = {u.stage_number: u.core_eng for u in upper_stages}
    groups = parse_same_engines(same_engines)
    req_eng = get_required_engine(1, assigned, groups)
    candidate_liquids = [req_eng] if req_eng is not None else LIQUIDS

    for strapon_eng in BOOSTERS:
        for n_strapons in STRAPON_COUNTS:
            m_strapons_prop = strapon_eng.m_prop * n_strapons
            strap_thrust = strapon_eng.thrust_sl * n_strapons

            for core_eng in candidate_liquids:
                s1_k = calc_stage_k(core_eng, 1, margin=mass_margin)
                strapon_inert_margined = strapon_eng.m_inert * n_strapons * (1.0 + mass_margin)
                hi_base = (max_glow_avail - m_above - m_strapons_prop - strapon_inert_margined) / (1 + s1_k)
                if hi_base <= 0:
                    continue

                core_thrust_1 = core_eng.thrust_sl
                # Analytical bounds on n_core_eng to satisfy liftoff T/W
                n_core_min = max(1, math.ceil((MIN_LIFTOFF_TW0 * MIN_VEHICLE_WEIGHT - strap_thrust) / core_thrust_1))
                n_core_max = min(MAX_MAIN_ENGINES, math.floor((MAX_LIFTOFF_TW0 * max_glow_avail - strap_thrust) / core_thrust_1))
                burn_per_eng = core_eng.mdot * strapon_eng.t_burn
                if burn_per_eng > 0:
                    n_core_max = min(n_core_max, math.floor(hi_base / burn_per_eng))
                if n_core_min > n_core_max:
                    continue

                for n_core_eng in range(n_core_min, n_core_max + 1):
                    m_hardware_inert = n_core_eng * core_eng.m_inert + n_strapons * strapon_eng.m_inert
                    if m_above + m_hardware_inert >= max_glow_avail:
                        continue

                    stage1 = solve_strapon_stage(
                        core_eng, strapon_eng, n_core_eng, n_strapons, dV,
                        m_above, max_glow_avail, fails, stage=1, mass_margin=mass_margin
                    )
                    if stage1 is None:
                        continue
                    total_engine_count = n_core_eng + n_strapons + n_upper_engines
                    if is_better_candidate(stage1.m0, total_engine_count, working_cfg):
                        working_cfg = make_working_cfg(stage1, upper_stages, total_engine_count)
                        max_glow_avail = min(MAX_VEHICLE_WEIGHT, working_cfg['GLOW'])

    return working_cfg


def search_core_stage(
    upper_stages: list[StageSpecs],
    dV: float,
    working_cfg: dict,
    fails: dict,
    same_engines: object = None,
    mass_margin: float = MASS_MARGIN
) -> dict:
    m_above = PAYLOAD_LBS + sum(u.m_total for u in upper_stages)
    n_upper_engines = sum(u.n_core_eng for u in upper_stages)

    assigned = {u.stage_number: u.core_eng for u in upper_stages}
    groups = parse_same_engines(same_engines)
    req_eng = get_required_engine(1, assigned, groups)
    candidate_liquids = [req_eng] if req_eng is not None else LIQUIDS

    for core_eng in candidate_liquids:
        s1_k = calc_stage_k(core_eng, 1, margin=mass_margin)
        core_masses = size_core_stage_masses(core_eng, dV, m_above, s1_k,
            upper_stages, working_cfg, fails)
        if core_masses is None:
            continue

        n_core_min = max(1, math.ceil(MIN_LIFTOFF_TW0 * core_masses["GLOW"] / core_eng.thrust_sl))
        n_core_max = min(MAX_MAIN_ENGINES, math.floor(MAX_LIFTOFF_TW0 * core_masses["GLOW"] / core_eng.thrust_sl))
        if n_core_min > n_core_max:
            continue

        for n_core_eng in range(n_core_min, n_core_max + 1):
            total_engine_count = n_core_eng + n_upper_engines
            if not engine_count_ok(core_masses["GLOW"], working_cfg["GLOW"],
                    total_engine_count, working_cfg["Total Engine Count"], fails):
                break

            liftoff_thrust = core_eng.thrust_sl * n_core_eng
            liftoff_TW = liftoff_thrust / core_masses["GLOW"]

            stage1 = size_core_stage_engines(core_masses, core_eng, n_core_eng,
                liftoff_thrust, liftoff_TW, dV, s1_k, fails)
            if stage1 is None:
                continue

            if is_better_candidate(stage1.m0, total_engine_count, working_cfg):
                working_cfg = make_working_cfg(stage1, upper_stages, total_engine_count)

    return working_cfg


def search_upper_stages(
    stage: int,
    n_stages: int,
    upper_stages: list[StageSpecs],
    dV_left: float,
    dV_grid: object,
    search_stage1: object,
    working_cfg: dict,
    fails: dict,
    same_engines: object = None,
    mass_margin: float = MASS_MARGIN
) -> dict:
    m_above = PAYLOAD_LBS + sum(upper_stage.m_total for upper_stage in upper_stages)

    assigned = {u.stage_number: u.core_eng for u in upper_stages}
    groups = parse_same_engines(same_engines)
    req_eng = get_required_engine(stage, assigned, groups)
    candidate_liquids = [req_eng] if req_eng is not None else LIQUIDS

    total_outer = len(candidate_liquids)
    total_steps = total_outer * len(dV_grid)

    for outer_loop_iters, eng in enumerate(candidate_liquids):
        upper_k = calc_stage_k(eng, stage, margin=mass_margin)
        for dV_idx, dV in enumerate(dV_grid):
            dV_remaining = dV_left - dV
            if not stage_dV_positive(dV_remaining, fails):
                continue

            # Pre-filter using isp_vac for upper stages
            ISP = calc_stage_isp(eng, stage)
            MR = math.exp(dV / (G0 * ISP))
            denom = 1 + upper_k * (1 - MR)
            if denom <= 0:
                stage_feasible(upper_k, MR, fails)
                continue
            m_prop2 = (MR - 1) * m_above / denom
            m_total2 = m_prop2 * (1 + upper_k)
            m0_2 = m_above + m_total2

            if m0_2 + MIN_S1_DRY >= working_cfg['GLOW']:
                glow_improves(m0_2 + MIN_S1_DRY, working_cfg['GLOW'], fails, strict=True)
                continue

            # Analytical T/W filtering for upper stage engine count
            n_min = max(1, math.ceil(UPPER_TW0_BOUNDS[0] * m0_2 / eng.thrust_vac))
            n_max = min(MAX_STAGE2_ENGINES, math.floor(UPPER_TW0_BOUNDS[1] * m0_2 / eng.thrust_vac))
            if n_min > n_max:
                continue

            for n_eng in range(n_min, n_max + 1):
                stage_specs = size_upper_stage(eng, n_eng, dV, m_above, upper_k,
                    UPPER_TW0_BOUNDS, fails, stage)
                if stage_specs is None:
                    continue

                if stage == 2:
                    working_cfg = search_stage1(
                        upper_stages + [stage_specs],
                        dV_remaining,
                        working_cfg,
                        fails,
                        same_engines=same_engines,
                        mass_margin=mass_margin
                    )
                else:
                    working_cfg = search_upper_stages(
                        stage - 1,
                        n_stages,
                        upper_stages + [stage_specs],
                        dV_remaining,
                        dV_grid,
                        search_stage1,
                        working_cfg,
                        fails,
                        same_engines=same_engines,
                        mass_margin=mass_margin
                    )

            # Continuous in-place progress update
            update_interval = max(1, len(dV_grid) // 25)
            if stage == n_stages and (dV_idx % update_interval == 0 or dV_idx == len(dV_grid) - 1):
                cur_step = outer_loop_iters * len(dV_grid) + dV_idx + 1
                pct = (cur_step / total_steps) * 100 if total_steps else 100.0
                print(f"\r{pct:5.1f}% finished ({eng.name})", flush=True, end="")

        if stage == n_stages:
            pct = ((outer_loop_iters + 1) / total_outer) * 100 if total_outer else 100.0
            print(f"\r{pct:5.1f}% finished ({eng.name})", flush=True, end="")

    return working_cfg


def n_stage_sizing(
    n_stages: int,
    dV_grid: object,
    boosters: bool = False,
    same_engines: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    assert n_stages >= 2

    groups = parse_same_engines(same_engines)
    for g in groups:
        for s in g:
            if s < 1 or s > n_stages:
                raise ValueError(f"Stage {s} in same_engines is out of range for a {n_stages}-stage vehicle")

    # Subsample dense 1D grid for >=3 stage vehicles to ensure fast completion
    if n_stages >= 3 and len(dV_grid) > 100:
        target_pts = 40 if boosters else 60
        stride = math.ceil(len(dV_grid) / target_pts)
        print(f"Subsampling dV_grid by stride {stride} ({len(dV_grid)} -> {len(dV_grid[::stride])} points) for tractable {n_stages}-stage search.")
        dV_grid = dV_grid[::stride]

    n_liquids = len(LIQUIDS)
    n_dv = len(dV_grid)
    n_upper_eng = MAX_STAGE2_ENGINES
    loop_size = n_liquids * n_dv * n_upper_eng
    if n_stages >= 3:
        loop_size = n_liquids**2 * n_dv**2 * n_upper_eng**2
    if boosters:
        loop_size *= len(BOOSTERS) * len(STRAPON_COUNTS) * MAX_MAIN_ENGINES
        search_stage1 = search_strapon_stage
    else:
        search_stage1 = search_core_stage

    print(f"Running up to ~{loop_size:,} configurations.")
    working_cfg = {'GLOW': 1e100, 'Total Engine Count': 1e100}
    fails: dict[str, int] = {}

    working_cfg = search_upper_stages(
        n_stages, n_stages, [], DV_BUDGET, dV_grid,
        search_stage1, working_cfg, fails, same_engines=same_engines, mass_margin=mass_margin
    )

    print("\n")
    print_results(working_cfg, fails)
    if print_sensitivities and working_cfg.get("GLOW", 1e100) < 1e99:
        calc_and_print_cfg_sensitivity(working_cfg)
    return working_cfg


def two_stage_sizing(
    same_engines: object = None,
    dV_grid: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    if dV_grid is None:
        dV_grid = STAGE2_DV
    return n_stage_sizing(2, dV_grid, boosters=False, same_engines=same_engines, mass_margin=mass_margin, print_sensitivities=print_sensitivities)


def two_p_five_sizing(
    same_engines: object = None,
    dV_grid: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    if dV_grid is None:
        dV_grid = STAGE2_DV
    return n_stage_sizing(2, dV_grid, boosters=True, same_engines=same_engines, mass_margin=mass_margin, print_sensitivities=print_sensitivities)


def three_stage_sizing(
    same_engines: object = None,
    dV_grid: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    if dV_grid is None:
        dV_grid = np.linspace(0.12, 0.55, 60) * DV_BUDGET
    return n_stage_sizing(3, dV_grid, boosters=False, same_engines=same_engines, mass_margin=mass_margin, print_sensitivities=print_sensitivities)


def three_p_five_sizing(
    same_engines: object = None,
    dV_grid: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    if dV_grid is None:
        dV_grid = np.linspace(0.12, 0.55, 40) * DV_BUDGET
    return n_stage_sizing(3, dV_grid, boosters=True, same_engines=same_engines, mass_margin=mass_margin, print_sensitivities=print_sensitivities)


def find_engine(eng: object, engine_list: list | None = None) -> object | None:
    if eng is None:
        return None
    if not isinstance(eng, str):
        return eng
    if engine_list is None:
        engine_list = LIQUIDS + SOLIDS
    for e in engine_list:
        if e.name.upper() == eng.upper():
            return e
    raise ValueError(f"Engine '{eng}' not found in engine database.")


def eval_fixed_config(
    m_prop2: float,
    core_eng: object,
    n_core_eng: int,
    strapon_eng: object | None,
    n_strapons: int,
    upper_eng: object,
    n_upper_eng: int,
    GLOW: float,
    mass_margin: float = MASS_MARGIN
) -> tuple | None:
    """Size one fixed 2-stage or 2.5-stage vehicle with rigorous checks."""
    fails: dict[str, int] = {}
    glow_in_bounds(MIN_VEHICLE_WEIGHT, MAX_VEHICLE_WEIGHT, GLOW, fails)

    upper_k = calc_stage_k(upper_eng, 2, margin=mass_margin)
    s1_k = calc_stage_k(core_eng, 1, margin=mass_margin)

    # ---- Stage 2 (Upper Stage): use isp_vac
    ISP2 = calc_stage_isp(upper_eng, 2)
    m_inert2 = upper_k * m_prop2
    m_eng2 = upper_eng.m_inert * n_upper_eng
    m_total2 = m_prop2 + m_inert2
    m0_2 = PAYLOAD_LBS + m_total2
    mf_2 = m0_2 - m_prop2
    if mf_2 <= 0 or m0_2 <= 0:
        return None

    MR2 = m0_2 / mf_2
    dV2 = ISP2 * G0 * math.log(MR2)
    thrust2 = upper_eng.thrust_vac * n_upper_eng
    tw0_2 = thrust2 / m0_2
    tw_bo2 = thrust2 / mf_2

    hardware_inert_mass(m_eng2, m_inert2, fails)
    upper_stage_TW0(2, *UPPER_TW0_BOUNDS, tw0_2, fails)

    # g-limit: unmargined burnout for stage 2
    m_struct2 = m_inert2 - m_eng2
    m_struct2_unmargined = calc_unmargined_inert(max(0.0, m_struct2), mass_margin)
    mf_2_unmargined = mf_2 - max(0.0, m_struct2) + m_struct2_unmargined
    g_burnout2_unmargined = upper_eng.min_thrust_vac * n_upper_eng / mf_2_unmargined if mf_2_unmargined > 0 else 1e10
    g_limit_ok(g_burnout2_unmargined, G_LIMIT, fails)

    g_burnout2 = upper_eng.min_thrust_vac * n_upper_eng / mf_2

    # ---- Stage 1
    m_total1 = GLOW - m0_2
    if m_total1 <= 0:
        return None
    m_prop1 = m_total1 / (1 + s1_k)
    m_inert1 = s1_k * m_prop1
    dV1_required = DV_BUDGET - dV2

    has_strapons = (strapon_eng is not None) and (n_strapons > 0)

    if not has_strapons:
        # Pure liquid core stage (no strap-on boosters)
        m_eng1 = core_eng.m_inert * n_core_eng
        hardware_inert_mass(m_eng1, m_inert1, fails)
        core_sl_thrust = core_eng.thrust_sl * n_core_eng
        liftoff_TW = core_sl_thrust / GLOW
        liftoff_TW_max(liftoff_TW, MAX_LIFTOFF_TW0, fails)
        liftoff_TW_min(liftoff_TW, MIN_LIFTOFF_TW0, fails)

        mf_1 = GLOW - m_prop1
        if mf_1 <= 0:
            return None
        MR1 = GLOW / mf_1
        # Stage 1 core-only burns through atmosphere, use isp_avg
        dV1_delivered = core_eng.isp_avg * G0 * math.log(MR1)

        # g-limit: unmargined
        m_struct1 = m_inert1 - m_eng1
        m_struct1_unmargined = calc_unmargined_inert(max(0.0, m_struct1), mass_margin)
        mf_1_unmargined = mf_1 - max(0.0, m_struct1) + m_struct1_unmargined
        g_core_burnout_unmargined = core_eng.min_thrust_vac * n_core_eng / mf_1_unmargined if mf_1_unmargined > 0 else 1e10
        g_limit_ok(g_core_burnout_unmargined, G_LIMIT, fails)

        tw_bo1 = core_eng.thrust_vac * n_core_eng / mf_1
        g_core_burnout = core_eng.min_thrust_vac * n_core_eng / mf_1
        stage1_dV_possible(dV1_delivered, dV1_required, fails)

        s1 = dict(
            stage_number=1, core_eng=core_eng, n_core_eng=n_core_eng,
            strapon_eng=None, n_strapons=0, m0=GLOW,
            m_total=m_total1, m_prop=m_prop1, m_inert=m_inert1,
            m_prop_liquid=m_prop1, m_strapon_prop=0.0,
            m_strapon_inert=0.0, m_liquid_burned_boost=None,
            m_boost_burnout=None, m0_core_only=None, m_core_burnout=mf_1,
            k=s1_k, mass_ratio=MR1,
            dV=dV1_required, dV_delivered=dV1_delivered, ISP=core_eng.isp_avg,
            boost_eff_ISP=None, boost_phase_dV=None, core_only_dV=None,
            thrust_core=core_sl_thrust, thrust_strapon=0.0,
            thrust_total=core_sl_thrust, tw0=liftoff_TW,
            accel_boost_burnout_min_g=None, accel_core_burnout_min_g=g_core_burnout,
            tw_burnout=tw_bo1, tw_before_booster_sep=None, tw_after_booster_sep=None,
        )
    else:
        # Core with strap-on boosters: separate booster inert from core k
        m_strapons_prop = strapon_eng.m_prop * n_strapons
        strapon_m_inert_real = strapon_eng.m_inert * n_strapons
        strapon_m_inert_margined = strapon_m_inert_real * (1.0 + mass_margin)
        strapon_m_total_real = strapon_eng.m_tot * n_strapons
        strapon_sl_thrust_total = strapon_eng.thrust_sl * n_strapons

        # Recompute stage 1 with boosters treated separately
        # m_total1 = GLOW - m0_2 (already computed)
        # Core inert = s1_k * m_prop_core
        # Total S1 = m_prop_core + s1_k * m_prop_core + m_strapons_prop + strapon_inert_margined
        # m_total1 = (1 + s1_k) * m_prop_core + m_strapons_prop + strapon_inert_margined
        m_prop_core = (m_total1 - m_strapons_prop - strapon_m_inert_margined) / (1 + s1_k)
        if not core_prop_positive(m_prop_core, fails):
            return None

        m_core_inert = s1_k * m_prop_core
        m_prop1_actual = m_prop_core + m_strapons_prop
        m_inert1_actual = m_core_inert + strapon_m_inert_margined

        m_eng1 = core_eng.m_inert * n_core_eng
        hardware_inert_mass(m_eng1 + strapon_m_inert_real, m_inert1_actual, fails)
        core_sl_thrust = core_eng.thrust_sl * n_core_eng
        liftoff_thrust = core_sl_thrust + strapon_sl_thrust_total
        liftoff_TW = liftoff_thrust / GLOW
        liftoff_TW_max(liftoff_TW, MAX_LIFTOFF_TW0, fails)
        liftoff_TW_min(liftoff_TW, MIN_LIFTOFF_TW0, fails)

        m_burn_liquid = core_eng.mdot * n_core_eng * strapon_eng.t_burn
        m_boost_burnout = GLOW - m_strapons_prop - m_burn_liquid
        m0_core_only = GLOW - m_burn_liquid - strapon_m_total_real
        ok = boost_burnout_mass_positive(m_boost_burnout, fails)
        ok &= core_survives_boost(m_burn_liquid, m_prop_core, fails)
        ok &= core_burnout_mass_positive(m0_core_only, fails)
        if not ok:
            return None

        m_core_burnout = m0_core_only - (m_prop_core - m_burn_liquid)
        if not core_burnout_mass_positive(m_core_burnout, fails):
            return None

        thrust_core_vac = core_eng.thrust_vac * n_core_eng
        thrust_strap_vac = strapon_eng.avg_thrust_vac * n_strapons

        # g-limit: unmargined burnout mass (lighter = worse)
        m_core_struct = m_core_inert - m_eng1
        m_core_struct_unmargined = calc_unmargined_inert(max(0.0, m_core_struct), mass_margin)
        margin_removed_boost = (strapon_m_inert_margined - strapon_m_inert_real) + (max(0.0, m_core_struct) - m_core_struct_unmargined)
        margin_removed_core = max(0.0, m_core_struct) - m_core_struct_unmargined

        m_boost_bo_unmargined = m_boost_burnout - margin_removed_boost
        m_core_bo_unmargined = m_core_burnout - margin_removed_core

        g_boost_burnout = (thrust_strap_vac + core_eng.min_thrust_vac * n_core_eng) / m_boost_bo_unmargined if m_boost_bo_unmargined > 0 else 1e10
        g_core_burnout = core_eng.min_thrust_vac * n_core_eng / m_core_bo_unmargined if m_core_bo_unmargined > 0 else 1e10
        g_limit_ok(g_boost_burnout, G_LIMIT, fails)
        g_limit_ok(g_core_burnout, G_LIMIT, fails)

        core_only_tw0 = thrust_core_vac / m0_core_only
        core_only_TW_min(core_only_tw0, MIN_CORE_ONLY_TW0, fails)
        core_only_TW_max(core_only_tw0, MAX_CORE_ONLY_TW0, fails)

        tw_before_sep = (thrust_strap_vac + thrust_core_vac) / m_boost_burnout
        tw_after_sep = core_only_tw0
        tw_bo1 = thrust_core_vac / m_core_burnout

        core_only_dV = core_eng.isp_vac * G0 * math.log(m0_core_only / m_core_burnout)
        mdot_strap_tot = strapon_eng.mdot * n_strapons
        mdot_core_tot = core_eng.mdot * n_core_eng
        ISP_eff = (strapon_eng.isp_avg * mdot_strap_tot + core_eng.isp_avg * mdot_core_tot) / (mdot_strap_tot + mdot_core_tot)
        boost_phase_dV = ISP_eff * G0 * math.log(GLOW / m_boost_burnout)
        dV1_delivered = boost_phase_dV + core_only_dV

        stage1_dV_possible(dV1_delivered, dV1_required, fails)

        eff_MR = (GLOW / m_boost_burnout) * (m0_core_only / m_core_burnout)
        eff_ISP = dV1_delivered / (G0 * math.log(eff_MR)) if eff_MR > 1.0 else core_eng.isp_avg

        s1 = dict(
            stage_number=1, core_eng=core_eng, n_core_eng=n_core_eng,
            strapon_eng=strapon_eng, n_strapons=n_strapons, m0=GLOW,
            m_total=m_prop1_actual + m_inert1_actual, m_prop=m_prop1_actual, m_inert=m_inert1_actual,
            m_prop_liquid=m_prop_core, m_strapon_prop=m_strapons_prop,
            m_strapon_inert=strapon_m_inert_margined,
            m_liquid_burned_boost=m_burn_liquid, m_boost_burnout=m_boost_burnout,
            m0_core_only=m0_core_only, m_core_burnout=m_core_burnout,
            k=s1_k, mass_ratio=eff_MR,
            dV=dV1_required, dV_delivered=dV1_delivered, ISP=eff_ISP,
            boost_eff_ISP=ISP_eff, boost_phase_dV=boost_phase_dV,
            core_only_dV=core_only_dV, thrust_core=core_sl_thrust,
            thrust_strapon=strapon_sl_thrust_total, thrust_total=liftoff_thrust,
            tw0=liftoff_TW, accel_boost_burnout_min_g=g_boost_burnout,
            accel_core_burnout_min_g=g_core_burnout,
            tw_burnout=tw_bo1, tw_before_booster_sep=tw_before_sep,
            tw_after_booster_sep=tw_after_sep,
        )

    s2 = dict(
        stage_number=2, core_eng=upper_eng, n_core_eng=n_upper_eng, m0=m0_2,
        m_total=m_total2, m_prop=m_prop2, m_inert=m_inert2,
        m_prop_liquid=m_prop2, k=upper_k, mass_ratio=MR2, dV=dV2,
        dV_delivered=dV2, ISP=ISP2, thrust_core=thrust2, thrust_total=thrust2,
        tw0=tw0_2, accel_core_burnout_min_g=g_burnout2,
        tw_burnout=tw_bo2,
    )
    return s1, s2, fails, dV1_delivered + dV2


def specific_config_sizing(
    GLOW: float | None = None,
    core_name: str = "RS_68A",
    n_core_eng: int = 9,
    strapon_name: str | None = None,
    n_strapons: int = 0,
    upper_name: str = "RS_68A",
    n_upper_eng: int = 2,
    n_grid: int = 4000,
    dV_grid: object = None,
    mass_margin: float = MASS_MARGIN,
    print_sensitivities: bool = False,
) -> dict:
    """Evaluate or size one specific vehicle configuration."""
    core_eng = find_engine(core_name)
    strapon_eng = find_engine(strapon_name) if strapon_name and n_strapons > 0 else None
    upper_eng = find_engine(upper_name)
    if strapon_eng is None:
        n_strapons = 0

    has_strapons = (strapon_eng is not None) and (n_strapons > 0)
    strap_str = f" + {n_strapons} x {strapon_eng.name}" if has_strapons else ""
    total_eng = n_core_eng + n_strapons + n_upper_eng

    upper_k = calc_stage_k(upper_eng, 2, margin=mass_margin)
    s1_k = calc_stage_k(core_eng, 1, margin=mass_margin)

    if GLOW is None:
        # Auto-Sizing Mode: find minimum GLOW vehicle delivering full DV_BUDGET
        if dV_grid is None:
            dV_grid = STAGE2_DV

        print(f"Sizing specific vehicle: {n_core_eng} x {core_eng.name}{strap_str} / {n_upper_eng} x {upper_eng.name}, "
              f"payload = {PAYLOAD_LBS:,.0f} lb")

        best_cfg = None
        all_fails: dict[str, int] = {}

        for dV2 in dV_grid:
            step_fails: dict[str, int] = {}
            s2 = size_upper_stage(upper_eng, n_upper_eng, dV2, PAYLOAD_LBS, upper_k, UPPER_TW0_BOUNDS, step_fails, 2)
            if s2 is None:
                for k, v in step_fails.items():
                    all_fails[k] = all_fails.get(k, 0) + v
                continue

            m_above = PAYLOAD_LBS + s2.m_total
            dV1_req = DV_BUDGET - dV2
            max_glow_avail = best_cfg['GLOW'] if best_cfg else MAX_VEHICLE_WEIGHT

            if has_strapons:
                stage1 = solve_strapon_stage(core_eng, strapon_eng, n_core_eng, n_strapons,
                                             dV1_req, m_above, max_glow_avail, step_fails, stage=1,
                                             mass_margin=mass_margin)
            else:
                core_masses = size_core_stage_masses(core_eng, dV1_req, m_above, s1_k, [s2],
                                                     best_cfg or {'GLOW': MAX_VEHICLE_WEIGHT, 'Total Engine Count': 1e9},
                                                     step_fails)
                if core_masses is not None:
                    liftoff_thrust = core_eng.thrust_sl * n_core_eng
                    liftoff_TW = liftoff_thrust / core_masses["GLOW"]
                    if liftoff_TW_min(liftoff_TW, MIN_LIFTOFF_TW0, step_fails) and liftoff_TW_max(liftoff_TW, MAX_LIFTOFF_TW0, step_fails):
                        stage1 = size_core_stage_engines(core_masses, core_eng, n_core_eng,
                                                         liftoff_thrust, liftoff_TW, dV1_req, s1_k, step_fails)
                    else:
                        stage1 = None
                else:
                    stage1 = None

            for k, v in step_fails.items():
                all_fails[k] = all_fails.get(k, 0) + v

            if stage1 is None:
                continue

            glow_in_bounds(MIN_VEHICLE_WEIGHT, MAX_VEHICLE_WEIGHT, stage1.m0, step_fails)
            if best_cfg is None or stage1.m0 < best_cfg['GLOW']:
                best_cfg = make_working_cfg(stage1, [s2], total_eng)

        if best_cfg is not None:
            print_results(best_cfg, all_fails)
            if print_sensitivities:
                calc_and_print_cfg_sensitivity(best_cfg)
            return best_cfg
        else:
            print("\nNo feasible vehicle found for this specific configuration that meets the delta-V budget.")
            print_results({}, all_fails)
            return {}

    else:
        # Fixed GLOW Mode: optimize stage propellant partition for fixed GLOW
        print(f"Fixed config evaluation: {n_core_eng} x {core_eng.name}{strap_str} / {n_upper_eng} x {upper_eng.name}, "
              f"GLOW = {GLOW:,.0f} lb, payload = {PAYLOAD_LBS:,.0f} lb")

        best_feasible = None
        best_feasible_dv = -1.0
        best_any = None
        best_any_key = None
        fails_all: dict[str, int] = {}

        thrust2 = upper_eng.thrust_vac * n_upper_eng
        tw_lo, tw_hi = UPPER_TW0_BOUNDS
        m2_tw_min = (thrust2 / tw_hi - PAYLOAD_LBS) / (1 + upper_k)
        m2_tw_max = (thrust2 / tw_lo - PAYLOAD_LBS) / (1 + upper_k)

        if m2_tw_min < m2_tw_max and m2_tw_max > 0:
            lo = max(0.001 * GLOW, m2_tw_min)
            hi = min(0.50 * GLOW, m2_tw_max)
        else:
            lo, hi = 0.01 * GLOW, 0.45 * GLOW

        for i in range(n_grid + 1):
            m_prop2 = lo + (hi - lo) * i / n_grid
            res = eval_fixed_config(m_prop2, core_eng, n_core_eng, strapon_eng,
                                    n_strapons, upper_eng, n_upper_eng, GLOW,
                                    mass_margin=mass_margin)
            if res is None:
                continue
            s1, s2, fails_iter, dV_total = res
            for name, count in fails_iter.items():
                fails_all[name] = fails_all.get(name, 0) + count

            num_fails = sum(fails_iter.values())
            if num_fails == 0:
                if dV_total > best_feasible_dv:
                    best_feasible_dv = dV_total
                    best_feasible = res

            key = (num_fails, -dV_total)
            if best_any_key is None or key < best_any_key:
                best_any_key = key
                best_any = res

        if best_feasible is None:
            lo_broad, hi_broad = 0.005 * GLOW, 0.50 * GLOW
            for i in range(n_grid + 1):
                m_prop2 = lo_broad + (hi_broad - lo_broad) * i / n_grid
                res = eval_fixed_config(m_prop2, core_eng, n_core_eng, strapon_eng,
                                        n_strapons, upper_eng, n_upper_eng, GLOW,
                                        mass_margin=mass_margin)
                if res is None:
                    continue
                s1, s2, fails_iter, dV_total = res
                num_fails = sum(fails_iter.values())
                if num_fails == 0 and dV_total > best_feasible_dv:
                    best_feasible_dv = dV_total
                    best_feasible = res
                key = (num_fails, -dV_total)
                if best_any_key is None or key < best_any_key:
                    best_any_key = key
                    best_any = res

        best = best_feasible if best_feasible is not None else best_any

        if best is None:
            print("\nNo valid points could be evaluated for this configuration.")
            print_results({}, fails_all)
            return {}

        s1, s2, report_fails, dV_delivered = best
        stage1, stage2 = StageSpecs(**s1), StageSpecs(**s2)
        working_cfg = make_working_cfg(stage1, [stage2], total_eng)

        print_results(working_cfg, report_fails)
        if print_sensitivities and working_cfg.get("GLOW", 1e100) < 1e99:
            calc_and_print_cfg_sensitivity(working_cfg)
        return working_cfg


fixed_config_sizing = specific_config_sizing


def main() -> None:
    print_sensitivities: bool = True
    # two_stage_sizing(same_engines=[1, 2], print_sensitivities=print_sensitivities)
    two_p_five_sizing(same_engines=[1, 2], print_sensitivities=print_sensitivities)
    # three_stage_sizing(same_engines=[1, 2, 3], print_sensitivities=print_sensitivities)


if __name__ == "__main__":
    main()
