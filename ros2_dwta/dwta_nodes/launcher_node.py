"""발사대 노드 (Launcher) — 교전계획 실행(물리 발사 + 탄약).

교전계획(/engagement_plan)을 받아 요격탄을 발사한다. 발사 가능 조건은 두 자원의
동시 충족: (1) 발사대 잔여탄 > 0, (2) 포대 사격통제레이다의 유도 채널 여유
(해당 포대 비행중 요격탄 < fire_control_channels). 발사 후 유도·요격 판정은 포대
레이다(FCR)가 수행하며, 그 결과 이벤트(INTERCEPT/MISS)로 비행중 상태를 정리한다.
"""
from __future__ import annotations

from typing import Dict, List

from .messages import (Event, EV_INTERCEPT, EV_LAUNCH, EV_MISS, Interceptor,
                       EngagementPlan, InterceptorStatus, RadarStatus)
from .ros_compat import Node
from .scenario import Battery


class LauncherNode(Node):
    PERIOD = 0.2  # 5 Hz status

    def __init__(self, batteries: List[Battery]):
        super().__init__("launcher_node")
        self._available = {b.id: b.available_missiles for b in batteries}
        self._channels = {b.id: b.fire_control_channels for b in batteries}
        self._flyout = {b.id: b.interceptor_flyout for b in batteries}
        self._in_flight: List[Interceptor] = []
        self._engaging: Dict[str, List[str]] = {b.id: [] for b in batteries}
        self._fired_seq = 0
        self.sim_t = 0.0

        self._ev_pub = self.create_publisher(Event, "/events", 10)
        self._st_pub = self.create_publisher(InterceptorStatus, "/interceptor_status", 10)
        self.create_subscription(EngagementPlan, "/engagement_plan", self._on_plan, 10)
        self.create_subscription(Event, "/events", self._on_event, 10)
        self.create_subscription(RadarStatus, "/radar_status", self._on_clock, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_clock(self, st: RadarStatus) -> None:
        self.sim_t = st.stamp

    def _battery_inflight(self, bid: str) -> int:
        return sum(1 for i in self._in_flight if i.system_id == bid)

    def _on_plan(self, plan: EngagementPlan) -> None:
        self.sim_t = plan.stamp
        active = {(i.system_id, i.target_threat_id) for i in self._in_flight}
        for a in plan.assignments:
            if (a.system_id, a.threat_id) in active:
                continue
            if self._available.get(a.system_id, 0) <= 0:
                continue
            # 포대 레이다 유도 채널 여유 확인
            if self._battery_inflight(a.system_id) >= self._channels.get(a.system_id, 1):
                continue
            self._available[a.system_id] -= 1
            self._fired_seq += 1
            itc = Interceptor(
                interceptor_id=f"{a.system_id}#{self._fired_seq}", system_id=a.system_id,
                target_threat_id=a.threat_id, pk=a.pk, launch_time=plan.stamp,
                intercept_time=plan.stamp + self._flyout.get(a.system_id, 2.0),
                layer=a.layer)
            self._in_flight.append(itc)
            self._engaging[a.system_id].append(a.threat_id)
            self._ev_pub.publish(Event(
                stamp=plan.stamp, kind=EV_LAUNCH, threat_id=a.threat_id,
                system_id=a.system_id, interceptor_id=itc.interceptor_id, pk=a.pk))
            self.get_logger().info(
                f"발사: {itc.interceptor_id} -> {a.threat_id} "
                f"({a.layer} Pk{a.pk}, 잔여탄 {self._available[a.system_id]})")
        self._publish_status(plan.stamp)

    def _on_event(self, ev: Event) -> None:
        # FCR 판정 결과로 비행중 요격탄 정리
        if ev.kind in (EV_INTERCEPT, EV_MISS):
            self._in_flight = [i for i in self._in_flight
                               if i.interceptor_id != ev.interceptor_id]
            if ev.system_id in self._engaging and ev.threat_id in self._engaging[ev.system_id]:
                self._engaging[ev.system_id].remove(ev.threat_id)

    def _tick(self) -> None:
        self._publish_status(self.sim_t)

    def _publish_status(self, stamp: float) -> None:
        self._st_pub.publish(InterceptorStatus(
            stamp=stamp, available=dict(self._available),
            engaging={k: list(v) for k, v in self._engaging.items()},
            in_flight=list(self._in_flight)))
