"""
Greedy DWTA Optimizer
=====================
Greedy 알고리즘 기반 DWTA 최적화기 (독립 모듈)

전략: 교전 가능한 첫 번째 시스템을 순차적으로 할당
- 제약 조건: 탄약 용량, 교전 범위
- 목적함수: MIP와 동일한 기댓값 손실 계산
"""

import numpy as np
import time
import timeit
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging
import sys

@dataclass
class Asset:
    """방어 자산"""
    id: str
    position: Tuple[float, float]
    value: float
    priority: int
    estimated_threat_missiles: List[str]

@dataclass 
class InterceptorSystem:
    """요격체계 (상층/하층)"""
    id: str
    system_type: str  # "LSAM" (상층) or "MSAM" (하층)
    position: Tuple[float, float]
    available_missiles: int
    max_missiles_per_target: int
    intercept_probability: float
    engagement_range: float

@dataclass
class Threat:
    """위협 미사일"""
    id: str
    target_asset_id: str
    current_position: Tuple[float, float, float]
    estimated_impact_time: float
    
    launch_position: Tuple[float, float] = (0.0, 0.0)
    flight_time: float = 300.0
    specs: dict = None
    launch_time: float = 0.0
    trajectory_type: str = "ballistic"
    rcs: float = 0.5
    
    def __post_init__(self):
        if self.specs is None:
            self.specs = {
                "max_altitude_km": 50.0,
                "avg_speed_kmh": 2000.0,
                "trajectory_type": self.trajectory_type,
                "rcs": self.rcs
            }


