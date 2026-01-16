import os
import time
import json

from loguru import logger
from typing import TypeVar, List

from scenario_runner.ctn_manager import ApolloCtnConfig
from scenario_runner.sandbox_operator import SandboxOperator
from apollo_bridge.common.container import ApolloContainer

from .config import ScenarioConfig
from .manager_scenario import OpenScenarioManager


def run_scenario(
    scenario_config: ScenarioConfig,
    sandbox_container_name: str,
    apollo_ctns: List[ApolloCtnConfig],
    scenario_dir: str = None,
    max_sim_time: float = 300, # seconds
    debug: bool = False
):
    """
    TODO: update this structure
    Execute the scenario based on the specification
    |_scenario
        |- scenario_idx
            |- scenario.json
            |- records_simulator.pkl
            |- simulation_result.json
            |- records_apollo (folder)
            |- debug (folder)
    """
    # convert to ApolloCtnConfig
    # apollo_ctns = [ApolloCtnConfig.from_dict(ctn) for ctn in apollo_ctns]
    
    if not os.path.exists(scenario_dir):
        os.makedirs(scenario_dir)
        logger.info(f'--> Create scenario folder: {scenario_dir}')

    # 1. save scenario file
    with open(os.path.join(scenario_dir, 'scenario.json'), "w") as f:
        json.dump(scenario_config.model_dump(), f, indent=4)
        
    # 2. check apollo containers & create containers
    map_name = scenario_config.get_map_name()
    apollo_ctn_instances = []
    for apollo_ctn_cfg in apollo_ctns:
        logger.debug(f'--> Start Apollo Container: {apollo_ctn_cfg.container_name} (TOTAL: {len(apollo_ctns)}) on GPU {apollo_ctn_cfg.gpu} Map Dreamview: {apollo_ctn_cfg.map_dreamview}')
        apollo_ctn = ApolloContainer(
            name=apollo_ctn_cfg.container_name,
            gpu=apollo_ctn_cfg.gpu,
            cpu=float(apollo_ctn_cfg.cpu),
            apollo_root=apollo_ctn_cfg.apollo_root,
            dreamview_port=apollo_ctn_cfg.dreamview_port,
            bridge_port=apollo_ctn_cfg.bridge_port,
            map_dreamview=apollo_ctn_cfg.map_dreamview,
            map_name=map_name,
        )
        apollo_ctn.create_container()
        apollo_ctn.start()
        apollo_ctn.clean_cache()
        
        apollo_ctn_instances.append(apollo_ctn)
        
    # 2.1 load town in simulator
    sandbox_api = SandboxOperator(
        container_name=sandbox_container_name
    )
    sandbox_api.load_map(
        map_name
    )
    sandbox_api.close()

    # 3. build scenario
    scenario_manager = OpenScenarioManager(
        config=scenario_config,
        apollo_ctns=apollo_ctns,
        sandbox_container_name=sandbox_container_name,
        scenario_dir=scenario_dir,
        max_time=max_sim_time,
        debug=debug,
    )
    
    # 4. run all components
    m_start_time = time.time()
    run_status = scenario_manager.run()
    m_end_time = time.time()
    simulation_spend_time = m_end_time - m_start_time
    logger.info('--> [Simulation Time] Simulation Spend Time (seconds): [=]{}[=]', simulation_spend_time)
    
    # 5. export related things
    scenario_manager.export_result(scenario_dir)
    logger.info(f'--> Simulation result saved to: {scenario_dir}')
    
    # 6. stop all apollo containers
    for apollo_ctn in apollo_ctn_instances:
        logger.debug(f'--> Stop Apollo Container: {apollo_ctn.name}')
        # apollo_ctn.stop_bridge()
        # apollo_ctn.stop_container()
    
    return run_status # TRUE or FALSE