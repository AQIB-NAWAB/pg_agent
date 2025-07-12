import os
import subprocess
import sys
from pathlib import Path

def open_in_editor(file_path: Path):
    """
    Opens a file in an editor with a smart, cross-platform strategy.
    It prioritizes VS Code but has safe fallbacks.
    """
    # The --wait flag is crucial. It tells the 'code' command to pause the script
    # until the user saves and closes the file tab in VS Code.
    editor_commands = [
        # 1. Highest Priority: The EDITOR environment variable, which VS Code's
        #    integrated terminal often sets correctly.
        os.environ.get('EDITOR'),
        
        # 2. Second Priority: The standard 'code' command with the --wait flag.
        #    This works if the user has installed 'code' in their system's PATH.
        "code --wait",
    ]

    # Try the editor commands in order of priority
    for command_str in editor_commands:
        if command_str:
            try:
                # We use shell=True for Windows compatibility and to handle commands with arguments
                print(f"Attempting to open editor with command: '{command_str}'...")
                subprocess.run(f'{command_str} "{file_path}"', shell=True, check=True)
                # If the command succeeds, we are done.
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                # This command failed, try the next one in the list.
                print(f"Command '{command_str}' failed. Trying next option...")
                continue

    # --- Failsafe Fallback ---
    # If all preferred methods fail, fall back to the OS default.
    print("Could not find a configured editor. Falling back to system default.")
    try:
        if sys.platform == "win32":
            os.startfile(file_path)
        elif sys.platform == "darwin": # macOS
            subprocess.run(["open", str(file_path)], check=True)
        else: # Linux
            subprocess.run(["xdg-open", str(file_path)], check=True)
    except Exception as e:
        # If even the fallback fails, provide manual instructions.
        print(f"\nFATAL: Could not open any editor: {e}")
        print("Please manually open the following file, add your notes, save, and close it.")
        print(f"File path: {file_path.resolve()}")
        input("Press Enter to continue after you have saved and closed the file...")
