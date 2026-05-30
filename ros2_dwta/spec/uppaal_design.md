# UPPAAL 모델 설계 · 구현 · 사용 — 완전 문서 (v6)

이 문서는 현 시점의 **메인 모델 [`dwta_model_v6_full.xml`](./dwta_model_v6_full.xml)** 을
기준으로, UPPAAL/Timed Automata 기초부터 v6의 모든 템플릿·노드·검증 쿼리·자동 dump
워크플로까지 한 장에 정리합니다. 검증 속성 카탈로그는
[`timed_automata.md`](./timed_automata.md) 참조.

> **메인 모델: `dwta_model_v6_full.xml`** — 임무절차 다이어그램의 모든 축을 단일
> 모델로 통합:
> - **프로세스 정합**: Planner가 WTA 의사결정 주체 (ROS2 `planning_node._tick →
>   GreedyWTA.solve() → Assignment 리스트` 와 1:1)
> - **다층 방어**: 상층 L-SAM + 하층 M-SAM, 같은 위협 동시 cover 가능
> - **포대별 동시교전 제한**: `CH_PER_U[b]` / `CH_PER_L[b]`
> - **사거리 + 고도 윈도우**: 사전 계산해 `U_ENTER/U_EXIT/L_ENTER/L_EXIT` 주입
> - **발당 Pk**: `PK_U[t][b]` / `PK_L[t][b]` (SMC에서 확률 가중치로 작동)
> - **Salvo (연속 사격)**: `MAX_SALVO_U` / `MAX_SALVO_L`로 동시 다발 표현
> - **비행시간 jitter**: `FLYOUT_*_MIN ~ MAX` 윈도우
> - **시나리오 자동 주입**: `scenario.inject_uppaal_constants()` 한 줄로 XML 갱신

---

## 0. 한 장 인덱스

| § | 내용 |
|---|---|
| 1 | UPPAAL과 Timed Automata 기초 (도구·이론·XML·TCTL·한계) |
| 2 | v6 모델 전체 구성 (템플릿/인스턴스/채널) |
| 3 | Declaration 상세 (구조 + 자동 주입 영역 분리) |
| 4 | 템플릿별 구현 (Radar / Threat / Slot_U / Slot_L / Planner) |
| 5 | 채널 사양 (handshake + broadcast) |
| 6 | 한 위협의 lifecycle (시간순) |
| 7 | 검증 쿼리 25개 (Safety/Geometry/Timing/Liveness/Reachability/Salvo/SMC) |
| 8 | MSC 읽는 법 + 흔히 헷갈리는 동작 |
| 9 | ROS2 시뮬레이터 ↔ UPPAAL 매핑 |
| 10 | PoC 활용 (GUI / verifyta / SMC) |
| 11 | `clean_slate_optimizer.py`와의 관계 |
| 12 | 시나리오 → 모델 **자동 주입 워크플로** (한 명령) |
| 13 | UPPAAL SMC (Pk · Salvo의 통계적 의미) |
| 14 | 모델 한계 + state space 상한 |
| 15 | Process Array (free parameter로 자동 인스턴스화) |
| 16 | Location 다이얼로그 옵션 (Exponential rate, Test Code, Comments) |
| 부록 A | v6 XML 파일 구조 |
| 부록 B | 디버깅 체크리스트 |

---

## 1. UPPAAL과 Timed Automata 기초

### 1.1 UPPAAL이 무엇인가

**UPPAAL** = Aalborg(덴마크) + Uppsala(스웨덴) 1995년 이후 개발 중인 **실시간 시스템
모델 체커**. 통합 GUI:

| 역할 | 도구 | 무엇을 |
|---|---|---|
| **에디터** | Editor 탭 | 시스템(템플릿 네트워크)을 그래프 + 코드로 명세 |
| **시뮬레이터** | Symbolic / Concrete Simulator 탭 | 한 step씩 실행, MSC + 변수 패널 |
| **검증기** | Verifier 탭 | TCTL/SMC 쿼리로 정형 + 통계 검증 |

CLI `verifyta.exe`로도 동작. UPPAAL 5는 SMC 통합.

### 1.2 Timed Automaton — 이론

TA = 유한 오토마타 + 실수값 클럭 (Alur & Dill 1994). UPPAAL 모델 = TA의 네트워크.

| 요소 | 정의 | XML |
|---|---|---|
| **Location** | 자동기 상태 노드 | `<location>` |
| **Edge / Transition** | location 간 화살표 | `<transition>` |
| **Clock** | 실수값, 모든 클럭 동일 속도 증가 | `clock x;` |
| **Guard** | edge fire 조건 | `<label kind="guard">x>=5</label>` |
| **Invariant** | location 머무는 조건. 위반 시 강제 이동 | `<label kind="invariant">x<=10</label>` |
| **Assignment** | edge fire 시 실행 | `<label kind="assignment">x=0</label>` |
| **Probability** | SMC branching 가중치 | `<label kind="probability">85</label>` |

**시간 진행 두 방식**:
1. **Delay**: 어떤 edge도 fire 안 하면 모든 클럭 동시 증가. invariant가 한계.
2. **Action**: edge fire 시 시간 진행 없이 즉시 다음 location.

**특수 location**:
- **Urgent** (`<urgent/>`): 시간 진행 금지, 즉시 fire
- **Committed** (`<committed/>`): urgent + 다른 자동기보다 우선 처리

v6에서 Planner의 `Decide`가 committed — 모든 포대 결심을 0-시간 안에 연쇄 처리.

**채널과 동기화**:
| 종류 | semantics | 선언 |
|---|---|---|
| **Handshake** | 정확히 1 sender + 1 receiver 매칭 | `chan a;` |
| **Broadcast** | 1 sender + receiver 0명 이상 | `broadcast chan a;` |

v6 = **handshake `assign_u/l`** (Planner→Slot 정확 매칭) + **broadcast 나머지**.

### 1.3 XML 명세 형식

```xml
<nta>
  <declaration> ... </declaration>       <!-- 글로벌 -->
  <template>
    <name>X</name>
    <parameter>const int id</parameter>
    <declaration> clock t; </declaration> <!-- 템플릿 로컬 -->
    <location id="l0"><name>S</name></location>
    <init ref="l0"/>
    <transition><source/><target/>...</transition>
  </template>
  <system> A = X(0); system A; </system>
  <queries><query><formula>...</formula></query></queries>
</nta>
```

