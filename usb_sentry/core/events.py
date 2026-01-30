from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
from datetime import datetime

class DeviceAction(Enum):
    ADD = "add"
    REMOVE = "remove"
    CHANGE = "change"
    BIND = "bind"
    UNBIND = "unbind"

class DeviceType(Enum):
    STORAGE = "storage"
    HID = "hid"
    NETWORK = "network"
    OTHER = "other"

@dataclass
class USBDevice:
    device_path: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    product_name: Optional[str] = None
    device_type: DeviceType = DeviceType.OTHER
    mount_point: Optional[str] = None
    timestamp: datetime = datetime.now()

    def get_id(self) -> str:
        """Returns a unique identifier for the device hash."""
        parts = [
            self.vendor_id or "0000",
            self.product_id or "0000",
            self.serial_number or "NOSERIAL"
        ]
        return ":".join(parts)

@dataclass
class USBEvent:
    action: DeviceAction
    device: USBDevice
    timestamp: datetime = datetime.now()
