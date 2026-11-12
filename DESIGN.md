# RocketSizer Design Specification

A desktop launch vehicle conceptual sizing, heritage cataloging, and interactive trade study platform built with Tauri v2, a Rust numerical core, and a React/TypeScript web interface.

## 0. Rules of Engagement & Implementation Philosophy

This document defines the complete architecture, mathematical models, data schemas, visual layouts, and implementation roadmap for RocketSizer.

1. **Physical & Mathematical Rigor**: Every equation decomposes into named intermediate terms with physical units. No hidden heuristics or arbitrary magic constants.
2. **Data Provenance**: Every number in the heritage tables links to a primary verified citation (document title, author, year, page number, URL) or an explicit mathematical derivation.
3. **Zero AI Style Tropes**: Clean technical prose without em dashes, negative parallelisms, or conversational filler.
4. **Unit System First**: Internal computations operate strictly in base SI units (`kg`, `m`, `N`, `s`, `Pa`, `USD`). Presentation layer provides zero-latency dynamic conversion between Metric and Imperial (`lbm`, `ft`, `lbf`, `s`, `psi`).
5. **Phase-by-Phase Delivery**: Development follows the phased roadmap in Section 15. Each phase must leave the application in a compiling, fully testable state.

## 1. Product Summary & Feature Scope

RocketSizer is an aerospace engineering workstation for rapid launch vehicle architecture evaluation, parametric trade studies, and heritage rocket/engine intelligence.

### 1.1 Core Capabilities
- **Hybrid Sizing Engine**: Explores discrete engine combinations, booster stages, and propellant types via combinatorial search, while offering an interactive manual sandbox where every parameter can be modified with real-time recalculation.
- **Flight Event Milestones**: Models fairing jettison during upper stage ascent (splitting the stage into pre- and post-jettison mass steps), Max-Q throttle reduction for aerodynamic load relief, and continuous throttle-down or sequential engine shutdown to clamp acceleration at the G-limit.
- **Multi-Mode Booster Reusability**: Dedicated recovery profiles for Expendable, Downrange Landing (ASDS / drone ship), Return-To-Launch-Site (RTLS), and Parachute/Mid-Air Catch with physics-based propellant allocations and structural penalties (landing legs, grid fins, thermal protection).
- **Physics-Based Tank Structural Mechanics**: Pressure vessel hoop stress and compressive buckling models paired with material presets (Al-Li 2195, Carbon Fiber Composite, 304L Stainless Steel) and square-cube diameter scaling, plus autogenous versus helium COPV pressurization mass.
- **Rubber Engine Scaler & Custom Propulsion**: Supports off-the-shelf heritage engines from the catalog as well as user-defined custom or parametrically scaled ("rubber") engines with cycle-specific thrust-to-weight and diameter scaling laws.
- **Parametric Fairing & Aerodynamic Drag**: Generates Von Kármán, ogive, or biconic fairing geometry from payload dimensions, computes acoustic blanket and dynamic clearance envelopes, calculates composite sandwich areal mass, and determines supersonic wave drag coefficient $C_{D,0}$ from nose fineness ratio.
- **Staging Separation & Cryogenic Options**: Selectable staging mechanics (cold pneumatic pushers with ullage settling burns versus hot-staging vented interstage ring with thermal blast shield) and propellant state toggles (standard boiling point versus deeply subcooled/densified cryogenics with boil-off coast loss modeling).
- **Cost Estimation & Multi-Objective Optimization**: Parametric cost modeling for development (DDT&E), flight hardware manufacturing (TFU), launch operations, propellants, and reusable refurbishment. Optimization can target minimum GLOW, minimum recurring launch cost, or a weighted multi-objective balance with hard user caps on mass, cost, or physical dimensions.
- **Comprehensive Heritage Database**: Filterable, sortable catalog of worldwide launch vehicles and rocket engines with over 50 specifications per vehicle and 45 specifications per engine.
- **Data Provenance Inspector**: Side drawer displaying verified primary sources (AIAA papers, NASA SP monographs, flight manuals, manufacturer guides) or step-by-step mathematical derivations for every data cell.
- **Geometric Engine Packaging & Clearance**: 2D circle-packing solver evaluating thrust structure layout, TVC gimbal clearance cones, nozzle no-touch margins, and skirt offsets with an interactive visual base layout diagram.
- **Dynamic Multi-Vehicle Scale Lineup**: Calibrated SVG visualizer rendering sized designs alongside historical and modern launch vehicles on a shared ground plane with dimension callouts.
- **Trade Study & Sensitivity Studio**: Automated sweeps across payload mass, delta-V split, structural mass fractions, and engine counts with multi-format export (PNG, SVG, CSV, Markdown, PDF).

### 1.2 Non-Goals
- Full 3D finite-element structural analysis or internal rib/stringer sizing.
- 6-DOF time-stepping trajectory guidance simulation with atmosphere wind profiles (the tool utilizes parametric loss integration).
- Solid rocket internal grain burn regression geometry modeling.

## 2. System Architecture & Tech Stack

```
+---------------------------------------------------------------------------------+
|                                Tauri v2 Shell                                   |
+---------------------------------------------------------------------------------+
|  React 19 / TypeScript 5 Frontend                                               |
|  - UI Primitives: Tailwind CSS, Radix UI / shadcn/ui, Lucide Icons              |
|  - Virtual Data Grids: TanStack Table v8 + TanStack Virtual                     |
|  - Visualizers: Native SVG with Pan/Zoom, Canvas 2D engine base renderer       |
|  - Analytical Plots: Recharts / Plotly.js for sensitivity curves and Pareto     |
|  - Presentation Layer: Metric <-> Imperial dynamic unit converter               |
+---------------------------------------+-----------------------------------------+
                                        | Tauri IPC (Binary Serde Protocol)
+---------------------------------------+-----------------------------------------+
|  Rust Numerical Core (rocket_sizer_core)                                        |
|  - Combinatorial Optimizer & Pareto Frontier Solver                             |
|  - Multistage Ascent Event Simulator (Fairing, Max-Q, G-Throttle)               |
|  - Multi-Mode Booster Reusability Allocator (RTLS, ASDS, Parachute)             |
|  - Pressure Vessel Hoop Stress & Material Buckling Solver                       |
|  - Concentric Circle-Packing & TVC Clearance Geometry Engine                   |
|  - Parametric Cost Model (TRANSCOST / NASA PCEC)                                |
|  - Serde In-Memory Data Store for Heritage Vehicles & Engines                   |
+---------------------------------------------------------------------------------+
```

### 2.1 Technology Rationale
- **Tauri v2 + Rust**: Standalone native desktop binary without Chromium overhead (15 MB executable, under 60 MB idle RAM). Rust executes multi-variable combinatorial sizing loops and geometry packing checks across 100,000 combinations in under 50 milliseconds.
- **React 19 + TypeScript**: Strong component typing, component state management, and virtualized rendering of large data tables without UI lag.
- **TanStack Table v8**: Powers advanced multi-column sorting, custom range/text filters, column pinning, and dynamic visibility toggles across 50+ data attributes.
- **Pure SVG Visualizers**: Crisp rendering at all zoom levels on 4K monitors, printable vector outputs, and straightforward DOM export to standalone `.svg` or high-resolution `.png`.

## 3. Data Provenance & Heritage Schemas

### 3.1 Provenance Contract
Every engineering parameter stored in the database or computed by the engine implements the `Provenance<T>` schema.

```typescript
export type ProvenanceStatus = 
  | "primary_source"       // NASA SP, user guide, flight manual, manufacturer spec
  | "derived"              // Calculated deterministically from other primary fields
  | "estimated"            // Engineering estimate with documented assumptions
  | "nominal_placeholder"; // Unverified default requiring validation

export interface Citation {
  document_title: string;
  author?: string;
  publisher?: string;
  publication_year?: number;
  page_number?: number;
  table_or_figure?: string;
  direct_url?: string;
  document_id?: string;
  excerpt?: string;
}

export interface Derivation {
  governing_equation: string;
  input_parameters: Record<string, number | string>;
  assumptions: string[];
  solver_method: string;
  confidence_rating: "high" | "medium" | "low";
}

export interface ProvenanceValue<T> {
  value: T;
  canonical_unit: string;
  status: ProvenanceStatus;
  citation?: Citation;
  derivation?: Derivation;
  notes?: string;
}
```

