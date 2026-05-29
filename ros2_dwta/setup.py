from setuptools import setup

package_name = "dwta_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=["dwta_nodes"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/dwta_poc.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="DWTA Optimizer",
    maintainer_email="cyber040946@gmail.com",
    description="Realtime DWTA C2 pipeline as ROS2 node loops (with no-install shim).",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # ros2 run dwta_ros2 dwta_poc
            "dwta_poc = dwta_nodes.poc_app:cli",
        ],
    },
)
