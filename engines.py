from models import estimate_thrust_sl, estimate_isp_sl, estimate_isp_vac, estimate_thrust_vac
from physics import calc_circle_area
KG_M3_TO_LB_FT3 = 0.062427961


class SolidEngine:
    def __init__(self, name, m_tot, m_prop, t_burn, thrust_vac, thrust_sl,
                 isp_vac, isp_sl, **kwargs):
        # kwargs always become class attributes
        for key, value in kwargs.items():
            if key != "self" and key is not None:
                setattr(self, key, value)

        # area from diameter
        if hasattr(self, "d_exit") and not hasattr(self, "a_exit"):
            self.a_exit = calc_circle_area(self.d_exit)
        elif not hasattr(self, "a_exit"):
            self.a_exit = None

        # get SL thrust if not given
        if (thrust_sl is None) and (thrust_vac is not None):
            thrust_sl = estimate_thrust_sl(thrust_vac, isp_vac, isp_sl, self.a_exit)

        # find vac thrust if not given
        if (thrust_vac is None) and (thrust_sl is not None):
            thrust_vac = estimate_thrust_vac(thrust_sl, isp_vac, isp_sl, self.a_exit)

        # find SL ISP if not given
        if (isp_sl is None) and (isp_vac is not None):
            isp_sl = estimate_isp_sl(isp_vac, thrust_vac, thrust_sl, self.a_exit)
        
        # find vac ISP if not given
        if (isp_vac is None) and (isp_sl is not None):
            isp_vac = estimate_isp_vac(isp_sl, thrust_vac, thrust_sl, self.a_exit)

        # set any locals to attrs if kwargs didn't already write them
        for key, value in locals().items():
            if (key != "self") and (key != "kwargs") and (key is not None) and (not hasattr(self, key)):
                setattr(self, key, value)

        vac_mdot = thrust_vac / isp_vac
        sl_mdot  = thrust_sl / isp_sl
        assert abs(vac_mdot - sl_mdot) / vac_mdot < 0.02
        self.mdot = m_prop / t_burn

        self.isp_avg = (isp_sl + isp_vac) / 2
        self.m_inert        = m_tot - m_prop
        self.avg_thrust_sl  = self.mdot * isp_sl
        self.avg_thrust_vac = self.mdot * isp_vac


class LiquidEngine:
    def __init__(self, name, m_inert, thrust_vac, thrust_sl,
                 isp_vac, isp_sl, fuel, min_throttle, mdot_tol = 0.052, **kwargs):
        # kwargs always become class attributes
        for key, value in kwargs.items():
            if key != "self" and key is not None:
                setattr(self, key, value)

        # area from diameter
        if hasattr(self, "d_exit") and not hasattr(self, "a_exit"):
            self.a_exit = calc_circle_area(self.d_exit)
        elif not hasattr(self, "a_exit"):
            self.a_exit = None

        # get SL thrust if not given
        if (thrust_sl is None) and (thrust_vac is not None):
            thrust_sl = estimate_thrust_sl(thrust_vac, isp_vac, isp_sl, self.a_exit)

        # find vac thrust if not given
        if (thrust_vac is None) and (thrust_sl is not None):
            thrust_vac = estimate_thrust_vac(thrust_sl, isp_vac, isp_sl, self.a_exit)

        # find SL ISP if not given
        if (isp_sl is None) and (isp_vac is not None):
            isp_sl = estimate_isp_sl(isp_vac, thrust_vac, thrust_sl, self.a_exit)
        
        # find vac ISP if not given
        if (isp_vac is None) and (isp_sl is not None):
            isp_vac = estimate_isp_vac(isp_sl, thrust_vac, thrust_sl, self.a_exit)

        # set any locals to attrs if kwargs didn't already write them
        for key, value in locals().items():
            if (key != "self") and (key != "kwargs") and (key is not None) and (not hasattr(self, key)):
                setattr(self, key, value)

        self.min_thrust_sl  = min_throttle * thrust_sl
        self.min_thrust_vac = min_throttle * thrust_vac

        self.isp_avg = (isp_sl + isp_vac) / 2
        vac_mdot = thrust_vac / isp_vac
        sl_mdot  = thrust_sl / isp_sl
        assert abs(vac_mdot - sl_mdot) / vac_mdot < mdot_tol
        self.mdot = (vac_mdot + sl_mdot) / 2


