# PyPM (Python Process Manager BETA) Installation and Usage Guide

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

5. The script will install all necessary dependencies and set up PyPM for the specified user.

## Usage

After installation, the specified user can use PyPM with the following commands:

1. Start a new process:
   ```
   pypm start <process_name> "<command>"
   ```
   Example: `pypm start myapp "python3 app.py"`

2. List all managed processes:
   ```
   pypm list
   ```

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

7. Set up autostart on system boot:
   ```
   pypm startup
   ```

## Managing Multiple Processes

You can manage multiple processes easily. Here's an example workflow:

```bash
cd /path/to/app1
pypm start app1 "python3 app1.py"

cd /path/to/app2
pypm start app2 "python3 app2.py"

pypm list  # View all running processes

pypm save  # Save current processes for autostart
pypm startup  # Set up autostart on system boot
```

## Notes

- PyPM automatically detects and uses virtual environments if they exist in your project directory.
- Processes started with PyPM run in the background, allowing you to continue using your terminal.
- The `pypm save` and `pypm startup` commands ensure your processes start automatically after system reboot.
- PyPM doesn't need to run continuously to manage processes, making it resource-efficient.

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
1. Ensure the user has the necessary permissions to run the processes.
2. Check the project directory for a virtual environment if your Python app requires specific dependencies.
3. Verify that all required Python packages are installed in the project's virtual environment.
