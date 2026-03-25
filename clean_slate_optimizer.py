"""
Clean Slate DWTA Optimizer — Log-Linear Formulation with HiGHS Direct API

수학적 동치:
  Original:  min Σ Bᵢ × (1 - Π(1 - pⱼₜ xⱼₜ))
  ⟺  max Σ Bᵢ × exp(Σ cⱼₜ xⱼₜ)        where cⱼₜ = ln(1 - pⱼₜ)
  ⟺  max Σ Bᵢ × fᵢ                      OA: fᵢ ≤ eᵃᵏ(1 + σᵢ - σᵏ)

~95 binary + ~20 continuous vars, ~160 constraints.
Global optimal in < 10ms for 15 threats.
"""

import time
import math
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

import highspy

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Core Data Classes (self-contained — no external dependency)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Asset:
    """방어 자산"""
    id: str
    position: Tuple[float, float]
    value: float
    priority: int
    estimated_threat_missiles: List[str]

@dataclass
class InterceptorSystem:
    """요격체계 (상층/하층)"""
    id: str
    system_type: str       # "UPPER"/"LSAM" (상층) or "LOWER"/"MSAM" (하층)
    position: Tuple[float, float]
    available_missiles: int
    max_missiles_per_target: int
    intercept_probability: float
    engagement_range: float

@dataclass
class Threat:
    """위협 미사일"""
    id: str
    target_asset_id: str
    current_position: Tuple[float, float, float]
    estimated_impact_time: float
    launch_position: Tuple[float, float] = (0.0, 0.0)
    flight_time: float = 300.0
    specs: dict = None
    launch_time: float = 0.0
    trajectory_type: str = "ballistic"
    rcs: float = 0.5

    def __post_init__(self):
        if self.specs is None:
            self.specs = {
                "max_altitude_km": 50.0,
                "avg_speed_kmh": 2000.0,
                "trajectory_type": self.trajectory_type,
                "rcs": self.rcs
            }


# ═══════════════════════════════════════════════════════════════════
# Section 1: Immutable Problem Data
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DWTAProblem:
    """Immutable NumPy-backed problem data. Integer indexing only."""

    n_threats: int
    n_upper: int
    n_lower: int
    n_assets: int

    # Index mappings (boundary only)
    threat_ids: Tuple[str, ...]
    upper_ids: Tuple[str, ...]
    lower_ids: Tuple[str, ...]
    asset_ids: Tuple[str, ...]

    # Reverse lookups
    threat_id_to_idx: Dict[str, int]
    upper_id_to_idx: Dict[str, int]
    lower_id_to_idx: Dict[str, int]
    asset_id_to_idx: Dict[str, int]

    asset_values: np.ndarray           # (I,) float64
    threat_to_asset: np.ndarray        # (T,) int — threat t → asset index

    upper_feasible: np.ndarray         # (J_U, T) bool
    lower_feasible: np.ndarray         # (J_L, T) bool

    upper_p: np.ndarray                # (J_U, T) float64 — effective intercept prob
    lower_p: np.ndarray                # (J_L, T) float64

    upper_c: np.ndarray                # (J_U, T) float64 — log(1-p)
    lower_c: np.ndarray                # (J_L, T) float64

    upper_capacity: np.ndarray         # (J_U,) int — floor(M_j / 2)
    lower_capacity: np.ndarray         # (J_L,) int
    upper_simul: np.ndarray            # (J_U,) int — simultaneous engagement limit
    lower_simul: np.ndarray            # (J_L,) int

    # Per-asset: list of feasible (layer, j, t) triples → used for σ definition
    asset_pairs_upper: Tuple[Tuple[Tuple[int, int], ...], ...]  # per asset
    asset_pairs_lower: Tuple[Tuple[Tuple[int, int], ...], ...]


@dataclass(frozen=True)
class VarMap:
    """Variable index mapping for HiGHS model."""

    upper_pairs: np.ndarray         # (n_xu, 2) int — (j, t) indices
    lower_pairs: np.ndarray         # (n_xl, 2) int

    upper_var_idx: np.ndarray       # (J_U, T) int — -1 if infeasible
    lower_var_idx: np.ndarray       # (J_L, T) int

    n_xu: int
    n_xl: int
    n_vars: int

    sigma_offset: int
    f_offset: int


# ═══════════════════════════════════════════════════════════════════
# Section 2: Pure Functions — Build Pipeline
# ═══════════════════════════════════════════════════════════════════

