# UPPAAL 모델 설계 · 구현 · 사용 — 완전 문서

이 문서는 현 시점의 메인 모델 [`dwta_model_v5_explicit_assign.xml`](./dwta_model_v5_explicit_assign.xml)
을 기준으로, UPPAAL/Timed Automata 기초부터 v5의 모든 템플릿·노드·검증 쿼리·운용
워크플로까지 한 장에 정리합니다. 검증 속성의 짧은 카탈로그는
[`timed_automata.md`](./timed_automata.md) 참조.

> **메인 모델**: `dwta_model_v5_explicit_assign.xml` — PlanningNode가 WTA 의사결정
> 주체이고, 명시적 `assign_u[b][t]`/`assign_l[b][t]` 채널로 발사 명령을 내리는
> 구조. ROS2 시뮬레이터의 `planning_node._tick → GreedyWTA.solve() → Assignment
> 리스트 → LauncherNode 실행` 흐름과 1:1 정합.

---

## 0. 한 장 인덱스

| § | 내용 |
|---|---|
| 1 | UPPAAL과 Timed Automata 기초 (도구·이론·XML·TCTL·한계) |
| 2 | v5 모델 전체 구성 (템플릿/인스턴스/채널) |
| 3 | Declaration 상세 (글로벌·로컬·시스템·함수) |
| 4 | 템플릿별 구현 (Radar / Threat / Slot_U / Slot_L / Planner) |
| 5 | 채널 전체 사양 (broadcast vs handshake) |
| 6 | 한 위협의 lifecycle (시간순) |
| 7 | 검증 쿼리 20개 상세 |
| 8 | MSC 읽는 법 + 흔히 헷갈리는 동작 |
| 9 | ROS2 시뮬레이터 ↔ UPPAAL 매핑 |
| 10 | PoC 활용 (GUI / verifyta / 헬퍼) |
| 11 | `clean_slate_optimizer.py`와의 관계 |
| 12 | UPPAAL SMC — 통계 검증과 확률·ODE |
| 13 | 모델 한계 + state space 상한 |
| 14 | 시나리오 → 모델 자동 dump 워크플로 |
| 15 | Process Array (free parameter로 자동 인스턴스화) |
| 16 | Location 다이얼로그 옵션 (Exponential rate, Test Code, Comments) |
| 부록 A | v5 XML 파일 구조 한눈에 |
| 부록 B | 디버깅 체크리스트 |

---

## 1. UPPAAL과 Timed Automata 기초

### 1.1 UPPAAL이 무엇인가

**UPPAAL**은 Aalborg(덴마크) + Uppsala(스웨덴) 두 대학이 1995년 이후 공동 개발해
온 **실시간 시스템 모델 체커**입니다. 세 기능을 한 GUI에 통합:

| 역할 | 도구 | 무엇을 |
|---|---|---|
| **에디터** | Editor 탭 | 시스템(템플릿 네트워크)을 그래프 + 코드로 명세 |
| **시뮬레이터** | Symbolic / Concrete Simulator 탭 | 한 step씩 실행, MSC + 변수 패널 관찰 |
| **검증기** | Verifier 탭 | TCTL 쿼리로 안전성·라이브니스·도달성·확률 검증 |

검증 엔진은 별도 CLI `verifyta.exe`로도 동작.

### 1.2 Timed Automaton — 이론 핵심

**Timed Automaton (TA)** = 유한 오토마타 + 실수값 클럭 (Alur & Dill, 1994). UPPAAL
모델 하나는 여러 TA의 **네트워크**.

#### 구성 요소

| 요소 | 정의 | UPPAAL XML |
|---|---|---|
| **Location** | 자동기의 상태 노드 | `<location id="...">` |
| **Edge / Transition** | location 간 화살표 | `<transition><source/><target/>` |
| **Clock** | 실수값 변수. 모든 클럭은 동일 속도로 증가 | `clock x;` |
| **Guard** | edge fire 조건 (클럭/정수 비교) | `<label kind="guard">x >= 5</label>` |
| **Invariant** | location 머무는 조건. 위반 시 강제 이동 | `<label kind="invariant">x <= 10</label>` |
| **Assignment** | edge fire 시 실행 (변수 갱신, 클럭 리셋) | `<label kind="assignment">x=0, n++</label>` |

#### 시간이 흐르는 두 방식
1. **Delay (시간 진행)**: 어떤 edge도 fire 안 하면 모든 클럭이 동시에 증가.
   **invariant가 한계** — `x <= 10`인 location에선 x가 10을 넘기 전에 무언가 fire.
2. **Action (전이)**: edge가 fire되면 시간 진행 없이 즉시 다음 location, assignment 실행.

#### 특수 location

| 종류 | 의미 | UPPAAL 표기 |
|---|---|---|
| 일반 | invariant 안에서 시간 진행 OK | (기본) |
| **Urgent** | 시간 진행 금지. 즉시 outgoing edge 중 하나 fire | `<urgent/>` |
| **Committed** | urgent + 다른 자동기보다 우선. 원자적 처리 | `<committed/>` |

v5에서는 Planner의 `Decide` 위치가 committed — 모든 포대의 결심을 0-시간 안에
연쇄 처리.

#### 채널과 동기화

| 채널 종류 | semantics | 선언 |
|---|---|---|
| **이진 동기 (handshake)** | 1 sender(`a!`) + **정확히 1 receiver**(`a?`) 동시 필요. 매칭 없으면 sender도 fire 못 함 | `chan a;` |
| **Broadcast** | 1 sender + receiver **0명 이상**. 매칭 없어도 sender fire OK | `broadcast chan a;` |
| **Urgent** | + 시간 진행 막음 | `urgent chan a;` |

v5는 **handshake `assign_u/l`** (Planner→Slot, 정확히 1 슬롯이 받아야 발사) +
**broadcast `detect/cross/impact/hit/miss`** (수신자 0 OK) 두 가지 혼합.

#### 네트워크 (NTA, Network of Timed Automata)

여러 TA가 채널·전역변수로 통신. **모든 클럭은 같은 절대 시각** — R0의 `t=6.0`과
P의 `cp=1.4`는 같은 절대 시각.

### 1.3 UPPAAL XML 명세 형식

