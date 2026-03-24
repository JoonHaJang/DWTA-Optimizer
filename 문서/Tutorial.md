# DWTA-Optimizer Tutorial

## 1. Project Overview

Dynamic Weapon-Target Assignment (DWTA) 최적화 시스템.
적 탄도 미사일 위협에 대해 방어 요격체계를 최적 할당하여 예상 피해를 최소화한다.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│           multi_missile_tracker_gui.py               │
│  ┌──────────────┐  ┌────────────────┐               │
│  │ DWTAMainWindow│  │MultiMissileTracker│            │
│  │  (PyQt5 GUI) │  │  (Simulation Engine)│           │
│  └──────┬───────┘  └────────┬────────┘              │
│         │                   │                        │
│         │    ┌──────────────┴──────────────┐        │
│         │    │     run_realtime_dwta()      │        │
│         │    │  _prepare_optimizer_inputs() │        │
│         │    │  _process_impact()           │        │
│         │    └──────────────┬──────────────┘        │
│         │                   │ 호출                   │
└─────────┼───────────────────┼───────────────────────┘
          │                   ▼
          │    ┌──────────────────────────┐
          │    │  clean_slate_optimizer.py │ ← 결정론적 해결사
          │    │  ga_optimizer.py          │
          │    │  greedy_optimizer.py      │
          │    └──────────────────────────┘
          │
          ▼
   ┌─────────────────┐
   │pyqtgraph_display│ ← 전술 시각화
   └─────────────────┘
```

### File Structure

| File | Role |
|------|------|
| `clean_slate_optimizer.py` | MIP 최적화 (HiGHS). 최적 할당 계산 |
| `multi_missile_tracker_gui.py` | 시뮬레이션 엔진 + PyQt5 GUI |
| `pyqtgraph_display.py` | PyQtGraph 전술 맵 위젯 |
| `config_mip.py` | 시나리오 + 시스템 설정 관리 |
| `config.py` | 기본 시뮬레이션 설정 (레이더, 무기체계) |
| `ga_optimizer.py` | Genetic Algorithm 옵티마이저 |
| `greedy_optimizer.py` | Greedy 옵티마이저 |
| `uncertainty_modeling.py` | Beta 분포 몬테카를로 불확실성 모델 |
| `scenario_dwta_balanced.py` | 벤치마크 시나리오 생성 |
| `stress_test_metrics.py` | 성능 메트릭 수집 |

---

## 2. Mathematical Formulation (clean_slate_optimizer.py)

### 2.1 Original Objective

```
min Σᵢ Bᵢ × (1 - Π_jt (1 - pⱼₜ xⱼₜ))
```

| Symbol | Meaning | Source |
|--------|---------|--------|
| Bᵢ | 자산 i의 가치 | `Asset.value` |
| pⱼₜ | 요격체 j가 위협 t를 격추할 확률 | `upper_p[j,t]`, `lower_p[j,t]` |
| xⱼₜ | 할당 변수 (0 or 1) | HiGHS binary variable |

### 2.2 Log-Linear Transformation

비선형 곱 → 선형 합으로 변환:

```
Step 1: cⱼₜ = ln(1 - pⱼₜ)              ← log-survival 계수 (< 0)
Step 2: σᵢ  = Σ cⱼₜ × xⱼₜ             ← 자산 i의 log-survival 합
Step 3: exp(σᵢ) = Π(1-pⱼₜ)^xⱼₜ        ← 위협 생존 확률
```

**Equivalent objective:**
```
min Σᵢ Bᵢ × exp(σᵢ)
```

### 2.3 Effective Intercept Probability

```
P_total = 1 - (1 - Pk)²               ← 2발 salvo 확률 (missiles_per_engagement = 2)
K       = 0.6 + 0.4 × max(0, 1-d/r)   ← 거리 기반 k-factor [0.6, 1.0]
pⱼₜ     = K × P_total                  ← 실효 요격 확률
```

예시: Pk=0.85 → P_total = 1-0.15² = 0.9775, K=0.8 → pⱼₜ = 0.782

### 2.4 OA (Outer Approximation) Linearization

`exp(σ)`는 비선형 → 접선(tangent line)으로 근사:

```
fᵢ ≥ e^σₖ × (1 + σᵢ - σₖ)    for each breakpoint σₖ
```

- 40개 breakpoint, 비균등 분포 (σ=0 근처에 집중)
- 반복 정제 (3 rounds): solve → 최적 σ*에서 tangent 추가 → re-solve
- 수렴 시 fᵢ = exp(σᵢ) (수학적 동치)

### 2.5 Constraints

| ID | Constraint | Formula | Meaning |
|----|-----------|---------|---------|
| C1 | σ 정의 | σᵢ - Σ cⱼₜ xⱼₜ = 0 | σᵢ는 할당된 교전의 log-survival 합 |
| C2 | OA 접선 | fᵢ ≥ e^σₖ(1+σᵢ-σₖ) | exp(σ)의 선형 하한 |
| C3 | 탄약 용량 | Σₜ xⱼₜ ≤ floor(Mⱼ/2) | 시스템 j의 최대 교전 수 |
| C4 | 동시 교전 | Σₜ xⱼₜ ≤ Cⱼ | 동시 교전 제한 (기본 5) |
| C5 | 상층 1개 | Σⱼ x_upper_jt ≤ 1 | 위협당 상층 1개 시스템만 |
| C6 | 하층 1개 | Σⱼ x_lower_jt ≤ 1 | 위협당 하층 1개 시스템만 |
| C7 | 커버리지 | (soft) | 목적함수가 자연 유도 |
| C8 | 다층 제한 | upper+lower ≤ 2 | 위협당 최대 2회 교전 |

**Special cases:**
- 위협 없는 자산: fᵢ = 0 (피해 없음)
- 교전 불가한 위협: fᵢ = 1 (방어 불가, 피해 100%)

### 2.6 Variable Layout in HiGHS

```
Column index:  [0 ... n_xu-1] [n_xu ... n_xu+n_xl-1] [σ₀ ... σₙ] [f₀ ... fₙ]
               ─────────────── ──────────────────────── ─────────── ───────────
               upper x_jt      lower x_jt               σᵢ          fᵢ
               (binary)        (binary)                 (continuous) (continuous)
