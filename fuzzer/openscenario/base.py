import os
import json
import shutil
import signal
import multiprocessing as mp

from loguru import logger
from typing import Dict, Any, Tuple
from datetime import datetime
from omegaconf import DictConfig, OmegaConf
from dataclasses import dataclass, field, asdict, fields

from scenario_corpus.openscenario.config import ScenarioConfig
from scenario_runner.config import RunnerConfig
from scenario_runner.sandbox_operator import SandboxContainer
from scenario_runner.ctn_manager import create_sandbox_ctn_config, create_apollo_ctn_configs
from scenario_corpus.openscenario.openscenario_executor import run_scenario

@dataclass
class FuzzSeed:
    """Data container for fuzzing seeds."""
    
    id: str
    scenario: ScenarioConfig
    oracle_result: Dict[str, Any] = field(default_factory=dict)
    feedback_result: Dict[str, Any] = field(default_factory=dict)
    is_expected: bool = False
    is_ignored: bool = False
    scenario_dir: str = ""
    apollo_num: int = 1

    def set_id(self, new_id: str):
        self.id = new_id
        self.scenario.id = new_id

    def set_scenario_dir(self, scenario_dir: str):
        self.scenario_dir = scenario_dir
        
    def get_apollo_num(self) -> int:
        if self.scenario:
            return len(self.scenario.ego_vehicles)
        else:
            raise ValueError("Scenario is not defined in the seed.")

    @classmethod
    def load_from_scenario_file(cls, config_path: str) -> "FuzzSeed":
        """Load the initial seed from the given path"""
        with open(config_path, 'r') as f:
            data = json.load(f)
        scenario = ScenarioConfig.model_validate(data)
        return cls(
            id="init_seed",
            scenario=scenario,
        )

    @classmethod
    def load_from_dict(cls, data: dict) -> "FuzzSeed":
        """Load instance from dict, compatible with subclasses."""
        init_args = {}
        for f in fields(cls):
            if f.name == "scenario":
                init_args["scenario"] = ScenarioConfig.model_validate(data["scenario"])
            else:
                init_args[f.name] = data.get(f.name, getattr(cls, f.name, None))
        return cls(**init_args)

    def to_dict(self) -> dict:
        """Convert seed to serializable dict (safe for JSON)."""
        result = asdict(self)
        result["scenario"] = self.scenario.model_dump()
        return result
    
    def to_deap_args(self) -> dict:
        """Convert seed to DEAP-compatible args (no nested dataclasses)."""
        result = asdict(self)
        result["scenario"] = self.scenario
        return result
    
