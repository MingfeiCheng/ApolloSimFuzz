import os
import sys
import hydra

from loguru import logger
from omegaconf import DictConfig, OmegaConf

from scenario_runner.config import RunnerConfig
from registry import ENGINE_REGISTRY
from registry.utils import discover_modules

# some fixed configurations
@hydra.main(config_path='.', config_name='config', version_base=None)
def main(cfg: DictConfig):
    # CUDA_VISIBLE_DEVICES=2,3 python start_fuzzer.py
    fuzzer_dir = cfg.get('fuzzer_dir', None)
    if fuzzer_dir is None:
        raise ValueError("Please provide the fuzzer directory.")
    
    discover_modules(os.path.dirname(os.path.abspath(__file__)), fuzzer_dir)
    
    scenario_config = cfg.get('scenario', None)
    if scenario_config is None:
        raise ValueError("Please provide the scenario config.")
    
    fuzzer_config = cfg.get('tester', None)
    if fuzzer_config is None:
        raise ValueError("Please provide the fuzzer config.")
    
    scenario_type = scenario_config.get('type', None)
    fuzzer_type = fuzzer_config.get('type', None)
    
    # config parameters
    RunnerConfig.use_dreamview = cfg.use_dreamview
    RunnerConfig.apollo_tag = cfg.apollo_tag
    RunnerConfig.run_tag = cfg.run_tag
    RunnerConfig.debug = cfg.debug
    RunnerConfig.resume = cfg.resume
    RunnerConfig.save_record = cfg.save_record
    if cfg.apollo_root.lower() != "default" and os.path.exists(cfg.apollo_root):   
        RunnerConfig.apollo_root = cfg.apollo_root
    RunnerConfig.output_root = os.path.join(cfg.output_root, RunnerConfig.run_tag)
    RunnerConfig.sandbox_image = cfg.sandbox_image
    RunnerConfig.sandbox_fps = cfg.sandbox_fps

    # print global config
    RunnerConfig.print()
    
    output_root = RunnerConfig.output_root
    if not os.path.exists(output_root):
        os.makedirs(output_root)
        logger.info(f"Create output root folder: {output_root}")
        
    if RunnerConfig.debug:
        level = 'DEBUG'
    else:
        level = 'INFO'
    logger.configure(handlers=[{"sink": sys.stderr, "level": level}])
    logger_file = os.path.join(output_root, 'run.log')
    _ = logger.add(logger_file, level=level, mode="a")  # Use mode="a" for append
    
    # save configs
    OmegaConf.save(config=cfg, f=os.path.join(output_root, 'config.yaml'))

    # direct to specific method, such as mr, avfuzzer..
    logger.info(f'Fuzzer type: {scenario_type}.{fuzzer_type}')
    fuzzer_class = ENGINE_REGISTRY.get(f"fuzzer.{scenario_type}.{fuzzer_type}")
    logger.info(f'Load fuzzer class from: {fuzzer_class}')
    
    fuzzer_instance = fuzzer_class(
        fuzzer_config,
        scenario_config
    )
    try:
        if not fuzzer_instance.finish_flag:
            fuzzer_instance.run()
    except KeyboardInterrupt:
        fuzzer_instance.close()
    finally:
        fuzzer_instance.close()

if __name__ == '__main__':
    # CUDA_VISIBLE_DEVICES=2,3 python start_fuzzer.py
    main()
    logger.info('DONE Drivora-ApolloSim @.@!')
    sys.exit(0)