```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE nta PUBLIC '...flat-1_6.dtd'>
<nta>
  <declaration>
    const int N = 3;                       <!-- 글로벌 declaration -->
    broadcast chan tick;
    int square(int x) { return x * x; }    <!-- C-like 함수 -->
  </declaration>

  <template>
    <name>Worker</name>
    <parameter>const int id</parameter>
    <declaration>clock x;</declaration>     <!-- 템플릿 로컬 declaration -->

    <location id="l0"><name>Idle</name>
      <label kind="invariant">x <= 10</label>
    </location>
    <location id="l1"><name>Busy</name><committed/></location>
    <init ref="l0"/>

    <transition>
      <source ref="l0"/><target ref="l1"/>
      <label kind="select">i : int[0,N-1]</label>
      <label kind="guard">x >= 5</label>
      <label kind="synchronisation">tick!</label>
      <label kind="assignment">x=0</label>
    </transition>
  </template>

  <system>                                   <!-- 인스턴스화 -->
    W0 = Worker(0); W1 = Worker(1);
    system W0, W1;
  </system>

  <queries>
    <query><formula>A[] not deadlock</formula><comment>...</comment></query>
  </queries>
</nta>
```

**Declaration 4 곳** (GUI 좌측 트리):
```
Project
├── Declarations               ← 글로벌
├── <TemplateName>
│   ├── Declarations           ← 템플릿 로컬
│   └── (graph)
└── System declarations        ← system 절
```

**Label 종류** (transition/location 옆 텍스트):
| `kind` | 위치에서 | 전이에서 |
|---|---|---|
| `invariant` | 머무는 조건 | — |
| `guard` | — | 전이 조건 |
| `synchronisation` | — | `chan!` 또는 `chan?` |
| `assignment` | — | 전이 시 실행 코드 |
| `select` | — | 비결정 변수 선택 |
| `probability` | — | SMC 분기 가중치 |
| `comments` | 메모 | 메모 |

### 1.4 TCTL 쿼리 기초

| 쿼리 | 의미 | 예 |
|---|---|---|
| `A[] φ` | 모든 실행의 모든 상태에서 φ (Safety) | `A[] ammo >= 0` |
| `A<> φ` | 모든 실행에서 언젠가 φ (Liveness) | `A<> done` |
| `E<> φ` | 어떤 실행에서 언젠가 φ (Reachability) | `E<> killed == 5` |
| `φ --> ψ` | φ가 참이면 결국 ψ (응답성) | `request --> response` |
| `Pr[<=T] (...)` | SMC 확률 | `Pr[<=40] (<> killed == MAXT)` |
| `E[<=T; N] (max: x)` | SMC 평균 | `E[<=40; 200] (max: killed)` |
| `simulate N [<=T] {x, y}` | SMC trace plot | (그래프 출력) |

φ 안에 위치 검사(`T0.Killed`), 변수 비교(`killed==3`), 클럭 비교(`P.cp <= 2`),
논리(`&&`, `||`, `not`, `imply`), 수량자(`forall`, `exists`) 사용.

검증 결과: `Formula is satisfied.` 또는 `Formula is NOT satisfied.` (`-t 1`로
반례 trace 받기).

### 1.5 UPPAAL이 못 다루는 것

- **연속 동역학**: sin/cos/sqrt 같은 비선형. 클럭은 `dx/dt = 1` 일정 (SMC에선
  위치별 다른 slope로 ODE 표현 부분 가능)
- **부동소수**: int/bool/clock만. 실수는 클럭 비교에서만 등장
- **무한 데이터**: 모든 배열·범위는 컴파일 타임 고정
- **확률**: 기본 TCTL은 비결정만. 통계 필요하면 같은 UPPAAL 5의 **통합 SMC** 사용 (§12)
- **MIP/LP 해**: 정수 최적해 자체는 표현 불가. 정책 규칙만 추상화

---

## 2. v5 모델 전체 구성

```
┌──── 시간 권위 ────┐    ┌───── 의사결정 ─────┐    ┌────── 실행 ──────┐
│ Radar(0..MAXT-1)  │    │     Planner        │    │  Slot_U × NCH_U   │
│  detect[i]!       │    │  Tick → Decide     │    │  Slot_L × NCH_L   │
│  enterU0/1/L0/1[i]│    │  (committed)        │    │  (Idle/Flying)    │
│  exit*[i]!        │    │  ammoU_b/inflU_b/   │    │  hit/miss 통보    │
│  impact[i]!       │    │  upCnt_bt 갱신      │    │                   │
└────────┬──────────┘    └──────────┬─────────┘    └─────────┬─────────┘
         │ broadcast                 │ handshake               │ broadcast
         ▼                           ▼  assign_u[b][t]!         ▼
      Threat(0..MAXT-1)              Slot_U(b) / Slot_L(b)    Threat(t)
      Inbound → Tracked              Idle → Flying            hit/miss/impact?
      ↑ engU_b/engL_b 토글           Flying → Idle (FLYOUT)   Killed/Leaked
      ↓ hit/miss/impact?
      Killed / Leaked
```

### 5개 템플릿 요약

| Template | parameter | local | 인스턴스 수 |
|---|---|---|---|
| `Radar` | `const int id` | `clock t` | MAXT (3) |
| `Threat` | `const int id` | — | MAXT (3) |
| `Slot_U` | `const int batt_id` | `clock f; int tgt` | sum(CH_PER_U) (3) |
| `Slot_L` | `const int batt_id` | `clock f; int tgt` | sum(CH_PER_L) (3) |
| `Planner` | — | `clock cp; int ds` | 1 |

### 13개 인스턴스 (System declarations)

```c
R0 = Radar(0); R1 = Radar(1); R2 = Radar(2);
T0 = Threat(0); T1 = Threat(1); T2 = Threat(2);
// 상층: CH_PER_U = {2, 1} -> 3 슬롯
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0); SU1_0 = Slot_U(1);
// 하층: CH_PER_L = {2, 1} -> 3 슬롯
SL0_0 = Slot_L(0); SL0_1 = Slot_L(0); SL1_0 = Slot_L(1);
P = Planner();
system R0, R1, R2, T0, T1, T2,
       SU0_0, SU0_1, SU1_0,
       SL0_0, SL0_1, SL1_0, P;
```

MSC에 세로줄로 그려지는 lifeline 정확히 이 13개.

---

## 3. Declaration 상세

### 3.1 시스템 상수
```c
const int MAXT             = 3;
const int NB_U             = 2;
const int NB_L             = 2;
const int CH_PER_U[NB_U]   = {2, 1};   // 상층 포대별 채널 수
const int CH_PER_L[NB_L]   = {2, 1};
const int FLYOUT_U         = 5;        // 상층 비행시간
const int FLYOUT_L         = 2;
const int PERIOD_P         = 2;        // 계획수립 주기
```

| 변수 | 누가 쓰나 |
|---|---|
| `MAXT` | 모든 배열 차원, `int[0,MAXT-1]` select range |
| `NB_U/NB_L` | 채널 풀 + `forall (b : int[0,NB_U-1])` 쿼리 |
| `CH_PER_U[b]` | Planner의 발사 가드 `inflU_b[b] < CH_PER_U[b]` |
| `FLYOUT_*` | Slot의 Flying invariant + 가드 `f >= FLYOUT_U` |
| `PERIOD_P` | Planner의 Tick invariant + 가드 `cp >= PERIOD_P` |

