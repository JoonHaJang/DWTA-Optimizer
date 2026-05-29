"""OO 가능성 평가 노드 — 교전 가능성/명중률 매트릭스.

탄도탄 예상궤적(/tracks) + 요격체계 상태(/interceptor_status) + 정적 방어영역
(배터리 사양, 사전입력)으로부터 (요격체계, 탄도탄) 교전창과 명중률(Pk)을 계산해
/engagement_matrix 로 발행한다.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import (EngagementCell, EngagementMatrix, InterceptorStatus,
                       TrackArray)
from .ros_compat import Node
from .scenario import Battery, distance


class EngageabilityNode(Node):
    PERIOD = 0.2   # 5 Hz
    MIN_TTA = 3.0  # 최소 비행/요격 준비 시간 (s)
    MIN_PK = 0.5   # 이 명중률 미만이면 교전 보류 (가능성 평가 게이트)

    def __init__(self, batteries: List[Battery]):
        super().__init__("engageability_node")
        self._batteries = {b.id: b for b in batteries}
        self._available = {b.id: b.available_missiles for b in batteries}
        self._latest: Optional[TrackArray] = None

        self._pub = self.create_publisher(EngagementMatrix, "/engagement_matrix", 10)
        self.create_subscription(TrackArray, "/tracks", self._on_tracks, 10)
        self.create_subscription(InterceptorStatus, "/interceptor_status", self._on_status, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_tracks(self, msg: TrackArray) -> None:
        self._latest = msg

    def _on_status(self, msg: InterceptorStatus) -> None:
        if msg.available:
            self._available.update(msg.available)

    def _tick(self) -> None:
        if self._latest is None:
            return
        cells: List[EngagementCell] = []
        for tr in self._latest.tracks:
            if tr.time_to_impact < self.MIN_TTA:
                continue  # 교전창 닫힘
            for bid, b in self._batteries.items():
                if self._available.get(bid, 0) <= 0:
                    continue
                d = distance(b.position, tr.position)
                if d > b.engagement_range:
                    continue
                # 거리 기반 Pk 보정 (가까울수록 명중률↑)
                range_factor = max(0.4, 1.0 - 0.5 * d / b.engagement_range)
                pk = round(min(0.97, b.base_pk * range_factor), 4)
                if pk < self.MIN_PK:
                    continue  # 명중률 부족 -> 교전 보류 (더 가까운 창 대기)
                cells.append(EngagementCell(
                    system_id=bid, threat_id=tr.threat_id, layer=b.layer, pk=pk,
                    window_open=self._latest.stamp,
                    window_close=self._latest.stamp + tr.time_to_impact,
                ))
        self._pub.publish(EngagementMatrix(stamp=self._latest.stamp, cells=cells))
