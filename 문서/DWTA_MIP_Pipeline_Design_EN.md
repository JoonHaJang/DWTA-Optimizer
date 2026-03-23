# DWTA-MIP: Pipeline Design, Analysis Checklist, and Bitmask Implementation Guide

---

## Part 1 — Recommended Full Pipeline

### 1.1 Data Type Contract (Per Phase)

The following defines the concrete Python types flowing through the pipeline.
Types marked ✅ are grounded in the paper's measured data.
Types marked ⚠️ depend on design decisions not yet finalized in the paper.

```
┌─────────────────────────────────────────────────────────────────────┐
│ SYSTEM INPUTS                                                       │
│                                                                     │
│  threats    : list[ThreatState]     # position, velocity, type      │
│  batteries  : list[BatteryState]    # position, ammo, layer         │
│  B          : dict[int, float]      # asset_id → value  ⚠️ undefined│
│  params     : dict[str, float]      # Pk, C_j, M_j, k_min, k_max   │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Phase 1 — CSR + Bitmask Feasibility Filter  ③

**Purpose**: Reduce the problem from dense (`|T| × |J|`) to sparse (`ρ · |T| × |J|`).

**Inputs**:
```python
threats:      list[ThreatState]
batteries:    list[BatteryState]
R:            dict[int, float]          # R[j] = engagement range of battery j
TW:           dict[tuple, tuple]        # TW[(i,j)] = (t_start, t_end) or None
```

**Computation**:
```
For each (i, j):
  1. Compute d_ij(t) — Euclidean distance at current time step
  2. Check d_ij(t) <= R[j]             → range filter
  3. Check TW[(i,j)] is not empty      → time-window filter
  4. If both pass → mark (i,j) feasible

Bitmask cache (for repeated re-optimization):
  feasible_mask[j] = uint64 bitmask over threat indices
  update on new threat arrival: feasible_mask[j] |= (1 << i)
  update on threat departure:   feasible_mask[j] &= ~(1 << i)
```

**Outputs**:
```python
feasible_pairs  : list[tuple[int, int]]     # [(i,j), ...]
pair_to_col     : dict[tuple[int,int], int] # (i,j) → column index
feasible_mask   : dict[int, int]            # battery_j → uint64 bitmask ← NEW
A_feasibility   : scipy.sparse.csr_matrix  # shape: (n_constraints, n_pairs)
```

**Execution**: Sequential (all downstream phases depend on this output)

---

### Phase 2A — FBBT: Variable Pre-fixing  ①

**Purpose**: Permanently fix `x_ij = 0` for logically impossible assignments before
Branch-and-Bound starts, reducing the B&B search space by ~66% on average. ✅ paper §4

**Inputs**:
```python
feasible_pairs  : list[tuple[int, int]]
M               : dict[int, int]    # M[j] = remaining ammo at battery j
m               : int               # missiles per salvo = 2
confirmed_count : dict[int, int]    # confirmed_count[j] = already-confirmed engagements
```

**Computation**:
```
For each (i, j) in feasible_pairs:
  If confirmed_count[j] * m + m > M[j]:
      → x_ij = 0  (adding this engagement would exceed ammo)
  If TW[(i,j)] is now empty (re-check after time advance):
      → x_ij = 0
```

**Outputs**:
```python
fixed_zero   : set[tuple[int, int]]          # pairs fixed to x_ij = 0
active_pairs : list[tuple[int, int]]         # feasible_pairs - fixed_zero
```

**Execution**: Sequential (depends on Phase 1 output), $O(|\text{feasible\_pairs}|)$

---

### Phase 2B — OBBT: K-factor Bound Tightening  ④

**Purpose**: Narrow each `k_ij` interval below `[0.6, 1.0]` by solving two small LPs,
then update McCormick envelope bounds accordingly.

**Inputs**:
```python
active_pairs    : list[tuple[int, int]]
k_global_bounds : tuple[float, float]   # (0.6, 1.0)  ✅ paper §3.1.3
current_constraints : list              # all active constraints at this node
```

**Computation**:
```
For each (i, j) in active_pairs (independently):
  k_min_ij = min k_ij  s.t. current_constraints
  k_max_ij = max k_ij  s.t. current_constraints