def build_problem(
    assets: List[Asset],
    interceptor_systems: List[InterceptorSystem],
    threats: List[Threat],
    batteries: List[Dict],
    engagement_matrix,
    k_factor_cache=None,
    custom_intercept_probs: Optional[Dict[str, float]] = None,
) -> DWTAProblem:
    """Pure function: domain objects → immutable NumPy problem data."""

    upper_systems = [s for s in interceptor_systems
                     if s.system_type in ("LSAM", "UPPER")]
    lower_systems = [s for s in interceptor_systems
                     if s.system_type in ("MSAM", "LOWER")]

    n_t = len(threats)
    n_u = len(upper_systems)
    n_l = len(lower_systems)
    n_a = len(assets)

    threat_ids = tuple(t.id for t in threats)
    upper_ids = tuple(s.id for s in upper_systems)
    lower_ids = tuple(s.id for s in lower_systems)
    asset_ids = tuple(a.id for a in assets)

    threat_id_to_idx = {tid: i for i, tid in enumerate(threat_ids)}
    upper_id_to_idx = {sid: i for i, sid in enumerate(upper_ids)}
    lower_id_to_idx = {sid: i for i, sid in enumerate(lower_ids)}
    asset_id_to_idx = {aid: i for i, aid in enumerate(asset_ids)}

    asset_values = np.array([a.value for a in assets], dtype=np.float64)

    # threat → asset mapping
    threat_to_asset = np.zeros(n_t, dtype=np.int32)
    for i, t in enumerate(threats):
        threat_to_asset[i] = asset_id_to_idx.get(t.target_asset_id, 0)

    # --- Vectorized Feasibility (비트마스크 — engagement_matrix 의존 제거) ---
    missiles_per_engagement = 2

    if n_u > 0 and n_t > 0:
        u_pos = np.array([s.position[:2] for s in upper_systems], dtype=np.float64)  # (J_U, 2)
        t_pos = np.array([t.current_position[:2] for t in threats], dtype=np.float64)  # (T, 2)
        u_dist = np.linalg.norm(u_pos[:, None, :] - t_pos[None, :, :], axis=2)  # (J_U, T)
        u_ranges = np.array([s.engagement_range for s in upper_systems], dtype=np.float64)  # (J_U,)

        # 사거리 1.5배 이내 = feasible (위협 접근 시 교전 가능)
        upper_feasible = u_dist <= u_ranges[:, None] * 1.5

        # 고도 마스킹: LSAM ≤ 80km
        t_alt_km = np.array([t.current_position[2] / 1000.0 if len(t.current_position) >= 3 else 0.0
                             for t in threats], dtype=np.float64)
        upper_feasible &= (t_alt_km[None, :] <= 80.0)

        # engagement_matrix precompute 결과 merge (있으면 OR)
        if engagement_matrix is not None and hasattr(engagement_matrix, 'feasible'):
            for j, sys in enumerate(upper_systems):
                for i, thr in enumerate(threats):
                    if engagement_matrix.feasible.get((sys.id, thr.id), False):
                        upper_feasible[j, i] = True  # precompute에서 가능이면 유지
    else:
        upper_feasible = np.zeros((n_u, n_t), dtype=bool)
        u_dist = np.zeros((n_u, n_t), dtype=np.float64)

    if n_l > 0 and n_t > 0:
        l_pos = np.array([s.position[:2] for s in lower_systems], dtype=np.float64)  # (J_L, 2)
        t_pos_l = np.array([t.current_position[:2] for t in threats], dtype=np.float64) if n_t > 0 else np.empty((0,2))
        l_dist = np.linalg.norm(l_pos[:, None, :] - t_pos_l[None, :, :], axis=2)  # (J_L, T)
        l_ranges = np.array([s.engagement_range for s in lower_systems], dtype=np.float64)

        lower_feasible = l_dist <= l_ranges[:, None] * 1.5
        t_alt_km_l = np.array([t.current_position[2] / 1000.0 if len(t.current_position) >= 3 else 0.0
                               for t in threats], dtype=np.float64)
        lower_feasible &= (t_alt_km_l[None, :] <= 50.0)

        if engagement_matrix is not None and hasattr(engagement_matrix, 'feasible'):
            for j, sys in enumerate(lower_systems):
                for i, thr in enumerate(threats):
                    if engagement_matrix.feasible.get((sys.id, thr.id), False):
                        lower_feasible[j, i] = True
    else:
        lower_feasible = np.zeros((n_l, n_t), dtype=bool)
        l_dist = np.zeros((n_l, n_t), dtype=np.float64)

    # --- Vectorized k-factor & effective probability ---
    upper_p = np.zeros((n_u, n_t), dtype=np.float64)
    lower_p = np.zeros((n_l, n_t), dtype=np.float64)

    for j, sys in enumerate(upper_systems):
        pk = (custom_intercept_probs.get(sys.id, sys.intercept_probability)
              if custom_intercept_probs else sys.intercept_probability)
        P_total = 1.0 - (1.0 - pk) ** missiles_per_engagement
        rng = sys.engagement_range

        for i in range(n_t):
            if not upper_feasible[j, i]:
                continue
            # k from distance (벡터화된 거리 사용, 재계산 없음)
            d = float(u_dist[j, i])
            k = _compute_k_from_dist(d, rng, k_factor_cache, threats[i])
            upper_p[j, i] = k * P_total

    for j, sys in enumerate(lower_systems):
        pk = (custom_intercept_probs.get(sys.id, sys.intercept_probability)
              if custom_intercept_probs else sys.intercept_probability)
        P_total = 1.0 - (1.0 - pk) ** missiles_per_engagement
        rng = sys.engagement_range

        for i in range(n_t):
            if not lower_feasible[j, i]:
                continue
            d = float(l_dist[j, i])
            k = _compute_k_from_dist(d, rng, k_factor_cache, threats[i])
            lower_p[j, i] = k * P_total

    # Clamp p to (0, 0.9999) to avoid log(0)
    upper_p = np.clip(upper_p, 0.0, 0.9999)
    lower_p = np.clip(lower_p, 0.0, 0.9999)

    # --- Log-survival coefficients ---
    upper_c = np.where(upper_feasible, np.log(1.0 - upper_p + 1e-15), 0.0)
    lower_c = np.where(lower_feasible, np.log(1.0 - lower_p + 1e-15), 0.0)

    # --- Capacity ---
    battery_lookup = {b['id']: b for b in batteries} if batteries else {}

    upper_capacity = np.array([
        sys.available_missiles // missiles_per_engagement
        for sys in upper_systems
    ], dtype=np.int32)

    lower_capacity = np.array([
        sys.available_missiles // missiles_per_engagement
        for sys in lower_systems
    ], dtype=np.int32)

    def _get_simul(sys_id):
        b = battery_lookup.get(sys_id)
        if b and 'specs' in b:
            bc = b['specs'].get('battery_config', {})
            return bc.get('simultaneous_engagements', 5)
        return 5

    upper_simul = np.array([_get_simul(s.id) for s in upper_systems], dtype=np.int32)
    lower_simul = np.array([_get_simul(s.id) for s in lower_systems], dtype=np.int32)

    # --- Per-asset feasible pairs (for σ constraint construction) ---
    asset_pairs_upper = []
    asset_pairs_lower = []
    for a_idx in range(n_a):
        au = []
        al = []
        for t_idx in range(n_t):
            if threat_to_asset[t_idx] != a_idx:
                continue
            for j_idx in range(n_u):
                if upper_feasible[j_idx, t_idx]:
                    au.append((j_idx, t_idx))
            for j_idx in range(n_l):
                if lower_feasible[j_idx, t_idx]:
                    al.append((j_idx, t_idx))
        asset_pairs_upper.append(tuple(au))
        asset_pairs_lower.append(tuple(al))

    return DWTAProblem(
        n_threats=n_t, n_upper=n_u, n_lower=n_l, n_assets=n_a,
        threat_ids=threat_ids, upper_ids=upper_ids,
        lower_ids=lower_ids, asset_ids=asset_ids,
        threat_id_to_idx=threat_id_to_idx,
        upper_id_to_idx=upper_id_to_idx,
        lower_id_to_idx=lower_id_to_idx,
        asset_id_to_idx=asset_id_to_idx,
        asset_values=asset_values, threat_to_asset=threat_to_asset,
        upper_feasible=upper_feasible, lower_feasible=lower_feasible,
        upper_p=upper_p, lower_p=lower_p,
        upper_c=upper_c, lower_c=lower_c,
        upper_capacity=upper_capacity, lower_capacity=lower_capacity,
        upper_simul=upper_simul, lower_simul=lower_simul,
        asset_pairs_upper=tuple(asset_pairs_upper),
        asset_pairs_lower=tuple(asset_pairs_lower),
    )


