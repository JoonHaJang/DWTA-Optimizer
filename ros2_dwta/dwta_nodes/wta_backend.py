"""Pluggable Weapon-Target Assignment (WTA) backends for planning_node.

The PoC default is a transparent greedy WTA (`GreedyWTA`) so the pipeline always
produces visible, sensible assignments. The project's existing optimizers
(greedy_optimizer.GreedyOptimizer, ga_optimizer, clean_slate_optimizer) plug in
by implementing the same `solve(...)` signature -- see `LegacyGreedyAdapter` for
the wiring seam.
"""
from __future__ import annotations

from typing import Dict, List

from .messages import Assignment, EngagementCell, ThreatScore


class WTABackend:
    """Interface: rank threats, assign feasible (system, threat) pairs."""

    name = "base"

    def solve(self, scores: List[ThreatScore], cells: List[EngagementCell],
              available: Dict[str, int], max_per_threat: int) -> List[Assignment]:
        raise NotImplementedError


class GreedyWTA(WTABackend):
    """Danger-first greedy with layer + capacity + ammo + multi-battery balancing.

    - Threats handled in descending danger order.
    - Each threat gets at most one battery PER LAYER (no two same-layer batteries
      on the same threat -> conflict-free across multiple L-SAMs / M-SAMs),
      capped by `max_per_threat` layers (multi-layer defence).
    - Among same-layer batteries that can engage a threat, picks by (Pk, then
      least-loaded) so load spreads across batteries instead of piling on one.
    - Respects each battery's fire-control channels (simultaneous) and ammo.
    """

    name = "GreedyWTA"

    def __init__(self, simultaneous: Dict[str, int]):
        self._simultaneous = dict(simultaneous)  # system_id -> max concurrent (FCR channels)

    def solve(self, scores, cells, available, max_per_threat):
        # feasible cells grouped by (threat, layer) -> candidate batteries
        by_tl: Dict[tuple, List[EngagementCell]] = {}
        for c in cells:
            by_tl.setdefault((c.threat_id, c.layer), []).append(c)

        remaining = dict(available)                 # ammo left
        used = {sid: 0 for sid in available}        # concurrent engagements this plan
        assignments: List[Assignment] = []

        for s in sorted(scores, key=lambda x: x.danger, reverse=True):
            layers_done = 0
            # 위협당 레이어 우선순위: 더 높은 최선 Pk 레이어 먼저
            layers = sorted(
                {c.layer for c in cells if c.threat_id == s.threat_id},
                key=lambda L: -max((c.pk for c in by_tl.get((s.threat_id, L), [])), default=0))
            for layer in layers:
                if layers_done >= max_per_threat:
                    break
                cands = by_tl.get((s.threat_id, layer), [])
                # 동일 레이어 후보 포대 중: 잔여탄>0, 채널 여유 -> (Pk 우선, 부하 적은 순)
                feasible = [c for c in cands
                            if remaining.get(c.system_id, 0) > 0
                            and used.get(c.system_id, 0) < self._simultaneous.get(c.system_id, 1)]
                if not feasible:
                    continue
                best = min(feasible, key=lambda c: (-round(c.pk * 20), used.get(c.system_id, 0)))
                assignments.append(Assignment(best.system_id, best.threat_id, best.layer, best.pk))
                remaining[best.system_id] -= 1
                used[best.system_id] += 1
                layers_done += 1
        return assignments

    @staticmethod
    def objective(assignments: List[Assignment], scores: List[ThreatScore]) -> float:
        """Expected protected value: sum over threats of danger * (1 - Π(1-pk))."""
        danger = {s.threat_id: s.danger for s in scores}
        by_threat: Dict[str, List[float]] = {}
        for a in assignments:
            by_threat.setdefault(a.threat_id, []).append(a.pk)
        total = 0.0
        for tid, pks in by_threat.items():
            kill = 1.0
            for p in pks:
                kill *= (1.0 - p)
            total += danger.get(tid, 0.0) * (1.0 - kill)
        return total


class LegacyGreedyAdapter(WTABackend):
    """Seam for the existing greedy_optimizer.GreedyOptimizer.

    Not used by default: the legacy optimizer is tightly coupled to config_mip
    battery-spec dicts and an EnhancedEngagementMatrix. To enable it, construct
    the `batteries` dicts + intercept-probability map it expects and translate
    its `upper_assignments`/`lower_assignments` result back into `Assignment`s.
    Kept here to document the integration point for GA / Clean-Slate / MIP too.
    """

    name = "LegacyGreedy(disabled)"

    def solve(self, scores, cells, available, max_per_threat):  # pragma: no cover
        raise NotImplementedError(
            "Wire greedy_optimizer.GreedyOptimizer here (see docstring)."
        )
