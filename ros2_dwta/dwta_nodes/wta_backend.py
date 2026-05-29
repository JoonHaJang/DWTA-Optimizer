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
    """Danger-first greedy with layer + capacity + ammo constraints.

    - Threats handled in descending danger order.
    - Each threat may get at most one UPPER and one LOWER interceptor
      (multi-layer defence), capped by `max_per_threat`.
    - Respects each battery's simultaneous-engagement capacity and remaining
      ammo. Picks the highest-Pk feasible battery for each (threat, layer).
    """

    name = "GreedyWTA"

    def __init__(self, simultaneous: Dict[str, int]):
        self._simultaneous = dict(simultaneous)  # system_id -> max concurrent

    def solve(self, scores, cells, available, max_per_threat):
        # index feasible cells by threat
        by_threat: Dict[str, List[EngagementCell]] = {}
        for c in cells:
            by_threat.setdefault(c.threat_id, []).append(c)

        remaining = dict(available)                 # ammo left
        used = {sid: 0 for sid in available}        # concurrent engagements this plan
        assignments: List[Assignment] = []

        for s in sorted(scores, key=lambda x: x.danger, reverse=True):
            options = by_threat.get(s.threat_id, [])
            if not options:
                continue
            picked_layers = set()
            # best Pk first
            for cell in sorted(options, key=lambda c: c.pk, reverse=True):
                if len(picked_layers) >= max_per_threat:
                    break
                if cell.layer in picked_layers:
                    continue
                if remaining.get(cell.system_id, 0) <= 0:
                    continue
                if used.get(cell.system_id, 0) >= self._simultaneous.get(cell.system_id, 1):
                    continue
                assignments.append(Assignment(cell.system_id, cell.threat_id, cell.layer, cell.pk))
                remaining[cell.system_id] -= 1
                used[cell.system_id] += 1
                picked_layers.add(cell.layer)
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
