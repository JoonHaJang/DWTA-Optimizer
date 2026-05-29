# UPPAAL 모델 동작 설계 문서

`dwta_model.xml` (SPEC) / `dwta_model_impl.xml` (IMPL) 두 모델의 **동작 방식**을
설명합니다. 검증 속성 표는 [`timed_automata.md`](./timed_automata.md)에 있고, 이
문서는 **MSC(Message Sequence Chart)·Simulator를 어떻게 읽는지**가 중심입니다.

---

## 1. 모델 한 장 요약

**5개 템플릿이 인스턴스화되어 함께 동작.** v2부터는 Radar가 위협별 timing을
소유하고 broadcast로 전 컴포넌트에 전파하며, Threat은 순수 signal consumer.

| Template | 인스턴스 수 | 역할 | 클럭 |
|---|---|---|---|
| `Radar(id)` | MAXT개 (T0~T2 짝) | 위협별 timing 소유, **detect/crossU/crossL/impact** broadcast | `t` (각자) |
| `Threat(id)` | MAXT개 | Radar 신호 받아 lifecycle 진행, hit/miss/impact로 종결 | 없음 (signal-driven) |
| `InterceptorU` | CH_U개 | 상층 유도채널 슬롯. plan? 받으면 Ready → 발사 또는 skip | `f` (각자) |
| `InterceptorL` | CH_L개 | 하층 유도채널 슬롯. 동일 패턴, FLYOUT_L 비행 | `f` |
| `Planner` | 1개 | PERIOD_P마다 `plan!` broadcast | `cp` |

기본 인스턴스화 (System declarations):
```c
R0=Radar(0); R1=Radar(1); R2=Radar(2);
T0=Threat(0); T1=Threat(1); T2=Threat(2);
U0=InterceptorU(); U1=InterceptorU();    // CH_U = 2
L0=InterceptorL(); L1=InterceptorL();    // CH_L = 2
P=Planner();
system R0,R1,R2, T0,T1,T2, U0,U1, L0,L1, P;
```
→ **MSC에 보이는 11개 세로줄(lifeline)**.

---

## 2. Broadcast 채널 — "누가 누구에게 무엇을"

UPPAAL의 `broadcast chan`은 한 명이 `chan!` 발사하면 그 채널을 listening하는
**모든 인스턴스가 동시에 수신**합니다 (수신자 0명이어도 OK).

| 채널 | sender | receiver | 의미 (실제 시스템 매핑) |
|---|---|---|---|
| `detect[id]` | `Radar(id)` | `Threat(id)` | "이 위협을 탐지하고 있음" (surveillance_radar /events: DETECTED) |
| `crossU[id]` | `Radar(id)` | `Threat(id)` | 상층 사거리 도달 (engageability_node가 상층 cell 발행) |
| `crossL[id]` | `Radar(id)` | `Threat(id)` | 하층 사거리 도달 (engageability_node가 하층 cell 발행) |
| `impact[id]` | `Radar(id)` | `Threat(id)` | 탄착 시각 (surveillance_radar /events: IMPACT) |
| `plan` | `Planner` | 모든 InterceptorU/L 4개 | 계획수립 주기 (planning_node /engagement_plan tick) |
| `hitU[id]` | `InterceptorU` | `Threat(id)` | 상층 요격 성공 (FCR /events: INTERCEPT) |
| `missU[id]` | `InterceptorU` | `Threat(id)` | 상층 요격 실패 (FCR /events: MISS) |
| `hitL[id]` | `InterceptorL` | `Threat(id)` | 하층 요격 성공 |
| `missL[id]` | `InterceptorL` | `Threat(id)` | 하층 요격 실패 |

> MSC에서 빨간 화살표가 그어지는 것은 항상 이 9가지 broadcast 중 하나입니다.
> 받는 쪽이 여러 명이면 같은 시점에서 여러 lifeline으로 동시에 도착 (예: `plan`은
> U0/U1/L0/L1 4개로).

---

## 3. 한 위협의 전체 lifecycle (시간순)

위협 1발이 들어와서 종결될 때까지 무슨 일이 어디서 일어나는지.

