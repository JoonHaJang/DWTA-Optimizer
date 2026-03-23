"""
Multi-Missile Real-time DWTA Analysis Simulator - GUI Version
============================================================
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import time
import random
from typing import Dict, List, Tuple, Optional, Set
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import warnings
from datetime import datetime

# Set matplotlib backend for GUI
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    # Suppress matplotlib aspect ratio warnings
    warnings.filterwarnings('ignore', message='.*fixed.*limits.*adjustable.*')
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# 🆕 Phase 2: PyQtGraph import for high-performance visualization
PYQTGRAPH_AVAILABLE = False
try:
    import pyqtgraph as pg
    from PyQt5 import QtWidgets, QtCore
    from pyqtgraph_display import PyQtGraphDisplay
    PYQTGRAPH_AVAILABLE = True
    print("[OK] PyQtGraph available for high-performance visualization")
except ImportError:
    print("[INFO] PyQtGraph not available (optional). Install with: pip install pyqtgraph PyQt5")

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
        
        # 🆕 2단계: 새로 할당될 위협에 대한 기존 할당 제거
        # (MIP 제약 조건 준수: 위협당 최대 2개 배터리)
        new_threat_ids = set()
        for battery_id, threat_list in new_assignments.items():
            new_threat_ids.update(threat_list)
        
        for threat_id in new_threat_ids:
            if threat_id in self.threat_id_to_idx:
                t_idx = self.threat_id_to_idx[threat_id]
                battery_indices = self.threat_to_batteries[t_idx].copy()
                for b_idx in battery_indices:
                    battery_id = self.idx_to_battery_id[b_idx]
                    self.unassign(threat_id, battery_id)
        
        # 3단계: 새 할당 추가
        for battery_id, threat_list in new_assignments.items():
            for threat_id in threat_list:
                if threat_id in active_threat_ids:
                    self.assign(threat_id, battery_id)

class ControlPanel:
    """GUI 제어 패널"""
    def __init__(self, tracker):
        self.tracker = tracker
        self.control_window = None
        self.running = False
        self.paused = False
        
        # 제어 변수들
        self.speed_var = tk.DoubleVar(value=1.0)
        self.objective_var = tk.StringVar(value=tracker.objective)
        self.max_duration_var = tk.IntVar(value=1600)
        self.scenario_var = tk.StringVar(value=tracker.config.scenario_type if hasattr(tracker.config, 'scenario_type') else "BASELINE_15")
        
        # 🆕 알고리즘 선택 변수
        self.algorithm_var = tk.StringVar(value="MIP")

        # 🆕 Warm-start 토글 변수
        self.warmstart_enabled_var = tk.BooleanVar(value=True)

        # 🆕 로그 수집 변수
        self.logging_enabled_var = tk.BooleanVar(value=False)

        # 🆕 Phase 2.3: Visualization backend selection
        self.viz_backend_var = tk.StringVar(value="matplotlib")
        
        # 실행 시간 측정용
        self.sim_start_time = None
        self.sim_elapsed_time = 0
        
    def create_control_window(self):
        """제어 창 생성 (교착 상태 방지 개선)"""
        try:
            # ⚡ 교착 방지: tkinter 이벤트 큐 정리
            import tkinter as tk
            root = tk._default_root
            if root:
                root.update_idletasks()
            
            self.control_window = tk.Toplevel()
            self.control_window.title("DWTA TACTICAL CONTROL SYSTEM")
            self.control_window.geometry("850x650")
            self.control_window.configure(bg='#0a0a0a')
            self.control_window.protocol("WM_DELETE_WINDOW", self.on_closing)
            
            # ⚡ 교착 방지: 창 생성 후 이벤트 처리
            self.control_window.update_idletasks()
        except Exception as e:
            print(f"[WARN] 제어 창 생성 실패: {e}")
            raise
        
        # Configure military-style theme
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure military colors
        style.configure('Military.TLabelframe', 
                       background='#0a0a0a',
                       bordercolor='#2a4a2a',
                       darkcolor='#1a2a1a',
                       lightcolor='#3a5a3a',
                       borderwidth=2,
                       relief='solid')
        style.configure('Military.TLabelframe.Label',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       font=('Consolas', 10, 'bold'))
        
        style.configure('Military.TButton',
                       background='#1a3a1a',
                       foreground='#00ff00',
                       bordercolor='#2a4a2a',
                       focuscolor='#0066ff',
                       font=('Consolas', 9, 'bold'),
                       relief='raised',
                       borderwidth=2)
        style.map('Military.TButton',
                 background=[('active', '#2a5a2a'), ('pressed', '#0a2a0a')],
                 foreground=[('active', '#66ff66'), ('pressed', '#ffffff')])
        
        style.configure('Military.TLabel',
                       background='#0a0a0a',
                       foreground='#cccccc',
                       font=('Consolas', 9))
        
        style.configure('Status.TLabel',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       font=('Consolas', 9, 'bold'))
        
        style.configure('Military.TCombobox',
                       fieldbackground='#1a1a1a',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       bordercolor='#2a4a2a',
                       arrowcolor='#00ff00',
                       selectbackground='#2a4a2a',
                       selectforeground='#00ff00')
        style.map('Military.TCombobox',
                 fieldbackground=[('readonly', '#1a1a1a')],
                 background=[('readonly', '#0a0a0a')])
        
        style.configure('Military.TSpinbox',
                       fieldbackground='#1a1a1a',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       bordercolor='#2a4a2a',
                       selectbackground='#2a4a2a',
                       selectforeground='#00ff00')
        style.map('Military.TSpinbox',
                 fieldbackground=[('readonly', '#1a1a1a')],
                 background=[('readonly', '#0a0a0a')])
        
        style.configure('Military.Horizontal.TScale',
                       background='#0a0a0a',
                       troughcolor='#404040',
                       bordercolor='#2a4a2a',
                       lightcolor='#00ff00',
                       darkcolor='#006600',
                       sliderlength=20)
        style.map('Military.Horizontal.TScale',
                 background=[('active', '#0a0a0a')],
                 troughcolor=[('active', '#505050')])
        
        # 🆕 Radiobutton 스타일
        style.configure('Military.TRadiobutton',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       font=('Consolas', 9))
        style.map('Military.TRadiobutton',
                 background=[('active', '#0a0a0a')],
                 foreground=[('active', '#66ff66')])
        
        # 🆕 Checkbutton 스타일
        style.configure('Military.TCheckbutton',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       font=('Consolas', 9))
        style.map('Military.TCheckbutton',
                 background=[('active', '#0a0a0a')],
                 foreground=[('active', '#66ff66')])
        
        # Additional status label styles
        style.configure('Success.TLabel',
                       background='#0a0a0a',
                       foreground='#00ff00',
                       font=('Consolas', 9, 'bold'))
        
        style.configure('Warning.TLabel',
                       background='#0a0a0a',
                       foreground='#ff6600',
                       font=('Consolas', 9, 'bold'))
        
        style.configure('Info.TLabel',
                       background='#0a0a0a',
                       foreground='#0066ff',
                       font=('Consolas', 9, 'bold'))
        
        # 메인 프레임
        main_frame = ttk.Frame(self.control_window, padding="15")
        main_frame.configure(style='Military.TFrame')
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure main frame style
        style.configure('Military.TFrame', background='#0a0a0a')
        
        # Configure button frame style
        style.configure('ButtonFrame.TFrame', background='#0a0a0a')
        
        # 제어 패널
        self.create_controls(main_frame)
        
        # 상태 패널
        self.create_status_panel(main_frame)
        
        # 로그 패널
        self.create_log_panel(main_frame)
        
        # 그리드 설정
        self.control_window.grid_rowconfigure(0, weight=1)
        self.control_window.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # ⚡ 교착 방지: 모든 위젯 생성 후 이벤트 처리
        self.control_window.update_idletasks()
        
    def create_controls(self, parent):
        """제어 버튼들 생성"""
        control_frame = ttk.LabelFrame(parent, text="⚡ SIMULATION CONTROL", 
                                     padding="15", style='Military.TLabelframe')
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0,15))
        
        # 첫 번째 행: 시나리오 선택
        ttk.Label(control_frame, text="시나리오:", style='Military.TLabel').grid(row=0, column=0, sticky="w", pady=5)
        
        # 시나리오 목록 가져오기
        try:
            from config_mip import ScenarioManager
            scenario_list = ScenarioManager.get_scenario_list()
            scenario_values = [f"{key}: {desc}" for key, desc in scenario_list.items()]
            scenario_keys = list(scenario_list.keys())
        except:
            scenario_values = ["BASELINE_15: 기본 시나리오"]
            scenario_keys = ["BASELINE_15"]
        
        scenario_combo = ttk.Combobox(control_frame, textvariable=self.scenario_var,
                                     values=scenario_keys, state="readonly", width=25,
                                     style='Military.TCombobox')
        scenario_combo.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        scenario_combo.bind('<<ComboboxSelected>>', self.on_scenario_change)
        
        # 두 번째 행: 목적함수, 속도, 최대 시간
        ttk.Label(control_frame, text="목적함수:", style='Military.TLabel').grid(row=1, column=0, sticky="w")
        objective_combo = ttk.Combobox(control_frame, textvariable=self.objective_var,
                                      values=list(OBJECTIVES.keys()), state="readonly", width=15,
                                      style='Military.TCombobox')
        objective_combo.grid(row=1, column=1, padx=5)
        objective_combo.bind('<<ComboboxSelected>>', self.on_objective_change)
        
        # 시뮬레이션 속도
        ttk.Label(control_frame, text="속도:", style='Military.TLabel').grid(row=1, column=2, padx=(20,0))
        speed_scale = ttk.Scale(control_frame, from_=0.1, to=5.0, 
                               variable=self.speed_var, orient="horizontal", length=120,
                               style='Military.Horizontal.TScale')
        speed_scale.grid(row=1, column=3, padx=5)
        speed_label = ttk.Label(control_frame, text="1.0x", style='Status.TLabel')
        speed_label.grid(row=1, column=4, padx=5)
        
        def update_speed_label(*args):
            speed_label.config(text=f"{self.speed_var.get():.1f}x")
        self.speed_var.trace('w', update_speed_label)
        
        # 최대 시간
        ttk.Label(control_frame, text="최대 시간(초):", style='Military.TLabel').grid(row=1, column=5, padx=(20,0))
        ttk.Spinbox(control_frame, from_=300, to=3000, 
                   textvariable=self.max_duration_var, width=8,
                   style='Military.TSpinbox').grid(row=1, column=6, padx=5)
        
        # 🆕 세 번째 행: 알고리즘 선택 및 Warm-start 옵션
        ttk.Label(control_frame, text="알고리즘:", style='Military.TLabel').grid(row=2, column=0, sticky="w", pady=5)
        
        algo_frame = ttk.Frame(control_frame, style='ButtonFrame.TFrame')
        algo_frame.grid(row=2, column=1, columnspan=3, sticky="w", padx=5)
        
        ttk.Radiobutton(algo_frame, text="MIP (최적)", 
                       variable=self.algorithm_var, value="MIP",
                       command=self.on_algorithm_change,
                       style='Military.TRadiobutton').pack(side="left", padx=5)
        ttk.Radiobutton(algo_frame, text="Greedy (빠름)", 
                       variable=self.algorithm_var, value="Greedy",
                       command=self.on_algorithm_change,
                       style='Military.TRadiobutton').pack(side="left", padx=5)
        ttk.Radiobutton(algo_frame, text="GA (균형)", 
                       variable=self.algorithm_var, value="GA",
                       command=self.on_algorithm_change,
                       style='Military.TRadiobutton').pack(side="left", padx=5)
        
        # Warm-start 체크박스
        self.warmstart_check = ttk.Checkbutton(control_frame, text="Warm-start 활성화", 
                                               variable=self.warmstart_enabled_var,
                                               command=self.on_warmstart_toggle,
                                               style='Military.TCheckbutton')
        self.warmstart_check.grid(row=2, column=4, columnspan=2, sticky="w", padx=(20,0))
        
        # 로그 수집 체크박스
        ttk.Checkbutton(control_frame, text="로그 자동 저장",
                       variable=self.logging_enabled_var,
                       command=self.on_logging_toggle,
                       style='Military.TCheckbutton').grid(row=2, column=6, sticky="w", padx=5)

        # 🆕 Phase 2.3: Visualization backend selector (row 3)
        ttk.Label(control_frame, text="Display:", style='Military.TLabel').grid(row=3, column=0, sticky="w", pady=5)

        # Backend selection combobox
        viz_combo = ttk.Combobox(control_frame, textvariable=self.viz_backend_var,
                                values=["matplotlib", "pyqtgraph"] if PYQTGRAPH_AVAILABLE else ["matplotlib"],
                                state="readonly", width=15,
                                style='Military.TCombobox')
        viz_combo.grid(row=3, column=1, padx=5, pady=5)
        viz_combo.bind('<<ComboboxSelected>>', self.on_viz_backend_change)

        # Backend info label
        backend_info_text = "PyQtGraph: <2ms/frame (FAST)" if PYQTGRAPH_AVAILABLE else "PyQtGraph not available (optional)"
        backend_info = ttk.Label(control_frame,
                               text=backend_info_text,
                               style='Military.TLabel',
                               foreground='#00ff00' if PYQTGRAPH_AVAILABLE else '#cccccc')
        backend_info.grid(row=3, column=2, columnspan=2, sticky="w", padx=5)

        # 제어 버튼들
        button_frame = ttk.Frame(control_frame, style='ButtonFrame.TFrame')
        button_frame.grid(row=4, column=0, columnspan=7, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="▶ 시작", command=self.start_simulation,
                                   style='Military.TButton')
        self.start_btn.pack(side="left", padx=8)
        
        self.pause_btn = ttk.Button(button_frame, text="⏸ 일시정지", command=self.pause_simulation, 
                                   state="disabled", style='Military.TButton')
        self.pause_btn.pack(side="left", padx=8)
        
        self.stop_btn = ttk.Button(button_frame, text="⏹ 정지", command=self.stop_simulation, 
                                  state="disabled", style='Military.TButton')
        self.stop_btn.pack(side="left", padx=8)
        
        self.reset_btn = ttk.Button(button_frame, text="[RESET] 리셋", command=self.reset_simulation,
                                   style='Military.TButton')
        self.reset_btn.pack(side="left", padx=8)
        
    def create_status_panel(self, parent):
        """상태 패널 생성"""
        status_frame = ttk.LabelFrame(parent, text="[STATUS] REAL-TIME STATUS", 
                                    padding="15", style='Military.TLabelframe')
        status_frame.grid(row=1, column=0, sticky="ew", pady=(0,15))
        
        # 상태 변수들
        self.time_var = tk.StringVar(value="T=0")
        self.active_var = tk.StringVar(value="활성 위협: 0")
        self.intercepted_var = tk.StringVar(value="요격 성공: 0")
        self.missed_var = tk.StringVar(value="요격 실패: 0")
        self.success_rate_var = tk.StringVar(value="성공률: 0%")
        self.objective_val_var = tk.StringVar(value="목적함수: -")
        self.warmstart_var = tk.StringVar(value="Warm-start: OFF")  # Warm-start 상태
        self.solver_time_var = tk.StringVar(value="솔버 시간: -")  # 🆕 솔버 시간
        
        # 상태 표시
        status_labels = [
            ("현재 시간:", self.time_var),
            ("활성 위협:", self.active_var),
            ("요격 성공:", self.intercepted_var),
            ("요격 실패:", self.missed_var),
            ("성공률:", self.success_rate_var),
            ("목적함수 값:", self.objective_val_var),
            ("Warm-start:", self.warmstart_var),  # 🆕
            ("솔버 시간:", self.solver_time_var)   # 🆕
        ]
        
        for i, (label, var) in enumerate(status_labels):
            # Add LED-style indicators
            led_frame = ttk.Frame(status_frame, style='Military.TFrame')
            led_frame.grid(row=i//3, column=(i%3)*3, sticky="w", padx=(0,5), pady=3)
            
            # LED indicator (colored circle)
            led_color = '#00ff00' if 'T=' in var.get() or '성공' in label else '#ff6600' if '실패' in label else '#0066ff'
            led_canvas = tk.Canvas(led_frame, width=12, height=12, bg='#0a0a0a', highlightthickness=0)
            led_canvas.pack(side='left')
            led_canvas.create_oval(2, 2, 10, 10, fill=led_color, outline='#ffffff', width=1)
            
            ttk.Label(status_frame, text=label, style='Military.TLabel').grid(row=i//3, column=(i%3)*3+1, sticky="w", padx=5, pady=3)
            
            # Color-coded status values
            status_style = 'Status.TLabel'
            if '성공' in label:
                status_style = 'Success.TLabel'
            elif '실패' in label:
                status_style = 'Warning.TLabel'
            elif '목적함수' in label:
                status_style = 'Info.TLabel'
                
            ttk.Label(status_frame, textvariable=var, style=status_style, width=15).grid(row=i//3, column=(i%3)*3+2, sticky="w", padx=5, pady=3)
        
    def create_log_panel(self, parent):
        """로그 패널 생성"""
        log_frame = ttk.LabelFrame(parent, text="📜 EVENT LOG", 
                                 padding="15", style='Military.TLabelframe')
        log_frame.grid(row=2, column=0, sticky="nsew")
        
        # 로그 텍스트
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9),
                                                bg='#0f0f0f', fg='#00ff00',
                                                insertbackground='#00ff00',
                                                selectbackground='#2a4a2a',
                                                selectforeground='#ffffff')
        self.log_text.pack(fill="both", expand=True)
        
        # Configure log text tags for different message types
        self.log_text.tag_configure('INFO', foreground='#00ff00')
        self.log_text.tag_configure('WARNING', foreground='#ff6600')
        self.log_text.tag_configure('ERROR', foreground='#ff3333')
        self.log_text.tag_configure('SUCCESS', foreground='#66ff66')
        self.log_text.tag_configure('ASSIGN', foreground='#0099ff')
        self.log_text.tag_configure('INTERCEPT', foreground='#ff9900')
        self.log_text.tag_configure('MISS', foreground='#ff6666')
        self.log_text.tag_configure('LAUNCH', foreground='#ffff00')
        self.log_text.tag_configure('TRAJECTORY', foreground='#cc99ff')
        
        # 로그 제어
        log_control = ttk.Frame(log_frame, style='ButtonFrame.TFrame')
        log_control.pack(fill="x", pady=(8,0))
        
        ttk.Button(log_control, text="🗑 로그 지우기", command=self.clear_log,
                  style='Military.TButton').pack(side="left")
        ttk.Button(log_control, text="💾 로그 저장", command=self.save_log,
                  style='Military.TButton').pack(side="left", padx=8)
        
    def log_message(self, message, level="INFO"):
        """로그 메시지 추가 (Thread-safe: 비메인 스레드에서 호출 시 main thread에 위임)"""
        timestamp = time.strftime("%H:%M:%S")

        # 🆕 DEBUG 레벨 메시지는 기본적으로 숨김
        if level == "DEBUG" and '[DEBUG]' in message:
            return  # DEBUG 메시지 필터링

        # 비메인 스레드에서 호출 시 main thread로 위임 (Tkinter thread safety)
        try:
            if threading.current_thread() is not threading.main_thread():
                self.control_window.after(0, lambda: self._log_message_impl(timestamp, message, level))
                return
        except RuntimeError:
            pass

        self._log_message_impl(timestamp, message, level)

    def _log_message_impl(self, timestamp, message, level):
        """로그 메시지 실제 삽입 (main thread에서만 호출)"""
        # Determine message type and apply appropriate tag
        tag = level
        if 'ASSIGN' in message.upper():
            tag = 'ASSIGN'
        elif 'INTERCEPT' in message.upper():
            tag = 'INTERCEPT'
        elif 'MISS' in message.upper():
            tag = 'MISS'
        elif 'LAUNCH' in message.upper():
            tag = 'LAUNCH'
        elif 'TRAJECTORY' in message.upper():
            tag = 'TRAJECTORY'
        elif 'SUCCESS' in message.upper() or '성공' in message:
            tag = 'SUCCESS'
        elif 'WARNING' in message.upper() or '경고' in message:
            tag = 'WARNING'
        elif 'ERROR' in message.upper() or '오류' in message:
            tag = 'ERROR'

        try:
            # Insert message with timestamp and apply color tag
            start_pos = self.log_text.index(tk.END)
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            end_pos = self.log_text.index(tk.END)

            # Apply color tag to the entire line
            self.log_text.tag_add(tag, start_pos, end_pos)
            self.log_text.see(tk.END)

            # 줄 수 제한
            lines = int(self.log_text.index(tk.END).split('.')[0])
            if lines > 1000:
                self.log_text.delete("1.0", "100.0")
        except tk.TclError:
            pass  # 위젯이 이미 파괴된 경우 무시
    
    def update_status(self, tracker):
        """상태 업데이트 (Thread-safe)"""
        # 상태값을 먼저 캡처 (스레드 안전)
        time_step = tracker.current_time_step
        active = tracker.stats['active']
        intercepted = tracker.stats['intercepted']
        missed = tracker.stats['missed']
        deviated_count = tracker.stats.get('deviated', 0)
        total = tracker.stats['total']
        obj_val = tracker.last_objective_value

        def _update():
            try:
                self.time_var.set(f"T={time_step}")
                self.active_var.set(f"활성 위협: {active}")
                self.intercepted_var.set(f"요격 성공: {intercepted}")
                self.missed_var.set(f"요격 실패: {missed}")

                actual_threats = total - deviated_count
                if actual_threats > 0:
                    success_rate = (intercepted / actual_threats) * 100
                    self.success_rate_var.set(f"성공률: {success_rate:.1f}%")

                if obj_val is not None:
                    self.objective_val_var.set(f"목적함수: {obj_val:.2f}")
            except tk.TclError:
                pass

        # 비메인 스레드에서 호출 시 main thread로 위임
        try:
            if threading.current_thread() is not threading.main_thread():
                self.control_window.after(0, _update)
                return
        except RuntimeError:
            pass

        _update()
    
    def start_simulation(self):
        """시뮬레이션 시작"""
        if self.running:
            return
            
        self.running = True
        self.paused = False
        
        # 실행 시간 측정 시작
        self.sim_start_time = time.time()
        
        # 버튼 상태 변경
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
        self.stop_btn.config(state="normal")
        
        # 목적함수 업데이트
        self.tracker.objective = self.objective_var.get()
        
        self.log_message(f"시뮬레이션 시작 - {OBJECTIVES[self.tracker.objective]}", "SUCCESS")
        self.log_message(f"시나리오: {self.scenario_var.get()}, 배속: {self.speed_var.get():.1f}x", "INFO")
        
        # 시뮬레이션 스레드 시작
        self.sim_thread = threading.Thread(target=self.run_simulation_thread, daemon=True)
        self.sim_thread.start()
    
    def run_simulation_thread(self):
        """시뮬레이션 실행 스레드"""
        try:
            # 🆕 시뮬레이션 시작 로그 (제어 패널이 준비된 후)
            self.log_message("[INFO] === SIMULATION START (T=0) ===", "INFO")
            
            # 시나리오 시작
            self.tracker.start_scenario()
            
            # 🆕 초기 정보 로그
            self.log_message(f"[INFO] Scenario: {self.tracker.scenario_data.get('name', 'Unknown')}", "INFO")
            self.log_message(f"[INFO] Batteries: {len(self.tracker.batteries)}, Assets: {len(self.tracker.assets)}", "INFO")
            self.log_message(f"[INFO] Total Threats: {len(self.tracker.missiles)} registered", "INFO")
            
            prev_stats = self.tracker.stats.copy()
            
            while self.running:
                if not self.paused:
                    # 시뮬레이션 상태 변경은 lock으로 보호 (디스플레이 스레드와 경쟁 방지)
                    with self.tracker._sim_lock:
                        # 1단계: 시뮬레이션 상태 업데이트 (미사일 이동, 충돌 처리, 이벤트)
                        self.tracker.update_simulation()

                        # 2단계: 실시간 DWTA 최적화 (최신 위치/상태 기반)
                        self.tracker.run_realtime_dwta()

                    # 새로운 이벤트 로깅
                    self.check_events(prev_stats, self.tracker.stats)
                    prev_stats = self.tracker.stats.copy()

                    # 종료 조건 확인
                    if self.should_terminate():
                        break

                # 속도 조절 (더 짧은 sleep으로 UI 응답성 향상)
                time.sleep(0.05 / self.speed_var.get())
                
        except Exception as e:
            self.log_message(f"시뮬레이션 오류: {e}", "ERROR")
        finally:
            self.control_window.after(0, self.simulation_finished)
    
    def check_events(self, prev_stats, current_stats):
        """이벤트 확인 및 로깅"""
        if current_stats['intercepted'] > prev_stats['intercepted']:
            self.control_window.after(0, lambda: self.log_message("요격 성공!", "INTERCEPT"))
        
        if current_stats['missed'] > prev_stats['missed']:
            self.control_window.after(0, lambda: self.log_message("요격 실패", "WARNING"))
            
        if current_stats['active'] > prev_stats['active']:
            new_threats = current_stats['active'] - prev_stats['active']
            self.control_window.after(0, lambda: self.log_message(f"{new_threats}개 새로운 위협 발견", "INFO"))
    
    def should_terminate(self):
        """종료 조건 확인"""
        if self.tracker.current_time_step >= self.max_duration_var.get():
            return True
        
        all_threats_launched = all(missile['launch_time'] <= self.tracker.current_time_step 
                                 for missile in self.tracker.missiles.values())
        all_threats_resolved = len(self.tracker.kill_results) == self.tracker.stats['total']
        no_active_threats = self.tracker.stats['active'] == 0
        
        return all_threats_launched and all_threats_resolved and no_active_threats
    
    def pause_simulation(self):
        """일시정지/재개"""
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.config(text="재개")
            self.log_message("시뮬레이션 일시정지", "WARNING")
        else:
            self.pause_btn.config(text="일시정지")
            self.log_message("시뮬레이션 재개", "SUCCESS")
    
    def stop_simulation(self):
        """시뮬레이션 정지"""
        self.running = False
        self.paused = False
        
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="일시정지")
        self.stop_btn.config(state="disabled")
        
        self.log_message("시뮬레이션 정지", "WARNING")
    
    def reset_simulation(self):
        """시뮬레이션 리셋"""
        self.stop_simulation()
        
        # 트래커 상태 초기화
        if hasattr(self.tracker, 'missiles'):
            self.tracker.missiles.clear()
            self.tracker.kill_results.clear()
            self.tracker.primary_assignments.clear()
            self.tracker.current_time_step = 0
            self.tracker.stats = {'intercepted': 0, 'missed': 0, 'active': 0, 'total': 0, 'retargeted': 0, 'tracked_misses': []}
        
        # 상태 초기화
        self.time_var.set("T=0")
        self.active_var.set("활성 위협: 0")
        self.intercepted_var.set("요격 성공: 0")
        self.missed_var.set("요격 실패: 0")
        self.success_rate_var.set("성공률: 0%")
        self.objective_val_var.set("목적함수: -")
        
        # 🆕 전략 뷰 및 목적함수 뷰 초기화
        if hasattr(self.tracker, 'fig') and self.tracker.fig:
            try:
                # 차트 초기화
                if hasattr(self.tracker, 'ax_main'):
                    self.tracker.ax_main.clear()
                if hasattr(self.tracker, 'ax_analysis'):
                    self.tracker.ax_analysis.clear()
                
                # 축 재초기화
                if hasattr(self.tracker, '_initialize_axes'):
                    self.tracker._initialize_axes()
                
                # 캔버스 업데이트
                self.tracker.fig.canvas.draw_idle()
            except Exception as e:
                print(f"차트 리셋 오류: {e}")
        
        self.log_message("시뮬레이션 리셋", "INFO")
    
    def simulation_finished(self):
        """시뮬레이션 완료"""
        self.running = False
        
        # 🆕 CRITICAL: Tracker의 finalize_simulation 호출 (메트릭 저장)
        if hasattr(self.tracker, 'finalize_simulation'):
            self.tracker.finalize_simulation()
        
        # 실행 시간 계산 및 로그 기록
        if self.sim_start_time is not None:
            self.sim_elapsed_time = time.time() - self.sim_start_time
            deviated = self.tracker.stats.get('deviated', 0)
            actual_threats = self.tracker.stats['total'] - deviated
            
            self.log_message(f"[INFO] === SIMULATION COMPLETE ===", "SUCCESS")
            self.log_message(f"[INFO] Scenario: {self.scenario_var.get()}", "INFO")
            self.log_message(f"[INFO] Total Threats: {self.tracker.stats['total']} ({actual_threats} actual, {deviated} deviated)", "INFO")
            self.log_message(f"[INFO] Speed: {self.speed_var.get():.1f}x", "INFO")
            self.log_message(f"[INFO] Simulation Time: {self.tracker.current_time_step}s", "INFO")
            self.log_message(f"[INFO] Real Time: {self.sim_elapsed_time:.2f}s", "INFO")
            self.log_message(f"[INFO] Time Compression: {self.tracker.current_time_step / self.sim_elapsed_time:.2f}x", "INFO")
        
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="일시정지")
        self.stop_btn.config(state="disabled")
        
        # 결과 표시
        stats = self.tracker.stats
        total = stats['total']
        deviated = stats.get('deviated', 0)
        actual_threats = total - deviated
        success_rate = min((stats['intercepted'] / total * 100) if total > 0 else 0, 100.0)

        result_msg = f"""시뮬레이션 완료!