```

**Outputs**:
```python
k_bounds : dict[tuple[int,int], tuple[float, float]]
# k_bounds[(i,j)] = (k_min_ij, k_max_ij) ⊆ [0.6, 1.0]
# Exact values depend on scenario — must be measured experimentally ⚠️
```

**Execution**: Each LP is independent → **parallel across pairs**
```python
with ThreadPoolExecutor(max_workers=4) as ex:
    futures = {ex.submit(solve_obbt_lp, pair): pair for pair in active_pairs}
    k_bounds = {pair: f.result() for pair, f in futures.items()}
```

---

### Phase 3A — Piecewise McCormick Constraint Generation  ⑤

**Purpose**: Split each `k_ij` range into 2 sub-intervals, apply a tighter McCormick
envelope to each. Reduces LP relaxation gap from 0.16 → 0.04. ✅ derived

**Inputs**:
```python
active_pairs : list[tuple[int, int]]
k_bounds     : dict[tuple, tuple[float,float]]   # from Phase 2B
P            : dict[int, float]                  # P[j] = Pk of battery j
```

**Computation**:
```
For each (i, j):
  mid = (k_min_ij + k_max_ij) / 2
  intervals = [(k_min_ij, mid), (mid, k_max_ij)]

  For each interval (lo, hi):
    Generate 4 McCormick inequalities with bounds (lo, hi)
    → 8 inequalities total per pair (vs. 4 in original)

  Add binary variable z_ij to select active interval
```

**Outputs** (MIP model components):
```python
# Variable index maps
x_vars : dict[tuple[int,int], int]    # binary,     col index
k_vars : dict[tuple[int,int], int]    # continuous, col index
w_vars : dict[tuple[int,int], int]    # continuous, col index
z_vars : dict[tuple[int,int], int]    # binary,     col index (NEW vs. original)

# Constraint matrix
A_mccormick : scipy.sparse.csr_matrix
b_mccormick : np.ndarray
sense       : list[str]               # '<=' or '>='
```

**Execution**: Sequential (depends on OBBT output)

---

### Phase 3B — Huffman Binary Tree Reconstruction  ⑨

**Purpose**: Reorder the binary tree used for linearizing the survival probability product
`∏(1 - w_t)` so that high-value asset threats are processed near the root,
improving the quality of B&B initial upper bounds.

**Inputs**:
```python
B            : dict[int, float]         # asset value ⚠️ must be defined
threat_asset : dict[int, int]           # threat_i → asset_id
```

**Computation**:
```
Standard Huffman algorithm:
  heap entries = [(B[threat_asset[i]], i) for i in threats]
  heapify → repeatedly merge two lowest-weight nodes
  → produces a binary tree minimizing WPL = Σ B_i · d_i

Time complexity: O(|T| log |T|)   ✅ runs once per re-optimization cycle
```

**Outputs**:
```python
tree_root    : HuffmanNode
node_order   : list[tuple[int,int]]   # internal node processing order
                                      # used to sequence McCormick applications
```

**Execution**: Independent of Phase 3A and 3C → **parallel with them**

---

### Phase 3C — Valid Inequalities Insertion  ⑦

**Purpose**: Add domain-specific cutting planes that generic solvers cannot generate,
tightening the LP relaxation at the root node.

**Inputs**:
```python
active_pairs    : list[tuple[int, int]]
C               : dict[int, int]    # C[j] = simultaneous engagement limit = 3  ✅
M               : dict[int, int]    # M[j] = remaining ammo
m               : int               # = 2  ✅
B               : dict[int, float]  # asset values  ⚠️
B_threshold     : float             # cutoff for "high-value" ⚠️ must be defined
```

**Three inequalities generated**:

```
VI-1 (ammo-engagement bound):
  Σ_i x_ij ≤ min(C_j, floor(M_j / m))   ∀ j
  → For current params: min(3, 12) = 3  [no new information for C_j=3]
  → Becomes meaningful when M_j is partially depleted mid-scenario

VI-2 (mandatory engagement):
  Σ_j x_ij ≥ 1   ∀ i : B[threat_asset[i]] > B_threshold
  → Prevents solver exploring "no-intercept" for high-value threats

VI-3 (layer engagement cap):
  x_iu + x_il ≤ 1 + 𝟙[B[threat_asset[i]] > B_threshold]   ∀ i, u∈U, l∈L
  → General threats: at most one layer
  → High-value threats: both layers allowed
