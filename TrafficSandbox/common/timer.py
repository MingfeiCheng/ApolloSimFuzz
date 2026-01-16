import time

from typing import Optional

class Timer:
    """Frame-based logical timer with real-time tracking and FPS measurement."""

    fps: float = 60.0
    frame_count: int = 0
    start_time: float = time.time()
    _last_tick_time: Optional[float] = None
    _real_fps: float = 0.0

    @classmethod
    def tick(cls):
        """Advance one frame and update timing statistics."""
        now = time.time()
        cls.frame_count += 1

        # FPS tracking
        if cls._last_tick_time is not None:
            delta = now - cls._last_tick_time
            if delta > 0:
                cls._real_fps = 1.0 / delta
        cls._last_tick_time = now

    @classmethod
    def get_frame_count(cls) -> int:
        return cls.frame_count

    @classmethod
    def get_game_time(cls) -> float:
        """Logical game time (seconds)."""
        return cls.frame_count / cls.fps

    @classmethod
    def get_real_time_elapsed(cls) -> float:
        """Elapsed real-world time since start."""
        return time.time() - cls.start_time

    @staticmethod
    def get_real_time() -> float:
        return time.time()

    @classmethod
    def get_real_fps(cls) -> float:
        """Measured instantaneous FPS based on tick intervals."""
        return cls._real_fps

    @classmethod
    def reset(cls):
        """Reset logical and real timers."""
        cls.start_time = time.time()
        cls.frame_count = 0
        cls._last_tick_time = None
        cls._real_fps = 0.0

    @classmethod
    def json_data(cls):
        return {
            "frame": cls.frame_count,
            "game_time": round(cls.get_game_time(), 4),
            "real_time_elapsed": round(cls.get_real_time_elapsed(), 4),
            "real_fps": round(cls._real_fps, 2),
            "target_fps": cls.fps,
            "server_time": round(cls.get_real_time(), 4),
        }