### 3.2 시나리오 윈도우 (위협별 / (위협, 포대)별 timing)
```c
const int APPEAR[MAXT]        = { 0,  3,  6};
const int IMPACT_AT[MAXT]     = {30, 32, 35};
const int U_ENTER[MAXT][NB_U] = { { 8, 9}, {11,12}, {14,15} };
const int U_EXIT [MAXT][NB_U] = { {22,21}, {24,23}, {26,25} };
const int L_ENTER[MAXT][NB_L] = { {16,17}, {19,18}, {20,21} };
const int L_EXIT [MAXT][NB_L] = { {28,27}, {30,29}, {33,31} };
```

`(위협 t, 포대 b)`의 사거리 + 고도 게이트를 모두 만족하는 시간 구간 = `[ENTER[t][b],
EXIT[t][b]]`. ROS2 `scenario.dump_uppaal_windows()`가 궤적 시뮬레이션으로 사전 계산.

오직 **Radar 템플릿의 self-loop 가드**(`t == U_ENTER[id][0]` 등)만 직접 참조.
다른 인스턴스는 broadcast 신호로만 통신.

### 3.3 공유 상태 (인스턴스 간 동기화 매개체)
```c
int  ammoU_b[NB_U]    = {3, 2};        // 포대 b 잔여탄
int  ammoL_b[NB_L]    = {3, 2};
int  inflU_b[NB_U];                    // 포대 b 비행중 요격탄
int  inflL_b[NB_L];
int  upCnt_bt[NB_U][MAXT];             // (포대, 위협) 동시 교전 카운터
int  loCnt_bt[NB_L][MAXT];
bool engU_b[MAXT][NB_U];               // 위협 t가 포대 b(상층) 윈도우 안?
bool engL_b[MAXT][NB_L];
int  killed = 0, leaked = 0;           // 종결 누계
int  shots_u_fired = 0;                // Planner 누계 발사
int  shots_l_fired = 0;
```

| 변수 | 쓰기 | 읽기 |
|---|---|---|
| `ammoU_b[b]` | **Planner** 발사 시 `--` | Planner 가드, S2u 쿼리 |
| `inflU_b[b]` | **Planner** 발사 시 `++`, Slot 판정 시 `--` | Planner 가드, S3 쿼리 |
| `upCnt_bt[b][t]` | **Planner** 발사 시 `++`, Slot 판정 시 `--` | best_u_b, S5 쿼리 |
| `engU_b[t][b]` | Threat의 enter*/exit* 토글, 종결 시 false | Planner 가드 (best_u_b), RD1 쿼리 |
| `killed` | Threat hit 시 `++` | L1/R1 쿼리 |
| `leaked` | Threat impact 시 `++` | R5 쿼리 |
| `shots_u_fired` | Planner 발사 시 `++` | E3 쿼리 |

⭐ v5 핵심: **자원 갱신(ammo/infl/upCnt)을 Planner가 발사 결심 시점에 수행**. Slot은
판정 시점에만 `--`로 정리.

### 3.4 채널

```c
// Handshake — 정확히 1 sender + 1 receiver 매칭 필요
chan assign_u[NB_U][MAXT];   // Planner -> Slot_U (특정 포대의 Idle 슬롯 1 명)
chan assign_l[NB_L][MAXT];   // Planner -> Slot_L

// Broadcast — receiver 0명도 OK
broadcast chan detect[MAXT];                       // Radar -> Threat
broadcast chan impact[MAXT];                       // Radar -> Threat
broadcast chan enterU0[MAXT], exitU0[MAXT];       // Radar -> Threat (상층 포대 0)
broadcast chan enterU1[MAXT], exitU1[MAXT];       // 상층 포대 1
broadcast chan enterL0[MAXT], exitL0[MAXT];       // 하층 포대 0
broadcast chan enterL1[MAXT], exitL1[MAXT];       // 하층 포대 1
broadcast chan hitU[MAXT], missU[MAXT];           // Slot_U -> Threat
broadcast chan hitL[MAXT], missL[MAXT];           // Slot_L -> Threat
```

**왜 assign은 handshake?** broadcast면 receiver 0명에서도 fire 가능 → "자유 채널
없는데 발사 명령" 가능해짐. handshake는 정확히 1 슬롯이 매칭되어야 fire → "발사
명령은 항상 자유 채널 1개 있을 때만" 자연히 강제.

**왜 hit/miss는 broadcast?** Threat이 이미 Killed라 수신 안 해도 Slot의 fire는
가능해야 함 (자원 정리 위해). receiver 0 허용 필요.

### 3.5 함수
```c
int best_u_b(int b) {                  // 포대 b의 GreedyWTA 우선순위
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] == 0) return i;
        i++;
    }
    return -1;
}
int best_l_b(int b) { /* engL/loCnt 동일 */ }

bool any_uCover(int t) { return upCnt_bt[0][t] + upCnt_bt[1][t] > 0; }
bool any_lCover(int t) { return loCnt_bt[0][t] + loCnt_bt[1][t] > 0; }
```

**Planner의 Decide 위치 가드에서 호출** — 매 결심 cycle마다 포대별 우선순위 위협
결정. ROS2 `GreedyWTA.solve()`의 `sorted(scores, key=danger, reverse=True)` 첫
후보와 동등.

---

## 4. 템플릿별 구현 상세

### 4.1 Radar(const int id) — 위협 timing 권위자

**왜 이런 구조?** 위협마다 등장·사거리 진입/이탈·탄착 시각이 다름. Radar 인스턴스
한 개가 위협 한 대를 처음부터 끝까지 책임지며 broadcast로 모두에게 알림.

**Local**: `clock t;`

**Locations** (3개):
- `Pre` — invariant `t <= APPEAR[id]` (탐지 전 대기)
- `Scan` — invariant `t <= IMPACT_AT[id]` (활성 추적)
- `Done` — terminal (탄착 후)

**Transitions** (10개):