# probably a good list
#                        name,       m_tot,     m_prop,   t_burn, thr_vac,   thr_sl,   isp_vac, isp_sl
# GEM_63    = SolidEngine('GEM_63',    108_600,   97_500,    97.6,  370_835,   None,      279.06, None, d_exit=54, notes="asuumed thrust and ISP were vacuum values")
# GEM_63XL  = SolidEngine('GEM_63XL',  117_700,   105_900,   87.3,  463_249,   None,      280.3,  None, d_exit=56, notes="asuumed thrust and ISP were vacuum values")
# AJ_60A    = SolidEngine('AJ_60A',    102_949,   93_980,    94,    379_600,   None,      279.3,  None,            notes="asuumed thrust and ISP were vacuum values")
P120C     = SolidEngine('P120C',     337_000,   311_700,   130,   1_045_361, None,      278.5,  None,            notes="asuumed thrust and ISP were vacuum values")
SS_SRB    = SolidEngine('SS_SRB',    1_300_000, 1_100_000, 123,   None,      3_300_000, 267.9,  None)
# CAS_120   = SolidEngine('CAS_120',   116_993,   107_914,   79.4,  440_000,   None,      280,    None)
# CAS_120XL = SolidEngine('CAS_120XL', 123_383,   114_194,   83.5,  458_500,   None,      279.1,  None)
P241      = SolidEngine('P241',      613_610,   529_410,   130,   1_590_000, None,      275,    None)
# SRB_3     = SolidEngine('SRB_3',     168_000,   148_000,   110,   520_000,   None,      283.6,  None)
# SRB_A     = SolidEngine('SRB_A',     166_449,   147_269,   110,   517_061,   None,      283.6,  None)
SLS       = SolidEngine('SLS',       1_600_000, 1_385_000, 126,   3_600_000, 3_280_000, 269,    None)
SRMU      = SolidEngine('SRMU',      770_673,   688_853,   135.7, 1_700_000, None,      285.6,  251.4)
SOLIDS  = [glo for glo in globals().values() if isinstance(glo, SolidEngine)]

# add more later
#                          name,   m_inert, thr_vac, thr_sl, isp_vac, isp_sl, fuel,  min_throt
BE_4       = LiquidEngine('BE_4',   11_900, None,    640_000, 340,   None,  "LOX/CH4", 0.4)
RAPTOR     = LiquidEngine('RAPTOR', 3_362,  606_300, 551_200, 350,   327,   "LOX/CH4", 0.4,  d_exit=51.2)
# RS_25      = LiquidEngine('RS_25',  7_004,  512_300, 418_000, 452.3, 366,   "LOX/LH2", 0.61, d_exit=90.6)
RD_180     = LiquidEngine('RD_180', 12_080, 930_000, 860_200, 338,   311,   "LOX/RP1", 0.47)
MERLIN     = LiquidEngine('MERLIN', 1_030,  221_000, 190_000, 311,   282,   "LOX/RP1", 0.57, d_exit=98.7)
RS_68A     = LiquidEngine('RS_68A', 14_870, 800_000, 705_000, 411.9, 365,   "LOX/LH2", 0.545)
RL_10A     = LiquidEngine('RL_10A', 664,    24_800,  None,    465.5, None,  "LOX/LH2", 0.3)
VINCI      = LiquidEngine('VINCI',  1_210,  40_000,  None,    457.2, None,  "LOX/LH2", 0.72)
LE_5B      = LiquidEngine('LE_5B',  593,    30_798,  None,    447,   None,  "LOX/LH2", 0.05)
RD_191     = LiquidEngine('RD_191', 5_050,  470_000, 430_000, 337,   310.7, "LOX/RP1", 0.257)
F1         = LiquidEngine('F1',     18_500, 1_746_000, 1_522_000, 304, 263, "LOX/RP1", 0.4)
# BE_3U      = LiquidEngine('BE_3U', idk, 211_658, 445, "LOX/LH2", 0.75) # no mass estimate
# ARCHIMEDES = LiquidEngine('ARCHIMEDES', idk, 200_000, 365, "LOX/CH4", 0.5) # no mass estimate
LIQUIDS  = [glo for glo in globals().values() if isinstance(glo, LiquidEngine)]


