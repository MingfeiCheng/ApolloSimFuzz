from typing import List, Optional, Any
from pydantic import BaseModel, Field

from scenario_elements.config import Waypoint

class ApolloConfig(BaseModel):
    """Configuration for the ego vehicle."""

    # identity
    id: str = Field(..., description="Unique identifier for the ego vehicle")
    model: Optional[str] = Field(None, description="Ego vehicle model name")
    rolename: str = Field("ego", description="Role name, usually 'ego'")
    category: Optional[str] = Field(
        "car", description="Actor category, e.g., 'car', 'truck', 'bus'"
    )

    # behavior
    route: List[Waypoint] = Field(
        ..., description="Route as a list of waypoints (x, y, z, pitch, yaw, roll)"
    )
    trigger_time: float = Field(
        0.0, description="Simulation time (seconds) when the ego vehicle starts"
    )
    
    def get_initial_waypoint(self) -> Waypoint:
        """Get the initial waypoint of the ego vehicle."""
        return self.route[0]