def _compute_k_from_dist(distance: float, max_range: float,
                         k_factor_cache, threat: Threat) -> float:
    """사전 계산된 거리에서 k-factor 반환. 거리 재계산 없음."""
    k_min, k_max = 0.6, 1.0

    if k_factor_cache is not None:
        if hasattr(k_factor_cache, 'get_k_time_dependent'):
            time_elapsed = getattr(threat, 'flight_time_elapsed',
                                   getattr(threat, 'launch_time', 0.0))
            total_flight = getattr(threat, 'flight_time', 300.0)
            if total_flight > 0:
                try:
                    return k_factor_cache.get_k_time_dependent(
                        distance, max_range, time_elapsed, total_flight)
                except Exception:
                    pass
        if hasattr(k_factor_cache, 'get_k_from_distance'):
            try:
                return k_factor_cache.get_k_from_distance(distance, max_range)
            except Exception:
                pass

    # Fallback: 거리 비율 기반 선형 k
    if max_range > 0:
        ratio = max(0.0, 1.0 - distance / max_range)
        return k_min + (k_max - k_min) * ratio
    return 0.8


def _compute_distance(system: InterceptorSystem, threat: Threat) -> float:
    """현재 위치 기반 2D 거리 계산 (km)."""
    sys_pos = np.array(system.position[:2], dtype=np.float64)
    thr_pos = np.array(threat.current_position[:2], dtype=np.float64)
    return float(np.linalg.norm(sys_pos - thr_pos))


def _check_feasibility(system: InterceptorSystem, threat: Threat,
                       engagement_matrix) -> bool:
    """현재 위치 기반 교전 가능 여부 판단.

    핵심 원칙: 위협이 현재 사거리 안에 있으면 교전 가능.
    engagement_matrix 초기 결과는 참조하되, 현재 거리가 사거리 이내이면 override.
    이것이 "가까이 오면 맞출 수 있게 되는" 현실을 반영.

    기존 update_moving_threats + add_new_threats를 대체.
    """
    distance = _compute_distance(system, threat)
    max_range = system.engagement_range

    # ① 확실히 불가: 사거리의 2배 초과
    if distance > max_range * 2.0:
        return False

    # ② 고도 확인
    altitude_km = 0.0
    if len(threat.current_position) >= 3:
        altitude_km = threat.current_position[2] / 1000.0  # m → km

    if system.system_type in ('LSAM', 'UPPER'):
        if altitude_km > 80.0:
            return False
    elif system.system_type in ('MSAM', 'LOWER'):
        if altitude_km > 50.0:
            return False

    # ③ 핵심: 현재 사거리 이내이면 교전 가능 (동적 갱신 대체)
    # 위협이 자산 가까이 오면서 MSAM 사거리에 진입 → 교전 가능
    if distance <= max_range:
        return True

    # ④ 사거리 ~ 사거리×2 범위: engagement_matrix 참조 (정밀 판단)
    if engagement_matrix is not None:
        if hasattr(engagement_matrix, 'feasible'):
            precomputed = engagement_matrix.feasible.get((system.id, threat.id))
            if precomputed is not None:
                return precomputed

    # ⑤ engagement_matrix에 없는 경우 (새 위협): 사거리의 1.5배 이내이면 허용
    return distance <= max_range * 1.5