**Declaration 4 곳** (GUI 좌측 트리):
1. 글로벌 (모든 인스턴스 공유)
2. 템플릿 로컬 (인스턴스마다 사본)
3. System (인스턴스화)
4. Queries (검증식)

**Label `kind`**: `invariant / guard / synchronisation / assignment / select / probability / comments`

### 1.4 TCTL + SMC 쿼리 기초

| 쿼리 | 의미 |
|---|---|
| `A[] φ` | 모든 실행의 모든 상태에서 φ (Safety) |
| `A<> φ` | 모든 실행에서 언젠가 φ (Liveness) |
| `E<> φ` | 어떤 실행에서 언젠가 φ (Reachability) |
| `φ --> ψ` | φ면 결국 ψ (응답성) |
| `Pr[<=T] (<> φ)` | T 안에 φ 도달 확률 (SMC) |
| `E[<=T; N] (max: x)` | N회 시뮬 평균 최댓값 (SMC) |
| `simulate N [<=T] {x,y}` | N개 trace plot (SMC) |

수량자 `forall (b : int[0,N-1]) ...`, `exists (...) ...` 가능.

### 1.5 UPPAAL이 못 다루는 것

- **연속 동역학**: sin/cos/sqrt → 외부에서 사전 계산
- **부동소수**: int/bool/clock만 (실수는 클럭에서만)
- **무한 데이터**: 모든 배열·범위는 컴파일타임 고정
- **확률**: 기본 TCTL은 비결정만 → **통합 SMC**로 해소
- **MIP/LP 해**: 정수 해 자체는 표현 불가, 정책 규칙만 추상화

---

## 2. v6 모델 전체 구성

```
┌──── 시간 권위 ────┐   ┌────── 의사결정 ──────┐   ┌────── 실행 ──────┐
│ Radar(0..MAXT-1)  │   │      Planner          │   │  Slot_U × sum(CH) │
│  detect/enter*/   │   │   Tick → Decide        │   │  Slot_L × sum(CH) │
│  exit*/impact!    │   │   (committed,          │   │  Idle ── assign?  │
│  (broadcast)      │   │    Salvo loop)         │   │      → Flying     │
│                   │   │  ammoU/L_b, infl,      │   │  → hit/miss!      │
│                   │   │  upCnt_bt 갱신         │   │   (Pk weight)     │
└─────────┬─────────┘   └──────────┬─────────────┘   └────────┬──────────┘
          │ broadcast                │ handshake                │ broadcast (Pk weight)
          ▼                          ▼ assign_u[b][t]!           ▼
       Threat(0..MAXT-1)             Slot_U(b) / Slot_L(b)      Threat(t)
       Inbound → Tracked             Idle → Flying              hit/miss/impact?
       ↑ engU_b/engL_b 토글           Flying → Idle              Killed / Leaked
       ↓ hit/miss/impact?             (FLYOUT_MIN..MAX jitter)
       Killed / Leaked
```

### 5개 템플릿 요약

| Template | parameter | local | 인스턴스 수 |
|---|---|---|---|
| `Radar` | `const int id` | `clock t` | MAXT (3) |
| `Threat` | `const int id` | — | MAXT (3) |
| `Slot_U` | `const int batt_id` | `clock f; int tgt` | sum(CH_PER_U) (5) |
| `Slot_L` | `const int batt_id` | `clock f; int tgt` | sum(CH_PER_L) (5) |
| `Planner` | — | `clock cp; int ds, ss` | 1 |

**총 15 인스턴스** (MSC lifeline 15개).

### System declarations

```c
R0 = Radar(0); R1 = Radar(1); R2 = Radar(2);
T0 = Threat(0); T1 = Threat(1); T2 = Threat(2);
// Upper: CH_PER_U = {3, 2}
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0); SU0_2 = Slot_U(0);
SU1_0 = Slot_U(1); SU1_1 = Slot_U(1);
// Lower: CH_PER_L = {3, 2}
SL0_0 = Slot_L(0); SL0_1 = Slot_L(0); SL0_2 = Slot_L(0);
SL1_0 = Slot_L(1); SL1_1 = Slot_L(1);
P = Planner();
system R0..R2, T0..T2, SU*, SL*, P;
```

---

## 3. Declaration 상세

v6의 글로벌 declaration은 **구조 영역 (수동)** 과 **시나리오 영역 (자동 주입)** 으로
명확히 분리됩니다.

### 3.1 구조 영역 (수동 — 시나리오 변경 시 그대로)
```c
const int MAXT             = 3;            // 위협 수
const int NB_U             = 2;            // 상층 포대 수
const int NB_L             = 2;            // 하층 포대 수
const int CH_PER_U[NB_U]   = {3, 2};       // 포대별 채널 수 (상층)
const int CH_PER_L[NB_L]   = {3, 2};
const int FLYOUT_U_MIN     = 4;            // 상층 비행시간 윈도우
const int FLYOUT_U_MAX     = 6;
const int FLYOUT_L_MIN     = 1;
const int FLYOUT_L_MAX     = 3;
const int PERIOD_P         = 2;            // 계획주기
const int MAX_SALVO_U      = 2;            // 상층 Salvo 한계
const int MAX_SALVO_L      = 1;
```

### 3.2 시나리오 영역 (AUTO-GENERATED — 한 명령으로 주입)

XML에 다음 마커가 있고, `inject_uppaal_constants()` 헬퍼가 그 사이를 갱신:
```c
// ===== BEGIN AUTO-GENERATED SCENARIO CONSTS =====
// (auto-generated from random_saturation_scenario seed=42, n_threats=3)
const int APPEAR[MAXT]        = { 3,  5,  9};
const int IMPACT_AT[MAXT]     = {40, 42, 48};
const int U_ENTER[MAXT][NB_U] = { {8, 8}, {14,16}, {14,19} };
const int U_EXIT [MAXT][NB_U] = { {34,34}, {35,35}, {41,41} };
const int L_ENTER[MAXT][NB_L] = { {34,34}, {35,35}, {41,41} };
const int L_EXIT [MAXT][NB_L] = { {38,38}, {40,40}, {46,46} };
const int PK_U[MAXT][NB_U]    = { {86,86}, {86,86}, {86,86} };
const int PK_L[MAXT][NB_L]    = { {90,90}, {90,90}, {90,90} };
// ===== END AUTO-GENERATED SCENARIO CONSTS =====
```

