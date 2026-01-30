from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from .logger import logger

class TrustState(Enum):
    DETECTED = "DETECTED"
    UNAUTHORIZED = "UNAUTHORIZED" # Known but not trusted
    MONITORED = "MONITORED"       # Allowed temporarily for observation
    AUTHORIZED = "AUTHORIZED"     # Explicitly allowed
    SUSPICIOUS = "SUSPICIOUS"     # Risky behavior detected
    BLOCKED = "BLOCKED"           # Enforcement active

@dataclass
class DeviceTrustState:
    device_id: str
    state: TrustState = TrustState.UNAUTHORIZED
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    # Behavioral Metrics
    files_accessed: int = 0
    data_transferred_mb: float = 0.0
    suspicious_events: int = 0
    
    # Thresholds (could be configurable)
    MAX_FILES_PER_MIN = 10
    MAX_DATA_MB = 100.0
    PROMOTION_TIME_MIN = 0.5 # 30 seconds for easier testing
    
    _window_start: datetime = field(default_factory=datetime.now)
    _window_files: int = 0
    executable_detected: bool = False
    
    def log_activity(self, size_mb: float = 0.0, is_executable: bool = False):
        now = datetime.now()
        self.last_seen = now
        self.files_accessed += 1
        self.data_transferred_mb += size_mb
        
        if is_executable:
            self.executable_detected = True
        
        # Rate limiting window (1 minute)
        if now - self._window_start > timedelta(minutes=1):
            self._window_start = now
            self._window_files = 0
            
        self._window_files += 1

    def evaluate(self) -> TrustState:
        """
        Evaluate current metrics against rules to determine next state.
        Returns the new state if changed, else current state.
        """
        # 1. Check Escalation (Suspicious)
        if self.executable_detected:
            logger.warning(f"Device {self.device_id} flagged SUSPICIOUS: Executable file activity detected")
            self.state = TrustState.SUSPICIOUS
            return self.state

        if self._window_files > self.MAX_FILES_PER_MIN:
            logger.warning(f"Device {self.device_id} flagged SUSPICIOUS: High file access rate ({self._window_files}/min)")
            self.state = TrustState.SUSPICIOUS
            return self.state
            
        if self.data_transferred_mb > self.MAX_DATA_MB:
            logger.warning(f"Device {self.device_id} flagged SUSPICIOUS: Data volume exceeded ({self.data_transferred_mb:.2f} MB)")
            self.state = TrustState.SUSPICIOUS
            return self.state

        # 2. Check Promotion (Authorized)
        # Only promote if currently Monitored
        if self.state == TrustState.MONITORED:
            duration = datetime.now() - self.first_seen
            if duration > timedelta(minutes=self.PROMOTION_TIME_MIN):
                # Only promote if usage was "normal" (simple heuristic: accessed at least 1 file but not too many)
                # Actually, passive existence is fine too.
                logger.info(f"Device {self.device_id} promoted to AUTHORIZED after {duration}")
                self.state = TrustState.AUTHORIZED
                return self.state

        return self.state

class TrustManager:
    def __init__(self):
        self.devices: Dict[str, DeviceTrustState] = {}

    def register_device(self, device_id: str, initial_state: TrustState = TrustState.UNAUTHORIZED):
        if device_id not in self.devices:
            self.devices[device_id] = DeviceTrustState(device_id=device_id, state=initial_state)
            logger.info(f"TrustManager registered {device_id} as {initial_state.name}")

    def update_state(self, device_id: str, new_state: TrustState):
        if device_id in self.devices:
            old_state = self.devices[device_id].state
            self.devices[device_id].state = new_state
            logger.info(f"TrustState change {device_id}: {old_state.name} -> {new_state.name}")

    def report_activity(self, device_id: str, size_mb: float = 0.0, is_executable: bool = False) -> TrustState:
        if device_id not in self.devices:
            return TrustState.UNAUTHORIZED
            
        device_state = self.devices[device_id]
        
        # If already blocked, ignore or re-affirm block?
        if device_state.state == TrustState.BLOCKED:
            return TrustState.BLOCKED
            
        device_state.log_activity(size_mb, is_executable)
        return device_state.evaluate()

    def get_state(self, device_id: str) -> TrustState:
        if device_id in self.devices:
            return self.devices[device_id].state
        return TrustState.UNAUTHORIZED

    def check_idle_promotions(self) -> List[str]:
        """Check all monitored devices for time-based promotion, even without activity."""
        promoted_ids = []
        for dev_id, state in self.devices.items():
            if state.state == TrustState.MONITORED:
                # evaluate() checks time duration
                new_state = state.evaluate()
                if new_state == TrustState.AUTHORIZED:
                    promoted_ids.append(dev_id)
        return promoted_ids
