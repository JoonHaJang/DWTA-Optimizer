"""PyQtGraph 실시간 전술화면 (TacticalView) — viz_node 의 pyqtgraph 백엔드.

디스플레이가 있는 환경에서만 사용. 헤드리스 환경에서는 viz_node 가 자동으로 ASCII로
폴백한다. /world_state 의 위협(생명주기별 색)·포대·자산·교전선을 갱신한다.

실제 ROS2에서의 실행 패턴(Qt 이벤트 루프 + rclpy spin):

    import rclpy, threading
    from dwta_nodes.viz_node import VizNode
    from dwta_nodes.scenario import default_scenario
    import pyqtgraph as pg

    rclpy.init()
    assets, batteries, _ = default_scenario()
    node = VizNode(assets, batteries, backend="pyqtgraph")
    threading.Thread(target=lambda: rclpy.spin(node), daemon=True).start()
    pg.exec()   # Qt 메인 루프
"""
from __future__ import annotations

from typing import List

from .messages import WorldState
from .scenario import Asset, Battery


_LIFE_COLOR = {
    "DETECTED": (150, 150, 150), "ASSESSED": (230, 220, 90),
    "ENGAGEABLE": (240, 160, 60), "ENGAGED": (230, 60, 60),
    "INTERCEPTED": (80, 200, 120), "LEAKED": (130, 0, 0),
}


class TacticalView:
    """pyqtgraph 기반 top-down 전술 디스플레이."""

    def __init__(self, assets: List[Asset], batteries: List[Battery]):
        import pyqtgraph as pg  # 디스플레이 없으면 여기서 예외 -> viz_node ascii 폴백
        self._pg = pg
        self._win = pg.GraphicsLayoutWidget(title="DWTA Tactical Picture")
        self._plot = self._win.addPlot()
        self._plot.setAspectLocked(True)
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setXRange(-30, 230)
        self._plot.setYRange(-60, 130)

        # 정적: 자산 / 포대
        ax = [a.position[0] for a in assets]; ay = [a.position[1] for a in assets]
        self._plot.plot(ax, ay, pen=None, symbol="s", symbolSize=14,
                        symbolBrush=(70, 130, 220), name="assets")
        bx = [b.position[0] for b in batteries]; by = [b.position[1] for b in batteries]
        self._plot.plot(bx, by, pen=None, symbol="t", symbolSize=14,
                        symbolBrush=(60, 200, 90), name="batteries")
        self._batteries = {b.id: b for b in batteries}

        self._threat_scatter = pg.ScatterPlotItem(size=11)
        self._plot.addItem(self._threat_scatter)
        self._lines = []  # 교전선
        self._win.show()

    def update(self, ws: WorldState) -> None:
        pg = self._pg
        spots = []
        pos = {}
        for t in ws.threats:
            pos[t.threat_id] = t.position
            spots.append({"pos": t.position, "brush": pg.mkBrush(*_LIFE_COLOR.get(t.lifecycle, (200, 200, 200)))})
        self._threat_scatter.setData(spots)

        # 교전선 갱신 (포대 -> 교전중 위협)
        for ln in self._lines:
            self._plot.removeItem(ln)
        self._lines.clear()
        for b in ws.batteries:
            bat = self._batteries.get(b.system_id)
            if not bat:
                continue
            for tid in b.engaging:
                if tid in pos:
                    ln = self._plot.plot([bat.position[0], pos[tid][0]],
                                         [bat.position[1], pos[tid][1]],
                                         pen=pg.mkPen((230, 120, 40), width=1))
                    self._lines.append(ln)
        self._win.setWindowTitle(f"DWTA Tactical  t={ws.stamp:.1f}s  threats={len(ws.threats)}")
        pg.QtWidgets.QApplication.processEvents()
