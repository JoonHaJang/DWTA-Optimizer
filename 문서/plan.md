# DWTA MIP 7 Optimization Techniques Implementation Plan

## Context

STRESS_100 (100 threats) 시나리오에서 MIP 솔버가 평균 2.87s, timeout률 44.8%로 실시간 한계를 초과한다. 문서 `DWTA_MIP_7Techniques_EN.md`에 정의된 7가지 최적화 기법을 현재 프로젝트 프레임워크 내에서 단계적으로 적용하여, 전역 최적해 보장을 유지하면서 풀이 시간을 대폭 줄인다.

**현재 상태**: 변수 생성은 이미 sparse (feasible pair만 생성), McCormick은 단일 envelope, Binary Tree는 balanced split, Probing은 3개 규칙만 존재. OBBT, Piecewise McCormick, Huffman Tree, Valid Inequalities, 그래프 분해는 미구현.

---

## Implementation Order (권장 순서)

```
Step 1: SparseEngagementIndex (Phase 1) — 기반 구조, 나머지 모두에 활용
Step 2: Valid Inequalities (Phase 3c)   — 위험 낮음, 즉시 효과
Step 3: Enhanced FBBT (Phase 2a)        — 기존 probing 확장
Step 4: Huffman Tree (Phase 3b)         — 소규모 수정, 독립적
Step 5: OBBT (Phase 2b)                 — FBBT 이후 실행
Step 6: Piecewise McCormick (Phase 3a)  — 가장 복잡한 수학적 변경
Step 7: Bipartite Decomposition (Phase 4) — 가장 큰 구조적 변경
```

### 의존 관계
```
Phase 1:  [1. CSR Sparse Index]  ← 기반 구조
              |
Phase 2:  [2. FBBT] → [3. OBBT]  ← OBBT는 FBBT에 의존
              |            |
Phase 3:  [4. Piecewise McCormick] ← OBBT bounds 활용 시 최적
          [5. Huffman Tree]         ← 독립적
          [6. Valid Inequalities]   ← 독립적
              |
Phase 4:  [7. Bipartite Decomp]   ← Sparse Index 활용
```

---

## Step 1: CSR Sparse Index Structure

**파일**: `config_mip.py` (새 클래스 추가, line ~2177 이후), `nonlinear_mip_optimizer.py` (수정)

**작업**:
1. `SparseEngagementIndex` 클래스 생성 (`config_mip.py`)
   - `feasible_pairs`, `upper_pairs`, `lower_pairs`: feasible (system_id, threat_id) 리스트
   - `threat_to_systems`: threat_id → [system_id, ...] 역인덱스
   - `system_to_threats`: system_id → [threat_id, ...] 역인덱스
   - `build()` 메서드: engagement matrix에서 1회 순회로 구축

2. `nonlinear_mip_optimizer.py` 수정:
   - `create_model()` (line 153): `self.sparse_index = SparseEngagementIndex()` 빌드
   - `_create_decision_variables()` (line 260): 이중 루프 → `sparse_index.upper_pairs` 순회로 교체
   - `_linearize_asset_survival_probability()` (line 591-604): 이중 루프 → sparse index 사용
   - `_add_basic_constraints()` (line 635): sparse index 기반 순회
   - `_add_battery_simultaneous_engagement_limits()` (line 924): `system_to_threats` 사용

**토글**: `self.use_sparse_index = True` (line 132 부근)
**예상 코드량**: ~120줄 (클래스 80 + 수정 40)
**기대 효과**: 모델 생성 시간 10-20% 단축, 이후 기법들의 기반 자료구조 제공

---

## Step 2: Valid Inequalities (Problem-Specific Cuts)

**파일**: `nonlinear_mip_optimizer.py` (`_add_original_constraints()` line 854 이후)

**작업**: `_add_valid_inequalities()` 메서드 추가

