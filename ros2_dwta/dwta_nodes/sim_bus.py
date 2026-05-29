"""In-process pub/sub bus that mirrors the rclpy API surface.

This lets the *exact same* node code (radar_node, planning_node, ...) run with no
ROS2 install. It implements a deterministic, single-threaded executor with a
virtual clock and Logical-Execution-Time (LET) style 1-tick delivery latency:
messages published during tick *k* are delivered at tick *k+1*. That makes runs
reproducible (the "model-checking flavour" you mentioned) while still modelling
each node as an independent periodic loop, exactly like ROS2 timers.

Real ROS2 mapping (see ros_compat.py): Node -> rclpy.node.Node,
create_timer/create_publisher/create_subscription are identical, and the
deterministic executor here corresponds to a SingleThreadedExecutor; for true
parallel loops use rclpy's MultiThreadedExecutor + callback groups, or the
Events/rclc executor for LET semantics.
"""
from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Dict, List


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t


_CLOCK = _Clock()


class _Logger:
    def __init__(self, name: str) -> None:
        self._name = name

    def info(self, msg: str) -> None:
        print(f"[{_CLOCK.now():6.2f}s][{self._name}] {msg}")

    # warn/error kept for rclpy parity
    warn = info
    error = info


class Subscription:
    def __init__(self, topic: str, callback: Callable) -> None:
        self.topic = topic
        self.callback = callback
        self._incoming: Deque = deque()   # published this tick
        self._ready: Deque = deque()       # to be delivered this tick


class Publisher:
    def __init__(self, bus: "_Bus", topic: str) -> None:
        self._bus = bus
        self.topic = topic

    def publish(self, msg) -> None:
        for sub in self._bus.topics.get(self.topic, ()):  # fan-out
            sub._incoming.append(msg)


class Timer:
    def __init__(self, period: float, callback: Callable) -> None:
        self.period = period
        self.callback = callback
        self._next = 0.0


class _Bus:
    def __init__(self) -> None:
        self.topics: Dict[str, List[Subscription]] = {}

    def register(self, sub: Subscription) -> None:
        self.topics.setdefault(sub.topic, []).append(sub)


_BUS = _Bus()


class Node:
    """Minimal rclpy.node.Node lookalike."""

    def __init__(self, node_name: str) -> None:
        self._name = node_name
        self._logger = _Logger(node_name)
        self.subscriptions: List[Subscription] = []
        self.timers: List[Timer] = []

    # --- rclpy-compatible API --------------------------------------------------
    def create_publisher(self, _msg_type, topic: str, _qos=10) -> Publisher:
        return Publisher(_BUS, topic)

    def create_subscription(self, _msg_type, topic: str, callback: Callable, _qos=10) -> Subscription:
        sub = Subscription(topic, callback)
        _BUS.register(sub)
        self.subscriptions.append(sub)
        return sub

    def create_timer(self, period_sec: float, callback: Callable) -> Timer:
        timer = Timer(period_sec, callback)
        self.timers.append(timer)
        return timer

    def get_logger(self) -> _Logger:
        return self._logger

    def get_name(self) -> str:
        return self._name


class SingleThreadedExecutor:
    """Deterministic virtual-clock executor.

    spin_for(duration, dt): step a virtual clock in `dt` increments, firing each
    node's timers at their own rate and delivering messages with 1-tick latency.
    """

    def __init__(self) -> None:
        self._nodes: List[Node] = []

    def add_node(self, node: Node) -> None:
        self._nodes.append(node)

    def spin_for(self, duration: float, dt: float = 0.05) -> None:
        steps = int(round(duration / dt))
        for i in range(steps + 1):
            _CLOCK.t = round(i * dt, 6)

            # 1) promote messages published last tick -> ready this tick (LET)
            for node in self._nodes:
                for sub in node.subscriptions:
                    if sub._incoming:
                        sub._ready.extend(sub._incoming)
                        sub._incoming.clear()

            # 2) fire due timers (independent periodic node loops)
            for node in self._nodes:
                for timer in node.timers:
                    if _CLOCK.t + 1e-9 >= timer._next:
                        timer.callback()
                        # advance, catching up if we fell behind
                        timer._next += timer.period
                        if timer._next < _CLOCK.t:
                            timer._next = _CLOCK.t + timer.period

            # 3) deliver ready messages to subscription callbacks
            for node in self._nodes:
                for sub in node.subscriptions:
                    while sub._ready:
                        sub.callback(sub._ready.popleft())


# --- module-level rclpy lookalikes --------------------------------------------
_OK = True


def init(args=None) -> None:
    global _OK
    _OK = True


def shutdown() -> None:
    global _OK
    _OK = False


def ok() -> bool:
    return _OK


def now() -> float:
    return _CLOCK.now()
