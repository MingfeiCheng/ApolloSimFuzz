import os

from loguru import logger
from typing import List, Optional

from apollo_bridge.instances.base_apollo import ApolloConfig, ApolloAgent

from scenario_runner.manager import SubScenarioManager
from scenario_runner.ctn_manager import ApolloCtnConfig

# from scenario_elements.criteria import CollisionCriteria, ReachDestinationCriteria, StuckCriteria
from scenario_elements.criteria import RuntimeSingleTest, RuntimeGroupTest

class SMEgo(SubScenarioManager[ApolloConfig]):

    name = 'openscenario_ego'

    def __init__(
        self,
        id: str,
        configs: List[ApolloConfig],
        apollo_ctns: List[ApolloCtnConfig],
        map_name: str,
        sandbox_container_name: str,
        scenario_dir: Optional[str] = None,
        terminate_on_failure: bool = True,
        debug: bool = False
    ):
        if len(configs) != len(apollo_ctns):
            raise ValueError(f"Number of Apollo configs ({len(configs)}) must match number of Apollo containers ({len(apollo_ctns)})")
                
        self.map_name = map_name        
        # ctn mapper
        self.ctn_mapper = {}
        for cfg, ctn in zip(configs, apollo_ctns):
            self.ctn_mapper[cfg.id] = ctn
        
        super(SMEgo, self).__init__(
            id=id,
            configs=configs,
            sandbox_container_name=sandbox_container_name,
            scenario_dir=scenario_dir,
            terminate_on_failure=terminate_on_failure,
            debug=debug
        )
    
    def _get_agent_cls(self):
        return ApolloAgent
    
    def _get_agent_config(self, config: ApolloConfig) -> dict:
        kwargs = {
            'id': config.id,
            'sim_ctn_name': self.sandbox_container_name,
            'actor_config': config.model_dump(),
            'other_config': {
                "scenario_id": os.path.basename(self.scenario_dir) if self.scenario_dir else "default",
                "save_root": self.scenario_dir,
                "apollo_container_name": self.ctn_mapper[config.id].container_name,
                "apollo_root": self.ctn_mapper[config.id].apollo_root,
                "map_name": self.map_name,
                "cpu": self.ctn_mapper[config.id].cpu,
                "gpu": self.ctn_mapper[config.id].gpu,
                "dreamview_port": self.ctn_mapper[config.id].dreamview_port,
                "bridge_port": self.ctn_mapper[config.id].bridge_port,
                "map_dreamview": self.ctn_mapper[config.id].map_dreamview, # only the first ego will setup the main dreamview
                "debug": self.debug,
            }
        }
        return kwargs
    
    def create_criteria(self):
        single_criterias = []
        
        for ego_cfg in self.configs:
            criteria = RuntimeSingleTest(
                name=f"single_criteria_{ego_cfg.id}",
                actor_id=ego_cfg.id,
                actor_config=ego_cfg,
                threshold_destination=5.0,
                threshold_stuck=200.0,
                threshold_speed=0.05,
                terminate_on_failure=self.terminate_on_failure
            )
            single_criterias.append(criteria)
        
        if len(single_criterias) == 1:
            return single_criterias
        else:
            group_criteria = RuntimeGroupTest(
                name=f"group_criteria",
                detectors=single_criterias,
                terminate_on_failure=self.terminate_on_failure
            )
            return [group_criteria]
    
    
        # # TODO: start when scenario start
        # # collision criteria
        # collision_criteria = CollisionCriteria({
        #     "actor_configs": self.configs,
        #     "threshold_collision": 0.1,
        #     "terminate_on_failure": True,
        # })
        
        # # reach destination criteria
        # reach_destination_criteria = ReachDestinationCriteria({
        #     "actor_configs": self.configs,
        #     "terminate_on_failure": True,
        #     "threshold_destination": 5.0,
        # })
        
        # # stuck criteria
        # stuck_criteria = StuckCriteria({
        #     "actor_configs": self.configs,
        #     "threshold_stuck": 200.0,
        #     "threshold_speed": 0.05,
        #     "terminate_on_failure": True,
        # })
        
        # return [collision_criteria, reach_destination_criteria, stuck_criteria]