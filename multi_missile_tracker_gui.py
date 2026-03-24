"""
Multi-Missile Real-time DWTA Analysis Simulator - GUI Version
============================================================
UI: PyQt5 single-window (DWTAMainWindow) + PyQtGraph TacticalMapWidget
"""

import numpy as np
import time
import random
from typing import Dict, List, Tuple, Optional, Set
import sys
import os
import threading
from datetime import datetime

# PyQt5 + PyQtGraph (required)
try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
        QGroupBox, QPushButton, QLabel, QComboBox, QTextEdit,
        QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
        QDoubleSpinBox, QSpinBox, QCheckBox, QButtonGroup,
        QRadioButton, QSizePolicy, QAbstractItemView, QFileDialog,
        QMessageBox, QSlider, QApplication,
    )
    import pyqtgraph as pg
    from pyqtgraph_display import TacticalMapWidget
    GUI_AVAILABLE = True
    PYQTGRAPH_AVAILABLE = True
    print("[OK] PyQt5 + PyQtGraph available")
except ImportError as _qt_err:
    GUI_AVAILABLE = False
    PYQTGRAPH_AVAILABLE = False
    print(f"[WARN] PyQt5/PyQtGraph not available: {_qt_err}")

# --- Dependency Handling (개별 import — 하나 실패해도 나머지 동작) ---

# ① 핵심: 시나리오 + 데이터 클래스 + CleanSlate Optimizer
try:
    from config_mip import MIPConfig, mip_config, EnhancedEngagementMatrix, KFactorCache
    from clean_slate_optimizer import Asset, InterceptorSystem, Threat, CleanSlateOptimizer
    MIP_AVAILABLE = True
    CLEANSLATE_AVAILABLE = True
except ImportError as e:
    MIP_AVAILABLE = False
    CLEANSLATE_AVAILABLE = False
    print(f"[CRITICAL] Core import failed: {e}")
    from dataclasses import dataclass
    @dataclass
    class Asset:
        id: str = ""; position: Tuple[float, float] = (0,0); value: float = 0; priority: int = 1; estimated_threat_missiles: List[str] = None
    @dataclass
    class InterceptorSystem:
        id: str = ""; system_type: str = ""; position: Tuple[float, float] = (0,0); available_missiles: int = 0; max_missiles_per_target: int = 0; intercept_probability: float = 0; engagement_range: float = 0
    @dataclass
    class Threat:
        id: str = ""; target_asset_id: str = ""; current_position: Tuple[float, float, float] = (0,0,0); estimated_impact_time: float = 0
    class MIPConfig:
        def __init__(self): self.scenario_type = "DWTA_BALANCED"
        def create_realistic_scenario(self, scenario_type=None):
            return {'name': 'Demo', 'assets': [], 'batteries': [], 'threats': [], 'engagement_matrix': {}}
    class EnhancedEngagementMatrix:
        def __init__(self): pass
        def precompute_all(self, *args, **kwargs): pass
    class KFactorCache:
        def __init__(self, *args, **kwargs): pass
    mip_config = MIPConfig()
    class CleanSlateOptimizer:
        def __init__(self, config=None): pass
        def create_model(self, *args, **kwargs): pass
        def solve(self): return {'feasible': False, 'objective_value': float('inf')}

# ② Legacy Optimizer stub (CleanSlate가 대체 — 하위 호환용)
NonLinearMIPOptimizer = CleanSlateOptimizer

# ④ 비교용 알고리즘 (선택)
try:
    from greedy_optimizer import GreedyOptimizer
except ImportError:
    GreedyOptimizer = None

try:
    from ga_optimizer import GeneticAlgorithmOptimizer
except ImportError:
    GeneticAlgorithmOptimizer = None

# ⑤ 확률 샘플링 (scipy 필요 — 없으면 고정 Pk 사용)
try:
    from uncertainty_modeling import UncertaintyModeling, UncertaintyConfig
except ImportError:
    print("[INFO] scipy not available — using fixed Pk (no Beta sampling)")
    class UncertaintyConfig:
        def __init__(self, **kwargs): pass
    class UncertaintyModeling:
        def __init__(self, config): pass
        def sample_intercept_probability(self, base_prob): return base_prob

# ⑥ 성능 로거 (선택)
try:
    from performance_logger import PerformanceLogger
except ImportError:
    class PerformanceLogger:
        def __init__(self, **kwargs): pass
        def log_optimization(self, *args, **kwargs): pass

# ⑦ 시각화 확장 (선택)
VISUALIZATION_AVAILABLE = False
try:
    from realtime_dwta_visualizer import RealTimeDWTAVisualizer
    VISUALIZATION_AVAILABLE = True
except ImportError:
    pass

# Define Objective Functions
OBJECTIVES = {
    'MIN_DAMAGE': 'Minimize Expected Damage (Value-based)',
    'MAX_KILLS': 'Maximize Kills (Egalitarian)',
}

# 🔧 OPTIMIZED: 하이브리드 할당 관리자 (양방향 인덱스 + 비트마스크)
class OptimizedAssignmentManager:
    """
    하이브리드 자료구조: 빠른 쓰기 O(1) + 빠른 탐색 O(1)~O(k)
    - battery_to_threats: List[List[int]] - 배터리→위협 인덱스
    - threat_to_batteries: List[List[int]] - 위협→배터리 인덱스
    - battery_masks: np.ndarray[uint64] - 다중 청크 비트마스크 (300+ 위협 지원)

    🔧 OPTIMIZED: Multi-chunk bitmask for 300+ threats support
    """
    def __init__(self, max_threats: int = 300, max_batteries: int = 20):
        self.max_threats = max_threats
        self.max_batteries = max_batteries
        self.battery_to_threats: List[List[int]] = [[] for _ in range(max_batteries)]
        self.threat_to_batteries: List[List[int]] = [[] for _ in range(max_threats)]

        # 🆕 Multi-chunk bitmask: supports 300+ threats (5 chunks of 64 bits each)
        self.num_bitmask_chunks = (max_threats + 63) // 64
        self.battery_masks = np.zeros((max_batteries, self.num_bitmask_chunks), dtype=np.uint64)

        self.threat_id_to_idx: Dict[str, int] = {}
        self.battery_id_to_idx: Dict[str, int] = {}
        self.idx_to_threat_id: Dict[int, str] = {}
        self.idx_to_battery_id: Dict[int, str] = {}
        self.next_threat_idx = 0
        self.next_battery_idx = 0
        self._total_assignments = 0
    
    def register_threat(self, threat_id: str) -> int:
        if threat_id in self.threat_id_to_idx:
            return self.threat_id_to_idx[threat_id]
        if self.next_threat_idx >= self.max_threats:
            raise ValueError(f"최대 위협 수 초과: {self.max_threats}")
        idx = self.next_threat_idx
        self.threat_id_to_idx[threat_id] = idx
        self.idx_to_threat_id[idx] = threat_id
        self.next_threat_idx += 1
        return idx
    
    def register_battery(self, battery_id: str) -> int:
        if battery_id in self.battery_id_to_idx:
            return self.battery_id_to_idx[battery_id]
        if self.next_battery_idx >= self.max_batteries:
            raise ValueError(f"최대 배터리 수 초과: {self.max_batteries}")
        idx = self.next_battery_idx
        self.battery_id_to_idx[battery_id] = idx
        self.idx_to_battery_id[idx] = battery_id
        self.next_battery_idx += 1
        return idx
    
    def assign(self, threat_id: str, battery_id: str) -> bool:
        if threat_id not in self.threat_id_to_idx:
            self.register_threat(threat_id)
        if battery_id not in self.battery_id_to_idx:
            self.register_battery(battery_id)
        t_idx = self.threat_id_to_idx[threat_id]
        b_idx = self.battery_id_to_idx[battery_id]

        # 🆕 Multi-chunk bitmask check
        chunk_idx = t_idx // 64
        bit_pos = t_idx % 64

        # Check if already assigned using chunk-based bitmask
        if (self.battery_masks[b_idx, chunk_idx] & np.uint64(1 << bit_pos)) != 0:
            return False

        # Add assignment
        self.battery_to_threats[b_idx].append(t_idx)
        self.threat_to_batteries[t_idx].append(b_idx)

        # Set bitmask bit
        self.battery_masks[b_idx, chunk_idx] |= np.uint64(1 << bit_pos)
        self._total_assignments += 1
        return True
    
    def unassign(self, threat_id: str, battery_id: str) -> bool:
        if threat_id not in self.threat_id_to_idx or battery_id not in self.battery_id_to_idx:
            return False
        t_idx = self.threat_id_to_idx[threat_id]
        b_idx = self.battery_id_to_idx[battery_id]
        if t_idx not in self.battery_to_threats[b_idx]:
            return False

        # Remove assignment
        self.battery_to_threats[b_idx].remove(t_idx)
        self.threat_to_batteries[t_idx].remove(b_idx)

        # 🆕 Multi-chunk bitmask unset
        chunk_idx = t_idx // 64
        bit_pos = t_idx % 64
        self.battery_masks[b_idx, chunk_idx] &= ~np.uint64(1 << bit_pos)

        self._total_assignments -= 1
        return True
    
    def get_batteries_for_threat(self, threat_id: str) -> List[str]:
        if threat_id not in self.threat_id_to_idx:
            return []
        t_idx = self.threat_id_to_idx[threat_id]
        return [self.idx_to_battery_id[b_idx] for b_idx in self.threat_to_batteries[t_idx]]
    
    def get_threats_for_battery(self, battery_id: str) -> List[str]:
        if battery_id not in self.battery_id_to_idx:
            return []
        b_idx = self.battery_id_to_idx[battery_id]
        return [self.idx_to_threat_id[t_idx] for t_idx in self.battery_to_threats[b_idx]]
    
    def get(self, battery_id: str, default=None) -> List[str]:
        """딕셔너리 호환성: get 메서드"""
        return self.get_threats_for_battery(battery_id) if self.get_threats_for_battery(battery_id) else (default if default is not None else [])
    
    def items(self):
        """딕셔너리 호환성: items 메서드"""
        for b_idx in range(self.next_battery_idx):
            battery_id = self.idx_to_battery_id[b_idx]
            threats = self.get_threats_for_battery(battery_id)
            if threats:
                yield (battery_id, threats)
    
    def keys(self):
        """딕셔너리 호환성: keys 메서드"""
        for b_idx in range(self.next_battery_idx):
            if len(self.battery_to_threats[b_idx]) > 0:
                yield self.idx_to_battery_id[b_idx]
    
    def values(self):
        """딕셔너리 호환성: values 메서드"""
        for b_idx in range(self.next_battery_idx):
            threats = self.get_threats_for_battery(self.idx_to_battery_id[b_idx])
            if threats:
                yield threats
    
    def __getitem__(self, battery_id: str) -> List[str]:
        """딕셔너리 호환성: [] 연산자"""
        return self.get_threats_for_battery(battery_id)
    
    def __setitem__(self, battery_id: str, threat_list: List[str]):
        """딕셔너리 호환성: [] 할당"""
        if battery_id not in self.battery_id_to_idx:
            self.register_battery(battery_id)
        b_idx = self.battery_id_to_idx[battery_id]
        old_threats = self.battery_to_threats[b_idx].copy()
        for t_idx in old_threats:
            threat_id = self.idx_to_threat_id[t_idx]
            self.unassign(threat_id, battery_id)
        for threat_id in threat_list:
            self.assign(threat_id, battery_id)
    
    def __contains__(self, battery_id: str) -> bool:
        """딕셔너리 호환성: in 연산자"""
        if battery_id not in self.battery_id_to_idx:
            return False
        b_idx = self.battery_id_to_idx[battery_id]
        return len(self.battery_to_threats[b_idx]) > 0
    
    def __delitem__(self, battery_id: str):
        """딕셔너리 호환성: del 연산자"""
        if battery_id not in self.battery_id_to_idx:
            return
        b_idx = self.battery_id_to_idx[battery_id]
        threats_copy = self.battery_to_threats[b_idx].copy()
        for t_idx in threats_copy:
            threat_id = self.idx_to_threat_id[t_idx]
            self.unassign(threat_id, battery_id)
    
    def get_total_assignments(self) -> int:
        return self._total_assignments
    
    def get_all_assigned_threats(self) -> Set[str]:
        assigned = set()
        for t_idx in range(self.next_threat_idx):
            if len(self.threat_to_batteries[t_idx]) > 0:
                assigned.add(self.idx_to_threat_id[t_idx])
        return assigned
    
    def clear(self):
        self.battery_to_threats = [[] for _ in range(self.max_batteries)]
        self.threat_to_batteries = [[] for _ in range(self.max_threats)]
        self.battery_masks.fill(0)
        self._total_assignments = 0
    
    def merge_assignments(self, new_assignments: Dict[str, List[str]], active_threat_ids: Set[str]):
        """
        새로운 할당으로 병합 (MIP 제약 조건 준수)
        
        제약 조건:
        - 위협당 상층 최대 1개 배터리
        - 위협당 하층 최대 1개 배터리
        - 총 최대 2개 배터리
        """
        # 1단계: 비활성 위협 제거
        for t_idx in range(self.next_threat_idx):
            threat_id = self.idx_to_threat_id.get(t_idx)
            if threat_id and threat_id not in active_threat_ids:
                battery_indices = self.threat_to_batteries[t_idx].copy()
                for b_idx in battery_indices:
                    battery_id = self.idx_to_battery_id[b_idx]
                    self.unassign(threat_id, battery_id)
        
        # 2단계: 새 플랜에 포함된 포대의 기존 할당을 전부 초기화
        # (옵티마이저 결과는 매 사이클 완전한 새 플랜 → 포대별로 replace)
        for battery_id in new_assignments:
            if battery_id in self.battery_id_to_idx:
                b_idx = self.battery_id_to_idx[battery_id]
                threats_copy = self.battery_to_threats[b_idx].copy()
                for t_idx in threats_copy:
                    threat_id = self.idx_to_threat_id[t_idx]
                    self.unassign(threat_id, battery_id)
        
        # 3단계: 새 할당 추가
        for battery_id, threat_list in new_assignments.items():
            for threat_id in threat_list:
                if threat_id in active_threat_ids:
                    self.assign(threat_id, battery_id)