**Cut 1 — 탄약-교전 상한**:
```
sum_i(x_ij) ≤ min(C_j, floor(M_j / m))   ∀ battery j
```
- `C_j` = `battery['specs']['battery_config']['simultaneous_engagements']` (이미 line 932에서 접근)
- 현재 capacity 제약 (`sum * 2 ≤ M_j`, line 737)보다 타이트

**Cut 2 — 고가치 자산 필수 교전**:
```
sum_j(x_ij_upper + x_ij_lower) ≥ 1   ∀ threat i : B_i > threshold
```
- threshold = asset value 상위 30%
- 현재는 일부 경우에만 `≥ 1` 적용 (line 677-692), 모든 고가치 threat에 확장

**Cut 3 — 계층 교전 제한**:
```
sum_j(x_ij_upper) + sum_j(x_ij_lower) ≤ 1 + 1[high_value]
```
- 비고가치 threat: 한 계층에서만 교전 (자원 절약)
- 고가치 threat: 양 계층 교전 허용

**호출 위치**: `_add_original_constraints()` 마지막에서 호출
**토글**: `self.use_valid_inequalities = True`
**예상 코드량**: ~80줄
**기대 효과**: Root node LP relaxation gap 5-15% 감소

---

## Step 3: Enhanced FBBT (Feasibility-Based Bound Tightening)

**파일**: `nonlinear_mip_optimizer.py` (새 메서드, `_probe_and_fix()` 이후 line ~1044)

**작업**: `_fbbt_bound_tightening()` 메서드 추가

- **Rule 4 (탄약 상한 전파)**: battery j에서 `sum(x_ij) ≤ floor(M_j / 2)` — 현재 capacity 제약보다 타이트한 bound 전파
- **Rule 5 (용량 소진 전파)**: battery의 남은 용량이 0이면 연결된 모든 x를 0으로 고정 (기존 Rule 2 강화)
- **Rule 6 (반복 전파 - Fixpoint)**: Rule 1~5를 변경이 없을 때까지 반복 수행

**호출 위치**: `solve()` line 1096에서 `_probe_and_fix()` 후 호출
**토글**: `self.use_fbbt = True`
**예상 코드량**: ~80줄
**기대 효과**: B&B 탐색 공간 5-15% 추가 감소 (기존 probing 대비)

---

## Step 4: Huffman Binary Tree (Weighted Binary Tree)

**파일**: `nonlinear_mip_optimizer.py` (`_create_product_variable()` line 1263 인근)

**작업**: `_create_product_variable_huffman()` 메서드 추가

- `heapq` 기반 Huffman 트리 구축
- weight = 해당 survival variable에 대응하는 threat의 위협도 (k_value × P_total)
- **높은 위협도 변수가 root 가까이** → McCormick 근사 오차 최소화, 초기 bound 품질 향상

```python
import heapq

def _create_product_variable_huffman(self, variables_list, var_name, weights):
    if len(variables_list) <= 2:
        return self._create_product_variable(variables_list, var_name)

    heap = [(w, i, v) for i, (w, v) in enumerate(zip(weights, variables_list))]
    heapq.heapify(heap)
    counter = len(variables_list)

    while len(heap) > 1:
        w1, _, v1 = heapq.heappop(heap)
        w2, _, v2 = heapq.heappop(heap)
        product = self._create_product_variable([v1, v2], f"{var_name}_h{counter}")
        heapq.heappush(heap, (w1 + w2, counter, product))
        counter += 1

    return heap[0][2]
```

**호출 위치**: `_linearize_asset_survival_probability()` line 622에서 분기
**토글**: `self.use_huffman_tree = True` (추가 비용 0이므로 기본 on)
**예상 코드량**: ~60줄
**기대 효과**: B&B 초기 UB 품질 향상, pruning 5-10% 개선. 추가 변수/제약 0.

---

## Step 5: OBBT (Optimality-Based Bound Tightening)

**파일**: `nonlinear_mip_optimizer.py` (새 메서드)

**작업**: `_obbt_bound_tightening()` 메서드 추가