```
시간       Radar(0)              Threat(0)                Interceptor          Planner
─────  ─────────────────  ─────────────────────  ────────────────────  ──────
  t=0   Pre (waiting...)   Inbound                Idle                 Tick(cp=0)
         |                  |                      |                    | ↺ PERIOD_P
APPEAR  detect[0]! ────────►Tracked                ↓                    |
         Track                ↑ (clock x 없음)      |                    |
         |                  (다음 broadcast 기다림)|                    |
         |                                         |                    cp≥PERIOD_P
         |                                         |◄────plan! ───── plan!→Tick(cp=0)
         |                                       Ready (committed)     |
         |                                  best_u()=? -1 (engU[0]=F)  |
         |                                       Idle (skip)            |
         |                                         |                    |
CROSS_U crossU[0]! ────────►UpperEng                                    |
                            engU[0]=true                                |
                              |                                         |
                              |                              cp≥PERIOD_P 다시
                              |                                         |
                              |◄── plan? ──────── Idle→Ready (committed)
                                                  best_u()=0 (engU[0]=T)
                                              ammoU--, inflU++, upCnt[0]++
                                              tgt=0, f=0
                                                  Flying (f<=FLYOUT_U)
                                                     |
                                                  f≥FLYOUT_U
                                              hitU[0]! ──────────────►
                              Killed                  Idle (inflU--, upCnt[0]--)
                              killed++
```

핵심 포인트:
- **위협이 직접 시간을 안 쥡니다.** Radar가 `detect/crossU/crossL/impact` 신호를
  쏘면 그제서야 위협이 다음 위치로 진행합니다. Threat에는 clock이 없습니다.
- **Interceptor는 plan? 때만 발사 결심**합니다. plan이 와도 `engU[t]==false`거나
  `ammoU==0`이면 Ready → Idle로 **skip** 합니다(MSC에서 Ready → Idle이 자주 보이는 이유).
- **격추도 broadcast**(`hitU[id]!`)라 Threat과 같은 step에서 동시에 일어납니다.

---

## 4. 사용자가 본 스크린샷 해석

| MSC step | 무슨 일이 일어났는가 |
|---|---|
| 초기 | R0/R1/R2 = Pre, T0/T1/T2 = Inbound, U0/U1/L0/L1 = Idle, P = Tick. 모든 컴포넌트 대기. |
| `detect[0]` 화살표 (R0 → T0) | R0의 clock t가 APPEAR[0]=0에 도달 → 즉시 detect[0]! broadcast. T0가 Inbound → Tracked. R0는 Pre → Track. |
| 첫 `plan` 화살표 (P → U0/U1/L0/L1) | P의 cp가 PERIOD_P=2에 도달. plan! broadcast. U0/U1/L0/L1 네 개가 동시에 Idle → Ready (committed 위치이므로 시간 진행 없이 즉시 다음 step). |
| Ready들이 모두 Idle로 다시 돌아감 | best_u()=−1 (T0가 Tracked일 뿐 UpperEng 아님, engU[0]=false). 발사 조건 미충족 → "no GreedyWTA candidate" skip 전이 발화. 각 Interceptor가 Ready → Idle. 시간은 step 한 번에 진행. |
| 두 번째 `plan` (4초 후) | 같은 사이클 반복. T0가 아직 Tracked라 또 skip. |
| `detect[1]` (R1 → T1) | R1의 clock이 APPEAR[1]=4에 도달. T1 → Tracked, R1 → Track. |
| `crossU[0]` (R0 → T0) | R0의 clock이 CROSS_U[0]=6에 도달. T0 → UpperEng (engU[0]=true), R0 → UpperCovered. **이 시점부터 다음 plan에서 발사 가능**. |
| (스크린샷 잘림) 다음 plan에서 | U0 또는 U1이 best_u()=0를 인식 → Flying으로 전이 + hitU[0]! 또는 missU[0]! 예정. |

스크린샷의 **첫 동안 발사가 한 발도 안 나간 이유**: T0가 detect만 받았지 crossU를
못 받아서 engU=false. Interceptor는 plan을 받아도 발사 조건 미충족 → skip. 시간이
충분히 흘러 `crossU[0]`이 broadcast된 직후의 plan부터 실제 발사가 시작됩니다.

---

## 5. MSC 읽는 법

