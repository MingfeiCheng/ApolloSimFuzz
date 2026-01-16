import os
import json
import inspect
import re

from loguru import logger
from typing import Dict
from dataclasses import dataclass, asdict

project_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
# exit(0)

def _resolve_dreamview_port(apollo_root: str) -> int:
    env_port = os.getenv("DREAMVIEW_PORT") or os.getenv("APOLLO_DREAMVIEW_PORT")
    if env_port and env_port.isdigit():
        return int(env_port)

    gflags_path = os.path.join(
        apollo_root, "modules/dreamview/backend/common/dreamview_gflags.cc"
    )
    if os.path.isfile(gflags_path):
        try:
            with open(gflags_path, "r") as f:
                content = f.read()
            match = re.search(
                r'DEFINE_string\(\s*server_ports\s*,\s*"([^"]+)"', content
            )
            if match:
                ports = match.group(1).split(",")
                for port_entry in ports:
                    num_match = re.search(r"\d+", port_entry)
                    if num_match:
                        return int(num_match.group(0))
        except OSError:
            pass

    return 8888

class RunnerConfig:

    # common
    run_tag: str = "default"  # tag for this run # NOTE: better short for convenience
    output_root: str = "" # also used in fuzzing
    max_sim_time: float = 300.0  # seconds, default is
    
    # simulator sandbox
    sandbox_image: str = "drivora/sandbox:latest"  # the docker image name of the apollo simulator sandbox
    sandbox_fps: float = 25.0  # the fps of the simulator sandbox # TODO: check this
    
    # apollo
    apollo_root: str = os.path.join(project_dir, 'apollo')  # the apollo root directory
    dreamview_port: int = _resolve_dreamview_port(apollo_root)
    bridge_port: int = 9090
    
    # fuzzer
    debug: bool = False
    resume: bool = True  # if resume the previous run
    save_record: bool = False
    
    # other details
    map_name: str = "" # NOTE: this is defined in the scenario # TODO: check this variable's usage

    @staticmethod
    def print():
        logger.info("Global Runner Config [Drivora-ApolloSim]:")

        attrs = {
            k: v for k, v in inspect.getmembers(RunnerConfig)
            if not k.startswith("_") and not inspect.isroutine(v)
        }
        max_key_len = max(len(k) for k in attrs.keys())
        for k, v in attrs.items():
            logger.info(f"  {k:<{max_key_len}} : {v}")

###### Your scenario config should inherit from this class ######
@dataclass
class MetaScenarioConfig:
    id: str
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def from_dict(cls, json_node: Dict):
        return cls(**json_node)
    
    def export(self, file_path: str):
        data_info = self.to_dict()
        with open(file_path, 'w') as f:
            json.dump(data_info, f, indent=4)
