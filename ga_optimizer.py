"""
Genetic Algorithm DWTA Optimizer
=================================
유전 알고리즘 기반 DWTA 최적화기 (독립 모듈)

전략: 교전 가능한 시스템 중 랜덤 선택 (단순화된 GA)
- 제약 조건: 탄약 용량, 교전 범위
- 목적함수: MIP와 동일한 기댓값 손실 계산
"""

import numpy as np
import random
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


class GeneticAlgorithmOptimizer:
    """유전 알고리즘 기반 DWTA 최적화기"""
    
    def __init__(self, config, population_size=200, generations=100, mutation_rate=0.15):
        """
        GA 파라미터 (공정한 비교를 위해 증가):
        - population_size: 200 (다양성 대폭 증가)
        - generations: 100 (충분한 수렴 시간)
        - mutation_rate: 0.15 (15% 돌연변이율)
        
        총 평가 횟수: 200 × 100 = 20,000번 (MIP와 비교 가능한 수준)
        """
        self.config = config
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        
        self.model = None
        self.variables = {}
        self.constraints = {}
        self.objective_value = 0
        self.solve_time = 0
        self.status = "NOT_SOLVED"
        self.convergence_history = []
        
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
        """GA 모델 생성 - 데이터 구조 초기화"""
        
        # Enhanced Engagement Matrix 처리
        if hasattr(engagement_matrix, 'is_feasible'):
            self.engagement_matrix_cache = engagement_matrix
            print("[OK] Enhanced Engagement Matrix 사용 (GA)")
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
        
        print(f"GA setup: {len(assets)} assets, {len(self.upper_systems)} upper, {len(self.lower_systems)} lower systems, {len(threats)} threats")
        print(f"GA parameters: population={self.population_size}, generations={self.generations}, mutation_rate={self.mutation_rate}")
    
    def set_intercept_probabilities(self, intercept_probs):
        """몬테카를로 시뮬레이션에서 샘플링된 요격확률 설정"""
        self.custom_intercept_probs = intercept_probs.copy()
        print(f"GA Optimizer: Set custom intercept probabilities for {len(intercept_probs)} threats")
    
    def solve(self):
        """진짜 유전 알고리즘 실행 (Population-based Evolution)"""
        start_time = timeit.default_timer()
        
        # 🔧 위협이 없으면 빈 결과 반환
        if not self.threats:
            return {
                'feasible': True,
                'objective_value': 0.0,
                'solve_time': 0.0,
                'upper_assignments': {},
                'lower_assignments': {},
                'algorithm': 'GA',
                'status': 'NO_THREATS'
            }
        
        try:
            # 초기 개체군 생성
            population = [self._create_random_individual() for _ in range(self.population_size)]
            
            # 진화 과정
            best_individual = None
            best_fitness = float('inf')
            
            for generation in range(self.generations):
                # Fitness 평가
                fitness_scores = []
                for individual in population:
                    fitness = self._evaluate_fitness(individual)
                    fitness_scores.append(fitness)
                    
                    # 최고 개체 추적
                    if fitness < best_fitness:
                        best_fitness = fitness
                        best_individual = individual.copy()
                
                # 수렴 기록
                avg_fitness = sum(fitness_scores) / len(fitness_scores)
                self.convergence_history.append({
                    'generation': generation,
                    'best_fitness': best_fitness,
                    'avg_fitness': avg_fitness
                })
                
                # 새로운 세대 생성
                new_population = []
                
                # Elitism: 상위 5% 보존 (공정한 비교를 위해)
                elite_count = max(1, int(self.population_size * 0.05))
                elite_indices = sorted(range(len(fitness_scores)), key=lambda i: fitness_scores[i])[:elite_count]
                for idx in elite_indices:
                    new_population.append(population[idx].copy())
                
                # 나머지 개체 생성
                while len(new_population) < self.population_size:
                    # Tournament Selection
                    parent1 = self._tournament_selection(population, fitness_scores)
                    parent2 = self._tournament_selection(population, fitness_scores)
                    
                    # Crossover
                    if random.random() < 0.8:  # 80% crossover rate
                        child = self._crossover(parent1, parent2)
                    else:
                        child = parent1.copy()
                    
                    # Mutation
                    if random.random() < self.mutation_rate:
                        child = self._mutate(child)
                    
                    # 지역 탐색 (10% 확률로 목적함수 기반 개선)
                    if random.random() < 0.1:
                        child = self._local_search(child)
                    
                    new_population.append(child)
                
                population = new_population
            
            self.solve_time = timeit.default_timer() - start_time
            
            # 최종 결과
            upper_assignments = best_individual['upper']
            lower_assignments = best_individual['lower']
            self.objective_value = best_fitness
            self.status = "OPTIMAL"
            
            # 🆕 Diagnosis 정보 생성
            total_assignments = len(upper_assignments) + len(lower_assignments)
            num_threats = len(self.threats)
            
            return {
                'feasible': True,
                'objective_value': self.objective_value,
                'solve_time': self.solve_time,
                'upper_assignments': upper_assignments,
                'lower_assignments': lower_assignments,
                'algorithm': 'GA',
                'status': self.status,
                'convergence_history': self.convergence_history,
                'diagnosis': {
                    'solver_status': 'Optimal',
                    'num_variables': total_assignments,
                    'num_constraints': 0,
                    'num_threats': num_threats,
                    'total_missiles': sum(b.get('available_missiles', 0) for b in self.batteries),
                    'feasible_engagements': total_assignments,
                    'time_limit_reached': False
                }
            }
        
        except Exception as e:
            # 🔧 예외 발생 시 적절한 에러 메시지와 함께 반환
            print(f"GA Optimizer Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'feasible': False,
                'objective_value': float('inf'),
                'solve_time': timeit.default_timer() - start_time,
                'upper_assignments': {},
                'lower_assignments': {},
                'algorithm': 'GA',
                'status': f'ERROR: {type(e).__name__}: {e}',
                'diagnosis': {
                    'solver_status': 'Error',
                    'num_variables': 0,
                    'num_constraints': 0,
                    'num_threats': len(self.threats) if hasattr(self, 'threats') else 0,
                    'total_missiles': sum(b.get('available_missiles', 0) for b in self.batteries) if hasattr(self, 'batteries') else 0,
                    'feasible_engagements': 0,
                    'time_limit_reached': False
                }
            }
    
    def _create_random_individual(self):
        """랜덤 개체 생성 (제약 조건 준수)"""
        upper_assignments = {}
        lower_assignments = {}
        
        # 🔧 OPTIMIZED Phase 1: 배터리 스펙 캐싱
        battery_id_to_idx = {b['id']: idx for idx, b in enumerate(self.batteries)}
        battery_specs_cache = np.array([
            b['specs']['battery_config'].get('simultaneous_engagements', 3)
            for b in self.batteries
        ], dtype=np.uint8)
        
        # 🔧 OPTIMIZED Phase 2: NumPy 배열 기반 용량 추적
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
        
        for threat in self.threats:
            threat_id = getattr(threat, 'id', '')
            target_asset_id = getattr(threat, 'target_asset_id', '')
            key = f"{target_asset_id}_{threat_id}"
            
            # ✅ 개선 1: 70% 확률로 상층 할당 시도 (다양성 확보)
            # 1단계: LSAM 할당 (상층)
            if random.random() < 0.7 and key not in upper_assignments and upper_assignment_count < max_upper_assignments:
                feasible_lsam = self._get_feasible_systems(self.upper_systems, threat_id, battery_usage, battery_capacity, battery_engagement_count, battery_id_to_idx, battery_specs_cache)
                if feasible_lsam:
                    # ✅ 개선 2: k-factor 기반 가중 랜덤 선택
                    scored_systems = []
                    for sys in feasible_lsam:
                        k = self._get_k_factor(getattr(sys, 'id', ''), threat_id)
                        scored_systems.append((sys, k))
                    
                    # k-factor에 비례하는 확률로 선택
                    systems = [sys for sys, _ in scored_systems]
                    weights = [k for _, k in scored_systems]
                    selected = random.choices(systems, weights=weights)[0]
                    
                    selected_id = getattr(selected, 'id', '')
                    upper_assignments[key] = selected_id
                    bat_idx = battery_id_to_idx[selected_id]
                    battery_usage[bat_idx] += 2  # missiles_per_engagement = 2
                    battery_engagement_count[bat_idx] += 1
                    upper_assigned[threat_id] = selected_id
                    upper_assignment_count += 1
            
            # ✅ 개선 3: 다층 방어 활성화 (70% 확률로 하층도 시도)
            if threat_id in upper_assigned:
                if random.random() < 0.3:  # 30% 확률로 하층 건너뛰기
                    continue
                # 70% 확률로 하층도 할당 시도 (다층 방어)
            
            # 2단계: MSAM 할당 (하층)
            if random.random() < 0.7 and key not in lower_assignments and lower_assignment_count < max_lower_assignments:
                feasible_msam = self._get_feasible_systems(self.lower_systems, threat_id, battery_usage, battery_capacity, battery_engagement_count, battery_id_to_idx, battery_specs_cache)
                if feasible_msam:
                    # ✅ 개선 2: k-factor 기반 가중 랜덤 선택
                    scored_systems = []
                    for sys in feasible_msam:
                        k = self._get_k_factor(getattr(sys, 'id', ''), threat_id)
                        scored_systems.append((sys, k))
                    
                    systems = [sys for sys, _ in scored_systems]
                    weights = [k for _, k in scored_systems]
                    selected = random.choices(systems, weights=weights)[0]
                    
                    selected_id = getattr(selected, 'id', '')
                    lower_assignments[key] = selected_id
                    bat_idx = battery_id_to_idx[selected_id]
                    battery_usage[bat_idx] += 2  # missiles_per_engagement = 2
                    battery_engagement_count[bat_idx] += 1
                    lower_assigned[threat_id] = selected_id
                    lower_assignment_count += 1
        
        return {'upper': upper_assignments, 'lower': lower_assignments}
    
    def _get_feasible_systems(self, systems, threat_id, battery_usage, battery_capacity, battery_engagement_count, battery_id_to_idx, battery_specs_cache):
        """교전 가능하고 용량이 남은 시스템 목록 반환 (동시 교전 제약 포함)"""
        feasible = []
        for system in systems:
            system_id = getattr(system, 'id', '')
            
            # 교전 가능 여부
            if self.engagement_matrix_cache:
                is_feasible = self.engagement_matrix_cache.is_feasible(system_id, threat_id)
            else:
                is_feasible = self.engagement_matrix.get((system_id, threat_id), False)
            
            if not is_feasible:
                continue
            
            # 🔧 OPTIMIZED: 배열 인덱싱으로 용량 확인 (O(1))
            bat_idx = battery_id_to_idx[system_id]
            if battery_usage[bat_idx] >= battery_capacity[bat_idx]:
                continue
            
            # 🔧 OPTIMIZED: 캐시된 스펙으로 동시 교전 제약 확인 (O(1))
            if battery_engagement_count[bat_idx] >= battery_specs_cache[bat_idx]:
                continue
            
            feasible.append(system)
        
        return feasible
    
    def _evaluate_fitness(self, individual):
        """Fitness 평가 (목적함수 = 기댓값 손실) + 제약 위반 페널티"""
        # 상층/하층 할당 개수 체크
        upper_count = len(individual['upper'])
        lower_count = len(individual['lower'])
        
        # 최대 할당 개수 동적 계산
        battery_id_to_idx = {b['id']: idx for idx, b in enumerate(self.batteries)}
        battery_specs_cache = np.array([
            b['specs']['battery_config'].get('simultaneous_engagements', 3)
            for b in self.batteries
        ], dtype=np.uint8)
        
        max_upper_assignments = sum(
            battery_specs_cache[battery_id_to_idx[getattr(sys, 'id', '')]]
            for sys in self.upper_systems
        )
        max_lower_assignments = sum(
            battery_specs_cache[battery_id_to_idx[getattr(sys, 'id', '')]]
            for sys in self.lower_systems
        )
        
        # 제약 위반 시 큰 페널티 (최악의 fitness)
        if upper_count > max_upper_assignments or lower_count > max_lower_assignments:
            return 999999.0  # 매우 나쁜 fitness (최소화 문제)
        
        return self._calculate_objective(individual['upper'], individual['lower'])
    
    def _tournament_selection(self, population, fitness_scores, tournament_size=3):
        """Tournament Selection"""
        tournament_indices = random.sample(range(len(population)), min(tournament_size, len(population)))
        best_idx = min(tournament_indices, key=lambda i: fitness_scores[i])
        return population[best_idx].copy()
    
    def _crossover(self, parent1, parent2):
        """Uniform Crossover (각 할당을 독립적으로 교환)"""
        child = {'upper': {}, 'lower': {}}
        
        # Upper assignments crossover
        all_upper_keys = set(parent1['upper'].keys()) | set(parent2['upper'].keys())
        for key in all_upper_keys:
            if random.random() < 0.5 and key in parent1['upper']:
                child['upper'][key] = parent1['upper'][key]
            elif key in parent2['upper']:
                child['upper'][key] = parent2['upper'][key]
            elif key in parent1['upper']:
                child['upper'][key] = parent1['upper'][key]
        
        # Lower assignments crossover
        all_lower_keys = set(parent1['lower'].keys()) | set(parent2['lower'].keys())
        for key in all_lower_keys:
            if random.random() < 0.5 and key in parent1['lower']:
                child['lower'][key] = parent1['lower'][key]
            elif key in parent2['lower']:
                child['lower'][key] = parent2['lower'][key]
            elif key in parent1['lower']:
                child['lower'][key] = parent1['lower'][key]
        
        return child
    
    def _mutate(self, individual):
        """Mutation (일부 할당을 랜덤하게 재할당)"""
        mutated = {'upper': individual['upper'].copy(), 'lower': individual['lower'].copy()}
        
        # 20% 확률로 각 할당 변경
        if self.threats and random.random() < 0.3:
            threat = random.choice(self.threats)
            threat_id = getattr(threat, 'id', '')
            target_asset_id = getattr(threat, 'target_asset_id', '')
            key = f"{target_asset_id}_{threat_id}"
            
            # 🔧 배터리 인덱스 및 스펙 캐시 생성
            battery_id_to_idx = {b['id']: idx for idx, b in enumerate(self.batteries)}
            battery_specs_cache = np.array([
                b['specs']['battery_config'].get('simultaneous_engagements', 3)
                for b in self.batteries
            ], dtype=np.uint8)
            
            # 🔧 NumPy 배열 기반 용량 추적 (딕셔너리 대신)
            n_batteries = len(self.batteries)
            battery_usage = np.zeros(n_batteries, dtype=np.uint8)
            battery_capacity = np.array([
                b.get('available_missiles', 10) for b in self.batteries
            ], dtype=np.uint8)
            battery_engagement_count = np.zeros(n_batteries, dtype=np.uint8)
            
            # Upper mutation
            feasible_lsam = self._get_feasible_systems(self.upper_systems, threat_id, battery_usage, battery_capacity, battery_engagement_count, battery_id_to_idx, battery_specs_cache)
            if feasible_lsam:
                mutated['upper'][key] = getattr(random.choice(feasible_lsam), 'id', '')
            
            # Lower mutation
            feasible_msam = self._get_feasible_systems(self.lower_systems, threat_id, battery_usage, battery_capacity, battery_engagement_count, battery_id_to_idx, battery_specs_cache)
            if feasible_msam:
                mutated['lower'][key] = getattr(random.choice(feasible_msam), 'id', '')
        
        return mutated
    
    def _local_search(self, individual):
        """
        지역 탐색 (Local Search) - 목적함수 기반 개선
        현재 할당에서 작은 변경을 시도하여 목적함수를 개선
        """
        current_fitness = self._evaluate_fitness(individual)
        improved = individual.copy()
        
        # 몇 개의 위협에 대해 재할당 시도
        num_attempts = min(5, len(self.threats))
        threats_to_try = random.sample(self.threats, num_attempts)
        
        for threat in threats_to_try:
            threat_id = getattr(threat, 'id', '')
            target_asset_id = getattr(threat, 'target_asset_id', '')
            key = f"{target_asset_id}_{threat_id}"
            
            # 현재 할당 저장
            old_upper = improved['upper'].get(key)
            old_lower = improved['lower'].get(key)
            
            # 배터리 캐시 생성
            battery_id_to_idx = {b['id']: idx for idx, b in enumerate(self.batteries)}
            battery_specs_cache = np.array([
                b['specs']['battery_config'].get('simultaneous_engagements', 3)
                for b in self.batteries
            ], dtype=np.uint8)
            
            n_batteries = len(self.batteries)
            battery_usage = np.zeros(n_batteries, dtype=np.uint8)
            battery_capacity = np.array([
                b.get('available_missiles', 10) for b in self.batteries
            ], dtype=np.uint8)
            battery_engagement_count = np.zeros(n_batteries, dtype=np.uint8)
            
            # 상층 재할당 시도
            feasible_lsam = self._get_feasible_systems(
                self.upper_systems, threat_id, battery_usage, 
                battery_capacity, battery_engagement_count, 
                battery_id_to_idx, battery_specs_cache
            )
            
            if feasible_lsam:
                # k-factor 최대 시스템 선택 (greedy하게)
                best_sys = max(feasible_lsam, 
                              key=lambda s: self._get_k_factor(getattr(s, 'id', ''), threat_id))
                improved['upper'][key] = getattr(best_sys, 'id', '')
                
                # 개선되었는지 확인
                new_fitness = self._evaluate_fitness(improved)
                if new_fitness >= current_fitness:
                    # 개선 안 됨 - 원래대로
                    if old_upper:
                        improved['upper'][key] = old_upper
                    elif key in improved['upper']:
                        del improved['upper'][key]
                else:
                    current_fitness = new_fitness
            
            # 하층 재할당 시도
            feasible_msam = self._get_feasible_systems(
                self.lower_systems, threat_id, battery_usage,
                battery_capacity, battery_engagement_count,
                battery_id_to_idx, battery_specs_cache
            )
            
            if feasible_msam:
                best_sys = max(feasible_msam,
                              key=lambda s: self._get_k_factor(getattr(s, 'id', ''), threat_id))
                improved['lower'][key] = getattr(best_sys, 'id', '')
                
                new_fitness = self._evaluate_fitness(improved)
                if new_fitness >= current_fitness:
                    if old_lower:
                        improved['lower'][key] = old_lower
                    elif key in improved['lower']:
                        del improved['lower'][key]
                else:
                    current_fitness = new_fitness
        
        return improved
    
    def _calculate_objective(self, upper_assignments, lower_assignments):
        """
        목적함수 계산: MIP와 동일한 방식
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
            'objective_value': self.objective_value,
            'population_size': self.population_size,
            'generations': self.generations
        }