class GreedyOptimizer:
    """Greedy 알고리즘 기반 DWTA 최적화기"""
    
    def __init__(self, config):
        self.config = config
        self.model = None
        self.variables = {}
        self.constraints = {}
        self.objective_value = 0
        self.solve_time = 0
        self.status = "NOT_SOLVED"
        
        # 몬테카를로 시뮬레이션용 샘플링된 요격확률
        self.custom_intercept_probs = {}
        
        # 로깅 설정
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.WARNING)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
        
        # k 파라미터 범위 (교전 윈도우 기반 확률 보정 계수)
        self.k_min = 0.6
        self.k_max = 1.0
        
        # 미사일 수 고정값
        self.missiles_per_engagement = 2
        
        # 교전 가능성 매트릭스
        self.engagement_matrix = None
        self.engagement_matrix_cache = None
        self.k_factor_cache = None
        self.battery_specs = {}
    
    def create_model(self, 
                    assets: List[Asset],
                    interceptor_systems: List[InterceptorSystem], 
                    threats: List[Threat],
                    batteries: List[Dict] = None,
                    engagement_matrix = None):
        """Greedy 모델 생성 - 데이터 구조 초기화"""
        
        # Enhanced Engagement Matrix 처리
        if hasattr(engagement_matrix, 'is_feasible'):
            self.engagement_matrix_cache = engagement_matrix
            print(f"[OK] Enhanced Engagement Matrix 사용 (Greedy)")
        else:
            self.engagement_matrix = engagement_matrix or {}
            self.engagement_matrix_cache = None
        
        # K-Factor 캐시 생성
        if self.engagement_matrix_cache:
            from config_mip import KFactorCache
            self.k_factor_cache = KFactorCache(k_min=self.k_min, k_max=self.k_max)
            self.k_factor_cache.precompute(
                threats, 
                interceptor_systems, 
                self.engagement_matrix_cache
            )
        
        # 데이터 저장
        self.assets = assets
        self.interceptor_systems = interceptor_systems
        self.threats = threats
        self.batteries = batteries or []
        
        # 상층/하층 시스템 분리
        self.upper_systems = [s for s in interceptor_systems if getattr(s, 'system_type', '') in ["LSAM", "UPPER"]]
        self.lower_systems = [s for s in interceptor_systems if getattr(s, 'system_type', '') in ["MSAM", "LOWER"]]
        
        # 포대별 스펙 정보 저장
        for battery in self.batteries:
            self.battery_specs[battery["id"]] = battery.get("specs", {})
        
        print(f"Greedy setup: {len(assets)} assets, {len(self.upper_systems)} upper, {len(self.lower_systems)} lower systems, {len(threats)} threats")
    
    def set_intercept_probabilities(self, intercept_probs):
        """몬테카를로 시뮬레이션에서 샘플링된 요격확률 설정"""
        self.custom_intercept_probs = intercept_probs.copy()
        print(f"Greedy Optimizer: Set custom intercept probabilities for {len(intercept_probs)} threats")
    
    def solve(self):
        """
        Greedy 알고리즘 실행 (공정한 비교를 위해 개선)
        
        개선 사항:
        - 단순 First-fit이 아닌 Best-fit with lookahead
        - 각 할당이 전체 목적함수에 미치는 영향 평가
        - 여러 할당 조합 중 최선 선택
        """
        start_time = timeit.default_timer()
        
        upper_assignments = {}
        lower_assignments = {}
        
        # 🔧 OPTIMIZED Phase 1: 배터리 스펙 캐싱 (초기화 시 1회만 계산)
        battery_id_to_idx = {b['id']: idx for idx, b in enumerate(self.batteries)}
        battery_specs_cache = np.array([
            b['specs']['battery_config'].get('simultaneous_engagements', 3)
            for b in self.batteries
        ], dtype=np.uint8)
        
        # 🔧 OPTIMIZED Phase 2: NumPy 배열 기반 용량 추적 (딕셔너리 → 배열)
        n_batteries = len(self.batteries)
        battery_usage = np.zeros(n_batteries, dtype=np.uint8)
        battery_capacity = np.array([
            b.get('available_missiles', 10) for b in self.batteries
        ], dtype=np.uint8)
        battery_engagement_count = np.zeros(n_batteries, dtype=np.uint8)
        
        # 🆕 다층 방어: 상층과 하층 모두 할당 추적
        upper_assigned = {}  # 상층 할당 추적
        lower_assigned = {}  # 하층 할당 추적
        upper_assignment_count = 0  # 전체 상층 할당 개수 추적
        
        # 상층 최대 할당 개수 동적 계산 (상층 배터리 수 × 동시 교전 수)
        max_upper_assignments = sum(
            battery_specs_cache[battery_id_to_idx[getattr(sys, 'id', '')]]
            for sys in self.upper_systems
        )
        
        # 하층 최대 할당 개수 동적 계산 (하층 배터리 수 × 동시 교전 수)
        max_lower_assignments = sum(
            battery_specs_cache[battery_id_to_idx[getattr(sys, 'id', '')]]
            for sys in self.lower_systems
        )
        lower_assignment_count = 0  # 전체 하층 할당 개수 추적
        
        # ✅ Greedy 전략: 자산 가치 기반 우선순위 정렬
        # 가치가 높은 자산을 목표로 하는 위협부터 할당
        asset_value_map = {getattr(a, 'id', ''): getattr(a, 'value', 0) for a in self.assets}
        threats_sorted = sorted(
            self.threats,
            key=lambda t: asset_value_map.get(getattr(t, 'target_asset_id', ''), 0),
            reverse=True  # 가치 높은 순
        )
        
        # 각 위협에 대해 상층과 하층 시스템 할당 (우선순위 순)
        for threat in threats_sorted:
            threat_id = getattr(threat, 'id', '')
            target_asset_id = getattr(threat, 'target_asset_id', '')
            key = f"{target_asset_id}_{threat_id}"
            
            # ✅ 개선 1: Best-fit 전략 (k-factor 최대 시스템 선택)
            # 1단계: LSAM 할당 (상층)
            if key not in upper_assignments and upper_assignment_count < max_upper_assignments:
                best_system = None
                best_k = 0
                
                for system in self.upper_systems:
                    system_id = getattr(system, 'id', '')
                    
                    # 교전 가능 여부 확인
                    if self.engagement_matrix_cache:
                        is_feasible = self.engagement_matrix_cache.is_feasible(system_id, threat_id)
                    else:
                        engagement_key = (system_id, threat_id)
                        is_feasible = self.engagement_matrix.get(engagement_key, False)
                    
                    if not is_feasible:
                        continue
                    
                    # 용량 확인
                    bat_idx = battery_id_to_idx[system_id]
                    if battery_usage[bat_idx] >= battery_capacity[bat_idx]:
                        continue
                    
                    # 동시 교전 제약 확인
                    if battery_engagement_count[bat_idx] >= battery_specs_cache[bat_idx]:
                        continue
                    
                    # ✅ k-factor 계산 및 비교
                    k = self._get_k_factor(system_id, threat_id)
                    if k > best_k:
                        best_k = k
                        best_system = system
                
                # 최선의 시스템 할당
                if best_system:
                    system_id = getattr(best_system, 'id', '')
                    upper_assignments[key] = system_id
                    bat_idx = battery_id_to_idx[system_id]
                    battery_usage[bat_idx] += 2
                    battery_engagement_count[bat_idx] += 1
                    upper_assigned[threat_id] = system_id
                    upper_assignment_count += 1
            
            # ✅ 개선 2: 다층 방어 활성화 (자산 가치 기반 조건부)
            if threat_id in upper_assigned:
                asset = next((a for a in self.assets 
                             if getattr(a, 'id', '') == target_asset_id), None)
                if asset and getattr(asset, 'value', 0) < 70:
                    continue  # 가치 낮으면 하층 건너뛰기
                # 가치 높으면 하층도 시도 (다층 방어)
            
            # 2단계: MSAM 할당 (하층)
            if key not in lower_assignments and lower_assignment_count < max_lower_assignments:
                best_system = None
                best_k = 0
                
                for system in self.lower_systems:
                    system_id = getattr(system, 'id', '')
                    
                    # 교전 가능 여부 확인
                    if self.engagement_matrix_cache:
                        is_feasible = self.engagement_matrix_cache.is_feasible(system_id, threat_id)
                    else:
                        engagement_key = (system_id, threat_id)
                        is_feasible = self.engagement_matrix.get(engagement_key, False)
                    
                    if not is_feasible:
                        continue
                    
                    # 용량 확인
                    bat_idx = battery_id_to_idx[system_id]
                    if battery_usage[bat_idx] >= battery_capacity[bat_idx]:
                        continue
                    
                    # 동시 교전 제약 확인
                    if battery_engagement_count[bat_idx] >= battery_specs_cache[bat_idx]:
                        continue
                    
                    # ✅ k-factor 계산 및 비교
                    k = self._get_k_factor(system_id, threat_id)
                    if k > best_k:
                        best_k = k
                        best_system = system
                
                # 최선의 시스템 할당
                if best_system:
                    system_id = getattr(best_system, 'id', '')
                    lower_assignments[key] = system_id
                    bat_idx = battery_id_to_idx[system_id]
                    battery_usage[bat_idx] += 2
                    battery_engagement_count[bat_idx] += 1
                    lower_assigned[threat_id] = system_id
                    lower_assignment_count += 1
        
        self.solve_time = timeit.default_timer() - start_time
        
        # 목적함수 계산
        self.objective_value = self._calculate_objective(upper_assignments, lower_assignments)
        self.status = "OPTIMAL"
        
        return {
            'feasible': True,
            'objective_value': self.objective_value,
            'solve_time': self.solve_time,
            'upper_assignments': upper_assignments,
            'lower_assignments': lower_assignments,
            'algorithm': 'Greedy',
            'status': self.status
        }
    
    def _calculate_objective(self, upper_assignments, lower_assignments):
        """
        목적함수 계산: GA와 동일한 방식
        MIN_DAMAGE: min Σ B_i * [Π (1 - x*k*P)]
        = 기댓값 손실 최소화 (K-factor 포함)
        """
        objective_value = 0.0
        
        # 각 자산에 대해 생존 확률 계산
        for asset in self.assets:
            asset_id = getattr(asset, 'id', '')
            asset_value = getattr(asset, 'value', 0)
            
            # 이 자산을 목표로 하는 모든 위협 찾기
            threats_to_asset = [t for t in self.threats 
                               if getattr(t, 'target_asset_id', '') == asset_id]
            
            asset_survival_prob = 1.0
            
            for threat in threats_to_asset:
                threat_id = getattr(threat, 'id', '')
                key = f"{asset_id}_{threat_id}"
                
                # ✅ 초기화: 기본값은 할당 안 됨 (pk_effective = 0)
                pk_effective = 0.0
                
                # 할당 여부 확인
                if key in upper_assignments:
                    system_id = upper_assignments[key]
                    
                    # 요격 확률 가져오기
                    if threat_id in self.custom_intercept_probs:
                        pk = self.custom_intercept_probs[threat_id]
                    else:
                        pk = 0.85  # LSAM 기본값
                    
                    # 2발 발사 시 총 요격 확률
                    P_total = 1 - (1 - pk) ** self.missiles_per_engagement
                    
                    # K-factor 가져오기
                    k_factor = self._get_k_factor(system_id, threat_id)
                    
                    # 유효 요격 확률 = k * P_total
                    pk_effective = k_factor * P_total
                    
                elif key in lower_assignments:
                    system_id = lower_assignments[key]
                    
                    # 요격 확률 가져오기
                    if threat_id in self.custom_intercept_probs:
                        pk = self.custom_intercept_probs[threat_id]
                    else:
                        pk = 0.78  # MSAM 기본값
                    
                    # 2발 발사 시 총 요격 확률
                    P_total = 1 - (1 - pk) ** self.missiles_per_engagement
                    
                    # K-factor 가져오기
                    k_factor = self._get_k_factor(system_id, threat_id)
                    pk_effective = k_factor * P_total
                
                # ✅ 모든 경우에 생존 확률 곱하기 (할당 안 된 경우 pk_effective=0)
                # 할당 안 됨 → 요격 안 함 → pk_effective = 0 → survival *= (1-0) = 변화 없음
                asset_survival_prob *= (1 - pk_effective)
            
            # 손실 확률 = 1 - 생존 확률
            loss_prob = 1 - asset_survival_prob
            
            # 기댓값 손실 = 자산 가치 × 손실 확률
            objective_value += asset_value * loss_prob
        
        return objective_value
    
    def _get_k_factor(self, system_id, threat_id):
        """K-factor 가져오기: 캐시에서 또는 거리 기반 계산"""
        # K-factor 캐시가 있으면 사용
        if self.k_factor_cache and hasattr(self.k_factor_cache, 'get_k_factor'):
            return self.k_factor_cache.get_k_factor(threat_id, system_id)
        
        # 캐시가 없으면 거리 기반으로 직접 계산
        if self.engagement_matrix_cache and hasattr(self.engagement_matrix_cache, 'get_distance'):
            distance = self.engagement_matrix_cache.get_distance(system_id, threat_id)
            max_range = 150.0 if 'LSAM' in system_id else 80.0
            
            if distance > 0 and max_range > 0:
                range_ratio = 1.0 - (distance / max_range)
                k_factor = self.k_min + (self.k_max - self.k_min) * max(0, range_ratio)
                return max(self.k_min, min(self.k_max, k_factor))
        
        # 기본값
        return 0.9
    
    def get_assignment_details(self):
        """할당 세부 정보 반환"""
        return {
            'upper_systems': len(self.upper_systems),
            'lower_systems': len(self.lower_systems),
            'total_threats': len(self.threats),
            'solve_time': self.solve_time,
            'objective_value': self.objective_value
        }
