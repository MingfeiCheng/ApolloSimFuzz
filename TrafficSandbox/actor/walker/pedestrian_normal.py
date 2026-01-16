from registry import ACTOR_REGISTRY
from .base import WalkerActor, BoundingBox, Location

@ACTOR_REGISTRY.register("walker.pedestrian.normal")
class PedestrianNormal(WalkerActor):

    category = "walker.pedestrian.normal"
    _bbox = BoundingBox(
        length=0.5,
        width=0.5,
        height=1.8,
    )

    _max_acceleration = 10.0
    _max_deceleration = 10.0

    def __init__(self, id: int, location: Location):
        super(PedestrianNormal, self).__init__(id, location)