UPPAAL Concrete Simulator의 Message Sequence Chart는 통상 SDL/UML 시퀀스
다이어그램과 다음과 같이 다릅니다.

| 기호 | 의미 |
|---|---|
| 세로 막대 (lifeline) | 인스턴스 1개 (R0, T0, U0, ...) |
| 가로 빨간 화살표 | broadcast 발사 + 수신. **양쪽 lifeline 모두 같은 시점**에 다음 위치로 이동 |
| 박스 (Pre/Track/UpperEng/...) | 그 lifeline의 현재 위치(location). 박스가 새로 그려질 때마다 위치 전이 발생 |
| 박스 색 (옅은 회색) | committed 위치 (`Ready`). 시간 진행 없이 즉시 다음 전이 발생해야 함 |
| 박스 사이 빈 공간 | 시간 진행. 길이는 의미 없음 (UPPAAL은 step 수만 표시) |
| 빨간 화살표가 없는 박스 전이 | guard만으로 발화한 internal transition (예: Radar의 시간 가드 `t ≥ APPEAR[id]`) |

**시간**은 화살표 아래 표시되지 않습니다. Symbolic 시뮬레이션이라 "지금이 t=4.0"
같은 구체 시각은 안 나오고, **상대 순서**만 보장됩니다. 정확한 시각을 보고 싶으면
**Concrete Simulator** 탭으로 전환하면 변수 패널에 `R0.t = 6.0`, `P.cp = 1.4` 같은
실수값이 함께 표시됩니다.

---

## 6. 흔히 헷갈리는 동작 3가지

### (1) "plan을 받았는데 왜 발사 안 하나"
Ready(committed)에서 두 가지 outgoing edge가 있습니다:
- `Ready → Flying` (guard: `ammoU>0 && best_u()>=0 && t==best_u()`)
- `Ready → Idle` (guard: `best_u()<0 || ammoU==0`)

committed 위치는 시간 진행 없이 **둘 중 하나가 즉시** 발화해야 하니까, 첫 가드가
거짓이면 두 번째(skip)가 발화 → Ready 잠깐 보였다가 Idle로. MSC에서 자주 보이는
짧은 Ready 박스가 이 케이스입니다.

### (2) "왜 모든 Interceptor가 동시에 Ready로 가나"
`plan`이 broadcast이기 때문. Planner가 `plan!` 한 번 발사하면 4개 슬롯이 **모두**
Idle → Ready로 동시 전이. 그 다음 각자 best_u/best_l 계산해서 발사하거나 skip.

### (3) "hitU[0]! 직전에 위협 T0가 Killed로 안 가는데?"
broadcast 전이는 **양쪽이 같은 step에 동시에 이동**합니다. MSC에는 한 step 안의
순서가 위→아래로 그려지지만 실제 시간 차이는 0. T0의 Killed 박스는 Interceptor의
Flying → Idle 전이와 같은 시점에 표시됩니다.

---

## 7. 시나리오 → UPPAAL 정합

ROS2 시뮬레이터(`dwta_nodes/`)와 UPPAAL 모델은 다음 매핑으로 1:1입니다:

| ROS2 이벤트 | UPPAAL broadcast | 의미 |
|---|---|---|
| `surveillance_radar_node` /events: DETECTED | `Radar(id) detect[id]!` | 탐지 |
| `engageability_node`가 상층 cell 발행 | `Radar(id) crossU[id]!` | 상층 사거리 진입 |
| `engageability_node`가 하층 cell 발행 | `Radar(id) crossL[id]!` | 하층 사거리 진입 |
| `planning_node._tick` (2 Hz) /engagement_plan | `Planner plan!` | 계획수립 |
| `LauncherNode._on_plan`의 발사 | `InterceptorU/L Ready → Flying` | 발사 |
| `FireControlRadarNode.resolve` INTERCEPT/MISS | `hitU/L! / missU/L!` | 판정 |
| `surveillance_radar_node` /events: IMPACT | `Radar(id) impact[id]!` | 탄착 |

ROS2의 random_saturation_scenario(seed=42)에서 위협별 `APPEAR/CROSS_U/CROSS_L/
IMPACT_AT` 시각을 추출해 모델 declaration의 const 배열에 주입하면, **두 도구가 같은
시나리오로 PoC**를 돌릴 수 있습니다 (헬퍼는 별도 작업으로 추가 가능).

