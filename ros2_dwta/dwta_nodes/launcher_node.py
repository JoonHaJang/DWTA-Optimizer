"""발사대/요격체계 노드 — 교전계획 실행.

교전계획(/engagement_plan)을 받아 유도탄을 발사하고(잔여탄 차감), 발사 이벤트
(/launch_events)와 요격체계 상태(/interceptor_status)를 발행한다.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import (EngagementPlan, InterceptorStatus, LaunchEvent)
from .ros_compat import Node
from .scenario import Battery


class LauncherNode(Node):
    PERIOD = 0.2  # 5 Hz status

    def __init__(self, batteries: List[Battery]):
        super().__init__("launcher_node")
        self._available = {b.id: b.available_missiles for b in batteries}
        self._engaging: Dict[str, List[str]] = {b.id: [] for b in batteries}
        self._fired: set = set()  # (system_id, threat_id) dedup
        self.sim_t = 0.0

        self._le_pub = self.create_publisher(LaunchEvent, "/launch_events", 10)
        self._st_pub = self.create_publisher(InterceptorStatus, "/interceptor_status", 10)
        self.create_subscription(EngagementPlan, "/engagement_plan", self._on_plan, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_plan(self, plan: EngagementPlan) -> None:
        self.sim_t = plan.stamp
        for a in plan.assignments:
            key = (a.system_id, a.threat_id)
            if key in self._fired or self._available.get(a.system_id, 0) <= 0:
                continue
            self._available[a.system_id] -= 1
            self._engaging[a.system_id].append(a.threat_id)
            self._fired.add(key)
            self._le_pub.publish(LaunchEvent(
                stamp=plan.stamp, system_id=a.system_id, threat_id=a.threat_id, pk=a.pk))
            self.get_logger().info(
                f"발사: {a.system_id} -> {a.threat_id} (잔여탄 {self._available[a.system_id]})")
        self._publish_status(plan.stamp)

    def _tick(self) -> None:
        self._publish_status(self.sim_t)

    def _publish_status(self, stamp: float) -> None:
        self._st_pub.publish(InterceptorStatus(
            stamp=stamp,
            available=dict(self._available),
            engaging={k: list(v) for k, v in self._engaging.items()},
        ))
