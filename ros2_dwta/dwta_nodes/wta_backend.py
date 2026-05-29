"""DWTA backend for planning_node.

The project mandates a single canonical optimizer: **CleanSlateOptimizer**
(clean_slate_optimizer.py -- log-linear MIP via HiGHS direct API).  The earlier
in-house GreedyWTA / GA / LegacyGreedy stubs were removed.  CleanSlateAdapter
performs the same bookkeeping the GUI's _prepare_optimizer_inputs does:

    ros2 ThreatScore + BallisticTrack -> clean_slate_optimizer.Threat
    ros2 Asset                        -> clean_slate_optimizer.Asset
    ros2 Battery                      -> clean_slate_optimizer.InterceptorSystem
                                       + raw `batteries` dict that
                                         clean_slate_optimizer.build_problem
                                         requires

so PlanningNode can hand the whole WTAInput bundle to .solve() and get
List[Assignment] in the ROS2 layer's own message shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .messages import Assignment, BallisticTrack, EngagementCell, ThreatScore
from .scenario import Asset, Battery


# ---------------------------------------------------------------------------
# Input bundle
# ---------------------------------------------------------------------------
@dataclass
class WTAInput:
    """Bundle of state passed to a WTABackend.solve()."""
    scores: List[ThreatScore]
    cells: List[EngagementCell]
    tracks: Dict[str, BallisticTrack]   # threat_id -> latest BallisticTrack
    assets: List[Asset]
    batteries: List[Battery]
    available: Dict[str, int]            # current ammo from /interceptor_status
    max_per_threat: int = 2


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class WTABackend:
    """Single canonical interface used by PlanningNode."""

    name = "base"

    def solve(self, wta_in: WTAInput) -> List[Assignment]:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CleanSlate adapter (the only production backend)
# ---------------------------------------------------------------------------
class CleanSlateAdapter(WTABackend):
    """Wraps clean_slate_optimizer.CleanSlateOptimizer (HiGHS-based MIP).

    Lazy-imports the optimizer so the ROS2 layer can still be unit-tested in
    environments without HiGHS installed -- the import only fires on construction.
    """

    name = "CleanSlate"

    def __init__(self, config: Any = None) -> None:
        from clean_slate_optimizer import CleanSlateOptimizer  # type: ignore
        self._optimizer = CleanSlateOptimizer(config)

    @staticmethod
    def _battery_to_dict(b: Battery) -> Dict[str, Any]:
        """Raw battery dict shape that the GUI feeds into CleanSlate."""
        system_type = "LSAM" if b.layer == "UPPER" else "MSAM"
        return {
            "id": b.id,
            "system_type": system_type,
            "position": b.position,
            "available_missiles": b.available_missiles,
            "status": "OPERATIONAL",
            "specs": {
                "ballistic_missile_specs": {
                    "intercept_probability": b.base_pk,
                    "engagement_range_km": {"max": b.engagement_range, "min": 0.0},
                },
                "battery_config": {
                    "simultaneous_engagements": b.fire_control_channels,
                },
            },
        }

    def solve(self, wta_in: WTAInput) -> List[Assignment]:
        from clean_slate_optimizer import Asset as CsAsset       # type: ignore
        from clean_slate_optimizer import InterceptorSystem as CsSys  # type: ignore
        from clean_slate_optimizer import Threat as CsThreat     # type: ignore

        # 1) Assets
        active_by_target: Dict[str, List[str]] = {}
        for s in wta_in.scores:
            active_by_target.setdefault(s.target_asset_id, []).append(s.threat_id)
        assets_opt = [
            CsAsset(
                id=a.id,
                position=a.position,
                value=getattr(a, "value", 1.0),
                priority=1,
                estimated_threat_missiles=active_by_target.get(a.id, []),
            )
            for a in wta_in.assets
        ]

        # 2) Interceptor systems + raw battery dicts
        systems_opt: List = []
        batteries_raw: List[Dict[str, Any]] = []
        for b in wta_in.batteries:
            current_ammo = wta_in.available.get(b.id, b.available_missiles)
            if current_ammo <= 0:
                continue
            systems_opt.append(
                CsSys(
                    id=b.id,
                    system_type="LSAM" if b.layer == "UPPER" else "MSAM",
                    position=b.position,
                    available_missiles=current_ammo,
                    max_missiles_per_target=min(b.fire_control_channels, current_ammo),
                    intercept_probability=b.base_pk,
                    engagement_range=b.engagement_range,
                )
            )
            d = self._battery_to_dict(b)
            d["available_missiles"] = current_ammo
            batteries_raw.append(d)

        # 3) Threats (need 3D current_position; altitude is a placeholder)
        threats_opt: List = []
        for s in wta_in.scores:
            tr = wta_in.tracks.get(s.threat_id)
            if tr is None:
                continue
            altitude = 10_000.0
            t = CsThreat(
                id=s.threat_id,
                target_asset_id=s.target_asset_id,
                current_position=(tr.position[0], tr.position[1], altitude),
                estimated_impact_time=max(s.time_to_impact, 0.1),
            )
            t.launch_position = tr.launch_position
            t.flight_time = max(s.time_to_impact, 1.0)
            t.launch_time = 0.0
            threats_opt.append(t)

        if not threats_opt or not systems_opt:
            return []

        # 4) Sampled intercept probabilities derived from EngagementCells
        max_pk_by_threat: Dict[str, float] = {}
        for c in wta_in.cells:
            if c.pk > max_pk_by_threat.get(c.threat_id, 0.0):
                max_pk_by_threat[c.threat_id] = c.pk
        if max_pk_by_threat:
            self._optimizer.set_intercept_probabilities(max_pk_by_threat)

        # 5) Solve
        try:
            self._optimizer.create_model(
                assets=assets_opt,
                interceptor_systems=systems_opt,
                threats=threats_opt,
                batteries=batteries_raw,
                engagement_matrix=None,
            )
            result = self._optimizer.solve()
        except Exception as e:  # noqa: BLE001
            print(f"[CleanSlateAdapter] solve failed: {e}")
            return []

        if not result.get("feasible", False):
            return []

        # 6) Convert result -> List[Assignment].
        #    CleanSlate sometimes returns threat ids namespaced by their asset
        #    (e.g. "A1_Command_T01"); normalize back to the original score ids.
        assignments: List[Assignment] = []
        pk_map = {(c.system_id, c.threat_id): c.pk for c in wta_in.cells}
        score_ids = {s.threat_id for s in wta_in.scores}

        def _normalize(tid: Any) -> str:
            s = str(tid)
            if s in score_ids:
                return s
            for orig in score_ids:
                if s == orig or s.endswith("_" + orig):
                    return orig
            return s

        def _push(layer: str, table: Dict[str, Any]) -> None:
            for raw_tid, system_ids in (table or {}).items():
                tid = _normalize(raw_tid)
                if not isinstance(system_ids, (list, tuple, set)):
                    system_ids = [system_ids]
                for sid in system_ids:
                    assignments.append(
                        Assignment(
                            system_id=str(sid),
                            threat_id=tid,
                            layer=layer,
                            pk=pk_map.get((sid, tid), 0.5),
                        )
                    )

        _push("UPPER", result.get("upper_assignments", {}))
        _push("LOWER", result.get("lower_assignments", {}))
        return assignments

    @staticmethod
    def objective(assignments: List[Assignment], scores: List[ThreatScore]) -> float:
        """Expected protected value: sum over threats of danger * (1 - Pi(1-pk))."""
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