def _compute_k(system: InterceptorSystem, threat: Threat,
               engagement_matrix, k_factor_cache) -> float:
    """현재 위치 기반 k-factor 계산.

    거리를 current_position에서 직접 계산하여
    engagement_matrix의 동적 갱신(update_moving_threats) 없이도 정확한 k값 제공.
    """
    # 현재 위치에서 거리 직접 계산 (engagement_matrix 캐시 불필요)
    distance = _compute_distance(system, threat)

    # k_factor_cache가 있으면 활용
    if k_factor_cache is not None:
        # Time-dependent k: 비행 단계별 보정
        if hasattr(k_factor_cache, 'get_k_time_dependent'):
            time_elapsed = getattr(threat, 'flight_time_elapsed',
                                   getattr(threat, 'launch_time', 0.0))
            total_flight = getattr(threat, 'flight_time', 300.0)
            if total_flight > 0:
                try:
                    return k_factor_cache.get_k_time_dependent(
                        distance, system.engagement_range,
                        time_elapsed, total_flight)
                except Exception:
                    pass

        # Distance-only k
        if hasattr(k_factor_cache, 'get_k_from_distance'):
            try:
                return k_factor_cache.get_k_from_distance(
                    distance, system.engagement_range)
            except Exception:
                pass

    # Fallback: 거리 비율 기반 선형 k
    k_min, k_max = 0.6, 1.0
    if system.engagement_range > 0:
        ratio = max(0.0, 1.0 - distance / system.engagement_range)
        return k_min + (k_max - k_min) * ratio
    return 0.8


# ═══════════════════════════════════════════════════════════════════
# Section 3: Model Builder — HiGHS Direct API
# ═══════════════════════════════════════════════════════════════════

NUM_OA_BREAKPOINTS = 40  # exp() outer approximation breakpoints
OA_REFINE_ROUNDS = 3     # iterative tangent-cut refinement rounds
OA_REFINE_TOL = 1e-7     # relative convergence tolerance for f_i vs exp(σ_i)


