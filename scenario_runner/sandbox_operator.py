import time
import docker
import threading
import subprocess
import zmq
import msgpack_numpy as m
m.patch()

from tinyrpc import RPCClient
from tinyrpc.protocols.msgpackrpc import MSGPACKRPCProtocol as MsgpackRPCProtocol
from tinyrpc.transports.zmq import ZmqClientTransport

from loguru import logger

RECONNECT_INTERVAL = 0.5  # seconds between retries
MAX_RETRIES = 5         # max retries before giving up

REP_PORT = 10667

class SandboxContainer:
    
    # no need gpu, the sandbox is lightweight

    def __init__(
        self, 
        idx: int,
        container_name: str,
        docker_image: str = "",
        fps: float = 100.0,
        container_user=None
    ):
        self.idx = idx
        self.container_name = container_name
        self.docker_image = docker_image
        self.fps = fps
        self.container_user = container_user

        self.container_command = "python /app/app.py"

    @property
    def host(self):
        while not self.is_running:
            self.start()
            time.sleep(1.0)
            
        ctn = docker.from_env().containers.get(self.container_name)
        return ctn.attrs['NetworkSettings']['IPAddress']
    
    @property
    def is_running(self) -> bool:
        """
        Checks if the container is running

        :returns: True if running, False otherwise
        :rtype: bool
        """
        try:
            return docker.from_env().containers.get(self.container_name).status == 'running'
        except:
            return False
        
    def start(self, wait_time=1.0, max_wait=60.0):
        """_summary_
        1. create container:
            docker run -it \
                --name sandbox_debug \
                drivora/sandbox:latest \
                bash

        Args:
            wait_time (float, optional): _description_. Defaults to 1.0.
            max_wait (float, optional): _description_. Defaults to 60.0.

        Raises:
            TimeoutError: _description_
        """
        
        # 1. Start new container
        cmd_parts = [
            f"docker run --name {self.container_name} --rm -d",
        ]
        
        if self.container_user:
            cmd_parts.append(f"--user {self.container_user}")
            
        cmd_parts.append(f"{self.docker_image}")
        cmd_parts.append(f"bash -c \"{self.container_command} --fps {self.fps}\"")  # TODO: change the entry command
        
        cmd = " ".join(cmd_parts)
        
        logger.info(f"Starting container with command: {cmd}")
        subprocess.run(cmd, shell=True)
        
        # Wait for the container to be up
        logger.info("Waiting for container to be in 'running' state...")
        start_time = time.time()
        while True:
            check_cmd = f"docker ps -q -f name=^{self.container_name}$"
            result = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.stdout.strip():
                logger.info(f"Container '{self.container_name}' is now running.")
                break

            if time.time() - start_time > max_wait:
                logger.error(f"Timeout: Container '{self.container_name}' did not start within {max_wait} seconds.")
                raise TimeoutError(f"Container '{self.container_name}' did not start in time.")

            time.sleep(1.0)  # poll every 1 second
        time.sleep(wait_time)
        
    def stop(self):        
         # close the container
        cmd = f"docker stop {self.container_name}"
        process = subprocess.run(cmd, shell=True)
        logger.info('Stop container: {}', self.container_name)
        time.sleep(1.0)
        
    def remove(self):
        logger.warning(f"Removing existing container '{self.container_name}' from environment...")
        cmd = f"docker rm -f {self.container_name}"
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
class SandboxOperator:
    """Unified RPC + container operator with dot-style RPC access."""

    def __init__(self, container_name: str):
        self.container_name = container_name
        self.ctx = None
        self.transport = None
        self.client = None
        self.prefix = ""
        self.one_way = False
        self._send_lock = threading.Lock()

        self.connect()

    # =====================
    # Container utilities
    # =====================
    @property
    def is_running(self) -> bool:
        """Checks if the container is running."""
        try:
            return docker.from_env().containers.get(self.container_name).status == "running"
        except Exception:
            return False

    @property
    def host(self) -> str:
        """Returns container IP address if running."""
        if not self.is_running:
            raise RuntimeError(f"Container {self.container_name} is not running.")
        ctn = docker.from_env().containers.get(self.container_name)
        return ctn.attrs["NetworkSettings"]["IPAddress"]

    # =====================
    # Connection handling
    # =====================
    def connect(self):
        """Connect to sandbox RPC server inside container."""
        self.ctx = zmq.Context()
        address = f"tcp://{self.host}:{REP_PORT}"
        self.transport = ZmqClientTransport.create(self.ctx, address)
        self.client = RPCClient(MsgpackRPCProtocol(), self.transport)
        logger.info(f"[SandboxOperator] Connected to {address}")

    def close(self):
        """Gracefully close RPC and ZMQ connections."""
        try:
            if self.transport and hasattr(self.transport, "socket"):
                try:
                    self.transport.socket.close(linger=0)
                    logger.info(f"[SandboxOperator] Closed RPC transport for {self.container_name}.")
                except Exception as e:
                    logger.warning(f"[SandboxOperator] Failed to close RPC transport: {e}")
                self.transport = None

            if self.ctx:
                try:
                    self.ctx.term()
                    logger.info(f"[SandboxOperator] Terminated ZMQ context for {self.container_name}.")
                except Exception as e:
                    logger.warning(f"[SandboxOperator] Failed to terminate ZMQ context: {e}")
                self.ctx = None

            self.client = None
            logger.info(f"[SandboxOperator] Connection to '{self.container_name}' closed successfully.")
        except Exception as e:
            logger.error(f"[SandboxOperator] Error during close(): {e}")

    # =====================
    # RPC proxying logic (dot-style)
    # =====================
    def __getattr__(self, name):
        """Enable dot-style nested proxy access."""
        new_prefix = f"{self.prefix}.{name}" if self.prefix else name
        new_proxy = SandboxOperator.__new__(SandboxOperator)
        new_proxy.__dict__.update(self.__dict__)  # share same connection context
        new_proxy.prefix = new_prefix
        return new_proxy

    def __call__(self, *args, **kwargs):
        """Trigger remote RPC call."""
        method = self.prefix
        if not method:
            raise AttributeError("No RPC method specified.")
        with self._send_lock:
            # logger.debug(f"[SandboxOperator] Calling RPC method: {method} args={args}, kwargs={kwargs}")
            return self.client.call(method, args, kwargs, one_way=self.one_way)

    # optional context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

