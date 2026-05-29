"""Message types for the DWTA ROS2 pipeline.

For the PoC these are plain dataclasses so the exact same node code runs both
under real ROS2 (rclpy) and under the in-process shim (sim_bus) without a ROS2
install.  For a real deployment, replace these with a `dwta_msgs` rosidl
interface package (the equivalent .msg files live in ros2_dwta/msg/) and import
the generated types instead -- the field names are kept identical on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---- 경보체계 / 레이다 (sensor) -------------------------------------------------
@dataclass
class BallisticTrack:
    """단일 탄도탄 추적 정보 (위치/속도/예상탄착/발사점)."""
    threat_id: str
    target_asset_id: str
    position: Tuple[float, float]
    velocity: Tuple[float, float]
    launch_position: Tuple[float, float]
    time_to_impact: float          # TTA, seconds
    stamp: float                   # sim time the track was produced


@dataclass
class TrackArray:
    stamp: float
    tracks: List[BallisticTrack] = field(default_factory=list)


@dataclass
class RadarStatus:
    stamp: float
    detecting: bool
    n_tracks: int


# ---- OO평가 (threat assessment) -----------------------------------------------
@dataclass
class ThreatScore:
    threat_id: str
    target_asset_id: str
    danger: float                  # 높을수록 위험 (가치/TTA 기반 점수화)
    time_to_impact: float


@dataclass
class ThreatScores:
    stamp: float
    scores: List[ThreatScore] = field(default_factory=list)


# ---- OO 가능성 평가 (engageability) -------------------------------------------
@dataclass
class EngagementCell:
    """(요격체계, 탄도탄) 교전 가능성 한 칸: 교전창 + 명중률."""
    system_id: str
    threat_id: str
    layer: str                     # "UPPER" | "LOWER"
    pk: float                      # 명중률 (Probability of kill)
    window_open: float             # 교전 가능 시작 (s, sim time)
    window_close: float            # 교전 가능 종료 (s, sim time)


@dataclass
class EngagementMatrix:
    stamp: float
    cells: List[EngagementCell] = field(default_factory=list)


# ---- OO계획 수립/전송 (planning) ----------------------------------------------
@dataclass
class Assignment:
    system_id: str
    threat_id: str
    layer: str
    pk: float


@dataclass
class EngagementPlan:
    stamp: float
    assignments: List[Assignment] = field(default_factory=list)
    objective_value: float = 0.0
    solver: str = ""


# ---- OO체계 (actuators / status) ----------------------------------------------
@dataclass
class Interceptor:
    """아군 요격탄 한 발의 상태 (비행중 유도탄)."""
    interceptor_id: str
    system_id: str
    target_threat_id: str
    pk: float
    launch_time: float
    intercept_time: float          # 예상 요격 시각 (launch + flyout)
    state: str = "IN_FLIGHT"       # IN_FLIGHT | HIT | MISS


@dataclass
class InterceptorStatus:
    """발사대/요격체계 상태 (잔여탄·비행중 요격탄·교전 상태) — 전 노드 공유."""
    stamp: float
    available: Dict[str, int] = field(default_factory=dict)        # system_id -> 잔여탄
    engaging: Dict[str, List[str]] = field(default_factory=dict)   # system_id -> [threat_id]
    in_flight: List[Interceptor] = field(default_factory=list)     # 현재 비행중 요격탄


@dataclass
class LaunchEvent:
    stamp: float
    system_id: str
    threat_id: str
    pk: float


# ---- 통제소 (policy) -----------------------------------------------------------
@dataclass
class DefensePolicy:
    stamp: float
    posture: str = "WARTIME"       # 전시/평시
    fire_doctrine: str = "SHOOT_LOOK_SHOOT"   # 단발/연속, SSL/SLS
    max_interceptors_per_threat: int = 2


# ---- 통합 이벤트 버스 (event-driven sharing) -----------------------------------
# 이벤트 종류: 탐지/발사/요격성공/요격실패/탄착(누설)
EV_DETECTED = "DETECTED"
EV_LAUNCH = "LAUNCH"
EV_INTERCEPT = "INTERCEPT"   # 요격 성공 (HIT)
EV_MISS = "MISS"             # 요격 실패 -> 위협 계속 (재교전 대상)
EV_IMPACT = "IMPACT"         # 방어 실패 (탄착)


@dataclass
class Event:
    stamp: float
    kind: str                              # EV_* 중 하나
    threat_id: str = ""
    system_id: str = ""
    interceptor_id: str = ""
    detail: str = ""


# ---- Common Operational Picture (전 노드 공유 월드 상태) ------------------------
# 위협 생명주기: DETECTED -> ASSESSED -> ENGAGEABLE -> ENGAGED -> INTERCEPTED | LEAKED
@dataclass
class ThreatState:
    threat_id: str
    target_asset_id: str
    position: Tuple[float, float]
    time_to_impact: float
    danger: float
    lifecycle: str                          # DETECTED|ASSESSED|ENGAGEABLE|ENGAGED|INTERCEPTED|LEAKED
    assigned_systems: List[str] = field(default_factory=list)


@dataclass
class BatteryState:
    system_id: str
    layer: str
    available: int                          # 잔여탄
    in_flight: int                          # 비행중 요격탄 수
    engaging: List[str] = field(default_factory=list)


@dataclass
class WorldState:
    """모든 노드가 구독하는 통합 상황도(적 탄도탄 + 아군 요격탄 상태)."""
    stamp: float
    threats: List[ThreatState] = field(default_factory=list)
    batteries: List[BatteryState] = field(default_factory=list)
    recent_events: List[Event] = field(default_factory=list)
