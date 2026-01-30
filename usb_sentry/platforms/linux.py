import pyudev
from datetime import datetime
from typing import Optional
from ..core.monitor import USBMonitor
from ..core.events import USBEvent, USBDevice, DeviceAction, DeviceType
from ..core.logger import logger

class LinuxUSBMonitor(USBMonitor):
    def __init__(self, callback):
        super().__init__(callback)
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')

    def start(self):
        super().start()
        self.observer = pyudev.MonitorObserver(self.monitor, callback=self._handle_event)
        self.observer.start()
        logger.info("Linux USB Monitor started.")

    def stop(self):
        super().stop()
        if hasattr(self, 'observer'):
            self.observer.stop()
        logger.info("Linux USB Monitor stopped.")

    def _handle_event(self, device):
        action = device.action
        if action not in ('add', 'remove', 'change'):
            return

        # Skip devices that are not physical USB devices (interfaces usually)
        if device.device_type != 'usb_device':
            return
            
        usb_device = self._parse_device(device)
        
        event_action = DeviceAction.CHANGE
        if action == 'add':
            event_action = DeviceAction.ADD
        elif action == 'remove':
            event_action = DeviceAction.REMOVE
            
        event = USBEvent(
            action=event_action,
            device=usb_device,
            timestamp=datetime.now()
        )
        self._notify(event)
        
    def _parse_device(self, device) -> USBDevice:
        # Determine device type (broad heuristic)
        dev_type = DeviceType.OTHER
        
        # Heuristic 1: Check children for block devices
        try:
            for child in device.children:
                if child.subsystem == 'block':
                    dev_type = DeviceType.STORAGE
                    break
        except:
            pass
            
        # Heuristic 2: Check ID_USB_INTERFACES for Mass Storage (08)
        # Format usually looks like ':080650:'
        if dev_type == DeviceType.OTHER:
            interfaces = device.get('ID_USB_INTERFACES')
            if interfaces and ':08' in interfaces:
                dev_type = DeviceType.STORAGE
                
        # Heuristic 3: Check bDeviceClass attribute
        if dev_type == DeviceType.OTHER:
            try:
                # Class 8 is Mass Storage
                if device.attributes.get('bDeviceClass') == '08':
                    dev_type = DeviceType.STORAGE
            except:
                pass

        # Check if it has storage children and attempt to find mount point
        # This requires searching the children for block devices
        mount_point = None
        # We perform mount resolution later in main.py, so simple placeholder here is fine.
            
        # Try to get attributes, fallback to environment variables which persist in remove events
        vendor_id = device.get('ID_VENDOR_ID') or device.get('ID_VENDOR_ID') # Attributes
        if not vendor_id:
             vendor_id = device.get('ID_VENDOR_ID') # Environment
        
        # In pyudev, device.get() checks environment for some events, but attributes are property.
        # For 'remove', attributes are gone, we MUST use environment values (like ID_VENDOR_ID).
        # device.get(KEY) actually checks the environment or properties provided by udev in the event.
        
        return USBDevice(
            device_path=device.device_path,
            vendor_id=device.get('ID_VENDOR_ID') or "0000",
            product_id=device.get('ID_MODEL_ID') or "0000",
            serial_number=device.get('ID_SERIAL_SHORT') or device.get('ID_SERIAL') or "NOSERIAL",
            manufacturer=device.get('ID_VENDOR'),
            product_name=device.get('ID_MODEL'),
            device_type=dev_type,
            mount_point=mount_point
        )

    def resolve_mount_point(self, device: USBDevice) -> Optional[str]:
        """
        Reverse lookup: Iterate all mounted partitions and check if they belong
        to the given USB device by comparing ancestry or serial numbers.
        """
        import psutil
        
        try:
            partitions = psutil.disk_partitions()
            for part in partitions:
                # Basic filter to avoid scanning everything (optional but good for perf)
                if not part.device.startswith('/dev/'):
                    continue

                try:
                    # Get udev device for the partition's device node (e.g. /dev/sdb1)
                    part_device = pyudev.Devices.from_device_file(self.context, part.device)
                    
                    # 1. Check Serial Number Match (Exact and Robust)
                    # The partition udev device usually inherits ID_SERIAL from the parent disk
                    part_serial = part_device.get('ID_SERIAL_SHORT') or part_device.get('ID_SERIAL')
                    if part_serial == device.serial_number and device.serial_number != "NOSERIAL":
                        return part.mountpoint
                        
                    # 2. Ancestry Check
                    # If the partition's syspath starts with the USB device's syspath, it is a child.
                    if device.device_path and part_device.sys_path.startswith(device.device_path):
                         return part.mountpoint
                         
                except Exception:
                    # Not a udev device or permission denied, skip
                    continue

        except Exception as e:
            logger.error(f"Error resolving mount point: {e}")
            pass
            
        return None