| # | from → to | guard | sync | 의미 |
|---|---|---|---|---|
| 1 | Pre → Scan | `t == APPEAR[id]` | `detect[id]!` | 탐지 |
| 2 | Scan → Scan | `t == U_ENTER[id][0]` | `enterU0[id]!` | 상층 포대 0 윈도우 진입 |
| 3 | Scan → Scan | `t == U_EXIT[id][0]` | `exitU0[id]!` | 상층 포대 0 이탈 |
| 4 | Scan → Scan | `t == U_ENTER[id][1]` | `enterU1[id]!` | 상층 포대 1 진입 |
| 5 | Scan → Scan | `t == U_EXIT[id][1]` | `exitU1[id]!` | 상층 포대 1 이탈 |
| 6 | Scan → Scan | `t == L_ENTER[id][0]` | `enterL0[id]!` | 하층 포대 0 진입 |
| 7 | Scan → Scan | `t == L_EXIT[id][0]` | `exitL0[id]!` | 하층 포대 0 이탈 |
| 8 | Scan → Scan | `t == L_ENTER[id][1]` | `enterL1[id]!` | 하층 포대 1 진입 |
| 9 | Scan → Scan | `t == L_EXIT[id][1]` | `exitL1[id]!` | 하층 포대 1 이탈 |
| 10 | Scan → Done | `t == IMPACT_AT[id]` | `impact[id]!` | 탄착 |

**동작 원리**: `t == X` 가드와 `t <= X` invariant 조합으로 정확히 X 시각에 fire
강제. self-loop 8개로 위치 안 바꾸고 broadcast만 발사.

### 4.2 Threat(const int id) — signal-driven 적 탄도탄

**왜 이런 구조?** 위협은 자기 시간을 모름. Radar 신호로만 진행, hit 한 발에 종결.
v5는 단발이라 한 hit에 즉시 Killed.

**Local**: 없음 (clock 없음, signal-driven)

**Locations** (4개): `Inbound` (초기) / `Tracked` (활성) / `Killed` (격추, terminal) / `Leaked` (탄착, terminal)

**Transitions** (15개):

| # | from → to | sync | assignment |
|---|---|---|---|
| 1 | Inbound → Tracked | `detect[id]?` | — |
| 2 | Tracked → Tracked | `enterU0[id]?` | `engU_b[id][0]=true` |
| 3 | Tracked → Tracked | `exitU0[id]?` | `engU_b[id][0]=false` |
| 4 | Tracked → Tracked | `enterU1[id]?` | `engU_b[id][1]=true` |
| 5 | Tracked → Tracked | `exitU1[id]?` | `engU_b[id][1]=false` |
| 6 | Tracked → Tracked | `enterL0[id]?` | `engL_b[id][0]=true` |
| 7 | Tracked → Tracked | `exitL0[id]?` | `engL_b[id][0]=false` |
| 8 | Tracked → Tracked | `enterL1[id]?` | `engL_b[id][1]=true` |
| 9 | Tracked → Tracked | `exitL1[id]?` | `engL_b[id][1]=false` |
| 10 | Tracked → Tracked | `missU[id]?` | — (재교전 대기) |
| 11 | Tracked → Tracked | `missL[id]?` | — |
| 12 | Tracked → Killed | `hitU[id]?` | engU/engL 모두 false, `killed++` |
| 13 | Tracked → Killed | `hitL[id]?` | (같음) |
| 14 | Inbound → Leaked | `impact[id]?` | `leaked++` |
| 15 | Tracked → Leaked | `impact[id]?` | engU/engL 모두 false, `leaked++` |

### 4.3 Slot_U(const int batt_id) — 상층 채널 (단순 reactive)

**왜 이런 구조?** v5에서 Slot은 의사결정 안 함. Planner의 명시적 명령(`assign_u
[batt_id][t]?`)만 받아 즉시 비행 시작. 비행 끝나면 hit 또는 miss 통보만.

**Local**: `clock f; int tgt;`

**Locations** (2개):
- `Idle` — Planner 명령 대기
- `Flying` — invariant `f <= FLYOUT_U` (비행 중)

**Transitions** (3개):

| # | from → to | select | guard | sync | assignment | 의미 |
|---|---|---|---|---|---|---|
| 1 | Idle → Flying | `t : int[0,MAXT-1]` | — | `assign_u[batt_id][t]?` | `tgt=t, f=0` | Planner 명령 수신 → 비행 시작 |
| 2 | Flying → Idle | — | `f >= FLYOUT_U` | `hitU[tgt]!` | `inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--` | 명중 |
| 3 | Flying → Idle | — | `f >= FLYOUT_U` | `missU[tgt]!` | (같음) | 실패 |

**핵심**: 발사 결심 시점의 자원 갱신(ammo/infl/upCnt `++`)은 Planner가 함. Slot은
판정 시점의 자원 회수(`--`)만 함. committed Ready 없음, skip 전이 없음, best
함수 호출 없음.

### 4.4 Slot_L(const int batt_id) — 하층 채널

Slot_U와 구조 100% 동일. L-계열 변수 (`ammoL_b/inflL_b/loCnt_bt/FLYOUT_L/hitL/missL/assign_l/best_l_b`).

### 4.5 Planner — WTA 의사결정 주체 (v5 핵심)

**왜 이런 구조?** ROS2 PlanningNode와 1:1 매핑. 매 PERIOD_P 주기마다 모든 포대를
순회하며 `best_u_b()`/`best_l_b()`로 위협 결정 → 가능한 결정마다 `assign!`
broadcast + 자원 즉시 갱신. 한 cycle은 committed 위치에서 0-시간 안에 완료.

**Local**: `clock cp; int ds = 0;`
- `cp`: 주기 클럭
- `ds`: decision step (포대 순회 카운터, 0~NB_U+NB_L)

**Locations** (2개):
- `Tick` — invariant `cp <= PERIOD_P` (주기 대기)
- `Decide` — **committed** (결심 진행, 0-시간)

**Transitions** (6개):

#### Edge 1 — Tick → Decide (주기 도래)
- guard `cp >= PERIOD_P`
- assign `ds = 0`
- 의미: "주기 도달, 결심 cycle 시작"

#### Edge 2 — Decide → Decide (상층 발사)
- select `t : int[0,MAXT-1]`
- guard `ds < NB_U && ammoU_b[ds] > 0 && inflU_b[ds] < CH_PER_U[ds] && best_u_b(ds) >= 0 && t == best_u_b(ds)`
- sync `assign_u[ds][t]!`
- assign `ammoU_b[ds]--, inflU_b[ds]++, upCnt_bt[ds][t]++, shots_u_fired++, ds++`
- 의미: "포대 ds (상층) 가 위협 t를 노릴 수 있음 → 그 포대 슬롯 한 명에게 명령
  + 자원 갱신 + 다음 포대로"

#### Edge 3 — Decide → Decide (상층 skip)
- guard `ds < NB_U && (ammoU_b[ds] == 0 || inflU_b[ds] >= CH_PER_U[ds] || best_u_b(ds) < 0)`
- assign `ds++`
- 의미: "상층 포대 ds 발사 불가 → 그냥 다음으로"

