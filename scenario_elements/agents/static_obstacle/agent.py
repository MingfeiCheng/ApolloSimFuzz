import os
import ray
import time

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from tools.logger_tools import get_instance_logger

from scenario_elements.config import Waypoint
from scenario_elements.agents.base import AgentBase

class StaticObstacleConfig(BaseModel):
    
    id: str = Field(..., description="Unique identifier of the NPC vehicle")
    model: str = Field(..., description="Vehicle model name")
    rolename: str = Field(..., description="Role name, e.g., 'ego' or 'npc'")
    
    category: Optional[str] = Field("car", description="Vehicle category, e.g., 'car'")
    trigger_time: float = Field(..., ge=0, description="Time to start moving (seconds)")
    route: List[Waypoint] = Field(
        ..., description="List of waypoints describing the route"
    )
    
    def get_initial_waypoint(self) -> Waypoint:
        return self.route[0]

class StaticObstacleAgent(AgentBase):
    
    prefix = 'static_obstacle'
    running_frequency = 10.0

    def __init__(
        self,
        id: str,
        sim_ctn_name: str,
        actor_config: Dict[str, Any],
        other_config: Dict[str, Any] = {},
        start_event = None,
        stop_event = None
    ):
        super(StaticObstacleAgent, self).__init__(
            id=id,
            sim_ctn_name=sim_ctn_name,
            actor_config=actor_config,
            other_config=other_config,
            start_event=start_event,
            stop_event=stop_event,
            remove_after_finished=False
        )
        
    def _initialize(self):
        # other config
        self.output_folder = self.other_config.get('output_folder', None)
        self.debug = self.other_config.get('debug', False)
        
        # convert to config
        self.actor_config_py: StaticObstacleConfig = StaticObstacleConfig.model_validate(self.actor_config)

        if self.output_folder is not None:
            self.debug_folder = os.path.join(self.output_folder, f"debug/{self.prefix}")
            self.logger = self._init_logger()
            
    def _init_logger(self):
        if self.debug:
            os.makedirs(self.debug_folder, exist_ok=True)
            log_file = os.path.join(self.debug_folder, f"{self.prefix}_{self.id}.log")
            logger = get_instance_logger(f"{self.prefix}_{self.id}", log_file)
            logger.info(f"Logger initialized for {self.prefix}_{self.id}")
            return logger
        return None
            
    def _tick(self, snapshot: dict):
        self.sandbox_operator.sim.set_static_location(
            self.id, 
            self.actor_config_py.get_initial_waypoint().model_dump()()
        )