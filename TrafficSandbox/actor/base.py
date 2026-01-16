from typing import TypeVar

class Actor(object):

    id: int or str = 0 # only support int id
    category: str = 'unknown'

    # control running
    status: str = 'not_ready'

    def __init__(
            self,
            id: int or str,
            **kwargs
    ):
        self.id = id
        self.status = 'not_ready'

    def set_status(self, status: str):
        self.status = status

    def _tick(self, delta_time: float):
        pass

    def tick(self, delta_time: float):
        try:
            self._tick(delta_time)
        except Exception as e:
            raise e

ActorClass = TypeVar("ActorClass", bound=Actor)