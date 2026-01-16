import os
import subprocess
import time
import docker

from typing import Optional
from loguru import logger

from .cyber_bridge import CyberBridge
from .dreamview import Dreamview

# script refer: https://github.com/ApolloAuto/apollo/issues/13353

class ApolloContainerOperator:
    """
    Class to represent Apollo container
    TODO: add running counter to restart to save time
    TODO: add exception handler
    """
    def __init__(
        self,
        name: str,
        modules: list = ['Routing', 'Prediction', 'Planning', 'Control'], # no need routing in v9.0
        map_name: str = 'sunnyvale_big_loop',
        dreamview_port: int = 8888,
        bridge_port: int = 9090
    ) -> None:

        self.user = name
        self.name = name
        # self.name = f"apollo_dev_{self.user}"  # test for name
        # create docker container if it is not exist
        self.hd_map = map_name
        self.APOLLO_MODULES = modules

        self.dreamview = None
        self.dreamview_port = dreamview_port

        self.bridge: Optional[CyberBridge] = None
        self.bridge_port = bridge_port

        self.running_count = 0
        self.start_time = time.time()

    @property
    def host(self) -> str:
        """
        Gets the ip address of the container

        :type: str
        """
        ctn = docker.from_env().containers.get(self.name)
        host = ctn.attrs['NetworkSettings']['IPAddress']
        if host == '':
            return 'localhost'
        return ctn.attrs['NetworkSettings']['IPAddress']

    @property
    def is_container_running(self) -> bool:
        """
        Checks if the container is running

        :returns: True if running, False otherwise
        :rtype: bool
        """
        try:
            return docker.from_env().containers.get(self.name).status == 'running'
        except Exception:
            return False

    @property
    def is_dreamview_running(self) -> bool:
        # 1. check connection
        try:
            if self.dreamview is None:
                return False
            self.dreamview.reconnect()
            return True
        except Exception as e:
            # traceback.print_exc()
            return False

    @property
    def is_modules_running(self) -> bool:
        for module in self.APOLLO_MODULES:
            module_status = self.dreamview.check_module_status(module)
            if not module_status:
                return False
        return True

    @property
    def is_bridge_running(self) -> bool:
        try:
            b = CyberBridge(self.host, self.bridge_port)
            b.conn.close()
            return True
        except Exception as e:
            # traceback.print_exc()
            return False

    ##### Apollo Cyber Bridge #####
    def connect_bridge(self) -> bool:
        """
        Start cyber bridge
        """
        if not self.is_bridge_running:
            for _ in range(10):
                # try 10 times max:
                try:
                    cmd = f"docker exec --user {self.user} -d {self.name} ./scripts/bridge.sh"
                    _ = subprocess.run(cmd, shell=True)
                    self.bridge = CyberBridge(self.host, self.bridge_port)
                    break
                except (ConnectionRefusedError, AssertionError):
                    # traceback.print_exc()
                    time.sleep(1.0)
                    continue
        else:
            self.bridge = CyberBridge(self.host, self.bridge_port)

        if self.bridge is not None:
            logger.info(f'Connected Apollo cyber bridge: {self.host}:{self.bridge_port}')

        return self.is_bridge_running

    ###### Dreamview Operators ######
    def start_dreamview(
        self,
        hd_map,
        dv_mode= 'Mkz Standard Debug', #'Mkz Lgsvl', #'Mkz Standard Debug',
        apollo_type='Mkz_Example' #'Lincoln2017MKZ_LGSVL' #'Mkz_Example'
    ) -> bool:

        try:
            self.dreamview = Dreamview(self.host, self.dreamview_port)
        except Exception as e:
            pass

        if not self.is_dreamview_running:
            for _ in range(10):
                # try 10 times max
                logger.info(
                    f'Start Apollo dreamview: http://{self.host}:{self.dreamview_port} HD_MAP: {hd_map} DV_MODE: {dv_mode} APOLLO_TYPE: {apollo_type}')

                cmd = f"docker exec --user root {self.name} chmod +x /apollo/scripts/bootstrap.sh"
                _ = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                cmd_op = 'restart'
                cmd = f"docker exec --user {self.user} {self.name} ./scripts/bootstrap.sh {cmd_op} --gpu {self.gpu_usage}"
                _ = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    self.dreamview = Dreamview(self.host, self.dreamview_port)
                    self.dreamview.set_hd_map(hd_map)
                    self.dreamview.set_setup_mode(dv_mode)
                    self.dreamview.set_vehicle(apollo_type)
                    break
                except Exception as e:
                    time.sleep(1.0)
                    continue

        return self.is_dreamview_running

    def start_modules_dm(self):
        logger.info(f'Start Apollo modules: {self.APOLLO_MODULES}')
        for dv_m in self.APOLLO_MODULES:
            self.dreamview.enable_module(dv_m, 0.0)
            time.sleep(0.1)

    def disable_modules_dm(self):
        logger.info(f'Disable modules: {self.APOLLO_MODULES}')
        for dv_m in self.APOLLO_MODULES:
            self.dreamview.disable_module(dv_m, 0.0)
            time.sleep(0.1)
            
    def start_modules_script(self):
        """
        Start Apollo modules inside container via start_drivora_modules.sh
        """        
        MODULE_LAUNCHES = [
            "modules/routing/launch/routing.launch",
            "modules/prediction/launch/prediction.launch",
            "modules/planning/launch/planning.launch",
            "modules/control/launch/control.launch",
        ]

        for launch in MODULE_LAUNCHES:
            cmd = (
                f'docker exec --user {self.user} -d {self.name} '
                f'bash -c "'
                f'source /apollo/scripts/apollo_base.sh && '
                f'export CUDA_VISIBLE_DEVICES={self.gpu_usage} '
                f'NVIDIA_VISIBLE_DEVICES={self.gpu_usage} && '
                f'cyber_launch start {launch}'
                f'"'
            )

            subprocess.run(cmd, shell=True)


    def disable_modules_script(self):
        """
        Stop Apollo modules started by start_drivora_modules.sh
        (tag-based, safe termination)
        """
        MODULE_LAUNCHES = [
            "modules/routing/launch/routing.launch",
            "modules/prediction/launch/prediction.launch",
            "modules/planning/launch/planning.launch",
            "modules/control/launch/control.launch",
        ]

        for launch in MODULE_LAUNCHES:
            cmd = (
                f'docker exec --user {self.user} {self.name} '
                f'bash -c "'
                f'source /apollo/scripts/apollo_base.sh && '
                f'cyber_launch stop {launch}'
                f'"'
            )

            subprocess.run(cmd, shell=True)


    ###### Recorder Operators #####
    def start_recorder(self, record_folder: str, record_id: str):
        """
        Starts cyber_recorder
        """
        logger.info(f'Start Apollo recorder: {record_folder}/{record_id}')

        # cmd = f"docker exec --user {self.user} {self.name} rm -rf cyber_recorder.log.INFO*"
        cmd = f"docker exec --user {self.user} {self.name} sh -c 'find /apollo -name \"cyber_recorder.log.INFO.*\" -delete'"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        cmd = f"docker exec --user {self.user} {self.name} rm -rf {record_folder}/{record_id}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        cmd = f"docker exec --user {self.user} {self.name} mkdir -p {record_folder}/{record_id}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        container_cmd_recorder = "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        container_cmd_cmd = f"{container_cmd_recorder} record -o {record_folder}/{record_id}/recording -a &"
        cmd = f"docker exec -d --user {self.user} {self.name} {container_cmd_cmd}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)
        time.sleep(1.0)

    def stop_recorder(self):
        """
        Stops cyber_recorder
        """
        logger.info(f'Stop Apollo recorder.')
        container_cmd = "python3 /apollo/scripts/record_bag.py --stop --stop_signal SIGINT"
        cmd = f"docker exec --user {self.user} {self.name} {container_cmd}"
        # cmd = f"docker exec {self.name} {container_cmd}"
        _ = subprocess.run(cmd, shell=True)
        time.sleep(1.0)

    def copy_record(self, record_folder: str, record_id: str, target_folder: str, delete=False):
        logger.info(f'Copy Apollo record: {self.name}:{record_folder}/{record_id} {target_folder}')
        cmd = f'docker cp {self.name}:{record_folder}/{record_id} {target_folder}'
        _ = subprocess.run(cmd, shell=True)
        if delete:
            cmd = f'docker exec --user {self.user} {self.name} rm -rf {record_folder}/{record_id}'
            # cmd = f'docker exec {self.name} rm -rf {record_folder}/{record_id}'
            _ = subprocess.run(cmd, shell=True)

    ###### Others ######
    def clean_cache(self):
        """
        Removes Apollo's log files to save disk space
        """
        cmd = f"docker exec --user {self.user} {self.name} rm -rf /apollo/data"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} rm -rf /apollo/records"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} sh -c 'find /apollo -name \"*.log.*\" -delete'"
        _ = subprocess.run(cmd, shell=True)
        # create data dir
        cmd = f"docker exec --user {self.user} {self.name} mkdir -p /apollo/data"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} mkdir -p /apollo/data/bag"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} mkdir -p /apollo/data/log"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} mkdir -p /apollo/data/core"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.name} mkdir -p /apollo/records"
        _ = subprocess.run(cmd, shell=True)

    ###### Global ######
    def start(self) -> bool:
        self.start_container()

        # clean logs
        self.clean_cache()

        # logger.debug(f"bridge: {self.bridge}")
        # repeat 5 times in total
        restart_flag = False
        for _ in range(5):

            if restart_flag:
                logger.warning(f'Restart Apollo container: {self.name}:{restart_flag}')
                self.restart_container()

            self.start_bridge()
            # logger.debug(f"bridge: {self.bridge}")
            self.start_dreamview(self.hd_map)

            if (not self.is_bridge_running) or (not self.is_dreamview_running):
                restart_flag = True
            else:
                break

        # only start once if apollo is ok
        # restart  modules
        # must clean all modules first
        self.stop_recorder()
        self.disable_modules_script()
        self.start_modules_script()
        
        self.already_start = True