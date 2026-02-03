import os
import subprocess
import time
import docker

from typing import Optional
from loguru import logger

from .cyber_bridge import CyberBridge
from .dreamview import Dreamview

# script refer: https://github.com/ApolloAuto/apollo/issues/13353

class ApolloContainer:
    """
    Class to represent Apollo container
    TODO: add running counter to restart to save time
    TODO: add exception handler
    """
    
    def __init__(
        self,
        name: str,
        modules: list = ['Routing', 'Prediction', 'Planning', 'Control'], # no need routing in v9.0
        gpu: str = '0',
        cpu: str = '24.0',
        apollo_root: str = '/apollo',
        map_name: str = 'sunnyvale_big_loop',
        dreamview_port: int = 8888,
        bridge_port: int = 9090,
        map_dreamview: bool = False
    ) -> None:

        self.APOLLO_MODULES = modules

        # NOTE: Apollo's dev start scripts create a docker container named:
        #   apollo_dev_${USER}
        # In this project, we set USER=<instance_name> when starting containers,
        # so the actual docker container is `apollo_dev_<instance_name>`.
        # Keep `instance_name` for logging, but always use `container_name`
        # for docker API calls / docker exec / docker start.
        self.user = name
        self.instance_name = name
        # Backward-compat: other parts of the codebase expect `.name` to exist.
        # Here `.name` refers to the logical instance name (e.g. "apollo_debug_0"),
        # not the docker container name.
        self.name = self.instance_name
        self.container_name = f"apollo_dev_{self.user}"
        # create docker container if it is not exist
        self.hd_map = map_name
        self.apollo_root = apollo_root
        self.map_dreamview = map_dreamview

        self.dreamview = None
        self.dreamview_port = dreamview_port

        self.bridge: Optional[CyberBridge] = None
        self.bridge_port = bridge_port

        self.cpu_usage = cpu
        self.gpu_usage = gpu

        self.running_count = 0
        self.start_time = time.time()

        # this has created and started a container
        self.create_container()
        # self.start_container()

    @property
    def host(self) -> str:
        """
        Gets the ip address of the container

        :type: str
        """
        ctn = docker.from_env().containers.get(self.container_name)
        ns = ctn.attrs.get("NetworkSettings") or {}
        ip = ns.get("IPAddress")
        if ip:
            return ip
        networks = ns.get("Networks") or {}
        for net in networks.values():
            ip = net.get("IPAddress")
            if ip:
                return ip
        return "localhost"

    @property
    def is_container_running(self) -> bool:
        """
        Checks if the container is running

        :returns: True if running, False otherwise
        :rtype: bool
        """
        try:
            return docker.from_env().containers.get(self.container_name).status == 'running'
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

    ###### Container Operators ######
    def create_container(self):
        client = docker.from_env()
        has_create = False
        try:
            _ = client.containers.get(self.container_name)
            has_create = True
            # logger.debug(f'Apollo instance {self.container_name} already exists')
        except Exception as e:
            pass

        if not has_create:
            logger.info(f'Create Apollo container {self.container_name}')
            # start_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'dev_start_ctn.sh')
            
            start_script_path = os.path.join(self.apollo_root, "docker", "scripts", "dev_start_ctn.sh")
            options = f"-y -l --gpus {str(self.gpu_usage)} --cpus {self.cpu_usage}"
            if self.map_dreamview:
                options += f" -md"
            docker_script_dir = os.path.join(self.apollo_root, "docker", "scripts")
            cmd = f"bash {start_script_path} {options}"
            logger.debug(cmd)
            subprocess.run(
                cmd,
                env={
                    "CURR_DIR": docker_script_dir,
                    "APOLLO_ROOT_DIR": self.apollo_root,
                    "USER": self.user
                },
                shell=True
            )

    def start_container(self):
        # while not self.is_container_running:
        if self.is_container_running:
            logger.debug(f'Apollo container {self.container_name} is already running')
            return True
        
        logger.info(f'Start Apollo container {self.container_name}')
        cmd = f'docker start {self.container_name}'
        _ = subprocess.run(cmd, shell=True)
        time.sleep(0.5)
        self.start_time = time.time()
        
    def restart_container(self):
        """
        Restarts an Apollo container instance
        """
        logger.info(f'Restart Apollo container {self.container_name}')
        cmd = f'docker restart {self.container_name}'
        _ = subprocess.run(cmd, shell=True)
        time.sleep(0.5)
        self.start_time = time.time()

    def stop_container(self):
        """
        Starts an Apollo container instance

        param bool restart: force container to restart
        """
        if self.is_container_running:
            logger.info(f'Stop Apollo container {self.container_name}')
            cmd = f'docker stop {self.container_name}'
            _ = subprocess.run(cmd, shell=True)

    ##### Apollo Cyber Bridge #####
    def start_bridge(self) -> bool:
        """
        Start cyber bridge
        """
        if not self.is_bridge_running:
            for _ in range(10):
                # try 10 times max:
                try:
                    cmd = f"docker exec --user {self.user} -d {self.container_name} ./scripts/bridge.sh"
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

    def stop_bridge(self):
        logger.info(f"Stop Apollo bridge: {self.host}:{self.bridge_port}")
        self.bridge.conn.close()
        self.bridge.stop()

    ###### Dreamview Operators ######
    # def start_dreamview(
    #     self,
    #     hd_map,
    #     dv_mode= 'Mkz Standard Debug', #'Mkz Lgsvl', #'Mkz Standard Debug',
    #     apollo_type='Mkz_Example' #'Lincoln2017MKZ_LGSVL' #'Mkz_Example'
    # ) -> bool:

    #     try:
    #         self.dreamview = Dreamview(self.host, self.dreamview_port)
    #     except Exception as e:
    #         pass

    #     # if not self.is_dreamview_running:
    #     if self.dreamview is None:
    #         for _ in range(10):
    #             # try 10 times max
    #             logger.info(
    #                 f'Start Apollo dreamview: http://{self.host}:{self.dreamview_port} HD_MAP: {hd_map} DV_MODE: {dv_mode} APOLLO_TYPE: {apollo_type}')

    #             cmd = f"docker exec --user root {self.name} chmod +x /scripts/bootstrap.sh"
    #             _ = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    #             cmd_op = 'restart'
    #             cmd = f"docker exec --user {self.user} {self.name} ./scripts/bootstrap.sh {cmd_op} --gpu {self.gpu_usage}"
    #             _ = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    #             try:
    #                 self.dreamview = Dreamview(self.host, self.dreamview_port)
    #                 self.dreamview.set_hd_map(hd_map)
    #                 self.dreamview.set_setup_mode(dv_mode)
    #                 self.dreamview.set_vehicle(apollo_type)
    #                 break
    #             except Exception as e:
    #                 time.sleep(1.0)
    #                 continue
    #     else:
    #         try:
    #             self.dreamview = Dreamview(self.host, self.dreamview_port)
    #             self.dreamview.set_hd_map(hd_map)
    #             self.dreamview.set_setup_mode(dv_mode)
    #             self.dreamview.set_vehicle(apollo_type)
    #         except Exception as e:
    #             time.sleep(1.0)
    def start_dreamview(
        self,
        hd_map,
        dv_mode="Mkz Standard Debug",
        # Must match a folder under /apollo/modules/calibration/data/.
        # In Apollo 7.0 this is `mkz_example` (lowercase) rather than `Mkz_Example`.
        apollo_type="mkz_example",
        max_retry: int = 10,
        retry_interval: float = 1.0,
    ) -> bool:
        logger.info(
            f"Starting Dreamview: http://{self.host}:{self.dreamview_port} "
            f"HD_MAP={hd_map}, DV_MODE={dv_mode}, APOLLO_TYPE={apollo_type}"
        )

        def try_connect() -> bool:
            try:
                self.dreamview = Dreamview(self.host, self.dreamview_port)
                self.dreamview.set_hd_map(hd_map)
                self.dreamview.set_setup_mode(dv_mode)
                self.dreamview.set_vehicle(apollo_type)
                return True
            except Exception as e:
                logger.debug(f"Dreamview not ready yet: {e}")
                self.dreamview = None
                return False

        # 1️⃣ 先尝试直接连接（已经在跑的情况）
        if try_connect():
            logger.info("Dreamview already running and configured.")
            return True

        # 2️⃣ 启动 / 重启 Apollo + Dreamview
        for i in range(max_retry):
            logger.info(f"[{i+1}/{max_retry}] Bootstrapping Apollo Dreamview...")

            # restart dreamview
            cmd = (
                f"docker exec --user {self.user} {self.container_name} "
                f"./scripts/bootstrap.sh restart --gpu {self.gpu_usage}"
            )
            r = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if r.returncode != 0:
                logger.warning(f"bootstrap.sh failed: {r.stderr.decode().strip()}")

            time.sleep(retry_interval)

            if try_connect():
                logger.info("Dreamview started and configured successfully.")
                return True

        # 3️⃣ 最终失败
        logger.error(
            f"Failed to start Dreamview after {max_retry} attempts "
            f"(port={self.dreamview_port})"
        )
        self.dreamview = None
        return False

                

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
                f'docker exec --user {self.user} -d {self.container_name} '
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
                f'docker exec --user {self.user} {self.container_name} '
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
        cmd = f"docker exec --user {self.user} {self.container_name} sh -c 'find /apollo -name \"cyber_recorder.log.INFO.*\" -delete'"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        cmd = f"docker exec --user {self.user} {self.container_name} rm -rf {record_folder}/{record_id}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p {record_folder}/{record_id}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)

        container_cmd_recorder = "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        container_cmd_cmd = f"{container_cmd_recorder} record -o {record_folder}/{record_id}/recording -a &"
        cmd = f"docker exec -d --user {self.user} {self.container_name} {container_cmd_cmd}"
        # logger.debug(cmd)
        _ = subprocess.run(cmd, shell=True)
        time.sleep(1.0)

    def stop_recorder(self):
        """
        Stops cyber_recorder
        """
        logger.info(f'Stop Apollo recorder.')
        container_cmd = "python3 /apollo/scripts/record_bag.py --stop --stop_signal SIGINT"
        cmd = f"docker exec --user {self.user} {self.container_name} {container_cmd}"
        # cmd = f"docker exec {self.name} {container_cmd}"
        _ = subprocess.run(cmd, shell=True)
        time.sleep(1.0)

    def copy_record(self, record_folder: str, record_id: str, target_folder: str, delete=False):
        logger.info(f'Copy Apollo record: {self.container_name}:{record_folder}/{record_id} {target_folder}')
        cmd = f'docker cp {self.container_name}:{record_folder}/{record_id} {target_folder}'
        _ = subprocess.run(cmd, shell=True)
        if delete:
            cmd = f'docker exec --user {self.user} {self.container_name} rm -rf {record_folder}/{record_id}'
            # cmd = f'docker exec {self.name} rm -rf {record_folder}/{record_id}'
            _ = subprocess.run(cmd, shell=True)

    ###### Others ######
    def clean_cache(self):
        """
        Removes Apollo's log files to save disk space
        """
        cmd = f"docker exec --user {self.user} {self.container_name} rm -rf /apollo/data"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} rm -rf /apollo/records"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} sh -c 'find /apollo -name \"*.log.*\" -delete'"
        _ = subprocess.run(cmd, shell=True)
        # create data dir
        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p /apollo/data"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p /apollo/data/bag"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p /apollo/data/log"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p /apollo/data/core"
        _ = subprocess.run(cmd, shell=True)
        cmd = f"docker exec --user {self.user} {self.container_name} mkdir -p /apollo/records"
        _ = subprocess.run(cmd, shell=True)

    ###### Global ######
    def _start_modules_with_retry(
        self,
        timeout: float = 120.0,
        interval: float = 10.0
    ) -> bool:
        logger.info("Starting Apollo modules...")

        self.disable_modules_script()

        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            logger.info(f"Starting modules (attempt {attempt})")

            self.start_modules_script()
            time.sleep(interval)

            if self.is_modules_running:
                logger.info("Apollo modules are running")
                return True

        logger.error("Modules failed to start within timeout")
        return False

    def safe_shutdown(self):
        logger.warning(f"Entering safe shutdown for container: {self.container_name}")
        try:
            self.stop_recorder()
        except Exception:
            pass

        try:
            self.disable_modules_script()
        except Exception:
            pass
        
    def start(self) -> bool:
        logger.info(f"Starting Apollo container: {self.container_name}")

        # 1️⃣ 启动 container
        self.start_container()

        # 2️⃣ 清理 cache
        self.clean_cache()

        # 3️⃣ 启动 Dreamview（轻量 retry）
        if not self.start_dreamview(self.hd_map):
            logger.warning("Dreamview not ready, retrying with container restart...")

            # 4️⃣ container 级别 retry（重操作）
            for i in range(5):
                logger.warning(
                    f"[{i+1}/5] Restart Apollo container due to Dreamview failure: {self.container_name}"
                )
                self.restart_container()
                self.clean_cache()

                if self.start_dreamview(self.hd_map):
                    break
            else:
                # ❗ 最终失败，进入安全状态
                logger.error(f"Dreamview failed after container retries: {self.container_name}")
                self.safe_shutdown()
                raise RuntimeError(
                    f"Dreamview not running after retries: {self.container_name}"
                )

        # 5️⃣ Dreamview OK，开始 modules
        self.stop_recorder()

        if not self.is_modules_running:
            if not self._start_modules_with_retry():
                logger.error("Apollo modules failed to start")
                self.safe_shutdown()
                raise RuntimeError("Apollo modules not running")

        logger.info(f"Apollo container {self.container_name} started successfully")
        return True


    # def start(self) -> bool:
    #     self.start_container()

    #     # clean logs
    #     self.clean_cache()
        
    #     correct_setup_dm = self.start_dreamview(self.hd_map)
        
    #     if not correct_setup_dm:
    #         for _ in range(5):
    #             logger.warning(f'Restart Apollo container: {self.name} due to Dreamview not running')
    #             self.restart_container()
    #             self.clean_cache()
    #             correct_setup_dm = self.start_dreamview(self.hd_map)
    #             if correct_setup_dm:
    #                 break
        
    #     if not correct_setup_dm:
    #         raise RuntimeError(f'Dreamview not running after several retries: {self.name}')
            
    #         # # logger.debug(f"bridge: {self.bridge}")
    #         # # repeat 5 times in total
    #         # restart_flag = False
    #         # for _ in range(5):

    #         #     if restart_flag:
    #         #         logger.warning(f'Restart Apollo container: {self.name}:{restart_flag}')
    #         #         self.restart_container()

    #         #     # self.start_bridge()
    #         #     # logger.debug(f"bridge: {self.bridge}")
    #         #     if not self.is_dreamview_running:
    #         #         restart_flag = True
    #         #     else:
    #         #         break

    #     # only start once if apollo is ok
    #     # restart  modules
    #     # must clean all modules first
    #     self.stop_recorder()
        
    #     # self.disable_modules_script()
    #     if not self.is_modules_running:
    #         start_time = time.time()
    #         self.disable_modules_script()
    #         while time.time() - start_time <120.0:
    #             self.start_modules_script()
    #             time.sleep(10.0)
    #             if self.is_modules_running:
    #                 break
                
    #     # self.start_modules_script()