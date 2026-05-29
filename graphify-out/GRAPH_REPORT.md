# Graph Report - .  (2026-05-29)

## Corpus Check
- 15 files · ~51,266 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 655 nodes · 1463 edges · 27 communities (21 shown, 6 thin omitted)
- Extraction: 75% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 365 edges (avg confidence: 0.52)
- Token cost: 235,640 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Clean-Slate Optimizer & Scenarios|Clean-Slate Optimizer & Scenarios]]
- [[_COMMUNITY_Configuration & Engagement Models|Configuration & Engagement Models]]
- [[_COMMUNITY_Feasibility & McCormick Caches|Feasibility & McCormick Caches]]
- [[_COMMUNITY_Tactical Map Widget (PyQtGraph)|Tactical Map Widget (PyQtGraph)]]
- [[_COMMUNITY_K-Factor & McCormick Computation|K-Factor & McCormick Computation]]
- [[_COMMUNITY_MIP Solver Techniques|MIP Solver Techniques]]
- [[_COMMUNITY_Simulation Engine (MultiMissileTracker)|Simulation Engine (MultiMissileTracker)]]
- [[_COMMUNITY_Clean-Slate MIP Model Building|Clean-Slate MIP Model Building]]
- [[_COMMUNITY_Genetic Algorithm Optimizer|Genetic Algorithm Optimizer]]
- [[_COMMUNITY_Main Window GUI Layout|Main Window GUI Layout]]
- [[_COMMUNITY_Scenario Generation & Deployment|Scenario Generation & Deployment]]
- [[_COMMUNITY_Stress Metrics & Table Refresh|Stress Metrics & Table Refresh]]
- [[_COMMUNITY_Assignment Manager Data Structure|Assignment Manager Data Structure]]
- [[_COMMUNITY_Config Class Aggregates|Config Class Aggregates]]
- [[_COMMUNITY_GUI Controls & Event Handlers|GUI Controls & Event Handlers]]
- [[_COMMUNITY_Display Update Methods|Display Update Methods]]
- [[_COMMUNITY_Optimization Metrics Reporting|Optimization Metrics Reporting]]
- [[_COMMUNITY_Large-Scale Stress Scenarios|Large-Scale Stress Scenarios]]
- [[_COMMUNITY_Optimizer Model Builders|Optimizer Model Builders]]
- [[_COMMUNITY_Optimizer Solve & Objective|Optimizer Solve & Objective]]
- [[_COMMUNITY_Greedy Optimizer|Greedy Optimizer]]
- [[_COMMUNITY_Optimizer Strategies & Uncertainty|Optimizer Strategies & Uncertainty]]
- [[_COMMUNITY_Stress Test Module|Stress Test Module]]
- [[_COMMUNITY_Matplotlib Dependency|Matplotlib Dependency]]
- [[_COMMUNITY_SciPy Dependency|SciPy Dependency]]
- [[_COMMUNITY_Engagement Zone Config|Engagement Zone Config]]
- [[_COMMUNITY_Config Node|Config Node]]

## God Nodes (most connected - your core abstractions)
1. `DWTAMainWindow` - 55 edges
2. `KFactorCache` - 50 edges
3. `TacticalMapWidget` - 45 edges
4. `ScenarioManager` - 40 edges
5. `GeneticAlgorithmOptimizer` - 38 edges
6. `MultiMissileTracker` - 37 edges
7. `OptimizedAssignmentManager` - 36 edges
8. `MIPConfig` - 34 edges
9. `EnhancedEngagementMatrix` - 34 edges
10. `str` - 33 edges

## Surprising Connections (you probably didn't know these)
- `TacticalMapWidget._compute_tta` --semantically_similar_to--> `DWTAMainWindow._compute_tta`  [INFERRED] [semantically similar]
  pyqtgraph_display.py → multi_missile_tracker_gui.py
- `GeneticAlgorithmOptimizer` --semantically_similar_to--> `CleanSlateOptimizer`  [INFERRED] [semantically similar]
  ga_optimizer.py → clean_slate_optimizer.py
- `GeneticAlgorithmOptimizer.solve` --semantically_similar_to--> `GreedyOptimizer.solve`  [INFERRED] [semantically similar]
  ga_optimizer.py → greedy_optimizer.py
- `GeneticAlgorithmOptimizer._calculate_objective` --semantically_similar_to--> `GreedyOptimizer._calculate_objective`  [INFERRED] [semantically similar]
  ga_optimizer.py → greedy_optimizer.py
