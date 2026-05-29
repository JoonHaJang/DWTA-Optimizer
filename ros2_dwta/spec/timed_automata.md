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

## 4. 생명주기 오토마타 (강화 모델 `dwta_model.xml`)

전역 공유: `ammoU/ammoL`(계층 잔여탄), `inflU/inflL`(계층 비행중), `upCnt[t]/loCnt[t]`
(위협 t의 상/하층 동시 교전 수 — 충돌-자유 정형화), `engU[t]/engL[t]`(상/하층 교전대
진입), `killed/leaked`(누계). 채널: `plan`(주기 틱, broadcast), `hitU/missU/hitL/missL`
(broadcast — 종결 위협이어도 요격탄이 판정 가능).

### 4.1 Threat(id) — 적 탄도탄
```
Inbound --[x>=ENTER_U] engU:=T--> Live --hitU?|hitL?--> Killed (killed++)
   │                       │  ⤺ [x>=ENTER_L] engL:=T (하층 중첩대 진입)
   │                       │  ⤺ missU?|missL? (재교전)
   └────[x>=IMPACT]────────┴── [x>=IMPACT] --> Leaked (leaked++)
```
상층은 `ENTER_U`(원거리)부터, 하층은 `ENTER_L`(근거리)부터 교전대 → **중첩대에서
상·하층 동시 교전**. 불변식: 비종결 위치에서 `x ≤ IMPACT`.

### 4.2 InterceptorU / InterceptorL — 포대 계층별 유도채널 슬롯
인스턴스 수 = 그 계층 채널 수(`CH_U`/`CH_L`). 발사는 **계획주기(`plan?`)에만** 결심.
```
Idle --plan?--> Ready(committed) --[ammo>0 && eng[t] && cnt[t]==0] cnt[t]++,infl++,ammo-- --> Flying
Flying(f<=FLYOUT) --[f>=FLYOUT] hit[t]!|miss[t]! ; infl--, cnt[t]-- --> Idle
```
- `cnt[t]==0` 가드 = **동일 위협·동일 계층 중복 교전 금지**(다포대 충돌회피).
- 인스턴스 수 제한으로 `infl ≤ CH` 가 구조적 보장.

### 4.3 Planner — 계획수립 주기 클럭
```
Tick(cp<=PERIOD_P) --[cp>=PERIOD_P] plan! ; cp:=0--> Tick
```
발사 cadence를 주기에 묶어 타이밍 속성을 인과적으로 만든다.

## 4.2 두 모델 — SPEC vs IMPL

검증 모델은 두 개로 분리해 둡니다.

| 파일 | 정책 | 목적 |
|---|---|---|
| `dwta_model.xml` (**SPEC**) | 비결정 `select t`: 채널이 임의의 feasible 대상 선택 | **어떤 합리적 WTA 정책이든** 만족해야 하는 안전·타이밍·라이브니스를 검증 (강제 검증) |
| `dwta_model_impl.xml` (**IMPL**) | `select t` + 가드 `t == best_u()/best_l()` → ROS2 시뮬레이터의 `GreedyWTA`와 동일한 결정적 정책 | **실제 코드의 정책**이 같은 속성을 보존하는지, 그리고 정책 고유의 invariants(D3/D4: danger DESC 우선순위)를 검증 |

IMPL 모델의 declaration에는 `best_u()` / `best_l()` 함수가 정의되어 있고
(`dwta_nodes/wta_backend.py` `GreedyWTA.solve()` 의 핵심 루프 ―
*가장 danger 큰 위협부터 (위협, 계층)별 1개씩 배정*― 의 추상화), `Ready → Flying`
전이가 이 함수 반환값과 일치할 때만 발화하므로 정책 자체가 모델에 내장됩니다.

> 단순화: ID 작은 위협이 danger 큰 것으로 추상(시뮬레이터는 호출 전에 `sorted(scores,
> key=danger, reverse=True)`로 미리 정렬). danger 자체를 모델링하지 않고 우선순위
> 결과만 검증하는 데 충분합니다. Pk 비교는 안전성/충돌-자유 검증과 직교하므로
> 의도적으로 제외했습니다.

## 5. 검증 속성 & 쿼리 (TCTL)

두 모델 모두 4범주로 구성. SPEC=16개, IMPL=18개(D1~D4 정책-특화 4개 추가).

### 안전성 (Safety, `A[]`)
| ID | 쿼리 | 의미 |
|---|---|---|
| S1 | `A[] not deadlock` | 교착 없음 |
| S2 | `A[] (ammoU>=0 && ammoL>=0)` | 잔여탄 음수 불가 |
| S3/S4 | `A[] inflU<=CH_U` / `A[] inflL<=CH_L` | 비행 요격탄 ≤ 계층 채널 |
| S5/S6 | `A[] forall(t) upCnt[t]<=1` / `loCnt[t]<=1` | **충돌회피**: 위협당 계층별 ≤1 포대 |
| S7 | `A[] (killed+leaked<=MAXT)` | 종결 위협 ≤ 전체 (이중계수 없음) |
| S8 | `A[] forall(t) upCnt[t]+loCnt[t]<=2` | 위협당 동시 요격탄 ≤ 2 (상1+하1) |

### 타이밍/데드라인 (Timing, `A[]`)
| ID | 쿼리 | 의미 |
|---|---|---|
| T1 | `A[] P.cp<=PERIOD_P` | 계획수립 **주기 데드라인** 보장 |
| T2 | `A[] (T0.Live imply T0.x<=IMPACT)` | 활성 위협은 교전창(탄착시각) 이내 |

