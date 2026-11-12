import numpy as np
from dataclasses import dataclass
from inputs import DV_BUDGET, V_ORBIT, DV_LOSSES, DV_ROTATION

W = 78


def _fmt(v: object) -> str:
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.5g}"
    return str(v)


# (section title, [(row label, attr name | callable(stage) -> str)])
_SECTIONS = [
    ("Configuration", [
        ("core engines",   lambda s: f"{s.n_core_eng} x {s.core_eng.name}"),
        ("strap-ons",      lambda s: f"{s.n_strapons} x {s.strapon_eng.name}"
         if s.strapon_eng else "-"),
        ("total engines",  "total_engines"),
    ]),

    ("Mass (lb)", [
        ("m0 (GLOW / ignition)", "m0"),
        ("stage mass",           "m_total"),
        ("propellant",           "m_prop"),
        ("  strap-on",           "m_strapon_prop"),
        ("  liquid",             "m_prop_liquid"),
        ("inert",                "m_inert"),
        ("  engines (core)",     "m_core_engines"),
        ("  strap-on inert",     "m_strapon_inert"),
        ("  structure budget",   "m_structure_budget"),
        ("propellant fraction",  "m_fraction"),
    ]),

    ("Thrust (lbf)", [
        ("core (SL at S1, vac at upper stages)", "thrust_core"),
        ("strap-on (peak, SL)",                  "thrust_strapon"),
        ("total at ignition",                    "thrust_total"),
        ("T/W at ignition",                      "tw0"),
        ("T/W before booster separation",        "tw_before_booster_sep"),
        ("T/W after booster separation",         "tw_after_booster_sep"),
        ("T/W at burnout",                       "tw_burnout"),
    ]),

    ("Delta-V (ft/s)", [
        ("required",             "dV"),
        ("delivered",            "dV_delivered"),
        ("margin",               "dv_margin"),
        ("split fraction",       "dv_split_frac"),
        ("  boost phase",        "boost_phase_dV"),
        ("  core only",          "core_only_dV"),
        ("sizing ISP (s)",       "ISP"),
        ("boost eff. ISP (s)",   "boost_eff_ISP"),
        ("mass ratio",           "mass_ratio"),
    ]),

    ("Burn & acceleration", [
        ("strap-on burn (s)",                  "t_burn_strapon"),
        ("core burn (s)",                      "t_burn_liquid"),
        ("core burn after strapon separation", "core_burn_margin"),
        ("g @ boost end, min thr",             "accel_boost_burnout_min_g"),
        ("g @ burnout, min thr",               "accel_core_burnout_min_g"),
    ]),
]

_ENGINE_STATS = [
    ("type",                 lambda e: "Solid" if hasattr(e, "m_tot") else "Liquid"),
    ("fuel",                 lambda e: getattr(e, "fuel", "Solid")),
    ("thrust SL (lbf)",      lambda e: getattr(e, "thrust_sl", None)),
    ("thrust vac (lbf)",     lambda e: getattr(e, "thrust_vac", None)),
    ("min throttle",         lambda e: f"{e.min_throttle:.0%}" if getattr(e, "min_throttle", None) is not None else "-"),
    ("min thrust SL (lbf)",  lambda e: getattr(e, "min_thrust_sl", None)),
    ("min thrust vac (lbf)", lambda e: getattr(e, "min_thrust_vac", None)),
    ("ISP SL (s)",           lambda e: getattr(e, "isp_sl", None)),
    ("ISP vac (s)",          lambda e: getattr(e, "isp_vac", None)),
    ("ISP avg (s)",          lambda e: getattr(e, "isp_avg", None)),
    ("inert mass (lb)",      lambda e: getattr(e, "m_inert", None)),
    ("propellant mass (lb)", lambda e: getattr(e, "m_prop", None)),
    ("total mass (lb)",      lambda e: getattr(e, "m_tot", None)),
    ("mdot (lb/s)",          lambda e: getattr(e, "mdot", None)),
    ("burn time (s)",        lambda e: getattr(e, "t_burn", None)),
    ("exit diameter (in)",   lambda e: getattr(e, "d_exit", None)),
]


def _cell(stage: object, spec: object) -> str:
    """Return a formatted cell, including a dash for unavailable values."""
    if stage is None:
        return "-"

    if callable(spec):
        v = spec(stage)
    else:
        v = getattr(stage, spec, None)

    if v is None:
        return "-"

    return v if isinstance(v, str) else _fmt(v)


def _print_stage_table(*stages: object, cw: int = 22) -> None:
    """
    Print a table for however many stages are provided.

    Supports:
        _print_stage_table(stage1, stage2)
        _print_stage_table(stage1, stage2, stage3)

    Stage 1 can include strap-on boosters. Upper stages normally have none.
    """
    if not stages:
        print("No stages to display.")
        return

    lw = max(
        len(label)
        for _, rows in _SECTIONS
        for label, _ in rows
    )

    # Stage headings are generated dynamically.
    headers = [f"STAGE {i}" for i in range(1, len(stages) + 1)]

    print(f"  {'':<{lw}}", end="")
    for header in headers:
        print(f"  {header:>{cw}}", end="")
    print()

    table_width = lw + len(stages) * (cw + 2)

    for title, rows in _SECTIONS:
        print(f"\n  {title}")
        print(f"  {'-' * table_width}")

        for label, spec in rows:
            print(f"  {label:<{lw}}", end="")

            for stage in stages:
                print(f"  {_cell(stage, spec):>{cw}}", end="")

            print()