```

**Outputs**:
```python
A_valid : scipy.sparse.csr_matrix   # additional rows appended to A_mccormick
b_valid : np.ndarray
```

**Execution**: Independent of 3A and 3B → **parallel with them**

---

### Phase 4 — Bipartite Decomposition  ⑩

**Purpose**: Detect independent threat groups (no shared batteries) and split
the single MIP into `k` smaller MIPs solvable in parallel.

**Inputs**:
```python
active_pairs    : list[tuple[int, int]]
feasible_mask   : dict[int, int]     # battery_j → uint64 bitmask (from Phase 1)
```

**Computation — bitmask-accelerated Union-Find**:
```
For each threat i:
  battery_mask[i] = OR of feasible_mask[j] entries where (i,j) active
  → uint8 bitmask (6 batteries → 6 bits)

Two threats i, i' are in the same group iff:
  battery_mask[i] & battery_mask[i'] != 0  (they share at least one battery)

Run Union-Find over threats using bitmask overlap as the merge condition
→ groups: list[set[int]]  (each set is an independent threat group)
```

**Outputs**:
```python
subproblems : list[MIPSubproblem]
# Each subproblem contains:
#   - its own active_pairs subset
#   - its own variable/constraint matrices
#   - its own k_bounds subset
```

**Execution**: Detection is sequential; subproblem solving is **parallel (processes)**

---

### Phase 5 — Solver Execution (HiGHS)

**Single subproblem** (or no decomposition possible):
```python
solver = highspy.Highs()
solver.setOptionValue("threads",       4)       # ✅ paper §4
solver.setOptionValue("time_limit",    5.0)     # ✅ paper §4
solver.setOptionValue("mip_rel_gap",   0.01)    # ✅ paper §4

# Warm-start from previous solution
if warm_start_available:
    solver.setSolution(prev_x, prev_k)
    # 4-5× speedup on average  ✅ paper §4
```

**Multiple independent subproblems** (after Phase 4 decomposition):
```python
# Use ProcessPoolExecutor — HiGHS is CPU-bound, GIL applies to threads
with ProcessPoolExecutor(max_workers=len(subproblems)) as ex:
    results = list(ex.map(solve_subproblem, subproblems))

Z_star     = sum(r.objective for r in results)
x_optimal  = {pair: val for r in results for pair, val in r.assignments.items()}
```

**Output**:
```python
x_optimal  : dict[tuple[int,int], int]   # {(i,j): 0 or 1}
k_optimal  : dict[tuple[int,int], float] # {(i,j): k_ij value}
Z_star     : float                       # optimal objective value
solve_time : float                       # seconds
```

---

### Execution Thread Map

```
Main Thread (sequential spine):
  Phase 1 (CSR + bitmask)
    └─ Phase 2A (FBBT)
         └─ Phase 2B (OBBT) ──────────── [worker threads: one LP per pair]
              └─ Phase 3A (Piecewise) ──┐
                   │                    │ [parallel threads]
                   ├── Phase 3B (Huffman)
                   │
                   └── Phase 3C (Valid Ineq)
                        └─ Phase 4 (Bipartite detect)
                             └─ Phase 5 ── [worker processes: one per subproblem]
                                  └─ RESULT
```

**Rule**: ThreadPoolExecutor for Phase 2B (I/O-style LP calls, light GIL impact).
ProcessPoolExecutor for Phase 5 (CPU-bound HiGHS, GIL must be bypassed).
Phases 3B and 3C use threading since they are pure Python with no heavy computation.

---

---

## Part 2 — What to Measure Before Finalizing the Design

These are the ⚠️ unknowns identified throughout the pipeline.
Each needs a targeted experiment or design decision before the paper can make
quantitative performance claims.

### M1 — Measure ρ (Feasible Engagement Ratio)

**Why**: CSR's speedup is $\rho^{2.5}$. Without measured $\rho$, the claim is ungrounded.

**How**:
```python
def measure_rho(scenario):
    total_pairs = len(threats) * len(batteries)
    feasible = sum(
        1 for i in threats for j in batteries
        if distance(i, j) <= R[j] and engagement_window(i, j) is not None
    )
    return feasible / total_pairs

# Run across all three scenarios and report:
# rho_BASELINE, rho_BALANCED, rho_STRESS
# and separately for L-SAM vs. M-SAM batteries
```

**Expected outcome**: M-SAM $\rho$ likely much lower than L-SAM $\rho$
(M-SAM range 5–50 km vs. L-SAM 150–300 km). Reporting these separately
is more informative than a single aggregate $\rho$.

---

### M2 — Measure α (FBBT-only Fix Rate)

**Why**: The 66% figure from the paper includes CSR. FBBT's independent contribution
is unknown and may overlap significantly with CSR.

**How**:
```python
# Run two conditions:
# Condition A: CSR only → count active_pairs_after_CSR
# Condition B: CSR + FBBT → count active_pairs_after_FBBT
alpha_FBBT = 1 - (len(active_pairs_after_FBBT) / len(active_pairs_after_CSR))
```

---

### M3 — Measure OBBT Interval Tightening

**Why**: The speedup claimed for OBBT (referenced as 17–19% from external benchmarks)
has not been verified for DWTA-MIP specifically.

**How**:
```python
# For each (i,j) after FBBT, record:
interval_reduction = [
    (k_max_ij - k_min_ij) / (k_global_max - k_global_min)
    for (i,j) in active_pairs
]
# Report: mean, median, min reduction ratio
# Also measure: total OBBT LP solve time vs. B&B time saved
```

---

### M4 — Measure Piecewise McCormick Node Count

**Why**: The claim that B&B nodes decrease exponentially with gap reduction
is theoretically sound but needs empirical confirmation for this problem structure.

**How**: Run HiGHS with node counting enabled:
```python
solver.setOptionValue("output_flag", True)
# Parse HiGHS log for "Nodes" field
# Compare: original McCormick vs. Piecewise (p=2)
# Across all three scenarios
```

---

### M5 — Define B_i and B_threshold

**Why**: Huffman tree ordering and Valid Inequality VI-2/VI-3 both require
explicit asset value definitions. Currently undefined in the paper.

**Design options**:
```
Option A — Discrete tiers:
  Critical (command post, radar):   B_i = 100
  Important (supply depot):         B_i = 50
  Standard:                         B_i = 10
  B_threshold = 50

Option B — Continuous scale:
  B_i = function of asset type + strategic importance score
  B_threshold = top 30th percentile

Option C — Binary (for simplicity in initial experiments):
  B_i ∈ {1, 10}  (high / low value)
  B_threshold = 5
```

The choice affects Huffman tree depth distribution and the number of VI-2/VI-3 constraints,
so it should be fixed before running comparative experiments.

---

### M6 — Measure Bipartite Decomposition Rate k

**Why**: The complexity reduction $O(2^n) \to O(k \cdot 2^{n/k})$ is only meaningful
if $k \geq 2$ actually occurs in real scenarios.

**How**:
```python
import networkx as nx

def measure_decomposition(scenario):
    G = nx.Graph()
    for (i, j) in active_pairs:
        G.add_edge(f"t{i}", f"b{j}")
    components = list(nx.connected_components(G))
    k = len([c for c in components if any(n.startswith("t") for n in c)])
    return k

# Run across multiple random seeds of each scenario
# Report: mean k, fraction of runs where k >= 2
```

**Hypothesis**: In STRESS (100 threats, 6 batteries), geographic clustering of threats
may naturally produce $k \geq 2$ groups — worth verifying.

---

### M7 — Profile Warm-Start Hit Rate vs. Scenario Volatility

**Why**: The paper reports 4–5× speedup from warm-starting, but this is highly
scenario-dependent. Understanding when warm-start fails informs whether
additional techniques (e.g., Piecewise) are needed as fallback.

**How**: Track per re-optimization cycle:
```python
metrics = {
    "warm_start_used":    bool,
    "solve_time":         float,
    "objective_delta":    float,   # how much the solution changed
    "threat_count_delta": int      # how many threats changed since last cycle
}
# Correlate objective_delta with warm_start speedup
# Find threshold: "if threat_count_delta > X, warm-start loses effectiveness"
```

---

---

## Part 3 — Bitmask Implementation Guide

### 3.1 Design Principles

The two places where bitmasks provide concrete value:

| Phase | Structure | Type | Max bits needed |
|---|---|---|---|
| Phase 1 (CSR cache) | `feasible_mask[j]` = which threats are feasible for battery `j` | `uint64` | 64 threats max |
| Phase 4 (Bipartite) | `battery_mask[i]` = which batteries can engage threat `i` | `uint8` | 6 batteries = 6 bits |

For scenarios with more than 64 threats (e.g., STRESS with 100), use two `uint64`
values or a `numpy` boolean array backed by bitwise ops.

---

### 3.2 Phase 1 — Feasibility Cache Implementation

```python
import numpy as np
from dataclasses import dataclass, field

@dataclass
class FeasibilityCache:
    """
    Maintains per-battery bitmask of feasible threats.
    Supports O(1) update and O(popcount) extraction.
    """
    n_threats:   int
    n_batteries: int

    # For n_threats <= 64: single uint64 per battery
    # For n_threats > 64:  numpy uint64 array, length = ceil(n_threats / 64)
    masks: np.ndarray = field(init=False)

    def __post_init__(self):
        n_words = (self.n_threats + 63) // 64
        self.masks = np.zeros((self.n_batteries, n_words), dtype=np.uint64)

    def set_feasible(self, threat_i: int, battery_j: int):
        word  = threat_i // 64
        bit   = threat_i  % 64
        self.masks[battery_j, word] |= np.uint64(1 << bit)

    def clear_feasible(self, threat_i: int, battery_j: int):
        word  = threat_i // 64
        bit   = threat_i  % 64
        self.masks[battery_j, word] &= ~np.uint64(1 << bit)

    def is_feasible(self, threat_i: int, battery_j: int) -> bool:
        word = threat_i // 64
        bit  = threat_i  % 64
        return bool(self.masks[battery_j, word] & np.uint64(1 << bit))

    def get_feasible_threats(self, battery_j: int) -> list[int]:
        """Extract all set bits (feasible threat indices) for battery j."""
        result = []
        for word_idx, word in enumerate(self.masks[battery_j]):
            base = word_idx * 64
            w = int(word)
            while w:
                lsb = w & (-w)          # isolate lowest set bit
                bit = lsb.bit_length() - 1
                result.append(base + bit)
                w ^= lsb                # clear lowest set bit
        return result

    def get_active_pairs(self) -> list[tuple[int, int]]:
        """Return all (threat_i, battery_j) feasible pairs."""
        return [
            (i, j)
            for j in range(self.n_batteries)
            for i in self.get_feasible_threats(j)
        ]
```

**Usage in rolling re-optimization**:
```python
cache = FeasibilityCache(n_threats=100, n_batteries=6)

# Initial build: O(n_threats × n_batteries)
for j, battery in enumerate(batteries):
    for i, threat in enumerate(threats):
        if is_engageable(threat, battery):
            cache.set_feasible(i, j)

# Per re-optimization cycle — only update changed threats
for i in new_threat_indices:
    for j in range(n_batteries):
        if is_engageable(threats[i], batteries[j]):
            cache.set_feasible(i, j)
        else:
            cache.clear_feasible(i, j)

for i in departed_threat_indices:
    for j in range(n_batteries):
        cache.clear_feasible(i, j)   # single XOR op per battery

# Extract pairs — no floating-point ops
active_pairs = cache.get_active_pairs()
```

**Speedup**: On repeated re-optimization, initial full build is $O(|T| \times |J|)$.
Each subsequent cycle costs $O(\Delta \cdot |J|)$ where $\Delta$ is the number of
threat changes — typically much smaller than $|T|$.

---

### 3.3 Phase 4 — Bitmask-Accelerated Bipartite Decomposition

```python
def find_independent_groups_bitmask(
    active_pairs:  list[tuple[int, int]],
    n_batteries:   int = 6
) -> list[list[int]]:
    """
    Find independent threat groups using bitmask Union-Find.
    Each threat is represented by a uint8 battery-membership mask.

    Two threats are in the same group iff they share any battery:
        battery_mask[i] & battery_mask[i'] != 0
    """
    # Step 1: Build battery mask per threat  — O(|active_pairs|)
    battery_mask: dict[int, int] = {}  # threat_i → uint8 (6 bits for 6 batteries)
    for (i, j) in active_pairs:
        battery_mask[i] = battery_mask.get(i, 0) | (1 << j)

    threats = list(battery_mask.keys())

    # Step 2: Union-Find with bitmask merge check
    parent = {i: i for i in threats}
    group_mask = {i: battery_mask[i] for i in threats}  # group root → union of masks

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]   # path compression
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx == ry:
            return
        parent[ry] = rx
        group_mask[rx] |= group_mask[ry]   # merge battery masks

    # Step 3: Merge threats that share batteries
    # Key insight: instead of checking all pairs O(n²),
    # group by battery first — O(|active_pairs|)
    battery_to_threats: dict[int, list[int]] = {}
    for i, mask in battery_mask.items():
        for j in range(n_batteries):
            if mask & (1 << j):
                battery_to_threats.setdefault(j, []).append(i)

    for j, threat_list in battery_to_threats.items():
        for k in range(1, len(threat_list)):
            union(threat_list[0], threat_list[k])

    # Step 4: Collect groups
    groups: dict[int, list[int]] = {}
    for i in threats:
        root = find(i)
        groups.setdefault(root, []).append(i)

    return list(groups.values())
