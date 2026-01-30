from abc import ABC, abstractmethod
from typing import Callable, Optional
from threading import Thread
import time
from ..core.events import USBEvent

class USBMonitor(ABC):
    def __init__(self, callback: Callable[[USBEvent], None]):
        self.callback = callback
        self.running = False
        self._thread: Optional[Thread] = None

    @abstractmethod
    def start(self):
        """Start the monitoring process."""
        self.running = True

    @abstractmethod
    def stop(self):
        """Stop the monitoring process."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()

    def _notify(self, event: USBEvent):
        """Dispatch event to callback."""
        if self.running:
            self.callback(event)

    def resolve_mount_point(self, device: 'USBDevice') -> Optional[str]:
        """
        Attempt to resolve the mount point (e.g., drive letter or path) for a device.
        This is platform specific and might need to be called repeatedly as mounting is async.
        """
        return None
