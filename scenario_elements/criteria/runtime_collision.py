from loguru import logger
from typing import Dict
from shapely.geometry import Polygon

from .base import CriteriaBase

class CollisionCriteria(CriteriaBase):
    """Monitor collision events and optionally terminate simulation."""

    def __init__(
        self, 
        name: str, 
        actor_id: str, 
        actor_config: dict, 
        terminate_on_failure: bool = True
    ):
        super(CollisionCriteria, self).__init__(
            name, 
            actor_id, 
            actor_config, 
            terminate_on_failure
        )

        # Load configs
        self._threshold_collision = 0.01

    def _tick_collision(self, snapshot: dict) -> None:
        """
        Check if any pair of actors are colliding (polygon overlap or near).
        """
        time_info = snapshot.get('time', {})
        env_actors = snapshot.get('actors', {})

        ego_id = self.actor_id
        ego_info = env_actors[ego_id]
        
        if not ego_info:
            return

        ego_poly = Polygon(ego_info['polygon'])

        for other_id, other_info in env_actors.items():
            if ego_id == other_id:
                continue

            other_poly = Polygon(other_info['polygon'])
            distance = ego_poly.distance(other_poly)

            if distance <= self._threshold_collision:
                # Simple heuristic for distinguishing ADS vs static actor
                ads_collision = int(other_id) < 1000  # optional: move this logic to a utility func

                self.st_detail = {
                    "occurred": True,
                    "details": {
                        "time": time_info,
                        "ads_collision": ads_collision,
                        "actor": ego_info,
                        "other_actor": other_info
                    }
                }
                
                logger.warning(f"[Collision] Actor {ego_id} collided with {other_id} at time {time_info}")

    def _check_termination(self) -> bool:
        """Determine whether simulation should be terminated due to collision."""
        return self.st_detail["occurred"] and self.terminate_on_failure
    
    def tick(self, snapshot: dict) -> None:
        self._tick_collision(snapshot)
        self._termination = self._check_termination()