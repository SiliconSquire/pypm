import subprocess
import os
import sys
import json
import signal
import psutil
import time
import re
import fcntl
import logging
from pathlib import Path
import threading

CONFIG_FILE = Path.home() / '.pypm_config.json'
STARTUP_SCRIPT = Path.home() / '.pypm_startup.sh'
CRON_MARKER = "# PyPM autostart entry"
PYPM_PID_FILE = Path.home() / '.pypm_pid'
PYPM_AUTOSTART_MARKER = "# PyPM self-start entry"
LOG_FILE = Path.home() / '.pypm.log'

# Set up logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def enable_pypm_autostart():
    pypm_command = f"{sys.executable} {os.path.abspath(__file__)} start-self"
    cron_entry = f"{PYPM_AUTOSTART_MARKER}\n@reboot nohup {pypm_command} >/dev/null 2>&1 &"
    
    current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout
    if PYPM_AUTOSTART_MARKER not in current_crontab:
        new_crontab = current_crontab.strip() + f"\n{cron_entry}\n"
        subprocess.run(f"echo '{new_crontab}' | crontab -", shell=True)
        print("PyPM autostart enabled")
    else:
        print("PyPM autostart is already enabled")


def disable_pypm_autostart():
    current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout.splitlines()
    new_crontab = [line for line in current_crontab if PYPM_AUTOSTART_MARKER not in line]
    subprocess.run("crontab -", input="\n".join(new_crontab), shell=True, text=True)
    print("PyPM autostart disabled")

def validate_process_name(name):
    """Validate process name to prevent duplicates and ensure valid characters."""
    if not name or not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False, "Process name must contain only alphanumeric characters, underscores, and hyphens."
    
    config = load_config()
    if name in config:
        return False, f"Process '{name}' already exists. Use a different name or delete the existing process first."
    
    return True, ""

def validate_command(directory, command):
    """Validate that the command is executable and the script exists."""
    # Extract the Python script name from the command
    match = re.search(r'python3?\s+([^\s;|&]+)', command)
    if not match:
        return False, "Command must include a Python script (e.g., 'python3 app.py')"
    
    script_path = match.group(1)
    full_path = os.path.join(directory, script_path)
    
    if not os.path.isfile(full_path):
        return False, f"Python script '{script_path}' not found in directory '{directory}'"
    
    return True, ""

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            # Lock the file for reading
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Error decoding JSON from config file")
                return {}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    return {}


def save_config(config):
    # Create parent directory if it doesn't exist
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Use atomic write pattern
    temp_file = CONFIG_FILE.with_suffix('.tmp')
    with open(temp_file, 'w') as f:
        # Lock the file for writing
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    
    # Atomic rename
    temp_file.rename(CONFIG_FILE)