- `Asset` --uses--> `KFactorCache`  [INFERRED]
  multi_missile_tracker_gui.py → config_mip.py

## Hyperedges (group relationships)
- **Seven DWTA-MIP Optimization Techniques** — _dwta_mip_7techniques_en_csr_sparse_matrix, _dwta_mip_7techniques_en_fbbt, _dwta_mip_7techniques_en_obbt, _dwta_mip_7techniques_en_piecewise_mccormick, _dwta_mip_7techniques_en_huffman_binary_tree, _dwta_mip_7techniques_en_valid_inequalities, _dwta_mip_7techniques_en_bipartite_decomposition [EXTRACTED 1.00]
- **Clean Slate Functional Pipeline** — the_plan_for_great_dwta_dwtaproblem, the_plan_for_great_dwta_varmap, the_plan_for_great_dwta_highspy_direct_api, the_plan_for_great_dwta_log_linear_formulation [INFERRED 0.85]
- **Bitmask-Accelerated Pipeline (Phase 1 + Phase 4)** — dwta_mip_pipeline_design_en_feasibility_cache, dwta_mip_pipeline_design_en_bitmask_union_find, dwta_mip_pipeline_design_en_rho_measurement [INFERRED 0.75]
- **Tactical map per-frame render pipeline** — pyqtgraph_display_update_display, pyqtgraph_display_update_threats, pyqtgraph_display_update_assignment_lines, pyqtgraph_display_update_trajectory_lines, pyqtgraph_display_update_batteries [EXTRACTED 1.00]
- **Trajectory-based engagement feasibility and probability pipeline** — config_mip_calculate_trajectory_intercept_point, config_mip_can_engage_trajectory, config_mip_calculate_engagement_time_window, config_mip_calculate_window_adjusted_probability, config_mip_create_engagement_matrix [INFERRED 0.85]
- **Sim thread to GUI display shared tracker state** — multi_missile_tracker_gui_run_sim_thread, multi_missile_tracker_gui_on_display_tick, pyqtgraph_display_tacticalmapwidget, multi_missile_tracker_gui_optimizedassignmentmanager [INFERRED 0.75]
- **DWTA optimizer strategies implementing shared solve/create_model interface** — ga_optimizer_geneticalgorithmoptimizer, greedy_optimizer_greedyoptimizer, clean_slate_optimizer_cleanslateoptimizer [INFERRED 0.85]
- **Optimizers sharing Asset/InterceptorSystem/Threat dataclasses and engagement-matrix data** — ga_optimizer_geneticalgorithmoptimizer, greedy_optimizer_greedyoptimizer, clean_slate_optimizer_build_problem [INFERRED 0.85]

## Communities (27 total, 6 thin omitted)

### Community 0 - "Clean-Slate Optimizer & Scenarios"
Cohesion: 0.06
Nodes (55): Asset, CleanSlateOptimizer, InterceptorSystem, Backward compatibility., Drop-in replacement for NonLinearMIPOptimizer.      Interface contract:, Provide k-factor cache for distance/time-based k computation., Threat, EnhancedEngagementMatrix (+47 more)

### Community 1 - "Configuration & Engagement Models"
Cohesion: 0.06
Nodes (50): BaseModel, bool, bool, str, BatteryPosition, Config, EnemyMissile, EnemyMissileSpec (+42 more)

### Community 2 - "Feasibility & McCormick Caches"
Cohesion: 0.05
Nodes (29): int, str, BinaryTreeMcCormickCache, FeasibilityCache, 교전 가능 여부 (정적 precompute + 실시간 거리 체크)                  Args:             battery_, 새로운 위협에 대해서만 증분 계산                  Args:             batteries: 포대 리스트, 이동 중인 위협의 현재 위치 기반으로 교전 매트릭스 동적 업데이트.          기존 정적 precompute는 발사 위치 기반이었으나, 이, 특정 위협에 대해 유효한 state 조합만 생성                  Args:             threat_id: 위협 ID (+21 more)

