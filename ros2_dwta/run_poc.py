#!/usr/bin/env python3
"""Standalone PoC runner (no ROS2 install required).

    python3 ros2_dwta/run_poc.py [duration_seconds]

Uses real ROS2 (rclpy) if installed, otherwise the deterministic in-process shim.
The actual orchestration lives in dwta_nodes/poc_app.py so the same logic is
reachable as the `dwta_poc` console entry point after an ament build.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dwta_nodes.poc_app import main  # noqa: E402

if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 70.0
    scenario = sys.argv[2] if len(sys.argv) > 2 else "saturation"
    main(dur, scenario)
