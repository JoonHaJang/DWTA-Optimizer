# UPPAAL 모델 설계 · 구현 · 사용 — 완전 문서

이 문서 하나로 `ros2_dwta/spec/` 의 모든 UPPAAL 모델을 **읽고, 시뮬레이션하고,
검증하고, ROS2 시뮬레이터와 정합**시킬 수 있게 작성됐습니다. UPPAAL/Timed Automata
기초부터, 모델 진화(v2→v3), 각 템플릿의 location/transition/guard, declaration의
모든 변수/함수, 19개 검증 쿼리 의미, MSC 해석, PoC 흐름까지 한 장에 정리합니다.

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
| 1 | **UPPAAL과 Timed Automata 기초** (도구·이론·XML 명세 형식·TCTL) |
| 2 | 모델 진화 (v1→v2→v3) |
| 3 | v3 모델 전체 구성 (템플릿/인스턴스/채널 한눈에) |
| 4 | Declaration 상세 (글로벌·로컬·시스템·함수) |
| 5 | 템플릿별 구현 상세 (Radar / Threat / Slot_U / Slot_L / Planner) |
| 6 | Broadcast 채널 전체 사양 |
| 7 | 한 위협의 lifecycle (v3 기준 단계별) |
| 8 | v2 vs v3 차이점 |
| 9 | 검증 쿼리 19개 상세 |
| 10 | MSC 읽는 법 + 흔히 헷갈리는 동작 |
| 11 | ROS2 시뮬레이터 ↔ UPPAAL 매핑 |
| 12 | PoC 활용 (GUI / verifyta / 헬퍼) |
| 13 | clean_slate_optimizer 와의 관계 |
| 14 | 모델 한계 + state space 상한 |
| 15 | 시나리오 → 모델 자동 dump 워크플로 |

---

## 1. UPPAAL과 Timed Automata 기초

이 섹션을 먼저 읽으면 본문(§2~)의 모든 표·다이어그램 기호가 자연스럽게 읽힙니다.
UPPAAL을 처음 보는 사람을 가정하고 도구·이론·XML 명세 형식·검증식 4가지를 차례로
설명합니다.

### 1.1 UPPAAL이 무엇인가

**UPPAAL**은 Aalborg(덴마크) + Uppsala(스웨덴) 두 대학이 1995년 이후 공동 개발해
온 **실시간 시스템 모델 체커**입니다. 통합 도구로 다음 세 가지를 한 GUI에서 제공:

| 역할 | 도구 | 무엇을 |
|---|---|---|
| **에디터** | Editor 탭 | 시스템(템플릿들의 네트워크)을 그래프 + 코드로 명세 |
| **시뮬레이터** | Symbolic / Concrete Simulator 탭 | 한 step씩 실행하며 trace 관찰 (MSC, 변수 패널) |
| **검증기** | Verifier 탭 | TCTL 쿼리로 안전성·라이브니스·도달성을 형식 증명 |

검증 엔진은 별도 CLI `verifyta.exe`로도 동작 (라이선스 동일).

**모델링 대상**: 분산 임베디드 시스템, 통신 프로토콜, 실시간 컨트롤러, 작업 스케줄러,
의료 기기, 자동차 ECU, 항공 시스템 등. 학계 + 산업계에서 30년간 검증된 표준 도구.

### 1.2 Timed Automaton — 이론 핵심

**Timed Automaton (TA)**은 유한 오토마타에 **실수값 클럭**(continuous time)을 더한
형식 모델입니다 (Alur & Dill, 1994). UPPAAL 모델 하나는 여러 TA의 **네트워크**.

#### 구성 요소 6가지

| 요소 | 정의 | UPPAAL XML |
|---|---|---|
| **Location (위치)** | 자동기의 상태 노드. 시스템의 현재 위치 | `<location id="...">` |
| **Edge / Transition (전이)** | location 간 화살표. guard 만족 시 fire | `<transition><source/><target/>` |
| **Clock (클럭)** | 실수값 변수. 모든 클럭은 동일 속도로 증가 | `clock x;` (declaration) |
| **Guard (가드)** | edge fire 조건. 클럭 비교·정수 변수 | `<label kind="guard">x >= 5</label>` |
| **Invariant (불변식)** | location에 머무는 조건. 위반 시 강제 이동 | `<label kind="invariant">x <= 10</label>` |
| **Assignment (할당)** | edge fire 시 실행. 클럭 리셋 + 변수 갱신 | `<label kind="assignment">x=0, n++</label>` |

#### 시간이 흐르는 두 가지 방식

1. **Delay (시간 진행)**: 어떤 edge도 fire하지 않으면 모든 클럭이 동시에 같은
   속도로 증가. **invariant가 한계** — `x <= 10`인 location에선 `x`가 10을
   넘기 전에 어떤 edge가 발화해야 함.
2. **Action (전이)**: edge가 fire하면 시간 진행 없이 즉시 다음 location으로.
   같은 step에서 assignment 실행.

#### 특수 location 종류

| 종류 | 의미 | UPPAAL 표기 |
|---|---|---|
| 일반 | invariant 한계 안에서 시간 진행 OK | (기본) |
| **Urgent** | 시간 진행 금지. 즉시 outgoing edge 중 하나 fire | `<urgent/>` 자식 태그 |
| **Committed** | urgent + 다른 자동기보다 우선. 원자적 처리 | `<committed/>` |

v3 모델에서 Slot_U의 `Ready` 위치가 committed. 의미: plan? 받은 직후 시간 진행
없이 즉시 발사 또는 skip 결심.

#### 채널(Channel)과 동기화

여러 자동기의 transition을 동기화하는 메커니즘.

| 채널 종류 | semantics | UPPAAL 선언 |
|---|---|---|
| **이진 동기 (handshake)** | 정확히 한 sender(`a!`) + 한 receiver(`a?`) 동시 발화 필요. 매칭 없으면 fire 불가 | `chan a;` |
| **Broadcast** | sender(`a!`) 한 명, receiver(`a?`) **0명 이상** 동시 수신. 매칭 안 돼도 sender 발화 가능 | `broadcast chan a;` |
| **Urgent** | + 시간 진행 막음. 가능하면 즉시 fire | `urgent chan a;` |

**v3 모델은 모든 채널이 broadcast** — receiver 0명이어도 fire 가능 → deadlock
방지. (예: 종결된 위협에 Slot이 hit를 발사해도 Threat는 이미 Killed라 수신
안 하지만 broadcast라 OK.)

#### 네트워크(NTA, Network of Timed Automata)

여러 TA가 채널·전역변수로 통신하며 함께 동작. UPPAAL의 `<nta>` 루트가 이 NTA를
의미. **모든 클럭은 절대 시각이 같다** (모두 같은 속도로 흐름) — 즉 R0의 `t=6.0`과
R1의 `t=6.0`은 같은 절대 시각.

### 1.3 UPPAAL XML 명세 형식

UPPAAL 모델 파일은 표준 XML. 핵심 태그 6가지.

```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE nta PUBLIC '...flat-1_6.dtd'>
<nta>                                     <!-- (1) 최상위: Network of Timed Automata -->

  <declaration>                            <!-- (2) 글로벌 declaration -->
    const int N = 3;
    int counter;
    broadcast chan tick;
    int square(int x) { return x * x; }    <!-- 함수도 정의 가능 (C-like) -->
  </declaration>

  <template>                               <!-- (3) 자동기 한 개 -->
    <name>Worker</name>
    <parameter>const int id</parameter>     <!-- 인스턴스화 시 받는 파라미터 -->
    <declaration>clock x;</declaration>     <!-- (4) 템플릿 로컬 declaration -->

    <location id="l0" x="0" y="0">          <!-- (5) location -->
      <name>Idle</name>
      <label kind="invariant">x <= 10</label>
    </location>
    <location id="l1" x="200" y="0">
      <name>Busy</name>
      <committed/>                          <!-- committed 위치 표시 -->
    </location>
    <init ref="l0"/>                        <!-- 초기 위치 -->

    <transition>                            <!-- (6) transition -->
      <source ref="l0"/>
      <target ref="l1"/>
      <label kind="select">i : int[0,N-1]</label>  <!-- 비결정 선택 -->
      <label kind="guard">x >= 5</label>
      <label kind="synchronisation">tick!</label>
      <label kind="assignment">x=0, counter++</label>
      <nail x="100" y="50"/>                 <!-- 곡선용 중간 핀 -->
    </transition>
  </template>

  <system>                                  <!-- (7) 인스턴스화 -->
    W0 = Worker(0);
    W1 = Worker(1);
    system W0, W1;                          <!-- 시뮬레이션할 인스턴스 -->
  </system>

  <queries>                                 <!-- (8) 검증식 -->
    <query><formula>A[] not deadlock</formula><comment>...</comment></query>
  </queries>
</nta>
```

#### Declaration 4 곳 (UPPAAL GUI 좌측 트리)

| 위치 | XML | 가시성 |
|---|---|---|
| **글로벌** | `<nta><declaration>` | 모든 인스턴스 공유 |
| **템플릿 로컬** | `<template><declaration>` | 그 템플릿의 인스턴스마다 자기 사본 |
| **System** | `<system>` | 인스턴스화 + `system A, B, C;` |
| **Queries** | `<queries>` | 검증 쿼리 |

GUI에서 좌측 트리:
```
Project
├── Declarations               ← 글로벌
├── <TemplateName>
│   ├── Declarations           ← 템플릿 로컬
│   └── (graph 영역)
├── ... (다른 템플릿)
└── System declarations         ← system 절
```

#### Label 종류 (transition / location 옆에 붙는 텍스트)

| `kind` 값 | 위치에서 | 전이에서 |
|---|---|---|
| `invariant` | location 머무는 조건 | — |
| `guard` | — | 전이 조건 |
| `synchronisation` | — | `chan!` 또는 `chan?` |
| `assignment` | — | 전이 시 실행할 코드 |
| `select` | — | 비결정 변수 선택 `i : int[0, N-1]` |
| `comments` | — | 메모 |

### 1.4 TCTL 쿼리 기초 — 무엇을 검증하나

UPPAAL 검증식은 **TCTL(Timed Computation Tree Logic)** 의 단순 부분집합.

| 쿼리 형태 | 의미 | 예 |
|---|---|---|
| `A[] φ` | **모든** 실행의 **모든 상태**에서 φ 성립 (Safety) | `A[] x >= 0` 클럭 x는 음수 X |
| `A<> φ` | 모든 실행에서 **언젠가** φ 성립 (Liveness) | `A<> done` 결국 done 도달 |
| `E[] φ` | **어떤** 실행에서 모든 상태에 φ 성립 (가능성) | 드물게 사용 |
| `E<> φ` | **어떤** 실행에서 언젠가 φ 성립 (Reachability) | `E<> killed == 5` 5건 격추 가능 |
| `φ --> ψ` | φ가 참이면 **결국** ψ가 참 (leads-to, 응답성) | `request --> response` |

**φ 안에 쓸 수 있는 것**:
- 위치 검사: `T0.Killed` (인스턴스 T0가 Killed 위치인가)
- 변수 비교: `killed == 3`, `ammoU_b[0] > 0`
- 클럭 비교: `P.cp <= 2`
- 논리: `&&`, `||`, `not`, `imply`
- 수량자: `forall (i : int[0,N-1]) ...`, `exists (...) ...`

**예시 (v3 모델)**:
- `A[] not deadlock` — 어떤 실행에서도 교착 없음
- `A[] forall (b : int[0,NB_U-1]) inflU_b[b] <= CH_PER_U[b]` — 모든 포대에서
  비행중 ≤ 채널
- `E<> killed == MAXT` — 전량 격추 시나리오가 가능