### 라이브니스 (Liveness)
| ID | 쿼리 | 의미 |
|---|---|---|
| L1 | `A<> (killed+leaked==MAXT)` | 모든 위협은 결국 종결 |
| L2 | `T0.Live --> (T0.Killed \|\| T0.Leaked)` | 교전대 진입 위협은 결국 종결 (응답성) |

### 도달성 (Reachability, `E<>`)
| ID | 쿼리 | 의미 |
|---|---|---|
| R1 | `E<> killed==MAXT` | 전량 격추(완전 방어) 가능 |
| R2 | `E<> (inflU>0 && inflL>0)` | 상·하층 동시 교전 도달 가능 |
| R3 | `E<> (upCnt[0]>0 && loCnt[0]>0)` | 동일 위협 다층요격 도달 가능 |
| R4 | `E<> leaked>0` | 자원부족/요격실패 누설 가능 (포화 한계) |

> 자원 설정 `ammoU=ammoL=2, MAXT=3` 은 R1(전량격추)과 R4(누설) 둘 다 도달 가능하게
> 하여, 모델이 완전방어와 포화실패를 모두 표현하는지 점검한다.

## 6. IMPL 모델 추가 쿼리 (정책-특화, D1~D4)

`dwta_model_impl.xml`은 S1~S8 / T1 / L1~L2 / R1~R4를 SPEC과 동일하게 검증하고,
추가로 GreedyWTA 정책 고유의 속성을 4개 더 검증한다.

| ID | 쿼리 | 의미 |
|---|---|---|
| D1 | `A[] (best_u() >= -1 && best_u() < MAXT)` | `best_u()`는 유효 id 또는 -1 (함수 totality) |
| D2 | `A[] (best_l() >= -1 && best_l() < MAXT)` | `best_l()` 동일 |
| D3 | `A[] forall(i,j) ((upCnt[i]>0 && upCnt[j]==0 && engU[j]) imply i <= j)` | **danger DESC** 우선순위: 더 위협적인(작은 id) 위협이 커버될 수 있다면 덜 위협적인 위협에 먼저 발사하지 않는다 |
| D4 | `A[] forall(i,j) ((loCnt[i]>0 && loCnt[j]==0 && engL[j]) imply i <= j)` | 하층도 동일 |

> S1~S8 / T1 / L1~L2 / R1~R4 는 SPEC·IMPL 양쪽 모두 동일하게 검증한다.
> 동일 속성이 두 모델 모두에서 성립하면 **명세는 강하고 구현은 정합한 것**.

### ROS2 시뮬레이터 ↔ IMPL 모델 정합

| ROS2 구현 (`dwta_nodes/`) | IMPL 모델 |
|---|---|
| `wta_backend.GreedyWTA.solve`: `for s in sorted(scores, key=danger, reverse=True)` | `best_u()/best_l()`: 가장 작은 id 우선 (danger DESC 추상) |
| 가드 `if cell.system_id not in covered_layer[t]` (충돌회피) | 가드 `upCnt[t] == 0 / loCnt[t] == 0` |
| `LauncherNode._on_plan`: `if ammo>0 and channels left` | 가드 `ammoU>0 && best_u()>=0` + 인스턴스 수 `CH_U` |
| `Planner._tick(2Hz)` → `/engagement_plan` | `Planner` 템플릿 `plan!` (주기 클럭 `cp<=PERIOD_P`) |
| `FCR.resolve` Pk≥θ → hit/miss | broadcast `hitU/L!` / `missU/L!` (비결정 분기로 양쪽 trace 모두 검증) |
| `WorldState`의 `(threat,layer)`별 커버 집합 | 전역 `upCnt/loCnt[MAXT]` |

## 7. UPPAAL로 검증하는 법

설치(Windows): UPPAAL 5 GUI는 Java 17+ 필요(verifyta CLI는 불필요).
라이선스는 학술용 무료(<https://uppaal.veriaal.dk/academic.html>) 또는
키 없이 동작하는 **UPPAAL 4.1.26-2** 사용(<https://uppaal.org/downloads/other/>).

```powershell
# CLI 일괄 검증
verifyta.exe -q ros2_dwta\spec\dwta_model.xml       # SPEC 모델
verifyta.exe -q ros2_dwta\spec\dwta_model_impl.xml  # IMPL 모델 (GreedyWTA)

# 반례 trace 생성 (실패한 쿼리 분석용)
verifyta.exe -t 1 -q ros2_dwta\spec\dwta_model_impl.xml
```

GUI 사용: 파일 열기 -> Verifier 탭 -> 각 쿼리 Check. 한글 주석은 UPPAAL 5 Windows
빌드에서 깨지므로 **본 XML들은 모두 ASCII**로 작성되어 있다.

구현(`dwta_nodes/`) 변경 시 두 모델/쿼리를 함께 갱신·재검증한다(graphify 그래프도 동기).

## 8. 워크플로 (spec-first)

1. 본 명세로 노드/채널/타이밍을 합의 → `dwta_model.xml`로 속성 검증.
2. 검증 통과한 구조를 `dwta_nodes/`에 구현 (현재 PoC가 이 명세를 따름).
3. 구현 변경 시 명세/모델을 함께 갱신하고 재검증 (graphify 그래프도 동기 갱신).

> 참고: XML 모델은 검증을 위해 작게 추상화(N=3, CH_U=CH_L=2, 정수 시간)했습니다. 실제
> 파이프라인의 연속 동역학(궤적/Pk)은 구현이 담당하고, 모델은 **타이밍·자원·생명주기
> 불변식**의 정형 보증에 집중합니다.