### Community 3 - "Tactical Map Widget (PyQtGraph)"
Cohesion: 0.05
Nodes (30): _draw_star(), _LegendWidget, _pentagon_points(), TacticalMapWidget - PyQtGraph Tactical Display for DWTA Operator ===============, High-performance PyQtGraph tactical map widget.     Designed for MLAD (Multi-Lay, Configure plot axes, background, and labels., Pre-allocate all scatter/line plot items., 좌하단 고정 범례 — QPainter 기반 실제 심볼 렌더링. (+22 more)

### Community 4 - "K-Factor & McCormick Computation"
Cohesion: 0.08
Nodes (22): float, KFactorCache, McCormickCoefficients, 기본 요격 확률 (O(1) lookup), K-factor 사전 계산 캐시 + 경량 실시간 계산 (최적화 #3), 모든 (threat, system) 조합의 k-factor 계산                  Args:             threats:, K-factor 조회 (캐시에서, O(1)), 실시간 K값 계산 (LUT 기반, 초경량)                  Args:             threat_pos: 위협 현재 위치 (+14 more)

### Community 5 - "MIP Solver Techniques"
Cohesion: 0.06
Nodes (41): Bipartite Graph-Based Problem Decomposition, Branch and Bound (B&B), CSR Sparse Matrix, Exact Algorithm (Global Optimality Guarantee), FBBT (Feasibility-Based Bound Tightening), Huffman Binary Tree, LP Relaxation, McCormick Relaxation (+33 more)

### Community 6 - "Simulation Engine (MultiMissileTracker)"
Cohesion: 0.09
Nodes (17): MultiMissileTracker, Called by MultiMissileTracker internals. Thread-safe via signal., 실시간 DWTA 분석 시뮬레이터 - GUI 지원 버전, Invalidate active threats count cache, Invalidate operational battery and ammo cache, Get operational batteries with caching (O(1) after first call), Rebuild persistent battery lookup cache, Simple linear trajectory for visualization. (+9 more)

### Community 7 - "Clean-Slate MIP Model Building"
Cohesion: 0.10
Nodes (29): bool, float, int, str, apply_warmstart(), build_model(), build_problem(), _check_feasibility() (+21 more)

### Community 8 - "Genetic Algorithm Optimizer"
Cohesion: 0.10
Nodes (16): Asset, GeneticAlgorithmOptimizer, InterceptorSystem, Genetic Algorithm DWTA Optimizer ================================= 유전 알고리즘 기반 DW, GA 모델 생성 - 데이터 구조 초기화, 몬테카를로 시뮬레이션에서 샘플링된 요격확률 설정, 진짜 유전 알고리즘 실행 (Population-based Evolution), 교전 가능하고 용량이 남은 시스템 목록 반환 (동시 교전 제약 포함) (+8 more)

### Community 9 - "Main Window GUI Layout"
Cohesion: 0.11
Nodes (6): DWTAMainWindow, Trigger flash + immediately clean up engagement lines and threat dot., Update solver time, warm-start, or objective value labels., Compatibility: tracker calls this after update_simulation()., DWTA 단일 PyQt5 메인 윈도우.     tkinter ControlPanel + matplotlib figure 를 완전히 대체한다., QMainWindow

### Community 10 - "Scenario Generation & Deployment"
Cohesion: 0.10
Nodes (10): 방어 자산 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 포대 배치 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 위협 미사일 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 현실적인 시나리오 생성 - 시나리오 타입에 따라 다른 위협 구성, 전구 방어 구역 기반 포대 배치 - 각 자산당 전담 상층/하층 시스템 배정, L-SAM (장거리 지대공 미사일) 실제 스펙, 세밀한 시간 기반 북한 탄도탄 15발 시나리오 (노동 + Scud-B), M-SAM (중거리 지대공 미사일) 실제 스펙 - 한국형 천궁-II (+2 more)

### Community 11 - "Stress Metrics & Table Refresh"
Cohesion: 0.17
Nodes (9): _calculate_stress_metrics(), Called on main thread when simulation thread exits., Fires every 250 ms on the main thread — refresh all visual elements., 누적 로그 방식: 신규 위협은 행 추가, 기존 위협은 상태만 갱신., Flash alert bar if there are unengaged high-danger threats., Text-based status report (원본 코드), Final reporting (원본 코드 유지), 성능 지표를 CSV 파일로 저장 (확장된 메트릭) (+1 more)

### Community 12 - "Assignment Manager Data Structure"
Cohesion: 0.27
Nodes (4): OptimizedAssignmentManager, 하이브리드 자료구조: 빠른 쓰기 O(1) + 빠른 탐색 O(1)~O(k)     - battery_to_threats: List[List[int, 새로운 할당으로 병합 (MIP 제약 조건 준수)                  제약 조건:         - 위협당 상층 최대 1개 배터리, str

### Community 13 - "Config Class Aggregates"
Cohesion: 0.16
Nodes (15): AssetConfig, BatteryDeploymentConfig, EngagementZoneConfig.calculate_engagement_time_window, EngagementZoneConfig.calculate_trajectory_intercept_point, EngagementZoneConfig.calculate_window_adjusted_probability, EngagementZoneConfig.can_engage_trajectory, EngagementZoneConfig.create_engagement_matrix, InterceptorSystemConfig (+7 more)

### Community 15 - "Display Update Methods"
Cohesion: 0.16
Nodes (14): DWTAMainWindow._compute_tta, OptimizedAssignmentManager.get_batteries_for_threat, OptimizedAssignmentManager.get_threats_for_battery, OptimizedAssignmentManager.merge_assignments, DWTAMainWindow._on_display_tick, DWTAMainWindow._refresh_battery_table, DWTAMainWindow._refresh_threat_table, DWTAMainWindow._run_sim_thread (+6 more)

### Community 16 - "Optimization Metrics Reporting"
Cohesion: 0.20
Nodes (5): OptimizationMetrics, Stress Test Metrics Collection System ====================================== MIP, float, int, str

### Community 17 - "Large-Scale Stress Scenarios"
Cohesion: 0.20
Nodes (5): 스트레스 테스트 시나리오 (100발 - 성능 한계 검증), 스트레스 테스트 시나리오 (150발 - 점진적 확장), 스트레스 테스트 시나리오 (200발 - 한계 탐색), 스트레스 테스트 시나리오 (300발 - 극한 테스트), 스트레스 테스트 공통 생성 함수                  Args:             base_threats: 기본 위협 템플릿 (15

### Community 18 - "Optimizer Model Builders"
Cohesion: 0.22
Nodes (9): apply_warmstart, build_model, build_problem, CleanSlateOptimizer.create_model, DWTAProblem, GeneticAlgorithmOptimizer.create_model, GreedyOptimizer.create_model, DWTABalancedScenario (+1 more)

### Community 19 - "Optimizer Solve & Objective"
Cohesion: 0.29
Nodes (8): extract_result, CleanSlateOptimizer.solve, GeneticAlgorithmOptimizer._calculate_objective, GeneticAlgorithmOptimizer._evaluate_fitness, GeneticAlgorithmOptimizer.solve, GreedyOptimizer._calculate_objective, GreedyOptimizer.solve, StressTestMetrics

### Community 20 - "Greedy Optimizer"
Cohesion: 0.40
Nodes (3): Greedy 알고리즘 실행 (공정한 비교를 위해 개선)                  개선 사항:         - 단순 First-fit이 아, 목적함수 계산: GA와 동일한 방식         MIN_DAMAGE: min Σ B_i * [Π (1 - x*k*P)]         = 기댓, K-factor 가져오기: 캐시에서 또는 거리 기반 계산

### Community 21 - "Optimizer Strategies & Uncertainty"
Cohesion: 0.83
Nodes (4): CleanSlateOptimizer, GeneticAlgorithmOptimizer, GreedyOptimizer, UncertaintyModeling

## Knowledge Gaps
- **35 isolated node(s):** `str`, `bool`, `int`, `str`, `bool` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `KFactorCache` connect `K-Factor & McCormick Computation` to `Clean-Slate Optimizer & Scenarios`, `Configuration & Engagement Models`, `Simulation Engine (MultiMissileTracker)`, `Genetic Algorithm Optimizer`, `Main Window GUI Layout`, `Assignment Manager Data Structure`?**
  _High betweenness centrality (0.140) - this node is a cross-community bridge._
- **Why does `TacticalMapWidget` connect `Tactical Map Widget (PyQtGraph)` to `Clean-Slate Optimizer & Scenarios`, `Main Window GUI Layout`, `Assignment Manager Data Structure`, `Simulation Engine (MultiMissileTracker)`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Why does `ScenarioManager` connect `Clean-Slate Optimizer & Scenarios` to `Configuration & Engagement Models`, `Simulation Engine (MultiMissileTracker)`, `Main Window GUI Layout`, `Scenario Generation & Deployment`, `Assignment Manager Data Structure`, `Large-Scale Stress Scenarios`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `DWTAMainWindow` (e.g. with `Asset` and `CleanSlateOptimizer`) actually correct?**
  _`DWTAMainWindow` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `KFactorCache` (e.g. with `Config` and `ScenarioManager`) actually correct?**
  _`KFactorCache` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `TacticalMapWidget` (e.g. with `Asset` and `CleanSlateOptimizer`) actually correct?**
  _`TacticalMapWidget` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `ScenarioManager` (e.g. with `Config` and `ScenarioManager`) actually correct?**
  _`ScenarioManager` has 22 INFERRED edges - model-reasoned connections that need verification._