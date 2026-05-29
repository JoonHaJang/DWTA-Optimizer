# Graph Report - DWTA-Optimizer  (2026-05-29)

## Corpus Check
- 38 files · ~59,584 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1264 nodes · 2647 edges · 94 communities (71 shown, 23 thin omitted)
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 721 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `28fa1e4a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]

## God Nodes (most connected - your core abstractions)
1. `DWTAMainWindow` - 55 edges
2. `Battery` - 54 edges
3. `KFactorCache` - 50 edges
4. `TacticalMapWidget` - 45 edges
5. `InterceptorStatus` - 43 edges
6. `ScenarioManager` - 40 edges
7. `Event` - 39 edges
8. `GeneticAlgorithmOptimizer` - 38 edges
9. `MultiMissileTracker` - 37 edges
10. `OptimizedAssignmentManager` - 36 edges

## Surprising Connections (you probably didn't know these)
- `TacticalMapWidget._compute_tta` --semantically_similar_to--> `DWTAMainWindow._compute_tta`  [INFERRED] [semantically similar]
  pyqtgraph_display.py → multi_missile_tracker_gui.py
- `GeneticAlgorithmOptimizer` --semantically_similar_to--> `CleanSlateOptimizer`  [INFERRED] [semantically similar]
  ga_optimizer.py → clean_slate_optimizer.py
- `GeneticAlgorithmOptimizer.solve` --semantically_similar_to--> `GreedyOptimizer.solve`  [INFERRED] [semantically similar]
  ga_optimizer.py → greedy_optimizer.py
- `GeneticAlgorithmOptimizer._calculate_objective` --semantically_similar_to--> `GreedyOptimizer._calculate_objective`  [INFERRED] [semantically similar]
  ga_optimizer.py → greedy_optimizer.py
- `Asset` --uses--> `CleanSlateOptimizer`  [INFERRED]
  multi_missile_tracker_gui.py → clean_slate_optimizer.py

## Hyperedges (group relationships)
- **Seven DWTA-MIP Optimization Techniques** — _dwta_mip_7techniques_en_csr_sparse_matrix, _dwta_mip_7techniques_en_fbbt, _dwta_mip_7techniques_en_obbt, _dwta_mip_7techniques_en_piecewise_mccormick, _dwta_mip_7techniques_en_huffman_binary_tree, _dwta_mip_7techniques_en_valid_inequalities, _dwta_mip_7techniques_en_bipartite_decomposition [EXTRACTED 1.00]
- **Clean Slate Functional Pipeline** — the_plan_for_great_dwta_dwtaproblem, the_plan_for_great_dwta_varmap, the_plan_for_great_dwta_highspy_direct_api, the_plan_for_great_dwta_log_linear_formulation [INFERRED 0.85]
- **Bitmask-Accelerated Pipeline (Phase 1 + Phase 4)** — dwta_mip_pipeline_design_en_feasibility_cache, dwta_mip_pipeline_design_en_bitmask_union_find, dwta_mip_pipeline_design_en_rho_measurement [INFERRED 0.75]
- **Tactical map per-frame render pipeline** — pyqtgraph_display_update_display, pyqtgraph_display_update_threats, pyqtgraph_display_update_assignment_lines, pyqtgraph_display_update_trajectory_lines, pyqtgraph_display_update_batteries [EXTRACTED 1.00]
- **Trajectory-based engagement feasibility and probability pipeline** — config_mip_calculate_trajectory_intercept_point, config_mip_can_engage_trajectory, config_mip_calculate_engagement_time_window, config_mip_calculate_window_adjusted_probability, config_mip_create_engagement_matrix [INFERRED 0.85]
- **Sim thread to GUI display shared tracker state** — multi_missile_tracker_gui_run_sim_thread, multi_missile_tracker_gui_on_display_tick, pyqtgraph_display_tacticalmapwidget, multi_missile_tracker_gui_optimizedassignmentmanager [INFERRED 0.75]
- **DWTA optimizer strategies implementing shared solve/create_model interface** — ga_optimizer_geneticalgorithmoptimizer, greedy_optimizer_greedyoptimizer, clean_slate_optimizer_cleanslateoptimizer [INFERRED 0.85]
- **Optimizers sharing Asset/InterceptorSystem/Threat dataclasses and engagement-matrix data** — ga_optimizer_geneticalgorithmoptimizer, greedy_optimizer_greedyoptimizer, clean_slate_optimizer_build_problem [INFERRED 0.85]

## Communities (94 total, 23 thin omitted)

### Community 0 - "Clean-Slate Optimizer & Scenarios"
Cohesion: 0.18
Nodes (34): Asset, InterceptorSystem, EnhancedEngagementMatrix, KFactorCache, MIPConfig, MIP 최적화 통합 설정 - 현실적 규모 버전, 교전 가능성 및 관련 파라미터 사전 계산 (최적화 #1), K-factor 사전 계산 캐시 + 경량 실시간 계산 (최적화 #3) (+26 more)

### Community 1 - "Configuration & Engagement Models"
Cohesion: 0.20
Nodes (8): DWTABalancedScenario, 제약된 방어 자원 (6개 포대)         - LSAM 3개 (20발/포대) = 60발         - MSAM 3개 (30발/포대) =, 균형잡힌 자산 가치 분포 (10개)         - 균등 분포로 편차 최소화         - 총 가치: 9,500, 시나리오 타입에 따라 자산, 배터리, 위협 생성, DWTA 설계 원칙을 적용한 위협 생성         - NODONG: Y=500km (상층 방어)         - SCUD_B: Y=80km, 균형잡힌 위협 분배 (20발)         - 모든 자산에 정확히 2발씩 할당         - 동시 발사 + 순차 발사 혼합, int, str

### Community 2 - "Feasibility & McCormick Caches"
Cohesion: 0.11
Nodes (13): str, FeasibilityCache, 비트마스크 기반 교전 가능성 캐시      각 포대(battery)마다 uint64 비트마스크로 feasible한 위협을 관리.     - O(, battery_idx에 대해 feasible한 위협 인덱스 리스트 (bit extraction), threat_idx에 대해 feasible한 포대 인덱스 리스트, 모든 feasible (threat_idx, battery_idx) 쌍 반환, 특정 레이어의 feasible (system_id, threat_id) 쌍 반환, 특정 threat에 대해 feasible한 상층 system ID 리스트 (+5 more)

### Community 3 - "Tactical Map Widget (PyQtGraph)"
Cohesion: 0.08
Nodes (16): Return time-to-arrival in seconds for an active missile., Return (r, g, b, a) tuple based on TTA urgency., Update threat scatter + glow ring with TTA-based colour.          Unassigned thr, 미교전 위협(배터리 미할당)만 궤적선 표시., Return 0/1/2 for red/yellow/green — used to detect pen changes., Draw engagement lines: battery → threat.          Reuses existing PlotCurveItem, Called immediately on intercept signal: removes lines + refreshes scatter., Update battery markers: colour by ammo, ammo bar below, highlight when assigned. (+8 more)

### Community 4 - "K-Factor & McCormick Computation"
Cohesion: 0.09
Nodes (13): float, McCormickCoefficients, 기본 요격 확률 (O(1) lookup), K-factor 조회 (캐시에서, O(1)), 실시간 K값 계산 (LUT 기반, 초경량)                  Args:             threat_pos: 위협 현재 위치, 거리 기반 K값 계산 (LUT 사용, O(1))          Args:             distance: 위협-시스템 거리 (km), 위협의 비행 단계 판별          탄도 미사일 비행 단계:         - Boost phase:     0% ~ 15% of fligh, 시간 종속 K-factor: k(t) = k_geometric × k_temporal(phase, t)          기존 거리 기반 k에 비 (+5 more)

### Community 5 - "MIP Solver Techniques"
Cohesion: 0.06
Nodes (41): Bipartite Graph-Based Problem Decomposition, Branch and Bound (B&B), CSR Sparse Matrix, Exact Algorithm (Global Optimality Guarantee), FBBT (Feasibility-Based Bound Tightening), Huffman Binary Tree, LP Relaxation, McCormick Relaxation (+33 more)

### Community 6 - "Simulation Engine (MultiMissileTracker)"
Cohesion: 0.17
Nodes (8): _calculate_stress_metrics(), Called by MultiMissileTracker internals. Thread-safe via signal., Invalidate active threats count cache, Invalidate operational battery and ammo cache, Advance simulation by one time step., Handles dynamic scenario changes including controlled retargeting events., Process missile impact with comprehensive shoot-look-shoot logic., Stress test 메트릭 계산 (iteration 종료 시 1회만 호출)

### Community 7 - "Clean-Slate MIP Model Building"
Cohesion: 0.10
Nodes (30): bool, float, int, str, apply_warmstart(), build_model(), build_problem(), _check_feasibility() (+22 more)

### Community 8 - "Genetic Algorithm Optimizer"
Cohesion: 0.14
Nodes (8): 진짜 유전 알고리즘 실행 (Population-based Evolution), 교전 가능하고 용량이 남은 시스템 목록 반환 (동시 교전 제약 포함), Fitness 평가 (목적함수 = 기댓값 손실) + 제약 위반 페널티, Uniform Crossover (각 할당을 독립적으로 교환), Mutation (일부 할당을 랜덤하게 재할당), 지역 탐색 (Local Search) - 목적함수 기반 개선         현재 할당에서 작은 변경을 시도하여 목적함수를 개선, 목적함수 계산: MIP와 동일한 방식         MIN_DAMAGE: min Σ B_i * [Π (1 - x*k*P)]         = 기, K-factor 가져오기: 캐시에서 또는 거리 기반 계산

### Community 9 - "Main Window GUI Layout"
Cohesion: 0.14
Nodes (5): DWTAMainWindow, Update solver time, warm-start, or objective value labels., Compatibility: tracker calls this after update_simulation()., DWTA 단일 PyQt5 메인 윈도우.     tkinter ControlPanel + matplotlib figure 를 완전히 대체한다., QMainWindow

### Community 10 - "Scenario Generation & Deployment"
Cohesion: 0.06
Nodes (42): 1. 대응 관계 (ROS2 ↔ TA), 2. 전역 선언 (shared), 3.1 radar_node (10 Hz, 시간/월드 권위), 3.1 surveillance_radar_node (중앙 감시레이다, 10 Hz, 시간/월드 권위), 3.1b fire_control_radar_node[b] (포대 사격통제레이다, 포대당 1개), 3.2 threat_assessment_node (5 Hz), 3.3 engageability_node (5 Hz, Pk 게이트), 3.4 planning_node (2 Hz, WTA) (+34 more)

### Community 12 - "Assignment Manager Data Structure"
Cohesion: 0.15
Nodes (21): balanced_scenario(), Battery, default_scenario(), distance(), lsam(), msam(), 시나리오 + 미사일/포대 스펙 (numpy-only, no pydantic / GUI deps).  레이다는 역할별로 분리:   - 중앙 감시레, 방어 자산(요격체계/발사대) 사양 + 가용 자원. (+13 more)

### Community 13 - "Config Class Aggregates"
Cohesion: 0.16
Nodes (15): AssetConfig, BatteryDeploymentConfig, EngagementZoneConfig.calculate_engagement_time_window, EngagementZoneConfig.calculate_trajectory_intercept_point, EngagementZoneConfig.calculate_window_adjusted_probability, EngagementZoneConfig.can_engage_trajectory, EngagementZoneConfig.create_engagement_matrix, InterceptorSystemConfig (+7 more)

### Community 14 - "GUI Controls & Event Handlers"
Cohesion: 0.10
Nodes (11): _draw_star(), _LegendWidget, _pentagon_points(), TacticalMapWidget - PyQtGraph Tactical Display for DWTA Operator ===============, Configure plot axes, background, and labels., Pre-allocate all scatter/line plot items., 좌하단 고정 범례 — QPainter 기반 실제 심볼 렌더링., 우상단 HUD 오버레이 QLabel 초기화. (+3 more)

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

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (32): BaseModel, BatteryPosition, Config, EnemyMissile, EnemyMissileSpec, InterceptorConfig, AssetConfig, BatteryDeploymentConfig (+24 more)

### Community 28 - "Community 28"
Cohesion: 0.50
Nodes (3): bool, str, 이 무기 시스템이 특정 위협 유형을 요격할 수 있는지 확인합니다.

### Community 29 - "Community 29"
Cohesion: 0.10
Nodes (10): 방어 자산 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 포대 배치 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 위협 미사일 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용, 현실적인 시나리오 생성 - 시나리오 타입에 따라 다른 위협 구성, 전구 방어 구역 기반 포대 배치 - 각 자산당 전담 상층/하층 시스템 배정, L-SAM (장거리 지대공 미사일) 실제 스펙, 세밀한 시간 기반 북한 탄도탄 15발 시나리오 (노동 + Scud-B), M-SAM (중거리 지대공 미사일) 실제 스펙 - 한국형 천궁-II (+2 more)

### Community 30 - "Community 30"
Cohesion: 0.14
Nodes (8): bool, 교전 가능 여부 (정적 precompute + 실시간 거리 체크)                  Args:             battery_, 우선순위 기반 주요 방어 자산 10개 선택, 미사일 궤적에서 교전 시점의 위치와 고도 계산, 궤적 기반 교전 가능성 및 교전 시간 윈도우 계산, 포대가 위협을 교전할 수 있는지 계산 (궁적 기반), 교전 타임 윈도우 계산 - 궁적 기반 실시간 분석, 교전 윈도우 기반 조정된 요격 확률 계산

### Community 31 - "Community 31"
Cohesion: 0.12
Nodes (8): 특정 위협에 대해 유효한 state 조합만 생성                  Args:             threat_id: 위협 ID, ③ CSR Sparse Index: feasible (system, threat) 쌍의 인덱스 구조      모든 메서드에서 이중 루프 대신 사, engagement matrix에서 1회 순회로 feasible pair 인덱스를 구축한다.          Args:             u, feasibility 검사 (EnhancedEngagementMatrix 또는 dict fallback), 특정 threat에 대해 feasible한 상층 system ID 리스트, 특정 threat에 대해 feasible한 하층 system ID 리스트, 특정 system에 대해 feasible한 threat ID 리스트, SparseEngagementIndex

### Community 32 - "Community 32"
Cohesion: 0.05
Nodes (37): C.1 현재 시스템의 모듈 간 상호작용 (수학적 함수로 표현), C.2 모듈 간 데이터 흐름 — 자료구조 매핑, C.3 현재 GUI의 문제점과 Clean Slate 통합 전략, C.4 통합 구현 계획, C.5 구현 우선순위, C.6 발견된 문제: Segfault (HiGHS/engagement_matrix), C.7 검증 체크리스트, code:block48 (┌───────────────────────────────────────────────────────────) (+29 more)

### Community 33 - "Community 33"
Cohesion: 0.18
Nodes (13): build_nodes(), cli(), main(), Composition entry point: runs all DWTA nodes under one executor.  Valid as a rea, _summary(), Deterministic virtual-clock executor.      spin_for(duration, dt): step a virtua, SingleThreadedExecutor, ThreatAssessmentNode (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.13
Nodes (25): FireControlRadarNode, LauncherNode, BallisticTrack, EngagementPlan, Event, Interceptor, LaunchEvent, RadarStatus (+17 more)

### Community 35 - "Community 35"
Cohesion: 0.11
Nodes (10): CleanSlateOptimizer, MultiMissileTracker, 실시간 DWTA 분석 시뮬레이터 - GUI 지원 버전, Rebuild persistent battery lookup cache, Load realistic scenario with comprehensive threat configuration., Perform real-time optimization (DWTA) with comprehensive logic.          이벤트 기반, Clean Slate: 시뮬레이션 상태에서 옵티마이저 입력 생성.          기존 대비 변경:         - engagement_mat, DWTAMainWindow QTimer(_on_display_tick)가 TacticalMapWidget을 직접 갱신한다. (+2 more)

### Community 36 - "Community 36"
Cohesion: 0.08
Nodes (17): _Bus, _Clock, _Logger, Node, now(), ok(), Publisher, In-process pub/sub bus that mirrors the rclpy API surface.  This lets the *exact (+9 more)

### Community 37 - "Community 37"
Cohesion: 0.15
Nodes (13): ControlStationNode, 통제소 노드 — 방어정책 발행 (전시/평시, 단발/연속, 위협당 최대 요격탄)., OO 가능성 평가 노드 — 교전 가능성/명중률 매트릭스.  탄도탄 예상궤적(/tracks) + 요격체계 상태(/interceptor_status, 포대 사격통제레이다 노드 (Fire-Control Radar, FCR) — 요격탄 유도용.  포대마다 1개. 자기 포대의 발사(LAUNCH) 이, DWTA ROS2 nodes (rclpy-compatible; runs under real ROS2 or the in-process shim)., 발사대 노드 (Launcher) — 교전계획 실행(물리 발사 + 탄약).  교전계획(/engagement_plan)을 받아 요격탄을 발사한다., DefensePolicy, Message types for the DWTA ROS2 pipeline.  For the PoC these are plain dataclass (+5 more)

### Community 38 - "Community 38"
Cohesion: 0.32
Nodes (5): Asset, InterceptorSystem, Greedy DWTA Optimizer ===================== Greedy 알고리즘 기반 DWTA 최적화기 (독립 모듈)  전략, Greedy 모델 생성 - 데이터 구조 초기화, Threat

### Community 41 - "Community 41"
Cohesion: 0.13
Nodes (24): EngageabilityNode, BatteryState, EngagementMatrix, ThreatScores, ThreatState, TrackArray, latched_qos(), QoS for the shared world-state topic.      Real ROS2: TRANSIENT_LOCAL durability (+16 more)

### Community 42 - "Community 42"
Cohesion: 0.07
Nodes (27): 7a. `BipartiteDecomposer` 클래스 (Union-Find), 7b. `solve()` 수정, 7c. `_solve_decomposed(components)`, code:block1 (Step 1: SparseEngagementIndex (Phase 1) — 기반 구조, 나머지 모두에 활용), code:block2 (Phase 1:  [1. CSR Sparse Index]  ← 기반 구조), code:block3 (sum_i(x_ij) ≤ min(C_j, floor(M_j / m))   ∀ battery j), code:block4 (sum_j(x_ij_upper + x_ij_lower) ≥ 1   ∀ threat i : B_i > thre), code:block5 (sum_j(x_ij_upper) + sum_j(x_ij_lower) ≤ 1 + 1[high_value]) (+19 more)

### Community 43 - "Community 43"
Cohesion: 0.07
Nodes (27): 0.1 원래 목적함수 (Primal), 0.2 동치 변환: 단계별 증명, 0.3 동치성 요약, 0.4 k 상수화의 정당성, 0. 수학적 동치 증명 (Original ↔ Log-Linear), code:block1 ([P]  min  Z = Σᵢ Bᵢ × (1 - Sᵢ)), code:block10 (exp(σ) ≥ exp(σᵏ)(1 + σ - σᵏ)    ∀ σ, σᵏ), code:block11 (fᵢ ≥ exp(σᵏ)(1 + σᵢ - σᵏ)    ∀ k = 1..K) (+19 more)

### Community 44 - "Community 44"
Cohesion: 0.19
Nodes (6): Called on main thread when simulation thread exits., Fires every 250 ms on the main thread — refresh all visual elements., 누적 로그 방식: 신규 위협은 행 추가, 기존 위협은 상태만 갱신., Flash alert bar if there are unengaged high-danger threats., Trigger flash + immediately clean up engagement lines and threat dot., Get operational batteries with caching (O(1) after first call)

### Community 45 - "Community 45"
Cohesion: 0.08
Nodes (25): ⑩ Bipartite Graph-Based Problem Decomposition, ① FBBT (Feasibility-Based Bound Tightening), ③ CSR (Compressed Sparse Row) Sparse Matrix, ④ OBBT (Optimality-Based Bound Tightening), ⑤ Piecewise McCormick, ⑦ Problem-Specific Valid Inequalities, ⑨ Huffman Binary Tree (Weighted Binary Tree Redesign), code:block1 (Phase 1 [Data Structure]   ③ CSR Sparse Matrix) (+17 more)

### Community 46 - "Community 46"
Cohesion: 0.12
Nodes (25): Assignment, Assignment, EngagementCell, (요격체계, 탄도탄) 교전 가능성 한 칸: 교전창 + 명중률., ThreatScore, PlanningNode, GreedyWTA, LegacyGreedyAdapter (+17 more)

### Community 47 - "Community 47"
Cohesion: 0.13
Nodes (15): code:python (def measure_rho(scenario):), code:python (# Run two conditions:), code:python (# For each (i,j) after FBBT, record:), code:python (solver.setOptionValue("output_flag", True)), code:block32 (Option A — Discrete tiers:), code:python (import networkx as nx), code:python (metrics = {), M1 — Measure ρ (Feasible Engagement Ratio) (+7 more)

### Community 48 - "Community 48"
Cohesion: 0.22
Nodes (7): 불확실성 모델링 및 몬테카를로 시뮬레이션 모듈 ==================================================== 요, 불확실성 모델링 및 몬테카를로 시뮬레이션, 기본 요격 확률에서 불확실성을 고려한 베타 분포 샘플링, test_uncertainty_modeling(), UncertaintyModeling, float, str

### Community 49 - "Community 49"
Cohesion: 0.14
Nodes (14): 0.7 병렬화 분석 — 무엇을 분산할 것인가, 1. `build_problem()` 내부 — k/p/c 계산, 2. `build_model()` — 제약 행렬 구성, 3. `model.run()` — HiGHS 솔버, 4. 시뮬레이션 레벨 병렬화 (타임스텝 간), 5. 멀티 시나리오 / 비교 모드 병렬화, code:block19 (build_problem()    : ~0.5ms  (NumPy 배열 생성, k/p/c 계산)), code:python (# 현재 (순차):) (+6 more)

### Community 50 - "Community 50"
Cohesion: 0.11
Nodes (17): 1) ROS2 없이 (어디서나 — Windows/Linux/Mac, Python만 필요), 2) 실제 ROS2 (rclpy), code:block1 ([경보체계]              [통제체계 (결심)]                          [체계), code:bash (python3 ros2_dwta/run_poc.py 45      # 45초 시뮬레이션), code:bash (# 워크스페이스에 dwta_ros2/ 를 두고), code:block4 ([t= 15.50s] 위협 30  ASSESSED=23 ENGAGEABLE=1 ENGAGED=6), dwta_ros2 — 실시간 DWTA C2 파이프라인 (ROS2 노드 모델), 다이어그램 ↔ 노드 매핑 (+9 more)

### Community 51 - "Community 51"
Cohesion: 0.17
Nodes (12): 1.1 현재 Formulation의 복잡도 원인, 1.2 핵심 수학적 통찰 3가지, 1.3 최종 Formulation, 1.4 모델 크기 비교, 1. 수학적 본질 분석, code:block24 (현재: min Σ Bᵢ × (1 - Πⱼ(1 - xⱼₜ × kⱼₜ × Pⱼ))), code:block25 (x_jt ∈ {0,1}이므로:), code:block26 (max Σ Bᵢ × exp(σᵢ)    where σᵢ = Σ c_jt × x_jt) (+4 more)

### Community 52 - "Community 52"
Cohesion: 0.17
Nodes (10): A.1 전체 파이프라인을 수학 함수로 표현, A.2 데이터 흐름 매핑 (누가 → 무엇을 → 누구에게), A.3 객체 간 데이터 의존성 그래프, A.4 Clean Slate에서 보존해야 할 인터페이스 계약, code:block41 (Advance: SimState × ℝ → SimState'), code:block42 (┌───────────────────────────────────────────────────────────), code:block43 (ScenarioConfig ──────→ assets[], batteries[], threats[]), code:python ({) (+2 more)

### Community 53 - "Community 53"
Cohesion: 0.21
Nodes (6): OptimizedAssignmentManager, 하이브리드 자료구조: 빠른 쓰기 O(1) + 빠른 탐색 O(1)~O(k)     - battery_to_threats: List[List[int, Process comprehensive optimization results with enhanced assignment validation., 새로운 할당으로 병합 (MIP 제약 조건 준수)                  제약 조건:         - 위협당 상층 최대 1개 배터리, int, str

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (9): 3.1 Design Principles, 3.2 Phase 1 — Feasibility Cache Implementation, 3.3 Phase 4 — Bitmask-Accelerated Bipartite Decomposition, 3.4 Extended: Bitmask for FBBT Propagation (Optional), code:python (import numpy as np), code:python (cache = FeasibilityCache(n_threats=100, n_batteries=6)), code:python (groups = find_independent_groups_bitmask(active_pairs, n_bat), code:python (# After each FBBT deduction, clear the bit:) (+1 more)

### Community 55 - "Community 55"
Cohesion: 0.15
Nodes (8): int, BinaryTreeMcCormickCache, 새로운 위협에 대해서만 증분 계산                  Args:             batteries: 포대 리스트, 이동 중인 위협의 현재 위치 기반으로 교전 매트릭스 동적 업데이트.          기존 정적 precompute는 발사 위치 기반이었으나, 이, 동적 업데이트된 교전 매트릭스의 거리 정보로 k-factor 캐시 갱신.          update_moving_threats() 이후 호출하, 🆕 Binary Tree McCormick 계수 캐시 (선택적 최적화)          자산별 생존 확률 곱셈에 사용되는 McCormick 계수, Binary Tree 깊이 계산 (캐싱), 필요한 McCormick 적용 횟수 계산 (캐싱)

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (9): 1.1 Data Type Contract (Per Phase), code:block1 (┌───────────────────────────────────────────────────────────), code:python (solver = highspy.Highs()), code:python (# Use ProcessPoolExecutor — HiGHS is CPU-bound, GIL applies ), code:python (x_optimal  : dict[tuple[int,int], int]   # {(i,j): 0 or 1}), code:block27 (Main Thread (sequential spine):), Execution Thread Map, Part 1 — Recommended Full Pipeline (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (9): 0.6 자료구조 선정 근거 — 연산 최적화 관점, code:block16 (현재: self.variables['x_upper'][(system_id, threat_id)] → PuLP), code:block17 (변수 레이아웃 (단일 1D 배열):), code:python (@dataclass(frozen=True)), 밀집 vs 희소, 변수 인덱싱 전략, 왜 frozen dataclass인가, 왜 NumPy 밀집 행렬인가 (+1 more)

### Community 59 - "Community 59"
Cohesion: 0.22
Nodes (8): 3.1 비교 분석, 3.2 결정: HiGHS 직접 API (highspy) — 1순위, CP-SAT — 대안, 3. 솔버 선택, 7. 핵심 수치 (Baseline Scenario), Clean Slate DWTA Optimizer — Duality 기반 완전 재설계, code:block39 (자산: 10개, 가치 650-1500), Context, 요약

### Community 60 - "Community 60"
Cohesion: 0.22
Nodes (9): 4.1 자료구조: 연산 최적화 설계, 4.2 함수형 파이프라인, 4.3 HiGHS 모델 빌딩 상세, 4.4 Warm-Start 전략, 4. Clean Slate 아키텍처, code:python (@dataclass(frozen=True)), code:python (# === 순수함수 파이프라인 ===), code:python (def build_model(prob: DWTAProblem) -> Tuple[Highs, VarMap]:) (+1 more)

### Community 61 - "Community 61"
Cohesion: 0.19
Nodes (23): FireControlStatus, InterceptorStatus, 발사대/요격체계 상태 (잔여탄·비행중 요격탄·교전 상태) — 전 노드 공유., 발사대/요격체계 상태 (잔여탄·비행중 요격탄·교전 상태) — 전 노드 공유., 포대 사격통제레이다(FCR) 상태: 유도 채널 점유 현황 — 전 노드 공유., 모든 노드가 구독하는 통합 상황도(적 탄도탄 + 아군 요격탄 상태)., 모든 노드가 구독하는 통합 상황도(적 탄도탄 + 아군 요격탄 상태)., WorldState (+15 more)

### Community 62 - "Community 62"
Cohesion: 0.25
Nodes (8): 5.1 새 파일, 5.2 기존 파일 수정, 5.3 구현 순서, 5.4 의존성, 5. 파일 구조 및 구현 계획, code:block34 (v8/), code:block35 (multi_missile_tracker_gui.py:), code:block36 (필수: highspy (pip install highspy) — 이미 PuLP 백엔드로 설치됨)

### Community 63 - "Community 63"
Cohesion: 0.25
Nodes (8): 6.1 정확도 검증, 6.2 성능 벤치마크 — 실측 결과 ✅, 6.3 Edge Case, 6.3 GUI 통합 실측 결과 ✅ (STRESS_100, 실시간 시뮬레이션), 6.4 GUI 통합 테스트, 6. 검증 계획, code:block37 (시나리오           위협  변수   제약   시간(ms)   상태      | 기존 MIP), code:block38 (시나리오: STRESS_100 (100발 탄도미사일))

### Community 64 - "Community 64"
Cohesion: 0.25
Nodes (8): B.1 핵심 파일 (보존 + 수정), B.2 교체 대상 (Clean Slate가 대체), B.3 비교용 보존 (선택적), B.4 제거 가능 (불필요 또는 중복), B.5 문서 정리, B.6 제안 프로젝트 구조, code:block47 (v8/), 부록 B. 프로젝트 파일 정리 — 보존/제거 분류

### Community 67 - "Community 67"
Cohesion: 0.33
Nodes (5): 2.1 Lagrangian Dual, 2.2 Duality Gap, 2.3 왜 Lagrangian이 필요 없는가, 2. Duality 분석, code:block29 (max Bᵢ × exp(Σ c_jt × x_jt) - Σ (λⱼ + μⱼ) × x_jt)

### Community 68 - "Community 68"
Cohesion: 0.40
Nodes (5): code:python (k_bounds : dict[tuple[int,int], tuple[float, float]]), code:python (with ThreadPoolExecutor(max_workers=4) as ex:), code:python (active_pairs    : list[tuple[int, int]]), code:block9 (For each (i, j) in active_pairs (independently):), Phase 2B — OBBT: K-factor Bound Tightening  ④

### Community 71 - "Community 71"
Cohesion: 0.50
Nodes (4): code:python (active_pairs : list[tuple[int, int]]), code:block13 (For each (i, j):), code:python (# Variable index maps), Phase 3A — Piecewise McCormick Constraint Generation  ⑤

### Community 72 - "Community 72"
Cohesion: 0.50
Nodes (4): code:python (B            : dict[int, float]         # asset value ⚠️ mus), code:block16 (Standard Huffman algorithm:), code:python (tree_root    : HuffmanNode), Phase 3B — Huffman Binary Tree Reconstruction  ⑨

### Community 73 - "Community 73"
Cohesion: 0.50
Nodes (4): code:python (active_pairs    : list[tuple[int, int]]), code:block19 (VI-1 (ammo-engagement bound):), code:python (A_valid : scipy.sparse.csr_matrix   # additional rows append), Phase 3C — Valid Inequalities Insertion  ⑦

### Community 74 - "Community 74"
Cohesion: 0.50
Nodes (4): code:python (threats:      list[ThreatState]), code:block3 (For each (i, j):), code:python (feasible_pairs  : list[tuple[int, int]]     # [(i,j), ...]), Phase 1 — CSR + Bitmask Feasibility Filter  ③

### Community 75 - "Community 75"
Cohesion: 0.50
Nodes (4): code:python (active_pairs    : list[tuple[int, int]]), code:block22 (For each threat i:), code:python (subproblems : list[MIPSubproblem]), Phase 4 — Bipartite Decomposition  ⑩

### Community 76 - "Community 76"
Cohesion: 0.50
Nodes (3): code:block40 (┌───────────────────────────────────────────────────────────), DWTA-MIP: Pipeline Design, Analysis Checklist, and Bitmask Implementation Guide, Summary

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (4): code:python (feasible_pairs  : list[tuple[int, int]]), code:block6 (For each (i, j) in feasible_pairs:), code:python (fixed_zero   : set[tuple[int, int]]          # pairs fixed t), Phase 2A — FBBT: Variable Pre-fixing  ①

### Community 80 - "Community 80"
Cohesion: 0.40
Nodes (5): 0.5 완전한 변수 명세, 결정변수 (Decision Variables), 보조변수 (Auxiliary Variables), 사전계산 상수 (Precomputed Constants), 인덱스 집합 (Index Sets)

### Community 87 - "Community 87"
Cohesion: 0.22
Nodes (4): CleanSlateOptimizer, Backward compatibility., Drop-in replacement for NonLinearMIPOptimizer.      Interface contract:, Provide k-factor cache for distance/time-based k computation.

### Community 88 - "Community 88"
Cohesion: 0.32
Nodes (5): Asset, InterceptorSystem, Genetic Algorithm DWTA Optimizer ================================= 유전 알고리즘 기반 DW, GA 모델 생성 - 데이터 구조 초기화, Threat

### Community 92 - "Community 92"
Cohesion: 0.29
Nodes (3): Simple linear trajectory for visualization., Initialize the fixed scenario threats., Simulation background thread (mirrors ControlPanel.run_simulation_thread).

## Knowledge Gaps
- **224 isolated node(s):** `str`, `bool`, `int`, `str`, `bool` (+219 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `extract_result()` connect `Clean-Slate MIP Model Building` to `Community 36`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Why does `Node` connect `Community 36` to `Community 33`, `Community 34`, `Community 37`, `Community 41`, `Assignment Manager Data Structure`, `Community 46`, `Community 61`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `CleanSlateOptimizer` connect `Community 87` to `Clean-Slate Optimizer & Scenarios`, `Community 35`, `Clean-Slate MIP Model Building`, `Main Window GUI Layout`, `Community 53`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `DWTAMainWindow` (e.g. with `Asset` and `CleanSlateOptimizer`) actually correct?**
  _`DWTAMainWindow` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 39 inferred relationships involving `Battery` (e.g. with `EngageabilityNode` and `FireControlRadarNode`) actually correct?**
  _`Battery` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `KFactorCache` (e.g. with `Config` and `ScenarioManager`) actually correct?**
  _`KFactorCache` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `TacticalMapWidget` (e.g. with `Asset` and `CleanSlateOptimizer`) actually correct?**
  _`TacticalMapWidget` has 20 INFERRED edges - model-reasoned connections that need verification._