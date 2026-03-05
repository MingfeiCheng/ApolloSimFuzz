import os
import json
import copy
import shutil
import signal
import pickle
import numpy as np
import multiprocessing as mp

from loguru import logger
from typing import Dict, Any, Tuple
from datetime import datetime
from omegaconf import DictConfig, OmegaConf
from deap import base, creator, tools
from dataclasses import dataclass, field, asdict, fields

from registry import ENGINE_REGISTRY

from scenario_corpus.openscenario.config import ScenarioConfig
from scenario_runner.config import RunnerConfig
from scenario_runner.sandbox_operator import SandboxContainer
from scenario_runner.ctn_manager import create_sandbox_ctn_config, create_apollo_ctn_configs
from scenario_corpus.openscenario.openscenario_executor import run_scenario

from tools.recorder_tool import load_observation, load_runtime_result, visualize_trajectories

from .scenario_sampler import RandomSampler
from .feedback import TraditionalSafetyFeedback
from .oracle.safe_oracle import SafeOracle
from .scenario_space import ScenarioODDSpace

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
    
@ENGINE_REGISTRY.register("fuzzer.random")
class RandomFuzzer:
    
    def __init__(
        self,
        fuzzer_config: DictConfig,
        scenario_config: DictConfig
    ):
        self.finish_flag = False
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
        
        # 0. create container manager
        self.sandbox_ctn_cfg = create_sandbox_ctn_config(
            run_tag=RunnerConfig.run_tag,
            sandbox_image=RunnerConfig.sandbox_image,
            sandbox_fps=RunnerConfig.sandbox_fps,
        )
        
        # 1. create scenario space
        self.scenario_space_config = self.pipeline_config['scenario_space']
        self.scenario_space = ScenarioODDSpace(self.scenario_space_config)
        
        
        # 2. mutation 
        self.mutator_config = self.pipeline_config.get('mutator', {})
        self.mutator = RandomSampler(self.scenario_space, self.mutator_config)
        
        # 3. create the feedback calculator
        # NOTE: fuzzer-specific feedback calculator, if you want to use a different feedback calculator
        self.feedback_config = self.pipeline_config.get('feedback', {})
        self.feedback = TraditionalSafetyFeedback(self.feedback_config) # No need in random
        
        # 4. create oracle (here is the offline oracle, online shoud defined criteria in feedback calculator)
        self.oracle_config = self.pipeline_config.get('oracle', {})
        self.oracle = SafeOracle(self.oracle_config)
        
        # other parameters
        self.used_time = 0.0
        
        # 5. setup toolbox
        self.toolbox = None
        
        # 6. for eval processes
        self.subprocess_pids = mp.Manager().list()
        
        # some parameters
        self.global_search_step = 0
        self.initialized = False
        
        self.seed_recorder = []
        self.F_corpus = [] # save all expected corpus
        
        self.logbook = tools.Logbook()
        # we have five, but we only use first three for now
        self.logbook.header = ["gen", "fitnesses"]
        
        # 8. setup deap toolbox
        self.setup_deap()
        
        # 9. load checkpoint path
        if not self.resume:
            self.time_counter = 0.0
            logger.info("Start from scratch, time counter reset to 0.")    
    
    def setup_deap(self):
        self.toolbox = base.Toolbox()
        self.toolbox.register("evaluate", self.execute_evaluate)
        
        if not hasattr(creator, "FitnessMin"):
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))  # single-objective minimize -> diff min
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMin)
        
    def load_checkpoint(self):
        if os.path.exists(self.checkpoint_path):
            with open(self.checkpoint_path, 'rb') as f:
                checkpoint_data = pickle.load(f)
            
            # parameters
            self.global_search_step = checkpoint_data['global_search_step']
            self.initialized = checkpoint_data['initialized']
            
            self.seed_recorder = checkpoint_data['seed_recorder']
            self.F_corpus = checkpoint_data['F_corpus']
            
            # load logbook
            logbook_file = os.path.join(self.output_root, "logbook.json")
            if os.path.exists(logbook_file):
                with open(logbook_file, 'r') as f:
                    log_data = json.load(f)
                    for entry in log_data:
                        self.logbook.record(**entry)
                        
            logger.info('Load checkpoint from {}', self.checkpoint_path)
        else:
            logger.warning('Checkpoint file not found, start from scratch.')
    
    def save_checkpoint(self):
        """
        Save checkpoint
        """
        checkpoint_data = {
            "global_search_step": self.global_search_step,
            "initialized": self.initialized,
            "seed_recorder": self.seed_recorder,
            "F_corpus": self.F_corpus
        }
        with open(self.checkpoint_path, 'wb') as f:
            pickle.dump(checkpoint_data, f)            
        logger.info('Save checkpoint to {}', self.checkpoint_path)
        
        # save a result overview
        overview_res = {
            'summary': {
                'F_size': len(self.F_corpus),
                'time_budget_hours': self.time_budget,
                'time_used_hours': self.used_time / 3600.0,
                'F_corpus': self.F_corpus
            },
            'details': {
            }
        }
        
        for seed_brief in self.seed_recorder:
            overview_item_detail = {
                'scenario_id': seed_brief['id'],
                'is_expected': seed_brief['is_expected'],
                'is_ignored': seed_brief['is_ignored'],
                'oracle_result': seed_brief['oracle_result'],
                # 'feedback_result': seed_brief['feedback_result'],
            }
            overview_res['details'][seed_brief['id']] = overview_item_detail
        
        # logger.debug(f"Overview res: {overview_res}")
        overview_res_file = os.path.join(self.output_root, 'overview.json')
        with open(overview_res_file, 'w') as f:
            json.dump(overview_res, f, indent=4)
            
        # save lookbook
        with open(os.path.join(self.output_root, "logbook.json"), 'w') as f:
            json.dump(self.logbook, f, indent=2, default=str)

    @staticmethod
    def clone_ind(ind):
        new_seed = copy.deepcopy(ind[0])     # clone scenario
        new_ind = creator.Individual([new_seed])

        # copy fitness (safe)
        if ind.fitness.valid:
            new_ind.fitness.values = ind.fitness.values 

        return new_ind
    # fitnesses    
    def get_seed_fitness(self, seed: FuzzSeed):
        
        oracle_result = seed.oracle_result
        if oracle_result.get("is_ignored", False):
            return 0.0 # best fitness for expected scenario
        
        feedback_result = seed.feedback_result
        f_collision = feedback_result.get('collision_feedback', 0.0)
        
        return f_collision
    
    def assign_feedback_to_ind(self, ind):
        fitness_score = self.get_seed_fitness(ind[0])
        ind.fitness.values = (fitness_score, ) # min is better
        return ind
   
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
            self.finish_flag = True
            return True
        
        if self.time_budget is None:
            logger.info(f"Note that you set [Infinite] testing budget.")
        
        self.finish_flag = False
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
    
    def execute_evaluate(self, individuals: list):
        """
        Evaluate a list of individuals using multiprocessing + container pool.
        Args:
            individuals (list): List of individuals to evaluate.
        Returns:
            list of (individual, fitness_score)
        """
        # Run execution in parallel (container + scenario simulation)        
        batch_info = {
            "seed_recorder": [],
            "F_corpus": [],
        }        
        for ind_index in range(len(individuals)):
            
            exec_res = self.execute_individual(
                individuals[ind_index][0]
            )
            # Evaluate oracle and feedback on the produced scenario
            
            scenario_exec_status = exec_res['status']
            scenario_dir = exec_res['scenario_dir']
            
            scenario_config = individuals[ind_index][0].scenario
                   
            if not scenario_exec_status:
                # has error of this execution
                # no update this individual
                feedback_result = self.feedback.get_default_feedback()
                
                oracle_result = {
                    'expected': False,
                    'ignored': True,
                    "runtime_results": "error",
                    "offline_results": {}
                }
                
                scenario_observation = []
                
            else:
            
                visualize_trajectories(scenario_dir)
                
                scenario_observation = load_observation(scenario_dir)
                runtime_oracle_results = load_runtime_result(scenario_dir)
                runtime_oracle_results= runtime_oracle_results["ego"]
                
                oracle_result = self.oracle.evaluate(scenario_observation, runtime_oracle_results)
                            
            # some info can reused in feedback
            feedback_result = self.feedback.evaluate(
                scenario_observation, 
                oracle_result,
                scenario_config=scenario_config
            )
            
            seed = individuals[ind_index][0]
            seed.oracle_result = oracle_result
            seed.is_expected = oracle_result['expected']
            seed.is_ignored = oracle_result['ignored']
            seed.feedback_result = feedback_result
            seed.set_scenario_dir(scenario_dir)
            individuals[ind_index][0] = seed            
            individuals[ind_index] = self.assign_feedback_to_ind(individuals[ind_index], feedback_result)
            
            # add breif
            batch_info['seed_recorder'].append({
                'id': seed.id,
                'is_expected': seed.is_expected,
                'is_ignored': seed.is_ignored,
                'oracle_result': seed.oracle_result,
                'feedback_result': seed.feedback_result,
            })
            
            # add to F corpus
            if seed.is_expected and (not seed.is_ignored):
                batch_info['F_corpus'].append({
                    'id': seed.id,
                    'is_expected': seed.is_expected,
                    'is_ignored': seed.is_ignored,
                    'oracle_result': seed.oracle_result,
                    # 'feedback_result': seed.feedback_result,
                })

        self.seed_recorder.extend(batch_info['seed_recorder'])
        self.F_corpus.extend(batch_info['F_corpus'])
        self.save_checkpoint()
        return individuals
    
    def record_logbook(self, gen, pop):

        fitness_lst = []

        for ind in pop:
            if not ind.fitness.valid:
                continue
            fitness_lst.append(ind.fitness.values)

        if len(fitness_lst) == 0:
            mean_fitness = [float('inf')]
        else:
            fitness_array = np.array(fitness_lst)
            mean_fitness = np.mean(fitness_array, axis=0)

            if np.isscalar(mean_fitness):
                mean_fitness = [float(mean_fitness)]
            else:
                mean_fitness = mean_fitness.tolist()

        self.logbook.record(
            gen=gen,
            fitnesses=mean_fitness,
        )
        
    # scenario sample
    def scenario_sample(self) -> FuzzSeed:
        logger.info(f"Start random sampling ...")
        sandbox_container_name = self.start_sandbox_container()
        self.mutator.reset(sandbox_container_name)
              
        sampled_scenario = self.mutator.sample()
        self.mutator.close()
        
        return FuzzSeed(
            id="unnamed",
            scenario=sampled_scenario,
            oracle_result={},
            feedback_result={},
            is_expected=False,
            is_ignored=False
        )
        
    def run(self):
        if self.resume:
            self.load_checkpoint()
            
        start_time = datetime.now()    
        
        while not self.termination_check(start_time):            
            # sampling
            self.global_search_step += 1
            
            # sample seed
            ind_id = f'g_{self.global_search_step}'
            
            new_seed = self.scenario_sample()        
            new_seed.set_id(ind_id)
            ind = creator.Individual([new_seed])
            del ind.fitness.values
            
            # execute
            evaluated = self.toolbox.evaluate([ind])
            self.record_logbook(gen=ind_id, pop=evaluated)
            self.save_checkpoint()
            
            for ind in evaluated:
                logger.info(f"Ind ID: {ind[0].id}, is_expected: {ind[0].is_expected}, is_ignored: {ind[0].is_ignored}")
                if ind[0].is_expected and not ind[0].is_ignored:
                    logger.success(f"Expected scenario found: {ind[0].id}")
        
