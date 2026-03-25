"""
DWTA 벤치마크 최적화 시나리오
================================
학술 논문용 균형잡힌 DWTA 시나리오 설계

목표:
- 알고리즘 차별성 명확화 (MIP vs GA vs Greedy)
- 자원 제약 현실화 (과도한 자원 제거)
- 공정한 위협 분배 (모든 자산에 균등)
- 적절한 난이도 (GA 85~95%, MIP 90~98%)
"""

from typing import Dict, List
from config_mip import AssetConfig, InterceptorSystemConfig

class DWTABalancedScenario:
    """DWTA 벤치마크용 균형 시나리오"""
    
    @staticmethod
    def create_balanced_assets() -> List[Dict]:
        """
        균형잡힌 자산 가치 분포 (10개)
        - 균등 분포로 편차 최소화
        - 총 가치: 9,500
        """
        assets = [
            # 3계층 구조: 고가(4개), 중가(3개), 저가(3개)
            # 고가 자산 (1200~1500)
            {"id": "A01", "name": "Blue_House", "position": (0, 0), "value": 1500, "priority": 1},
            {"id": "A02", "name": "Defense_Ministry", "position": (2, -1), "value": 1400, "priority": 1},
            {"id": "A03", "name": "Intelligence_Service", "position": (-3, 1), "value": 1300, "priority": 1},
            {"id": "A04", "name": "Gyeryong_Command", "position": (15, -25), "value": 1200, "priority": 1},
            
            # 중가 자산 (800~1000)
            {"id": "A05", "name": "Pyeongtaek_US_Base", "position": (5, -15), "value": 1000, "priority": 2},
            {"id": "A06", "name": "Osan_Air_Base", "position": (8, -20), "value": 900, "priority": 2},
            {"id": "A07", "name": "Incheon_Airport", "position": (-25, 15), "value": 800, "priority": 2},
            
            # 저가 자산 (500~700)
            {"id": "A08", "name": "Busan_Port", "position": (50, -80), "value": 700, "priority": 3},
            {"id": "A09", "name": "Incheon_Port", "position": (-20, 10), "value": 600, "priority": 3},
            {"id": "A10", "name": "Gimpo_Airport", "position": (-10, 5), "value": 500, "priority": 3}
        ]
        
        # 통계 출력
        values = [a['value'] for a in assets]
        print(f"자산 가치 분포: 평균={sum(values)/len(values):.0f}, 총합={sum(values)}, 범위={min(values)}~{max(values)}")
        
        return assets
    
    @staticmethod
    def create_balanced_threats() -> List[Dict]:
        """
        균형잡힌 위협 분배 (20발)
        - 모든 자산에 정확히 2발씩 할당
        - 동시 발사 + 순차 발사 혼합
        """
        threats = []
        
        # 자산 목록 (위치 정보 포함)
        assets = DWTABalancedScenario.create_balanced_assets()
        asset_map = {asset["id"]: asset["position"] for asset in assets}
        asset_ids = [f"A{i:02d}" for i in range(1, 11)]
        
        # 각 자산당 2발씩 할당
        threat_id = 1
        
        # 1차 공격파: 각 자산에 1발씩 (0~90초, 10초 간격)
        for i, asset_id in enumerate(asset_ids):
            threats.append({
                "id": f"T{threat_id:02d}",
                "name": f"Nodong_{threat_id}",
                "type": "NODONG",
                "target_asset_id": asset_id,
                "target_position": asset_map[asset_id],  # 교전 매트릭스 계산용
                "launch_time": i * 10,  # 0, 10, 20, ..., 90초
                "flight_time": 480,
                "launch_position": (i * 20 - 90, 500),  # Y축 500km (상승+하강 모두 교전 가능)
                "trajectory_type": "ballistic",
                "rcs": 1.5,
                "phase_events": {
                    "midcourse_time": i * 10 + 240,
                    "terminal_time": i * 10 + 320,
                    "critical_altitude_km": 55.0,  # LSAM 최적 범위 (40~70km 중간)
                    "terminal_velocity_ms": 1800
                },
                "specs": {
                    "max_range_km": 1300,
                    "max_altitude_km": 80,
                    "speed_mach": 3.5,
                    "payload_kg": 800,
                    "cep_m": 2000,
                    "launch_weight_kg": 16500
                }
            })
            threat_id += 1
        
        # 2차 공격파: MSAM 담당 자산을 목표로 (120~210초, 10초 간격)
        # MSAM 담당 자산: A01,A02,A03 (MSAM_01), A07,A09,A10 (MSAM_02), A04,A05 (MSAM_03)
        scud_targets = ["A05", "A02", "A03", "A07", "A09", "A10", "A04", "A05", "A01", "A02"]  # T11: A01→A05 (MSAM 사거리 내)
        
        for i, target_asset_id in enumerate(scud_targets):
            threats.append({
                "id": f"T{threat_id:02d}",
                "name": f"ScudB_{threat_id}",
                "type": "SCUD_B",
                "target_asset_id": target_asset_id,
                "target_position": asset_map[target_asset_id],  # 교전 매트릭스 계산용
                "launch_time": 140 + i * 10,  # 140, 150, 160, ..., 230초 (10초 앞당김)
                "flight_time": 270,  # 250→270초 (20초 연장)
                "launch_position": (i * 15 - 70, 80),  # Y=80km으로 조정 (MSAM 사거리 내)
                "trajectory_type": "ballistic",
                "rcs": 0.8,
                "phase_events": {
                    "midcourse_time": 140 + i * 10 + 135,  # 중간 단계 (비행 50%)
                    "terminal_time": 140 + i * 10 + 220,  # 종말 단계 (비행 81%)
                    "critical_altitude_km": 25.0,
                    "terminal_velocity_ms": 1200
                },
                "specs": {
                    "max_range_km": 300,
                    "max_altitude_km": 40,
                    "speed_mach": 2.5,
                    "payload_kg": 985,
                    "cep_m": 450,
                    "launch_weight_kg": 5900
                }
            })
            threat_id += 1
        
        # 통계 출력
        print(f"위협 분배: 총 {len(threats)}발, 자산당 {len(threats)//10}발")
        
        # 표적 분포 확인
        target_dist = {}
        for t in threats:
            target = t['target_asset_id']
            target_dist[target] = target_dist.get(target, 0) + 1
        print(f"표적 분포: {target_dist}")
        
        return threats
    
    @staticmethod
    def create_constrained_batteries() -> List[Dict]:
        """
        제약된 방어 자원 (6개 포대)
        - LSAM 3개 (20발/포대) = 60발
        - MSAM 3개 (30발/포대) = 90발
        - 총 150발 (위협 20발 대비 7.5배)
        """
        batteries = [
            # 상층 방어 (LSAM) - 3개 포대
            {
                "id": "LSAM_01",
                "name": "Seoul_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (0, 0),
                "coverage_radius_km": 150,
                "defense_zone": "ZONE_1_SEOUL",
                "dedicated_assets": ["A01", "A02", "A03", "A04"],
                "specs": {
                    **InterceptorSystemConfig.get_lsam_specs(),
                    "battery_config": {
                        "launchers": 4,
                        "missiles_per_launcher": 5,  # 6→5
                        "total_missiles": 20,  # 24→20
                        "simultaneous_engagements": 5
                    }
                }
            },
            {
                "id": "LSAM_02",
                "name": "Central_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (10, -20),
                "coverage_radius_km": 150,
                "defense_zone": "ZONE_2_CENTRAL",
                "dedicated_assets": ["A05", "A06", "A07"],
                "specs": {
                    **InterceptorSystemConfig.get_lsam_specs(),
                    "battery_config": {
                        "launchers": 4,
                        "missiles_per_launcher": 5,
                        "total_missiles": 20,
                        "simultaneous_engagements": 5
                    }
                }
            },
            {
                "id": "LSAM_03",
                "name": "South_LSAM",
                "system_type": "LSAM",
                "layer": "UPPER",
                "position": (50, -75),
                "coverage_radius_km": 150,
                "defense_zone": "ZONE_3_SOUTH",
                "dedicated_assets": ["A08", "A09", "A10"],
                "specs": {
                    **InterceptorSystemConfig.get_lsam_specs(),
                    "battery_config": {
                        "launchers": 4,
                        "missiles_per_launcher": 5,
                        "total_missiles": 20,
                        "simultaneous_engagements": 5
                    }
                }
            },
            
            # 하층 방어 (MSAM) - 3개 포대
            {
                "id": "MSAM_01",
                "name": "Seoul_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (5, -5),
                "coverage_radius_km": 40,
                "defense_zone": "ZONE_1_SEOUL",
                "dedicated_assets": ["A01", "A02", "A03", "A04"],
                "specs": {
                    **InterceptorSystemConfig.get_msam_specs(),
                    "battery_config": {
                        "launchers": 6,
                        "missiles_per_launcher": 5,  # 8→5
                        "total_missiles": 30,  # 48→30
                        "simultaneous_engagements": 5
                    }
                }
            },
            {
                "id": "MSAM_02",
                "name": "Central_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (15, -25),
                "coverage_radius_km": 40,
                "defense_zone": "ZONE_2_CENTRAL",
                "dedicated_assets": ["A05", "A06", "A07"],
                "specs": {
                    **InterceptorSystemConfig.get_msam_specs(),
                    "battery_config": {
                        "launchers": 6,
                        "missiles_per_launcher": 5,
                        "total_missiles": 30,
                        "simultaneous_engagements": 5
                    }
                }
            },
            {
                "id": "MSAM_03",
                "name": "South_MSAM",
                "system_type": "MSAM",
                "layer": "LOWER",
                "position": (55, -80),
                "coverage_radius_km": 40,
                "defense_zone": "ZONE_3_SOUTH",
                "dedicated_assets": ["A08", "A09", "A10"],
                "specs": {
                    **InterceptorSystemConfig.get_msam_specs(),
                    "battery_config": {
                        "launchers": 6,
                        "missiles_per_launcher": 5,
                        "total_missiles": 30,
                        "simultaneous_engagements": 5
                    }
                }
            }
        ]
        
        # 통계 출력
        total_missiles = sum(b['specs']['battery_config']['total_missiles'] for b in batteries)
        print(f"방어 자원: 총 {len(batteries)}개 포대, {total_missiles}발 미사일")
        
        return batteries


