# UPPAAL 모델 설계 · 구현 · 사용 — 완전 문서

이 문서 하나로 `ros2_dwta/spec/` 의 모든 UPPAAL 모델을 **읽고, 시뮬레이션하고,
검증하고, ROS2 시뮬레이터와 정합**시킬 수 있게 작성됐습니다. 모델 진화(v2→v3),
각 템플릿의 location/transition/guard, declaration의 모든 변수/함수, 19개 검증
쿼리 의미, MSC 해석, PoC 흐름까지 한 장에 정리합니다.

검증 속성의 짧은 카탈로그는 [`timed_automata.md`](./timed_automata.md), 모델
파일은 다음 세 개입니다.

| 파일 | 내용 | 인스턴스 수 |
|---|---|---|
| [`dwta_model.xml`](./dwta_model.xml) (**v2 SPEC**) | 비결정 WTA + Radar broadcaster | 11 |
| [`dwta_model_impl.xml`](./dwta_model_impl.xml) (**v2 IMPL**) | 결정적 GreedyWTA 정책 + Radar | 11 |
| [`dwta_model_v3_geometry.xml`](./dwta_model_v3_geometry.xml) (**v3**) | 궤적·고도 윈도우 + 포대별 채널 슬롯 | 13 |

---

## 0. 한 장 인덱스

| § | 내용 |
|---|---|
| 1 | 모델 진화 (v1→v2→v3) |
| 2 | v3 모델 전체 구성 (템플릿/인스턴스/채널 한눈에) |
| 3 | Declaration 상세 (글로벌·로컬·시스템·함수) |
| 4 | 템플릿별 구현 상세 (Radar / Threat / Slot_U / Slot_L / Planner) |
| 5 | Broadcast 채널 전체 사양 |
| 6 | 한 위협의 lifecycle (v3 기준 단계별) |
| 7 | v2 vs v3 차이점 |
| 8 | 검증 쿼리 19개 상세 |
| 9 | MSC 읽는 법 + 흔히 헷갈리는 동작 |
| 10 | ROS2 시뮬레이터 ↔ UPPAAL 매핑 |
| 11 | PoC 활용 (GUI / verifyta / 헬퍼) |
| 12 | clean_slate_optimizer 와의 관계 |
| 13 | 모델 한계 + state space 상한 |
| 14 | 시나리오 → 모델 자동 dump 워크플로 |

---

## 1. 모델 진화 (v1 → v2 → v3)

### v1 (초기, 폐기)
- 위협이 자체 클럭 `x`를 가지고 `x>=ENTER`로 자동 교전대 진입.
- 위협별 timing 다양성 표현 불가, Radar 컴포넌트 없음.

### v2 (`dwta_model.xml`, `dwta_model_impl.xml`)
- **Radar 템플릿 신규** — 위협별 timing(`APPEAR/CROSS_U/CROSS_L/IMPACT_AT`)을
  소유하고 broadcast로 전 컴포넌트에 전파.
- **Threat이 signal-driven** — clock 제거, broadcast 신호로만 lifecycle 진행.
- **SPEC vs IMPL 분리**:
  - SPEC: Interceptor의 발사 대상이 비결정 `select t`
  - IMPL: `best_u()/best_l()` 함수로 결정적 GreedyWTA 정책 모델링
- **v2 한계**: 위협당 교전대 시점이 **한 점**(`ENTER_U`)으로 압축됨 → 고도/사거리
  윈도우의 시간 진폭, 포대별 사거리 차이 표현 못 함. 포대도 단일 풀(`CH_U`).

### v3 (`dwta_model_v3_geometry.xml`)
v2가 한 점으로 압축했던 두 가지를 풀어 헤친 모델.

| 항목 | v2 | v3 |
|---|---|---|
| 교전대 표현 | 시간 한 점 `ENTER_U[id]` | **시간 윈도우** `[U_ENTER[id][b], U_EXIT[id][b]]` |
| 사거리·고도 | 모델 밖, 시간으로 환원 | **(사거리 ∧ 고도)** 교집합을 ROS2에서 사전 계산해 윈도우 const로 주입 |
| 포대 표현 | 인스턴스 풀(`CH_U=2`) | **포대별 분리** (`NB_U=2`, `CH_PER_U[b]={2,1}`), 인스턴스 = 포대당 채널 수 |
| 잔여탄/비행중 | 단일 `ammoU`, `inflU` | **포대별 배열** `ammoU_b[b]`, `inflU_b[b]` |
| 충돌-자유 | `upCnt[t]<=1` | **`upCnt_bt[b][t]<=1`** (포대 단위) |
| 윈도우 enter/exit | 없음 | **`enterU0/exitU0/enterU1/exitU1`** 등 8종 broadcast |
| 검증 쿼리 수 | 16 (SPEC), 18 (IMPL) | **19** (v3) |
| 인스턴스 수 | 11 | 13 |

이 문서의 본문은 **v3 기준**으로 쓰여 있고, v2 차이는 §7과 각 섹션의 "v2 동등물"에서
함께 짚습니다.

---

## 2. v3 모델 전체 구성 (한 장 view)

```
┌──────────────── 시간 권위 ────────────────┐    ┌────── 결심 ──────┐    ┌──────── 실행 ────────┐
│  Radar(0)         Radar(1)      Radar(2)  │    │    Planner       │    │  Slot_U × 3 (상층)    │
│   detect[0]!       detect[1]!    detect[2]!│    │       plan!      │    │  Slot_L × 3 (하층)    │
│   enterU0/1[i]!    exitU0/1[i]!            │    │   (PERIOD_P=2)   │    │   (Idle/Ready/Flying) │
│   enterL0/1[i]!    exitL0/1[i]!            │    │                  │    │   ammoU_b/inflU_b     │
│   impact[i]!                               │    │                  │    │   upCnt_bt 갱신       │
└────────────────────┬───────────────────────┘    └────────┬─────────┘    └───────┬───────────────┘
                     │ broadcast                            │ broadcast            │ hitU/L! / missU/L! (broadcast)
                     ▼                                      ▼                      ▼
                  Threat(0/1/2)  ◄────────────── plan? (단순 listening 아님; 직접 갱신 없음) ─────────┐
                  Inbound → Tracked                                                                  │
                            ↑                                                                        │
                     engU_b[id][b], engL_b[id][b]  ◄── enter/exit                                    │
                            ↓ (hitU/L? 또는 impact?)                                                 │
                          Killed / Leaked  ─────────────────────────────────────────────────────────┘
```

### 13개 인스턴스 (System declarations)

```c
// 위협별 Radar + Threat (MAXT=3)
R0 = Radar(0); R1 = Radar(1); R2 = Radar(2);
T0 = Threat(0); T1 = Threat(1); T2 = Threat(2);

// 상층: CH_PER_U = {2, 1} -> 상층 포대 0번이 2 채널, 1번이 1 채널
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0);     // L1_LSAM의 채널 0, 1
SU1_0 = Slot_U(1);                         // L2_LSAM의 채널 0

// 하층: CH_PER_L = {2, 1}
SL0_0 = Slot_L(0); SL0_1 = Slot_L(0);     // M1_MSAM의 채널 0, 1
SL1_0 = Slot_L(1);                         // M2_MSAM의 채널 0

P = Planner();

system R0, R1, R2,
       T0, T1, T2,
       SU0_0, SU0_1, SU1_0,
       SL0_0, SL0_1, SL1_0,
       P;
```

