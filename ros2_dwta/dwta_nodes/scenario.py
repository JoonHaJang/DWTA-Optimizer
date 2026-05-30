"""시나리오 + 미사일/포대 스펙 (numpy-only, no pydantic / GUI deps).

레이다는 역할별로 분리:
  - 중앙 감시레이다(SurveillanceRadar): 탐지/추적 (1개)
  - 포대 사격통제레이다(FireControlRadar): 요격탄 유도 (포대당 1개)
배터리(포대)는 '탄약(발사대)'과 '유도 채널(포대 레이다)'을 별개 자원으로 가진다:
  동시 교전 수 = min(잔여탄, 유도 채널 수).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple


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
    """L-SAM (장거리·상층): 넓은 사거리·고Pk, 탄약/채널 제한(고가치). 임의 스펙."""
    return Battery(bid, "UPPER", pos, engagement_range=160.0, base_pk=0.86,
                   available_missiles=8, fire_control_channels=3, interceptor_flyout=5.0)


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
        lsam("L1_LSAM", (0.0, -20.0)),       # 상층 #1 (남측 섹터)
        lsam("L2_LSAM", (0.0, 65.0)),        # 상층 #2 (북측 섹터) — 다포대 충돌회피 검증
        msam("M1_MSAM", (0.0, 8.0)),         # 하층: A1 방어
        msam("M2_MSAM", (0.0, 50.0)),        # 하층: A2 방어
    ]
    # 16발 포화 웨이브 (0~9s 집중 발사), 두 자산에 분산
    waves = [
        ("A1_Command", (0.0, 0.0)), ("A2_Airbase", (0.0, 45.0)),
    ]
    spawns: List[ThreatSpawn] = []
    # 고속·집중 30발 포화: 상층(L-SAM 2포대) 화력 포화 -> 일부가 하층(M-SAM) 중첩
    # 사거리로 진입 -> 상·하층 동시 교전 + 다포대 분산이 함께 발생하도록 균형.
    n = 30
    a1_ys = [-45, -25, -10, 5, 20, 40]   # A1 방향 위협 y 분포
    a2_ys = [40, 55, 70, 85, 100, 110]   # A2 방향 위협 y 분포
    for i in range(n):
        tidx = i % 2                      # A1 / A2 번갈아
        ys = a1_ys if tidx == 0 else a2_ys
        y = float(ys[(i // 2) % len(ys)])
        x = 185.0 + (i % 8) * 5.0         # 185~220
        spd = 5.2 + (i % 5) * 0.2         # 5.2~6.0
        t = round(i * 0.4, 1)             # 0~11.6s 집중 버스트
        spawns.append(ThreatSpawn(f"T{i + 1:02d}", waves[tidx][0], (x, y), spd, t))
    return assets, batteries, spawns


def random_saturation_scenario(
    seed: Optional[int] = 42,
    n_threats: int = 24,
    burst_window: Tuple[float, float] = (0.0, 12.0),
    speed_range: Tuple[float, float] = (4.5, 6.5),
    launch_x_range: Tuple[float, float] = (170.0, 230.0),
) -> Tuple[List[Asset], List[Battery], List[ThreatSpawn]]:
    """Random saturation scenario (seeded for reproducibility).

    Goal: every run produces a different but multi-layer-defence-friendly
    saturation:
      * Targets are picked uniformly from the asset list so both A1 / A2 are
        loaded simultaneously, forcing the L-SAMs to share fire.
      * Launch y-position is sampled around each target's y so the trajectory
        crosses both the L-SAM (long range) and M-SAM (medium range, overlap)
        engagement zones -- the geometry that lets the overlap zone fire.
      * Speeds are picked from a moderate-high band so the planner cannot
        defeat the burst with one layer alone (forces lower-layer follow-up).

    The total ammo of the default 2x LSAM + 2x MSAM layout (16+16 missiles)
    sits a bit below n_threats * 2 so the optimiser must pick which threats
    to layer and which to gamble with a single shot, surfacing R3 (layered
    intercept) and R4 (leakage under saturation) at the same time.
    """
    rng = random.Random(seed)
    assets = [Asset("A1_Command", (0.0, 0.0), 100.0),
              Asset("A2_Airbase", (0.0, 45.0), 75.0)]
    batteries = [
        lsam("L1_LSAM", (0.0, -20.0)),
        lsam("L2_LSAM", (0.0, 65.0)),
        msam("M1_MSAM", (0.0, 8.0)),
        msam("M2_MSAM", (0.0, 50.0)),
    ]
    t_lo, t_hi = burst_window
    s_lo, s_hi = speed_range
    x_lo, x_hi = launch_x_range
    spawns: List[ThreatSpawn] = []
    for i in range(n_threats):
        target = rng.choice(assets)
        # y around the target +/- 35 km so the trajectory threads the overlap
        # of both layers' engagement disks (radii 160 / 130 around (0, y_bat)).
        y = target.position[1] + rng.uniform(-35.0, 35.0)
        x = rng.uniform(x_lo, x_hi)
        spd = rng.uniform(s_lo, s_hi)
        t = round(rng.uniform(t_lo, t_hi), 2)
        spawns.append(ThreatSpawn(
            threat_id=f"T{i + 1:02d}",
            target_asset_id=target.id,
            launch_position=(x, y),
            speed=spd,
            launch_time=t,
        ))
    # sort by launch_time so the log reads chronologically
    spawns.sort(key=lambda s: s.launch_time)
    return assets, batteries, spawns


SCENARIOS = {
    "balanced": balanced_scenario,
    "saturation": saturation_scenario,
    "random": random_saturation_scenario,
}


def default_scenario():
    return saturation_scenario()


def velocity_toward(src: Tuple[float, float], dst: Tuple[float, float], speed: float) -> Tuple[float, float]:
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    dist = math.hypot(dx, dy) or 1.0
    return (speed * dx / dist, speed * dy / dist)


def distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ---------------------------------------------------------------------------
# UPPAAL geometry helper: precompute (range AND altitude) engagement windows
# ---------------------------------------------------------------------------
# UPPAAL only knows integer time, so we sample the trajectory in ROS2 and
# emit the resulting [enter, exit] window per (threat, battery).  The altitude
# is a simple parabola peaking at MAX_ALT_KM, which is the abstraction the
# UPPAAL v3 model expects.  L-SAM is gated to 40-150 km, M-SAM to 5-40 km --
# tune via alt_window_km if your scenario differs.

UPPER_ALT_WINDOW_KM = (40.0, 150.0)
LOWER_ALT_WINDOW_KM = (5.0, 40.0)


def compute_engagement_window(
    spawn: ThreatSpawn,
    battery: Battery,
    assets: List[Asset],
    *,
    max_alt_km: float = 80.0,
    dt: float = 0.05,
    alt_window_km: Optional[Tuple[float, float]] = None,
) -> Optional[Tuple[float, float]]:
    """Time window in which (range OK) AND (altitude OK) for this pair.

    Returns ``(enter_s, exit_s)`` in absolute seconds (i.e. wall-clock from
    t=0), or ``None`` if the trajectory never enters this battery's effective
    envelope.  The parabolic-altitude model is a rough abstraction that lets
    L-SAM (high-altitude) and M-SAM (low-altitude) windows naturally separate.
    """
    if alt_window_km is None:
        alt_window_km = (UPPER_ALT_WINDOW_KM if battery.layer == "UPPER"
                         else LOWER_ALT_WINDOW_KM)
    target = next(a for a in assets if a.id == spawn.target_asset_id)
    lx, ly = spawn.launch_position
    ix, iy = target.position
    horiz = math.hypot(ix - lx, iy - ly)
    flight = horiz / max(spawn.speed, 1e-6)
    enter: Optional[float] = None
    exit_: Optional[float] = None
    steps = int(flight / dt) + 1
    for k in range(steps):
        rel = k * dt
        u = min(1.0, rel / flight)
        x = lx + (ix - lx) * u
        y = ly + (iy - ly) * u
        h = 4.0 * max_alt_km * u * (1.0 - u)        # apex = max_alt_km at u=0.5
        d = math.hypot(x - battery.position[0], y - battery.position[1])
        ok = (d <= battery.engagement_range
              and alt_window_km[0] <= h <= alt_window_km[1])
        if ok:
            t_abs = spawn.launch_time + rel
            if enter is None:
                enter = t_abs
            exit_ = t_abs
    if enter is None:
        return None
    return (round(enter, 1), round(exit_, 1))


def dump_uppaal_windows(
    seed: Optional[int] = 42,
    n_threats: int = 3,
    *,
    max_alt_km: float = 80.0,
) -> str:
    """Render the random scenario's per-threat / per-battery windows as the
    UPPAAL declaration block consumed by ``dwta_model_v3_geometry.xml``.

    Sentinel ``-1`` is emitted when a battery cannot engage a threat at all
    (e.g. wrong altitude band).  The v3 model treats ``-1`` as "never fires".
    """
    assets, batteries, spawns = random_saturation_scenario(
        seed=seed, n_threats=n_threats)
    upper = [b for b in batteries if b.layer == "UPPER"]
    lower = [b for b in batteries if b.layer == "LOWER"]
    asset_lookup = {a.id: a for a in assets}

    def windows(layer_batts: List[Battery]) -> List[List[Tuple[int, int]]]:
        rows: List[List[Tuple[int, int]]] = []
        for s in spawns:
            row: List[Tuple[int, int]] = []
            for b in layer_batts:
                w = compute_engagement_window(s, b, assets, max_alt_km=max_alt_km)
                row.append((int(w[0]), int(w[1])) if w is not None else (-1, -1))
            rows.append(row)
        return rows

    u_w = windows(upper)
    l_w = windows(lower)

    def fmt_2d(rows: List[List[Tuple[int, int]]], idx: int) -> str:
        outer = ", ".join(
            "{" + ", ".join(str(r[i][idx]) for i in range(len(r))) + "}"
            for r in rows
        )
        return "{ " + outer + " }"

    appear = [int(round(s.launch_time)) for s in spawns]
    impacts: List[int] = []
    for s in spawns:
        target = asset_lookup[s.target_asset_id]
        horiz = math.hypot(target.position[0] - s.launch_position[0],
                           target.position[1] - s.launch_position[1])
        impacts.append(int(math.ceil(s.launch_time + horiz / s.speed)))

    lines = [
        f"// auto-generated from random_saturation_scenario(seed={seed}, n_threats={n_threats})",
        f"const int MAXT             = {n_threats};",
        f"const int NB_U             = {len(upper)};",
        f"const int NB_L             = {len(lower)};",
        "const int CH_PER_U[NB_U]   = "
            f"{{ {', '.join(str(b.fire_control_channels) for b in upper)} }};",
        "const int CH_PER_L[NB_L]   = "
            f"{{ {', '.join(str(b.fire_control_channels) for b in lower)} }};",
        "const int AMMO0_U[NB_U]    = "
            f"{{ {', '.join(str(b.available_missiles) for b in upper)} }};",
        "const int AMMO0_L[NB_L]    = "
            f"{{ {', '.join(str(b.available_missiles) for b in lower)} }};",
        f"const int APPEAR[MAXT]    = {{ {', '.join(map(str, appear))} }};",
        f"const int IMPACT_AT[MAXT] = {{ {', '.join(map(str, impacts))} }};",
        f"const int U_ENTER[MAXT][NB_U] = {fmt_2d(u_w, 0)};",
        f"const int U_EXIT [MAXT][NB_U] = {fmt_2d(u_w, 1)};",
        f"const int L_ENTER[MAXT][NB_L] = {fmt_2d(l_w, 0)};",
        f"const int L_EXIT [MAXT][NB_L] = {fmt_2d(l_w, 1)};",
    ]
    return "\n".join(lines)


def dump_uppaal_pk(
    seed: Optional[int] = 42,
    n_threats: int = 3,
) -> str:
    """Render per-(threat, battery) Pk as the const arrays that v4 expects.

    Pk is rendered as an integer percentage (Pk * 100) because UPPAAL has no
    floats.  The simple model below uses each battery's base_pk * 100 for
    every threat -- replace with a more sophisticated lookup if your scenario
    needs per-threat Pk variance.
    """
    assets, batteries, spawns = random_saturation_scenario(
        seed=seed, n_threats=n_threats)
    upper = [b for b in batteries if b.layer == "UPPER"]
    lower = [b for b in batteries if b.layer == "LOWER"]

    def fmt_2d_pk(layer_batts: List[Battery]) -> str:
        rows = [
            "{" + ", ".join(str(int(round(b.base_pk * 100))) for b in layer_batts) + "}"
            for _ in range(n_threats)
        ]
        return "{ " + ", ".join(rows) + " }"

    return "\n".join([
        f"const int PK_U[MAXT][NB_U] = {fmt_2d_pk(upper)};",
        f"const int PK_L[MAXT][NB_L] = {fmt_2d_pk(lower)};",
    ])


def dump_uppaal_system(
    seed: Optional[int] = 42,
    n_threats: int = 3,
) -> str:
    """Render the v4 ``<system>`` block with one Slot_U / Slot_L per channel.

    Multiplies each battery's fire_control_channels by an instance with the
    correct batt_id so the model gets the exact channel-pool sizes the ROS2
    scenario uses.  Drop this into ``dwta_model_v4_salvo_pk.xml``'s
    ``<system>`` element.
    """
    assets, batteries, spawns = random_saturation_scenario(
        seed=seed, n_threats=n_threats)
    upper = [b for b in batteries if b.layer == "UPPER"]
    lower = [b for b in batteries if b.layer == "LOWER"]

    lines: List[str] = []
    lines.append(", ".join(f"R{i} = Radar({i})" for i in range(n_threats)) + ";")
    lines.append(", ".join(f"T{i} = Threat({i})" for i in range(n_threats)) + ";")
    su_names: List[str] = []
    for b_idx, b in enumerate(upper):
        for ch in range(b.fire_control_channels):
            name = f"SU{b_idx}_{ch}"
            su_names.append(name)
            lines.append(f"{name} = Slot_U({b_idx});")
    sl_names: List[str] = []
    for b_idx, b in enumerate(lower):
        for ch in range(b.fire_control_channels):
            name = f"SL{b_idx}_{ch}"
            sl_names.append(name)
            lines.append(f"{name} = Slot_L({b_idx});")
    lines.append("P = Planner();")

    system_parts = (
        [f"R{i}" for i in range(n_threats)]
        + [f"T{i}" for i in range(n_threats)]
        + su_names
        + sl_names
        + ["P"]
    )
    lines.append("system " + ", ".join(system_parts) + ";")
    return "\n".join(lines)
