from loguru import logger
from typing import List, Union

from scenario_runner.manager import SubScenarioManager

from scenario_elements.agents.traffic_light import RuleLightAgent, RuleLightConfig, LightConfig

class SMTrafficLight(SubScenarioManager[RuleLightConfig]):

    name: str = 'openscenario_traffic_light'

    def __init__(
        self,
        id: str,
        configs: Union[List[RuleLightConfig], RuleLightConfig],
        sandbox_container_name: str,
        scenario_dir: str = None,
        terminate_on_failure: bool = False,
        debug: bool = False
    ):
        
        if isinstance(configs, RuleLightConfig):
            configs = [configs]
            
        if len(configs) != 1:
            raise ValueError("TrafficLightManager only supports one traffic light config at a time.")
        
        super(SMTrafficLight, self).__init__(
            id=id,
            configs=configs,
            sandbox_container_name=sandbox_container_name,
            scenario_dir=scenario_dir,
            terminate_on_failure=terminate_on_failure,
            debug=debug
        )
        
    def _get_agent_cls(self):
        return RuleLightAgent
    
    def _get_agent_config(self, config):
        kwargs = {
            "id": config.id,
            "sim_ctn_name": self.sandbox_container_name,
            "actor_config": config.model_dump(),
            "other_config": {
                "output_folder": self.scenario_dir,
                "debug": self.debug
            }
        }
        return kwargs
    
    
    def create_actors(self):
        for traffic_light in self.configs[0].lights:
            response = self.sandbox_api.sim.create_signal(
                {
                    "signal_id": traffic_light.id,
                    "signal_type": "signal.traffic_light",
                    "signal_state": "green", # default state
                }
            )
            if not response[0]:
                raise RuntimeError(f"Failed to create actor in the simulator: {response}")
