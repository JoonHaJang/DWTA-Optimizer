"""OO평가 노드 — 위협 평가/점수화.

탄도탄 정보(/tracks) + 방어자산 정보(사전입력)를 받아 위협을 점수화하고
/threat_scores 로 발행한다. danger = 자산가치 / TTA (가치 높고 임박할수록 위험).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import ThreatScore, ThreatScores, TrackArray
from .ros_compat import Node
from .scenario import Asset


class ThreatAssessmentNode(Node):
    PERIOD = 0.2  # 5 Hz

    def __init__(self, assets: List[Asset]):
        super().__init__("threat_assessment_node")
        self._asset_value = {a.id: a.value for a in assets}
        self._latest: Optional[TrackArray] = None

        self._pub = self.create_publisher(ThreatScores, "/threat_scores", 10)
        self.create_subscription(TrackArray, "/tracks", self._on_tracks, 10)
        self.create_timer(self.PERIOD, self._tick)

    def _on_tracks(self, msg: TrackArray) -> None:
        self._latest = msg

    def _tick(self) -> None:
        if self._latest is None:
            return
        scores: List[ThreatScore] = []
        for tr in self._latest.tracks:
            value = self._asset_value.get(tr.target_asset_id, 1.0)
            danger = value / max(tr.time_to_impact, 1.0)
            scores.append(ThreatScore(
                threat_id=tr.threat_id, target_asset_id=tr.target_asset_id,
                danger=round(danger, 4), time_to_impact=tr.time_to_impact,
            ))
        self._pub.publish(ThreatScores(stamp=self._latest.stamp, scores=scores))