Rust representation:
```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ProvenanceStatus {
    PrimarySource,
    Derived,
    Estimated,
    NominalPlaceholder,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    pub document_title: String,
    pub author: Option<String>,
    pub publisher: Option<String>,
    pub publication_year: Option<u16>,
    pub page_number: Option<u16>,
    pub table_or_figure: Option<String>,
    pub direct_url: Option<String>,
    pub document_id: Option<String>,
    pub excerpt: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Derivation {
    pub governing_equation: String,
    pub input_parameters: HashMap<String, String>,
    pub assumptions: Vec<String>,
    pub solver_method: String,
    pub confidence_rating: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProvenanceValue<T> {
    pub value: T,
    pub canonical_unit: String,
    pub status: ProvenanceStatus,
    pub citation: Option<Citation>,
    pub derivation: Option<Derivation>,
    pub notes: Option<String>,
}
```

### 3.2 Heritage Vehicle Catalog Specification
The heritage vehicle catalog (`data/vehicles/*.json`) tracks the following fields per vehicle:

| Category | Field ID | Name & Description | Canonical Unit |
| :--- | :--- | :--- | :--- |
| Identity | `id` | Unique alphanumeric identifier (e.g. `saturn_v`) | text |
| Identity | `name` | Common vehicle name (e.g. Saturn V) | text |
| Identity | `variant` | Specific configuration variant (e.g. Block 1) | text |
| Identity | `manufacturer` | Primary vehicle contractor / agency | text |
| Identity | `country` | Nation of origin | text |
| Identity | `operational_status` | Status: active, retired, in_development | enum |
| Identity | `maiden_flight_year` | Calendar year of initial orbital attempt | year |
| Identity | `retirement_year` | Calendar year of final flight (if retired) | year |
| Mission Capacity | `payload_leo_kg` | Payload to Low Earth Orbit (200 km, 28.5 deg) | kg |
| Mission Capacity | `payload_sso_kg` | Payload to Sun-Synchronous Orbit (500 km, 98 deg) | kg |
| Mission Capacity | `payload_gto_kg` | Payload to Geostationary Transfer Orbit | kg |
| Mission Capacity | `payload_geo_kg` | Payload to Geostationary Orbit (direct) | kg |
| Mission Capacity | `payload_tli_kg` | Payload to Trans-Lunar Injection | kg |
| Mission Capacity | `payload_tmi_kg` | Payload to Trans-Mars Injection | kg |
| Physical Geometry | `total_height_m` | Total vehicle height on launch pad | m |
| Physical Geometry | `core_diameter_m` | Main core stage outer structural diameter | m |
| Physical Geometry | `max_width_m` | Total span including boosters or fins | m |
| Physical Geometry | `fairing_diameter_m` | Outer payload fairing diameter | m |
| Physical Geometry | `fairing_length_m` | Total axial fairing length | m |
| Physical Geometry | `usable_fairing_vol_m3` | Net payload static envelope volume | m^3 |
| Mass Properties | `glow_kg` | Gross Liftoff Weight (total fueled launch mass) | kg |
| Mass Properties | `total_dry_mass_kg` | Total inert mass of all stages (excluding payload) | kg |
| Mass Properties | `payload_fraction_leo` | Ratio of LEO payload to GLOW | fraction |
| Propulsion Summary | `liftoff_thrust_sl_n` | Total combined sea-level thrust at ignition | N |
| Propulsion Summary | `liftoff_tw0` | Initial vehicle thrust-to-weight ratio | ratio |
| Propulsion Summary | `stage_count` | Number of core tandem stages (e.g. 2, 3) | integer |
| Propulsion Summary | `booster_count` | Number of parallel strap-on boosters | integer |
| Propulsion Summary | `booster_type` | Booster classification: solid, liquid, none | enum |
| Stage 1 Detail | `s1_propellant` | Propellant combination (e.g. LOX/RP-1) | enum |
| Stage 1 Detail | `s1_engine_id` | Engine identifier | text |
| Stage 1 Detail | `s1_engine_count` | Number of engines in first stage | integer |
| Stage 1 Detail | `s1_prop_mass_kg` | Usable stage 1 propellant mass | kg |
| Stage 1 Detail | `s1_dry_mass_kg` | Stage 1 dry mass including engines | kg |
| Stage 1 Detail | `s1_burn_time_s` | Nominal stage 1 burn duration | s |
| Stage 2 Detail | `s2_propellant` | Propellant combination (e.g. LOX/LH2) | enum |
| Stage 2 Detail | `s2_engine_id` | Engine identifier | text |
| Stage 2 Detail | `s2_engine_count` | Number of engines in second stage | integer |
| Stage 2 Detail | `s2_prop_mass_kg` | Usable stage 2 propellant mass | kg |
| Stage 2 Detail | `s2_dry_mass_kg` | Stage 2 dry mass including engines | kg |
| Stage 2 Detail | `s2_burn_time_s` | Nominal stage 2 burn duration | s |
| Booster Detail | `booster_propellant` | Propellant combination | enum |
| Booster Detail | `booster_engine_id` | Motor or engine identifier | text |
| Booster Detail | `booster_engine_count`| Engines per individual booster | integer |
| Booster Detail | `booster_prop_mass_kg`| Usable propellant per individual booster | kg |
| Booster Detail | `booster_dry_mass_kg` | Dry mass per individual booster | kg |
| Booster Detail | `booster_burn_time_s` | Booster burn duration | s |
| Financial & Operations | `launch_cost_original_usd` | Historical launch price per flight | USD |
| Financial & Operations | `launch_cost_year` | Dollar year of original quote | year |
| Financial & Operations | `launch_cost_adj_usd` | Inflation-adjusted launch price (FY2026$) | USD |
| Financial & Operations | `cost_per_kg_leo_usd` | Launch price divided by LEO payload capacity | USD/kg |
| Financial & Operations | `development_cost_usd` | Program DDT&E investment cost | USD |
| Track Record | `total_launches` | Total orbital launch attempts | integer |
| Track Record | `successful_launches`| Fully successful missions | integer |
| Track Record | `launch_success_rate`| Percentage of successful flights | percent |

### 3.3 Heritage Engine Catalog Specification
The propulsion catalog (`data/engines/*.json`) tracks the following fields per engine:

| Category | Field ID | Name & Description | Canonical Unit |
| :--- | :--- | :--- | :--- |
| Identity | `id` | Unique alphanumeric identifier (e.g. `raptor_2`) | text |
| Identity | `name` | Common engine name (e.g. Raptor 2) | text |
| Identity | `manufacturer` | Prime propulsion contractor | text |
| Identity | `country` | Nation of origin | text |
| Identity | `status` | Operational status: active, retired, dev | enum |
| Identity | `propulsion_type` | Engine classification: liquid, solid | enum |
| Cycle & Chemistry | `propellant` | Fuel and oxidizer combination | enum |
| Cycle & Chemistry | `cycle` | Power cycle (gas generator, staged comb, etc.) | enum |
| Cycle & Chemistry | `oxidizer_fuel_ratio` | Optimum oxidizer-to-fuel mixture ratio | ratio |
| Thrust & Isp | `thrust_sl_n` | Sea-level thrust at 100% throttle | N |
| Thrust & Isp | `thrust_vac_n` | Vacuum thrust at 100% throttle | N |
| Thrust & Isp | `isp_sl_s` | Sea-level specific impulse | s |
| Thrust & Isp | `isp_vac_s` | Vacuum specific impulse | s |
| Thrust & Isp | `isp_avg_s` | Trajectory average Isp through atmosphere | s |
| Thrust & Isp | `mass_flow_rate_kg_s` | Total propellant mass flow rate at full throttle | kg/s |
| Operating Conditions | `chamber_pressure_bar`| Main combustion chamber pressure | bar |
| Operating Conditions | `expansion_ratio` | Nozzle expansion area ratio (Ae / At) | ratio |
| Operating Conditions | `min_throttle_pct` | Minimum reliable throttle setting | percent |
| Operating Conditions | `max_throttle_pct` | Maximum allowable throttle overthrust | percent |
| Operating Conditions | `restarts_rated` | Number of verified in-flight restarts | integer |
| Geometry & Inertia | `dry_mass_kg` | Bare engine dry weight including TVC actuators | kg |
| Geometry & Inertia | `height_m` | Axial length from gimbal mount to nozzle exit | m |
| Geometry & Inertia | `nozzle_diameter_m` | Maximum outer diameter of nozzle exit bell | m |
| Geometry & Inertia | `gimbal_envelope_dia_m`| Outer powerhead / actuator swing circle | m |
| Geometry & Inertia | `tvc_gimbal_range_deg`| Maximum vector angle in pitch/yaw axes | deg |
| Performance Ratios | `thrust_to_weight_vac` | Vacuum thrust divided by engine dry weight | ratio |
| Financial & Operations | `unit_cost_usd` | Recurring hardware procurement cost | USD |
| Financial & Operations | `development_cost_usd` | Engine development and test program cost | USD |