총 위협: {total}발
궤적 이탈: {deviated}발
실제 위협: {actual_threats}발

요격 성공: {stats['intercepted']}발
요격 실패: {stats['missed']}발
성공률: {success_rate:.1f}%

실제 실행 시간: {self.sim_elapsed_time:.2f}초
시뮬레이션 시간: {self.tracker.current_time_step}초
배속: {self.speed_var.get():.1f}x"""
        
        messagebox.showinfo("시뮬레이션 완료", result_msg)
        self.log_message("시뮬레이션 완료", "SUCCESS")
    
    def on_objective_change(self, event=None):
        """목적함수 변경"""
        if hasattr(self.tracker, 'objective'):
            self.tracker.objective = self.objective_var.get()
            self.log_message(f"목적함수 변경: {OBJECTIVES[self.tracker.objective]}", "INFO")
    
    def on_algorithm_change(self):
        """🆕 알고리즘 변경"""
        algorithm = self.algorithm_var.get()
        if hasattr(self.tracker, 'current_algorithm'):
            self.tracker.current_algorithm = algorithm
            self.log_message(f"알고리즘 변경: {algorithm}", "INFO")
            
            # MIP가 아닌 경우 Warm-start 비활성화
            if algorithm != "MIP":
                self.warmstart_enabled_var.set(False)
                self.warmstart_check.config(state="disabled")
                self.log_message("Warm-start는 MIP 알고리즘에서만 사용 가능합니다", "WARNING")
            else:
                self.warmstart_check.config(state="normal")
    
    def on_warmstart_toggle(self):
        """🆕 Warm-start 토글"""
        enabled = self.warmstart_enabled_var.get()
        
        # MIP Optimizer 인스턴스 초기화 여부 결정
        if hasattr(self.tracker, 'mip_optimizer_instance') and not enabled:
            # Warm-start 비활성화 시 기존 인스턴스 제거
            delattr(self.tracker, 'mip_optimizer_instance')
            self.log_message("Warm-start 비활성화 - MIP 인스턴스 초기화됨", "INFO")
        elif enabled:
            self.log_message("Warm-start 활성화", "SUCCESS")
        
        # 상태 업데이트
        self.warmstart_var.set(f"Warm-start: {'ON' if enabled else 'OFF'}")
    
    def on_logging_toggle(self):
        """🆕 로그 수집 토글"""
        enabled = self.logging_enabled_var.get()
        if hasattr(self.tracker, 'enable_logging'):
            self.tracker.enable_logging = enabled
            status = "활성화" if enabled else "비활성화"
            self.log_message(f"로그 자동 저장 {status}", "INFO")

    def on_viz_backend_change(self, event=None):
        """🆕 Phase 2.3: Visualization backend change handler"""
        new_backend = self.viz_backend_var.get()

        if self.running:
            messagebox.showwarning("경고", "시뮬레이션 실행 중에는 디스플레이 모드를 변경할 수 없습니다.")
            # Restore previous value
            current = "pyqtgraph" if (hasattr(self.tracker, 'use_pyqtgraph') and self.tracker.use_pyqtgraph) else "matplotlib"
            self.viz_backend_var.set(current)
            return

        # Require restart for backend change
        if messagebox.askyesno("디스플레이 모드 변경",
                             f"디스플레이를 '{new_backend}'로 변경하시겠습니까?\n"
                             f"변경 사항은 다음 시뮬레이션 시작 시 적용됩니다."):
            # Store preference (will be applied on next simulation start)
            self.tracker.use_pyqtgraph = (new_backend == "pyqtgraph" and PYQTGRAPH_AVAILABLE)
            status_msg = f"디스플레이 모드: {new_backend} (다음 시작 시 적용)"
            self.log_message(status_msg, "SUCCESS")

            if new_backend == "pyqtgraph" and PYQTGRAPH_AVAILABLE:
                self.log_message("🚀 PyQtGraph 모드: 고성능 렌더링 (<2ms/frame)", "INFO")
            else:
                self.log_message("📊 Matplotlib 모드: 기본 렌더링", "INFO")
        else:
            # Restore previous value
            current = "pyqtgraph" if (hasattr(self.tracker, 'use_pyqtgraph') and self.tracker.use_pyqtgraph) else "matplotlib"
            self.viz_backend_var.set(current)

    def on_scenario_change(self, event=None):
        """시나리오 변경"""
        if self.running:
            messagebox.showwarning("경고", "시뮬레이션 실행 중에는 시나리오를 변경할 수 없습니다.")
            return
        
        new_scenario = self.scenario_var.get()
        
        # 시나리오 변경 확인
        if messagebox.askyesno("시나리오 변경", 
                               f"시나리오를 '{new_scenario}'로 변경하시겠습니까?\n현재 시뮬레이션 상태가 초기화됩니다."):
            try:
                # config 업데이트
                self.tracker.config.scenario_type = new_scenario
                
                # 시나리오 재로드
                self.tracker._load_scenario()
                
                # 트래커 상태 초기화
                self.tracker.missiles.clear()
                self.tracker.kill_results.clear()
                self.tracker.primary_assignments.clear()
                self.tracker.current_time_step = 0
                self.tracker.stats = {'intercepted': 0, 'missed': 0, 'active': 0, 'total': 0, 'retargeted': 0, 'tracked_misses': []}
                
                # 상태 초기화
                self.time_var.set("T=0")
                self.active_var.set("활성 위협: 0")
                self.intercepted_var.set("요격 성공: 0")
                self.missed_var.set("요격 실패: 0")
                self.success_rate_var.set("성공률: 0%")
                self.objective_val_var.set("목적함수: -")
                
                # 시나리오 정보 로깅
                from config_mip import ScenarioManager
                scenario_list = ScenarioManager.get_scenario_list()
                scenario_desc = scenario_list.get(new_scenario, "Unknown")
                threat_count = len(self.tracker.initial_threats_config)
                
                self.log_message(f"시나리오 변경: {scenario_desc}", "SUCCESS")
                self.log_message(f"위협 미사일 수: {threat_count}발", "INFO")
                
            except Exception as e:
                messagebox.showerror("오류", f"시나리오 변경 실패: {e}")
                self.log_message(f"시나리오 변경 오류: {e}", "ERROR")
        else:
            # 취소 시 원래 값으로 복원
            self.scenario_var.set(self.tracker.config.scenario_type)
    
    def clear_log(self):
        """로그 지우기"""
        self.log_text.delete("1.0", tk.END)
    
    def save_log(self):
        """로그 저장"""
        try:
            from tkinter import filedialog
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
            )
            if filename:
                content = self.log_text.get("1.0", tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("성공", f"로그가 저장되었습니다: {filename}")
        except Exception as e:
            messagebox.showerror("오류", f"로그 저장 실패: {e}")
    
    def on_closing(self):
        """창 닫기"""
        if self.running:
            if messagebox.askokcancel("종료", "시뮬레이션이 실행 중입니다. 종료하시겠습니까?"):
                self.stop_simulation()
                self.control_window.destroy()
        else:
            self.control_window.destroy()

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

        # Initialize configuration and load scenario
        self.config = mip_config
        #mip 사용으로 _load_scenario 실행 
        self._load_scenario()
        #config_mip.py에서 데이터 추출:시나리오데이터, 자산 데이터, 포대 데이터, 초기 위협 정보, 교전 확률 매트릭스
        
        # Simulation State
        self.current_time_step = 0
        self.missiles = {} #미사일 객체 저장, 미사일 ID: 미사일 객체
        
        # Optimization Tracking
        # 🔧 OPTIMIZED: 하이브리드 자료구조로 교체 (딕셔너리 → 양방향 인덱스 + 비트마스크)
        # 성능: 탐색 O(1), 메모리 6배 절감 - 🆕 300 위협 지원
        self.primary_assignments = OptimizedAssignmentManager(max_threats=300, max_batteries=20)
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
        
        # GUI 컴포넌트
        self.control_panel = None
        self.text_mode = self.headless  # headless 모드 = text 모드
        self.pyqtgraph_display = None  # 🆕 PyQtGraph display instance

        # Visualization Setup
        # Headless 모드에서는 GUI 완전히 비활성화
        if self.headless:
            self.fig = None
            self.control_panel = None
            self.text_mode = True
            print("Headless 모드: GUI 없이 실행합니다.")
        elif self.use_pyqtgraph and PYQTGRAPH_AVAILABLE:
            # 🆕 Phase 2: PyQtGraph visualization (high-performance mode)
            try:
                print("[OK] Initializing PyQtGraph high-performance visualization...")
                self.pyqtgraph_display = PyQtGraphDisplay(self)
                self.fig = None  # No matplotlib figure in PyQtGraph mode
                print("[OK] PyQtGraph display ready (target: <2ms per frame)")
            except Exception as e:
                print(f"[ERROR] PyQtGraph initialization failed: {e}")
                print("   Falling back to matplotlib...")
                self.use_pyqtgraph = False
                self._setup_gui_visualization()
        elif GUI_AVAILABLE:
            try:
                self._setup_gui_visualization()
            except Exception as e:
                print(f"GUI 초기화 실패: {e}")
                self.fig = None
                self.control_panel = None
                print("GUI를 사용할 수 없어 시각화 없이 실행합니다.")
        else:
            self.fig = None
            self.control_panel = None
            print("GUI를 사용할 수 없어 시각화 없이 실행합니다.")

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

    def _setup_gui_visualization(self):
        """GUI 시각화 설정 (교착 상태 방지 개선)"""
        max_retries = 3
        retry_count = 0
        
        # 초기화
        self.fig = None
        self.control_panel = None
        
        while retry_count < max_retries:
            try:
                print("[OK] GUI 레이아웃 버전: v4.0 - 전술 디스플레이(왼쪽) 75%, 목적함수(오른쪽) 25% (3:1 비율)")
                
                # ⚡ 교착 방지: matplotlib 백엔드 명시적 초기화
                import matplotlib
                matplotlib.use('TkAgg', force=True)
                
                plt.ion()
                plt.style.use('dark_background')
                
                # Figure 생성
                self.fig = plt.figure(figsize=(20, 8))
                
                # 수동으로 subplot 위치 지정 (3:1 비율로 왼쪽이 더 크게)
                # [left, bottom, width, height] 형식
                # 계산: 전체 가용 폭 = 1.0 - 0.04(left_margin) - 0.03(gap) - 0.03(right_margin) = 0.90
                # 좌측 = 0.90 * 0.75 = 0.675, 우측 = 0.90 * 0.25 = 0.225
                self.ax_main = self.fig.add_axes([0.04, 0.08, 0.675, 0.85])      # 전술 디스플레이(왼쪽): 67.5% 폭
                self.ax_analysis = self.fig.add_axes([0.745, 0.08, 0.225, 0.85])  # 목적함수(오른쪽): 22.5% 폭
                
                print(f"[OK] Tactical Display (LEFT): left=0.04, width=0.675 (75%)")
                print(f"[OK] Objective View (RIGHT): left=0.745, width=0.225 (25%)")
                print(f"[OK] Ratio verification: 0.675 / 0.225 = {0.675/0.225:.2f}:1")
                
                #self.fig.suptitle(f'Real-time DWTA Analysis (Objective: {self.objective})', fontsize=16, color='white')
                
                # 메인 창을 GUI 모드로 설정
                self.fig.canvas.manager.set_window_title("DWTA 실시간 시뮬레이션")
                
                self._initialize_axes()
                
                # 제어 패널 생성 (headless 모드가 아닌 경우에만)
                if GUI_AVAILABLE and not self.headless:
                    # ⚡ 교착 방지: matplotlib 이벤트 큐 정리
                    self.fig.canvas.draw_idle()
                    self.fig.canvas.flush_events()
                    
                    self.control_panel = ControlPanel(self)
                    self.control_panel.create_control_window()
                else:
                    self.control_panel = None
                
                # 성공 시 루프 탈출
                print("[OK] GUI 초기화 성공")
                break
                    
            except Exception as e:
                retry_count += 1
                print(f"[WARN] GUI 초기화 실패 (시도 {retry_count}/{max_retries}): {e}")
                
                # 정리 작업
                if hasattr(self, 'fig') and self.fig:
                    plt.close(self.fig)
                    self.fig = None
                if hasattr(self, 'control_panel') and self.control_panel:
                    self.control_panel = None
                
                if retry_count >= max_retries:
                    print("❌ GUI 초기화 최대 재시도 횟수 초과. Headless 모드로 전환합니다.")
                    self.headless = True
                    self.text_mode = True
                    self.fig = None
                    self.control_panel = None
                    return
                
                # 재시도 전 대기
                import time
                time.sleep(0.5)
        
        # 최종 실패 처리 (루프 밖)
        if retry_count >= max_retries:
            return
        
        # 원래 예외 처리 (성공 시에는 실행되지 않음)
        try:
            pass
        except Exception as e:
            print(f"GUI 시각화 설정 실패: {e}")
            self.fig = None
    
    # _setup_visualization() 메서드 제거됨 - GUI 전용 버전에서는 필요 없음

    def _initialize_axes(self):
        """Enhanced axes initialization with better scaling and visibility."""
        if not self.fig: return
        
        # Main tactical display with improved bounds
        self.ax_main.set_facecolor('black')
        self.ax_main.set_title('Tactical Display', fontsize=14, color='white')
        # Further expanded bounds to ensure all elements are visible
        self.ax_main.set_xlim(-90, 120) 
        self.ax_main.set_ylim(-130, 270)
        # 'auto' aspect ratio to use full allocated width (0.675) without shrinking
        self.ax_main.set_aspect('auto')
        self.ax_main.grid(True, color='cyan', alpha=0.3, linestyle=':')
        self.ax_main.tick_params(colors='white', labelsize=10)
        self.ax_main.set_xlabel('X Position (km)', color='white', fontsize=11)
        self.ax_main.set_ylabel('Y Position (km)', color='white', fontsize=11)
        
        # Analysis panel
        if hasattr(self, 'ax_analysis'):
            self.ax_analysis.set_facecolor('#111111')
            self.ax_analysis.set_title('Objective Function Analysis', fontsize=12, color='white')
            self.ax_analysis.tick_params(colors='white', labelsize=9)
        
        # History panel (if exists)
        if hasattr(self, 'ax_history'):
            self.ax_history.set_facecolor('#111111')
            self.ax_history.set_title('Event Log', fontsize=12, color='white')
            self.ax_history.axis('off')

    # 기존 메서드들 유지 (원본 코드와 동일)
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
        self.current_time_step += 5
        
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
        
        # GUI 상태 업데이트
        if self.control_panel:
            self.control_panel.update_status(self)

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
            if random.random() < missile.get('retarget_probability', 0.002):
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
                
                base_Pk = 0.85  # LSAM 기본 요격 확률
                
                salvo_results = []
                for shot_num in range(missiles_to_fire):
                    Pk_shot = self.uncertainty_model.sample_intercept_probability(base_Pk)
                    salvo_results.append((shot_num + 1, Pk_shot))
                    P_survival *= (1 - Pk_shot)
                
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
                    
                    base_Pk = 0.78  # MSAM 기본 요격 확률
                    
                    salvo_results = []
                    for shot_num in range(missiles_to_fire):
                        Pk_shot = self.uncertainty_model.sample_intercept_probability(base_Pk)
                        salvo_results.append((shot_num + 1, Pk_shot))
                        P_survival *= (1 - Pk_shot)
                    
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

        # 🆕 Deterministic Outcome (Stage 2 제거)
        # 기댓값 기반 판정: 불확실성은 Stage 1(Beta 분포)에서만 적용
        # 최적화-실행 편차 최소화 및 알고리즘 비교 공정성 확보
        if P_kill >= 0.5 and missiles_fired > 0:  # 50% 이상 확률이면 성공으로 판정
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
            
            # 불확실성 모델링: 매 최적화마다 확률 샘플링
            # Clean Slate: engagement_matrix.is_feasible() 대신 거리 기반 판단
            sampled_probs = {}
            for threat in threats_opt:
                threat_id = getattr(threat, 'id', '')
                threat_pos = getattr(threat, 'current_position', (0, 0, 0))

                can_engage_lsam = False
                can_engage_msam = False

                for battery in self.batteries:
                    if battery.get('available_missiles', 0) <= 0:
                        continue
                    bpos = battery.get('position', (0, 0))
                    dx = threat_pos[0] - bpos[0]
                    dy = threat_pos[1] - bpos[1]
                    dist = (dx*dx + dy*dy) ** 0.5

                    sys_type = battery.get('system_type', '')
                    specs = battery.get('specs', {})
                    bm_specs = specs.get('ballistic_missile_specs', {})
                    rng_info = bm_specs.get('engagement_range_km', {})
                    max_range = rng_info.get('max', 300 if 'LSAM' in sys_type else 50)

                    if dist <= max_range * 1.5:
                        if 'LSAM' in sys_type:
                            can_engage_lsam = True
                        elif 'MSAM' in sys_type:
                            can_engage_msam = True

                if can_engage_lsam:
                    base_prob = 0.85
                elif can_engage_msam:
                    base_prob = 0.78
                else:
                    base_prob = 0.85

                sampled_prob = self.uncertainty_model.sample_intercept_probability(base_prob)
                sampled_probs[threat_id] = sampled_prob
            
            # 🆕 알고리즘 선택 (MIP, Greedy, GA)
            # 모든 알고리즘이 독립 모듈을 사용하여 동일한 프로세스를 거침
            if self.current_algorithm == 'Greedy':
                # Greedy Optimizer 모듈 사용
                optimizer = GreedyOptimizer(self.config)
                optimizer.set_intercept_probabilities(sampled_probs)
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
                optimizer.set_intercept_probabilities(sampled_probs)
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

                optimizer.set_intercept_probabilities(sampled_probs)
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
                        self.last_objective_value = 999.99  # 마지막 수단으로 높은 값 설정
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
                        if diag['time_limit_reached']:
                            reason = "시간 초과 (복잡도)"
                            detail = f"변수 {diag['num_variables']}개, 제약 {diag['num_constraints']}개"
                        elif diag['solver_status'] == 'Infeasible':
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
                    # Default specs for unknown system types
                    Pk = 0.95
                    Range = 50.0
                    max_missiles = 3
                    
            except (KeyError, TypeError):
                # Fallback specs for demo mode or missing data
                Pk = 0.95
                Range = 50.0
                max_missiles = 3

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
                # Estimate altitude based on flight progress (ballistic trajectory)
                altitude = 10000.0 * (1.0 - missile['flight_progress'])
                
                # Find original threat configuration for enhanced data
                original_threat_data = None
                for threat_data in self.initial_threats_config:
                    if threat_data['id'] == missile['id']:
                        original_threat_data = threat_data
                        break
                
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

            # 🆕 GUI 상태 업데이트: 솔버 시간 (Thread-safe)
            if hasattr(self.control_panel, 'solver_time_var'):
                st = f"{pure_st:.3f}s"
                self.control_panel.control_window.after(0, lambda: self.control_panel.solver_time_var.set(st))

        # 🆕 Warm-start 상태 업데이트 (Thread-safe)
        if self.control_panel and hasattr(self.control_panel, 'warmstart_var'):
            warmstart_applied = result.get('warmstart_applied', False)
            warmstart_count = result.get('warmstart_count', 0)

            if warmstart_applied and warmstart_count > 0:
                ws_text = f"ON ({warmstart_count} vars)"
            else:
                ws_text = "OFF"
            self.control_panel.control_window.after(0, lambda: self.control_panel.warmstart_var.set(ws_text))
        
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
        """Update the display - matplotlib or PyQtGraph based on mode."""
        # 🆕 Phase 2: PyQtGraph mode (high-performance, <2ms per frame)
        if self.use_pyqtgraph and self.pyqtgraph_display:
            try:
                self.pyqtgraph_display.update_display()
            except Exception as e:
                print(f"PyQtGraph update error: {e}")
                print("Disabling PyQtGraph mode...")
                self.use_pyqtgraph = False
            return

        # Original matplotlib mode
        if self.fig:
            try:
                # clear() 대신 기존 객체 재사용 (성능 향상)
                self.ax_main.clear()
                self._initialize_axes()
                self._draw_tactical_display()

                # History와 Analysis는 덜 자주 업데이트 (5초마다)
                if self.current_time_step % 5 == 0:
                    if hasattr(self, 'ax_history'):
                        self._draw_history_panel()
                    if hasattr(self, 'ax_analysis'):
                        self._draw_analysis_panel()

                # draw_idle()만 사용 (flush_events와 pause 제거로 성능 향상)
                self.fig.canvas.draw_idle()
            except Exception as e:
                if plt.fignum_exists(self.fig.number):
                    print(f"Visualization update error: {e}")
                self.fig = None

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

    def _check_text_overlap(self, x, y, width, height):
        """Check if text area overlaps with existing text areas"""
        for occupied in self.occupied_areas:
            ox, oy, ow, oh = occupied
            if (x < ox + ow and x + width > ox and 
                y < oy + oh and y + height > oy):
                return True
        return False
    
    def _find_best_text_position(self, center_x, center_y, text_width, text_height, preferred_positions):
        """Find the best position for text that doesn't overlap"""
        for dx, dy in preferred_positions:
            test_x = center_x + dx - text_width/2
            test_y = center_y + dy - text_height/2
            
            if not self._check_text_overlap(test_x, test_y, text_width, text_height):
                self.occupied_areas.append((test_x, test_y, text_width, text_height))
                return center_x + dx, center_y + dy
        
        # If no position found, use the first preference and add to occupied areas anyway
        dx, dy = preferred_positions[0]
        test_x = center_x + dx - text_width/2
        test_y = center_y + dy - text_height/2
        self.occupied_areas.append((test_x, test_y, text_width, text_height))
        return center_x + dx, center_y + dy

    def _find_optimal_label_position(self, center_x, center_y, text_width, text_height, system_type=None):
        """Find optimal label position to avoid overlaps using 8-direction priority system"""
        # Define 8 directions with priority based on system type
        if system_type == 'LSAM':
            # LSAM priority: left directions first
            preferred_positions = [
                (-35, -25), (-35, 0), (-35, 25),   # Left side
                (35, -25), (0, -30), (0, 30),      # Right and vertical
                (35, 0), (35, 25)                  # Right side
            ]
        else:  # MSAM or others
            # MSAM priority: right directions first
            preferred_positions = [
                (35, 25), (35, 0), (35, -25),      # Right side
                (-35, 25), (0, 30), (0, -30),      # Left and vertical
                (-35, 0), (-35, -25)               # Left side
            ]
        
        # Try each position until we find one without overlap
        for dx, dy in preferred_positions:
            test_x = center_x + dx - text_width/2
            test_y = center_y + dy - text_height/2
            
            if not self._check_text_overlap(test_x, test_y, text_width, text_height):
                self.occupied_areas.append((test_x, test_y, text_width, text_height))
                return center_x + dx, center_y + dy, dx, dy  # Return offset for leader line
        
        # If no position found, use the first preference and add to occupied areas anyway
        dx, dy = preferred_positions[0]
        test_x = center_x + dx - text_width/2
        test_y = center_y + dy - text_height/2
        self.occupied_areas.append((test_x, test_y, text_width, text_height))
        return center_x + dx, center_y + dy, dx, dy

    def _draw_tactical_display(self):
        """Enhanced tactical display with military-style appearance."""
        import numpy as np
        
        # Initialize occupied areas tracker
        self.occupied_areas = []
        
        # Set dark background with military-style grid (matching reference image)
        self.ax_main.set_facecolor('#0a0a0a')  # Very dark background like reference
        self.ax_main.grid(True, alpha=0.4, color='#2a4a2a', linestyle='-', linewidth=0.8)  # Green grid
        
        # Add North indicator with blue background like reference
        bbox_props = dict(boxstyle="round,pad=0.3", facecolor='#4a90e2', alpha=0.8)
        self.ax_main.text(0.95, 0.95, '⬆ N', transform=self.ax_main.transAxes, 
                         ha='center', va='center', fontsize=12, color='white', weight='bold',
                         bbox=bbox_props)
        
        # Draw assets with diamond markers (friendly blue)
        for asset in self.assets:
            # Handle both 2D and 3D positions
            pos = asset['position']
            x, y = pos[:2] if len(pos) > 2 else pos
            color = '#4a90e2'  # NATO friendly blue
            
            # Draw asset as diamond (reduced size)
            self.ax_main.scatter(x, y, c=color, s=90,marker='D', alpha=0.9, 
                               edgecolors='black',linewidth=1.0)
            
            # ⚡ 성능 최적화: 문자열 조회 최소화
            asset_id = asset['id']
            asset_number = asset_id.split('_')[-1] if '_' in asset_id else asset_id[-2:]
            self.ax_main.text(x, y, asset_number, ha='center', va='center', 
                            fontsize=5, color='black', weight='bold', zorder=13)

        # Draw batteries with type-specific styling and coverage areas
        for battery in self.batteries:
            # ⚡ 성능 최적화: 한 번만 조회
            # Handle both 2D and 3D positions
            pos = battery['position']
            x, y = pos[:2] if len(pos) > 2 else pos
            system_type = battery.get('system_type', 'UNKNOWN')
            available = battery.get('available_missiles', 0)
            status = battery.get('status', 'UNKNOWN')
            
            # Different colors, markers and sizes for different battery types
            if system_type == 'LSAM':
                color = '#ff6b35'  # Orange-red for LSAM
                marker = 's'       # Square for LSAM
                marker_size = 150  # Reduced size for LSAM
                max_range = 300    # LSAM max range in km (실제 스펙: 150-300km)
                min_range = 150    # LSAM min range in km
                offset_x, offset_y = -8, -8  # Position offset to prevent overlap
            elif system_type == 'MSAM':
                color = '#00d4aa'  # Teal green for MSAM to distinguish
                marker = '^'       # Triangle for MSAM
                marker_size = 120  # Reduced size for MSAM
                max_range = 50     # MSAM max range in km (실제 스펙: 5-50km)
                min_range = 5      # MSAM min range in km
                offset_x, offset_y = 8, 8   # Different offset to prevent overlap
            else:
                color = 'gray'
                marker = 'D'
                marker_size = 100  # Reduced size
                max_range = 50
                min_range = 10
                offset_x, offset_y = 0, 0
            
            # Adjust alpha based on status
            alpha = 0.9 if status == 'OPERATIONAL' else 0.4
            
            # Draw concentric circles for coverage area (only if operational)
            if status == 'OPERATIONAL':
                # Use green color for range circles like reference image
                circle_color = '#2d5a2d' if system_type == 'LSAM' else '#1a4a1a'
                
                # Outer circle (max range) - dashed line
                circle_outer = plt.Circle((x, y), max_range, fill=False, 
                                        color=circle_color, alpha=0.6, linewidth=1.2, linestyle='--')
                self.ax_main.add_patch(circle_outer)
                
                # Inner circle (min range) - dotted line
                if min_range > 0:
                    circle_inner = plt.Circle((x, y), min_range, fill=False, 
                                            color=circle_color, alpha=0.4, linewidth=0.8, linestyle=':')
                    self.ax_main.add_patch(circle_inner)
            
            # Draw battery with type-specific marker and position offset
            actual_x, actual_y = x + offset_x, y + offset_y
            self.ax_main.scatter(actual_x, actual_y, c=color, s=marker_size, marker=marker, alpha=alpha,
                               edgecolors='white', linewidth=2, zorder=10)
            
            # Draw heading line (pointing north as default)
            heading_angle = np.radians(90)  # 90 degrees (North direction)
            heading_length = 20 if system_type == 'LSAM' else 15  # Different lengths
            end_x = actual_x + heading_length * np.cos(heading_angle)
            end_y = actual_y + heading_length * np.sin(heading_angle)
            
            if status == 'OPERATIONAL':
                self.ax_main.plot([actual_x, end_x], [actual_y, end_y], '-', color=color, 
                                linewidth=2.5 if system_type == 'LSAM' else 2, alpha=0.9, zorder=9)
                # Add arrowhead
                self.ax_main.annotate('', xy=(end_x, end_y), xytext=(actual_x, actual_y),
                                    arrowprops=dict(arrowstyle='->', color=color, 
                                                  lw=2.5 if system_type == 'LSAM' else 2, alpha=0.9),
                                    zorder=9)
            
            # Battery number inside symbol
            battery_number = battery['id'].split('_')[-1] if '_' in battery['id'] else battery['id'][-2:]
            self.ax_main.text(actual_x, actual_y, battery_number, ha='center', va='center', 
                            fontsize=6, color='black', weight='bold', zorder=13)

        # Draw missiles with threat-based styling
        for missile_id, missile in self.missiles.items():
            if missile_id in self.kill_results:
                # Show different symbols for intercepted vs missed threats
                # Handle both 2D and 3D positions
                pos = missile['position']
                x, y = pos[:2] if len(pos) > 2 else pos
                result = self.kill_results[missile_id][0]  # Get result from tuple
                
                if result == 'INTERCEPTED':
                    # Successfully intercepted (green X mark)
                    self.ax_main.scatter(x, y, c='#00ff00', s=80, marker='x', alpha=0.8,
                                       edgecolors='white', linewidth=2)
                else:
                    # Missed/Failed intercept (red explosion-like symbol)
                    self.ax_main.scatter(x, y, c='#ff3333', s=100, marker='*', alpha=0.8,
                                       edgecolors='white', linewidth=1.5)
            
            elif missile['active']:
                # Handle both 2D and 3D positions
                pos = missile['position']
                x, y = pos[:2] if len(pos) > 2 else pos

                # Check if missile is assigned to any battery
                is_assigned = any(threat_id == missile_id for threat_id in self.primary_assignments.values())

                if is_assigned:
                    # Assigned threat (orange downward triangle)
                    color = '#ff8c42'  # Orange for assigned
                    marker = 'v'  # Downward triangle
                else:
                    # Unassigned threat (red downward triangle)
                    color = '#cc4125'  # Threat red
                    marker = 'v'  # Downward triangle

                # Draw threat missile (reduced size)
                self.ax_main.scatter(x, y, c=color, s=180, marker=marker, alpha=0.9,
                                   edgecolors='white', linewidth=1.0)

                # Threat number inside symbol with progress
                threat_number = missile_id.split('_')[-1] if '_' in missile_id else missile_id[-2:]
                progress = missile['flight_progress']
                self.ax_main.text(x, y, f"{threat_number}\n{progress:.0%}", ha='center', va='center',
                                fontsize=4, color='white', weight='bold', zorder=13)

                # Draw trajectory line (green for missile trajectory)
                # Handle both 2D and 3D target positions
                tpos = missile['target_position']
                tx, ty = tpos[:2] if len(tpos) > 2 else tpos
                self.ax_main.plot([x, tx], [y, ty], '-', color='#2d5a2d', alpha=0.7, linewidth=1)

        # Draw assignment lines with better visibility
        for battery_id, threat_list in self.primary_assignments.items():
            for threat_id in threat_list:
                if threat_id in self.missiles and self.missiles[threat_id]['active']:
                    battery = next((b for b in self.batteries if b['id'] == battery_id), None)
                    if battery:
                        # Handle both 2D and 3D positions
                        bpos = battery['position']
                        bx, by = bpos[:2] if len(bpos) > 2 else bpos
                        mpos = self.missiles[threat_id]['position']
                        mx, my = mpos[:2] if len(mpos) > 2 else mpos
                        # Thin assignment line with subtle indicator
                        self.ax_main.plot([bx, mx], [by, my], '-', color='lime',
                                        linewidth=1, alpha=0.6)
                        # Small assignment indicator at midpoint
                        mid_x, mid_y = (bx + mx) / 2, (by + my) / 2
                        self.ax_main.text(mid_x, mid_y, '●', ha='center', va='center',
                                    fontsize=4, color='lime', alpha=0.8)
        
        # Add ammunition status panel in top-right corner
        self._draw_ammunition_status()

    def _draw_ammunition_status(self):
        """Draw ammunition status and legend with separated layout"""
        from matplotlib.lines import Line2D
        
        # Create ammunition status legend (upper left)
        ammo_elements = []
        sorted_batteries = sorted(self.batteries, key=lambda b: b['id'])
        
        for battery in sorted_batteries:
            available = battery.get('available_missiles', 0)
            system_type = battery.get('system_type', 'UNKNOWN')
            battery_id = battery['id']
            
            # Format display text
            display_text = f"{battery_id}: {available} missiles"
            
            # Color coding based on ammunition level
            if available >= 20:
                marker_color = '#00ff00'  # Green for high ammo
            elif available >= 10:
                marker_color = '#ffff00'  # Yellow for medium ammo
            elif available >= 5:
                marker_color = '#ff8800'  # Orange for low ammo
            else:
                marker_color = '#ff0000'  # Red for critical ammo
            
            # Create ammunition status element
            marker_shape = 's' if system_type == 'LSAM' else '^'
            ammo_elements.append(Line2D([0], [0], marker=marker_shape, color='w', 
                                        markerfacecolor=marker_color, markersize=6,
                                        label=display_text, 
                                        markeredgecolor='white', markeredgewidth=1))
        
        # Add ammunition status legend (upper left)
        if ammo_elements:
            ammo_legend = self.ax_main.legend(handles=ammo_elements, 
                                            title='AMMUNITION STATUS', 
                                            loc='upper left',
                                            bbox_to_anchor=(0.02, 0.98),
                                            fontsize=5,
                                            title_fontsize=7,
                                            frameon=True,
                                            framealpha=0.9,
                                            fancybox=True,
                                            shadow=True,
                                            facecolor='black',
                                            edgecolor='#2d5a2d')
            
            # Style the ammunition legend
            ammo_legend.get_title().set_color('#00ff00')
            ammo_legend.get_title().set_weight('bold')
            
            # Set text colors to white for better visibility
            for text in ammo_legend.get_texts():
                text.set_color('white')
        
        # Create symbol legend (lower left)
        symbol_elements = []
        
        # Add symbol type explanations
        symbol_elements.append(Line2D([0], [0], marker='D', color='w', 
                                    markerfacecolor='#4a90e2', markersize=8,
                                    label='Assets (Protected)', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='s', color='w', 
                                    markerfacecolor='#ff6b35', markersize=8,
                                    label='LSAM Batteries', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='^', color='w', 
                                    markerfacecolor='#00d4aa', markersize=8,
                                    label='MSAM Batteries', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='v', color='w', 
                                    markerfacecolor='#ff8c42', markersize=8,
                                    label='Assigned Threats', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='v', color='w', 
                                    markerfacecolor='#cc4125', markersize=8,
                                    label='Unassigned Threats', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='x', color='w', 
                                    markerfacecolor='#00ff00', markersize=8,
                                    label='Intercepted Threats', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        symbol_elements.append(Line2D([0], [0], marker='*', color='w', 
                                    markerfacecolor='#ff3333', markersize=8,
                                    label='Failed Intercepts', 
                                    markeredgecolor='white', markeredgewidth=1))
        
        # Add symbol legend (lower left)
        if symbol_elements:
            symbol_legend = self.ax_main.legend(handles=symbol_elements, 
                                              title='SYMBOL LEGEND', 
                                              loc='lower left',
                                              bbox_to_anchor=(0.02, 0.02),
                                              fontsize=5,
                                              title_fontsize=7,
                                              frameon=True,
                                              framealpha=0.9,
                                              fancybox=True,
                                              shadow=True,
                                              facecolor='black',
                                              edgecolor='#2d5a2d')
            
            # Style the symbol legend
            symbol_legend.get_title().set_color('#00ff00')
            symbol_legend.get_title().set_weight('bold')
            
            # Set text colors to white for better visibility
            for text in symbol_legend.get_texts():
                text.set_color('white')
        
        # Add both legends to the plot (matplotlib supports multiple legends)
        if ammo_elements:
            self.ax_main.add_artist(ammo_legend)

    def _draw_history_panel(self):
        """Draw history panel (원본 코드)"""
        self.ax_history.clear()
        self.ax_history.set_facecolor('#111111')
        self.ax_history.set_title('Event Log', fontsize=12, color='white')
        self.ax_history.axis('off')
        
        y_pos = 0.95
        self.ax_history.text(0.05, y_pos, f"Time Step: {self.current_time_step}", fontsize=10, color='white')
        y_pos -= 0.05
        self.ax_history.text(0.05, y_pos, f"Active: {self.stats['active']}", fontsize=10, color='yellow')
        y_pos -= 0.05
        self.ax_history.text(0.05, y_pos, f"Killed: {self.stats['intercepted']}", fontsize=10, color='lime')
        y_pos -= 0.05
        self.ax_history.text(0.05, y_pos, f"Missed: {self.stats['missed']}", fontsize=10, color='red')
        y_pos -= 0.06

        self.ax_history.text(0.05, y_pos, "Recent Events:", fontsize=10, color='cyan')
        y_pos -= 0.05
        
        recent_results = sorted(self.kill_results.items(), key=lambda item: item[1][1], reverse=True)[:15]
        for missile_id, (result, time, _) in recent_results:
            if result == 'INTERCEPTED':
                color = 'lime'
                symbol = '✓'
            else:
                color = 'red'
                symbol = '✗'
            self.ax_history.text(0.05, y_pos, f"[T={time}] {symbol} {missile_id}: {result}", fontsize=9, color=color)
            y_pos -= 0.05
            if y_pos < 0.05: break

    def _draw_analysis_panel(self):
        """Draw analysis panel (원본 코드)"""
        self.ax_analysis.clear()
        self.ax_analysis.set_title('Objective Function Value Over Time', fontsize=12, color='cyan')
        
        if self.objective == 'MIN_DAMAGE':
            ylabel = 'Expected Damage (Minimize)'
        else:
            ylabel = 'Expected Hits (Minimize)'
            
        self.ax_analysis.set_ylabel(ylabel, fontsize=9, color='white')
        self.ax_analysis.set_xlabel('Time Step', fontsize=9, color='white')
        self.ax_analysis.tick_params(colors='white', labelsize=8)

        if self.optimization_history:
            valid_history = [h for h in self.optimization_history if h[1] != float('inf')]
            if valid_history:
                times = [h[0] for h in valid_history]
                values = [h[1] for h in valid_history]

                self.ax_analysis.plot(times, values, color='orange', marker='o', markersize=4, linestyle='-')
                self.ax_analysis.grid(True, alpha=0.3, linestyle='--')

    def run_simulation(self, max_duration=3000):
        """Run simulation (GUI 모드에서는 제어 패널에서 실행)"""
        # Headless 모드에서는 GUI 루프 건너뛰기
        if self.headless or not self.control_panel:
            # 텍스트 모드에서는 기존 로직 실행
            self.start_scenario()
            return
        
        # GUI 모드에서만 제어 패널 루프 실행
        if self.control_panel and self.fig is not None:
            print("GUI 모드: 제어 패널에서 시뮬레이션을 제어하세요.")
            try:
                # GUI 모드에서는 메인 루프만 실행
                # update_display 호출 빈도 제한 (bottleneck 방지)
                last_display_update = time.time()
                display_update_interval = 0.5  # 0.5초마다 업데이트
                
                while self.fig is not None and plt.fignum_exists(self.fig.number):
                    current_time = time.time()
                    if current_time - last_display_update >= display_update_interval:
                        # Non-blocking: 시뮬레이션 실행 중이면 이번 프레임 건너뜀
                        # (Tkinter 이벤트 루프를 차단하면 안 됨)
                        if self._sim_lock.acquire(blocking=False):
                            try:
                                self.update_display()
                            finally:
                                self._sim_lock.release()
                            last_display_update = current_time
                    plt.pause(0.1)
            except KeyboardInterrupt:
                print("\n시뮬레이션이 중단되었습니다.")
            finally:
                if self.control_panel and self.control_panel.control_window:
                    try:
                        self.control_panel.control_window.destroy()
                    except:
                        pass  # 이미 닫힌 경우 무시
            return
        
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
        
        # 제어 패널 목적함수 값 업데이트 (Thread-safe)
        if self.control_panel and self.last_objective_value is not None:
            obj_text = f"목적함수: {self.last_objective_value:.2f}"
            try:
                self.control_panel.control_window.after(0, lambda: self.control_panel.objective_val_var.set(obj_text))
            except (tk.TclError, RuntimeError):
                pass
        
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
        
        # 시각화 유지
        if not self.text_mode and self.fig:
            try:
                plt.savefig(f"dwta_analysis_{self.objective}.png")
                print("\nVisualization saved to dwta_analysis.png")
            except:
                pass
            
            # Compare 모드에서는 GUI 창 대기 생략 (자동 진행)
            if not self.comparison_mode:
                print("\nKeeping visualization open. Close the window to exit.")
                plt.ioff() 
                self.update_display()
                plt.show(block=True)

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