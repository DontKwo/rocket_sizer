import math
from inputs import G0
IN_TO_M = 0.0254
LBF_TO_N = 4.44822162
P_SL = 14.695948803581565 # psi
DEFAULT_RATIO_VAC_TO_SL_THRUST = 1.1


def calc_boost_phase_eff_ISP(ISP_strapon, ISP_core, mdot_strapon, mdot_core):
    return (ISP_strapon * mdot_strapon + ISP_core * mdot_core) / (mdot_strapon + mdot_core)


def calc_boost_phase_dV(GLOW, m_burn_boost_phase_strapon, m_burn_boost_phase_liquid, ISP_eff, g0=G0):
    m_leftover = GLOW - m_burn_boost_phase_strapon - m_burn_boost_phase_liquid
    return ISP_eff * g0 * math.log(GLOW / m_leftover)


def estimate_vac_sl_ratio(
    thrust_vac=None,
    thrust_sl=None,
    isp_vac=None,
    isp_sl=None,
    exit_area=None,
    p_sl=P_SL,
    default_ratio=DEFAULT_RATIO_VAC_TO_SL_THRUST,
):
    # best: nozzle physics
    if exit_area is not None:
        if thrust_vac is not None:
            ratio = thrust_vac / (thrust_vac - p_sl * exit_area)
        elif thrust_sl is not None:
            ratio = (thrust_sl + p_sl * exit_area) / thrust_sl
        else:
            ratio = default_ratio

    # second best: Isp ratio
    elif isp_vac is not None and isp_sl is not None:
        ratio = isp_vac / isp_sl

    elif thrust_vac is not None and thrust_sl is not None:
        ratio = thrust_vac / thrust_sl

    else:
        ratio = default_ratio

    return min(max(ratio, 1.0), 1.5)


def estimate_thrust_sl(
    thrust_vac,
    isp_vac=None,
    isp_sl=None,
    exit_area=None,
    p_sl=P_SL,
):
    ratio = estimate_vac_sl_ratio(
        thrust_vac=thrust_vac,
        isp_vac=isp_vac,
        isp_sl=isp_sl,
        exit_area=exit_area,
        p_sl=p_sl,
    )

    return thrust_vac / ratio


def estimate_thrust_vac(
    thrust_sl,
    isp_vac=None,
    isp_sl=None,
    exit_area=None,
    p_sl=P_SL,
):
    ratio = estimate_vac_sl_ratio(
        thrust_sl=thrust_sl,
        isp_vac=isp_vac,
        isp_sl=isp_sl,
        exit_area=exit_area,
        p_sl=p_sl,
    )

    return thrust_sl * ratio


def estimate_isp_sl(
    isp_vac,
    thrust_vac=None,
    thrust_sl=None,
    exit_area=None,
):
    ratio = estimate_vac_sl_ratio(
        thrust_vac=thrust_vac,
        thrust_sl=thrust_sl,
        exit_area=exit_area,
    )

    return isp_vac / ratio


def estimate_isp_vac(
    isp_sl,
    thrust_vac=None,
    thrust_sl=None,
    exit_area=None,
):
    ratio = estimate_vac_sl_ratio(
        thrust_vac=thrust_vac,
        thrust_sl=thrust_sl,
        exit_area=exit_area,
    )

    return isp_sl * ratio