MSC에 세로줄로 그려지는 lifeline 정확히 이 13개.

### 5개 템플릿 요약

| Template | parameter | local clock | local var | 인스턴스 수 |
|---|---|---|---|---|
| `Radar` | `const int id` | `clock t` | — | MAXT (3) |
| `Threat` | `const int id` | — | — | MAXT (3) |
| `Slot_U` | `const int batt_id` | `clock f` | `int tgt` | sum(CH_PER_U) (3) |
| `Slot_L` | `const int batt_id` | `clock f` | `int tgt` | sum(CH_PER_L) (3) |
| `Planner` | — | `clock cp` | — | 1 |

---

## 3. Declaration 상세 — "어디에 무엇이 있고 누가 쓰나"

UPPAAL의 declaration은 4 곳에 분산됩니다:
1. **Global** — 모든 인스턴스가 공유. `<nta><declaration>...</declaration>`.
2. **Template-local** — 각 인스턴스가 자기 사본을 가짐. `<template><declaration>`.
3. **System declarations** — 인스턴스화 + `system ... ;`.
4. **Queries** — 검증식. `<queries>`.

UPPAAL GUI 좌측 트리에서:
```
Project
├── Declarations           ← (1) 글로벌
├── Radar
│   ├── Declarations       ← (2) Radar 로컬: clock t
│   └── (graph)
├── Threat
│   ├── Declarations       ← (2) Threat 로컬: 비어있음
│   └── (graph)
├── Slot_U
│   ├── Declarations       ← (2) Slot_U 로컬: clock f; int tgt
│   └── (graph)
├── Slot_L  (동일)
├── Planner
│   ├── Declarations       ← (2) clock cp
│   └── (graph)
└── System declarations    ← (3) 인스턴스화 + system
```

### 3.1 글로벌 declaration의 모든 항목 (v3)

#### (a) 시스템 상수 — 컴파일 타임 고정값
```c
const int MAXT     = 3;     // 위협 수 (모든 배열의 첫 차원)
const int NB_U     = 2;     // 상층 포대 수
const int NB_L     = 2;     // 하층 포대 수
const int CH_PER_U[NB_U] = {2, 1};  // 포대 b의 동시 교전 채널 수 (상층)
const int CH_PER_L[NB_L] = {2, 1};
const int FLYOUT_U = 5;     // 상층 요격탄 비행시간 (초)
const int FLYOUT_L = 2;     // 하층 요격탄 비행시간
const int PERIOD_P = 2;     // 계획수립 주기
```
**누가 쓰나**:
- `MAXT`: 모든 배열 차원, `int[0,MAXT-1]` select range
- `NB_U/NB_L`: 채널 풀 배열 차원, `forall (b : int[0,NB_U-1])` 쿼리
- `CH_PER_U[b]`: Slot_U의 발사 가드 (`inflU_b[batt_id] < CH_PER_U[batt_id]`)
- `FLYOUT_*`: Slot의 Flying invariant + 판정 가드 `f >= FLYOUT_U`
- `PERIOD_P`: Planner의 invariant `cp <= PERIOD_P` + 가드 `cp >= PERIOD_P`

#### (b) 시나리오 윈도우 — 위협별 / (위협, 포대)별 timing
```c
const int APPEAR[MAXT]        = { 0,  3,  6};       // 위협 탐지 시각
const int IMPACT_AT[MAXT]     = {30, 32, 35};       // 위협 탄착 시각
const int U_ENTER[MAXT][NB_U] = { { 8, 9}, {11,12}, {14,15} };  // 상층 포대 b의 교전대 진입
const int U_EXIT [MAXT][NB_U] = { {22,21}, {24,23}, {26,25} };  // 상층 포대 b의 교전대 이탈
const int L_ENTER[MAXT][NB_L] = { {16,17}, {19,18}, {20,21} };  // 하층 동일
const int L_EXIT [MAXT][NB_L] = { {28,27}, {30,29}, {33,31} };
```
**의미**: 위협 `t`가 포대 `b`(상층 또는 하층)의 사거리 + 고도 게이트를 모두 만족하는
시간 구간이 `[ENTER[t][b], EXIT[t][b]]`. ROS2 `scenario.dump_uppaal_windows()`가
궤적 시뮬레이션으로 사전 계산해 dump.

**누가 쓰나**: 오직 `Radar` 템플릿의 self-loop 가드(`t == U_ENTER[id][0]` 등).
다른 인스턴스는 const를 직접 보지 않고 broadcast 신호로만 통신.

#### (c) 공유 상태 — 인스턴스 간 동기화 매개체
```c
int  ammoU_b[NB_U]    = {3, 2};    // 포대 b 잔여탄 (상층)
int  ammoL_b[NB_L]    = {3, 2};
int  inflU_b[NB_U];                // 포대 b 비행중 요격탄 수 (초기 0)
int  inflL_b[NB_L];
int  upCnt_bt[NB_U][MAXT];         // (포대 b, 위협 t) 동시 교전 카운터
int  loCnt_bt[NB_L][MAXT];
bool engU_b[MAXT][NB_U];           // 위협 t가 포대 b(상층)의 윈도우 안인가
bool engL_b[MAXT][NB_L];
int  killed = 0, leaked = 0;       // 종결 누계
```
**누가 갱신하나**:
| 변수 | 쓰기 | 읽기 |
|---|---|---|
| `ammoU_b[b]` | Slot_U(b) 발사 시 `--` | Slot_U 가드, S2u 쿼리 |
| `inflU_b[b]` | Slot_U(b) 발사 시 `++`, 판정 시 `--` | Slot_U 가드, S3 쿼리 |
| `upCnt_bt[b][t]` | Slot_U(b) 발사/판정 시 `++/--` | Slot_U 가드, best_u_b() 함수, S5/S7 쿼리 |
| `engU_b[t][b]` | Threat의 enter*/exit* 토글 + 종결 시 false | Slot_U 가드, RD1 쿼리 |
| `killed` | Threat의 hit 전이 `++` | L1/R1 쿼리 |
| `leaked` | Threat의 impact 전이 `++` | R6 쿼리 |

#### (d) Broadcast 채널 — 인스턴스 간 통신
```c
broadcast chan plan;                       // Planner -> 모든 Slot
broadcast chan detect[MAXT];               // Radar(i) -> Threat(i)
broadcast chan impact[MAXT];               // Radar(i) -> Threat(i)
broadcast chan enterU0[MAXT], exitU0[MAXT]; // Radar(i)의 상층 포대 0 윈도우
broadcast chan enterU1[MAXT], exitU1[MAXT]; // 상층 포대 1
broadcast chan enterL0[MAXT], exitL0[MAXT]; // 하층 포대 0
broadcast chan enterL1[MAXT], exitL1[MAXT]; // 하층 포대 1
broadcast chan hitU[MAXT], missU[MAXT];    // Slot_U -> Threat(tgt)
broadcast chan hitL[MAXT], missL[MAXT];    // Slot_L -> Threat(tgt)
```
**왜 broadcast인가**: 한 `Radar(0).enterU0[0]!`가 발사되면 listening 중인 모든
인스턴스가 동시 수신. `Threat(0)`가 받아 `engU_b[0][0]=true`로 토글, 다른 Slot은
수신 안 함(noop). receiver 0명이어도 발사 가능 → 모델이 deadlock 없음.

