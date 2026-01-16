from loguru import logger
from deap import base, creator, tools
from omegaconf import DictConfig

from registry import ENGINE_REGISTRY

from .scenario_sampler.random_sample import RandomSampler
from .feedback.traditional_safety import TraditionalSafetyFeedback
from .oracle.safe_oracle import ScenarioOracle

from .runner_template import FuzzerTemplate
    
@ENGINE_REGISTRY.register("fuzzer.openscenario.random")
class RandomFuzzer(FuzzerTemplate):
    """
    The random fuzzer is:
    """

    def __init__(
        self,
        fuzzer_config: DictConfig,
        scenario_config: DictConfig
    ):
        super(RandomFuzzer, self).__init__(
            fuzzer_config,
            scenario_config
        )
                
        # 1. create a mutator
        # NOTE: fuzzer-specific mutator, if you want to use a different mutator, you can change it here
        self.mutator = RandomSampler(self.scenario_space, self.mutator_config)

        # 3. create the feedback calculator
        # NOTE: fuzzer-specific feedback calculator, if you want to use a different feedback calculator
        self.feedback = TraditionalSafetyFeedback(
            config=self.feedback_config
        )
        
        # 4. create the oracle
        self.oracle = ScenarioOracle(
            config=self.oracle_config
        ) # TODO: implement oracle if needed

    def _setup_deap_pending(self):
        if not hasattr(creator, "FitnessMin"):
            creator.create("FitnessMin", base.Fitness, weights=(-1.0,))  # single-objective minimize
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMin)

    def _run(self, start_time):        
        
        while not self.termination_check(start_time):            
            # sampling
            self.global_search_step += 1
            
            # sample seed
            ind_id = f'g_{self.global_search_step}'
            
            new_seed = self.random_sample_seed()        
            new_seed.set_id(ind_id)
            ind = creator.Individual([new_seed])
            del ind.fitness.values
            
            # execute
            evaluated = self.toolbox.evaluate([ind])
            self.record_logbook(gen=ind_id, pop=evaluated)
            self.save_checkpoint()
            
            expected_now = False
            for ind in evaluated:
                logger.info(f"Ind ID: {ind[0].id}, is_expected: {ind[0].is_expected}, is_ignored: {ind[0].is_ignored}")
                if ind[0].is_expected and not ind[0].is_ignored:
                    expected_now = True
            
            if expected_now:
                logger.success(f"Expected found during global fuzzing epoch.")    