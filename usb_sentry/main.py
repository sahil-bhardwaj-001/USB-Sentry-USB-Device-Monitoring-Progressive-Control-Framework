import typer
import sys
import time
import signal
import os
import stat
import subprocess
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from .core.logger import logger, log_file_path
from .core.policy import PolicyEngine, PolicyAction, TrustState
from .core.events import USBEvent, DeviceAction, DeviceType
from .file_audit.watcher import FileAuditor
from threading import Thread

# Platform imports
if sys.platform == 'linux':
    from .platforms.linux import LinuxUSBMonitor as PlatformMonitor
elif sys.platform == 'win32':
    from .platforms.windows import WindowsUSBMonitor as PlatformMonitor
else:
    print(f"Unsupported platform: {sys.platform}")
    sys.exit(1)

app = typer.Typer()
console = Console()
policy_engine = PolicyEngine()
file_auditor = FileAuditor()
monitor = None
active_devices = {} # Map device_id -> {device, mount_path}

def check_mount_rw(mount_path):
    """Check if a mount is actually RW by reading /proc/mounts."""
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == mount_path:
                    options = parts[3].split(',')
                    if 'rw' in options:
                        return True
                    if 'ro' in options:
                        return False
    except Exception:
        pass
    return False

def promote_device(device, mount_path):
    """Handle device promotion to Authorized state."""
    # Atomic check-and-remove to prevent race conditions (Infinite Loop Fix)
    if active_devices.pop(device.get_id(), None) is None:
        return

    console.print(f"[bold green]Device {device.product_name} has earned TRUST (AUTHORIZED).[/bold green]")
    
    # Interactive Prompt
    if Confirm.ask(f"Do you want to add {device.product_name} to the allowlist and enable Read/Write access?"):
        # Add to allowlist
        policy_engine.add_to_allowlist(device)
        console.print(f"[green]Added {device.get_id()} to allowlist.[/green]")
        
        # Remount RW
        try:
            console.print(f"[yellow]Remounting {mount_path} as Read/Write...[/yellow]")
            subprocess.run(["mount", "-o", "remount,rw", mount_path], check=True)
            
            # Verify actual state
            if check_mount_rw(mount_path):
                console.print(f"[bold green]Device is now Authorized and Read/Write.[/bold green]")
            else:
                console.print(f"[bold red]WARNING: Remount command succeeded but device appears to still be Read-Only![/bold red]")
                console.print(f"[red]This usually implies filesystem errors. Run 'dmesg' for details.[/red]")
                
        except Exception as e:
            logger.error(f"Failed to remount RW: {e}")
            console.print(f"[red]Failed to remount RW: {e}[/red]")
    else:
        # User declined promotion -> BLOCK the device
        console.print(f"[bold red]User declined authorization. Blocking device {device.product_name}...[/bold red]")
        policy_engine.add_to_blocklist(device)
        policy_engine.trust_manager.update_state(device.get_id(), TrustState.BLOCKED)
        console.print("[red]Device has been added to the blocklist. Future connections will be blocked.[/red]")
        
        # Enforce Block IMMEDIATELY and PERSISTENTLY
        blocked_devices_connected.add(device.get_id())
        Thread(target=enforce_block_persistent, args=(device,), daemon=True).start()