class ScenarioManager:
    """통합 시나리오 관리자 - config_mip.py의 모든 시나리오를 DWTA 설계 원칙으로 재구현"""
    
    @staticmethod
    def get_scenario_list() -> Dict[str, str]:
        """사용 가능한 모든 시나리오 목록"""
        return {
            # 확장성 테스트 (Scalability)
            "SMALL_3": "초소규모 (3발 - 알고리즘 검증)",
            "SMALL_5": "소규모 (5발 - 기본 성능)",
            "SMALL_8": "소중규모 (8발 - 전환점)",
            "MEDIUM_10": "중소규모 (10발 - 일반 공격)",
            "BASELINE_15": "중규모 기본 (15발 - 표준)",
            "MEDIUM_20": "중대규모 (20발 - 균형 공격)",
            "LARGE_30": "대규모 (30발 - 포화 공격)",
            "LARGE_40": "초대규모 (40발 - 한계 테스트)",
            "STRESS_100": "스트레스 (100발 - 성능 검증)",
            "STRESS_150": "스트레스 (150발 - 점진적 확장)",
            "STRESS_200": "스트레스 (200발 - 한계 탐색)",
            "STRESS_300": "스트레스 (300발 - 극한 테스트)",

            # 공격 패턴
            "SEQUENTIAL_15": "순차 공격 (15발 - 순차 발사)",
            "SIMULTANEOUS_15": "동시 공격 (15발 - 동시 발사)",

            # 표준 벤치마크
            "DWTA_BALANCED": "표준 벤치마크 (20발, 6개 배터리)"
        }
    
    @staticmethod
    def create_scenario(scenario_type: str) -> Dict:
        """시나리오 타입에 따라 자산, 배터리, 위협 생성"""
        if scenario_type == "DWTA_BALANCED":
            return {
                "assets": DWTABalancedScenario.create_balanced_assets(),
                "batteries": DWTABalancedScenario.create_constrained_batteries(),
                "threats": DWTABalancedScenario.create_balanced_threats()
            }
        elif scenario_type.startswith("SEQUENTIAL_"):
            num_threats = int(scenario_type.split("_")[1])
            return {
                "assets": ScenarioManager._create_assets(num_threats),
                "batteries": ScenarioManager._create_batteries(num_threats),
                "threats": ScenarioManager._create_threats(num_threats, pattern="sequential")
            }
        elif scenario_type.startswith("SIMULTANEOUS_"):
            num_threats = int(scenario_type.split("_")[1])
            return {
                "assets": ScenarioManager._create_assets(num_threats),
                "batteries": ScenarioManager._create_batteries(num_threats),
                "threats": ScenarioManager._create_threats(num_threats, pattern="simultaneous")
            }
        else:
            # SMALL_N, MEDIUM_N, BASELINE_N, HEAVY_N, LARGE_N, STRESS_N 등
            # 마지막 _숫자 패턴에서 위협 수 추출
            parts = scenario_type.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                num_threats = int(parts[1])
            else:
                raise ValueError(f"Unknown scenario type: {scenario_type}")
            return {
                "assets": ScenarioManager._create_assets(num_threats),
                "batteries": ScenarioManager._create_batteries(num_threats),
                "threats": ScenarioManager._create_threats(num_threats, pattern="balanced")
            }
    
    @staticmethod
    def _create_assets(num_threats: int) -> List[Dict]:
        """위협 수에 비례한 자산 생성"""
        base_assets = DWTABalancedScenario.create_balanced_assets()
        
        if num_threats <= 10:
            return base_assets
        
        # 위협이 많으면 자산 추가 (최대 20개)
        num_assets = min(20, max(10, num_threats // 2))
        assets = base_assets[:num_assets]
        
        for i in range(len(base_assets), num_assets):
            assets.append({
                "id": f"A{i+1:02d}",
                "name": f"Asset_{i+1}",
                "position": ((i-10) * 10, (i-10) * -8),
                "value": 1000 - (i-10) * 50,
                "priority": 2
            })
        
        return assets
    
    @staticmethod
    def _create_batteries(num_threats: int) -> List[Dict]:
        """위협 수에 비례한 배터리 생성"""
        if num_threats <= 20:
            # 20발 이하: 6개 배터리 (제약)
            return DWTABalancedScenario.create_constrained_batteries()
        elif num_threats <= 50:
            # 50발 이하: 10개 배터리 (균형)
            base = DWTABalancedScenario.create_constrained_batteries()
            additional = [
                {
                    "id": "LSAM_04", "name": "East_LSAM", "system_type": "LSAM", "layer": "UPPER",
                    "position": (30, -10), "coverage_radius_km": 150, "defense_zone": "ZONE_4",
                    "dedicated_assets": ["A05", "A06"],
                    "specs": {
                        **InterceptorSystemConfig.get_lsam_specs(),
                        "battery_config": {"launchers": 4, "missiles_per_launcher": 5, "total_missiles": 20, "simultaneous_engagements": 5}
                    }
                },
                {
                    "id": "LSAM_05", "name": "West_LSAM", "system_type": "LSAM", "layer": "UPPER",
                    "position": (-30, 10), "coverage_radius_km": 150, "defense_zone": "ZONE_5",
                    "dedicated_assets": ["A07", "A09"],
                    "specs": {
                        **InterceptorSystemConfig.get_lsam_specs(),
                        "battery_config": {"launchers": 4, "missiles_per_launcher": 5, "total_missiles": 20, "simultaneous_engagements": 5}
                    }
                },
                {
                    "id": "MSAM_04", "name": "East_MSAM", "system_type": "MSAM", "layer": "LOWER",
                    "position": (35, -15), "coverage_radius_km": 40, "defense_zone": "ZONE_4",
                    "dedicated_assets": ["A05", "A06"],
                    "specs": {
                        **InterceptorSystemConfig.get_msam_specs(),
                        "battery_config": {"launchers": 6, "missiles_per_launcher": 5, "total_missiles": 30, "simultaneous_engagements": 5}
                    }
                },
                {
                    "id": "MSAM_05", "name": "West_MSAM", "system_type": "MSAM", "layer": "LOWER",
                    "position": (-25, 5), "coverage_radius_km": 40, "defense_zone": "ZONE_5",
                    "dedicated_assets": ["A07", "A09"],
                    "specs": {
                        **InterceptorSystemConfig.get_msam_specs(),
                        "battery_config": {"launchers": 6, "missiles_per_launcher": 5, "total_missiles": 30, "simultaneous_engagements": 5}
                    }
                }
            ]
            return base + additional
        elif num_threats <= 100:
            # 100발: 15개 배터리 (LSAM×10 + MSAM×5)
            batteries_10 = ScenarioManager._create_batteries(50)
            more = [
                {
                    "id": f"LSAM_{i:02d}", "name": f"Extra_LSAM_{i}", "system_type": "LSAM", "layer": "UPPER",
                    "position": ((i-6) * 40, (i-6) * -30), "coverage_radius_km": 150, "defense_zone": f"ZONE_{i}",
                    "dedicated_assets": [f"A{(i%10)+1:02d}"],
                    "specs": {
                        **InterceptorSystemConfig.get_lsam_specs(),
                        "battery_config": {"launchers": 4, "missiles_per_launcher": 5, "total_missiles": 20, "simultaneous_engagements": 5}
                    }
                } for i in range(6, 11)
            ]
            return batteries_10 + more
        elif num_threats <= 200:
            # 200발: 20개 배터리 (LSAM×10 + MSAM×10)
            batteries_15 = ScenarioManager._create_batteries(100)
            more = [
                {
                    "id": f"MSAM_{i:02d}", "name": f"Extra_MSAM_{i}", "system_type": "MSAM", "layer": "LOWER",
                    "position": ((i-6) * 30, (i-6) * -20), "coverage_radius_km": 40, "defense_zone": f"ZONE_M{i}",
                    "dedicated_assets": [f"A{(i%10)+1:02d}"],
                    "specs": {
                        **InterceptorSystemConfig.get_msam_specs(),
                        "battery_config": {"launchers": 6, "missiles_per_launcher": 8, "total_missiles": 48, "simultaneous_engagements": 5}
                    }
                } for i in range(6, 11)
            ]
            return batteries_15 + more
        else:
            # 300발+: 25개 배터리 (LSAM×15 + MSAM×10)
            batteries_20 = ScenarioManager._create_batteries(200)
            more = [
                {
                    "id": f"LSAM_{i:02d}", "name": f"Extra_LSAM_{i}", "system_type": "LSAM", "layer": "UPPER",
                    "position": ((i-11) * 50, (i-11) * -35), "coverage_radius_km": 150, "defense_zone": f"ZONE_{i}",
                    "dedicated_assets": [f"A{(i%10)+1:02d}"],
                    "specs": {
                        **InterceptorSystemConfig.get_lsam_specs(),
                        "battery_config": {"launchers": 4, "missiles_per_launcher": 6, "total_missiles": 24, "simultaneous_engagements": 5}
                    }
                } for i in range(11, 16)
            ]
            return batteries_20 + more
    
    @staticmethod
    def _create_threats(num_threats: int, pattern: str = "balanced") -> List[Dict]:
        """
        DWTA 설계 원칙을 적용한 위협 생성
        - NODONG: Y=500km (상층 방어)
        - SCUD_B: Y=80km (하층 방어, 실시간 거리 체크)
        - 발사 간격: McCormick 솔버 최적화
        """
        threats = []
        assets = ScenarioManager._create_assets(num_threats)
        asset_map = {a["id"]: a["position"] for a in assets}
        asset_ids = [a["id"] for a in assets]
        
        # 발사 간격 계산 (McCormick 솔버 최적화)
        if num_threats <= 5:
            interval = 15
        elif num_threats <= 10:
            interval = 10
        elif num_threats <= 20:
            interval = 8
        elif num_threats <= 30:
            interval = 6
        elif num_threats <= 50:
            interval = 5
        else:
            interval = 3
        
        # 공격 패턴별 발사 시간 계산
        if pattern == "simultaneous":
            # 동시 발사: 모두 T=0
            launch_times = [0] * num_threats
        elif pattern == "sequential":
            # 순차 발사: 긴 간격
            launch_times = [i * interval * 2 for i in range(num_threats)]
        else:
            # 균형 발사: 표준 간격
            launch_times = [i * interval for i in range(num_threats)]
        
        # NODONG vs SCUD_B 비율 (50:50)
        num_nodong = num_threats // 2
        num_scud = num_threats - num_nodong
        
        # NODONG 미사일 생성 (상층 방어)
        for i in range(num_nodong):
            target_asset = asset_ids[i % len(asset_ids)]
            threats.append({
                "id": f"T{i+1:02d}",
                "name": f"Nodong_{i+1}",
                "type": "NODONG",
                "target_asset_id": target_asset,
                "target_position": asset_map[target_asset],
                "launch_time": launch_times[i],
                "flight_time": 480,
                "launch_position": (i * 20 - num_nodong * 10, 500),  # Y=500km
                "trajectory_type": "ballistic",
                "rcs": 1.5,
                "phase_events": {
                    "midcourse_time": launch_times[i] + 240,
                    "terminal_time": launch_times[i] + 320,
                    "critical_altitude_km": 55.0,
                    "terminal_velocity_ms": 1800
                },
                "specs": {
                    "max_range_km": 1300,
                    "max_altitude_km": 80,
                    "speed_mach": 3.5,
                    "payload_kg": 800,
                    "cep_m": 2000,
                    "launch_weight_kg": 16500
                }
            })
        
        # SCUD_B 미사일 생성 (하층 방어)
        for i in range(num_scud):
            target_asset = asset_ids[i % len(asset_ids)]
            threat_id = num_nodong + i + 1
            launch_time = launch_times[num_nodong + i]
            
            threats.append({
                "id": f"T{threat_id:02d}",
                "name": f"ScudB_{threat_id}",
                "type": "SCUD_B",
                "target_asset_id": target_asset,
                "target_position": asset_map[target_asset],
                "launch_time": launch_time,
                "flight_time": 300,
                "launch_position": (i * 15 - num_scud * 7, 80),  # Y=80km
                "trajectory_type": "ballistic",
                "rcs": 0.8,
                "phase_events": {
                    "midcourse_time": launch_time + 135,
                    "terminal_time": launch_time + 220,
                    "critical_altitude_km": 25.0,
                    "terminal_velocity_ms": 1200
                },
                "specs": {
                    "max_range_km": 300,
                    "max_altitude_km": 40,
                    "speed_mach": 2.5,
                    "payload_kg": 985,
                    "cep_m": 450,
                    "launch_weight_kg": 5900
                }
            })
        
        print(f"시나리오 생성: {num_threats}발 (NODONG: {num_nodong}, SCUD_B: {num_scud}), 간격: {interval}초, 패턴: {pattern}")
        return threats


# 사용 예시
if __name__ == "__main__":
    print("=" * 80)
    print("DWTA 균형 시나리오 설계")
    print("=" * 80)
    
    scenario = DWTABalancedScenario()
    
    print("\n[1] 자산 구성")
    assets = scenario.create_balanced_assets()
    
    print("\n[2] 위협 구성")
    threats = scenario.create_balanced_threats()
    
    print("\n[3] 방어 자원")
    batteries = scenario.create_constrained_batteries()
    
    print("\n" + "=" * 80)
    print("시나리오 요약")
    print("=" * 80)
    print(f"자산: {len(assets)}개, 총 가치: {sum(a['value'] for a in assets):,}")
    print(f"위협: {len(threats)}발 (자산당 {len(threats)//len(assets)}발)")
    print(f"방어: {len(batteries)}개 포대, 총 {sum(b['specs']['battery_config']['total_missiles'] for b in batteries)}발")
    print(f"자원 비율: {sum(b['specs']['battery_config']['total_missiles'] for b in batteries) / len(threats):.1f}배")
    print("\n예상 성능:")
    print("  MIP:    90~98% (최적 할당)")
    print("  GA:     85~95% (준최적)")
    print("  Greedy: 60~75% (휴리스틱)")
    print("=" * 80)