def _print_engines_table(*engines: object, cw: int = 22, max_cols: int = 3) -> None:
    """
    Tabulate stats for the provided engine instances.
    """
    if not engines:
        print("  No engines to display.")
        return

    for chunk_start in range(0, len(engines), max_cols):
        chunk = engines[chunk_start:chunk_start + max_cols]
        lw = max(len(label) for label, _ in _ENGINE_STATS)
        headers = [getattr(e, "name", str(e)) for e in chunk]

        table_width = lw + len(chunk) * (cw + 2)
        if chunk_start > 0:
            print()
        print(f"  {'-' * table_width}")
        print(f"  {'':<{lw}}", end="")
        for header in headers:
            print(f"  {header:>{cw}}", end="")
        print()
        print(f"  {'-' * table_width}")

        for label, spec in _ENGINE_STATS:
            print(f"  {label:<{lw}}", end="")
            for eng in chunk:
                if callable(spec):
                    v = spec(eng)
                else:
                    v = getattr(eng, spec, None)
                formatted = "-" if v is None else (v if isinstance(v, str) else _fmt(v))
                print(f"  {formatted:>{cw}}", end="")
            print()


print_engine_table = _print_engines_table


def _banner(title: str, ch: str = "=") -> None:
    print(ch * W)
    print(f" {title}")
    print(ch * W)


def print_results(working_cfg: dict, fails: dict) -> None:
    """
    Print the vehicle sizing results.

    Supports two-stage and three-stage configurations. Stage 1 may have
    strap-on boosters; the printing code does not require boosters to exist.
    """
    print("\n")

    # Find which stage keys are present.
    stage_keys = [
        key for key in ("Stage 1", "Stage 2", "Stage 3")
        if key in working_cfg and working_cfg[key] is not None
    ]

    if "Stage 1" not in working_cfg:
        print("No feasible configuration found.")

    else:
        stages = [working_cfg[key] for key in stage_keys]

        total_dv = working_cfg.get("dV_delivered") or sum(s.dV_delivered for s in stages if s.dV_delivered)
        for s in stages:
            if getattr(s, "dv_split_frac", None) is None:
                s.dv_split_frac = s.dV_delivered / total_dv if total_dv else 0.0

        _banner("VEHICLE")

        vehicle = [
            ("GLOW (lb)",                 working_cfg.get("GLOW")),
            ("payload fraction",          working_cfg.get("payload_frac")),
            ("total delivered dV (ft/s)", working_cfg.get("dV_delivered")),
            ("dV budget (ft/s)",          DV_BUDGET),
            ("dV split fractions",        " / ".join(f"{s.dv_split_frac:.3f}" for s in stages)),
        ]

        lw = max(len(label) for label, _ in vehicle)

        for label, value in vehicle:
            formatted = "-" if value is None else _fmt(value)
            print(f"  {label:<{lw}}  {formatted:>12}")

        print(f"  (budget = orbital {V_ORBIT:,.0f} + losses {DV_LOSSES:,} "
            f"- rotation {DV_ROTATION:,.0f} ft/s)")

        print()
        _banner("STAGES")

        _print_stage_table(*stages)

        print()
        _banner("ENGINES")

        vehicle_engines = []
        for stage in stages:
            if getattr(stage, "core_eng", None) and stage.core_eng not in vehicle_engines:
                vehicle_engines.append(stage.core_eng)
            if getattr(stage, "strapon_eng", None) and stage.strapon_eng not in vehicle_engines:
                vehicle_engines.append(stage.strapon_eng)
        _print_engines_table(*vehicle_engines)

    print()
    _banner("REJECTIONS (why configs were discarded)")

    if not fails:
        print("  No rejection statistics available.")
        return

    total = sum(fails.values())
    kw = max(len(k) for k in fails)

    for k, v in sorted(fails.items(), key=lambda kv: -kv[1]):
        pct = v / total if total else 0
        print(f"  {k:<{kw}}  {v:>14,}  {pct:6.1%}")

    print(f"  {'TOTAL':<{kw}}  {total:>14,}")


