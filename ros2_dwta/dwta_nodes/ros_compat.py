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

__all__ = ["rclpy", "Node", "USING_ROS2"]