- FBBT 후 고정되지 않은 k 변수들에 대해, LP relaxation을 풀어 실제 달성 가능한 [k_min_actual, k_max_actual] 계산
- **구현 방법**: 별도 PuLP LP 모델 생성, 현재 제약을 복사하되 모든 binary → continuous [0,1]
- **상위 N개 변수만** 처리 (asset value 기준 정렬), **시간 제한 1초**
- 결과로 McCormick envelope bounds를 갱신: `_update_mccormick_bounds(tightened)`
- **헬퍼 메서드**: `_update_mccormick_bounds(tightened_dict)` — McCormick 제약의 kP_min, kP_max를 tightened bounds로 갱신

**호출 위치**: `solve()` 에서 FBBT 후, 솔버 실행 전
**토글**: `self.use_obbt = False` (기본 off — LP 풀이 비용 존재)
- `self.obbt_max_vars = 10`
- `self.obbt_time_limit = 1.0` (초)

**예상 코드량**: ~150줄
**기대 효과**: McCormick gap 17-19% 감소 (MINLPLib2 벤치마크 기준)

---

## Step 6: Piecewise McCormick (p=2)

**파일**: `nonlinear_mip_optimizer.py` (`_linearize_xkp_products()` line 442 인근)

**작업**: `_linearize_xkp_products_piecewise()` 메서드 추가

- k 범위 [k_min, k_max]를 p=2 구간으로 분할: [k_min, k_mid], [k_mid, k_max]
- 구간 선택 binary variable `z` 1개 추가 per feasible pair
- 각 구간에 대해 McCormick 4개 제약 → 총 8개 제약 per pair
- Big-M는 `k_max * P_total` (tight value)

```
For each feasible pair (i,j):
    z_ij ∈ {0, 1}     # 1 = lower interval, 0 = upper interval

    # Interval selection for k
    k_ij ≥ k_min
    k_ij ≤ k_mid + (k_max - k_mid) * (1 - z_ij)    # if z=1, k ≤ k_mid
    k_ij ≥ k_mid * (1 - z_ij) + k_min * z_ij        # additional bound

    # Tighter McCormick per interval
    # Interval 1 [k_min, k_mid]: active when z=1
    # Interval 2 [k_mid, k_max]: active when z=0
    # ... 8 constraints total
```

**호출 위치**: `_create_mccormick_linearization()` 에서 분기
**토글**: `self.use_piecewise_mccormick = False` (기본 off — binary 변수 추가)
- `self.piecewise_pieces = 2`

**예상 코드량**: ~130줄
**기대 효과**: LP relaxation gap 1/p² = 1/4 = 75% 감소, B&B 노드 수 지수적 감소
**주의**: Warm-start에서 새 z 변수 처리 필요 (warmstart_integration.py에서 무시하도록 처리)

---

## Step 7: Bipartite Graph Decomposition

**파일**: `nonlinear_mip_optimizer.py` (새 클래스 + `solve()` 수정)

**작업**:

### 7a. `BipartiteDecomposer` 클래스 (Union-Find)

```python
class BipartiteDecomposer:
    def find_components(self, upper_pairs, lower_pairs):
        """Union-Find로 연결 요소 탐색"""
        parent = {}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # 모든 노드 초기화
        for sys_id, thr_id in upper_pairs + lower_pairs:
            parent.setdefault(f"S:{sys_id}", f"S:{sys_id}")
            parent.setdefault(f"T:{thr_id}", f"T:{thr_id}")

        # 연결된 쌍 union
        for sys_id, thr_id in upper_pairs + lower_pairs:
            union(f"S:{sys_id}", f"T:{thr_id}")

        # 컴포넌트별 분류
        components = {}
        for nid in parent:
            root = find(nid)
            components.setdefault(root, {'threats': set(), 'systems': set()})
            if nid.startswith('T:'):
                components[root]['threats'].add(nid[2:])
            else:
                components[root]['systems'].add(nid[2:])

        return list(components.values())
```