---

## 8. PoC 활용 레시피

### (A) GUI로 한 step씩 따라가기 (가장 직관적)
```
1. UPPAAL 실행 → File→Open → dwta_model.xml (또는 _impl)
2. "Symbolic Simulator" 탭
3. Reset 누른 다음 enabled transition을 하나씩 클릭
4. 우측 Variables 패널에서 ammoU/inflU/engU/killed 변화 관찰
5. Trace 영역에 MSC가 자동 누적됨
```

### (B) verifyta로 trace 자동 생성
```powershell
# R1 = "전량 격추 가능" trace 생성 (가장 좋은 시나리오)
verifyta.exe -t 1 -f r1 ros2_dwta\spec\dwta_model_impl.xml
# 생성된 r1.xtr를 GUI의 File→Open trace로 로드 -> MSC가 그 trace로 채워짐
```

### (C) 자주 보고 싶은 trace
- **R3 (다층요격)**: 같은 위협 id에 hitU[i]!와 hitL[i]! 둘 다 발화하는 trace
- **R4 (누설)**: 위협 lifecycle이 `impact[id]?`로 Leaked에 도달하는 trace
- **D3 (우선순위)**: best_u()가 작은 id를 먼저 선택했음을 보여주는 trace

---

## 9. 참고: 이 모델이 다루지 않는 것

이 모델은 형식 검증에 집중해서 다음은 **의도적으로 추상화**되어 있습니다.

- 위협 **위치/궤적**: 시간 임계로 환원 (`CROSS_U[id]` 한 변수에 거리 정보가 압축)
- **Pk 확률**: `hitU!`/`missU!` 비결정 분기 (양쪽 trace 모두 검증). 실제 0.85
  Pk가 95% 확률로 격추한다는 통계적 추론은 안 함 → SMC(Stratego) 필요
- **다포대 차이**: 상층 두 포대(L1/L2)를 InterceptorU 인스턴스 두 개로 추상,
  포대별 사거리/위치 차이는 없음. 다포대 충돌-자유는 `upCnt[t]<=1` 가드만
- **CleanSlate MIP 해**: WTA 결과 자체는 best_u/best_l 순서로 추상

이 한계 안에서 모델이 보장하는 것: **타이밍·자원·생명주기·충돌-자유**의
모든 정형 속성 (16~18개 TCTL 쿼리).

---

## 10. `clean_slate_optimizer.py`는 UPPAAL과 어떻게 연결되나?

**짧은 답: UPPAAL은 그 파이썬 코드를 호출하지 않습니다.** Python 함수, MIP solver
(HiGHS), 부동소수 계수 같은 것은 UPPAAL이 다룰 수 있는 영역이 아니에요.

### 왜 직접 안 쓰는가
1. UPPAAL은 **finite-state timed automata** 검증기. `int`/`bool`/`clock`만 압니다.
   HiGHS의 LP/MIP 해는 실수·정수 변수와 행렬 조작이 필요해 모델 컴파일 자체가 불가.
2. CleanSlate가 만드는 **한 번의 할당 결정**은 사실 수십~수백 정수 변수의 최적해입니다.
   이걸 그대로 모델에 박으면 state space가 폭발해서 verifyta가 못 끝납니다.
3. UPPAAL의 본업은 "**어떤 합리적 결정자든 만족해야 할 안전성·라이브니스**" 검증.
   특정 옵티마이저의 정수 해 그 자체가 아니라 **그 옵티마이저가 따르는 규칙**을
   검증해야 합니다.

### 그래서 어떻게 "연결" 되어 있나
두 단계로 추상화해서 연결합니다.

**1단계 — 정책의 본질만 추출**
`clean_slate_optimizer.GreedyOptimizer.solve()` / `CleanSlateOptimizer.solve()`의
공통 규칙을 의미적으로 압축하면 이렇게 됩니다.
```python
# 의사 코드 (실제 CleanSlate는 MIP로 한 방에 풀지만 의미는 같음)
for threat in sorted(threats, key=danger, reverse=True):     # ① 우선순위
    if upper_feasible(threat) and not upper_already_locked(threat):  # ② 충돌 회피
        assign_upper(threat)
    if lower_feasible(threat) and not lower_already_locked(threat):
        assign_lower(threat)                                  # ③ 다층요격 허용
```
이 세 규칙 — **(1) danger DESC 우선순위 / (2) 위협당 계층별 1포대 / (3) 다층요격** —
이 옵티마이저 종류와 무관한 **policy invariant**입니다.

