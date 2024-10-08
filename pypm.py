import subprocess
import os
import sys
import json
import signal
import psutil
from pathlib import Path

CONFIG_FILE = Path.home() / '.pypm_config.json'
STARTUP_SCRIPT = Path.home() / '.pypm_startup.sh'

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def list_processes(config):
    for name, process in config.items():
        if psutil.pid_exists(process['pid']):
            p = psutil.Process(process['pid'])
            status = "RUNNING" if p.is_running() else "STOPPED"
            cpu = p.cpu_percent()
            memory = p.memory_info().rss / 1024 / 1024  # Convert to MB
            print(f"{name:<20} {status:<10} PID: {process['pid']:<6} CPU: {cpu:.1f}% MEM: {memory:.1f}MB")
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
    
    process = subprocess.Popen(full_command, shell=True, executable='/bin/bash', start_new_session=True)
    return process.pid

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
    cron_command = f"@reboot {STARTUP_SCRIPT}"
    subprocess.run(f"(crontab -l 2>/dev/null; echo \"{cron_command}\") | crontab -", shell=True)

def main():
    config = load_config()

    if len(sys.argv) < 2:
        print("Usage: python process_manager.py [list|start|stop|restart|delete|save|startup]")
        return

    action = sys.argv[1]

    if action == 'list':
        list_processes(config)
    elif action == 'start':
        if len(sys.argv) < 3:
            print("Usage: python process_manager.py start <name> [command]")
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
    elif action in ['stop', 'restart', 'delete']:
        if len(sys.argv) < 3:
            print(f"Usage: python process_manager.py {action} <name|all>")
            return
        target = sys.argv[2]
        if target == 'all':
            for name in list(config.keys()):
                stop_process(config[name]['pid'])
                if action == 'restart':
                    pid = start_process(name, config[name]['directory'], config[name]['command'])
                    config[name]['pid'] = pid
                    print(f"Restarted {name} with PID {pid}")
                elif action == 'delete':
                    del config[name]
                    print(f"Deleted {name}")
                else:
                    config[name]['pid'] = None
                    print(f"Stopped {name}")
        elif target in config:
            stop_process(config[target]['pid'])
            if action == 'restart':
                pid = start_process(target, config[target]['directory'], config[target]['command'])
                config[target]['pid'] = pid
                print(f"Restarted {target} with PID {pid}")
            elif action == 'delete':
                del config[target]
                print(f"Deleted {target}")
            else:
                config[target]['pid'] = None
                print(f"Stopped {target}")
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
        print("Set up autostart on system boot")
    else:
        print("Unknown action. Use list, start, stop, restart, delete, save, or startup.")

if __name__ == "__main__":
    main()
