import math
from inputs import G0


class PropellantProperties:
    def __init__(self):
        pass


def calc_k(mf, multiplier=1.25):
    return ((1 - mf) / mf) * multiplier


def calc_MR(dV, Isp, g0=G0):
    return math.exp(dV / (g0 * Isp))


def calc_m_prop(MR, m_above, k):
    return (MR - 1) * m_above / (1 + k*(1 - MR))


def calc_m_inert(k, m_prop):
    return k * m_prop


def calc_m_stage(m_prop, m_inert):
    return m_prop + m_inert


def calc_m0(m_pl, m_stages):
    # stage, n_stages are int, m_stages a list
    return m_pl + sum(m_stages)


def calc_boost_phase_m_burn(mdot_core, t_burn):
    # liquid prop burnt
    return mdot_core * t_burn


def calc_core_only_dv(ISP, GLOW, m_total_strapon, m_burn_liquid, m_prop_total_liquid, g0=G0):
    m0_core_only = GLOW - m_burn_liquid - m_total_strapon
    mf_core_only = m0_core_only - (m_prop_total_liquid - m_burn_liquid)
    return ISP * g0 * math.log(m0_core_only / mf_core_only)


def calc_s1_dV(boost_phase_dV, core_dV):
    return boost_phase_dV + core_dV


def calc_core_only_m_prop(m_prop_total, m_prop_strapon):
    return m_prop_total - m_prop_strapon


def calc_circle_area(diameter):
    return math.pi / 4 * diameter**2

