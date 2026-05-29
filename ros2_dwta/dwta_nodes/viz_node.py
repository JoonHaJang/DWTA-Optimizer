"""표시 노드 (Viz) — Common Operational Picture 시각화 (표시 전용, sim과 분리).

`/world_state`(+ 요격체계/사격통제 상태)만 구독해 전술 상황을 렌더링한다. 시뮬레이션
로직과 완전히 분리되어 있어, 표시를 끄거나 교체해도 파이프라인에 영향이 없다.

백엔드:
  - "ascii"     : 헤드리스 텍스트 전술맵 (어디서나 동작, 기본값)
  - "pyqtgraph" : 실시간 PyQtGraph 전술화면 (viz_pyqtgraph.TacticalView, 디스플레이 필요)
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .messages import FireControlStatus, InterceptorStatus, WorldState
from .ros_compat import Node
from .scenario import Asset, Battery


# 위협 생명주기 -> 표시 문자
_LIFE_CHAR = {
    "DETECTED": "?", "ASSESSED": "*", "ENGAGEABLE": "o",
    "ENGAGED": "x", "INTERCEPTED": "+", "LEAKED": "!",
}


def render_ascii(ws: WorldState, assets: List[Asset], batteries: List[Battery],
                 w: int = 64, h: int = 22) -> str:
    x0, x1, y0, y1 = -30.0, 230.0, -60.0, 130.0

    def cell(px: float, py: float):
        c = int((px - x0) / (x1 - x0) * (w - 1))
        r = int((y1 - py) / (y1 - y0) * (h - 1))
        return max(0, min(h - 1, r)), max(0, min(w - 1, c))

    grid = [[" "] * w for _ in range(h)]
    # 자산
    for a in assets:
        r, c = cell(*a.position)
        grid[r][c] = "A"
    # 포대 (L/M)
    bpos = {b.id: b.position for b in batteries}
    for b in batteries:
        r, c = cell(*b.position)
        grid[r][c] = "L" if b.layer == "UPPER" else "M"
    # 위협
    for t in ws.threats:
        r, c = cell(*t.position)
        if grid[r][c] in (" ",):
            grid[r][c] = _LIFE_CHAR.get(t.lifecycle, ".")

    body = "\n".join("".join(row) for row in grid)
    # HUD
    ammo = "  ".join(f"{b.system_id}:{b.available}탄/{b.in_flight}비행" for b in ws.batteries)
    from collections import Counter
    life = Counter(t.lifecycle for t in ws.threats)
    counts = " ".join(f"{k}={v}" for k, v in sorted(life.items()))
    sep = "-" * w
    return (f"{sep}\n[t={ws.stamp:6.2f}s] 위협 {len(ws.threats)}  {counts}\n"
            f"포대: {ammo}\n{sep}\n{body}\n{sep}")


class VizNode(Node):
    def __init__(self, assets: List[Asset], batteries: List[Battery],
                 backend: str = "ascii", period: float = 2.0):
        super().__init__("viz_node")
        self._assets = assets
        self._batteries = batteries
        self._backend = backend
        self._ws: Optional[WorldState] = None
        self._view = None  # pyqtgraph TacticalView (lazy)

        self.create_subscription(WorldState, "/world_state", self._on_world, 10)
        self.create_timer(period, self._render)

        if backend == "pyqtgraph":
            try:
                from .viz_pyqtgraph import TacticalView
                self._view = TacticalView(assets, batteries)
            except Exception as e:  # 디스플레이/pyqtgraph 없음 -> ascii 폴백
                self.get_logger().info(f"pyqtgraph 사용 불가 ({e}); ascii 폴백")
                self._backend = "ascii"

    def _on_world(self, ws: WorldState) -> None:
        self._ws = ws

    def _render(self) -> None:
        if self._ws is None:
            return
        if self._backend == "pyqtgraph" and self._view is not None:
            self._view.update(self._ws)
        else:
            print(render_ascii(self._ws, self._assets, self._batteries))