```

**Usage**:
```python
groups = find_independent_groups_bitmask(active_pairs, n_batteries=6)

if len(groups) == 1:
    # No decomposition possible — solve as single MIP
    result = solve_mip(active_pairs, ...)
else:
    # Decompose and solve in parallel
    subproblems = [build_subproblem(g, active_pairs) for g in groups]
    with ProcessPoolExecutor(max_workers=len(subproblems)) as ex:
        results = list(ex.map(solve_subproblem, subproblems))
    result = merge_results(results)
```

**Complexity comparison**:

| Method | Build | Decompose | Note |
|---|---|---|---|
| `networkx` | $O(E)$ | $O(V + E)$ | Python object overhead per node/edge |
| Bitmask Union-Find | $O(E)$ | $O(E \cdot \alpha(V))$ | Integer ops only, $\alpha$ ≈ constant |

For $V = 100$ threats, $E = 400$ active pairs: networkx involves ~500 Python object
allocations; bitmask version uses integer arrays only.
Absolute difference is ~1–3 ms, but matters in a tight re-optimization loop.

---

### 3.4 Extended: Bitmask for FBBT Propagation (Optional)

If FBBT is extended beyond simple range/ammo checks to include constraint propagation
(logical deductions chained across multiple variables), bitmasks can represent
"which threats are still open for battery j" compactly:

```python
# After each FBBT deduction, clear the bit:
cache.clear_feasible(i, j)