### 7b. `solve()` 수정

- decomposition 활성화 시, `find_components()` 호출
- 2개 이상 component → `_solve_decomposed()` 호출
- 1개 component → 기존 monolithic solve 실행

### 7c. `_solve_decomposed(components)`

- 각 component에 대해:
  1. component 외부의 모든 x 변수를 bounds(0,0)으로 고정
  2. solver 실행
  3. 결과 수집 (assignments, objective)
  4. 변수 bounds 복원
- 결과 병합: 모든 component의 assignments 합산

**현실적 기대**: 한반도 시나리오에서 battery 커버리지 중첩으로 1~2개 component가 일반적. STRESS_100에서 지리적 분리 시 3+ component 가능 → O(2^n) → O(k × 2^(n/k)) 으로 지수적 감소.

**토글**: `self.use_decomposition = True`
**예상 코드량**: ~150줄
**기대 효과**: n=100, k=3일 때 이론적 85배 속도 향상

---

## Configuration Summary

`nonlinear_mip_optimizer.py` `__init__()` (line 132 부근)에 추가:

```python
# === 7 Optimization Techniques ===
# Phase 1: Data Structure
self.use_sparse_index = True

# Phase 2: Preprocessing
self.use_fbbt = True
self.use_obbt = False          # 대규모에서만 활성화
self.obbt_max_vars = 10
self.obbt_time_limit = 1.0

# Phase 3: Mathematical Tightening
self.use_piecewise_mccormick = False  # binary 추가되므로 기본 off
self.piecewise_pieces = 2
self.use_huffman_tree = True          # 추가 비용 0
self.use_valid_inequalities = True

# Phase 4: Decomposition
self.use_decomposition = True
```

---

## 수정 대상 파일 요약

| 파일 | 변경 내용 |
|------|-----------|
| `nonlinear_mip_optimizer.py` | 7개 기법 모두 (새 메서드 6개 + 클래스 1개 + 기존 메서드 수정) |
| `config_mip.py` | `SparseEngagementIndex` 클래스 추가 (line 2177 이후) |
| `stress_test_metrics.py` | 기법별 메트릭 필드 추가 (fbbt_fixed, obbt_tightened, num_components) |

`multi_missile_tracker_gui.py`와 `warmstart_integration.py`는 구조 변경 없음.

---

## 기대 효과 종합

| 기법 | 복잡도/속도 효과 | 추가 변수 | 추가 제약 |
|------|------------------|-----------|-----------|
| ③ CSR Sparse Index | LP 시간 ρ^2.5 ≈ 20× 단축 | 감소 | 감소 |
| ① Enhanced FBBT | 탐색 공간 (1-α)^n 감소 | 감소 | 없음 |
| ④ OBBT | 평균 17-19% 속도 향상 | 없음 | 없음 |
| ⑤ Piecewise McCormick | B&B 노드 지수적 감소 | p-1개/pair | 4(p-1)개/pair |
| ⑨ Huffman Tree | 초기 bound 품질 향상 | 없음 | 없음 |
| ⑦ Valid Inequalities | Root node gap 감소 | 없음 | 3-5개 |
| ⑩ Bipartite Decomp | O(2^n) → O(k·2^(n/k)) | 없음 | 없음 |

**핵심**: 7개 기법 모두 전역 최적해 보장(Exact Algorithm)을 완전히 유지하며, 상호 충돌 없이 누적 적용 가능.

---

## Verification

1. **정확성**: 각 기법 on/off 토글하며 DWTA_BALANCED (20 threats)에서 objective value 비교
2. **성능**: STRESS_100 시나리오 실행하여 solve_time, timeout률, 요격률 비교
3. **회귀**: 기존 BASELINE_15, DWTA_BALANCED 시나리오에서 결과 악화 없음 확인
4. **Warm-start 호환**: Piecewise McCormick의 새 binary 변수가 warm-start에서 올바르게 처리되는지 확인

**총 예상 코드량**: ~770줄 신규/수정
