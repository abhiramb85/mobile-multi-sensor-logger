from abc import ABC, abstractmethod
from typing import Optional, Dict
from queue import Queue


class SensorDriver(ABC):
    """Abstract base class for all sensor drivers."""

    def __init__(self, *args, **kwargs):
        self._is_running = False
        self.data_queue = Queue(maxsize=100)

    @abstractmethod
    def start(self) -> bool:
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def get_data(self) -> Optional[Dict]:
        pass

    def is_running(self) -> bool:
        return self._is_running