#### Edge 4 — Decide → Decide (하층 발사)
- select `t : int[0,MAXT-1]`
- guard `ds >= NB_U && ds < NB_U + NB_L && ammoL_b[ds-NB_U] > 0 && inflL_b[ds-NB_U] < CH_PER_L[ds-NB_U] && best_l_b(ds-NB_U) >= 0 && t == best_l_b(ds-NB_U)`
- sync `assign_l[ds-NB_U][t]!`
- assign `ammoL_b[ds-NB_U]--, inflL_b[ds-NB_U]++, loCnt_bt[ds-NB_U][t]++, shots_l_fired++, ds++`

#### Edge 5 — Decide → Decide (하층 skip)
- guard `ds >= NB_U && ds < NB_U + NB_L && (ammoL_b == 0 || ...)`
- assign `ds++`

#### Edge 6 — Decide → Tick (cycle 종료)
- guard `ds == NB_U + NB_L`
- assign `cp = 0`
- 의미: "모든 포대 순회 끝 → 주기 클럭 리셋 후 다시 대기"

#### 결심 cycle 흐름 (t = 10 예시)
```
P.Tick (cp=2) ──[Edge 1, ds=0]──► P.Decide (committed)
  ds=0 (상층 포대 0): best_u_b(0)=0, ammo OK, channel OK
    Edge 2: assign_u[0][0]! → 어느 SU0_x로
      ammoU_b[0]=2, inflU_b[0]=1, upCnt_bt[0][0]=1, ds=1
  ds=1 (상층 포대 1): best_u_b(1)=0이지만 upCnt_bt[1][0]=0 (다른 포대)
    Edge 2: assign_u[1][0]! → SU1_0로 (위협 0이 포대 1 윈도우 안인 경우)
      ds=2
  ds=2 (하층 포대 0): best_l_b(0)=-1 (위협 0 하층 진입 안 함)
    Edge 5 skip: ds=3
  ds=3 (하층 포대 1): best_l_b(1)=-1
    Edge 5 skip: ds=4 (=NB_U+NB_L)
  Edge 6: cp=0
P.Decide ──► P.Tick   (모든 게 0 시간 안에 처리)
```

ROS2 `GreedyWTA.solve()`가 매 tick에 반환하는 Assignment 리스트와 정확히 같은
패턴.

---

## 5. 채널 전체 사양

| 채널 | 종류 | sender | receivers | 의미 |
|---|---|---|---|---|
| `assign_u[b][t]` | **handshake** | Planner | Slot_U(b) 중 Idle 한 명 | 상층 포대 b가 위협 t 노리라는 명령 |
| `assign_l[b][t]` | **handshake** | Planner | Slot_L(b) 중 Idle 한 명 | 하층 동일 |
| `detect[i]` | broadcast | Radar(i) | Threat(i) | 탐지 |
| `enterU0[i]` ... `exitL1[i]` | broadcast | Radar(i) | Threat(i) | (위협 i, 포대 b) 윈도우 enter/exit |
| `impact[i]` | broadcast | Radar(i) | Threat(i) | 탄착 |
| `hitU[t]` / `missU[t]` | broadcast | Slot_U | Threat(t) | 상층 명중/실패 |
| `hitL[t]` / `missL[t]` | broadcast | Slot_L | Threat(t) | 하층 동일 |

총 chan slot: `2*NB_U*MAXT + 2*NB_L*MAXT + 9*MAXT + 4*MAXT` ≈ 50개 (MAXT=3, NB=2).

---

## 6. 한 위협의 lifecycle (시간순)

위협 0이 t=0에 등장 → 격추까지.

```
t=0   R0.Pre[t=0], T0.Inbound, Slots.Idle, P.Tick[cp=0]
      ─── R0.t reaches APPEAR[0]=0 ───
      R0 fires detect[0]! ──► T0: Inbound → Tracked
      R0: Pre → Scan[t=0]

t=2   ─── P.cp reaches 2 ───
      P.Tick → P.Decide (committed, ds=0)
        ds=0: best_u_b(0)=-1 (engU_b[0][0]=false 아직)
              Edge 3 skip: ds=1
        ds=1: best_u_b(1)=-1
              Edge 3 skip: ds=2
        ds=2: best_l_b(0)=-1
              Edge 5 skip: ds=3
        ds=3: best_l_b(1)=-1
              Edge 5 skip: ds=4
        Edge 6: cp=0
      P.Decide → P.Tick (0 시간 안에 처리)

t=4   동일 (모두 skip)

t=8   ─── R0.t reaches U_ENTER[0][0]=8 ───
      R0 fires enterU0[0]! ──► T0: engU_b[0][0]=true (self-loop)

t=9   R0 fires enterU1[0]! ──► T0: engU_b[0][1]=true

t=10  P.cp reaches 2 다시
      P.Tick → P.Decide (ds=0)
        ds=0: best_u_b(0)=0 (engU_b[0][0]=true, upCnt_bt[0][0]=0)
              Edge 2: assign_u[0][0]! → 어느 SU0_x 슬롯이 handshake 매칭
                SU0_0 (Idle인 첫 후보): select t=0
                  Idle → Flying[f=0]
                  Planner assign: ammoU_b[0]=2, inflU_b[0]=1, upCnt_bt[0][0]=1, ds=1
        ds=1: best_u_b(1)=0 (engU_b[0][1]=true, upCnt_bt[1][0]=0)
              Edge 2: assign_u[1][0]! → SU1_0 매칭
                SU1_0: Idle → Flying
                Planner: ammoU_b[1]=1, inflU_b[1]=1, upCnt_bt[1][0]=1, ds=2
        ds=2: best_l_b(0)=-1 (engL_b[0][0]=false)
              Edge 5: ds=3
        ds=3: Edge 5: ds=4
        Edge 6: cp=0

t=15  ─── SU0_0.f reaches FLYOUT_U=5 ───
      SU0_0 fires hitU[0]! (또는 missU[0]!)
        ──► T0: Tracked → Killed (engU/engL false, killed=1)
        SU0_0: inflU_b[0]=0, upCnt_bt[0][0]=0, Flying → Idle
      동시: SU1_0.f도 5 도달 → hitU[0]! 또는 missU[0]!
        T0는 이미 Killed라 수신 안 함 (broadcast라 OK)
        SU1_0: inflU_b[1]=0, upCnt_bt[1][0]=0, Flying → Idle

t=30  R0.t reaches IMPACT_AT[0]=30
      R0 fires impact[0]! → T0는 Killed (sink)라 수신 안 함
      R0: Scan → Done
```

