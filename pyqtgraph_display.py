"""
TacticalMapWidget - PyQtGraph Tactical Display for DWTA Operator
================================================================

Operator-focused map widget for Multi-Layer Air Defense (MLAD).
Replaces matplotlib TkAgg with PyQtGraph for real-time performance.

Features:
  - TTA-based threat color coding (red <30s / yellow <60s / green >=60s)
  - LSAM range rings (150km inner solid, 300km outer dotted) and MSAM (5km/50km)
  - Threat glow ring (semi-transparent background circle)
  - Assigned-threat white outline + glow highlight
  - Threat trajectory prediction lines (unassigned threats only, dotted)
  - Battery-to-threat engagement lines (TTA-based color/thickness, distance-gated)
  - Battery ammo bar below marker
  - Assigned-battery outline highlight
  - HUD overlay (top-right: ACTIVE / ENGAGED / FREE counts)
  - QPainter-based legend (bottom-left, actual symbol rendering)
  - Intercept/miss flash animations (TTL 1.2s)

Author: Claude Code
"""

import math
import numpy as np
import time
from typing import Dict

try:
    import pyqtgraph as pg
    from PyQt5 import QtCore, QtGui, QtWidgets
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("[WARNING] PyQtGraph not available. Install: pip install pyqtgraph PyQt5")


# ---------------------------------------------------------------------------
# QPainter-based legend widget
# ---------------------------------------------------------------------------

class _LegendWidget(QtWidgets.QWidget):
    """Compact legend: battery symbols + asset + threat TTA colours."""

    _ROW_H = 16
    _ROWS = 3
    _PAD = 6
    _W = 220

    def sizeHint(self):
        h = self._PAD * 2 + self._ROW_H * self._ROWS
        return QtCore.QSize(self._W, h)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 160))
        p.setPen(QtGui.QColor(0x33, 0x33, 0x33))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        pad = self._PAD
        rh = self._ROW_H
        rows_y = [pad + rh * i + rh // 2 for i in range(self._ROWS)]
        font = QtGui.QFont("monospace", 8)
        p.setFont(font)

        # ── Row 0: LSAM square + MSAM pentagon ──────────────────────────────
        y = rows_y[0]
        sx = pad + 6
        p.setPen(QtGui.QPen(QtGui.QColor(0xff, 0x88, 0x00), 2))
        p.setBrush(QtGui.QBrush(QtGui.QColor(0xff, 0x88, 0x00, 80)))
        p.drawRect(sx - 5, y - 5, 10, 10)
        p.setPen(QtGui.QColor(0xff, 0x88, 0x00))
        p.drawText(sx + 9, y + 4, "LSAM")
        cx2 = sx + 60
        pts = _pentagon_points(cx2, y, 6)
        p.setPen(QtGui.QPen(QtGui.QColor(0x00, 0xcc, 0xcc), 2))
        p.setBrush(QtGui.QBrush(QtGui.QColor(0x00, 0xcc, 0xcc, 80)))
        p.drawPolygon(pts)
        p.setPen(QtGui.QColor(0x00, 0xcc, 0xcc))
        p.drawText(cx2 + 9, y + 4, "MSAM")

        # ── Row 1: Protected asset star ──────────────────────────────────────
        y = rows_y[1]
        _draw_star(p, pad + 6, y, 6, QtGui.QColor(0xff, 0xe0, 0x66))
        p.setPen(QtGui.QColor(0xff, 0xe0, 0x66))
        p.drawText(pad + 16, y + 4, "Asset")

        # ── Row 2: Threat symbols + TTA colours ─────────────────────────────
        y = rows_y[2]
        threat_colors = [
            (QtGui.QColor(255, 50, 50),  "<30s"),
            (QtGui.QColor(255, 200, 0),  "<60s"),
            (QtGui.QColor(0, 210, 80),   "≥60s"),
        ]
        x_off = pad + 6
        # Triangle = unassigned (first entry as example)
        col0 = threat_colors[0][0]
        tri = QtGui.QPolygon([
            QtCore.QPoint(x_off,     y - 5),
            QtCore.QPoint(x_off - 5, y + 4),
            QtCore.QPoint(x_off + 5, y + 4),
        ])
        p.setPen(QtGui.QPen(col0, 1.5))
        p.setBrush(QtGui.QBrush(col0))
        p.drawPolygon(tri)
        p.setPen(QtGui.QColor(0xaa, 0xaa, 0xaa))
        p.drawText(x_off + 8, y + 4, "▲free")
        x_off += 52
        # Circle = assigned
        col1 = threat_colors[1][0]
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5))
        p.setBrush(QtGui.QBrush(col1))
        p.drawEllipse(QtCore.QPoint(x_off, y), 5, 5)
        p.setPen(QtGui.QColor(0xaa, 0xaa, 0xaa))
        p.drawText(x_off + 8, y + 4, "●engaged")

        p.end()


