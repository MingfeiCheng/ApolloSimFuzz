class VehicleControl(object):

    def __init__(self, throttle: float = 0.0, brake: float = 0.0, steer: float = 0.0, reverse: bool = False):
        self.throttle = throttle
        self.brake = brake
        self.steer = steer
        self.reverse = reverse

    def json_data(self):
        return {
            "throttle": self.throttle,
            "brake": self.brake,
            "steer": self.steer,
            "reverse": self.reverse
        }

class VehiclePerfectControl(object):

    def __init__(self, acceleration: float = 0.0, heading:float = 0.0, throttle: float = 0.0, brake: float = 0.0, steer: float = 0.0, reverse: bool = False):
        self.acceleration = acceleration
        self.heading = heading
        self.throttle = throttle
        self.brake = brake
        self.steer = steer
        self.reverse = reverse

    def json_data(self):
        return {
            "acceleration": self.acceleration,
            "heading": self.heading,
            "throttle": self.throttle,
            "brake": self.brake,
            "steer": self.steer,
            "reverse": self.reverse
        }