| 변수 | 의미 |
|---|---|
| `APPEAR[t]` | 위협 t가 surveillance volume에 등장하는 시각 |
| `IMPACT_AT[t]` | 위협 t가 탄착하는 시각 (요격 데드라인) |
| `U_ENTER[t][b] ~ U_EXIT[t][b]` | 위협 t가 상층 포대 b의 **(사거리 ∧ 고도)** 윈도우 안인 시간 구간 |
| `L_ENTER/L_EXIT` | 하층 동일 |
| `PK_U[t][b]` | 상층 포대 b가 위협 t를 명중시킬 확률 × 100 (정수) |
| `PK_L[t][b]` | 하층 동일 |

오직 **Radar 템플릿**과 **Slot_U/L hit/miss 가중치**가 이 const를 직접 참조.

### 3.3 공유 상태
```c
int  ammoU_b[NB_U] = {4, 3};            // 포대 b 잔여탄
int  ammoL_b[NB_L] = {4, 3};
int  inflU_b[NB_U];                     // 포대 b 비행중
int  inflL_b[NB_L];
int  upCnt_bt[NB_U][MAXT];              // (포대, 위협) 동시 교전 카운터 (≤ MAX_SALVO_U)
int  loCnt_bt[NB_L][MAXT];
bool engU_b[MAXT][NB_U];                // 위협 t가 포대 b 윈도우 안?
bool engL_b[MAXT][NB_L];
int  killed = 0, leaked = 0;
int  shots_u_fired = 0, shots_l_fired = 0;
```

| 변수 | 쓰기 | 읽기 |
|---|---|---|
| `ammoU_b[b]` | **Planner** 발사 시 `--` | Planner 가드, S2u 쿼리 |
| `inflU_b[b]` | **Planner** 발사 시 `++`, Slot 판정 시 `--` | Planner 가드, S3 쿼리 |
| `upCnt_bt[b][t]` | **Planner** 발사 시 `++`, Slot 판정 시 `--` | `best_u_b_salvo`, S5 쿼리 |
| `engU_b[t][b]` | Threat의 enter*/exit* 토글, 종결 시 false | Planner 가드, RD1 쿼리 |
| `killed` | Threat hit 시 `++` | L1/R1 |
| `shots_*_fired` | Planner 발사 시 `++` | E3, SMC3 |

⭐ v6: **자원 갱신은 Planner가 발사 결심 시점에**. Slot은 판정 시 `--`만.

### 3.4 채널
```c
chan assign_u[NB_U][MAXT];                  // handshake: Planner → Slot_U
chan assign_l[NB_L][MAXT];                  // handshake: Planner → Slot_L
broadcast chan detect[MAXT], impact[MAXT];
broadcast chan enterU0/U1/L0/L1[MAXT];      // Radar → Threat
broadcast chan exitU0/U1/L0/L1[MAXT];
broadcast chan hitU/missU[MAXT];            // Slot_U → Threat (Pk weight!)
broadcast chan hitL/missL[MAXT];
```

### 3.5 함수
```c
int best_u_b_salvo(int b) {                 // 우선순위 + Salvo 가드
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] < MAX_SALVO_U) return i;
        i++;
    }
    return -1;
}
int best_l_b_salvo(int b) { /* loCnt < MAX_SALVO_L */ }

bool any_uCover(int t) { return upCnt_bt[0][t] + upCnt_bt[1][t] > 0; }
bool any_lCover(int t) { return loCnt_bt[0][t] + loCnt_bt[1][t] > 0; }
```

`best_*_salvo`의 `< MAX_SALVO_U` 가드 한 글자가 **Salvo의 모든 것** (`== 0` 이면 단발).

---

## 4. 템플릿별 구현 상세

### 4.1 Radar(const int id) — 위협 timing 권위자

**왜?** 위협 한 대를 처음부터 끝까지 책임. 등장·윈도우 enter/exit·탄착 모두 broadcast.

**Locations** (3): `Pre` (대기) / `Scan` (활성) / `Done` (sink)

**Transitions** (10): Pre→Scan 1개 (detect), Scan self-loop 8개 (포대별 enter/exit),
Scan→Done 1개 (impact).

| 핵심 패턴 | guard | sync |
|---|---|---|
| 시각 X에 정확히 fire | `t == X` + invariant `t <= X` | `enterU0[id]!` 등 |

### 4.2 Threat(const int id) — signal-driven 적 탄도탄

**왜?** 자기 시간 모름. broadcast 신호로만 진행. hit 한 발에 종결 (Salvo로 두 발이
와도 한 발이면 끝).

**Locations** (4): `Inbound` (초기) / `Tracked` (활성) / `Killed` (sink) / `Leaked` (sink)

**Transitions** (15):
- detect → Tracked (1)
- enter*/exit* 8 self-loop on Tracked (engU_b/engL_b 토글)
- miss self-loop 2 (재교전 대기)
- hit → Killed 2 (engU/engL 모두 false, killed++)
- impact → Leaked 2

### 4.3 Slot_U(const int batt_id) — 상층 채널 (Pk + jitter)

**왜?** Planner의 명령(`assign_u[batt_id][t]?`)만 받는 reactive executor. 자기 결정
없음. 비행 후 Pk 기반으로 hit/miss.

**Locations** (2): `Idle` / `Flying` (invariant `f <= FLYOUT_U_MAX`)

**Transitions** (3):

| from → to | guard / select / sync | probability | assignment |
|---|---|---|---|
| Idle → Flying | select `t:int[0,MAXT-1]`, sync `assign_u[batt_id][t]?` | — | `tgt=t, f=0` |
| Flying → Idle (hit) | guard `f >= FLYOUT_U_MIN`, sync `hitU[tgt]!` | **`PK_U[tgt][batt_id]`** | `inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--` |
| Flying → Idle (miss) | 동일 + `missU[tgt]!` | **`100 - PK_U[tgt][batt_id]`** | (같음) |