```

### 2.7 Solve Pipeline

```
build_problem(assets, systems, threats, ...)
    → DWTAProblem (immutable NumPy arrays)
    → feasibility matrix, p_jt, c_jt, capacities

build_model(DWTAProblem)
    → HiGHS model + VarMap
    → variables, objective, constraints (batch addRows)

solve()
    → model.run()
    → iterative OA refinement (3 rounds)
    → extract_result() → Dict

Warm-start:
    → 이전 할당을 MIP start hint로 전달
    → 동일/유사 위협 구조에서 수렴 가속
```

### 2.8 Output (result Dict)

```python
{
    'feasible': True,
    'objective_value': 358.08,           # Σ Bᵢ × exp(σᵢ) = 예상 총 피해
    'upper_assignments': {               # "asset_threat": system_id
        'A1_T01': 'LSAM_01',
    },
    'lower_assignments': {
        'A1_T01': 'MSAM_02',
    },
    'asset_survival_probs': {            # 1 - exp(σᵢ)
        'A1': 0.761,
        'A2': 1.0,                       # 위협 없음 → 100% 생존
    },
    'diagnosis': {
        'num_variables': 95,
        'num_constraints': 160,
    },
}
```

---

## 3. Simulation Flow (multi_missile_tracker_gui.py)

### 3.1 Lifecycle

```
__init__
  ├─ _load_scenario() → assets, batteries, threats 로드
  ├─ EnhancedEngagementMatrix 초기화 (교전 가능성 사전 계산)
  ├─ KFactorCache 초기화 (거리/시간 기반 K값 캐싱)
  ├─ UncertaintyModeling 초기화 (Beta α=9, β=1)
  └─ GUI 초기화 (DWTAMainWindow)

start_scenario()
  └─ 각 위협을 missiles Dict에 등록 (active=False)

Main Loop (매 timestep):
  ├─ update_simulation()      ← 위협 이동, 상태 갱신
  ├─ run_realtime_dwta()      ← 최적화 호출 (이벤트 기반)
  └─ display update (250ms)   ← GUI 갱신
```

### 3.2 update_simulation() — 매 timestep

```
current_time_step += 1

For each missile:
  1. 발사 시간 도달? → active = True
  2. flight_progress = (현재시간 - 발사시간) / 비행시간
  3. position = trajectory[progress_idx]
  4. flight_progress ≥ 0.60? → _process_impact() 호출
```

### 3.3 run_realtime_dwta() — 최적화 호출

**트리거 조건** (이벤트 기반):
1. 탄약 확보 감지 (요격 성공 → 여유 용량)
2. 미할당 위협 재할당 필요
3. 정기 간격 (optimization_interval = 1초)

```
_prepare_optimizer_inputs()
  ├─ Asset 객체 생성 (value, position)
  ├─ InterceptorSystem 객체 생성 (Pk, Range, ammo)
  │   └─ Fallback: LSAM(0.85/300km), MSAM(0.78/50km)
  └─ Threat 객체 생성
      ├─ current_position = (x, y, altitude)
      └─ altitude = max_alt_km × 1000 × sin(π × flight_progress)
                    └─ 탄도 포물선: 발사(0%) → 정점(50%) → 낙하(100%)