검증 결과는:
- `Formula is satisfied.` — 증명 완료
- `Formula is NOT satisfied.` — 반례 발견 (verifyta `-t 1` 옵션으로 trace 받아 분석)

### 1.5 UPPAAL이 못 다루는 것 (한계)

- **연속 동역학**: sin/cos/sqrt 같은 비선형 함수. 클럭 동력학은 항상 `dx/dt = 1`
  (일정 속도). 거리·고도 계산은 외부에서 사전 계산 필요.
- **부동소수 실수**: int/bool/clock만. 실수는 적분식이 아닌 시간 비교 안에서만 등장.
- **무한 데이터 구조**: 모든 배열·범위는 컴파일 타임 고정.
- **확률**: 기본 TCTL 검증(`A[]`, `E<>`)은 비결정만. 확률·통계가 필요하면 같은
  UPPAAL 5에 **통합된 SMC(Statistical Model Checker)** 사용 (별도 설치 불요).
  §17 참조 — `Pr[<=T](...)`, `simulate`, `E[...]` 쿼리 + branching edge에
  확률 가중치 + 위치별 clock slope (ODE) 표현.
- **MIP/LP 해**: 정수 최적해 자체는 표현 불가. 그 옵티마이저의 **정책 규칙**은
  추상화해서 모델에 박을 수 있음.

이 한계들이 본문 §13(모델 한계)와 §14(자동 dump)에서 우리 모델이 어떻게 우회했는지
설명됩니다.

---

## 2. 모델 진화 (v1 → v2 → v3)

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

이 문서의 본문은 **v3 기준**으로 쓰여 있고, v2 차이는 §8과 각 섹션의 "v2 동등물"에서
함께 짚습니다.

---

## 3. v3 모델 전체 구성 (한 장 view)

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
                  Threat(0/1/2)
                  Inbound → Tracked
                            ↑
                     engU_b[id][b], engL_b[id][b]  ◄── enter/exit
                            ↓ (hitU/L? 또는 impact?)
                          Killed / Leaked
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

## 4. Declaration 상세 — "어디에 무엇이 있고 누가 쓰나"

UPPAAL의 declaration은 4 곳에 분산됩니다 (§1.3 참조):
1. **Global** — 모든 인스턴스가 공유. `<nta><declaration>...</declaration>`.
2. **Template-local** — 각 인스턴스가 자기 사본을 가짐. `<template><declaration>`.
3. **System declarations** — 인스턴스화 + `system ... ;`.
4. **Queries** — 검증식. `<queries>`.

### 4.1 글로벌 declaration의 모든 항목 (v3)

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
**왜 broadcast인가**: §1.2 표 참조. handshake(`chan`)는 receiver 1명 필요해 일치
못 하면 sender도 fire 불가. broadcast는 receiver 0명이어도 OK → 종결된 위협에
hit를 fire해도 모델이 안 막힘.

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

### 4.2 Template-local declarations

| Template | local | 의미 |
|---|---|---|
| `Radar` | `clock t;` | 인스턴스마다 0부터 시작하는 절대 시각. APPEAR/IMPACT_AT 가드의 기준. |
| `Threat` | (없음) | 순수 signal-driven |
| `Slot_U` | `clock f; int tgt;` | `f` = 비행 시간 클럭. `tgt` = 발사 시 select한 위협 id (Flying에서 판정 시 사용) |
| `Slot_L` | `clock f; int tgt;` | 동일 |
| `Planner` | `clock cp;` | 계획수립 주기 클럭 |

> Local clock은 인스턴스마다 별개입니다. `R0.t`와 `R1.t`는 완전히 독립.

### 4.3 System declarations

위 §3의 13 인스턴스 + `system ...;` 행. `Slot_U(0)` 처럼 같은 batt_id로 인스턴스 두
개를 만들면 둘이 같은 `ammoU_b[0]` / `inflU_b[0]` 자원을 공유하는 두 채널이 됩니다.

---

## 5. 템플릿별 구현 상세

각 템플릿의 location, transition, guard/assignment를 한 줄씩 설명합니다.

### 5.1 Radar(const int id) — 위협 타이밍의 권위자

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

### 5.2 Threat(const int id) — 신호 소비자

**Local**: 없음 (clock 없음, 변수 없음 — 순수 signal-driven)

**Locations** (4개):
- `Inbound` — 초기. 탐지 전 대기
- `Tracked` — 탐지 후 활성 (사거리/고도 진입/이탈은 self-loop)
- `Killed` — terminal (격추)
- `Leaked` — terminal (탄착)

**Transitions** (15개):

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
| 10 | Tracked → Tracked | `missU[id]?` | — | 상층 요격탄 빗나감 |
| 11 | Tracked → Tracked | `missL[id]?` | — | 하층 요격탄 빗나감 |
| 12 | Tracked → Killed | `hitU[id]?` | `engU_b[id][0]=false, engU_b[id][1]=false, engL_b[id][0]=false, engL_b[id][1]=false, killed++` | 상층 격추 |
| 13 | Tracked → Killed | `hitL[id]?` | (같음) | 하층 격추 |
| 14 | Inbound → Leaked | `impact[id]?` | `leaked++` | 탐지 전 탄착 |
| 15 | Tracked → Leaked | `impact[id]?` | (engU/engL 모두 false, leaked++) | 탐지 후 탄착 |

### 5.3 Slot_U(const int batt_id) — 상층 채널 슬롯

**Local**: `clock f; int tgt;`

**Locations** (3개):
- `Idle` — 발사 대기
- `Ready` — committed (계획수립 신호 받은 직후. 즉시 다음 전이)
- `Flying` — invariant `f <= FLYOUT_U` (요격탄 비행 중)

**Transitions** (5개):

| # | from → to | select | guard | sync | assignment | 의미 |
|---|---|---|---|---|---|---|
| 1 | Idle → Ready | — | — | `plan?` | — | 계획수립 신호 수신 |
| 2 | Ready → Flying | `t : int[0,MAXT-1]` | `ammoU_b[batt_id]>0 && inflU_b[batt_id]<CH_PER_U[batt_id] && best_u_b(batt_id)>=0 && t==best_u_b(batt_id)` | — | `ammoU_b[batt_id]--, inflU_b[batt_id]++, upCnt_bt[batt_id][t]++, tgt=t, f=0` | **발사** |
| 3 | Ready → Idle | — | `best_u_b(batt_id)<0 \|\| ammoU_b[batt_id]==0 \|\| inflU_b[batt_id]>=CH_PER_U[batt_id]` | — | — | **skip** |
| 4 | Flying → Idle | — | `f >= FLYOUT_U` | `hitU[tgt]!` | `inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--` | 요격 성공 |
| 5 | Flying → Idle | — | `f >= FLYOUT_U` | `missU[tgt]!` | (같음) | 요격 실패 |

**작동 원리 — 핵심 4가지**:
1. **committed Ready**: `plan?` 수신 후 시간 진행 X → 즉시 발사 또는 skip.
2. **결정적 발사**: `t==best_u_b(batt_id)` 가드가 select range를 단 하나의 t로 고정.
3. **포대별 자원 분리**: 모든 mutation이 `[batt_id]`로 indexed.
4. **격추/실패 둘 다 비결정 발화**: Pk 확률을 추상화한 채 양쪽 trace 검증.

### 5.4 Slot_L(const int batt_id) — 하층 채널 슬롯

Slot_U와 구조 100% 동일. 변수만 `ammoL_b/inflL_b/loCnt_bt/best_l_b/FLYOUT_L`로
대체. broadcast도 `hitL/missL`.

### 5.5 Planner — `plan!` 의 모든 것

Planner는 **모델 전체의 클럭 주파수**를 결정하는 핵심 컴포넌트. 단 하나의 인스턴스
`P`, 단 하나의 location, 단 하나의 transition으로 이루어진 가장 단순한 템플릿이지만
그 `plan!` 한 줄이 모든 발사 결심의 출발점.

**Local**: `clock cp;` (Planner 인스턴스의 주기 클럭)

**Locations** (1개):
- `Tick` — invariant `cp <= PERIOD_P`

**Transitions** (1개):
- `Tick → Tick`: guard `cp >= PERIOD_P`, sync `plan!`, assignment `cp = 0`

#### 5.5.1 `plan!`이 정확히 무엇을 하나

```c
//                            ┌─── invariant: cp <= PERIOD_P ───┐
//                            │                                 │
//   ┌────────────► Tick ─────┴─── guard: cp >= PERIOD_P ───────┘
//   │              clock cp;       sync: plan!
//   │                              assign: cp = 0
//   └──────────── (self-loop) ────────────
```

**단계별로 보면**:
1. **시뮬레이션 시작 (t=0)**: P는 Tick 위치, cp=0
2. **시간 진행**: cp가 0부터 자동 증가 (모든 클럭과 같은 속도)
3. **invariant 한계 도달 직전 (cp=2)**: invariant `cp <= PERIOD_P`가 cp를 더 증가
   못 하게 막음 → 어떤 enabled transition이 즉시 fire해야 함
4. **가드 만족 확인**: 유일한 outgoing edge의 가드 `cp >= PERIOD_P` (2 >= 2) ✓
5. **edge fire**:
   - **sync `plan!`** — broadcast로 "지금 계획수립!" 신호 발사
   - **assignment `cp = 0`** — 클럭 리셋
6. **다시 Tick** — cp=0부터 다시 증가

**결과**: 정확히 매 `PERIOD_P=2`초마다 `plan!` 한 번씩 발사 (절대 시각으로 t=2,
4, 6, 8, ...).

#### 5.5.2 invariant + guard 결합의 의미

UPPAAL에서 "정확한 주기"는 항상 이 두 줄의 조합으로 표현됩니다:
```c
invariant: cp <= PERIOD_P    // (a) cp는 PERIOD_P 초과 못 함
guard:     cp >= PERIOD_P    // (b) 정확히 PERIOD_P 도달 시 fire
```
- (a)만 있으면: PERIOD_P 도달하면 시간이 멈출 뿐 fire 안 됨 → 교착
- (b)만 있으면: PERIOD_P 도달 후 시간이 더 흐르고 언제든 fire 가능 → 비정확
- **둘 다**: PERIOD_P에 도달하면 시간이 멈춰서(invariant) 즉시 fire 해야만 시간이
  다시 흐를 수 있음(guard) → **정확한 주기 강제**

이 패턴은 v2/v3 모든 정기적 이벤트(Radar의 detect/cross/impact, Planner의 plan)에
공통.

#### 5.5.3 `plan!` 발사 직후 무슨 일이 일어나나

broadcast이므로 **현재 `plan?`을 listening 중인 모든 인스턴스가 동시에 수신**.
v3 모델에서 그 인스턴스는:

| 인스턴스 | 현재 위치 | plan? 수신 시 행동 |
|---|---|---|
| SU0_0 (Slot_U, batt_id=0) | Idle | Idle → Ready (committed) |
| SU0_1 (Slot_U, batt_id=0) | Idle | Idle → Ready (committed) |
| SU1_0 (Slot_U, batt_id=1) | Idle | Idle → Ready (committed) |
| SL0_0 (Slot_L, batt_id=0) | Idle | Idle → Ready (committed) |
| SL0_1 (Slot_L, batt_id=0) | Idle | Idle → Ready (committed) |
| SL1_0 (Slot_L, batt_id=1) | Idle | Idle → Ready (committed) |

**6개 Slot이 동시에** Ready로 전이 → committed라 시간 진행 없이 즉시 다음 결심.

각 Slot은 자기 차례에서 두 가지 갈림길:
- 발사: `best_u_b(batt_id) >= 0` 이고 자원 OK → Flying으로
- skip: 자원 부족 또는 가능 위협 없음 → Idle로