class StageSpecs:
    """
    Record of one sized stage.

    Takes the values the sizing gates already computed and calculates
    the remaining derived quantities.

    Stage 1 may have strap-on boosters.
    Upper stages can be represented without strap-on boosters.
    """

    def __init__(
        self,
        *,
        stage_number: int,
        core_eng: object,
        n_core_eng: int,
        m0: float,
        m_total: float,
        m_prop: float,
        m_inert: float,
        m_prop_liquid: float,
        k: float,
        mass_ratio: float,
        dV: float,
        dV_delivered: float,
        ISP: float,
        thrust_core: float,
        thrust_total: float,
        tw0: float,
        accel_core_burnout_min_g: float,
        m0_core_only: float | None = None,
        m_core_burnout: float | None = None,
        strapon_eng: object | None = None,
        n_strapons: int = 0,
        m_strapon_prop: float = 0,
        m_strapon_inert: float = 0,
        thrust_strapon: float = 0,
        m_liquid_burned_boost: float | None = None,
        m_boost_burnout: float | None = None,
        boost_eff_ISP: float | None = None,
        boost_phase_dV: float | None = None,
        core_only_dV: float | None = None,
        accel_boost_burnout_min_g: float | None = None,
        dv_split_frac: float | None = None,
        tw_burnout: float | None = None,
        tw_before_booster_sep: float | None = None,
        tw_after_booster_sep: float | None = None,
    ) -> None:
        has_strapons = strapon_eng is not None and n_strapons > 0

        # inputs
        self.stage_number = stage_number
        self.core_eng = core_eng
        self.n_core_eng = n_core_eng
        self.strapon_eng = strapon_eng
        self.n_strapons = n_strapons

        self.m0 = m0
        self.m_total = m_total
        self.m_prop = m_prop
        self.m_inert = m_inert
        self.m_prop_liquid = m_prop_liquid

        self.m_strapon_prop = m_strapon_prop
        self.m_strapon_inert = m_strapon_inert

        self.m_liquid_burned_boost = m_liquid_burned_boost
        self.m_boost_burnout = m_boost_burnout
        self.m0_core_only = m0_core_only

        self.k = k
        self.mass_ratio = mass_ratio
        self.dV = dV
        self.dV_delivered = dV_delivered
        self.ISP = ISP

        self.boost_eff_ISP = boost_eff_ISP
        self.boost_phase_dV = boost_phase_dV
        self.core_only_dV = core_only_dV
        self.dv_split_frac = dv_split_frac

        self.thrust_core = thrust_core
        self.thrust_strapon = thrust_strapon
        self.thrust_total = thrust_total
        self.tw0 = tw0

        self.accel_core_burnout_min_g = accel_core_burnout_min_g
        self.accel_boost_burnout_min_g = accel_boost_burnout_min_g

        # configuration
        self.total_engines = n_core_eng + n_strapons

        # masses (lb)
        self.mf = m0 - m_prop
        if m_core_burnout is not None:
            self.m_core_burnout = m_core_burnout
        elif has_strapons:
            self.m_core_burnout = m0 - m_prop - m_strapon_inert
        else:
            self.m_core_burnout = self.mf

        self.m_fraction = m_prop / m_total if m_total else 0

        self.m_core_engines = core_eng.m_inert * n_core_eng

        self.m_structure_budget = (
            m_inert - self.m_core_engines - m_strapon_inert
        )

        self.structure_frac = (
            self.m_structure_budget / m_inert if m_inert else 0
        )

        self.hardware_frac_of_inert = (
            1 - self.m_structure_budget / m_inert if m_inert else 0
        )

        self.m_strapon_total = (
            strapon_eng.m_tot * n_strapons if has_strapons else 0
        )

        # delta-V
        self.mr_max = 1 + 1 / k if k else None
        self.dv_margin = dV_delivered - dV

        # thrust (lbf)
        self.thrust_core_vac = core_eng.thrust_vac * n_core_eng
        self.thrust_core_min = core_eng.min_thrust_vac * n_core_eng

        self.thrust_strapon_avg = (
            strapon_eng.avg_thrust_vac * n_strapons
            if has_strapons else 0
        )

        # T/W and acceleration calculations
        if tw_burnout is not None:
            self.tw_burnout = tw_burnout
        else:
            self.tw_burnout = (
                self.thrust_core_vac / self.m_core_burnout
                if self.m_core_burnout else None
            )

        if tw_before_booster_sep is not None:
            self.tw_before_booster_sep = tw_before_booster_sep
        elif has_strapons and m_boost_burnout:
            num_strap_thrust = self.thrust_strapon_avg + self.thrust_core_vac
            self.tw_before_booster_sep = num_strap_thrust / m_boost_burnout
        else:
            self.tw_before_booster_sep = None

        if tw_after_booster_sep is not None:
            self.tw_after_booster_sep = tw_after_booster_sep
        elif has_strapons and self.m0_core_only:
            self.tw_after_booster_sep = self.thrust_core_vac / self.m0_core_only
        else:
            self.tw_after_booster_sep = None

        self.accel_core_burnout_g = self.tw_burnout
        self.accel_boost_burnout_g = self.tw_before_booster_sep

        # burn times (s)
        self.t_burn_strapon = (
            strapon_eng.t_burn if has_strapons else 0
        )

        total_liquid_mdot = core_eng.mdot * n_core_eng

        self.t_burn_liquid = (
            m_prop_liquid / total_liquid_mdot
            if total_liquid_mdot else None
        )

        self.core_burn_margin = (
            self.t_burn_liquid - self.t_burn_strapon
            if has_strapons and self.t_burn_liquid is not None
            else None
        )
