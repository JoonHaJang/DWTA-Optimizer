# config.py (업데이트됨)
SIMULATION_TIME_STEP = 0.1  # 시뮬레이션 시간 단계 (초)

from pydantic import BaseModel, Field, model_validator, validator, ValidationError
from typing import Tuple, Dict
import numpy as np

# 1. 레이더 설정 모델
class RadarConfig(BaseModel):
    max_concurrent_tracks: int = Field(50, description="최대 동시 추적 대상 수")
    detection_range_km: int = Field(1200, description="탐지 범위 (km)")
    scan_interval_sec: float = Field(0.25, description="스캔 간격 (초)")
    min_signal_strength_db: int = Field(-80, description="최소 신호 강도 (dB)")
    min_track_quality: float = Field(0.6, description="최소 트랙 품질 (비율)")
    position_accuracy: float = Field(0.98, description="위치 정확도 (비율)")
    max_range_km: int = Field(2000, description="최대 범위 (km)")
    azimuth_angle_deg: int = Field(360, description="방위각 (도)")
    elevation_angle_deg: int = Field(90, description="고도 각 (도)")
    update_rate_sec: float = Field(0.5, description="업데이트 주기 (초)")

# 2. 인터셉터 설정 모델
class InterceptorConfig(BaseModel):
    speed_km_s: float = Field(1.7, description="요격 미사일 속도 (km/s)")
    max_range_km: int = Field(70, description="최대 사거리 (km)")
    min_range_km: float = Field(3.0, description="최소 사거리 (km)")
    max_g: int = Field(30, description="최대 G-포스")
    guidance_delay_sec: float = Field(0.5, description="유도 지연 (초)")
    kill_radius_km: float = Field(1.0, description="요격 반경 (km)")
    min_rcs_m2: float = Field(0.05, description="최소 RCS (m²)")
    # 새로운 설정: 요격 미사일 물리 시뮬레이션 관련
    max_flight_time_sec: float = Field(60.0, description="최대 비행 시간 (초)")
    gravity_effect: bool = Field(True, description="중력 효과 적용 여부")
    post_miss_simulation_time: float = Field(10.0, description="실패 후 추가 시뮬레이션 시간 (초)")

# 3. 무기 레이더 설정 모델
class WeaponRadarConfig(BaseModel):
    max_range_km: int = Field(100, description="레이더 최대 범위 (km)")
    azimuth_angle_deg: int = Field(90, description="레이더 방위각 (도)")
    elevation_angle_deg: int = Field(80, description="레이더 고도 각 (도)")
    accuracy: float = Field(0.95, description="레이더 정확도 (비율)")
    update_rate_hz: float = Field(1.0, description="업데이트 주기 (Hz)")

# 4. 무기 체계 모델
class WeaponSystem(BaseModel):
    name: str = Field("PATRIOT", description="무기 체계 이름")
    radar: WeaponRadarConfig = Field(default_factory=WeaponRadarConfig)
    interceptor: InterceptorConfig = Field(default_factory=InterceptorConfig)
    min_altitude_km: float = Field(0.1, description="최소 운용 고도 (km)")
    max_altitude_km: int = Field(25, description="최대 운용 고도 (km)")
    missiles_per_launcher: int = Field(4, description="발사대당 미사일 수")
    launchers_per_battery: int = Field(6, description="포대당 발사대 수")
    max_simultaneous_engagements: int = Field(2, description="동시 교전 가능한 목표 수")
    reload_time_sec: int = Field(300, description="재장전 시간 (초)")
    short_reload_time_sec: int = Field(20, description="짧은 재장전 시간 (초)") # 새로운 설정
    engagement_time_sec: int = Field(60, description="교전 시간 (초)")
    interceptable_threat_types: list[str] = Field(default_factory=list, description="요격 가능한 위협 유형 목록")

    def can_intercept(self, threat_type: str) -> bool:
        """이 무기 시스템이 특정 위협 유형을 요격할 수 있는지 확인합니다."""
        return threat_type in self.interceptable_threat_types

    @validator('min_altitude_km')
    def altitude_check(cls, v, values):
        max_alt = values.get('max_altitude_km')
        if max_alt is not None and v > max_alt:
            raise ValueError('min_altitude_km는 max_altitude_km보다 작아야 합니다.')
        return v

# 5. 배터리 위치 설정 모델
class BatteryPosition(BaseModel):
    type: str = Field("PATRIOT", description="무기 체계 타입 (예: PATRIOT, THAAD 등)")
    position_km: Tuple[int, int, int] = Field((10, 10, 0), description="배터리 위치 (x, y, z) km")
    max_range_km: int = Field(70, description="요격 미사일 최대 사거리 (km)")

