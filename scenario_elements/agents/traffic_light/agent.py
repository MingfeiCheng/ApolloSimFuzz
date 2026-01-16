import os
import ray
import time
import random

from typing import List, Dict, Any

from tools.logger_tools import get_instance_logger
from scenario_elements.agents.base import AgentBase

from .config import LightConfig, RuleLightConfig

class RuleLightAgent(AgentBase):
    
    prefix = 'rule_light'
    running_frequency: float = 50.0

    def __init__(
        self, 
        id: str,
        sim_ctn_name: str,
        actor_config: dict,
        other_config: dict = {},    
        start_event = None,
        stop_event = None
    ):
        super(RuleLightAgent, self).__init__(
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
        
        # agent config
        self.actor_config_py: RuleLightConfig = RuleLightConfig.model_validate(self.actor_config)
        self.lights: List[LightConfig] = self.actor_config_py.lights
        self.green_time = self.actor_config_py.green_time
        self.yellow_time = self.actor_config_py.yellow_time
        self.red_time = self.actor_config_py.red_time
        self.force_green = self.actor_config_py.force_green
        self.random_seed = self.actor_config_py.initial_seed

        if self.output_folder is not None:
            self._init_logger()
            
        self._init_state()
        
        self.initialize_traffic_lights()

    def _init_logger(self):
        self.debug_folder = os.path.join(self.output_folder, f"debug/{self.prefix}")
        self.logger = None
        if self.debug:
            os.makedirs(self.debug_folder, exist_ok=True)
            log_file = os.path.join(self.debug_folder, f"{self.prefix}.log")
            if os.path.exists(log_file):
                os.remove(log_file)
            self.logger = get_instance_logger(f"{self.prefix}", log_file)
            self.logger.info(f"Logger initialized for {self.prefix}")

    def _init_state(self):
        self.local_random = random.Random(self.random_seed)
        self.local_random.shuffle(self.lights)
        self.light_count: Dict[str, int] = {light.id: 0 for light in self.lights}

    def initialize_traffic_lights(self):
        if self.force_green:
            for light in self.lights:
                self.sandbox_operator.sim.set_signal_state(light.id, "green")
                self._log(f"Set traffic light {light.id} to GREEN (forced)")
            return

        complete = set()
        for light in self.lights:
            if light.id in complete:
                continue

            self.sandbox_operator.sim.set_signal_state(light.id, "green")
            self.light_count[light.id] = 1
            complete.add(light.id)
            self._log(f"Set traffic light {light.id} to GREEN")

            for conflict in light.conflicts:
                if conflict not in complete:
                    self.sandbox_operator.sim.set_signal_state(conflict, "red")
                    complete.add(conflict)
                    self._log(f"Set traffic light {conflict} (conflict) to RED")

            for eq in light.equals:
                if eq not in complete:
                    self.sandbox_operator.sim.set_signal_state(eq, "green")
                    self.light_count[eq] = 1
                    complete.add(eq)
                    self._log(f"Set traffic light {eq} (equals) to GREEN")

    def _tick(self, snapshot: dict) -> List[dict]:
        if self.force_green:
            return []

        complete = set()
        game_time = snapshot['time']['game_time']

        for light in self.lights:
            lid = light.id
            if lid in complete:
                continue

            light_info = self.sandbox_operator.sim.get_signal(lid)
            state = light_info['state']
            elapsed = light_info['state_time']

            self._log(f"[{lid}] State: {state}, Elapsed: {elapsed:.2f}, Game Time: {game_time:.2f}")

            if state == 'green' and elapsed >= self.green_time:
                self.sandbox_operator.sim.set_signal_state(lid, "yellow")
                self._log(f"Traffic light {lid} transitioned GREEN → YELLOW")

            elif state == 'yellow' and elapsed >= self.yellow_time:
                self.sandbox_operator.sim.set_signal_state(lid, "red")
                self._log(f"Traffic light {lid} transitioned YELLOW → RED")

            elif state == 'red' and elapsed >= self.red_time:
                if self.light_count[lid] == 0 and self._conflict_clear(light):
                    self._turn_green_with_equals(light)
                    self._reset_loop_flags(light)
                else:
                    self._log(f"Traffic light {lid} remains RED (conflicts or already green)")

            complete.add(lid)

        return []

    def _conflict_clear(self, light: LightConfig) -> bool:
        for conflict in light.conflicts:
            info = self.sandbox_operator.sim.get_signal(conflict)
            if info['state'] in {'green', 'yellow'}:
                return False
        return True

    def _turn_green_with_equals(self, light: LightConfig):
        self.sandbox_operator.sim.set_signal_state(light.id, "green")
        self.light_count[light.id] = 1
        self._log(f"Traffic light {light.id} transitioned RED → GREEN")

        for eq_id in light.equals:
            self.sandbox_operator.sim.set_signal_state(eq_id, "green")
            self.light_count[eq_id] = 1
            self._log(f"Traffic light {eq_id} transitioned RED → GREEN (equals)")

    def _reset_loop_flags(self, light: LightConfig):
        should_reset = all(
            self.light_count.get(cid, 0) == 1 for cid in light.conflicts
        )
        if should_reset:
            self.light_count[light.id] = 0
            for cid in light.conflicts:
                self.light_count[cid] = 0
            for eq_id in light.equals:
                self.light_count[eq_id] = 0
            self._log(f"Reset loop flags for {light.id} and its conflicts/equals")

    def _log(self, message: str):
        if self.debug and self.logger:
            self.logger.info(message)