여러 Slot이 같은 위협을 노릴 수 있나? — best_u_b(b)가 `upCnt_bt[b][i] == 0` 가드를
포함하므로, **같은 포대(같은 batt_id)의 두 Slot은 자동으로 다른 위협 선택**. 다른
포대는 같은 위협을 선택 가능 → 다포대 동시 사격 가능 (R2/R3 쿼리).

이미 Flying인 Slot은 `plan?`을 받지 않습니다 (Idle에서만 listening). 즉 비행 중인
Slot은 plan 무시.

#### 5.5.4 다른 인스턴스와의 시간적 관계

```
t=0   P:Tick(cp=0)        R0:Pre(t=0)         ...
                          (R0.t reaches APPEAR[0]=0)
                          R0 fires detect[0]!  ────► T0: Inbound → Tracked
t=2   P.cp == 2
      P fires plan!  ─────► 6 Slots: Idle → Ready (committed)
      cp = 0
                            6 Slots 동시 결심:
                              best_u_b(0) = -1 (engU_b[0][0]=false 아직)
                              모두 skip → Ready → Idle
t=4   P fires plan!  ─────► (또 모두 skip; 위협들 아직 사거리 안 들어옴)
...
t=8   R0 fires enterU0[0]! ─► T0: engU_b[0][0]=true (다음 plan에서 발사 가능)
...
t=10  P fires plan!  ─────► SU0_0: best_u_b(0) = 0, 발사!
                            SU0_1: best_u_b(0) = -1 (위협 0은 이미 SU0_0이 잡음),
                                   다음 위협들 아직 engU_b 안 됨 → skip
                            SU1_0: best_u_b(1) = ? (engU_b[0][1]은 t=9에 true 됐다면) ...
                            ...
```

**핵심**: Planner의 plan!은 "지금이 결심할 순간"을 알릴 뿐. 실제 발사는 각 Slot이
독립 판단. 위협이 사거리 안에 안 들어왔거나(`engU_b=false`) 자원 부족이면 plan을
받아도 skip → MSC에 Ready 박스 잠깐 보였다가 Idle로 돌아감.

#### 5.5.5 ROS2 시뮬레이터와의 매핑

| ROS2 | UPPAAL v3 |
|---|---|
| `planning_node.PERIOD = 0.5` (2 Hz timer) | `Planner.PERIOD_P = 2` (단위 임의, 의미 동등) |
| `planning_node._tick()` 호출 | `plan!` broadcast 발사 |
| `_tick` 안에서 GreedyWTA.solve() 호출 | 각 Slot의 Ready → Flying 가드에서 best_u_b/best_l_b |
| solve() 반환 후 LauncherNode가 발사 | Slot 인스턴스의 ammo/inflight 갱신 |

ROS2의 `_tick`이 위협 정보가 부족할 때 plan을 만들지 않거나 빈 plan을 보내는 것과
동등하게, UPPAAL의 Slot은 plan?을 받아도 skip 가능.

#### 5.5.6 디버깅 팁

- "왜 plan이 아예 안 발사되나?" → P의 cp가 PERIOD_P에 도달 못 함. 다른 인스턴스의
  invariant가 시간 진행을 막고 있을 가능성 (예: Radar의 Pre invariant가 위반되면
  교착 → P의 cp도 멈춤). verifyta `A[] not deadlock`으로 확인.
- "plan이 너무 자주 발사되는데?" → PERIOD_P 값 확인. 또는 다른 자동기의 urgent
  edge가 시간 진행을 자꾸 막는지 확인.
- "plan 받았는데 Slot이 fire 안 함" → committed Ready의 두 outgoing edge 가드를
  점검. (Idle → Ready → Flying 또는 Idle → Ready → Idle)
- "T1 쿼리 (`A[] P.cp <= PERIOD_P`) NOT satisfied" → 절대 일어나지 않아야 하는데
  일어났다면 model에 bug (invariant 누락 등).

---

## 6. Broadcast 채널 전체 사양

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
MAXT=3이면 `1 + 8*3 + 4*3 = 37 chan slot`.

---

## 7. 한 위협의 lifecycle (v3 기준 단계별)

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
          - skip 전이 발화
        6 Slots: Ready → Idle (즉시, 시간 진행 없음)
     P: Tick[cp=0] (리셋)

t=4  P가 다시 plan! 발사. 동일하게 모두 skip.

t=8  ─── R0.t reaches U_ENTER[0][0]=8 ───
     R0 fires enterU0[0]! ──► T0: engU_b[0][0]=true (T0 위치 변화 없음, self-loop)

t=9  ─── R0.t reaches U_ENTER[0][1]=9 ───
     R0 fires enterU1[0]! ──► T0: engU_b[0][1]=true

t=10 ─── P.cp reaches 2 다시 ───
     P fires plan! ──────────► 6 Slots: Idle → Ready
        SU0_0(batt_id=0): best_u_b(0)=0, 발사
                          ammoU_b[0]=2, inflU_b[0]=1, upCnt_bt[0][0]=1, tgt=0, f=0
                          SU0_0: Ready → Flying[f=0]
        SU0_1(batt_id=0): best_u_b(0)=-1 (이미 같은 포대 잡음), skip
        SU1_0(batt_id=1): best_u_b(1)=0, 발사
                          ammoU_b[1]=1, inflU_b[1]=1, upCnt_bt[1][0]=1
                          SU1_0: Ready → Flying

t=15 ─── SU0_0.f reaches FLYOUT_U=5 ───
     SU0_0 fires hitU[0]! ──► T0: Tracked → Killed
                              engU_b/engL_b 모두 false, killed=1
     SU0_0: inflU_b[0]=0, upCnt_bt[0][0]=0, Flying → Idle

     SU1_0.f도 5 도달 → hitU[0]! 또는 missU[0]! fire
        T0는 이미 Killed라 수신 안 함, broadcast라 OK
        SU1_0: 카운터 정리 후 Idle

t=30 ─── R0.t reaches IMPACT_AT[0]=30 ───
     R0 fires impact[0]! ──► T0는 Killed (sink)라 수신 안 함
     R0: Scan → Done
```

**6가지 핵심 포인트**:
1. 위협이 시간을 모름. Radar의 broadcast가 모든 상태 변화 트리거.
2. plan은 매 PERIOD_P=2초마다 발사되지만 발사 조건 미충족 시 모두 skip.
3. 같은 포대의 두 채널이 같은 위협을 노릴 수 없음.
4. 다른 포대는 같은 위협을 노릴 수 있음 (포대별 cnt가 별개).
5. broadcast hit/miss는 0 receiver여도 OK.
6. `f == FLYOUT_U` 가드 만족 시 hit/miss는 비결정 → 양쪽 trace 다 탐색.

---

## 8. v2 vs v3 차이점 — 한 표로

| 항목 | v2 SPEC/IMPL | v3 |
|---|---|---|
| **위협 진입 표현** | `crossU[id]!` 한 번 → engU[id]=true 영원 | `enterU0[id]!`/`exitU0[id]!` 4종 × 2포대 = 8 broadcast |
| **Threat 위치** | Inbound/UpperEng/BothEng/Killed/Leaked (5개) | Inbound/Tracked/Killed/Leaked (4개) |
| **포대 자원** | 단일 `ammoU`, `inflU` | 포대별 `ammoU_b[NB_U]`, `inflU_b[NB_U]` |
| **충돌 회피 카운터** | `upCnt[t]` (1D) | `upCnt_bt[b][t]` (2D) |
| **Interceptor 인스턴스** | `InterceptorU × CH_U` | `Slot_U(b) × CH_PER_U[b]` for each b |
| **best 함수** | `best_u()`, `best_l()` | `best_u_b(b)`, `best_l_b(b)` |
| **시간 const 표현** | `ENTER_U[MAXT]` 1D | `U_ENTER[MAXT][NB_U]`, `U_EXIT[MAXT][NB_U]` 2D |
| **검증 쿼리 수** | 16 (SPEC) / 18 (IMPL) | 19 |
| **새 쿼리 (v3 only)** | — | S3/S4 포대별 채널, S7 위협당 포대 수, RD1/RD2 윈도우 일관성, R2/R3/R5 |
| **윈도우 이탈 표현** | 불가 (영원히 engU=true) | 가능 (`exitU0/exitU1`로 다른 포대로 인계) |

---

## 9. 검증 쿼리 19개 상세

### 9.1 Safety (A[], 9개)

#### S1: `A[] not deadlock`
**의미**: 어떤 reachable 상태에서도 시간 진행 또는 enabled transition이 있음.
**왜 성립하나**: Threat의 Tracked는 결국 impact 수신, Slot의 Ready committed는
skip 전이가 항상 enabled, Radar의 Pre/Scan/Done은 시간 진행 OK.

#### S2u/S2l: `A[] forall (b) ammoU_b[b] >= 0` / `ammoL_b[b] >= 0`
**왜 성립하나**: Slot 발사 가드에 `ammoU_b[batt_id] > 0` 포함. `--`는 발사 시 한
번만 실행.

#### S3: `A[] forall (b) inflU_b[b] <= CH_PER_U[b]`
**왜 성립하나**: 발사 가드 `inflU_b[batt_id] < CH_PER_U[batt_id]`. `++`/`--` 균형.

#### S4: 하층 동일

#### S5: `A[] forall (b)(t) upCnt_bt[b][t] <= 1`
**의미**: 한 포대가 같은 위협에 두 발 동시 발사 안 함.
**왜 성립하나**: `best_u_b(b)`가 `upCnt_bt[b][i]==0` 가드로 필터.

#### S6: 하층 동일

#### S7: `A[] forall (t) upCnt_bt[0][t] + upCnt_bt[1][t] <= NB_U`
**의미**: 한 위협 chase 중 상층 포대 수 ≤ NB_U.

#### S8: `A[] killed + leaked <= MAXT`
**의미**: 종결 카운터 합이 위협 총 수 이내.

### 9.2 Geometry invariants (A[], 2개)

#### RD1: `A[] forall (b)(t) upCnt_bt[b][t] > 0 imply engU_b[t][b]`
**의미**: 발사 중인 위협은 반드시 그 포대의 윈도우 안에 있음.
**의의**: **"사거리·고도 밖 발사 0건"** — v3 핵심 보장.

#### RD2: 하층 동일

### 9.3 Policy invariants (A[], 2개)

#### D1: `A[] forall (b) best_u_b(b) >= -1 && best_u_b(b) < MAXT`
**의미**: `best_u_b()` 반환값 totality 검증.

#### D2: 하층 동일

### 9.4 Timing (A[], 1개)

#### T1: `A[] P.cp <= PERIOD_P`
**의미**: Planner 주기 클럭이 PERIOD_P 초과 못 함.
**왜 성립하나**: §5.5.2 invariant + guard 결합 (Planner location의 invariant
`cp <= PERIOD_P`가 시간 진행을 막고, 가드 `cp >= PERIOD_P`가 정확히 그 시각에
fire 강제).

### 9.5 Liveness (1개)

#### L1: `A<> killed + leaked == MAXT`
**의미**: 모든 위협은 결국 종결.

### 9.6 Reachability (E<>, 6개)

#### R1: `E<> killed == MAXT` — 전량 격추 가능
#### R2: `E<> inflU_b[0] > 0 && inflU_b[1] > 0` — 두 상층 포대 동시 가동
#### R3: 하층 동일
#### R4: `E<> any_uCover(0) && any_lCover(0)` — 위협 0 다층요격 도달
#### R5: `E<> inflU_b[0] == CH_PER_U[0]` — 상층 포대 0 채널 만탱크
#### R6: `E<> leaked > 0` — 누설 도달

---

## 10. MSC 읽는 법 + 흔히 헷갈리는 동작

### 10.1 MSC 기본 기호

| 기호 | 의미 |
|---|---|
| 세로 막대 (lifeline) | 인스턴스 1개. 위→아래 = 시간 진행 |
| 박스 | 현재 location |
| 가로 빨간 화살표 | broadcast 발사 + 수신. 양쪽 모두 같은 시점에 전이 |
| 옅은 회색 박스 (Ready) | committed 위치. 시간 진행 없이 즉시 다음 |
| 박스 사이 빈 공간 | 시간 진행. 길이는 의미 없음 |
| 화살표 없는 박스 전이 | internal transition (가드만, 예: Radar `t == APPEAR[id]`) |

### 10.2 흔히 헷갈리는 3가지

#### (1) "plan을 받았는데 왜 발사 안 하나"
Ready(committed)에서 두 outgoing edge — 가드 만족하는 쪽이 즉시 fire.
첫 가드 거짓이면 skip → MSC에 Ready 박스 잠깐 보였다가 Idle로 돌아감.

#### (2) "왜 모든 Slot이 동시에 Ready로 가나"
`plan`이 broadcast → Planner 한 발사로 6개 Slot이 동시 수신 → 6개 동시 Ready.

#### (3) "Threat 자체 클럭이 없는데 어떻게 진행하나"
모든 상태 변화는 broadcast 수신으로만 발생. 시간 권위는 Radar.

---

## 11. ROS2 시뮬레이터 ↔ UPPAAL 정합

| ROS2 (`dwta_nodes/`) | UPPAAL v3 | 의미 |
|---|---|---|
| `surveillance_radar_node` /events: DETECTED | `Radar(id) detect[id]!` | 탐지 |
| `engageability_node`의 상층 cell (포대 b) 열림 | `Radar(id) enterU<b>[id]!` | 상층 진입 |
| `engageability_node`의 상층 cell 닫힘 | `Radar(id) exitU<b>[id]!` | 이탈 |
| 하층 동일 | `enterL<b>[id]!` / `exitL<b>[id]!` | 하층 |
| `planning_node._tick(2 Hz)` | `Planner plan!` | 계획수립 주기 |
| `LauncherNode._on_plan`의 발사 (포대 b) | `Slot_U(b) Ready → Flying` | 발사 |
| `FireControlRadarNode.resolve` INTERCEPT | `Slot_U hitU[tgt]!` | 격추 |
| `FireControlRadarNode.resolve` MISS | `Slot_U missU[tgt]!` | 실패 |
| `surveillance_radar_node` /events: IMPACT | `Radar(id) impact[id]!` | 탄착 |
| `wta_backend.CleanSlateAdapter` 우선순위 | `best_u_b(b)`, `best_l_b(b)` | 정책 추상 |

---

## 12. PoC 활용 — 3가지 길

### (A) GUI 시뮬레이터로 한 step씩 따라가기
```
1. UPPAAL 5 실행 → File → Open → dwta_model_v3_geometry.xml
2. "Symbolic Simulator" 탭
3. Reset → enabled transition을 클릭하며 진행
4. 우측 Variables 패널: ammoU_b/inflU_b/engU_b/killed 변화 관찰
5. Trace 영역에 MSC 자동 누적
```

### (B) verifyta로 trace 자동 생성
```powershell
cd c:\Users\USER\Desktop\DWTA-Optimizer
verifyta.exe -t 1 -f r1 ros2_dwta\spec\dwta_model_v3_geometry.xml
verifyta.exe -t 1 -f r4 ros2_dwta\spec\dwta_model_v3_geometry.xml
```

### (C) 19개 쿼리 일괄 검증
```powershell
verifyta.exe -q ros2_dwta\spec\dwta_model_v3_geometry.xml
```

### 단축 명령
```powershell
# 시나리오 dump
python -c "import sys; sys.path.insert(0,'ros2_dwta'); from dwta_nodes.scenario import dump_uppaal_windows; print(dump_uppaal_windows(seed=42, n_threats=3))"

