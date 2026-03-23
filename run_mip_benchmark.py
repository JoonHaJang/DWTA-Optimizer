"""
MIP Solver Benchmark Script (논문 실험 데이터 수집용)
=====================================================
GUI 없이 MIP 솔버의 create_model + solve 성능을 규모별로 측정.

측정 항목:
- create_model() 소요 시간
- solve() 소요 시간
- 변수 수, 제약 수
- 최적성 갭, 풀이 상태
- Probing 고정 변수 수

사용법:
    python run_mip_benchmark.py
"""

import sys
import os
import io
import time
import json
import statistics
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

# UTF-8 출력 강제
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 프로젝트 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_mip import MIPConfig, MIPSolverConfig
from nonlinear_mip_optimizer import NonLinearMIPOptimizer


@dataclass
class BenchmarkResult:
    """단일 벤치마크 실행 결과"""
    scenario: str
    num_threats: int
    num_assets: int
    num_batteries: int

    # 모델 규모
    num_variables: int = 0
    num_constraints: int = 0

    # 시간 측정
    build_time_ms: float = 0.0
    solve_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # 솔버 결과
    feasible: bool = False
    status: str = ""
    objective_value: float = float('inf')
    gap: float = -1.0

    # 내부 기법
    probing_fixed: int = 0
    warmstart_applied: bool = False


def create_simple_objects(assets_data, batteries_data, threats_data):
    """딕셔너리 데이터를 간단한 객체로 변환 (optimizer 호환용)"""

    class SimpleObj:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)
        def __repr__(self):
            return f"<{getattr(self, 'id', '?')}>"

    assets = []
    for a in assets_data:
        obj = SimpleObj(a)
        if not hasattr(obj, 'weighted_value'):
            obj.weighted_value = obj.value
        assets.append(obj)

    batteries = batteries_data  # 딕셔너리 리스트 그대로 전달

    threats = []
    for t in threats_data:
        obj = SimpleObj(t)
        # 필수 속성 보장
        if not hasattr(obj, 'current_position'):
            launch_pos = getattr(obj, 'launch_position', (0, 100))
            obj.current_position = (launch_pos[0], launch_pos[1], 50.0)
        if not hasattr(obj, 'flight_time_elapsed'):
            obj.flight_time_elapsed = 0.0
        if not hasattr(obj, 'specs'):
            obj.specs = {}
        threats.append(obj)

    # 요격 시스템 객체 생성
    interceptor_systems = []
    for bat in batteries_data:
        sys_obj = SimpleObj({
            'id': bat['id'],
            'system_type': bat['system_type'],
            'layer': bat['layer'],
            'position': bat['position'],
            'engagement_range': bat['coverage_radius_km'],
            'available_missiles': bat['specs']['battery_config']['total_missiles']
        })
        interceptor_systems.append(sys_obj)

    return assets, batteries, threats, interceptor_systems


