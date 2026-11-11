from collections.abc import Iterator
from dataclasses import Field, dataclass, field, fields
from datetime import timedelta
from enum import Enum, unique
from typing import Any, Dict, Optional, TYPE_CHECKING

from dcs.forcedoptions import ForcedOptions

from .booleanoption import boolean_option
from .boundedfloatoption import bounded_float_option
from .boundedintoption import bounded_int_option
from .choicesoption import choices_option
from .minutesoption import minutes_option
from .optiondescription import OptionDescription, SETTING_DESCRIPTION_KEY
from .skilloption import skill_option
from ..ato.starttype import StartType
from ..opening import Surprise
from ..warfare.collateral import RoeSetting

if TYPE_CHECKING:
    from ..ato.flighttype import FlightType

Views = ForcedOptions.Views


@unique
class AutoAtoBehavior(Enum):
    Disabled = "Disabled"
    Never = "Never assign player pilots"
    Default = "No preference"
    Prefer = "Prefer player pilots"
    #: The commander flies the routine lines (CAP, AWACS, tankers, ground
    #: alert); the player plans the rest by hand (P7).
    RoutineOnly = "Commander flies routine lines, you plan the rest"


@unique
class PlannerEngine(Enum):
    """Which air campaign planner a side uses."""

    AUTO = "By faction doctrine"
    DOCTRINE = "Doctrine-driven air campaign (JFACC)"
    LEGACY = "Legacy priority planner"


@unique
class NightMissions(Enum):
    DayAndNight = "nightmissions_nightandday"
    OnlyDay = "nightmissions_onlyday"
    OnlyNight = "nightmissions_onlynight"


@unique
class FastForwardStopCondition(Enum):
    DISABLED = "Fast forward disabled"
    FIRST_CONTACT = "First contact"
    PLAYER_TAKEOFF = "Player takeoff time"
    PLAYER_TAXI = "Player taxi time"
    PLAYER_STARTUP = "Player startup time"
    PLAYER_AT_IP = "Player at IP"
    MANUAL = "Manual fast forward control"
    END_OF_TURN = "Simulate entire turn"


@unique
class CombatResolutionMethod(Enum):
    PAUSE = "Pause simulation"
    RESOLVE = "Resolve combat"
    SKIP = "Skip combat"


@unique
class FogOfWar(Enum):
    OFF = "Off"
    SOFT = "Soft"
    STRICT = "Strict"


@unique
class DefaultPlayerLaserCode(Enum):
    DEFAULT_1688 = "Default (1688)"
    ALLOCATE_OWN = "Allocate own (unique per flight)"


DIFFICULTY_PAGE = "Difficulty"

AI_DIFFICULTY_SECTION = "AI Difficulty"
MISSION_DIFFICULTY_SECTION = "Mission Difficulty"
MISSION_RESTRICTIONS_SECTION = "Mission Restrictions"

CAMPAIGN_MANAGEMENT_PAGE = "Campaign Management"

GENERAL_SECTION = "General"
PILOTS_AND_SQUADRONS_SECTION = "Pilots and Squadrons"
HQ_AUTOMATION_SECTION = "HQ Automation"
FLIGHT_PLANNER_AUTOMATION = "Flight Planner Automation"
DYNAMIC_FARPS_SECTION = "Dynamic FARPs"

CAMPAIGN_DOCTRINE_PAGE = "Campaign Doctrine"
DOCTRINE_DISTANCES_SECTION = "Doctrine distances"
WARFARE_SECTION = "Intelligence, morale and electronic warfare"

PRETENSE_PAGE = "Pretense"

MISSION_GENERATOR_PAGE = "Mission Generator"

GAMEPLAY_SECTION = "Gameplay"

# TODO: Make sections a type and add headers.
# This section had the header: "Disabling settings below may improve performance, but
# will impact the overall quality of the experience."
PERFORMANCE_SECTION = "Performance"