# 모델 well-formedness 점검 (라이선스 없이)
python -c "import xml.dom.minidom as m; m.parse('ros2_dwta/spec/dwta_model_v3_geometry.xml'); print('OK')"
```

---

## 13. `clean_slate_optimizer.py`와 UPPAAL의 관계

**UPPAAL은 그 파이썬 코드를 호출하지 않습니다.** Python 함수, HiGHS MIP, 부동소수
계수는 UPPAAL이 못 다룹니다 (§1.5 한계 참조). 대신 그 옵티마이저가 따르는
**정책 규칙**을 추상화해서 모델에 박았습니다.

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
```
③ 다층요격은 Slot_U와 Slot_L이 독립 동작하므로 자연 표현.

### 따라오는 보장
- (S5) `upCnt_bt[b][t] <= 1` — 어느 시나리오에서도 한 포대가 같은 위협에 두 발 X
- (RD1) `upCnt_bt[b][t] > 0 ⇒ engU_b[t][b]` — 윈도우 밖 발사 0건
- (D1) `best_u_b(b)` 항상 valid 반환

### 교차 검증 흐름
```
[ROS2]                                    [UPPAAL]
random_saturation_scenario(seed=42)       const 배열 (헬퍼로 자동 dump)
  ↓                                         ↓
CleanSlateOptimizer 매 plan!마다 풀음        verifyta -q dwta_model_v3...
  ↓                                         ↓
"격추 34/0 누설, 다층 9구간"                "19개 쿼리 모두 satisfied"
```

---

## 14. 모델 한계 + state space 상한

### 14.1 의도적으로 추상화한 것
- **위협 위치/궤적**: 시간 윈도우로 환원 (사거리 + 고도의 교집합)
- **Pk 확률**: hit/miss 비결정 (Pk 0.85 → 85% 격추는 SMC/Stratego 필요)
- **MIP 정수 해 자체**: best_u_b/best_l_b 순서로 추상
- **연속 좌표 / 속도**: 사전 계산된 시간 윈도우로 변환

### 14.2 검증 가능 규모 (state space 추정)

| MAXT | NB_U+NB_L | sum(CH) | 총 인스턴스 | verifyta 시간 |
|---|---|---|---|---|
| 2 | 2 | 4 | ~10 | 초 단위 |
| 3 | 2 | 8 | ~15 | 수십 초 |
| **3** | **4** | **6** | **13 (현재 v3)** | **분 단위** |
| 5 | 4 | 16 | ~25 | 분~십수 분 |
| 10+ | — | — | — | timeout |

### 14.3 확장하려면
포대별 6채널 같은 큰 capacity:
```c
const int CH_PER_U[NB_U] = {6, 4};
// System:
SU0_0 = Slot_U(0); ... SU0_5 = Slot_U(0);   // 6 슬롯
SU1_0 = Slot_U(1); ... SU1_3 = Slot_U(1);   // 4 슬롯
```

---

## 15. 시나리오 → 모델 자동 dump 워크플로

ROS2 random 시나리오를 UPPAAL 모델에 그대로 박는 한 줄.

### 15.1 헬퍼 함수 (`scenario.py`)

#### `compute_engagement_window(spawn, battery, assets, *, max_alt_km=80.0, dt=0.05, alt_window_km=None)`
위협의 포물선 궤적을 샘플링해서 `(d ≤ R_battery) ∧ (h ∈ alt_window_km)`을 모두
만족하는 첫·마지막 절대 시각을 반환. 기본 고도: 상층 40~150 km, 하층 5~40 km.

```python
from dwta_nodes.scenario import compute_engagement_window, random_saturation_scenario
assets, batteries, spawns = random_saturation_scenario(seed=42, n_threats=3)
upper_bat = next(b for b in batteries if b.layer == "UPPER")
w = compute_engagement_window(spawns[0], upper_bat, assets)
# -> (8.4, 23.1)
```

#### `dump_uppaal_windows(seed=42, n_threats=3, *, max_alt_km=80.0) -> str`
random 시나리오의 모든 (위협, 포대) 윈도우를 UPPAAL declaration 형식으로 출력.

### 15.2 v3 XML에 주입

1. 위 출력의 const 블록을 복사
2. v3 XML의 `<declaration>` 안 const 부분을 교체
3. `MAXT/NB_U/NB_L/CH_PER_*/AMMO0_*` 일치 확인
4. verifyta 또는 GUI로 검증

### 15.3 일관성 점검
ROS2와 UPPAAL이 같은 시나리오 const를 쓰면 trace를 직접 비교 가능.

---

## 16. 모델 안 동적 계산 vs 사전 계산 — trade-off

> "ROS2에서 사전 계산해 const로 박는 대신, UPPAAL declaration 안에서 함수로
> 직접 계산하면 안 되나?" 자주 나오는 질문. 답: **부분적으로 가능하지만 권하지
> 않습니다.** UPPAAL 함수 능력의 정확한 경계와 trade-off를 정리합니다.

### 16.1 UPPAAL declaration 함수가 할 수 있는 것

C 스타일 함수 정의가 declaration 블록(글로벌·템플릿 로컬 어디든)에서 가능:

```c
int square(int x) { return x * x; }

int linear_pos(int launch, int impact, int step, int flight) {
    // 위치 = launch + (impact - launch) * step / flight
    return launch + (impact - launch) * step / flight;
}

int parabolic_altitude(int max_alt, int step, int flight) {
    // h = 4 * max_alt * step * (flight - step) / (flight * flight)
    return (4 * max_alt * step * (flight - step)) / (flight * flight);
}

bool in_range_sq(int x1, int y1, int x2, int y2, int range_sq) {
    // sqrt 회피: 거리^2 ≤ 사거리^2 로 비교
    int dx = x1 - x2;
    int dy = y1 - y2;
    return dx * dx + dy * dy <= range_sq;
}

bool engageable(int id, int b, int step) {
    int x = linear_pos(LAUNCH_X[id], IMPACT_X[id], step, FLIGHT[id]);
    int y = linear_pos(LAUNCH_Y[id], IMPACT_Y[id], step, FLIGHT[id]);
    int h = parabolic_altitude(MAX_ALT[id], step, FLIGHT[id]);
    return in_range_sq(x, y, BAT_X[b], BAT_Y[b], RANGE_SQ[b])
        && (ALT_MIN[b] <= h && h <= ALT_MAX[b]);
}
```

**지원되는 것**:
- `int`, `bool`, 다차원 배열의 산술/논리 연산
- `for`, `while`, `if/else`, `return`
- 글로벌 변수 읽기/쓰기 (전이의 assignment처럼)
- 함수에서 다른 함수 호출
- `const` 배열 색인 (`U_ENTER[id][b]`)
- 정수 곱·나누기·모듈로 (sqrt 없이 `dx*dx + dy*dy <= R*R`로 대체)

**지원 안 되는 것** (UPPAAL Stratego/SMC 빼고 기본 UPPAAL):
- **sqrt, sin, cos, exp, log** — 비선형 함수
- **부동소수 실수** — `double` 없음
- **clock을 함수 인자로** — 클럭은 함수 안에서 비교/할당 못 함 (전이 가드에서만)
- **함수 안에서 시간 진행** — 모든 함수는 0-시간 atomic 실행
- **재귀** — 일부 버전 제한적 (스택 작음)

### 16.2 우리 use case에 적용하면

위협 궤적이 선형이고 고도가 포물선이면 **모든 산술은 정수로 표현 가능**. sqrt는
squared distance로 우회. 즉 §11의 사전 계산을 UPPAAL 안으로 옮길 수 있습니다.

**하지만 한 가지 장벽**: 클럭 `t`(실수)를 함수 입력으로 못 씀. 우회는:

#### 방법 A — Discrete step 변수
```c
// Radar(id) declaration
clock t;
int step;          // 정수 시간 진행 카운터

// Radar location Tick (invariant t <= step + 1)
// Tick -> Tick: guard t == step + 1; assign step++
```
매 정수 초마다 `step++` → 함수가 `step`을 받아 위치/고도/거리 계산.
**대가**: continuous time semantics 일부 손실, state space 증가
(`step ∈ [0, IMPACT_AT]` 만큼 추가 차원).

#### 방법 B — 매 정수 시각마다 미리 계산해 const로 (현재 v3 방식)
ROS2가 100Hz로 샘플링하고 `[enter, exit]` 압축. UPPAAL은 그 const만 봄.

### 16.3 trade-off 표

| 항목 | 사전 계산 + const (현재 v3) | 모델 안 동적 계산 (대안 A) |
|---|---|---|
| **모델 복잡도** | 낮음 (4종 const 배열) | 높음 (8+ 함수, step 변수, 추가 location) |
| **State space** | 작음 (윈도우는 const) | **큼** (step 차원 + 함수 호출마다 평가) |
| **검증 시간 (MAXT=3, NB=2)** | 수십 초 ~ 분 | **분~십수 분 또는 timeout** |
| **시나리오 변경 시** | ROS2 헬퍼 재실행 후 const 교체 | UPPAAL 모델 declaration의 const(LAUNCH_X 등)만 교체 |
| **궤적 모델 변경 시** | ROS2 헬퍼만 수정 | UPPAAL 함수 수정 (재검증) |
| **continuous time 보존** | 완전 (`t` 실수 그대로) | 부분 손실 (정수 step) |
| **검증 가능 규모** | MAXT 5~10까지 | MAXT 3 이상 어려움 |
| **모델 가독성 (MSC)** | 깔끔 | step 변화가 모든 MSC step에 표시 |
| **ROS2 시뮬레이터와의 정합** | 헬퍼가 보장 | 함수 식과 시뮬레이터 식을 따로 관리 |
| **Pk·고도 분포 모델링** | 사전 계산이 양쪽 모두 흡수 | 함수에 직접 표현 가능하나 비선형이면 다시 막힘 |

### 16.4 권고

**v3는 사전 계산 + const 채택**. 이유:
1. **검증 효율이 핵심** — UPPAAL의 본업이 정형 검증인데 동적 계산을 모델에 넣으면
   state space가 폭발해 invariant 증명이 timeout.
2. **연속 동역학은 ROS2가 더 잘함** — Python에서 100Hz 샘플링, numpy로 정확히
   계산. UPPAAL에 그걸 정수로 다시 표현하는 건 손해.
3. **모델은 invariant 기계**, 시뮬레이터는 동력학 기계로 역할 분리 → 두 도구의
   장점을 각자 살림.

**모델 안 동적 계산이 유리한 경우**:
- 위협 수가 매우 적고(MAXT ≤ 2) state space 여유가 큼
- 궤적/고도 식을 자주 바꿔가며 invariant 영향을 비교하고 싶음 (parametric study)
- ROS2 헬퍼 없이 UPPAAL 단독으로 self-contained 모델을 원함

이 경우 §16.1 예시 코드를 출발점으로 `dwta_model_v3b_inmodel_geometry.xml` 같은
별도 파일을 만들면 됩니다. 본 프로젝트는 v3 사전 계산 방식을 메인으로 유지.

### 16.5 부분적 동적 계산 — 절충안

전부 다 안 하더라도 일부 정책 함수는 declaration에 넣어도 cost가 적습니다.
v3 모델의 `best_u_b(b)`, `best_l_b(b)`, `any_uCover(t)` 같은 것이 그 예 — 이건
정수 배열 한 번 스캔으로 끝나서 state space 영향 거의 없음.

거리·고도처럼 step마다 계산하는 함수는 step 차원 때문에 state space가 커지지만,
"매 plan! 때만 한 번 호출"되는 정책 함수는 부담 없음.

> 즉, UPPAAL declaration 함수는 **"정책 / 우선순위 / 자원 점검"** 같은 한 step에
> 한 번 호출되는 결정 로직에 최적이고, **"매 step 진화하는 동력학"** 표현에는
> 부적합. v3가 이미 그 분할을 따르고 있습니다.

---

## 17. UPPAAL SMC — 통계적 검증과 확률·ODE 표현

§1.5와 §16의 두 한계 — "확률 못 다룸 / sqrt·sin·연속 동역학 못 다룸" — 이
**SMC 모드에서 부분 해제**됩니다. 사용자 환경의 UPPAAL 5는 SMC가 통합되어 있어
(Verifier 탭의 `Options → Statistical parameters...` 메뉴) 별도 설치 없이 즉시
사용 가능.

### 17.1 SMC가 무엇을 추가하나

기본 TCTL은 **모든 실행 / 어떤 실행**에 대한 정형 증명. SMC는 **무작위 시뮬레이션을
N번 반복해 확률을 통계적으로 추정**합니다. 결과는 100% 증명이 아니라 신뢰구간
포함 추정치.

| 기능 | 기본 TCTL | SMC |
|---|---|---|
| 안전성 증명 | `A[] φ` | `Pr[<=T] [] φ`  (시간 T까지 항상 φ일 확률) |
| 도달성 증명 | `E<> φ` | `Pr[<=T] <> φ`  (시간 T 안에 φ에 도달할 확률) |
| 평균/최대/분포 | (없음) | `E[<=T; N] (max: x)`  (N회 시뮬 후 x의 평균 최댓값) |
| 무작위 trace | 한 trace | `simulate N [<=T] {x, y, z}`  (N개 plot) |
| 확률 모델링 | 비결정 분기 | **branching edge에 확률 가중치** `[1, 4]` (20% vs 80%) |
| 연속 동역학 | clock slope = 1 고정 | **위치별 다른 slope** → ODE 표현 가능 |

### 17.2 사용자가 본 파라미터 다이얼로그 해석

| 파라미터 | 의미 | 보통 값 |
|---|---|---|
| Lower/Upper probabilistic deviation (±δ) | 확률 추정의 허용 오차 폭 (신뢰구간 절반 너비) | 0.01 (=1%) |
| Probability of false negatives (α) | Type I 오류 (참인데 거짓 판정) 한계. 보통 5% | 0.05 |
| Probability of false positives (β) | Type II 오류 (거짓인데 참 판정) 한계 | 0.05 |
| Probability uncertainty (ε) | 확률 비교 시 uncertainty zone 폭 | 0.05 |
| Ratio lower bound (u0) / upper bound (u1) | 가설 검정의 두 임계 — `H0: P ≤ u0` vs `H1: P ≥ u1` (SPRT) | 0.9 / 1.1 (가중치 비교용) |
| Histogram bucket width / count | `E[]` 결과 히스토그램 빈 크기/개수. 0이면 자동 | 0 |
| Trace resolution | `simulate`의 샘플 수 (해상도) | 4000 |
| Discretization step for hybrid systems | hybrid ODE의 이산화 시간 step | 0.01 (=10ms) |
| Local integration error bound | ODE 적분 한 step 오차 한계 | 0.01 |
| Integration error bound pr. time-unit | ODE 적분 누적 오차 한계 (시간 단위당) | 0.01 |

신뢰구간 95%로 확률을 ±1% 안에서 추정하고, hybrid ODE는 10ms step으로 적분.
보통은 기본값 그대로 두고 변경 안 함.

### 17.3 우리 v3 모델에 적용 — 새 쿼리 4가지

`dwta_model_v3_geometry.xml`의 `<queries>`에 다음을 추가하면 곧바로 통계 분석:

```c
// (1) 시간 T=40초 안에 전량 격추할 확률
Pr[<=40] (<> killed == MAXT)

// (2) T=40초 안에 누설이 한 번이라도 발생할 확률
Pr[<=40] (<> leaked > 0)

// (3) 100회 시뮬레이션 후 격추 수의 평균
E[<=40; 100] (max: killed)

// (4) trace 100개를 시간 0~40 구간에서 plot — killed/leaked/inflU_b 변화 관찰
simulate 100 [<=40] {killed, leaked, inflU_b[0], inflU_b[1]}
```

GUI Verifier 탭에서 (1)(2)는 P값과 신뢰구간, (3)은 평균과 분포 히스토그램,
(4)는 100개 trace 그래프를 출력.

### 17.4 우리 모델에 확률 가중치 추가하기 — Pk 직접 모델링

현재 v3는 `hitU[tgt]!` / `missU[tgt]!`를 비결정 분기로 표현 → "둘 다 가능한 trace
존재" 만 검증. SMC를 쓰면 Pk를 **확률 가중치**로 표현해서 정확한 격추율 계산
가능:

```c
// Slot_U.Flying -> Idle 전이에 weight 부여
// pk=0.85 가정: 17 : 3 = 85% : 15%
<transition>
  <source ref="su_fly"/><target ref="su_idle"/>
  <label kind="guard">f >= FLYOUT_U</label>
  <label kind="synchronisation">hitU[tgt]!</label>
  <label kind="probability">17</label>   <!-- 새로 추가 -->
  ...
</transition>
<transition>
  <source ref="su_fly"/><target ref="su_idle"/>
  <label kind="guard">f >= FLYOUT_U</label>
  <label kind="synchronisation">missU[tgt]!</label>
  <label kind="probability">3</label>    <!-- 17:3 = 85%:15% -->
  ...
</transition>
```

이러면 `Pr[<=T] (<> killed == MAXT)` 결과가 **"Pk=0.85 조건에서 전량 격추 확률
= 0.62 ± 0.01"** 같은 양적 답이 됩니다. ROS2 시뮬레이터의 "30번 돌려 평균 격추율
X%" 와 직접 비교 가능.

### 17.5 Hybrid (ODE) 표현 — sqrt/궤적 동적 계산?

SMC에선 **위치마다 clock slope를 다르게** 줄 수 있어서 ODE 표현이 부분 가능:
```c
// declaration
clock x_pos, y_pos;       // 위치 (clock으로 표현)

// Threat location Flight (invariant ...) 에:
// rate 명시 (위치별 dynamics)
//   x_pos' = SPD_X[id]        // dx/dt
//   y_pos' = SPD_Y[id]        // dy/dt
```
시간이 흐르면 `x_pos`/`y_pos`가 자동으로 적분됨. 거리 비교는 여전히 sqrt 못 쓰지만
`x_pos*x_pos + y_pos*y_pos <= R*R` 식으로 우회 가능.

다만 **state space는 더 폭발**. SMC는 정형 증명이 아닌 통계 추정이므로 state
space에 덜 민감하지만, 단순 통계 시뮬레이션은 빨라도 정확한 정형 보증은 약해짐.

### 17.6 SMC vs 기본 TCTL — 언제 무엇을 쓰나

| 목표 | 도구 |
|---|---|
| "절대 안 일어남" 정형 증명 (안전성) | **기본 TCTL** `A[] φ` |
| "결국 도달" 정형 증명 (라이브니스) | **기본 TCTL** `A<> φ`, `φ --> ψ` |
| "Pk 0.85에서 격추율 평균" 양적 분석 | **SMC** `E[...; N]` |
| "10초 안에 누설 확률 < 5%" 위험 분석 | **SMC** `Pr[<=10] (<> leaked>0)` |
| 시각화: 100 trace plot | **SMC** `simulate 100 [<=T] {...}` |
| 연속 위치/궤적 직접 표현 | **SMC** hybrid ODE (단, 검증 신뢰도는 통계적) |

### 17.7 권고 — 두 단계 워크플로

1. **기본 TCTL로 invariant 정형 증명** (v3의 19개 쿼리: 안전성, 충돌-자유, 채널
   한계, 우선순위 등) — "어떤 시나리오에서도 깨지지 않음" 보장.
