#!/bin/bash

# PyPM Installation Script

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit
fi

# Prompt for the username
read -p "Enter the username to install PyPM for: " USERNAME

# Check if user exists
if ! id "$USERNAME" &>/dev/null; then
    echo "User $USERNAME does not exist. Please create the user first."
    exit 1
fi

# Install system dependencies
command -v wget >/dev/null 2>&1 || { echo "wget is required but not installed. Installing wget..."; apt install -y wget; }
apt update
apt install -y python3-pip python3-venv

# Create directory for PyPM
USER_HOME="/home/$USERNAME"
PYPM_DIR="$USER_HOME/.pypm"
LOCAL_BIN_DIR="$USER_HOME/.local/bin"
mkdir -p "$PYPM_DIR"
mkdir -p "$LOCAL_BIN_DIR"

# Create virtual environment and install dependencies
python3 -m venv "$PYPM_DIR/venv"
chown -R $USERNAME:$USERNAME "$PYPM_DIR"
su - $USERNAME -c "$PYPM_DIR/venv/bin/pip install --user psutil"

# Download PyPM script
if ! wget https://raw.githubusercontent.com/SiliconSquire/pypm/main/pypm.py -O "$PYPM_DIR/pypm.py"; then
    echo "Failed to download PyPM script"
    exit 1
fi
chmod +x "$PYPM_DIR/pypm.py"

# Create wrapper script
cat > "$LOCAL_BIN_DIR/pypm" << EOF
#!/bin/bash
$PYPM_DIR/venv/bin/python $PYPM_DIR/pypm.py "\$@"
EOF

chmod +x "$LOCAL_BIN_DIR/pypm"

# Create .bashrc if it doesn't exist
if [ ! -f "$USER_HOME/.bashrc" ]; then
    touch "$USER_HOME/.bashrc"
    chown $USERNAME:$USERNAME "$USER_HOME/.bashrc"
fi

# Add to PATH if not already there
if ! grep -q "$LOCAL_BIN_DIR" "$USER_HOME/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$USER_HOME/.bashrc"
fi

# Set correct ownership
chown -R $USERNAME:$USERNAME "$PYPM_DIR"
chown -R $USERNAME:$USERNAME "$LOCAL_BIN_DIR"

echo "PyPM has been installed for user $USERNAME."
echo "Please ask $USERNAME to log out and log back in, or run 'source ~/.bashrc' to update their PATH."
echo "They can then use PyPM by simply typing 'pypm' followed by commands."

# Usage guide
cat << EOF

Usage Guide for PyPM:

1. Start a new process:
   pypm start myapp "python3 app.py"

2. List all processes:
   pypm list

3. Stop a process:
   pypm stop myapp

4. Restart a process:
   pypm restart myapp

5. Delete a process from PyPM:
   pypm delete myapp

6. Save current processes for autostart:
   pypm save

7. Set up autostart on system boot:
   pypm startup

For more information, run 'pypm' without any arguments.
EOF
