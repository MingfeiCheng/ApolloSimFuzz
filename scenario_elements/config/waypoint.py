from pydantic import BaseModel, Field
from typing import Optional

class Location(BaseModel):
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    z: float = Field(..., description="Z coordinate")
    
class Rotation(BaseModel):
    pitch: float = Field(..., description="Pitch angle in degrees")
    yaw: float = Field(..., description="Yaw angle in degrees")
    roll: float = Field(..., description="Roll angle in degrees")

class LaneItem(BaseModel):
    id: str = Field(..., description="ID of the lane")
    s: float = Field(..., description="Longitudinal distance along the lane")
    l: float = Field(..., description="Lateral distance to the lane center")

class Waypoint(BaseModel):
    lane: LaneItem = Field(..., description="Lane information for the waypoint")
    location: Location = Field(..., description="3D location of the waypoint")
    rotation: Rotation = Field(..., description="Rotation at the waypoint")
    speed: float = Field(..., ge=0, description="Speed at this waypoint")