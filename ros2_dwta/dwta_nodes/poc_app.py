"""Composition entry point: runs all DWTA nodes under one executor.

Valid as a real ROS2 program too -- running multiple nodes in one process with a
MultiThreadedExecutor is standard ROS2 composition. Under the shim it uses the
deterministic SingleThreadedExecutor.
"""
from __future__ import annotations

import sys

from .ros_compat import rclpy, USING_ROS2
from . import (ControlStationNode, EngageabilityNode, LauncherNode,
               PlanningNode, RadarNode, ThreatAssessmentNode, WorldStateNode)
from .scenario import default_scenario


def build_nodes():
    assets, batteries, spawns = default_scenario()
    radar = RadarNode(assets, batteries, spawns)
    assessment = ThreatAssessmentNode(assets)
    engage = EngageabilityNode(batteries)
    planning = PlanningNode(batteries)
    launcher = LauncherNode(batteries)
    control = ControlStationNode()
    world = WorldStateNode()
    world.set_battery_layers({b.id: b.layer for b in batteries})
    # control & radar first so policy/tracks are available early; world last (COP)
    nodes = [control, radar, assessment, engage, planning, launcher, world]
    return nodes, batteries, launcher


def main(duration: float = 45.0, args=None) -> None:
    rclpy.init(args=args)
    nodes, batteries, launcher = build_nodes()

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
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    main(dur)


if __name__ == "__main__":
    cli()
