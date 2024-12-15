import subprocess
import os
import sys
import json
import signal
import psutil
import time
from pathlib import Path
import threading

CONFIG_FILE = Path.home() / '.pypm_config.json'
STARTUP_SCRIPT = Path.home() / '.pypm_startup.sh'
CRON_MARKER = "# PyPM autostart entry"
PYPM_PID_FILE = Path.home() / '.pypm_pid'
PYPM_AUTOSTART_MARKER = "# PyPM self-start entry"


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

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def list_processes(config):
    if not config:
        print("No processes are currently being managed by PyPM")
        return
        
    for name, process in config.items():
        pid = process.get('pid')
        if pid is not None and psutil.pid_exists(pid):
            p = psutil.Process(pid)
            status = "RUNNING" if p.is_running() else "STOPPED"
            cpu = p.cpu_percent()
            memory = p.memory_info().rss / 1024 / 1024  # Convert to MB
            print(f"{name:<20} {status:<10} PID: {pid:<6} CPU: {cpu:.1f}% MEM: {memory:.1f}MB")
        else:
            print(f"{name:<20} STOPPED    PID: N/A")


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
    venv_path = find_venv(directory)
    if venv_path:
        activate_venv = f"source {venv_path}/bin/activate"
        full_command = f"cd {directory} && {activate_venv} && {command}"
    else:
        full_command = f"cd {directory} && {command}"
    
    # Start the process in a new session
    process = subprocess.Popen(full_command, shell=True, executable='/bin/bash', start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Start a monitor thread for this process
    monitor_thread = threading.Thread(target=monitor_and_restart, args=(name, directory, command, process.pid), daemon=True)
    monitor_thread.start()
    
    return process.pid


def monitor_and_restart(name, directory, command, pid):
    max_restarts = 5
    restart_count = 0
    restart_delay = 3  # seconds

    while restart_count < max_restarts:
        try:
            # Wait for process to exit
            process = psutil.Process(pid)
            process.wait()
            
            # If process exited, restart it
            print(f"Process {name} (PID: {pid}) exited, restarting...")
            time.sleep(restart_delay)
            
            # Start the process again
            new_pid = start_process(name, directory, command)
            
            # Update the config with new PID
            config = load_config()
            if name in config:
                config[name]['pid'] = new_pid
                save_config(config)
            
            restart_count += 1
            pid = new_pid
            
        except psutil.NoSuchProcess:
            break
        except Exception as e:
            print(f"Error monitoring process {name}: {e}")
            break

    if restart_count >= max_restarts:
        print(f"Process {name} failed to stay running after {max_restarts} restarts. Giving up.")


def stop_process(pid):
    if pid and psutil.pid_exists(pid):
        os.killpg(os.getpgid(pid), signal.SIGTERM)


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

def main():
    save_pid()  # Save the PID when PyPM starts
    config = load_config()

    if len(sys.argv) < 2:
        print("Usage: pypm [list|start|stop|restart|delete|save|startup|disable-startup|stop-self|restart-self|start-self]")
        return

    action = sys.argv[1]

    if action == 'list':
        list_processes(config)
    elif action == 'start':
        if len(sys.argv) < 3:
            print("Usage: pypm start <name> [command]")
            return
        name = sys.argv[2]
        if name in config:
            directory = config[name]['directory']
            command = config[name]['command']
        else:
            directory = os.getcwd()
            command = ' '.join(sys.argv[3:])
        pid = start_process(name, directory, command)
        config[name] = {'command': command, 'pid': pid, 'directory': directory}
        save_config(config)
        print(f"Started {name} with PID {pid}")
    elif action in ['stop', 'delete']:
        if len(sys.argv) < 3:
            print(f"Usage: pypm {action} <name|all>")
            return
        target = sys.argv[2]
        if target == 'all':
            for name in list(config.keys()):
                stop_process(config[name]['pid'])
                if action == 'delete':
                    del config[name]
                    print(f"Deleted {name}")
                else:
                    config[name]['pid'] = None
                    print(f"Stopped {name}")
        elif target in config:
            stop_process(config[target]['pid'])
            if action == 'delete':
                del config[target]
                print(f"Deleted {target}")
            else:
                config[target]['pid'] = None
                print(f"Stopped {target}")
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
                stop_process(config[name]['pid'])
                time.sleep(5)  # Add a 5-second delay
                pid = start_process(name, config[name]['directory'], config[name]['command'])
                config[name]['pid'] = pid
                print(f"Restarted {name} with PID {pid}")
        elif target in config:
            stop_process(config[target]['pid'])
            time.sleep(5)  # Add a 5-second delay
            pid = start_process(target, config[target]['directory'], config[target]['command'])
            config[target]['pid'] = pid
            print(f"Restarted {target} with PID {pid}")
        else:
            print(f"Process {target} not found")
        save_config(config)
    elif action == 'save':
        for name, process in config.items():
            process['autostart'] = True
        save_config(config)
        create_startup_script(config)
        print("Saved current process list for autostart")
    elif action == 'startup':
        setup_autostart()
    elif action == 'disable-startup':
        disable_autostart()
    elif action == 'stop-self':
        stop_self()
    elif action == 'restart-self':
        restart_self()
    elif action == 'start-self':
        start_self()
    elif action == 'enable':
        enable_pypm_autostart()
    elif action == 'disable':
        disable_pypm_autostart()
    else:
        print("Unknown action. Use list, start, stop, restart, delete, save, startup, disable-startup, stop-self, restart-self, start-self, enable, or disable.")


if __name__ == "__main__":
    main()