### 핵심 6가지
1. Threat은 시간 모름. Radar broadcast가 모든 상태 변화 트리거.
2. Planner는 매 주기마다 Decide cycle을 0-시간 안에 모두 처리 (committed).
3. 같은 포대 두 슬롯은 같은 위협에 동시 발사 안 됨 (best_u_b의 `upCnt_bt==0` 가드).
4. 다른 포대는 같은 위협 노릴 수 있음 (포대별 cnt 별개).
5. broadcast hit/miss는 receiver 0 OK (종결된 위협 무시해도 fire 가능).
6. handshake assign은 정확히 1 슬롯 매칭 (자유 채널 보장).

---

## 7. 검증 쿼리 20개 상세

### 7.1 Safety (A[], 8개)

| ID | 쿼리 | 의미 | 왜 성립? |
|---|---|---|---|
| S1 | `A[] not deadlock` | 교착 없음 | Planner cycle 종결 + Slot skip 없음 + broadcast 수신 0 허용 |
| S2u | `A[] forall (b) ammoU_b[b] >= 0` | 잔여탄 음수 불가 | Planner 발사 가드에 `ammo > 0` |
| S2l | `A[] forall (b) ammoL_b[b] >= 0` | 하층 동일 | |
| S3 | `A[] forall (b) inflU_b[b] <= CH_PER_U[b]` | 비행중 ≤ 채널 | Planner 가드 + Slot 판정 시 `--` |
| S4 | `A[] forall (b) inflL_b[b] <= CH_PER_L[b]` | 하층 동일 | |
| S5 | `A[] forall (b)(t) upCnt_bt[b][t] <= 1` | 포대당 위협당 ≤1발 (단발) | best_u_b의 `upCnt_bt==0` 가드 |
| S6 | `A[] forall (b)(t) loCnt_bt[b][t] <= 1` | 하층 동일 | |
| S7 | `A[] killed + leaked <= MAXT` | 이중계수 없음 | Threat Killed/Leaked terminal 한 번만 |

### 7.2 Geometry (A[], 2개)
| ID | 쿼리 | 의미 |
|---|---|---|
| RD1 | `A[] forall (b)(t) upCnt_bt[b][t] > 0 imply engU_b[t][b]` | **윈도우 밖 발사 0건** (사거리·고도 게이트 일관성) |
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
| R2 | `E<> (inflU_b[0] > 0 && inflU_b[1] > 0)` | 상층 두 포대 동시 가동 |
| R3 | `E<> (inflL_b[0] > 0 && inflL_b[1] > 0)` | 하층 두 포대 동시 가동 |
| R4 | `E<> (any_uCover(0) && any_lCover(0))` | 위협 0 **다층 요격** 도달 |
| R5 | `E<> leaked > 0` | 누설 도달 |

### 7.6 v5 전용 (3개)
| ID | 쿼리 | 의미 |
|---|---|---|
| E1 | `A[] (P.Tick or P.Decide)` | Planner는 두 위치 중 하나에 (sanity) |
| E2 | `A[] (P.Decide imply 0 <= P.ds <= NB_U+NB_L)` | decision-step 유효 범위 |
| E3 | `E<> (shots_u_fired > 0 && shots_l_fired > 0)` | 양 계층이 실제 명령 받음 |

---

## 8. MSC 읽는 법 + 흔히 헷갈리는 동작

### 8.1 MSC 기본 기호

| 기호 | 의미 |
|---|---|
| 세로 막대 (lifeline) | 인스턴스 1개. 위→아래 = 시간 진행 |
| 박스 | 현재 location |
| 가로 빨간 화살표 | 채널 발사 + 수신. 양쪽 모두 같은 시점 전이 |
| 옅은 회색 박스 (Decide) | committed 위치. 시간 진행 없이 즉시 다음 |
| 박스 사이 빈 공간 | 시간 진행 |
| 화살표 없는 박스 전이 | guard만으로 발화한 internal transition (예: Planner의 ds++) |

Symbolic Simulator는 상대 순서만, Concrete Simulator는 변수 패널에 `R0.t = 6.0`,
`P.cp = 1.4` 같은 실수값 표시.

### 8.2 흔히 헷갈리는 동작

#### (1) "Planner Decide 박스가 한 cycle에 여러 번 그려지는데?"
committed 위치에서 self-loop가 NB_U + NB_L번 발화하므로 Decide 박스가 그만큼
연속 표시. 모두 같은 절대 시각 (시간 진행 0).

#### (2) "왜 모든 Slot이 동시에 활성화 안 되나?"
v5는 handshake `assign_u[b][t]!` → 정확히 1 Slot이 매칭. v3/v4의 broadcast `plan!`
처럼 6 Slot 동시 활성은 없음. MSC가 훨씬 깔끔.

#### (3) "Threat 종결 후 Slot이 fire한 hit를 누가 받나?"
broadcast라 receiver 0명도 OK. Threat이 Killed라 안 받지만 Slot은 자원 정리 `--`
수행 후 Idle로. 모델에 deadlock 없음.

---

## 9. ROS2 시뮬레이터 ↔ UPPAAL v5 매핑

| ROS2 (`dwta_nodes/`) | UPPAAL v5 |
|---|---|
| `surveillance_radar_node` /events: DETECTED | `Radar(id) detect[id]!` |
| `engageability_node` 상층 cell 열림 (포대 b) | `Radar(id) enterU<b>[id]!` |
| `engageability_node` 상층 cell 닫힘 | `Radar(id) exitU<b>[id]!` |
| 하층 동일 | `enterL<b>` / `exitL<b>` |
| `planning_node._tick()` 진입 | `P.Tick → P.Decide` |
| `WTABackend.solve()` 호출 | Planner의 Decide self-loop 4개 |
| Assignment(L1_LSAM, T0) 1행 | `assign_u[0][0]!` 1 fire |
| `LauncherNode._on_plan` 자기 명령 발사 | `Slot_U(batt_id).Idle → Flying` |
| `FireControlRadarNode.resolve` INTERCEPT | `Slot_U hitU[tgt]!` |
| `FireControlRadarNode.resolve` MISS | `Slot_U missU[tgt]!` |
| `surveillance_radar_node` /events: IMPACT | `Radar(id) impact[id]!` |
| `Battery.fire_control_channels` | `CH_PER_U[b]` / `CH_PER_L[b]` |
| `Battery.available_missiles` | `ammoU_b[b]` / `ammoL_b[b]` |

⭐ **v5의 핵심 정합**: ROS2 trace의 `Assignment 리스트` ↔ UPPAAL Decide cycle의
`assign! 시퀀스` 가 1:1 대응. 누가 누구를 잡았는지 직접 trace 비교.

---

## 10. PoC 활용

