import os
import gzip
import time
import copy
import json
import signal
import traceback
import multiprocessing as mp

from abc import ABC
from tqdm import tqdm
from loguru import logger
from threading import Thread
from typing import Dict, Generic, List, Optional, TypeVar

from scenario_elements.criteria.base import CriteriaBase
from scenario_elements.agents.base import AgentBase

from .config import MetaScenarioConfig
from .sandbox_operator import SandboxOperator
from .ctn_manager import ApolloCtnConfig

AgentConfigT = TypeVar("AgentConfigT")  # Generic for scenario config
MScenarioConfigT = TypeVar("MScenarioConfigT", bound=MetaScenarioConfig)

AgentClassT = TypeVar("AgentClassT", bound=AgentBase)
CriteriaClassT = TypeVar("CriteriaClassT", bound=CriteriaBase)

class ScenarioManager(ABC, Generic[MScenarioConfigT]):

    def __init__(
        self,
        config: MScenarioConfigT,
        apollo_ctns: List[ApolloCtnConfig],
        sandbox_container_name: str,
        scenario_dir: str,
        max_time: float = 600, # seconds -> to monitor
        debug: bool = False
    ):
        self.config = config
        self.apollo_ctns = apollo_ctns
        self.sandbox_container_name = sandbox_container_name
        self.scenario_dir = scenario_dir
        self.max_time = max_time
        self.debug = debug

        self.sandbox_api = SandboxOperator(
            container_name=sandbox_container_name
        )

        # observations
        self.running = False
        self.observations = []
        self.threads = []

        self.sub_managers: Dict[str, SubScenarioManager] = {}
        self._create_sub_managers()
        
        # filter None sub managers
        self.sub_managers = {k: v for k, v in self.sub_managers.items() if v is not None}
    
    def _create_sub_managers(self):
        raise NotImplementedError("This method should be implemented in subclass")

    def _initialize_scenario(self):
        for manager_id, manager in self.sub_managers.items():
            logger.info(f"[{manager_id}] Creating actors and agents. {manager}") 
            try: 
                manager.create_actors()
                manager.create_agents()
            except Exception as e:
                logger.error(f"Error initializing sub-manager {manager_id}: {e}")
                traceback.print_exc()
                raise e

    def _terminate(self) -> bool:
        return any(manager.terminate() for manager in self.sub_managers.values())

    def export_result(self, scenario_dir: str):
        
        obs_dir = os.path.join(scenario_dir, 'observations')
        
        if not os.path.exists(obs_dir):
            os.makedirs(obs_dir)
        
        frame_dir = os.path.join(obs_dir, 'frames')
        if not os.path.exists(frame_dir):
            os.makedirs(frame_dir)
        
        for i in tqdm(range(len(self.observations)), desc="Exporting observations"):
            scene_observation = self.observations[i]
            frame = scene_observation['frame']
            file_path = os.path.join(frame_dir, f"{frame}.json")
            with open(file_path, 'w') as f:
                json.dump(scene_observation, f, indent=4)
        
        overview_file = os.path.join(scenario_dir, 'observation.jsonl.gz')
        with gzip.open(overview_file, "wt", encoding="utf-8") as f:
            for record in self.observations:
                f.write(json.dumps(record) + "\n")
                        
        # scenario_observations = {
        #     'scenario_id': self.config.id,
        #     'observations': self.observations,
        # }
        
        # # observation.jsonl.gz
        # overview_file = os.path.join(obs_dir, 'overview.json')
        # with open(overview_file, 'w') as f:
        #     json.dump(scenario_observations, f, indent=4)
            
        # export sub manager results
        criteria_result = {}
        for manager_id, manager in self.sub_managers.items():
            manager_results = manager.get_criteria_results()
            if manager_results is not None:
                criteria_result[manager_id] = manager_results
                
        result_file = os.path.join(scenario_dir, 'result.json')
        with open(result_file, 'w') as f:
            json.dump(criteria_result, f, indent=4)
            
    def run(self):
        
        try:
            self._run()
        except Exception as e:
            logger.error(f"Error during scenario run: {e}")
            traceback.print_exc()
            self.stop()
            return False
        
        return True
            
    def _run(self):
        # 1. reset simulator env
        # 2. create actors in the simulator and corresponding agents
        # 3. start managers, in each agent -> sending ready flag, all ready & our flag -> start
        self.sandbox_api.sim.reset() # send a start flag
        self._initialize_scenario()
        
        # add observation thread
        self.threads.append(
            Thread(target=self.run_observation_collect, daemon=True)
        )
        
        # start managers
        self.running = True
        # start simulator first
        self.sandbox_api.sim.start_scenario()
        # start local managers & threads
        for manager_id, manager in self.sub_managers.items():
            manager.start()
        
        # threads in main manager
        for thread in self.threads:
            thread.start()
            
        bar = tqdm()
        start_time = time.time()
        scenario_started = False
        while not self._terminate():
            # todo: check termination flag
            spend_time = time.time() - start_time
            if spend_time >= self.max_time:
                break

            if not scenario_started:
                scenario_status = self.sandbox_api.sim.get_scenario_status()
                if scenario_status == 'running':
                    scenario_started = True
                time.sleep(0.01)
                continue

            sim_time = self.sandbox_api.sim.get_time()
            bar.set_description(
                f"-> Scenario {self.config.id}: Frame: {sim_time['frame']} Game Time: {sim_time['game_time']:.4f}")
            time.sleep(0.01)
            
        self.stop() # stop simulator & all managers

    def stop(self, signum=None, frame=None):
        
        self.running = False
        # stop local threads
        for thread in self.threads:
            thread.join()
        self.threads = []
        
        # stop sub managers
        for manager_id, manager in self.sub_managers.items():
            manager.stop()
            
        if self.sandbox_api is not None:
            try:
                self.sandbox_api.close()
            except Exception as e:
                logger.warning(f"Error closing traffic API: {e}")

    def run_observation_collect(self):
        # TODO: add timestamp alignment, is better
        scenario_running = False
        start_frame = 0
        last_frame = 0
        local_api = SandboxOperator(
            container_name=self.sandbox_container_name
        )
        while self.running:
            time_info = local_api.sim.get_time()
            if not scenario_running:
                scenario_status = local_api.sim.get_scenario_status()
                if scenario_status == 'running':
                    scenario_running = True
                start_frame = int(time_info['frame'])
                last_frame = start_frame
                time.sleep(0.01)
                continue

            curr_frame = int(time_info['frame']) # 100 hz -> 0.01
            if (curr_frame - start_frame) % 10 == 0 and curr_frame > last_frame:
                scene_observation = {
                    'frame': curr_frame - start_frame,
                    'curr_frame': curr_frame,
                    'start_frame': start_frame,
                    'delta_time': (curr_frame - start_frame) * 0.01,
                    'snapshot': local_api.sim.get_snapshot(),
                    'sub_manager_observations': {
                        manager_id: manager.get_observation() for manager_id, manager in self.sub_managers.items()
                    }
                }
                self.observations.append(copy.deepcopy(scene_observation))
                last_frame = curr_frame
            time.sleep(0.001)
            
        local_api.close()
 