## 4. Multistage Sizing & Flight Mechanics

The sizing solver supports 1.5-stage, 2-stage, 2-stage with parallel boosters (liquid or solid), and 3-stage vehicles.

### 4.1 Trajectory Loss Modeling & Delta-V Formulation
The total required Delta-V budget is computed from mission mechanics:

$$\Delta V_{\text{budget}} = \Delta V_{\text{orbit}} + \Delta V_{\text{gravity}} + \Delta V_{\text{aero}} + \Delta V_{\text{steering}} - \Delta V_{\text{Earth}}$$

Intermediate calculation decomposition:
1. **Target Orbit Velocity**:
$$v_{\text{orbit}} = \sqrt{\frac{\mu_E}{R_E + h_{\text{orbit}}}}$$
$$\Delta V_{\text{orbit}} = v_{\text{orbit}} + v_{\text{insertion\_margin}}$$
2. **Earth Rotation Assist**:
$$v_{\text{rot\_equator}} = \omega_E \cdot R_E$$
$$\Delta V_{\text{Earth}} = v_{\text{rot\_equator}} \cdot \cos(\phi_{\text{launch}}) \cdot \sin(\beta_{\text{azimuth}})$$
Where $\omega_E = 7.2921159 \times 10^{-5}\text{ rad/s}$, $R_E = 6,378,137\text{ m}$.
3. **Gravity Losses**:
Decomposed using average pitch angle $\bar{\theta}$ and stage burn time $t_{\text{burn}}$:
$$g_{\text{eff}} = g_0 \cdot \sin(\bar{\theta}_{\text{pitch}})$$
$$\Delta V_{\text{gravity}} = \sum_{i=1}^{N_{\text{stages}}} g_{\text{eff}, i} \cdot t_{\text{burn}, i}$$
4. **Aerodynamic Drag Losses**:
Parametric scaling based on vehicle diameter $D_{\text{core}}$ and liftoff mass:
$$\text{term1}_{\text{aero}} = \frac{1}{2} \cdot \rho_0 \cdot v_{\text{maxQ}}^2 \cdot C_D \cdot A_{\text{ref}}$$
$$\Delta V_{\text{aero}} = \frac{\text{term1}_{\text{aero}} \cdot \Delta t_{\text{transonic}}}{m_{\text{transonic}}}$$
5. **Steering Losses**:
Empirical gravity turn curvature loss:
$$\Delta V_{\text{steering}} = v_{\text{orbit}} \cdot \left(1 - \cos(\Delta \theta_{\text{turn}})\right)$$

Standard Mission Presets:
- **LEO 28.5 deg (Cape Canaveral)**: $\Delta V = 9,250\text{ m/s}$ (30,348 ft/s).
- **LEO 51.6 deg (ISS)**: $\Delta V = 9,400\text{ m/s}$ (30,840 ft/s).
- **SSO 98.0 deg (Vandenberg)**: $\Delta V = 9,600\text{ m/s}$ (31,496 ft/s).
- **GTO (28.5 deg to $185 \times 35,786\text{ km}$)**: $\Delta V = 11,700\text{ m/s}$ (38,386 ft/s).
- **TLI (Direct Moon Injection)**: $\Delta V = 12,450\text{ m/s}$ (40,846 ft/s).
- **TMI (Trans-Mars Injection)**: $\Delta V = 12,850\text{ m/s}$ (42,159 ft/s).

### 4.2 Event-Based Ascent Milestones
Rather than treating each stage as a single monolithic mass dump, RocketSizer models discrete in-flight flight events:

1. **Fairing Jettison Sub-Phasing**:
The upper stage burn is split into two distinct mass integration regimes:
- *Phase 2A (Pre-Fairing Jettison)*: Carries payload, fairing mass ($m_{\text{fairing}}$), and stage 2 dry hardware. Burns until atmospheric pressure drops below $p_{\text{exit}} \le 0.1\text{ Pa}$ (altitude $\sim 105\text{ km}$, typically consuming $\Delta V_{\text{pre\_fairing}} \approx 800\text{ to }1,200\text{ m/s}$).
$$m_{\text{initial, 2A}} = m_{\text{prop, 2}} + m_{\text{dry, 2}} + m_{\text{fairing}} + m_{\text{payload}}$$
$$m_{\text{final, 2A}} = m_{\text{initial, 2A}} - \dot{m}_2 \cdot t_{\text{jettison}}$$
- *Phase 2B (Post-Fairing Jettison)*: Fairing mass is discarded:
$$m_{\text{initial, 2B}} = m_{\text{final, 2A}} - m_{\text{fairing}}$$
$$m_{\text{final, 2B}} = m_{\text{dry, 2}} + m_{\text{payload}}$$
$$\Delta V_2 = I_{\text{sp, 2}} \cdot g_0 \cdot \ln\left(\frac{m_{\text{initial, 2A}}}{m_{\text{final, 2A}}}\right) + I_{\text{sp, 2}} \cdot g_0 \cdot \ln\left(\frac{m_{\text{initial, 2B}}}{m_{\text{final, 2B}}}\right)$$
This accurate modeling prevents the common 15% to 25% payload underestimation caused by assuming fairing retention to orbit.

2. **Max-Q Throttle Reduction (Load Relief Bucket)**:
During atmospheric ascent, aerodynamic dynamic pressure peaks at Max-Q:
$$q_{\text{max}} = \frac{1}{2} \cdot \rho(h_{\text{maxQ}}) \cdot v(h_{\text{maxQ}})^2$$
Core stage throttle throttles down to $T_{\text{throttle\_min}} \in [65\%, 75\%]$ for a duration $\Delta t_{\text{bucket}} \approx 20\text{ to }30\text{ s}$ to keep dynamic pressure within structural limits ($q_{\text{allow}} \le 35\text{ to }42\text{ kPa}$). Average boost phase specific impulse and burn time account for this throttle bucket.

3. **Burnout Acceleration Clamping (G-Limiting)**:
As propellants deplete, vehicle acceleration increases:
$$a(t) = \frac{T(t)}{m(t)}$$
When $a(t)$ reaches the user-specified ceiling $G_{\text{limit}}$ (default 4.5 g for commercial satellite payloads, 6.0 g for cargo):
- Continuous throttling: Throttle reduces linearly down to $T_{\text{min\_throttle}}$:
$$T_{\text{clamped}}(t) = G_{\text{limit}} \cdot m(t)$$
- Engine cutoff sequencing: If $T_{\text{clamped}} < T_{\text{min\_throttle}} \cdot N_{\text{engines}}$, the solver simulates sequential engine shutdown (e.g. shutting down center engines first, then symmetrical pairs).

### 4.3 Multi-Mode Booster Reusability Allocations
When booster recovery is selected, usable propellant is partitioned between ascent and recovery:
$$m_{\text{prop, booster}} = m_{\text{prop, ascent}} + m_{\text{prop, recovery}}$$

Four distinct recovery profiles are implemented:

| Recovery Profile | Mission Profile Description | Propellant Reserve ($\%$ Booster Prop) | Added Dry Hardware Mass ($\%$ Dry Mass) |
| :--- | :--- | :--- | :--- |
| **Expendable** | Core stage and boosters burn all propellant to burnout | $0.0\%$ | $0.0\%$ |
| **Downrange Landing (ASDS)** | Boosters coast downrange; perform entry burn and landing burn onto ocean barge | $6.5\%\text{ to }9.0\%$ | Legs: $2.5\%$, Fins: $1.2\%$, TPS: $1.5\%$ |
| **Return to Launch Site (RTLS)** | Full boostback burn cancels downrange velocity and returns to pad | $12.5\%\text{ to }16.0\%$ | Legs: $2.5\%$, Fins: $1.2\%$, TPS: $2.0\%$ |
| **Parachute / Mid-Air Catch** | Atmospheric deceleration via drogue and parafoil | $0.5\%\text{ (ullage only)}$ | Parachutes + heat shield: $6.0\%\text{ to }8.5\%$ |