2. **SMC로 양적 분석** (격추율, 누설 확률, 자원 소비 분포) — Pk와 시나리오
   variance를 반영한 실용 통계.

ROS2 시뮬레이터의 통계와 SMC 결과를 교차 비교하면 시뮬레이터 코드의 정합성도
간접 확인 가능. 예:
- ROS2: random scenario 100회 → 격추율 85%, 누설 0
- UPPAAL SMC: `E[<=75; 100] (max: killed)` → 28.4 (n_threats=30 기준 평균)
- 두 값이 ±오차 안에서 일치하면 정합

이 SMC 쿼리들은 **검증 가능한 자산**이라 v3 모델에 정식으로 추가할 만합니다.
원하시면 위 (1)~(4) + Pk 가중치 분기를 `dwta_model_v3_geometry.xml`에 박아드릴 수
있습니다.

---

## 18. UPPAAL 모델 편의 기능 — 인스턴스 자동화, Test Code, Exponential rate

§3의 System declarations에서 `SU0_0, SU0_1, SU1_0, SL0_0, SL0_1, SL1_0`을 하나씩
손으로 적어둔 게 어색했죠. UPPAAL은 **free parameter 자동 enumerate**를 지원해서
포대 수·채널 수만 바꾸면 인스턴스를 자동 생성할 수 있습니다. 그리고 Location
다이얼로그의 모든 옵션도 의미가 있습니다.

### 18.1 Process Array — `system` 한 줄로 인스턴스 자동 생성

**핵심 원리**: 템플릿 파라미터를 **bounded int 타입**으로 선언하고 `system` 절에
템플릿 이름만 적으면, UPPAAL이 그 도메인의 **모든 조합에 대해 프로세스를 자동 생성**.

#### 방법 A — 현재 v3 (명시적 list)
```c
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0); SU1_0 = Slot_U(1);
SL0_0 = Slot_L(0); SL0_1 = Slot_L(0); SL1_0 = Slot_L(1);
system R0, R1, R2, T0, T1, T2,
       SU0_0, SU0_1, SU1_0, SL0_0, SL0_1, SL1_0, P;
```
포대/채널이 늘면 손으로 추가해야 함.

#### 방법 B — Free parameter (자동 enumerate)
템플릿 파라미터 타입에 도메인을 명시하면 됩니다.

```c
// (1) 글로벌 declaration
const int MAXT     = 3;
const int NCH_U    = 3;             // 상층 채널 총 수 (CH_PER_U 합)
const int NCH_L    = 3;
const int batt_of_u[NCH_U] = {0, 0, 1};   // 슬롯 ch_id가 어느 포대인가
const int batt_of_l[NCH_L] = {0, 0, 1};

// (2) Threat / Radar 도 같은 패턴 — id를 bounded int로 선언:
//     template <Radar> parameter: const int[0, MAXT-1] id

// (3) Slot_U 템플릿 파라미터를 bounded int 채널 id로:
template <Slot_U>
  parameter: const int[0, NCH_U-1] ch_id;
  declaration: int batt_id = batt_of_u[ch_id];  // 내부에서 매핑
  // (나머지 location/transition은 batt_id로 그대로 사용)

template <Slot_L>
  parameter: const int[0, NCH_L-1] ch_id;
  declaration: int batt_id = batt_of_l[ch_id];

// (4) System declarations — 한 줄로 끝
system Radar, Threat, Slot_U, Slot_L, Planner;
```

UPPAAL 동작:
- `Radar` 파라미터 `id : int[0, MAXT-1]` → 자동으로 `Radar(0), Radar(1), Radar(2)`
- `Slot_U` 파라미터 `ch_id : int[0, NCH_U-1]` → 자동으로 `Slot_U(0), Slot_U(1),
  Slot_U(2)` 생성. 각 인스턴스 안에서 `batt_id = batt_of_u[ch_id]`로 포대 결정

#### 시나리오 변경 흐름 (Free parameter 적용 후)

"L1=6채널, L2=4채널, M1=5채널, M2=3채널"로 가고 싶을 때:

```c
const int NCH_U = 10;   // 6 + 4
const int NCH_L = 8;    // 5 + 3
const int batt_of_u[NCH_U] = {0,0,0,0,0,0, 1,1,1,1};   // 6개 + 4개
const int batt_of_l[NCH_L] = {0,0,0,0,0,   1,1,1};      // 5개 + 3개
const int CH_PER_U[NB_U]   = {6, 4};
const int CH_PER_L[NB_L]   = {5, 3};
const int AMMO0_U[NB_U]    = {12, 8};
const int AMMO0_L[NB_L]    = {15, 9};

// system은 변경 없음 — 그대로 한 줄
system Radar, Threat, Slot_U, Slot_L, Planner;
```
→ 18개 슬롯 인스턴스 자동 생성. v3를 free parameter 패턴으로 옮기면 시나리오
변경이 const 4줄로 끝남.

#### Trade-off

| 항목 | 명시적 list (v3 현재) | Free parameter |
|---|---|---|
| 인스턴스 추가 시 | 손으로 system 절 수정 | const 배열만 수정 |
| MSC 가독성 | 인스턴스 이름이 `SU0_0` 명확 | UPPAAL이 `Slot_U(0).Idle` 형태로 표시 |
| 디버깅 (특정 인스턴스 trace 추적) | 이름으로 바로 식별 | 인덱스로 식별 |
| 모델 컴파일 시간 | 동일 | 동일 (인스턴스 수가 동일하면) |
| 가독성 (다른 사람이 읽을 때) | 인스턴스화가 한눈에 | "어디서 인스턴스 정해지나" 한 번 더 찾아야 |

### 18.2 ROS2 헬퍼로 system declarations도 자동 dump

§15의 `dump_uppaal_windows`에 system 절 + batt_of 배열도 함께 출력하면 시나리오
한 줄로 v3 모델 update 완료. 다음 patch를 `scenario.py`에 추가하면 됩니다 (직접
편집해 드릴 수도).

```python
def dump_uppaal_system(NB_U, CH_PER_U, NB_L, CH_PER_L):
    """system declarations 텍스트 생성."""
    batt_u = []
    for b in range(NB_U):
        batt_u.extend([b] * CH_PER_U[b])
    batt_l = []
    for b in range(NB_L):
        batt_l.extend([b] * CH_PER_L[b])
    lines = [
        f"const int NCH_U = {sum(CH_PER_U)};",
        f"const int NCH_L = {sum(CH_PER_L)};",
        f"const int batt_of_u[NCH_U] = {{ {', '.join(map(str, batt_u))} }};",
        f"const int batt_of_l[NCH_L] = {{ {', '.join(map(str, batt_l))} }};",
        "// (template Slot_U parameter: const int[0,NCH_U-1] ch_id;",
        "//  declaration: int batt_id = batt_of_u[ch_id];)",
        "system Radar, Threat, Slot_U, Slot_L, Planner;",
    ]
    return "\n".join(lines)
```

### 18.3 Location 편집 다이얼로그의 모든 옵션

사용자가 본 다이얼로그의 모든 항목 의미:

| 항목 | 설명 | 우리 모델 사용 |
|---|---|---|
| **Name** | location 이름. 쿼리에서 `R0.Scan` 같이 참조 | 모든 location |
| **Invariant** | 시간 제약. 위반 시 위치 머무는 시간 강제 종료 | `t <= IMPACT_AT[id]` 등 |
| **Rate of Exponential** | **SMC 전용**. invariant 없는 location 머무는 시간이 지수분포 따를 때 그 rate λ. `Pr(t후 떠남) = 1 - e^(-λt)` | 안 씀 (결정적 invariant 사용) |
| **Initial** | 초기 location 여부 | Radar의 `Pre`, Threat의 `Inbound` 등 |
| **Urgent** | 시간 진행 금지 (즉시 다음 step) | 안 씀 |
| **Committed** | urgent + 다른 자동기보다 우선 처리 | `Ready` 위치 |
| **Comments 탭** | 주석. 모델 의미만 적음, 검증/시뮬레이션 무관 | 미사용 (XML주석으로 대체) |
| **Test Code 탭 — On enter** | location 진입 시 실행 코드. UPPAAL **Yggdrasil**(test case 생성 도구)이 사용 | 일반 검증엔 무시 |
| **Test Code 탭 — On exit** | location 이탈 시 실행 코드. Yggdrasil용 | 일반 검증엔 무시 |

#### Rate of Exponential — 언제 쓰나

invariant 없는 location에 머무는 시간을 **확률적**으로 모델링할 때:
```
rate = 2   →  평균 0.5초 머무름 (1/2)
rate = 1:5 →  rate r/q = 0.2 → 평균 5초 머무름
rate = 0   →  결정적 0초 (사실상 즉시 떠남)
```

우리 v3에 적용한다면:
- Slot_U.Flying의 invariant `f <= FLYOUT_U` 빼고 rate `1:5` 두면 → 비행시간이
  평균 5초 ± 분산의 지수분포가 됨. 실제 요격탄 비행시간이 발사 조건에 따라
  변동한다는 가정을 표현.
- 다만 invariant가 있어도 rate를 함께 두면 "invariant 한계 안에서 지수분포".
- 결정적 검증(`A[]`, `E<>`)에선 rate가 무시됨 → 비결정. SMC 쿼리에서만 효과.

#### Test Code — 언제 쓰나

UPPAAL **Yggdrasil**은 모델로부터 자동으로 **테스트 케이스를 생성**하는 도구.
On enter / On exit에 적은 코드가 생성된 테스트의 일부가 됨. 예:
```c
// On enter (Threat.Killed)
printf("Threat %d killed at time %f\n", id, t);
log_test_event("KILL", id);
```
이걸로 모델 → 외부 시스템(시뮬레이터·실제 ECU 등) 자동 테스트 가능. 우리 일반
검증/SMC 워크플로엔 무관. 비워두면 됨.

### 18.4 v3를 free parameter 패턴으로 옮길까?

장점: 시나리오 변경이 const 4줄로 끝남. 사용자 헬퍼 자동화에 적합.
단점: MSC에서 인스턴스가 `Slot_U(0)`, `Slot_U(1)`로 표시 → 어느 게 어느 포대의
몇 번째 채널인지 한 번 더 찾아야.

추천 워크플로:
1. **소규모 데모(13 인스턴스 이하, 현재 v3)** — 명시적 list 유지, 가독성 우위
2. **대규모 시나리오(20+ 인스턴스)** — free parameter로 자동화, `scenario.py`
   헬퍼와 통합

원하시면 v3를 free parameter 버전으로 (`dwta_model_v3_geometry_auto.xml` 같은
이름으로) 옮겨드리고, `scenario.py`에 `dump_uppaal_system()` 헬퍼도 추가하겠
습니다. 본 파일은 가독성 우위로 그대로 두고 자동 버전을 별도 파일로 추가.

---

## 19. Salvo(동시 다발) · 발당 Pk · 비행시간 jitter — 더 현실적인 교전 모사

현재 v3는 검증 가능성을 우선해 **단순화 3가지**를 채택했습니다:

| 측면 | v3 현재 | 한계 |
|---|---|---|
| 격추/실패 판정 | `hitU!` / `missU!` 비결정 분기 | "양쪽 trace 다 가능"만 검증, 격추율 양적 표현 X |
| 발사 패턴 | 위협당 포대당 1발(`upCnt_bt[b][t]==0` 가드) | Salvo(동시 다발 사격) 불가 |
| 비행시간 | `f >= FLYOUT_U` 결정적 5초 | 미사일마다 비행 jitter 없음 |

세 가지 모두 표현 가능합니다. SMC 빌드(§17)에서 가장 자연. 패턴을 정리합니다.