**핵심 4**:
1. ⭐ Pk weight: SMC 모드에서 Bernoulli 분기 (예: 85% hit / 15% miss). 기본 TCTL에선
   비결정 분기로 두 trace 모두 탐색
2. ⭐ jitter: `[FLYOUT_U_MIN, FLYOUT_U_MAX]` 사이 비결정 시각 fire
3. 자원 갱신 (ammo/infl/upCnt `++`)은 Planner가 함. Slot은 판정 시 `--`만.
4. committed Ready 없음, skip transition 없음, best 호출 없음.

### 4.4 Slot_L(const int batt_id) — 하층 채널

Slot_U와 구조 100% 동일. L 계열 변수 (`ammoL_b/inflL_b/loCnt_bt/FLYOUT_L_*/hitL/missL/assign_l/PK_L`).

### 4.5 Planner — WTA 의사결정 주체 + Salvo loop (v6 핵심)

**왜?** ROS2 PlanningNode와 1:1. 매 PERIOD_P마다 모든 포대를 순회하며 결심.
Salvo 활성화 시 한 포대당 MAX_SALVO발까지 같은 위협에 발사 가능.

**Local**: `clock cp; int ds = 0; int ss = 0;`
- `ds`: 포대 인덱스 (0 ~ NB_U + NB_L - 1)
- `ss`: 현재 포대에서의 Salvo 카운터 (0 ~ MAX_SALVO_* - 1)

**Locations** (2): `Tick` (invariant `cp <= PERIOD_P`) / `Decide` (committed)

**Transitions** (6):

#### Edge 1 — Tick → Decide (주기 도래)
- guard `cp >= PERIOD_P`
- assign `ds = 0, ss = 0`

#### Edge 2 — Decide → Decide (상층 발사, Salvo 한 step)
- select `t : int[0,MAXT-1]`
- guard:
  ```
  ds < NB_U
  && ss < MAX_SALVO_U
  && ammoU_b[ds] > 0
  && inflU_b[ds] < CH_PER_U[ds]
  && best_u_b_salvo(ds) >= 0
  && t == best_u_b_salvo(ds)
  ```
- sync `assign_u[ds][t]!`
- assign `ammoU_b[ds]--, inflU_b[ds]++, upCnt_bt[ds][t]++, shots_u_fired++, ss++`
- ⭐ `ds` 유지, `ss`만 증가 → 같은 포대에서 Salvo 추가 발사 가능

#### Edge 3 — Decide → Decide (상층 다음 포대로)
- guard: `ds < NB_U && (ss >= MAX_SALVO_U || ammoU_b[ds]==0 || inflU_b[ds] >= CH_PER_U[ds] || best_u_b_salvo(ds) < 0)`
- assign `ds++, ss = 0`

#### Edge 4 — Decide → Decide (하층 발사, Salvo 한 step)
- Edge 2의 하층 버전 (`ds >= NB_U && ds < NB_U+NB_L`, `ss < MAX_SALVO_L`, `assign_l[ds-NB_U][t]!`)

#### Edge 5 — Decide → Decide (하층 다음 포대로)
- Edge 3 하층 버전

#### Edge 6 — Decide → Tick (cycle 종료)
- guard `ds == NB_U + NB_L`
- assign `cp = 0`

#### 한 cycle 흐름 (예시, MAX_SALVO_U=2)
```
t=2  P.Tick (cp=2) ─[Edge 1, ds=0, ss=0]─► P.Decide
       ds=0, ss=0: best_u_b_salvo(0)=0, ammo OK, channel OK
         Edge 2: assign_u[0][0]! → SU0_x 매칭
         ammoU_b[0]=3, inflU_b[0]=1, upCnt_bt[0][0]=1, ss=1, ds=0
       ds=0, ss=1: best_u_b_salvo(0)=0 (upCnt_bt[0][0]=1 < MAX_SALVO_U=2)
         Edge 2: assign_u[0][0]! → SU0_y 매칭 (같은 위협에 두 번째 발사 — Salvo!)
         ammoU_b[0]=2, inflU_b[0]=2, upCnt_bt[0][0]=2, ss=2, ds=0
       ds=0, ss=2: ss >= MAX_SALVO_U
         Edge 3 skip: ds=1, ss=0
       ds=1, ss=0: best_u_b_salvo(1)=0이지만 ... (다른 포대 다른 위협)
       ... 모든 포대 처리 ...
       ds=4 (=NB_U+NB_L): Edge 6, cp=0
     P.Decide → P.Tick (0 시간 안에 모두 처리)
```

⭐ 위 예시에서 **같은 포대(상층 0)가 같은 위협(0)에 동시에 두 발 발사** = **Salvo**.

---

## 5. 채널 사양

| 채널 | 종류 | sender → receivers | 의미 |
|---|---|---|---|
| `assign_u[b][t]` | **handshake** | Planner → Slot_U(b) 중 Idle 한 명 | 상층 포대 b가 위협 t 노리라는 명령 |
| `assign_l[b][t]` | **handshake** | Planner → Slot_L(b) 중 Idle 한 명 | 하층 동일 |
| `detect[i]` | broadcast | Radar(i) → Threat(i) | 탐지 |
| `enter*/exit*[i]` | broadcast | Radar(i) → Threat(i) | 윈도우 진입/이탈 |
| `impact[i]` | broadcast | Radar(i) → Threat(i) | 탄착 |
| `hitU[t]` / `missU[t]` | broadcast (**Pk weight**) | Slot_U → Threat(t) | 상층 명중/실패 |
| `hitL[t]` / `missL[t]` | broadcast (**Pk weight**) | Slot_L → Threat(t) | 하층 동일 |

**왜 assign은 handshake?** broadcast면 자유 채널 없을 때도 fire → "발사 명령은
자유 채널 있을 때만"이 깨짐. handshake가 자연 강제.

**왜 hit/miss는 broadcast?** Threat이 이미 Killed면 수신 안 해도 Slot은 자원 정리
`--`를 위해 fire 가능해야 함.

---

## 6. 한 위협의 lifecycle (시간순)

위협 0이 t=0에 등장 → Salvo 두 발 발사 → 첫 hit으로 종결.

