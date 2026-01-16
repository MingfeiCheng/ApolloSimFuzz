"""
This select route for the ego
Here defines the scenario configuration
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

from scenario_elements.config.waypoint import Waypoint, Location, Rotation, LaneItem

from .sm_ego import ApolloConfig
from .sm_static_obstacle import StaticObstacleConfig
from .sm_waypoint_vehicle import WaypointVehicleConfig
from .sm_waypoint_walker import WaypointWalkerConfig
from .sm_traffic_light import RuleLightConfig, LightConfig

class MapConfig(BaseModel):
    map_name: str = Field(..., description="map name, e.g., 'san_francisco'")
    
    coarse_points: List[List[float]] = Field(
        ..., description="List of coarse points defining the drivable area, each point is [x, y]"
    )
    lanes: Optional[List[str]] = Field(
        None, description="List of lane IDs relevant to the scenario"
    )
    crosswalks: Optional[List[str]] = Field(
        None, description="List of crosswalk IDs relevant to the scenario"
    )
    
class ScenarioConfig(BaseModel):
    id: str = Field(
        ..., 
        description="Unique identifier for the scenario")
    scenario_type: str = Field(
        "openscenario", 
        description="Type of scenario, e.g., 'intersection', 'lane_change'")
    ego_vehicles: Optional[List[ApolloConfig]] = Field(
        None, description="List of Ego vehicle configurations"
    )
    npc_vehicles: Optional[List[WaypointVehicleConfig]] = Field(
        None, description="List of NPC vehicle configurations"
    )
    npc_walkers: Optional[List[WaypointWalkerConfig]] = Field(
        None, description="List of NPC walker configurations"
    )
    npc_statics: Optional[List[StaticObstacleConfig]] = Field(
        None, description="List of Static obstacle configurations"
    )
    traffic_light: Optional[RuleLightConfig] = Field(
        None, description="Traffic light behavior configuration")
    map_region: Optional[MapConfig] = Field(
        None, description="Map configuration")
    
    def get_map_name(self) -> str:
        return self.map_region.map_name