**2단계 — IMPL 모델에 그 규칙만 내장**
`dwta_model_impl.xml`의 declaration:
```c
int best_u() {                  // ① 작은 id (= danger DESC 추상) 우선
    int i = 0;
    while (i < MAXT) {
        if (engU[i] && upCnt[i] == 0) return i;   // ② upCnt==0 가드로 충돌 회피
        i++;
    }
    return -1;
}
```
그리고 Interceptor의 발사 가드:
```c
ammoU > 0 && best_u() >= 0 && t == best_u()
```
이게 **CleanSlate의 모든 핵심 규칙을 정수-only로 추상**한 모델입니다.

### 결과: 어떤 보장이 따라오나
모델은 옵티마이저의 *해 그 자체*를 검증하지는 못하지만, **옵티마이저가 따르는 규칙
하에서** 다음을 정형 보증합니다.

- (S5/S6) `upCnt[t] ≤ 1`, `loCnt[t] ≤ 1` — 어떤 시나리오에서도 한 위협에 같은 계층
  포대가 두 발 들어가는 일은 없음 → CleanSlate가 만든 어떤 trace에도 성립
- (D3/D4) "더 위협적인 위협이 살아있는데 덜 위협적인 위협을 먼저 잡는" trace는
  존재할 수 없음 → CleanSlate의 우선순위 일관성 정형 보증
- (RD1/RD2) `upCnt[t] > 0` 이면 반드시 `engU[t] = true` → CleanSlate가 만든 모든
  할당은 탐지·사거리 도달 후에만 발사 (시뮬레이터 코드의 "탄착 전 발사 금지" 제약과 동등)

### 정합성을 어떻게 점검하나
두 도구의 결과를 **같은 시나리오에서** 교차 비교:

```
[ROS2 시뮬레이터]                          [UPPAAL]
random_saturation_scenario(seed=42)        const APPEAR/CROSS_U/CROSS_L 배열에
  ↓                                        같은 seed에서 추출한 값을 주입
CleanSlateOptimizer가 매 plan!마다 푼다     ↓
  ↓                                        verifyta -q dwta_model_impl.xml
ROS2 trace: "격추 34/0 누설, 다층 9구간"     ↓
                                           "16~18개 TCTL 속성 모두 satisfied"
```
- ROS2 trace의 모든 step이 UPPAAL의 안전성 속성을 어기지 않아야 함 → 정합
- UPPAAL이 발견한 반례(누설 가능 등)는 ROS2에서 동일 seed로 재현되어야 함

### 다른 옵티마이저(GA, MIP, Greedy)도 같은 방식
세 정책 모두 위 (1)(2)(3) invariant를 공유합니다. 그래서 ROS2의 백엔드를
`GeneticAlgorithmOptimizer`나 `GreedyOptimizer`로 바꿔도 **UPPAAL IMPL 모델은
재사용 가능**합니다. 모델은 "CleanSlate의 모델"이 아니라 "**우리 프로젝트의
WTA 정책을 따르는 어떤 옵티마이저든 만족하는 모델**"입니다.

> 정리: UPPAAL이 검증하는 것은 옵티마이저의 **해**가 아니라 그 **정책의 골격**.
> 정책 골격이 동일하다면 옵티마이저가 무엇이든 같은 정형 보증이 따라옵니다.
> 옵티마이저의 진짜 해는 ROS2 시뮬레이터가 매 tick에서 실측하고, UPPAAL이 미리
> 정형 보증한 invariant를 그 trace가 어기지 않는지 검증합니다.

---

## 11. 궤적·고도 기반 교전대 (사거리 + 고도 동시 게이트)

