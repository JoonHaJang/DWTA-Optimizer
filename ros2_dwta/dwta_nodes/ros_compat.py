"""Selects the real ROS2 (rclpy) backend if available, else the in-process shim.

Node code imports `Node` and `rclpy` from here, so a single source tree runs in
both worlds:

    from .ros_compat import Node, rclpy, USING_ROS2
"""
from __future__ import annotations

try:  # real ROS2
    import rclpy  # type: ignore
    from rclpy.node import Node  # type: ignore

    USING_ROS2 = True
except Exception:  # fall back to the deterministic in-process shim
    from . import sim_bus as rclpy  # type: ignore
    from .sim_bus import Node  # type: ignore

    USING_ROS2 = False

def latched_qos(depth: int = 1):
    """QoS for the shared world-state topic.

    Real ROS2: TRANSIENT_LOCAL durability so a node joining late still receives
    the latest Common Operational Picture. Shim: just a depth int (ignored).
    """
    if USING_ROS2:  # pragma: no cover - requires a ROS2 install
        from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                               ReliabilityPolicy)
        return QoSProfile(
            depth=depth,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
    return depth


__all__ = ["rclpy", "Node", "USING_ROS2", "latched_qos"]