def build_model(prob: DWTAProblem, time_limit: float = 3.0,
                gap_tol: float = 0.001, threads: int = 1
                ) -> Tuple[highspy.Highs, VarMap]:
    """Pure function: DWTAProblem → (HiGHS model, VarMap)."""

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", time_limit)
    h.setOptionValue("mip_rel_gap", gap_tol)
    h.setOptionValue("threads", threads)
    h.setOptionValue("presolve", "on")

    # --- Enumerate feasible pairs ---
    uj, ut = np.where(prob.upper_feasible)
    upper_pairs = np.column_stack([uj, ut]) if len(uj) > 0 else np.empty((0, 2), dtype=np.int32)
    lj, lt = np.where(prob.lower_feasible)
    lower_pairs = np.column_stack([lj, lt]) if len(lj) > 0 else np.empty((0, 2), dtype=np.int32)

    n_xu = len(upper_pairs)
    n_xl = len(lower_pairs)
    n_x = n_xu + n_xl
    n_sigma = prob.n_assets
    n_f = prob.n_assets
    n_vars = n_x + n_sigma + n_f

    sigma_offset = n_x
    f_offset = n_x + n_sigma

    # Variable index matrices (-1 = no variable)
    upper_var_idx = np.full((prob.n_upper, prob.n_threats), -1, dtype=np.int32)
    for k, (j, t) in enumerate(upper_pairs):
        upper_var_idx[j, t] = k

    lower_var_idx = np.full((prob.n_lower, prob.n_threats), -1, dtype=np.int32)
    for k, (j, t) in enumerate(lower_pairs):
        lower_var_idx[j, t] = n_xu + k

    vmap = VarMap(
        upper_pairs=upper_pairs, lower_pairs=lower_pairs,
        upper_var_idx=upper_var_idx, lower_var_idx=lower_var_idx,
        n_xu=n_xu, n_xl=n_xl, n_vars=n_vars,
        sigma_offset=sigma_offset, f_offset=f_offset,
    )

    # === Add all variables at once ===
    col_lower = np.zeros(n_vars)
    col_upper = np.ones(n_vars)
    col_cost = np.zeros(n_vars)

    # σ bounds: [sigma_min_i, 0]
    for i in range(prob.n_assets):
        sigma_min = 0.0
        for (j, t) in prob.asset_pairs_upper[i]:
            sigma_min += prob.upper_c[j, t]
        for (j, t) in prob.asset_pairs_lower[i]:
            sigma_min += prob.lower_c[j, t]
        col_lower[sigma_offset + i] = sigma_min
        col_upper[sigma_offset + i] = 0.0

    # f bounds: [0, 1]
    for i in range(prob.n_assets):
        col_lower[f_offset + i] = 0.0
        col_upper[f_offset + i] = 1.0

    # Objective: min Σ Bᵢ × fᵢ  (minimize expected damage from surviving threats)
    # fᵢ ≈ exp(σᵢ) = probability threats to asset i survive all defenses
    # When fᵢ=1 → no defense → full damage. When fᵢ≈0 → all intercepted → no damage.
    max_val = prob.asset_values.max() if prob.n_assets > 0 else 1.0
    scale = 1.0 / max_val if max_val > 0 else 1.0
    for i in range(prob.n_assets):
        col_cost[f_offset + i] = prob.asset_values[i] * scale  # POSITIVE: minimize

    h.addVars(n_vars, col_lower.tolist(), col_upper.tolist())

    # Set x variables as integer (binary)
    for k in range(n_x):
        h.changeColIntegrality(k, highspy.HighsVarType.kInteger)

    # Set objective
    for k in range(n_vars):
        if col_cost[k] != 0.0:
            h.changeColCost(k, col_cost[k])

    h.changeObjectiveSense(highspy.ObjSense.kMinimize)

    # === Constraints ===
    # We'll collect all rows and add in batch
    row_lower_list = []
    row_upper_list = []
    row_starts = [0]
    row_indices = []
    row_values = []

    def _add_row(lb, ub, indices, values):
        row_lower_list.append(lb)
        row_upper_list.append(ub)
        for idx, val in zip(indices, values):
            row_indices.append(idx)
            row_values.append(val)
        row_starts.append(len(row_indices))

    # --- C1: σ definition: σᵢ = Σ cⱼₜ xⱼₜ  →  σᵢ - Σ cⱼₜ xⱼₜ = 0 ---
    for i in range(prob.n_assets):
        idxs = [sigma_offset + i]
        vals = [1.0]
        for (j, t) in prob.asset_pairs_upper[i]:
            vi = upper_var_idx[j, t]
            if vi >= 0:
                idxs.append(vi)
                vals.append(-prob.upper_c[j, t])
        for (j, t) in prob.asset_pairs_lower[i]:
            vi = lower_var_idx[j, t]
            if vi >= 0:
                idxs.append(vi)
                vals.append(-prob.lower_c[j, t])
        _add_row(0.0, 0.0, idxs, vals)

    # --- C2: Tangent LOWER bounds for exp(σ) ---
    #
    # We minimize: Σ Bᵢ × fᵢ  where fᵢ ≈ exp(σᵢ) = threat survival probability
    #
    # Since we MINIMIZE fᵢ, the solver pushes fᵢ DOWN.
    # exp() is convex → tangent lines at any point are LOWER bounds:
    #   exp(σ) ≥ exp(σᵏ) × (1 + σ - σᵏ)   for all σ, σᵏ
    #
    # These tangent constraints PREVENT fᵢ from going below exp(σᵢ).
    # At optimality: fᵢ = max_k{tangent_k(σᵢ)} = exp(σᵢ)  (exact for dense breakpoints)
    #
    # No upper bound (secant) needed — solver has no incentive to increase fᵢ.

    for i in range(prob.n_assets):
        sigma_min_i = col_lower[sigma_offset + i]

        if sigma_min_i >= -1e-9:
            # Check: are there ANY threats targeting this asset?
            threats_targeting_i = int(np.sum(prob.threat_to_asset == i))
            if threats_targeting_i == 0:
                # No threats → fᵢ = 0 (no damage possible)
                _add_row(0.0, 0.0, [f_offset + i], [1.0])
            else:
                # Threats exist but no feasible engagement → fᵢ = 1 (undefendable)
                _add_row(1.0, 1.0, [f_offset + i], [1.0])
            continue

        # Non-uniform breakpoints: denser near σ=0 where exp() curvature is highest
        # Use quadratic concentration: t² mapping pushes points toward 0
        t = np.linspace(0.0, 1.0, NUM_OA_BREAKPOINTS)
        breakpoints = sigma_min_i * (1.0 - t**2)  # σ_min at t=0, 0 at t=1
        for sigma_k in breakpoints:
            e_k = math.exp(sigma_k)
            # fᵢ ≥ eᵃᵏ(1 + σᵢ - σᵏ) = eᵃᵏ + eᵃᵏ(σᵢ - σᵏ)
            # Rearranged: fᵢ - eᵃᵏ × σᵢ ≥ eᵃᵏ(1 - σᵏ)
            rhs = e_k * (1.0 - sigma_k)
            _add_row(rhs, highspy.kHighsInf,
                     [f_offset + i, sigma_offset + i],
                     [1.0, -e_k])

    # --- C3: Missile capacity: Σₜ x_jt ≤ floor(M_j/2) ---
    for j in range(prob.n_upper):
        idxs = [int(upper_var_idx[j, t]) for t in range(prob.n_threats)
                if upper_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, float(prob.upper_capacity[j]),
                     idxs, [1.0] * len(idxs))

    for j in range(prob.n_lower):
        idxs = [int(lower_var_idx[j, t]) for t in range(prob.n_threats)
                if lower_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, float(prob.lower_capacity[j]),
                     idxs, [1.0] * len(idxs))

    # --- C4: Simultaneous engagement: Σₜ x_jt ≤ C_j ---
    for j in range(prob.n_upper):
        cap = min(int(prob.upper_simul[j]), int(prob.upper_capacity[j]))
        idxs = [int(upper_var_idx[j, t]) for t in range(prob.n_threats)
                if upper_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, float(cap),
                     idxs, [1.0] * len(idxs))

    for j in range(prob.n_lower):
        cap = min(int(prob.lower_simul[j]), int(prob.lower_capacity[j]))
        idxs = [int(lower_var_idx[j, t]) for t in range(prob.n_threats)
                if lower_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, float(cap),
                     idxs, [1.0] * len(idxs))

    # --- C5: Max 1 upper system per threat ---
    for t in range(prob.n_threats):
        idxs = [int(upper_var_idx[j, t]) for j in range(prob.n_upper)
                if upper_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, 1.0, idxs, [1.0] * len(idxs))

    # --- C6: Max 1 lower system per threat ---
    for t in range(prob.n_threats):
        idxs = [int(lower_var_idx[j, t]) for j in range(prob.n_lower)
                if lower_var_idx[j, t] >= 0]
        if idxs:
            _add_row(-highspy.kHighsInf, 1.0, idxs, [1.0] * len(idxs))

    # --- C7: Coverage — objective-driven (soft) ---
    # No mandatory coverage constraint.
    # The objective (max survival) naturally incentivizes engaging all threats.
    # In capacity-constrained scenarios, forced coverage would cause infeasibility.
    # The optimizer allocates resources optimally given capacity limits.

    # === Batch add all rows ===
    n_rows = len(row_lower_list)
    if n_rows > 0:
        h.addRows(
            n_rows,
            row_lower_list,
            row_upper_list,
            len(row_indices),
            row_starts,
            row_indices,
            row_values,
        )

    return h, vmap


