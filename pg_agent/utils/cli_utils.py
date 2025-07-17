import os
import json
import subprocess
import sys
from pathlib import Path

def open_in_editor(file_path: Path):
    """
    Opens a file in an editor with a smart, cross-platform strategy.
    It reads from 'pg_agent_settings.json' to determine the editor.
    """
    editor_command = "system_default"
    settings_path = Path.cwd() / "pg_agent_settings.json"

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            editor_command = settings.get("default_editor", "system_default")
        except json.JSONDecodeError:
            print(f"Warning: Could not parse {settings_path}. Using system default editor.")

    print(f"Opening {file_path.name} for your review...")

    try:
        if editor_command == "system_default":
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin": # macOS
                subprocess.run(["open", str(file_path)], check=True)
            else: # Linux
                subprocess.run(["xdg-open", str(file_path)], check=True)
            # After launching the non-blocking default editor, wait for user confirmation
            input("\nPress Enter to continue after you have saved and closed the editor...")
        else:
            # Use the user-specified command (e.g., "code --wait")
            print(f"(Using custom editor command: '{editor_command}')")
            # The command itself is not quoted, only the file path.
            subprocess.run(f'{editor_command} "{file_path}"', shell=True, check=True)
            
    except Exception as e:
        print(f"\nError opening editor '{editor_command}': {e}")
        print("Please manually open the file, add your notes, save, and close it.")
        print(f"File path: {file_path.resolve()}")
        input("Press Enter to continue after you have saved and closed the file...") 