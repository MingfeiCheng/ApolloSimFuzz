from registry import ACTOR_REGISTRY
from actor.base import Actor

@ACTOR_REGISTRY.register("signal.traffic_light")
class TrafficLight(Actor):
    # TODO: add time count, use may query the time of the last state change
    # TODO: simplify these attributes

    id: int or str = 0
    # basic information - fixed

    _category: str = 'signal'
    _sub_category: str = 'traffic_light'

    def __init__(
            self,
            id: int or str,
            state: str = "green",
    ):
        # Note that the idx should align with the map id
        super(TrafficLight, self).__init__(id)
        self.state = state
        self.state_time = 0.0

    def json_data(self):
        return {
            "id": self.id,
            "category": self._category,
            "sub_category": self._sub_category,
            "state": self.state,
            "state_time": self.state_time,
        }

    def update_state(self, state: str):
        if self.state != state:
            self.state = state
            self.state_time = 0.0

    def get_state(self):
        return self.state

    def tick(self, delta_time: float):
        self.state_time += delta_time
