from typing import List, Any
from pydantic import BaseModel, Field

class LightConfig(BaseModel):
    
    id: str = Field(..., description="Unique identifier for the traffic light")
    category: str = Field(..., description="Category of the traffic light, e.g., 'stop_sign', 'traffic_light'")
    conflicts: List[str] = Field(
        default_factory=list, description="List of light IDs that conflict with this light"
    )
    equals: List[str] = Field(
        default_factory=list, description="List of light IDs that are synchronized with this light"
    )

class RuleLightConfig(BaseModel):
    
    id: str = Field(..., description="Unique identifier for the traffic light group")
    lights: List[LightConfig] = Field(..., description="List of traffic lights in this group")
    green_time: float = Field(10.0, description="Duration of green light (seconds)")
    yellow_time: float = Field(3.0, description="Duration of yellow light (seconds)")
    red_time: float = Field(10.0, description="Duration of red light (seconds)")
    initial_seed: int = Field(0, description="Initial random seed for timing variations")
    force_green: bool = Field(False, description="If true, forces all lights to green")