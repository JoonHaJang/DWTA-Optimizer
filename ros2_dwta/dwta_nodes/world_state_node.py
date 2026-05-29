"""통합 상황도(Common Operational Picture) 노드.

모든 토픽(/tracks, /threat_scores, /engagement_matrix, /interceptor_status,
/events)을 집계해 적 탄도탄과 아군 요격탄의 통합 상태를 만들고, 래치(latched)
토픽 /world_state 로 전 노드에 공유한다. 이벤트 발생 시 즉시, 그리고 주기적으로
스냅샷을 발행하므로 어느 노드든 동일한 상황 인식을 갖는다.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List

from .messages import (BatteryState, EngagementMatrix, Event, EV_DETECTED,
                       EV_IMPACT, EV_INTERCEPT, InterceptorStatus, ThreatScores,
                       ThreatState, TrackArray, WorldState)
from .ros_compat import Node, latched_qos


class WorldStateNode(Node):
    PERIOD = 0.5  # 2 Hz 스냅샷

    def __init__(self) -> None:
        super().__init__("world_state_node")
        self._threats: Dict[str, dict] = {}        # threat_id -> partial state
        self._danger: Dict[str, float] = {}
        self._engageable: set = set()
        self._batteries: Dict[str, BatteryState] = {}
        self._covered: set = set()
        self._events: Deque[Event] = deque(maxlen=12)
        self.sim_t = 0.0

        self._pub = self.create_publisher(WorldState, "/world_state", latched_qos())
        self.create_subscription(TrackArray, "/tracks", self._on_tracks, 10)
        self.create_subscription(ThreatScores, "/threat_scores", self._on_scores, 10)
        self.create_subscription(EngagementMatrix, "/engagement_matrix", self._on_matrix, 10)
        self.create_subscription(InterceptorStatus, "/interceptor_status", self._on_status, 10)
        self.create_subscription(Event, "/events", self._on_event, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_tracks(self, msg: TrackArray) -> None:
        self.sim_t = msg.stamp
        seen = set()
        for tr in msg.tracks:
            seen.add(tr.threat_id)
            self._threats[tr.threat_id] = {
                "target": tr.target_asset_id,
                "pos": tr.position,
                "tta": tr.time_to_impact,
            }
        # 더 이상 보이지 않는(제거/탄착) 위협 정리
        for tid in list(self._threats):
            if tid not in seen:
                self._threats.pop(tid, None)

    def _on_scores(self, msg: ThreatScores) -> None:
        for s in msg.scores:
            self._danger[s.threat_id] = s.danger

    def _on_matrix(self, msg: EngagementMatrix) -> None:
        self._engageable = {c.threat_id for c in msg.cells}

    def _on_status(self, msg: InterceptorStatus) -> None:
        covered = set()
        for sid, threats in msg.engaging.items():
            covered.update(threats)
        covered.update(i.target_threat_id for i in msg.in_flight)
        self._covered = covered
        in_flight_count: Dict[str, int] = {}
        for i in msg.in_flight:
            in_flight_count[i.system_id] = in_flight_count.get(i.system_id, 0) + 1
        # battery layer는 첫 관측 시 보존
        layers = {sid: bs.layer for sid, bs in self._batteries.items()}
        self._batteries = {
            sid: BatteryState(
                system_id=sid, layer=layers.get(sid, "?"),
                available=avail, in_flight=in_flight_count.get(sid, 0),
                engaging=list(msg.engaging.get(sid, [])))
            for sid, avail in msg.available.items()
        }

    def set_battery_layers(self, layers: Dict[str, str]) -> None:
        """정적 레이어 정보 주입 (UPPER/LOWER 표시용)."""
        for sid, layer in layers.items():
            self._batteries.setdefault(sid, BatteryState(sid, layer, 0, 0, []))
            self._batteries[sid].layer = layer

    def _on_event(self, ev: Event) -> None:
        self._events.append(ev)
        if ev.kind in (EV_INTERCEPT, EV_IMPACT):
            self._danger.pop(ev.threat_id, None)
            self._engageable.discard(ev.threat_id)
        if ev.kind in (EV_DETECTED, EV_INTERCEPT, EV_IMPACT):
            self._publish()  # 이벤트 발생 즉시 공유

    def _lifecycle(self, tid: str) -> str:
        if tid in self._covered:
            return "ENGAGED"
        if tid in self._engageable:
            return "ENGAGEABLE"
        if tid in self._danger:
            return "ASSESSED"
        return "DETECTED"

    def _build(self) -> WorldState:
        threats: List[ThreatState] = []
        for tid, st in self._threats.items():
            threats.append(ThreatState(
                threat_id=tid, target_asset_id=st["target"], position=st["pos"],
                time_to_impact=st["tta"], danger=self._danger.get(tid, 0.0),
                lifecycle=self._lifecycle(tid),
                assigned_systems=[b.system_id for b in self._batteries.values()
                                  if tid in b.engaging]))
        return WorldState(stamp=self.sim_t, threats=threats,
                          batteries=list(self._batteries.values()),
                          recent_events=list(self._events))

    def _publish(self) -> None:
        self._pub.publish(self._build())

    def _tick(self) -> None:
        ws = self._build()
        self._publish()
        active = ", ".join(f"{t.threat_id}:{t.lifecycle}" for t in ws.threats) or "-"
        ammo = " ".join(f"{b.system_id}({b.available}탄/{b.in_flight}비행)"
                        for b in ws.batteries)
        self.get_logger().info(f"[COP] 위협[{active}] | 포대 {ammo}")