@dataclass
class Settings:
    version: Optional[str] = None

    # Difficulty settings
    # AI Difficulty
    player_skill: str = skill_option(
        "Player coalition skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
    )
    enemy_skill: str = skill_option(
        "Enemy coalition skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
    )
    enemy_vehicle_skill: str = skill_option(
        "Enemy AA and vehicles skill",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        default="High",
    )
    player_income_multiplier: float = bounded_float_option(
        "Player income multiplier",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.0,
    )
    enemy_income_multiplier: float = bounded_float_option(
        "Enemy income multiplier",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        min=0,
        max=5,
        divisor=10,
        default=1.0,
    )
    invulnerable_player_pilots: bool = boolean_option(
        "Player pilots cannot be killed",
        page=DIFFICULTY_PAGE,
        section=AI_DIFFICULTY_SECTION,
        detail=(
            "Aircraft are vulnerable, but the player's pilot will be returned to the "
            "squadron at the end of the mission"
        ),
        default=True,
    )
    # Mission Difficulty
    manpads: bool = boolean_option(
        "Manpads on frontlines",
        page=DIFFICULTY_PAGE,
        section=MISSION_DIFFICULTY_SECTION,
        default=True,
    )
    night_day_missions: NightMissions = choices_option(
        "Night/day mission options",
        page=DIFFICULTY_PAGE,
        section=MISSION_DIFFICULTY_SECTION,
        choices={
            "Generate night and day missions": NightMissions.DayAndNight,
            "Only generate day missions": NightMissions.OnlyDay,
            "Only generate night missions": NightMissions.OnlyNight,
        },
        default=NightMissions.DayAndNight,
    )
    # Mission Restrictions
    labels: str = choices_option(
        "In game labels",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices=["Full", "Abbreviated", "Dot Only", "Neutral Dot", "Off"],
        default="Full",
    )
    map_coalition_visibility: Views = choices_option(
        "Map visibility options",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={
            "All": Views.All,
            "Fog of war": Views.Allies,
            "Allies only": Views.OnlyAllies,
            "Own aircraft only": Views.MyAircraft,
            "Map only": Views.OnlyMap,
        },
        default=Views.All,
    )
    external_views_allowed: bool = boolean_option(
        "Allow external views",
        DIFFICULTY_PAGE,
        MISSION_RESTRICTIONS_SECTION,
        default=True,
    )

    easy_communication: Optional[bool] = choices_option(
        "Easy Communication",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={"Player preference": None, "Enforced on": True, "Enforced off": False},
        default=None,
    )

    battle_damage_assessment: Optional[bool] = choices_option(
        "Battle damage assessment",
        page=DIFFICULTY_PAGE,
        section=MISSION_RESTRICTIONS_SECTION,
        choices={"Player preference": None, "Enforced on": True, "Enforced off": False},
        default=None,
    )

    # CAMPAIGN DOCTRINE
    desired_barcap_mission_duration: timedelta = minutes_option(
        "Desired BARCAP on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
        detail="Implicitly determines the number of BARCAPs planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    desired_awacs_mission_duration: timedelta = minutes_option(
        "Desired AWACS on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=120),
        min=60,
        max=300,
        detail="Implicitly determines the number of AWACS flights planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    desired_tanker_on_station_time: timedelta = minutes_option(
        "Desired tanker on-station time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
        detail="Implicitly determines the number of Tanker flights planned by taking the mission duration"
        " and dividing it by the desired on-station time.",
    )
    autoplan_tankers_for_strike: bool = boolean_option(
        "Auto-planner plans refueling flights for Strike packages",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        invert=False,
        detail=(
            "If checked, the auto-planner will include tankers in Strike packages, "
            "provided the faction has access to them."
        ),
    )
    autoplan_tankers_for_oca: bool = boolean_option(
        "Auto-planner plans refueling flights for OCA packages",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        invert=False,
        detail=(
            "If checked, the auto-planner will include tankers in OCA packages, "
            "provided the faction has access to them."
        ),
    )
    autoplan_tankers_for_dead: bool = boolean_option(
        "Auto-planner plans refueling flights for DEAD packages",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        invert=False,
        detail=(
            "If checked, the auto-planner will include tankers in DEAD packages, "
            "provided the faction has access to them."
        ),
    )
    aircraft_per_recovery_tanker: int = bounded_int_option(
        "Number of aircraft per recovery tanker",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=4,
        min=2,
        max=12,
        detail=(
            "A higher number will force the autoplanner to generate less recovery tankers."
        ),
    )
    oca_target_autoplanner_min_aircraft_count: int = bounded_int_option(
        "Minimum number of aircraft (at vulnerable airfields) for auto-planner to plan OCA packages against",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "How many aircraft there has to be at an airfield for "
            "the auto-planner to plan an OCA strike against it."
        ),
    )
    ownfor_autoplanner_aggressiveness: int = bounded_int_option(
        "OWNFOR auto-planner aggressiveness (%)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "Ratio of the threat-radius that will be ignored by the OWNFOR "
            "AI-autoplanner. 0% means the entire threat-radius is considered, "
            "while 100% would have the autoplanner completely ignore OPFOR air defences."
        ),
    )
    opfor_autoplanner_aggressiveness: int = bounded_int_option(
        "OPFOR auto-planner aggressiveness (%)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=20,
        min=0,
        max=100,
        detail=(
            "Ratio of the threat-radius that will be ignored by the OPFOR "
            "AI-autoplanner. 0% means the entire threat-radius is considered, "
            "while 100% would have the autoplanner completely ignore OWNFOR air defences."
        ),
    )
    heli_combat_alt_agl: int = bounded_int_option(
        "Helicopter combat altitude (feet AGL)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=200,
        min=1,
        max=10000,
        detail=(
            "Altitude for helicopters in feet AGL while flying between combat waypoints."
            " Combat waypoints are considered INGRESS, CAS, TGT, EGRESS & SPLIT."
            " In campaigns in more mountainous areas, you might want to increase this "
            "setting to avoid the AI flying into the terrain."
        ),
    )
    heli_cruise_alt_agl: int = bounded_int_option(
        "Helicopter cruise altitude (feet AGL)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=500,
        min=1,
        max=10000,
        detail=(
            "Altitude for helicopters in feet AGL while flying between non-combat waypoints."
            " In campaigns in more mountainous areas, you might want to increase this "
            "setting to avoid the AI flying into the terrain."
        ),
    )
    atflir_autoswap: bool = boolean_option(
        "Auto-swap ATFLIR to LITENING",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "Automatically swaps ATFLIR to LITENING pod for newly generated land-based F/A-18 flights "
            "without having to change the payload. <u>Takes effect after current turn!</u>"
        ),
    )
    ai_jettison_empty_tanks: bool = boolean_option(
        "Enable AI empty fuel tank jettison",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail="AI will jettison their fuel tanks as soon as they're empty.",
    )
    ai_avoid_gun_runs_in_defended_areas: bool = boolean_option(
        "AI avoids gun runs on defended targets",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "When the target of an AI strike, BAI, CAS, armed recon or OCA/Aircraft "
            "flight is covered by enemy SAMs or AAA, the AI has its bullets removed "
            "and heads home once its air-to-ground ordnance (missiles, bombs and "
            "rockets) is spent, instead of pressing home low altitude gun runs. BAI "
            "flights make a single attack and egress. Helicopters and flights with "
            "players keep their guns."
        ),
    )
    ai_vertical_takoff_landing: bool = boolean_option(
        "AI helicopters use vertical takeoff and landing",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail="AI will use vertical takeoff and landing instead of combat takeoff and landing.",
    )
    max_csar_flights: int = bounded_int_option(
        "Maximum CSAR flights planned per side each turn",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=2,
        min=0,
        max=10,
        detail=(
            "Maximum number of CSAR rescue packages the auto-planner will commit to in a "
            "turn, for each coalition."
        ),
    )
    max_plane_altitude_offset: int = bounded_int_option(
        "Maximum randomized altitude offset (x1000 ft) for airplanes.",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        min=0,
        max=5,
        default=2,
        detail="Creates a randomized altitude offset for airplanes.",
    )

    player_startup_time: int = bounded_int_option(
        "Player startup time",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=GENERAL_SECTION,
        default=10,
        min=0,
        max=100,
        detail=(
            "The startup time allocated to player flights (default : 10 minutes, AI is 2 minutes). "
            "Packages have to be planned again for this to take effect. "
        ),
    )

    # Doctrine Distances Section
    airbase_threat_range: int = bounded_int_option(
        "Airbase threat range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=100,
        min=0,
        max=300,
        detail=(
            "Will impact both defensive (BARCAP) and offensive flights. Also has a performance impact, "
            "lower threat range generally means less BARCAPs are planned."
        ),
    )
    max_threat_range: int = bounded_int_option(
        "Maxiumum threat range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=200,
        min=60,
        max=500,
        detail=(
            "Provides an upper limit to threat-ranges to avoid partial nav-meshes, which leads to errors. "
            "Lower this setting further if the map's bounds aren't covered by the nav-mesh."
        ),
    )
    cas_engagement_range_distance: int = bounded_int_option(
        "CAS engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=10,
        min=0,
        max=100,
    )
    armed_recon_engagement_range_distance: int = bounded_int_option(
        "Armed Recon engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=5,
        min=0,
        max=25,
    )
    sead_sweep_engagement_range_distance: int = bounded_int_option(
        "SEAD Sweep engagement range (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=30,
        min=0,
        max=100,
    )
    sead_threat_buffer_min_distance: int = bounded_int_option(
        "SEAD Escort/Sweep threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=5,
        min=0,
        max=100,
        detail=(
            "How close to known threats will the SEAD Escort / SEAD Sweep engagement zone extend."
        ),
    )
    tarcap_threat_buffer_min_distance: int = bounded_int_option(
        "TARCAP threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=20,
        min=0,
        max=100,
        detail=("How close to known threats will the TARCAP racetrack extend."),
    )
    aewc_threat_buffer_min_distance: int = bounded_int_option(
        "AEW&C threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=80,
        min=0,
        max=300,
        detail=(
            "How far, at minimum, will AEW&C racetracks be planned "
            "to known threat zones."
        ),
    )
    tanker_threat_buffer_min_distance: int = bounded_int_option(
        "Theater tanker threat buffer distance (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=70,
        min=0,
        max=300,
        detail=(
            "How far, at minimum, will theater tanker racetracks be "
            "planned to known threat zones."
        ),
    )
    max_mission_range_planes: int = bounded_int_option(
        "Auto-planner maximum mission range for airplanes (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=150,
        min=150,
        max=1000,
        detail=(
            "The maximum mission distance that's used by the auto-planner for airplanes. "
            "This setting won't take effect when a larger "
            "range is defined in the airplane's yaml specification."
        ),
    )
    max_mission_range_helicopters: int = bounded_int_option(
        "Auto-planner maximum mission range for helicopters (NM)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=DOCTRINE_DISTANCES_SECTION,
        default=100,
        min=50,
        max=1000,
        detail=(
            "The maximum mission distance that's used by the auto-planner for helicopters. "
            "This setting won't take effect when a larger "
            "range is defined in the helicopter's yaml specification."
        ),
    )

    # Campaign management
    # General
    squadron_random_chance: int = bounded_int_option(
        "Percentage of randomly selected aircraft types (only for generated squadrons)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=50,
        min=0,
        max=100,
        detail=(
            "Aircraft type selection is governed by the campaign and the squadron definitions available to "
            "Retribution. Squadrons are generated by Retribution if the faction does not have access to the campaign "
            "designer's squadron/aircraft definitions. Use the above to increase/decrease aircraft variety by making "
            "some selections random instead of picking aircraft types from a priority list."
        ),
    )
    restrict_weapons_by_date: bool = boolean_option(
        "Restrict weapons by date (WIP)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Restricts weapon availability based on the campaign date. Data is "
            "extremely incomplete so does not affect all weapons."
        ),
    )
    restrict_props_by_date: bool = boolean_option(
        "Restrict aircraft options by date (WIP)",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "Restricts era-defining aircraft mission options (e.g. the JHMCS helmet "
            "cueing selection) based on the campaign date: gated options are hidden "
            "from the payload editor and clamped to a period-correct value at "
            "mission generation. Independent of the weapons restriction so either "
            "can be enforced alone. Data is curated per airframe and incomplete."
        ),
    )
    motorpool_enabled: bool = boolean_option(
        "Spawn strikeable motorpool reserves",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "Render each control point's not-yet-deployed reserve armor as a "
            "strikeable motorpool (only where the campaign authored one). "
            "Destroying reserves forces the owner to repurchase."
        ),
    )
    motorpool_spawn_cap: int = bounded_int_option(
        "Maximum motorpool vehicles per turn",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=10,
        min=0,
        max=25,
        detail=(
            "Caps how many reserve vehicles a control point renders across its "
            "motorpool(s) per turn. Lower this if motorpools hurt mission "
            "performance."
        ),
    )
    apply_target_overrides_to_loadouts: bool = boolean_option(
        "Apply target-based weapon settings to player loadouts",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "When enabled, applies target-specific weapon settings from weapon "
            "configurations to player-controlled aircraft. AI aircraft always receive "
            "target-based settings. This includes settings for degraded loadouts."
        ),
    )
    prefer_squadrons_with_matching_primary_task: bool = boolean_option(
        "Prefer squadrons with matching primary task when planning missions",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=(
            "If checked, squadrons with a primary task matching the mission will be "
            "preferred even if there is a closer squadron capable of the mission as a "
            "secondary task. Expect longer flights, but squadrons will be more often "
            "assigned to their primary task."
        ),
    )
    use_bandit_clouds: bool = boolean_option(
        "Use Bandit's clouds",
        page=CAMPAIGN_MANAGEMENT_PAGE,
        section=GENERAL_SECTION,
        default=False,
        detail=("If checked, Bandit's cloud presets will become available."),
    )

    # Pilots and Squadrons
    ai_pilot_levelling: bool = boolean_option(
        "Allow AI pilot leveling",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail=(
            "Set whether or not AI pilots will level up after completing a number of"
            " sorties. Since pilot level affects the AI skill, you may wish to disable"
            " this, lest you face an Ace!"
        ),
    )
    #: Feature flag for squadron limits.
    enable_squadron_pilot_limits: bool = boolean_option(
        "Enable per-squadron pilot limits",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail=(
            "If set, squadrons will be limited to a maximum number of pilots and dead "
            "pilots will replenish at a fixed rate, each defined with the settings "
            "below. Auto-purchase may buy aircraft for which there are no pilots"
            "available, so this feature is still a work-in-progress."
        ),
    )
    #: The maximum number of pilots a squadron can have at one time. Changing this after
    #: the campaign has started will have no immediate effect; pilots already in the
    #: squadron will not be removed if the limit is lowered and pilots will not be
    #: immediately created if the limit is raised.
    squadron_pilot_limit: int = bounded_int_option(
        "Maximum number of pilots per squadron",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=16,
        min=6,
        max=72,
        detail=(
            "Sets the maximum number of pilots a squadron may have active. "
            "Changing this value will not have an immediate effect, but will alter "
            "replenishment for future turns."
        ),
    )
    #: The number of pilots a squadron can replace per turn.
    squadron_replenishment_rate: int = bounded_int_option(
        "Squadron pilot replenishment rate",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=4,
        min=1,
        max=20,
        detail=(
            "Sets the maximum number of pilots that will be recruited to each squadron "
            "at the end of each turn. Squadrons will not recruit new pilots beyond the "
            "pilot limit, but each squadron with room for more pilots will recruit "
            "this many pilots each turn up to the limit."
        ),
    )
    # Feature flag for squadron limits.
    enable_squadron_aircraft_limits: bool = boolean_option(
        "Enable per-squadron aircraft limits",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=False,
        detail=(
            "If set, squadrons will not be able to buy more aircraft than the configured maximum."
        ),
    )
    # Combat Search and Rescue
    csar_enabled: bool = boolean_option(
        "Enable CSAR for the player coalition",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail="Enable CSAR rescue flights for OWNFOR (BLUE) Coalition.",
    )
    csar_enabled_red: bool = boolean_option(
        "Enable CSAR for the enemy coalition",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=True,
        detail="Enable CSAR rescue flights for OPFOR (RED) Coalition.",
    )
    csar_ejection_chance: int = bounded_int_option(
        "CSAR pilot survival chance (%)",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=40,
        min=0,
        max=100,
        detail=(
            "Chance of pilot survival and becoming a downed pilot for aircraft losses "
            "where DCS did not report an ejection (AI kills and all losses on skipped/simulated turns)."
            "Real in-mission ejections always produce a downed pilot."
        ),
    )
    csar_control_point_radius: int = bounded_int_option(
        "Control point radius resolving a downed pilot (nm)",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=15,
        min=0,
        max=100,
        detail=(
            "A pilot who comes down this close to a control point does not need a "
            "rescue flight: inside a friendly one they make their own way back and "
            "go straight into recovery, inside an enemy one they are captured and "
            "go missing in action. Only pilots outside every control point's radius "
            "become downed pilots on the map. Set to 0 to always require a rescue."
        ),
    )
    csar_capture_radius: int = bounded_int_option(
        "Capture radius for unrescued pilots (nm)",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=30,
        min=0,
        max=200,
        detail=(
            "A pilot whose survival turns run out is taken prisoner only if they "
            "are in enemy territory and this close to the enemy base that finds "
            "them. Anyone further out is simply missing in action -- nobody "
            "reached them either way. Prisoners come home if their base is "
            "captured; the missing do not. Set to 0 so an unrescued pilot is "
            "always missing rather than captured. "
            "Kept separate from the landing radius above, which resolves a pilot "
            "the moment they come down: anyone still on the map is by definition "
            "outside it, so reusing it here would mean no one is ever captured."
        ),
    )
    csar_cluster_radius: int = bounded_int_option(
        "Collect downed pilots within (m) on one flight",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=1000,
        min=0,
        max=5000,
        detail=(
            "Downed pilots this close together are collected by a single AI rescue "
            "flight rather than one flight each: the survivors walk to the same "
            "landing zone, or are hoisted on the same hover. Only affects the "
            "auto-planner -- a package planned by hand still targets one pilot. Set "
            "to 0 to plan a separate flight for every pilot."
        ),
    )
    csar_survival_turns: int = bounded_int_option(
        "Turns a downed pilot survives",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=3,
        min=1,
        max=10,
        detail=(
            "Number of turns a downed pilot in friendly rear territory waits for "
            "rescue before going missing in action."
        ),
    )
    csar_survival_turns_hostile: int = bounded_int_option(
        "Turns a downed pilot survives near the front",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=2,
        min=1,
        max=10,
        detail=(
            "Number of turns a downed pilot in hostile territory or close to a front "
            "line, where enemy ground forces are more likely to capture them waits for "
            "rescue before going missing in action."
        ),
    )
    csar_ai_recovery_turns: int = bounded_int_option(
        "Turns a rescued AI pilot recovers",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=2,
        min=0,
        max=10,
        detail=(
            "Number of turns a rescued AI pilot is unavailable (recovering) before "
            "returning to active duty."
        ),
    )
    csar_player_recovery_turns: int = bounded_int_option(
        "Turns a rescued player pilot recovers",
        CAMPAIGN_MANAGEMENT_PAGE,
        PILOTS_AND_SQUADRONS_SECTION,
        default=1,
        min=0,
        max=10,
        detail=(
            "Number of turns a rescued human pilot is unavailable (recovering) before "
            "returning to active duty."
        ),
    )

    # Dynamic FARPs
    enable_dynamic_farps: bool = boolean_option(
        "Enable player-established FARPs",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=False,
        detail=(
            "Allows the player to establish FARPs in friendly territory near the "
            "front line and station helicopter detachments at them. A Wet Wing FARP "
            "(set up by a C-130) holds more helicopters; a Fat Cow FARP (set up by a "
            "CH-47) holds 2 and is cheaper."
        ),
    )
    wet_wing_farp_deploy_cost: int = bounded_int_option(
        "Wet Wing FARP deployment cost",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=250,
        min=0,
        max=2000,
    )
    wet_wing_farp_upkeep: int = bounded_int_option(
        "Wet Wing FARP upkeep per turn",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=25,
        min=0,
        max=500,
    )
    wet_wing_farp_capacity: int = bounded_int_option(
        "Wet Wing FARP helicopter capacity",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=4,
        min=1,
        max=12,
    )
    fat_cow_farp_deploy_cost: int = bounded_int_option(
        "Fat Cow FARP deployment cost",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=150,
        min=0,
        max=2000,
    )
    fat_cow_farp_upkeep: int = bounded_int_option(
        "Fat Cow FARP upkeep per turn",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=15,
        min=0,
        max=500,
    )
    max_farps: int = bounded_int_option(
        "Maximum number of FARPs",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=4,
        min=0,
        max=15,
        detail="Wet Wing and Fat Cow FARPs together.",
    )
    farp_min_frontline_distance: int = bounded_int_option(
        "FARP minimum distance from front (nm)",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=3,
        min=0,
        max=30,
    )
    farp_max_frontline_distance: int = bounded_int_option(
        "FARP maximum distance from front (nm)",
        CAMPAIGN_MANAGEMENT_PAGE,
        DYNAMIC_FARPS_SECTION,
        default=20,
        min=0,
        max=60,
        detail="0 means no limit: FARPs can be built any distance from the front.",
    )

    # HQ Automation
    automate_runway_repair: bool = boolean_option(
        "Automate runway repairs",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    automate_front_line_reinforcements: bool = boolean_option(
        "Automate front-line purchases",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    automate_aircraft_reinforcements: bool = boolean_option(
        "Automate aircraft purchases",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    auto_ato_behavior: AutoAtoBehavior = choices_option(
        "Automatic package planning behavior",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=AutoAtoBehavior.Default,
        choices={v.value: v for v in AutoAtoBehavior},
        detail=(
            "No preference: the commander plans everything and frags you one "
            "flight from the plan, by your preference (the Your flight card). "
            "Prefer player pilots: players are spread over many flights, as "
            "before. Never: nobody is fragged. Commander flies routine lines: "
            "CAP, AWACS, tankers and ground alert are planned for you and you "
            "plan the strikes yourself. Disabled: nothing is planned. Aircraft "
            "auto-purchase is directed by the auto-planner, so disabling "
            "auto-planning disables auto-purchase."
        ),
    )
    auto_ato_behavior_awacs: bool = boolean_option(
        "Automatic AWACS package planning",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    auto_ato_behavior_tankers: bool = boolean_option(
        "Automatic Theater tanker package planning",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
    )
    auto_ato_player_missions_asap: bool = boolean_option(
        "Automatically generated packages with players are scheduled ASAP",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    automate_front_line_stance: bool = boolean_option(
        "Automatically manage front line stances",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
    )
    planner_engine_blue: PlannerEngine = choices_option(
        "Air campaign planner (OWNFOR)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=PlannerEngine.AUTO,
        choices={v.value: v for v in PlannerEngine},
        detail=(
            "The doctrine-driven planner plans each turn as a 6 hour air tasking "
            "order: campaign phases, a prioritized target list with battle damage "
            "assessment, sortie apportionment and threat-scaled packages. By "
            "faction doctrine, Western factions use it and others use the legacy "
            "planner."
        ),
    )
    planner_engine_red: PlannerEngine = choices_option(
        "Air campaign planner (OPFOR)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=PlannerEngine.AUTO,
        choices={v.value: v for v in PlannerEngine},
    )
    focused_turns: bool = boolean_option(
        "Mission only (plan one mission instead of the 6 hour turn)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=False,
        detail=(
            "Doctrine-driven planner only. Off (the default): each turn is a "
            "full 6 hour air war for both sides. The commander plans routine "
            "lines, strike waves and a main push; you fly a window of it in DCS "
            "and the combat model fights the rest. On: the turn plans only one "
            "mission (the desired mission duration plus a short lead-in), with "
            "every time on target inside it and nothing flying between "
            "missions. Turns advance 6 hours either way. A change applies from "
            "the next turn. The mission only model gets no new features."
        ),
    )
    bubble_enabled: bool = boolean_option(
        "Full turn: only what you'd meet is in DCS (the bubble)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=True,
        detail=(
            "Full turns with a player flight. On (the default): the DCS mission "
            "holds your package, your tanker and AWACS, the SEAD on your route, "
            "pinned packages, and the packages of both sides you are likely to "
            "meet; the combat model fights the rest over the same time. Off: "
            "every package flying during the mission is in DCS."
        ),
    )
    bubble_package_target: int = bounded_int_option(
        "Full turn: packages per side in DCS (guidance)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=10,
        min=2,
        max=60,
        detail=(
            "With the bubble on: roughly how many packages of each side, besides "
            "the ones always in (yours, your tanker and AWACS, your SEAD "
            "corridor, pinned), go into the DCS mission, the most likely to meet "
            "you first. A CAP and the raid it would fight go in together, so a "
            "side can go past it."
        ),
    )
    focused_lead_in_min: int = bounded_int_option(
        "Mission only: lead-in (minutes)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=30,
        min=0,
        max=90,
        detail=(
            "Mission only model. How long before the mission starts flights may "
            "take off. Their flight up to mission start is fought by the combat "
            "model, and they appear in the mission where they are by then."
        ),
    )
    focused_package_target: int = bounded_int_option(
        "Mission only: packages per side (guidance)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=10,
        min=4,
        max=40,
        detail=(
            "Mission only model. Roughly how many packages each side plans per "
            "turn. Once a side reaches it, the planner stops adding further "
            "strike, interdiction, SEAD and CAS packages. Personnel recovery, "
            "AEW&C, tankers, CAPs, ground alerts and raids can still take a side "
            "past it."
        ),
    )
    ato_period_hours: int = bounded_int_option(
        "Air tasking order period (hours)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=6,
        min=1,
        max=6,
        detail=(
            "Doctrine-driven planner with mission only off. Each turn plans this "
            "many hours of air operations. The DCS mission covers a window of it "
            "(chosen before take off); everything outside that window is resolved "
            "by the combat model."
        ),
    )
    jfacc_attrition_limit_override: int = bounded_int_option(
        "Acceptable attrition per sortie override (%, 0 = doctrine)",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        default=0,
        min=0,
        max=20,
        detail=(
            "Doctrine-driven planner only. Packages whose estimated losses per "
            "sortie exceed this are scrubbed. 0 uses the doctrine's limits "
            "(2% for Western doctrine, more for troops in contact)."
        ),
    )
    auto_procurement_balance: int = bounded_int_option(
        "AI ground unit procurement budget ratio (%) for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=100,
        default=50,
        detail=(
            "Ratio (larger number -> more budget for ground units) "
            "that indicates how the AI procurement planner should "
            "spend its budget."
        ),
    )
    frontline_reserves_factor: int = bounded_int_option(
        "AI ground unit front-line reserves factor (%) for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=130,
        detail=(
            "Factor to be multiplied with the control point's unit count limit "
            "to calculate the procurement target for reserve troops at front-lines."
        ),
    )
    reserves_procurement_target: int = bounded_int_option(
        "AI ground unit reserves procurement target for OWNFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=10,
        detail=(
            "The number of units that will be bought as reserves for applicable control points."
        ),
    )
    auto_procurement_balance_red: int = bounded_int_option(
        "AI ground unit procurement budget ratio (%) for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=100,
        default=50,
        detail=(
            "Ratio (larger number -> more budget for ground units) "
            "that indicates how the AI procurement planner should "
            "spend its budget."
        ),
    )
    frontline_reserves_factor_red: int = bounded_int_option(
        "AI ground unit front-line reserves factor (%) for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=130,
        detail=(
            "Factor to be multiplied with the control point's unit count limit "
            "to calculate the procurement target for reserve troops at front-lines."
        ),
    )
    reserves_procurement_target_red: int = bounded_int_option(
        "AI ground unit reserves procurement target for OPFOR",
        CAMPAIGN_MANAGEMENT_PAGE,
        HQ_AUTOMATION_SECTION,
        min=0,
        max=1000,
        default=10,
        detail=(
            "The number of units that will be bought as reserves for applicable control points."
        ),
    )

    # Flight Planner Automation
    #: The weight used for 2-ships.
    fpa_2ship_weight: int = bounded_int_option(
        "2-ship weight factor (WF2)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=50,
        min=0,
        max=100,
        detail=(
            "Used as a distribution to randomize 2/3/4-ships for BARCAP, CAS, OCA & ANTI-SHIP flights. "
            "The weight W_i is calculated according to the following formula: &#10;&#13;"
            "W_i = WF_i / (WF2 + WF3 + WF4)"
        ),
    )
    #: The weight used for 3-ships.
    fpa_3ship_weight: int = bounded_int_option(
        "3-ship weight factor (WF3)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=35,
        min=0,
        max=100,
        detail="See 2-ship weight factor (WF3)",
    )
    fpa_4ship_weight: int = bounded_int_option(
        "4-ship weight factor (WF4)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=15,
        min=0,
        max=100,
        detail="See 2-ship weight factor (WF4)",
    )
    primary_task_distance_factor: int = bounded_int_option(
        "Primary task distance weight (NM)",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=75,
        min=10,
        max=250,
        detail="A larger number will force the auto-planner to stick with squadrons that have a matching primary task."
        " A smaller number will ignore squadrons with a matching primary task that are too far out.",
    )
    csar_single_flight: bool = boolean_option(
        "Enable single flight CSAR",
        CAMPAIGN_MANAGEMENT_PAGE,
        FLIGHT_PLANNER_AUTOMATION,
        default=False,
        detail=(
            "Plans rescue packages with one helicopter instead of a pair. Cheaper "
            "in airframes and pilots, at the cost of having no wingman to cover the "
            "pickup or take over if the lead is lost. The weight factors above do "
            "not apply to CSAR either way."
        ),
    )

    # Mission Generator
    # Gameplay
    fast_forward_stop_condition: FastForwardStopCondition = choices_option(
        "Fast forward until",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=FastForwardStopCondition.PLAYER_STARTUP,
        choices={
            "No fast forward": FastForwardStopCondition.DISABLED,
            "Player startup time": FastForwardStopCondition.PLAYER_STARTUP,
            "Player taxi time": FastForwardStopCondition.PLAYER_TAXI,
            "Player takeoff time": FastForwardStopCondition.PLAYER_TAKEOFF,
            "Player at IP": FastForwardStopCondition.PLAYER_AT_IP,
            "First contact": FastForwardStopCondition.FIRST_CONTACT,
            "Manual": FastForwardStopCondition.MANUAL,
            "Simulate entire turn (no DCS)": FastForwardStopCondition.END_OF_TURN,
        },
        detail=(
            "Determines when fast forwarding stops: "
            "No fast forward: disables fast forward. "
            "Player startup time: fast forward until player startup time. "
            "Player taxi time: fast forward until player taxi time. "
            "Player takeoff time: fast forward until player takeoff time. "
            "First contact: fast forward until first contact between blue and red units. "
            "Manual: manually control fast forward. Show manual controls with --show-sim-speed-controls. "
            "Simulate entire turn: the whole turn is fought by the combat model without launching "
            "DCS, including player flights, and the results are presented for acceptance."
        ),
    )
    combat_resolution_method: CombatResolutionMethod = choices_option(
        "Resolve combat when fast forwarding by",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=CombatResolutionMethod.PAUSE,
        choices={
            "Pause": CombatResolutionMethod.PAUSE,
            "Resolve combat (combat model)": CombatResolutionMethod.RESOLVE,
            "Skipping combat": CombatResolutionMethod.SKIP,
        },
        detail=(
            "Determines what happens when combat occurs when fast forwarding. "
            "Pause: pause fast forward and generate mission. Fast forwarding may stop before the condition specified in the above setting. "
            "Resolve combat: fight it out with the combat model. Air combat, air defenses, strikes and "
            "front-line battles are simulated from the units, weapons, sensors, pilot skill, tactics "
            "and weather involved. Losses and damage carry into the generated mission. "
            "Skipping combat: skip combat as if it did not occur."
        ),
    )
    combat_model_lethality: float = bounded_float_option(
        "Combat model lethality",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        min=0.25,
        max=2.0,
        divisor=100,
        default=1.0,
        detail=(
            "Scales the kill probability of every weapon in the fast-forward combat "
            "model. 1.0 is calibrated against historical performance."
        ),
    )
    combat_model_force_quality: bool = boolean_option(
        "Historical force quality in the combat model",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Training, readiness, air defense integration and doctrine differ by "
            "faction (e.g. NATO vs. Iraq 1991), as they did historically. The skill "
            "settings still apply on top as a difficulty adjustment. When off, all "
            "factions are equally capable and only equipment differs."
        ),
    )
    combat_model_ground_war: bool = boolean_option(
        "Simulate front-line battles while fast forwarding",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=True,
        detail=(
            "When resolving combat, front-line ground forces fight during fast "
            "forward. Their losses carry into the mission and move the front line."
        ),
    )
    combat_model_ground_interval: int = bounded_int_option(
        "Front-line battle round length (minutes)",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        min=2,
        max=30,
        default=10,
    )
    intel_enabled: bool = boolean_option(
        "Intelligence: sides only know what they have detected",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        causes_expensive_game_update=True,
        detail=(
            "Each side builds a picture of the enemy from pre-war intelligence, early "
            "warning radars, AWACS, sightings, engagements, strike reports and "
            "reconnaissance. The AI plans only against what it knows, unknown SAM "
            "sites achieve surprise, and battle damage assessment can be wrong."
        ),
    )
    fog_of_war: FogOfWar = choices_option(
        "Fog of war on the map",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=FogOfWar.STRICT,
        causes_expensive_game_update=True,
        choices={
            "Off: show all enemy forces": FogOfWar.OFF,
            "Soft: show all, unconfirmed sites dimmed": FogOfWar.SOFT,
            "Strict: show only detected, at estimated positions": FogOfWar.STRICT,
        },
        detail=(
            "What the map shows of enemy forces. Strict hides undetected sites and "
            "shows detected ones at their estimated position with an uncertainty "
            "ring until confirmed. Soft shows everything but marks unconfirmed sites. "
            "Requires intelligence to be enabled."
        ),
    )
    morale_enabled: bool = boolean_option(
        "Morale: squadrons, ground forces and SAM crews",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Losses and failures lower morale and success raises it. Shaken "
            "squadrons fly worse and stand aircraft down, demoralised fronts break "
            "and surrender units, and frightened SAM crews keep their radars dark."
        ),
    )
    war_weariness_enabled: bool = boolean_option(
        "National war-weariness",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Sustained losses relative to the size of a side's forces lower its "
            "resolve, which reduces income and every morale baseline. It never ends "
            "the war by itself."
        ),
    )
    strategic_surprise: Surprise = choices_option(
        "Strategic surprise at H-hour",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=Surprise.PARTIAL,
        choices={v.value: v for v in Surprise},
        detail=(
            "Set before Begin Campaign. How ready the enemy is when the war "
            "starts: with none, many of its mobile SAMs have left their known "
            "sites, its radars wait in ambush, decoys are out, aircraft are "
            "dispersed and more fighters sit on alert; with full surprise its "
            "SAMs are where intelligence saw them, radiating, and its aircraft "
            "are parked in the open. It also changes how well the opening "
            "missile strikes hit."
        ),
    )
    opening_missile_strikes: bool = boolean_option(
        "Opening missile strikes",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Set before Begin Campaign. When on, your side opens the war with a "
            "cruise missile salvo at the enemy's fixed targets (airfields, air "
            "defenses, command posts). The Begin Campaign window lists the "
            "planned strikes and can turn them off too."
        ),
    )
    road_base_operations: bool = boolean_option(
        "Road base operations",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "When an airfield's runway is cratered, part of its fighters and "
            "attack aircraft keep flying from road strips nearby: they start "
            "in the air a few miles from the field. Helicopters all fly on; "
            "bombers, tankers, AWACS and transports stay grounded. Red's share "
            "at the opening follows the strategic surprise. Off: a cratered "
            "runway grounds everything there."
        ),
    )
    fire_missions: bool = boolean_option(
        "Fire missions (missile and artillery strikes)",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "From turn 1, cruise missile ships, missile sites and front-line "
            "artillery fire planned strikes: yours from the Fire Missions "
            "window, the enemy's by its commander. Strikes timed inside the "
            "DCS mission are fired in DCS; the rest by the combat model."
        ),
    )
    space_and_agency_intel: bool = boolean_option(
        "Satellites and intelligence agencies",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Imaging satellites (by national capability; optical needs daylight and "
            "clear skies) and agencies (order of battle, site tips, warnings of enemy "
            "offensives and strikes). Both sides get them by the same rules, and "
            "every report is uncertain."
        ),
    )
    intel_source_strength: float = bounded_float_option(
        "Strategic intelligence strength",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        min=0.25,
        max=2.0,
        divisor=100,
        default=1.0,
        detail="Scales satellite image quality and agency reliability for both sides.",
    )
    deception_enabled: bool = boolean_option(
        "Deception: decoy sites and camouflage",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Forces with a deception doctrine set up decoys beside mobile air "
            "defenses. Imagery and agents are fooled into reporting decoys as real "
            "sites; strikes on them are wasted until reconnaissance sees through them."
        ),
    )
    roe_strictness: RoeSetting = choices_option(
        "Rules of engagement",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=RoeSetting.DOCTRINE,
        choices={
            "By doctrine (Western: restrictive)": RoeSetting.DOCTRINE,
            "Permissive": RoeSetting.PERMISSIVE,
            "Restrictive": RoeSetting.RESTRICTIVE,
        },
        detail=(
            "Restrictive rules keep the AI from striking targets in built-up areas "
            "and make pilots more careful with unguided weapons near towns."
        ),
    )
    collateral_damage_enabled: bool = boolean_option(
        "Collateral damage",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Weapons that go astray near towns cause civilian casualties, which cost "
            "the striking side national resolve and boost the enemy's."
        ),
    )
    ew_enabled: bool = boolean_option(
        "Electronic warfare in the combat model",
        page=CAMPAIGN_DOCTRINE_PAGE,
        section=WARFARE_SECTION,
        default=True,
        detail=(
            "Decoys, stand-off jamming of radars and communications, and GPS "
            "jamming over territory held by forces that use it."
        ),
    )
    supercarrier: bool = boolean_option(
        "Use supercarrier module",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
    )
    supercarrier_deck_crew: bool = boolean_option(
        "Use supercarrier deck-crew",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    generate_portable_tacans: bool = boolean_option(
        "Place portable TACAN beacons at blue airfields",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Automatically places a portable TACAN beacon at blue-captured "
            "airfields that don't already have a built-in TACAN from the "
            "terrain data. An unused X-band channel is assigned to each."
        ),
    )
    generate_marks: bool = boolean_option(
        "Put objective markers on the map",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    eplrs_enabled: bool = boolean_option(
        "Enable EPLRS",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    generate_dark_kneeboard: bool = boolean_option(
        "Generate dark kneeboard",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Dark kneeboard for night missions. This will likely make the kneeboard on "
            "the pilot leg unreadable."
        ),
    )
    never_delay_player_flights: bool = boolean_option(
        "Player flights ignore TOT and spawn immediately",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Does not adjust package waypoint times. Should not be used if players "
            "have runway or in-air starts."
        ),
        tooltip=(
            "Always spawns player aircraft immediately, even if their start time is "
            "more than 10 minutes after the start of the mission. <strong>This does "
            "not alter the timing of your mission. Your TOT will not change. This "
            "option only allows the player to wait on the ground.</strong>"
        ),
    )
    untasked_opfor_client_slots: bool = boolean_option(
        "Convert untasked OPFOR aircraft into client slots",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Warning: Enabling this will significantly reduce the number of "
            "targets available for OCA/Aircraft missions."
        ),
    )
    default_start_type: StartType = choices_option(
        "Default start type for AI aircraft",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        choices={v.value: v for v in StartType},
        default=StartType.COLD,
        detail=(
            "Warning: Options other than Cold will significantly reduce the number of "
            "targets available for OCA/Aircraft missions, and OCA/Aircraft flights "
            "will not be included in automatically planned OCA packages."
        ),
    )
    default_start_type_client: StartType = choices_option(
        "Default start type for Player flights",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        choices={v.value: v for v in StartType},
        default=StartType.COLD,
        detail="Default start type for flights containing Player/Client slots.",
    )
    csar_start_type: StartType = choices_option(
        "Default start type for CSAR flights",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        choices={v.value: v for v in StartType},
        default=StartType.WARM,
        detail=(
            "Start type for combat search and rescue flights, overriding the AI "
            "and player defaults above."
        ),
    )
    csar_hover_extraction: bool = boolean_option(
        "CSAR hover extraction",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Controls how an AI rescue helicopter recovers a downed pilot.\n\n"
            "Unchecked: the helicopter lands and the pilot walks aboard.\n\n"
            "Checked (default): the helicopter holds a low hover over the pickup and the "
            "pilot is extracted by script, as though hoisted."
        ),
    )
    csar_rescue_ai_pilots: bool = boolean_option(
        "CSAR rescues AI-controlled downed pilots",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "If set, Ops.CSAR will register AI downed pilots in the mission for "
            "player flights, not only player-flown ejections."
        ),
    )
    csar_player_hover_height: int = bounded_int_option(
        "Player hover pickup height (m)",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=20,
        min=5,
        max=100,
        detail=(
            "How low a player has to hover over a survivor to winch them up. "
            "Ops.CSAR's rescuehoverheight. Player pickups only."
        ),
    )
    csar_player_hover_distance: int = bounded_int_option(
        "Player hover pickup distance (m)",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=10,
        min=5,
        max=200,
        detail=(
            "How close to the survivor a player has to hold that hover. "
            "Ops.CSAR's rescuehoverdistance. Player pickups only."
        ),
    )
    csar_require_open_doors: bool = boolean_option(
        "Require cabin door open",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "If set, a survivor will not climb aboard a player's helicopter until "
            "its cabin door is open, and will not get out again until it is opened."
            "Player Flights Only"
        ),
    )
    default_player_laser_code: DefaultPlayerLaserCode = choices_option(
        "Default laser code for Player flights",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        choices={v.value: v for v in DefaultPlayerLaserCode},
        default=DefaultPlayerLaserCode.ALLOCATE_OWN,
        detail=(
            "Allocate own gives every newly-created player flight a unique TGP/"
            "weapon laser code. Default (1688) leaves the code unset so bombs "
            "and the cockpit TGP fall back to 1688. Affects newly-created "
            "flights only; existing flights are unchanged."
        ),
    )
    nevatim_parking_fix: bool = boolean_option(
        "Force air-starts for aircraft at Nevatim and Ramon Airbase inoperable parking slots",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=False,  # TODO: set to False or remove this when DCS is fixed
        detail=(
            "Air-starts forced for all aircraft at Nevatim and Ramon Airbase except parking slots "
            "which are known to work as of DCS World 2.9.4.53990."
        ),
    )
    switch_baro_fix: bool = boolean_option(
        "Switch altitude type of waypoints to AMSL above seas for helicopters",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=True,  # TODO: set to False or remove this when DCS is fixed?
        detail=(
            "AGL seems to reference the bottom of the sea which causes issues for helicopters"
            " trying to fly at altitudes lower than the sea-bottom."
        ),
    )
    limit_ai_radios: bool = boolean_option(
        "Limit AI radio callouts",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=True,
        detail="Avoids the target-detection callouts over the radio by AI. (except for AWACS flights)",
    )
    silence_ai_radios: bool = boolean_option(
        "Suppress AI radio callouts",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=False,
        detail="Keeps the AI silent at all times for flights with human pilots. (except for AWACS flights)",
    )
    use_ai_combat_landing: bool = boolean_option(
        "Use AI combat landing waypoint task",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=False,
        detail="Turns the combat landing flag on in the landing waypoint task.",
    )
    # Mission specific
    desired_player_mission_duration: timedelta = minutes_option(
        "Desired mission duration",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=timedelta(minutes=60),
        min=30,
        max=150,
    )
    max_frontline_width: int = bounded_int_option(
        "Maximum frontline width (km)",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=80,
        min=1,
        max=100,
    )
    game_masters_count: int = bounded_int_option(
        "Number of game masters",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=1,
        min=0,
        max=10,
        detail=(
            "The number of game master slots to generate for each side. "
            "Game masters can see, control & direct all units in the mission."
        ),
    )
    tactical_commander_count: int = bounded_int_option(
        "Number of tactical commands",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=3,
        min=0,
        max=10,
        detail=(
            "The number of tactical commander slots to generate for each side. "
            "Tactical commanders can control & direct friendly units."
        ),
    )
    jtac_count: int = bounded_int_option(
        "Number of JTAC controllers",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=3,
        min=0,
        max=10,
        detail=(
            "The number of JTAC controller slots to generate for each side. "
            "JTAC operators can only control friendly units."
        ),
    )
    observer_count: int = bounded_int_option(
        "Number of observers",
        page=MISSION_GENERATOR_PAGE,
        section=GAMEPLAY_SECTION,
        default=0,
        min=0,
        max=10,
        detail=(
            "The number of observers slots to generate for each side. "
            'Use this to allow spectators when disabling "Allow external views".'
        ),
    )
    ground_start_ai_planes: bool = boolean_option(
        "AI fixed-wing aircraft can use roadbases / bases with only ground spawns",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "If enabled, AI can use roadbases or airbases which only have ground spawns. "
            "AI will always air-start from these bases (due to DCS limitation)."
        ),
    )
    ground_start_scenery_remove_triggers: bool = boolean_option(
        "Generate SCENERY REMOVE OBJECTS ZONE triggers at roadbase first waypoints",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Can be used to remove lightposts and other obstacles from roadbase runways. "
            "Might not work in DCS multiplayer."
        ),
    )
    ground_start_trucks: bool = boolean_option(
        "Spawn trucks at ground spawns in airbases instead of FARP statics",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=("Might have a negative performance impact."),
    )
    ground_start_trucks_roadbase: bool = boolean_option(
        "Spawn trucks at ground spawns in roadbases instead of FARP statics",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=("Might have a negative performance impact."),
    )
    ground_start_ground_power_trucks: bool = boolean_option(
        "Spawn ground power trucks at ground starts in airbases",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Needed to cold-start some aircraft types. Might have a performance impact."
        ),
    )
    ground_start_ground_power_trucks_roadbase: bool = boolean_option(
        "Spawn ground power trucks at ground starts in roadbases",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Needed to cold-start some aircraft types. Might have a performance impact."
        ),
    )
    ground_start_airbase_statics_farps_remove: bool = boolean_option(
        "Remove ground spawn statics, including invisible FARPs, at airbases",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "Ammo and fuel statics and invisible FARPs should be unnecessary when creating "
            "additional spawns for players at airbases. This setting will disable them and "
            "potentially grant a marginal performance benefit."
        ),
    )
    ai_unlimited_fuel: bool = boolean_option(
        "AI flights have unlimited fuel",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=(
            "AI aircraft have unlimited fuel applied at start, removed at join/racetrack start,"
            " and reapplied at split/racetrack end for applicable flights. "
        ),
    )
    dynamic_slots: bool = boolean_option(
        "Dynamic slots",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=False,
        detail=(
            "Enables dynamic slots. Please note that losses from dynamic slots won't be registered."
        ),
    )
    dynamic_slots_hot: bool = boolean_option(
        "Allow dynamic slot hot start",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=("Enables hot start for dynamic slots."),
    )
    dynamic_cargo: bool = boolean_option(
        "Dynamic cargo",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
        detail=("Enables dynamic cargo for airfields, ships, FARPs & warehouses."),
    )
    player_flights_sixpack: bool = boolean_option(
        "Player flights can spawn on the sixpack",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )
    use_auto_fog: bool = boolean_option(
        "Use DCS' automatic fog setting",
        MISSION_GENERATOR_PAGE,
        GAMEPLAY_SECTION,
        default=True,
    )

    # Performance
    perf_smoke_gen: bool = boolean_option(
        "Smoke visual effect on the front line",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_smoke_spacing: int = bounded_int_option(
        "Smoke generator spacing (higher means less smoke)",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=1600,
        min=800,
        max=24000,
    )
    perf_red_alert_state: bool = boolean_option(
        "SAM starts in red alert mode",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_artillery: bool = boolean_option(
        "Artillery strikes",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    generate_fire_tasks_for_missile_sites: bool = boolean_option(
        "Generate fire tasks for missile sites",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        detail=(
            "If enabled, missile sites like V2s and Scuds will fire on random targets "
            "at the start of the mission."
        ),
        default=True,
    )
    perf_moving_units: bool = boolean_option(
        "Moving ground units",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    convoys_travel_full_distance: bool = boolean_option(
        "Convoys drive the full distance between control points",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_disable_convoys: bool = boolean_option(
        "Disable convoys",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_disable_cargo_ships: bool = boolean_option(
        "Disable shipping-convoys",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_frontline_units_prefer_roads: bool = boolean_option(
        "Front line troops prefer roads",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_frontline_units_max_supply: int = bounded_int_option(
        "Maximum ground units deployed per frontline by faction",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=60,
        min=10,
        max=300,
        causes_expensive_game_update=True,
    )
    perf_infantry: bool = boolean_option(
        "Generate infantry squads alongside vehicles",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_destroyed_units: bool = boolean_option(
        "Generate carcasses for units destroyed in previous turns",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_disable_untasked_blufor_aircraft: bool = boolean_option(
        "Disable untasked OWNFOR aircraft at airfields",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_disable_untasked_opfor_aircraft: bool = boolean_option(
        "Disable untasked OPFOR aircraft at airfields",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    # Performance culling
    perf_culling: bool = boolean_option(
        "Culling of distant units enabled",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
    )
    perf_culling_distance: int = bounded_int_option(
        "Culling distance (km)",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=100,
        min=10,
        max=10000,
        causes_expensive_game_update=True,
    )
    perf_do_not_cull_threatening_iads: bool = boolean_option(
        "Do not cull threatening IADS",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
    )
    perf_do_not_cull_carrier: bool = boolean_option(
        "Do not cull carrier's surroundings",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=True,
        causes_expensive_game_update=True,
    )
    perf_ai_despawn_airstarted: bool = boolean_option(
        "De-spawn AI in the air upon RTB",
        page=MISSION_GENERATOR_PAGE,
        section=PERFORMANCE_SECTION,
        default=False,
        detail=(
            "If enabled, AI flights will de-spawn over their base "
            "if the start-up type was manually changed to 'In-Flight'."
        ),
    )
    pretense_maxdistfromfront_distance: int = bounded_int_option(
        "Max distance from front (km)",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=130,
        min=10,
        max=10000,
        detail=(
            "Zones farther away than this from the front line are switched "
            "into low activity state, but will still be there as functional "
            "parts of the economy. Use this to adjust performance."
        ),
    )
    pretense_controllable_carrier: bool = boolean_option(
        "Controllable carrier",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "This can be used to enable or disable the native carrier support in Pretense. The Pretense carrier "
            "can be controlled through the communication menu (if the Pretense character has enough rank/CMD points) "
            "and the player can call in AI aerial and cruise missile missions using it."
            "The controllable carriers in Pretense do not build and deploy AI missions autonomously, so if you prefer "
            "to have both sides deploy carrier aviation autonomously, you might want to disable this option. "
            "When this option is disabled, moving the carrier can only be done with the Retribution interface."
        ),
    )
    pretense_carrier_steams_into_wind: bool = boolean_option(
        "Carriers steam into wind",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=True,
        detail=(
            "This setting controls whether carriers and their escorts will steam into wind. Disable to "
            "to ensure that the carriers stay within the carrier zone in Pretense, but note that "
            "doing so might limit carrier operations, takeoff weights and landings."
        ),
    )
    pretense_carrier_zones_navmesh: str = choices_option(
        "Navmesh to use for Pretense carrier zones",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        choices=["Blue navmesh", "Red navmesh"],
        default="Blue navmesh",
        detail=(
            "Use the Retribution map interface options to compare the blue navmesh and the red navmesh."
            "You can select which navmesh to use when generating the zones in which the controllable carrier(s) "
            "move and operate."
        ),
    )
    pretense_extra_zone_connections: int = bounded_int_option(
        "Extra friendly zone connections",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=2,
        min=0,
        max=10,
        detail=(
            "Add connections from each zone to this many closest friendly zones,"
            "which don't have an existing supply route defined in the campaign."
        ),
    )
    pretense_num_of_cargo_planes: int = bounded_int_option(
        "Number of cargo planes per side",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=2,
        min=1,
        max=100,
    )
    pretense_sead_flights_per_cp: int = bounded_int_option(
        "Number of AI SEAD flights per control point / zone",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_cas_flights_per_cp: int = bounded_int_option(
        "Number of AI CAS flights per control point / zone",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_bai_flights_per_cp: int = bounded_int_option(
        "Number of AI BAI flights per control point / zone",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_strike_flights_per_cp: int = bounded_int_option(
        "Number of AI Strike flights per control point / zone",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_barcap_flights_per_cp: int = bounded_int_option(
        "Number of AI BARCAP flights per control point / zone",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_ai_aircraft_per_flight: int = bounded_int_option(
        "Number of AI aircraft per flight",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=2,
        min=1,
        max=4,
    )
    pretense_player_flights_per_type: int = bounded_int_option(
        "Number of player flights per aircraft type at each base",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=1,
        min=1,
        max=10,
    )
    pretense_ai_cargo_planes_per_side: int = bounded_int_option(
        "Number of AI cargo planes per side",
        page=PRETENSE_PAGE,
        section=GENERAL_SECTION,
        default=2,
        min=1,
        max=20,
    )

    # Cheating. Not using auto settings because the same page also has buttons which do
    # not alter settings.
    enable_frontline_cheats: bool = False
    enable_base_capture_cheat: bool = False
    enable_transfer_cheat: bool = False
    #: Player FARPs are set up as soon as they're ordered, without a transport
    #: having to fly their equipment in.
    enable_instant_farp_cheat: bool = False
    enable_runway_state_cheat: bool = False
    enable_air_wing_adjustments: bool = False
    enable_enemy_buy_sell: bool = False

    # LUA Plugins system
    plugins: Dict[str, bool] = field(default_factory=dict)

    only_player_takeoff: bool = True  # Legacy parameter do not use

    def start_type_for(self, flight_type: "FlightType", has_players: bool) -> StartType:
        """The start type a newly planned flight of this kind should default to.

        The single source of this decision. It is applied from the auto-planner
        (PackageBuilder.plan_flight) and from both places the UI recomputes a
        default (QFlightCreator and QFlightStartType), so a task with its own
        start type behaves the same however the flight came to exist.

        Callers must still let a base that dictates its own start type win --
        carriers and off-map spawns -- via
        ControlPoint.required_aircraft_start_type.
        """
        from ..ato.flighttype import FlightType

        if flight_type is FlightType.CSAR:
            # A downed pilot is on a timer, so the rescue is usually worth
            # launching sooner than the rest of the ATO. Overrides both defaults
            # below, players included: the setting exists precisely so CSAR does
            # not have to inherit them.
            return self.csar_start_type
        if has_players:
            return self.default_start_type_client
        return self.default_start_type

    @staticmethod
    def plugin_settings_key(identifier: str) -> str:
        return f"{identifier}"

    def initialize_plugin_option(self, identifier: str, default_value: Any) -> None:
        try:
            self.plugin_option(identifier)
        except KeyError:
            self.set_plugin_option(identifier, default_value)

    def plugin_option(self, identifier: str) -> Any:
        return self.plugins[self.plugin_settings_key(identifier)]

    def set_plugin_option(self, identifier: str, value: Any) -> None:
        self.plugins[self.plugin_settings_key(identifier)] = value

    def __setstate__(self, state: dict[str, Any]) -> None:
        # __setstate__ is called with the dict of the object being unpickled. We
        # can provide save compatibility for new settings options (which
        # normally would not be present in the unpickled object) by creating a
        # new settings object, updating it with the unpickled state, and
        # updating our dict with that.
        new_state = Settings().__dict__
        new_state.update(self.deserialize_state_dict(state))
        self.__dict__.update(new_state)
        from game.plugins import LuaPluginManager

        LuaPluginManager().load_settings(self)

    @staticmethod
    def deserialize_state_dict(state: dict[str, Any]) -> dict[str, Any]:
        # restore Enum & timedelta types
        s = Settings()
        Settings._migrate_legacy_fast_forward(state)
        for key, value in list(state.items()):
            default = s.__dict__.get(key)
            if isinstance(default, Enum):
                # Restore the stored member, falling back to the field default
                # for any value that no longer resolves to a member of this
                # field's enum -- a stale/renamed choice, or a legacy non-enum
                # value such as None or a bool. Otherwise the bad value crashes
                # the load and later the settings UI via text_for_value.
                restored = Settings._restore_enum(value, type(default))
                state[key] = restored if restored is not None else default
            elif isinstance(default, timedelta) and isinstance(value, int):
                state[key] = timedelta(minutes=value)
            elif isinstance(value, dict):
                state[key] = s.obj_hook(value)
        return state

    @staticmethod
    def _restore_enum(value: Any, enum_cls: type[Enum]) -> Optional[Enum]:
        """Resolve a serialized value to a member of enum_cls, or None if it no
        longer maps to one (stale, renamed, or a legacy non-enum value)."""
        if isinstance(value, enum_cls):
            return value
        # Accept the JSON form {"Enum": "EnumName.MEMBER"} and the bare
        # "EnumName.MEMBER" string; ignore anything that does not eval to a
        # member of this field's enum.
        expr: Optional[str] = None
        if isinstance(value, dict):
            inner = value.get("Enum")
            if isinstance(inner, str):
                expr = inner
        elif isinstance(value, str):
            expr = value
        if expr is not None:
            try:
                restored = eval(expr)
            except Exception:
                return None
            if isinstance(restored, enum_cls):
                return restored
        return None

    @staticmethod
    def _migrate_legacy_fast_forward(state: dict[str, Any]) -> None:
        """Map pre-#684 fast-forward settings onto the current enums.

        Before #684 fast-forward was three separate fields::

            fast_forward_to_first_contact: bool          # was it enabled
            player_mission_interrupts_sim_at: Optional[StartType]
                # None=Never, COLD=startup, WARM=taxi, RUNWAY=takeoff
            auto_resolve_combat: bool

        #684 replaced them with ``fast_forward_stop_condition`` /
        ``combat_resolution_method``. Translate old saves so the user keeps an
        equivalent setting instead of crashing on load, and normalize the legacy
        "Never"/None sentinel (which has no enum member) to "no fast forward".
        """
        legacy_ff = state.pop("fast_forward_to_first_contact", None)
        legacy_interrupt = state.pop("player_mission_interrupts_sim_at", None)
        legacy_auto = state.pop("auto_resolve_combat", None)

        if "fast_forward_stop_condition" not in state and legacy_ff is not None:
            if not legacy_ff:
                state["fast_forward_stop_condition"] = FastForwardStopCondition.DISABLED
            else:
                interrupt = Settings._resolve_start_type(legacy_interrupt)
                if interrupt is None:
                    state["fast_forward_stop_condition"] = (
                        FastForwardStopCondition.FIRST_CONTACT
                    )
                else:
                    state["fast_forward_stop_condition"] = {
                        StartType.COLD: FastForwardStopCondition.PLAYER_STARTUP,
                        StartType.WARM: FastForwardStopCondition.PLAYER_TAXI,
                        StartType.RUNWAY: FastForwardStopCondition.PLAYER_TAKEOFF,
                    }.get(interrupt, FastForwardStopCondition.FIRST_CONTACT)

        if "combat_resolution_method" not in state and legacy_auto is not None:
            state["combat_resolution_method"] = (
                CombatResolutionMethod.RESOLVE
                if legacy_auto
                else CombatResolutionMethod.PAUSE
            )

        # A "none"/"Never"/None value stored directly under the new key has no
        # matching enum member; treat that family as "no fast forward".
        ff = state.get("fast_forward_stop_condition")
        if ff is None and "fast_forward_stop_condition" in state:
            state["fast_forward_stop_condition"] = FastForwardStopCondition.DISABLED
        elif isinstance(ff, str) and ff.strip().lower() in {"none", "never", ""}:
            state["fast_forward_stop_condition"] = FastForwardStopCondition.DISABLED

    @staticmethod
    def _resolve_start_type(value: Any) -> Optional[StartType]:
        """Coerce a serialized legacy value to a StartType member, or None."""
        if isinstance(value, StartType):
            return value
        if isinstance(value, str):
            name = value.rsplit(".", 1)[-1]
            for member in StartType:
                if name == member.name or value == member.value:
                    return member
        return None

    @classmethod
    def _field_description(cls, settings_field: Field[Any]) -> OptionDescription:
        return settings_field.metadata[SETTING_DESCRIPTION_KEY]

    @classmethod
    def pages(cls) -> Iterator[str]:
        seen: set[str] = set()
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if description.page not in seen:
                yield description.page
                seen.add(description.page)

    @classmethod
    def sections(cls, page: str) -> Iterator[str]:
        seen: set[str] = set()
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if description.page == page and description.section not in seen:
                yield description.section
                seen.add(description.section)

    @classmethod
    def fields(cls, page: str, section: str) -> Iterator[tuple[str, OptionDescription]]:
        for settings_field in cls._user_fields():
            description = cls._field_description(settings_field)
            if description.page == page and description.section == section:
                yield settings_field.name, description

    @classmethod
    def _user_fields(cls) -> Iterator[Field[Any]]:
        for settings_field in fields(cls):
            if SETTING_DESCRIPTION_KEY in settings_field.metadata:
                yield settings_field

    @staticmethod
    def default_json(obj: Any) -> Any:
        # Known types that don't like being serialized,
        # so we introduce our own implementation...
        if isinstance(obj, Enum):
            return {"Enum": str(obj)}
        elif isinstance(obj, timedelta):
            return {"timedelta": round(obj.seconds / 60)}
        return obj

    @staticmethod
    def obj_hook(obj: Any) -> Any:
        if (value := obj.get("Enum")) is not None:
            return eval(value)
        elif (value := obj.get("timedelta")) is not None:
            return timedelta(minutes=value)
        else:
            return obj
