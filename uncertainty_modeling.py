"""
불확실성 모델링 및 몬테카를로 시뮬레이션 모듈
====================================================
요격 확률의 불확실성을 베타/정규 분포로 모델링하고
몬테카를로 시뮬레이션을 통한 통계적 신뢰성 분석
"""

import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

@dataclass
class UncertaintyConfig:
    """불확실성 모델링 설정"""
    distribution_type: str = "beta"  # "beta" or "normal"
    beta_alpha: float = 9.0  # 베타 분포 α 파라미터
    beta_beta: float = 1.0   # 베타 분포 β 파라미터
    normal_std: float = 0.05  # 정규 분포 표준편차
    monte_carlo_runs: int = 50  # 몬테카를로 반복 횟수
    confidence_level: float = 0.95  # 신뢰구간 수준

class UncertaintyModeling:
    """불확실성 모델링 및 몬테카를로 시뮬레이션"""
    
    def __init__(self, config: UncertaintyConfig = None):
        self.config = config or UncertaintyConfig()
        self.simulation_results = []
        self.statistical_summary = {}
        
    def sample_intercept_probability(self, base_probability: float) -> float:
        """기본 요격 확률에서 불확실성을 고려한 베타 분포 샘플링"""
        if self.config.distribution_type == "beta":
            # 베타 분포에서 직접 샘플링 (GUI와 동일한 방식)
            alpha = self.config.beta_alpha
            beta = self.config.beta_beta
            sampled = np.random.beta(alpha, beta)
            return sampled
            
        elif self.config.distribution_type == "normal":
            # 정규 분포: 평균을 기본 확률로, 표준편차는 설정값
            sampled = np.random.normal(base_probability, self.config.normal_std)
            # [0,1] 범위로 클리핑
            sampled = np.clip(sampled, 0.0, 1.0)
            
        else:
            # 기본값: 고정 확률
            sampled = base_probability
            
        return sampled
    
    def run_monte_carlo_simulation(self, simulation_function, *args, **kwargs) -> Dict:
        """몬테카를로 시뮬레이션 실행"""
        print(f"\n=== 몬테카를로 시뮬레이션 시작 ===")
        print(f"반복 횟수: {self.config.monte_carlo_runs}")
        print(f"분포 타입: {self.config.distribution_type}")
        
        results = []
        objective_values = []
        success_rates = []
        
        for run in range(self.config.monte_carlo_runs):
            print(f"Run {run+1}/{self.config.monte_carlo_runs}...", end=" ")
            
            try:
                # 시뮬레이션 실행
                result = simulation_function(*args, **kwargs)
                
                if result:
                    results.append(result)
                    objective_values.append(result.get('objective_value', 0))
                    success_rates.append(result.get('success_rate', 0))
                    print(f"완료 (목적함수: {result.get('objective_value', 0):.2f})")
                else:
                    print("실패")
                    
            except Exception as e:
                print(f"오류: {e}")
                continue
        
        # 통계 분석
        if objective_values:
            stats_summary = self._calculate_statistics(objective_values, success_rates)
            print(f"\n=== 몬테카를로 시뮬레이션 완료 ===")
            print(f"성공한 실행: {len(results)}/{self.config.monte_carlo_runs}")
            print(f"목적함수 평균: {stats_summary['objective_mean']:.3f} ± {stats_summary['objective_std']:.3f}")
            print(f"성공률 평균: {stats_summary['success_rate_mean']:.1f}% ± {stats_summary['success_rate_std']:.1f}%")
            
            return {
                'results': results,
                'statistics': stats_summary,
                'config': self.config.__dict__
            }
        else:
            print("모든 시뮬레이션이 실패했습니다.")
            return None
    
    def _calculate_statistics(self, objective_values: List[float], success_rates: List[float]) -> Dict:
        """통계 분석 수행"""
        obj_array = np.array(objective_values)
        success_array = np.array(success_rates) * 100  # 백분율로 변환
        
        # 기본 통계
        stats_summary = {
            'objective_mean': np.mean(obj_array),
            'objective_std': np.std(obj_array),
            'objective_min': np.min(obj_array),
            'objective_max': np.max(obj_array),
            'objective_median': np.median(obj_array),
            'success_rate_mean': np.mean(success_array),
            'success_rate_std': np.std(success_array),
            'success_rate_min': np.min(success_array),
            'success_rate_max': np.max(success_array),
        }
        
        # 신뢰구간 계산
        confidence = self.config.confidence_level
        alpha = 1 - confidence
        
        # 목적함수 신뢰구간
        obj_ci = stats.t.interval(confidence, len(obj_array)-1, 
                                 loc=np.mean(obj_array), 
                                 scale=stats.sem(obj_array))
        stats_summary['objective_ci_lower'] = obj_ci[0]
        stats_summary['objective_ci_upper'] = obj_ci[1]
        
        # 성공률 신뢰구간
        success_ci = stats.t.interval(confidence, len(success_array)-1,
                                     loc=np.mean(success_array),
                                     scale=stats.sem(success_array))
        stats_summary['success_rate_ci_lower'] = success_ci[0]
        stats_summary['success_rate_ci_upper'] = success_ci[1]
        
        return stats_summary
    
    def generate_uncertainty_report(self, results: Dict, output_file: str = None) -> str:
        """불확실성 분석 보고서 생성"""
        if not results:
            return "분석 결과가 없습니다."
        
        stats = results['statistics']
        config = results['config']
        
        report = f"""
=== DWTA 불확실성 분석 보고서 ===
생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

[시뮬레이션 설정]
- 분포 타입: {config['distribution_type']}
- 몬테카를로 반복: {config['monte_carlo_runs']}회
- 신뢰구간: {config['confidence_level']*100:.0f}%

[목적함수 분석]
- 평균: {stats['objective_mean']:.3f}
- 표준편차: {stats['objective_std']:.3f}
- 최솟값: {stats['objective_min']:.3f}
- 최댓값: {stats['objective_max']:.3f}
- 중앙값: {stats['objective_median']:.3f}
- {config['confidence_level']*100:.0f}% 신뢰구간: [{stats['objective_ci_lower']:.3f}, {stats['objective_ci_upper']:.3f}]

[성공률 분석]
- 평균: {stats['success_rate_mean']:.1f}%
- 표준편차: {stats['success_rate_std']:.1f}%
- 최솟값: {stats['success_rate_min']:.1f}%
- 최댓값: {stats['success_rate_max']:.1f}%
- {config['confidence_level']*100:.0f}% 신뢰구간: [{stats['success_rate_ci_lower']:.1f}%, {stats['success_rate_ci_upper']:.1f}%]

[통계적 해석]
- 목적함수 변동계수: {(stats['objective_std']/stats['objective_mean']*100):.1f}%
- 성공률 안정성: {'높음' if stats['success_rate_std'] < 5 else '보통' if stats['success_rate_std'] < 10 else '낮음'}
- 신뢰구간 폭: {stats['objective_ci_upper'] - stats['objective_ci_lower']:.3f}

[권고사항]
"""
        
        # 권고사항 추가
        cv = stats['objective_std']/stats['objective_mean']*100
        if cv < 10:
            report += "- 목적함수가 안정적입니다. 현재 설정을 유지하세요.\n"
        elif cv < 20:
            report += "- 목적함수에 중간 수준의 변동이 있습니다. 추가 분석을 고려하세요.\n"
        else:
            report += "- 목적함수 변동이 큽니다. 시스템 안정성 개선이 필요합니다.\n"
            
        if stats['success_rate_std'] > 10:
            report += "- 성공률 변동이 큽니다. 요격 시스템 신뢰성 검토가 필요합니다.\n"
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"보고서가 {output_file}에 저장되었습니다.")
        
        return report
    
    def plot_uncertainty_analysis(self, results: Dict, save_path: str = None):
        """불확실성 분석 결과 시각화"""
        if not results:
            print("분석 결과가 없습니다.")
            return
        
        objective_values = [r.get('objective_value', 0) for r in results['results']]
        success_rates = [r.get('success_rate', 0) * 100 for r in results['results']]
        
        # 한글 폰트 설정
        plt.rcParams['font.family'] = ['Malgun Gothic', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('DWTA Uncertainty Analysis Results', fontsize=16, fontweight='bold', y=0.95)
        
        # 목적함수 히스토그램
        ax1.hist(objective_values, bins=15, alpha=0.7, color='steelblue', edgecolor='black', linewidth=1.2)
        ax1.axvline(np.mean(objective_values), color='red', linestyle='--', linewidth=2,
                   label=f'Mean: {np.mean(objective_values):.3f}')
        ax1.set_xlabel('Objective Function Value', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax1.set_title('Objective Function Distribution', fontsize=14, fontweight='bold', pad=15)
        ax1.legend(fontsize=11)
        ax1.grid(True, alpha=0.4, linestyle='-', linewidth=0.5)
        ax1.tick_params(labelsize=10)
        
        # 성공률 히스토그램
        ax2.hist(success_rates, bins=15, alpha=0.7, color='forestgreen', edgecolor='black', linewidth=1.2)
        ax2.axvline(np.mean(success_rates), color='red', linestyle='--', linewidth=2,
                   label=f'Mean: {np.mean(success_rates):.1f}%')
        ax2.set_xlabel('Success Rate (%)', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax2.set_title('Success Rate Distribution', fontsize=14, fontweight='bold', pad=15)
        ax2.legend(fontsize=11)
        ax2.grid(True, alpha=0.4, linestyle='-', linewidth=0.5)
        ax2.tick_params(labelsize=10)
        
        # 목적함수 시계열
        ax3.plot(range(1, len(objective_values)+1), objective_values, 'b-o', 
                markersize=4, linewidth=2, markerfacecolor='lightblue', markeredgecolor='blue')
        ax3.axhline(np.mean(objective_values), color='red', linestyle='--', alpha=0.8, linewidth=2)
        ax3.set_xlabel('Simulation Run Number', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Objective Function Value', fontsize=12, fontweight='bold')
        ax3.set_title('Objective Function Time Series', fontsize=14, fontweight='bold', pad=15)
        ax3.grid(True, alpha=0.4, linestyle='-', linewidth=0.5)
        ax3.tick_params(labelsize=10)
        
        # 산점도: 목적함수 vs 성공률
        scatter = ax4.scatter(success_rates, objective_values, alpha=0.7, color='purple', 
                            s=50, edgecolors='darkviolet', linewidth=1)
        ax4.set_xlabel('Success Rate (%)', fontsize=12, fontweight='bold')
        ax4.set_ylabel('Objective Function Value', fontsize=12, fontweight='bold')
        ax4.set_title('Success Rate vs Objective Function', fontsize=14, fontweight='bold', pad=15)
        ax4.grid(True, alpha=0.4, linestyle='-', linewidth=0.5)
        ax4.tick_params(labelsize=10)
        
        # 레이아웃 조정
        plt.tight_layout(rect=[0, 0.03, 1, 0.93])
        plt.subplots_adjust(hspace=0.35, wspace=0.25)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
            print(f"그래프가 {save_path}에 저장되었습니다.")
        
        plt.show()

def test_uncertainty_modeling():
    """불확실성 모델링 테스트 함수"""
    print("=== 불확실성 모델링 테스트 ===")
    
    # 설정
    config = UncertaintyConfig(
        distribution_type="beta",
        monte_carlo_runs=30,
        confidence_level=0.95
    )
    
    uncertainty_model = UncertaintyModeling(config)
    
    # 간단한 시뮬레이션 함수 (실제 DWTA 시뮬레이션 대신)
    def mock_simulation():
        # 기본 요격 확률들
        base_probabilities = [0.95, 0.90, 0.85]
        
        # 불확실성을 고려한 샘플링
        sampled_probs = [uncertainty_model.sample_intercept_probability(p) 
                        for p in base_probabilities]
        
        # 모의 목적함수 계산
        objective_value = sum(sampled_probs) * np.random.uniform(0.8, 1.2)
        success_rate = np.mean(sampled_probs)
        
        return {
            'objective_value': objective_value,
            'success_rate': success_rate,
            'intercept_probabilities': sampled_probs
        }
    
    # 몬테카를로 시뮬레이션 실행
    results = uncertainty_model.run_monte_carlo_simulation(mock_simulation)
    
    if results:
        # 보고서 생성
        report = uncertainty_model.generate_uncertainty_report(results)
        print(report)
        
        # 시각화
        uncertainty_model.plot_uncertainty_analysis(results)
        
        return results
    else:
        print("테스트 실패")
        return None

if __name__ == "__main__":
    test_uncertainty_modeling()