**§11/§12 패턴 차이**: 패턴 설명에서는 `enterU[MAXT][NB_U]` 2차원 chan을 썼지만,
실제 구현은 호환성을 위해 `enterU0/enterU1` 1차원 4종으로 풀어 씀.

#### (e) 함수 — 정책 추상화
```c
int best_u_b(int b) {       // 포대 b의 GreedyWTA 우선순위 (작은 id가 더 위협)
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] == 0) return i;
        i++;
    }
    return -1;              // 발사 가능 위협 없음
}
int best_l_b(int b) { ... } // 하층 동일

bool any_uCover(int t) { return upCnt_bt[0][t] + upCnt_bt[1][t] > 0; }
bool any_lCover(int t) { return loCnt_bt[0][t] + loCnt_bt[1][t] > 0; }
bool any_engU(int t)   { return engU_b[t][0] || engU_b[t][1]; }
bool any_engL(int t)   { return engL_b[t][0] || engL_b[t][1]; }
```
**누가 호출하나**:
- `best_u_b(batt_id)`: Slot_U의 `Ready → Flying` 가드. 매 발사 결심마다 호출되어
  현재 시점에서 가장 위협적이면서 그 포대로 아직 안 잡은 위협의 id를 반환.
- `any_uCover(t)` / `any_lCover(t)` / `any_engU(t)` / `any_engL(t)`: 검증 쿼리
  `R4: E<> (any_uCover(0) && any_lCover(0))` 같은 곳에서 사용.

### 3.2 Template-local declarations

| Template | local | 의미 |
|---|---|---|
| `Radar` | `clock t;` | 인스턴스마다 0부터 시작하는 절대 시각. APPEAR/IMPACT_AT 가드의 기준. |
| `Threat` | (없음) | 순수 signal-driven |
| `Slot_U` | `clock f; int tgt;` | `f` = 비행 시간 클럭. `tgt` = 발사 시 select한 위협 id (Flying에서 판정 시 사용) |
| `Slot_L` | `clock f; int tgt;` | 동일 |
| `Planner` | `clock cp;` | 계획수립 주기 클럭 |

> Local clock은 인스턴스마다 별개입니다. `R0.t`와 `R1.t`는 완전히 독립.

### 3.3 System declarations

위 §2의 13 인스턴스 + `system ...;` 행. `Slot_U(0)` 처럼 같은 batt_id로 인스턴스 두
개를 만들면 둘이 같은 `ammoU_b[0]` / `inflU_b[0]` 자원을 공유하는 두 채널이 됩니다.

---

## 4. 템플릿별 구현 상세

각 템플릿의 location, transition, guard/assignment를 한 줄씩 설명합니다.

### 4.1 Radar(const int id) — 위협 타이밍의 권위자

**Local**: `clock t;` (0초부터 시작)

**Locations** (3개):
- `Pre` — invariant `t <= APPEAR[id]` (탐지 전 대기. 클럭이 APPEAR 넘으면 안 됨)
- `Scan` — invariant `t <= IMPACT_AT[id]` (탐지 후 활성 추적 구간)
- `Done` — terminal (탄착 후. 더 이상 전이 없음)

**Transitions** (10개):

| # | from → to | guard | sync | assignment | 의미 |
|---|---|---|---|---|---|
| 1 | Pre → Scan | `t == APPEAR[id]` | `detect[id]!` | — | 탐지: 위협 등장 |
| 2 | Scan → Scan | `t == U_ENTER[id][0]` | `enterU0[id]!` | — | 상층 포대 0 사거리·고도 진입 |
| 3 | Scan → Scan | `t == U_EXIT[id][0]` | `exitU0[id]!` | — | 상층 포대 0 윈도우 이탈 |
| 4 | Scan → Scan | `t == U_ENTER[id][1]` | `enterU1[id]!` | — | 상층 포대 1 진입 |
| 5 | Scan → Scan | `t == U_EXIT[id][1]` | `exitU1[id]!` | — | 상층 포대 1 이탈 |
| 6 | Scan → Scan | `t == L_ENTER[id][0]` | `enterL0[id]!` | — | 하층 포대 0 진입 |
| 7 | Scan → Scan | `t == L_EXIT[id][0]` | `exitL0[id]!` | — | 하층 포대 0 이탈 |
| 8 | Scan → Scan | `t == L_ENTER[id][1]` | `enterL1[id]!` | — | 하층 포대 1 진입 |
| 9 | Scan → Scan | `t == L_EXIT[id][1]` | `exitL1[id]!` | — | 하층 포대 1 이탈 |
| 10 | Scan → Done | `t == IMPACT_AT[id]` | `impact[id]!` | — | 탄착 |

**작동 원리**:
- `t == X` 가드와 `t <= X` invariant의 조합으로 **정확히 X 시각에 발사 강제**.
  invariant가 시간 진행을 막고, 가드가 그 시점에 fire하게 함.
- 2~9번 self-loop는 위치를 안 바꿔도 broadcast를 발사할 수 있도록 self-edge로
  설계. 위협별로 8개 enter/exit 시각이 모두 distinct하다는 가정 (시나리오 생성
  시 충돌 방지).
- `Done`은 더 이상 전이 없는 sink. impact가 발사된 후엔 Radar 인스턴스가 영원히
  Done에 머묾.

**v2 동등물**: v2는 `crossU[id]!`, `crossL[id]!` 두 가지만 있었고 enter만 표현
(exit 없음). v3는 enter/exit 8종으로 확장.

### 4.2 Threat(const int id) — 신호 소비자

**Local**: 없음 (clock 없음, 변수 없음 — 순수 signal-driven)

**Locations** (4개):
- `Inbound` — 초기. 탐지 전 대기
- `Tracked` — 탐지 후 활성 (사거리/고도 진입/이탈은 self-loop)
- `Killed` — terminal (격추)
- `Leaked` — terminal (탄착)

**Transitions** (13개):

| # | from → to | sync | assignment | 의미 |
|---|---|---|---|---|
| 1 | Inbound → Tracked | `detect[id]?` | — | Radar의 탐지 수신 |
| 2 | Tracked → Tracked | `enterU0[id]?` | `engU_b[id][0]=true` | 상층 포대 0 윈도우 진입 |
| 3 | Tracked → Tracked | `exitU0[id]?` | `engU_b[id][0]=false` | 상층 포대 0 윈도우 이탈 |
| 4 | Tracked → Tracked | `enterU1[id]?` | `engU_b[id][1]=true` | 상층 포대 1 진입 |
| 5 | Tracked → Tracked | `exitU1[id]?` | `engU_b[id][1]=false` | 상층 포대 1 이탈 |
| 6 | Tracked → Tracked | `enterL0[id]?` | `engL_b[id][0]=true` | 하층 포대 0 진입 |
| 7 | Tracked → Tracked | `exitL0[id]?` | `engL_b[id][0]=false` | 하층 포대 0 이탈 |
| 8 | Tracked → Tracked | `enterL1[id]?` | `engL_b[id][1]=true` | 하층 포대 1 진입 |
| 9 | Tracked → Tracked | `exitL1[id]?` | `engL_b[id][1]=false` | 하층 포대 1 이탈 |
| 10 | Tracked → Tracked | `missU[id]?` | — | 상층 요격탄 빗나감 (lifeline 유지) |
| 11 | Tracked → Tracked | `missL[id]?` | — | 하층 요격탄 빗나감 |
| 12 | Tracked → Killed | `hitU[id]?` | `engU_b[id][0]=false, engU_b[id][1]=false, engL_b[id][0]=false, engL_b[id][1]=false, killed++` | 상층 격추 |
| 13 | Tracked → Killed | `hitL[id]?` | (같음) | 하층 격추 |
| 14 | Inbound → Leaked | `impact[id]?` | `leaked++` | 탐지 전 탄착 (드물지만 가능) |
| 15 | Tracked → Leaked | `impact[id]?` | (engU/engL 모두 false, leaked++) | 탐지 후 탄착 |

