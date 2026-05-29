"""발사대/요격체계 노드 — 교전계획 실행 + 요격탄 비행/판정.

교전계획(/engagement_plan)을 받아 요격탄을 발사하고, 비행중 요격탄을 추적하다
비행시간(flyout) 경과 시 결정적으로 요격 성공/실패를 판정한다. 결과는 통합
이벤트(/events)와 요격체계 상태(/interceptor_status, 비행중 요격탄 포함)로 공유한다.

요격 판정(결정적·재현가능): pk >= HIT_THRESHOLD 이면 HIT, 아니면 MISS.
MISS 위협은 계속 비행 -> 더 가까이서(높은 Pk) 또는 하층에서 재교전(SLS 교리).
"""
from __future__ import annotations

from typing import Dict, List

from .messages import (Event, EV_INTERCEPT, EV_LAUNCH, EV_MISS, Interceptor,
                       EngagementPlan, InterceptorStatus, RadarStatus)
from .ros_compat import Node
from .scenario import Battery


class LauncherNode(Node):
    PERIOD = 0.2          # 5 Hz status
    FLYOUT = 2.0          # 요격탄 비행시간 (s)
    HIT_THRESHOLD = 0.5   # pk 임계 (결정적 판정)

    def __init__(self, batteries: List[Battery]):
        super().__init__("launcher_node")
        self._available = {b.id: b.available_missiles for b in batteries}
        self._in_flight: List[Interceptor] = []
        self._engaging: Dict[str, List[str]] = {b.id: [] for b in batteries}
        self._fired_seq = 0
        self.sim_t = 0.0

        self._ev_pub = self.create_publisher(Event, "/events", 10)
        self._st_pub = self.create_publisher(InterceptorStatus, "/interceptor_status", 10)
        self.create_subscription(EngagementPlan, "/engagement_plan", self._on_plan, 10)
        self.create_subscription(RadarStatus, "/radar_status", self._on_clock, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_clock(self, st: RadarStatus) -> None:
        self.sim_t = st.stamp

    def _on_plan(self, plan: EngagementPlan) -> None:
        self.sim_t = plan.stamp
        active_pairs = {(i.system_id, i.target_threat_id) for i in self._in_flight}
        for a in plan.assignments:
            if (a.system_id, a.threat_id) in active_pairs:
                continue
            if self._available.get(a.system_id, 0) <= 0:
                continue
            self._available[a.system_id] -= 1
            self._fired_seq += 1
            interceptor = Interceptor(
                interceptor_id=f"{a.system_id}#{self._fired_seq}",
                system_id=a.system_id, target_threat_id=a.threat_id, pk=a.pk,
                launch_time=plan.stamp, intercept_time=plan.stamp + self.FLYOUT)
            self._in_flight.append(interceptor)
            self._engaging[a.system_id].append(a.threat_id)
            self._ev_pub.publish(Event(
                stamp=plan.stamp, kind=EV_LAUNCH, threat_id=a.threat_id,
                system_id=a.system_id, interceptor_id=interceptor.interceptor_id,
                detail=f"Pk={a.pk}"))
            self.get_logger().info(
                f"발사: {interceptor.interceptor_id} -> {a.threat_id} "
                f"(Pk{a.pk}, 잔여탄 {self._available[a.system_id]})")
        self._publish_status(plan.stamp)

    def _resolve(self) -> None:
        """비행시간 경과한 요격탄 판정."""
        still: List[Interceptor] = []
        for itc in self._in_flight:
            if self.sim_t + 1e-9 < itc.intercept_time:
                still.append(itc)
                continue
            hit = itc.pk >= self.HIT_THRESHOLD
            itc.state = "HIT" if hit else "MISS"
            if itc.target_threat_id in self._engaging[itc.system_id]:
                self._engaging[itc.system_id].remove(itc.target_threat_id)
            kind = EV_INTERCEPT if hit else EV_MISS
            self._ev_pub.publish(Event(
                stamp=self.sim_t, kind=kind, threat_id=itc.target_threat_id,
                system_id=itc.system_id, interceptor_id=itc.interceptor_id))
            verdict = "요격성공" if hit else "요격실패(재교전 가능)"
            self.get_logger().info(f"{verdict}: {itc.interceptor_id} -> {itc.target_threat_id}")
        self._in_flight = still

    def _tick(self) -> None:
        self._resolve()
        self._publish_status(self.sim_t)

    def _publish_status(self, stamp: float) -> None:
        self._st_pub.publish(InterceptorStatus(
            stamp=stamp,
            available=dict(self._available),
            engaging={k: list(v) for k, v in self._engaging.items()},
            in_flight=list(self._in_flight),
        ))
