"""Composition entry point: runs all DWTA nodes under one executor.

Valid as a real ROS2 program too -- running multiple nodes in one process with a
MultiThreadedExecutor is standard ROS2 composition. Under the shim it uses the
deterministic SingleThreadedExecutor.
"""
from __future__ import annotations

import sys

from .ros_compat import rclpy, USING_ROS2
from . import (ControlStationNode, EngageabilityNode, FireControlRadarNode,
               LauncherNode, PlanningNode, SurveillanceRadarNode,
               ThreatAssessmentNode, VizNode, WorldStateNode)
from .scenario import SCENARIOS


def build_nodes(scenario: str = "saturation", viz: bool = False,
                viz_backend: str = "ascii"):
    assets, batteries, spawns = SCENARIOS[scenario]()
    radar = SurveillanceRadarNode(assets, batteries, spawns)   # 중앙 감시레이다 (1개)
    fcrs = [FireControlRadarNode(b) for b in batteries]        # 포대 사격통제레이다 (포대당 1개)
    assessment = ThreatAssessmentNode(assets)
    engage = EngageabilityNode(batteries)
    planning = PlanningNode(batteries, assets=assets)
    launcher = LauncherNode(batteries)
    control = ControlStationNode()
    world = WorldStateNode()
    world.set_battery_layers({b.id: b.layer for b in batteries})
    nodes = [control, radar, *fcrs, assessment, engage, planning, launcher, world]
    if viz:
        nodes.append(VizNode(assets, batteries, backend=viz_backend))  # 표시 전용 (분리)
    return nodes, batteries, launcher


def main(duration: float = 70.0, scenario: str = "saturation",
         viz: bool = False, args=None) -> None:
    rclpy.init(args=args)
    nodes, batteries, launcher = build_nodes(scenario, viz=viz)

    mode = "REAL ROS2 (rclpy)" if USING_ROS2 else "in-process shim (deterministic)"
    print("=" * 78)
    print(f" DWTA realtime pipeline PoC  |  executor: {mode}")
    print(f" nodes: {', '.join(n.get_name() for n in nodes)}")
    print("=" * 78)

    if USING_ROS2:  # pragma: no cover - requires a ROS2 install
        from rclpy.executors import MultiThreadedExecutor
        ex = MultiThreadedExecutor()
        for n in nodes:
            ex.add_node(n)
        try:
            ex.spin()
        except KeyboardInterrupt:
            pass
        finally:
            for n in nodes:
                n.destroy_node()
            rclpy.shutdown()
    else:
        from .sim_bus import SingleThreadedExecutor
        ex = SingleThreadedExecutor()
        for n in nodes:
            ex.add_node(n)
        ex.spin_for(duration, dt=0.05)
        _summary(launcher, batteries)
        rclpy.shutdown()


def _summary(launcher, batteries) -> None:
    print("=" * 78)
    print(" 종료 요약")
    print(f"  발사된 요격탄 총 {launcher._fired_seq}발, 비행중 {len(launcher._in_flight)}발")
    for b in batteries:
        used = b.available_missiles - launcher._available[b.id]
        print(f"  {b.id:9s} [{b.layer:5s}] 사용 {used}/{b.available_missiles}  "
              f"교전중 위협: {launcher._engaging[b.id]}")
    print("=" * 78)


def cli() -> None:
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
    scenario = sys.argv[2] if len(sys.argv) > 2 else "saturation"
    viz = "viz" in sys.argv[3:]
    main(dur, scenario, viz)


if __name__ == "__main__":
    cli()