1. **Boostback Burn Allocation (RTLS only)**:
$$\Delta V_{\text{boostback}} = v_{\text{staging}} \cdot \cos(\gamma_{\text{staging}}) + v_{\text{return\_target}}$$
$$m_{\text{prop, boostback}} = m_{\text{booster, burnout}} \cdot \left(\exp\left(\frac{\Delta V_{\text{boostback}}}{I_{\text{sp, vac}} \cdot g_0}\right) - 1\right)$$
2. **Re-entry Burn Allocation (ASDS and RTLS)**:
Provides supersonic retro-propulsion to reduce thermal aero-heating from Mach 6 down to Mach 3:
$$\Delta V_{\text{entry}} = 450\text{ to }750\text{ m/s}$$
3. **Terminal Landing Burn Allocation (ASDS and RTLS)**:
Final suicide burn executed by a single or clustered center engines:
$$\Delta V_{\text{landing}} = \sqrt{2 \cdot g_{\text{eff}} \cdot h_{\text{ignition}}} + \Delta v_{\text{hover\_margin}} \approx 250\text{ to }350\text{ m/s}$$

### 4.4 Staging Mechanics: Pneumatic Cold Staging vs Hot Staging Ring
The solver models both primary separation architectures:

1. **Pneumatic Pushers with Ullage Settling (Cold Staging)**:
- Core stage engines shut down fully before separation.
- Pneumatic pusher cylinders or pyrotechnic latches impart relative separation velocity ($\Delta v_{\text{sep}} \approx 1.5\text{ to }2.5\text{ m/s}$).
- Small solid rocket motors or cold-gas RCS thrusters fire for $\Delta t_{\text{ullage}} \approx 3\text{ to }5\text{ s}$ to settle liquid propellants at the bottom of upper stage tanks before engine ignition.
- Gravity loss penalty: Coasting unpowered for 4 to 8 seconds incurs an effective velocity loss of $\Delta V_{\text{ullage\_loss}} = g_0 \cdot \Delta t_{\text{coast}}$.

2. **Vented Interstage Ring (Hot Staging)**:
- Upper stage engines ignite while the first stage is still firing (or at low throttle).
- Interstage adapter features open cutouts and exhaust vents to channel upper stage plume gas outward.
- Eliminates ullage settle motors, reduces coast gravity loss to near zero ($\Delta t_{\text{coast}} = 0$), and improves delivered payload to orbit by $4\%\text{ to }8\%$.
- Structural penalty: Adds heavy titanium/Inconel thermal blast deflection dome to first stage forward dome and stiffened interstage venting ring ($m_{\text{hot\_staging\_penalty}} = 450\text{ to }1,200\text{ kg}$).

## 5. Structural Mechanics & Material Sizing

RocketSizer pairs empirical mass fraction baselines with a physics-based pressure vessel structural model.

### 5.1 Pressure Vessel Wall Thickness & Hoop Stress
Tank barrel wall thickness $t_{\text{wall}}$ is calculated from maximum expected operating pressure (MEOP), hydrostatic liquid head, and material yield strength:
$$P_{\text{total}} = P_{\text{ullage}} + \rho_{\text{prop}} \cdot a_{\text{max}} \cdot h_{\text{fluid\_column}}$$
$$\text{term1}_{\text{hoop}} = \frac{P_{\text{total}} \cdot R_{\text{tank}}}{\sigma_{\text{allow}} - 0.6 \cdot P_{\text{total}}}$$
$$t_{\text{wall}} = \max\left(\text{term1}_{\text{hoop}} \cdot \text{SF}_{\text{burst}}, \quad t_{\text{mfg\_min}}\right)$$
Where $\text{SF}_{\text{burst}} = 1.40$ (standard aerospace factor of safety for pressure vessels), $t_{\text{mfg\_min}}$ is manufacturing minimum gauge (e.g. 1.2 mm for aluminum-lithium, 0.8 mm for stainless steel, 1.5 mm for composite).

### 5.2 Compressive Axial Buckling Check
During flight under maximum axial load ($F_{\text{axial}} = m_{\text{upper}} \cdot a_{\text{max}} + F_{\text{aero}}$):
$$\sigma_{\text{critical}} = \gamma_{\text{knockdown}} \cdot \frac{E}{\sqrt{3 \cdot (1 - \nu^2)}} \cdot \left(\frac{t_{\text{wall}}}{R_{\text{tank}}}\right)$$
If internal pressure stabilization is insufficient to prevent buckling, an isogrid or orthogrid stiffening mass factor is added.

### 5.3 Material Database Presets
The engineering database includes physical properties for modern aerospace tank materials:

| Material Name | Density $\rho$ ($\text{kg/m}^3$) | Tensile Yield $\sigma_y$ ($\text{MPa}$) | Cryogenic Yield $\sigma_{y, \text{cryo}}$ ($\text{MPa}$) | Modulus $E$ ($\text{GPa}$) | Raw Material Cost (\$/kg) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Al-Li 2195** | 2,710 | 540 | 660 | 76 | \$48.00 |
| **CFRP Composite** | 1,550 | 850 | 920 | 110 | \$140.00 |
| **304L Stainless Steel**| 7,930 | 290 | 1,150 | 195 | \$4.50 |
| **Titanium Ti-6Al-4V** | 4,430 | 880 | 1,220 | 114 | \$85.00 |

### 5.4 Pressurization Architecture: Autogenous vs Helium COPV
1. **Autogenous Pressurization**:
Taps gaseous fuel and oxidizer from engine chamber cooling jackets or preburners, routing high-pressure warm gas back to tanks.
- Eliminates helium storage bottles and sub-dewar plumbing.
- Gas mass: $m_{\text{gas}} = \frac{P_{\text{ullage}} \cdot V_{\text{ullage}}}{R_{\text{specific}} \cdot T_{\text{gas}}}$.
- Net system mass reduction: Saves 300 to 1,200 kg compared to helium pressure systems on large vehicles.

2. **Helium COPV Pressurization**:
Stores gaseous helium at 310 bar (4,500 psi) in carbon overwrapped pressure vessels submerged inside cryogenic tanks.
- Helium mass required:
$$m_{\text{He}} = \frac{P_{\text{tank}} \cdot V_{\text{tank}}}{R_{\text{He}} \cdot T_{\text{He}}} \cdot \gamma_{\text{collapse}}$$
Where $\gamma_{\text{collapse}} \approx 1.25$ accounts for helium thermal contraction in cold cryogenic ullage.
- Bottle dry mass: $m_{\text{copv}} = 0.55 \cdot m_{\text{He}}$.

### 5.5 Cryogenic Densification & Coast Boil-Off
1. **Deep Subcooling / Densification**:
- Liquid Oxygen cooled from boiling ($90.2\text{ K}$) down to $66.5\text{ K}$: Density increases from $1,141\text{ kg/m}^3$ to $1,230\text{ kg/m}^3$ ($+7.8\%$).
- Liquid Methane cooled from boiling ($111.6\text{ K}$) down to $91.0\text{ K}$: Density increases from $422\text{ kg/m}^3$ to $451\text{ kg/m}^3$ ($+6.9\%$).
- Result: Slashes tank length and structural dry mass, allowing a higher propellant mass fraction.

2. **Orbital Coast Boil-Off Loss**:
For upper stages performing multi-hour coasts (GTO / TLI / GEO direct):
$$\dot{Q}_{\text{leak}} = \frac{k_{\text{insulation}} \cdot A_{\text{wetted}} \cdot \Delta T}{t_{\text{MLI}}}$$
$$\dot{m}_{\text{boiloff}} = \frac{\dot{Q}_{\text{leak}}}{h_{\text{vaporization}}}$$
$$m_{\text{boiloff\_loss}} = \dot{m}_{\text{boiloff}} \cdot t_{\text{coast}}$$
The sizing engine flags stages with insufficient propellant margin for long-duration coast insertions.

## 6. Propulsion & "Rubber Engine" Parametric Scaling

RocketSizer enables both discrete heritage engine selection and parametric scaling of custom ("rubber") engines.

### 6.1 Rubber Engine Scaling Laws
When rubber engine mode is active, the user specifies desired thrust $T_{\text{target}}$ and propellant cycle family. The engine calculates all physical properties using aerospace scaling exponents:

1. **Engine Dry Mass Scaling**:
$$m_{\text{dry, scaled}} = m_{\text{ref}} \cdot \left(\frac{T_{\text{target}}}{T_{\text{ref}}}\right)^{\alpha_{\text{mass}}} \cdot \left(\frac{P_{\text{chamber}}}{P_{\text{ref}}}\right)^{\beta_{\text{mass}}}$$
Where $\alpha_{\text{mass}} = 0.82$, $\beta_{\text{mass}} = -0.15$ (higher chamber pressure reduces engine physical size for a given thrust).

2. **Nozzle Exit Diameter Scaling**:
$$A_{\text{throat}} = \frac{T_{\text{target}}}{C_F \cdot P_{\text{chamber}}}$$
$$A_{\text{exit}} = \epsilon \cdot A_{\text{throat}}$$
$$D_{\text{exit, scaled}} = \sqrt{\frac{4 \cdot A_{\text{exit}}}{\pi}}$$

3. **Sea-Level Specific Impulse Adaptation**:
For a scaled nozzle exit area $A_{\text{exit}}$ and vacuum thrust $T_{\text{vac}}$:
$$T_{\text{sl, scaled}} = T_{\text{vac, scaled}} - p_{\text{sl}} \cdot A_{\text{exit}}$$
$$I_{\text{sp, sl}} = I_{\text{sp, vac}} \cdot \left(\frac{T_{\text{sl, scaled}}}{T_{\text{vac, scaled}}}\right)$$

## 7. Parametric Fairing Geometry & Aerodynamics

Fairings are sized directly from payload dimensions and modeled for structural mass and aerodynamic wave drag.

### 7.1 Fairing Geometry Profiles
1. **Von Kármán Profile (Minimum Wave Drag)**:
Nose profile coordinate $y(x)$ from tip ($x = 0$) to base ($x = L_{\text{nose}}$) for base radius $R = D_{\text{fairing}} / 2$:
$$\theta = \arccos\left(1 - \frac{2 \cdot x}{L_{\text{nose}}}\right)$$
$$y(x) = \frac{R}{\sqrt{\pi}} \cdot \sqrt{\theta - \frac{\sin(2\cdot\theta)}{2}}$$
2. **Tangent Ogive Profile**:
Defined by circular arc of radius $\rho_{\text{ogive}} = \frac{R^2 + L_{\text{nose}}^2}{2 \cdot R}$:
$$y(x) = \sqrt{\rho_{\text{ogive}}^2 - (L_{\text{nose}} - x)^2} + R - \rho_{\text{ogive}}$$

### 7.2 Clearances & Dynamic Envelopes
$$\text{term1}_{\text{clearance}} = \delta_{\text{dynamic\_sway}} + t_{\text{acoustic\_blanket}}$$
$$D_{\text{fairing, outer}} = D_{\text{payload}} + 2 \cdot \text{term1}_{\text{clearance}} + 2 \cdot t_{\text{fairing\_shell}}$$
$$L_{\text{fairing, total}} = L_{\text{nose}} + L_{\text{barrel}} + L_{\text{boat\_tail}}$$
Where $\delta_{\text{dynamic\_sway}} = 0.05 \cdot D_{\text{payload}}$ (payload deflection allowance) and $t_{\text{acoustic\_blanket}} = 0.075\text{ m}$ (3 inches).

### 7.3 Fairing Mass & Supersonic Wave Drag
Fairing surface area $S_{\text{fairing}}$ is integrated over nose and barrel sections:
$$m_{\text{fairing}} = S_{\text{fairing}} \cdot \rho_{\text{areal}} \cdot (1 + \text{margin}_{\text{mfg}})$$
Where $\rho_{\text{areal}} = 8.5\text{ kg/m}^2$ for CFRP aluminum honeycomb sandwich, $14.0\text{ kg/m}^2$ for aluminum isogrid.

Supersonic zero-lift wave drag coefficient $C_{D,0}$ scales inversely with nose fineness ratio $\lambda = L_{\text{nose}} / D_{\text{fairing}}$:
$$C_{D,0} \approx \frac{0.80}{\lambda^{1.65}} + C_{f, \text{skin}} \cdot \left(\frac{S_{\text{wetted}}}{A_{\text{ref}}}\right)$$

## 8. Parametric Cost Model

RocketSizer incorporates a full parametric life-cycle cost engine based on established aerospace cost estimation relationships (NASA PCEC, TRANSCOST, and commercial launch market regressions).

### 8.1 Cost Decomposition
The cost model outputs costs across four distinct tiers:
1. **DDT&E Cost**: Non-recurring design, development, test, and evaluation investment.
2. **TFU Cost**: Theoretical First Unit hardware manufacturing cost.
3. **Recurring Cost per Flight**: Manufacturing amortized over production lot + launch operations + propellants + range fees.
4. **Reusable Amortized Cost**: Flight cost accounting for booster/fairing recovery, fleet size, and turnaround refurbishment.

### 8.2 Airframe & Stage Structure Cost Models
Airframe manufacturing cost scales with stage dry mass minus engine mass ($m_{\text{airframe}} = m_{\text{dry}} - \sum m_{\text{engine}}$):

**DDT&E Cost Formulation**:
$$\text{term1}_{\text{ddte}} = a_{\text{struct}} \cdot (m_{\text{airframe}, \text{kg}})^{b_{\text{struct}}}$$
$$C_{\text{ddte, struct}} = \text{term1}_{\text{ddte}} \cdot f_{\text{complexity}} \cdot f_{\text{material}} \cdot f_{\text{inflation}}$$

Where:
- $a_{\text{struct}} = 125,000\text{ USD}$, $b_{\text{struct}} = 0.55$.
- $f_{\text{material}}$: Aluminum-Lithium = 1.0, Carbon Composite = 1.35, Stainless Steel 304L/301 = 0.65.
- $f_{\text{complexity}}$: Core liquid stage = 1.0, Upper cryogenic stage = 1.25, Solid motor casing = 0.50.

**Theoretical First Unit (TFU) Manufacturing Cost**:
$$\text{term1}_{\text{tfu}} = a_{\text{tfu}} \cdot (m_{\text{airframe}, \text{kg}})^{b_{\text{tfu}}}$$
$$C_{\text{tfu, struct}} = \text{term1}_{\text{tfu}} \cdot f_{\text{material}} \cdot f_{\text{inflation}}$$
Where $a_{\text{tfu}} = 18,500\text{ USD}$, $b_{\text{tfu}} = 0.62$.

**Cumulative Average Unit Cost (Learning Curve)**:
For production quantity $Q$ with learning rate $s$ (default $s = 0.85$ for aerospace structures):
$$p = \frac{\ln(s)}{\ln(2)}$$
$$C_{\text{avg, struct}}(Q) = C_{\text{tfu, struct}} \cdot \frac{Q^p}{1 + p}$$

### 8.3 Propulsion Hardware Cost Model
Liquid rocket engines are priced using thrust, chamber pressure, and cycle complexity factors:

**Engine DDT&E**:
$$\text{term1}_{\text{eng\_ddte}} = a_{\text{eng\_ddte}} \cdot (T_{\text{vac, kN}})^{0.535} \cdot (P_{\text{chamber, bar}})^{0.21}$$
$$C_{\text{ddte, eng}} = \text{term1}_{\text{eng\_ddte}} \cdot f_{\text{cycle}} \cdot f_{\text{propellant}}$$

Where:
- $a_{\text{eng\_ddte}} = 850,000\text{ USD}$.
- $f_{\text{cycle}}$: Pressure-fed = 0.40, Gas Generator = 1.0, Staged Combustion = 1.75, Full-Flow Staged Combustion = 2.20.
- $f_{\text{propellant}}$: LOX/RP-1 = 1.0, LOX/CH4 = 1.15, LOX/LH2 = 1.45.

**Engine Recurring Production (TFU)**:
$$\text{term1}_{\text{eng\_tfu}} = a_{\text{eng\_tfu}} \cdot (T_{\text{vac, kN}})^{0.485} \cdot (P_{\text{chamber, bar}})^{0.18}$$
$$C_{\text{tfu, eng}} = \text{term1}_{\text{eng\_tfu}} \cdot f_{\text{cycle}} \cdot f_{\text{propellant}}$$
Where $a_{\text{eng\_tfu}} = 42,000\text{ USD}$.

### 8.4 Propellant & Consumables Cost Model
Chemical propellants are calculated directly from stage fuel and oxidizer loads:
$$m_{\text{ox}} = m_{\text{prop}} \cdot \frac{O/F}{1 + O/F}, \quad m_{\text{fuel}} = m_{\text{prop}} \cdot \frac{1}{1 + O/F}$$
$$C_{\text{prop}} = m_{\text{ox}} \cdot c_{\text{ox}} + m_{\text{fuel}} \cdot c_{\text{fuel}} + m_{\text{helium}} \cdot c_{\text{helium}}$$