def _pentagon_points(cx, cy, r):
    pts = QtGui.QPolygon()
    for i in range(5):
        angle = math.radians(-90 + 72 * i)
        pts.append(QtCore.QPoint(int(cx + r * math.cos(angle)),
                                 int(cy + r * math.sin(angle))))
    return pts


def _draw_star(painter, cx, cy, r, color):
    painter.setPen(QtGui.QPen(color, 1.5))
    painter.setBrush(QtGui.QBrush(color))
    pts = QtGui.QPolygon()
    for i in range(10):
        angle = math.radians(-90 + 36 * i)
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(QtCore.QPoint(int(cx + rr * math.cos(angle)),
                                 int(cy + rr * math.sin(angle))))
    painter.drawPolygon(pts)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

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

        # Change detection cache (battery ammo only; assignment lines rebuilt every frame)
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
        self.setBackground('#050a14')
        self.showGrid(x=True, y=True, alpha=0.06)
        self.setXRange(-90, 120, padding=0)
        self.setYRange(-130, 270, padding=0)
        self.setLabel('left', 'Y (km)', color='#1c5f96')
        self.setLabel('bottom', 'X (km)', color='#1c5f96')
        self.setTitle('TACTICAL SITUATION DISPLAY', color='#1c5f96', size='11pt')
        self.setAspectLocked(False)

        # Style axes ticks
        for axis in ('left', 'bottom'):
            self.getAxis(axis).setTextPen(pg.mkPen('#2a4a6a'))
            self.getAxis(axis).setPen(pg.mkPen('#1a2a3a'))

        # North indicator
        north = pg.TextItem('N\u2191', color='#2a4a6a', anchor=(0.5, 0.5))
        north.setPos(112, 258)
        self.addItem(north)

    def _init_static_items(self):
        """Pre-allocate all scatter/line plot items."""
        # Protected assets -- 노란 별 (★)
        self.asset_scatter = pg.ScatterPlotItem(
            size=20,
            pen=pg.mkPen('#ffe066', width=2),
            brush=pg.mkBrush(255, 224, 102, 210),
            symbol='star'
        )
        self.addItem(self.asset_scatter)

        # Threat glow ring (behind main dot) — semi-transparent larger circle
        self.threat_glow = pg.ScatterPlotItem()
        self.addItem(self.threat_glow)

        # Active threats -- TTA-based colour; assigned → white outline
        self.threat_scatter = pg.ScatterPlotItem()
        self.addItem(self.threat_scatter)

        # Intercepted -- 하늘색 X
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
        self._init_hud()

    def _draw_legend(self):
        """좌하단 고정 범례 — QPainter 기반 실제 심볼 렌더링."""
        if hasattr(self, '_legend_widget'):
            return
        self._legend_widget = _LegendWidget(self)
        self._legend_widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._legend_widget.show()
        self._legend_widget.adjustSize()

    def _init_hud(self):
        """우상단 HUD 오버레이 QLabel 초기화."""
        if hasattr(self, '_hud_label'):
            return  # 시나리오 재로드 시 중복 생성 방지
        self._hud_label = QtWidgets.QLabel(self)
        self._hud_label.setStyleSheet(
            "background: rgba(0,0,0,160);"
            "color: #00ccff;"
            "font-size: 11px;"
            "font-family: monospace;"
            "padding: 5px 8px;"
            "border: 1px solid #1a4a6a;"
        )
        self._hud_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        self._hud_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._hud_label.setText("ACTIVE     0\nENGAGED    0\nFREE       0")
        self._hud_label.show()
        self._hud_label.adjustSize()

    def resizeEvent(self, event):
        """위젯 크기 변경 시 범례·HUD 위치 재고정."""
        super().resizeEvent(event)
        margin = 6
        if hasattr(self, '_legend_widget'):
            self._legend_widget.adjustSize()
            lh = self._legend_widget.height()
            self._legend_widget.move(margin, self.height() - lh - margin)
        if hasattr(self, '_hud_label'):
            self._hud_label.adjustSize()
            self._hud_label.move(
                self.width() - self._hud_label.width() - margin, margin
            )

    def _draw_range_rings(self):
        """Draw LSAM/MSAM engagement range rings (called once at init).

        Inner ring: solid, brighter.
        Outer ring: dotted, dimmer.
        """
        if not hasattr(self.tracker, 'batteries'):
            return

        for battery in self.tracker.batteries:
            bx, by = battery['position']
            stype = battery.get('system_type', 'MSAM')

            if stype == 'LSAM':
                radii = [150, 300]
                rv, gv, bv = 255, 140, 0
            else:
                radii = [5, 50]
                rv, gv, bv = 0, 200, 180

            for idx, r in enumerate(radii):
                theta = np.linspace(0, 2 * np.pi, 120)
                xs = bx + r * np.cos(theta)
                ys = by + r * np.sin(theta)
                if idx == 0:
                    # Inner ring: brighter, solid
                    pen = pg.mkPen(rv, gv, bv, 140, width=1.5)
                else:
                    # Outer ring: dimmer, dotted
                    pen = pg.mkPen(rv, gv, bv, 45, width=1,
                                   style=QtCore.Qt.DotLine)
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
        """Update threat scatter + glow ring with TTA-based colour.

        Unassigned threats : triangle (▲) — approaching, no intercept yet.
        Assigned threats   : circle  (●) — TTA colour, white outline.
        """
        missiles = self.tracker.missiles
        kill_results = self.tracker.kill_results

        # Threats with a VISIBLE engagement line (assigned + within ENGAGEMENT_LINE_DIST_KM).
        # Uses assignment_items from the previous frame — aligned with line visibility.
        assigned_threats = {mid for (_, mid) in self.assignment_items}

        active = {mid: m for mid, m in missiles.items() if m.get('active')}
        glow_spots = []
        threat_spots = []

        if active:
            for mid, m in active.items():
                tta = self._compute_tta(m)
                r, g, b, a = self._tta_color(tta)
                is_assigned = mid in assigned_threats
                pos = (m['position'][0], m['position'][1])

                if is_assigned:
                    # Assigned: circle + white outline + glow
                    glow_spots.append({
                        'pos': pos,
                        'pen': pg.mkPen(r, g, b, 80, width=1),
                        'brush': pg.mkBrush(r, g, b, 45),
                        'size': 24,
                        'symbol': 'o',
                    })
                    threat_spots.append({
                        'pos': pos,
                        'pen': pg.mkPen(255, 255, 255, 210, width=2),
                        'brush': pg.mkBrush(r, g, b, a),
                        'size': 12,
                        'symbol': 'o',
                    })
                else:
                    # Unassigned: triangle, TTA colour outline, no glow
                    threat_spots.append({
                        'pos': pos,
                        'pen': pg.mkPen(r, g, b, 200, width=1.5),
                        'brush': pg.mkBrush(r, g, b, 160),
                        'size': 11,
                        'symbol': 't',
                    })

        self.threat_glow.setData(spots=glow_spots)
        self.threat_scatter.setData(spots=threat_spots)

        current_t = getattr(self.tracker, 'current_time_step', 0)
        int_pos = [
            (missiles[mid]['position'][0], missiles[mid]['position'][1])
            for mid, (res, t, _) in kill_results.items()
            if res == 'INTERCEPTED' and mid in missiles and (current_t - t) <= 5
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
        """미교전 위협(배터리 미할당)만 궤적선 표시."""
        missiles = self.tracker.missiles
        asset_lookup = {a['id']: a for a in self.tracker.assets}
        assign_mgr = self.tracker.primary_assignments

        for mid in list(self.trajectory_items.keys()):
            m = missiles.get(mid)
            engaged = bool(assign_mgr.get_batteries_for_threat(mid))
            if not m or not m.get('active') or engaged:
                self.removeItem(self.trajectory_items.pop(mid))

        for mid, m in missiles.items():
            if not m.get('active'):
                continue
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
                pen = pg.mkPen('#cc6600', width=1.2, style=QtCore.Qt.DotLine)
                line = pg.PlotCurveItem([tx, ax], [ty, ay], pen=pen)
                self.addItem(line)
                self.trajectory_items[mid] = line

    @staticmethod
    def _tta_bucket(tta: float) -> int:
        """Return 0/1/2 for red/yellow/green — used to detect pen changes."""
        if tta < 30:
            return 0
        elif tta < 60:
            return 1
        return 2

    _ENGAGEMENT_PENS = None   # lazily initialised once

    @classmethod
    def _get_engagement_pens(cls):
        if cls._ENGAGEMENT_PENS is None:
            cls._ENGAGEMENT_PENS = [
                pg.mkPen(255, 50,  50,  200, width=2.5, style=QtCore.Qt.DashLine),  # red
                pg.mkPen(255, 200, 0,   200, width=1.8, style=QtCore.Qt.DashLine),  # yellow
                pg.mkPen(0,   210, 80,  180, width=1.2, style=QtCore.Qt.DashLine),  # green
            ]
        return cls._ENGAGEMENT_PENS

    def _update_assignment_lines(self):
        """Draw engagement lines: battery → threat.

        Reuses existing PlotCurveItem objects — only setData/setPen per frame.
        Items are added/removed only when the visible set actually changes.
        """
        current = dict(self.tracker.primary_assignments.items())
        bat_lookup = {b['id']: b for b in self.tracker.batteries}
        pens = self._get_engagement_pens()

        # Build desired (bat_id, mid) set for this frame.
        # Line appears when flight_progress >= 0.50 (intercept fires at 0.60),
        # ensuring the line is always visible before the intercept flash.
        desired: dict = {}   # key → (bx, by, tx, ty, bucket)
        for bat_id, threat_ids in current.items():
            battery = bat_lookup.get(bat_id)
            if not battery:
                continue
            bx, by = battery['position']
            for mid in threat_ids:
                m = self.tracker.missiles.get(mid)
                if not m or not m.get('active'):
                    continue
                if m.get('flight_progress', 0) < 0.50:
                    continue
                tx, ty = m['position'][0], m['position'][1]
                desired[(bat_id, mid)] = (bx, by, tx, ty,
                                          self._tta_bucket(self._compute_tta(m)))

        # Remove stale items
        for key in list(self.assignment_items.keys()):
            if key not in desired:
                self.removeItem(self.assignment_items.pop(key))

        # Update existing / create new
        for key, (bx, by, tx, ty, bucket) in desired.items():
            if key in self.assignment_items:
                line = self.assignment_items[key]
                line.setData([bx, tx], [by, ty])
                line.setPen(pens[bucket])
            else:
                line = pg.PlotCurveItem([bx, tx], [by, ty], pen=pens[bucket])
                self.addItem(line)
                self.assignment_items[key] = line

    def remove_intercepted(self, missile_id: str):
        """Called immediately on intercept signal: removes lines + refreshes scatter.

        Ensures engagement line and threat dot disappear at the same time as the
        flash animation — no 250ms polling lag for the intercept event.
        """
        for key in list(self.assignment_items.keys()):
            if key[1] == missile_id:
                self.removeItem(self.assignment_items.pop(key))
        if missile_id in self.trajectory_items:
            self.removeItem(self.trajectory_items.pop(missile_id))
        self._update_threats()

    def _update_batteries(self):
        """Update battery markers: colour by ammo, ammo bar below, highlight when assigned."""
        current_ammo = {
            b['id']: b.get('available_missiles', 0) for b in self.tracker.batteries
        }
        if current_ammo == self._last_battery_ammo:
            return

        for items in self.battery_items.values():
            for it in items:
                self.removeItem(it)
        self.battery_items.clear()

        # Collect which batteries currently have active assignments
        assigned_batteries: set = set()
        for bat_id, tids in self.tracker.primary_assignments.items():
            if tids:
                assigned_batteries.add(bat_id)

        for battery in self.tracker.batteries:
            bid = battery['id']
            bx, by = battery['position']
            ammo = battery.get('available_missiles', 0)
            stype = battery.get('system_type', 'LSAM')
            is_engaged = bid in assigned_batteries

            if stype == 'LSAM':
                base_color = '#ff8800'
                symbol = 's'
                size = 18
            else:
                base_color = '#00cccc'
                symbol = 'p'
                size = 16

            if ammo >= 20:
                alpha = 180
            elif ammo >= 10:
                alpha = 120
            elif ammo >= 5:
                alpha = 70
            else:
                alpha = 30

            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)

            pen_width = 3 if is_engaged else 2
            pen_alpha = 255 if is_engaged else 200

            scatter = pg.ScatterPlotItem(
                pos=np.array([[bx, by]]),
                size=size,
                pen=pg.mkPen(r, g, b, pen_alpha, width=pen_width),
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

    def _update_hud(self):
        """Update top-right HUD overlay with ACTIVE / ENGAGED / FREE counts.

        ENGAGED = flight_progress >= 0.50 (engagement line visible), matching
        the 'ENGAGED' status shown in the threat table.
        """
        missiles = self.tracker.missiles
        active_cnt = sum(1 for m in missiles.values() if m.get('active'))
        engaged_ids = {mid for (_, mid) in self.assignment_items}
        engaged_cnt = sum(1 for mid in engaged_ids if missiles.get(mid, {}).get('active'))
        free_cnt = active_cnt - engaged_cnt
        text = (f"ACTIVE   {active_cnt:4d}\n"
                f"ENGAGED  {engaged_cnt:4d}\n"
                f"FREE     {free_cnt:4d}")
        self._hud_label.setText(text)
        self._hud_label.adjustSize()
        margin = 6
        self._hud_label.move(
            self.width() - self._hud_label.width() - margin, margin
        )

    # ------------------------------------------------------------------
    # Flash animation
    # ------------------------------------------------------------------

    def trigger_kill_flash(self, x: float, y: float, success: bool):
        """
        Trigger a flash animation at (x, y).
        success=True  -> cyan flash (intercept)
        success=False -> red flash  (miss)
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
        self._update_hud()


# ---------------------------------------------------------------------------
# Backwards-compatible alias
# ---------------------------------------------------------------------------
PyQtGraphDisplay = TacticalMapWidget


if __name__ == '__main__':
    print("TacticalMapWidget -- Ready for integration with DWTAMainWindow")
    print("Install dependencies: pip install pyqtgraph PyQt5")