# Check if battery j has any remaining open threats:
def has_open_threats(cache, battery_j):
    return any(cache.masks[battery_j])   # fast: numpy any()

# Check if threat i is still contested by any battery:
def is_still_contested(cache, threat_i, battery_indices):
    return any(cache.is_feasible(threat_i, j) for j in battery_indices)
```

This allows FBBT to run as a **single pass over the bitmask arrays** rather than
iterating over Python lists, which is particularly valuable when FBBT is triggered
repeatedly inside the B&B tree at each node.

---

## Summary

```
┌───────────────────────────────────────────────────────────────────────┐
│ PIPELINE AT A GLANCE                                                  │
│                                                                       │
│ Phase 1  ③ CSR + Bitmask Cache  →  feasible_pairs, feasible_mask     │
│ Phase 2A ① FBBT               →  active_pairs, fixed_zero            │
│ Phase 2B ④ OBBT  [parallel]   →  k_bounds per pair                  │
│ Phase 3A ⑤ Piecewise          →  MIP variables + constraint matrix   │
│ Phase 3B ⑨ Huffman [parallel] →  node_order for tree linearization   │
│ Phase 3C ⑦ Valid Ineq [par.]  →  additional constraint rows          │
│ Phase 4  ⑩ Bipartite+Bitmask  →  subproblems (if k >= 2)            │
│ Phase 5  HiGHS [proc. parallel] →  x_optimal, Z_star                │
│                                                                       │
│ MEASUREMENTS NEEDED BEFORE PAPER SUBMISSION                          │
│   M1  ρ per scenario and per battery layer                           │
│   M2  α (FBBT-only, separated from CSR)                              │
│   M3  OBBT interval reduction ratio + LP cost vs. B&B time saved    │
│   M4  B&B node count: original vs. Piecewise                         │
│   M5  Define B_i values and B_threshold explicitly                   │
│   M6  Measure k (independent groups) across scenario runs            │
│   M7  Warm-start effectiveness vs. scenario volatility               │
│                                                                       │
│ BITMASK IMPLEMENTATION                                                │
│   Phase 1  FeasibilityCache   uint64 per battery  (100-threat safe)  │
│   Phase 4  Union-Find         uint8 per threat    (6-battery safe)   │
│   Optional FBBT propagation   reuse FeasibilityCache.masks           │
└───────────────────────────────────────────────────────────────────────┘
```