```
t=0   R0.Pre[t=0], T0.Inbound, Slots.Idle, P.Tick[cp=0]
      ─── R0.t reaches APPEAR[0]=0 ───
      R0 fires detect[0]! ──► T0: Inbound → Tracked, R0: Pre → Scan

t=2   P.cp == 2 → P.Tick → P.Decide (ds=0, ss=0)
      ds=0, ss=0: best_u_b_salvo(0)=-1 (engU_b[0][0]=false 아직)
        Edge 3 skip: ds=1, ss=0
      ds=1: 동일 skip → ds=2
      ds=2,3: 하층 동일 skip → ds=4
      Edge 6: cp=0, P.Decide → P.Tick

t=4,6,8 동일 (모두 skip)

t=8   R0.t == U_ENTER[0][0]=8 → R0 fires enterU0[0]!
      ──► T0: engU_b[0][0]=true (self-loop)
t=9   R0 fires enterU1[0]! ──► T0: engU_b[0][1]=true

t=10  P.cp == 2 → P.Tick → P.Decide (ds=0, ss=0)
      ds=0, ss=0: best_u_b_salvo(0)=0, assign_u[0][0]!
        SU0_0 (Idle): Idle → Flying[f=0], tgt=0
        Planner: ammoU_b[0]=3, inflU_b[0]=1, upCnt_bt[0][0]=1, ss=1, ds=0
      ds=0, ss=1: best_u_b_salvo(0)=0 (upCnt < MAX_SALVO_U=2)
        Edge 2: assign_u[0][0]! → SU0_1 매칭 (Salvo!)
        Planner: ammoU_b[0]=2, inflU_b[0]=2, upCnt_bt[0][0]=2, ss=2, ds=0
      ds=0, ss=2: ss >= MAX_SALVO_U
        Edge 3 skip: ds=1, ss=0
      ds=1, ss=0: best_u_b_salvo(1)=0
        Edge 2: assign_u[1][0]! → SU1_0 매칭
        Planner: ammoU_b[1]=2, inflU_b[1]=1, upCnt_bt[1][0]=1, ss=1, ds=1
      ds=1, ss=1: best_u_b_salvo(1)=-1 (upCnt < MAX_SALVO_U이지만 다른 위협 없음)
        Edge 3 skip: ds=2, ss=0
      ds=2,3: 하층 skip → ds=4
      Edge 6: cp=0

t=14  ─── SU0_0.f reaches FLYOUT_U_MIN=4 ─── (jitter)
      SU0_0 fires hitU[0]! (SMC 확률 85%) 또는 missU[0]! (15%)
      hit인 경우:
        T0: Tracked → Killed, engU/engL 모두 false, killed=1
        SU0_0: inflU_b[0]=1, upCnt_bt[0][0]=1, Flying → Idle

t=15  SU0_1.f가 5 도달 → hitU[0]! 또는 missU[0]!
      T0는 이미 Killed라 수신 안 함 (broadcast, OK)
      SU0_1: inflU_b[0]=0, upCnt_bt[0][0]=0, Flying → Idle

t=16  SU1_0.f가 jitter 시각 도달 → hitU[0]! 또는 missU[0]!
      T0 이미 Killed (sink), 무시
      SU1_0: inflU_b[1]=0, upCnt_bt[1][0]=0, Flying → Idle

t=40  R0.t == IMPACT_AT[0]=40 → R0 fires impact[0]!
      T0 이미 Killed라 수신 안 함, R0: Scan → Done
```

**핵심 6**:
1. Threat은 시간 모름. Radar broadcast가 모든 상태 변화 트리거.
2. Planner는 매 주기 Decide cycle 0-시간 처리 (committed).
3. ⭐ 같은 포대가 같은 위협에 **MAX_SALVO_U발까지** 동시 발사 (Salvo).
4. 다른 포대는 같은 위협 노릴 수 있음 (포대별 cnt 별개, 다층 또는 다포대).
5. broadcast hit/miss는 receiver 0 OK.
6. hit이 결정되는 시각은 `[FLYOUT_U_MIN, FLYOUT_U_MAX]` 사이 비결정 (jitter).

---

## 7. 검증 쿼리 25개 상세

### 7.1 Safety (A[], 8개)

| ID | 쿼리 | 의미 |
|---|---|---|
| S1 | `A[] not deadlock` | 교착 없음 |
| S2u | `A[] forall (b) ammoU_b[b] >= 0` | 상층 잔여탄 음수 불가 |
| S2l | `A[] forall (b) ammoL_b[b] >= 0` | 하층 동일 |
| S3 | `A[] forall (b) inflU_b[b] <= CH_PER_U[b]` | 상층 비행중 ≤ 채널 |
| S4 | `A[] forall (b) inflL_b[b] <= CH_PER_L[b]` | 하층 동일 |
| **S5** | `A[] forall (b)(t) upCnt_bt[b][t] <= MAX_SALVO_U` | **Salvo 한계 (상층)** |
| **S6** | `A[] forall (b)(t) loCnt_bt[b][t] <= MAX_SALVO_L` | **Salvo 한계 (하층)** |
| S7 | `A[] killed + leaked <= MAXT` | 종결 이중계수 없음 |

### 7.2 Geometry (A[], 2개)

| ID | 쿼리 | 의미 |
|---|---|---|
| RD1 | `A[] forall (b)(t) upCnt_bt[b][t] > 0 imply engU_b[t][b]` | **사거리·고도 밖 발사 0건** |
| RD2 | `A[] forall (b)(t) loCnt_bt[b][t] > 0 imply engL_b[t][b]` | 하층 동일 |

### 7.3 Timing (A[], 1개)

| T1 | `A[] P.cp <= PERIOD_P` | Planner 주기 데드라인 |
|---|---|---|

### 7.4 Liveness (1개)

| L1 | `A<> killed + leaked == MAXT` | 모든 위협 결국 종결 |
|---|---|---|

### 7.5 Reachability (E<>, 5개)

| ID | 쿼리 | 의미 |
|---|---|---|
| R1 | `E<> killed == MAXT` | 전량 격추 도달 |
| R2 | `E<> (inflU_b[0]>0 && inflU_b[1]>0)` | 상층 두 포대 동시 가동 |
| R3 | `E<> (inflL_b[0]>0 && inflL_b[1]>0)` | 하층 두 포대 동시 가동 |
| R4 | `E<> (any_uCover(0) && any_lCover(0))` | **다층 요격** (상+하 동시 cover) |
| R5 | `E<> leaked > 0` | 누설 도달 (포화 한계) |