### 19.1 발당 Pk — 결정적 변수 + SMC 확률 가중치

#### 19.1.1 글로벌 declaration에 Pk 도입
```c
// (위협, 포대) 쌍별 명중률 — ROS2 시나리오에서 사전 계산
// 정수 표기: Pk × 100 (예: 0.85 → 85)
const int PK_U[MAXT][NB_U] = {
    {85, 80},   // 위협 0: 상층 포대 0=85%, 1=80%
    {78, 82},   // 위협 1
    {88, 75},   // 위협 2
};
const int PK_L[MAXT][NB_L] = {
    {72, 70},
    {75, 73},
    {68, 71},
};
```

#### 19.1.2 SMC 모드 — branching edge 확률 가중치
Slot_U의 Flying → Idle 전이를 둘로 갈라 가중치 부여:

```xml
<!-- hit 전이 -->
<transition>
  <source ref="su_fly"/><target ref="su_idle"/>
  <label kind="guard">f >= FLYOUT_U</label>
  <label kind="synchronisation">hitU[tgt]!</label>
  <label kind="probability">PK_U[tgt][batt_id]</label>      <!-- 새로 -->
  <label kind="assignment">inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--</label>
</transition>

<!-- miss 전이 -->
<transition>
  <source ref="su_fly"/><target ref="su_idle"/>
  <label kind="guard">f >= FLYOUT_U</label>
  <label kind="synchronisation">missU[tgt]!</label>
  <label kind="probability">100 - PK_U[tgt][batt_id]</label>
  <label kind="assignment">inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--</label>
</transition>
```

비율 `Pk : (100-Pk)`로 SMC가 무작위 선택. 이제 `Pr[<=40](<> killed==MAXT)`가
실제 Pk를 반영한 격추 확률을 반환.

#### 19.1.3 결정적 검증(기본 TCTL) 호환성
가중치는 SMC 쿼리(`Pr/simulate/E[]`)에서만 효과. 기본 TCTL(`A[]/E<>`)는 두 분기를
비결정으로 동등 취급 → §9의 19개 안전성 쿼리는 그대로 성립.

### 19.2 Salvo — 위협당 동시 다발 사격

#### 19.2.1 Salvo 한계 변수 도입
```c
const int MAX_SALVO_U = 2;   // 한 포대가 한 위협에 동시 발사 가능한 최대 발수
const int MAX_SALVO_L = 1;
```

#### 19.2.2 Slot_U 가드 완화
현재:
```c
ammoU_b[batt_id] > 0 && inflU_b[batt_id] < CH_PER_U[batt_id]
  && best_u_b(batt_id) >= 0 && t == best_u_b(batt_id)
```
변경 후 (Salvo 허용):
```c
ammoU_b[batt_id] > 0 && inflU_b[batt_id] < CH_PER_U[batt_id]
  && best_u_b_salvo(batt_id) >= 0 && t == best_u_b_salvo(batt_id)
```
새 함수:
```c
int best_u_b_salvo(int b) {
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] < MAX_SALVO_U) return i;
        i++;
    }
    return -1;
}
```
즉 한 포대가 한 위협에 **MAX_SALVO_U발까지 동시 비행** 가능. 채널 한계
(`inflU_b < CH_PER_U`)는 여전히 있어서 무한정은 아님.

#### 19.2.3 따라오는 효과
- 같은 plan! tick에서 한 포대가 한 위협에 두 발 동시 발사 (committed Ready에서
  best_u_b_salvo가 두 번 호출되면 같은 위협 반환)
- `inflU_b[b]`가 빠르게 채널 한계 도달 → 다른 위협 못 잡음 trade-off
- Pk 효과: 한 발만 맞으면 격추. 효과적 Pk = `1 - (1-Pk)^salvo_size`
- 새 보장: `A[] forall (b)(t) upCnt_bt[b][t] <= MAX_SALVO_U` (S5 갱신)

#### 19.2.4 효과적 Pk 검증 (SMC)
```c
// Salvo=2, Pk=0.85 가정 → 효과적 Pk = 1 - 0.15² = 0.9775
// SMC로 확인:
Pr[<=40] (<> killed == MAXT)
// 결과가 약 0.97 ± 0.01 나오면 정합
```

### 19.3 비행시간 jitter — 미사일마다 delay 다양화

#### 19.3.1 단순 비결정 (select)
```c
// declaration
const int FLYOUT_U_MIN = 4;
const int FLYOUT_U_MAX = 6;

// Slot_U.Flying invariant: f <= FLYOUT_U_MAX
// Flying -> Idle hit/miss 가드:
f >= FLYOUT_U_MIN
```
가드와 invariant 사이 구간에서 verifyta가 어떤 시점에 fire될지 비결정 선택 →
효과적 jitter 표현.

#### 19.3.2 SMC 모드 — 지수분포 또는 정규분포 근사
Flying에 `rate of exponential = 1` 두면 평균 1초 머무름. 결정적 + 확률 결합:
```
invariant: f <= FLYOUT_U_MAX
rate of exponential: 1    (평균 1초, 단 invariant까지)
```
또는 별도 location들로 정규분포 근사 (좀 복잡).

#### 19.3.3 슬롯별 launch jitter
같은 plan!에서 발사된 두 슬롯의 비행시간을 다르게 하려면:
```c
// Slot_U local declaration
int my_jitter;   // 인스턴스마다 다른 jitter

// Idle -> Ready committed 전이 assignment:
my_jitter = ch_id;  // ch_id가 free parameter면 자동으로 다름

// Flying -> Idle 가드:
f >= FLYOUT_U + my_jitter
```
free parameter 패턴(§18.1)과 결합하면 자동으로 슬롯별 다른 비행시간.

### 19.4 세 가지 합쳐서 — v4 모델 후보 스케치

`dwta_model_v4_salvo_pk.xml` (가칭) 의 핵심 추가:

```c
const int MAXT     = 3;
const int NB_U     = 2;
const int NB_L     = 2;
const int CH_PER_U[NB_U] = {3, 2};      // Salvo 위해 채널 약간 늘림
const int CH_PER_L[NB_L] = {3, 2};
const int FLYOUT_U_MIN = 4, FLYOUT_U_MAX = 6;   // jitter 윈도우
const int FLYOUT_L_MIN = 1, FLYOUT_L_MAX = 3;
const int MAX_SALVO_U = 2;
const int MAX_SALVO_L = 1;

// 위협별 포대별 명중률 (Pk × 100)
const int PK_U[MAXT][NB_U] = { {85, 80}, {78, 82}, {88, 75} };
const int PK_L[MAXT][NB_L] = { {72, 70}, {75, 73}, {68, 71} };

// (나머지 ammoU_b, inflU_b, upCnt_bt, engU_b 등 v3 그대로)

int best_u_b_salvo(int b) {
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] < MAX_SALVO_U) return i;
        i++;
    }
    return -1;
}
```

새 검증 쿼리:
```c
// (Safety) Salvo 한계
A[] forall (b : int[0,NB_U-1]) forall (t : int[0,MAXT-1])
   (upCnt_bt[b][t] <= MAX_SALVO_U)

// (Reachability) 같은 포대가 한 위협에 동시 2발
E<> exists (b : int[0,NB_U-1]) exists (t : int[0,MAXT-1])
   (upCnt_bt[b][t] == 2)

// (SMC) 효과적 격추율
Pr[<=40] (<> killed == MAXT)

// (SMC) 평균 격추 수
E[<=40; 200] (max: killed)

// (SMC) 평균 미사일 소비량 (= initial - remaining)
E[<=40; 200] (max: (AMMO0_U[0] - ammoU_b[0]) + (AMMO0_U[1] - ammoU_b[1]))
```

### 19.5 ROS2 시뮬레이터와의 정합

| ROS2 | UPPAAL v4 후보 |
|---|---|
| `Battery.base_pk` (포대 Pk) | `PK_U[t][b] / PK_L[t][b]` (위협별 Pk) |
| `FireControlRadarNode.HIT_THRESHOLD = 0.5` | SMC probability weight |
| `interceptor_flyout` 결정값 | `FLYOUT_U_MIN ~ MAX` 윈도우 또는 SMC rate |
| `LauncherNode`의 SLS(shoot-look-shoot) | Salvo (현재 ROS2는 비활성, v4에선 모델화) |
| ROS2 통계 "격추율 85%" | UPPAAL SMC `Pr[<=T](<> killed==MAXT)` |

### 19.6 만들어드릴까

§19의 패턴 셋(Pk + Salvo + jitter)을 적용한 **v4 모델 (`dwta_model_v4_salvo_pk.xml`)**
과 ROS2 측 헬퍼 확장(`dump_uppaal_pk()`, `dump_uppaal_system()`)을 한 묶음으로
만들어드릴 수 있습니다. 시작 시 결정 필요 사항:

- 검증 가능 규모: MAXT=3, NB_U=NB_L=2, sum(CH)=8~10 정도 (state space 안전)
- Salvo 크기: MAX_SALVO_U=2, MAX_SALVO_L=1 권장
- 모델 옵션: (a) v4 신규 파일 또는 (b) v3에 옵션 플래그
- 검증 쿼리: 기존 19개 + Salvo 1 + SMC 2~3 = 약 23개

원하시면 (a) 또는 (b) 선택만 알려주세요.

---

## 20. v4 모델 완전 walkthrough — `dwta_model_v4_salvo_pk.xml`

**구현 완료**: [`dwta_model_v4_salvo_pk.xml`](./dwta_model_v4_salvo_pk.xml). §19 패턴
(Salvo + 발당 Pk + 비행시간 jitter)을 그대로 적용한 v3 확장 모델. 13개 인스턴스에서
15개로 늘었고(상층 슬롯 +2, 하층 슬롯 +2), 검증 쿼리는 19개 → **23개**(Salvo 1 +
SMC 4 추가).

이 섹션은 **자연어 → 템플릿 단위 → 템플릿 내 노드** 순으로 모델을 풀어 설명합니다.

### 20.0 자연어로 본 v4 시스템

**우리가 표현하려는 것**:
*"여러 대의 탄도탄이 시간 차이를 두고 다가올 때, 두 종류(L-SAM 상층, M-SAM 하층)의
방어 포대들이 각자 사거리·고도 윈도우에 들어온 위협을 명중률(Pk)에 기반해 요격하되,
필요 시 한 위협에 한 포대가 여러 발을 동시 발사(Salvo)하고, 미사일마다 비행시간이
조금씩 다를 수 있다."*

**시스템 행위자(actor)** — 자연어로 정리하면 다섯 부류:

1. **Radar (감시·사격통제 통합 추상)** — 각 위협을 추적하면서 등장·사거리 진입·이탈·탄착 시각을 모든 컴포넌트에 broadcast.
2. **Threat (적 탄도탄)** — 자기 시간을 모르고 Radar 신호로 진행. hit/miss/impact 수신으로 종결.
3. **Slot_U / Slot_L (요격 채널 슬롯)** — 한 발 단위 발사 능력. plan?에 결심, Salvo 허용 안에서 best 위협 발사.
4. **Planner (계획수립)** — 일정 주기로 plan! broadcast.
5. **공유 상태** — 포대별 잔여탄·비행중·동시 추적 카운터·윈도우 플래그·종결 누계·총 발사 수.

이 5개 행위자를 UPPAAL 템플릿 5개로 1:1 매핑한 것이 v4.

### 20.1 글로벌 declaration이 표현하는 것

