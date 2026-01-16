class WalkerControl(object):

    def __init__(self, acceleration: float = 0.0, heading:float = 0.0):
        self.acceleration = acceleration
        self.heading = heading

    def json_data(self):
        return {
            "acceleration": self.acceleration,
            "heading": self.heading
        }