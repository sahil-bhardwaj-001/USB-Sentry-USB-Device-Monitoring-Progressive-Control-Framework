from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ..core.logger import logger
import time
import os
import getpass
from threading import Thread

def get_current_user():
    """
    Get the real user associated with the process.
    If running as root (via sudo), returns the SUDO_USER.
    Otherwise, returns the current effective user.
    On Windows, SUDO_USER is usually not present, so it falls back to getpass.getuser().
    """
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        return sudo_user
    return getpass.getuser()

class USBFileHandler(FileSystemEventHandler):
    def __init__(self, callback=None):
        self.callback = callback

    def _get_user(self, path):
        # In some cases, like deleted files, os.stat might fail.
        # Fallback to get_current_user() if owner cannot be determined.
        try:
            file_stat = os.stat(path)
            # On Linux, st_uid is the user ID. We'd need to map this to a username.
            # For simplicity, we'll use get_current_user() for now,
            # or if we want the actual file owner, we'd need 'pwd' module.
            # For this context, get_current_user() is likely what's intended for the *actor*.
            return get_current_user()
        except FileNotFoundError:
            # If the file is already gone (e.g., on_deleted), use the current process user.
            return get_current_user()
        except Exception:
            # Other errors, fallback to current user
            return get_current_user()

    def _notify(self, event_type, src_path, dest_path=None):
        user = self._get_user(src_path)
        
        # Check for executable traits
        is_executable = False
        try:
            # Check extension
            _, ext = os.path.splitext(src_path)
            if ext.lower() in self.EXECUTABLE_EXTENSIONS:
                is_executable = True
            
            # Check permissions (stat.S_IXUSR) if file exists
            if os.path.exists(src_path):
                st = os.stat(src_path)
                if st.st_mode & stat.S_IXUSR:
                    is_executable = True
        except Exception:
            pass # File might be gone or inaccessible

        logger.info(f"FILE {event_type}: {src_path}", extra={
             'event_code': event_type,
             'src_path': src_path,
             'dest_path': dest_path,
             'user': user,
             'is_executable': is_executable
        })
        
        if self.callback:
            # Estimate size (very rough) - for accurate tracking we'd need os.stat
            size_mb = 0
            if os.path.exists(src_path):
                 try:
                     size_mb = os.path.getsize(src_path) / (1024 * 1024)
                 except:
                     pass
            self.callback(size_mb=size_mb, is_executable=is_executable)

    def on_created(self, event):
        self._notify("CREATED", event.src_path)

    def on_deleted(self, event):
        self._notify("DELETED", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._notify("MODIFIED", event.src_path)

    def on_moved(self, event):
        self._notify("MOVED", event.src_path, event.dest_path)

class FileAuditor:
    def __init__(self):
        self.observers = {}

    def start_monitoring(self, path: str, callback=None):
        if path in self.observers:
            return
            
        logger.info(f"Starting file audit on {path}")
        observer = Observer()
        observer.schedule(USBFileHandler(callback), path, recursive=True)
        observer.start()
        self.observers[path] = observer

    def stop_monitoring(self, path: str):
        if path in self.observers:
            logger.info(f"Stopping file audit on {path}")
            self.observers[path].stop()
            self.observers[path].join()
            del self.observers[path]

    def stop_all(self):
        for path in list(self.observers.keys()):
            self.stop_monitoring(path)
