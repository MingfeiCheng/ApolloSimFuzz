from loguru import logger
from typing import Dict, Tuple
from shapely.geometry import Point, Polygon

from .base import CriteriaBase

class ReachDestinationCriteria(CriteriaBase):
    """Monitor if actors reach their destination and handle termination."""

    name = 'criteria.reach_destination'

    def __init__(
        self, 
        name: str, 
        actor_id: str, 
        actor_config: Dict, 
        threshold_destination: float = 5.0,
        terminate_on_failure: bool = False
    ):
        super(ReachDestinationCriteria, self).__init__(
            name, 
            actor_id,
            actor_config, 
            terminate_on_failure
        )

        # --- Hyperparameters ---
        self._threshold_destination = threshold_destination

        # --- Runtime state ---
        # Waypoint format
        self._actor_destination: Tuple[float, float] = (
            self.actor_config.route[-1].location.x,
            self.actor_config.route[-1].location.y
        )
        
        self._actor_last_position = None
        self._actor_travel_distance = 0.0
        self._actor_reach_dest_states = False

    def _tick_destination(self, snapshot: dict) -> None:
        env_actors = snapshot.get('actors', {})
        time_info = snapshot.get('time', {})
        
        actor_id = self.actor_id 
        actor_info = env_actors[actor_id]
        if not actor_info:
            return

        speed = actor_info['speed']
        location = actor_info['location']
        polygon = Polygon(actor_info['polygon'])
        current_pos = Point(location['x'], location['y'])

        # Update travel distance
        last_pos = self._actor_last_position
        if last_pos is None:
            self._actor_last_position = [location['x'], location['y']]
            return

        last_point = Point(last_pos)
        delta = last_point.distance(current_pos)
        self._actor_travel_distance += delta
        self._actor_last_position = [location['x'], location['y']]

        # Check reach destination
        destination = Point(self._actor_destination)
        dist_to_dest = polygon.distance(destination)

        if dist_to_dest < self._threshold_destination and self._actor_travel_distance > 5.0:
            if not self._actor_reach_dest_states:
                self._actor_reach_dest_states = True
                logger.info(f"[ReachDestination] Actor {actor_id} reached destination.")
                
        self.st_detail = {
            "occurred": self._actor_reach_dest_states,
            "details": {
                "time": time_info,
                "destination": [self._actor_destination[0], self._actor_destination[1]],
                "travel_distance": self._actor_travel_distance,
                "distance_to_destination": dist_to_dest,
                "actor": actor_info
            }
        }

    def _check_termination(self) -> bool:
        return self._actor_reach_dest_states and self.terminate_on_failure
    
    def tick(self, snapshot: dict):
        self._tick_destination(snapshot)
        self._termination = self._check_termination()