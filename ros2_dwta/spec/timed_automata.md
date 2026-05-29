# DWTA 실시간 파이프라인 — 타임드 오토마타(Timed Automata) 명세

ROS2 노드 구조를 **먼저 형식 명세**로 고정해 두기 위한 문서입니다. 각 노드를
타임드 오토마타로, 토픽을 채널로, 주기를 클럭으로 보면 구조가 1:1 대응되며,
구현(`dwta_nodes/`) 이전에 타이밍·자원·생명주기 불변식을 UPPAAL로 검증할 수 있습니다.

- 검증 가능한 축약 모델: [`dwta_model.xml`](./dwta_model.xml) (UPPAAL에서 바로 로드).
- 본 문서: 전체 노드 망(網)의 형식 명세 + 검증 속성.

## 1. 대응 관계 (ROS2 ↔ TA)

| ROS2 개념 | 타임드 오토마타 |
|---|---|
| 노드(주기 타이머 루프) | 템플릿(자동기) + 클럭 `c`, 불변식 `c <= period` |
| 토픽 publish/subscribe | 채널 `topic!` / `topic?` (broadcast=다수 수신) |
| 메시지 페이로드 | 전역/지역 변수 (정수 추상화) |
| 공유 상태(COP) | 전역 변수 `ammo, inflight, killed, leaked`, 위협 위치(`loc`) |
| 콜백 실행 | 위치 간 전이(transition), 가드/할당 |
| 주기(period) | 클럭 불변식 + 가드 `c >= period`로 reset |

## 2. 전역 선언 (shared)

```
const int N;            // 위협 수
const int CAP;          // 동시 교전 수 (= Interceptor 인스턴스 수)
const int ENTER;        // 교전영역 진입 시각 (engageability 게이트)
const int IMPACT;       // 탄착 시각 (미요격 누설)
const int FLYOUT;       // 요격탄 비행시간
const int PERIOD_*;     // 노드별 주기 (radar=0.1, assess=0.2, engage=0.2, plan=0.5, ...)

int  ammo;              // 잔여 요격탄        ┐
int  inflight;          // 비행중 요격탄 수    │ 전 노드 공유 (COP)
int  killed, leaked;    // 종결 누계           ┘
chan assign[N], hit[N], miss[N];   // 교전배정/성공/실패
broadcast chan tracks, scores, matrix, plan, status, policy;  // 노드 주기 발행
```

## 3. 노드 템플릿 명세

각 노드는 "주기 클럭 + 발행" 패턴의 타임드 오토마타입니다. 핵심만 표기.

### 3.1 surveillance_radar_node (중앙 감시레이다, 10 Hz, 시간/월드 권위)
```
clock c;  loc Run (invariant c <= PERIOD_R)
Run --[c >= PERIOD_R]--> Run : tracks! ; c := 0          // 추적 발행
Run --(threat enters)--> : detected!                      // 이벤트
Run --hit[t]?--> : (위협 t 제거)                           // 요격 반영(폐루프)
```
불변식: `c <= PERIOD_R` (주기 보장). 이벤트 `detected/impact` 발행.

### 3.1b fire_control_radar_node[b] (포대 사격통제레이다, 포대당 1개)
요격탄 유도 = `Interceptor` 슬롯이 곧 유도 채널. 포대 b의 채널 수 `CH[b]`가 동시
교전 한계. LAUNCH 수신 시 채널 점유, FLYOUT 경과 시 hit/miss 판정.
```
loc Idle ──launch[b,t]?──> Guiding(f <= FLYOUT[b]) ──[f>=FLYOUT[b]] hit[t]!|miss[t]!──> Idle
```
인스턴스 수 = `CH[b]` 이므로 포대별 `inflight[b] <= CH[b]` 가 구조적으로 보장.

### 3.2 threat_assessment_node (5 Hz)
```
clock c;  loc Run (inv c <= PERIOD_A)
Run --tracks?--> Run : (최신 트랙 저장)
Run --[c >= PERIOD_A]--> Run : scores! ; c := 0           // 점수화 발행
```

### 3.3 engageability_node (5 Hz, Pk 게이트)
```
Run --tracks?/status?--> Run : (상태 갱신)
Run --[c >= PERIOD_E]--> Run : matrix! ; c := 0
  // 가드: 위협이 사거리 내 && TTA >= MIN_TTA && Pk >= MIN_PK 인 칸만 발행
```