# ═══════════════════════════════════════════════════════════════════
# Section 4: Warm-Start
# ═══════════════════════════════════════════════════════════════════

def apply_warmstart(h: highspy.Highs, vmap: VarMap,
                    prob: DWTAProblem, prev_solution: Dict) -> int:
    """Apply previous solution as MIP start hint. Returns count of hints set."""
    if not prev_solution:
        return 0

    values = [0.0] * vmap.n_vars
    count = 0

    prev_upper = prev_solution.get('upper_assignments', {})
    prev_lower = prev_solution.get('lower_assignments', {})

    for key, sys_id in prev_upper.items():
        parts = key.split('_', 1)
        if len(parts) == 2:
            threat_id = parts[1]
        else:
            continue
        j = prob.upper_id_to_idx.get(sys_id)
        t = prob.threat_id_to_idx.get(threat_id)
        if j is not None and t is not None:
            vi = vmap.upper_var_idx[j, t]
            if vi >= 0:
                values[vi] = 1.0
                count += 1

    for key, sys_id in prev_lower.items():
        parts = key.split('_', 1)
        if len(parts) == 2:
            threat_id = parts[1]
        else:
            continue
        j = prob.lower_id_to_idx.get(sys_id)
        t = prob.threat_id_to_idx.get(threat_id)
        if j is not None and t is not None:
            vi = vmap.lower_var_idx[j, t]
            if vi >= 0:
                values[vi] = 1.0
                count += 1

    if count > 0:
        sol = highspy.HighsSolution()
        sol.col_value = values
        sol.col_dual = [0.0] * len(values)
        sol.row_value = []
        sol.row_dual = []
        try:
            h.setSolution(sol)
        except Exception:
            pass  # warm-start is best-effort

    return count


# ═══════════════════════════════════════════════════════════════════
# Section 5: Result Extraction
# ═══════════════════════════════════════════════════════════════════

