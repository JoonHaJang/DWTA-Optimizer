"""
config_mip.py
=============
MIP 최적화 전용 설정 파일

기존 config.py를 확장하여 MIP 모델에 특화된 설정들을 관리합니다.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Tuple, Optional, Set
import numpy as np
import itertools
from config import Config as BaseConfig

class MIPSolverConfig(BaseModel):
    """MIP 솔버 설정 (최적해 탐색 우선)"""
    solver_name: str = Field("pulp", description="사용할 솔버 (pulp, gurobi, cplex, ortools)")
    time_limit_sec: int = Field(5, description="솔버 시간 제한 (초) - GUI 응답성 우선 (60→5)")
    gap_tolerance: float = Field(0.01, description="최적성 갭 허용치 - 빠른 해 탐색 (0.0→0.01)")
    threads: int = Field(4, description="병렬 처리 스레드 수 - GUI 응답성 (4)")
    verbose: bool = Field(False, description="상세 로그 출력 여부 - GUI 성능 (True→False)")

class SLSConfig(BaseModel):
    """Shoot-Look-Shoot 설정 (실제 살보 발사 방식)"""
    evaluation_delay_sec: float = Field(3.0, description="살보 발사 간격 (첫발 → 3초 → 둘째발)")
    re_engagement_factor: float = Field(0.9, description="재교전 확률 보정 계수")
    discount_factor: float = Field(0.8, description="예비 교전 할인 계수 (δ)")
    max_engagements_per_target: int = Field(2, description="표적당 최대 교전 횟수 (살보 발사)")

class InterceptorSystemConfig(BaseModel):
    """요격 시스템 상세 스펙 설정"""
    
    @staticmethod
    def get_lsam_specs() -> Dict:
        """L-SAM (장거리 지대공 미사일) 실제 스펙"""
        return {
            "system_type": "LSAM",
            "layer": "UPPER",
            "ballistic_missile_specs": {  # 탄도탄 요격 미사일 (ABM)
                "engagement_altitude_km": {"min": 40, "max": 70},
                "engagement_range_km": {"min": 150, "max": 300},
                "simultaneous_engagements": 10,
                "intercept_probability_single": 0.85,  # 단발 요격 확률
                "intercept_probability_salvo": 0.9775,  # 2발 살보 요격 확률 (1-(1-0.85)^2)
                "missiles_per_engagement": 2  # 살보 미사일 수
            },
            "aircraft_specs": {  # 항공기 요격 미사일 (AAM)
                "engagement_altitude_km": {"min": 40, "max": 70},
                "engagement_range_km": {"min": 150, "max": 300},
                "simultaneous_engagements": 20,  # 추정
                "intercept_probability_single": 0.85,  # 단발 요격 확률
                "intercept_probability_salvo": 0.9775,  # 2발 살보 요격 확률
                "missiles_per_engagement": 2
            },
            "radar_specs": {
                "type": "S-band AESA",
                "aircraft_tracking": 100,
                "ballistic_tracking": 10,
                "detection_range_km": 400
            },
            "battery_config": {
                "launchers": 4,
                "missiles_per_launcher": 6,
                "total_missiles": 24,
                "simultaneous_engagements": 5
            }
        }
    
    @staticmethod
    def get_msam_specs() -> Dict:
        """M-SAM (중거리 지대공 미사일) 실제 스펙 - 한국형 천궁-II"""
        return {
            "system_type": "MSAM",
            "layer": "LOWER",
            "ballistic_specs": {
                "engagement_altitude_km": {"min": 0.05, "max": 40},  # 실제 한국형 체계 스펙
                "engagement_range_km": {"min": 5, "max": 50},
                "simultaneous_engagements": 8,  # 6-8개 표적
                "intercept_probability_single": 0.80,  # 단발 요격 확률
                "intercept_probability_salvo": 0.96,  # 2발 살보 요격 확률 (1-(1-0.80)^2)
                "missiles_per_engagement": 2
            },
            "ballistic_missile_specs": {
                "engagement_altitude_km": {"min": 0.05, "max": 40},  # 실제 한국형 체계 스펙
                "engagement_range_km": {"min": 5, "max": 50},
                "simultaneous_engagements": 10,
                "intercept_probability_single": 0.80,  # 단발 요격 확률
                "intercept_probability_salvo": 0.96,  # 2발 살보 요격 확률
                "missiles_per_engagement": 2
            },
            "radar_specs": {
                "type": "X-band PESA",
                "target_tracking": 40,
                "detection_range_km": 100,
                "rotation_rpm": 40,
                "elevation_coverage": 80
            },
            "battery_config": {
                "launchers": 6,  # 4-6개
                "missiles_per_launcher": 8,
                "total_missiles": 48,
                "simultaneous_engagements": 5
            }
        }

class ProbabilityConfig(BaseModel):
    """교전 타임 윈도우 기반 확률 계산 설정"""
    
    # 기본 요격 확률 (이상적 교전 조건 하)
    base_probabilities: Dict[str, float] = Field(
        default_factory=lambda: {
            "LSAM_ABM": 0.85,    # 상층 탄도탄 요격 (이상적 조건)
            "LSAM_AAM": 0.85,    # 상층 항공기 요격 (이상적 조건)
            "MSAM_AIRCRAFT": 0.78,  # 하층 항공기 요격 (이상적 조건)
            "MSAM_BALLISTIC": 0.78   # 하층 탄도탄 요격 (이상적 조건)
        },
        description="무기체계별 기본 요격 확률 (이상적 교전 조건)"
    )
    
    # 교전 타임 윈도우 모델링 파라미터 (높은 요격률 유지)
    engagement_window_config: Dict[str, Dict] = Field(
        default_factory=lambda: {
            "LSAM": {
                "optimal_window_sec": 35.0,      # 최적 교전 윈도우 (초)
                "minimum_window_sec": 12.0,      # 최소 교전 윈도우 (초)
                "maximum_range_km": 300,         # 최대 교전 거리 (km)
                "optimal_altitude_km": 55,       # 최적 교전 고도 (km) - 40-70km 범위 중앙
                "window_efficiency_factor": 0.95  # 윈도우 효율성 계수 - 높은 요격률 유지
            },
            "MSAM": {
                "optimal_window_sec": 20.0,      # 최적 교전 윈도우 (초)
                "minimum_window_sec": 8.0,       # 최소 교전 윈도우 (초)
                "maximum_range_km": 50,          # 최대 교전 거리 (km)
                "optimal_altitude_km": 12.5,     # 최적 교전 고도 (km) - 10-15km 범위 중앙
                "window_efficiency_factor": 0.92  # 윈도우 효율성 계수 - 높은 요격률 유지
            }
        },
        description="교전 타임 윈도우 모델링 설정 (높은 요격률 유지)"
    )
    
    # 다층 방어 협력 효과 계수
    layered_defense_bonus: Dict[str, float] = Field(
        default_factory=lambda: {
            "upper_lower_coordination": 0.15,  # 상층-하층 협력 보너스
            "sequential_engagement": 0.12,     # 순차적 교전 보너스
            "overlapping_coverage": 0.08       # 중첩 커버리지 보너스
        },
        description="다층 방어 협력 효과"
    )
    
    # 동적 요소 튜닝 계수 (교전 성공률 향상을 위한 조정)
    distance_factor_beta: float = Field(1.2, description="거리 요소 지수 - 완화")
    speed_factor_beta: float = Field(0.4, description="속도 요소 계수 - 완화")
    altitude_factor_gamma: float = Field(0.3, description="고도 요소 계수 - 완화")
    rcs_factor_lambda: float = Field(0.15, description="RCS 요소 계수 - 완화")
    
    # 최소/최대 확률 제한 (높은 요격률 보장)
    min_probability: float = Field(0.45, description="최소 요격 확률 - 높은 요격률 보장")
    max_probability: float = Field(0.98, description="최대 요격 확률")

class BatteryDeploymentConfig(BaseModel):
    """전구 방어 기반 포대 배치 설정 (10개 고정: 상층 5개, 하층 5개)"""
    
    @staticmethod
    def create_battery_deployment() -> List[Dict]:
        """전구 방어 구역 기반 포대 배치 - 각 자산당 전담 상층/하층 시스템 배정"""
        
        # 전구 방어 구역 정의 (중복 제거)
        defense_zones = {
            "ZONE_1_SEOUL": {
                "center": (0, 0),
                "primary_assets": ["A01", "A02", "A03"],  # 청와대, 국방부, 국정원
                "upper_battery": "LSAM_01",
                "lower_battery": "MSAM_01"
            },
            "ZONE_2_GYEONGGI": {
                "center": (-15, 10),
                "primary_assets": ["A07", "A09", "A10"],  # 인천공항, 인천항, 김포공항
                "upper_battery": "LSAM_02",
                "lower_battery": "MSAM_02"
            },
            "ZONE_3_CHUNGNAM": {
                "center": (15, -25),
                "primary_assets": ["A04", "A05"],  # 계룡대, 평택 미군기지
                "upper_battery": "LSAM_03",
                "lower_battery": "MSAM_03"
            },
            "ZONE_4_GYEONGBUK": {
                "center": (40, -35),
                "primary_assets": ["A06"],  # 오산 공군기지
                "upper_battery": "LSAM_04",
                "lower_battery": "MSAM_04"
            },
            "ZONE_5_BUSAN": {
                "center": (55, -70),
                "primary_assets": ["A08"],  # 부산항
                "upper_battery": "LSAM_05",
                "lower_battery": "MSAM_05"
            }
        }
        
        batteries = [
            # 상층 방어 (L-SAM) - 전구 방어 구역별 전담 배치
            {
                "id": "LSAM_01",
                "name": "Seoul_Theater_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (0, 0),  # 서울 전구 방어 구역
                "coverage_radius_km": 150,  # 전구 방어: 중복 제거로 반경 축소
                "defense_zone": "ZONE_1_SEOUL",
                "dedicated_assets": ["A01", "A02", "A03"],
                "specs": InterceptorSystemConfig.get_lsam_specs()
            },
            {
                "id": "LSAM_02",
                "name": "Gyeonggi_Theater_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (-15, 10),  # 경기도 전구 방어 구역
                "coverage_radius_km": 150,  # 전구 방어: 중복 제거로 반경 축소
                "defense_zone": "ZONE_2_GYEONGGI",
                "dedicated_assets": ["A07", "A09", "A10"],
                "specs": InterceptorSystemConfig.get_lsam_specs()
            },
            {
                "id": "LSAM_03",
                "name": "Chungnam_Theater_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (15, -25),  # 충남 전구 방어 구역
                "coverage_radius_km": 150,  # 전구 방어: 중복 제거로 반경 축소
                "defense_zone": "ZONE_3_CHUNGNAM",
                "dedicated_assets": ["A04", "A05"],
                "specs": InterceptorSystemConfig.get_lsam_specs()
            },
            {
                "id": "LSAM_04",
                "name": "Gyeongbuk_Theater_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (40, -35),  # 경북 전구 방어 구역
                "coverage_radius_km": 150,  # 전구 방어: 중복 제거로 반경 축소
                "defense_zone": "ZONE_4_GYEONGBUK",
                "dedicated_assets": ["A06"],
                "specs": InterceptorSystemConfig.get_lsam_specs()
            },
            {
                "id": "LSAM_05",
                "name": "Busan_Theater_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (55, -70),  # 부산 전구 방어 구역
                "coverage_radius_km": 150,  # 전구 방어: 중복 제거로 반경 축소
                "defense_zone": "ZONE_5_BUSAN",
                "dedicated_assets": ["A08"],
                "specs": InterceptorSystemConfig.get_lsam_specs()
            },
            
            # 하층 방어 (M-SAM) - 전구 방어 구역별 전담 배치
            {
                "id": "MSAM_01",
                "name": "Seoul_Theater_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (7, -5),  # 서울 전구 방어 구역 (최종 방어선)
                "coverage_radius_km": 40,  # 전구 방어: 정밀 방어를 위한 반경 조정
                "defense_zone": "ZONE_1_SEOUL",
                "dedicated_assets": ["A01", "A02", "A03"],
                "specs": InterceptorSystemConfig.get_msam_specs()
            },
            {
                "id": "MSAM_02",
                "name": "Gyeonggi_Theater_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (-20, 15),  # 경기도 전구 방어 구역 (최종 방어선)
                "coverage_radius_km": 40,  # 전구 방어: 정밀 방어를 위한 반경 조정
                "defense_zone": "ZONE_2_GYEONGGI",
                "dedicated_assets": ["A07", "A09", "A10"],
                "specs": InterceptorSystemConfig.get_msam_specs()
            },
            {
                "id": "MSAM_03",
                "name": "Chungnam_Theater_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (20, -30),  # 충남 전구 방어 구역 (최종 방어선)
                "coverage_radius_km": 40,  # 전구 방어: 정밀 방어를 위한 반경 조정
                "defense_zone": "ZONE_3_CHUNGNAM",
                "dedicated_assets": ["A04", "A05"],
                "specs": InterceptorSystemConfig.get_msam_specs()
            },
            {
                "id": "MSAM_04",
                "name": "Gyeongbuk_Theater_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (45, -40),  # 경북 전구 방어 구역 (최종 방어선)
                "coverage_radius_km": 40,  # 전구 방어: 정밀 방어를 위한 반경 조정
                "defense_zone": "ZONE_4_GYEONGBUK",
                "dedicated_assets": ["A06"],
                "specs": InterceptorSystemConfig.get_msam_specs()
            },
            {
                "id": "MSAM_05",
                "name": "Busan_Theater_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (60, -75),  # 부산 전구 방어 구역 (최종 방어선)
                "coverage_radius_km": 40,  # 전구 방어: 정밀 방어를 위한 반경 조정
                "defense_zone": "ZONE_5_BUSAN",
                "dedicated_assets": ["A08"],
                "specs": InterceptorSystemConfig.get_msam_specs()
            }
        ]
        return batteries


class AssetConfig(BaseModel):
    """방어 자산 설정 (10개 선택 - 우선순위 기반)"""
    
    @staticmethod
    def create_priority_defense_assets() -> List[Dict]:
        """우선순위 기반 주요 방어 자산 10개 선택"""
        # 전략적 가치 재정의: 군사적 중요도와 전시 운용 가치 반영
        assets = [
            # 최고 우선순위 (Priority 1) - 국가 중추 기관
            {"id": "A01", "name": "Blue_House", "position": (0, 0), "value": 1500, "priority": 1},  # 국가 상징성 강화
            {"id": "A02", "name": "Defense_Ministry", "position": (2, -1), "value": 900, "priority": 1},
            {"id": "A03", "name": "Intelligence_Service", "position": (-3, 1), "value": 850, "priority": 1},
            
            # 높은 우선순위 (Priority 2) - 전략적 가치 순 재정렬
            {"id": "A04", "name": "Gyeryong_Command", "position": (15, -25), "value": 950, "priority": 2},  # 군 지휘부 최고 우선순위
            {"id": "A05", "name": "Pyeongtaek_US_Base", "position": (5, -15), "value": 900, "priority": 2},  # 동맹 군사기지 강화
            {"id": "A06", "name": "Osan_Air_Base", "position": (8, -20), "value": 850, "priority": 2},  # 공군 작전 기지
            {"id": "A07", "name": "Incheon_Airport", "position": (-25, 15), "value": 800, "priority": 2},  # 국제 공항
            {"id": "A08", "name": "Busan_Port", "position": (50, -80), "value": 750, "priority": 2},  # 주요 항구
            {"id": "A09", "name": "Incheon_Port", "position": (-20, 10), "value": 700, "priority": 2},  # 수도권 항구
            {"id": "A10", "name": "Gimpo_Airport", "position": (-10, 5), "value": 650, "priority": 2}   # 국내 공항
        ]
        
        # 우선순위별 가중치 적용
        priority_weights = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4}
        for asset in assets:
            asset["weighted_value"] = asset["value"] * priority_weights[asset["priority"]]
        return assets

class ThreatMissileConfig(BaseModel):
    """위협 미사일 설정 (15발 탄도탄)"""
    
    @staticmethod
    def create_ballistic_missile_threats() -> List[Dict]:
        """세밀한 시간 기반 북한 탄도탄 15발 시나리오 (노동 + Scud-B)"""
        threats = [
            # === 1차 공격파 (노동 미사일) - 8발 ===
            # 15초 간격 순차 발사, 장거리 탄도탄으로 8분 비행시간 (최소 80km 거리 보장)
            {"id": "T01", "name": "Nodong_1", "type": "NODONG", 
             "target_asset_id": "A01", "launch_time": 0, "flight_time": 480,
             "launch_position": (0, 180), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 160,    # 발사 후 1/3 지점 (최적 요격 구간)
                 "terminal_time": 320,     # 발사 후 2/3 지점 (마지막 요격 기회)
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T02", "name": "Nodong_2", "type": "NODONG", 
             "target_asset_id": "A02", "launch_time": 15, "flight_time": 465,
             "launch_position": (-30, 170), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 170,
                 "terminal_time": 325,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T03", "name": "Nodong_3", "type": "NODONG", 
             "target_asset_id": "A04", "launch_time": 30, "flight_time": 450,
             "launch_position": (35, 190), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 180,
                 "terminal_time": 330,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T04", "name": "Nodong_4", "type": "NODONG", 
             "target_asset_id": "A06", "launch_time": 45, "flight_time": 470,
             "launch_position": (15, 175), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 202,
                 "terminal_time": 358,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T05", "name": "Nodong_5", "type": "NODONG", 
             "target_asset_id": "A08", "launch_time": 60, "flight_time": 485,
             "launch_position": (20, 185), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 222,
                 "terminal_time": 383,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800,
                 "retarget_opportunity": 150  # T+150초에 재목표 가능성
             }},
            {"id": "T06", "name": "Nodong_6", "type": "NODONG", 
             "target_asset_id": "A09", "launch_time": 75, "flight_time": 460,
             "launch_position": (-25, 165), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 228,
                 "terminal_time": 382,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T07", "name": "Nodong_7", "type": "NODONG", 
             "target_asset_id": "A10", "launch_time": 90, "flight_time": 475,
             "launch_position": (40, 195), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 248,
                 "terminal_time": 407,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
            {"id": "T08", "name": "Nodong_8", "type": "NODONG", 
             "target_asset_id": "A05", "launch_time": 105, "flight_time": 455,
             "launch_position": (-15, 180), "trajectory_type": "ballistic", "rcs": 1.5,
             "phase_events": {
                 "midcourse_time": 257,
                 "terminal_time": 408,
                 "critical_altitude_km": 45.0,
                 "terminal_velocity_ms": 1800
             }},
             
            # === 2차 공격파 (Scud-B 미사일) - 7발 ===
            # 15초 간격 집중 발사, 단거리 탄도탄으로 4분 비행시간 (최소 80km 거리 보장)
            {"id": "T09", "name": "ScudB_1", "type": "SCUD_B", 
             "target_asset_id": "A03", "launch_time": 120, "flight_time": 240,
             "launch_position": (10, 110), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 240,    # 중간 코스 (더 짧은 비행시간)
                 "terminal_time": 300,     # 터미널 단계
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }},
            {"id": "T10", "name": "ScudB_2", "type": "SCUD_B", 
             "target_asset_id": "A07", "launch_time": 135, "flight_time": 235,
             "launch_position": (-15, 105), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 252,
                 "terminal_time": 313,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200,
                 "retarget_opportunity": 200  # T+200초에 재목표 가능성
             }},
            {"id": "T11", "name": "ScudB_3", "type": "SCUD_B", 
             "target_asset_id": "A01", "launch_time": 150, "flight_time": 245,
             "launch_position": (20, 115), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 272,
                 "terminal_time": 333,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }},
            {"id": "T12", "name": "ScudB_4", "type": "SCUD_B", 
             "target_asset_id": "A02", "launch_time": 165, "flight_time": 230,
             "launch_position": (-20, 100), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 280,
                 "terminal_time": 342,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }},
            {"id": "T13", "name": "ScudB_5", "type": "SCUD_B", 
             "target_asset_id": "A04", "launch_time": 180, "flight_time": 250,
             "launch_position": (25, 120), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 305,
                 "terminal_time": 363,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }},
            {"id": "T14", "name": "ScudB_6", "type": "SCUD_B", 
             "target_asset_id": "A06", "launch_time": 195, "flight_time": 225,
             "launch_position": (-10, 95), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 307,
                 "terminal_time": 363,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }},
            {"id": "T15", "name": "ScudB_7", "type": "SCUD_B", 
             "target_asset_id": "A08", "launch_time": 210, "flight_time": 240,
             "launch_position": (15, 108), "trajectory_type": "ballistic", "rcs": 0.8,
             "phase_events": {
                 "midcourse_time": 330,
                 "terminal_time": 390,
                 "critical_altitude_km": 25.0,
                 "terminal_velocity_ms": 1200
             }}
        ]
        
        # 실제 미사일별 스펙 추가 (노동 + Scud-B)
        missile_specs = {
            "NODONG": {
                "max_range_km": 1300,      # 노동 미사일 실제 사거리
                "max_altitude_km": 80,      # 탄도궤적 최대 고도 (추정)
                "speed_mach": 3.5,          # 마하 3-4 (현실적 속도)
                "payload_kg": 800,          # 실제 페이로드
                "cep_m": 2000,              # 원형공산오차 2km
                "launch_weight_kg": 16500   # 발사중량
            },
            "SCUD_B": {
                "max_range_km": 300,        # Scud-B 실제 사거리
                "max_altitude_km": 40,       # 탄도궤적 최대 고도
                "speed_mach": 2.5,          # 마하 2-3 (현실적 속도)
                "payload_kg": 985,          # 실제 페이로드
                "cep_m": 450,               # 원형공산오차 450m
                "launch_weight_kg": 5900    # 발사중량
            }
        }
        
        # 위협별 세밀한 타임라인 정보 추가
        for threat in threats:
            threat["specs"] = missile_specs[threat["type"]]
            threat["estimated_impact_time"] = threat["launch_time"] + threat["flight_time"]
            
            # 단계별 이벤트 시간 계산
            if "phase_events" in threat:
                events = threat["phase_events"]
                threat["midcourse_absolute_time"] = threat["launch_time"] + events["midcourse_time"]
                threat["terminal_absolute_time"] = threat["launch_time"] + events["terminal_time"]
                
                # 최적 요격 윈도우 계산 (중간코스 ±30초)
                threat["optimal_intercept_window"] = {
                    "start": threat["midcourse_absolute_time"] - 30,
                    "end": threat["midcourse_absolute_time"] + 30
                }
                
                # 마지막 요격 기회 (터미널 단계 시작)
                threat["last_intercept_time"] = threat["terminal_absolute_time"]
        
        return threats

class LaunchBaseConfig(BaseModel):
    """북한 미사일 발사 기지 설정"""
    
    @staticmethod
    def create_north_korean_bases() -> Dict[str, Dict]:
        """North Korean missile launch bases information"""
        return {
            "Pyongyang": {"coords": (39.0392, 125.7625), "weight": 0.3},
            "Hamhung": {"coords": (39.9180, 127.5360), "weight": 0.2},
            "Wonsan": {"coords": (39.1547, 127.4453), "weight": 0.15},
            "Sinpo": {"coords": (40.1031, 128.1847), "weight": 0.1},
            "Musudan_ri": {"coords": (40.8581, 129.6667), "weight": 0.1},
            "Dongchang_ri": {"coords": (39.6603, 124.7056), "weight": 0.1},
            "Cheolsan": {"coords": (39.7833, 124.8333), "weight": 0.05}
        }

class ThreatScenarioConfig(BaseModel):
    """위협 시나리오 설정"""
    
    scenarios: Dict[str, Dict] = Field(
        default_factory=lambda: {
            "north_korea_conventional": {
                "name": "NK_Conventional",
                "missile_types": {"SRBM": 0.6, "MBRM": 0.3, "IRBM": 0.1},
                "threat_count": 50,
                "attack_pattern": "saturation",
                "target_preference": "government_military",
                "salvo_interval": 15.0
            },
            "north_korea_escalated": {
                "name": "NK_Escalated",
                "missile_types": {"IRBM": 0.4, "ICBM": 0.2, "SRBM": 0.4},
                "threat_count": 60,
                "attack_pattern": "precision_then_saturation",
                "target_preference": "critical_infrastructure",
                "salvo_interval": 20.0
            },
            "multi_vector_attack": {
                "name": "Multi_Vector_Attack",
                "missile_types": {"SRBM": 0.3, "MBRM": 0.3, "IRBM": 0.3, "ICBM": 0.1},
                "threat_count": 70,
                "attack_pattern": "coordinated_multi_axis",
                "target_preference": "economic_centers",
                "salvo_interval": 10.0
            },
            "precision_strike": {
                "name": "Precision_Strike",
                "missile_types": {"IRBM": 0.5, "ICBM": 0.3, "MBRM": 0.2},
                "threat_count": 50,
                "attack_pattern": "precision_sequential",
                "target_preference": "command_control",
                "salvo_interval": 30.0
            },
            "sustained_campaign": {
                "name": "Sustained_Campaign",
                "missile_types": {"SRBM": 0.5, "MBRM": 0.4, "IRBM": 0.1},
                "threat_count": 80,
                "attack_pattern": "wave_attack",
                "target_preference": "broad_spectrum",
                "salvo_interval": 5.0
            }
        }
    )

class EngagementZoneConfig(BaseModel):
    """교전 영역 계산 설정 - 궁적 기반 교전 영역 모델링"""
    
    @staticmethod
    def calculate_trajectory_intercept_point(threat: Dict, intercept_time: float, assets: List[Dict] = None) -> Dict:
        """미사일 궤적에서 교전 시점의 위치와 고도 계산"""
        import math
        
        launch_pos = threat["launch_position"]
        
        # 목표 위치 가져오기 (threat에 직접 포함되어 있으면 사용)
        target_pos = threat.get("target_position")
        
        if not target_pos:
            # 목표 자산 위치 찾기
            if assets is None:
                assets = AssetConfig.create_priority_defense_assets()
            for asset in assets:
                if asset["id"] == threat.get("target_asset_id"):
                    target_pos = asset["position"]
                    break
        
        if not target_pos:
            return None
        
        # 미사일 스펙 (안전한 속성 접근)
        missile_specs = getattr(threat, 'specs', threat.get('specs', {}))
        flight_time = getattr(threat, 'flight_time', threat.get('flight_time', 100))
        max_altitude = getattr(missile_specs, 'max_altitude_km', missile_specs.get('max_altitude_km', 50.0))
        
        # critical_altitude_km 가져오기 (phase_events에서)
        phase_events = getattr(threat, 'phase_events', threat.get('phase_events', {}))
        critical_altitude = getattr(phase_events, 'critical_altitude_km', 
                                   phase_events.get('critical_altitude_km', max_altitude * 0.7))
        
        # 탄도 궤적 계산 (포물선 근사)
        total_distance = math.sqrt(
            (target_pos[0] - launch_pos[0])**2 + 
            (target_pos[1] - launch_pos[1])**2
        )
        
        # 교전 시점에서의 위치 (비선형 보간)
        time_ratio = intercept_time / flight_time
        
        if time_ratio < 0 or time_ratio > 1:
            return None
        
        # 수평 위치 (선형 보간)
        intercept_x = launch_pos[0] + (target_pos[0] - launch_pos[0]) * time_ratio
        intercept_y = launch_pos[1] + (target_pos[1] - launch_pos[1]) * time_ratio
        
        # 고도 계산 (critical_altitude 기준 포물선)
        # critical_altitude를 최대 고도로 사용하여 교전 윈도우 확장
        if time_ratio <= 0.5:  # 상승기
            altitude = critical_altitude * (2 * time_ratio)
        else:  # 하강기
            altitude = critical_altitude * (2 * (1 - time_ratio))
        
        return {
            "position": (intercept_x, intercept_y),
            "altitude_km": altitude,
            "time": intercept_time
        }
    
    @staticmethod
    def can_engage_trajectory(battery: Dict, threat: Dict, assets: List[Dict] = None) -> Dict:
        """궤적 기반 교전 가능성 및 교전 시간 윈도우 계산"""
        import math
        
        battery_pos = battery["position"]
        specs = battery["specs"]
        
        # 시스템 별 교전 스펙
        if battery["system_type"] == "LSAM":
            engagement_specs = specs["ballistic_missile_specs"]
        else:  # MSAM
            engagement_specs = specs["ballistic_missile_specs"]
        
        min_range = engagement_specs["engagement_range_km"]["min"]
        max_range = engagement_specs["engagement_range_km"]["max"]
        min_altitude = engagement_specs["engagement_altitude_km"]["min"]
        max_altitude = engagement_specs["engagement_altitude_km"]["max"]
        
        # 교전 가능 시간 윈도우 찾기
        flight_time = threat["flight_time"]
        engagement_windows = []
        
        # 10초 간격으로 궤적 상의 지점들 검사
        for t in range(0, int(flight_time), 10):
            intercept_point = EngagementZoneConfig.calculate_trajectory_intercept_point(threat, t, assets)
            
            if not intercept_point:
                continue
            
            # 거리 계산
            distance = math.sqrt(
                (battery_pos[0] - intercept_point["position"][0])**2 + 
                (battery_pos[1] - intercept_point["position"][1])**2
            )
            
            altitude = intercept_point["altitude_km"]
            
            # 교전 가능 조건 확인
            if (min_range <= distance <= max_range and 
                min_altitude <= altitude <= max_altitude):
                engagement_windows.append({
                    "time": t,
                    "distance": distance,
                    "altitude": altitude,
                    "position": intercept_point["position"]
                })
        
        return {
            "can_engage": len(engagement_windows) > 0,
            "engagement_windows": engagement_windows,
            "optimal_time": engagement_windows[0]["time"] if engagement_windows else None
        }
    
    @staticmethod
    def can_engage(battery: Dict, threat: Dict, assets: List[Dict] = None) -> bool:
        """포대가 위협을 교전할 수 있는지 계산 (궁적 기반)"""
        
        # 궁적 기반 교전 가능성 계산
        engagement_analysis = EngagementZoneConfig.can_engage_trajectory(battery, threat, assets)
        return engagement_analysis["can_engage"]
    
    @staticmethod
    def create_engagement_matrix() -> Dict:
        """교전 가능성 매트릭스 생성 (궁적 기반)"""
        batteries = BatteryDeploymentConfig.create_battery_deployment()
        threats = ThreatMissileConfig.create_ballistic_missile_threats()
        
        engagement_matrix = {}
        detailed_analysis = {}
        
        print("\nCalculating trajectory-based engagement zones...")
        
        for battery in batteries:
            for threat in threats:
                key = (battery["id"], threat["id"])
                
                try:
                    # 궤적 기반 상세 분석 (assets는 기본값 사용)
                    analysis = EngagementZoneConfig.can_engage_trajectory(battery, threat, None)
                    engagement_matrix[key] = analysis["can_engage"]
                    detailed_analysis[key] = analysis
                except Exception as e:
                    print(f"Warning: Failed to analyze {key}: {e}")
                    # 기본값으로 교전 불가능 설정
                    engagement_matrix[key] = False
                    detailed_analysis[key] = {"can_engage": False, "engagement_windows": [], "error": str(e)}
        
        # 교전 가능성 통계
        total_pairs = len(engagement_matrix)
        feasible_pairs = sum(engagement_matrix.values())
        
        print(f"Trajectory-based engagement analysis complete:")
        print(f"  Total battery-threat pairs: {total_pairs}")
        print(f"  Feasible engagements: {feasible_pairs} ({100*feasible_pairs/total_pairs:.1f}%)")
        
        # 시스템별 교전 가능성
        lsam_engagements = sum(1 for (battery_id, threat_id), can_engage in engagement_matrix.items() 
                              if battery_id.startswith('LSAM') and can_engage)
        msam_engagements = sum(1 for (battery_id, threat_id), can_engage in engagement_matrix.items() 
                              if battery_id.startswith('MSAM') and can_engage)
        
        print(f"  LSAM engagements: {lsam_engagements}")
        print(f"  MSAM engagements: {msam_engagements}")
        
        # LSAM 교전 디버깅: 각 LSAM-위협 조합 상세 분석
        print("\nLSAM Engagement Debug:")
        for battery in batteries:
            if battery["system_type"] == "LSAM":
                battery_id = battery["id"]
                print(f"\n{battery_id} analysis:")
                for threat in threats:
                    threat_id = threat["id"]
                    key = (battery_id, threat_id)
                    can_engage = engagement_matrix.get(key, False)
                    
                    if can_engage:
                        print(f"  [OK] {threat_id}: CAN ENGAGE")
                    else:
                        print(f"  [NO] {threat_id}: CANNOT ENGAGE")
                        # 상세 분석 (assets는 기본값 사용)
                        analysis = EngagementZoneConfig.can_engage_trajectory(battery, threat, None)
                        print(f"     - Windows: {len(analysis.get('engagement_windows', []))}")
                        print(f"     - Threat type: {threat.get('type', 'Unknown')}")
                        print(f"     - Max altitude: {threat.get('specs', {}).get('max_altitude_km', 'Unknown')}km")
        
        return engagement_matrix
    
    @staticmethod
    def calculate_engagement_time_window(battery: Dict, threat: Dict) -> Dict:
        """교전 타임 윈도우 계산 - 궁적 기반 실시간 분석"""
        import math
        
        battery_pos = battery["position"]
        battery_range = battery["coverage_radius_km"]
        system_type = battery["system_type"]
        
        # 위협 미사일 궁적 정보
        launch_pos = threat["launch_position"]
        target_asset_id = threat["target_asset_id"]
        flight_time = threat["flight_time"]
        missile_specs = threat["specs"]
        
        # 목표 자산 위치 찾기
        assets = AssetConfig.create_priority_defense_assets()
        target_pos = None
        for asset in assets:
            if asset["id"] == target_asset_id:
                target_pos = asset["position"]
                break
        
        if not target_pos:
            return {"engagement_window_sec": 0, "can_engage": False, "window_quality": 0.0}
        
        # 미사일 총 비행 거리
        total_distance = math.sqrt(
            (target_pos[0] - launch_pos[0])**2 + 
            (target_pos[1] - launch_pos[1])**2
        )
        
        # 미사일 평균 속도 (km/s)
        avg_missile_speed = total_distance / flight_time if flight_time > 0 else 1.0
        
        # 포대에서 미사일 궁적까지의 거리 계산
        engagement_opportunities = []
        
        # 미사일 궁적을 시간별로 샘플링 (0.5초 간격)
        time_step = 0.5  # 초
        for t in range(int(flight_time / time_step)):
            current_time = t * time_step
            
            # 현재 시점에서 미사일 위치 계산
            intercept_point = EngagementZoneConfig.calculate_trajectory_intercept_point(
                threat, current_time
            )
            
            if intercept_point:
                missile_pos = intercept_point["position"]
                missile_altitude = intercept_point["altitude_km"]
                
                # 포대에서 미사일까지의 거리
                distance_to_missile = math.sqrt(
                    (missile_pos[0] - battery_pos[0])**2 + 
                    (missile_pos[1] - battery_pos[1])**2
                )
                
                # 교전 가능 범위 내인지 확인
                if distance_to_missile <= battery_range:
                    engagement_opportunities.append({
                        "time": current_time,
                        "distance": distance_to_missile,
                        "altitude": missile_altitude,
                        "missile_speed": avg_missile_speed
                    })
        
        # 교전 윈도우 계산
        if not engagement_opportunities:
            return {"engagement_window_sec": 0, "can_engage": False, "window_quality": 0.0}
        
        # 연속된 교전 기회 찾기
        engagement_window_sec = len(engagement_opportunities) * time_step
        
        # 교전 품질 평가 (0.0 ~ 1.0)
        prob_config = ProbabilityConfig()
        window_config = prob_config.engagement_window_config[system_type]
        
        optimal_window = window_config["optimal_window_sec"]
        minimum_window = window_config["minimum_window_sec"]
        
        # 윈도우 품질 계산
        if engagement_window_sec >= optimal_window:
            window_quality = 1.0  # 최적 윈도우
        elif engagement_window_sec >= minimum_window:
            # 선형 보간
            window_quality = (engagement_window_sec - minimum_window) / (optimal_window - minimum_window)
        else:
            # 최소 윈도우 미달
            window_quality = 0.2 * (engagement_window_sec / minimum_window)
        
        # 최적 거리/고도 고려
        avg_distance = sum(opp["distance"] for opp in engagement_opportunities) / len(engagement_opportunities)
        avg_altitude = sum(opp["altitude"] for opp in engagement_opportunities) / len(engagement_opportunities)
        
        optimal_range = window_config["maximum_range_km"] * 0.6  # 최적 거리는 최대의 60%
        optimal_altitude = window_config["optimal_altitude_km"]
        
        # 거리 효율성
        if avg_distance <= optimal_range:
            distance_efficiency = 1.0
        else:
            distance_efficiency = max(0.3, optimal_range / avg_distance)
        
        # 고도 효율성
        altitude_diff = abs(avg_altitude - optimal_altitude)
        altitude_efficiency = max(0.4, 1.0 - (altitude_diff / optimal_altitude))
        
        # 종합 윈도우 품질
        final_quality = window_quality * distance_efficiency * altitude_efficiency
        
        return {
            "engagement_window_sec": engagement_window_sec,
            "can_engage": engagement_window_sec >= minimum_window,
            "window_quality": min(1.0, max(0.0, final_quality)),
            "avg_distance_km": avg_distance,
            "avg_altitude_km": avg_altitude,
            "opportunities_count": len(engagement_opportunities)
        }
    
    @staticmethod
    def calculate_window_adjusted_probability(battery: Dict, threat: Dict, base_probability: float) -> float:
        """교전 윈도우 기반 조정된 요격 확률 계산"""
        window_analysis = EngagementZoneConfig.calculate_engagement_time_window(battery, threat)
        
        if not window_analysis["can_engage"]:
            return 0.0
        
        window_quality = window_analysis["window_quality"]
        system_type = battery["system_type"]
        
        # 기본 확률에 윈도우 품질 적용
        prob_config = ProbabilityConfig()
        window_config = prob_config.engagement_window_config[system_type]
        efficiency_factor = window_config["window_efficiency_factor"]
        
        # 윈도우 품질에 따른 확률 조정 (더 관대한 조정)
        # 기본 확률의 90% 이상을 보장하고, 윈도우 품질에 따라 10% 범위에서만 조정
        quality_bonus = (1 - efficiency_factor) * window_quality * 0.5  # 품질 보너스 완화
        adjusted_probability = base_probability * (efficiency_factor + quality_bonus)
        
        # 기본 확률의 85% 이상은 항상 보장
        guaranteed_minimum = base_probability * 0.85
        
        # 범위 제한
        min_prob = max(prob_config.min_probability, guaranteed_minimum)
        max_prob = prob_config.max_probability
        
        return max(min_prob, min(max_prob, adjusted_probability))

class ScenarioManager:
    """다양한 위협 시나리오 버전 관리 클래스"""
    
    @staticmethod
    def get_scenario_list() -> Dict[str, str]:
        """사용 가능한 시나리오 목록 반환 (확장성 테스트 최적화)"""
        return {
            # Small 시나리오 (알고리즘 기본 성능 검증)
            "SMALL_3": "초소규모 (3발 - 알고리즘 검증)",
            "SMALL_5": "소규모 (5발 - 기본 성능)",
            "SMALL_8": "소중규모 (8발 - 전환점 테스트)",
            
            # Medium 시나리오 (실전 시나리오)
            "MEDIUM_10": "중소규모 (10발 - 일반 공격)",
            "BASELINE_15": "중규모 기본 (15발 - 표준 시나리오)",
            "MEDIUM_20": "중대규모 (20발 - 균형 공격)",
            
            # Large 시나리오 (확장성 한계 테스트)
            "LARGE_30": "대규모 (30발 - 포화 공격)",
            "LARGE_40": "초대규모 (40발 - 한계 테스트)",
            
            # Stress 시나리오 (MIP 솔버 성능 한계 검증)
            "STRESS_100": "스트레스 테스트 (100발 - 성능 검증)",
            "STRESS_150": "스트레스 테스트 (150발 - 점진적 확장)",
            "STRESS_200": "스트레스 테스트 (200발 - 한계 탐색)",
            "STRESS_300": "스트레스 테스트 (300발 - 극한 테스트)",
            
            # 패턴 테스트 (발사 패턴 분석)
            "SEQUENTIAL_15": "순차 공격 (15발 - 순차 발사)",
            "SIMULTANEOUS_15": "동시 공격 (15발 - 동시 발사)"
        }
    
    @staticmethod
    def create_small_attack_3(base_threats: List[Dict]) -> List[Dict]:
        """초소규모 공격 시나리오 (3발 - 알고리즘 검증)"""
        selected = [base_threats[i].copy() for i in [0, 1, 2]]  # T01-T03
        
        # 발사 시간: 40초 간격 순차 발사
        for i, threat in enumerate(selected):
            threat['launch_time'] = i * 40
            threat['id'] = f"T{i+1:02d}"
        
        return selected
    
    @staticmethod
    def create_small_attack_5(base_threats: List[Dict]) -> List[Dict]:
        """소규모 공격 시나리오 (5발 - 기본 성능)"""
        selected = [base_threats[i].copy() for i in [0, 1, 2, 3, 4]]  # T01-T05
        
        # 발사 시간: 30초 간격 순차 발사
        for i, threat in enumerate(selected):
            threat['launch_time'] = i * 30
            threat['id'] = f"T{i+1:02d}"
        
        return selected
    
    @staticmethod
    def create_small_attack_8(base_threats: List[Dict]) -> List[Dict]:
        """소중규모 공격 시나리오 (8발 - 전환점 테스트)"""
        selected = [base_threats[i].copy() for i in range(8)]  # T01-T08
        
        # 발사 시간: 25초 간격 순차 발사
        for i, threat in enumerate(selected):
            threat['launch_time'] = i * 25
            threat['id'] = f"T{i+1:02d}"
        
        return selected
    
    @staticmethod
    def create_medium_attack_10(base_threats: List[Dict]) -> List[Dict]:
        """중소규모 공격 시나리오 (10발 - 일반 공격)"""
        selected = [base_threats[i].copy() for i in range(10)]  # T01-T10
        
        # 발사 시간: 20초 간격 순차 발사
        for i, threat in enumerate(selected):
            threat['launch_time'] = i * 20
            threat['id'] = f"T{i+1:02d}"
        
        return selected
    
    @staticmethod
    def create_medium_attack_20(base_threats: List[Dict]) -> List[Dict]:
        """중대규모 공격 시나리오 (20발 - 균형 공격)"""
        threats = []
        
        # 기본 15발 + 5발 추가
        for i in range(20):
            threat = base_threats[i % 15].copy()
            threat['id'] = f"T{i+1:02d}"
            threat['name'] = f"{threat['type']}_{i+1}"
            # 발사 시간: 15초 간격
            threat['launch_time'] = i * 15
            threats.append(threat)
        
        return threats
    
    @staticmethod
    def create_heavy_attack_30(base_threats: List[Dict]) -> List[Dict]:
        """대규모 포화 공격 시나리오 (30발 - 집중 발사)"""
        threats = []
        
        # 기본 15발을 2배로 복제하여 30발 생성
        for i in range(2):
            for j, threat in enumerate(base_threats):
                new_threat = threat.copy()
                new_threat['id'] = f"T{i*15 + j + 1:02d}"
                new_threat['name'] = f"{threat['type']}_{i*15 + j + 1}"
                # 발사 시간: 10초 간격으로 집중 발사
                new_threat['launch_time'] = (i * 15 + j) * 10
                threats.append(new_threat)
        
        return threats
    
    @staticmethod
    def create_large_attack_40(base_threats: List[Dict]) -> List[Dict]:
        """초대규모 공격 시나리오 (40발 - 한계 테스트)"""
        threats = []
        
        # 기본 15발을 반복하여 40발 생성
        for i in range(40):
            threat = base_threats[i % 15].copy()
            threat['id'] = f"T{i+1:02d}"
            threat['name'] = f"{threat['type']}_{i+1}"
            # 발사 시간: 8초 간격으로 집중 발사
            threat['launch_time'] = i * 8
            threats.append(threat)
        
        return threats
    
    @staticmethod
    def create_sequential_attack_15(base_threats: List[Dict]) -> List[Dict]:
        """순차 공격 시나리오 (15발 - 순차 발사)"""
        threats = []
        
        # 기본 15발 사용
        # 발사 시간: 25초 간격으로 순차 발사
        for i, threat in enumerate(base_threats):
            new_threat = threat.copy()
            new_threat['id'] = f"T{i+1:02d}"
            new_threat['name'] = f"{threat['type']}_{i+1}"
            new_threat['launch_time'] = i * 25
            threats.append(new_threat)
        
        return threats
    
    @staticmethod
    def create_simultaneous_attack_15(base_threats: List[Dict]) -> List[Dict]:
        """동시 공격 시나리오 (15발 - 동시 발사)"""
        threats = []
        
        # 기본 15발을 3개 웨이브로 나누어 동시 발사
        wave_times = [0, 60, 120]  # 0초, 60초, 120초에 발사
        
        for i, threat in enumerate(base_threats):
            new_threat = threat.copy()
            new_threat['id'] = f"T{i+1:02d}"
            new_threat['name'] = f"{threat['type']}_{i+1}"
            # 각 웨이브마다 동시 발사 (±2초 편차)
            wave_idx = i // 5
            new_threat['launch_time'] = wave_times[wave_idx] + (i % 5) * 2
            threats.append(new_threat)
        
        return threats
    
    @staticmethod
    def create_stress_test_100(base_threats: List[Dict]) -> List[Dict]:
        """스트레스 테스트 시나리오 (100발 - 성능 한계 검증)"""
        return ScenarioManager._create_stress_test(base_threats, 100, interval=10)
    
    @staticmethod
    def create_stress_test_150(base_threats: List[Dict]) -> List[Dict]:
        """스트레스 테스트 시나리오 (150발 - 점진적 확장)"""
        return ScenarioManager._create_stress_test(base_threats, 150, interval=6)
    
    @staticmethod
    def create_stress_test_200(base_threats: List[Dict]) -> List[Dict]:
        """스트레스 테스트 시나리오 (200발 - 한계 탐색)"""
        return ScenarioManager._create_stress_test(base_threats, 200, interval=5)
    
    @staticmethod
    def create_stress_test_300(base_threats: List[Dict]) -> List[Dict]:
        """스트레스 테스트 시나리오 (300발 - 극한 테스트)"""
        return ScenarioManager._create_stress_test(base_threats, 300, interval=3)
    
    @staticmethod
    def _create_stress_test(base_threats: List[Dict], count: int, interval: int) -> List[Dict]:
        """스트레스 테스트 공통 생성 함수
        
        Args:
            base_threats: 기본 위협 템플릿 (15발)
            count: 생성할 위협 수
            interval: 발사 간격 (초)
        
        개선사항: 발사 거리를 순차적으로 증가시켜 시간에 따라 자연스럽게 다가오도록 설정
        - 초기 위협: 가까운 거리 (100-120km)
        - 중기 위협: 중간 거리 (120-160km)
        - 후기 위협: 먼 거리 (160-200km)
        """
        threats = []
        
        for i in range(count):
            threat = base_threats[i % 15].copy()
            threat['id'] = f"T{i+1:03d}"
            threat['name'] = f"{threat['type']}_{i+1}"
            threat['launch_time'] = i * interval
            
            # 발사 거리 순차 증가
            base_distance = 100
            distance_increment = i * 1.0
            target_distance = base_distance + distance_increment
            
            # launch_position 조정
            original_launch_y = threat['launch_position'][1]
            new_launch_y = original_launch_y + distance_increment
            threat['launch_position'] = (threat['launch_position'][0], new_launch_y)
            
            # flight_time 조정
            original_flight_time = threat.get('flight_time', 300)
            distance_ratio = target_distance / base_distance
            threat['flight_time'] = int(original_flight_time * distance_ratio)
            
            threats.append(threat)
        
        return threats

class MIPConfig(BaseModel):
    """MIP 최적화 통합 설정 - 현실적 규모 버전"""
    
    base_config: BaseConfig = Field(default_factory=BaseConfig)
    solver_config: MIPSolverConfig = Field(default_factory=MIPSolverConfig)
    sls_config: SLSConfig = Field(default_factory=SLSConfig)
    probability_config: ProbabilityConfig = Field(default_factory=ProbabilityConfig)
    
    # 현실적 규모 설정
    num_assets: int = Field(10, description="방어 자산 수")
    num_batteries: int = Field(10, description="총 포대 수 (LSAM 5개 + MSAM 5개)")
    num_threats: int = Field(15, description="위협 미사일 수")
    
    weapon_types: List[str] = Field(["LSAM", "MSAM"], description="사용 가능한 무기체계")
    time_step_sec: float = Field(1.0, description="시간 단계 (초)")
    simulation_duration_sec: float = Field(800.0, description="시뮬레이션 지속 시간 (13.3분)")
    
    # 시나리오 선택 (기본값: DWTA_BALANCED)
    scenario_type: str = Field("DWTA_BALANCED", description="시나리오 타입")
    
    def get_defense_assets(self):
        """방어 자산 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용"""
        # 🔧 통합: scenario_dwta_balanced.py의 ScenarioManager 사용
        try:
            from scenario_dwta_balanced import ScenarioManager
            scenario_data = ScenarioManager.create_scenario(self.scenario_type)
            return scenario_data["assets"]
        except (ImportError, ValueError) as e:
            print(f"Warning: Failed to load assets for '{self.scenario_type}': {e}")
            print("Falling back to default assets")
            return AssetConfig.create_priority_defense_assets()
    
    def get_battery_deployment(self):
        """포대 배치 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용"""
        # 🔧 통합: scenario_dwta_balanced.py의 ScenarioManager 사용
        try:
            from scenario_dwta_balanced import ScenarioManager
            scenario_data = ScenarioManager.create_scenario(self.scenario_type)
            return scenario_data["batteries"]
        except (ImportError, ValueError) as e:
            print(f"Warning: Failed to load batteries for '{self.scenario_type}': {e}")
            print("Falling back to default battery deployment")
            return BatteryDeploymentConfig.create_battery_deployment()
    
    def get_threat_missiles(self, scenario_type: Optional[str] = None):
        """위협 미사일 목록 반환 - scenario_dwta_balanced.py의 ScenarioManager 사용"""
        if scenario_type is None:
            scenario_type = self.scenario_type
        
        # 🔧 통합: scenario_dwta_balanced.py의 ScenarioManager 사용
        try:
            from scenario_dwta_balanced import ScenarioManager
            scenario_data = ScenarioManager.create_scenario(scenario_type)
            return scenario_data["threats"]
        except (ImportError, ValueError) as e:
            print(f"Warning: Failed to load scenario '{scenario_type}': {e}")
            print("Falling back to BASELINE_15")
            # Fallback: 기본 15발 시나리오
            return ThreatMissileConfig.create_ballistic_missile_threats()
    
    def get_engagement_matrix(self):
        """교전 가능성 매트릭스 반환"""
        return EngagementZoneConfig.create_engagement_matrix()
    
    def get_interceptor_specs(self, system_type: str):
        """요격 시스템 스펙 반환"""
        if system_type == "LSAM":
            return InterceptorSystemConfig.get_lsam_specs()
        elif system_type == "MSAM":
            return InterceptorSystemConfig.get_msam_specs()
        else:
            raise ValueError(f"Unknown system type: {system_type}")
    
    def get_launch_bases(self) -> Dict[str, Dict]:
        """발사 기지 목록 반환"""
        return LaunchBaseConfig.create_north_korean_bases()
    
    def get_threat_scenarios(self):
        """위협 시나리오 목록 반환"""
        return ThreatScenarioConfig().scenarios
    
    def create_realistic_scenario(self, scenario_type: Optional[str] = None) -> Dict:
        """현실적인 시나리오 생성 - 시나리오 타입에 따라 다른 위협 구성"""
        if scenario_type is None:
            scenario_type = self.scenario_type
        
        # 시나리오 정보 가져오기
        scenario_list = ScenarioManager.get_scenario_list()
        scenario_desc = scenario_list.get(scenario_type, "Unknown scenario")
        
        # 위협 미사일 생성
        threats = self.get_threat_missiles(scenario_type)
        num_threats = len(threats)
        
        return {
            "name": f"Korean_Defense_Scenario_{scenario_type}",
            "description": f"{scenario_desc} - 10 assets, 10 batteries (5 LSAM + 5 MSAM), {num_threats} missiles",
            "scenario_type": scenario_type,
            "assets": self.get_defense_assets(),
            "batteries": self.get_battery_deployment(),
            "threats": threats,
            "engagement_matrix": self.get_engagement_matrix(),
            "total_variables_estimate": self.num_assets * num_threats * self.num_batteries * 2,
            "total_constraints_estimate": self.num_assets * num_threats * 5
        }

# 기본 MIP 설정 인스턴스 생성 (현실적 규모)
mip_config = MIPConfig()

if __name__ == "__main__":
    print("=== MIP Configuration Test (Realistic Scale) ===")
    config = MIPConfig()
    
    print(f"Solver: {config.solver_config.solver_name}")
    print(f"Time limit: {config.solver_config.time_limit_sec}s")
    print(f"Scale: {config.num_assets} assets, {config.num_batteries} batteries, {config.num_threats} threats")
    print(f"Weapon types: {config.weapon_types}")
    
    # 현실적 시나리오 테스트
    scenario = config.create_realistic_scenario()
    print(f"\n=== Realistic Scenario: {scenario['name']} ===")
    print(f"Description: {scenario['description']}")
    print(f"Estimated variables: {scenario['total_variables_estimate']}")
    print(f"Estimated constraints: {scenario['total_constraints_estimate']}")
    
    # 자산 정보
    assets = config.get_defense_assets()
    print(f"\nDefense Assets ({len(assets)}):") 
    for asset in assets:
        print(f"  {asset['id']}: {asset['name']} (Priority {asset['priority']}, Value: {asset['value']})")
    
    # 포대 정보
    batteries = config.get_battery_deployment()
    print(f"\nBattery Deployment ({len(batteries)}):")
    for battery in batteries:
        print(f"  {battery['id']}: {battery['name']} ({battery['system_type']}) - Range: {battery['coverage_radius_km']}km")
    
    # 위협 정보
    threats = config.get_threat_missiles()
    print(f"\nThreat Missiles ({len(threats)}):")
    for threat in threats[:5]:  # 처음 5개만 출력
        print(f"  {threat['id']}: {threat['name']} -> {threat['target_asset_id']} (T+{threat['launch_time']}s)")
    print(f"  ... and {len(threats)-5} more threats")
    
    # 교전 가능성 통계
    engagement_matrix = config.get_engagement_matrix()
    total_engagements = sum(engagement_matrix.values())
    total_possible = len(engagement_matrix)
    print(f"\nEngagement Capability: {total_engagements}/{total_possible} ({100*total_engagements/total_possible:.1f}%) battery-threat pairs can engage")
    
    # 시스템 스펙 샘플
    lsam_specs = config.get_interceptor_specs("LSAM")
    msam_specs = config.get_interceptor_specs("MSAM")
    print(f"\nLSAM Range: {lsam_specs['ballistic_missile_specs']['engagement_range_km']['min']}-{lsam_specs['ballistic_missile_specs']['engagement_range_km']['max']}km")
    print(f"MSAM Range: {msam_specs['ballistic_missile_specs']['engagement_range_km']['min']}-{msam_specs['ballistic_missile_specs']['engagement_range_km']['max']}km")
    for asset in mip_config.get_defense_assets()[:5]:  # Show first 5 assets
        print(f"{asset['id']}: {asset['name']} - Weight: {asset['weighted_value']}")
    
    print("\n=== Launch Bases List ===")
    for base_name, base_info in mip_config.get_launch_bases().items():
        print(f"{base_name}: {base_info['coords']} (Weight: {base_info['weight']})")


# ============================================================================
# 최적화 사전 계산 캐시 클래스들
# ============================================================================

class EnhancedEngagementMatrix:
    """교전 가능성 및 관련 파라미터 사전 계산 (최적화 #1)"""
    
    def __init__(self):
        self.feasible: Dict[Tuple[str, str], bool] = {}
        self.distances: Dict[Tuple[str, str], float] = {}
        self.base_probabilities: Dict[Tuple[str, str], float] = {}
        self.computed_threats: Set[str] = set()  # 계산된 위협 추적
        
    def precompute_all(self, batteries: List[Dict], threats: List[Dict], assets: List[Dict]):
        """
        모든 (battery, threat) 조합의 파라미터를 미리 계산
        
        Args:
            batteries: 포대 리스트
            threats: 위협 리스트 (initial_threats_config)
            assets: 자산 리스트
        """
        print("=" * 60)
        print("사전 계산 시작: Engagement Matrix")
        print("=" * 60)
        
        total_combinations = len(batteries) * len(threats)
        feasible_count = 0
        
        for battery in batteries:
            bat_pos = np.array(battery['position'][:2])  # x, y만 사용
            
            # 스펙 추출
            if 'specs' in battery and battery['specs']:
                specs = battery['specs']
                if battery['system_type'] == 'LSAM':
                    spec_key = 'ballistic_missile_specs'
                else:
                    spec_key = 'ballistic_missile_specs'
                
                if spec_key in specs:
                    range_info = specs[spec_key]['engagement_range_km']
                    min_range = range_info.get('min', 0)
                    max_range = range_info['max']
                    # 단발 요격 확률 사용 (새 키 이름 지원)
                    intercept_prob = specs[spec_key].get('intercept_probability_single', 
                                                          specs[spec_key].get('intercept_probability', 0.85))
                    
                    altitude_info = specs[spec_key]['engagement_altitude_km']
                    min_alt = altitude_info.get('min', 0)
                    max_alt = altitude_info['max']
                else:
                    # Fallback
                    min_range = 0
                    max_range = 150 if battery['system_type'] == 'LSAM' else 80
                    intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                    min_alt = 0
                    max_alt = 100
            else:
                # Fallback
                min_range = 0
                max_range = 150 if battery['system_type'] == 'LSAM' else 80
                intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                min_alt = 0
                max_alt = 100
            
            for threat in threats:
                threat_id = threat['id']
                key = (battery['id'], threat_id)
                
                # 1. Distance 계산 (궤적 기반 - 발사 위치와 목표 위치 고려)
                threat_launch_pos = np.array(threat['launch_position'][:2])
                dist_from_launch = np.linalg.norm(bat_pos - threat_launch_pos)
                self.distances[key] = dist_from_launch  # 참고용
                
                # 2. Feasibility 판정: 잠재적 교전 가능 여부
                # 위협이 배터리 사거리 내로 진입할 가능성이 있는지 판단
                
                # 고도 체크 (critical_altitude 사용 - 실제 교전 고도)
                phase_events = threat.get('phase_events', {})
                critical_alt = phase_events.get('critical_altitude_km')
                if critical_alt is None:
                    # fallback: max_altitude의 70%
                    threat_max_alt = threat.get('specs', {}).get('max_altitude_km', 50.0)
                    critical_alt = threat_max_alt * 0.7
                altitude_ok = (min_alt <= critical_alt <= max_alt)
                
                # 거리 체크: 궤적 기반 (발사→목표 경로가 배터리 사거리를 통과하는지)
                threat_target_pos = threat.get('target_position')
                if threat_target_pos is not None:
                    threat_target_pos = np.array(threat_target_pos[:2])
                    dist_to_target = np.linalg.norm(bat_pos - threat_target_pos)
                    # 발사 위치 또는 목표 위치 중 하나라도 사거리 내면 교전 가능
                    min_dist = min(dist_from_launch, dist_to_target)
                    potential_range = max_range * 2.0
                    in_potential_range = (min_dist <= potential_range)
                else:
                    # target_position이 없으면 발사 위치만 사용 (fallback)
                    potential_range = max_range * 2.0
                    in_potential_range = (dist_from_launch <= potential_range)
                
                self.feasible[key] = in_potential_range and altitude_ok
                
                # 3. Base intercept probability
                if self.feasible[key]:
                    self.base_probabilities[key] = intercept_prob
                    feasible_count += 1
                else:
                    self.base_probabilities[key] = 0.0
                
                # 계산된 위협 추적
                self.computed_threats.add(threat_id)
        
        print(f"[OK] 총 조합: {total_combinations}")
        print(f"[OK] 교전 가능: {feasible_count} ({feasible_count/total_combinations*100:.1f}%)")
        print(f"[OK] 교전 불가: {total_combinations - feasible_count}")
        
        # DEBUG: SCUD_B (T11-T20)에 대한 MSAM 교전 가능성 확인
        scud_msam_count = 0
        for battery in batteries:
            if battery['system_type'] == 'MSAM':
                for threat in threats:
                    if threat['id'] in ['T11', 'T12', 'T13']:
                        key = (battery['id'], threat['id'])
                        if self.feasible.get(key, False):
                            scud_msam_count += 1
                            print(f"[DEBUG precompute] {battery['id']} CAN engage {threat['id']}")
                        else:
                            print(f"[DEBUG precompute] {battery['id']} CANNOT engage {threat['id']}")
        
        print("=" * 60)
    
    def is_feasible(self, battery_id: str, threat_id: str, threat_current_position: tuple = None, 
                    battery_position: tuple = None, battery_specs: dict = None) -> bool:
        """
        교전 가능 여부 (정적 precompute + 실시간 거리 체크)
        
        Args:
            battery_id: 배터리 ID
            threat_id: 위협 ID
            threat_current_position: 위협의 현재 위치 (x, y) - 실시간 체크용
            battery_position: 배터리 위치 (x, y) - 실시간 체크용
            battery_specs: 배터리 스펙 - 실시간 체크용
        
        Returns:
            교전 가능 여부
        """
        # 1단계: 정적 precompute 결과 확인
        static_feasible = self.feasible.get((battery_id, threat_id), False)
        
        # 2단계: 실시간 거리 체크 (미사일이 비행 중 사거리 내로 진입했는지 확인)
        if not static_feasible and threat_current_position and battery_position and battery_specs:
            # 현재 거리 계산
            bat_pos = np.array(battery_position[:2])
            threat_pos = np.array(threat_current_position[:2])
            current_distance = np.linalg.norm(bat_pos - threat_pos)
            
            # 배터리 사거리 확인
            spec_key = 'ballistic_missile_specs'
            if spec_key in battery_specs:
                range_info = battery_specs[spec_key]['engagement_range_km']
                max_range = range_info['max']
                
                # 현재 거리가 사거리 내면 교전 가능
                if current_distance <= max_range:
                    return True
        
        return static_feasible
    
    def get_distance(self, battery_id: str, threat_id: str) -> float:
        """거리 (O(1) lookup)"""
        return self.distances.get((battery_id, threat_id), float('inf'))
    
    def get_base_pk(self, battery_id: str, threat_id: str) -> float:
        """기본 요격 확률 (O(1) lookup)"""
        return self.base_probabilities.get((battery_id, threat_id), 0.0)
    
    def add_new_threats(self, batteries: List[Dict], new_threats: List[Dict]) -> int:
        """
        새로운 위협에 대해서만 증분 계산
        
        Args:
            batteries: 포대 리스트
            new_threats: 새로 발견된 위협 리스트
        
        Returns:
            계산된 위협 수
        """
        computed_count = 0
        
        for threat in new_threats:
            threat_id = threat['id']
            
            # 이미 계산된 위협은 스킵
            if threat_id in self.computed_threats:
                continue
            
            # 모든 배터리에 대해 계산
            for battery in batteries:
                bat_pos = np.array(battery['position'][:2])
                
                # 스펙 추출
                if 'specs' in battery and battery['specs']:
                    specs = battery['specs']
                    spec_key = 'ballistic_missile_specs'
                    
                    if spec_key in specs:
                        range_info = specs[spec_key]['engagement_range_km']
                        min_range = range_info.get('min', 0)
                        max_range = range_info['max']
                        intercept_prob = specs[spec_key]['intercept_probability']
                        
                        altitude_info = specs[spec_key]['engagement_altitude_km']
                        min_alt = altitude_info.get('min', 0)
                        max_alt = altitude_info['max']
                    else:
                        min_range = 0
                        max_range = 150 if battery['system_type'] == 'LSAM' else 80
                        intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                        min_alt = 0
                        max_alt = 100
                else:
                    min_range = 0
                    max_range = 150 if battery['system_type'] == 'LSAM' else 80
                    intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                    min_alt = 0
                    max_alt = 100
                
                key = (battery['id'], threat_id)
                
                # Distance 계산 (발사 위치 기준 - 참고용)
                threat_launch_pos = np.array(threat['launch_position'][:2])
                dist_2d = np.linalg.norm(bat_pos - threat_launch_pos)
                self.distances[key] = dist_2d
                
                # Feasibility 판정: 잠재적 교전 가능 여부 (궤적 기반)
                # 위협이 배터리 사거리 내로 진입할 가능성이 있는지 판단
                # 발사 위치가 사거리 밖이어도, 목표로 날아가면서 사거리 안으로 들어올 수 있음
                
                # 고도 체크 (critical_altitude 사용 - 실제 교전 고도)
                phase_events = threat.get('phase_events', {})
                critical_alt = phase_events.get('critical_altitude_km')
                if critical_alt is None:
                    # fallback: max_altitude의 70%
                    threat_max_alt = threat.get('specs', {}).get('max_altitude_km', 50.0)
                    critical_alt = threat_max_alt * 0.7
                
                # DEBUG: SCUD_B 교전 가능성 확인
                if threat_id in ['T11', 'T12'] and battery['system_type'] == 'MSAM':
                    print(f"[DEBUG add_new_threats] {battery['id']} vs {threat_id}: "
                          f"critical_alt={critical_alt}km, range=[{min_alt}-{max_alt}km], "
                          f"phase_events={phase_events}")
                
                altitude_ok = (min_alt <= critical_alt <= max_alt)
                
                # 거리 체크: 발사 위치가 최대 사거리의 2배 이내면 잠재적 교전 가능
                # (위협이 날아가면서 배터리에 가까워질 수 있음)
                potential_range = max_range * 2.0  # 잠재적 교전 범위 확대
                in_potential_range = (dist_2d <= potential_range)
                
                self.feasible[key] = in_potential_range and altitude_ok
                
                # Base intercept probability
                if self.feasible[key]:
                    self.base_probabilities[key] = intercept_prob
                else:
                    self.base_probabilities[key] = 0.0
            
            self.computed_threats.add(threat_id)
            computed_count += 1
        
        return computed_count

    def update_moving_threats(self, batteries: List[Dict], active_missiles: Dict) -> int:
        """
        이동 중인 위협의 현재 위치 기반으로 교전 매트릭스 동적 업데이트.

        기존 정적 precompute는 발사 위치 기반이었으나, 이 메서드는
        비행 중인 미사일의 현재 위치를 반영하여 feasibility/distance/Pk를 갱신함.

        Args:
            batteries: 포대 리스트
            active_missiles: 활성 미사일 딕셔너리 {missile_id: missile_dict}
                             각 missile_dict는 'position', 'active', 'flight_progress' 키 포함

        Returns:
            업데이트된 (battery, threat) 조합 수
        """
        updated_count = 0

        for missile_id, missile in active_missiles.items():
            if not missile.get('active', False):
                continue

            threat_id = missile.get('id', missile_id)
            current_pos = missile.get('position')
            if current_pos is None:
                continue

            threat_pos_2d = np.array(current_pos[:2])
            # 비행 진행률 기반 현재 고도 추정 (탄도 궤적)
            flight_progress = missile.get('flight_progress', 0.0)
            current_altitude_km = 10000.0 * (1.0 - flight_progress) / 1000.0  # m → km
            # 간단한 탄도 고도 모델: 정점 근처에서 높고 시작/끝에서 낮음
            if flight_progress <= 0.5:
                current_altitude_km = missile.get('specs', {}).get('max_altitude_km', 50.0) * (flight_progress / 0.5)
            else:
                current_altitude_km = missile.get('specs', {}).get('max_altitude_km', 50.0) * ((1.0 - flight_progress) / 0.5)

            for battery in batteries:
                bat_pos = np.array(battery['position'][:2])
                key = (battery['id'], threat_id)

                # 현재 거리 계산
                current_distance = float(np.linalg.norm(bat_pos - threat_pos_2d))

                # 스펙 추출
                if 'specs' in battery and battery['specs']:
                    specs = battery['specs']
                    spec_key = 'ballistic_missile_specs'
                    if spec_key in specs:
                        range_info = specs[spec_key]['engagement_range_km']
                        max_range = range_info['max']
                        intercept_prob = specs[spec_key].get('intercept_probability_single',
                                                              specs[spec_key].get('intercept_probability', 0.85))
                        altitude_info = specs[spec_key]['engagement_altitude_km']
                        min_alt = altitude_info.get('min', 0)
                        max_alt = altitude_info['max']
                    else:
                        max_range = 150 if battery['system_type'] == 'LSAM' else 80
                        intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                        min_alt = 0
                        max_alt = 100
                else:
                    max_range = 150 if battery['system_type'] == 'LSAM' else 80
                    intercept_prob = 0.85 if battery['system_type'] == 'LSAM' else 0.78
                    min_alt = 0
                    max_alt = 100

                # 현재 위치 기반 feasibility 재평가
                in_range = (current_distance <= max_range)
                altitude_ok = (min_alt <= current_altitude_km <= max_alt)

                old_feasible = self.feasible.get(key, False)
                new_feasible = in_range and altitude_ok

                # 정적 feasibility가 True였으면 유지 (궤적 기반 판정 존중)
                # 추가로 현재 위치 기반으로 새로 feasible해진 경우도 반영
                if new_feasible and not old_feasible:
                    self.feasible[key] = True
                    self.base_probabilities[key] = intercept_prob

                # 거리 업데이트 (현재 위치 기반으로 항상 갱신)
                if self.feasible.get(key, False):
                    self.distances[key] = current_distance
                    updated_count += 1

        return updated_count


class KFactorCache:
    """K-factor 사전 계산 캐시 + 경량 실시간 계산 (최적화 #3)"""
    
    def __init__(self, k_min: float = 0.6, k_max: float = 1.0):
        self.k_min = k_min
        self.k_max = k_max
        self.k_table: Dict[Tuple[str, str], float] = {}
        
        # 🆕 LUT (Lookup Table) - 1000단계, 8KB 메모리
        # 거리 비율 → K값 매핑 (사전 계산)
        self.LUT_SIZE = 1000
        self.k_lut = np.linspace(k_min, k_max, self.LUT_SIZE + 1)
        
        # 시스템 사거리 캐시 (실시간 계산용)
        self.system_ranges: Dict[str, float] = {}
    
    def precompute(self, threats: List, systems: List, engagement_matrix: EnhancedEngagementMatrix):
        """
        모든 (threat, system) 조합의 k-factor 계산
        
        Args:
            threats: Threat 객체 리스트
            systems: InterceptorSystem 객체 리스트
            engagement_matrix: 교전 가능성 매트릭스
        """
        print("사전 계산 시작: K-Factor (LUT 기반)")
        
        # 시스템 사거리 캐시 (실시간 계산용)
        for system in systems:
            self.system_ranges[system.id] = system.engagement_range
        
        for threat in threats:
            for system in systems:
                key = (threat.id, system.id)
                
                # Feasible한 경우만 계산
                if not engagement_matrix.is_feasible(system.id, threat.id):
                    self.k_table[key] = self.k_min
                    continue
                
                # K-factor 계산
                k_value = self._calculate_k_factor(threat, system, engagement_matrix)
                self.k_table[key] = k_value
        
        print(f"[OK] K-factor 계산 완료: {len(self.k_table)} 조합 (LUT: {self.LUT_SIZE+1} 단계)")
    
    def get_k(self, threat_id: str, system_id: str) -> float:
        """K-factor 조회 (캐시에서, O(1))"""
        return self.k_table.get((threat_id, system_id), self.k_min)
    
    def get_k_realtime(self, threat_pos: tuple, system_id: str) -> float:
        """
        실시간 K값 계산 (LUT 기반, 초경량)
        
        Args:
            threat_pos: 위협 현재 위치 (x, y)
            system_id: 시스템 ID
        
        Returns:
            K값 (0.6 ~ 1.0)
        
        성능: 거리 계산 + LUT 인덱싱만 (나눗셈/곱셈 없음)
        """
        # 시스템 사거리 조회 (O(1))
        max_range = self.system_ranges.get(system_id)
        if max_range is None or max_range <= 0:
            return self.k_min
        
        # 거리 계산은 이미 threat['current_position']에서 수행됨
        # 여기서는 거리만 받아서 LUT 조회
        # (실제로는 optimizer에서 거리를 전달받음)
        return self.k_min  # Placeholder - optimizer에서 직접 호출
    
    def get_k_from_distance(self, distance: float, max_range: float) -> float:
        """
        거리 기반 K값 계산 (LUT 사용, O(1))

        Args:
            distance: 위협-시스템 거리 (km)
            max_range: 시스템 최대 사거리 (km)

        Returns:
            K값 (0.6 ~ 1.0)

        성능: 나눗셈 1회 + 배열 인덱싱 (곱셈 없음)
        """
        if distance <= 0 or max_range <= 0:
            return self.k_min

        # 거리 비율 계산 (나눗셈 1회)
        ratio = 1.0 - (distance / max_range)

        # 범위 체크
        if ratio <= 0:
            return self.k_min
        elif ratio >= 1:
            return self.k_max

        # LUT 인덱싱 (O(1), 초고속)
        idx = int(ratio * self.LUT_SIZE)
        return self.k_lut[idx]

    # ===== B-1: Time-Dependent K-Factor (시간 종속 교전 품질 계수) =====
    # 학술적 기여: 대부분 DWTA 문헌은 정적 k 사용.
    # 위협의 비행 단계(boost/midcourse/terminal)에 따라 k가 변하는 모델은 새로운 기여.

    @staticmethod
    def _get_flight_phase(time_elapsed: float, total_flight_time: float):
        """
        위협의 비행 단계 판별

        탄도 미사일 비행 단계:
        - Boost phase:     0% ~ 15% of flight time (발사 직후, 가속 중)
        - Midcourse phase: 15% ~ 75% of flight time (관성 비행, 최적 교전 구간)
        - Terminal phase:  75% ~ 100% of flight time (최종 돌입, 교전 매우 어려움)

        Returns:
            (phase_name, phase_progress) - 단계명, 해당 단계 내 진행률 [0, 1]
        """
        if total_flight_time <= 0:
            return 'midcourse', 0.5

        progress = min(1.0, max(0.0, time_elapsed / total_flight_time))

        if progress < 0.15:
            # Boost phase: 0~15%
            phase_progress = progress / 0.15
            return 'boost', phase_progress
        elif progress < 0.75:
            # Midcourse phase: 15~75%
            phase_progress = (progress - 0.15) / 0.60
            return 'midcourse', phase_progress
        else:
            # Terminal phase: 75~100%
            phase_progress = (progress - 0.75) / 0.25
            return 'terminal', phase_progress

    def get_k_time_dependent(self, distance: float, max_range: float,
                              time_elapsed: float, total_flight_time: float) -> float:
        """
        시간 종속 K-factor: k(t) = k_geometric × k_temporal(phase, t)

        기존 거리 기반 k에 비행 단계별 시간 가중치를 곱함.
        - Boost:     k_temporal ∈ [0.70, 0.85] (가속 중, 교전 어려움)
        - Midcourse: k_temporal ∈ [0.90, 1.00] (최적 교전 구간)
        - Terminal:  k_temporal ∈ [0.50, 0.75] (급감, 교전 매우 어려움)

        학술적 의의: 정적 k 대비 현실적 교전 품질 모델링.
        Terminal phase에서 k 급감 → 조기 교전 유도 효과.

        Args:
            distance: 위협-시스템 거리 (km)
            max_range: 시스템 최대 사거리 (km)
            time_elapsed: 위협 비행 경과 시간 (초)
            total_flight_time: 위협 총 비행 시간 (초)

        Returns:
            Time-dependent K값 (k_min ~ k_max)
        """
        # 1) 거리 기반 k (기존 LUT)
        k_geometric = self.get_k_from_distance(distance, max_range)

        # 2) 비행 단계 판별
        phase, phase_progress = self._get_flight_phase(time_elapsed, total_flight_time)

        # 3) 단계별 시간 가중치 k_temporal
        if phase == 'boost':
            # Boost: 초기 가속 → 교전 어려움, 단계 후반으로 갈수록 개선
            k_temporal = 0.70 + 0.15 * phase_progress
        elif phase == 'midcourse':
            # Midcourse: 관성 비행 → 최적 교전 구간
            # 중반부가 가장 좋고, 초반/후반은 약간 감소
            midpoint_bonus = 1.0 - 0.5 * (2.0 * phase_progress - 1.0) ** 2
            k_temporal = 0.90 + 0.10 * midpoint_bonus
        else:  # terminal
            # Terminal: 급감 — 교전 시간 부족, 위협 기동 증가
            k_temporal = 0.75 - 0.25 * phase_progress  # 0.75 → 0.50

        # 4) 종합: k = k_geometric × k_temporal, 범위 제한
        k_combined = k_geometric * k_temporal
        return float(np.clip(k_combined, self.k_min, self.k_max))
    
    def update_from_engagement_matrix(self, engagement_matrix: 'EnhancedEngagementMatrix',
                                      active_threat_ids: set) -> int:
        """
        동적 업데이트된 교전 매트릭스의 거리 정보로 k-factor 캐시 갱신.

        update_moving_threats() 이후 호출하여, 변경된 거리를 반영한 k-factor 재계산.

        Args:
            engagement_matrix: 동적 업데이트된 교전 매트릭스
            active_threat_ids: 활성 위협 ID 집합

        Returns:
            업데이트된 k-factor 수
        """
        updated = 0
        for (threat_id, system_id), old_k in list(self.k_table.items()):
            if threat_id not in active_threat_ids:
                continue

            bat_key = (system_id, threat_id)
            if not engagement_matrix.feasible.get(bat_key, False):
                continue

            current_distance = engagement_matrix.distances.get(bat_key, float('inf'))
            max_range = self.system_ranges.get(system_id)
            if max_range is None or max_range <= 0:
                continue

            new_k = self.get_k_from_distance(current_distance, max_range)
            if abs(new_k - old_k) > 0.01:  # 1% 이상 변화 시만 업데이트
                self.k_table[(threat_id, system_id)] = new_k
                updated += 1

        return updated

    def get_k_value(self, threat_id: str, system_id: str) -> float:
        """Warmstart용 K값 조회 (별칭)"""
        return self.get_k(threat_id, system_id)

    def _calculate_k_factor(self, threat, system, engagement_matrix) -> float:
        """
        K-factor 계산 로직 (4가지 요소 종합)
        
        k_ij(t) = k_base(t) × distance_correction(t)
        where:
          k_base(t) = k_min + (k_max - k_min) × (t_remaining / t_window)
          distance_correction(t) = 1 - 0.4 × (d_ij(t) / R_j)
        """
        # 1. 기본 정보 추출
        distance = engagement_matrix.get_distance(system.id, threat.id)
        max_range = system.engagement_range
        current_time = getattr(threat, 'current_time', 0.0)
        
        # 2. 시간적 요소 (Temporal Factor)
        temporal_factor = self._calculate_temporal_factor(threat, current_time)
        
        # 3. 기하학적 요소 (Geometric Factor) - 거리 보정
        geometric_factor = self._calculate_geometric_factor(distance, max_range)
        
        # 4. 운동학적 요소 (Kinematic Factor)
        kinematic_factor = self._calculate_kinematic_factor(threat)
        
        # 5. 환경적 요소 (Environmental Factor)
        environmental_factor = self._calculate_environmental_factor(threat)
        
        # 6. 종합 K-factor 계산 (가중 기하 평균)
        weights = {'temporal': 0.3, 'geometric': 0.25, 'kinematic': 0.25, 'environmental': 0.2}
        total_weight = sum(weights.values())
        
        k_combined = (
            (temporal_factor ** weights['temporal']) *
            (geometric_factor ** weights['geometric']) *
            (kinematic_factor ** weights['kinematic']) *
            (environmental_factor ** weights['environmental'])
        ) ** (1.0 / total_weight)
        
        return np.clip(k_combined, self.k_min, self.k_max)
    
    def _calculate_temporal_factor(self, threat, current_time: float) -> float:
        """시간적 요소: 교전 윈도우 품질"""
        # 교전 윈도우 정보
        launch_time = getattr(threat, 'launch_time', 0.0)
        impact_time = getattr(threat, 'estimated_impact_time', launch_time + 300.0)
        
        # 교전 윈도우 시작/종료 시간 (시스템별로 다를 수 있음)
        window_start = launch_time + 50.0  # 예: 발사 후 50초부터 교전 가능
        window_end = impact_time - 30.0    # 예: 충격 30초 전까지 교전 가능
        window_duration = window_end - window_start
        
        if window_duration <= 0:
            return self.k_min
        
        # 현재 시점에서의 남은 시간
        if current_time < window_start:
            t_remaining = window_end - window_start  # 최대 시간
        elif current_time > window_end:
            return self.k_min  # 교전 윈도 외
        else:
            t_remaining = window_end - current_time
        
        # 시간 품질 계수
        time_ratio = t_remaining / window_duration
        k_temporal = self.k_min + (self.k_max - self.k_min) * max(0, time_ratio)
        
        return k_temporal
    
    def _calculate_geometric_factor(self, distance: float, max_range: float) -> float:
        """기하학적 요소: 거리 보정 계수"""
        if distance <= 0 or max_range <= 0:
            return self.k_min
        
        # 거리 보정: k_distance = 1 - 0.4 × (d / R)
        distance_ratio = distance / max_range
        k_distance = 1.0 - 0.4 * distance_ratio
        
        # 범위 제한 및 정규화
        k_distance = max(0.6, k_distance)  # 최소 0.6
        
        # k_min~k_max 범위로 매핑
        k_geometric = self.k_min + (self.k_max - self.k_min) * (k_distance - 0.6) / 0.4
        
        return np.clip(k_geometric, self.k_min, self.k_max)
    
    def _calculate_kinematic_factor(self, threat) -> float:
        """운동학적 요소: 고도와 속도에 따른 요격 난이도"""
        # 기본값 설정
        altitude = getattr(threat, 'altitude', 30.0)  # km
        speed = getattr(threat, 'speed', 2.0)         # km/s
        
        # 고도 효과 (중간 고도가 최적)
        optimal_altitude = 30.0  # km
        altitude_deviation = abs(altitude - optimal_altitude) / optimal_altitude
        altitude_factor = 1.0 - 0.2 * min(1.0, altitude_deviation)
        
        # 속도 효과 (너무 빠르면 어려움)
        optimal_speed = 2.0  # km/s
        if speed <= optimal_speed:
            speed_factor = 1.0
        else:
            speed_ratio = speed / optimal_speed
            speed_factor = 1.0 - 0.2 * min(1.0, speed_ratio - 1.0)
        
        k_kinematic = self.k_min + (self.k_max - self.k_min) * altitude_factor * speed_factor
        
        return np.clip(k_kinematic, self.k_min, self.k_max)
    
    def _calculate_environmental_factor(self, threat) -> float:
        """환경적 요소: 대기 밀도 등"""
        altitude = getattr(threat, 'altitude', 30.0)  # km
        
        # 대기 밀도 효과 (고도가 높을수록 밀도 감소)
        air_density_sea_level = 1.225  # kg/m³
        atmospheric_density = air_density_sea_level * np.exp(-altitude / 8.5)
        density_ratio = atmospheric_density / air_density_sea_level
        
        # 대기 밀도가 높을수록 요격체 성능 향상
        k_environmental = self.k_min + (self.k_max - self.k_min) * (0.9 + 0.1 * density_ratio)
        
        return np.clip(k_environmental, self.k_min, self.k_max)


class McCormickCoefficients:
    """McCormick Relaxation 계수 사전 계산 (최적화 #3)"""
    
    def __init__(self, k_min: float = 0.6, k_max: float = 1.0, missiles_per_engagement: int = 2):
        self.k_min = k_min
        self.k_max = k_max
        self.missiles_per_engagement = missiles_per_engagement
        self.coeffs: Dict[Tuple[str, str], Dict] = {}
    
    def precompute(self, threats: List, systems: List, k_cache: KFactorCache):
        """
        모든 조합의 McCormick linearization 계수 계산
        
        Args:
            threats: Threat 리스트
            systems: InterceptorSystem 리스트
            k_cache: K-factor 캐시
        """
        print("사전 계산 시작: McCormick Coefficients")
        
        for threat in threats:
            for system in systems:
                key = (threat.id, system.id)
                
                # 단발 요격 확률
                P_single = system.intercept_probability
                # 2발 살보 요격 확률
                P_total = 1.0 - (1.0 - P_single) ** self.missiles_per_engagement
                
                k = k_cache.get_k(threat.id, system.id)
                
                # ln(1 - P) 계산 (한 번만)
                if P_total >= 1.0:
                    log_term = -1e10
                elif P_total <= 0.0:
                    log_term = 0.0
                else:
                    log_term = np.log(1.0 - P_total)
                
                # McCormick envelope 계수들
                self.coeffs[key] = {
                    'P_single': P_single,
                    'P_total': P_total,
                    'log_1_minus_P': log_term,
                    'k_value': k,
                    'k_lower': self.k_min,
                    'k_upper': self.k_max,
                    'kP_min': self.k_min * P_total,
                    'kP_max': self.k_max * P_total,
                }
        
        print(f"[OK] McCormick 계수 계산 완료: {len(self.coeffs)} 조합")
    
    def get_coeffs(self, threat_id: str, system_id: str) -> Optional[Dict]:
        """계수 조회 (O(1) lookup)"""
        return self.coeffs.get((threat_id, system_id), None)


class StateFilter:
    """Invalid state 필터링 (최적화 #2)"""
    
    @staticmethod
    def get_valid_states_for_threat(
        threat_id: str, 
        systems: List, 
        engagement_matrix: EnhancedEngagementMatrix,
        max_combination_size: int = 3
    ) -> List[Set[str]]:
        """
        특정 위협에 대해 유효한 state 조합만 생성
        
        Args:
            threat_id: 위협 ID
            systems: InterceptorSystem 리스트
            engagement_matrix: 교전 가능성 매트릭스
            max_combination_size: 최대 조합 크기
            
        Returns:
            유효한 state 리스트
        """
        # 1. Feasible systems 필터링
        feasible_systems = [
            s for s in systems 
            if engagement_matrix.is_feasible(s.id, threat_id)
        ]
        
        if not feasible_systems:
            return [set()]  # Empty state만
        
        valid_states = [set()]  # Empty state
        
        # 2. 조합 생성 (크기 제한)
        actual_max_size = min(max_combination_size, len(feasible_systems))
        
        for size in range(1, actual_max_size + 1):
            for combination in itertools.combinations(feasible_systems, size):
                state = set([s.id for s in combination])
                valid_states.append(state)
        
        return valid_states


class BinaryTreeMcCormickCache:
    """
    🆕 Binary Tree McCormick 계수 캐시 (선택적 최적화)
    
    자산별 생존 확률 곱셈에 사용되는 McCormick 계수를 사전 계산
    실제로는 변수가 동적으로 생성되므로 제한적 효과
    """
    
    def __init__(self):
        self.tree_depth_cache = {}  # {n_vars: depth}
        self.mccormick_count_cache = {}  # {n_vars: count}
    
    def get_tree_depth(self, n_variables: int) -> int:
        """Binary Tree 깊이 계산 (캐싱)"""
        if n_variables in self.tree_depth_cache:
            return self.tree_depth_cache[n_variables]
        
        import math
        depth = math.ceil(math.log2(n_variables)) if n_variables > 0 else 0
        self.tree_depth_cache[n_variables] = depth
        return depth
    
    def get_mccormick_count(self, n_variables: int) -> int:
        """필요한 McCormick 적용 횟수 계산 (캐싱)"""
        if n_variables in self.mccormick_count_cache:
            return self.mccormick_count_cache[n_variables]
        
        # n개 변수 → n-1회 McCormick (Binary Tree)
        count = max(0, n_variables - 1)
        self.mccormick_count_cache[n_variables] = count
        return count
    
    def estimate_constraints(self, n_variables: int) -> int:
        """예상 제약 개수 계산"""
        # 각 McCormick당 4개 제약
        return self.get_mccormick_count(n_variables) * 4


class FeasibilityCache:
    """
    비트마스크 기반 교전 가능성 캐시

    각 포대(battery)마다 uint64 비트마스크로 feasible한 위협을 관리.
    - O(1) set/clear/query
    - O(popcount) extraction
    - 증분 업데이트: 변경된 위협만 O(Δ·|J|)
    - 거리 캐시 내장: (battery_idx, threat_idx) → distance
    """

    def __init__(self, n_threats: int, n_batteries: int):
        self.n_threats = n_threats
        self.n_batteries = n_batteries
        self._n_words = (n_threats + 63) // 64
        # shape: (n_batteries, n_words), dtype=uint64
        self.masks = np.zeros((n_batteries, self._n_words), dtype=np.uint64)
        # 거리 캐시: (battery_idx, threat_idx) → float
        self.distances: Dict[Tuple[int, int], float] = {}
        # ID ↔ index 매핑
        self.threat_id_to_idx: Dict[str, int] = {}
        self.battery_id_to_idx: Dict[str, int] = {}
        self.idx_to_threat_id: Dict[int, str] = {}
        self.idx_to_battery_id: Dict[int, str] = {}
        # 레이어 정보: battery_idx → 'upper' or 'lower'
        self.battery_layer: Dict[int, str] = {}
        self._built = False

    def set_feasible(self, threat_idx: int, battery_idx: int):
        word = threat_idx // 64
        bit = threat_idx % 64
        self.masks[battery_idx, word] |= np.uint64(1 << bit)

    def clear_feasible(self, threat_idx: int, battery_idx: int):
        word = threat_idx // 64
        bit = threat_idx % 64
        self.masks[battery_idx, word] &= ~np.uint64(1 << bit)

    def is_feasible(self, threat_idx: int, battery_idx: int) -> bool:
        word = threat_idx // 64
        bit = threat_idx % 64
        return bool(self.masks[battery_idx, word] & np.uint64(1 << bit))

    def get_feasible_threats(self, battery_idx: int) -> List[int]:
        """battery_idx에 대해 feasible한 위협 인덱스 리스트 (bit extraction)"""
        result = []
        for word_idx in range(self._n_words):
            w = int(self.masks[battery_idx, word_idx])
            base = word_idx * 64
            while w:
                lsb = w & (-w)
                bit = lsb.bit_length() - 1
                result.append(base + bit)
                w ^= lsb
        return result

    def get_feasible_batteries(self, threat_idx: int) -> List[int]:
        """threat_idx에 대해 feasible한 포대 인덱스 리스트"""
        word = threat_idx // 64
        bit = threat_idx % 64
        mask = np.uint64(1 << bit)
        return [j for j in range(self.n_batteries) if self.masks[j, word] & mask]

    def get_active_pairs(self) -> List[Tuple[int, int]]:
        """모든 feasible (threat_idx, battery_idx) 쌍 반환"""
        return [
            (i, j)
            for j in range(self.n_batteries)
            for i in self.get_feasible_threats(j)
        ]

    def get_active_pairs_by_layer(self, layer: str) -> List[Tuple[str, str]]:
        """특정 레이어의 feasible (system_id, threat_id) 쌍 반환"""
        pairs = []
        for j in range(self.n_batteries):
            if self.battery_layer.get(j) != layer:
                continue
            sys_id = self.idx_to_battery_id[j]
            for i in self.get_feasible_threats(j):
                thr_id = self.idx_to_threat_id[i]
                pairs.append((sys_id, thr_id))
        return pairs

    def get_upper_systems_for_threat(self, threat_id: str) -> List[str]:
        """특정 threat에 대해 feasible한 상층 system ID 리스트"""
        thr_idx = self.threat_id_to_idx.get(threat_id)
        if thr_idx is None:
            return []
        return [
            self.idx_to_battery_id[j]
            for j in self.get_feasible_batteries(thr_idx)
            if self.battery_layer.get(j) == 'upper'
        ]

    def get_lower_systems_for_threat(self, threat_id: str) -> List[str]:
        """특정 threat에 대해 feasible한 하층 system ID 리스트"""
        thr_idx = self.threat_id_to_idx.get(threat_id)
        if thr_idx is None:
            return []
        return [
            self.idx_to_battery_id[j]
            for j in self.get_feasible_batteries(thr_idx)
            if self.battery_layer.get(j) == 'lower'
        ]

    def get_threats_for_system(self, system_id: str) -> List[str]:
        """특정 system에 대해 feasible한 threat ID 리스트"""
        bat_idx = self.battery_id_to_idx.get(system_id)
        if bat_idx is None:
            return []
        return [self.idx_to_threat_id[i] for i in self.get_feasible_threats(bat_idx)]

    def build(self, upper_systems, lower_systems, threats,
              engagement_matrix_cache=None, engagement_matrix_dict=None,
              battery_lookup=None):
        """
        전체 빌드: feasibility 검사 + 거리 캐싱을 1회 순회로 완료.
        SparseEngagementIndex.build()와 동일한 인터페이스.
        """
        # ID → index 매핑 구축
        all_systems = list(upper_systems) + list(lower_systems)
        self.threat_id_to_idx = {getattr(t, 'id', ''): i for i, t in enumerate(threats)}
        self.idx_to_threat_id = {i: tid for tid, i in self.threat_id_to_idx.items()}
        self.battery_id_to_idx = {getattr(s, 'id', ''): j for j, s in enumerate(all_systems)}
        self.idx_to_battery_id = {j: sid for sid, j in self.battery_id_to_idx.items()}

        # 레이어 정보 기록
        n_upper = len(list(upper_systems))
        for j in range(len(all_systems)):
            self.battery_layer[j] = 'upper' if j < n_upper else 'lower'

        # 크기 재조정 (위협/포대 수가 변경될 수 있음)
        self.n_threats = len(threats)
        self.n_batteries = len(all_systems)
        self._n_words = (self.n_threats + 63) // 64
        self.masks = np.zeros((self.n_batteries, self._n_words), dtype=np.uint64)
        self.distances = {}

        # 1회 순회: feasibility + 거리 캐싱
        for i, threat in enumerate(threats):
            threat_id = getattr(threat, 'id', '')
            threat_pos = getattr(threat, 'current_position', None)
            if threat_pos and len(threat_pos) >= 2:
                threat_pos_2d = np.array([threat_pos[0], threat_pos[1]])
            else:
                threat_pos_2d = None

            for j, system in enumerate(all_systems):
                system_id = getattr(system, 'id', '')

                # 거리 계산 + 캐싱
                if threat_pos_2d is not None:
                    sys_pos = getattr(system, 'position', None)
                    if sys_pos:
                        dist = float(np.linalg.norm(threat_pos_2d - np.array(sys_pos[:2])))
                        self.distances[(j, i)] = dist

                # feasibility 검사
                feasible = False
                if engagement_matrix_cache:
                    t_pos = (threat_pos[0], threat_pos[1]) if threat_pos and len(threat_pos) >= 2 else None
                    bat = battery_lookup.get(system_id) if battery_lookup else None
                    bat_pos = bat.get('position') if bat else None
                    bat_specs = bat.get('specs') if bat else None
                    feasible = engagement_matrix_cache.is_feasible(
                        system_id, threat_id,
                        threat_current_position=t_pos,
                        battery_position=bat_pos,
                        battery_specs=bat_specs
                    )
                elif engagement_matrix_dict:
                    feasible = engagement_matrix_dict.get((system_id, threat_id), False)

                if feasible:
                    self.set_feasible(i, j)

        self._built = True

    def update_incremental(self, changed_threat_indices: List[int],
                           all_systems, threats,
                           engagement_matrix_cache=None,
                           engagement_matrix_dict=None,
                           battery_lookup=None):
        """증분 업데이트: 변경된 위협만 O(Δ·|J|)"""
        for i in changed_threat_indices:
            threat = threats[i]
            threat_id = getattr(threat, 'id', '')
            threat_pos = getattr(threat, 'current_position', None)
            if threat_pos and len(threat_pos) >= 2:
                threat_pos_2d = np.array([threat_pos[0], threat_pos[1]])
            else:
                threat_pos_2d = None

            for j, system in enumerate(all_systems):
                system_id = getattr(system, 'id', '')

                if threat_pos_2d is not None:
                    sys_pos = getattr(system, 'position', None)
                    if sys_pos:
                        dist = float(np.linalg.norm(threat_pos_2d - np.array(sys_pos[:2])))
                        self.distances[(j, i)] = dist

                feasible = False
                if engagement_matrix_cache:
                    t_pos = (threat_pos[0], threat_pos[1]) if threat_pos and len(threat_pos) >= 2 else None
                    bat = battery_lookup.get(system_id) if battery_lookup else None
                    bat_pos = bat.get('position') if bat else None
                    bat_specs = bat.get('specs') if bat else None
                    feasible = engagement_matrix_cache.is_feasible(
                        system_id, threat_id,
                        threat_current_position=t_pos,
                        battery_position=bat_pos,
                        battery_specs=bat_specs
                    )
                elif engagement_matrix_dict:
                    feasible = engagement_matrix_dict.get((system_id, threat_id), False)

                if feasible:
                    self.set_feasible(i, j)
                else:
                    self.clear_feasible(i, j)

    @property
    def density(self) -> float:
        """feasible pair 비율 (ρ)"""
        if not self._built or self.n_threats == 0 or self.n_batteries == 0:
            return 0.0
        total = sum(len(self.get_feasible_threats(j)) for j in range(self.n_batteries))
        return total / (self.n_threats * self.n_batteries)

    # === SparseEngagementIndex 호환 속성 ===
    @property
    def upper_pairs(self) -> List[Tuple[str, str]]:
        return self.get_active_pairs_by_layer('upper')

    @property
    def lower_pairs(self) -> List[Tuple[str, str]]:
        return self.get_active_pairs_by_layer('lower')

    @property
    def all_pairs(self) -> List[Tuple[str, str]]:
        return self.upper_pairs + self.lower_pairs


class SparseEngagementIndex:
    """
    ③ CSR Sparse Index: feasible (system, threat) 쌍의 인덱스 구조

    모든 메서드에서 이중 루프 대신 사전 구축된 feasible pair 리스트를 순회하여
    모델 생성 시간을 단축하고, 이후 기법들의 기반 자료구조를 제공한다.
    """

    def __init__(self):
        self.upper_pairs: List[Tuple[str, str]] = []   # [(system_id, threat_id), ...]
        self.lower_pairs: List[Tuple[str, str]] = []
        self.all_pairs: List[Tuple[str, str]] = []
        self.threat_to_upper: Dict[str, List[str]] = {}  # threat_id -> [system_id, ...]
        self.threat_to_lower: Dict[str, List[str]] = {}
        self.system_to_threats: Dict[str, List[str]] = {}  # system_id -> [threat_id, ...]
        self._built = False

    def build(self, upper_systems, lower_systems, threats,
              engagement_matrix_cache=None, engagement_matrix_dict=None,
              battery_lookup=None):
        """
        engagement matrix에서 1회 순회로 feasible pair 인덱스를 구축한다.

        Args:
            upper_systems: 상층 시스템 리스트
            lower_systems: 하층 시스템 리스트
            threats: 위협 리스트
            engagement_matrix_cache: EnhancedEngagementMatrix 객체 (우선)
            engagement_matrix_dict: 기존 dict 형태 engagement matrix (fallback)
            battery_lookup: battery_id -> battery dict 매핑
        """
        self.upper_pairs = []
        self.lower_pairs = []
        self.threat_to_upper = {}
        self.threat_to_lower = {}
        self.system_to_threats = {}

        for threat in threats:
            threat_id = getattr(threat, 'id', '')
            self.threat_to_upper[threat_id] = []
            self.threat_to_lower[threat_id] = []

            # 상층 시스템 feasibility 검사
            for system in upper_systems:
                system_id = getattr(system, 'id', '')
                if self._check_feasible(system_id, threat_id, threat,
                                         engagement_matrix_cache,
                                         engagement_matrix_dict,
                                         battery_lookup):
                    self.upper_pairs.append((system_id, threat_id))
                    self.threat_to_upper[threat_id].append(system_id)
                    self.system_to_threats.setdefault(system_id, []).append(threat_id)

            # 하층 시스템 feasibility 검사
            for system in lower_systems:
                system_id = getattr(system, 'id', '')
                if self._check_feasible(system_id, threat_id, threat,
                                         engagement_matrix_cache,
                                         engagement_matrix_dict,
                                         battery_lookup):
                    self.lower_pairs.append((system_id, threat_id))
                    self.threat_to_lower[threat_id].append(system_id)
                    self.system_to_threats.setdefault(system_id, []).append(threat_id)

        self.all_pairs = self.upper_pairs + self.lower_pairs
        self._built = True

    def _check_feasible(self, system_id, threat_id, threat,
                         engagement_matrix_cache, engagement_matrix_dict,
                         battery_lookup):
        """feasibility 검사 (EnhancedEngagementMatrix 또는 dict fallback)"""
        if engagement_matrix_cache:
            threat_current_pos = getattr(threat, 'current_position', None)
            if threat_current_pos and len(threat_current_pos) >= 2:
                threat_current_pos = (threat_current_pos[0], threat_current_pos[1])
            bat = battery_lookup.get(system_id) if battery_lookup else None
            battery_position = bat.get('position') if bat else None
            battery_specs = bat.get('specs') if bat else None
            return engagement_matrix_cache.is_feasible(
                system_id, threat_id,
                threat_current_position=threat_current_pos,
                battery_position=battery_position,
                battery_specs=battery_specs
            )
        elif engagement_matrix_dict:
            return engagement_matrix_dict.get((system_id, threat_id), False)
        return False

    def get_upper_systems_for_threat(self, threat_id: str) -> List[str]:
        """특정 threat에 대해 feasible한 상층 system ID 리스트"""
        return self.threat_to_upper.get(threat_id, [])

    def get_lower_systems_for_threat(self, threat_id: str) -> List[str]:
        """특정 threat에 대해 feasible한 하층 system ID 리스트"""
        return self.threat_to_lower.get(threat_id, [])

    def get_threats_for_system(self, system_id: str) -> List[str]:
        """특정 system에 대해 feasible한 threat ID 리스트"""
        return self.system_to_threats.get(system_id, [])

    @property
    def density(self) -> float:
        """feasible pair 비율 (ρ)"""
        if not self._built:
            return 0.0
        return len(self.all_pairs) / max(1, len(self.threat_to_upper) *
               (len(set(s for s, _ in self.upper_pairs)) + len(set(s for s, _ in self.lower_pairs))))
