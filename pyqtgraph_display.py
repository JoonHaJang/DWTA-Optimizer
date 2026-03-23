"""
TacticalMapWidget - PyQtGraph Tactical Display for DWTA Operator
================================================================

Operator-focused map widget for Multi-Layer Air Defense (MLAD).
Replaces matplotlib TkAgg with PyQtGraph for real-time performance.

Features:
  - TTA-based threat color coding (red <30s / yellow <60s / green >=60s)
  - LSAM range rings (150km, 300km) and MSAM range rings (5km, 50km)
  - Threat trajectory prediction lines (threat -> target asset, dashed)
  - Battery-to-threat assignment lines (green dashed)
  - Intercept/miss flash animations (TTL 1.2s)
  - Color-coded battery markers (ammo level)

Author: Claude Code
"""

import numpy as np
import time
from typing import Dict

try:
    import pyqtgraph as pg
    from PyQt5 import QtCore, QtWidgets
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("[WARNING] PyQtGraph not available. Install: pip install pyqtgraph PyQt5")


class TacticalMapWidget(pg.PlotWidget):
    """
    High-performance PyQtGraph tactical map widget.
    Designed for MLAD (Multi-Layer Air Defense) operators.

    Usage:
        widget = TacticalMapWidget(tracker)
        # Called periodically by DWTAMainWindow QTimer:
        widget.update_display()
        # Called on kill event from signal:
        widget.trigger_kill_flash(x, y, success=True)
    """

    def __init__(self, tracker, parent=None):
        super().__init__(parent)
        self.tracker = tracker

        # Flash animation list: [{'item': PlotItem, 'created': float, 'ttl': float}]
        self._flash_items = []

        # Change detection caches
        self._last_assignments: dict = {}
        self._last_battery_ammo: dict = {}

        self._configure_plot()
        self._init_static_items()
        self._draw_range_rings()
        self._update_assets()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _configure_plot(self):
        """Configure plot axes, background, and labels."""
        self.setBackground('#0a0a0a')
        self.showGrid(x=True, y=True, alpha=0.2)
        self.setXRange(-90, 120, padding=0)
        self.setYRange(-130, 270, padding=0)
        self.setLabel('left', 'Y Position (km)', color='#00cc00')
        self.setLabel('bottom', 'X Position (km)', color='#00cc00')
        self.setTitle('TACTICAL SITUATION DISPLAY', color='#00ff00', size='11pt')
        self.setAspectLocked(False)

        # Style axes ticks
        for axis in ('left', 'bottom'):
            self.getAxis(axis).setTextPen(pg.mkPen('#888888'))
            self.getAxis(axis).setPen(pg.mkPen('#333333'))

        # North indicator
        north = pg.TextItem('N\u2191', color='white', anchor=(0.5, 0.5))
        north.setPos(112, 258)
        self.addItem(north)

    def _init_static_items(self):
        """Pre-allocate all scatter/line plot items."""
        # Protected assets -- 노란 별 (★) : 자산은 포대/위협과 명확히 구분
        self.asset_scatter = pg.ScatterPlotItem(
            size=20,
            pen=pg.mkPen('#ffe066', width=2),
            brush=pg.mkBrush(255, 224, 102, 210),
            symbol='star'
        )
        self.addItem(self.asset_scatter)

        # Active threats -- 원 (●) : 크기·색상으로 TTA 표현 (spots API)
        self.threat_scatter = pg.ScatterPlotItem()
        self.addItem(self.threat_scatter)

        # Intercepted -- 하늘색 X (요격 성공, 위협 녹색과 구분)
        self.intercepted_scatter = pg.ScatterPlotItem(
            size=12,
            pen=pg.mkPen('#00ccff', width=2),
            brush=pg.mkBrush(None),
            symbol='x'
        )
        self.addItem(self.intercepted_scatter)

        # Missed -- 작은 적색 십자
        self.missed_scatter = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen('#ff3333', width=2),
            brush=pg.mkBrush(None),
            symbol='+'
        )
        self.addItem(self.missed_scatter)

        # Dicts for dynamic items
        self.battery_items: Dict[str, list] = {}
        self.trajectory_items: Dict[str, object] = {}
        self.assignment_items: Dict[tuple, object] = {}
        self.asset_text_items: Dict[str, object] = {}

        self._draw_legend()

    def _draw_legend(self):
        """좌하단 고정 범례 — QLabel 오버레이 (줌/패닝과 무관하게 고정)."""
        if hasattr(self, '_legend_label'):
            return  # 중복 생성 방지
        lines = [
            ('<span style="color:#ff8800">■ LSAM(주황)</span>'
             '&nbsp;&nbsp;'
             '<span style="color:#00cccc">⬟ MSAM(청록)</span>'
             '&nbsp;&nbsp;잔탄: 밝음→어두움'),
            '<span style="color:#ffe066">★ 보호 자산 (노랑)</span>',
            '<span style="color:#ff3333">● 위협 적&lt;30s</span>'
             '&nbsp;<span style="color:#ffcc00">황&lt;60s</span>'
             '&nbsp;<span style="color:#00dd55">녹≥60s</span>',
            '<span style="color:#00ff00">— 녹색점선: 교전 중</span>'
             '&nbsp;&nbsp;'
             '<span style="color:#cc6600">주황점선: 미교전</span>',
            '<span style="color:#00ccff">✕ 요격</span>'
             '&nbsp;&nbsp;'
             '<span style="color:#ff4444">+ 피격</span>',
        ]
        html = '<br>'.join(lines)

        self._legend_label = QtWidgets.QLabel(self)
        self._legend_label.setTextFormat(QtCore.Qt.RichText)
        self._legend_label.setText(html)
        self._legend_label.setStyleSheet(
            "background-color: rgba(0,0,0,170);"
            "color: #aaaaaa;"
            "font-size: 10px;"
            "padding: 4px 6px;"
            "border: 1px solid #333333;"
        )
        self._legend_label.adjustSize()
        self._legend_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._legend_label.show()

    def resizeEvent(self, event):
        """위젯 크기 변경 시 범례를 좌하단에 재고정."""
        super().resizeEvent(event)
        if hasattr(self, '_legend_label'):
            margin = 6
            lw = self._legend_label.width()
            lh = self._legend_label.height()
            self._legend_label.move(margin, self.height() - lh - margin)

    def _draw_range_rings(self):
        """Draw LSAM/MSAM engagement range rings (called once at init)."""
        if not hasattr(self.tracker, 'batteries'):
            return

        for battery in self.tracker.batteries:
            bx, by = battery['position']
            stype = battery.get('system_type', 'MSAM')

            if stype == 'LSAM':
                radii = [150, 300]
                pen = pg.mkPen(255, 140, 0, 70, width=1,
                               style=QtCore.Qt.DashLine)
            else:
                radii = [5, 50]
                pen = pg.mkPen(0, 200, 180, 70, width=1,
                               style=QtCore.Qt.DashLine)

            for r in radii:
                theta = np.linspace(0, 2 * np.pi, 120)
                xs = bx + r * np.cos(theta)
                ys = by + r * np.sin(theta)
                ring = pg.PlotCurveItem(xs, ys, pen=pen)
                self.addItem(ring)

    def _update_assets(self):
        """Draw asset markers and labels (called once -- assets are static)."""
        if not hasattr(self.tracker, 'assets') or not self.tracker.assets:
            return

        for item in self.asset_text_items.values():
            self.removeItem(item)
        self.asset_text_items.clear()

        positions = np.array(
            [[a['position'][0], a['position'][1]] for a in self.tracker.assets]
        )
        self.asset_scatter.setData(pos=positions)

        for asset in self.tracker.assets:
            short_id = asset['id'].replace('ASSET_', 'A')
            label = pg.TextItem(short_id, color='#ffe066', anchor=(0.5, 1.6))
            label.setPos(asset['position'][0], asset['position'][1])
            self.addItem(label)
            self.asset_text_items[asset['id']] = label

    # ------------------------------------------------------------------
    # Per-frame update helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_tta(missile: dict) -> float:
        """Return time-to-arrival in seconds for an active missile."""
        if not missile.get('active', False):
            return float('inf')
        remaining = max(1.0 - missile.get('flight_progress', 0.0), 0.0)
        return missile.get('flight_time', 300) * remaining

    @staticmethod
    def _tta_color(tta: float):
        """Return (r, g, b, a) tuple based on TTA urgency."""
        if tta < 30:
            return (255, 50, 50, 235)
        elif tta < 60:
            return (255, 200, 0, 235)
        else:
            return (0, 210, 80, 235)

    def _update_threats(self):
        """Update threat scatter with per-missile TTA-based colour."""
        missiles = self.tracker.missiles
        kill_results = self.tracker.kill_results

        active = {mid: m for mid, m in missiles.items() if m.get('active')}
        if active:
            spots = []
            for mid, m in active.items():
                tta = self._compute_tta(m)
                r, g, b, a = self._tta_color(tta)
                spots.append({
                    'pos': (m['position'][0], m['position'][1]),
                    'pen': pg.mkPen(r, g, b, 220, width=1.5),
                    'brush': pg.mkBrush(r, g, b, a),
                    'size': 10,
                    'symbol': 'o',  # 원 — 포대(사각/오각)·자산(별)과 명확히 구분
                })
            self.threat_scatter.setData(spots=spots)
        else:
            self.threat_scatter.setData(spots=[])

        int_pos = [
            (missiles[mid]['position'][0], missiles[mid]['position'][1])
            for mid, (res, _, _) in kill_results.items()
            if res == 'INTERCEPTED' and mid in missiles
        ]
        self.intercepted_scatter.setData(
            pos=np.array(int_pos) if int_pos else np.empty((0, 2))
        )

        miss_pos = [
            (missiles[mid]['position'][0], missiles[mid]['position'][1])
            for mid, (res, _, _) in kill_results.items()
            if res == 'MISSED' and mid in missiles
        ]
        self.missed_scatter.setData(
            pos=np.array(miss_pos) if miss_pos else np.empty((0, 2))
        )

    def _update_trajectory_lines(self):
        """미교전 위협(배터리 미할당)만 궤적선 표시 — 교전 중인 위협은 교전선으로 표현."""
        missiles = self.tracker.missiles
        asset_lookup = {a['id']: a for a in self.tracker.assets}
        assign_mgr = self.tracker.primary_assignments

        # 비활성 또는 교전 중인 위협의 기존 선 제거
        for mid in list(self.trajectory_items.keys()):
            m = missiles.get(mid)
            engaged = bool(assign_mgr.get_batteries_for_threat(mid))
            if not m or not m.get('active') or engaged:
                self.removeItem(self.trajectory_items.pop(mid))

        for mid, m in missiles.items():
            if not m.get('active'):
                continue
            # 교전 중이면 교전선(녹색)으로 표현하므로 궤적선 불필요
            if assign_mgr.get_batteries_for_threat(mid):
                continue
            target_id = m.get('target_asset')
            if not target_id or target_id == 'EMPTY_AREA':
                continue
            asset = asset_lookup.get(target_id)
            if asset is None:
                continue

            tx, ty = m['position'][0], m['position'][1]
            ax, ay = asset['position'][0], asset['position'][1]

            if mid in self.trajectory_items:
                self.trajectory_items[mid].setData([tx, ax], [ty, ay])
            else:
                # 미교전 위협 궤적: 밝은 주황 점선 (위험 경고)
                pen = pg.mkPen('#cc6600', width=1.2, style=QtCore.Qt.DotLine)
                line = pg.PlotCurveItem([tx, ax], [ty, ay], pen=pen)
                self.addItem(line)
                self.trajectory_items[mid] = line

    def _update_assignment_lines(self):
        """Draw assignment lines: battery -> assigned active threat (green dashed)."""
        current = dict(self.tracker.primary_assignments.items())

        if current == self._last_assignments:
            return

        for item in self.assignment_items.values():
            self.removeItem(item)
        self.assignment_items.clear()

        bat_lookup = {b['id']: b for b in self.tracker.batteries}
        pen = pg.mkPen('#00ff00', width=1, style=QtCore.Qt.DashLine)

        for bat_id, threat_ids in current.items():
            battery = bat_lookup.get(bat_id)
            if not battery:
                continue
            bx, by = battery['position']

            for mid in threat_ids:
                m = self.tracker.missiles.get(mid)
                if not m or not m.get('active'):
                    continue
                tx, ty = m['position'][0], m['position'][1]
                line = pg.PlotCurveItem([bx, tx], [by, ty], pen=pen)
                self.addItem(line)
                self.assignment_items[(bat_id, mid)] = line

        self._last_assignments = current

    def _update_batteries(self):
        """Update battery markers colour-coded by remaining ammo."""
        current_ammo = {
            b['id']: b.get('available_missiles', 0) for b in self.tracker.batteries
        }
        if current_ammo == self._last_battery_ammo:
            return

        for items in self.battery_items.values():
            for it in items:
                self.removeItem(it)
        self.battery_items.clear()

        for battery in self.tracker.batteries:
            bid = battery['id']
            bx, by = battery['position']
            ammo = battery.get('available_missiles', 0)
            stype = battery.get('system_type', 'LSAM')

            # 무기체계별 고정 기본색 (자산 노랑과 확실히 구분)
            if stype == 'LSAM':
                base_color = '#ff8800'   # 주황 — LSAM
                symbol = 's'             # 사각형
                size = 18
            else:
                base_color = '#00cccc'   # 청록 — MSAM
                symbol = 'p'             # 오각형
                size = 16

            # 잔탄에 따른 내부 채움 투명도 (잔탄 많을수록 밝게)
            if ammo >= 20:
                alpha = 180
            elif ammo >= 10:
                alpha = 120
            elif ammo >= 5:
                alpha = 70
            else:
                alpha = 30   # 잔탄 거의 없음 → 거의 투명

            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)

            scatter = pg.ScatterPlotItem(
                pos=np.array([[bx, by]]),
                size=size,
                pen=pg.mkPen(base_color, width=2),
                brush=pg.mkBrush(r, g, b, alpha),
                symbol=symbol
            )
            self.addItem(scatter)

            short_id = (bid.replace('LSAM_BATTERY_', 'L')
                           .replace('MSAM_BATTERY_', 'M')
                           .replace('LSAM_', 'L')
                           .replace('MSAM_', 'M'))
            text = pg.TextItem(
                f'{short_id}\n{ammo}', color=base_color, anchor=(0.5, 1.9)
            )
            text.setPos(bx, by)
            self.addItem(text)

            self.battery_items[bid] = [scatter, text]

        self._last_battery_ammo = current_ammo

    # ------------------------------------------------------------------
    # Flash animation
    # ------------------------------------------------------------------

    def trigger_kill_flash(self, x: float, y: float, success: bool):
        """
        Trigger a flash animation at (x, y).
        success=True  -> green flash (intercept)
        success=False -> red flash   (miss)
        """
        if success:
            pen = pg.mkPen('#00ccff', width=3)
            brush = pg.mkBrush(0, 204, 255, 130)
        else:
            pen = pg.mkPen('#ff3333', width=3)
            brush = pg.mkBrush(255, 51, 51, 130)

        flash = pg.ScatterPlotItem(
            pos=np.array([[x, y]]),
            size=32, pen=pen, brush=brush, symbol='o'
        )
        self.addItem(flash)
        self._flash_items.append({
            'item': flash,
            'created': time.time(),
            'ttl': 1.2
        })

    def _clear_expired_flashes(self):
        """Remove flash items that have exceeded their TTL."""
        now = time.time()
        remaining = []
        for entry in self._flash_items:
            if now - entry['created'] > entry['ttl']:
                try:
                    self.removeItem(entry['item'])
                except Exception:
                    pass
            else:
                remaining.append(entry)
        self._flash_items = remaining

    # ------------------------------------------------------------------
    # Main update (called by QTimer every 250 ms)
    # ------------------------------------------------------------------

    def update_display(self):
        """
        Orchestrate all per-frame visual updates.
        Called by DWTAMainWindow._on_display_tick() under _sim_lock.
        """
        self._clear_expired_flashes()
        self._update_threats()
        self._update_trajectory_lines()
        self._update_assignment_lines()
        self._update_batteries()


# ---------------------------------------------------------------------------
# Backwards-compatible alias kept to avoid ImportError if anything still
# references the old class name.
# ---------------------------------------------------------------------------
PyQtGraphDisplay = TacticalMapWidget


if __name__ == '__main__':
    print("TacticalMapWidget -- Ready for integration with DWTAMainWindow")
    print("Install dependencies: pip install pyqtgraph PyQt5")