**작동 원리**:
- Threat 자체는 어떤 시간 추론도 안 함. `t == ...` 가드 없음.
- 모든 상태 변화는 broadcast 수신(`?`)으로만 발생.
- 종결 시(`Killed`/`Leaked`) `engU_b/engL_b`를 모두 false로 초기화 → Slot이
  종결된 위협에 발사 결심하지 않음.

**v2 동등물**: v2는 위치가 더 많았고(`Inbound/UpperEng/BothEng/Killed/Leaked`)
self-loop 대신 위치 전이로 표현. v3는 윈도우 토글이 잦아 self-loop가 자연.

### 4.3 Slot_U(const int batt_id) — 상층 채널 슬롯

**Local**: `clock f; int tgt;`

**Locations** (3개):
- `Idle` — 발사 대기
- `Ready` — committed (계획수립 신호 받은 직후. 즉시 다음 전이)
- `Flying` — invariant `f <= FLYOUT_U` (요격탄 비행 중)

**Transitions** (5개):

| # | from → to | select | guard | sync | assignment | 의미 |
|---|---|---|---|---|---|---|
| 1 | Idle → Ready | — | — | `plan?` | — | 계획수립 신호 수신 |
| 2 | Ready → Flying | `t : int[0,MAXT-1]` | `ammoU_b[batt_id]>0 && inflU_b[batt_id]<CH_PER_U[batt_id] && best_u_b(batt_id)>=0 && t==best_u_b(batt_id)` | — | `ammoU_b[batt_id]--, inflU_b[batt_id]++, upCnt_bt[batt_id][t]++, tgt=t, f=0` | **발사**: GreedyWTA 우선순위 위협(`best_u_b`)에 사격 |
| 3 | Ready → Idle | — | `best_u_b(batt_id)<0 \|\| ammoU_b[batt_id]==0 \|\| inflU_b[batt_id]>=CH_PER_U[batt_id]` | — | — | **skip**: 발사 조건 미충족 |
| 4 | Flying → Idle | — | `f >= FLYOUT_U` | `hitU[tgt]!` | `inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--` | 요격 성공 (양보) |
| 5 | Flying → Idle | — | `f >= FLYOUT_U` | `missU[tgt]!` | (같음) | 요격 실패 |

**작동 원리 — 핵심 4가지**:

1. **committed Ready**: `plan?`을 수신하면 Ready로 가는데 committed라서 시간이
   흐를 수 없음. 반드시 전이 2(발사) 또는 전이 3(skip)이 **즉시** 발화.
2. **결정적 발사 (GreedyWTA)**: `t==best_u_b(batt_id)` 가드가 select range를 단
   하나의 t로 고정. v2 IMPL과 같은 결정성. SPEC 모델이 필요하면 이 가드를
   `engU_b[t][batt_id] && upCnt_bt[batt_id][t]==0`로 바꾸면 비결정.
3. **포대별 자원 분리**: 모든 mutation이 `[batt_id]`로 indexed → 다른 포대의
   채널과 자원 충돌 없음.
4. **격추/실패 둘 다 비결정 발화**: Flying에서 `f >= FLYOUT_U` 가드만 동일.
   verifyta가 두 경로를 모두 탐색하므로 Pk 확률을 추상화한 채 양쪽 시나리오
   모두 검증.

### 4.4 Slot_L(const int batt_id) — 하층 채널 슬롯

Slot_U와 구조 100% 동일. 변수만 `ammoL_b/inflL_b/loCnt_bt/best_l_b/FLYOUT_L`로
대체. broadcast도 `hitL/missL`.

### 4.5 Planner — 계획수립 주기

**Local**: `clock cp;`

**Locations** (1개):
- `Tick` — invariant `cp <= PERIOD_P`

**Transitions** (1개):

| # | from → to | guard | sync | assignment | 의미 |
|---|---|---|---|---|---|
| 1 | Tick → Tick | `cp >= PERIOD_P` | `plan!` | `cp = 0` | 주기마다 계획수립 broadcast 후 클럭 리셋 |

**작동 원리**: invariant + 가드 결합으로 정확히 `PERIOD_P`마다 fire 강제. Slot
6개(상층 3 + 하층 3)가 동시에 `plan?`을 수신.

---

## 5. Broadcast 채널 전체 사양

| 채널 | sender | receivers | 의미 |
|---|---|---|---|
| `plan` | Planner | SU0_0, SU0_1, SU1_0, SL0_0, SL0_1, SL1_0 (6개) | 계획수립 주기 |
| `detect[i]` | Radar(i) | Threat(i) | 탐지 |
| `enterU0[i]` | Radar(i) | Threat(i) | 위협 i가 상층 포대 0 윈도우 진입 |
| `exitU0[i]` | Radar(i) | Threat(i) | 위협 i가 상층 포대 0 윈도우 이탈 |
| `enterU1[i]` | Radar(i) | Threat(i) | 상층 포대 1 진입 |
| `exitU1[i]` | Radar(i) | Threat(i) | 상층 포대 1 이탈 |
| `enterL0[i]` | Radar(i) | Threat(i) | 하층 포대 0 진입 |
| `exitL0[i]` | Radar(i) | Threat(i) | 하층 포대 0 이탈 |
| `enterL1[i]` | Radar(i) | Threat(i) | 하층 포대 1 진입 |
| `exitL1[i]` | Radar(i) | Threat(i) | 하층 포대 1 이탈 |
| `impact[i]` | Radar(i) | Threat(i) | 탄착 |
| `hitU[t]` | Slot_U (어느 batt_id든) | Threat(t) | 상층 요격 성공 |
| `missU[t]` | Slot_U | Threat(t) | 상층 요격 실패 |
| `hitL[t]` | Slot_L | Threat(t) | 하층 요격 성공 |
| `missL[t]` | Slot_L | Threat(t) | 하층 요격 실패 |

**총 broadcast 종류**: `plan` 단일 + 8종 × MAXT + 4종(hit/miss × U/L) × MAXT.
MAXT=3이면 `1 + 8*3 + 4*3 = 37 chan slot`. 모두 listening 가능한 인스턴스 자동 fan-out.

**MSC 화살표**: 매 broadcast가 한 가로 화살표. receiver가 다수면 같은 시점에
여러 lifeline으로 동시 도달 (예: `plan!`은 6개 Slot으로).

---

## 6. 한 위협의 lifecycle (v3 기준 단계별)