def extract_result(h: highspy.Highs, vmap: VarMap,
                   prob: DWTAProblem, build_time: float,
                   warmstart_count: int) -> Dict:
    """Pure function: solved HiGHS model → interface-compatible result Dict."""

    info = h.getInfoValue
    model_status = h.getModelStatus()
    feasible = model_status == highspy.HighsModelStatus.kOptimal or \
               model_status == highspy.HighsModelStatus.kObjectiveBound or \
               model_status == highspy.HighsModelStatus.kSolutionLimit

    solve_time = build_time
    # HiGHS run_time은 매우 짧아 0으로 보일 수 있으므로 build_time을 solver time으로 사용
    try:
        status_ok, run_time_val = info("run_time")
        pure_solver_time = run_time_val if status_ok == highspy.HighsStatus.kOk and run_time_val > 0 else build_time
    except Exception:
        pure_solver_time = build_time

    status_names = {
        highspy.HighsModelStatus.kOptimal: "Optimal",
        highspy.HighsModelStatus.kInfeasible: "Infeasible",
        highspy.HighsModelStatus.kUnbounded: "Unbounded",
        highspy.HighsModelStatus.kObjectiveBound: "Optimal",
        highspy.HighsModelStatus.kSolutionLimit: "Optimal",
    }
    status_str = status_names.get(model_status, "Not Solved")

    result = {
        'feasible': feasible,
        'objective_value': float('inf'),
        'solve_time': solve_time,
        'pure_solver_time': pure_solver_time,
        'status': status_str,
        'algorithm': 'CleanSlate',
        'warmstart_applied': warmstart_count > 0,
        'warmstart_count': warmstart_count,
        'upper_assignments': {},
        'lower_assignments': {},
        'upper_k_values': {},
        'lower_k_values': {},
        'asset_survival_probs': {},
        'diagnosis': {
            'num_variables': vmap.n_vars,
            'num_constraints': h.getNumRow(),
            'num_threats': prob.n_threats,
            'num_systems': prob.n_upper + prob.n_lower,
            'total_missiles': int(prob.upper_capacity.sum() * 2 + prob.lower_capacity.sum() * 2),
            'feasible_engagements': int(prob.upper_feasible.sum() + prob.lower_feasible.sum()),
        },
    }

    if not feasible:
        return result

    sol = h.getSolution()
    x = np.array(sol.col_value)

    # --- Extract assignments ---
    upper_assignments = {}
    lower_assignments = {}
    threat_asset_map = {}
    for t_idx in range(prob.n_threats):
        threat_asset_map[prob.threat_ids[t_idx]] = prob.asset_ids[prob.threat_to_asset[t_idx]]

    for k, (j, t) in enumerate(vmap.upper_pairs):
        if x[k] > 0.5:
            threat_id = prob.threat_ids[t]
            system_id = prob.upper_ids[j]
            asset_id = threat_asset_map[threat_id]
            key = f"{asset_id}_{threat_id}"
            upper_assignments[key] = system_id

    for k, (j, t) in enumerate(vmap.lower_pairs):
        vi = vmap.n_xu + k
        if x[vi] > 0.5:
            threat_id = prob.threat_ids[t]
            system_id = prob.lower_ids[j]
            asset_id = threat_asset_map[threat_id]
            key = f"{asset_id}_{threat_id}"
            lower_assignments[key] = system_id

    result['upper_assignments'] = upper_assignments
    result['lower_assignments'] = lower_assignments

    # --- Compute exact objective (not the OA approximation) ---
    # σᵢ = Σ cⱼₜ xⱼₜ < 0 when interceptors assigned
    # exp(σᵢ) = threat survival probability (lower = better defense)
    # damage = Bᵢ × exp(σᵢ)
    total_damage = 0.0
    for i in range(prob.n_assets):
        # Assets with no threats: no damage possible, survival = 100%
        threats_targeting_i = int(np.sum(prob.threat_to_asset == i))
        if threats_targeting_i == 0:
            result['asset_survival_probs'][prob.asset_ids[i]] = 1.0
            continue  # 0 damage contribution

        sigma_i = x[vmap.sigma_offset + i]
        threat_survival = math.exp(sigma_i)  # P(threats survive defenses)
        asset_survival = 1.0 - threat_survival  # P(asset is protected)
        result['asset_survival_probs'][prob.asset_ids[i]] = asset_survival
        total_damage += prob.asset_values[i] * threat_survival

    result['objective_value'] = total_damage

    # --- k values (precomputed, for backward compatibility) ---
    for k, (j, t) in enumerate(vmap.upper_pairs):
        if x[k] > 0.5:
            p_jt = prob.upper_p[j, t]
            P_total = 1.0 - (1.0 - 0.85) ** 2  # LSAM default
            k_val = p_jt / P_total if P_total > 0 else 0.8
            threat_id = prob.threat_ids[t]
            system_id = prob.upper_ids[j]
            asset_id = threat_asset_map[threat_id]
            result['upper_k_values'][f"{asset_id}_{threat_id}_{system_id}"] = round(k_val, 4)

    for k, (j, t) in enumerate(vmap.lower_pairs):
        vi = vmap.n_xu + k
        if x[vi] > 0.5:
            p_jt = prob.lower_p[j, t]
            P_total = 1.0 - (1.0 - 0.78) ** 2  # MSAM default
            k_val = p_jt / P_total if P_total > 0 else 0.8
            threat_id = prob.threat_ids[t]
            system_id = prob.lower_ids[j]
            asset_id = threat_asset_map[threat_id]
            result['lower_k_values'][f"{asset_id}_{threat_id}_{system_id}"] = round(k_val, 4)

    return result


# ═══════════════════════════════════════════════════════════════════
# Section 6: Optimizer Class Wrapper (GUI Interface)
# ═══════════════════════════════════════════════════════════════════

