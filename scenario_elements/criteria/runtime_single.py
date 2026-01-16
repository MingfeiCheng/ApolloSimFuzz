from loguru import logger

from .base import CriteriaBase
from .runtime_collision import CollisionCriteria
from .runtime_destination import ReachDestinationCriteria
from .runtime_stuck import StuckCriteria

class RuntimeSingleTest(CriteriaBase):
    
    """
    Immediate stop:
    1. Collision -> Failure
    Wait for others:
    1. Stuck -> Success
    2. Reach the destination -> Success
    
    We need an attribute to note the failures
    event:
    {
        "id": "vehicle.id",
        "collision": {
            "occurred": True/False,
            "details": "detailed info"
        },
        "stuck": {
            "occurred": True/False,
            "details": "detailed info"
        },
        "reach_destination": {
            "occurred": True/False,
            "details": "detailed info"
        }
    }
    """
    
    def __init__(
        self, 
        name: str,
        actor_id: str,
        actor_config: dict,
        threshold_stuck: float = 10.0,
        threshold_speed: float = 0.05,
        threshold_destination: float = 5.0,
        terminate_on_failure: bool = True,
    ):
        super(RuntimeSingleTest, self).__init__(name, actor_id, actor_config, terminate_on_failure)
        
        # hyperparameters
        self.threshold_stuck = threshold_stuck
        self.threshold_speed = threshold_speed
        self.threshold_destination = threshold_destination
        
        # inner parameters
        self.st_detail = {
            "id": self.actor_id, # TODO: check the observation saver!!!!!, we use actor id here
            "collision": {
                "occurred": False,
                "details": {}
            },
            "stuck": {
                "occurred": False,
                "details": {}
            },
            "reach_destination": {
                "occurred": False,
                "details": {}
            }
        }
        
        
        self.events = []
        self.actor_destination = (
            self.actor_config.route[-1].location.x,
            self.actor_config.route[-1].location.y
        )
        
        self.success_value = 1 # this defines the success value of the criterion, expected to be 1
        self.actual_value = 0 # this is the actual value of the criterion, updated during the update phase
        self.already_terminate = False
        
        # create sub-criteria
        self.collision_test = CollisionCriteria(
            name=f"{self.actor_id}_collision",
            actor_id=self.actor_id,
            actor_config=self.actor_config,
            terminate_on_failure=self.terminate_on_failure
        )
        self.stuck_test = StuckCriteria(
            name=f"{self.actor_id}_stuck",
            actor_id=self.actor_id,
            actor_config=self.actor_config,
            threshold_stuck=self.threshold_stuck,
            threshold_speed=self.threshold_speed,
            terminate_on_failure=self.terminate_on_failure
        )
        
        self.reach_destination_test = ReachDestinationCriteria(
            name=f"{self.actor_id}_reach_destination",
            actor_id=self.actor_id,
            actor_config=self.actor_config,
            threshold_destination=self.threshold_destination,
            terminate_on_failure=self.terminate_on_failure,
        )
            
    def get_stop(self) -> bool:
        return self.already_terminate
        # return self.st_detail["collision"]["occurred"] or self.st_detail["stuck"]["occurred"] or self.st_detail["reach_destination"]["occurred"]
        
    def tick(self, snapshot):
        
        # check whether to terminate
        if self.already_terminate:
            self._termination = True
            return
        
        env_actors = snapshot.get('actors', {})
        time_info = snapshot.get('time', {})
        
        actor_id = self.actor_id 
        actor_info = env_actors[actor_id]
        if not actor_info:
            return
        
        self.collision_test.tick(snapshot)
        self.stuck_test.tick(snapshot)
        self.reach_destination_test.tick(snapshot)
        
        self.st_detail["collision"] = self.collision_test.st_detail
        self.st_detail["stuck"] = self.stuck_test.st_detail
        self.st_detail["reach_destination"] = self.reach_destination_test.st_detail
        
        if self.st_detail["reach_destination"]["occurred"]:
            self.already_terminate = True
            logger.success(f"Vehicle {self.actor_id} has reached its destination.")
                
        if self.st_detail["collision"]["occurred"]:
            self.already_terminate = True
            logger.error(f"Vehicle {self.actor_id} has a collision.")            
                
        if self.st_detail["stuck"]["occurred"]:
            # check the distance to the route destination
            # route: route.append((wp.transform, connection))
            self.already_terminate = True
            
            location = actor_info['location']
            curr_loca = [location['x'], location['y']]
            dist2dest = ((curr_loca[0] - self.actor_destination[0]) ** 2 + (curr_loca[1] - self.actor_destination[1]) ** 2) ** 0.5
            if dist2dest < 5.0:
                logger.success(f"Vehicle {self.actor_id} has reached its destination.")
            else:
                logger.error(f"Vehicle {self.actor_id} is stuck.")
                