위협 0이 t=0에 발사되어 격추까지 가는 가장 일반적 흐름. 시간 축은 위→아래.

```
t=0  R0:Pre[t=0]      T0:Inbound       Slots:Idle      P:Tick[cp=0]
     ────  R0.t reaches APPEAR[0]=0 immediately  ────
     R0 fires detect[0]! 
              ─────────────►  T0: Inbound → Tracked
     R0: Pre → Scan[t=0]

t=2  ─── P.cp reaches 2 ───
     P fires plan! ──────────► 6 Slots: Idle → Ready (committed)
        Slots 각자 best_u_b(batt_id) 호출:
          - engU_b[0][0]=false → best_u_b(0) = -1
          - skip 전이 (트랜지션 3) 발화
        6 Slots: Ready → Idle (즉시, 시간 진행 없음)
     P: Tick[cp=0] (리셋)

t=4  P가 다시 plan! 발사. 동일하게 모두 skip.

t=8  ─── R0.t reaches U_ENTER[0][0]=8 ───
     R0 fires enterU0[0]! ──► T0: engU_b[0][0]=true
     (T0 위치는 변하지 않음. self-loop)

t=9  ─── R0.t reaches U_ENTER[0][1]=9 ───
     R0 fires enterU1[0]! ──► T0: engU_b[0][1]=true

t=10 ─── P.cp reaches 2 다시 ───
     P fires plan! ──────────► 6 Slots: Idle → Ready
        SU0_0(batt_id=0): best_u_b(0)=0 (engU_b[0][0]=true, upCnt_bt[0][0]=0)
                          가드 만족: ammoU_b[0]=3>0, inflU_b[0]=0<CH_PER_U[0]=2
                          ammoU_b[0]=2, inflU_b[0]=1, upCnt_bt[0][0]=1, tgt=0, f=0
                          SU0_0: Ready → Flying[f=0]
        SU0_1(batt_id=0): best_u_b(0) 호출 시 upCnt_bt[0][0]=1 → return -1
                          (이미 같은 포대가 잡았으니 다음 위협 봐야)
                          best_u_b(0)에서 if (engU_b[i][b] && upCnt_bt[b][i] == 0)
                          위협 0은 cnt 1이라 skip, 위협 1은 engU_b[1][0]=false, ...
                          → -1 → skip 전이로 Idle
        SU1_0(batt_id=1): best_u_b(1) = 0 (engU_b[0][1]=true, upCnt_bt[1][0]=0)
                          발사: ammoU_b[1]=2→1, inflU_b[1]=0→1, upCnt_bt[1][0]=1
                          SU1_0: Ready → Flying

t=15 ─── SU0_0.f reaches FLYOUT_U=5 (발사 후 5초) ───
     SU0_0 fires hitU[0]! ──► T0: Tracked → Killed
                              engU_b[0][0]=false, engU_b[0][1]=false,
                              engL_b[0][0]=false, engL_b[0][1]=false, killed=1
                              (다른 Slot의 engU 등은 영향 X. 위 4개만 reset)
     SU0_0: inflU_b[0]=0, upCnt_bt[0][0]=0, Flying → Idle
     
     동시: SU1_0.f가 마침 5 도달 → hitU[0]! 또는 missU[0]! fire
        T0는 이미 Killed라 더 받지 않지만 SU1_0의 카운터는 정리됨:
        inflU_b[1]=0, upCnt_bt[1][0]=0
        broadcast는 0 receiver여도 OK.

t=30 ─── R0.t reaches IMPACT_AT[0]=30 ───
     R0 fires impact[0]! ──► T0는 Killed라 받지 않음 (Killed는 sink)
     R0: Scan → Done
```

**6가지 핵심 포인트**:
1. 위협이 시간을 모름. Radar의 broadcast가 모든 상태 변화의 트리거.
2. plan은 매 PERIOD_P=2초마다 발사되지만 발사 조건 미충족 시 모두 skip.
3. 같은 포대의 두 채널이 같은 위협을 노릴 수 없음 (`best_u_b` 자체가 cnt==0인
   위협만 반환).
4. 다른 포대는 같은 위협을 노릴 수 있음 (포대별 cnt가 별개).
5. broadcast hit/miss는 0 receiver여도 OK → Slot이 종결된 위협에 대해 fire해도
   model이 안 막힘.
6. `f == FLYOUT_U` 가드 만족 시 hit/miss는 비결정 → 양쪽 trace 다 탐색.

---

## 7. v2 vs v3 차이점 — 한 표로

| 항목 | v2 SPEC/IMPL | v3 |
|---|---|---|
| **위협 진입 표현** | `crossU[id]!` 한 번 발사 → engU[id]=true 영원 | `enterU0[id]!`/`exitU0[id]!` 등 4종 × 2포대 = 8 broadcast로 (위협,포대)별 토글 |
| **Threat 위치** | Inbound/UpperEng/BothEng/Killed/Leaked (5개) | Inbound/Tracked/Killed/Leaked (4개) — 윈도우는 self-loop로 표현 |
| **포대 자원** | 단일 `ammoU`, `inflU` | 포대별 `ammoU_b[NB_U]`, `inflU_b[NB_U]` |
| **충돌 회피 카운터** | `upCnt[t]` (1D) | `upCnt_bt[b][t]` (2D, 포대 단위) |
| **Interceptor 인스턴스** | `InterceptorU × CH_U` (단일 풀) | `Slot_U(b) × CH_PER_U[b]` for each b ∈ NB_U |
| **best 함수** | `best_u()`, `best_l()` (글로벌) | `best_u_b(b)`, `best_l_b(b)` (포대 단위) |
| **시간 const 표현** | `ENTER_U[MAXT]` 1D | `U_ENTER[MAXT][NB_U]`, `U_EXIT[MAXT][NB_U]` 2D |
| **검증 쿼리 수** | 16 (SPEC) / 18 (IMPL) | 19 |
| **새 쿼리 (v3 only)** | — | S3/S4 포대별 채널, S7 위협당 포대 수, RD1/RD2 윈도우 일관성, R2/R3/R5 포대 동시/만탱크 |
| **표현 가능한 게임플레이** | 위협 1발이 사거리 진입 후 영원히 교전 가능 | 위협이 사거리 안 ↔ 밖을 오가며 다른 포대로 인계됨 |

---

## 8. 검증 쿼리 19개 상세

각 쿼리가 무엇을 보장하고 어떤 모델 요소가 그것을 만들어내는지.

### 8.1 Safety (A[], 9개)

#### S1: `A[] not deadlock`
**의미**: 어떤 reachable 상태에서도 시간 진행 또는 enabled transition이 있음.
**왜 성립하나**:
- Threat의 `Tracked`는 hitU/hitL/impact 어느 하나는 결국 도달 (모든 위협이
  `IMPACT_AT[id]`에 도달하면 impact 발사).
- Slot의 committed `Ready`는 skip 전이가 항상 enabled (가드가 `best_u_b<0 ||
  ammo==0 || infl>=CH`로 발사 가드의 정확한 negation을 포함).
- Radar의 `Pre/Scan/Done`은 시간 진행 OK (invariant 한계 안에서).

