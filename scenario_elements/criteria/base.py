from abc import ABC, abstractmethod

class CriteriaBase(ABC):
    """
    Base class for runtime criterias/oracles, run in subprocesses.
    """
    
    def __init__(
        self, 
        name: str,
        actor_id: str,
        actor_config: dict,
        terminate_on_failure: bool = True
    ):
        self.name = name
        self.actor_id = actor_id
        self.actor_config = actor_config
        self.terminate_on_failure = terminate_on_failure
        
        # internal items
        self._termination = False
        self.st_detail = {
            "occurred": False,
            "details": {}
        }

    @abstractmethod
    def tick(self, snapshot: dict):
        pass

    def terminate(self):
        return self._termination
    
    def stop(self):
        pass
    
    def event_occurred(self) -> bool:
        return self.st_detail["occurred"]
    