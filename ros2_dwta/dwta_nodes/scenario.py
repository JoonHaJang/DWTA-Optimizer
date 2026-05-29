"""Lightweight scenario for the PoC (numpy-only, no pydantic / GUI deps).

Mirrors the domain objects used by the existing optimizers (Asset / battery /
threat) but kept self-contained so the pipeline runs anywhere. Coordinates are
abstract 2D km; threats fly from a launch point toward their target asset at
constant velocity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class Asset:
    id: str
    position: Tuple[float, float]
    value: float


@dataclass
class Battery:
    """방어 자산(요격체계/발사대) 사양 + 가용 자원."""
    id: str
    layer: str                 # "UPPER" (L-SAM) | "LOWER" (M-SAM)
    position: Tuple[float, float]
    engagement_range: float
    base_pk: float
    available_missiles: int
    simultaneous_engagements: int


@dataclass
class ThreatSpawn:
    threat_id: str
    target_asset_id: str
    launch_position: Tuple[float, float]
    speed: float               # km/s
    launch_time: float         # sim time the threat appears


def default_scenario() -> Tuple[List[Asset], List[Battery], List[ThreatSpawn]]:
    assets = [
        Asset("A1_Command", (0.0, 0.0), value=100.0),
        Asset("A2_Airbase", (0.0, 40.0), value=70.0),
    ]
    batteries = [
        Battery("L1_LSAM", "UPPER", (0.0, -15.0), engagement_range=150.0,
                base_pk=0.82, available_missiles=6, simultaneous_engagements=3),
        Battery("M1_MSAM", "LOWER", (0.0, 10.0), engagement_range=45.0,
                base_pk=0.70, available_missiles=8, simultaneous_engagements=4),
    ]
    # threats launched from the east, staggered in time (saturation ramp)
    spawns = [
        ThreatSpawn("T1", "A1_Command", (190.0, 5.0), speed=2.4, launch_time=0.0),
        ThreatSpawn("T2", "A1_Command", (210.0, -10.0), speed=2.2, launch_time=2.0),
        ThreatSpawn("T3", "A2_Airbase", (200.0, 60.0), speed=2.3, launch_time=4.0),
        ThreatSpawn("T4", "A1_Command", (230.0, 20.0), speed=2.6, launch_time=6.0),
        ThreatSpawn("T5", "A2_Airbase", (220.0, 80.0), speed=2.1, launch_time=9.0),
        ThreatSpawn("T6", "A1_Command", (250.0, -30.0), speed=2.7, launch_time=12.0),
    ]
    return assets, batteries, spawns


def velocity_toward(src: Tuple[float, float], dst: Tuple[float, float], speed: float) -> Tuple[float, float]:
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    dist = math.hypot(dx, dy) or 1.0
    return (speed * dx / dist, speed * dy / dist)


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
