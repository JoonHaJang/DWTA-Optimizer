"""
Stress Test Metrics Collection System
======================================
MIP DWTA 솔버의 성능 메트릭 자동 수집 및 분석

사용법:
    tracker = StressTestMetrics()
    
    # 최적화 결과 기록
    tracker.record_optimization(result, solve_time)
    
    # 시뮬레이션 종료 시 리포트 생성
    report = tracker.generate_report()
    tracker.save_report("stress_test_report.json")
"""

import time
import json
import psutil
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class OptimizationMetrics:
    """단일 최적화 실행의 메트릭"""
    timestep: int
    solver_time: float
    num_variables: int
    num_constraints: int
    num_threats: int
    warmstart_applied: bool
    warmstart_count: int
    timeout: bool
    feasible: bool
    objective_value: float
    gap: Optional[float] = None


@dataclass
class StressTestMetrics:
    """Stress Test 전체 메트릭 수집 (연구 논문용 확장)"""
    
    scenario_name: str = ""
    algorithm: str = "McCormick"  # 🆕 알고리즘 비교용
    start_time: float = field(default_factory=time.time)
    
    # 수집된 메트릭
    solver_times: List[float] = field(default_factory=list)
    timeout_count: int = 0
    warmstart_count: int = 0
    total_optimizations: int = 0
    
    variables_history: List[int] = field(default_factory=list)
    constraints_history: List[int] = field(default_factory=list)
    
    memory_peak_mb: float = 0.0
    memory_samples: List[float] = field(default_factory=list)
    
    # 시뮬레이션 결과
    total_threats: int = 0
    intercepted_threats: int = 0
    missed_threats: int = 0
    deviated_threats: int = 0  # 🆕 궤적 이탈
    
    # 🆕 계층별 요격 통계
    upper_layer_intercepts: int = 0
    lower_layer_intercepts: int = 0
    
    # 🆕 위협 유형별 분석
    threat_type_breakdown: Dict[str, int] = field(default_factory=dict)
    
    # 🆕 자산 보호
    total_assets: int = 0
    assets_protected: int = 0
    
    # 🆕 미사일 효율성
    missiles_fired: int = 0
    missiles_available: int = 0
    
    # 🆕 추가 비교 지표 (연구 논문용)
    objective_values: List[float] = field(default_factory=list)  # 목적함수 값 기록
    assignment_changes: List[int] = field(default_factory=list)  # 할당 변경 횟수
    battery_usage: Dict[str, int] = field(default_factory=dict)  # 배터리별 사용 횟수
    infeasible_count: int = 0  # 실행 불가능 횟수
    
    # 상세 기록
    optimization_records: List[OptimizationMetrics] = field(default_factory=list)
    
    def record_optimization(self, result: Dict, solve_time: float, timestep: int):
        """최적화 결과 기록 (확장)"""
        self.total_optimizations += 1
        self.solver_times.append(solve_time)
        
        # 🆕 목적함수 값 기록
        obj_value = result.get('objective_value', float('inf'))
        if obj_value != float('inf'):
            self.objective_values.append(obj_value)
        
        # 🆕 실행 불가능 체크
        if not result.get('feasible', False):
            self.infeasible_count += 1
        
        # Timeout 체크
        diagnosis = result.get('diagnosis', {})
        if diagnosis.get('time_limit_reached', False):
            self.timeout_count += 1
        
        # Warm-start 체크
        if result.get('warmstart_applied', False):
            self.warmstart_count += 1
        
        # 변수/제약 수 기록
        num_vars = diagnosis.get('num_variables', 0)
        num_constraints = diagnosis.get('num_constraints', 0)
        self.variables_history.append(num_vars)
        self.constraints_history.append(num_constraints)
        
        # 메모리 샘플링
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        self.memory_samples.append(current_memory)
        self.memory_peak_mb = max(self.memory_peak_mb, current_memory)
        
        # 상세 기록 저장
        record = OptimizationMetrics(
            timestep=timestep,
            solver_time=solve_time,
            num_variables=num_vars,
            num_constraints=num_constraints,
            num_threats=diagnosis.get('num_threats', 0),
            warmstart_applied=result.get('warmstart_applied', False),
            warmstart_count=result.get('warmstart_count', 0),
            timeout=diagnosis.get('time_limit_reached', False),
            feasible=result.get('feasible', False),
            objective_value=result.get('objective_value', 0.0)
        )
        self.optimization_records.append(record)
    
    def record_simulation_result(self, intercepted: int, missed: int, total: int, 
                                   deviated: int = 0, upper_intercepts: int = 0, lower_intercepts: int = 0,
                                   threat_types: Dict[str, int] = None, assets_protected: int = 0, total_assets: int = 0,
                                   missiles_fired: int = 0, missiles_available: int = 0):
        """시뮬레이션 최종 결과 기록 (확장)"""
        self.intercepted_threats = intercepted
        self.missed_threats = missed
        self.total_threats = total
        self.deviated_threats = deviated
        self.upper_layer_intercepts = upper_intercepts
        self.lower_layer_intercepts = lower_intercepts
        self.threat_type_breakdown = threat_types or {}
        self.assets_protected = assets_protected
        self.total_assets = total_assets
        self.missiles_fired = missiles_fired
        self.missiles_available = missiles_available
    
    def generate_report(self) -> Dict:
        """성능 리포트 생성"""
        elapsed_time = time.time() - self.start_time
        
        # 통계 계산
        avg_solver_time = sum(self.solver_times) / len(self.solver_times) if self.solver_times else 0
        max_solver_time = max(self.solver_times) if self.solver_times else 0
        min_solver_time = min(self.solver_times) if self.solver_times else 0
        
        timeout_rate = (self.timeout_count / self.total_optimizations * 100) if self.total_optimizations > 0 else 0
        warmstart_rate = (self.warmstart_count / self.total_optimizations * 100) if self.total_optimizations > 0 else 0
        
        avg_variables = sum(self.variables_history) / len(self.variables_history) if self.variables_history else 0
        avg_constraints = sum(self.constraints_history) / len(self.constraints_history) if self.constraints_history else 0
        
        intercept_rate = (self.intercepted_threats / self.total_threats * 100) if self.total_threats > 0 else 0
        asset_protection_rate = (self.assets_protected / self.total_assets * 100) if self.total_assets > 0 else 0
        missile_efficiency = (self.intercepted_threats / self.missiles_fired * 100) if self.missiles_fired > 0 else 0
        
        # 🆕 확장성 지표
        time_per_threat = sum(self.solver_times) / self.total_threats if self.total_threats > 0 else 0
        time_per_optimization = avg_solver_time
        
        # 🆕 추가 비교 지표 계산
        # 해의 안정성
        import numpy as np
        objective_variance = np.var(self.objective_values) if len(self.objective_values) > 1 else 0.0
        objective_std = np.std(self.objective_values) if len(self.objective_values) > 1 else 0.0
        
        # 자원 활용도
        total_battery_usage = sum(self.battery_usage.values())
        num_batteries_used = len(self.battery_usage)
        battery_usage_balance = 1.0 - (np.std(list(self.battery_usage.values())) / np.mean(list(self.battery_usage.values()))) if self.battery_usage and np.mean(list(self.battery_usage.values())) > 0 else 0.0
        
        # 강건성
        success_rate = ((self.total_optimizations - self.infeasible_count) / self.total_optimizations * 100) if self.total_optimizations > 0 else 0.0
        infeasible_rate = (self.infeasible_count / self.total_optimizations * 100) if self.total_optimizations > 0 else 0.0
        
        # 계산 효율성
        memory_per_threat = (self.memory_peak_mb / self.total_threats) if self.total_threats > 0 else 0.0
        
        report = {
            'scenario': self.scenario_name,
            'timestamp': datetime.now().isoformat(),
            'elapsed_time_sec': elapsed_time,
            
            # 핵심 메트릭
            'solver_performance': {
                'avg_time_sec': avg_solver_time,
                'max_time_sec': max_solver_time,
                'min_time_sec': min_solver_time,
                'total_optimizations': self.total_optimizations,
                'timeout_count': self.timeout_count,
                'timeout_rate_pct': timeout_rate,
                'warmstart_count': self.warmstart_count,
                'warmstart_rate_pct': warmstart_rate
            },
            
            # 문제 규모
            'problem_scale': {
                'avg_variables': avg_variables,
                'max_variables': max(self.variables_history) if self.variables_history else 0,
                'avg_constraints': avg_constraints,
                'max_constraints': max(self.constraints_history) if self.constraints_history else 0
            },
            
            # 메모리 사용
            'memory_usage': {
                'peak_mb': self.memory_peak_mb,
                'avg_mb': sum(self.memory_samples) / len(self.memory_samples) if self.memory_samples else 0
            },
            
            # 시뮬레이션 결과 (확장)
            'simulation_result': {
                'total_threats': self.total_threats,
                'intercepted': self.intercepted_threats,
                'missed': self.missed_threats,
                'deviated': self.deviated_threats,
                'intercept_rate_pct': intercept_rate,
                'upper_layer_intercepts': self.upper_layer_intercepts,
                'lower_layer_intercepts': self.lower_layer_intercepts,
                'threat_type_breakdown': self.threat_type_breakdown
            },
            
            # 🆕 자산 보호
            'asset_protection': {
                'total_assets': self.total_assets,
                'protected': self.assets_protected,
                'damaged': self.total_assets - self.assets_protected,
                'protection_rate_pct': asset_protection_rate
            },
            
            # 🆕 미사일 효율성
            'missile_efficiency': {
                'fired': self.missiles_fired,
                'available': self.missiles_available,
                'efficiency_pct': missile_efficiency,
                'missiles_per_intercept': self.missiles_fired / self.intercepted_threats if self.intercepted_threats > 0 else 0
            },
            
            # 🆕 확장성 지표
            'scalability': {
                'time_per_threat': time_per_threat,
                'time_per_optimization': time_per_optimization,
                'threats_per_second': 1.0 / time_per_threat if time_per_threat > 0 else 0
            },
            
            # 🆕 알고리즘 정보
            'algorithm': self.algorithm,
            
            # 🆕 해의 안정성 (Solution Stability)
            'solution_stability': {
                'objective_variance': objective_variance,
                'objective_std': objective_std,
                'objective_mean': np.mean(self.objective_values) if self.objective_values else 0.0,
                'coefficient_of_variation': (objective_std / np.mean(self.objective_values) * 100) if self.objective_values and np.mean(self.objective_values) > 0 else 0.0
            },
            
            # 🆕 자원 활용도 (Resource Utilization)
            'resource_utilization': {
                'total_battery_usage': total_battery_usage,
                'num_batteries_used': num_batteries_used,
                'battery_usage_balance': battery_usage_balance,
                'battery_usage_detail': self.battery_usage
            },
            
            # 🆕 강건성 (Robustness)
            'robustness': {
                'success_rate_pct': success_rate,
                'infeasible_count': self.infeasible_count,
                'infeasible_rate_pct': infeasible_rate,
                'timeout_recovery_rate': ((self.total_optimizations - self.timeout_count) / self.total_optimizations * 100) if self.total_optimizations > 0 else 0.0
            },
            
            # 🆕 계산 효율성 (Computational Efficiency)
            'computational_efficiency': {
                'memory_per_threat_mb': memory_per_threat,
                'time_complexity_observed': time_per_threat / (self.total_threats ** 1.5) if self.total_threats > 1 else 0.0,  # 실측 복잡도 지수
                'throughput_threats_per_sec': 1.0 / time_per_threat if time_per_threat > 0 else 0.0
            },
            
            # 성능 등급
            'performance_grade': self._calculate_grade(avg_solver_time, timeout_rate),
            
            # 상세 기록 (옵션)
            'detailed_records': [asdict(r) for r in self.optimization_records[-10:]]  # 마지막 10개만
        }
        
        return report
    
    def _calculate_grade(self, avg_time: float, timeout_rate: float) -> str:
        """성능 등급 계산"""
        if avg_time < 0.5 and timeout_rate == 0:
            return "A+ (우수)"
        elif avg_time < 1.0 and timeout_rate < 5:
            return "A (양호)"
        elif avg_time < 2.0 and timeout_rate < 15:
            return "B (주의)"
        elif avg_time < 5.0 and timeout_rate < 30:
            return "C (한계)"
        else:
            return "D (불가)"
    
    def save_report(self, filename: str):
        """리포트를 JSON 파일로 저장"""
        report = self.generate_report()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[OK] Stress test report saved: {filename}")
    
    def print_summary(self):
        """콘솔에 요약 출력"""
        report = self.generate_report()
        
        print("\n" + "="*60)
        print(f"📊 STRESS TEST SUMMARY: {report['scenario']}")
        print("="*60)
        
        perf = report['solver_performance']
        print(f"\n⏱️  Solver Performance:")
        print(f"   Average Time: {perf['avg_time_sec']:.3f}s")
        print(f"   Max Time: {perf['max_time_sec']:.3f}s")
        print(f"   Timeout Rate: {perf['timeout_rate_pct']:.1f}% ({perf['timeout_count']}/{perf['total_optimizations']})")
        print(f"   Warm-start Rate: {perf['warmstart_rate_pct']:.1f}%")
        
        scale = report['problem_scale']
        print(f"\n📐 Problem Scale:")
        print(f"   Avg Variables: {scale['avg_variables']:.0f} (Max: {scale['max_variables']})")
        print(f"   Avg Constraints: {scale['avg_constraints']:.0f} (Max: {scale['max_constraints']})")
        
        mem = report['memory_usage']
        print(f"\n💾 Memory Usage:")
        print(f"   Peak: {mem['peak_mb']:.1f} MB")
        print(f"   Average: {mem['avg_mb']:.1f} MB")
        
        sim = report['simulation_result']
        print(f"\n🎯 Simulation Result:")
        print(f"   Intercept Rate: {sim['intercept_rate_pct']:.1f}% ({sim['intercepted']}/{sim['total_threats']})")
        print(f"   Upper Layer: {sim['upper_layer_intercepts']}, Lower Layer: {sim['lower_layer_intercepts']}")
        
        asset = report['asset_protection']
        print(f"\n🛡️  Asset Protection:")
        print(f"   Protected: {asset['protection_rate_pct']:.1f}% ({asset['protected']}/{asset['total_assets']})")
        
        missile = report['missile_efficiency']
        print(f"\n🚀 Missile Efficiency:")
        print(f"   Efficiency: {missile['efficiency_pct']:.1f}% ({missile['fired']} fired)")
        print(f"   Missiles per Intercept: {missile['missiles_per_intercept']:.2f}")
        
        scale = report['scalability']
        print(f"\n📈 Scalability:")
        print(f"   Time per Threat: {scale['time_per_threat']:.3f}s")
        print(f"   Throughput: {scale['threats_per_second']:.2f} threats/sec")
        
        print(f"\n🏆 Performance Grade: {report['performance_grade']}")
        print(f"🔬 Algorithm: {report['algorithm']}")
        print("="*60 + "\n")
