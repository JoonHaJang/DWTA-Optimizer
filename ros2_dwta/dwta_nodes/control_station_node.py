"""통제소 노드 — 방어정책 발행 (전시/평시, 단발/연속, 위협당 최대 요격탄)."""
from __future__ import annotations

from .messages import DefensePolicy
from .ros_compat import Node


class ControlStationNode(Node):
    PERIOD = 1.0  # 1 Hz

    def __init__(self, posture: str = "WARTIME",
                 fire_doctrine: str = "SHOOT_LOOK_SHOOT",
                 max_interceptors_per_threat: int = 2):
        super().__init__("control_station_node")
        self._posture = posture
        self._doctrine = fire_doctrine
        self._max = max_interceptors_per_threat
        self.sim_t = 0.0
        self._pub = self.create_publisher(DefensePolicy, "/policy", 10)
        self.create_timer(self.PERIOD, self._tick)

    def _tick(self) -> None:
        self.sim_t = round(self.sim_t + self.PERIOD, 6)
        self._pub.publish(DefensePolicy(
            stamp=self.sim_t, posture=self._posture, fire_doctrine=self._doctrine,
            max_interceptors_per_threat=self._max))
