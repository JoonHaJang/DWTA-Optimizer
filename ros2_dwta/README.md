# dwta_ros2 — 실시간 DWTA C2 파이프라인 (ROS2 노드 모델)

기존 모놀리식 실시간 시뮬레이터(`multi_missile_tracker_gui.py`의 단일
`_run_sim_thread` 루프)를, 임무절차 다이어그램처럼 **독립적으로 도는 노드 루프**로
재구성한 PoC입니다. 각 노드는 ROS2 타이머 콜백(독립 주기)으로 동작하고 토픽으로
비동기 통신합니다.

```
[경보체계]              [통제체계 (결심)]                          [체계]
radar_node ──/tracks──► threat_assessment_node ──/threat_scores──┐
   (10Hz)               engageability_node ──────/engagement_matrix┤
   │  /radar_status         ▲ (window+Pk, 5Hz)                     ▼
   │                        │                          planning_node (WTA, 2Hz)
launcher_node ◄──/engagement_plan────────────────────────────────┘
 (발사·잔여탄)  ──/interceptor_status──► (engageability·planning 피드백)
   └──/launch_events──► radar_node (요격 반영, 폐루프)
control_station_node ──/policy(전시·평시, SLS/SSL, 위협당 최대탄)──► planning_node
```

## 다이어그램 ↔ 노드 매핑

| 다이어그램 블록 | 노드 | 주기 | 입력 → 출력 |
|---|---|---|---|
| 레이다/경보 | `radar_node` | 10 Hz | (시나리오) → `/tracks`, `/radar_status` |
| OO평가 | `threat_assessment_node` | 5 Hz | `/tracks` + 자산가치 → `/threat_scores`(점수화) |
| OO가능성평가 | `engageability_node` | 5 Hz | `/tracks` + `/interceptor_status` + 방어영역 → `/engagement_matrix`(교전창·Pk) |
| OO계획수립(WTA) | `planning_node` | 2 Hz | scores + matrix + `/policy` → `/engagement_plan` |
| 발사대 | `launcher_node` | 이벤트+5 Hz | `/engagement_plan` → `/launch_events`, `/interceptor_status` |
| 통제소 | `control_station_node` | 1 Hz | → `/policy` |

WTA 백엔드는 교체식(`dwta_nodes/wta_backend.py`): 기본 `GreedyWTA`(위험도 우선,
상·하층/동시교전/잔여탄 제약). 기존 `greedy_optimizer`/`ga_optimizer`/
`clean_slate_optimizer`(MIP)는 `WTABackend.solve()` 시그니처만 맞추면 끼웁니다
(`LegacyGreedyAdapter` 참고).

## 실행

### 1) ROS2 없이 (어디서나 — Windows/Linux/Mac, Python만 필요)
```bash
python3 ros2_dwta/run_poc.py 45      # 45초 시뮬레이션
```
`dwta_nodes/sim_bus.py`의 **결정적 인프로세스 executor**가 가상 클럭으로 각 노드의
타이머를 주기대로 발화하고, 메시지를 **1-tick 지연(LET 유사)**으로 전달합니다 →
실행이 재현 가능(모델체킹 친화적). 동일한 노드 코드가 그대로 쓰입니다.

### 2) 실제 ROS2 (rclpy)
```bash
# 워크스페이스에 dwta_ros2/ 를 두고
colcon build --packages-select dwta_ros2
source install/setup.bash
ros2 launch dwta_ros2 dwta_poc.launch.py     # 또는: ros2 run dwta_ros2 dwta_poc
```
`dwta_nodes/ros_compat.py`가 `rclpy` 존재 시 자동으로 실제 ROS2 백엔드를 선택합니다
(코드 수정 불필요). 메시지는 PoC에서 dataclass를 쓰며, 실배포 시 `ros2_dwta/msg/`의
`.msg`로 **`dwta_msgs` rosidl 패키지**를 만들어 교체하면 됩니다(필드명 동일).

## 실시간/계층 스케줄링 메모 (조사 결과 반영)

- **노드 실행 결정성**: 기본 rclpy executor는 비결정·우선순위역전 이슈가 있음.
  실시간이 필요하면 **Events Executor / Callback-group Executor**(LET, CPU 10–15%↓)
  또는 마이크로컨트롤러급 **rclc Executor**(정적 순서+LET) + 콜백그룹 사용.
- **OS 실시간**: 리눅스 **PREEMPT_RT + SCHED_DEADLINE(EDF)** (메인라인·유지보수).
- **계층 스케줄링(대규모 검증)**: 결심 오케스트레이션은 **BehaviorTree.CPP**
  (Nav2·MoveIt 검증), 안전필수 파티셔닝은 **ARINC 653**(XtratuM/POK; 항전 IMA 표준).
  ※ LITMUS^RT는 연구 테스트베드(2017 이후 미유지보수)라 비권장.
- **정형 검증**: 노드=타임드 오토마타, 토픽=채널, 주기=clock invariant 로 보면
  **UPPAAL**에서 데드라인·교전창 누락을 모델체킹 가능(구조가 1:1 대응).

## 플랫폼 (Windows 포함)

| 구성요소 | Windows | 비고 |
|---|---|---|
| 본 PoC(`run_poc.py`, shim) | ✅ | Python만 있으면 동작 (numpy 불요) |
| ROS2 / rclpy | ✅ | Humble/Jazzy Windows 바이너리 지원(설치는 무거움) |
| BehaviorTree.CPP | ✅ | 크로스플랫폼 |
| PREEMPT_RT / SCHED_DEADLINE | ❌ | 리눅스 커널 전용 |
| ARINC 653 (XtratuM/POK), LITMUS^RT | ❌ | 리눅스/RTOS·베어메탈 전용 |

요약: **개발·시뮬레이션은 Windows로 충분**하지만, **경성 실시간 보장(하드 RT)은
리눅스/RTOS**가 필요합니다.

## 현재 PoC의 단순화 (다음 단계)

- 요격은 결정적 단발(사격=제거)로 모델. → Pk 확률·비행시간 모델로 누설/재교전 추가.
- 기하 특성상 상층(L-SAM)이 먼저 요격 → 하층(M-SAM)·동시 다발 포화 시나리오 튜닝.
- 노드별 독립 실행파일 + 파라미터(YAML) 분리, 콜백그룹/결정적 executor 적용.
- `viz_node`로 PyQtGraph 표시 분리(현재 GUI는 별도).
