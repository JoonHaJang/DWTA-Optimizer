"""ROS2 launch file for the DWTA PoC (composition: all nodes in one process).

    ros2 launch dwta_ros2 dwta_poc.launch.py

For a production layout, split each node into its own `Node(...)` action with its
own executable + parameters (assets/batteries/scenario from a YAML), and assign
callback groups / a deterministic executor (Events or rclc) per the README.
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package="dwta_ros2",
            executable="dwta_poc",
            name="dwta_poc",
            output="screen",
        ),
    ])
