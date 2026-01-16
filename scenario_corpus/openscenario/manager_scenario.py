from loguru import logger
from typing import Optional, List

from registry import MANAGER_REGISTRY
from scenario_runner.manager import ScenarioManager
from scenario_runner.ctn_manager import ApolloCtnConfig

from .config import ScenarioConfig
from .sm_ego import SMEgo
from .sm_waypoint_vehicle import SMWaypointVehicle
from .sm_waypoint_walker import SMWaypointWalker
from .sm_static_obstacle import SMStaticObstacle
from .sm_traffic_light import SMTrafficLight

class OpenScenarioManager(ScenarioManager[ScenarioConfig]):

    def __init__(
        self,
        config: ScenarioConfig,
        apollo_ctns: List[ApolloCtnConfig],
        sandbox_container_name: Optional[str] = None,
        scenario_dir: Optional[str] = None,
        max_time: float = 600,
        debug: bool = False
    ):
        super(OpenScenarioManager, self).__init__(
            config=config,
            apollo_ctns=apollo_ctns,
            sandbox_container_name=sandbox_container_name,
            scenario_dir=scenario_dir,
            max_time=max_time,
            debug=debug
        )

    def _create_sub_managers(self):
        self.sub_managers["ego"] = SMEgo(
            id="ego",
            configs=self.config.ego_vehicles,
            apollo_ctns=self.apollo_ctns,
            map_name=self.config.get_map_name(),
            sandbox_container_name=self.sandbox_container_name,
            scenario_dir=self.scenario_dir,
            terminate_on_failure=True,
            debug=self.debug
        )

        self.sub_managers["npc_vehicle"] = SMWaypointVehicle(
            id="npc_vehicle",
            configs=self.config.npc_vehicles,
            sandbox_container_name=self.sandbox_container_name,
            scenario_dir=self.scenario_dir,
            terminate_on_failure=False,
            debug=self.debug
        )

        self.sub_managers["npc_walker"] = SMWaypointWalker(
            id="npc_walker",
            configs=self.config.npc_walkers,
            sandbox_container_name=self.sandbox_container_name,
            scenario_dir=self.scenario_dir,
            terminate_on_failure=False,
            debug=self.debug
        )
        
        self.sub_managers["npc_static"] = SMStaticObstacle(
            id="npc_static",
            configs=self.config.npc_statics,
            sandbox_container_name=self.sandbox_container_name,
            scenario_dir=self.scenario_dir,
            terminate_on_failure=False,
            debug=self.debug
        )

        self.sub_managers["traffic_light"] = SMTrafficLight(
            id="traffic_light",
            configs=self.config.traffic_light,
            sandbox_container_name=self.sandbox_container_name,
            scenario_dir=self.scenario_dir,
            terminate_on_failure=False,
            debug=self.debug
        )
