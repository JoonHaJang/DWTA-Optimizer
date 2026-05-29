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
| 중앙 감시레이다 | `surveillance_radar_node` (1개) | 10 Hz | 탐지·추적 → `/tracks`, `/radar_status`, `/events` |
| 포대 사격통제레이다 | `fire_control_radar_node` (**포대당 1개**) | 10 Hz | 요격탄 유도+판정 → `/events`(INTERCEPT/MISS), `/fire_control_status` |
| OO평가 | `threat_assessment_node` | 5 Hz | `/tracks` + 자산가치 → `/threat_scores`(점수화) |
| OO가능성평가 | `engageability_node` | 5 Hz | `/tracks` + `/interceptor_status` + 방어영역 → `/engagement_matrix`(교전창·Pk) |
| OO계획수립(WTA) | `planning_node` | 2 Hz | scores + matrix + `/policy` → `/engagement_plan` |
| 발사대 | `launcher_node` | 이벤트+5 Hz | `/engagement_plan` → `/launch_events`, `/interceptor_status` |
| 통제소 | `control_station_node` | 1 Hz | → `/policy` |
| 상황도(COP) | `world_state_node` | 2 Hz | 전 토픽 구독 → `/world_state`(latched) |
| 표시(분리) | `viz_node` | 0.5 Hz | `/world_state` 구독 → PyQtGraph/ASCII 전술화면 |

## 레이다 다중 객체 처리 (중앙 vs 포대)

레이다는 역할이 다른 복수 객체이므로 노드를 분리:
- **중앙 감시레이다** `surveillance_radar_node` (전구 1개): 적 탄도탄 탐지·추적, 표적
  할당용 트랙(`/tracks`) 제공.
- **포대 사격통제레이다** `fire_control_radar_node` (포대당 1개): 자기 포대의 요격탄을
  유도. **유도 채널 수(`fire_control_channels`)가 그 포대의 동시 교전 한계**이며,
  비행시간 경과 후 요격 성공/실패를 판정해 `/events`로 공유.

→ 그 결과 포대의 동시 교전 한계는 **min(잔여탄, 유도 채널)**: `launcher_node`(탄약)와
`fire_control_radar_node`(유도 채널)가 별개 자원으로 협력. 새 포대/레이다를 추가하려면
`fire_control_radar_node` 인스턴스를 하나 더 띄우면 됩니다(노드 인스턴스 = 물리 객체).

## 시나리오 (포화 / 상하층 동시)

`SCENARIOS = {balanced, saturation}` (`scenario.py`). 기본은 `saturation`:
- 임의 스펙: L-SAM(사거리160·Pk0.86·채널4), M-SAM(중첩사거리130·Pk0.90·채널5) ×2,
  고속 위협 20발 집중 버스트.
- 결과: 상층(L) 교전 진행 중 하층(M) 중첩 사거리 진입 → **상·하층 동시 교전**
  (예: L1 4발 + M1/M2 각 1~2발 동시 비행). `python3 run_poc.py 60 saturation`.
- 소규모 기능 확인: `python3 run_poc.py 45 balanced`.

## 정보 공유 / 이벤트 / COP

- **통합 이벤트 버스 `/events`**: `DETECTED / LAUNCH / INTERCEPT / MISS / IMPACT`.
  레이다·발사대가 발행하고 관련 노드가 구독해 **이벤트 기반으로 상태가 전파**됩니다.
- **아군 요격탄 상태 공유**: `launcher_node`가 비행중 요격탄(`Interceptor`: 표적·
  비행시간·Pk·상태)을 `/interceptor_status.in_flight`로 발행 → engageability·planning이
  잔여탄/비행중을 단일 진실원으로 사용. **MISS 시 자동 재교전(SLS)**, `INTERCEPT/IMPACT`는
  종결 처리(재할당 금지).
- **Common Operational Picture `world_state_node`**: 적 탄도탄 생명주기
  (DETECTED→ASSESSED→ENGAGEABLE→ENGAGED→INTERCEPTED/LEAKED)와 아군 포대(잔여탄·비행중·
  교전중)를 하나의 `/world_state`로 집계해 **모든 노드가 동일한 상황 인식**을 갖습니다
  (latched QoS로 늦게 합류한 노드도 최신 COP 수신).

## 형식 명세 (spec-first, 타임드 오토마타)

`spec/` — ROS2 구조를 구현 전에 형식 명세로 고정하고 검증:
- `spec/timed_automata.md` — 노드=오토마타, 토픽=채널, 주기=클럭 명세 + 검증 속성.
- `spec/dwta_model.xml` — UPPAAL 모델(위협/요격탄 생명주기). 검증 쿼리:
  교착없음, `ammo>=0`, `inflight<=CAP`, 모든 위협 종결(라이브니스), 전량요격 가능 등.

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

## 표시 분리 (viz_node)

표시는 `/world_state`만 구독하는 **별도 노드**로 분리되어 시뮬레이션과 완전 독립:
- 백엔드 `pyqtgraph`(실시간 전술화면, 디스플레이 필요) / `ascii`(헤드리스 폴백, 기본).
- 켜기: `python3 run_poc.py 60 saturation viz`. 표시를 꺼도/교체해도 파이프라인 무영향.
- 실 ROS2에서는 `viz_pyqtgraph.TacticalView`를 Qt 메인루프 + `rclpy.spin`(스레드)로 구동
  (모듈 docstring 참고). 기존 `pyqtgraph_display.TacticalMapWidget`도 같은 방식으로 연결 가능.

## 현재 PoC의 단순화 (다음 단계)

- 요격 판정은 결정적(Pk≥θ). → 확률·기동/이심률 등 연속 동역학으로 고도화.
- 노드별 독립 실행파일 + 파라미터(YAML) 분리, 콜백그룹/결정적 executor 적용.
- `viz_node`로 PyQtGraph 표시 분리(현재 GUI는 별도).
- 다포대(여러 L-SAM) 확장 시 표적할당 충돌 회피(중복 교전 최소화) 정책 추가.