def list_processes(config):
    if not config:
        print("No processes are currently being managed by PyPM")
        return
    
    # First call to cpu_percent for all processes to initialize measurement
    process_objects = {}
    for name, process in config.items():
        pid = process.get('pid')
        if pid is not None and psutil.pid_exists(pid):
            try:
                p = psutil.Process(pid)
                if p.is_running():
                    p.cpu_percent()  # First call to initialize
                    process_objects[name] = p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    # Wait a moment for CPU measurement
    time.sleep(0.1)
    
    # Now get actual measurements and display
    print(f"{'NAME':<20} {'STATUS':<10} {'PID':<8} {'CPU':<8} {'MEM':<8} {'RESTARTS':<8}")
    print("-" * 65)
    
    for name, process in config.items():
        pid = process.get('pid')
        restarts = process.get('restart_count', 0)
        
        if name in process_objects and process_objects[name].is_running():
            p = process_objects[name]
            status = "RUNNING"
            try:
                cpu = p.cpu_percent()
                memory = p.memory_info().rss / 1024 / 1024  # Convert to MB
                print(f"{name:<20} {status:<10} {pid:<8} {cpu:>6.1f}% {memory:>6.1f}MB {restarts:>8}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                print(f"{name:<20} ERROR      {pid:<8} {'N/A':<8} {'N/A':<8} {restarts:>8}")
        else:
            print(f"{name:<20} STOPPED    {'N/A':<8} {'N/A':<8} {'N/A':<8} {restarts:>8}")


def find_venv(directory):
    venv_dirs = ['venv', '.venv', 'env', '.env', '.']
    for venv in venv_dirs:
        venv_path = Path(directory) / venv
        if (venv_path / 'bin' / 'activate').exists():
            return venv_path
        # Check if we're already in a venv
        elif (venv_path / 'activate').exists():
            return venv_path.parent
    
    # Check parent directory as well
    parent_dir = Path(directory).parent
    for venv in venv_dirs:
        venv_path = parent_dir / venv
        if (venv_path / 'bin' / 'activate').exists():
            return venv_path
    
    return None


def start_process(name, directory, command):
    # Validate command before execution
    valid, msg = validate_command(directory, command)
    if not valid:
        logging.error(f"Invalid command for {name}: {msg}")
        print(f"Error: {msg}")
        return None
    
    venv_path = find_venv(directory)
    if venv_path:
        activate_venv = f"source {venv_path}/bin/activate"
        full_command = f"cd {directory} && {activate_venv} && {command}"
    else:
        full_command = f"cd {directory} && {command}"
    
    try:
        # Start the process in a new session
        process = subprocess.Popen(
            full_command, 
            shell=True, 
            executable='/bin/bash', 
            start_new_session=True,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        # Start a monitor thread for this process
        monitor_thread = threading.Thread(
            target=monitor_and_restart, 
            args=(name, directory, command, process.pid), 
            daemon=True
        )
        monitor_thread.start()
        
        logging.info(f"Started process {name} with PID {process.pid}")
        return process.pid
    except Exception as e:
        logging.error(f"Failed to start process {name}: {e}")
        print(f"Error starting process: {e}")
        return None


def monitor_and_restart(name, directory, command, pid):
    config = load_config()
    process_config = config.get(name, {})
    max_restarts = process_config.get('max_restarts', 5)
    restart_delay = process_config.get('restart_delay', 3)
    restart_count = process_config.get('restart_count', 0)
    
    # Use exponential backoff for restart delays
    current_delay = restart_delay

    while restart_count < max_restarts:
        try:
            # Check if process exists
            if not psutil.pid_exists(pid):
                raise psutil.NoSuchProcess(pid)
                
            # Wait for process to exit
            process = psutil.Process(pid)
            
            # Use polling instead of blocking wait
            while process.is_running():
                time.sleep(1)
            
            # If process exited, restart it
            logging.info(f"Process {name} (PID: {pid}) exited, restarting in {current_delay}s...")
            print(f"Process {name} (PID: {pid}) exited, restarting in {current_delay}s...")
            time.sleep(current_delay)
            
            # Start the process again
            new_pid = start_process(name, directory, command)
            if new_pid is None:
                logging.error(f"Failed to restart process {name}")
                break
                
            # Update the config with new PID and restart count
            config = load_config()
            if name in config:
                restart_count += 1
                config[name]['pid'] = new_pid
                config[name]['restart_count'] = restart_count
                save_config(config)
            
            pid = new_pid
            
            # Increase delay for next restart (exponential backoff)
            current_delay = min(current_delay * 2, 60)  # Cap at 60 seconds
            
        except psutil.NoSuchProcess:
            logging.info(f"Process {name} (PID: {pid}) no longer exists")
            break
        except Exception as e:
            logging.error(f"Error monitoring process {name}: {e}")
            print(f"Error monitoring process {name}: {e}")
            break

    if restart_count >= max_restarts:
        logging.warning(f"Process {name} failed to stay running after {max_restarts} restarts. Giving up.")
        print(f"Process {name} failed to stay running after {max_restarts} restarts. Giving up.")
        
        # Update config to mark process as failed
        config = load_config()
        if name in config:
            config[name]['status'] = 'failed'
            config[name]['pid'] = None
            save_config(config)


def stop_process(pid):
    if pid and psutil.pid_exists(pid):
        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            
            # Wait up to 5 seconds for process to terminate
            for _ in range(5):
                if not psutil.pid_exists(pid):
                    return True
                time.sleep(1)
                
            # If process still exists, send SIGKILL
            if psutil.pid_exists(pid):
                logging.warning(f"Process {pid} did not terminate with SIGTERM, sending SIGKILL")
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                return True
        except (ProcessLookupError, psutil.NoSuchProcess):
            # Process already gone
            return True
        except Exception as e:
            logging.error(f"Error stopping process {pid}: {e}")
            return False
    return True


def create_startup_script(config):
    with open(STARTUP_SCRIPT, 'w') as f:
        f.write("#!/bin/bash\n")
        for name, process in config.items():
            if process.get('autostart', False):
                venv_path = find_venv(process['directory'])
                if venv_path:
                    f.write(f"cd {process['directory']} && source {venv_path}/bin/activate && {process['command']} &\n")
                else:
                    f.write(f"cd {process['directory']} && {process['command']} &\n")
    os.chmod(STARTUP_SCRIPT, 0o755)


def setup_autostart():
    cron_command = f"{CRON_MARKER}\n@reboot {STARTUP_SCRIPT}"
    current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout
    if CRON_MARKER not in current_crontab:
        new_crontab = current_crontab.strip() + f"\n{cron_command}\n"
        subprocess.run(f"echo '{new_crontab}' | crontab -", shell=True)
        print("Set up autostart on system boot")
    else:
        print("Autostart is already set up")


def disable_autostart():
    current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout
    new_crontab = "\n".join([line for line in current_crontab.split("\n") if CRON_MARKER not in line and STARTUP_SCRIPT not in line])
    subprocess.run(f"echo '{new_crontab}' | crontab -", shell=True)
    print("Disabled autostart on system boot")


def save_pid():
    with open(PYPM_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def get_saved_pid():
    if PYPM_PID_FILE.exists():
        with open(PYPM_PID_FILE, 'r') as f:
            return int(f.read().strip())
    return None


def stop_self():
    pid = get_saved_pid()
    if pid and psutil.pid_exists(pid):
        try:
            parent = psutil.Process(pid)
            parent.terminate()
            print(f"PyPM (PID: {pid}) has been stopped.")
        except psutil.NoSuchProcess:
            print("PyPM process not found.")
    else:
        print("No running PyPM process found.")
    if PYPM_PID_FILE.exists():
        PYPM_PID_FILE.unlink()
    sys.exit(0)


def restart_self():
    stop_self()
    time.sleep(1)  # Give the process time to terminate
    start_self()


def start_self():
    pypm_path = Path(sys.executable).parent / 'pypm'
    if pypm_path.exists():
        subprocess.Popen(f"nohup {pypm_path} >/dev/null 2>&1 &", shell=True, start_new_session=True)
        print("PyPM has been started.")
    else:
        print("PyPM executable not found. Please ensure it's installed correctly.")

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(sig, frame):
        logging.info(f"Received signal {sig}, shutting down gracefully")
        print(f"Received signal {sig}, shutting down gracefully")
        
        # Stop all managed processes
        config = load_config()
        for name, process in config.items():
            pid = process.get('pid')
            if pid and psutil.pid_exists(pid):
                print(f"Stopping process {name} (PID: {pid})")
                stop_process(pid)
                config[name]['pid'] = None
        
        save_config(config)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    save_pid()  # Save the PID when PyPM starts
    setup_signal_handlers()  # Set up signal handlers
    config = load_config()

    if len(sys.argv) < 2:
        print("Usage: pypm [list|start|stop|restart|delete|save|startup|disable-startup|stop-self|restart-self|start-self|enable|disable]")
        return

    action = sys.argv[1]

    if action == 'list':
        list_processes(config)
    elif action == 'start':
        if len(sys.argv) < 4:  # Require command parameter
            print("Usage: pypm start <name> <command>")
            return
        
        name = sys.argv[2]
        directory = os.getcwd()
        command = ' '.join(sys.argv[3:])
        
        # Validate process name
        if name in config:
            print(f"Process '{name}' already exists. Use a different name or delete the existing process first.")
            return
        
        valid_name, name_msg = validate_process_name(name)
        if not valid_name:
            print(f"Error: {name_msg}")
            return
        
        pid = start_process(name, directory, command)
        if pid:
            config[name] = {
                'command': command, 
                'pid': pid, 
                'directory': directory,
                'max_restarts': 5,  # Default value
                'restart_delay': 3,  # Default value
                'restart_count': 0,
                'created_at': time.time()
            }
            save_config(config)
            print(f"Started {name} with PID {pid}")
    elif action in ['stop', 'delete']:
        if len(sys.argv) < 3:
            print(f"Usage: pypm {action} <name|all>")
            return
        
        target = sys.argv[2]
        if target == 'all':
            for name in list(config.keys()):
                pid = config[name].get('pid')
                if pid:
                    if stop_process(pid):
                        if action == 'delete':
                            del config[name]
                            print(f"Deleted {name}")
                            logging.info(f"Deleted process {name}")
                        else:
                            config[name]['pid'] = None
                            print(f"Stopped {name}")
                            logging.info(f"Stopped process {name}")
                    else:
                        print(f"Failed to stop {name}")
                        logging.error(f"Failed to stop process {name}")
        elif target in config:
            pid = config[target].get('pid')
            if pid:
                if stop_process(pid):
                    if action == 'delete':
                        del config[target]
                        print(f"Deleted {target}")
                        logging.info(f"Deleted process {target}")
                    else:
                        config[target]['pid'] = None
                        print(f"Stopped {target}")
                        logging.info(f"Stopped process {target}")
                else:
                    print(f"Failed to stop {target}")
                    logging.error(f"Failed to stop process {target}")
            else:
                if action == 'delete':
                    del config[target]
                    print(f"Deleted {target}")
                    logging.info(f"Deleted process {target}")
                else:
                    print(f"{target} is already stopped")
        else:
            print(f"Process {target} not found")
        
        save_config(config)
    elif action == 'restart':
        if len(sys.argv) < 3:
            print(f"Usage: pypm {action} <name|all>")
            return
        
        target = sys.argv[2]
        if target == 'all':
            for name in list(config.keys()):
                pid = config[name].get('pid')
                if pid:
                    if stop_process(pid):
                        print(f"Stopped {name}, restarting...")
                        time.sleep(2)  # Shorter delay
                        new_pid = start_process(name, config[name]['directory'], config[name]['command'])
                        if new_pid:
                            config[name]['pid'] = new_pid
                            config[name]['restart_count'] = config[name].get('restart_count', 0) + 1
                            print(f"Restarted {name} with PID {new_pid}")
                            logging.info(f"Restarted process {name} with PID {new_pid}")
                        else:
                            print(f"Failed to restart {name}")
                            logging.error(f"Failed to restart process {name}")
                    else:
                        print(f"Failed to stop {name} for restart")
                        logging.error(f"Failed to stop process {name} for restart")
        elif target in config:
            pid = config[target].get('pid')
            if pid:
                if stop_process(pid):
                    print(f"Stopped {target}, restarting...")
                    time.sleep(2)  # Shorter delay
                    new_pid = start_process(target, config[target]['directory'], config[target]['command'])
                    if new_pid:
                        config[target]['pid'] = new_pid
                        config[target]['restart_count'] = config[target].get('restart_count', 0) + 1
                        print(f"Restarted {target} with PID {new_pid}")
                        logging.info(f"Restarted process {target} with PID {new_pid}")
                    else:
                        print(f"Failed to restart {target}")
                        logging.error(f"Failed to restart process {target}")
                else:
                    print(f"Failed to stop {target} for restart")
                    logging.error(f"Failed to stop process {target} for restart")
            else:
                # Process is already stopped, just start it
                new_pid = start_process(target, config[target]['directory'], config[target]['command'])
                if new_pid:
                    config[target]['pid'] = new_pid
                    config[target]['restart_count'] = config[target].get('restart_count', 0) + 1
                    print(f"Started {target} with PID {new_pid}")
                    logging.info(f"Started process {target} with PID {new_pid}")
                else:
                    print(f"Failed to start {target}")
                    logging.error(f"Failed to start process {target}")
        else:
            print(f"Process {target} not found")
        
        save_config(config)
    elif action == 'config':
        if len(sys.argv) < 4:
            print("Usage: pypm config <name> <key> <value>")
            return
        
        name = sys.argv[2]
        if name not in config:
            print(f"Process {name} not found")
            return
            
        key = sys.argv[3]
        value = sys.argv[4]
        
        # Convert value to appropriate type
        if key in ['max_restarts', 'restart_delay']:
            try:
                value = int(value)
            except ValueError:
                print(f"Value for {key} must be a number")
                return
        
        # Update config
        config[name][key] = value
        save_config(config)
        print(f"Updated {key} to {value} for process {name}")
        logging.info(f"Updated {key} to {value} for process {name}")
    
    elif action == 'status':
        # Show PyPM status
        pid = get_saved_pid()
        if pid and psutil.pid_exists(pid):
            print(f"PyPM is running with PID {pid}")
            print(f"Log file: {LOG_FILE}")
            print(f"Config file: {CONFIG_FILE}")
            print(f"Startup script: {STARTUP_SCRIPT}")
            
            # Check if autostart is enabled
            current_crontab = subprocess.run("crontab -l", shell=True, capture_output=True, text=True).stdout
            if PYPM_AUTOSTART_MARKER in current_crontab:
                print("PyPM autostart: Enabled")
            else:
                print("PyPM autostart: Disabled")
                
            if CRON_MARKER in current_crontab:
                print("Process autostart: Enabled")
            else:
                print("Process autostart: Disabled")
        else:
            print("PyPM is not running")
    
    elif action == 'save':
        for name, process in config.items():
            process['autostart'] = True
        save_config(config)
        create_startup_script(config)
        print("Saved current process list for autostart")
        logging.info("Saved current process list for autostart")
    elif action == 'startup':
        setup_autostart()
        logging.info("Set up autostart on system boot")
    elif action == 'disable-startup':
        disable_autostart()
        logging.info("Disabled autostart on system boot")
    elif action == 'stop-self':
        logging.info("Stopping PyPM")
        stop_self()
    elif action == 'restart-self':
        logging.info("Restarting PyPM")
        restart_self()
    elif action == 'start-self':
        logging.info("Starting PyPM")
        start_self()
    elif action == 'enable':
        enable_pypm_autostart()
        logging.info("Enabled PyPM autostart")
    elif action == 'disable':
        disable_pypm_autostart()
        logging.info("Disabled PyPM autostart")
    else:
        print("Unknown action. Use list, start, stop, restart, delete, save, startup, disable-startup, stop-self, restart-self, start-self, enable, disable, config, or status.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)