########### some nodes ###########    
class CriteriaWrapper:
    
    def __init__(
        self, 
        sandbox_container_name: str, # shared
        criterias: List[CriteriaClassT]
    ):
        self.sandbox_api = SandboxOperator(
            container_name=sandbox_container_name
        )
        self.criterias = criterias
    
    def tick(self):
        snapshot = self.sandbox_api.sim.get_snapshot()
        if not snapshot.get('scenario_running', False):
            return
        
        # TODO: can improve this by multiple threads
        for criteria in self.criterias:
            criteria.tick(snapshot)
            
    def terminate(self) -> bool:
        return any(criteria.terminate() for criteria in self.criterias)
    
    def get_results(self) -> dict:
        results = {}
        for criteria in self.criterias:
            results[criteria.name] = criteria.st_detail
        return results
    
    def stop(self):
        self.sandbox_api.close()

######### Agent Tools ########
def agent_process_entry(agent_cls, agent_kwargs):
    agent = agent_cls(**agent_kwargs)
    agent.run()

class MPAgentHandle:
    def __init__(self, agent_cls, agent_kwargs):
        self.start_event = mp.Event()
        self.stop_event = mp.Event()

        agent_kwargs = dict(agent_kwargs)
        agent_kwargs["start_event"] = self.start_event
        agent_kwargs["stop_event"] = self.stop_event

        self.proc = mp.Process(
            target=agent_process_entry,
            args=(agent_cls, agent_kwargs),
            daemon=True
        )
        self.proc.start()
        self.pid = self.proc.pid

    def setup_start_signal(self, signal: bool):
        if signal:
            self.start_event.set()

    def setup_stop_signal(self, signal: bool):
        if signal:
            self.stop_event.set()
            self.proc.join(timeout=5)
            if self.proc.is_alive():
                self.proc.terminate()