v2 모델은 위협별 timing을 `ENTER_U` / `ENTER_L` 한 점으로 압축해서 "언제부터 상층/
하층 교전대"인지만 표현했습니다. 실제 탄도탄은 **포물선 궤적 + 고도 윈도우**가
있어서 "사거리 안" ∧ "고도 안"을 둘 다 만족해야 사격 가능합니다.

UPPAAL은 sqrt/sin/cos 같은 연속 동역학을 못 다룹니다 (clock = 시간 정수만). 그렇지만
**사거리 + 고도 둘 다의 교집합을 시간 윈도우로 사전 계산**하면 모델 안에서는 정수
배열만 다루므로 정합 그대로 표현됩니다.

### 1단계 — ROS2 시나리오에서 윈도우 사전 계산

매 위협마다 발사 위치 / 속도 / 정점 고도가 정해지면 궤적이 결정되고, 포대마다
사거리·고도 윈도우의 교집합은 한 구간 `[enter, exit]`로 떨어집니다.

```python
# ros2_dwta/dwta_nodes/scenario.py  (의사 코드)
import math

def compute_engagement_window(threat, battery):
    """위협 궤적 × 포대 (사거리 + 고도) 게이트의 교집합 -> [enter_s, exit_s]."""
    flight_time = math.hypot(*[i - l for i, l in
                                zip(threat.impact_xy, threat.launch_xy)]) / threat.speed
    enter, exit_ = None, None
    # 100Hz 등 충분히 잘게 샘플링해서 두 게이트의 AND를 만족하는 첫/마지막 시각
    n = int(flight_time / 0.01) + 1
    for i in range(n):
        t = i * 0.01
        x = lerp(threat.launch_xy[0], threat.impact_xy[0], t / flight_time)
        y = lerp(threat.launch_xy[1], threat.impact_xy[1], t / flight_time)
        # 포물선: h(t) = 4 * MAX_ALT * (t/T) * (1 - t/T)
        h = 4 * threat.max_alt_km * (t / flight_time) * (1 - t / flight_time)
        d = math.hypot(x - battery.position[0], y - battery.position[1])
        in_range = d <= battery.engagement_range
        in_alt   = battery.alt_min_km <= h <= battery.alt_max_km
        if in_range and in_alt:
            enter = t if enter is None else enter
            exit_ = t
    return (round(enter, 1), round(exit_, 1)) if enter is not None else None
```

L-SAM은 외기권/대기권 위쪽 (고도 40~150 km), M-SAM은 대기권 (고도 5~40 km) 같이
**고도가 서로 다른 윈도우**라 자연스럽게 분리됩니다.

### 2단계 — UPPAAL declaration에 const 배열로 주입

UPPAAL은 다차원 정수 배열 지원합니다.

```c
const int MAXT  = 3;
const int NB_U  = 2;             // 상층 포대 수 (L1_LSAM, L2_LSAM)
const int NB_L  = 2;             // 하층 포대 수 (M1_MSAM, M2_MSAM)

// (위협, 포대)쌍의 effective window 시작/끝 시각.
// -1 = "이 포대로는 절대 교전 불가" sentinel.
const int U_ENTER[MAXT][NB_U] = { { 8, -1}, {12, 10}, {-1, 14} };
const int U_EXIT [MAXT][NB_U] = { {22, -1}, {24, 26}, {-1, 28} };
const int L_ENTER[MAXT][NB_L] = { {15, 17}, {19, 21}, {22, 24} };
const int L_EXIT [MAXT][NB_L] = { {30, 30}, {30, 32}, {32, 34} };
```

### 3단계 — Radar 템플릿에서 윈도우 신호로 broadcast

```
Radar(id) — 위치 시퀀스 (시간이 흐르며 한 위치씩 전이)

Pre   ─[t≥APPEAR[id]]    detect[id]!────►  Scan_t0
Scan_tk ─[t≥W_k(b)]      enterU[id][b]!──► Scan_tk+1   // 포대 b 윈도우 진입
Scan_tk ─[t≥W_k(b)]      exitU[id][b]!───► Scan_tk+1   // 포대 b 윈도우 이탈
... (포대 × 4종 신호의 시간순)
Scan_last ─[t≥IMPACT_AT] impact[id]!──►   Done
```

