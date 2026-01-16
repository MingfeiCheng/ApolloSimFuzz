from apollo_modules.modules.planning.proto.planning_pb2 import ADCTrajectory


from .base import Subscriber
from registry import SUBSCRIBER_REGISTRY

@SUBSCRIBER_REGISTRY.register('subscriber.planning')
class PlanningSubscriber(Subscriber):
    """
    Class representing Planning channel
    """
    channel: str = '/apollo/planning'
    msg_type: str = 'apollo.planning.ADCTrajectory'
    msg_cls: any = ADCTrajectory

    def __init__(self, idx, bridge):
        self.planning_data = None
        self.trajectory = None
        super(PlanningSubscriber, self).__init__(idx, bridge)

    def _callback(self, data):
        self.planning_data = data
        self.trajectory = data.trajectory_point # if success -> should not None or not empty

    def get_data(self):
        return self.trajectory