#### S2u/S2l: `A[] forall (b) ammoU_b[b] >= 0` / `ammoL_b[b] >= 0`
**의미**: 포대별 잔여탄이 음수가 되지 않음.
**왜 성립하나**: Slot 발사 가드에 `ammoU_b[batt_id] > 0` 포함. `--`는 발사 시 한
번만 실행.

#### S3: `A[] forall (b) inflU_b[b] <= CH_PER_U[b]`
**의미**: 포대 b의 비행 중 요격탄이 그 포대의 채널 수를 초과하지 않음.
**왜 성립하나**: 발사 가드에 `inflU_b[batt_id] < CH_PER_U[batt_id]`. `++`는
발사 시, `--`는 hit/miss 시 호출되어 균형.
**v3 특유**: v2는 인스턴스 수로 구조적 보장이었는데 v3는 가드로 명시 보장.

#### S4: `A[] forall (b) inflL_b[b] <= CH_PER_L[b]`
하층 동일.

#### S5: `A[] forall (b)(t) upCnt_bt[b][t] <= 1`
**의미**: 한 포대가 같은 위협에 두 발 동시 발사 안 함.
**왜 성립하나**: `best_u_b(b)`가 `upCnt_bt[b][i]==0` 가드로 필터. 한 번 발사해
1이 되면 그 위협은 더 이상 best 후보가 아님.

#### S6: 하층 동일 (`loCnt_bt[b][t] <= 1`)

#### S7: `A[] forall (t) upCnt_bt[0][t] + upCnt_bt[1][t] <= NB_U`
**의미**: 한 위협을 chase 중인 상층 포대 수가 NB_U(=2) 초과 못 함.
**왜 성립하나**: 포대마다 upCnt[t]<=1 (S5), 포대 수 = NB_U.
**의의**: 위협당 다포대 분산 한계.

#### S8: `A[] killed + leaked <= MAXT`
**의미**: 종결 카운터 합이 위협 총 수 이내.
**왜 성립하나**: Threat 인스턴스마다 Killed/Leaked는 한 번만 진입 (terminal).
counter ++ 도 한 번만.

### 8.2 Geometry invariants (A[], 2개)

#### RD1: `A[] forall (b)(t) upCnt_bt[b][t] > 0 imply engU_b[t][b]`
**의미**: 포대 b가 위협 t에 발사 중이면 위협 t는 반드시 포대 b의 윈도우 안에 있음.
**왜 성립하나**: 발사 가드가 `best_u_b(b)==t` 요구 → `best_u_b`가 `engU_b[t][b]`
true만 반환. 종결 시 `upCnt_bt[b][t]--`와 `engU_b[t][b]=false` 모두 reset.
**의의**: **"사거리·고도 밖 발사 0건"** — v3 추가 핵심 보장.

#### RD2: 하층 동일 (`loCnt_bt[b][t] > 0 imply engL_b[t][b]`)

### 8.3 Policy invariants (A[], 2개)

#### D1: `A[] forall (b) best_u_b(b) >= -1 && best_u_b(b) < MAXT`
**의미**: `best_u_b()` 반환값이 [-1, MAXT-1] 범위 (totality + 안전).
**왜 성립하나**: 함수 정의가 `return -1`로 fallback, 루프 반환은 `i < MAXT`로 제한.
**의의**: 함수 자체의 well-formedness 검증.

#### D2: 하층 동일.

### 8.4 Timing (A[], 1개)

#### T1: `A[] P.cp <= PERIOD_P`
**의미**: Planner의 주기 클럭이 PERIOD_P 초과 못 함.
**왜 성립하나**: Tick 위치의 invariant `cp <= PERIOD_P` + 가드 `cp >= PERIOD_P`로
정확히 PERIOD_P에 도달하면 fire되어 0으로 리셋.
**의의**: 계획수립 데드라인 보장. 시뮬레이터의 `planning_node._tick(2 Hz)` 데드라인
동등물.

### 8.5 Liveness (1개)

#### L1: `A<> killed + leaked == MAXT`
**의미**: 모든 위협은 결국 종결 (격추 또는 누설).
**왜 성립하나**: 모든 Threat의 Tracked는 결국 `impact[id]?`를 수신 (Radar가
IMPACT_AT[id]에 fire). impact 수신 → Leaked. 그 전에 hitU/hitL을 수신했으면
Killed. 어느 쪽이든 terminal.

### 8.6 Reachability (E<>, 6개)

#### R1: `E<> killed == MAXT`
**의미**: 전량 격추 시나리오가 존재.
**확인**: verifyta가 hit 경로만 선택하는 trace를 찾아주면 성립.

#### R2: `E<> inflU_b[0] > 0 && inflU_b[1] > 0`
**의미**: 두 상층 포대가 동시에 비행 중인 trace 존재 = **부하 분산 가능**.
**의의**: 한 포대로 다 처리하지 않고 두 포대로 나누는 동적 전략 가능성 검증.

#### R3: `E<> inflL_b[0] > 0 && inflL_b[1] > 0` (하층 동일)

#### R4: `E<> any_uCover(0) && any_lCover(0)`
**의미**: 위협 0이 상층 AND 하층 어느 포대로든 동시에 cover되는 trace 존재 =
**다층 요격 가능**.
**의의**: §11 패턴의 핵심 목표 검증.

#### R5: `E<> inflU_b[0] == CH_PER_U[0]`
**의미**: 상층 포대 0의 채널이 만탱크(=2) 차는 trace 존재 = **포화 상황 도달 가능**.
**의의**: 채널 한계 게이트가 활성화되는 시나리오가 모델 안에 있는지 sanity check.

#### R6: `E<> leaked > 0`
**의미**: 누설(탄착) 시나리오 존재.
**확인**: ammo/채널이 부족하거나 윈도우를 못 잡는 trace를 verifyta가 찾으면 성립.

### 8.7 어떤 쿼리가 v3 특유인가

| 쿼리 | v2 | v3 |
|---|---|---|
| S1, S2, S8, T1, L1, R1, R6 | ✅ (이름만 다를 수도) | ✅ |
| S3, S4 (포대별 채널) | ❌ (단일 `inflU<=CH_U`) | ✅ 포대별 forall |
| S5, S6 (포대별 충돌) | upCnt[t]<=1 (1D) | upCnt_bt[b][t]<=1 (2D) |
| S7 (위협당 포대 수) | ❌ | ✅ |
| RD1, RD2 (윈도우 일관성) | ❌ | ✅ |
| D1, D2 (정책 totality) | IMPL 한정 | ✅ |
| R2, R3 (포대 동시) | ❌ | ✅ |
| R4 (다층요격) | E<>(upCnt[0]>0 && loCnt[0]>0) | E<>(any_uCover(0) && any_lCover(0)) |
| R5 (만탱크) | ❌ | ✅ |

---

## 9. MSC 읽는 법 + 흔히 헷갈리는 동작

### 9.1 MSC 기본 기호

| 기호 | 의미 |
|---|---|
| 세로 막대 (lifeline) | 인스턴스 1개. 위→아래 = 시간 진행 |
| 박스 (Pre/Scan/Tracked/Idle/Ready/Flying/...) | 현재 location |
| 가로 빨간 화살표 | broadcast 발사 + 수신. 양쪽 모두 같은 시점에 전이 |
| 옅은 회색 박스 (Ready) | committed 위치. 시간 진행 없이 즉시 다음 |
| 박스 사이 빈 공간 | 시간 진행. 길이는 의미 없음 |
| 화살표 없는 박스 전이 | internal transition (가드만, 예: Radar `t == APPEAR[id]`) |

