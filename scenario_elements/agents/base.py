import time
import traceback

from loguru import logger
from abc import ABC, abstractmethod
from typing import Any, Dict

from scenario_runner.sandbox_operator import SandboxOperator

class AgentBase(ABC):
    """
    Base class for all agents, run in a multiprocessing subprocess.
    """
    
    running_frequency: float = 50.0

    def __init__(
        self,
        id: str,
        sim_ctn_name: str,
        actor_config: Dict[str, Any],
        other_config: Dict[str, Any] = {},
        start_event = None,
        stop_event = None,
        remove_after_finished: bool = True
    ):
        self.id = str(id)

        # IPC signals
        self.start_event = start_event
        self.stop_event = stop_event

        self.sandbox_operator = SandboxOperator(
            container_name=sim_ctn_name
        )
        self.actor_config = actor_config
        self.other_config = other_config
        self.remove_after_finished = remove_after_finished
        
        # some default parameters
        self.logger = None
        self.task_finished = False
        
        self._initialize()

        # notify simulator ready
        self.sandbox_operator.sim.set_actor_status(self.id, "ready")

    def _initialize(self):
        pass

    # ===== IPC hooks =====
    def setup_start_signal(self, signal: bool):
        if signal:
            self.start_event.set()

    def setup_stop_signal(self, signal: bool):
        if signal:
            self.stop_event.set()

    # ===== Main loop =====
    def run(self):
        """
        Blocking loop. Called inside subprocess.
        """
        while not self.start_event.is_set():
            time.sleep(0.01)
            if self.stop_event.is_set():
                self.sandbox_operator.close()
                return
            
        last_time = 0.0
        while not self.stop_event.is_set():
            try:
                snapshot = self.sandbox_operator.sim.get_snapshot()
                # logger.debug(f"actor ids: {snapshot['actors'].keys()}")
                timestamp = snapshot['time']['game_time']
                if timestamp > last_time:
                    last_time = timestamp
                    self._tick(snapshot)
                
                if self.task_finished and self.remove_after_finished:
                    break
                                
            except Exception as e:
                logger.error(f"Agent '{self.id}' encountered an error during tick: {e}")
                logger.error(traceback.print_exc())
                if self.logger:
                    self.logger.exception(f"Agent '{self.id}' encountered an error during tick: {e}")
            
            time.sleep(1 / self.running_frequency)      
        
        if self.remove_after_finished:
            try:
                # NOTE: here is the fixed time
                time.sleep(5.0)
                self.sandbox_operator.sim.remove_actor(self.id)
            except Exception as e:
                # logger.error(f"Error removing actor '{self.id}': {e}")
                pass
        
        self.sandbox_operator.close()  
        
    @abstractmethod
    def _tick(self, snapshot: Dict):
        """
        One control / decision step.
        """
        pass
    