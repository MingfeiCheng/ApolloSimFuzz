from loguru import logger
from typing import Dict

from .base import CriteriaBase

class StuckCriteria(CriteriaBase):
    """Monitor whether any actor is stuck for too long."""

    name = 'criteria.stuck'

    def __init__(
        self,
        name: str,
        actor_id: str,
        actor_config: Dict,
        threshold_stuck: float = 10.0,
        threshold_speed: float = 0.05,
        terminate_on_failure: bool = True
    ):
        super(StuckCriteria, self).__init__(name, actor_id, actor_config, terminate_on_failure)

        self._threshold_stuck = threshold_stuck
        self._threshold_speed = threshold_speed

        self._last_move_timer = 0.0
        self._event_added = False
        self._max_stuck_time = 0.0

    def _tick_stuck(self, snapshot: dict) -> None:
        """Check whether any actor is stuck beyond the threshold time."""

        if not snapshot.get('scenario_running', False):
            current_time = snapshot['time']['game_time']
            self._last_move_timer = current_time
            return

        time_info = snapshot.get('time', {})
        current_time = snapshot['time']['game_time']
        env_actors = snapshot.get('actors', {})

        actor_id = self.actor_id
        actor_trigger_time = getattr(self.actor_config, 'trigger_time', 0.0)

        # Skip early trigger
        if current_time <= actor_trigger_time:
            self._last_move_timer = current_time
            return

        actor_info = env_actors[actor_id]
        if not actor_info:
            return

        speed = actor_info['speed']
        
        # Check if actor is moving
        if speed <= self._threshold_speed:
            stuck_time = current_time - self._last_move_timer
        else:
            stuck_time = 0.0
            self._last_move_timer = current_time
        
        if stuck_time > self._max_stuck_time:
            self._max_stuck_time = stuck_time
            
            stuck_occurred = False
            if self._max_stuck_time >= self._threshold_stuck:
                stuck_occurred = True
            
            self.st_detail = {
                "occurred": stuck_occurred,
                "details": {
                    "time": time_info,
                    "id": actor_id,
                    "max_blocked_duration": self._max_stuck_time,
                    "actor": actor_info
                }
            }
            
            if stuck_occurred:
                self._event_added = True
                # logger.warning(f"[Stuck] Actor {actor_id} stuck for {self._max_stuck_time:.2f}s")

    def _check_termination(self) -> bool:
        """Determine whether simulation should be terminated due to stuck."""
        return self.st_detail["occurred"] and self.terminate_on_failure

    def tick(self, snapshot) -> None:
        self._tick_stuck(snapshot)
        self._termination = self._check_termination()