### 7.6 Salvo 전용 (1개)

| SV1 | `E<> exists (b)(t) upCnt_bt[b][t] == MAX_SALVO_U` | **실제 Salvo full 발사** 도달 |
|---|---|---|

### 7.7 v6 explicit-assign sanity (3개)

| ID | 쿼리 | 의미 |
|---|---|---|
| E1 | `A[] (P.Tick or P.Decide)` | Planner 위치 sanity |
| E2 | `A[] (P.Decide imply 0 <= P.ds <= NB_U+NB_L)` | decision step 유효 범위 |
| E3 | `E<> (shots_u_fired>0 && shots_l_fired>0)` | 양 계층 실제 명령 받음 |

### 7.8 SMC 통계 (4개)

| ID | 쿼리 | 의미 |
|---|---|---|
| **SMC1** | `Pr[<=40] (<> killed == MAXT)` | **40초 안에 전량 격추할 확률** (Pk 반영) |
| **SMC2** | `E[<=40; 200] (max: killed)` | 200회 시뮬 후 평균 격추 수 |
| **SMC3** | `E[<=40; 200] (max: shots_u_fired + shots_l_fired)` | 평균 총 발사 미사일 수 (소비 분석) |
| **SMC4** | `simulate 50 [<=40] {killed, leaked, inflU_b[0], inflL_b[0]}` | 50 trace plot |

---

## 8. MSC 읽는 법 + 흔히 헷갈리는 동작

| 기호 | 의미 |
|---|---|
| 세로 막대 (lifeline) | 인스턴스 1개. 위→아래 = 시간 진행 |
| 박스 | 현재 location |
| 가로 빨간 화살표 | 채널 발사 + 수신. 양쪽 동시 전이 |
| 옅은 회색 박스 (Decide) | committed. 시간 진행 0 |
| 박스 사이 빈 공간 | 시간 진행 |

### 흔히 헷갈리는 동작 3가지

#### (1) "Decide 박스가 한 cycle에 여러 번 그려지는데?"
committed에서 NB_U + NB_L번(또는 Salvo 시 더) self-loop fire → Decide 박스가 연속
표시. 모두 같은 절대 시각 (시간 진행 0).

#### (2) "같은 포대의 두 슬롯이 동시에 Flying이네?"
Salvo가 활성화된 경우 정상. `best_u_b_salvo`의 `upCnt < MAX_SALVO_U` 가드가 같은
위협에 두 번째 발사 허용.

#### (3) "hit과 miss가 둘 다 trace에 보이는데?"
기본 TCTL에선 두 분기 모두 탐색 (Pk weight 무시). SMC 쿼리에서만 가중치로 확률
샘플링 → `Pr[...]`, `E[...]`, `simulate` 결과는 양적.

---

## 9. ROS2 시뮬레이터 ↔ UPPAAL v6 매핑

| ROS2 (`dwta_nodes/`) | UPPAAL v6 |
|---|---|
| `surveillance_radar_node` /events: DETECTED | `Radar(id) detect[id]!` |
| `engageability_node` 상층 cell (포대 b) 열림 | `Radar(id) enterU<b>[id]!` |
| 닫힘 | `exitU<b>[id]!` |
| 하층 동일 | `enterL<b>` / `exitL<b>` |
| `planning_node._tick()` 진입 | `P.Tick → P.Decide` |
| `WTABackend.solve()` 호출 (GreedyWTA) | Planner Decide self-loop (Salvo + 포대 순회) |
| Assignment(L1_LSAM, T0) 1행 | `assign_u[0][0]!` 1 fire |
| `LauncherNode._on_plan` 자기 명령 발사 | `Slot_U(batt_id).Idle → Flying` |
| `FireControlRadarNode.resolve` (Pk≥θ) | `Slot_U hitU[tgt]!` (Pk weight) |
| `FireControlRadarNode.resolve` (Pk<θ) | `Slot_U missU[tgt]!` (1-Pk weight) |
| `surveillance_radar_node` /events: IMPACT | `Radar(id) impact[id]!` |
| `Battery.fire_control_channels` | `CH_PER_U[b]` / `CH_PER_L[b]` |
| `Battery.available_missiles` | `ammoU_b[b]` / `ammoL_b[b]` (초기값) |
| `Battery.base_pk` | `PK_U[t][b]` / `PK_L[t][b]` (×100) |
| `interceptor_flyout`의 분산 | `[FLYOUT_U_MIN, FLYOUT_U_MAX]` 윈도우 |
| Salvo (SSL) | `MAX_SALVO_U / MAX_SALVO_L` |

⭐ ROS2 PoC log의 Assignment 리스트 ↔ UPPAAL Decide cycle의 assign! 시퀀스가
1:1 대응. ROS2 통계 "격추율 X%" ↔ UPPAAL SMC1 결과 직접 비교.

---

## 10. PoC 활용

### (A) GUI 시뮬레이터
```
1. UPPAAL 5 실행 → File → Open → dwta_model_v6_full.xml
2. Symbolic Simulator 탭 → Reset → enabled transition 클릭
3. 우측 Variables: ammoU_b, inflU_b, upCnt_bt, engU_b, killed, P.ds/ss 관찰
4. Trace 영역에 MSC 자동 누적
```

### (B) verifyta 일괄 검증 (기본 TCTL)
```powershell
cd c:\Users\USER\Desktop\DWTA-Optimizer
verifyta.exe -q ros2_dwta\spec\dwta_model_v6_full.xml
```
S1~SV1, E1~E3 (21개 결정적 쿼리) 일괄 검증. SMC 쿼리는 GUI에서 개별 Check.

### (C) SMC 쿼리 (GUI)
```
1. Verifier 탭 → SMC1~SMC4 쿼리 옆 Check 버튼
2. SMC1: 확률 + 95% 신뢰구간 표시
3. SMC2/3: 평균 + 히스토그램
4. SMC4: trace plot 다이얼로그 자동 표시
```
파라미터 조정: Options → Statistical parameters