class Fuzzer(object):
    
    def __init__(
        self,
        fuzzer_config: DictConfig,
        scenario_config: DictConfig
    ):
        self.fuzzer_config = fuzzer_config
        self.scenario_config = scenario_config
        
        self.resume = RunnerConfig.resume
        self.output_root = RunnerConfig.output_root
        
        # result dir
        self.result_folder = os.path.join(self.output_root, 'results')
        if not os.path.exists(self.result_folder):
            os.makedirs(self.result_folder)
            
        # tmp dir
        self.tmp_dir = os.path.join(self.output_root, 'tmp') # save some temporary files
        if not os.path.exists(self.tmp_dir):
            os.makedirs(self.tmp_dir)
        self.checkpoint_path = os.path.join(self.tmp_dir, 'checkpoint.pkl')
        
        # save cfgs
        fuzzer_config_path = os.path.join(self.output_root, 'fuzzer_config.yaml')
        OmegaConf.save(config=fuzzer_config, f=fuzzer_config_path)
        logger.info('Fuzzer config saved to {}', fuzzer_config_path)
        
        # basic fuzzer config
        self.time_budget = fuzzer_config.get('time_budget', 1.0)  # in hours        
        # basic scenario config
        self.seed_path = self.scenario_config.get('seed_path', None)
        # if self.seed_path is None or not os.path.isfile(self.seed_path):
        #     logger.error(f"Please provide a valid seed scenario path: {self.seed_path}")
        #     raise ValueError("Invalid seed scenario path.")
        
        # check time counter & load previous time, before execution, we check if we have already finished the testing
        self.time_counter_file = os.path.join(self.tmp_dir, 'time_counter.txt')
        self.time_counter = 0.0
        if os.path.exists(self.time_counter_file):
            with open(self.time_counter_file, 'r') as f:
                line = f.readline()
                if line:
                    self.time_counter = float(line.rstrip())
                    
        if self.termination_check(datetime.now()):
            logger.info(f"Already tested for {self.time_budget} hours, skip.")
            return
        
        # Load detailed configs
        fuzzer_config_path = fuzzer_config.get('config_path', None)
        if fuzzer_config_path is None or not os.path.isfile(fuzzer_config_path):
            logger.error(f"Please provide a valid fuzzer config path: {fuzzer_config_path}")
            raise ValueError("Invalid fuzzer config path.")
        
        self.pipeline_config = OmegaConf.load(fuzzer_config_path)
        
        # 1. create container manager
        self.sandbox_ctn_cfg = create_sandbox_ctn_config(
            run_tag=RunnerConfig.run_tag,
            sandbox_image=RunnerConfig.sandbox_image,
            sandbox_fps=RunnerConfig.sandbox_fps,
        )
        
        # 2. mutation 
        self.mutator_config = self.pipeline_config.get('mutator', {})

        # 3. create the feedback calculator
        # NOTE: fuzzer-specific feedback calculator, if you want to use a different feedback calculator
        self.feedback_config = self.pipeline_config.get('feedback', {})
        
        # 4. create oracle (here is the offline oracle, online shoud defined criteria in feedback calculator)
        self.oracle_config = self.pipeline_config.get('oracle', {})
        
        # other parameters
        self.used_time = 0.0
        
        # 5. setup toolbox
        self.toolbox = None
        
        # 6. for eval processes
        self.subprocess_pids = mp.Manager().list()
    
    def load_checkpoint(self):
        pass
    
    def save_checkpoint(self):
        pass

    def run(self):
        if self.resume:
            self.load_checkpoint()
            
        start_time = datetime.now()
        self._run(start_time)
        
    def _run(self, start_time):
        raise NotImplementedError("Method _run not implemented")
    
    def close(
        self
    ):
        """
        Close the fuzzer, such as closing the database connection, etc.
        """
        self.cleanup_all_subprocesses()
    
    def kill_process_tree(self, pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            pass
        
    def cleanup_all_subprocesses(self):
        logger.warning(f"Killing {len(self.subprocess_pids)} subprocesses...")

        for pid in list(self.subprocess_pids):
            self.kill_process_tree(pid)

        self.subprocess_pids[:] = []

    def termination_check(self, start_time) -> bool:
        curr_time = datetime.now()
        t_delta = (curr_time - start_time).total_seconds()
        self.used_time = t_delta + self.time_counter
        # update total time
        with open(self.time_counter_file, 'w') as f:
            f.write(str(self.used_time))
            f.write('\n')
            
        if (self.time_budget is not None) and self.used_time / 3600.0 > self.time_budget:
            return True
        
        if self.time_budget is None:
            logger.info(f"Note that you set [Infinite] testing budget.")
            
        return False
    
    def start_sandbox_container(self) -> str:
        """
        Start the sandbox container and return the container name.
        """
        logger.info("Starting the sandbox container...")
        ctn_container = SandboxContainer(
            idx=self.sandbox_ctn_cfg.idx,
            container_name=self.sandbox_ctn_cfg.container_name,
            docker_image=self.sandbox_ctn_cfg.docker_image,
            fps=self.sandbox_ctn_cfg.fps,
            container_user=self.sandbox_ctn_cfg.container_user
        ) 
        # remove first and create new one for clean state
        ctn_container.stop()
        ctn_container.start()
        return ctn_container.container_name
    
    def execute_individual(
        self,
        ind: FuzzSeed
    ) -> Dict:
        
        # ==========================================================
        # Step 1: Prepare directory
        # ==========================================================
        # scenario_dir = ind.scenario_dir
        scenario_dir = os.path.join(self.result_folder, f"{ind.id}")
        if os.path.exists(scenario_dir):
            shutil.rmtree(scenario_dir)
            
        scenario_config = ind.scenario

        os.makedirs(scenario_dir, exist_ok=True)
        logger.info(f"[Worker {os.getpid()}] Created scenario folder: {scenario_dir}")

        scenario_json_path = os.path.join(scenario_dir, "scenario.json")
        ctn_json_path = os.path.join(scenario_dir, "ctn_config.json")

        # Write configs
        with open(scenario_json_path, "w") as f:
            json.dump(scenario_config.model_dump(), f, indent=4)

        with open(ctn_json_path, "w") as f:
            json.dump(self.sandbox_ctn_cfg.to_dict(), f, indent=4)

        # TODO: assign Apollo CTN Configs
        # ego_num
        ego_num = len(scenario_config.ego_vehicles)
        apollo_ctns = create_apollo_ctn_configs(
            run_tag=RunnerConfig.run_tag,
            apollo_root=RunnerConfig.apollo_root,
            dreamview_port=RunnerConfig.dreamview_port,
            bridge_port=RunnerConfig.bridge_port,
            apollo_ctn_num=ego_num
        )
        
        # start sandbox container
        sandbox_container_name = self.start_sandbox_container()
        
        run_status = run_scenario(
            scenario_config=scenario_config,
            sandbox_container_name=sandbox_container_name,
            apollo_ctns=apollo_ctns,
            scenario_dir=scenario_dir,
            max_sim_time=RunnerConfig.max_sim_time,
            debug=RunnerConfig.debug
        )
        
        exec_res = {
            "status": run_status,
            "scenario_dir": scenario_dir,
            "apollo_num": ego_num
        }
        
        return exec_res