Symbolic Simulator는 절대 시각을 안 보이고, Concrete Simulator는 변수 패널에
`R0.t = 6.0`, `P.cp = 1.4` 같은 실수값을 함께 표시.

### 9.2 흔히 헷갈리는 3가지

#### (1) "plan을 받았는데 왜 발사 안 하나"
Ready(committed)에서 두 outgoing edge:
- `Ready → Flying`: 가드 `ammoU_b[batt_id]>0 && infl<CH && best_u_b>=0 && t==best`
- `Ready → Idle`: 가드 `best_u_b<0 || ammo==0 || infl>=CH`

committed라서 둘 중 하나가 즉시 발화. 첫 가드가 거짓이면 skip → MSC에 Ready 박스
잠깐 보였다가 Idle로 돌아감.

#### (2) "왜 모든 Slot이 동시에 Ready로 가나"
`plan`이 broadcast → Planner 한 발사로 6개 Slot이 동시 수신 → 6개 동시 Idle → Ready.

#### (3) "Threat 자체 클럭이 없는데 어떻게 진행하나"
Threat에는 clock 없음. 모든 상태 변화는 broadcast 수신으로만 발생. 시간 권위는
Radar가 가짐 (Radar의 `clock t`가 위협별 timing 결정).

---

## 10. ROS2 시뮬레이터 ↔ UPPAAL 정합

| ROS2 (`dwta_nodes/`) | UPPAAL v3 | 의미 |
|---|---|---|
| `surveillance_radar_node` /events: DETECTED | `Radar(id) detect[id]!` | 탐지 |
| `engageability_node`의 상층 cell (포대 b) 열림 | `Radar(id) enterU<b>[id]!` | 상층 포대 b 사거리·고도 진입 |
| `engageability_node`의 상층 cell (포대 b) 닫힘 | `Radar(id) exitU<b>[id]!` | 이탈 |
| `engageability_node`의 하층 cell 열림/닫힘 | `enterL<b>[id]!` / `exitL<b>[id]!` | 하층 동일 |
| `planning_node._tick(2 Hz)` | `Planner plan!` | 계획수립 주기 |
| `LauncherNode._on_plan`의 발사 (포대 b) | `Slot_U(b) Ready → Flying` | 발사 |
| `FireControlRadarNode.resolve` INTERCEPT | `Slot_U hitU[tgt]!` | 격추 |
| `FireControlRadarNode.resolve` MISS | `Slot_U missU[tgt]!` | 실패 |
| `surveillance_radar_node` /events: IMPACT | `Radar(id) impact[id]!` | 탄착 |
| `wta_backend.CleanSlateAdapter`의 우선순위 | `best_u_b(b)`, `best_l_b(b)` 함수 | 정책 추상 |
| (포대 b 잔여탄) `LauncherNode._available[battery.id]` | `ammoU_b[b]` | 잔여탄 |
| (포대 b 비행중) `LauncherNode._inflight[battery.id]` | `inflU_b[b]` | 비행중 |

---

## 11. PoC 활용 — 3가지 길

### (A) GUI 시뮬레이터로 한 step씩 따라가기
```
1. UPPAAL 5 실행 → File → Open → dwta_model_v3_geometry.xml
2. "Symbolic Simulator" 탭
3. Reset → enabled transition을 클릭하며 진행
4. 우측 Variables 패널: ammoU_b/inflU_b/engU_b/killed 변화 관찰
5. Trace 영역에 MSC 자동 누적
```
가장 직관적. "정말 사거리 밖에선 발사 안 하나" 같은 의문을 즉시 확인.

### (B) verifyta로 trace 자동 생성
```powershell
cd c:\Users\USER\Desktop\DWTA-Optimizer
# R1: 전량 격추 trace
verifyta.exe -t 1 -f r1 ros2_dwta\spec\dwta_model_v3_geometry.xml
# R4: 다층요격 trace
verifyta.exe -t 1 -f r4 ros2_dwta\spec\dwta_model_v3_geometry.xml
# 생성된 r1.xtr/r4.xtr를 GUI File→Open Trace로 로드 → MSC가 채워짐
```

### (C) 19개 쿼리 일괄 검증
```powershell
verifyta.exe -q ros2_dwta\spec\dwta_model_v3_geometry.xml
```
각 쿼리에 `Formula is satisfied` 또는 `Formula is NOT satisfied`가 출력됨.
NOT satisfied가 나오면 `-t 1`로 반례 trace를 받아 분석.

### 단축 명령 (PowerShell)
```powershell
# 시나리오 dump 후 v3 모델에 주입할 const 출력
python -c "import sys; sys.path.insert(0,'ros2_dwta'); from dwta_nodes.scenario import dump_uppaal_windows; print(dump_uppaal_windows(seed=42, n_threats=3))"

# 모델 well-formedness 점검 (라이선스 없이)
python -c "import xml.dom.minidom as m; m.parse('ros2_dwta/spec/dwta_model_v3_geometry.xml'); print('OK')"
```

---

## 12. `clean_slate_optimizer.py`와 UPPAAL의 관계

**UPPAAL은 그 파이썬 코드를 호출하지 않습니다.** Python 함수, HiGHS MIP, 부동소수
계수는 UPPAAL이 못 다룹니다. 대신 그 옵티마이저가 따르는 **정책 규칙**을 추상화해서
모델에 박았습니다.

### 정책의 본질만 추출
```python
# 의사 코드
for threat in sorted(threats, key=danger, reverse=True):   # ① 우선순위
    if upper_feasible(t) and not upper_already_locked(t):  # ② 충돌 회피
        assign_upper(t)
    if lower_feasible(t) and not lower_already_locked(t):
        assign_lower(t)                                     # ③ 다층요격
```

### IMPL/v3 모델에 그 규칙만 내장
```c
int best_u_b(int b) {       // ① 작은 id (= danger DESC 추상) 우선
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] == 0) return i;   // ② 충돌 회피
        i++;
    }
    return -1;
}
// Slot_U 발사 가드:
ammoU_b[batt_id] > 0 && inflU_b[batt_id] < CH_PER_U[batt_id]
  && best_u_b(batt_id) >= 0 && t == best_u_b(batt_id)
```
③ 다층요격은 Slot_L의 독립 동작으로 자연 표현 (Slot_U와 Slot_L이 같은 위협을 동시
잡아도 OK, 단 각자 cnt 관리).

### 따라오는 보장
- (S5) `upCnt_bt[b][t] <= 1` — 어느 시나리오에서도 한 포대가 같은 위협에 두 발 X
- (RD1) `upCnt_bt[b][t] > 0 ⇒ engU_b[t][b]` — 윈도우 밖 발사 0건
- (D1) `best_u_b(b)` 항상 valid 반환

이 규칙이 모든 합리적 WTA(GA/MIP/Greedy)에 공통이므로, ROS2 백엔드를 다른 옵티마이저로
바꿔도 동일 모델 사용 가능.