### (D) 반례 trace
```powershell
verifyta.exe -t 1 -f r4 ros2_dwta\spec\dwta_model_v6_full.xml
# r4.xtr를 GUI File → Open Trace로 로드 → MSC에 채워짐
```

---

## 11. `clean_slate_optimizer.py`와 UPPAAL의 관계

**UPPAAL은 그 파이썬 코드를 호출하지 않습니다.** Python 함수, HiGHS MIP, 부동소수는
UPPAAL이 못 다룸. 대신 옵티마이저의 **정책 규칙**을 v6 모델에 추상화:

| 옵티마이저 규칙 | v6 표현 |
|---|---|
| ① `sorted(scores, key=danger, reverse=True)` | `best_u_b_salvo(b)` 작은 id 우선 |
| ② `not upper_already_locked(t)` | `upCnt_bt[b][i] < MAX_SALVO_U` 가드 |
| ③ Salvo (`SSL`) | `MAX_SALVO_U`, Planner Salvo loop |
| ④ 다층요격 | Slot_U와 Slot_L 독립, R4 쿼리 도달 |
| ⑤ Pk 기반 판정 | `PK_U[t][b]` weight on hit/miss |

따라오는 보장:
- (S5/S6) Salvo 한계 모든 trace에서 보장
- (RD1/RD2) 사거리·고도 밖 발사 0
- (SMC1) Pk 반영한 양적 격추 확률

다른 옵티마이저(GA/MIP/Greedy)로 백엔드 교체해도 같은 정책 골격이면 v6 모델
그대로 재사용.

---

## 12. ⭐ 시나리오 → 모델 자동 주입 워크플로 (한 명령)

v6는 XML 안에 **AUTO-GENERATED 마커**가 있어 ROS2 헬퍼가 한 명령으로 갱신합니다.

### 12.1 XML의 마커 영역
```c
// ===== BEGIN AUTO-GENERATED SCENARIO CONSTS =====
const int APPEAR[MAXT] = ...;
const int IMPACT_AT[MAXT] = ...;
const int U_ENTER[MAXT][NB_U] = ...;
const int U_EXIT [MAXT][NB_U] = ...;
const int L_ENTER[MAXT][NB_L] = ...;
const int L_EXIT [MAXT][NB_L] = ...;
const int PK_U[MAXT][NB_U] = ...;
const int PK_L[MAXT][NB_L] = ...;
// ===== END AUTO-GENERATED SCENARIO CONSTS =====
```
마커 사이가 자동 갱신 영역. 바깥 구조 const(MAXT/NB_U/NB_L/CH_PER/FLYOUT/PERIOD_P/
MAX_SALVO)는 수동.

### 12.2 한 명령으로 주입
```powershell
python -c "import sys; sys.path.insert(0,'ros2_dwta'); from dwta_nodes.scenario import inject_uppaal_constants; inject_uppaal_constants('ros2_dwta/spec/dwta_model_v6_full.xml', seed=42, n_threats=3)"
```
효과: v6 XML의 BEGIN/END 마커 사이 블록이 `random_saturation_scenario(seed=42, n_threats=3)`에서 계산된 값으로 교체. XML well-formed 유지.

### 12.3 헬퍼 함수
```python
# 텍스트만 보기
from dwta_nodes.scenario import dump_uppaal_scenario
print(dump_uppaal_scenario(seed=42, n_threats=3))

# XML에 직접 주입 (in-place 또는 새 파일)
from dwta_nodes.scenario import inject_uppaal_constants
inject_uppaal_constants('ros2_dwta/spec/dwta_model_v6_full.xml',
                        seed=42, n_threats=3)
# 또는:
inject_uppaal_constants('ros2_dwta/spec/dwta_model_v6_full.xml',
                        seed=7, n_threats=3,
                        out_path='ros2_dwta/spec/dwta_model_v6_seed7.xml')
```

### 12.4 워크플로 (전체 cycle)
```
1. ROS2: python ros2_dwta\run_poc.py 75 random  → 실제 trace + 통계 생산
2. UPPAAL 시나리오 주입:
   python -c "...; inject_uppaal_constants('...v6_full.xml', seed=42, n_threats=3)"
3. UPPAAL: verifyta -q ros2_dwta\spec\dwta_model_v6_full.xml
4. SMC1 (Pr[<=40](<> killed==MAXT)) 결과 vs ROS2 통계 "격추율" 비교
```

ROS2와 UPPAAL이 **정확히 같은 시나리오로** PoC → 정합 검증 가능.

---

## 13. UPPAAL SMC — Pk·Salvo의 통계적 의미

UPPAAL 5는 SMC가 통합되어 별도 설치 없이 확률 분석 가능.

### Pk weight의 의미
v6 Slot의 hit edge `probability = PK_U[tgt][batt_id]` (예: 85), miss edge
`probability = 100 - 85 = 15`. SMC 모드에서:
- `Pr[<=T] (<> killed == MAXT)` → Pk 0.85 가정 시 전량 격추 확률을 통계 추정

### Salvo의 효과적 Pk
Salvo=2, Pk=0.85 → 효과적 Pk = `1 - (1-0.85)² = 0.9775`. SMC1 결과로 직접 확인 가능.

### SMC 파라미터 (Verifier 탭 → Options → Statistical parameters)
| 파라미터 | 의미 | 기본 |
|---|---|---|
| Lower/Upper deviation (δ) | 신뢰구간 절반 폭 | 0.01 |
| Probability false negatives (α) | Type I 오류 | 0.05 |
| Probability false positives (β) | Type II 오류 | 0.05 |
| Trace resolution | simulate 샘플 수 | 4000 |
| Discretization step for hybrid | ODE 적분 step | 0.01 |

### Location의 Rate of Exponential (별도 옵션)
invariant 없는 location에 머무는 시간이 지수분포 따를 때 그 rate λ. v6는 결정적
invariant 사용하므로 안 씀.

---

## 14. 모델 한계 + state space 상한

### 14.1 의도적 추상화
- **위협 위치/궤적**: 시간 윈도우로 환원 (사거리 + 고도 교집합)
- **Pk**: 정수 확률 (×100). SMC 가중치로 양적
- **MIP 해**: best_u_b_salvo 순서로 추상
- **연속 좌표**: 사전 계산된 시간 윈도우