Standard Commodity Pricing (USD/kg):
- Liquid Oxygen (LOX): \$0.18 / kg.
- Liquid Hydrogen (LH2): \$4.50 / kg.
- Rocket Propellant 1 (RP-1): \$1.85 / kg.
- Liquid Methane (LCH4): \$0.65 / kg.
- Solid HTPB Propellant: \$16.00 / kg.
- High-Pressure Gaseous Helium: \$35.00 / kg.

### 8.5 Reusable Operations & Refurbishment Model
When recovery toggles are enabled:
$$C_{\text{flight, reusable}} = \frac{C_{\text{hardware, expendable}}}{N_{\text{reuses}}} + C_{\text{refurb}} + C_{\text{recovery\_ops}} + C_{\text{prop}} + C_{\text{range}}$$
Where:
- $N_{\text{reuses}}$: Expected booster flight count (e.g. 10 to 20 flights).
- $C_{\text{refurb}} = f_{\text{refurb}} \cdot C_{\text{hardware, stage1}}$ (default $f_{\text{refurb}} = 0.08$ for methane, $0.15$ for RP-1).
- $C_{\text{recovery\_ops}}$: Drone ship / return to launch site recovery fleet operations (\$450,000 per recovery).
- Fairing reuse credit: Fairing recovery saves 80% of fairing manufacturing cost minus \$350,000 recovery inspection cost.

## 9. Optimization Architecture & Objective Formulations

RocketSizer allows the user to solve architectures across multiple optimization regimes.

### 9.1 Multi-Objective Function Formulation
The solver optimizes a configurable scalar fitness score:
$$J(x) = w_{\text{GLOW}} \cdot \left(\frac{\text{GLOW}(x)}{\text{GLOW}_{\text{ref}}}\right) + w_{\text{cost}} \cdot \left(\frac{C_{\text{flight}}(x)}{C_{\text{ref}}}\right) + w_{\text{dry}} \cdot \left(\frac{m_{\text{dry}}(x)}{m_{\text{dry, ref}}}\right)$$

User Controls:
- **Optimization Strategy Selector**:
  1. *Minimize GLOW*: $w_{\text{GLOW}} = 1.0, w_{\text{cost}} = 0.0$.
  2. *Minimize Launch Cost*: $w_{\text{GLOW}} = 0.0, w_{\text{cost}} = 1.0$.
  3. *Balanced Trade*: Interactive slider setting $w_{\text{GLOW}} \in [0.0, 1.0]$ and $w_{\text{cost}} = 1.0 - w_{\text{GLOW}}$.
  4. *Pareto Frontier Generation*: Sweeps weights from 0 to 1 to produce a non-dominated trade curve of Mass versus Cost.

### 9.2 Hard Constraint Envelopes & User Overrides
Configurations violating any hard constraint are pruned immediately or tagged with violation flags:
1. **Cost Ceiling**: $C_{\text{flight}} \le C_{\text{max, user}}$ (e.g. "Do not exceed \$90M per launch").
2. **GLOW Ceiling**: $\text{GLOW} \le \text{GLOW}_{\text{max, user}}$ (e.g. "Pad maximum crane limit 1,500,000 lbs").
3. **Core Diameter Limit**: $D_{\text{core}} \le D_{\text{max, user}}$ (e.g. "Tooling or road transport constraint $\le 33\text{ ft}$").
4. **Maximum Total Height**: $H_{\text{total}} \le H_{\text{max, user}}$ (e.g. "Vehicle Assembly Building clearance").
5. **Acceleration Limit**: $a_{\text{burnout}} \le G_{\text{limit}}$ (default 4.5 g for commercial payloads, 6.0 g for cargo).
6. **Engine Count Bounds**: $N_{\text{core}} \le N_{\text{max, core}}$, $N_{\text{upper}} \le N_{\text{max, upper}}$, $N_{\text{boosters}} \in [0, 2, 3, 4, 6]$.
7. **Liftoff Thrust-to-Weight**: $T/W_{\text{liftoff, min}} \le T/W_0 \le T/W_{\text{liftoff, max}}$ (defaults: $1.20 \le T/W_0 \le 1.60$).
8. **Geometric Base Packing**: Required engine circle envelope must fit within usable thrust structure diameter.

## 10. Geometric Packaging & Base Layout Engine

### 10.1 Dynamic 2D Circle-Packing Algorithm
To determine whether an engine cluster fits physically in a stage diameter, the geometric engine executes a concentric ring circle-packing routine.

1. **Individual Engine Effective Footprint**:
$$\text{term1}_{\text{tvc}} = 2 \cdot L_{\text{gimbal}} \cdot \sin(\theta_{\text{tvc}})$$
$$D_{\text{footprint}} = D_{\text{nozzle}} + \text{term1}_{\text{tvc}} + \delta_{\text{no\_touch}}$$
Where $D_{\text{nozzle}}$ is nozzle exit diameter, $L_{\text{gimbal}}$ is actuator lever arm, $\theta_{\text{tvc}}$ is gimbal deflection angle (default 7 deg), and $\delta_{\text{no\_touch}}$ is physical separation margin (default 4 inches / 0.10 m).

2. **Usable Stage Base Diameter**:
$$D_{\text{usable}} = D_{\text{stage}} - 2 \cdot (t_{\text{skirt\_wall}} + \delta_{\text{skirt\_clearance}})$$
Where $t_{\text{skirt\_wall}}$ is structural wall thickness and $\delta_{\text{skirt\_clearance}}$ is ring frame margin.

3. **Pattern Geometry Generator**:
- **Pattern A (Single Engine)**: $D_{\text{req}} = D_{\text{footprint}}$.
- **Pattern B (Ring of $N$ Engines without Center)**:
$$R_{\text{ring}} = \frac{D_{\text{footprint}}}{2 \cdot \sin(\pi / N)}$$
$$D_{\text{req}} = 2 \cdot R_{\text{ring}} + D_{\text{footprint}}$$
- **Pattern C (Center Engine + Outer Ring of $N$ Engines)**:
$$R_{\text{ring}} = D_{\text{footprint}}$$
Maximum engines in outer ring:
$$N_{\text{max}} = \left\lfloor \frac{\pi}{\arcsin(1 / 2)} \right\rfloor = 6$$
For $N > 6$, radius expands:
$$R_{\text{ring}} = \frac{D_{\text{footprint}}}{2 \cdot \sin(\pi / N)}$$
$$D_{\text{req}} = 2 \cdot R_{\text{ring}} + D_{\text{footprint}}$$
- **Pattern D (Multi-Ring Dense Packing - e.g. Super Heavy 33-engine style)**:
  - Inner cluster: 3 center engines.
  - Middle ring: 10 engines.
  - Outer ring: 20 engines.

4. **Interactive Sandbox Overrides**:
The 2D base view visualizer allows users to override automatic coordinate generation:
- Click and drag engines to custom $(x, y)$ positions.
- Adjust per-engine TVC gimbal angles.
- Toggle individual engines on or off.
- The clearance engine dynamically highlights overlapping gimbal cones in red and displays numerical clash margins.

### 10.2 Tank Sizing & Dome Volume Geometry
Tank volumes are sized from required propellant mass, fuel/ox densities, and ullage margins:
$$V_{\text{ox\_req}} = \frac{m_{\text{ox}}}{\rho_{\text{ox}}} \cdot (1 + \text{ullage}_{\text{ox}}), \quad V_{\text{fuel\_req}} = \frac{m_{\text{fuel}}}{\rho_{\text{fuel}}} \cdot (1 + \text{ullage}_{\text{fuel}})$$

Standard Propellant Densities:
- LOX: $1,141\text{ kg/m}^3$ ($71.23\text{ lb/ft}^3$).
- RP-1: $810\text{ kg/m}^3$ ($50.57\text{ lb/ft}^3$).
- LCH4: $422\text{ kg/m}^3$ ($26.34\text{ lb/ft}^3$).
- LH2: $70.85\text{ kg/m}^3$ ($4.42\text{ lb/ft}^3$).