### 교차 검증 흐름
```
[ROS2]                                    [UPPAAL]
random_saturation_scenario(seed=42)       const 배열 (헬퍼로 자동 dump)
  ↓                                         ↓
CleanSlateOptimizer 매 plan!마다 풀음        verifyta -q dwta_model_v3...
  ↓                                         ↓
"격추 34/0 누설, 다층 9구간"                "19개 쿼리 모두 satisfied"
```
ROS2 trace의 모든 step이 UPPAAL의 19개 invariant를 어기지 않으면 정합.

---

## 13. 모델 한계 + state space 상한

### 13.1 의도적으로 추상화한 것
- **위협 위치/궤적**: 시간 윈도우로 환원 (사거리 + 고도의 교집합)
- **Pk 확률**: hit/miss 비결정 (Pk 0.85 → 85% 격추는 SMC/Stratego 필요)
- **MIP 정수 해 자체**: best_u_b/best_l_b 순서로 추상
- **연속 좌표 / 속도**: 사전 계산된 시간 윈도우로 변환

### 13.2 검증 가능 규모 (state space 추정)

| MAXT | NB_U+NB_L | sum(CH) | 총 인스턴스 | verifyta 시간 |
|---|---|---|---|---|
| 2 | 2 | 4 | ~10 | 초 단위 |
| 3 | 2 | 8 | ~15 | 수십 초 |
| **3** | **4** | **6** | **13 (현재 v3)** | **분 단위 (예상)** |
| 5 | 4 | 16 | ~25 | 분~십수 분 |
| 10+ | — | — | — | timeout / 불가 |

ROS2의 24발 random 시나리오를 그대로는 못 검증. **축소 대표 시나리오로 invariant
보증 → 큰 trace에 일반화 적용**이 정석.

### 13.3 확장하려면
포대별 6채널 같은 큰 capacity로 가려면:
```c
const int CH_PER_U[NB_U] = {6, 4};   // L1=6, L2=4
// System:
SU0_0 = Slot_U(0); ... SU0_5 = Slot_U(0);   // L1: 6 슬롯
SU1_0 = Slot_U(1); ... SU1_3 = Slot_U(1);   // L2: 4 슬롯
```
총 16+ 상층 슬롯 → verifyta 1~3분 안에 끝나는 범위. MSC 가독성은 떨어짐.

---

## 14. 시나리오 → 모델 자동 dump 워크플로

ROS2 random 시나리오를 UPPAAL 모델에 그대로 박는 한 줄.

### 14.1 헬퍼 함수 (`scenario.py`)

#### `compute_engagement_window(spawn, battery, assets, *, max_alt_km=80.0, dt=0.05, alt_window_km=None)`
위협의 포물선 궤적을 100Hz 샘플링해서 `(d ≤ R_battery) ∧ (h ∈ alt_window_km)`을
모두 만족하는 첫·마지막 절대 시각을 반환. `alt_window_km` 기본값: 상층 40~150 km,
하층 5~40 km.

```python
from dwta_nodes.scenario import compute_engagement_window, random_saturation_scenario
assets, batteries, spawns = random_saturation_scenario(seed=42, n_threats=3)
upper_bat = next(b for b in batteries if b.layer == "UPPER")
w = compute_engagement_window(spawns[0], upper_bat, assets)
# -> (8.4, 23.1)  같은 (enter, exit) 절대 초
```

#### `dump_uppaal_windows(seed=42, n_threats=3, *, max_alt_km=80.0) -> str`
random 시나리오의 모든 (위협, 포대) 윈도우를 UPPAAL declaration 형식으로 출력.

```python
print(dump_uppaal_windows(seed=42, n_threats=3))
# const int MAXT             = 3;
# const int NB_U             = 2;
# const int APPEAR[MAXT]    = { 3, 5, 9 };
# const int U_ENTER[MAXT][NB_U] = { {8, 8}, {14, 16}, {14, 19} };
# ...
```

### 14.2 v3 XML에 주입

1. 위 출력의 const 블록을 복사
2. `dwta_model_v3_geometry.xml`의 `<declaration>` 안 const 부분을 교체 (또는
   별도 파일에 붙여 새 인스턴스로)
3. `MAXT/NB_U/NB_L/CH_PER_*/AMMO0_*` 일치 확인
4. verifyta 또는 GUI로 검증

### 14.3 일관성 점검
ROS2 PoC와 UPPAAL이 같은 시나리오 const를 쓰면:
- ROS2 trace: `python ros2_dwta\run_poc.py 75 random` (시뮬레이션 결과)
- UPPAAL trace: `verifyta.exe -q dwta_model_v3_geometry.xml` (정형 검증)

두 결과의 일관성을 직접 비교 가능. UPPAAL이 invariant 위반을 발견하면 ROS2도
같은 seed로 재현되어야 함.

---

## 부록 A. v3 모델 파일 구조 한눈에

```
<?xml ?>
<nta>
  <declaration>
    // §3.1(a) 시스템 상수: MAXT, NB_U, NB_L, CH_PER_U/L, FLYOUT_U/L, PERIOD_P
    // §3.1(b) 시나리오 윈도우: APPEAR, IMPACT_AT, U_ENTER, U_EXIT, L_ENTER, L_EXIT
    // §3.1(c) 공유 상태: ammoU_b, ammoL_b, inflU_b, inflL_b, upCnt_bt, loCnt_bt,
    //                   engU_b, engL_b, killed, leaked
    // §3.1(d) Broadcast 채널: plan, detect, enterU0/U1/L0/L1, exit*, impact, hit/miss
    // §3.1(e) 함수: best_u_b, best_l_b, any_uCover, any_lCover, any_engU, any_engL
  </declaration>

  <template><name>Radar</name> ... (§4.1)
  <template><name>Threat</name> ... (§4.2)
  <template><name>Slot_U</name> ... (§4.3)
  <template><name>Slot_L</name> ... (§4.4)
  <template><name>Planner</name> ... (§4.5)

  <system>
    R0/R1/R2, T0/T1/T2,
    SU0_0/SU0_1/SU1_0, SL0_0/SL0_1/SL1_0,
    P;
  </system>

  <queries>
    S1~S8 (Safety), RD1~RD2 (Geometry), D1~D2 (Policy),
    T1 (Timing), L1 (Liveness), R1~R6 (Reachability)
  </queries>
</nta>
```

## 부록 B. v3 디버깅 체크리스트

문제 → 어디를 보나:
- 모델 열리지 않음 → XML well-formed? `python -m xml.dom.minidom ...`
- "is enabled but never fires" → committed 위치(Ready)의 두 outgoing edge 가드가
  배타적이고 합집합이 전체인지 확인
- best_u_b가 항상 -1 → engU_b가 true로 안 들어옴 → Radar의 enter* fire 시점 확인
- inflU_b 음수 → 발사/판정 시 `++/--` 균형 깨짐. 종결 시 reset 누락 확인
- 위협이 종결돼도 Slot의 cnt가 안 줄어듦 → broadcast hit가 0 receiver여서 OK여야
  하는데 동기화 에러? UPPAAL broadcast는 sender만 fire하므로 정상
- state space explosion → MAXT/NB/CH 줄이거나 invariant 단순화

---

이 문서로 v2/v3 모델의 모든 요소를 추적할 수 있습니다. 추가 질문(특정 transition의
의미, 새 쿼리 추가, ROS2 시뮬레이터 결과와 trace 비교)은 §11(PoC) 또는 §10(매핑)
섹션을 출발점으로.