######### You can implement specific scenarios by subclassing SubScenarioManager #########
class SubScenarioManager(ABC, Generic[AgentConfigT]):
    """
    Abstract base class for sub-scenario managers coordinating NPC/agent behavior and traffic API.
    """

    name: str = "undefined"

    def __init__(
        self,
        id: str,
        configs: List[AgentConfigT],
        sandbox_container_name: str,
        scenario_dir: Optional[str] = None,
        terminate_on_failure: bool = True,
        debug: bool = False
    ):
        self.id = id
        self.configs = configs
        self.sandbox_container_name = sandbox_container_name
        self.scenario_dir = scenario_dir
        self.terminate_on_failure = terminate_on_failure
        self.debug = debug
        
        self.sandbox_api = SandboxOperator(
            container_name=sandbox_container_name
        )

        self.agents: Dict[str, AgentClassT] = {}

        self.running = False
        
        criterias = self.create_criteria()
        if criterias is not None:
            self.criteria = CriteriaWrapper(
                self.sandbox_container_name,
                criterias
            )
        else:
            self.criteria = None
            
        self.threads: List[Thread] = []
        if self.criteria is not None:
            self.threads.append(Thread(target=self._run_criteria, daemon=True))
            
        # sub process managers
        # self.subprocess_pids = mp.Manager().list()
        self.agent_processes = {}

    # ==== Threads ====
    def _run_criteria(self):
        if self.criteria is None:
            return
        
        while self.running:
            self.criteria.tick()
            if self.criteria.terminate():
                self.running = False
                break
            time.sleep(0.01)
            
        self.criteria.stop()

    # ==== Abstract Methods ====
    # NOTE: in sometime, you should wrapper this
    def create_actors(self):
        for actor_config in self.configs:
            logger.info(f"[{actor_config.id}] Creating actor in simulator: {actor_config.model}")
            actor_initial_waypoint = actor_config.get_initial_waypoint()
            
            response = self.sandbox_api.sim.create_actor(
                {
                    "actor_id": actor_config.id,
                    "actor_type": actor_config.model,
                    "x": actor_initial_waypoint.location.x,
                    "y": actor_initial_waypoint.location.y,
                    "z": actor_initial_waypoint.location.z,
                    "heading": actor_initial_waypoint.rotation.yaw
                }
            )
            # logger.debug(f"[{actor_config.id}] Create actor response: {response}")
            if not response[0]:
                raise RuntimeError(f"Failed to create actor in the simulator: {response}")
    
    def create_agents(self):
        for config in self.configs:
            agent_kwargs = self._get_agent_config(config)

            agent = MPAgentHandle(
                agent_cls=self._get_agent_cls(),
                agent_kwargs=agent_kwargs
            )

            self.agents[config.id] = agent
            self.agent_processes[config.id] = agent.proc

    # def create_agents(self):
    #     for config in self.configs:
    #         agent_kwargs = self._get_agent_config(config)
    #         # agent = MPAgentHandle(
    #         #     agent_cls=self._get_agent_cls(),
    #         #     agent_kwargs=dict(
    #         #         id=config.id,
    #         #         sim_ctn_name=self.sandbox_container_name,
    #         #         actor_config=config.to_dict(),
    #         #         other_config={}
    #         #     )
    #         # )
    #         agent = MPAgentHandle(
    #             agent_cls=self._get_agent_cls(),
    #             agent_kwargs=agent_kwargs
    #         )
    #         self.agents[config.id] = agent
    #         self.subprocess_pids.append(agent.pid)
    
    def _get_agent_config(self, config: AgentConfigT) -> dict:
        raise NotImplementedError("This method should be implemented in subclass")
        
    def _get_agent_cls(self):
        raise NotImplementedError("This method should be implemented in subclass")
    
    def create_criteria(self) -> Optional[List[CriteriaClassT]]:
        return None
    
    # ==== Lifecycle ====    
    def start(self):
        self.running = True
        logger.info(f"[{self.name}] Starting SubScenarioManager {self.id}")
        
        # start agents (processes)
        for agent_id, agent in self.agents.items():
            logger.debug(f"[{agent_id}] Sending start event")
            agent.setup_start_signal(True)

        # start local threads if any
        for thread in self.threads:
            logger.debug("Starting thread")
            thread.start()

    def stop(self):
        logger.info(f"[{self.name}] Stopping SubScenarioManager {self.id}")
        self.running = False
        
        # stop agents (processes)
        for agent_id, agent in self.agents.items():
            logger.debug(f"[{agent_id}] Sending stop event")
            agent.setup_stop_signal(True)
            
        # stop local threads if any
        if self.criteria is not None:
            try:
                self.criteria.stop()
            except Exception as e:
                logger.warning(f"Error stopping criteria: {e}")

        for thread in self.threads:
            try:
                thread.join()
            except Exception as e:
                logger.warning(f"Error stopping thread: {e}")
        self.threads = []

        if self.sandbox_api is not None:
            try:
                self.sandbox_api.close()
            except Exception as e:
                logger.warning(f"Error closing traffic API: {e}")
                
        # force kill
        self.cleanup_all_subprocesses()

    # ==== Runtime Helpers ====
    def terminate(self) -> bool:
        return not self.running

    def get_observation(self) -> Optional[dict]:
        return None

    def get_criteria_results(self) -> Optional[dict]:
        if self.criteria is not None:
            return self.criteria.get_results()
        return None
        
    def cleanup_all_subprocesses(self):
        logger.warning(
            f"Stopping {len(self.agent_processes)} agent processes..."
        )

        # 1️⃣ 先发 stop signal（你已经有，非常好）
        for agent in self.agents.values():
            agent.setup_stop_signal(True)

        # 2️⃣ join
        for proc in self.agent_processes.values():
            proc.join(timeout=5)

        # 3️⃣ terminate still-alive
        for proc in self.agent_processes.values():
            if proc.is_alive():
                logger.warning(f"Terminating agent pid={proc.pid}")
                proc.terminate()

        # 4️⃣ 最后兜底 kill（极少发生）
        for proc in self.agent_processes.values():
            if proc.is_alive():
                logger.error(f"Force killing agent pid={proc.pid}")
                os.kill(proc.pid, signal.SIGKILL)

        self.agent_processes.clear()

