"""시나리오 + 미사일/포대 스펙 (numpy-only, no pydantic / GUI deps).

레이다는 역할별로 분리:
  - 중앙 감시레이다(SurveillanceRadar): 탐지/추적 (1개)
  - 포대 사격통제레이다(FireControlRadar): 요격탄 유도 (포대당 1개)
배터리(포대)는 '탄약(발사대)'과 '유도 채널(포대 레이다)'을 별개 자원으로 가진다:
  동시 교전 수 = min(잔여탄, 유도 채널 수).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Asset:
    id: str
    position: Tuple[float, float]
    value: float


@dataclass
class Battery:
    """방어 포대 = 발사대(탄약) + 포대 사격통제레이다(유도 채널)."""
    id: str
    layer: str                     # "UPPER" (L-SAM) | "LOWER" (M-SAM)
    position: Tuple[float, float]
    engagement_range: float        # 요격 가능 거리
    base_pk: float                 # 기본 명중률
    available_missiles: int        # 발사대 잔여탄
    fire_control_channels: int     # 포대 레이다 동시 유도 채널 수 (= 동시교전 한계)
    interceptor_flyout: float      # 요격탄 비행시간 (s)


@dataclass
class ThreatSpawn:
    threat_id: str
    target_asset_id: str
    launch_position: Tuple[float, float]
    speed: float                   # km/s
    launch_time: float


# --- 임의 미사일/포대 스펙 프리셋 -------------------------------------------------
def lsam(bid: str, pos: Tuple[float, float]) -> Battery:
    """L-SAM (장거리·상층): 넓은 사거리, 유도 채널 적음(고가치). 임의 스펙."""
    return Battery(bid, "UPPER", pos, engagement_range=160.0, base_pk=0.86,
                   available_missiles=16, fire_control_channels=4, interceptor_flyout=2.5)


def msam(bid: str, pos: Tuple[float, float]) -> Battery:
    """M-SAM (중첩 사거리·하층·고Pk): 상층과 교전대 중첩 -> 상하층 동시 교전. 임의 스펙."""
    return Battery(bid, "LOWER", pos, engagement_range=130.0, base_pk=0.90,
                   available_missiles=16, fire_control_channels=5, interceptor_flyout=1.6)


def balanced_scenario() -> Tuple[List[Asset], List[Battery], List[ThreatSpawn]]:
    """소규모 6발 (기능 확인용)."""
    assets = [Asset("A1_Command", (0.0, 0.0), 100.0),
              Asset("A2_Airbase", (0.0, 40.0), 70.0)]
    batteries = [lsam("L1_LSAM", (0.0, -15.0)), msam("M1_MSAM", (0.0, 10.0))]
    spawns = [
        ThreatSpawn("T1", "A1_Command", (190.0, 5.0), 2.4, 0.0),
        ThreatSpawn("T2", "A1_Command", (210.0, -10.0), 2.2, 2.0),
        ThreatSpawn("T3", "A2_Airbase", (200.0, 60.0), 2.3, 4.0),
        ThreatSpawn("T4", "A1_Command", (230.0, 20.0), 2.6, 6.0),
        ThreatSpawn("T5", "A2_Airbase", (220.0, 80.0), 2.1, 9.0),
        ThreatSpawn("T6", "A1_Command", (250.0, -30.0), 2.7, 12.0),
    ]
    return assets, batteries, spawns


def saturation_scenario() -> Tuple[List[Asset], List[Battery], List[ThreatSpawn]]:
    """대규모 포화 웨이브: 다수 위협이 짧은 간격으로 도착 -> 상층(L-SAM) 유도채널이
    포화되어 일부가 하층(M-SAM) 사거리로 진입 -> 상·하층 동시 교전 발생.
    """
    assets = [Asset("A1_Command", (0.0, 0.0), 100.0),
              Asset("A2_Airbase", (0.0, 45.0), 75.0)]
    batteries = [
        lsam("L1_LSAM", (0.0, -20.0)),       # 상층 1포대 (채널 3) — 포화 유발
        msam("M1_MSAM", (0.0, 8.0)),         # 하층: A1 방어
        msam("M2_MSAM", (0.0, 50.0)),        # 하층: A2 방어
    ]
    # 16발 포화 웨이브 (0~9s 집중 발사), 두 자산에 분산
    waves = [
        ("A1_Command", (0.0, 0.0)), ("A2_Airbase", (0.0, 45.0)),
    ]
    spawns: List[ThreatSpawn] = []
    # 고속·집중 버스트 -> 상층(L) 교전 진행 중에 하층(M) 중첩 사거리 진입 -> 상하층 동시 교전
    import_seed = [
        # (target_idx, x, y, speed, t)
        (0, 190, 10, 5.4, 0.0), (0, 200, -20, 5.6, 0.4), (1, 195, 70, 5.3, 0.8),
        (0, 205, 30, 5.8, 1.2), (1, 190, 95, 5.2, 1.6), (0, 185, -40, 5.5, 2.0),
        (0, 210, 50, 5.7, 2.4), (1, 200, 35, 5.4, 2.8), (0, 195, -10, 5.5, 3.2),
        (1, 205, 110, 5.3, 3.6), (0, 215, 20, 5.9, 4.0), (0, 190, 60, 5.4, 4.4),
        (1, 198, 40, 5.4, 4.8), (0, 208, -30, 5.7, 5.2), (1, 202, 95, 5.5, 5.6),
        (0, 192, 5, 5.4, 6.0), (0, 212, 45, 5.6, 6.4), (1, 196, 80, 5.3, 6.8),
        (0, 188, -15, 5.5, 7.2), (1, 204, 60, 5.4, 7.6),
    ]
    for i, (tidx, x, y, spd, t) in enumerate(import_seed, start=1):
        tgt = waves[tidx][0]
        spawns.append(ThreatSpawn(f"T{i:02d}", tgt, (float(x), float(y)), spd, t))
    return assets, batteries, spawns


SCENARIOS = {"balanced": balanced_scenario, "saturation": saturation_scenario}


def default_scenario():
    return saturation_scenario()


def velocity_toward(src: Tuple[float, float], dst: Tuple[float, float], speed: float) -> Tuple[float, float]:
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    dist = math.hypot(dx, dy) or 1.0
    return (speed * dx / dist, speed * dy / dist)


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
