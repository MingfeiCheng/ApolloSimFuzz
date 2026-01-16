from loguru import logger
from typing import List

from scenario_runner.manager import SubScenarioManager

from scenario_elements.agents.static_obstacle import StaticObstacleAgent, StaticObstacleConfig

class SMStaticObstacle(SubScenarioManager[StaticObstacleConfig]):

    name: str = 'openscenario_static_obstacle'

    def __init__(
        self,
        id: str,
        configs: List[StaticObstacleConfig],
        sandbox_container_name: str,
        scenario_dir: str = None,
        terminate_on_failure: bool = False,
        debug: bool = False
    ):
        super(SMStaticObstacle, self).__init__(
            id=id,
            configs=configs,
            sandbox_container_name=sandbox_container_name,
            scenario_dir=scenario_dir,
            terminate_on_failure=terminate_on_failure,
            debug=debug
        )
        
    def _get_agent_config(self, config):
        kwargs = {
            "id": config.id,
            "sim_ctn_name": self.sandbox_container_name,
            "actor_config": config.model_dump(),
            "other_config": {
                "save_root": self.scenario_dir,
                "debug": self.debug
            }
        }
        return kwargs
    
    def _get_agent_cls(self):
        return StaticObstacleAgent