optimizer.create_model(assets, systems, threats, batteries, engagement_matrix)
optimizer.solve() → result

_process_optimization_results(result)
  └─ primary_assignments에 할당 저장 (battery ↔ threat 매핑)
```

### 3.4 _process_impact() — 교전 판정

**2단계 방어 구조 (상층 LSAM → 하층 MSAM):**

```
Phase 1: UPPER LAYER (LSAM)
───────────────────────────
For each assigned LSAM battery:
  Pk_base = 0.85 (or from specs)

  Stage 1 — Beta 샘플링 (불확실성):
    missiles_to_fire = 2 (salvo)
    P_surv = 1.0
    For each shot:
      Pk_shot = Beta(9, 1).sample()     ← 몬테카를로 불확실성
      P_surv *= (1 - Pk_shot)

  Stage 2 — K factor (결정론적):
    K = 0.6 + 0.4 × max(0, 1 - dist/range)
    P_eff = K × (1 - P_surv)
    P_survival *= (1 - P_eff)

P_kill_upper = 1 - P_survival
if P_kill_upper >= 0.5 → INTERCEPTED ✓


Phase 2: LOWER LAYER (MSAM) — 상층 실패 시만
─────────────────────────────────────────────
Same process, Pk_base = 0.78, Range = 50km

P_kill_final = 1 - P_survival
if P_kill_final >= 0.5 → INTERCEPTED ✓
else → MISSED (SLS 재교전 또는 최종 실패)
```

**변수 흐름:**
```
Pk_base (배터리 스펙)
  → Beta(9,1) 샘플링 per shot     ← Stage 1: 불확실성 (몬테카를로)
  → P_surv = Π(1 - Pk_shot)
  → K factor (거리 기반)            ← Stage 2: 환경 보정 (결정론적)
  → P_eff = K × (1 - P_surv)
  → P_survival *= (1 - P_eff)      ← 배터리별 누적
  → P_kill = 1 - P_survival
  → P_kill >= 0.5 → 성공/실패      ← 임계값 판정
```

**설계 원칙:**
- **Stage 1 (Beta)**: 현실의 비결정성 반영 (몬테카를로 목적)
- **Stage 2 (K, threshold)**: 결정론적 — 최적화-실행 편차 최소화

### 3.5 Shoot-Look-Shoot (SLS)

```
max_engagement_attempts = 3

if MISSED and attempt < 3:
  → missile['needs_reassignment'] = True
  → 다음 최적화 사이클에서 재할당
  → _process_impact 재호출 (flight_progress < 0.85)
```

### 3.6 Key Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| optimization_interval | 1초 | 정기 최적화 간격 |
| max_engagement_attempts | 3 | SLS 최대 재교전 횟수 |
| flight_progress (교전) | 0.60 | 교전 시작 시점 (~20-30km) |
| flight_progress (최종) | 0.85 | 재할당 불가 시점 |
| P_kill threshold | 0.50 | 요격 성공 판정 임계값 |
| Beta α, β | 9, 1 | 불확실성 분포 (평균 ~0.9) |
| LSAM Pk_base | 0.85 | 상층 기본 요격 확률 |
| MSAM Pk_base | 0.78 | 하층 기본 요격 확률 |
| LSAM Range | 300km | 상층 최대 교전 거리 |
| MSAM Range | 50km | 하층 최대 교전 거리 |
| Salvo size | 2발 | 교전당 발사 미사일 수 |
| LSAM ammo | 24발 | 상층 배터리 보유 탄약 |
| MSAM ammo | 48발 | 하층 배터리 보유 탄약 |

---

## 4. Optimizer vs Simulator — Role Separation

```
┌─────────────────────────────┐   ┌──────────────────────────────┐
│   clean_slate_optimizer.py   │   │  multi_missile_tracker_gui.py │
│                              │   │                               │
│  역할: 결정론적 해결사        │   │  역할: 전체 시스템 시뮬레이터  │
│                              │   │                               │
│  Input:                      │   │  Input:                       │
│   - 고정 Pk (배터리 스펙)     │   │   - optimizer 할당 결과        │
│   - 동적 K (거리/시간)        │   │   - Beta(9,1) 샘플링          │
│                              │   │   - 동적 K factor              │
│  Output:                     │   │                               │
│   - 최적 할당 (x_jt)         │   │  Output:                      │
│   - 예상 피해 (objective)     │   │   - INTERCEPTED / MISSED      │
│   - 자산 생존율               │   │   - 실제 요격률                │
│                              │   │   - 탄약 소모 추적             │
│  특징:                        │   │                               │
│   - 수학적 최적해             │   │  특징:                         │
│   - < 10ms 풀이              │   │   - 몬테카를로 불확실성        │
│   - Warm-start 지원           │   │   - Shoot-Look-Shoot          │
│   - OA 정확도 보장            │   │   - 실시간 시각화             │
└─────────────────────────────┘   └──────────────────────────────┘
```

---

## 5. Headless Mode & CLI

### 5.1 GUI Mode (기본)

```bash
python multi_missile_tracker_gui.py
```

PyQt5 GUI가 실행되며, 제어 패널에서 시나리오/알고리즘 선택 후 시뮬레이션 시작.

### 5.2 Headless Compare Mode

```bash
# 기본 (BASELINE_15, MIP+Greedy+GA, 1회)
python multi_missile_tracker_gui.py --compare