### 3.4 planning_node (2 Hz, WTA)
```
Run --scores?/matrix?/policy?/status?/event?--> Run : (입력 갱신, terminal/covered 집합 갱신)
Run --[c >= PERIOD_P && have(scores,matrix)]--> Run : plan! ; c := 0
  // covered(비행중)·terminal(요격성공/탄착) 위협 제외 후 WTA solve
```

### 3.5 launcher_node (이벤트 + 5 Hz)  — `Interceptor` 슬롯과 결합
```
loc Ready
Ready --plan?--> : [ammo > 0] ammo--, inflight++, assign[t]! (요격탄 비행 시작)
   (요격탄 비행: clock f, inv f <= FLYOUT)
   --[f >= FLYOUT]--> : (Pk>=θ) hit[t]! ; inflight--      // 성공
                      | (else)   miss[t]! ; inflight--     // 실패 -> 재교전
```

### 3.6 control_station_node (1 Hz)
```
clock c; Run --[c >= PERIOD_C]--> Run : policy! ; c := 0  // 방어정책 발행
```

### 3.7 world_state_node (2 Hz, COP)
```
Run --tracks?/scores?/matrix?/status?/event?--> Run : (통합 상황도 갱신)
Run --[c >= PERIOD_W]--> Run : world_state! ; c := 0      // latched 발행 -> 전 노드
Run --event(detected/intercept/impact)?--> Run : world_state!  // 이벤트 즉시 공유
```

## 4. 생명주기 오토마타 (검증 모델의 핵심)

### 4.1 Threat (적 탄도탄)
```
Inbound --[x>=ENTER]--> Engageable --assign[id]?--> Engaged --hit[id]?--> Killed
   │                        │                          │
   │                        │ [x>=IMPACT]              │ miss[id]?  -> Engageable (재교전)
   └──────────────[x>=IMPACT]┴──────────────────────────┴ [x>=IMPACT] -> Leaked
```
불변식: 모든 비종결 위치에서 `x <= IMPACT`.

### 4.2 Interceptor (아군 요격탄 슬롯, CAP개 병렬)
```
Idle --[ammo>0] assign[t]!--> Flying(f<=FLYOUT) --[f>=FLYOUT] hit[t]!|miss[t]!--> Idle
```
인스턴스 수가 `CAP`이므로 `inflight <= CAP`가 구조적으로 보장됨.

## 5. 검증 속성 (TCTL 쿼리)

`dwta_model.xml`에 포함. 의미:

| 쿼리 | 의미 |
|---|---|
| `A[] not deadlock` | 교착 없음 |
| `A[] ammo >= 0` | 잔여탄 음수 불가 (자원 안전) |
| `A[] inflight >= 0 && inflight <= CAP` | 동시 비행 요격탄 ≤ 동시교전 용량 |
| `A<> (T.Killed \|\| T.Leaked)` | 모든 위협은 결국 종결 (라이브니스) |
| `E<> killed == N` | 전량 요격 가능한 실행 존재 |
| `A[] (T.Engaged imply inflight >= 1)` | 교전중이면 비행 요격탄 존재 (일관성) |

추가로 명세할 수 있는 속성(설계 확장 시):
- 데드라인: `A[] (T.Engageable imply T.x <= IMPACT)` — 교전창 내 처리.
- 무낭비: `A[] not (두 요격탄이 동일 위협에 동시 비행)` (terminal/covered 제외 규칙의 정형화).
- 포화 한계: `E<> leaked >= 1` (자원 부족 시 누설 발생 가능 — 시나리오 설계 검증).

## 6. 워크플로 (spec-first)

1. 본 명세로 노드/채널/타이밍을 합의 → `dwta_model.xml`로 속성 검증.
2. 검증 통과한 구조를 `dwta_nodes/`에 구현 (현재 PoC가 이 명세를 따름).
3. 구현 변경 시 명세/모델을 함께 갱신하고 재검증 (graphify 그래프도 동기 갱신).

> 참고: XML 모델은 검증을 위해 작게 추상화(N=3, CAP=2, 정수 시간)했습니다. 실제
> 파이프라인의 연속 동역학(궤적/Pk)은 구현이 담당하고, 모델은 **타이밍·자원·생명주기
> 불변식**의 정형 보증에 집중합니다.