### (A) GUI 시뮬레이터
```
1. UPPAAL 5 실행 → File → Open → dwta_model_v5_explicit_assign.xml
2. Symbolic Simulator 탭 → Reset → enabled transition 클릭
3. 우측 Variables: ammoU_b/inflU_b/engU_b/killed/P.ds 관찰
4. Trace 영역에 MSC 자동 누적
```

### (B) verifyta 일괄 검증
```powershell
cd c:\Users\USER\Desktop\DWTA-Optimizer
verifyta.exe -q ros2_dwta\spec\dwta_model_v5_explicit_assign.xml
```
각 쿼리에 `Formula is satisfied` 또는 `NOT satisfied` 출력.

### (C) 반례 trace 생성
```powershell
verifyta.exe -t 1 -f r1 ros2_dwta\spec\dwta_model_v5_explicit_assign.xml
# r1.xtr를 GUI File → Open Trace로 로드
```

### (D) 단축 명령
```powershell
# 시나리오 윈도우 자동 생성
python -c "import sys; sys.path.insert(0,'ros2_dwta'); from dwta_nodes.scenario import dump_uppaal_windows; print(dump_uppaal_windows(seed=42, n_threats=3))"

# XML well-formedness 점검 (라이선스 없이)
python -c "import xml.dom.minidom as m; m.parse('ros2_dwta/spec/dwta_model_v5_explicit_assign.xml'); print('OK')"
```

---

## 11. `clean_slate_optimizer.py`와 UPPAAL의 관계

**UPPAAL은 그 파이썬 코드를 호출하지 않습니다.** Python 함수, HiGHS MIP, 부동소수
계수는 UPPAAL이 못 다룹니다. 대신 그 옵티마이저가 따르는 **정책 규칙**을 추상화해서
모델에 박았습니다.

### 정책의 본질
```python
# 의사 코드
for threat in sorted(threats, key=danger, reverse=True):   # ① 우선순위
    if upper_feasible(t) and not upper_already_locked(t):  # ② 충돌 회피
        assign_upper(t)
    if lower_feasible(t) and not lower_already_locked(t):
        assign_lower(t)                                     # ③ 다층요격
```

### v5에 그대로 내장됨
- ① 우선순위: `best_u_b(b)` (작은 id = 더 위협)
- ② 충돌 회피: `upCnt_bt[b][i] == 0` 가드
- ③ 다층요격: Slot_U와 Slot_L이 독립 동작, 같은 위협 동시 cover 가능 (R4 쿼리)

### 따라오는 보장
- (S5) `upCnt_bt[b][t] <= 1` — 모든 trace에서 한 포대 한 위협 단발만
- (RD1) `upCnt_bt[b][t] > 0 ⇒ engU_b[t][b]` — 윈도우 밖 발사 0건

다른 옵티마이저(GA/MIP/Greedy)로 백엔드 교체해도 같은 정책 골격이면 v5 모델 그대로
재사용 가능.

---

## 12. UPPAAL SMC — 통계 검증과 확률·ODE

UPPAAL 5는 **SMC(Statistical Model Checker)가 통합**되어 있어 별도 설치 없이
확률·통계 분석 가능 (Verifier 탭 → Options → Statistical parameters).

### 기본 TCTL vs SMC
| 기능 | 기본 TCTL | SMC |
|---|---|---|
| 안전성 증명 | `A[] φ` | `Pr[<=T] [] φ` (T까지 항상 φ 확률) |
| 도달성 증명 | `E<> φ` | `Pr[<=T] <> φ` (T 안에 φ 도달 확률) |
| 평균/분포 | (없음) | `E[<=T; N] (max: x)` (N회 평균 최댓값) |
| trace plot | 한 trace | `simulate N [<=T] {x, y, z}` |
| 확률 분기 | 비결정 | branching edge에 `probability` weight |
| 연속 동역학 | clock slope = 1 | 위치별 다른 slope (ODE) |

### v5 + SMC 쿼리 예시
v5에 다음 쿼리들을 추가하면 통계 분석 가능:
```c
Pr[<=40] (<> killed == MAXT)                   // 전량 격추 확률
E[<=40; 200] (max: killed)                     // 평균 격추 수
E[<=40; 200] (max: shots_u_fired + shots_l_fired)  // 평균 미사일 소비
simulate 50 [<=40] {killed, leaked, inflU_b[0]}    // 50 trace plot
```

### Pk를 SMC에 표현하려면
v5는 단발/Pk 비결정이지만, hit/miss edge에 `probability` 가중치를 추가하면 양적
격추율 계산 가능:
```xml
<transition>  <!-- hit edge -->
  <label kind="probability">85</label>   <!-- Pk=0.85 -->
  ...
</transition>
<transition>  <!-- miss edge -->
  <label kind="probability">15</label>   <!-- 1-Pk -->
  ...
</transition>
```
ROS2 시뮬레이터 통계 "격추율 X%"와 SMC `Pr[<=T] (<> killed==MAXT)` 결과를 직접 비교.

### Rate of Exponential (Location 옵션)
invariant 없는 location의 머무는 시간이 지수분포 따를 때 그 rate λ. `Pr(t 후 떠남)
= 1 - e^(-λt)`. `rate=2` → 평균 0.5초. 기본 TCTL에선 무시, SMC에서만 효과.

v5에 적용한다면 Slot의 Flying invariant 빼고 `rate = 1:5` 두면 평균 5초 ± 분산.

---

## 13. 모델 한계 + state space 상한

### 13.1 의도적으로 추상화한 것
- **위협 위치/궤적**: 시간 윈도우로 환원 (사거리 + 고도 교집합)
- **Pk 확률**: hit/miss 비결정 (SMC 가중치로 양적 표현 가능 — §12)
- **MIP 정수 해**: best_u_b/best_l_b 순서로 추상
- **연속 좌표**: 사전 계산된 시간 윈도우로 변환

### 13.2 검증 가능 규모

| MAXT | NB_U+NB_L | sum(CH) | 총 인스턴스 | verifyta 시간 |
|---|---|---|---|---|
| 2 | 2 | 4 | ~10 | 초 단위 |
| **3** | **4** | **6** | **13 (현재 v5)** | **분 단위** |
| 5 | 4 | 16 | ~25 | 분~십수 분 |
| 10+ | — | — | — | timeout |

### 13.3 확장
포대별 6채널 같은 큰 capacity:
```c
const int CH_PER_U[NB_U] = {6, 4};
// System:
SU0_0 = Slot_U(0); ... SU0_5 = Slot_U(0);
SU1_0 = Slot_U(1); ... SU1_3 = Slot_U(1);
```

---

## 14. 시나리오 → 모델 자동 dump 워크플로

