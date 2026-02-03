import os
import json
import copy
import pickle
import numpy as np

from loguru import logger
from datetime import datetime
from omegaconf import DictConfig
from deap import base, creator, tools

from fuzzer.openscenario.base import Fuzzer, FuzzSeed
from tools.recorder_tool import load_observation, load_runtime_result, visualize_trajectories

from .scenario_sampler.random_sample import RandomSampler
from .feedback.traditional_safety import TraditionalSafetyFeedback
from .oracle.safe_oracle import ScenarioOracle
from .scenario_space import ScenarioODDSpace

def find_ndarrays(obj, path="root"):
    """Recursively find where ndarray appears in a nested dict/list structure."""
    if isinstance(obj, np.ndarray):
        print(f"[FOUND ndarray] at: {path}, shape={obj.shape}, dtype={obj.dtype}")
    
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_ndarrays(v, f"{path}.{k}")
    
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_ndarrays(v, f"{path}[{i}]")
    
    elif isinstance(obj, tuple):
        for i, v in enumerate(obj):
            find_ndarrays(v, f"{path}({i})")
            
class FuzzerTemplate(Fuzzer):
    
    def __init__(
        self, 
        fuzzer_config: DictConfig,
        scenario_config: DictConfig
    ):
        super(FuzzerTemplate, self).__init__(
            fuzzer_config,
            scenario_config
        )
        
        # 1. create scenario space
        self.scenario_space_config = self.pipeline_config['scenario_space']
        self.scenario_space = ScenarioODDSpace(self.scenario_space_config)
        
        # 2. create mutator
        # NOTE: fuzzer-specific mutator, if you want to use a different mutator, you can change it here
        self.mutator = RandomSampler(self.scenario_space, self.mutator_config)

        # 3. create the feedback calculator
        # NOTE: fuzzer-specific feedback calculator, if you want to use a different feedback calculator
        self.feedback = TraditionalSafetyFeedback(self.feedback_config) # 
        
        # 4. create oracle (here is the offline oracle, online shoud defined criteria in feedback calculator)
        self.oracle = ScenarioOracle(self.oracle_config)
        
        # some parameters
        self.global_search_step = 0
        self.initialized = False
        
        self.seed_recorder = []
        self.F_corpus = [] # save all expected corpus
        
        self.logbook = tools.Logbook()
        # we have five, but we only use first three for now
        self.logbook.header = ["gen", "single_score", "multi_score"]
        
        # 8. setup deap toolbox
        self.setup_deap()
        
        # 9. load checkpoint path
        if not self.resume:
            self.time_counter = 0.0
            logger.info("Start from scratch, time counter reset to 0.")                

    def setup_deap(self):
        self.toolbox = base.Toolbox()
        self.toolbox.register("evaluate", self.execute_evaluate)
        self.toolbox.register("re_evaluate", self.re_evaluate_population)
        
        self._setup_deap_pending()
    
    def _setup_deap_pending(self):
        """
        Setup deap for pender fuzzer
        """
        pass
    
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
        
        self._load_checkpoint_pending()
        
    def _load_checkpoint_pending(self):
        """
        Load checkpoint for pender fuzzer
        """
        pass
            
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
        
        self._save_checkpoint_pending()
            
    def _save_checkpoint_pending(self):
        """
        Save checkpoint for pender fuzzer
        """
        pass
    
    def random_sample_seed(self) -> FuzzSeed:
        # this should be in the logical scenario space
        logger.info("Start mutation ...")
        
        # start container first
        sandbox_container_name = self.start_sandbox_container()
              
        sampled_scenario = self.mutator.sample(
            sandbox_container_name=sandbox_container_name
        ) 
        
        return FuzzSeed(
            id="unnamed",
            scenario=sampled_scenario,
            oracle_result={},
            feedback_result={},
            is_expected=False,
            is_ignored=False,
            scenario_dir=None,
            apollo_num=len(sampled_scenario.ego_vehicles)
        )
    
    @staticmethod
    def clone_ind(ind):
        new_seed = copy.deepcopy(ind[0])     # clone scenario
        new_ind = creator.Individual([new_seed])

        # copy fitness (safe)
        if ind.fitness.valid:
            new_ind.fitness.values = ind.fitness.values 

        return new_ind
    
    # abstract method
    def assign_feedback_to_ind(self, ind, feedback_result):
        single_score = feedback_result['single_score']
        ind.fitness.values = (single_score, ) # min is better
        return ind

    def re_evaluate_population(self, individuals: list):
        """
        Evaluate a list of individuals using multiprocessing + container pool.
        Args:
            individuals (list): List of individuals to evaluate.
        Returns:
            list of (individual, fitness_score)
        """
        logger.info(f"Start re-evaluate {len(individuals)} individuals ...")
        
        batch_info = {
            "seed_recorder": []
        }
        for ind_index, ind in enumerate(individuals):
            
            ind_id = ind[0].id
            new_ind_id = f"{ind_id}_reeval"
            ind[0].set_id(new_ind_id)
                
            scenario_dir = ind[0].scenario_dir # NOTE: must exist
            try:
                scenario_observation = load_observation(scenario_dir)
                runtime_oracle_results = load_runtime_result(scenario_dir)
                runtime_oracle_results= runtime_oracle_results["ego"]
                
                oracle_result = self.oracle.evaluate(scenario_observation, runtime_oracle_results)
                                
                # some info can reused in feedback
                feedback_result = self.feedback.evaluate(
                    scenario_observation, 
                    oracle_result,
                    scenario_config=ind[0].scenario
                )
                
            except Exception as e:
                logger.error(f"Error re-evaluating individual {ind[0].id}: {e}")
                import traceback
                traceback.print_exc()
                
                # has error of this execution
                # no update this individual
                feedback_result = self.feedback.get_default_feedback()
                
                oracle_result = {
                    'expected': False,
                    'ignored': True,
                    "runtime_results": "error",
                    "offline_results": {}
                }
                
            seed = ind[0]
            seed.oracle_result = oracle_result
            seed.is_expected = oracle_result['expected']
            seed.is_ignored = oracle_result['ignored']
            seed.feedback_result = feedback_result
            ind[0] = seed
            
            ind = self.assign_feedback_to_ind(ind, feedback_result)
            individuals[ind_index] = ind
            
            # add breif
            batch_info['seed_recorder'].append({
                'id': seed.id,
                'is_expected': seed.is_expected,
                'is_ignored': seed.is_ignored,
                'oracle_result': seed.oracle_result,
                'feedback_result': seed.feedback_result,
            })
            
        self.seed_recorder.extend(batch_info['seed_recorder'])       
        return individuals
    
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
        single_score_list = []
        multi_score_list = [] # list of list of float

        try: 
            # TODO: add more error handling, for example, execution return false with errors
            for ind in pop:
                seed = ind[0]
                fr = seed.feedback_result
                single_score_list.append(fr['single_score'])
                multi_score_list.append(fr['mutliple_scores'])

            self.logbook.record(
                gen=gen,
                single_score=np.mean(single_score_list),
                multi_score=np.mean(np.array(multi_score_list), axis=0).tolist()
            )
        except Exception as e:
            logger.error(f"Error recording logbook for generation {gen}: {e}")
            pass

    def run(self):
        if self.resume:
            self.load_checkpoint()
            
        start_time = datetime.now()
        self._run(start_time)

    def _run(self, start_time: datetime):
        """
        The main run loop of the fuzzer.
        """
        raise NotImplementedError("This is an abstract class method.")
            