from loguru import logger
from typing import List

from .container import ApolloContainer
from registry import PUBLISHER_REGISTRY, SUBSCRIBER_REGISTRY

class ApolloMessenger:
    """
    Class to manage and communicate with an Apollo instance/container
    """

    def __init__(
        self,
        idx: int,
        apollo_modules: List[str],
        publishers: List[str], # only provide names
        subscribers: List[str], # only provide names
        container_name: str = None,
        gpu: str = '0',
        cpu: float = 24.0,
        apollo_root: str = '/apollo',
        map_name: str = 'sunnyvale_big_loop',
        dreamview_port: int = 8888,
        bridge_port: int = 9090,
        map_dreamview: bool = False,
    ):
        self.idx = idx
        self.publishers = publishers
        self.subscribers = subscribers
        self.container_name = container_name

        self.publisher_pool = dict()
        self.subscriber_pool = dict()

        self.container = ApolloContainer(
            self.container_name,
            modules=apollo_modules,
            gpu=gpu,
            cpu=cpu,
            apollo_root=apollo_root,
            map_name=map_name,
            dreamview_port=dreamview_port,
            bridge_port=bridge_port,
            map_dreamview=map_dreamview
        )

        # start container & register publishers/subscribers
        # self.container.start()
        self.container.start_bridge()
        
        self.clean_cache()
        self.register_publishers()
        self.register_subscribers()
        self.container.bridge.spin()

    def clean_cache(self):
        self.container.clean_cache()

    def shutdown(self):
        self.container.stop_bridge()
        # self.container.stop_container()
        self.publisher_pool.clear()
        self.subscriber_pool.clear()

    def register_publishers(self):
        """
        Register publishers for the cyberRT communication
        """
        for p_name in self.publishers:
            if p_name in self.publisher_pool:
                logger.error(f"Publisher {p_name} already exists")
                raise RuntimeError(f"Publisher {p_name} already exists")
            publisher_class = PUBLISHER_REGISTRY.get(p_name)
            self.publisher_pool[p_name] = publisher_class(
                idx = p_name,
                bridge = self.container.bridge
            )
        logger.info(f"Registered publisher: {self.publishers}")

    def register_subscribers(self):
        """
        Define user-defined subscribers
        :return:
        """
        for s_name in self.subscribers:
            if s_name in self.subscriber_pool:
                logger.error(f"Subscriber {s_name} already exists")
                raise RuntimeError(f"Subscriber {s_name} already exists")
            subscriber_class = SUBSCRIBER_REGISTRY.get(s_name)
            self.subscriber_pool[s_name] = subscriber_class(
                idx = s_name,
                bridge = self.container.bridge
            )
        logger.info(f"Registered subscriber: {self.subscribers}")

    ######### publish data #########
    def publish_message(self, name: str, message: any):
        try:
            self.publisher_pool[name].publish(message)
        except Exception as e:
            logger.warning(f"Error publishing message: {e}")

    ######### Other Tools #########
    def recorder_operator(self, operation, record_folder=None, scenario_id=None):
        if operation == 'start':
            self.container.start_recorder(record_folder, scenario_id)
        elif operation == 'stop':
            self.container.stop_recorder()
        else:
            raise RuntimeError(f"Not supported operation: {operation}")

    def move_recording(self, record_folder: str, scenario_id: str, local_folder: str, delete: bool = True):
        self.container.copy_record(
            record_folder=record_folder,
            record_id=scenario_id,
            target_folder=local_folder,
            delete=delete
        )