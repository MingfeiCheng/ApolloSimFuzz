from loguru import logger
from dataclasses import dataclass
from typing import Optional
from omegaconf import DictConfig

@dataclass
class MapRegionSpace:
    
    map_name = "san_mateo"
    region_points = [
        [559667.48, 4157903.06],
        [559742.52, 4157909.33],
        [559771.16, 4157886.54],
        [559762.98, 4157794.33],
        [559737.12, 4157774.33],
        [559653.62, 4157797.13],
        [559631.16, 4157834.61],
        [559646.16, 4157897.11],
        [559667.48, 4157903.06]
    ]
    forbidden_region_points = []  # if empty, means no restriction
    
    # refine lanes and crosswalks
    driving_lanes = []  # if empty, means no restriction
    crosswalks = []     # if empty, means no restriction
    forbidden_lanes = []  # if empty, means no restriction
    
    potential_route_lanes = []
    
@dataclass
class EGOSpace:
    num_range = [1, 5]
    route_length_range = [50.0, 200.0]
    trigger_time_range = [0.0, 5.0]
    
    model_range = [
        "vehicle.lincoln.mkz",
    ]
    
    # other hyperparameters # NOTE: may not useful
    dist2vehicle_same_lane = 10.0
    dist2vehicle_other_lane = 2.0 # in case overlapping
    dist2pedestrian = 1.0
    dist2static_same_lane = 10.0
    dist2static_other_lane = 5.0
    
@dataclass
class NPCVhicleSpace:
    
     # npc vehicles
    num_range = [0, 5] # now we fixed
    trigger_time_range = [0.0, 5.0]
    speed_range = [0.3, 10.0]  # in m/s
    delta_speed = 2.0 # in m/s
    route_length_range = [100.0, 400.0]  # in meters
    
    model_range = [
        "vehicle.lincoln.mkz",
        "vehicle.bicycle.normal"
    ]
    
    # other hyperparameters
    dist2vehicle_same_lane = 10.0
    dist2vehicle_other_lane = 2.0 # in case overlapping
    dist2pedestrian = 1.0 # always on sidewals
    dist2static_same_lane = 10.0
    dist2static_other_lane = 5.0
    
@dataclass
class NPCPedestrianSpace:
        
    # npc pedestrians
    num = [0, 10] # now we fixed
    trigger_time = [0.0, 5.0]
    
    speed = [0.0, 3.0]  # in m/s
    delta_speed = [0.0, 1.0] # in m/s
    route_length = [20.0, 100.0]  # in meters
    
    # other hyperparameters
    dist2vehicle_same_lane = 5.0
    dist2vehicle_other_lane = 2.0 # in case overlapping
    dist2pedestrian = 1.0
    dist2static_same_lane = 5.0
    dist2static_other_lane = 2.0

@dataclass
class NPCStaticSpace:
    
    num = [0, 2]   
    # other hyperparameters
    dist2vehicle_same_lane = 10.0
    dist2vehicle_other_lane = 5.0 # in case overlapping
    dist2pedestrian = 1.0 # always on sidewals
    dist2static_same_lane = 5.0
    dist2static_other_lane = 15.0
    
@dataclass
class TrafficLightSpace:
    """Traffic light states."""
    # 4
    pattern_range = ["force_green", "rule"] # NOTE: we first only using green lights, for quick safety check
    green_duration_range = [5.0, 10.0]  # in seconds
    yellow_duration_range = [2.0, 3.0]  # in seconds
    red_duration_range = [5.0, 10.0]    # in seconds

class ScenarioODDSpace:
    """Overall ODD space for scenario sampling."""
    
    map_region_space: MapRegionSpace = MapRegionSpace()
    ego_space: EGOSpace = EGOSpace()
    npc_vehicle_space: NPCVhicleSpace = NPCVhicleSpace()
    npc_pedestrian_space: NPCPedestrianSpace = NPCPedestrianSpace()
    npc_static_space: NPCStaticSpace = NPCStaticSpace()
    traffic_light_space: TrafficLightSpace = TrafficLightSpace()

    def __init__(self, space_config: Optional[DictConfig] = None):
        """
        space_config 是一个 OmegaConf DictConfig用法
        
        space_config:
            ego_space:
                trigger_time: [0.0, 10.0]
                route_length: [40, 300]
            weather_space:
                precipitation: [0, 80]
                fog_distance: [0, 200]
        
        只更新给定字段，未指定字段保持默认。
        """

        if space_config is None:
            return
        
        # 依次更新每个空间
        self._assign_config_to_space("map_region_space", MapRegionSpace, space_config)
        self._assign_config_to_space("ego_space", EGOSpace, space_config)
        self._assign_config_to_space("npc_vehicle_space", NPCVhicleSpace, space_config)
        self._assign_config_to_space("npc_pedestrian_space", NPCPedestrianSpace, space_config)
        self._assign_config_to_space("npc_static_space", NPCStaticSpace, space_config)
        self._assign_config_to_space("traffic_light_space", TrafficLightSpace, space_config)

    def _assign_config_to_space(self, attr_name: str, cls, cfg: DictConfig):
        """
        将 cfg 中 attr_name 对应的配置赋值给 self.attr_name。

        attr_name : 字段名称（字符串）
        cls : dataclass 类
        cfg : DictConfig
        
        示例：
        cfg = {
          "ego_space": {
              "trigger_time": [0, 5],
              "route_length": [60, 200]
          }
        }
        """
        if attr_name not in cfg:
            return
        
        sub_cfg = cfg[attr_name]
        space_obj = getattr(self, attr_name)

        for key, val in sub_cfg.items():
            if hasattr(space_obj, key):
                setattr(space_obj, key, val)
            else:
                logger.warning(f"[WARNING] Unknown config key '{key}' in '{attr_name}' (ignored).")