### 14.2 검증 가능 규모

| MAXT | NB_U+NB_L | sum(CH) | MAX_SALVO_U | 인스턴스 | verifyta 시간 |
|---|---|---|---|---|---|
| 2 | 2 | 4 | 1 | ~10 | 초 |
| **3** | **4** | **10** | **2** | **15 (현재 v6)** | **분~십수 분** |
| 5 | 4 | 16 | 2 | ~25 | 십수 분~timeout |

v6는 Salvo + Pk + 자동 주입 다 들어가 v3/v4/v5보다 state space가 큼. MAXT=3,
NB=2x2가 권장 한계.

### 14.3 ROS2 PoC 규모 검증
ROS2의 24+발 시나리오는 그대로는 못 검증. **축소 대표 시나리오로 invariant 보증 →
ROS2 대규모 trace에 일반화 적용**이 표준 방법.

---

## 15. Process Array (선택적 — 인스턴스 자동화)

현재 v6 System declarations는 인스턴스를 명시적으로 나열. 시나리오가 자주 바뀌면
UPPAAL의 **free parameter** 자동 enumerate 활용 가능:

```c
const int NCH_U = 5;                          // = sum(CH_PER_U)
const int batt_of_u[NCH_U] = {0,0,0, 1,1};    // 슬롯 ch_id → 포대 id

// Slot_U 파라미터를 bounded int로 (v6 변경 필요):
template Slot_U
  parameter: const int[0, NCH_U-1] ch_id;
  declaration: int batt_id = batt_of_u[ch_id];

// system 한 줄로
system Radar, Threat, Slot_U, Slot_L, Planner;
```
→ UPPAAL이 NCH_U개 Slot_U 자동 생성. ROS2 `dump_uppaal_system()` 헬퍼 출력으로
교체.

| | 현재 (명시적 list) | Free parameter |
|---|---|---|
| 인스턴스 추가 | 손으로 system 수정 | const 배열만 |
| MSC 가독성 | `SU0_0` 명확 | `Slot_U(0)` 형태 |

대규모(20+ 인스턴스) 시나리오는 free parameter가 유리.

---

## 16. Location 다이얼로그 옵션

GUI에서 location 더블클릭 시 표시:

| 항목 | 의미 | v6 사용 |
|---|---|---|
| Name | 쿼리에서 참조 (`P.Tick` 등) | 모든 location |
| Invariant | 시간 제약 | Pre/Scan/Tick/Flying |
| Rate of Exponential | SMC 전용 (지수분포 머무는 시간) | 안 씀 |
| Initial | 초기 위치 | Pre/Inbound/Idle/Tick |
| Urgent | 시간 진행 금지 | 안 씀 |
| Committed | urgent + 우선 처리 | Decide |
| Comments 탭 | 주석 (검증 무관) | 미사용 |
| Test Code 탭 (On enter/exit) | UPPAAL Yggdrasil 테스트 생성 hook | 미사용 |

---

## 부록 A. v6 XML 파일 구조

```
<?xml ?>
<nta>
  <declaration>
    // ---- 구조 영역 (수동) ----
    // §3.1 MAXT, NB_U/L, CH_PER_*, FLYOUT_*, PERIOD_P, MAX_SALVO_*

    // ===== BEGIN AUTO-GENERATED SCENARIO CONSTS =====
    // §3.2 APPEAR, IMPACT_AT, U/L_ENTER/EXIT, PK_U/L
    // (inject_uppaal_constants()가 갱신)
    // ===== END AUTO-GENERATED SCENARIO CONSTS =====

    // ---- 공유 상태 (수동) ----
    // §3.3 ammoU/L_b, inflU/L_b, upCnt_bt, loCnt_bt, engU/L_b,
    //      killed, leaked, shots_u/l_fired

    // ---- 채널 (수동) ----
    // §3.4 assign_u/l (handshake), detect/cross*/impact/hit*/miss* (broadcast)

    // ---- 함수 (수동) ----
    // §3.5 best_u/l_b_salvo, any_uCover/lCover
  </declaration>

  <template><name>Radar</name>     ... (§4.1)
  <template><name>Threat</name>    ... (§4.2)
  <template><name>Slot_U</name>    ... (§4.3, Pk + jitter)
  <template><name>Slot_L</name>    ... (§4.4)
  <template><name>Planner</name>   ... (§4.5, decider + Salvo loop)

  <system>
    R0/R1/R2, T0/T1/T2,
    SU0_0..SU0_2, SU1_0..SU1_1,   // CH_PER_U={3,2}
    SL0_0..SL0_2, SL1_0..SL1_1,   // CH_PER_L={3,2}
    P;
  </system>

  <queries>
    S1~S7, RD1/RD2, T1, L1, R1~R5, SV1, E1~E3, SMC1~SMC4   (총 25개)
  </queries>
</nta>
```

## 부록 B. 디버깅 체크리스트

| 증상 | 확인 |
|---|---|
| 모델 안 열림 | XML well-formed? `python -m xml.dom.minidom <file>` |
| inject가 실패함 | XML에 BEGIN/END 마커 정확히 있는지 확인 |
| Planner가 Decide에 영원히 머묾 | Edge 6 가드 `ds == NB_U + NB_L`, 각 skip edge 가드 OR 조건 |
| Salvo가 안 일어남 | `MAX_SALVO_U > 1`? best_u_b_salvo가 `< MAX_SALVO_U` 가드? |
| assign이 fire 안 됨 | Idle인 Slot_U(b) 있나? best_u_b_salvo(b) ≥ 0? |
| `best_*_salvo` 항상 -1 | engU_b/engL_b가 true 안 됨 → Radar enter* fire 시점 |
| `inflU_b` 음수 | Planner `++` vs Slot `--` 균형 |
| state space 폭발 | MAXT/NB/CH/MAX_SALVO 줄이기 |
| T1 NOT satisfied | invariant + guard 조합 |
| SMC1 결과가 100%만 나옴 | Pk weight 무시되는 검증 모드? Verifier가 SMC 모드인지 확인 |

---

추가 질문은 §10(PoC), §12(자동 주입), §9(매핑) 출발.
