def _record_fail(fails, key):
    fails[key] = fails.get(key, 0) + 1


def stage_feasible(k, MR, fails):
    ok = 1 + k * (1 - MR) > 0
    if not ok:
        _record_fail(fails, "Feasibility")
    return ok


def stage_dV_positive(dV, fails):
    ok = dV > 0
    if not ok:
        _record_fail(fails, "Feasibility")
    return ok


def hardware_inert_mass(estimated_inert, m_inert_available, fails):
    ok = estimated_inert <= m_inert_available
    if not ok:
        _record_fail(fails, "Hardware")
    return ok


def core_prop_positive(m_prop_core, fails):
    ok = m_prop_core > 0
    if not ok:
        _record_fail(fails, "Core Prop < 0")
    return ok


def glow_in_bounds(min_glow, max_glow, GLOW, fails):
    ok = min_glow <= GLOW <= max_glow
    if not ok:
        _record_fail(fails, "OOB GLOW")
    return ok


def glow_improves(GLOW, best_GLOW, fails, strict=False):
    ok = GLOW < best_GLOW if strict else GLOW <= best_GLOW
    if not ok:
        _record_fail(fails, "Worse GLOW")
    return ok


def engine_count_ok(GLOW, best_GLOW, total_engines, best_total_engines,
                    fails, strict=False):
    if GLOW != best_GLOW:
        return True
    if strict:
        ok = total_engines < best_total_engines
    else:
        ok = total_engines <= best_total_engines
    if not ok:
        _record_fail(fails, "Engine Count")
    return ok


def liftoff_TW_max(liftoff_TW, max_TW, fails):
    ok = liftoff_TW <= max_TW
    if not ok:
        _record_fail(fails, "Liftoff TW")
    return ok


def liftoff_TW_min(liftoff_TW, min_TW, fails):
    ok = liftoff_TW >= min_TW
    if not ok:
        _record_fail(fails, "Liftoff TW")
    return ok


def core_only_TW_min(core_only_TW, min_TW, fails):
    ok = core_only_TW >= min_TW
    if not ok:
        _record_fail(fails, "Core only TW")
    return ok


def core_only_TW_max(core_only_TW, max_TW, fails):
    ok = core_only_TW <= max_TW
    if not ok:
        _record_fail(fails, "Core only TW")
    return ok


def upper_stage_TW0(stage, min_TW0, max_TW0, TW0, fails):
    ok = min_TW0 <= TW0 <= max_TW0
    if not ok:
        _record_fail(fails, f"Stage {stage} TW0")
    return ok


def stage2_TW0(min_s2_TW0, max_s2_TW0, s2_TW0, fails):
    return upper_stage_TW0(2, min_s2_TW0, max_s2_TW0, s2_TW0, fails)


def stage3_TW0(min_s3_TW0, max_s3_TW0, s3_TW0, fails):
    return upper_stage_TW0(3, min_s3_TW0, max_s3_TW0, s3_TW0, fails)


def g_limit_ok(g, g_limit, fails):
    ok = g <= g_limit
    if not ok:
        _record_fail(fails, "g Limit")
    return ok


def boost_burnout_mass_positive(m_boost_burnout, fails):
    ok = m_boost_burnout > 0
    if not ok:
        _record_fail(fails, "Core Burns Out In Boost")
    return ok


def core_survives_boost(m_burn_liquid, m_prop_core_only, fails):
    ok = m_burn_liquid < m_prop_core_only
    if not ok:
        _record_fail(fails, "Core Burns Out In Boost")
    return ok


def core_burnout_mass_positive(m_core_burnout, fails, key="g Limit"):
    ok = m_core_burnout > 0
    if not ok:
        _record_fail(fails, key)
    return ok


def stage1_dV_possible(s1_dV_delivered, s1_dV, fails):
    ok = s1_dV_delivered >= s1_dV
    if not ok:
        _record_fail(fails, "Stage 1 dV Not Possible")
    return ok


def is_better_candidate(candidate_glow, candidate_n_eng,  best):
    if candidate_glow < best["GLOW"]:
        return True

    if candidate_glow == best["GLOW"]:
        return (
            candidate_n_eng
            < best["Total Engine Count"]
        )

    return False