# 6. 적 미사일 스펙 모델
class EnemyMissileSpec(BaseModel):
    speed_range_km_s: Tuple[float, float] = Field((3.0, 4.0), description="속도 범위 (km/s)")
    altitude_range_km: Tuple[int, int] = Field((120, 150), description="고도 범위 (km)")
    rcs_range_m2: Tuple[float, float] = Field((0.1, 0.3), description="RCS 범위 (m²)")
    weight: float = 0.25

# 7. 시각화 설정 모델 (새로운 추가)
class VisualizationConfig(BaseModel):
    log_window_enabled: bool = Field(True, description="로그 창 활성화 여부")
    log_window_size: Tuple[int, int] = Field((800, 600), description="로그 창 크기 (너비, 높이)")
    log_max_lines: int = Field(2000, description="로그 최대 라인 수")
    log_update_interval_ms: int = Field(100, description="로그 업데이트 간격 (밀리초)")
    auto_scroll: bool = Field(True, description="자동 스크롤 여부")
    log_colors: Dict[str, str] = Field(default_factory=lambda: {
        'INFO': '#00FF00',
        'WARNING': '#FFFF00', 
        'ERROR': '#FF0000',
        'SUCCESS': '#00FFFF',
        'MISSILE': '#FF00FF',
        'INTERCEPT': '#FFA500',
        'DEFAULT': '#FFFFFF'
    }, description="로그 레벨별 색상")

# 8. 전체 구성 모델
class Config(BaseModel):
    radar_config: RadarConfig = Field(default_factory=RadarConfig)
    visualization_config: VisualizationConfig = Field(default_factory=VisualizationConfig)  # 새로운 추가
    weapon_systems: Dict[str, WeaponSystem] = Field(default_factory=lambda: {
        "PATRIOT": WeaponSystem(
            name="PATRIOT",
            radar=WeaponRadarConfig(
                max_range_km=100,
                azimuth_angle_deg=90,
                elevation_angle_deg=80,
                accuracy=0.95,
                update_rate_hz=1.0
            ),
            interceptor=InterceptorConfig(
                speed_km_s=1.7,
                max_range_km=70,
                min_range_km=3,
                max_g=30,
                guidance_delay_sec=0.5,
                kill_radius_km=0.5,
                min_rcs_m2=0.05,
                max_flight_time_sec=60.0,
                gravity_effect=True,
                post_miss_simulation_time=10.0
            ),
            min_altitude_km=2,
            max_altitude_km=25,
            missiles_per_launcher=4,
            launchers_per_battery=6,
            max_simultaneous_engagements=2,
            reload_time_sec=300,
            short_reload_time_sec=20,
            engagement_time_sec=60,
            interceptable_threat_types=["BALLISTIC", "CRUISE"]
        ),
        "THAAD": WeaponSystem(
            name="THAAD",
            radar=WeaponRadarConfig(
                max_range_km=1000,
                azimuth_angle_deg=360,
                elevation_angle_deg=90,
                accuracy=0.98,
                update_rate_hz=2.0
            ),
            interceptor=InterceptorConfig(
                speed_km_s=2.8,
                max_range_km=200,
                min_range_km=5,
                max_g=25,
                guidance_delay_sec=0.3,
                kill_radius_km=0.7,
                min_rcs_m2=0.1,
                max_flight_time_sec=45.0,
                gravity_effect=True,
                post_miss_simulation_time=8.0
            ),
            min_altitude_km=20,
            max_altitude_km=150,
            missiles_per_launcher=4,
            launchers_per_battery=6,
            max_simultaneous_engagements=3,
            reload_time_sec=400,
            short_reload_time_sec=25,
            engagement_time_sec=45,
            interceptable_threat_types=["BALLISTIC"]
        ),
        "LSAM": WeaponSystem(
            name="LSAM",
            radar=WeaponRadarConfig(
                max_range_km=400,
                azimuth_angle_deg=360,
                elevation_angle_deg=90,
                accuracy=0.85,
                update_rate_hz=2.0
            ),
            interceptor=InterceptorConfig(
                speed_km_s=2.5,
                max_range_km=150,
                min_range_km=10,
                max_g=20,
                guidance_delay_sec=0.4,
                kill_radius_km=0.6,
                min_rcs_m2=0.15,
                max_flight_time_sec=50.0,
                gravity_effect=True,
                post_miss_simulation_time=12.0
            ),
            min_altitude_km=15,
            max_altitude_km=100,
            missiles_per_launcher=4,
            launchers_per_battery=6,
            max_simultaneous_engagements=3,
            reload_time_sec=350,
            short_reload_time_sec=22,
            engagement_time_sec=50,
            interceptable_threat_types=["BALLISTIC", "AIRCRAFT", "CRUISE"]
        ),
        "IRON_DOME": WeaponSystem(
            name="IRON_DOME",
            radar=WeaponRadarConfig(
                max_range_km=20,
                azimuth_angle_deg=90,
                elevation_angle_deg=70,
                accuracy=0.9,
                update_rate_hz=1.0
            ),
            interceptor=InterceptorConfig(
                speed_km_s=0.7,
                max_range_km=10,
                min_range_km=0.5,
                max_g=15,
                guidance_delay_sec=0.2,
                kill_radius_km=0.1,
                min_rcs_m2=0.01,
                max_flight_time_sec=30.0,
                gravity_effect=True,
                post_miss_simulation_time=5.0
            ),
            min_altitude_km=0.1,
            max_altitude_km=10,
            missiles_per_launcher=20,
            launchers_per_battery=1,
            max_simultaneous_engagements=10,
            reload_time_sec=1800,
            short_reload_time_sec=5,
            engagement_time_sec=30,
            interceptable_threat_types=["ROCKET", "MORTAR"]
        ),
        "MSAM": WeaponSystem(
            name="MSAM",
            radar=WeaponRadarConfig(
                max_range_km=200,
                azimuth_angle_deg=180,
                elevation_angle_deg=85,
                accuracy=0.78,
                update_rate_hz=1.5
            ),
            interceptor=InterceptorConfig(
                speed_km_s=2.0,
                max_range_km=120,
                min_range_km=5,
                max_g=25,
                guidance_delay_sec=0.3,
                kill_radius_km=0.4,
                min_rcs_m2=0.1,
                max_flight_time_sec=55.0,
                gravity_effect=True,
                post_miss_simulation_time=9.0
            ),
            min_altitude_km=10,
            max_altitude_km=80,
            missiles_per_launcher=4,
            launchers_per_battery=6,
            max_simultaneous_engagements=3,
            reload_time_sec=300,
            short_reload_time_sec=18,
            engagement_time_sec=40,
            interceptable_threat_types=["BALLISTIC", "AIRCRAFT", "CRUISE"]
        )
    })
    battery_positions: Dict[str, BatteryPosition] = Field(default_factory=lambda: {
        "BAT_1": BatteryPosition(),
        "BAT_2": BatteryPosition(type="PATRIOT", position_km=(-5, -20, 0), max_range_km=70)
    })
    enemy_missile_specs: Dict[str, EnemyMissileSpec] = Field(default_factory=lambda: {
        "ICBM": EnemyMissileSpec(
            speed_range_km_s=(3.0, 4.0),
            altitude_range_km=(120, 150),
            rcs_range_m2=(0.1, 0.3),
            weight = 0.3
        ),
        "IRBM": EnemyMissileSpec(
            speed_range_km_s=(2.5, 3.5),
            altitude_range_km=(100, 110),
            rcs_range_m2=(0.15, 0.35),
            weight = 0.2
        ),
        "SRBM": EnemyMissileSpec(
            speed_range_km_s=(1.5, 2.5),
            altitude_range_km=(10, 50),
            rcs_range_m2=(0.25, 0.45),
            weight = 0.25  
        ),
        "MBRM": EnemyMissileSpec(
            speed_range_km_s=(2.0, 3.0),
            altitude_range_km=(30, 90),
            rcs_range_m2=(0.2, 0.4),
            weight = 0.25
        )
    })

    @model_validator(mode='after')
    def validate_battery_types(self) -> 'Config':
        weapon_systems = self.weapon_systems
        battery_positions = self.battery_positions
        if weapon_systems and battery_positions:
            for bat_name, bat in battery_positions.items():
                if bat.type not in weapon_systems:
                    raise ValueError(
                        f"Battery {bat_name}의 타입 '{bat.type}'이 weapon_systems에 정의되어 있지 않습니다."
                    )
        return self

