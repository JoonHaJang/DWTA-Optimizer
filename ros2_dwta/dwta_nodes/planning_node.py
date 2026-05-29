"""Planning node -- DWTA engagement-plan generator.

Subscribes to /threat_scores, /engagement_matrix, /policy, /interceptor_status,
/events, /tracks, and publishes /engagement_plan.  The WTA backend is the
project's canonical optimizer: clean_slate_optimizer.CleanSlateOptimizer
(MIP/HiGHS) wrapped in CleanSlateAdapter.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import (Assignment, BallisticTrack, DefensePolicy,
                       EngagementMatrix, EngagementPlan, Event, EV_IMPACT,
                       EV_INTERCEPT, InterceptorStatus, ThreatScores,
                       TrackArray)
from .ros_compat import Node
from .scenario import Asset, Battery
from .wta_backend import CleanSlateAdapter, WTABackend, WTAInput


class PlanningNode(Node):
    PERIOD = 0.5  # 2 Hz

    def __init__(self, batteries: List[Battery],
                 assets: Optional[List[Asset]] = None,
                 backend: Optional[WTABackend] = None) -> None:
        super().__init__("planning_node")
        # Default backend: project's canonical CleanSlateOptimizer.
        # Construction does a lazy import of clean_slate_optimizer; failure
        # surfaces as a clear error rather than silently switching to a stub.
        self._backend: WTABackend = backend or CleanSlateAdapter()
        self._batteries: List[Battery] = list(batteries)
        self._assets: List[Asset] = list(assets or [])
        self._available: Dict[str, int] = {b.id: b.available_missiles for b in batteries}
        self._layer: Dict[str, str] = {b.id: b.layer for b in batteries}
        self._scores: Optional[ThreatScores] = None
        self._matrix: Optional[EngagementMatrix] = None
        self._policy = DefensePolicy(stamp=0.0)
        self._tracks: Dict[str, BallisticTrack] = {}
        self._covered: set = set()    # (threat_id, layer) -- in-flight or engaging
        self._terminal: set = set()   # threat ids that hit Killed or Leaked

        self._pub = self.create_publisher(EngagementPlan, "/engagement_plan", 10)
        self.create_subscription(ThreatScores, "/threat_scores", self._on_scores, 10)
        self.create_subscription(EngagementMatrix, "/engagement_matrix", self._on_matrix, 10)
        self.create_subscription(DefensePolicy, "/policy", self._on_policy, 10)
        self.create_subscription(InterceptorStatus, "/interceptor_status", self._on_status, 10)
        self.create_subscription(Event, "/events", self._on_event, 10)
        self.create_subscription(TrackArray, "/tracks", self._on_tracks, 10)
        self.create_timer(self.PERIOD, self._tick)

    # ---- callbacks --------------------------------------------------------
    def _on_event(self, ev: Event) -> None:
        if ev.kind in (EV_INTERCEPT, EV_IMPACT):
            self._terminal.add(ev.threat_id)

    def _on_scores(self, msg: ThreatScores) -> None: self._scores = msg
    def _on_matrix(self, msg: EngagementMatrix) -> None: self._matrix = msg
    def _on_policy(self, msg: DefensePolicy) -> None: self._policy = msg

    def _on_tracks(self, msg: TrackArray) -> None:
        seen = set()
        for tr in msg.tracks:
            seen.add(tr.threat_id)
            self._tracks[tr.threat_id] = tr
        # drop stale tracks (the radar has dropped them)
        for tid in list(self._tracks):
            if tid not in seen:
                self._tracks.pop(tid, None)

    def _on_status(self, msg: InterceptorStatus) -> None:
        if msg.available:
            self._available.update(msg.available)
        covered = set()
        for sid, threats in msg.engaging.items():
            layer = self._layer.get(sid, "?")
            for t in threats:
                covered.add((t, layer))
        for i in msg.in_flight:
            covered.add((i.target_threat_id, i.layer))
        self._covered = covered

    # ---- main loop --------------------------------------------------------
    def _tick(self) -> None:
        if self._scores is None or self._matrix is None:
            return

        # Filter terminal threats out and already-covered (threat, layer) cells.
        # MISS leaves both sets untouched, so re-engagement happens automatically.
        scores = [s for s in self._scores.scores if s.threat_id not in self._terminal]
        cells = [c for c in self._matrix.cells
                 if c.threat_id not in self._terminal
                 and (c.threat_id, c.layer) not in self._covered]
        if not scores or not cells:
            return

        # Tracks supply geometry (position, launch_position, TTA) the optimizer needs.
        # Skip threats we have no track for -- the optimizer can't reason about them.
        scores = [s for s in scores if s.threat_id in self._tracks]
        cells = [c for c in cells if c.threat_id in self._tracks]
        if not scores or not cells:
            return

        wta_in = WTAInput(
            scores=scores,
            cells=cells,
            tracks=dict(self._tracks),
            assets=self._assets,
            batteries=self._batteries,
            available=dict(self._available),
            max_per_threat=self._policy.max_interceptors_per_threat,
        )

        assignments: List[Assignment] = self._backend.solve(wta_in)
        if not assignments:
            return

        obj = CleanSlateAdapter.objective(assignments, scores)
        self._pub.publish(EngagementPlan(
            stamp=self._matrix.stamp,
            assignments=assignments,
            objective_value=round(obj, 4),
            solver=self._backend.name,
        ))
        plan = ", ".join(
            f"{a.system_id}->{a.threat_id}({a.layer} Pk{a.pk:.2f})" for a in assignments
        )
        self.get_logger().info(f"교전계획[{self._backend.name}] obj={obj:.2f}: {plan}")
