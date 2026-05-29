"""중앙 감시레이다 노드 (Surveillance Radar) — 탐지/추적/표적할당용.

전구 단위 1개. 적 탄도탄을 탐지·추적하고 추적정보(/tracks)를 발행한다(월드 truth
보유). 통합 이벤트(/events)의 요격성공(INTERCEPT)으로 위협을 제거하고, 탐지
(DETECTED)·탄착(IMPACT) 이벤트를 발행한다. 요격탄 유도는 포대 사격통제레이다 담당.
"""
from __future__ import annotations

from typing import Dict, List

from .messages import (BallisticTrack, Event, EV_DETECTED, EV_IMPACT,
                       EV_INTERCEPT, RadarStatus, TrackArray)
from .ros_compat import Node
from .scenario import Asset, Battery, ThreatSpawn, distance, velocity_toward


class SurveillanceRadarNode(Node):
    PERIOD = 0.1  # 10 Hz

    def __init__(self, assets: List[Asset], batteries: List[Battery],
                 spawns: List[ThreatSpawn]):
        super().__init__("surveillance_radar_node")
        self._assets = {a.id: a for a in assets}
        self._spawns = list(spawns)
        self._spawned: set = set()
        self._threats: Dict[str, dict] = {}
        self._killed: set = set()
        self.sim_t = 0.0

        self._track_pub = self.create_publisher(TrackArray, "/tracks", 10)
        self._status_pub = self.create_publisher(RadarStatus, "/radar_status", 10)
        self._ev_pub = self.create_publisher(Event, "/events", 10)
        self.create_subscription(Event, "/events", self._on_event, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_event(self, ev: Event) -> None:
        if ev.kind == EV_INTERCEPT:
            self._killed.add(ev.threat_id)

    def _spawn_due(self) -> None:
        for sp in self._spawns:
            if sp.threat_id in self._spawned or self.sim_t < sp.launch_time:
                continue
            asset = self._assets[sp.target_asset_id]
            vel = velocity_toward(sp.launch_position, asset.position, sp.speed)
            self._threats[sp.threat_id] = {
                "target": sp.target_asset_id, "pos": list(sp.launch_position),
                "vel": vel, "launch_pos": sp.launch_position}
            self._spawned.add(sp.threat_id)
            self._ev_pub.publish(Event(stamp=self.sim_t, kind=EV_DETECTED,
                                       threat_id=sp.threat_id, detail=sp.target_asset_id))
            self.get_logger().info(f"탐지: {sp.threat_id} -> {sp.target_asset_id} 발사 포착")

    def _tick(self) -> None:
        self.sim_t = round(self.sim_t + self.PERIOD, 6)
        self._spawn_due()
        tracks: List[BallisticTrack] = []
        for tid in list(self._threats):
            if tid in self._killed:
                self.get_logger().info(f"요격 확인: {tid} 제거")
                del self._threats[tid]
                continue
            st = self._threats[tid]
            st["pos"][0] += st["vel"][0] * self.PERIOD
            st["pos"][1] += st["vel"][1] * self.PERIOD
            asset = self._assets[st["target"]]
            d = distance(tuple(st["pos"]), asset.position)
            speed = (st["vel"][0] ** 2 + st["vel"][1] ** 2) ** 0.5 or 1.0
            tta = d / speed
            if d <= 1.0:
                self._ev_pub.publish(Event(stamp=self.sim_t, kind=EV_IMPACT,
                                           threat_id=tid, detail=st["target"]))
                self.get_logger().info(f"!! 탄착: {tid} -> {st['target']} 방어 실패")
                del self._threats[tid]
                continue
            tracks.append(BallisticTrack(
                threat_id=tid, target_asset_id=st["target"], position=tuple(st["pos"]),
                velocity=st["vel"], launch_position=st["launch_pos"],
                time_to_impact=tta, stamp=self.sim_t))
        self._track_pub.publish(TrackArray(stamp=self.sim_t, tracks=tracks))
        self._status_pub.publish(RadarStatus(stamp=self.sim_t, detecting=True,
                                             n_tracks=len(tracks)))

    @property
    def done(self) -> bool:
        return len(self._spawned) == len(self._spawns) and not self._threats
