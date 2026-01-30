import time
from threading import Thread
from datetime import datetime
from typing import Dict, Optional
from ..core.monitor import USBMonitor
from ..core.events import USBEvent, USBDevice, DeviceAction, DeviceType
from ..core.logger import logger

try:
    import wmi
    import pythoncom
except ImportError:
    wmi = None

class WindowsUSBMonitor(USBMonitor):
    def __init__(self, callback):
        super().__init__(callback)
        if wmi is None:
            logger.warning("WMI module not found. Windows monitoring will not work.")
        self._seen_devices: Dict[str, USBDevice] = {}

    def start(self):
        super().start()
        self._thread = Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Windows USB Monitor started.")

    def _monitor_loop(self):
        # Initial scan
        pythoncom.CoInitialize()
        w = wmi.WMI()
        
        while self.running:
            try:
                current_devices = self._scan_devices(w)
                
                # Check for added devices
                for device_id, device in current_devices.items():
                    if device_id not in self._seen_devices:
                        self._notify(USBEvent(DeviceAction.ADD, device))
                
                # Check for removed devices
                removed_ids = set(self._seen_devices.keys()) - set(current_devices.keys())
                for device_id in removed_ids:
                    device = self._seen_devices[device_id]
                    self._notify(USBEvent(DeviceAction.REMOVE, device))
                
                self._seen_devices = current_devices
                time.sleep(1) # Poll every second
            except Exception as e:
                logger.error(f"Error in Windows monitor loop: {e}")
                time.sleep(5)
            
    def _scan_devices(self, w_interface) -> Dict[str, USBDevice]:
        devices = {}
        # Query typical USB storage specific WMI classes or Win32_PnPEntity
        for item in w_interface.Win32_PnPEntity(ConfigManagerErrorCode=0):
            if item.DeviceID and "USB" in item.DeviceID:
                # Parse Device ID for Vendor/Product
                # Format usually: USB\VID_xxxx&PID_xxxx\Serial
                try:
                    props = self._parse_device_id(item.DeviceID)
                    if props:
                        device = USBDevice(
                            device_path=item.DeviceID,
                            vendor_id=props['vid'],
                            product_id=props['pid'],
                            serial_number=props['serial'],
                            product_name=item.Name,
                            device_type=DeviceType.STORAGE if "Mass Storage" in (item.Description or "") else DeviceType.OTHER
                        )
                        devices[item.DeviceID] = device
                except Exception:
                    continue
        return devices

    def _parse_device_id(self, device_id: str):
        # Simple parser for standard USB\VID_XXXX&PID_YYYY\Serial format
        try:
            parts = device_id.split('\\')
            if len(parts) >= 3:
                hw_id = parts[1]
                serial = parts[2]
                
                vid = ""
                pid = ""
                
                if "VID_" in hw_id and "PID_" in hw_id:
                     vid = hw_id.split("VID_")[1].split("&")[0]
                     pid = hw_id.split("PID_")[1].split("&")[0]
                     
                return {"vid": vid, "pid": pid, "serial": serial}
        except:
            pass
        return None

    def resolve_mount_point(self, device: USBDevice) -> Optional[str]:
        """
        On Windows, we map the PNP DeviceID to a Logical Disk (Drive Letter) via WMI.
        Chain: PnPEntity -> DiskDrive -> Partition -> LogicalDisk
        """
        if wmi is None:
            return None
            
        try:
            # Re-initialize WMI for the thread if needed (though usually WMI() handles it)
            # We create a local instance to be safe
            w = wmi.WMI()
            
            # 1. Find the Win32_DiskDrive associated with the PNP DeviceID
            # The device.device_path is the PNP DeviceID
            # Escape backslashes for WQL
            escaped_id = device.device_path.replace("\\", "\\\\")
            disk_drives = w.query(f"SELECT * FROM Win32_DiskDrive WHERE PNPDeviceID = '{escaped_id}'")
            
            for drive in disk_drives:
                # 2. Associated Partitions
                for partition in drive.associators("Win32_DiskDriveToDiskPartition"):
                    # 3. Associated Logical Disks
                    for logical_disk in partition.associators("Win32_LogicalDiskToPartition"):
                        if logical_disk.DeviceID:
                            return logical_disk.DeviceID + "\\" # Return e.g. "E:\"
        except Exception as e:
            logger.error(f"Error resolving mount point for {device.device_path}: {e}")
            
        return None