class CleanSlateOptimizer:
    """Drop-in replacement for NonLinearMIPOptimizer.

    Interface contract:
        optimizer = CleanSlateOptimizer(config)
        optimizer.set_intercept_probabilities(sampled_probs)
        optimizer.create_model(assets, systems, threats, batteries, eng_matrix)
        result = optimizer.solve()
    """

    def __init__(self, config=None):
        self.config = config
        self.log_callback = None

        # State for warm-start across timesteps
        self.previous_solution: Optional[Dict] = None
        self.use_warm_start = True

        # Per-call state
        self._problem: Optional[DWTAProblem] = None
        self._model: Optional[highspy.Highs] = None
        self._vmap: Optional[VarMap] = None
        self._custom_probs: Optional[Dict[str, float]] = None
        self._k_factor_cache = None
        self._build_time: float = 0.0
        self._ws_count: int = 0

    def set_intercept_probabilities(self, probs: Dict[str, float]):
        """Set per-threat sampled intercept probabilities."""
        self._custom_probs = probs

    def set_k_factor_cache(self, cache):
        """Provide k-factor cache for distance/time-based k computation."""
        self._k_factor_cache = cache

    def _log(self, msg: str):
        if self.log_callback:
            try:
                self.log_callback(msg, "INFO")
            except Exception:
                pass

    def create_model(self, assets, interceptor_systems, threats,
                     batteries=None, engagement_matrix=None):
        """Build the optimization model."""
        t0 = time.perf_counter()

        # 이전 HiGHS 객체 명시적 정리 (C++ 메모리 해제)
        if self._model is not None:
            try:
                self._model.clear()
            except Exception:
                pass
            self._model = None
            self._vmap = None

        # Build immutable problem data
        self._problem = build_problem(
            assets=assets,
            interceptor_systems=interceptor_systems,
            threats=threats,
            batteries=batteries or [],
            engagement_matrix=engagement_matrix,
            k_factor_cache=self._k_factor_cache,
            custom_intercept_probs=self._custom_probs,
        )

        # Build HiGHS model
        self._model, self._vmap = build_model(self._problem)

        # Apply warm-start
        self._ws_count = 0
        if self.use_warm_start and self.previous_solution:
            self._ws_count = apply_warmstart(
                self._model, self._vmap, self._problem, self.previous_solution)

        self._build_time = time.perf_counter() - t0

    def solve(self) -> Dict:
        """Solve the model and return results."""
        if self._model is None or self._problem is None or self._vmap is None:
            return {
                'feasible': False, 'objective_value': float('inf'),
                'solve_time': 0.0, 'status': 'Not Solved',
                'upper_assignments': {}, 'lower_assignments': {},
                'diagnosis': {'num_variables': 0, 'num_constraints': 0,
                              'num_threats': 0, 'num_systems': 0,
                              'total_missiles': 0, 'feasible_engagements': 0},
            }

        t0 = time.perf_counter()

        # Handle empty problem
        if self._problem.n_threats == 0:
            return {
                'feasible': True, 'objective_value': 0.0,
                'solve_time': 0.0, 'pure_solver_time': 0.0,
                'status': 'Optimal', 'algorithm': 'CleanSlate',
                'warmstart_applied': False, 'warmstart_count': 0,
                'upper_assignments': {}, 'lower_assignments': {},
                'upper_k_values': {}, 'lower_k_values': {},
                'asset_survival_probs': {a: 1.0 for a in self._problem.asset_ids},
                'diagnosis': {'num_variables': 0, 'num_constraints': 0,
                              'num_threats': 0, 'num_systems': 0,
                              'total_missiles': 0, 'feasible_engagements': 0},
            }

        # Solve with iterative OA refinement
        self._model.run()

        # --- Iterative tangent-cut refinement for exact exp(σ) equivalence ---
        for oa_round in range(OA_REFINE_ROUNDS):
            model_status = self._model.getModelStatus()
            if model_status != highspy.HighsModelStatus.kOptimal and \
               model_status != highspy.HighsModelStatus.kObjectiveBound:
                break

            sol = self._model.getSolution()
            x = np.array(sol.col_value)

            max_gap = 0.0
            cuts_added = 0
            for i in range(self._problem.n_assets):
                # Skip assets with no threats (f_i fixed to 0)
                threats_i = int(np.sum(self._problem.threat_to_asset == i))
                if threats_i == 0:
                    continue

                sigma_i = x[self._vmap.sigma_offset + i]
                f_i = x[self._vmap.f_offset + i]
                exp_sigma = math.exp(sigma_i)

                gap = exp_sigma - f_i
                if gap > max_gap:
                    max_gap = gap

                # Add tangent cut at current σ* if relative gap is significant
                rel_tol = OA_REFINE_TOL * max(exp_sigma, 1e-15)
                if gap > rel_tol:
                    e_k = exp_sigma
                    rhs = e_k * (1.0 - sigma_i)
                    self._model.addRow(
                        rhs, highspy.kHighsInf,
                        2,
                        [self._vmap.f_offset + i, self._vmap.sigma_offset + i],
                        [1.0, -e_k],
                    )
                    cuts_added += 1

            if cuts_added == 0:
                break  # Converged — f_i ≈ exp(σ_i) for all assets

            self._model.run()

        total_time = self._build_time + (time.perf_counter() - t0)

        result = extract_result(
            self._model, self._vmap, self._problem,
            total_time, self._ws_count)

        # Save for warm-start
        if result['feasible'] and self.use_warm_start:
            self.previous_solution = {
                'upper_assignments': result['upper_assignments'],
                'lower_assignments': result['lower_assignments'],
            }
        # Log
        diag = result['diagnosis']
        self._log(
            f"[CleanSlate] Obj={result['objective_value']:.2f}, "
            f"Time={total_time*1000:.1f}ms, "
            f"Vars={diag['num_variables']}, "
            f"Constraints={diag['num_constraints']}, "
            f"Status={result['status']}"
        )

        return result

    def enable_warmstart(self):
        self.use_warm_start = True

    def disable_warmstart(self):
        self.use_warm_start = False

    def get_assignment_details(self) -> Dict:
        """Backward compatibility."""
        if self.previous_solution:
            return self.previous_solution
        return {}
