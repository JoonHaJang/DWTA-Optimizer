"""OO계획 수립/전송 노드 — WTA 교전계획.

위협 점수(/threat_scores) + 교전 매트릭스(/engagement_matrix) + 방어정책
(/policy) + 요격체계 상태(/interceptor_status)를 종합해 WTA(Weapon-Target
Assignment)를 풀고 교전계획(/engagement_plan)을 전송한다. WTA 백엔드는 교체식
(GreedyWTA 기본; GA/Clean-Slate/MIP 어댑터 가능).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import (DefensePolicy, EngagementMatrix, EngagementPlan,
                       InterceptorStatus, ThreatScores)
from .ros_compat import Node
from .scenario import Battery
from .wta_backend import GreedyWTA, WTABackend


class PlanningNode(Node):
    PERIOD = 0.5  # 2 Hz

    def __init__(self, batteries: List[Battery], backend: Optional[WTABackend] = None):
        super().__init__("planning_node")
        self._backend = backend or GreedyWTA(
            {b.id: b.simultaneous_engagements for b in batteries})
        self._available = {b.id: b.available_missiles for b in batteries}
        self._scores: Optional[ThreatScores] = None
        self._matrix: Optional[EngagementMatrix] = None
        self._policy = DefensePolicy(stamp=0.0)
        self._engaged: set = set()  # threat_ids already covered (avoid re-fire)

        self._pub = self.create_publisher(EngagementPlan, "/engagement_plan", 10)
        self.create_subscription(ThreatScores, "/threat_scores", self._on_scores, 10)
        self.create_subscription(EngagementMatrix, "/engagement_matrix", self._on_matrix, 10)
        self.create_subscription(DefensePolicy, "/policy", self._on_policy, 10)
        self.create_subscription(InterceptorStatus, "/interceptor_status", self._on_status, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_scores(self, msg): self._scores = msg
    def _on_matrix(self, msg): self._matrix = msg
    def _on_policy(self, msg): self._policy = msg

    def _on_status(self, msg: InterceptorStatus) -> None:
        if msg.available:
            self._available.update(msg.available)
        for threats in msg.engaging.values():
            self._engaged.update(threats)

    def _tick(self) -> None:
        if self._scores is None or self._matrix is None:
            return
        # 이미 교전 중인 위협은 제외 (재할당 방지)
        scores = [s for s in self._scores.scores if s.threat_id not in self._engaged]
        cells = [c for c in self._matrix.cells if c.threat_id not in self._engaged]
        if not scores or not cells:
            return

        assignments = self._backend.solve(
            scores, cells, self._available, self._policy.max_interceptors_per_threat)
        if not assignments:
            return
        obj = GreedyWTA.objective(assignments, scores)
        for a in assignments:
            self._engaged.add(a.threat_id)
        self._pub.publish(EngagementPlan(
            stamp=self._matrix.stamp, assignments=assignments,
            objective_value=round(obj, 4), solver=self._backend.name))
        plan = ", ".join(f"{a.system_id}->{a.threat_id}(Pk{a.pk})" for a in assignments)
        self.get_logger().info(f"교전계획[{self._backend.name}] obj={obj:.2f}: {plan}")