윈도우 enter/exit 신호 4종(`enterU[id][b]`, `exitU[id][b]`, `enterL[id][b]`,
`exitL[id][b]`)을 한 Radar가 시간 순서대로 발사합니다. 위치 한 개로 다 표현하려면
`select b : int[0,NB_U-1]`로 가드 분기하는 트릭도 가능.

### 4단계 — Threat의 engU/engL을 포대 단위로 토글

```c
bool engU_b[MAXT][NB_U];    // (위협, 상층 포대) 교전 가능?
bool engL_b[MAXT][NB_L];    // (위협, 하층 포대) 교전 가능?
```

Threat 템플릿 (signal-driven, 위치 분리 없이 self-loop로 토글):
```
Inbound  ─ detect[id]?            ─► Tracked
Tracked  ─ enterU[id][b]? / engU_b[id][b]=true   ─► Tracked (self)
Tracked  ─ exitU[id][b]?  / engU_b[id][b]=false  ─► Tracked (self)
Tracked  ─ enterL[id][b]? / engL_b[id][b]=true   ─► Tracked (self)
Tracked  ─ exitL[id][b]?  / engL_b[id][b]=false  ─► Tracked (self)
Tracked  ─ hitU[id]? ─► Killed (모든 engU_b/engL_b 초기화, killed++)
Tracked  ─ hitL[id]? ─► Killed
Tracked  ─ missU[id]? / missL[id]? ─► Tracked (재교전)
Tracked  ─ impact[id]? ─► Leaked
```

### 5단계 — Interceptor 가드를 (위협, 포대) 단위로

기존 `engU[t]`를 `engU_b[t][batt_id]`로 바꾸면 됩니다. 포대 b의 슬롯이 발사하려면
**그 포대 자신의 사거리·고도 게이트**가 살아 있어야 합니다.
```c
// InterceptorU.Ready -> Flying 가드 (포대별 인스턴스)
ammoU_b[batt_id] > 0
  && inflU_b[batt_id] < CH_PER_U[batt_id]
  && exists (t : int[0,MAXT-1]) (engU_b[t][batt_id] && upCnt_bt[batt_id][t] == 0)
```

이렇게 하면 자동으로 다음 검증 속성이 따라옵니다.
- **고도 게이트 일관성**: `A[] (upCnt_bt[b][t] > 0 imply engU_b[t][b])` — 사거리·고도
  벗어난 위협에 발사 trace 없음
- **윈도우 이탈 회복**: `exitU[id][b]?`가 와도 위협이 종결 안 되고 다른 포대 윈도우로
  넘어갈 수 있음 (다포대 효과)

### v2 와의 비교

| 항목 | v2 (현재 모델) | v3 (이 패턴) |
|---|---|---|
| 위협당 교전대 | 시간 임계 한 점 (`ENTER_U`) | 포대별 시간 윈도우 (`U_ENTER[id][b]`/`U_EXIT[id][b]`) |
| 고도 영향 | 모델 밖 | 사거리×고도 교집합으로 사전 계산되어 윈도우에 반영 |
| 포대 차이 | 인스턴스 수만 (`CH_U`) | 포대별 윈도우 + 사정거리 + 고도대 |
| const 배열 | 1D `[MAXT]` | 2D `[MAXT][NB_U]` |
| 검증 시간 | 빠름 | 약간 늦음 (state space 약간 큼) |

---

## 12. 포대별 동시 교전 수 (6대 등)

v2 모델은 `InterceptorU` 인스턴스 수 = `CH_U` 한 숫자로, "상층 채널 전체 합"만
표현했습니다. 사용자가 원한 "L1_LSAM 6대 + L2_LSAM 4대" 같은 **포대별 독립 채널
풀**은 인스턴스를 포대 단위로 분리해 표현합니다.

### 핵심 패턴 — Slot 인스턴스에 batt_id 부여