def run_single_benchmark(scenario_type: str, config: MIPConfig) -> Optional[BenchmarkResult]:
    """단일 시나리오 벤치마크 실행"""

    try:
        # 시나리오 데이터 생성
        scenario = config.create_realistic_scenario(scenario_type)
        assets_data = scenario['assets']
        batteries_data = scenario['batteries']
        threats_data = scenario['threats']

        # 객체 변환
        assets, batteries, threats, interceptor_systems = create_simple_objects(
            assets_data, batteries_data, threats_data
        )

        result = BenchmarkResult(
            scenario=scenario_type,
            num_threats=len(threats),
            num_assets=len(assets),
            num_batteries=len(batteries)
        )

        # MIP 옵티마이저 생성
        optimizer = NonLinearMIPOptimizer(config)

        # 교전 매트릭스 생성 (간단 버전: 거리 기반)
        engagement_matrix = {}
        for bat in batteries:
            bat_id = bat['id']
            bat_pos = bat['position']
            bat_range = bat['coverage_radius_km']
            for t_obj in threats:
                t_id = t_obj.id
                t_pos = getattr(t_obj, 'launch_position', (0, 100))
                dist = ((bat_pos[0] - t_pos[0])**2 + (bat_pos[1] - t_pos[1])**2)**0.5
                # 거리 기반 교전 가능성 판정
                engagement_matrix[(bat_id, t_id)] = dist <= bat_range * 2

        optimizer.engagement_matrix = engagement_matrix
        optimizer.battery_specs = {bat['id']: bat['specs'] for bat in batteries}

        # === 모델 구축 시간 측정 ===
        build_start = time.perf_counter()
        try:
            optimizer.create_model(
                assets=assets,
                interceptor_systems=interceptor_systems,
                threats=threats,
                batteries=batteries,
                engagement_matrix=engagement_matrix
            )
            build_time = (time.perf_counter() - build_start) * 1000  # ms
        except Exception as e:
            print(f"  [WARNING] create_model failed: {e}")
            result.build_time_ms = (time.perf_counter() - build_start) * 1000
            result.status = f"BUILD_ERROR: {str(e)[:50]}"
            return result

        result.build_time_ms = build_time

        # 모델 규모 기록
        if optimizer.model:
            result.num_variables = optimizer.model.numVariables()
            result.num_constraints = len(optimizer.model.constraints)

        # === 솔버 풀이 시간 측정 ===
        solve_start = time.perf_counter()
        try:
            solve_result = optimizer.solve()
            solve_time = (time.perf_counter() - solve_start) * 1000  # ms
        except Exception as e:
            print(f"  [WARNING] solve failed: {e}")
            result.solve_time_ms = (time.perf_counter() - solve_start) * 1000
            result.status = f"SOLVE_ERROR: {str(e)[:50]}"
            return result

        result.solve_time_ms = solve_time
        result.total_time_ms = build_time + solve_time
        result.feasible = solve_result.get('feasible', False)
        result.status = solve_result.get('status', 'Unknown')
        result.objective_value = solve_result.get('objective_value', float('inf'))
        result.warmstart_applied = solve_result.get('warmstart_applied', False)

        # 진단 정보
        diag = solve_result.get('diagnosis', {})
        result.num_variables = diag.get('num_variables', result.num_variables)
        result.num_constraints = diag.get('num_constraints', result.num_constraints)

        return result

    except Exception as e:
        print(f"  [ERROR] {scenario_type}: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_benchmark_suite(scenarios: List[str], repeats: int = 3) -> Dict:
    """전체 벤치마크 스위트 실행"""

    config = MIPConfig()
    all_results = {}

    print("=" * 90)
    print(f"  MIP Solver Benchmark Suite")
    print(f"  시나리오: {len(scenarios)}개, 반복: {repeats}회")
    print(f"  솔버: HiGHS (primary) / CBC (fallback)")
    print(f"  시간 제한: 5초, 최적성 갭: 1%, 스레드: 4")
    print("=" * 90)

    for scenario_type in scenarios:
        print(f"\n[{scenario_type}] 벤치마크 시작...")

        results = []
        for run in range(repeats):
            print(f"  Run {run+1}/{repeats}...", end=" ", flush=True)
            result = run_single_benchmark(scenario_type, config)
            if result:
                results.append(result)
                print(f"✓ {result.total_time_ms:.1f}ms "
                      f"(build={result.build_time_ms:.1f}, solve={result.solve_time_ms:.1f}) "
                      f"vars={result.num_variables}, cons={result.num_constraints} "
                      f"{'Optimal' if result.feasible else result.status}")
            else:
                print(f"✗ Failed")

        if results:
            # 통계 계산
            build_times = [r.build_time_ms for r in results]
            solve_times = [r.solve_time_ms for r in results]
            total_times = [r.total_time_ms for r in results]

            summary = {
                'scenario': scenario_type,
                'num_threats': results[0].num_threats,
                'num_assets': results[0].num_assets,
                'num_batteries': results[0].num_batteries,
                'runs': repeats,
                'successful_runs': len(results),

                'avg_variables': statistics.mean([r.num_variables for r in results]),
                'avg_constraints': statistics.mean([r.num_constraints for r in results]),

                'avg_build_ms': statistics.mean(build_times),
                'avg_solve_ms': statistics.mean(solve_times),
                'avg_total_ms': statistics.mean(total_times),
                'max_total_ms': max(total_times),
                'min_total_ms': min(total_times),
                'std_total_ms': statistics.stdev(total_times) if len(total_times) > 1 else 0,

                'feasible_rate': sum(1 for r in results if r.feasible) / len(results) * 100,
                'avg_objective': statistics.mean([r.objective_value for r in results if r.feasible]) if any(r.feasible for r in results) else None,

                'raw_results': [asdict(r) for r in results]
            }
            all_results[scenario_type] = summary

            print(f"  → 평균: {summary['avg_total_ms']:.1f}ms "
                  f"(build={summary['avg_build_ms']:.1f} + solve={summary['avg_solve_ms']:.1f}), "
                  f"vars={summary['avg_variables']:.0f}, cons={summary['avg_constraints']:.0f}, "
                  f"feasible={summary['feasible_rate']:.0f}%")

    return all_results


def print_summary_table(results: Dict):
    """결과 요약 테이블 출력 (논문 Table 1 형식)"""

    print("\n" + "=" * 120)
    print("  Table 1: 규모별 MIP Solver 성능 (Benchmark)")
    print("=" * 120)
    print(f"{'시나리오':<16} {'위협':>4} {'자산':>4} {'포대':>4} │ {'변수':>6} {'제약':>6} │ "
          f"{'build(ms)':>10} {'solve(ms)':>10} {'total(ms)':>10} {'max(ms)':>10} │ "
          f"{'Feasible':>8} {'Objective':>10}")
    print("─" * 120)

    for key, s in results.items():
        obj_str = f"{s['avg_objective']:.4f}" if s['avg_objective'] is not None else "N/A"
        print(f"{s['scenario']:<16} {s['num_threats']:>4} {s['num_assets']:>4} {s['num_batteries']:>4} │ "
              f"{s['avg_variables']:>6.0f} {s['avg_constraints']:>6.0f} │ "
              f"{s['avg_build_ms']:>10.1f} {s['avg_solve_ms']:>10.1f} {s['avg_total_ms']:>10.1f} {s['max_total_ms']:>10.1f} │ "
              f"{s['feasible_rate']:>7.0f}% {obj_str:>10}")

    print("=" * 120)


def main():
    """메인 벤치마크 실행"""

    # 벤치마크 대상 시나리오 (확장성 테스트)
    scenarios = [
        "SMALL_3",
        "SMALL_5",
        "SMALL_8",
        "MEDIUM_10",
        "BASELINE_15",
        "MEDIUM_20",
        "DWTA_BALANCED",
        "HEAVY_30",
        "LARGE_40",
        "STRESS_100",
    ]

    # 실행 (각 3회 반복)
    results = run_benchmark_suite(scenarios, repeats=3)

    # 요약 테이블 출력
    print_summary_table(results)

    # 결과 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"mip_benchmark_{timestamp}.json"
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_file)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'scenarios': list(results.keys()),
            'results': results
        }, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n결과 저장: {output_file}")
    return results


if __name__ == "__main__":
    main()
