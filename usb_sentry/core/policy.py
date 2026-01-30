import yaml
import json
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any
from .events import USBDevice
from .logger import logger
from .trust import TrustManager, TrustState

class PolicyAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ALERT = "alert"

class PolicyEngine:
    def __init__(self, policy_path: str = "policies.yaml"):
        self.policy_path = Path(policy_path)
        self.allowlist: List[str] = [] # List of device IDs (vendor:product:serial)
        self.blocklist: List[str] = []
        self.default_action = PolicyAction.BLOCK
        self.trust_manager = TrustManager()
        self.load_policy()

    def load_policy(self):
        if not self.policy_path.exists():
            logger.warning(f"Policy file {self.policy_path} not found. Using default DENY ALL.")
            return

        try:
            with open(self.policy_path, "r") as f:
                data = yaml.safe_load(f) or {}
                
            self.allowlist = data.get("allowlist", [])
            self.blocklist = data.get("blocklist", [])
            default = data.get("default_action", "block").upper()
            if default in PolicyAction.__members__:
                self.default_action = PolicyAction[default]
            
            logger.info(f"Loaded policy: {len(self.allowlist)} allowed, {len(self.blocklist)} blocked. Default: {self.default_action}")
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")

    def evaluate(self, device: USBDevice) -> PolicyAction:
        device_id = device.get_id()
        
        # Check specific blocklist
        if device_id in self.blocklist:
            logger.info(f"Device {device_id} is explicitly BLOCKED.")
            return PolicyAction.BLOCK

        # Check specific allowlist
        if device_id in self.allowlist:
            logger.info(f"Device {device_id} is explicitly ALLOWED.")
            return PolicyAction.ALLOW

        # Fallback to default (modified for Progressive Trust)
        # Instead of immediately applying default_action (BLOCK), we check TrustManager.
        
        # Register if new
        current_state = self.trust_manager.get_state(device_id)
        if current_state == TrustState.UNAUTHORIZED: # Not seen before
             self.trust_manager.register_device(device_id, TrustState.MONITORED)
             logger.info(f"Device {device_id} is unknown. Setting state to MONITORED.")
             return PolicyAction.ALLOW
             
        elif current_state == TrustState.MONITORED:
             return PolicyAction.ALLOW
             
        elif current_state == TrustState.AUTHORIZED:
             return PolicyAction.ALLOW
             
        elif current_state in (TrustState.SUSPICIOUS, TrustState.BLOCKED):
             return PolicyAction.BLOCK

        logger.info(f"Device {device_id} matched no specific rule. Default action: {self.default_action}")
        return self.default_action

    def add_to_allowlist(self, device: USBDevice):
        device_id = device.get_id()
        if device_id not in self.allowlist:
            self.allowlist.append(device_id)
            self._save_policy()

    def add_to_blocklist(self, device: USBDevice):
        device_id = device.get_id()
        if device_id not in self.blocklist:
            self.blocklist.append(device_id)
            self._save_policy()

    def _save_policy(self):
        data = {
            "allowlist": self.allowlist,
            "blocklist": self.blocklist,
            "default_action": self.default_action.value
        }
        try:
            with open(self.policy_path, "w") as f:
                yaml.dump(data, f)
            logger.info("Policy updated.")
        except Exception as e:
            logger.error(f"Failed to save policy: {e}")