# 9. 적 미사일 모델
class EnemyMissile(BaseModel):
    missile_id: str = Field(..., description="미사일 고유 식별자")
    type: str = Field(..., description="미사일 종류 (예: ICBM, IRBM 등)")
    speed_km_s: float = Field(..., description="미사일 속도 (km/s)")
    altitude_km: float = Field(..., description="미사일 고도 (km)")
    rcs_m2: float = Field(..., description="미사일 RCS (m²)")
    initial_position: Tuple[float, float, float] = Field(..., description="발사 위치 (x, y, z)")
    current_position: Tuple[float, float, float] = Field(..., description="현재 위치 (x, y, z)")
    target_position: Tuple[float, float, float]  = Field(..., description="적 미사일 표적의 위치 (x, y, z)")
    heading_deg: float = Field(..., description="미사일 진행 방향 (도)")
    timestamp: float = Field(..., description="미사일 생성 또는 마지막 업데이트 시뮬레이션 시간")
    status: str = Field("flying", description="미사일 상태 (예: flying, intercepted 등)")

# 기본 구성 값으로 Config 인스턴스 생성
try:
    config = Config()
    print("Configuration values validated successfully.")
except ValidationError as e:
    print("구성 값 검증 실패:")
    print(e.json())

if __name__ == "__main__":
    print(config.model_dump_json(indent=2))