### 14.1 헬퍼 함수 (`scenario.py`)

#### `compute_engagement_window(spawn, battery, assets, *, max_alt_km=80.0, dt=0.05, alt_window_km=None)`
위협의 포물선 궤적을 100Hz 샘플링해서 `(d ≤ R_battery) ∧ (h ∈ alt_window_km)`을
모두 만족하는 첫·마지막 절대 시각 반환. 기본 고도: 상층 40~150 km, 하층 5~40 km.

#### `dump_uppaal_windows(seed=42, n_threats=3, *, max_alt_km=80.0) -> str`
random 시나리오의 모든 (위협, 포대) 윈도우를 UPPAAL declaration 형식으로 출력.

#### `dump_uppaal_system(NB_U, CH_PER_U, NB_L, CH_PER_L) -> str`
`CH_PER` 배열에 맞춰 Slot 인스턴스 자동 생성 + `system` 절.

### 14.2 v5 XML에 주입

1. 헬퍼 출력의 const 블록을 복사
2. v5 XML의 `<declaration>` const 부분 교체
3. `MAXT/NB_U/NB_L/CH_PER_*` 일치 확인
4. verifyta 또는 GUI로 검증

### 14.3 일관성 점검
ROS2와 UPPAAL이 같은 시나리오 const를 쓰면 trace를 직접 비교 가능.

---

## 15. Process Array — `system` 한 줄로 인스턴스 자동 생성

### 현재 (명시적 list)
```c
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0); SU1_0 = Slot_U(1);
SL0_0 = Slot_L(0); SL0_1 = Slot_L(0); SL1_0 = Slot_L(1);
system R0, R1, R2, T0, T1, T2, SU0_0, ..., SL1_0, P;
```
포대/채널이 늘면 손으로 추가.

### 대안: Free parameter (자동 enumerate)
템플릿 파라미터 타입에 도메인 명시하면 UPPAAL이 자동 enumerate.

```c
// 글로벌 declaration
const int NCH_U = 3;
const int batt_of_u[NCH_U] = {0, 0, 1};   // 슬롯 ch_id → 포대 id

// Slot_U 파라미터를 bounded int로
template Slot_U
  parameter: const int[0, NCH_U-1] ch_id;
  declaration: int batt_id = batt_of_u[ch_id];

// System: 한 줄
system Radar, Threat, Slot_U, Slot_L, Planner;
```
→ UPPAAL이 `Slot_U(0), Slot_U(1), Slot_U(2)` 자동 생성. 시나리오 변경 시 `NCH_U`
와 `batt_of_u`만 갱신.

### Trade-off
| | 명시적 list (현재 v5) | Free parameter |
|---|---|---|
| 인스턴스 추가 | 손으로 system 절 | const 배열만 |
| MSC 가독성 | `SU0_0` 명확 | `Slot_U(0).Idle` 형태 |
| 가독성 | 한눈에 | 한 번 더 찾아야 |

대규모 시나리오(20+ 인스턴스)는 free parameter가 자동화에 유리.

---

## 16. Location 다이얼로그 옵션

UPPAAL GUI에서 location을 더블클릭하면:

| 항목 | 의미 | v5에서 사용 |
|---|---|---|
| **Name** | location 이름. 쿼리에서 `P.Tick` 같이 참조 | 모든 location |
| **Invariant** | 시간 제약 (`t <= ...`) | Pre/Scan/Tick/Flying |
| **Rate of Exponential** | SMC 전용. 머무는 시간 지수분포 rate | 안 씀 (결정적 invariant 사용) |
| **Initial** | 초기 location | Pre/Inbound/Idle/Tick |
| **Urgent** | 시간 진행 금지 | 안 씀 |
| **Committed** | urgent + 우선 처리 | Decide |
| **Comments 탭** | 주석. 검증 무관 | 미사용 |
| **Test Code 탭 — On enter/exit** | UPPAAL Yggdrasil(테스트 생성 도구) hook. 일반 검증 무관 | 미사용 |

---

## 부록 A. v5 XML 파일 구조

```
<?xml ?>
<nta>
  <declaration>
    // §3.1 시스템 상수: MAXT, NB_U/L, CH_PER_*, FLYOUT_*, PERIOD_P
    // §3.2 시나리오 윈도우: APPEAR, IMPACT_AT, U_ENTER, U_EXIT, L_ENTER, L_EXIT
    // §3.3 공유 상태: ammoU_b/L_b, inflU_b/L_b, upCnt_bt, loCnt_bt,
    //                engU_b, engL_b, killed, leaked, shots_u/l_fired
    // §3.4 채널: assign_u/l (handshake), detect/cross*/impact/hit*/miss* (broadcast)
    // §3.5 함수: best_u_b, best_l_b, any_uCover, any_lCover
  </declaration>

  <template><name>Radar</name>     ... (§4.1)
  <template><name>Threat</name>    ... (§4.2)
  <template><name>Slot_U</name>    ... (§4.3)
  <template><name>Slot_L</name>    ... (§4.4)
  <template><name>Planner</name>   ... (§4.5)

  <system>
    R0/R1/R2, T0/T1/T2,
    SU0_0/SU0_1/SU1_0, SL0_0/SL0_1/SL1_0,
    P;
  </system>

  <queries>
    S1~S7 (Safety), RD1/RD2 (Geometry), T1 (Timing),
    L1 (Liveness), R1~R5 (Reachability), E1~E3 (v5 specific)
  </queries>
</nta>
```

## 부록 B. 디버깅 체크리스트

| 증상 | 어디 확인 |
|---|---|
| 모델 안 열림 | XML well-formed? `python -m xml.dom.minidom` |
| Planner가 영원히 Decide에 머묾 | Edge 6 가드 `ds == NB_U + NB_L` 확인, 각 skip edge 가드의 OR 조건 점검 |
| `assign_u[b][t]!` fire 안 됨 | Idle인 Slot_U(b) 인스턴스 존재? 또는 best_u_b(b) ≥ 0 ? |
| `best_u_b`가 항상 -1 | `engU_b`가 true로 안 들어옴 → Radar의 enter* fire 시각 확인 |
| `inflU_b` 음수 | Planner 발사 `++` 시점과 Slot 판정 `--` 시점 균형 |
| state space 폭발 | MAXT/NB/CH 줄이기 |
| T1 (`A[] P.cp <= PERIOD_P`) NOT satisfied | invariant + guard 조합 점검 |
| 다른 자동기가 시간 멈춤 | urgent edge 또는 invariant 위반 확인 |

---

추가 질문(특정 transition 의미, 새 쿼리, ROS2 trace 비교)은 §10(PoC) 또는 §9(매핑)
섹션을 출발점으로.