def unmount_device(mount_path):
    """Unmount the device at the given path (Cross-Platform)."""
    if sys.platform == 'linux':
        try:
            # Try simple umount first
            subprocess.run(["umount", mount_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            try:
                # Try lazily if busy
                subprocess.run(["umount", "-l", mount_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                logger.error(f"Failed to unmount {mount_path}: {e}")
                return False
    elif sys.platform == 'win32':
        # On Windows, we can't easily 'unmount' a drive letter without admin API calls or powershell.
        # mountvol D: /D removes the volume mount point assignment.
        try:
            # Remove trailing slash if present for mountvol
            drive = mount_path.rstrip('\\')
            subprocess.run(["mountvol", drive, "/D"], check=True, shell=True)
            return True
        except Exception as e:
            logger.error(f"Failed to unmount {mount_path} on Windows: {e}")
            return False
    return False

def wait_for_mount(device, timeout=10):
    """Poll for the mount point of a connected device."""
    console.print(f"[dim]Waiting for mount point for {device.product_name}...[/dim]")
    mount_path = None
    for _ in range(timeout):
        mount_path = monitor.resolve_mount_point(device)
        if mount_path:
            break
        time.sleep(1)
    return mount_path



blocked_devices_connected = set()

def enforce_block_persistent(dev):
    """
    Persistently check for and unmount a blocked device until it is disconnected.
    """
    d_id = dev.get_id()
    console.print(f"[bold red]Starting persistent enforcement for {dev.product_name}...[/bold red]")
    
    # Loop until device is removed
    while d_id in blocked_devices_connected:
        # Check if mounted
        mount_path = monitor.resolve_mount_point(dev)
        if mount_path:
            console.print(f"[bold red]Detected mount at {mount_path}. Enforcing BLOCK (Unmounting)...[/bold red]")
            if unmount_device(mount_path):
                console.print(f"[bold red]Device unmounted successfully. Access Denied.[/bold red]")
                logger.info(f"Enforced block on {d_id} (Unmounted {mount_path})")
            else:
                console.print(f"[red]Failed to unmount {mount_path}. Retrying...[/red]")
        
        time.sleep(1) # Poll every second
    
    console.print(f"[dim]Stopped enforcement for {dev.product_name} (Disconnected)[/dim]")


def handle_usb_event(event: USBEvent):
    """Callback for USB events."""
    device = event.device
    dev_id = device.get_id()
    
    if event.action == DeviceAction.ADD:
        action = policy_engine.evaluate(device)
        trust_state = policy_engine.trust_manager.get_state(dev_id)
        
        status_color = "green" if action == PolicyAction.ALLOW else "red"
        
        # Explicit Logging for Unauthorized/Monitored devices
        if trust_state == TrustState.MONITORED:
            console.print(f"[{status_color}]UNAUTHORIZED DEVICE DETECTED: {device.product_name} ({dev_id}) - MONITORING[/{status_color}]")
            logger.warning(f"UNAUTHORIZED ACCESS DETECTED: {dev_id}. State: {trust_state.name} Action: {action.name}", extra={"device_info": device.__dict__})
        elif action == PolicyAction.BLOCK:
             console.print(f"[bold red]BLOCKED DEVICE CONNECTED: {device.product_name} ({dev_id})[/bold red]")
             logger.warning(f"BLOCKED DEVICE CONNECTED: {dev_id}", extra={"device_info": device.__dict__})
        else:
            console.print(f"[{status_color}]DEVICE DETECTED: {device.product_name} ({dev_id}) - {action.name}[/{status_color}]")
            logger.info(f"Device connected: {dev_id}. Action: {action.name}", extra={"device_info": device.__dict__})

        # Handle Blocking (Active Persistent Enforcement)
        if action == PolicyAction.BLOCK and device.device_type == DeviceType.STORAGE:
            # Add to tracking set
            blocked_devices_connected.add(dev_id)
            Thread(target=enforce_block_persistent, args=(device,), daemon=True).start()

        # Handle Allowed/Monitored (Monitoring)
        elif action == PolicyAction.ALLOW and device.device_type == DeviceType.STORAGE:
            # We need to find where this device is mounted (drive letter or path).
            # Mounting might take a few seconds after the USB event.
            

            
            def start_audit_async(dev):
                mount_path = wait_for_mount(dev)
                    
                if mount_path:
                    console.print(f"[bold green]Mount detected at {mount_path}. Starting file audit.[/bold green]")
                    logger.info(f"Mount detected: {dev.get_id()} -> {mount_path}")
                    
                    # Enforce Read-Only for Unauthorized (Monitored) Devices
                    if trust_state == TrustState.MONITORED:
                        try:
                            console.print(f"[yellow]Enforcing Read-Only permissions on {mount_path}...[/yellow]")
                            subprocess.run(["mount", "-o", "remount,ro", mount_path], check=True)
                            logger.info(f"Enforced Read-Only on {mount_path}")
                        except Exception as e:
                            logger.error(f"Failed to enforce Read-Only on {mount_path}: {e}")
                            console.print(f"[red]Failed to enforce Read-Only: {e}[/red]")
                    
                    # Track active device for idle promotion
                    if trust_state == TrustState.MONITORED:
                         active_devices[dev.get_id()] = {'device': dev, 'mount_path': mount_path}
                    
                    # Diagnostics: Check write permissions
                    try:
                        st = os.stat(mount_path)
                        access = "R/W" if os.access(mount_path, os.W_OK) else "RO"
                        console.print(f"[dim]Mount Permissions: {access} (Mode: {oct(st.st_mode)})[/dim]")
                        logger.info(f"Mount Permissions for {mount_path}: {access} Mode: {oct(st.st_mode)}")
                    except Exception as e:
                        logger.error(f"Failed to check permissions for {mount_path}: {e}")

                    # Trust Callback
                    def activity_callback(size_mb=0, is_executable=False):
                        new_state = policy_engine.trust_manager.report_activity(dev.get_id(), size_mb, is_executable=is_executable)
                        if new_state == TrustState.SUSPICIOUS:
                            console.print(f"[bold red]ALERT: Device {dev.product_name} is behaving SUSPICIOUSLY![/bold red]")
                            # Here we would trigger enforcement (e.g. unmount)
                        elif new_state == TrustState.AUTHORIZED:
                            promote_device(dev, mount_path)

                    file_auditor.start_monitoring(mount_path, callback=activity_callback)
                else:
                    console.print(f"[yellow]Could not determine mount point for {dev.product_name}. Manual mount required?[/yellow]")
                    logger.warning(f"Could not determine mount point for {dev.get_id()}")

            Thread(target=start_audit_async, args=(device,), daemon=True).start()

    elif event.action == DeviceAction.REMOVE:
        console.print(f"[yellow]DEVICE REMOVED: {device.product_name} ({dev_id})[/yellow]")
        logger.info(f"Device disconnected: {dev_id}")
        
        # Cleanup active tracking
        if dev_id in active_devices:
            del active_devices[dev_id]
        
        # Cleanup blocked tracking (stops enforcement thread)
        if dev_id in blocked_devices_connected:
            blocked_devices_connected.remove(dev_id)
        # Ideally we stop auditing the specific path here.
        # But determining the old mount point of a removed device requires state tracking.
        # For this implementation, we accept that auditors will error out or just stop receiving events.
        # We could improve this by maintaining a map of device_id -> mount_point in the main scope.

@app.command()
def start(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    policy: str = typer.Option("policies.yaml", "--policy", "-p", help="Path to policy file")
):
    """Start the USB Sentry monitoring service."""
    global policy_engine, monitor
    policy_engine = PolicyEngine(policy)
    
    console.print(f"[bold green]Starting USB Sentry on {sys.platform}...[/bold green]")
    console.print(f"Logging to: {log_file_path}")
    
    # Clear logs on startup
    with open(log_file_path, 'w') as f:
        f.truncate(0)
    logger.info("Session started. Logs cleared.")
    
    monitor = PlatformMonitor(callback=handle_usb_event)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        console.print("\n[bold red]Stopping service...[/bold red]")
        monitor.stop()
        file_auditor.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    
    monitor.start()
    
    def launch_interactive_cli():
        """Helper to launch the interactive CLI in a new terminal."""
        if sys.platform == "win32":
            # Windows Launch Logic
            python_exe = f'"{sys.executable}"'
            cli_cmd = f'{python_exe} -m usb_sentry.interactive'
            
            console.print(f"\n[bold yellow]Launching Interactive Device Manager...[/bold yellow]")
            try:
                # 'start' is a shell command. 
                # Syntax: start "Title" cmd /k "command..."
                # We need to be careful with inner quotes.
                full_cmd = f'start "USB Sentry Interactive" cmd /k "{cli_cmd}"'
                subprocess.Popen(full_cmd, shell=True)
                console.print("[green]Launched Interactive CLI (New Window).[/green]")
            except Exception as e:
                console.print(f"[yellow]Could not launch interactive CLI automatically: {e}[/yellow]")
            return

        if sys.platform != "linux":
            return

        # Ensure we use the same python interpreter (venv) for the subprocess
        # QUOTING FIX: Handle spaces in path (e.g. "UNI Pro 3")
        python_exe = f'"{sys.executable}"'
        cli_cmd = f"sudo {python_exe} -m usb_sentry.interactive"
        
        console.print(f"\n[bold yellow]Launching Interactive Device Manager...[/bold yellow]")
        console.print(f"[dim]If the window does not appear, run this command in a new terminal:[/dim]")
        console.print(f"[bold]{cli_cmd}[/bold]\n")
        
        # Try 1: Gnome Terminal with dbus-launch (Fixes sudo issue)
        try:
             # We execute bash -c so we can keep the window open or handle errors inside
            subprocess.Popen([
                "dbus-launch", "gnome-terminal", "--geometry=130x40", "--", "bash", "-c", f"{cli_cmd}; exec bash"
            ], start_new_session=True)
            console.print("[green]Launched Interactive CLI (Gnome Terminal).[/green]")
        except (FileNotFoundError, OSError):
             # Try 2: xterm (Reliable fallback)
            try:
                subprocess.Popen([
                    "xterm", "-geometry", "130x40", "-e", cli_cmd
                ], start_new_session=True)
                console.print("[green]Launched Interactive CLI (xterm).[/green]")
            except (FileNotFoundError, OSError):
                 # Try 3: Raw gnome-terminal (Last resort)
                try:
                    subprocess.Popen([
                        "gnome-terminal", "--geometry=130x40", "--", "bash", "-c", f"{cli_cmd}; exec bash"
                    ], start_new_session=True)
                    console.print("[green]Launched Interactive CLI (fallback).[/green]")
                except Exception as e:
                    console.print(f"[yellow]Could not launch interactive CLI automatically: {e}[/yellow]")

    # Launch immediately on start
    launch_interactive_cli()
    
    # Background Thread for Maintenance (Idle Promotions)
    def maintenance_loop():
        while True:
            try:
                # Check for idle promotions
                promoted_ids = policy_engine.trust_manager.check_idle_promotions()
                for dev_id in promoted_ids:
                    if dev_id in active_devices:
                        info = active_devices[dev_id]
                        # We need to run promotion on the main thread/console ideally, 
                        # but simple promotion logic is thread-safe enough for now 
                        # as long as we don't output too much to stdout roughly.
                        # For better safety, we could use a queue, but this works for prototype.
                        promote_device(info['device'], info['mount_path'])
                time.sleep(1)
            except Exception as e:
                logger.error(f"Maintenance loop error: {e}")
                time.sleep(5)

    maintenance_thread = Thread(target=maintenance_loop, daemon=True)
    maintenance_thread.start()

    # Main Command Loop
    console.print("\n[bold cyan]Main Terminal Active. Type 'r' to RE-LAUNCH Interactive CLI or 'q' to QUIT.[/bold cyan]")
    
    try:
        while True:
            # Simple input loop
            cmd = input().strip().lower()
            if cmd in ('r', 'relaunch'):
                console.print("[yellow]Relaunching Interactive CLI...[/yellow]")
                launch_interactive_cli()
            elif cmd in ('q', 'quit', 'exit'):
                raise KeyboardInterrupt
            
    except KeyboardInterrupt:
        monitor.stop()

@app.command()
def report():
    """Generate a summary report from logs."""
    console.print("[bold]Simple Log Analysis[/bold]")
    if not log_file_path.exists():
        console.print("[red]No logs found.[/red]")
        return

    import json
    
    table = Table(title="Recent USB Activity")
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Level", style="magenta")
    table.add_column("Message", style="green")

    with open(log_file_path, 'r') as f:
        for line in f:
            try:
                log_entry = json.loads(line)
                message = log_entry['message']
                
                # Filter out noisy logs
                if "Loaded policy" in message:
                    continue
                    
                table.add_row(log_entry['timestamp'], log_entry['level'], message)
            except:
                pass
    
    console.print(table)

@app.command()
def list_devices():
    """List currently connected usb devices (Snapshot)."""
    console.print("[dim]Scanning usb devices...[/dim]")
    
    table = Table(title="Connected USB Devices")
    table.add_column("Device", style="cyan")
    table.add_column("VID:PID", style="magenta")
    table.add_column("Serial", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Path", style="dim", no_wrap=True)

    devices_found = 0

    if sys.platform == 'linux':
        try:
            import pyudev
            context = pyudev.Context()
            # Scan for all USB devices (not just storage)
            for device in context.list_devices(subsystem='usb'):
                # We care about the main USB device object (DEVTYPE=usb_device)
                if device.device_type != 'usb_device':
                    continue
                
                vid = device.get('ID_VENDOR_ID') or "????"
                pid = device.get('ID_MODEL_ID') or "????"
                serial = device.get('ID_SERIAL_SHORT') or device.get('ID_SERIAL') or "NOSERIAL"
                model = device.get('ID_MODEL') or device.get('ID_USB_MODEL') or "Unknown Device"
                vendor = device.get('ID_VENDOR') or "Unknown Vendor"
                
                # Heuristic for type (similar to linux.py platform logic)
                dev_type = "Peripheral"
                if device.get('ID_USB_INTERFACES') and ':08' in device.get('ID_USB_INTERFACES'):
                    dev_type = "Storage"
                
                table.add_row(
                    f"{vendor} {model}",
                    f"{vid}:{pid}",
                    serial,
                    dev_type,
                    device.device_path
                )
                devices_found += 1
        except ImportError:
            console.print("[red]Error: pyudev not installed or inactive.[/red]")

    elif sys.platform == 'win32':
        try:
            import wmi
            import pythoncom
            pythoncom.CoInitialize()
            w = wmi.WMI()
            
            # Query PnPEntity for USB devices
            for item in w.Win32_PnPEntity(ConfigManagerErrorCode=0):
                if item.DeviceID and "USB" in item.DeviceID and "VID_" in item.DeviceID:
                     # Parse ID: USB\VID_xxxx&PID_xxxx\Serial
                    try:
                        parts = item.DeviceID.split('\\')
                        hw_id = parts[1]
                        serial = parts[2]
                        
                        vid = ""
                        pid = ""
                        if "VID_" in hw_id and "PID_" in hw_id:
                             vid = hw_id.split("VID_")[1].split("&")[0]
                             pid = hw_id.split("PID_")[1].split("&")[0]
                        
                        name = item.Name or item.Description or "Unknown Device"
                        dev_type = "Storage" if "Mass Storage" in (item.Description or "") else "Peripheral"
                        
                        table.add_row(
                            name,
                            f"{vid}:{pid}",
                            serial,
                            dev_type,
                            item.DeviceID
                        )
                        devices_found += 1
                    except:
                        pass
        except ImportError:
             console.print("[red]Error: wmi module not installed.[/red]")
        except Exception as e:
             console.print(f"[red]Error scanning windows devices: {e}[/red]")

    if devices_found == 0:
        console.print("[yellow]No USB devices found.[/yellow]")
    else:
        console.print(table)

if __name__ == "__main__":
    app()