**자연어**: "위협 3발, 상층 포대 2개·채널 3/2, 하층 2개·채널 3/2. 상층 잔여탄 4/3, 하층 4/3. 위협별 등장·탄착 시각, (위협, 포대)별 윈도우와 Pk는 시나리오에서 사전 계산. 위협 한 대당 한 포대가 상층 최대 2발, 하층 1발 동시 발사. 비행시간 상층 4~6초, 하층 1~3초. 계획주기 2초."

```c
const int MAXT             = 3;
const int NB_U             = 2;
const int NB_L             = 2;
const int CH_PER_U[NB_U]   = {3, 2};
const int CH_PER_L[NB_L]   = {3, 2};
const int FLYOUT_U_MIN     = 4;  const int FLYOUT_U_MAX = 6;
const int FLYOUT_L_MIN     = 1;  const int FLYOUT_L_MAX = 3;
const int PERIOD_P         = 2;
const int MAX_SALVO_U      = 2;
const int MAX_SALVO_L      = 1;
const int PK_U[MAXT][NB_U] = {{85,80},{78,82},{88,75}};   // Pk × 100
const int PK_L[MAXT][NB_L] = {{72,70},{75,73},{68,71}};
```

**핵심 함수**:
```c
int best_u_b_salvo(int b) {
    int i = 0;
    while (i < MAXT) {
        if (engU_b[i][b] && upCnt_bt[b][i] < MAX_SALVO_U) return i;
        i++;
    }
    return -1;
}
```
v3 `best_u_b()`의 `== 0` → `< MAX_SALVO_U` 한 글자가 Salvo의 모든 것.

### 20.2 Radar 템플릿 — 시간 권위자 (v3와 동일)

**왜 이런 구조**: 위협 한 대 처음부터 끝까지 책임. 클럭 `t`로 시각 측정, invariant + guard 조합으로 정확한 시각 발사 강제.

**Pre** (초기) — invariant `t <= APPEAR[id]`
- 나가는 edge 1: `Pre → Scan`, guard `t == APPEAR[id]`, sync `detect[id]!`
  → 자연어: "APPEAR 시각 도달, '지금 등장' broadcast"

**Scan** (활성) — invariant `t <= IMPACT_AT[id]`
- 8 self-loop (포대별 enter/exit broadcast):
  * `enterU0[id]!` at `t==U_ENTER[id][0]` — "상층 포대 0 윈도우 진입"
  * `exitU0[id]!` at `t==U_EXIT[id][0]` — "상층 포대 0 윈도우 이탈"
  * (U1/L0/L1 동일 패턴 6개)
- 종결 edge: `Scan → Done`, guard `t == IMPACT_AT[id]`, sync `impact[id]!`

**Done** (sink) — 영원히 머묾.

**v4에서 변화**: 없음. Salvo/Pk는 슬롯 측 동작.

### 20.3 Threat 템플릿 — signal-driven consumer (v3와 동일)

**왜 이런 구조**: 자기 시간을 모름. Radar 신호로 토글, hit 한 발에 즉시 종결 (Salvo 두 발 비행 중이어도 한 발이면 끝).

**Inbound** (초기)
- `Inbound → Tracked`: sync `detect[id]?` — "탐지됨"
- `Inbound → Leaked`: sync `impact[id]?`, assign `leaked++` — "탐지 전 탄착"

**Tracked** (활성)
- 8 윈도우 toggle self-loop: `enterU0[id]?` → `engU_b[id][0]=true`, `exitU0[id]?` → `=false`, (U1/L0/L1 동일)
- 2 miss self-loop: `missU[id]?` / `missL[id]?` (무시, 재교전 대기)
- 2 격추 edge: `Tracked → Killed` on `hitU[id]?` 또는 `hitL[id]?`, assign 윈도우 정리 + `killed++`
  ⭐ Salvo로 두 발 비행 중이어도 hit 한 발에 종결. 다른 미사일 broadcast는 receiver 0 (Killed는 hit 무시).
- 탄착 edge: `Tracked → Leaked` on `impact[id]?`

**Killed/Leaked** (terminal sink)

**v4에서 변화**: 없음.

### 20.4 Slot_U 템플릿 — 상층 채널 (v4 핵심 변화 ⭐)

**왜 이런 구조**: 한 채널 = 한 발 능력. plan?에 결심, Salvo 허용 안에서 발사, 비행 후 Pk 기반 hit/miss.

`CH_PER_U = {3, 2}` → 인스턴스 5개 (SU0_0~2, SU1_0~1).

**Idle** (대기)
- `Idle → Ready`: sync `plan?` — "결심 시각"

**Ready** (committed, 시간 진행 0초)
- ⭐ **발사 edge** `Ready → Flying`:
  * select `t : int[0,MAXT-1]`
  * guard 분해:
    - `ammoU_b[batt_id]>0` : "내 포대 잔여탄"
    - `inflU_b[batt_id]<CH_PER_U[batt_id]` : "내 포대 채널 여유"
    - `best_u_b_salvo(batt_id)>=0` : "발사할 위협 존재"
    - `t==best_u_b_salvo(batt_id)` : "그 위협이 t (결정적)"
  * assign: `ammoU_b[batt_id]--, inflU_b[batt_id]++, upCnt_bt[batt_id][t]++, shots_u_fired++, tgt=t, f=0`
  * ⭐ v3 차이: `best_u_b_salvo`는 `upCnt_bt < MAX_SALVO_U` 가드 → 같은 위협 두 번째 발사도 통과
- **skip edge** `Ready → Idle`:
  * guard `best_u_b_salvo(batt_id)<0 || ammoU_b[batt_id]==0 || inflU_b[batt_id]>=CH_PER_U[batt_id]`

**Flying** (비행)
- invariant `f <= FLYOUT_U_MAX` ⭐ v3는 `f <= FLYOUT_U` 고정
- ⭐ **명중 edge** `Flying → Idle`:
  * guard `f >= FLYOUT_U_MIN` (jitter 윈도우 시작) ⭐ v3는 `f >= FLYOUT_U` 단일
  * sync `hitU[tgt]!`
  * ⭐ **probability `PK_U[tgt][batt_id]`** (SMC 가중치, v3엔 없음)
  * assign `inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]--`
- ⭐ **실패 edge** `Flying → Idle`:
  * guard `f >= FLYOUT_U_MIN`
  * sync `missU[tgt]!`
  * ⭐ **probability `100 - PK_U[tgt][batt_id]`**
  * assign 같음
- ⭐ jitter: `[FLYOUT_U_MIN, FLYOUT_U_MAX]` 안에서 fire 시각 비결정 → 같은 plan에 발사된 슬롯들도 결과 시각 다름

**v3와 차이 요약**:
1. `best_u_b` → `best_u_b_salvo`
2. invariant `FLYOUT_U` → `FLYOUT_U_MAX`
3. hit/miss guard `>= FLYOUT_U` → `>= FLYOUT_U_MIN`
4. hit/miss edge에 `probability` label 추가
5. 발사 assignment에 `shots_u_fired++` 추가

### 20.5 Slot_L 템플릿 — 하층 채널

Slot_U와 구조 동일, L-계열 변수 (`ammoL_b`, `inflL_b`, `loCnt_bt`, `FLYOUT_L_MIN/MAX`, `hitL/missL`, `PK_L`, `best_l_b_salvo`, `shots_l_fired`, `MAX_SALVO_L=1` 기본).

### 20.6 Planner 템플릿 — 주기 (v3와 동일)

**Tick** (유일 위치) — invariant `cp <= PERIOD_P`
- self-loop `Tick → Tick`: guard `cp >= PERIOD_P`, sync `plan!`, assign `cp=0`

### 20.7 System declarations

총 15 인스턴스. 헬퍼 `dump_uppaal_system()`이 자동 생성.

### 20.8 검증 쿼리 23개

| 그룹 | 개수 | 핵심 |
|---|---|---|
| Safety (S1~S8) | 8 | v3 + S5/S6의 `<=1`을 `<= MAX_SALVO_U/L`로 일반화 |
| Geometry (RD1/RD2) | 2 | v3 동일 |
| Timing (T1) | 1 | v3 동일 |
| Liveness (L1) | 1 | v3 동일 |
| Reachability (R1~R6) | 6 | v3 동일 |
| **Salvo (SV1)** | 1 | `E<> exists(b)(t) upCnt_bt[b][t]==MAX_SALVO_U` |
| **SMC (SMC1~SMC4)** | 4 | `Pr/E[...; 200]/simulate` |

### 20.9 사용 워크플로

```powershell
# 1) ROS2 시나리오에서 v4용 const 텍스트 생성
python -c "import sys; sys.path.insert(0,'ros2_dwta'); from dwta_nodes.scenario import dump_uppaal_windows, dump_uppaal_pk, dump_uppaal_system; print(dump_uppaal_windows(seed=42, n_threats=3)); print(); print(dump_uppaal_pk(seed=42, n_threats=3)); print(); print(dump_uppaal_system(seed=42, n_threats=3))"

# 2) v4 XML의 declaration / system 블록을 위 출력으로 교체

# 3) GUI에서 열기 (verifyta CLI도 가능)
# UPPAAL → File → Open → ros2_dwta\spec\dwta_model_v4_salvo_pk.xml
verifyta.exe -q ros2_dwta\spec\dwta_model_v4_salvo_pk.xml
```

### 20.10 ROS2 시뮬레이터와 정합

| ROS2 | UPPAAL v4 |
|---|---|
| `Battery.base_pk = 0.86` | `PK_U[t][b] = 86` (헬퍼 dump) |
| `LauncherNode` 단발 (현재) | `MAX_SALVO_U = 2` (의도적 강화) |
| `FCR.FLYOUT = 5` 결정 | `[FLYOUT_U_MIN, MAX] = [4, 6]` 윈도우 |
| ROS2 통계 "격추율 X%" | UPPAAL SMC `Pr[<=40] (<> killed==MAXT)` |
| ROS2 평균 발사 미사일 수 | `E[<=40; 200] (max: shots_u_fired + shots_l_fired)` |

v4 SMC와 ROS2 통계가 ±오차 안에서 일치하면 모델·시뮬레이터 정합.

---

## 부록 A. v3 모델 파일 구조 한눈에

```
<?xml ?>
<nta>
  <declaration>
    // §4.1(a) 시스템 상수
    // §4.1(b) 시나리오 윈도우
    // §4.1(c) 공유 상태
    // §4.1(d) Broadcast 채널
    // §4.1(e) 함수
  </declaration>

  <template><name>Radar</name>     ... (§5.1)
  <template><name>Threat</name>    ... (§5.2)
  <template><name>Slot_U</name>    ... (§5.3)
  <template><name>Slot_L</name>    ... (§5.4)
  <template><name>Planner</name>   ... (§5.5)

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

| 증상 | 어디를 확인 |
|---|---|
| 모델 안 열림 | XML well-formed? `python -m xml.dom.minidom ...` |
| 가드가 fire 안 됨 | committed 위치의 outgoing edge 가드가 배타적·합집합=전체 |
| `best_u_b`가 항상 -1 | `engU_b`가 true로 안 들어옴 → Radar의 enter* fire 시점 확인 |
| `inflU_b` 음수 | 발사/판정 `++/--` 균형 깨짐. 종결 시 reset 누락 |
| state space 폭발 | MAXT/NB/CH 줄이기 또는 invariant 단순화 |
| `plan!`이 안 발사됨 | P의 Tick invariant + guard 조합 확인 (§5.5.2) |
| 다른 자동기가 시간 멈춤 | urgent edge 또는 invariant 위반 확인 |

---

이 문서로 v2/v3 모델의 모든 요소를 추적할 수 있습니다. 추가 질문(특정 transition의
의미, 새 쿼리 추가, ROS2 시뮬레이터 결과와 trace 비교)은 §12(PoC) 또는 §11(매핑)
섹션을 출발점으로.