```c
const int NB_U          = 2;
const int CH_PER_U[NB_U] = {6, 4};      // L1=6, L2=4
const int ammoU_init[NB_U] = {12, 8};

int inflU_b[NB_U];                       // 포대별 비행 중 카운터
int ammoU_b[NB_U] = {12, 8};             // 포대별 잔여탄
int upCnt_bt[NB_U][MAXT];                // (포대, 위협) -- 충돌 회피용

template Slot_U {
    parameter const int batt_id;
    clock f;
    int tgt;

    loc Idle
    loc Ready (committed)
    loc Flying (invariant f <= FLYOUT_U)
    init Idle

    Idle  ─ plan?  ─► Ready

    Ready ─ select t : int[0,MAXT-1]
            [ ammoU_b[batt_id] > 0
              && inflU_b[batt_id] < CH_PER_U[batt_id]
              && engU_b[t][batt_id]
              && upCnt_bt[batt_id][t] == 0
              && t == best_u_b(batt_id)        // 우선순위 추상 (포대 단위)
            ] / ammoU_b[batt_id]--, inflU_b[batt_id]++, upCnt_bt[batt_id][t]++,
                tgt=t, f=0
          ─► Flying

    Ready ─ [no feasible target] ─► Idle

    Flying ─ [f>=FLYOUT_U] hitU[tgt]! / inflU_b[batt_id]--, upCnt_bt[batt_id][tgt]-- ─► Idle
    Flying ─ [f>=FLYOUT_U] missU[tgt]! / 같음 ─► Idle
}
```

### System declarations에서 채널 수만큼 인스턴스화

```c
// L1_LSAM: 6 channels (batt_id=0)
SU0_0 = Slot_U(0); SU0_1 = Slot_U(0); SU0_2 = Slot_U(0);
SU0_3 = Slot_U(0); SU0_4 = Slot_U(0); SU0_5 = Slot_U(0);
// L2_LSAM: 4 channels (batt_id=1)
SU1_0 = Slot_U(1); SU1_1 = Slot_U(1); SU1_2 = Slot_U(1); SU1_3 = Slot_U(1);
// ... (Slot_L 동일)
system SU0_0, ..., SU0_5, SU1_0, ..., SU1_3, ...;
```

총 슬롯 수 = `sum(CH_PER_U) + sum(CH_PER_L)` = 6 + 4 + 4 + 2 = 16 인스턴스 (예시).
MAXT=3과 합쳐 약 25개 lifeline → MSC 가독성은 떨어지지만 **검증 가능 범위**.

### 따라오는 보장

```c
// (Safety) 포대별 동시 비행 ≤ 그 포대 채널
A[] forall (b : int[0,NB_U-1]) (inflU_b[b] <= CH_PER_U[b])

// (Safety) 포대별 잔여탄 음수 불가
A[] forall (b : int[0,NB_U-1]) (ammoU_b[b] >= 0)

// (Safety) 한 위협에 같은 포대가 두 발 안 들어감
A[] forall (b : int[0,NB_U-1]) forall (t : int[0,MAXT-1]) (upCnt_bt[b][t] <= 1)

// (Reachability) 두 포대가 동시에 가동되는 trace 존재 (부하 분산)
E<> (inflU_b[0] > 0 && inflU_b[1] > 0)

// (Reachability) 포대 b가 채널 한계까지 꽉 차는 trace 존재
E<> (inflU_b[0] == CH_PER_U[0])
```

### 상한 추정 — 어디까지 키울 수 있나

UPPAAL state space는 인스턴스 수와 변수 도메인의 곱이라 다음 한계를 권합니다.

| MAXT | NB_U+NB_L | sum(CH) | 총 lifeline | 검증 시간 (목 표 기준) |
|---|---|---|---|---|
| 2 | 2 | 4 | ~10 | 초 단위 |
| 3 | 2 | 8 | ~15 | 수십 초 |
| 3 | 4 | 16 | ~25 | 분 단위 |
| 5 | 4 | 20 | ~35 | 십수 분 또는 timeout |

대규모 시나리오(MAXT=30 같은 ROS2 PoC)는 UPPAAL 한 모델로 다 검증 불가. 대신
**규모를 줄인 대표 시나리오**로 invariant를 정형 보증하고, 그 보증을 ROS2가 만든
대규모 trace에 일반화해서 적용하는 게 표준 방법입니다.

---

이 §11 / §12 패턴을 그대로 적용한 **`dwta_model_v3_geometry.xml`** (2D 윈도우 +
포대별 슬롯 + 검증 쿼리)을 별도 파일로 만들고 싶으시면 알려주세요. 모델 컴파일과
verifyta 가능 여부까지 함께 확인하겠습니다.
