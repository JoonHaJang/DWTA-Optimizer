"""포대 사격통제레이다 노드 (Fire-Control Radar, FCR) — 요격탄 유도용.

포대마다 1개. 자기 포대의 발사(LAUNCH) 이벤트를 받아 요격탄을 유도(guidance
channel 점유)하고, 비행시간 경과 시 요격 성공/실패를 판정(결정적: Pk>=θ)해
이벤트(/events: INTERCEPT|MISS)와 채널 현황(/fire_control_status)을 공유한다.

유도 채널 수(fire_control_channels)가 곧 그 포대의 동시 교전 한계다.
"""
from __future__ import annotations

from typing import List

from .messages import (Event, EV_INTERCEPT, EV_LAUNCH, EV_MISS,
                       FireControlStatus, RadarStatus)
from .ros_compat import Node
from .scenario import Battery


class FireControlRadarNode(Node):
    PERIOD = 0.1          # 10 Hz
    HIT_THRESHOLD = 0.5   # pk 임계 (결정적 판정)

    def __init__(self, battery: Battery):
        super().__init__(f"fcr_{battery.id.lower()}")
        self._bid = battery.id
        self._channels = battery.fire_control_channels
        self._flyout = battery.interceptor_flyout
        self._guiding: List[dict] = []   # {interceptor_id, threat_id, pk, t_resolve}
        self.sim_t = 0.0

        self._ev_pub = self.create_publisher(Event, "/events", 10)
        self._fc_pub = self.create_publisher(FireControlStatus, "/fire_control_status", 10)
        self.create_subscription(Event, "/events", self._on_event, 10)
        self.create_subscription(RadarStatus, "/radar_status", self._on_clock, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_clock(self, st: RadarStatus) -> None:
        self.sim_t = st.stamp

    def _on_event(self, ev: Event) -> None:
        # 자기 포대 발사 -> 유도 시작 (채널 점유)
        if ev.kind == EV_LAUNCH and ev.system_id == self._bid:
            self.sim_t = ev.stamp
            self._guiding.append({
                "interceptor_id": ev.interceptor_id, "threat_id": ev.threat_id,
                "pk": ev.pk, "t_resolve": ev.stamp + self._flyout})
            self.get_logger().info(
                f"유도 개시: {ev.interceptor_id} -> {ev.threat_id} "
                f"(채널 {len(self._guiding)}/{self._channels})")

    def _resolve(self) -> None:
        still: List[dict] = []
        for g in self._guiding:
            if self.sim_t + 1e-9 < g["t_resolve"]:
                still.append(g)
                continue
            hit = g["pk"] >= self.HIT_THRESHOLD
            kind = EV_INTERCEPT if hit else EV_MISS
            self._ev_pub.publish(Event(
                stamp=self.sim_t, kind=kind, threat_id=g["threat_id"],
                system_id=self._bid, interceptor_id=g["interceptor_id"], pk=g["pk"]))
            self.get_logger().info(
                f"{'요격성공' if hit else '요격실패(재교전)'}: "
                f"{g['interceptor_id']} -> {g['threat_id']}")
        self._guiding = still

    def _tick(self) -> None:
        self._resolve()
        self._fc_pub.publish(FireControlStatus(
            stamp=self.sim_t, system_id=self._bid, total_channels=self._channels,
            busy_channels=len(self._guiding),
            locked_threats=[g["threat_id"] for g in self._guiding]))
