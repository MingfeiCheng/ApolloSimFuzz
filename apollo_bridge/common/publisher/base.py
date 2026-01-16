import traceback

from ..cyber_bridge import CyberBridge
from loguru import logger

class Publisher(object):

    channel: str = '/default'
    msg_type: str = 'default'
    msg_cls: any = None

    def __init__(self, idx, bridge: CyberBridge):
        self.idx = idx
        self.bridge = bridge
        self.frame_count = 0
        self._register()

    def _register(self):
        self.bridge.add_publisher(
            self.channel,
            self.msg_type
        )

    def _process_data(self, message):
        raise NotImplementedError("This method should be implemented by the subclass")

    def publish(self, message):

        try:
            process_data = self._process_data(message)
        except Exception as e:
            logger.warning(f"Publisher {self.channel} tick failed: {e}")
            traceback.print_exc()
            return

        if process_data is not None:
            try:
                self.bridge.publish(self.channel, process_data.SerializeToString())
                self.frame_count += 1
            except Exception as e:
                logger.warning(f"Publisher {self.channel} tick failed: {e}")
                traceback.print_exc()
                return