# 시나리오 지정
python multi_missile_tracker_gui.py --compare STRESS_100

# 알고리즘 + 시나리오 + 반복 횟수
python multi_missile_tracker_gui.py --compare MIP,Greedy BASELINE_15,STRESS_100 --iterations 5

# 반복 횟수만
python multi_missile_tracker_gui.py --compare 10
```

### 5.3 Available Scenarios

| Category | Scenarios | Threat Count |
|----------|-----------|-------------|
| Small | SMALL_3, SMALL_5, SMALL_8 | 3-8 |
| Medium | MEDIUM_10, MEDIUM_20 | 10-20 |
| Baseline | BASELINE_15, BASELINE_30 | 15-30 |
| Large | LARGE_30, LARGE_40 | 30-40 |
| Stress | STRESS_100, STRESS_150, STRESS_200, STRESS_300 | 100-300 |
| Pattern | SEQUENTIAL_15, SIMULTANEOUS_15 | 15 |

### 5.4 Available Algorithms

| Algorithm | Class | Characteristics |
|-----------|-------|----------------|
| MIP | CleanSlateOptimizer | 전역 최적해, < 10ms, HiGHS |
| Greedy | GreedyOptimizer | 빠른 근사해, best-fit lookahead |
| GA | GeneticAlgorithmOptimizer | 진화적 탐색, pop=200, gen=100 |

### 5.5 Output

- Console: 알고리즘별 요격률, 풀이 시간, 목적함수 비교
- CSV: `performance_results/comparison_*.csv`
- JSON: `stress_test_*.json` (상세 메트릭)

---

## 6. Optimizer Interface Contract

모든 옵티마이저 (MIP, GA, Greedy)는 동일한 인터페이스:

```python
optimizer = OptimizerClass(config)
optimizer.create_model(assets, systems, threats, batteries, engagement_matrix)
result = optimizer.solve()
```

### Input Types

```python
Asset(id='A01', position=(0,0), value=1500, priority=1,
      estimated_threat_missiles=['T01','T02'])

InterceptorSystem(id='LSAM_01', system_type='UPPER',
                  position=(0,5), available_missiles=24,
                  max_missiles_per_target=2,
                  intercept_probability=0.85,
                  engagement_range=300.0)

Threat(id='T01', target_asset_id='A01',
       current_position=(5, 20, 30000),  # (x, y, altitude_m)
       estimated_impact_time=120.0)
```

### Output Dict

```python
result = {
    'feasible': bool,
    'objective_value': float,          # 예상 총 피해
    'upper_assignments': Dict,         # "{asset}_{threat}": system_id
    'lower_assignments': Dict,
    'asset_survival_probs': Dict,      # asset_id: survival (0~1)
    'solve_time': float,
    'status': str,                     # "Optimal", "Infeasible"
    'diagnosis': {
        'num_variables': int,
        'num_constraints': int,
        'feasible_engagements': int,
    },
}
```

---

## 7. Dependencies

```
numpy>=2.0          # 수치 계산
highspy>=1.13       # HiGHS MIP 솔버
scipy>=1.15         # Beta/Normal 분포 (몬테카를로)
pydantic            # 설정 검증
matplotlib>=3.8     # (레거시 시각화)
PyQt5               # GUI 프레임워크
pyqtgraph           # 실시간 전술 맵
```

Install:
```bash
pip install -r requirements.txt
pip install PyQt5 pyqtgraph    # GUI용 (선택)
```
