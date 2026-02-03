from dataclasses import dataclass
from loguru import logger
from typing import List

from tools.env_tools import get_available_gpus

def create_sandbox_ctn_config(
    run_tag, 
    sandbox_image, 
    sandbox_fps
) -> 'SandboxCtnConfig':
    
    op_cfg = SandboxCtnConfig(
        idx=0,
        container_name=f"sandbox_{run_tag}",
        docker_image=sandbox_image,
        fps=sandbox_fps,
        container_user=None
    )
    return op_cfg

def create_apollo_ctn_configs(
    run_tag, 
    apollo_root, 
    dreamview_port=8888, 
    bridge_port=9090,
    apollo_ctn_num=1,
    use_dreamview=True
) -> List['ApolloCtnConfig']:
    # Detect available GPUs
    available_gpus = get_available_gpus()
    if not available_gpus:
        logger.warning("[WARN] No GPU detected, containers will run on CPU (gpu=None).")
        raise RuntimeWarning("No GPU detected, containers will run on CPU (gpu=None).")

    num_gpus = len(available_gpus)
    logger.info(f"Setting up {apollo_ctn_num} apollo containers for parallel execution with AVAILABLE {num_gpus} GPUs: {available_gpus}")

    operators = []
    for i in range(apollo_ctn_num):
        # If there is only one GPU, assign all containers to it
        if num_gpus == 1:
            gpu_id = available_gpus[0]
        else:
            # With multiple GPUs, assign containers in a round-robin fashion
            gpu_id = available_gpus[i % num_gpus]
            
        map_dreamview = False
        if use_dreamview and i == 0:
            map_dreamview = True  # only map the first container, in case of port conflict # TODO: can be improved

        op_cfg = ApolloCtnConfig(
            idx=i,
            container_name=f"apollo_{run_tag}_{i}",
            gpu=gpu_id,
            cpu='24.0', # TODO: move to config
            apollo_root=apollo_root,
            dreamview_port=dreamview_port,
            bridge_port=bridge_port,
            map_dreamview=map_dreamview
        )
        logger.info(f"Container {op_cfg.container_name} started on GPU {gpu_id}.")
        operators.append(op_cfg)
        
    return operators

@dataclass
class SandboxCtnConfig:
    
    idx: int
    container_name: str
    docker_image: str = 'drivora/apollosim:latest'
    fps: float = 100.0
    container_user: str = None
    
    def to_dict(self):
        return {
            "idx": self.idx,
            "container_name": self.container_name,
            "docker_image": self.docker_image,
            "fps": self.fps,
            "container_user": self.container_user
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'SandboxCtnConfig':
        return cls(
            idx=data.get("idx", 0),
            container_name=data.get("container_name", "default_ctn"),
            docker_image=data.get("docker_image", 'drivora/apollosim:latest'),
            fps=data.get("fps", 100.0),
            container_user=data.get("container_user", None)
        )

@dataclass
class ApolloCtnConfig:
    
    idx: int
    container_name: str
    gpu: str = '0'
    cpu: str = '24.0'
    apollo_root: str = '/apollo'
    dreamview_port: int = 8888
    bridge_port: int = 9090
    map_dreamview: bool = False
    
    def to_dict(self):
        return {
            "idx": self.idx,
            "container_name": self.container_name,
            "gpu": self.gpu,
            "cpu": self.cpu,
            "apollo_root": self.apollo_root,
            "dreamview_port": self.dreamview_port,
            "bridge_port": self.bridge_port,
            "map_dreamview": self.map_dreamview
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'ApolloCtnConfig':
        return cls(
            idx=data.get("idx", 0),
            container_name=data.get("container_name", "default_apollo_ctn"),
            gpu=data.get("gpu", '0'),
            cpu=data.get("cpu", '24.0'),
            apollo_root=data.get("apollo_root", '/apollo'),
            dreamview_port=data.get("dreamview_port", 8888),
            bridge_port=data.get("bridge_port", 9090),
            map_dreamview=data.get("map_dreamview", False)
        )