OXIDIZERS = {"LOX": {"density": 1141.0 * KG_M3_TO_LB_FT3}}

FUELS = {
    "RP1": {"density": 810.0 * KG_M3_TO_LB_FT3, "default_of": 2.6, "cryogenic": False},
    "H2": {"density": 70.85 * KG_M3_TO_LB_FT3, "default_of": 6.0, "cryogenic": True},
    "CH4": {"density": 422.6 * KG_M3_TO_LB_FT3, "default_of": 3.4, "cryogenic": True},
}

OXIDIZER_ALIASES = {"LOX": "LOX", "LO2": "LOX", "O2": "LOX"}
FUEL_ALIASES = {
    "RP1": "RP1", "KEROSENE": "RP1",
    "H2": "H2", "LH2": "H2", "HYDROGEN": "H2",
    "CH4": "CH4", "LCH4": "CH4", "METHANE": "CH4",
}


def clean(token):
    return token.strip().upper().replace("-", "").replace(" ", "").replace("_", "")


class PropellantProperties:
    def __init__(self, propellant, of_ratio=None, fuel_density=None, ox_density=None):
        parts = [clean(p) for p in propellant.split("/")]
        if len(parts) != 2:
            raise ValueError(f"Expected 'FUEL/OXIDIZER', got {propellant}")

        oxidizers = [p for p in parts if p in OXIDIZER_ALIASES]
        fuels = [p for p in parts if p in FUEL_ALIASES]
        if len(oxidizers) != 1 or len(fuels) != 1:
            raise ValueError(
                f"Couldn't identify one fuel and one oxidizer in {propellant}. "
                f"Fuels: {sorted(set(FUEL_ALIASES))}, Oxidizers: {sorted(set(OXIDIZER_ALIASES))}"
            )

        self.fuel = FUEL_ALIASES[fuels[0]]
        self.oxidizer = OXIDIZER_ALIASES[oxidizers[0]]
        self.name = f"{self.fuel}/{self.oxidizer}"

        fuel_data = FUELS[self.fuel]
        self.fuel_density = fuel_density if fuel_density is not None else fuel_data["density"]
        self.ox_density = ox_density if ox_density is not None else OXIDIZERS[self.oxidizer]["density"]
        self.of_ratio = of_ratio if of_ratio is not None else fuel_data["default_of"]
        self.fuel_is_cryogenic = fuel_data["cryogenic"]

        if min(self.fuel_density, self.ox_density, self.of_ratio) <= 0:
            raise ValueError("Densities and O/F ratio must be positive.")

        # mass fractions of total propellant
        self.ox_mf = self.of_ratio / (1 + self.of_ratio)
        self.fuel_mf = 1 / (1 + self.of_ratio)

        # volume per lb of propellant (ft^3/lb) and the resulting bulk density
        self.fuel_vol_per_lb = self.fuel_mf / self.fuel_density
        self.ox_vol_per_lb = self.ox_mf / self.ox_density
        self.bulk_density = 1 / (self.fuel_vol_per_lb + self.ox_vol_per_lb)

        # fraction of total propellant VOLUME that is oxidizer (tank split)
        self.ox_vol_frac = self.ox_vol_per_lb / (self.fuel_vol_per_lb + self.ox_vol_per_lb)

    def split_mass(self, m_prop):
        # fuel, oxidizer
        return m_prop * self.fuel_mf, m_prop * self.ox_mf

    def volumes(self, m_prop, ullage=0.03):
        # fuel, ox
        m_fuel, m_ox = self.split_mass(m_prop)
        scale = 1 + ullage
        return (m_fuel / self.fuel_density * scale, m_ox / self.ox_density * scale)

    def total_volume(self, m_prop, ullage=0.0):
        return sum(self.volumes(m_prop, ullage))

    def __repr__(self):
        return (f"PropellantProperties({self.name}, O/F={self.of_ratio:g}, "
                f"fuel={self.fuel_density:.2f}, ox={self.ox_density:.2f}, "
                f"bulk={self.bulk_density:.2f} lb/ft^3)")