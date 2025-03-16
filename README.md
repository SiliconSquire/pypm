# PyPM (Python Process Manager) Installation and Usage Guide
## REQUIREMENT: Debian based system (Tested on Debian 12.x)
## Installation

1. Download the installation script:
   ```
   wget https://raw.githubusercontent.com/SiliconSquire/pypm/main/install_pypm.sh
   ```

2. Make the script executable:
   ```
   chmod +x install_pypm.sh
   ```

3. Run the installation script as root:
   ```
   sudo ./install_pypm.sh
   ```

4. When prompted, enter the username for which you want to install PyPM.

5. The script will install all necessary dependencies, set up PyPM for the specified user, and enable PyPM to start automatically on system boot.

## Usage

After installation, the specified user can use PyPM with the following commands:

1. Start a new process:
   ```
   pypm start <process_name> "<command>"
   ```
   Example: `pypm start myapp "python3 app.py"` (py script must be in the same folder as the venv)
   
   Note: PyPM now validates that the Python script exists before starting the process.

2. List all managed processes:
   ```
   pypm list
   ```
   The list command now shows more detailed information including CPU usage, memory usage, and restart count.

3. Stop a process:
   ```
   pypm stop <process_name>
   ```

4. Restart a process:
   ```
   pypm restart <process_name>
   ```

5. Delete a process from PyPM management:
   ```
   pypm delete <process_name>
   ```

6. Save current processes for autostart:
   ```
   pypm save
   ```

7. Set up autostart for managed processes on system boot:
   ```
   pypm startup
   ```

8. Disable autostart for managed processes:
   ```
   pypm disable-startup
   ```

9. Stop PyPM itself:
   ```
   pypm stop-self
   ```

10. Restart PyPM:
    ```
    pypm restart-self
    ```

11. Enable PyPM autostart (already done during installation):
    ```
    pypm enable
    ```

12. Disable PyPM autostart:
    ```
    pypm disable
    ```

13. Configure process settings:
    ```
    pypm config <process_name> <key> <value>
    ```
    Example: `pypm config myapp max_restarts 10`
    
    Available settings:
    - `max_restarts`: Maximum number of restart attempts (default: 5)
    - `restart_delay`: Initial delay in seconds between restarts (default: 3)

14. Check PyPM status:
    ```
    pypm status
    ```
    Shows information about PyPM including PID, log file location, and autostart status.

## Managing Multiple Processes

You can manage multiple processes easily. Here's an example workflow:

```bash
cd /path/to/app1
pypm start app1 "python3 app1.py"

cd /path/to/app2
pypm start app2 "python3 app2.py"

pypm list  # View all running processes

pypm save  # Save current processes for autostart
pypm startup  # Set up autostart for managed processes on system boot
```

## Features

- **Virtual Environment Support**: PyPM automatically detects and uses virtual environments if they exist in your project directory.
- **Background Execution**: Processes started with PyPM run in the background, allowing you to continue using your terminal.
- **Autostart Capability**: The `pypm save` and `pypm startup` commands ensure your managed processes start automatically after system reboot.
- **Process Monitoring**: PyPM monitors processes and automatically restarts them if they crash, with exponential backoff.
- **Resource Usage Tracking**: The `pypm list` command shows CPU and memory usage for each process.
- **Logging**: PyPM now logs all actions to `~/.pypm.log` for better troubleshooting.
- **Graceful Shutdown**: PyPM handles signals properly to ensure clean shutdown of managed processes.
- **Process Validation**: PyPM validates process names and commands before execution to prevent errors.
- **Configurable Settings**: Process settings like restart limits can be configured with the `pypm config` command.

## Transitioning from systemd

If you're transitioning from systemd to PyPM, you can remove old systemd services with these commands (run as root):

```bash
systemctl stop service1.service service2.service service3.service
systemctl disable service1.service service2.service service3.service
rm /etc/systemd/system/{service1.service,service2.service,service3.service}
systemctl daemon-reload
```

Replace `service1`, `service2`, etc., with your actual service names.

## Troubleshooting

If you encounter any issues:
1. Check the log file at `~/.pypm.log` for detailed error messages.
2. Ensure the user has the necessary permissions to run the processes.
3. Check the project directory for a virtual environment if your Python app requires specific dependencies.
4. Verify that all required Python packages are installed in the project's virtual environment.
5. If PyPM isn't starting automatically on boot, check its status with `pypm status` and re-enable if necessary.
6. For issues with managed processes not starting, check the autostart configuration with `pypm startup`.
7. Make sure your Python scripts exist in the specified directory before starting them.

For any persistent problems or feature requests, please open an issue on the GitHub repository.