class DWTAMainWindow(QMainWindow):
    """
    DWTA 단일 PyQt5 메인 윈도우.
    tkinter ControlPanel + matplotlib figure 를 완전히 대체한다.

    시그널 (크로스스레드 안전):
      sig_status_update  — 시뮬 스레드 → 임무 상황 라벨 갱신
      sig_log_message    — 시뮬 스레드 → 이벤트 로그 삽입
      sig_kill_event     — 시뮬 스레드 → 플래시 애니메이션 트리거
      sig_solver_update  — 시뮬 스레드 → 솔버 시간/Warm-start/목적함수 갱신
    """

    sig_status_update = pyqtSignal(dict)
    sig_log_message   = pyqtSignal(str, str)    # (message, level)
    sig_kill_event    = pyqtSignal(str, str)    # (missile_id, result)
    sig_solver_update = pyqtSignal(str, str)    # (key, value)

    # ------------------------------------------------------------------ init

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker

        # 시뮬레이션 제어 플래그 (sim thread가 읽음)
        self.running = False
        self.paused  = False
        self._sim_thread = None
        self._sim_start_time = None
        self._threat_row_map: dict = {}    # mid → row index (누적 로그용)
        self._threat_last_state: dict = {}  # mid → (tta_str, danger, d_color, bat_str) 마지막 활성 상태

        # 시나리오 목록 캐시
        try:
            from config_mip import ScenarioManager
            self._scenario_list = list(ScenarioManager.get_scenario_list().keys())
        except Exception:
            self._scenario_list = ["BASELINE_15"]

        # UI 구축
        self.setWindowTitle("DWTA 실시간 전술 운용 시스템")
        self.resize(1680, 960)
        self._apply_stylesheet()
        self._build_layout()

        # QTimer (250 ms, main thread) — display + table refresh
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(250)
        self._display_timer.timeout.connect(self._on_display_tick)

        # 신호-슬롯 연결
        self.sig_status_update.connect(self._update_status_labels)
        self.sig_log_message.connect(self._append_log)
        self.sig_kill_event.connect(self._handle_kill_event)
        self.sig_solver_update.connect(self._update_solver_info)

        # Blink timer for alert bar
        self._blink_state = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._blink_alert)

        # 이전 kill_results snapshot (이벤트 감지용)
        self._prev_kill_count = 0
        self._prev_stats: dict = {'intercepted': 0, 'missed': 0, 'active': 0}

    # ------------------------------------------------------------------ stylesheet

    def _apply_stylesheet(self):
        QApplication.instance().setStyle('Fusion')
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0a0a0a;
                color: #cccccc;
                font-family: Consolas, monospace;
                font-size: 9pt;
            }
            QGroupBox {
                border: 1px solid #2a4a2a;
                border-radius: 3px;
                margin-top: 6px;
                color: #00ff00;
                font-weight: bold;
                font-size: 8pt;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #1a3a1a;
                color: #00ff00;
                border: 1px solid #2a4a2a;
                border-radius: 3px;
                padding: 4px 10px;
                min-width: 60px;
            }
            QPushButton:hover  { background-color: #2a5a2a; }
            QPushButton:pressed{ background-color: #0a2a0a; }
            QPushButton:disabled { color: #445544; border-color: #1a2a1a; }
            QComboBox {
                background-color: #141414;
                color: #00ff00;
                border: 1px solid #2a4a2a;
                padding: 2px 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #141414;
                color: #00ff00;
                selection-background-color: #2a4a2a;
            }
            QSpinBox, QDoubleSpinBox, QSlider {
                background-color: #141414;
                color: #00ff00;
                border: 1px solid #2a4a2a;
            }
            QCheckBox, QRadioButton {
                color: #00ff00;
            }
            QTextEdit {
                background-color: #0d0d0d;
                color: #00ff00;
                border: 1px solid #1a2a1a;
            }
            QTableWidget {
                background-color: #0d0d0d;
                color: #cccccc;
                gridline-color: #1e1e1e;
                border: 1px solid #1a2a1a;
            }
            QTableWidget::item:selected {
                background-color: #1a3a1a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #111f11;
                color: #00ff00;
                border: 1px solid #1a2a1a;
                padding: 3px;
            }
            QSplitter::handle { background-color: #2a3a2a; }
            QSplitter::handle:hover { background-color: #005500; }
            QSplitter::handle:horizontal { width: 5px; }
            QSplitter::handle:vertical { height: 5px; }
            QLabel#AlertLabel {
                font-size: 9pt;
                font-weight: bold;
            }
        """)

    # ------------------------------------------------------------------ layout

    def _build_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        # 좌우 분할 스플리터 (드래그로 크기 조절)
        self._h_splitter = QSplitter(QtCore.Qt.Horizontal)
        self._h_splitter.setHandleWidth(5)
        self._h_splitter.addWidget(self._build_left_panel())
        self._h_splitter.addWidget(self._build_right_panel())
        self._h_splitter.setSizes([390, 1290])
        self._h_splitter.setStretchFactor(0, 0)
        self._h_splitter.setStretchFactor(1, 1)
        root.addWidget(self._h_splitter)

    def _build_left_panel(self) -> QWidget:
        # 상단 고정 섹션 (컨트롤 + 상태)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 4, 0)
        top_layout.setSpacing(4)
        top_layout.addWidget(self._build_sim_controls())
        top_layout.addWidget(self._build_mission_status())

        # 하단 가변 섹션 (위협 테이블 + 이벤트 로그) — 세로 스플리터
        bottom_split = QSplitter(QtCore.Qt.Vertical)
        bottom_split.setHandleWidth(5)
        bottom_split.addWidget(self._build_threat_table())
        bottom_split.addWidget(self._build_event_log())
        bottom_split.setSizes([220, 340])

        # 전체 좌측 세로 스플리터
        v_split = QSplitter(QtCore.Qt.Vertical)
        v_split.setHandleWidth(4)
        v_split.addWidget(top)
        v_split.addWidget(bottom_split)
        v_split.setSizes([300, 560])
        v_split.setStretchFactor(0, 0)
        v_split.setStretchFactor(1, 1)
        return v_split

    def _build_right_panel(self) -> QWidget:
        # 전술 맵 + 배터리 테이블 — 세로 스플리터
        v_split = QSplitter(QtCore.Qt.Vertical)
        v_split.setHandleWidth(5)

        self.tactical_map = TacticalMapWidget(self.tracker)
        v_split.addWidget(self.tactical_map)
        v_split.addWidget(self._build_battery_table())
        v_split.setSizes([740, 160])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        # 경보바는 아래 고정 (스플리터 밖)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(v_split, stretch=1)
        layout.addWidget(self._build_alert_bar())
        return w

    # ------------------------------------------------------------------ left sub-panels

    def _build_sim_controls(self) -> QGroupBox:
        box = QGroupBox("SIMULATION CONTROL")
        g = QVBoxLayout(box)
        g.setSpacing(4)

        # Row 0: Scenario
        r0 = QHBoxLayout()
        r0.addWidget(QLabel("시나리오:"))
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(self._scenario_list)
        current_scenario = getattr(self.tracker.config, 'scenario_type', 'BASELINE_15')
        if current_scenario in self._scenario_list:
            self.scenario_combo.setCurrentText(current_scenario)
        r0.addWidget(self.scenario_combo, stretch=1)
        g.addLayout(r0)

        # Row 1: Objective
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("목적함수:"))
        self.objective_combo = QComboBox()
        self.objective_combo.addItems(list(OBJECTIVES.keys()))
        self.objective_combo.setCurrentText(self.tracker.objective)
        r1.addWidget(self.objective_combo, stretch=1)
        g.addLayout(r1)

        # Row 2: Algorithm
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("알고리즘:"))
        self._algo_group = QButtonGroup(self)
        for label, key in [("MIP", "MIP"), ("Greedy", "Greedy"), ("GA", "GA")]:
            rb = QRadioButton(label)
            rb.setObjectName(f"algo_{key}")
            self._algo_group.addButton(rb)
            r2.addWidget(rb)
            if key == "MIP":
                rb.setChecked(True)
        g.addLayout(r2)

        # Row 3: Speed + Max Duration
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("속도:"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 5.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setFixedWidth(60)
        r3.addWidget(self.speed_spin)
        r3.addWidget(QLabel("x    최대:"))
        self.max_dur_spin = QSpinBox()
        self.max_dur_spin.setRange(300, 5000)
        self.max_dur_spin.setValue(1600)
        self.max_dur_spin.setFixedWidth(60)
        r3.addWidget(self.max_dur_spin)
        r3.addWidget(QLabel("s"))
        r3.addStretch()
        g.addLayout(r3)

        # Row 4: Checkboxes
        r4 = QHBoxLayout()
        self.warmstart_check = QCheckBox("Warm-start")
        self.warmstart_check.setChecked(False)
        self.logging_check = QCheckBox("로그 자동 저장")
        r4.addWidget(self.warmstart_check)
        r4.addWidget(self.logging_check)
        r4.addStretch()
        g.addLayout(r4)

        # Row 5: Buttons
        r5 = QHBoxLayout()
        self.start_btn  = QPushButton("▶ 시작")
        self.pause_btn  = QPushButton("⏸ 일시정지")
        self.stop_btn   = QPushButton("⏹ 정지")
        self.reset_btn  = QPushButton("↺ 리셋")
        for btn in (self.pause_btn, self.stop_btn):
            btn.setEnabled(False)
        self.start_btn.clicked.connect(self.on_start)
        self.pause_btn.clicked.connect(self.on_pause)
        self.stop_btn.clicked.connect(self.on_stop)
        self.reset_btn.clicked.connect(self.on_reset)
        for btn in (self.start_btn, self.pause_btn, self.stop_btn, self.reset_btn):
            r5.addWidget(btn)
        g.addLayout(r5)

        # Wire algorithm group
        self._algo_group.buttonClicked.connect(self._on_algo_changed)
        self.scenario_combo.currentTextChanged.connect(self._on_scenario_changed)
        self.objective_combo.currentTextChanged.connect(self._on_objective_changed)
        self.warmstart_check.toggled.connect(self._on_warmstart_toggled)
        self.logging_check.toggled.connect(self._on_logging_toggled)

        return box

    def _build_mission_status(self) -> QGroupBox:
        box = QGroupBox("MISSION STATUS")
        g = QVBoxLayout(box)
        g.setSpacing(2)

        self._status_labels: dict = {}
        fields = [
            ("time",     "T",         "#0099ff"),
            ("active",   "Active",    "#ffff00"),
            ("intercept","Kill",      "#00ff88"),
            ("missed",   "Miss",      "#ff4444"),
            ("rate",     "Rate",      "#00ff00"),
            ("obj",      "Obj",       "#ff9900"),
            ("solver",   "Solver",    "#aaaaaa"),
            ("warmstart","WarmStart", "#aaaaaa"),
        ]
        for i in range(0, len(fields), 2):
            row = QHBoxLayout()
            for key, text, color in fields[i:i+2]:
                lbl_name = QLabel(f"{text}:")
                lbl_name.setFixedWidth(68)
                lbl_val = QLabel("—")
                lbl_val.setStyleSheet(f"color: {color}; font-weight: bold;")
                lbl_val.setMinimumWidth(90)
                self._status_labels[key] = lbl_val
                row.addWidget(lbl_name)
                row.addWidget(lbl_val)
            row.addStretch()
            g.addLayout(row)
        return box

    def _build_threat_table(self) -> QGroupBox:
        box = QGroupBox("THREAT TRACK TABLE")
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)

        self.threat_table = QTableWidget(0, 5)
        self.threat_table.setHorizontalHeaderLabels(
            ["ID", "TTA(s)", "위험도", "배터리", "상태"]
        )
        self.threat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.threat_table.verticalHeader().setVisible(False)
        self.threat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.threat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.threat_table.setAlternatingRowColors(True)
        self.threat_table.setStyleSheet(
            "QTableWidget { alternate-background-color: #0f0f0f; }"
        )
        v.addWidget(self.threat_table)
        return box

    def _build_event_log(self) -> QGroupBox:
        box = QGroupBox("EVENT LOG")
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QtGui.QFont("Consolas", 8))
        v.addWidget(self.log_text)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("지우기")
        save_btn  = QPushButton("저장")
        clear_btn.setFixedWidth(60)
        save_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.log_text.clear)
        save_btn.clicked.connect(self._save_log)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return box

    def _build_battery_table(self) -> QGroupBox:
        box = QGroupBox("BATTERY STATUS")
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)

        self.battery_table = QTableWidget(0, 5)
        self.battery_table.setHorizontalHeaderLabels(
            ["ID", "종류", "잔탄", "교전중", "상태"]
        )
        self.battery_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.battery_table.verticalHeader().setVisible(False)
        self.battery_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.battery_table.setMinimumHeight(80)
        v.addWidget(self.battery_table)
        return box

    def _build_alert_bar(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFixedHeight(28)
        frame.setStyleSheet("background-color: #0a0a0a; border: 1px solid #1a2a1a;")
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 2, 8, 2)
        self.alert_label = QLabel("시스템 준비")
        self.alert_label.setObjectName("AlertLabel")
        self.alert_label.setStyleSheet("color: #444444;")
        h.addWidget(self.alert_label)
        self._alert_frame = frame
        return frame

    # ------------------------------------------------------------------ simulation control slots

    @pyqtSlot()
    def on_start(self):
        if self.running:
            return
        self.running = True
        self.paused  = False
        self._sim_start_time = time.time()

        # Apply current UI settings to tracker
        self.tracker.objective = self.objective_combo.currentText()
        algo = next(
            (b.objectName().replace('algo_', '')
             for b in self._algo_group.buttons() if b.isChecked()),
            'MIP'
        )
        if hasattr(self.tracker, 'current_algorithm'):
            self.tracker.current_algorithm = algo
        if hasattr(self.tracker, 'enable_logging'):
            self.tracker.enable_logging = self.logging_check.isChecked()

        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)

        # 누적 테이블 초기화 (새 시뮬레이션 시작)
        self._threat_row_map.clear()
        self._threat_last_state.clear()
        self.threat_table.setRowCount(0)
        self.battery_table.setRowCount(0)

        self._append_log(f"시뮬레이션 시작 — {OBJECTIVES[self.tracker.objective]}", "SUCCESS")
        self._append_log(f"시나리오: {self.scenario_combo.currentText()}, 배속: {self.speed_spin.value():.1f}x", "INFO")

        self._display_timer.start()

        self._sim_thread = threading.Thread(
            target=self._run_sim_thread, daemon=True
        )
        self._sim_thread.start()

    @pyqtSlot()
    def on_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.setText("▶ 재개")
            self._append_log("시뮬레이션 일시정지", "WARNING")
        else:
            self.pause_btn.setText("⏸ 일시정지")
            self._append_log("시뮬레이션 재개", "SUCCESS")

    @pyqtSlot()
    def on_stop(self):
        self.running = False
        self.paused  = False
        # 타이머 멈추기 전 최종 갱신 (마지막 상태 유지)
        self._refresh_threat_table()
        self._refresh_battery_table()
        self._display_timer.stop()
        self._blink_timer.stop()
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸ 일시정지")
        self.stop_btn.setEnabled(False)
        self._append_log("시뮬레이션 정지", "WARNING")

    @pyqtSlot()
    def on_reset(self):
        self.on_stop()
        if hasattr(self.tracker, 'missiles'):
            self.tracker.missiles.clear()
            self.tracker.kill_results.clear()
            self.tracker.primary_assignments.clear()
            self.tracker.current_time_step = 0
            self.tracker.stats = {
                'intercepted': 0, 'missed': 0, 'active': 0,
                'total': 0, 'retargeted': 0, 'tracked_misses': []
            }
        self._threat_row_map.clear()
        self._threat_last_state.clear()
        for key, lbl in self._status_labels.items():
            lbl.setText("—")
        self.threat_table.setRowCount(0)
        self.battery_table.setRowCount(0)
        self.alert_label.setText("시스템 준비")
        self.alert_label.setStyleSheet("color: #444444;")
        self._alert_frame.setStyleSheet(
            "background-color: #0a0a0a; border: 1px solid #1a2a1a;"
        )
        self._prev_stats = {'intercepted': 0, 'missed': 0, 'active': 0}
        self._prev_kill_count = 0
        # Reset tactical map state
        if hasattr(self, 'tactical_map'):
            self.tactical_map._last_assignments = {}
            self.tactical_map._last_battery_ammo = {}
            self.tactical_map._update_assets()
        self._append_log("시뮬레이션 리셋", "INFO")

    # ------------------------------------------------------------------ config change handlers

    def _on_scenario_changed(self, new_scenario: str):
        if self.running:
            QMessageBox.warning(self, "경고", "시뮬레이션 실행 중에는 시나리오를 변경할 수 없습니다.")
            self.scenario_combo.setCurrentText(
                getattr(self.tracker.config, 'scenario_type', 'BASELINE_15')
            )
            return
        reply = QMessageBox.question(
            self, "시나리오 변경",
            f"시나리오를 '{new_scenario}'로 변경하시겠습니까?\n현재 상태가 초기화됩니다.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.tracker.config.scenario_type = new_scenario
                self.tracker._load_scenario()
                self.tracker.missiles.clear()
                self.tracker.kill_results.clear()
                self.tracker.primary_assignments.clear()
                self.tracker.current_time_step = 0
                self.tracker.stats = {
                    'intercepted': 0, 'missed': 0, 'active': 0,
                    'total': 0, 'retargeted': 0, 'tracked_misses': []
                }
                # Redraw static map elements (assets/batteries/rings)
                self.tactical_map._last_assignments = {}
                self.tactical_map._last_battery_ammo = {}
                self.tactical_map.clear()
                self.tactical_map._configure_plot()
                self.tactical_map._init_static_items()
                self.tactical_map._draw_range_rings()
                self.tactical_map._update_assets()
                self._append_log(f"시나리오 변경: {new_scenario}", "SUCCESS")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"시나리오 변경 실패: {e}")
                self._append_log(f"시나리오 변경 오류: {e}", "ERROR")
                self.scenario_combo.setCurrentText(
                    getattr(self.tracker.config, 'scenario_type', 'BASELINE_15')
                )
        else:
            self.scenario_combo.setCurrentText(
                getattr(self.tracker.config, 'scenario_type', 'BASELINE_15')
            )

    def _on_objective_changed(self, key: str):
        if hasattr(self.tracker, 'objective'):
            self.tracker.objective = key
            self._append_log(f"목적함수 변경: {OBJECTIVES.get(key, key)}", "INFO")

    def _on_algo_changed(self, btn):
        algo = btn.objectName().replace('algo_', '')
        if hasattr(self.tracker, 'current_algorithm'):
            self.tracker.current_algorithm = algo
        self._append_log(f"알고리즘 변경: {algo}", "INFO")
        # Warm-start only available for MIP
        ws_ok = (algo == "MIP")
        self.warmstart_check.setEnabled(ws_ok)
        if not ws_ok:
            self.warmstart_check.setChecked(False)

    def _on_warmstart_toggled(self, enabled: bool):
        if not enabled and hasattr(self.tracker, 'mip_optimizer_instance'):
            try:
                delattr(self.tracker, 'mip_optimizer_instance')
            except AttributeError:
                pass
        self._append_log(
            f"Warm-start {'활성화' if enabled else '비활성화'}", "INFO"
        )

    def _on_logging_toggled(self, enabled: bool):
        if hasattr(self.tracker, 'enable_logging'):
            self.tracker.enable_logging = enabled

    # ------------------------------------------------------------------ simulation thread

    def _run_sim_thread(self):
        """Simulation background thread (mirrors ControlPanel.run_simulation_thread)."""
        try:
            self.sig_log_message.emit("=== SIMULATION START (T=0) ===", "INFO")
            self.tracker.start_scenario()
            self.sig_log_message.emit(
                f"Scenario: {self.tracker.scenario_data.get('name', '?')}  "
                f"Batteries: {len(self.tracker.batteries)}  "
                f"Assets: {len(self.tracker.assets)}  "
                f"Threats: {len(self.tracker.missiles)} registered",
                "INFO"
            )

            while self.running:
                if not self.paused:
                    with self.tracker._sim_lock:
                        self.tracker.update_simulation()
                        self.tracker.run_realtime_dwta()

                    # Emit stats for status labels
                    self.sig_status_update.emit(self.tracker.stats.copy())

                    # Event detection
                    cur = self.tracker.stats
                    if cur['intercepted'] > self._prev_stats['intercepted']:
                        self.sig_log_message.emit("요격 성공!", "INTERCEPT")
                    if cur['missed'] > self._prev_stats['missed']:
                        self.sig_log_message.emit("요격 실패", "WARNING")
                    new_active = cur['active'] - self._prev_stats['active']
                    if new_active > 0:
                        self.sig_log_message.emit(
                            f"{new_active}개 새로운 위협 발견", "INFO"
                        )
                    self._prev_stats = cur.copy()

                    # Kill flash events (only new entries)
                    total_kills = len(self.tracker.kill_results)
                    if total_kills > self._prev_kill_count:
                        for mid, (result, _, _) in list(self.tracker.kill_results.items()):
                            if result in ('INTERCEPTED', 'MISSED'):
                                m = self.tracker.missiles.get(mid)
                                if m:
                                    self.sig_kill_event.emit(mid, result)
                        self._prev_kill_count = total_kills

                    if self._should_terminate():
                        break

                time.sleep(0.05 / max(self.speed_spin.value(), 0.1))

        except Exception as e:
            self.sig_log_message.emit(f"시뮬레이션 오류: {e}", "ERROR")
        finally:
            QTimer.singleShot(0, self._on_sim_finished)

    def _should_terminate(self) -> bool:
        if self.tracker.current_time_step >= self.max_dur_spin.value():
            return True
        all_launched = all(
            m['launch_time'] <= self.tracker.current_time_step
            for m in self.tracker.missiles.values()
        )
        all_resolved = (
            len(self.tracker.kill_results) == self.tracker.stats.get('total', 0)
        )
        no_active = self.tracker.stats.get('active', 0) == 0
        return all_launched and all_resolved and no_active

    def _on_sim_finished(self):
        """Called on main thread when simulation thread exits."""
        self.running = False

        # 타이머 멈추기 전 최종 테이블 갱신
        self._refresh_threat_table()
        self._refresh_battery_table()
        self._refresh_alert_bar()

        self._display_timer.stop()
        self._blink_timer.stop()

        if hasattr(self.tracker, 'finalize_simulation'):
            self.tracker.finalize_simulation()

        elapsed = time.time() - self._sim_start_time if self._sim_start_time else 0
        stats = self.tracker.stats
        deviated = stats.get('deviated', 0)
        actual = stats['total'] - deviated
        rate = min((stats['intercepted'] / actual * 100) if actual > 0 else 0, 100.0)

        self._append_log("=== SIMULATION COMPLETE ===", "SUCCESS")
        self._append_log(
            f"총위협:{stats['total']}  이탈:{deviated}  실제:{actual}  "
            f"요격:{stats['intercepted']}  실패:{stats['missed']}  성공률:{rate:.1f}%",
            "INFO"
        )
        self._append_log(
            f"실제 실행시간: {elapsed:.2f}s  시뮬시간: {self.tracker.current_time_step}s",
            "INFO"
        )

        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸ 일시정지")
        self.stop_btn.setEnabled(False)

        msg = (
            f"시뮬레이션 완료!\n\n"
            f"총 위협: {stats['total']}발  (이탈: {deviated})\n"
            f"요격 성공: {stats['intercepted']}발\n"
            f"요격 실패: {stats['missed']}발\n"
            f"성공률: {rate:.1f}%\n\n"
            f"실제 실행시간: {elapsed:.2f}s\n"
            f"시뮬레이션 시간: {self.tracker.current_time_step}s"
        )
        QMessageBox.information(self, "시뮬레이션 완료", msg)

    # ------------------------------------------------------------------ QTimer tick

    def _on_display_tick(self):
        """Fires every 250 ms on the main thread — refresh all visual elements."""
        if not self.tracker._sim_lock.acquire(blocking=False):
            return
        try:
            try:
                self.tactical_map.update_display()
            except Exception as e:
                print(f"[WARN] tactical_map update error: {e}")
            self._refresh_threat_table()
            self._refresh_battery_table()
            self._refresh_alert_bar()
        finally:
            self.tracker._sim_lock.release()

    # ------------------------------------------------------------------ table refresh

    @staticmethod
    def _compute_tta(missile: dict) -> float:
        if not missile.get('active', False):
            return float('inf')
        remaining = max(1.0 - missile.get('flight_progress', 0.0), 0.0)
        return missile.get('flight_time', 300) * remaining

    def _refresh_threat_table(self):
        """누적 로그 방식: 신규 위협은 행 추가, 기존 위협은 상태만 갱신."""
        missiles   = self.tracker.missiles
        kill_res   = self.tracker.kill_results
        assign_mgr = self.tracker.primary_assignments

        self.threat_table.setUpdatesEnabled(False)
        scroll_to_bottom = False

        for mid, m in missiles.items():
            if mid in kill_res:
                result_str = kill_res[mid][0]
                if result_str == 'INTERCEPTED':
                    status, s_color = "INTERCEPT", "#00ccff"
                elif result_str == 'DEVIATED':
                    status, s_color = "이탈",      "#888888"
                else:
                    status, s_color = "MISSED",    "#ff4444"
                # 마지막 활성 상태(TTA, 위험도, 배터리) 보존
                last = self._threat_last_state.get(mid, ("—", "—", "#888888", "—"))
                tta_str, danger, d_color, bat_str = last
            elif m.get('active'):
                tta = self._compute_tta(m)
                if tta < 30:
                    danger, d_color = "HIGH", "#ff4444"
                elif tta < 60:
                    danger, d_color = "MED",  "#ffcc00"
                else:
                    danger, d_color = "LOW",  "#00cc44"
                batteries = assign_mgr.get_batteries_for_threat(mid)
                status    = "ENGAGED" if batteries else "TRACKED"
                s_color   = "#00ccff" if batteries else "#aaaaaa"
                tta_str   = f"{tta:.0f}"
                bat_str   = ", ".join(b.replace('LSAM_BATTERY_','L').replace('MSAM_BATTERY_','M')
                                        .replace('LSAM_','L').replace('MSAM_','M')
                                      for b in batteries) or "—"
                # 현재 상태 스냅샷 저장 (요격/피격 후에도 마지막 값 유지용)
                self._threat_last_state[mid] = (tta_str, danger, d_color, bat_str)
            else:
                continue  # 아직 발사 전

            short_id = mid.replace('MISSILE_', 'M').replace('THREAT_', 'T')
            cells  = [short_id, tta_str, danger, bat_str, status]
            colors = ["#00ff00", "#00ff00", d_color, "#00ff00", s_color]

            if mid in self._threat_row_map:
                # 기존 행 갱신 (상태 변경만)
                row = self._threat_row_map[mid]
                for j, (cell, color) in enumerate(zip(cells, colors)):
                    item = self.threat_table.item(row, j)
                    if item is None:
                        item = QTableWidgetItem(cell)
                        item.setTextAlignment(QtCore.Qt.AlignCenter)
                        self.threat_table.setItem(row, j, item)
                    else:
                        item.setText(cell)
                    item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
            else:
                # 신규 위협 → 맨 아래에 행 추가 (이벤트 로그처럼 누적)
                row = self.threat_table.rowCount()
                self.threat_table.insertRow(row)
                self._threat_row_map[mid] = row
                for j, (cell, color) in enumerate(zip(cells, colors)):
                    item = QTableWidgetItem(cell)
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                    item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                    self.threat_table.setItem(row, j, item)
                scroll_to_bottom = True

        self.threat_table.setUpdatesEnabled(True)
        if scroll_to_bottom:
            self.threat_table.scrollToBottom()

    def _refresh_battery_table(self):
        batteries  = self.tracker.batteries
        assign_mgr = self.tracker.primary_assignments

        self.battery_table.setUpdatesEnabled(False)
        self.battery_table.setRowCount(len(batteries))
        for i, b in enumerate(batteries):
            bid   = b['id']
            ammo  = b.get('available_missiles', 0)
            stype = b.get('system_type', '—')
            engaging = len(assign_mgr.get_threats_for_battery(bid))

            if ammo == 0:
                status, s_color = "EMPTY",   "#ff4444"
            elif ammo < 5:
                status, s_color = "LOW_AMMO","#ff9900"
            elif engaging > 0:
                status, s_color = "ENGAGING","#00ccff"
            else:
                status, s_color = "READY",   "#00ff44"

            short_id = (bid.replace('LSAM_BATTERY_', 'L')
                           .replace('MSAM_BATTERY_', 'M')
                           .replace('LSAM_', 'L')
                           .replace('MSAM_', 'M'))
            # 무기체계별 고정 색 (맵 심볼과 동일: LSAM=주황, MSAM=청록)
            id_color = '#ff8800' if stype == 'LSAM' else '#00cccc'
            cells  = [short_id, stype, str(ammo), str(engaging), status]
            colors = [id_color, id_color, None, None, s_color]
            for j, (cell, color) in enumerate(zip(cells, colors)):
                item = QTableWidgetItem(cell)
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                if color:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                self.battery_table.setItem(i, j, item)
        self.battery_table.setUpdatesEnabled(True)

    def _refresh_alert_bar(self):
        """Flash alert bar if there are unengaged high-danger threats."""
        assign_mgr = self.tracker.primary_assignments
        unengaged = [
            mid for mid, m in self.tracker.missiles.items()
            if m.get('active')
            and self._compute_tta(m) < 60
            and not assign_mgr.get_batteries_for_threat(mid)
        ]
        if unengaged:
            n = len(unengaged)
            self.alert_label.setText(f"⚠ ALERT — {n}개 미교전 위협 (TTA<60s)")
            if not self._blink_timer.isActive():
                self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self.alert_label.setText("정상 — 미교전 위협 없음")
            self.alert_label.setStyleSheet("color: #00cc44;")
            self._alert_frame.setStyleSheet(
                "background-color: #0a0a0a; border: 1px solid #1a2a1a;"
            )

    def _blink_alert(self):
        self._blink_state = not self._blink_state
        if self._blink_state:
            self._alert_frame.setStyleSheet(
                "background-color: #3a0000; border: 1px solid #ff0000;"
            )
            self.alert_label.setStyleSheet("color: #ff4444; font-weight: bold;")
        else:
            self._alert_frame.setStyleSheet(
                "background-color: #1a0000; border: 1px solid #880000;"
            )
            self.alert_label.setStyleSheet("color: #cc2222;")

    # ------------------------------------------------------------------ signal slots

    @pyqtSlot(dict)
    def _update_status_labels(self, stats: dict):
        ts  = self.tracker.current_time_step
        dev = stats.get('deviated', 0)
        act = stats['total'] - dev
        rate = min((stats['intercepted'] / act * 100) if act > 0 else 0, 100.0)
        obj  = self.tracker.last_objective_value

        self._status_labels['time'].setText(f"T={ts}s")
        self._status_labels['active'].setText(str(stats.get('active', 0)))
        self._status_labels['intercept'].setText(str(stats.get('intercepted', 0)))
        self._status_labels['missed'].setText(str(stats.get('missed', 0)))
        self._status_labels['rate'].setText(f"{rate:.1f}%")
        if obj is not None and obj != float('inf'):
            self._status_labels['obj'].setText(f"{obj:.2f}")

    @pyqtSlot(str, str)
    def _append_log(self, message: str, level: str):
        """Insert a colour-coded log entry (always runs on main thread via signal)."""
        COLOR = {
            'INFO':      '#00ff00',
            'SUCCESS':   '#66ff66',
            'WARNING':   '#ff9900',
            'ERROR':     '#ff4444',
            'INTERCEPT': '#ff9900',
            'ASSIGN':    '#0099ff',
            'MISS':      '#ff6666',
            'LAUNCH':    '#ffff00',
            'TRAJECTORY':'#cc99ff',
            'DEBUG':     '#555555',
        }
        # Determine colour from message content overrides
        if 'INTERCEPT' in message.upper():
            color = COLOR['INTERCEPT']
        elif 'MISS' in message.upper():
            color = COLOR['MISS']
        elif 'LAUNCH' in message.upper():
            color = COLOR['LAUNCH']
        elif 'ASSIGN' in message.upper():
            color = COLOR['ASSIGN']
        else:
            color = COLOR.get(level, '#00ff00')

        ts = time.strftime("%H:%M:%S")
        html = (
            f'<span style="color:#555555">[{ts}]</span> '
            f'<span style="color:{color}">{message}</span>'
        )
        self.log_text.append(html)

        # Keep log buffer under 1000 lines
        doc = self.log_text.document()
        while doc.blockCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QtGui.QTextCursor.Start)
            cursor.select(QtGui.QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

    @pyqtSlot(str, str)
    def _handle_kill_event(self, missile_id: str, result: str):
        """Trigger flash animation on tactical map for intercept/miss."""
        m = self.tracker.missiles.get(missile_id)
        if m:
            x, y = m['position'][0], m['position'][1]
            self.tactical_map.trigger_kill_flash(x, y, success=(result == 'INTERCEPTED'))

    @pyqtSlot(str, str)
    def _update_solver_info(self, key: str, value: str):
        """Update solver time, warm-start, or objective value labels."""
        if key == 'solver_time':
            self._status_labels['solver'].setText(value)
        elif key == 'warmstart':
            self._status_labels['warmstart'].setText(value)
        elif key == 'objective':
            self._status_labels['obj'].setText(value)

    # ------------------------------------------------------------------ log save

    def _save_log(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "로그 저장", "", "텍스트 파일 (*.txt);;모든 파일 (*)"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
            except Exception as e:
                QMessageBox.critical(self, "오류", f"로그 저장 실패: {e}")

    # ------------------------------------------------------------------ interface for tracker compatibility

    def log_message(self, message: str, level: str = "INFO"):
        """Called by MultiMissileTracker internals. Thread-safe via signal."""
        if level == "DEBUG":
            return  # suppress debug
        self.sig_log_message.emit(message, level)

    def update_status(self, tracker):
        """Compatibility: tracker calls this after update_simulation()."""
        self.sig_status_update.emit(tracker.stats.copy())

    # ------------------------------------------------------------------ window close

    def closeEvent(self, event):
        if self.running:
            reply = QMessageBox.question(
                self, "종료",
                "시뮬레이션이 실행 중입니다. 종료하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.on_stop()
        self._display_timer.stop()
        self._blink_timer.stop()
        event.accept()


# ---------------------------------------------------------------------------
# Backwards-compatible alias so any code still referencing ControlPanel works
# ---------------------------------------------------------------------------
ControlPanel = DWTAMainWindow


# ===========================================================================
# Simulation Engine
# ===========================================================================
class MultiMissileTracker:
    """실시간 DWTA 분석 시뮬레이터 - GUI 지원 버전"""

    def __init__(self, use_mip=True, objective='MIN_DAMAGE', headless=False, use_pyqtgraph=False):
        self.use_mip = use_mip and MIP_AVAILABLE
        self.objective = objective
        self.headless = headless  # CLI 모드에서 GUI 비활성화
        self.use_pyqtgraph = use_pyqtgraph and PYQTGRAPH_AVAILABLE  # 🆕 Phase 2: PyQtGraph mode

        # Thread safety: 시뮬레이션 스레드와 디스플레이 스레드 간 공유 상태 보호
        self._sim_lock = threading.Lock()

        if objective not in OBJECTIVES:
            print(f"Warning: Unknown objective '{objective}'. Defaulting to 'MIN_DAMAGE'.")
            self.objective = 'MIN_DAMAGE'

        # GUI 초기화를 먼저: 사용자가 빈 창이 아닌 로딩 중인 창을 볼 수 있도록
        self.control_panel = None
        self.text_mode = self.headless
        self.pyqtgraph_display = None
        self.fig = None

        # DWTAMainWindow 빌드 시 config.scenario_type 접근 — 먼저 설정
        self.config = mip_config

        if not self.headless and GUI_AVAILABLE:
            try:
                self._qt_app = QApplication.instance() or QApplication(sys.argv)
                self.main_window = DWTAMainWindow(self)
                self.control_panel = self.main_window
                self.main_window.show()
                self._qt_app.processEvents()  # 창이 화면에 즉시 나타나도록
                print("[OK] DWTAMainWindow (PyQt5) 초기화 완료")
            except Exception as e:
                print(f"GUI 초기화 실패: {e}")
                self.control_panel = None

        # Load scenario (무거운 사전 계산 — GUI 창 이후 실행)
        self._load_scenario()
        #config_mip.py에서 데이터 추출:시나리오데이터, 자산 데이터, 포대 데이터, 초기 위협 정보, 교전 확률 매트릭스
        
        # Simulation State
        self.current_time_step = 0
        self.missiles = {} #미사일 객체 저장, 미사일 ID: 미사일 객체
        
        # Optimization Tracking
        # 🔧 OPTIMIZED: 하이브리드 자료구조로 교체 (딕셔너리 → 양방향 인덱스 + 비트마스크)
        # 성능: 탐색 O(1), 메모리 6배 절감 - 🆕 300 위협 지원
        self.primary_assignments = OptimizedAssignmentManager(max_threats=300, max_batteries=50)
        self.last_optimization_step = -99 #마지막 최적화 단계 -99는 최적화 미수항 상태.
        self.optimization_interval = 1 #최적화 간격(1초)

        # 🆕 Phase 1 Performance Caches (10-20% speedup)
        self._cached_active_threats_count = 0
        self._active_cache_valid = False
        self._cached_operational_batteries = []
        self._cached_total_ammo = 0
        self._battery_cache_valid = False
        self._battery_lookup = {}  # Persistent battery lookup cache

        # 🆕 성능 로깅 (Performance Logging) - 먼저 초기화
        self.performance_logger = PerformanceLogger(output_dir="performance_results")
        self.comparison_mode = False  # 비교 실험 모드
        self.current_algorithm = 'MIP'  # 기본: MIP Optimizer
        self.optimization_history = [] #최적화 이력
        self.optimization_count = 0 #최적화 횟수
        self.max_optimizations_per_timestep = 1 #최적화 최대 횟수
        
        # 🆕 Stress Test Metrics (자동 수집) - current_algorithm 이후 초기화
        try:
            from stress_test_metrics import StressTestMetrics
            self.stress_metrics = StressTestMetrics()
            self.stress_metrics.scenario_name = self.config.scenario_type
            self.stress_metrics.algorithm = self.current_algorithm  # 🔬 알고리즘 비교용
        except ImportError:
            self.stress_metrics = None
        
        # 🆕 불확실성 모델링 (Uncertainty Modeling)
        self.uncertainty_config = UncertaintyConfig(
            distribution_type="beta",  # 베타 분포
            beta_alpha=9.0,           # α=9 (높은 확률 편향)
            beta_beta=1.0,            # β=1
            monte_carlo_runs=1,       # 실시간은 1회만
            confidence_level=0.95
        )
        self.uncertainty_model = UncertaintyModeling(self.uncertainty_config)
        print("[OK] 불확실성 모델링 초기화 완료 (Beta 분포: α=9, β=1)")
        
        # 🆕 로그 수집 기능
        self.enable_logging = False  # 로그 자동 저장 플래그
        self.run_logs = []  # 실행 로그 저장
        
        # Statistics
        self.stats = {'intercepted': 0, 'missed': 0, 'active': 0, 'total': 0, 'retargeted': 0, 'tracked_misses': []}
        self.kill_results = {}  # {missile_id: (result, timestamp, battery_id)}
        
        # Shoot-look-shoot tracking
        self.engagement_attempts = {} #각 위협에 대한 교전 
        self.max_engagement_attempts = 3 #동일 위협에 대한 최대 교전 횟수
        self.shoot_look_shoot_enabled = True
        self.lookback_time = 4 #교전 결과 확인을 위한 대기 시간 4초초 
        
        # Real-time tracking
        self.last_objective_value = None
        self.last_solve_time = None
        
        # GUI 초기화는 __init__ 상단에서 이미 완료 (시나리오 로드 전에 창이 먼저 뜸)
        if self.headless:
            print("Headless 모드: GUI 없이 실행합니다.")
        elif not GUI_AVAILABLE:
            print("PyQt5/PyQtGraph 없음 — GUI 비활성화 (pip install pyqtgraph PyQt5)")
        # DWTAMainWindow는 이미 _load_scenario() 전에 생성됨; 여기서 map 갱신
        if not self.headless and self.control_panel and hasattr(self.control_panel, 'tactical_map'):
            self.control_panel.tactical_map._draw_range_rings()
            self.control_panel.tactical_map._update_assets()
            self.control_panel.tactical_map._update_batteries()   # 시뮬 시작 전에도 포대 표시
            if hasattr(self, '_qt_app'):
                self._qt_app.processEvents()

    # 🆕 Phase 1.2-1.3: Performance Cache Helper Methods
    def _invalidate_active_cache(self):
        """Invalidate active threats count cache"""
        if hasattr(self, '_active_cache_valid'):
            self._active_cache_valid = False

    def _invalidate_battery_cache(self):
        """Invalidate operational battery and ammo cache"""
        if hasattr(self, '_battery_cache_valid'):
            self._battery_cache_valid = False

    def _get_operational_batteries(self):
        """Get operational batteries with caching (O(1) after first call)"""
        if not self._battery_cache_valid:
            self._cached_operational_batteries = [
                b for b in self.batteries
                if b.get('status') == 'OPERATIONAL' and b.get('available_missiles', 0) > 0
            ]
            self._cached_total_ammo = sum(b.get('available_missiles', 0) for b in self.batteries)
            self._battery_cache_valid = True
        return self._cached_operational_batteries, self._cached_total_ammo

    def _rebuild_battery_lookup(self):
        """Rebuild persistent battery lookup cache"""
        if hasattr(self, 'batteries') and self.batteries:
            self._battery_lookup = {b['id']: b for b in self.batteries}
            print(f"[OK] Battery lookup cache built: {len(self._battery_lookup)} batteries")

    def _load_scenario(self):
        """Load realistic scenario with comprehensive threat configuration."""
        try:
            # Pass scenario_type explicitly to ensure it uses the current value
            self.scenario_data = self.config.create_realistic_scenario(self.config.scenario_type)
            self.assets = self.scenario_data['assets']
            self.batteries = self.scenario_data['batteries']
            self.initial_threats_config = self.scenario_data['threats']
            self.engagement_matrix = self.scenario_data['engagement_matrix']
            
            # 🆕 Enhanced Engagement Matrix 생성 (시나리오 로드 직후)
            print("\n" + "=" * 80)
            print("최적화 사전 계산 시작...")
            print("=" * 80)
            
            self.enhanced_engagement_matrix = EnhancedEngagementMatrix()
            
            # DEBUG: NODONG phase_events 확인 (제거됨 - I/O 최적화)
            # for t in self.initial_threats_config[:3]:
            #     print(f"[DEBUG] Threat {t['id']}: phase_events={t.get('phase_events', 'MISSING')}")
            
            self.enhanced_engagement_matrix.precompute_all(
                self.batteries,
                self.initial_threats_config,  # List[Dict] 형태
                self.assets
            )
            
            # K-factor 캐시 생성 (모든 알고리즘이 공유)
            self.k_factor_cache = KFactorCache(k_min=0.6, k_max=1.0)
            print("K-factor 캐시 생성 완료")
            
            print("[OK] 사전 계산 완료")
            print("=" * 80 + "\n")
            
            # Initialize dynamic battery status
            for battery in self.batteries:
                try:
                    if 'specs' not in battery or 'battery_config' not in battery['specs']:
                        battery['available_missiles'] = 10
                    else:
                        battery['available_missiles'] = battery['specs']['battery_config']['total_missiles']
                    
                    battery['status'] = 'OPERATIONAL'
                    
                    if 'position' not in battery or len(battery['position']) != 2:
                        battery['position'] = (0.0, 0.0)
                        
                except (KeyError, TypeError) as be:
                    battery['available_missiles'] = 10
                    battery['status'] = 'OPERATIONAL'
                    battery['position'] = (0.0, 0.0)
            
            # Initialize assets
            for asset in self.assets:
                if 'position' not in asset or len(asset['position']) != 2:
                    asset['position'] = (0.0, 0.0)
                if 'value' not in asset:
                    asset['value'] = 100
                if 'priority' not in asset:
                    asset['priority'] = 1
            
            # Initialize threats
            for i, threat in enumerate(self.initial_threats_config):
                if 'launch_position' not in threat:
                    threat['launch_position'] = (0.0, 0.0)
                if 'target_asset_id' not in threat:
                    continue
                
                if 'launch_time' not in threat or threat['launch_time'] == 0:
                    if i == 0:
                        threat['launch_time'] = 5
                    else:
                        threat['launch_time'] = 5 + min(i * 8, 110) + (i % 3) * 2
                    
                if 'flight_time' not in threat:
                    threat['flight_time'] = 300
            
            print(f"Scenario Loaded: {self.scenario_data.get('name', 'Unknown')}. Objective: {OBJECTIVES[self.objective]}")

            # 🆕 Phase 1.4: Build persistent battery lookup cache after scenario load
            self._rebuild_battery_lookup()
            print("[OK] Battery lookup cache initialized")

        except Exception as e:
            print(f"Failed to load realistic scenario: {e}")
            raise e  # 시나리오 로딩 실패시 프로그램 종료


    # 나머지 메서드들은 원본 코드와 동일하게 유지
    def _calculate_trajectory(self, start_pos, target_pos, steps=100):
        """Simple linear trajectory for visualization."""
        # Handle both 2D and 3D positions (only use x, y)
        x1, y1 = start_pos[:2] if len(start_pos) > 2 else start_pos
        x2, y2 = target_pos[:2] if len(target_pos) > 2 else target_pos
        return [(x1 + t/steps * (x2 - x1), y1 + t/steps * (y2 - y1)) for t in range(steps + 1)]

    def reset_for_next_iteration(self):
        """다음 iteration을 위한 시뮬레이션 상태 리셋 (Compare 모드 전용)"""
        # 시뮬레이션 상태 초기화
        self.current_time_step = 0
        self.missiles = {}
        self.primary_assignments.clear()
        self.last_optimization_step = -99
        
        # 통계 초기화
        self.stats = {'intercepted': 0, 'missed': 0, 'active': 0, 'total': 0, 'retargeted': 0, 'tracked_misses': []}
        self.kill_results = {}
        self.engagement_attempts = {}
        self.optimization_history = []
        self.optimization_count = 0
        
        # 배터리 탄약 리셋 (초기값으로)
        for battery in self.batteries:
            battery_id = battery['id']
            if battery_id.startswith('LSAM'):
                battery['available_missiles'] = 24
            elif battery_id.startswith('MSAM'):
                battery['available_missiles'] = 48
        
        # 실시간 추적 변수 초기화
        self.last_objective_value = None
        self.last_solve_time = None
        
        # Compare 모드에서는 optimizer 인스턴스 초기화 (각 iteration 독립 실행)
        if self.comparison_mode:
            if hasattr(self, 'mip_optimizer_instance'):
                delattr(self, 'mip_optimizer_instance')
            if hasattr(self, 'ga_optimizer_instance'):
                delattr(self, 'ga_optimizer_instance')
            if hasattr(self, 'greedy_optimizer_instance'):
                delattr(self, 'greedy_optimizer_instance')
            
            # GUI 플래그 명시적 재설정 (타임아웃 방지)
            if self.headless:
                self.fig = None
                self.control_panel = None
                self.text_mode = True
        
        # 시나리오 설정은 유지 (assets, batteries, initial_threats_config)
    
    def start_scenario(self):
        """Initialize the fixed scenario threats."""
        print("\nStarting scenario simulation...")
        self.current_time_step = 0
        
        for threat in self.initial_threats_config:
            target_asset = next((a for a in self.assets if a['id'] == threat['target_asset_id']), None)
            if target_asset:
                self.missiles[threat['id']] = {
                    'id': threat['id'],
                    'position': threat['launch_position'],
                    'launch_position': threat['launch_position'],
                    'target_asset': threat['target_asset_id'],
                    'target_position': target_asset['position'],
                    'launch_time': threat.get('launch_time', 0),
                    'flight_time': threat.get('flight_time', 300),
                    'active': False,
                    'flight_progress': 0.0,
                    'trajectory': self._calculate_trajectory(threat['launch_position'], target_asset['position']),
                    'target_changed': 0,
                    'can_retarget': True,
                    'retarget_probability': 0.002,
                    'phase_events': threat.get('phase_events', {}),  # 교전 매트릭스용
                    'specs': threat.get('specs', {}),  # 교전 매트릭스용
                    'target_asset_id': threat['target_asset_id']  # 교전 매트릭스용
                }
        self.stats['total'] = len(self.missiles)

    def update_simulation(self):
        """Advance simulation by one time step."""
        self.current_time_step += 2
        
        self._simulate_dynamic_events()
        
        # ⚡ 성능 최적화: control_panel 존재 여부를 루프 밖에서 체크
        has_control_panel = self.control_panel is not None
        
        active_count = 0
        for missile_id, missile in self.missiles.items():
            
            # ⚡ 성능 최적화: 여러 조건을 한 번에 체크
            is_inactive = not missile['active']
            past_launch_time = self.current_time_step >= missile['launch_time']
            not_killed = missile_id not in self.kill_results
            
            if is_inactive and past_launch_time and not_killed:
                missile['active'] = True
                self._invalidate_active_cache()  # 🆕 Cache invalidation
                if has_control_panel:  # ⚡ 캐시된 값 사용
                    self.control_panel.log_message(f"[INFO] LAUNCH: {missile_id} → {missile['target_asset']}", "LAUNCH")

            if missile['active']:
                active_count += 1
                
                time_in_flight = self.current_time_step - missile['launch_time']
                flight_time = missile['flight_time']  # ⚡ 한 번만 조회
                if flight_time > 0:
                    missile['flight_progress'] = min(time_in_flight / flight_time, 1.0)
                else:
                    missile['flight_progress'] = 1.0
                
                progress_idx = int(missile['flight_progress'] * (len(missile['trajectory']) - 1))
                missile['position'] = missile['trajectory'][progress_idx]
                
                # Process engagement at 60-80% flight progress (20-30km from target)
                if missile['flight_progress'] >= 0.60:
                    self._process_impact(missile_id, missile)
        
        self.stats['active'] = active_count
        
        # GUI 상태 업데이트는 DWTAMainWindow QTimer (_on_display_tick) 에서 처리

    def _simulate_dynamic_events(self):
        """Handles dynamic scenario changes including controlled retargeting events."""
        
        # ⚡ 성능 최적화: control_panel과 current_time_step 캐싱
        has_control_panel = self.control_panel is not None
        current_time = self.current_time_step
        
        # Probabilistic trajectory deviation events (missile veers off target)
        for missile_id, missile in self.missiles.items():
            # ⚡ 성능 최적화: 조건 체크 순서 최적화 (빠른 실패)
            if not missile['active']:
                continue
            if not missile.get('can_retarget', True):
                continue
            
            flight_progress = missile['flight_progress']
            # Check if missile is in critical flight phase (30-60% of flight)
            if not (0.3 <= flight_progress <= 0.6):
                continue
            
            # Low probability of trajectory deviation (missile veers off course)
            # step=1초 기준으로 확률 정규화 (원래 step=5 기준 0.002 → 초당 0.0004)
            if random.random() < missile.get('retarget_probability', 0.002) * 0.2:
                # Missile deviates from intended target (goes to empty area)
                old_target = missile['target_asset']
                
                # ⚡ 성능 최적화: 한 번만 조회
                target_pos = missile['target_position']
                
                # Generate random deviation coordinates (empty area)
                deviation_x = target_pos[0] + random.uniform(-20, 20)
                deviation_y = target_pos[1] + random.uniform(-20, 20)
                
                # Update missile to target empty area
                missile['target_asset'] = 'EMPTY_AREA'
                missile['target_position'] = (deviation_x, deviation_y)
                missile['target_changed'] += 1
                
                # Recalculate trajectory to empty area
                current_pos = missile['position']  # ⚡ 한 번만 조회
                missile['trajectory'] = self._calculate_trajectory(
                    current_pos, (deviation_x, deviation_y)
                )
                
                # Clear existing assignments (battery abandons this threat)
                assigned_batteries = self.primary_assignments.get_batteries_for_threat(missile_id)
                for battery_id in assigned_batteries:
                    abandon_msg = f"[T={current_time}] ABANDON: Battery {battery_id} abandons {missile_id} (trajectory deviation)"
                    if has_control_panel:  # ⚡ 캐시된 값 사용
                        self.control_panel.log_message(f"[WARN] {abandon_msg}", "WARNING")
                    else:
                        print(abandon_msg)
                    self.primary_assignments.unassign(missile_id, battery_id)
                
                # Mark as no longer needing assignment (going to empty area)
                missile['needs_reassignment'] = False
                missile['active'] = False  # Deactivate missile going to empty area
                self._invalidate_active_cache()  # 🆕 Cache invalidation
                self.stats['retargeted'] += 1
                
                # 🔧 FIX: 궤적 이탈 시 요격 성공 카운트에서 제거
                # 이미 요격 성공으로 카운트된 미사일이 궤적 이탈하면 intercepted 감소
                if missile_id in self.kill_results and self.kill_results[missile_id][0] == 'INTERCEPTED':
                    self.stats['intercepted'] -= 1
                    del self.kill_results[missile_id]
                
                # Track as separate category (not intercepted, not missed)
                # 🔧 FIX: 중복 카운트 방지 - 이미 deviated로 표시된 미사일은 다시 카운트하지 않음
                if 'deviated' not in self.stats:
                    self.stats['deviated'] = 0
                
                if not missile.get('counted_as_deviated', False):
                    self.stats['deviated'] += 1
                    missile['counted_as_deviated'] = True  # 이탈 카운트 완료 플래그
                
                deviation_msg = f"[T={current_time}] TRAJECTORY DEVIATION: {missile_id} veered off from {old_target} to empty area"
                if has_control_panel:  # ⚡ 캐시된 값 사용
                    self.control_panel.log_message(f"[INFO] {deviation_msg}", "INFO")
                else:
                    print(deviation_msg)

    def _process_impact(self, missile_id, missile):
        """Process missile impact with comprehensive shoot-look-shoot logic."""
        # Track engagement attempts
        if missile_id not in self.engagement_attempts:
            self.engagement_attempts[missile_id] = 1
        else:
            self.engagement_attempts[missile_id] += 1
            
        current_attempt = self.engagement_attempts[missile_id]
        launch_failures = 0
            
        # Find assigned batteries
        assigned_batteries = self.primary_assignments.get_batteries_for_threat(missile_id)

        # Handle unassigned missiles
        if not assigned_batteries:
            if missile['flight_progress'] < 0.85:  # Not at engagement range yet (extended for realtime DWTA)
                missile['needs_reassignment'] = True
                if self.shoot_look_shoot_enabled and current_attempt < self.max_engagement_attempts:
                    # Keep missile active for re-engagement (진행도는 계속 진행)
                    return  # Exit function, handle in next optimization step

        # 🆕 Phase 1.4: Use persistent battery lookup cache (no recreation)
        # Defensive: Rebuild if not available
        if not hasattr(self, '_battery_lookup') or not self._battery_lookup:
            self._rebuild_battery_lookup()
        battery_lookup = self._battery_lookup
        
        # 🆕 다층 방어: 상층/하층 배터리 분리
        upper_batteries = []
        lower_batteries = []
        for bid in assigned_batteries:
            battery = battery_lookup.get(bid)
            if battery:
                battery_type = battery.get('system_type')
                if battery_type == 'LSAM':
                    upper_batteries.append(bid)
                elif battery_type == 'MSAM':
                    lower_batteries.append(bid)
        
        P_survival = 1.0
        missiles_fired = 0
        operational_batteries = 0
        upper_success = False
        
        # 🆕 1단계: 상층(LSAM) 교전
        for battery_id in upper_batteries:
            battery = battery_lookup.get(battery_id)  # ⚡ 캐시된 조회
            
            if battery:
                debug_status = battery.get('status', 'UNKNOWN')
                debug_ammo = battery.get('available_missiles', 'UNKNOWN')
            else:
                continue
                
            if battery and battery.get('status') == 'OPERATIONAL' and battery.get('available_missiles', 0) > 0:
                operational_batteries += 1
                missiles_to_fire = min(2, battery.get('available_missiles', 0))
                battery['available_missiles'] -= missiles_to_fire
                self._invalidate_battery_cache()  # 🆕 Cache invalidation
                missiles_fired += missiles_to_fire

                # ① 배터리 스펙에서 단발 Pₖ 취득 (없으면 LSAM 기본값)
                try:
                    Pk_base   = battery['specs']['ballistic_missile_specs']['intercept_probability']
                    max_range = battery['specs']['ballistic_missile_specs']['engagement_range_km']['max']
                except (KeyError, TypeError):
                    Pk_base, max_range = 0.85, 300

                # ② per-shot Beta 샘플링 → 이 배터리의 salvo 생존확률
                salvo_results = []
                P_surv_this = 1.0
                for shot_num in range(missiles_to_fire):
                    Pk_shot = self.uncertainty_model.sample_intercept_probability(Pk_base)
                    salvo_results.append((shot_num + 1, Pk_shot))
                    P_surv_this *= (1 - Pk_shot)

                # ③ K-factor: k_factor_cache 우선 (거리+시간), 없으면 거리 선형 폴백
                bx, by = battery['position']
                mx, my = missile['position'][0], missile['position'][1]
                dist = ((bx - mx) ** 2 + (by - my) ** 2) ** 0.5
                k_cache = getattr(self, 'k_factor_cache', None)
                if k_cache is not None and hasattr(k_cache, 'get_k_time_dependent'):
                    elapsed = missile.get('flight_progress', 0.0) * missile.get('flight_time', 300.0)
                    total   = missile.get('flight_time', 300.0)
                    try:
                        k = k_cache.get_k_time_dependent(dist, max_range, elapsed, total)
                    except Exception:
                        k = 0.6 + 0.4 * max(0.0, 1.0 - dist / max_range) if max_range > 0 else 0.8
                elif k_cache is not None and hasattr(k_cache, 'get_k_from_distance'):
                    try:
                        k = k_cache.get_k_from_distance(dist, max_range)
                    except Exception:
                        k = 0.6 + 0.4 * max(0.0, 1.0 - dist / max_range) if max_range > 0 else 0.8
                else:
                    k = 0.6 + 0.4 * max(0.0, 1.0 - dist / max_range) if max_range > 0 else 0.8
                p_eff = min(k * (1.0 - P_surv_this), 0.9999)   # k × Pⱼ

                # ④ 전체 생존확률 누적
                P_survival *= (1.0 - p_eff)
                
                if self.control_panel:
                    salvo_detail = ", ".join([f"{shot}발:Pk={pk:.4f}" for shot, pk in salvo_results])
                    self.control_panel.log_message(
                        f"[DEBUG] FIRE (UPPER): {battery_id} → {missile_id} (SALVO {missiles_to_fire}발 [{salvo_detail}], Ammo: {battery['available_missiles']+missiles_to_fire}→{battery['available_missiles']})",
                        "DEBUG"
                    )
        
        # 상층 교전 결과 판정
        P_kill_upper = 1.0 - P_survival
        if P_kill_upper >= 0.5 and missiles_fired > 0:
            upper_success = True
            if self.control_panel:
                self.control_panel.log_message(
                    f"[INFO] UPPER LAYER SUCCESS: {missile_id} (Pk={P_kill_upper:.4f})",
                    "SUCCESS"
                )
        
        # 🆕 2단계: 상층 실패 시에만 하층(MSAM) 교전
        if not upper_success and lower_batteries:
            if self.control_panel:
                self.control_panel.log_message(
                    f"[INFO] UPPER LAYER MISS: {missile_id} (Pk={P_kill_upper:.4f}) → Engaging LOWER LAYER",
                    "WARNING"
                )
            
            for battery_id in lower_batteries:
                battery = battery_lookup.get(battery_id)  # ⚡ 캐시된 조회
                
                if battery:
                    debug_status = battery.get('status', 'UNKNOWN')
                    debug_ammo = battery.get('available_missiles', 'UNKNOWN')
                else:
                    continue
                    
                if battery and battery.get('status') == 'OPERATIONAL' and battery.get('available_missiles', 0) > 0:
                    operational_batteries += 1
                    missiles_to_fire = min(2, battery.get('available_missiles', 0))
                    battery['available_missiles'] -= missiles_to_fire
                    self._invalidate_battery_cache()  # 🆕 Cache invalidation
                    missiles_fired += missiles_to_fire
                    
                    # ① 배터리 스펙에서 단발 Pₖ 취득 (없으면 MSAM 기본값)
                    try:
                        Pk_base   = battery['specs']['ballistic_missile_specs']['intercept_probability']
                        max_range = battery['specs']['ballistic_missile_specs']['engagement_range_km']['max']
                    except (KeyError, TypeError):
                        Pk_base, max_range = 0.78, 50

                    # ② per-shot Beta 샘플링 → 이 배터리의 salvo 생존확률
                    salvo_results = []
                    P_surv_this = 1.0
                    for shot_num in range(missiles_to_fire):
                        Pk_shot = self.uncertainty_model.sample_intercept_probability(Pk_base)
                        salvo_results.append((shot_num + 1, Pk_shot))
                        P_surv_this *= (1 - Pk_shot)

                    # ③ K-factor: 현재 거리 기반, salvo 결과 전체에 적용 (pⱼₜ = kⱼₜ × Pⱼ)
                    bx, by = battery['position']
                    mx, my = missile['position'][0], missile['position'][1]
                    dist = ((bx - mx) ** 2 + (by - my) ** 2) ** 0.5
                    k = 0.6 + 0.4 * max(0.0, 1.0 - dist / max_range) if max_range > 0 else 0.8
                    p_eff = min(k * (1.0 - P_surv_this), 0.9999)   # k × Pⱼ

                    # ④ 전체 생존확률 누적
                    P_survival *= (1.0 - p_eff)
                    
                    if self.control_panel:
                        salvo_detail = ", ".join([f"{shot}발:Pk={pk:.4f}" for shot, pk in salvo_results])
                        self.control_panel.log_message(
                            f"[DEBUG] FIRE (LOWER): {battery_id} → {missile_id} (SALVO {missiles_to_fire}발 [{salvo_detail}], Ammo: {battery['available_missiles']+missiles_to_fire}→{battery['available_missiles']})",
                            "DEBUG"
                        )

        # Update launch failure statistics
        if 'launch_failures' not in self.stats:
            self.stats['launch_failures'] = launch_failures
        else:
            self.stats['launch_failures'] += launch_failures

        # Set reassignment flag if no operational batteries and not at impact
        if assigned_batteries and operational_batteries == 0 and missile['flight_progress'] < 0.85:
            missile['needs_reassignment'] = True

        P_kill = 1.0 - P_survival
        P_kill = min(P_kill, 0.999)  # Cap probability

        # 기댓값 기반 판정: 불확실성은 Stage 1(Beta 분포)에서만 적용
        # Stage 2는 결정론적 임계값 — 최적화-실행 편차 최소화
        if P_kill >= 0.5 and missiles_fired > 0:
            result = 'INTERCEPTED'
            # 🔧 FIX: 각 위협은 최초 요격 성공 시에만 카운트 (재교전 중복 방지)
            if missile_id not in self.kill_results:
                self.stats['intercepted'] += 1
            missile['active'] = False  # Successfully intercepted - deactivate
            self._invalidate_active_cache()  # 🆕 Cache invalidation
            if self.control_panel:
                # 담당 배터리 찾기 및 상층/하층 정보 추가
                battery_list = self.primary_assignments.get_batteries_for_threat(missile_id)
                battery_info = f" by {','.join(battery_list)}" if battery_list else ""
                battery_count = len(battery_list)
                
                # 상층/하층 요격 정보 생성
                layer_info = ""
                if upper_success:
                    layer_info = " [상층(LSAM) 요격 성공]"
                elif upper_batteries and lower_batteries:
                    layer_info = " [상층 실패 → 하층(MSAM) 요격 성공]"
                elif lower_batteries:
                    layer_info = " [하층(MSAM) 요격 성공]"
                elif upper_batteries:
                    layer_info = " [상층(LSAM) 요격 성공]"
                
                self.control_panel.log_message(
                    f"[CRIT] INTERCEPT SUCCESS: {missile_id}{battery_info}{layer_info} (Pk={P_kill:.4f}, Batteries={battery_count}, Missiles={missiles_fired})",
                    "INTERCEPT"
                )
                # 요격 성공 시 primary_assignments 제거
                released_batteries = 0
                assigned_batteries = self.primary_assignments.get_batteries_for_threat(missile_id)
                for battery_id in assigned_batteries:
                    self.primary_assignments.unassign(missile_id, battery_id)
                    released_batteries += 1
                
                # 🆕 용량 확보 로그 및 즉시 최적화 트리거
                if released_batteries > 0:
                    total_capacity = sum(b['specs']['battery_config']['simultaneous_engagements'] 
                                        for b in self.batteries if b.get('status') == 'OPERATIONAL')
                    current_assignments = self.primary_assignments.get_total_assignments()
                    self.control_panel.log_message(
                        f"[INFO] [T={self.current_time_step}] 용량 확보: {released_batteries}개 배터리 해제 (현재 {current_assignments}/{total_capacity}개 할당)",
                        "INFO"
                    )
                    # 🆕 즉시 최적화 트리거: 용량 확보 시 대기 중인 위협 재할당
                    self.capacity_freed = True
                    
                    # 🔥 핵심 수정: 용량 확보 시 미할당 위협에 대해 즉시 needs_reassignment 플래그 설정
                    assigned_threat_ids = self.primary_assignments.get_all_assigned_threats()
                    unassigned_count = 0
                    for mid, m in self.missiles.items():
                        if m['active'] and mid not in assigned_threat_ids and m['flight_progress'] < 0.85:
                            m['needs_reassignment'] = True
                            unassigned_count += 1
                    
                    if unassigned_count > 0:
                        self.control_panel.log_message(
                            f"[INFO] [T={self.current_time_step}] 미할당 위협 {unassigned_count}개에 대해 재할당 플래그 설정",
                            "INFO"
                        )
            else:
                print(f"[T={self.current_time_step}] IMPACT: {missile_id} INTERCEPTED (Pk={P_kill:.4f}, Fired={missiles_fired}, Attempt={current_attempt})")
            # 요격 성공 시 배터리 ID 저장 (Stress metrics용)
            self.kill_results[missile_id] = (result, self.current_time_step, battery_id)
        else:
            result = 'MISSED'
            # 🔧 FIX: 최종 실패 시에만 missed 카운트 (재교전 중 실패는 제외)
            if missiles_fired > 0 and not (self.shoot_look_shoot_enabled and current_attempt < self.max_engagement_attempts):
                self.stats['missed'] += 1
            
            if self.shoot_look_shoot_enabled and current_attempt < self.max_engagement_attempts and missiles_fired > 0:
                # Keep missile active for re-engagement (shoot-look-shoot)
                # 진행도는 계속 진행 (현실적), 재교전 시간 여유 확인
                missile['last_engagement_time'] = self.current_time_step
                missile['needs_reassignment'] = True  # 즉시 재할당 요청
                if self.control_panel:
                    battery_list = self.primary_assignments.get_batteries_for_threat(missile_id)
                    battery_info = f" by {','.join(battery_list)}" if battery_list else ""
                    battery_count = len(battery_list)
                    
                    # 상층/하층 요격 정보 생성
                    layer_info = ""
                    if upper_batteries and lower_batteries:
                        layer_info = " [상층+하층 모두 실패]"
                    elif lower_batteries:
                        layer_info = " [하층(MSAM) 실패]"
                    elif upper_batteries:
                        layer_info = " [상층(LSAM) 실패]"
                    
                    self.control_panel.log_message(
                        f"[WARN] INTERCEPT MISS: {missile_id}{battery_info}{layer_info} (Pk={P_kill:.4f}, Batteries={battery_count}, Missiles={missiles_fired}) - Retry {current_attempt}/{self.max_engagement_attempts}",
                        "WARNING"
                    )
                else:
                    print(f"[T={self.current_time_step}] IMPACT: {missile_id} MISSED (Pk={P_kill:.2f}, Fired={missiles_fired}) -> Re-engaging in Shoot-Look-Shoot mode")
            elif missiles_fired == 0 and missile['flight_progress'] < 0.80:  # No missiles fired and not at engagement range (extended for realtime DWTA)
                # Set reassignment flag
                missile['needs_reassignment'] = True
            else:
                # Final miss - deactivate
                missile['active'] = False
                self._invalidate_active_cache()  # 🆕 Cache invalidation

                # 궤적 이탈 미사일(EMPTY_AREA 타격)은 MISSED에 카운트하지 않음
                if missile['target_asset'] == 'EMPTY_AREA':
                    # 의도적 미요격 - deviated에만 카운트됨
                    if self.control_panel:
                        self.control_panel.log_message(f"[INFO] TRAJECTORY DEVIATION: {missile_id} → EMPTY_AREA (intentional)", "INFO")
                    else:
                        print(f"[T={self.current_time_step}] IMPACT: {missile_id} MISSED (Pk={P_kill:.2f}, Fired={missiles_fired}, Attempt={current_attempt}) -> Hit EMPTY_AREA")
                    self.kill_results[missile_id] = ('DEVIATED', self.current_time_step, None)
                else:
                    # 실제 요격 실패 - 자산 타격
                    battery_list = self.primary_assignments.get_batteries_for_threat(missile_id)
                    if missiles_fired == 0:
                        reason = "No assignment"
                    elif P_kill < 0.5:
                        battery_info = f" by {','.join(battery_list)}" if battery_list else ""
                        reason = f"Low Pk{battery_info} (Pk={P_kill:.4f}, Fired={missiles_fired})"
                    else:
                        reason = "Unknown"
                    
                    if self.control_panel:
                        self.control_panel.log_message(
                            f"[CRIT] INTERCEPT FAILED: {missile_id} → {missile['target_asset']} - {reason}",
                            "ERROR"
                        )
                    else:
                        print(f"[T={self.current_time_step}] IMPACT: {missile_id} MISSED (Pk={P_kill:.2f}, Fired={missiles_fired}, Attempt={current_attempt}) -> Hit {missile['target_asset']}")
                    self.kill_results[missile_id] = (result, self.current_time_step, None)
                    
                    # Make sure we don't double-count this miss
                    if missile_id not in self.stats['tracked_misses']:
                        self.stats['missed'] += 1
                        self.stats['tracked_misses'].append(missile_id)

    def run_realtime_dwta(self):
        """Perform real-time optimization (DWTA) with comprehensive logic.

        이벤트 기반 트리거:
        1. 정기 최적화: optimization_interval 이상 경과 시 실행
        2. 용량 확보 트리거: 요격 성공으로 배터리 용량 확보 시 즉시 실행
        3. 재할당 트리거: 미할당 위협 발견 시 즉시 실행
        """

        # 🆕 OPTIMIZED: Use cached active threat count (10x speedup)
        # Defensive: Ensure cache variables exist
        if not hasattr(self, '_active_cache_valid'):
            self._active_cache_valid = False
            self._cached_active_threats_count = 0

        if not self._active_cache_valid:
            self._cached_active_threats_count = sum(1 for m in self.missiles.values() if m['active'])
            self._active_cache_valid = True
        active_threats_count = self._cached_active_threats_count

        if not self.use_mip or active_threats_count == 0:
            return

        # Deadlock prevention: limit optimizations per timestep
        if self.current_time_step == self.last_optimization_step:
            if self.optimization_count >= self.max_optimizations_per_timestep:
                return
        else:
            # Reset optimization counter for new timestep
            self.optimization_count = 0

        # 이벤트 기반 트리거 체크 (정기 최적화 간격 이전이라도 즉시 실행)
        time_since_last = self.current_time_step - self.last_optimization_step
        event_triggered = False

        # 트리거 1: 용량 확보 시 즉시 최적화
        if getattr(self, 'capacity_freed', False):
            self.capacity_freed = False
            event_triggered = True
            if self.control_panel:
                self.control_panel.log_message(
                    f"[INFO] [T={self.current_time_step}] 용량 확보 감지 - 즉시 최적화 실행", "INFO")

        # 트리거 2: 미할당 위협 재할당 필요 시
        if not event_triggered:
            for missile_id, missile in self.missiles.items():
                if missile['active'] and missile.get('needs_reassignment', False):
                    event_triggered = True
                    if self.control_panel:
                        self.control_panel.log_message(
                            f"[INFO] [T={self.current_time_step}] 재할당 필요 감지 - 즉시 최적화 실행", "INFO")
                    break

        # 정기 최적화 간격 체크 (이벤트 트리거가 없는 경우에만 적용)
        if not event_triggered and time_since_last < self.optimization_interval:
            return

        start_time = time.time()

        # Increment optimization counter (deadlock prevention)
        self.optimization_count += 1

        try:
            # Deadlock prevention with additional safety
            max_solve_time = 5  # Maximum 5 second limit for GUI responsiveness
            
            # Prepare inputs from current state
            assets_opt, systems_opt, threats_opt = self._prepare_optimizer_inputs()
            
            if not systems_opt or not threats_opt:
                if self.control_panel:
                    if not systems_opt:
                        total_ammo = sum(b.get('available_missiles', 0) for b in self.batteries)
                        self.control_panel.log_message(
                            f"[WARN] [T={self.current_time_step}] No operational systems (Total ammo: {total_ammo})",
                            "WARNING"
                        )
                    if not threats_opt:
                        self.control_panel.log_message(
                            f"[INFO] [T={self.current_time_step}] No active threats",
                            "INFO"
                        )
                return
            
            # 옵티마이저는 배터리 스펙 Pₖ를 결정론적으로 사용 (pⱼₜ = kⱼₜ × Pⱼ 상수 사전계산)
            # 불확실성(Beta 샘플링)은 시뮬레이션 판정(_process_impact)에서만 적용

            # 🆕 알고리즘 선택 (MIP, Greedy, GA)
            # 모든 알고리즘이 독립 모듈을 사용하여 동일한 프로세스를 거침
            if self.current_algorithm == 'Greedy':
                # Greedy Optimizer 모듈 사용
                optimizer = GreedyOptimizer(self.config)
                optimizer.create_model(
                    assets=assets_opt,
                    interceptor_systems=systems_opt,
                    threats=threats_opt,
                    batteries=self.batteries,
                    engagement_matrix=self.enhanced_engagement_matrix
                )
                result = optimizer.solve()
                solve_time = time.time() - start_time
            
            elif self.current_algorithm == 'GA':
                # Genetic Algorithm Optimizer 모듈 사용
                optimizer = GeneticAlgorithmOptimizer(self.config)
                optimizer.create_model(
                    assets=assets_opt,
                    interceptor_systems=systems_opt,
                    threats=threats_opt,
                    batteries=self.batteries,
                    engagement_matrix=self.enhanced_engagement_matrix
                )
                result = optimizer.solve()
                solve_time = time.time() - start_time
            
            else:  # 'MIP' (기본) → Clean Slate Optimizer
                # Clean Slate: Log-Linear formulation + HiGHS 직접 API
                # 인스턴스 재사용 (HiGHS C++ GC 해제 segfault 방지)
                # create_model() 내부에서 이전 모델 안전 해제 + warm-start 자동 적용

                if not hasattr(self, 'mip_optimizer_instance') or self.mip_optimizer_instance is None:
                    self.mip_optimizer_instance = CleanSlateOptimizer(self.config)
                    if hasattr(self, 'k_factor_cache') and self.k_factor_cache:
                        self.mip_optimizer_instance.set_k_factor_cache(self.k_factor_cache)

                optimizer = self.mip_optimizer_instance

                if self.control_panel:
                    optimizer.log_callback = self.control_panel.log_message

                optimizer.create_model(
                    assets=assets_opt,
                    interceptor_systems=systems_opt,
                    threats=threats_opt,
                    batteries=self.batteries,
                    engagement_matrix=self.enhanced_engagement_matrix
                )
                result = optimizer.solve()
                solve_time = time.time() - start_time
            
            # Warn if solver takes too long
            if solve_time > max_solve_time:
                warning_msg = f"[T={self.current_time_step}] WARNING: Solver timeout ({solve_time:.2f}s > {max_solve_time}s)"
                if self.control_panel:
                    self.control_panel.log_message(warning_msg, "WARNING")
                pass

            # Track objective value and solve time for visualization
            if result and result.get('feasible', False):
                obj_val = result.get('objective_value', 0.0)
                if obj_val != float('inf') and obj_val is not None:
                    self.last_objective_value = obj_val
                # inf인 경우 이전 값 유지
            else:
                # Infeasible 상황에서는 이전 값 유지
                # 이전 값이 없거나 inf인 경우에만 기본값 설정
                if self.last_objective_value is None or self.last_objective_value == float('inf'):
                    # 최적화 히스토리에서 마지막 유효한 값 찾기
                    valid_objective = None
                    for time_step, obj_val, solve_time_hist in reversed(self.optimization_history):
                        if obj_val != float('inf') and obj_val is not None:
                            valid_objective = obj_val
                            break
                    
                    if valid_objective is not None:
                        self.last_objective_value = valid_objective
                    else:
                        self.last_objective_value = 0.0  # 유효한 값 없음 = 피해 없음
            self.last_solve_time = solve_time
            
            # 모든 알고리즘에 대해 optimization_history에 추가
            objective_value = result.get('objective_value', 0.0) if result else 0.0
            self.optimization_history.append((self.current_time_step, objective_value, solve_time))
            
            # Process Results
            if result and result.get('feasible', False):
                self._process_optimization_results(result, solve_time)
                # Clear reassignment flags after successful optimization
                for missile_id in self.missiles:
                    if self.missiles[missile_id].get('needs_reassignment', False):
                        self.missiles[missile_id]['needs_reassignment'] = False
                        if self.control_panel:
                            self.control_panel.log_message(f"INFO: {missile_id} reassignment completed - flag cleared")
            else:
                # Optimization failed - keep reassignment flags for next attempt
                if self.control_panel:
                    # 진단 정보 기반 원인 분석
                    if result.get('diagnosis'):
                        diag = result['diagnosis']
                        
                        # 포대별 할당 현황 분석
                        battery_assignments = {}
                        for battery in self.batteries:
                            battery_id = battery['id']
                            assigned_threats = self.primary_assignments.get_threats_for_battery(battery_id)
                            battery_assignments[battery_id] = {
                                'assigned': len(assigned_threats),
                                'available_missiles': battery.get('available_missiles', 0),
                                'max_simultaneous': battery['specs']['battery_config'].get('simultaneous_engagements', 3)
                            }
                        
                        # 원인 분석
                        if diag.get('time_limit_reached', False):
                            reason = "시간 초과 (복잡도)"
                            detail = f"변수 {diag['num_variables']}개, 제약 {diag['num_constraints']}개"
                        elif diag.get('solver_status', '') == 'Infeasible':
                            # 자원 부족 vs 제약 충돌 구분
                            avg_missiles_per_threat = diag['total_missiles'] / max(diag['num_threats'], 1)
                            
                            # 포대별 용량 포화 확인 (primary_assignments 기반)
                            saturated_batteries = [bid for bid, info in battery_assignments.items() 
                                                  if info['assigned'] >= info['max_simultaneous']]
                            
                            # 🆕 Cross-check: 실제 할당 수 vs Matrix feasibility
                            total_assigned = sum(info['assigned'] for info in battery_assignments.values())
                            max_capacity = sum(info['max_simultaneous'] for info in battery_assignments.values())
                            
                            if avg_missiles_per_threat < 2:
                                reason = "자원 부족 (미사일)"
                                detail = f"위협 {diag['num_threats']}발 vs 미사일 {diag['total_missiles']}발"
                            elif total_assigned >= max_capacity * 0.9:  # 전체 용량의 90% 이상 사용
                                reason = "용량 부족 (동시 교전 제약)"
                                detail = f"할당 {total_assigned}/{max_capacity}개 (포화 포대: {len(saturated_batteries)}/{len(self.batteries)}개)"
                                # 포화 포대 상세 로깅
                                battery_details = ', '.join([f"{bid}:{info['assigned']}/{info['max_simultaneous']}" for bid, info in list(battery_assignments.items())[:5]])
                                self.control_panel.log_message(
                                    f"[DEBUG] 포대별 할당: {battery_details}",
                                    "DEBUG"
                                )
                            elif diag['feasible_engagements'] < diag['num_threats']:
                                reason = "커버리지 부족"
                                detail = f"교전 가능 {diag['feasible_engagements']} < 위협 {diag['num_threats']}"
                                # Cross-check: 할당 수가 적으면 실제 커버리지 문제
                                if total_assigned < max_capacity * 0.5:
                                    self.control_panel.log_message(
                                        f"[DEBUG] 실제 커버리지 문제 확인: 할당 {total_assigned}/{max_capacity}개 (용량 여유 있음)",
                                        "DEBUG"
                                    )
                            else:
                                reason = "제약 충돌"
                                detail = f"제약 조건 모순 (할당: {total_assigned}/{max_capacity})"
                        else:
                            reason = "알 수 없음"
                            detail = f"상태: {diag['solver_status']}"
                        
                        self.control_panel.log_message(
                            f"[WARN] [T={self.current_time_step}] DWTA Infeasible - {reason}", 
                            "WARNING"
                        )
                        self.control_panel.log_message(
                            f"[INFO] 상세: {detail}", 
                            "INFO"
                        )
                    else:
                        # 기존 로그 (하위 호환)
                        self.control_panel.log_message(
                            f"[WARN] [T={self.current_time_step}] DWTA Infeasible - retrying next optimization", 
                            "WARNING"
                        )
                pass

            self.last_optimization_step = self.current_time_step

        except Exception as e:
            # Log error but don't crash
            error_msg = f"[T={self.current_time_step}] DWTA Error: {e}"
            if self.control_panel:
                self.control_panel.log_message(error_msg, "ERROR")
            else:
                print(error_msg)
            
            # Keep reassignment flags for retry
            pass

    def _prepare_optimizer_inputs(self):
        """Clean Slate: 시뮬레이션 상태에서 옵티마이저 입력 생성.

        기존 대비 변경:
        - engagement_matrix.update_moving_threats() 제거 (segfault 원인)
        - engagement_matrix.add_new_threats() 제거 (segfault 원인)
        - 동적 feasibility/k-factor는 CleanSlateOptimizer.build_problem() 내부에서
          current_position 기반 거리 직접 계산으로 대체 (_check_feasibility, _compute_k)
        - Dict → Dataclass 변환은 그대로 유지 (옵티마이저 인터페이스 호환)
        """

        # Build active threat mapping
        active_threats = {}
        threat_to_asset_map = {}

        # ⚡ 성능 최적화: 한 번의 루프로 처리
        for missile in self.missiles.values():
            if missile['active']:
                threat_id = missile['id']
                target_asset_id = missile['target_asset']
                threat_to_asset_map[threat_id] = target_asset_id

                if target_asset_id not in active_threats:
                    active_threats[target_asset_id] = []
                active_threats[target_asset_id].append(threat_id)

        # ⚡ 성능 최적화: objective 체크를 루프 밖으로
        is_max_kills = (self.objective == 'MAX_KILLS')
        
        # Prepare assets with objective-based value weighting
        assets_opt = []
        for asset in self.assets:
            # Apply objective function weighting
            if is_max_kills:
                value = 1.0  # Egalitarian approach
            else:  # MIN_DAMAGE
                value = asset.get('weighted_value', asset.get('value', 0))

            estimated_threat_missiles = active_threats.get(asset['id'], [])
            
            assets_opt.append(Asset(
                id=asset['id'], 
                position=asset['position'], 
                value=value, 
                priority=asset.get('priority', 1), 
                estimated_threat_missiles=estimated_threat_missiles
            ))
            
        # Prepare interceptor systems with comprehensive specs
        systems_opt = []
        for battery in self.batteries:
            # Only include operational batteries with available missiles
            if battery.get('status') != 'OPERATIONAL' or battery.get('available_missiles', 0) <= 0:
                continue
            
            # Extract system specifications with fallbacks
            try:
                if battery['system_type'] == 'LSAM':
                    specs = battery['specs']['ballistic_missile_specs']
                    Pk = specs['intercept_probability']
                    Range = specs['engagement_range_km']['max']
                    max_missiles = battery['specs']['battery_config'].get('simultaneous_engagements', 2)
                elif battery['system_type'] == 'MSAM':
                    specs = battery['specs']['ballistic_missile_specs']
                    Pk = specs['intercept_probability']
                    Range = specs['engagement_range_km']['max']
                    max_missiles = battery['specs']['battery_config'].get('simultaneous_engagements', 2)
                else:
                    # Default specs by system type
                    if 'LSAM' in battery.get('system_type', ''):
                        Pk, Range, max_missiles = 0.85, 300.0, 3
                    else:
                        Pk, Range, max_missiles = 0.78, 50.0, 3

            except (KeyError, TypeError):
                # Fallback specs by system type
                if 'LSAM' in battery.get('system_type', ''):
                    Pk, Range, max_missiles = 0.85, 300.0, 3
                else:
                    Pk, Range, max_missiles = 0.78, 50.0, 3

            systems_opt.append(InterceptorSystem(
                id=battery['id'], 
                system_type=battery['system_type'], 
                position=battery['position'],
                available_missiles=battery['available_missiles'],
                max_missiles_per_target=min(max_missiles, battery['available_missiles']), 
                intercept_probability=Pk, 
                engagement_range=Range
            ))
            
        # Prepare threats with comprehensive trajectory and timing data
        threats_opt = []
        # (Clean Slate: 새 위협은 build_problem()에서 current_position 기반으로 처리)
        
        for missile in self.missiles.values():
            if missile['active']:
                # Calculate remaining flight time
                remaining_time = max(0.1, missile['flight_time'] * (1.0 - missile['flight_progress']))
                current_pos = missile['position']
                # Find original threat configuration for enhanced data
                original_threat_data = None
                for threat_data in self.initial_threats_config:
                    if threat_data['id'] == missile['id']:
                        original_threat_data = threat_data
                        break

                # Ballistic trajectory altitude: sin curve (launch → apex → impact)
                max_alt_km = 50.0  # default
                if original_threat_data:
                    max_alt_km = original_threat_data.get('specs', {}).get('max_altitude_km', 50.0)
                altitude = max_alt_km * 1000.0 * np.sin(np.pi * missile['flight_progress'])
                
                # Create threat object with basic data
                threat_obj = Threat(
                    id=missile['id'], 
                    target_asset_id=missile['target_asset'],
                    current_position=(current_pos[0], current_pos[1], altitude),
                    estimated_impact_time=remaining_time
                )
                
                # Enhance with original configuration data if available
                if original_threat_data:
                    threat_obj.launch_position = original_threat_data.get('launch_position', (0.0, 0.0))
                    threat_obj.flight_time = original_threat_data.get('flight_time', 300.0)
                    threat_obj.launch_time = original_threat_data.get('launch_time', 0.0)
                    threat_obj.trajectory_type = original_threat_data.get('trajectory_type', 'ballistic')
                    threat_obj.rcs = original_threat_data.get('rcs', 0.5)
                    
                    # Add comprehensive threat specifications
                    threat_obj.specs = {
                        "max_altitude_km": original_threat_data.get('specs', {}).get('max_altitude_km', 50.0),
                        "avg_speed_kmh": original_threat_data.get('specs', {}).get('avg_speed_kmh', 2000.0),
                        "trajectory_type": threat_obj.trajectory_type,
                        "rcs": threat_obj.rcs
                    }
                    # Add phase_events for engagement matrix calculation
                    threat_obj.phase_events = original_threat_data.get('phase_events', {})
                else:
                    # original_threat_data가 없는 경우 missile 객체에서 가져오기
                    threat_obj.launch_position = missile.get('launch_position', (0.0, 0.0))
                    threat_obj.flight_time = missile.get('flight_time', 300.0)
                    threat_obj.launch_time = missile.get('launch_time', 0.0)
                    threat_obj.trajectory_type = 'ballistic'
                    threat_obj.rcs = 0.5
                    threat_obj.specs = missile.get('specs', {
                        "max_altitude_km": 50.0,
                        "avg_speed_kmh": 2000.0,
                        "trajectory_type": 'ballistic',
                        "rcs": 0.5
                    })
                    threat_obj.phase_events = missile.get('phase_events', {})
                
                threats_opt.append(threat_obj)

        # Clean Slate: engagement matrix 증분 갱신 제거 (segfault 원인)
        # CleanSlateOptimizer.build_problem() 내부에서 거리 기반 k값 직접 계산

        return assets_opt, systems_opt, threats_opt

    def _process_optimization_results(self, result, solve_time):
        """Process comprehensive optimization results with enhanced assignment validation."""
        objective_value = result.get('objective_value', 0.0)
        
        # optimization_history는 run_realtime_dwta에서 이미 추가됨 (중복 방지)
        
        # 진단 정보 로그 (100발 시나리오용)
        if result.get('diagnosis') and self.control_panel:
            diag = result['diagnosis']
            pure_st = result.get('pure_solver_time', solve_time)
            self.control_panel.log_message(
                f"[INFO] [T={self.current_time_step}] Optimization: "
                f"Obj={objective_value:.1f}, Solver={pure_st:.3f}s/Total={solve_time:.3f}s, "
                f"Vars={diag['num_variables']}, Constraints={diag['num_constraints']}",
                "INFO"
            )

            # 🆕 GUI 상태 업데이트: 솔버 시간 (Thread-safe Qt signal)
            if self.control_panel and hasattr(self.control_panel, 'sig_solver_update'):
                st = f"{pure_st:.3f}s"
                self.control_panel.sig_solver_update.emit('solver_time', st)

        # 🆕 Warm-start 상태 업데이트 (Thread-safe Qt signal)
        if self.control_panel and hasattr(self.control_panel, 'sig_solver_update'):
            warmstart_applied = result.get('warmstart_applied', False)
            warmstart_count = result.get('warmstart_count', 0)

            if warmstart_applied and warmstart_count > 0:
                ws_text = f"ON ({warmstart_count} vars)"
            else:
                ws_text = "OFF"
            self.control_panel.sig_solver_update.emit('warmstart', ws_text)
        
        # 🆕 Stress Test Metrics 기록
        if self.stress_metrics:
            self.stress_metrics.record_optimization(result, solve_time, self.current_time_step)
        
        new_assignments = {}
        
        # Clear reassignment flags for missiles that were successfully processed
        for missile_id, missile in self.missiles.items():
            if missile.get('needs_reassignment', False) and missile['active']:
                missile['needs_reassignment'] = False
        
        # Extract assignments from both upper and lower layer results
        upper_assignments = result.get('upper_assignments', {})
        lower_assignments = result.get('lower_assignments', {})
        
        # DEBUG: Track what assignments are received from optimizer (제거됨 - I/O 최적화)
        
        # Process assignments separately to preserve both LSAM and MSAM
        all_assignments = {}
        
        # Add upper layer assignments (LSAM) with layer prefix
        for key, system_id in upper_assignments.items():
            all_assignments[f"upper_{key}"] = system_id
        
        # Add lower layer assignments (MSAM) with layer prefix  
        for key, system_id in lower_assignments.items():
            all_assignments[f"lower_{key}"] = system_id
            
        print(f"Combined assignments (with layer prefixes): {len(all_assignments)} - {all_assignments}")
        
        # Handle case where no assignments were made
        if not all_assignments:
            if self.control_panel:
                self.control_panel.log_message(f"[WARN] [T={self.current_time_step}] No assignments from optimization", "WARNING")
            return
        
        assignment_count = 0
        invalid_assignments = 0
        
        # Process each assignment with comprehensive validation
        for assignment_key, system_id in all_assignments.items():
            try:
                # ⚡ 성능 최적화: 문자열 검사 최소화
                # Parse assignment key (format: [upper_|lower_]asset_threat)
                if '_' not in assignment_key:
                    invalid_assignments += 1
                    continue
                
                # Handle layer prefixes
                key_starts_upper = assignment_key.startswith('upper_')  # ⚡ 한 번만 체크
                key_starts_lower = assignment_key.startswith('lower_')  # ⚡ 한 번만 체크
                
                if key_starts_upper or key_starts_lower:
                    # Remove layer prefix
                    actual_key = assignment_key.split('_', 1)[1]
                    layer_type = 'upper' if key_starts_upper else 'lower'  # ⚡ 조건 재사용
                else:
                    actual_key = assignment_key
                    layer_type = "unknown"
                    
                parts = actual_key.split('_', 1)
                if len(parts) != 2:
                    invalid_assignments += 1
                    continue
                    
                asset_id, threat_id = parts
                
                # Validate threat exists and is active
                threat_exists = threat_id in self.missiles and self.missiles[threat_id]['active']
                # Validate system exists and is operational
                system_exists = any(b['id'] == system_id for b in self.batteries if b.get('status') == 'OPERATIONAL')
                
                if not threat_exists or not system_exists:
                    invalid_assignments += 1
                    if not threat_exists:
                        debug_msg = f"Invalid assignment: Threat {threat_id} not found or inactive"
                    else:
                        debug_msg = f"Invalid assignment: System {system_id} not found or non-operational"
                    
                    if self.control_panel:
                        self.control_panel.log_message(debug_msg, "WARNING")
                    continue
                
                # Valid assignment - add to new assignments
                # 🔥 포대당 복수 할당 지원: 리스트에 추가
                if system_id not in new_assignments:
                    new_assignments[system_id] = []
                new_assignments[system_id].append(threat_id)
                assignment_count += 1
                
            except Exception as e:
                invalid_assignments += 1
                error_msg = f"Assignment processing error: {e}"
                if self.control_panel:
                    self.control_panel.log_message(error_msg, "ERROR")
                continue
        # 🆕 Update primary assignments - 리스트 기반 병합 (포대당 복수 할당)
        # 기존 할당 중 비활성 위협만 제거
        active_threat_ids = {tid for tid, m in self.missiles.items() if m.get('active', False)}

        # 🔧 OPTIMIZED: 하이브리드 자료구조의 merge_assignments 사용
        old_assignment_count = self.primary_assignments.get_total_assignments()
        self.primary_assignments.merge_assignments(new_assignments, active_threat_ids)
        total_assignment_count = self.primary_assignments.get_total_assignments()
        
        # 전체 용량 계산
        total_capacity = sum(b['specs']['battery_config']['simultaneous_engagements'] 
                            for b in self.batteries if b.get('status') == 'OPERATIONAL')
        
        # 포대 수 계산 (primary_assignments는 {battery_id: threat_id} 형태이므로 len()이 곧 할당 수)
        # total_assignment_count는 이미 len(self.primary_assignments)로 정확함
        num_batteries_assigned = len(set(self.primary_assignments.keys()))
        total_batteries = len(self.batteries)  # 🔧 FIX: 동적 포대 개수 계산
        capacity_usage = (total_assignment_count / total_capacity * 100) if total_capacity > 0 else 0
        
        # Log optimization summary with capacity status
        summary_msg = f"[INFO] [T={self.current_time_step}] Optimization: {assignment_count} assignments, {invalid_assignments} invalid, Obj={objective_value:.2f}, Time={solve_time:.2f}s"
        if self.control_panel:
            self.control_panel.log_message(summary_msg, "INFO")
            
            # 🆕 용량 상태 로그 (수정: 포대 수 대신 할당 수 표시)
            if assignment_count == 0 and old_assignment_count > 0:
                self.control_panel.log_message(
                    f"[INFO] [T={self.current_time_step}] Optimizer 0개 반환 → 기존 {old_assignment_count}개 할당 유지 (할당: {total_assignment_count}/{total_capacity}, 포대: {num_batteries_assigned}/{total_batteries}, {capacity_usage:.1f}%)",
                    "INFO"
                )
            elif capacity_usage >= 100:
                self.control_panel.log_message(
                    f"[WARN] [T={self.current_time_step}] 용량 포화: {total_assignment_count}/{total_capacity}개 할당 (포대: {num_batteries_assigned}/{total_batteries}, {capacity_usage:.1f}%)",
                    "WARNING"
                )
            elif assignment_count > 0:
                self.control_panel.log_message(
                    f"[INFO] [T={self.current_time_step}] 할당 가능: {assignment_count}개 신규 할당 (총 {total_assignment_count}/{total_capacity}, 포대: {num_batteries_assigned}/{total_batteries}, {capacity_usage:.1f}%)",
                    "INFO"
                )
        else:
            print(summary_msg)

    def update_display(self):
        """DWTAMainWindow QTimer(_on_display_tick)가 TacticalMapWidget을 직접 갱신한다."""
        pass

    def _print_status_report(self):
        """Text-based status report (원본 코드)"""
        if self.current_time_step % 10 == 0:
            print(f"\n{'='*60}")
            print(f"[T={self.current_time_step:3d}] TACTICAL SITUATION REPORT")
            print(f"{'='*60}")
            
            print(f"\n[STATS] Active: {self.stats['active']}, Intercepted: {self.stats['intercepted']}, Missed: {self.stats['missed']}, Total: {self.stats['total']}")
            
            print(f"\n[ASSETS] ({len(self.assets)} total):")
            for asset in self.assets:
                threats_targeting = [mid for mid, m in self.missiles.items() 
                                   if m['active'] and m['target_asset'] == asset['id']]
                status = f"UNDER ATTACK ({len(threats_targeting)} threats)" if threats_targeting else "SAFE"
                threat_list = ', '.join(threats_targeting) if threats_targeting else 'None'
                print(f"  {asset['id']}: Pos({asset['position'][0]:5.1f},{asset['position'][1]:5.1f}) Value:{asset.get('value', 0):4.0f} - {status} [{threat_list}]")
            
            print(f"\n[BATTERIES] ({len(self.batteries)} total):")
            for battery in self.batteries:
                status_icon = "[OK]" if battery.get('status') == 'OPERATIONAL' else "[OFF]"
                assignment = self.primary_assignments.get(battery['id'], 'None')
                ammo = battery.get('available_missiles', 0)
                print(f"  {status_icon} {battery['id']}: {battery.get('system_type', 'Unknown')} Ammo:{ammo:2d} Target:{assignment}")
            
            active_threats = [m for m in self.missiles.values() if m['active']]
            print(f"\n[ACTIVE THREATS] ({len(active_threats)} of {self.stats['total']}):")
            for missile in active_threats:
                progress = missile['flight_progress'] * 100
                remaining = missile['flight_time'] * (1.0 - missile['flight_progress'])
                target = missile['target_asset']
                print(f"  {missile['id']}: -> {target} Progress:{progress:5.1f}% ETA:{remaining:5.1f}s")
            
            print(f"{'='*60}\n")
        
        elif self.current_time_step % 5 == 0:
            active_count = len([m for m in self.missiles.values() if m['active']])
            print(f"[T={self.current_time_step:3d}] Active:{active_count:2d} | Int:{self.stats['intercepted']:2d} | Miss:{self.stats['missed']:2d} | Assignments:{len(self.primary_assignments)}")

    def run_simulation(self, max_duration=3000):
        """Run simulation (GUI 모드에서는 제어 패널에서 실행)"""
        # Headless 모드에서는 GUI 루프 건너뛰기
        if self.headless or not self.control_panel:
            # 텍스트 모드에서는 기존 로직 실행
            self.start_scenario()
            return
        
        # GUI 모드에서만 Qt 이벤트 루프 실행
        if self.control_panel and hasattr(self, '_qt_app'):
            print("GUI 모드: 제어 패널에서 시뮬레이션을 제어하세요.")
            sys.exit(self._qt_app.exec_())
        
        try:
            while True:
                # 1단계: 시뮬레이션 상태 업데이트 (미사일 이동, 충돌 처리)
                self.update_simulation()

                # 2단계: 실시간 DWTA 최적화 (최신 데이터 기반)
                self.run_realtime_dwta()
                
                if self.current_time_step % 2 == 0:
                    self.update_display()
                
                all_threats_launched = all(missile['launch_time'] <= self.current_time_step for missile in self.missiles.values())
                all_threats_resolved = len(self.kill_results) == self.stats['total']
                no_active_threats = self.stats['active'] == 0
                
                if all_threats_launched and all_threats_resolved and no_active_threats:
                    print(f"\nSimulation Complete at T={self.current_time_step}: All {self.stats['total']} threats launched and processed.")
                    break
                
                if self.current_time_step >= max_duration and no_active_threats:
                    print(f"\nSimulation safety limit reached at T={self.current_time_step}: Maximum duration reached.")
                    break
                    
                if self.current_time_step >= max_duration * 2:
                    print(f"\nSimulation emergency termination at T={self.current_time_step}: Absolute maximum duration reached.")
                    break
                
                if self.text_mode and self.current_time_step % 10 == 0:
                    time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nSimulation interrupted by user.")
        except Exception as e:
            print(f"\nAn error occurred during simulation: {e}")
            
        finally:
            # 🔧 Compare 모드에서는 finalize_simulation 생략 (성능 최적화)
            # Compare 모드는 매 iteration마다 실행되므로 파일 I/O와 출력 제거
            if not self.comparison_mode:
                self.finalize_simulation()

    def finalize_simulation(self):
        """Final reporting (원본 코드 유지)"""
        print("\n" + "=" * 50)
        print(f"SIMULATION COMPLETE: T={self.current_time_step}")
        print("=" * 50)
        
        # 시뮬레이션 종료 시 마지막 유효한 목적함수 값 보존
        if self.last_objective_value is None or self.last_objective_value == float('inf'):
            # 최적화 히스토리에서 마지막 유효한 값 찾기
            valid_objective = None
            for time_step, obj_val, solve_time in reversed(self.optimization_history):
                if obj_val != float('inf') and obj_val is not None:
                    valid_objective = obj_val
                    break
            
            if valid_objective is not None:
                self.last_objective_value = valid_objective
                print(f"Final objective value preserved: {self.last_objective_value:.2f}")
            else:
                self.last_objective_value = 0.0  # 기본값 설정
                print("No valid objective value found, set to 0.0")
        
        # 제어 패널 목적함수 값 업데이트 (Thread-safe Qt signal)
        if self.control_panel and self.last_objective_value is not None:
            if hasattr(self.control_panel, 'sig_solver_update'):
                self.control_panel.sig_solver_update.emit('objective', f"{self.last_objective_value:.2f}")
        
        # 🆕 로그 자동 저장
        if self.enable_logging:
            self._save_run_log()
        
        # 🆕 Stress Test Metrics 최종 처리 (연구 논문용 확장)
        if self.stress_metrics:
            # 기본 통계
            intercepted_count = self.stats.get('intercepted', 0)
            missed_count = self.stats.get('missed', 0)
            deviated_count = self.stats.get('deviated', 0)
            total_threats = len(self.missiles)
            
            # 계층별 요격 통계
            upper_intercepts = sum(1 for mid, (result, _, battery_id) in self.kill_results.items() 
                                  if result == 'INTERCEPTED' and battery_id and 'LSAM' in battery_id)
            lower_intercepts = sum(1 for mid, (result, _, battery_id) in self.kill_results.items() 
                                  if result == 'INTERCEPTED' and battery_id and 'MSAM' in battery_id)
            
            # 위협 유형별 분석
            threat_types = {}
            for missile in self.missiles.values():
                threat_type = missile.get('type', 'UNKNOWN')
                threat_types[threat_type] = threat_types.get(threat_type, 0) + 1
            
            # 자산 보호율
            missed_targets = set()
            for missile_id, (result, _, _) in self.kill_results.items():
                if result == 'MISSED':
                    missile = self.missiles.get(missile_id)
                    if missile and missile.get('target_asset') != 'EMPTY_AREA':
                        missed_targets.add(missile['target_asset'])
            assets_protected = len(self.assets) - len(missed_targets)
            
            # 미사일 효율성
            total_initial = sum(b.get('specs', {}).get('battery_config', {}).get('total_missiles', 0) for b in self.batteries)
            total_remaining = sum(b.get('available_missiles', 0) for b in self.batteries)
            missiles_fired = total_initial - total_remaining
            
            self.stress_metrics.record_simulation_result(
                intercepted=intercepted_count,
                missed=missed_count,
                total=total_threats,
                deviated=deviated_count,
                upper_intercepts=upper_intercepts,
                lower_intercepts=lower_intercepts,
                threat_types=threat_types,
                assets_protected=assets_protected,
                total_assets=len(self.assets),
                missiles_fired=missiles_fired,
                missiles_available=total_remaining
            )
            
            # 리포트 생성 및 저장
            self.stress_metrics.print_summary()
            report_filename = f"stress_test_{self.config.scenario_type}_{self.current_algorithm}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.stress_metrics.save_report(report_filename)
        
        # 최종 통계 처리 (원본 로직 유지)
        intercepted_threats = []
        missed_threats = []
        unprocessed_threats = []
        not_launched_threats = []
        
        for missile_id, (result, time, _) in self.kill_results.items():
            if result == 'INTERCEPTED':
                intercepted_threats.append(missile_id)
            elif result == 'MISSED':
                missed_threats.append(missile_id)
        
        for missile_id, missile in self.missiles.items():
            if missile_id not in self.kill_results:
                if missile.get('launch_time', 0) <= self.current_time_step:
                    unprocessed_threats.append(missile_id)
                    
                    if missile.get('active', False):
                        if missile_id not in self.stats['tracked_misses']:
                            self.stats['missed'] += 1
                            self.stats['tracked_misses'].append(missile_id)
                        missed_threats.append(missile_id)
                        self.kill_results[missile_id] = ('MISSED', self.current_time_step, None)
                else:
                    not_launched_threats.append(missile_id)
                    if missile_id not in self.stats['tracked_misses']:
                        self.stats['missed'] += 1
                        self.stats['tracked_misses'].append(missile_id)
                    missed_threats.append(missile_id)
                    self.kill_results[missile_id] = ('NOT_LAUNCHED', self.current_time_step, None)
        
        # 최종 통계 출력 (궤적 이탈 제외)
        deviated = self.stats.get('deviated', 0)
        actual_threats = self.stats['total'] - deviated
        
        print(f"\nFinal Statistics:")
        print(f"Total threats: {self.stats['total']}")
        print(f"Trajectory deviations: {deviated}")
        print(f"Actual threats: {actual_threats}")
        
        if actual_threats > 0:
            print(f"Intercepted: {self.stats['intercepted']} ({100*self.stats['intercepted']/actual_threats:.1f}%)")
            print(f"Missed: {self.stats['missed']} ({100*self.stats['missed']/actual_threats:.1f}%)")
        
        # 🆕 성능 지표 저장
        self.save_performance_metrics()
        
        # Qt GUI 모드에서는 이벤트 루프가 run_simulation()에서 관리됨 (추가 처리 불필요)

    def _save_run_log(self):
        """🆕 실행 로그를 CSV 파일로 저장"""
        import csv
        import os
        from datetime import datetime
        
        # 평균 솔버 시간 계산
        solve_times = [h[2] for h in self.optimization_history if len(h) >= 3 and h[2] is not None]
        avg_solve_time = sum(solve_times) / len(solve_times) if solve_times else 0
        
        # 로그 엔트리 생성
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'algorithm': self.current_algorithm,
            'scenario': self.config.scenario_type,
            'warmstart_enabled': hasattr(self, 'mip_optimizer_instance'),
            'total_threats': self.stats['total'],
            'intercepted': self.stats['intercepted'],
            'missed': self.stats['missed'],
            'intercept_rate': (self.stats['intercepted'] / self.stats['total'] * 100) if self.stats['total'] > 0 else 0,
            'avg_solve_time': avg_solve_time,
            'objective_value': self.last_objective_value if self.last_objective_value is not None else 0
        }
        
        self.run_logs.append(log_entry)
        
        # CSV 파일로 저장
        os.makedirs("performance_results", exist_ok=True)
        csv_file = f"performance_results/gui_run_log_{self.config.scenario_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if self.run_logs:
                writer = csv.DictWriter(f, fieldnames=log_entry.keys())
                writer.writeheader()
                writer.writerows(self.run_logs)
        
        print(f"[OK] 실행 로그 저장: {csv_file}")
    
    def save_performance_metrics(self):
        """성능 지표를 CSV 파일로 저장 (확장된 메트릭)"""
        import csv
        import os
        import numpy as np
        from datetime import datetime
        
        # 결과 디렉토리 생성
        os.makedirs('performance_results', exist_ok=True)
        
        # 파일명
        filename = f'performance_results/metrics_{self.config.scenario_type}_{self.current_algorithm}.csv'
        
        # 최적화 시간 통계
        solve_times = [h[2] for h in self.optimization_history if len(h) >= 3]
        objective_values = [h[1] for h in self.optimization_history if len(h) >= 2 and h[1] != float('inf')]
        
        # 미사일 효율성 계산
        total_initial_missiles = sum(b.get('specs', {}).get('battery_config', {}).get('total_missiles', 0) for b in self.batteries)
        total_remaining_missiles = sum(b.get('available_missiles', 0) for b in self.batteries)
        missiles_used = total_initial_missiles - total_remaining_missiles
        missile_efficiency = (self.stats['intercepted'] / missiles_used * 100) if missiles_used > 0 else 0
        
        # 자산 생존율 계산
        missed_targets = set()
        for missile_id, (result, _, _) in self.kill_results.items():
            if result == 'MISSED':
                missile = self.missiles.get(missile_id)
                if missile and missile.get('target_asset') != 'EMPTY_AREA':
                    missed_targets.add(missile['target_asset'])
        
        assets_survived = len(self.assets) - len(missed_targets)
        asset_survival_rate = (assets_survived / len(self.assets) * 100) if self.assets else 0
        
        # 궤적 이탈 제외한 실제 위협
        deviated = self.stats.get('deviated', 0)
        actual_threats = self.stats['total'] - deviated
        actual_intercept_rate = (self.stats['intercepted'] / actual_threats * 100) if actual_threats > 0 else 0
        
        # 메트릭 데이터
        metrics = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'scenario': self.config.scenario_type,
            'algorithm': self.current_algorithm,
            
            # 기본 지표
            'total_threats': self.stats['total'],
            'actual_threats': actual_threats,
            'deviated': deviated,
            'intercepted': self.stats['intercepted'],
            'missed': self.stats['missed'],
            'intercept_rate': actual_intercept_rate,
            
            # 계산 시간 통계
            'avg_solve_time': np.mean(solve_times) if solve_times else 0,
            'std_solve_time': np.std(solve_times) if solve_times else 0,
            'min_solve_time': np.min(solve_times) if solve_times else 0,
            'max_solve_time': np.max(solve_times) if solve_times else 0,
            
            # 목적함수 통계
            'final_objective': objective_values[-1] if objective_values else 0,
            'avg_objective': np.mean(objective_values) if objective_values else 0,
            'std_objective': np.std(objective_values) if objective_values else 0,
            'min_objective': np.min(objective_values) if objective_values else 0,
            'max_objective': np.max(objective_values) if objective_values else 0,
            
            # 자원 효율성
            'missiles_used': missiles_used,
            'missile_efficiency': missile_efficiency,
            
            # 전략 지표
            'asset_survival_rate': asset_survival_rate,
            'assets_survived': assets_survived,
            'assets_lost': len(missed_targets),
            
            # 기타
            'total_optimizations': len(solve_times),
            'simulation_time': self.current_time_step
        }
        
        # CSV 저장 (append 모드)
        file_exists = os.path.exists(filename)
        
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=metrics.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(metrics)
        
        if self.headless:
            print(f"성능 지표 저장: {filename}")
        
        return metrics


def _calculate_stress_metrics(tracker):
    """Stress test 메트릭 계산 (iteration 종료 시 1회만 호출)"""
    # 계층별 요격 통계
    upper_intercepts = 0
    lower_intercepts = 0
    for mid, result_tuple in tracker.kill_results.items():
        # kill_results 형식: (result, timestamp, battery_id) 또는 (result, timestamp)
        result = result_tuple[0]
        battery_id = result_tuple[2] if len(result_tuple) > 2 else None
        
        if result == 'INTERCEPTED' and battery_id:
            if 'LSAM' in battery_id:
                upper_intercepts += 1
            elif 'MSAM' in battery_id:
                lower_intercepts += 1
    
    # 자산 보호율
    missed_targets = set()
    for missile_id, result_tuple in tracker.kill_results.items():
        result = result_tuple[0]
        if result == 'MISSED':
            missile = tracker.missiles.get(missile_id)
            if missile and missile.get('target_asset') != 'EMPTY_AREA':
                missed_targets.add(missile['target_asset'])
    assets_protected = len(tracker.assets) - len(missed_targets)
    
    # 미사일 사용량
    total_initial = sum(b.get('specs', {}).get('battery_config', {}).get('total_missiles', 0) for b in tracker.batteries)
    total_remaining = sum(b.get('available_missiles', 0) for b in tracker.batteries)
    missiles_fired = total_initial - total_remaining
    
    return {
        'upper_intercepts': upper_intercepts,
        'lower_intercepts': lower_intercepts,
        'assets_protected': assets_protected,
        'missiles_fired': missiles_fired
    }


if __name__ == "__main__":
    import sys
    
    # 비교 실험 모드 체크
    if len(sys.argv) > 1 and sys.argv[1] == '--compare':
        # 비교 실험 모드
        algorithms = ['MIP', 'Greedy', 'GA']
        scenarios = ['BASELINE_15']
        iterations = 1  # 기본 반복 횟수
        
        # 명령줄 인자 파싱: --compare [N] [algorithms] [scenarios]
        # 예: --compare 10 MIP,Greedy,GA SMALL_3,BASELINE_15,LARGE_30
        i = 2
        algo_specified = False
        while i < len(sys.argv):
            arg = sys.argv[i]
            
            if arg == '--iterations' and i + 1 < len(sys.argv):
                iterations = int(sys.argv[i + 1])
                i += 2
            elif arg.isdigit():  # 숫자만 있으면 iterations로 처리
                iterations = int(arg)
                i += 1
            elif ',' in arg or arg in ['MIP', 'Greedy', 'GA']:
                # 알고리즘 리스트
                algorithms = arg.split(',')
                algo_specified = True
                i += 1
            elif arg.startswith('SMALL_') or arg.startswith('MEDIUM_') or arg.startswith('BASELINE_') or \
                 arg.startswith('LARGE_') or arg.startswith('HEAVY_') or arg.startswith('STRESS_') or \
                 arg.startswith('SEQUENTIAL_') or arg.startswith('SIMULTANEOUS_') or arg.startswith('LIGHT_') or \
                 arg.startswith('MIXED_') or ',' in arg:
                # 시나리오 리스트
                scenarios = arg.split(',')
                i += 1
            else:
                i += 1
        
        print("="*80)
        print("DWTA Algorithm Comparison Experiment")
        print("="*80)
        print(f"Scenarios: {scenarios}")
        print(f"Algorithms: {algorithms}")
        print(f"Iterations: {iterations}")
        print("="*80)
        
        all_results = []  # 모든 반복 결과 저장
        summary_results = []  # 통계 요약 결과
        
        for scenario in scenarios:
            print(f"\n{'='*80}")
            print(f"Testing Scenario: {scenario}")
            print(f"{'='*80}")
            
            mip_config.scenario_type = scenario
            
            # 🔧 리팩토링: 단일 tracker로 모든 알고리즘 및 iteration 실행
            tracker = MultiMissileTracker(
                use_mip=True, 
                objective='MIN_DAMAGE',
                headless=True
            )
            tracker.comparison_mode = True
            
            # Stress test 메트릭 초기화
            if hasattr(tracker, 'stress_metrics'):
                tracker.stress_metrics.scenario_name = scenario
            
            for algorithm in algorithms:
                print(f"\n--- Running {algorithm} ({iterations} iterations) ---")
                tracker.current_algorithm = algorithm
                
                # 알고리즘별 stress metrics 초기화
                if hasattr(tracker, 'stress_metrics'):
                    tracker.stress_metrics.algorithm = algorithm
                
                iteration_results = []
                
                for iteration in range(iterations):
                    try:
                        import time
                        import numpy as np
                        
                        print(f"\n  [{algorithm}] Iteration {iteration + 1}/{iterations}...", end=' ')
                        
                        # 🔧 시뮬레이션 상태만 리셋 (tracker는 재사용)
                        tracker.reset_for_next_iteration()
                        
                        # 알고리즘 설정 확인
                        print(f"Algorithm={tracker.current_algorithm}", end=' ')
                        
                        start_time = time.time()
                        tracker.run_simulation(max_duration=1600)
                        total_time = time.time() - start_time
                        
                        # 결과 수집
                        stats = tracker.stats
                        total_threats = stats['total']
                        deviated = stats.get('deviated', 0)
                        actual_threats = total_threats - deviated
                        intercepted = min(stats['intercepted'], actual_threats)
                        missed = stats['missed']
                        intercept_rate = (intercepted / actual_threats * 100) if actual_threats > 0 else 0
                        intercept_rate = min(intercept_rate, 100.0)
                        
                        # 최적화 시간
                        solve_times = [h[2] for h in tracker.optimization_history if len(h) >= 3]
                        avg_solve_time = sum(solve_times) / len(solve_times) if solve_times else 0
                        max_solve_time = max(solve_times) if solve_times else 0
                        min_solve_time = min(solve_times) if solve_times else 0
                        
                        # 목적함수 값 (기댓값 손실)
                        # 저장 시점에 이미 정규화되어 있으므로 필터링만 수행
                        objective_values = []
                        for h in tracker.optimization_history:
                            if len(h) >= 2:
                                obj_val = h[1]
                                # inf/nan 필터링
                                if obj_val != float('inf') and obj_val is not None and not (isinstance(obj_val, float) and obj_val != obj_val):
                                    objective_values.append(obj_val)
                        
                        final_objective = objective_values[-1] if objective_values else 0
                        avg_objective = sum(objective_values) / len(objective_values) if objective_values else 0
                        
                        # 추가 메트릭 계산
                        missiles_used = 0
                        if hasattr(tracker, 'stats'):
                            missiles_used = tracker.stats.get('intercepted', 0) * 2  # 살보 2발 가정
                        
                        # 자원 효율성
                        resource_efficiency = (intercepted / missiles_used * 100) if missiles_used > 0 else 0
                        
                        # 🆕 Stress test 메트릭 수집 (iteration 종료 시 1회만 계산)
                        stress_data = _calculate_stress_metrics(tracker)
                        
                        result = {
                            'scenario': scenario,
                            'algorithm': algorithm,
                            'iteration': iteration + 1,
                            'total_threats': total_threats,
                            'intercepted': intercepted,
                            'missed': missed,
                            'intercept_rate': intercept_rate,
                            'avg_solve_time': avg_solve_time,
                            'max_solve_time': max_solve_time,
                            'min_solve_time': min_solve_time,
                            'final_objective': final_objective,
                            'avg_objective': avg_objective,
                            'total_time': total_time,
                            'num_optimizations': len(solve_times),
                            'missiles_used': missiles_used,
                            'resource_efficiency': resource_efficiency,
                            **stress_data  # 🆕 Stress test 메트릭 추가
                        }
                        iteration_results.append(result)
                        all_results.append(result)
                        
                        print(f"[OK] ({intercept_rate:.1f}%, {avg_solve_time:.3f}s)")
                        
                    except Exception as e:
                        print(f"✗ Failed: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 통계 계산
                if iteration_results:
                    import numpy as np
                    intercept_rates = [r['intercept_rate'] for r in iteration_results]
                    solve_times = [r['avg_solve_time'] for r in iteration_results]
                    objectives = [r['final_objective'] for r in iteration_results]
                    total_times = [r['total_time'] for r in iteration_results]
                    
                    # 🆕 Stress test 메트릭 통계
                    stress_summary = {}
                    if 'upper_intercepts' in iteration_results[0]:
                        upper_intercepts = [r.get('upper_intercepts', 0) for r in iteration_results]
                        lower_intercepts = [r.get('lower_intercepts', 0) for r in iteration_results]
                        assets_protected = [r.get('assets_protected', 0) for r in iteration_results]
                        missiles_fired = [r.get('missiles_fired', 0) for r in iteration_results]
                        
                        stress_summary = {
                            'upper_intercepts_mean': np.mean(upper_intercepts),
                            'lower_intercepts_mean': np.mean(lower_intercepts),
                            'assets_protected_mean': np.mean(assets_protected),
                            'missiles_fired_mean': np.mean(missiles_fired)
                        }
                    
                    summary = {
                        'scenario': scenario,
                        'algorithm': algorithm,
                        'iterations': len(iteration_results),
                        'intercept_rate_mean': np.mean(intercept_rates),
                        'intercept_rate_std': np.std(intercept_rates),
                        'intercept_rate_min': np.min(intercept_rates),
                        'intercept_rate_max': np.max(intercept_rates),
                        'solve_time_mean': np.mean(solve_times),
                        'solve_time_std': np.std(solve_times),
                        'objective_mean': np.mean(objectives),
                        'objective_std': np.std(objectives),
                        'total_time_mean': np.mean(total_times),
                        'total_time_std': np.std(total_times),
                        **stress_summary  # 🆕 Stress test 통계 추가
                    }
                    summary_results.append(summary)
                    
                    print(f"\n  [SUMMARY] {algorithm}:")
                    print(f"    Intercept Rate: {summary['intercept_rate_mean']:.1f}% ± {summary['intercept_rate_std']:.1f}% (min: {summary['intercept_rate_min']:.1f}%, max: {summary['intercept_rate_max']:.1f}%)")
                    print(f"    Solve Time: {summary['solve_time_mean']:.4f}s ± {summary['solve_time_std']:.4f}s")
                    print(f"    Objective: {summary['objective_mean']:.2f} ± {summary['objective_std']:.2f}")
        
        # 결과 저장
        if all_results:
            import csv
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 전체 결과 저장 (모든 반복)
            csv_file_all = f"performance_results/comparison_all_{timestamp}.csv"
            with open(csv_file_all, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
                writer.writeheader()
                writer.writerows(all_results)
            print(f"\n[OK] 전체 결과 CSV 저장: {csv_file_all}")
            
            # 통계 요약 저장
            if summary_results:
                csv_file_summary = f"performance_results/comparison_summary_{timestamp}.csv"
                with open(csv_file_summary, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=summary_results[0].keys())
                    writer.writeheader()
                    writer.writerows(summary_results)
                print(f"[OK] 통계 요약 CSV 저장: {csv_file_summary}")
            
            # 개선된 비교 표 출력
            print("="*150)
            print("[PERFORMANCE] ENHANCED PERFORMANCE COMPARISON SUMMARY (with Stress Test Metrics)")
            print("="*150)
            print(f"{'Scenario':<15} {'Algorithm':<10} {'Intercept%':<23} {'Solve Time(s)':<18} {'Objective':<25} {'Upper/Lower':<15} {'Assets':<8}")
            print("="*150)
            for r in summary_results:
                scenario = r['scenario']
                algorithm = r['algorithm']
                
                intercept_mean = r['intercept_rate_mean']
                intercept_std = r['intercept_rate_std']
                intercept_min = r['intercept_rate_min']
                intercept_max = r['intercept_rate_max']
                
                solve_mean = r['solve_time_mean']
                solve_std = r['solve_time_std']
                
                # 목적함수 값 (스케일링 제거됨)
                obj_mean = r['objective_mean']
                obj_std = r['objective_std']
                
                # 🆕 Stress test 메트릭
                upper_mean = r.get('upper_intercepts_mean', 0)
                lower_mean = r.get('lower_intercepts_mean', 0)
                assets_mean = r.get('assets_protected_mean', 0)
                
                print(f"{scenario:<15} {algorithm:<10} {intercept_mean:5.1f}±{intercept_std:<4.1f} ({int(intercept_min)}-{int(intercept_max)})   "
                      f"{solve_mean:7.4f}±{solve_std:<7.4f}   {obj_mean:10.2f}±{obj_std:<10.2f}   "
                      f"{upper_mean:4.1f}/{lower_mean:<4.1f}   {assets_mean:>6.1f}")
            
            print("="*150)
            
            # 상세 분석 추가
            print(f"\n{'='*120}")
            print("[ANALYSIS] DETAILED ANALYSIS")
            print(f"{'='*120}")
            
            # 알고리즘별 그룹화
            algo_groups = {}
            for r in summary_results:
                algo = r['algorithm']
                if algo not in algo_groups:
                    algo_groups[algo] = []
                algo_groups[algo].append(r)
            
            for algo, results in algo_groups.items():
                print(f"\n[{algo}] Algorithm:")
                print(f"  {'Metric':<25} {'Value':<30} {'Interpretation'}")
                print(f"  {'-'*80}")
                
                for r in results:
                    # 요격률 분석
                    intercept_quality = "Excellent" if r['intercept_rate_mean'] >= 95 else \
                                       "Good" if r['intercept_rate_mean'] >= 85 else \
                                       "Fair" if r['intercept_rate_mean'] >= 70 else "Poor"
                    print(f"  {'Intercept Rate':<25} {r['intercept_rate_mean']:.1f}% ± {r['intercept_rate_std']:.1f}%{'':<10} {intercept_quality}")
                    
                    # 계산 시간 분석
                    speed_quality = "Very Fast" if r['solve_time_mean'] < 0.01 else \
                                   "Fast" if r['solve_time_mean'] < 0.1 else \
                                   "Moderate" if r['solve_time_mean'] < 1.0 else "Slow"
                    print(f"  {'Solve Time':<25} {r['solve_time_mean']:.4f}s ± {r['solve_time_std']:.4f}s{'':<5} {speed_quality}")
                    
                    # 안정성 분석
                    stability = "Stable" if r['intercept_rate_std'] < 5 else \
                               "Moderate" if r['intercept_rate_std'] < 10 else "Unstable"
                    print(f"  {'Stability (Std Dev)':<25} {r['intercept_rate_std']:.1f}%{'':<20} {stability}")
                    
                    # 목적함수 변동성
                    obj_cv = (r['objective_std'] / r['objective_mean'] * 100) if r['objective_mean'] > 0 else 0
                    obj_quality = "Low Variance" if obj_cv < 10 else \
                                 "Moderate Variance" if obj_cv < 30 else "High Variance"
                    print(f"  {'Objective Variance':<25} {obj_cv:.1f}% CV{'':<17} {obj_quality}")
                    
                    # 미사일 사용 효율 (SPK - Single-shot Probability of Kill equivalent)
                    spk = r['intercept_rate_mean'] / 100.0
                    spk_quality = "Excellent" if spk > 0.95 else "Good" if spk > 0.85 else "Fair"
                    print(f"  {'SPK (표적당 요격 확률)':<25} {spk:.3f}{'':<22} {spk_quality}")
                    
                    # Expected Damage (목적함수 값)
                    expected_damage = r['objective_mean']
                    damage_quality = "최소화" if expected_damage < 10000 else "보통" if expected_damage < 50000 else "높음"
                    print(f"  {'Expected Damage':<25} {expected_damage:,.0f}{'':<15} {damage_quality}")
                    
                    # 🆕 다층 방어 분석
                    if 'upper_intercepts_mean' in r:
                        upper_mean = r['upper_intercepts_mean']
                        lower_mean = r['lower_intercepts_mean']
                        total_layer = upper_mean + lower_mean
                        upper_ratio = (upper_mean / total_layer * 100) if total_layer > 0 else 0
                        layer_quality = "균형" if 40 <= upper_ratio <= 60 else "상층 우세" if upper_ratio > 60 else "하층 우세"
                        print(f"  {'Multi-Layer Defense':<25} U:{upper_mean:.1f} / L:{lower_mean:.1f} ({upper_ratio:.0f}%){'':<5} {layer_quality}")
                    
                    # 🆕 자산 보호율
                    if 'assets_protected_mean' in r:
                        assets_protected = r['assets_protected_mean']
                        protection_rate = assets_protected  # 이미 평균값
                        protection_quality = "우수" if protection_rate >= 9 else "양호" if protection_rate >= 7 else "보통"
                        print(f"  {'Assets Protected':<25} {assets_protected:.1f} / 10{'':<15} {protection_quality}")
                    
                    # Runtime (계산 시간)
                    runtime = r['solve_time_mean']
                    runtime_quality = "실시간 가능" if runtime < 0.1 else "준실시간" if runtime < 1.0 else "오프라인"
                    print(f"  {'Runtime':<25} {runtime:.4f}s{'':<17} {runtime_quality}")
            
            # 알고리즘 비교
            print(f"\n{'='*120}")
            print("[COMPARISON] ALGORITHM COMPARISON")
            print(f"{'='*120}")
            
            if len(algo_groups) >= 2:
                algos = list(algo_groups.keys())
                print(f"\n  Metric Comparison ({' vs '.join(algos)}):")
                print(f"  {'-'*80}")
                
                # MIP vs GA 비교
                if 'MIP' in algo_groups and 'GA' in algo_groups:
                    mip_data = algo_groups['MIP'][0]
                    ga_data = algo_groups['GA'][0]
                    
                    intercept_diff = mip_data['intercept_rate_mean'] - ga_data['intercept_rate_mean']
                    time_ratio = ga_data['solve_time_mean'] / mip_data['solve_time_mean'] if mip_data['solve_time_mean'] > 0 else 0
                    
                    print(f"  - Intercept Rate: MIP {mip_data['intercept_rate_mean']:.1f}% vs GA {ga_data['intercept_rate_mean']:.1f}% "
                          f"(Δ {intercept_diff:+.1f}%)")
                    print(f"  - Speed: GA is {time_ratio:.1f}x faster than MIP")
                    print(f"  - Quality/Speed Tradeoff: ", end="")
                    
                    if abs(intercept_diff) < 5 and time_ratio > 10:
                        print("GA recommended (similar quality, much faster)")
                    elif intercept_diff > 5:
                        print("MIP recommended (significantly better quality)")
                    else:
                        print("Comparable performance")
                
                # Greedy 비교
                if 'Greedy' in algo_groups:
                    greedy_data = algo_groups['Greedy'][0]
                    print(f"\n  - Greedy Baseline: {greedy_data['intercept_rate_mean']:.1f}% "
                          f"(fastest but lowest quality)")
            
            print(f"\n{'='*120}")
    
    else:
        # GUI 모드 (기본)
        SELECTED_OBJECTIVE = 'MIN_DAMAGE' 
        USE_MIP_SYSTEM = True
        
        tracker = MultiMissileTracker(use_mip=USE_MIP_SYSTEM, objective=SELECTED_OBJECTIVE)
        
        duration = getattr(mip_config, 'simulation_duration_sec', 800)
        tracker.run_simulation(max_duration=duration)

"""
===================================================================================
main 함수 실행 시 호출되는 주요 메서드 및 기능 설명
===================================================================================

1. MultiMissileTracker.__init__(use_mip=True, objective='MIN_DAMAGE', headless=False)
   - 역할: 실시간 DWTA 시뮬레이터 초기화
   - 주요 기능:
     * MIP 최적화 시스템 활성화 여부 설정 (use_mip)
     * 목적함수 설정 ('MIN_DAMAGE': 피해 최소화, 'MAX_KILLS': 요격 최대화)
     * config_mip.py에서 시나리오 데이터 로드 (_load_scenario 호출)
     * 시뮬레이션 상태 변수 초기화:
       - current_time_step: 현재 시간 단계 (0부터 시작)
       - missiles: 미사일 객체 저장 딕셔너리
       - primary_assignments: 최적화 할당 결과 저장
       - stats: 통계 정보 (요격 성공/실패, 활성 위협 등)
     * Shoot-Look-Shoot 전략 설정:
       - max_engagement_attempts: 동일 위협에 대한 최대 교전 횟수 (3회)
       - lookback_time: 교전 결과 확인 대기 시간 (4초)
     * GUI 시각화 설정 (_setup_gui_visualization 호출)
       - matplotlib 기반 전술 디스플레이 및 분석 패널 생성
       - ControlPanel 객체 생성 (GUI 제어 패널)

2. tracker.run_simulation(max_duration=1600)
   - 역할: 시뮬레이션 메인 루프 실행
   - 주요 기능:
     * GUI 모드: 제어 패널을 통한 수동 시뮬레이션 제어
       - 사용자가 시작/일시정지/정지 버튼으로 제어
       - 실시간 상태 업데이트 및 이벤트 로그 표시
     * 텍스트 모드 (headless): 자동 시뮬레이션 실행
       - start_scenario() 호출: 시나리오 초기화 및 위협 미사일 생성
       - 메인 루프:
         a) run_realtime_dwta(): 실시간 DWTA 최적화 수행
         b) update_simulation(): 시뮬레이션 상태 업데이트 (시간 진행)
         c) update_display(): 시각화 업데이트
       - 종료 조건 확인:
         * 모든 위협 발사 완료
         * 모든 위협 처리 완료 (요격 성공/실패 판정)
         * 최대 시뮬레이션 시간 도달

3. tracker.start_scenario() [run_simulation 내부에서 호출]
   - 역할: 시나리오 초기화 및 위협 미사일 생성
   - 주요 기능:
     * current_time_step을 0으로 초기화
     * initial_threats_config에서 각 위협에 대해:
       - 미사일 객체 생성 (ID, 발사 위치, 목표 자산, 발사 시간, 비행 시간 등)
       - 궤적 계산 (_calculate_trajectory 호출)
       - 재표적 가능 여부 및 확률 설정
     * 총 위협 수 통계 업데이트 (stats['total'])

4. tracker.run_realtime_dwta() [run_simulation 메인 루프에서 호출]
   - 역할: 실시간 DWTA(Dynamic Weapon-Target Assignment) 최적화 수행
   - 주요 기능:
     * 활성 위협 수 계산 및 검증
     * 최적화 간격 제어 (optimization_interval = 1초)
     * 데드락 방지: 타임스텝당 최대 최적화 횟수 제한
     * 최적화 입력 준비 (_prepare_optimizer_inputs 호출):
       - 현재 활성 위협 목록
       - 사용 가능한 요격 시스템 목록
       - 보호 대상 자산 목록
     * NonLinearMIPOptimizer 실행:
       - MIP 모델 생성 (create_model)
       - 최적화 문제 해결 (solve)
       - 타임아웃 모니터링 (최대 15초)
     * 최적화 결과 처리 (_process_optimization_results 호출):
       - 요격 미사일 할당 결정
       - 포대 탄약 상태 업데이트
       - 할당 이력 저장
     * 목적함수 값 및 해결 시간 추적

5. tracker.update_simulation() [run_simulation 메인 루프에서 호출]
   - 역할: 시뮬레이션 상태를 한 타임스텝(5초) 진행
   - 주요 기능:
     * current_time_step 증가 (5초 단위)
     * 동적 이벤트 시뮬레이션 (_simulate_dynamic_events 호출):
       - 새로운 위협 발사 확인 및 활성화
       - 미사일 비행 진행 상태 업데이트
       - 요격 결과 판정 (성공/실패)
       - 재표적 이벤트 처리
     * 통계 업데이트:
       - 활성 위협 수 (stats['active'])
       - 요격 성공/실패 카운트
       - 재표적 횟수
     * Shoot-Look-Shoot 로직 처리:
       - 교전 결과 확인 (lookback_time 후)
       - 실패 시 재교전 결정

6. tracker.update_display() [run_simulation에서 주기적으로 호출]
   - 역할: GUI 시각화 업데이트
   - 주요 기능:
     * 전술 디스플레이 업데이트 (_draw_tactical_display):
       - 자산, 포대, 미사일 위치 표시
       - 미사일 궤적 및 할당 관계 시각화
       - 탄약 상태 및 범위 표시
     * 분석 패널 업데이트 (_draw_analysis_panel):
       - 목적함수 값 변화 그래프
       - 최적화 이력 표시
     * 제어 패널 상태 업데이트 (control_panel.update_status):
       - 현재 시간, 활성 위협 수
       - 요격 성공/실패 통계
       - 성공률 계산

===================================================================================
실행 흐름 요약:
===================================================================================
1. MultiMissileTracker 객체 생성 → 시나리오 로드 및 GUI 초기화
2. run_simulation 호출 → GUI 모드 또는 자동 모드 선택
3. [GUI 모드] 사용자가 제어 패널에서 시뮬레이션 시작
   [자동 모드] start_scenario로 위협 초기화 후 메인 루프 진입
4. 메인 루프 반복:
   - run_realtime_dwta: 최적화 수행 및 요격 미사일 할당
   - update_simulation: 시간 진행 및 이벤트 처리
   - update_display: 시각화 업데이트
5. 종료 조건 만족 시 최종 통계 출력 및 시각화 저장
===================================================================================
"""