from loguru import logger
from typing import List

from scenario_runner.manager import SubScenarioManager

from scenario_elements.agents.waypoint_vehicle import WaypointVehicleAgent, WaypointVehicleConfig

class SMWaypointVehicle(SubScenarioManager[WaypointVehicleConfig]):
    
    # TODO: add behavior, if the agent stuck too long, remove it?

    name: str = 'openscenario_waypoint_vehicle'

    def __init__(
        self,
        id: str,
        configs: List[WaypointVehicleConfig],
        sandbox_container_name: str,
        scenario_dir: str = None,
        terminate_on_failure: bool = False,
        debug: bool = False
    ):
        super(SMWaypointVehicle, self).__init__(
            id = id,
            configs = configs,
            sandbox_container_name = sandbox_container_name,
            scenario_dir = scenario_dir,
            terminate_on_failure = terminate_on_failure,
            debug = debug
        )
        
    def _get_agent_cls(self):
        return WaypointVehicleAgent
    
    def _get_agent_config(self, config):
        kwargs = {
            "id": config.id,
            "sim_ctn_name": self.sandbox_container_name,
            "actor_config": config.model_dump(),
            "other_config": {
                "output_folder": self.scenario_dir,
                "debug": self.debug
            },
            "remove_after_finished": True
        }
        return kwargs