**2:1 Ellipsoidal Dome Geometry**:
For cylinder radius $R = D_{\text{core}} / 2$, height of a 2:1 semi-ellipsoidal dome is $b = R / 2$.
Volume of single 2:1 dome head:
$$V_{\text{dome}} = \frac{2}{3} \cdot \pi \cdot R^2 \cdot b = \frac{\pi \cdot R^3}{3}$$

Total volume of a tank with barrel length $L_{\text{barrel}}$ and two 2:1 domes:
$$V_{\text{tank}} = \pi \cdot R^2 \cdot L_{\text{barrel}} + 2 \cdot V_{\text{dome}}$$
$$L_{\text{barrel}} = \frac{V_{\text{tank}} - 2 \cdot V_{\text{dome}}}{\pi \cdot R^2}$$
Total tank overall axial length:
$$L_{\text{tank\_total}} = L_{\text{barrel}} + 2 \cdot b = L_{\text{barrel}} + R$$

**Common Bulkhead Sizing**:
When common bulkhead is enabled, intermediate dome separates oxidizer and fuel tanks, eliminating one dome length:
$$L_{\text{stage\_tanks}} = L_{\text{barrel, ox}} + L_{\text{barrel, fuel}} + 3 \cdot b$$

## 11. User Interface & Wireframe Specifications

The interface presents five specialized workspaces accessible via a persistent top navigation bar:
1. **Sizing Studio**: Interactive inputs, constraint sliders, 2D base layout, and dimensioned rocket schematic.
2. **Heritage Vehicles**: High-density data grid with sorting, filtering, column manager, and provenance drawer.
3. **Heritage Engines**: Propulsion catalog with cycle filters, thrust/Isp ranges, and technical datasheets.
4. **Scale Lineup**: Multi-rocket visual comparison stage on a shared ground plane with dimension callouts.
5. **Trade & Sensitivity Studio**: 2D/3D trade curves, Pareto frontiers, and multi-format report exports.

### 11.1 Header & Global Bar
- **App Brand**: `RocketSizer` logo and active project title.
- **Unit Toggle Button**: Global switch between `Metric (SI)` and `Imperial (US)`. Changes all inputs, tables, tooltips, and plot axes instantly.
- **Currency Year Picker**: Adjusts all historical cost comparisons (e.g. FY2026$ vs original dollar year).
- **Active Vehicle Summary Pill**: Displays current GLOW, LEO Payload, Cost/Launch, and Feasibility Status (Green Check / Red Warning).

### 11.2 Page 1: Sizing Studio Wireframe
```
+---------------------------------------------------------------------------------------------------+
|  [Mission & Payload Panel]          |  [Dimensioned Rocket Schematic]     |  [Base View & Layout] |
|  - Payload Mass: [ 100,000 ] lbm    |                                     |                       |
|  - Payload Diam: [   22.0  ] ft     |       /\   <-- Fairing              |       ( O ) ( O )     |
|  - Payload Len:  [   60.0  ] ft     |      /  \                           |      ( O ) X ( O )    |
|  - Destination:  [ LEO (28.5 deg) ] |     | PL |  <-- Payload Envelope    |       ( O ) ( O )     |
|  - Required dV:  [  30,500 ] ft/s   |     +----+                          |                       |
|  ---------------------------------- |     | S2 |  <-- Upper Stage         |  [x] TVC Cones        |
|  [Staging Architecture]             |     +====+  <-- Interstage          |  [x] No-Touch Margin  |
|  - Stages: [ 2-Stage + Boosters v ] |     |    |                          |  Usable: 30.2 ft      |
|  - Booster Type: [ Solid (SS_SRB) ] |     |    |  <-- Core Stage          |  Required: 28.6 ft    |
|  - Booster Qty:  [ 2            v ] | [B] | S1 | [B]                      |  Margin: +1.6 ft (OK) |
|  - Core Eng:     [ RS-25        v ] | [B] |    | [B]                      |  -------------------- |
|  - Core Qty:     [ 4            v ] | [B] |Engs| [B]                      |  [Sizing Output]      |
|  - Upper Eng:    [ RL-10A       v ] |                                     |  GLOW: 4,420,000 lbm  |
|  - Upper Qty:    [ 4            v ] |  =================================  |  Dry:    312,000 lbm  |
|  ---------------------------------- |     Ground Plane Elevation Grid     |  Cost:   $142.5M      |
|  [Cost & Weight Optimization Mode]  |                                     |  Cost/kg: $3,140/kg   |
|  [ Min GLOW ] [ Min Cost ] [ Both ] |  [ Mass Treemap ] [ dV Waterfall ]  |  Liftoff T/W: 1.45    |
|  GLOW vs Cost Weight: [====|====]   |  - Propellant: 89.2%                |  Max G: 4.2 g         |
|  Max Cost Cap:  [ $180M   ] / launch|  - Dry Mass:    8.5%                |  Status: FEASIBLE     |
|  Max GLOW Cap:  [ 5.5M lbs]         |  - Payload:     2.3%                |  [ Export Brief ]     |
+---------------------------------------------------------------------------------------------------+
```

### 11.3 Page 2: Heritage Vehicle Tabulation Wireframe
- **Filter Bar**: Text search + multi-select pills (Country, Status, Orbit, Booster Type) + numeric sliders (Payload to LEO $\ge X$, GLOW $\le Y$, Cost $\le Z$).
- **Column Picker**: Checkbox dropdown controlling 50+ columns grouped into categories (Identity, Payload, Dimensions, Staging, Propulsion, Cost).
- **TanStack Virtual Table**: Virtualized table rows supporting sorting on any column, pinned left identification columns (`Name`, `Variant`), and colored badge indicators for data status.
- **Inspector Slide-Over Drawer**:
  - Displays when clicking any table cell.
  - Section A: Verified Document Citation (Title, Author, Year, Page Number, Direct Link, Source Excerpt).
  - Section B: Derivation & Calculation Breakdown (Mathematical formula, parameter substitution, solver reasoning).
  - Section C: Confidence Score and User Correction Submission Form.

### 11.4 Page 3: Heritage Engine Tabulation Wireframe
- High-density grid listing all liquid and solid rocket engines.
- Propellant type filter chips: `All`, `LOX/RP-1`, `LOX/LH2`, `LOX/CH4`, `Solid HTPB`, `Hypergolic`.
- Cycle filter chips: `All`, `Gas Generator`, `Staged Combustion`, `Expander`, `Pressure-Fed`.
- Interactive scatter plot: Vacuum Isp ($y$-axis) versus Thrust-to-Weight ($x$-axis) with bubble size representing vacuum thrust.

### 11.5 Page 4: Visual Scale Lineup Wireframe
- Full-bleed SVG stage with calibrated ground grid (5-meter and 20-foot elevation markers).
- The user's sized rocket is positioned at center stage with a glowing highlight.
- Multi-select checklist allows toggling historical rockets onto the field:
  - *Small Class*: Electron, Vega.
  - *Medium Class*: Soyuz-2, Falcon 9, Delta II, Atlas V 401.
  - *Heavy Class*: Falcon Heavy, Ariane 5, Proton-M, Delta IV Heavy.
  - *Super Heavy Class*: Saturn V, Space Shuttle, SLS Block 1, Starship/Super Heavy, N1.
- Dimension line annotations display height, diameter, and GLOW metrics beneath each rocket silhouette.
- Dark mode engineering blueprint styling or clean presentation mode.

## 12. Rust Core API & Tauri IPC Command Signatures

The communication contract between frontend and numerical engine uses typed Tauri commands:

```rust
#[tauri::command]
pub fn run_combinatorial_sizing(
    request: SizingRequest
) -> Result<SizingSweepResponse, String>;

#[tauri::command]
pub fn evaluate_manual_architecture(
    config: VehicleConfiguration
) -> Result<VehicleSizingResult, String>;

#[tauri::command]
pub fn solve_engine_circle_packing(
    stage_diameter: f64,
    engines: Vec<EnginePlacementInput>,
    constraints: PackingConstraints
) -> Result<BaseLayoutResult, String>;

#[tauri::command]
pub fn compute_cost_model(
    vehicle: VehicleSizingResult,
    parameters: CostModelParameters
) -> Result<VehicleCostBreakdown, String>;

#[tauri::command]
pub fn get_heritage_vehicles() -> Result<Vec<ProvenanceVehicle>, String>;

#[tauri::command]
pub fn get_heritage_engines() -> Result<Vec<ProvenanceEngine>, String>;

#[tauri::command]
pub fn run_sensitivity_sweep(
    baseline: VehicleConfiguration,
    sweep_parameter: String,
    range_min: f64,
    range_max: f64,
    steps: usize
) -> Result<SensitivityCurveResponse, String>;

#[tauri::command]
pub fn scale_rubber_engine(
    reference_engine: ProvenanceEngine,
    target_thrust_vac_n: f64,
    chamber_pressure_override_bar: Option<f64>
) -> Result<ProvenanceEngine, String>;
```

## 13. File Tree & Workspace Structure

```
rocket_sizer/
├── src-tauri/                       # Rust desktop application backend
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── src/
│   │   ├── main.rs                  # Tauri entry point and command registration
│   │   ├── commands/                # Tauri IPC handlers
│   │   │   ├── sizing_commands.rs
│   │   │   ├── database_commands.rs
│   │   │   ├── geometry_commands.rs
│   │   │   ├── propulsion_commands.rs
│   │   │   └── cost_commands.rs
│   │   └── core/                    # Pure numerical aerospace library
│   │       ├── mod.rs
│   │       ├── physics.rs           # Orbital mechanics, delta-V, Earth rotation
│   │       ├── staging.rs           # Multistage rocket equation & mass fractions
│   │       ├── ascent_events.rs     # Fairing jettison, Max-Q, G-throttle clamping
│   │       ├── reusability.rs       # RTLS, ASDS, parachute recovery burns
│   │       ├── structures.rs        # Tank hoop stress, buckling, material presets
│   │       ├── rubber_engine.rs     # Cycle-specific thrust and diameter scaling
│   │       ├── optimizer.rs         # Combinatorial sweep and Pareto ranking
│   │       ├── packaging.rs         # 2D concentric circle-packing solver
│   │       ├── cost_engine.rs       # TRANSCOST / NASA PCEC cost relationships
│   │       ├── models/
│   │       │   ├── vehicle.rs
│   │       │   ├── engine.rs
│   │       │   ├── provenance.rs
│   │       │   └── mission.rs
│   │       └── data/                # In-memory datasets embedded at compile time
│   │           ├── vehicles.json
│   │           └── engines.json
├── src/                             # React 19 / TypeScript frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── config/
│   │   │   └── units.ts             # Unit definitions and conversion tables
│   │   ├── types/                   # TypeScript interfaces matching Rust schemas
│   │   │   ├── vehicle.ts
│   │   │   ├── engine.ts
│   │   │   ├── provenance.ts
│   │   │   └── sizing.ts
│   │   ├── components/
│   │   │   ├── common/              # Buttons, inputs, drawers, modals
│   │   │   ├── layout/              # Header, global unit toggle, nav bar
│   │   │   ├── tables/              # TanStack table grids and filter headers
│   │   │   ├── visualizers/
│   │   │   │   ├── RocketSchematic.tsx   # Dimensioned vector SVG
│   │   │   │   ├── BaseLayoutView.tsx    # 2D engine circle packing view
│   │   │   │   └── ScaleLineup.tsx       # Multi-vehicle scale stage
│   │   │   ├── charts/              # Recharts / Plotly analytics
│   │   │   └── inspector/           # Provenance citation & derivation drawer
│   │   └── views/
│   │       ├── SizingStudioView.tsx
│   │       ├── HeritageVehiclesView.tsx
│   │       ├── HeritageEnginesView.tsx
│   │       ├── ScaleLineupView.tsx
│   │       └── SensitivityStudioView.tsx
├── data/                            # Git-tracked primary JSON datasets
│   ├── vehicles/                    # Individual heritage vehicle records
│   ├── engines/                     # Individual propulsion records
│   └── citations/                   # Reference document bibliography
├── docs/
│   ├── MATHEMATICAL_MODELS.md
│   ├── COST_MODEL_REFERENCE.md
│   └── PROVENANCE_GUIDE.md
├── DESIGN.md                        # Master architectural design document
├── LICENSE                          # MIT License
├── README.md                        # Project summary & user guide
└── SECURITY.md                      # Security vulnerability policy
```

## 14. Verification Matrix & Acceptance Benchmarks

To ensure the sizing algorithms and cost models produce realistic, publication-grade results, the automated test suite checks against historical launch vehicles:

| Test Case | Reference Vehicle | Benchmark Metric | Acceptance Tolerance |
| :--- | :--- | :--- | :--- |
| Staging Mass Fraction | Saturn V (S-IC / S-II / S-IVB) | GLOW: 2,965,000 kg, Payload: 140,000 kg LEO | $\pm 3.5\%$ GLOW |
| Parallel Boost Phase | SLS Block 1 (Core + 2x 5-Seg SRB) | Booster burnout mass & core throttle profile | $\pm 4.0\%$ Mass |
| Modern Reusable Core | Falcon 9 v1.2 (Full Thrust) | GLOW: 549,054 kg, LEO Expendable: 22,800 kg | $\pm 3.0\%$ Payload |
| SmallSat Class | Electron (2-Stage Electric Pump) | GLOW: 13,000 kg, LEO Payload: 300 kg | $\pm 4.5\%$ Mass |
| Engine Circle Packing | Saturn V S-IC (5x F-1) | Diameter: 10.0 m, Pattern: 1 center + 4 outer | Fits within 10.0 m |
| Dense Engine Packing | Super Heavy (33x Raptor) | Diameter: 9.0 m, Pattern: 3 + 10 + 20 rings | Fits within 9.0 m |
| Cost Model Benchmark | Falcon 9 Recurring Launch | Market price \$67M, estimated cost \$28M-\$35M | Within \$5M range |
| Cost Model Benchmark | SLS Block 1 DDT&E | NASA IG reported development spend | Within $\pm 20\%$ |

## 15. Phased Implementation Roadmap

Development proceeds phase-by-phase. Each phase must be committed and verified before the next begins.

- **Phase 1: Rust Core Numerical Engine & Provenance Schemas**
  - Implement `rocket_sizer_core` crate with orbital mechanics, delta-V budget integrator, and multistage mass fraction solver.
  - Implement flight event milestones: atmospheric fairing jettison mass step, Max-Q load relief bucket, and G-limit throttle clamping.
  - Implement multi-mode reusability allocator: RTLS boostback, downrange barge landing (ASDS), and parachute recovery burns.
  - Implement pressure vessel structural models (hoop stress, buckling) with Al-Li, CFRP, and 304L material presets.
  - Implement the "rubber engine" parametric propulsion scaler.
  - Port existing Python logic from `checks.py`, `models.py`, and `sizing.py` into Rust with descriptive unit-suffixed variables.
  - Implement the `TRANSCOST` and `NASA PCEC` parametric cost engine.
  - Implement Serde schemas for `Provenance<T>`, `Citation`, and `Derivation`.
  - Achieve 100% pass rate on the verification benchmark matrix.

- **Phase 2: Tauri v2 Desktop Shell & Heritage Catalog Tabulation**
  - Initialize Tauri v2 application with React 19, TypeScript, Vite, and Tailwind CSS.
  - Integrate TanStack Table v8 with virtualized row scrolling for Vehicles and Engines.
  - Implement column visibility management and multi-criteria filter bars.
  - Build the slide-over Inspector Drawer displaying verified citations, math derivations, and confidence badges.
  - Implement the global zero-latency Metric/Imperial unit conversion system.

- **Phase 3: Sizing Studio & 2D Base Packaging Engine**
  - Implement the combinatorial sizing solver sweeping discrete engine combinations with Pareto ranking.
  - Build the interactive Manual Sandbox UI with real-time sliders and constraint overrides.
  - Implement the 2D concentric circle-packing geometry solver with TVC gimbal envelopes and no-touch gaps.
  - Build the interactive Canvas/SVG base layout editor allowing manual engine coordinate dragging.

- **Phase 4: Dimensioned Visualizer & Scale Lineup Stage**
  - Build the dynamic SVG rocket schematic with dimensions, cutaways, and tank geometries.
  - Implement the full-bleed Scale Lineup stage with calibrated elevation grid and heritage rocket silhouettes.
  - Add auto-matching to pull the closest heritage vehicles by payload or mass.

- **Phase 5: Trade Study Studio, Export Engine & Final Integration**
  - Implement Recharts / Plotly.js trade curves (GLOW vs Payload, Cost vs Payload, Staging dV Split).
  - Implement multi-format export: standalone SVG drawings, high-res PNG, CSV tables, and Markdown/PDF design briefs.
  - Complete git initialization, GitHub repository creation (`DontKwo/rocket_sizer`), branch protection rulesets, and secret scanning setup.
