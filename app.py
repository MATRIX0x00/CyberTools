#
# Filename: app.py
# Description: This file contains the backend Flask application with SocketIO
# for the Multi-Tool Web GUI. It has been modified to support multiple tools
# by dynamically loading their configurations from JSON files, and now
# includes configurable paths for 'commands' and 'notes'.
#
import os
import subprocess
import threading
import shlex
import json
import uuid
import shutil
import sys
import time
import requests
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room
from werkzeug.utils import secure_filename
from datetime import datetime
import atexit

# Attempt to import pty and tty, which are Unix-specific
try:
    import pty
    import tty
    UNIX_SYSTEM = True
except ImportError:
    UNIX_SYSTEM = False
    print("Warning: pty and tty modules not found. Assuming Windows system.")

# Flask and SocketIO initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key'
socketio = SocketIO(app)

# --- Global State for Multiple Sessions ---
# A nested dictionary: sessions[sid][terminalId] -> {process info}
sessions = {}

# --- Global State for Scheduled Tasks ---
scheduled_tasks = {}
TASKS_FILE = 'tasks.json'
daily_tasks_schedule = {}

# Directories for tool configuration and data
TOOLS_FOLDER = 'tools'
EXAMPLES_FOLDER = 'examples'
INSTALL_FOLDER = 'install'
OUTPUT_FOLDER = 'output'
NOTES_FOLDER_DEFAULT_NAME = 'notes'
COMMANDS_FOLDER_DEFAULT_NAME = 'commands'

# --- Path Management Setup (UPDATED FOR MULTI-PATH) ---
PATHS_FILE = 'paths.json'

# Default paths are now lists of strings (raw input from user/file)
DEFAULT_PATHS = {
    'commands_folder': [COMMANDS_FOLDER_DEFAULT_NAME],
    'notes_folder': [NOTES_FOLDER_DEFAULT_NAME]
}
path_config = DEFAULT_PATHS.copy()

# A separate structure to store the resolved, absolute paths for internal use
resolved_paths = DEFAULT_PATHS.copy()


def load_paths():
    """Loads path configurations from paths.json and updates global config."""
    global path_config, resolved_paths
    
    # Reset to defaults
    path_config = DEFAULT_PATHS.copy()
    
    if os.path.exists(PATHS_FILE):
        try:
            with open(PATHS_FILE, 'r') as f:
                loaded_paths = json.load(f)
                
                for key in DEFAULT_PATHS:
                    if key in loaded_paths:
                        # Handle both old single-string format and new list format
                        if isinstance(loaded_paths[key], list):
                            path_config[key] = [p for p in loaded_paths[key] if p] # Filter out empty strings
                        elif isinstance(loaded_paths[key], str):
                            path_config[key] = [loaded_paths[key]]
                        
                        # Ensure we don't end up with an empty list if loading a broken file
                        if not path_config[key]:
                             path_config[key] = DEFAULT_PATHS[key]
                
                print(f"Loaded configurable raw paths: {path_config}")
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading paths from {PATHS_FILE}: {e}. Using defaults.")

    # Resolve all configured paths to absolute paths for internal use and ensure they exist
    resolved_paths = {}
    for key in DEFAULT_PATHS:
        resolved_paths[key] = []
        for path in path_config[key]:
            # Resolve to absolute path
            full_path = path if os.path.isabs(path) else os.path.abspath(os.path.join(os.getcwd(), path))
            
            # Ensure the directory exists
            try:
                if not os.path.exists(full_path):
                    os.makedirs(full_path, exist_ok=True)
                    print(f"Created directory: {full_path}")
                resolved_paths[key].append(full_path)
            except Exception as e:
                print(f"Warning: Could not create directory {full_path} for key {key}: {e}. Skipping this path.")
                
        # Critical check: if all paths for a key failed, restore the default path
        if not resolved_paths[key]:
            default_path = os.path.abspath(os.path.join(os.getcwd(), DEFAULT_PATHS[key][0]))
            os.makedirs(default_path, exist_ok=True)
            resolved_paths[key].append(default_path)
            path_config[key] = DEFAULT_PATHS[key]
            print(f"Restored default path for {key}: {default_path}")


def save_paths():
    """Saves the current raw path configurations (list of strings) to paths.json."""
    try:
        # Save only the raw path_config structure
        with open(PATHS_FILE, 'w') as f:
            json.dump(path_config, f, indent=4)
        print(f"Successfully saved paths to '{PATHS_FILE}'.")
        
        # Reload immediately to re-resolve/validate and update the resolved_paths structure
        load_paths()
    except IOError as e:
        print(f"Error saving paths to {PATHS_FILE}: {e}")

def resolve_file_path_by_folder_name(filename_with_folder):
    """
    Takes a string like 'commands/file.txt' and returns the absolute path
    by checking all configured and resolved paths for the folder type.
    """
    normalized_path = os.path.normpath(filename_with_folder)
    parts = normalized_path.split(os.sep)

    if len(parts) >= 2:
        folder_name_check = parts[0]
        file_name = os.sep.join(parts[1:])
        
        config_key = None
        if folder_name_check == COMMANDS_FOLDER_DEFAULT_NAME:
            config_key = 'commands_folder'
        elif folder_name_check == NOTES_FOLDER_DEFAULT_NAME:
            config_key = 'notes_folder'
        
        if config_key and config_key in resolved_paths:
            # Check all resolved paths for the file
            for base_path in resolved_paths[config_key]:
                # Prevent path traversal outside of the configured directory
                full_file_path = os.path.abspath(os.path.join(base_path, file_name))
                
                # Check if the resolved path starts with the base_path to ensure it's inside
                if full_file_path.startswith(base_path + os.sep) or full_file_path == base_path:
                    if os.path.exists(full_file_path):
                        # Found the file in one of the configured paths
                        return full_file_path
            
    # Fallback for all other file paths (like output/, etc.)
    return os.path.abspath(os.path.join(os.getcwd(), filename_with_folder))

# --- Initial folder setup is now done inside load_paths() to use configurable paths ---
# We keep OUTPUT_FOLDER setup here as it is not configurable
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)

# Global dictionaries to store loaded configurations
ALL_TOOLS = {}
ALL_EXAMPLES = {}
ALL_INSTALLATIONS = {}

def load_tool_configurations():
    """
    Loads tool, example, and installation configurations from their respective folders.
    This function populates the global dictionaries for use by the application.
    """
    global ALL_TOOLS, ALL_EXAMPLES, ALL_INSTALLATIONS
    ALL_TOOLS = {}
    ALL_EXAMPLES = {}
    ALL_INSTALLATIONS = {}

    print("Loading tool configurations...")
    # ... (rest of load_tool_configurations remains unchanged) ...

    # Load tool JSON files
    if os.path.exists(TOOLS_FOLDER):
        for filename in os.listdir(TOOLS_FOLDER):
            if filename.endswith('.json'):
                tool_name = filename.replace('.json', '')
                try:
                    with open(os.path.join(TOOLS_FOLDER, filename), 'r', encoding='utf-8') as f:
                        tool_data = json.load(f)
                        ALL_TOOLS[tool_name] = tool_data
                        print(f"Loaded tool: {tool_name}")
                except json.JSONDecodeError:
                    print(f"Error: Could not decode JSON from '{filename}' in '{TOOLS_FOLDER}'.")
    else:
        print(f"Warning: The '{TOOLS_FOLDER}' folder was not found.")

    # Load example JSON files
    if os.path.exists(EXAMPLES_FOLDER):
        for filename in os.listdir(EXAMPLES_FOLDER):
            if filename.endswith('.json'):
                tool_name = filename.replace('.json', '')
                try:
                    with open(os.path.join(EXAMPLES_FOLDER, filename), 'r', encoding='utf-8') as f:
                        example_data = json.load(f)
                        ALL_EXAMPLES[tool_name] = example_data
                        print(f"Loaded examples for: {tool_name}")
                except json.JSONDecodeError:
                    print(f"Error: Could not decode JSON from '{filename}' in '{EXAMPLES_FOLDER}'.")
    else:
        print(f"Warning: The '{EXAMPLES_FOLDER}' folder was not found.")

    # Load installation JSON files
    if os.path.exists(INSTALL_FOLDER):
        for filename in os.listdir(INSTALL_FOLDER):
            if filename.endswith('.json'):
                tool_name = filename.replace('.json', '')
                try:
                    with open(os.path.join(INSTALL_FOLDER, filename), 'r', encoding='utf-8') as f:
                        install_data = json.load(f)
                        ALL_INSTALLATIONS[tool_name] = install_data
                        print(f"Loaded installation for: {tool_name}")
                except json.JSONDecodeError:
                    print(f"Error: Could not decode JSON from '{filename}' in '{INSTALL_FOLDER}'.")
    else:
        print(f"Warning: The '{INSTALL_FOLDER}' folder was not found.")


def run_scheduled_task(task_id):
# ... (rest of run_scheduled_task remains unchanged) ...
    """
    Function to be executed by the timer for a scheduled task.
    """
    if task_id in scheduled_tasks:
        task = scheduled_tasks[task_id]
        sid = task['sid']
        tool = task['tool']
        command = task['command']
        terminalId = task['terminalId']
        print(f"Executing scheduled task {task_id} in terminal {terminalId} for client {sid}: {tool} - {command}")
        
        if sid in sessions and terminalId in sessions[sid]:
            execute_command_in_session(sid, terminalId, command)
            socketio.emit('task_completed', {'taskId': task_id, 'message': f'Task {task_id} has been completed.'}, room=sid, namespace='/')
        else:
            print(f"Warning: Session {sid} or terminal {terminalId} for task {task_id} is no longer active. Task will not run.")
            
        status = task.get('status', 'once')
        if status == 'once':
            if task_id in scheduled_tasks:
                del scheduled_tasks[task_id]
            save_tasks()
        elif status == 'daily':
            schedule_time = datetime.fromisoformat(task['schedule_time'])
            next_run_time = schedule_time.replace(day=schedule_time.day + 1)
            
            delay_seconds = (next_run_time - datetime.now()).total_seconds()
            if delay_seconds < 0:
                next_run_time = next_run_time.replace(day=next_run_time.day + 1)
                delay_seconds = (next_run_time - datetime.now()).total_seconds()

            timer = threading.Timer(delay_seconds, run_scheduled_task, args=[task_id])
            timer.daemon = True
            timer.start()
            scheduled_tasks[task_id]['timer'] = timer
            scheduled_tasks[task_id]['schedule_time'] = next_run_time.isoformat()
            save_tasks()
        
    else:
        print(f"Task {task_id} not found in scheduled_tasks. It may have already been executed and removed.")

def load_tasks():
# ... (rest of load_tasks remains unchanged) ...
    """
    Loads scheduled tasks from the tasks.json file and re-schedules future tasks.
    """
    global scheduled_tasks
    if os.path.exists(TASKS_FILE):
        try:
            with open(TASKS_FILE, 'r') as f:
                tasks_data = json.load(f)
            
            scheduled_tasks = {}
            for task_data in tasks_data:
                task_id = task_data['id']
                schedule_time_str = task_data['schedule_time']
                
                # We can't automatically re-associate SIDs as they change on every connection.
                # The user must use the 'Use Last Terminal Session' button to re-map.
                
                schedule_time = datetime.fromisoformat(schedule_time_str)
                delay_seconds = (schedule_time - datetime.now()).total_seconds()
                
                if delay_seconds > 0:
                    timer = threading.Timer(delay_seconds, run_scheduled_task, args=[task_id])
                    timer.daemon = True
                    timer.start()
                    
                    scheduled_tasks[task_id] = {
                        'id': task_id,
                        'name': task_data.get('name', 'Unnamed Task'),
                        'command': task_data['command'],
                        'schedule_time': schedule_time_str,
                        'sid': task_data['sid'],
                        'terminalId': task_data.get('terminalId', 'main_terminal'),
                        'timer': timer,
                        'status': task_data.get('status', 'once'),
                        'tool': task_data.get('tool', 'nmap')
                    }
                    print(f"Re-scheduled task {task_id} for {schedule_time_str} in terminal {task_data['terminalId']}.")
                else:
                    print(f"Skipping past task {task_id} scheduled for {schedule_time_str}.")

        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading tasks from {TASKS_FILE}: {e}")

def save_tasks():
# ... (rest of save_tasks remains unchanged) ...
    """
    Saves the scheduled tasks to the tasks.json file.
    """
    try:
        tasks_to_save = [
            {'id': task_id, 'name': task['name'], 'command': task['command'], 'schedule_time': task['schedule_time'], 'sid': task['sid'], 'terminalId': task['terminalId'], 'status': task.get('status', 'once'), 'tool': task.get('tool', 'nmap')}
            for task_id, task in scheduled_tasks.items()
        ]
        with open(TASKS_FILE, 'w') as f:
            json.dump(tasks_to_save, f, indent=4)
        print(f"Successfully saved {len(tasks_to_save)} tasks to '{TASKS_FILE}'.")
    except IOError as e:
        print(f"Error saving tasks to {TASKS_FILE}: {e}")
        
def edit_task(task_id, new_name, new_command, new_time_str, new_status, new_terminalId, new_tool):
# ... (rest of edit_task remains unchanged) ...
    """
    Updates an existing scheduled task.
    """
    global scheduled_tasks
    if task_id in scheduled_tasks:
        task = scheduled_tasks[task_id]
        
        task['timer'].cancel()
        
        try:
            new_time = datetime.fromisoformat(new_time_str)
            delay_seconds = (new_time - datetime.now()).total_seconds()
            
            if delay_seconds < 0 and new_status != 'daily':
                raise ValueError("New time is in the past.")
            
            new_timer = threading.Timer(delay_seconds, run_scheduled_task, args=[task_id])
            new_timer.daemon = True
            new_timer.start()
            
            task['name'] = new_name
            task['command'] = new_command
            task['schedule_time'] = new_time_str
            task['timer'] = new_timer
            task['status'] = new_status
            task['terminalId'] = new_terminalId
            task['tool'] = new_tool
            
            save_tasks()
            return True, "Task updated and re-scheduled successfully."
        
        except ValueError as e:
            original_time = datetime.fromisoformat(task['schedule_time'])
            original_delay = (original_time - datetime.now()).total_seconds()
            if original_delay > 0:
                original_timer = threading.Timer(original_delay, run_scheduled_task, args=[task_id])
                original_timer.daemon = True
                original_timer.start()
                task['timer'] = original_timer
            return False, f"Invalid time format or time is in the past: {e}"
        except Exception as e:
            return False, f"An error occurred while editing the task: {e}"
    else:
        return False, "Task not found."


@app.route('/get_path_config', methods=['GET'])
def get_path_config_route():
    """Returns the current configurable paths."""
    # Only return the raw paths as lists
    return jsonify({
        'commands_folder': path_config['commands_folder'],
        'notes_folder': path_config['notes_folder']
    }), 200

@app.route('/set_path_config', methods=['POST'])
def set_path_config_route():
    """Updates and saves the path configurations."""
    data = request.json
    key = data.get('key')
    paths = data.get('paths') # paths is now a list
    
    if key not in DEFAULT_PATHS:
        return jsonify({'success': False, 'message': f'Invalid path key: {key}'}), 400
    
    if not isinstance(paths, list) or not [p for p in paths if p]:
        return jsonify({'success': False, 'message': 'Path list cannot be empty and must contain at least one non-empty path.'}), 400

    try:
        # Save the raw path input list
        path_config[key] = [p for p in paths if p] # Filter out any empty strings
        save_paths() # save_paths calls load_paths() to validate and resolve the path
        
        return jsonify({'success': True, 'message': f'Paths for {key} updated successfully.'}), 200
    except Exception as e:
        # load_paths already handles errors internally by reverting to a safe state
        return jsonify({'success': False, 'message': f'Error setting paths: {e}'}), 500

@app.route('/browse_path', methods=['POST'])
def browse_path():
    """Returns a list of folders and files in a specified directory for browsing."""
    data = request.json
    path = data.get('path', os.getcwd())
    
    try:
        # Ensure path is absolute and normalized
        full_path = os.path.abspath(path)

        if not os.path.isdir(full_path):
            # If the path doesn't exist, try to browse the parent
            parent_path = os.path.abspath(os.path.join(full_path, '..'))
            if os.path.isdir(parent_path):
                 full_path = parent_path
            else:
                 return jsonify({'success': False, 'message': f'The specified path does not exist or is not a directory: {path}'}), 404
        
        contents = []
        # Add a way to go up one level, unless it's the root of the file system
        # Use os.path.normcase for case-insensitive comparison (important for Windows)
        if os.path.normcase(full_path) != os.path.normcase(os.path.abspath(os.path.sep)):
             parent_path = os.path.abspath(os.path.join(full_path, '..'))
             if parent_path != full_path: # Check to prevent infinite loop on some systems
                contents.append({'name': '..', 'type': 'folder', 'full_path': parent_path})

        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            # Skip hidden files/folders (starting with '.') on Unix-like systems
            if UNIX_SYSTEM and item.startswith('.'):
                 continue

            if os.path.isdir(item_path):
                contents.append({'name': item, 'type': 'folder', 'full_path': item_path})
            elif os.path.isfile(item_path):
                contents.append({'name': item, 'type': 'file', 'full_path': item_path})
                
        # Sort to show folders first, then files
        contents.sort(key=lambda x: (0 if x['type'] == 'folder' else 1, x['name']))

        return jsonify({'success': True, 'contents': contents, 'current_path': full_path}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error browsing path: {e}'}), 500


@app.route('/')
def index():
# ... (rest of index remains unchanged) ...
    """Renders the main Multi-Tool Web GUI HTML page."""
    return render_template('index.html')

@app.route('/get_all_tools', methods=['GET'])
# ... (rest of get_all_tools remains unchanged) ...
def get_all_tools():
    """Returns the tool, example, and installation configurations as JSON."""
    return jsonify({
        'tools': ALL_TOOLS,
        'examples': ALL_EXAMPLES,
        'installations': ALL_INSTALLATIONS
    }), 200

@app.route('/get_output_files', methods=['GET'])
# ... (rest of get_output_files remains unchanged) ...
def get_output_files():
    """Returns a list of files in the output folder."""
    try:
        files = [f for f in os.listdir(OUTPUT_FOLDER) if os.path.isfile(os.path.join(OUTPUT_FOLDER, f))]
        return jsonify(files), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/generate_command', methods=['POST'])
# ... (rest of generate_command remains unchanged) ...
def generate_command():
    """Generates a command based on the selected tool and form data."""
    data = request.json
    tool_name = data.get('tool')
    options = data.get('options', {})

    tool_data = ALL_TOOLS.get(tool_name)
    if not tool_data:
        return jsonify({'command': f'Error: Tool "{tool_name}" not found.'})

    command_parts = [tool_data.get('executable', tool_name)]
    
    # Flags to prevent duplicate flags
    added_flags = set()

    def add_arg(flag, value):
        if value:
            if flag and flag in added_flags:
                # This flag is already handled by another input in the same tab, skip
                return
            quoted_value = f'"{str(value)}"' if not UNIX_SYSTEM else shlex.quote(str(value))
            if flag:
                command_parts.append(flag)
                added_flags.add(flag)
            command_parts.append(quoted_value)
    
    def add_checkbox_arg(flag, value):
        if value and flag not in added_flags:
            command_parts.append(flag)
            added_flags.add(flag)
    
    def add_radio_arg(flag, value):
        if value:
            if flag and flag in added_flags:
                # This flag is already handled by another input in the same tab, skip
                return
            quoted_value = f'"{str(value)}"' if not UNIX_SYSTEM else shlex.quote(str(value))
            if flag:
                command_parts.append(flag)
                added_flags.add(flag)
            command_parts.append(quoted_value)

    # Collect all inputs from all tabs of the tool
    for tab in tool_data.get('tabs', []):
        for input_def in tab.get('inputs', []):
            input_id = input_def['id']
            # For radio buttons, the name is the key, not the ID
            if input_def['type'] == 'radio':
                value = options.get(input_id)
            else:
                value = options.get(input_id)
            
            flag = input_def.get('flag')

            if value:
                if input_def['type'] == 'checkbox':
                    add_checkbox_arg(flag, value)
                elif input_def['type'] == 'radio':
                    add_radio_arg(flag, value)
                elif input_def['type'] == 'textarea':
                    if flag:
                         add_arg(flag, value.strip())
                    else:
                         add_arg('', value.strip())
                elif input_def['type'] == 'file':
                    # For file inputs, the value is the filename
                    # We assume it has already been uploaded to the OUTPUT_FOLDER by the frontend
                    add_arg(flag, os.path.join(OUTPUT_FOLDER, value))
                else:
                    add_arg(flag, value)
    
    generated_cmd = " ".join(command_parts)
    return jsonify({'command': generated_cmd})
    
@app.route('/move_files', methods=['POST'])
# ... (rest of move_files remains unchanged) ...
def move_files():
    """
    Moves selected files from the 'output' folder to a user-specified path.
    """
    data = request.json
    files = data.get('files')
    destination_path = data.get('destination_path')
    
    if not files or not destination_path:
        return jsonify({'success': False, 'message': 'Files and destination path are required.'}), 400
    
    if not os.path.isdir(destination_path):
        return jsonify({'success': False, 'message': f'Destination path does not exist or is not a directory: {destination_path}'}), 404

    for filename in files:
        source_file = os.path.join(OUTPUT_FOLDER, filename)
        destination_file = os.path.join(destination_path, filename)
        
        if not os.path.exists(source_file):
            return jsonify({'success': False, 'message': f'Source file not found: {source_file}'}), 404
        
        try:
            shutil.move(source_file, destination_file)
        except IOError as e:
            return jsonify({'success': False, 'message': f'Error moving file {filename}: {e}'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': f'An unexpected error occurred for {filename}: {e}'}), 500
    
    return jsonify({'success': True, 'message': f'Successfully moved {len(files)} file(s) to {destination_path}'}), 200

@app.route('/copy_files', methods=['POST'])
# ... (rest of copy_files remains unchanged) ...
def copy_files():
    """
    Copies selected files from the 'output' folder to a user-specified path.
    """
    data = request.json
    files = data.get('files')
    destination_path = data.get('destination_path')
    
    if not files or not destination_path:
        return jsonify({'success': False, 'message': 'Files and destination path are required.'}), 400
        
    if not os.path.isdir(destination_path):
        return jsonify({'success': False, 'message': f'Destination path does not exist or is not a directory: {destination_path}'}), 404

    for filename in files:
        source_file = os.path.join(OUTPUT_FOLDER, filename)
        destination_file = os.path.join(destination_path, filename)
        
        if not os.path.exists(source_file):
            return jsonify({'success': False, 'message': f'Source file not found: {source_file}'}), 404
            
        try:
            shutil.copy(source_file, destination_file)
        except IOError as e:
            return jsonify({'success': False, 'message': f'Error copying file {filename}: {e}'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': f'An unexpected error occurred for {filename}: {e}'}), 500
    
    return jsonify({'success': True, 'message': f'Successfully copied {len(files)} file(s) to {destination_path}'}), 200

@app.route('/save_output', methods=['POST'])
# ... (rest of save_output remains unchanged) ...
def save_output():
    """
    Saves the entire content of the terminal to a fixed file named 'output.txt' in the output directory.
    """
    data = request.json
    content = data.get('content')
    
    if not content:
        return jsonify({'success': False, 'message': 'No terminal content provided to save.'}), 400
    
    filename = 'output.txt'
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'message': f'Terminal output saved to {filename} successfully in the {OUTPUT_FOLDER} folder.'}), 200
    except IOError as e:
        return jsonify({'success': False, 'message': f'Error saving file: {e}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f'An unexpected error occurred: {e}'}), 500

@app.route('/upload_files', methods=['POST'])
# ... (rest of upload_files remains unchanged) ...
def upload_files():
    """
    Receives a list of filenames and a target URL, then sends the
    files to the URL via a backend proxy.
    """
    data = request.json
    target_url = data.get('url')
    selected_files = data.get('files')

    if not target_url or not selected_files:
        return jsonify({'success': False, 'message': 'Invalid request data. Please provide a URL and select files.'}), 400

    print(f"Attempting to upload {len(selected_files)} file(s) to {target_url}")

    files_to_send = []
    for filename in selected_files:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                files_to_send.append(('file[]', (filename, f.read(), 'text/plain')))
        else:
            print(f"File not found on server: {filename}")
            return jsonify({'success': False, 'message': f'File not found on server: {filename}'}), 404

    try:
        response = requests.post(target_url, files=files_to_send, timeout=30)
        
        if response.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'Files uploaded successfully!',
                'response_text': response.text
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Upload failed with status code: {response.status_code}',
                'response_text': response.text
            }), 500
    except requests.exceptions.RequestException as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred during the upload: {e}'
        }), 500

@app.route('/get_report_files', methods=['GET'])
# ... (rest of get_report_files remains unchanged) ...
def get_report_files():
    """
    Returns a list of all .txt files in the output folder.
    """
    try:
        files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.txt')]
        return jsonify(files), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_file_content', methods=['POST'])
def get_file_content():
    """
    Returns the content of a specified file.
    (Updated to use configurable paths)
    """
    data = request.json
    filename = data.get('filename') # e.g., 'commands/my_command.txt' or 'output/report.txt'
    
    if not filename:
        return jsonify({'success': False, 'message': 'Filename is required.'}), 400
    
    # Path is now resolved based on configuration
    file_path = resolve_file_path_by_folder_name(filename)
    
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found.'}), 404
        
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error reading file: {e}'}), 500

@app.route('/delete_file', methods=['POST'])
def delete_file():
    """
    Deletes a specified file.
    (Updated to use configurable paths)
    """
    data = request.json
    filename = data.get('filename') # e.g., 'commands/my_command.txt' or 'output/report.txt'
    
    if not filename:
        return jsonify({'success': False, 'message': 'Filename is required.'}), 400
    
    # Path is now resolved based on configuration
    file_path = resolve_file_path_by_folder_name(filename)
    
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found.'}), 404
        
    try:
        os.remove(file_path)
        # Note: filename here is the alias/filename (e.g., commands/file.txt). The path is resolved internally.
        return jsonify({'success': True, 'message': f'File {filename.split(os.sep)[-1]} deleted successfully.'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting file: {e}'}), 500

@app.route('/edit_file', methods=['POST'])
def edit_file():
    """
    Edits the content of a specified file.
    (Updated to use configurable paths)
    """
    data = request.json
    filename = data.get('filename') # e.g., 'commands/my_command.txt' or 'output/report.txt'
    content = data.get('content')
    
    if not filename or content is None:
        return jsonify({'success': False, 'message': 'Filename and content are required.'}), 400
    
    # Path is now resolved based on configuration
    file_path = resolve_file_path_by_folder_name(filename)
    
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found.'}), 404
        
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'message': f'File {filename.split(os.sep)[-1]} updated successfully.'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'An unexpected error occurred: {e}'}), 500
        
@app.route('/create_file', methods=['POST'])
def create_file():
    """
    Creates a new file with the specified name and content.
    (Updated to use configurable paths)
    """
    data = request.json
    file_name = data.get('file_name')
    file_content = data.get('file_content', '')
    path_key = data.get('path', '') # 'commands', 'notes', 'output', a configured raw path string, or a custom path
    
    if not file_name:
        return jsonify({'success': False, 'message': 'File name is required.'}), 400
    
    # Resolve the path to an absolute folder path
    save_path = ''
    
    # Check if the path_key is one of the fixed aliases
    if path_key == OUTPUT_FOLDER:
        save_path = os.path.abspath(OUTPUT_FOLDER)
    elif path_key == COMMANDS_FOLDER_DEFAULT_NAME: # This is the alias, default to first resolved path
        save_path = resolved_paths['commands_folder'][0]
    elif path_key == NOTES_FOLDER_DEFAULT_NAME: # This is the alias, default to first resolved path
        save_path = resolved_paths['notes_folder'][0]
    elif path_key:
        # Check if the path_key is one of the *raw* configured paths in our list (e.g., 'my_custom_commands_folder')
        found_configured_path = False
        for key in DEFAULT_PATHS:
            if path_key in path_config[key]:
                # This path is a configured, raw path string. Resolve it to its absolute path.
                save_path = os.path.abspath(os.path.join(os.getcwd(), path_key)) if not os.path.isabs(path_key) else path_key
                found_configured_path = True
                break
        
        if not found_configured_path:
            # Custom path, resolve them relative to CWD unless absolute
            if os.path.isabs(path_key):
                save_path = path_key
            else:
                save_path = os.path.abspath(os.path.join(os.getcwd(), path_key))
    else:
        # Default to CWD if no path is specified
        save_path = os.getcwd()
    
    # Security check: Ensure the resolved path is a directory
    if not save_path:
         return jsonify({'success': False, 'message': 'Could not resolve a valid save path.'}), 500
         
    os.makedirs(save_path, exist_ok=True)
    file_path = os.path.join(save_path, secure_filename(file_name))

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        return jsonify({'success': True, 'message': f'File "{file_name}" created successfully at "{os.path.basename(save_path)}".'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error creating file: {e}'}), 500

@app.route('/upload_file', methods=['POST'])
# ... (rest of upload_file remains unchanged) ...
def upload_file():
    """
    Handles file uploads via drag and drop.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in the request.'}), 400
    
    files = request.files.getlist('file')
    upload_path = request.form.get('path', '')
    
    if not files:
        return jsonify({'success': False, 'message': 'No files selected for upload.'}), 400
    
    save_path = os.path.join(os.getcwd(), upload_path) if upload_path else os.getcwd()
    os.makedirs(save_path, exist_ok=True)
    
    uploaded_files_count = 0
    for file in files:
        if file.filename == '':
            continue
        
        filename = secure_filename(file.filename)
        file.save(os.path.join(save_path, filename))
        uploaded_files_count += 1
    
    if uploaded_files_count > 0:
        return jsonify({'success': True, 'message': f'Successfully uploaded {uploaded_files_count} file(s) to "{save_path}".'}), 200
    else:
        return jsonify({'success': False, 'message': 'No files were uploaded.'}), 400

@app.route('/upload_tool_file', methods=['POST'])
# ... (rest of upload_tool_file remains unchanged) ...
def upload_tool_file():
    """
    Handles a single file upload from a tool's form input and saves it to the output folder.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in the request.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file.'}), 400
        
    filename = secure_filename(file.filename)
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    
    try:
        file.save(file_path)
        return jsonify({'success': True, 'message': f'File "{filename}" uploaded successfully.', 'filename': filename}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving file: {e}'}), 500


@app.route('/get_files_from_path', methods=['POST'])
def get_files_from_path():
    """
    Returns a list of all files in a specified directory or aggregates files
    from all configured paths if 'aggregate' is True.
    """
    data = request.json
    path_key = data.get('path', '') # 'commands', 'notes', or a full path
    aggregate = data.get('aggregate', False)
    
    full_path_list = []
    
    if aggregate and path_key in [COMMANDS_FOLDER_DEFAULT_NAME, NOTES_FOLDER_DEFAULT_NAME]:
        # Aggregate from all resolved paths for this key
        config_key = path_key + '_folder'
        if config_key in resolved_paths:
            full_path_list = resolved_paths[config_key]
        else:
            return jsonify({'success': False, 'message': f'Configuration for {path_key} not found.'}), 404
    else:
        # Standard single path resolution
        full_path = path_key
        if not os.path.isabs(path_key):
            full_path = os.path.abspath(os.path.join(os.getcwd(), path_key))
        full_path_list = [full_path]

    file_list = []
    for current_path in full_path_list:
        if not os.path.isdir(current_path):
            continue # Skip non-existent directories, especially for aggregation
            
        try:
            for filename in os.listdir(current_path):
                file_path = os.path.join(current_path, filename)
                if os.path.isfile(file_path):
                    if aggregate:
                        # For aggregation, return the folder alias (e.g., 'commands') and the filename
                        # This works because the backend's resolve_file_path_by_folder_name 
                        # uses the alias (e.g., 'commands') to check all resolved paths.
                        file_list.append(f"{path_key}{os.sep}{filename}")
                    else:
                        file_list.append(filename)
        except Exception as e:
            # Continue to the next path on error
            print(f"Error accessing path {current_path}: {e}")
            continue
            
    # Remove duplicates if aggregating (e.g., if two paths contain the same filename)
    if aggregate:
        # Split into filename (to check for duplicates) and full identifier
        seen_files = {}
        unique_file_list = []
        for file_id in file_list:
            filename_only = file_id.split(os.sep)[-1]
            if filename_only not in seen_files:
                seen_files[filename_only] = True
                unique_file_list.append(file_id)
        file_list = unique_file_list

    return jsonify({'success': True, 'files': file_list}), 200

@app.route('/copy_files_from_path', methods=['POST'])
# ... (rest of copy_files_from_path remains unchanged) ...
def copy_files_from_path():
    """
    Copies selected files from a source path to a destination path.
    """
    data = request.json
    source_path = data.get('source_path')
    destination_path = data.get('destination_path', os.getcwd())
    files = data.get('files')
    
    if not files or not source_path:
        return jsonify({'success': False, 'message': 'Source path and selected files are required.'}), 400
    
    full_source_path = os.path.join(os.getcwd(), source_path)
    full_destination_path = os.path.join(os.getcwd(), destination_path)
        
    if not os.path.isdir(full_source_path):
        return jsonify({'success': False, 'message': f'Source path does not exist or is not a directory: {source_path}'}), 404
        
    os.makedirs(full_destination_path, exist_ok=True)
    
    for filename in files:
        source_file = os.path.join(full_source_path, filename)
        destination_file = os.path.join(full_destination_path, filename)
        
        if not os.path.exists(source_file):
            return jsonify({'success': False, 'message': f'Source file not found: {source_file}'}), 404
            
        try:
            shutil.copy(source_file, destination_file)
        except IOError as e:
            return jsonify({'success': False, 'message': f'Error copying file {filename}: {e}'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': f'An unexpected error occurred for {filename}: {e}'}), 500
    
    return jsonify({'success': True, 'message': f'Successfully copied {len(files)} file(s) to {destination_path}'}), 200

@app.route('/move_files_from_path', methods=['POST'])
# ... (rest of move_files_from_path remains unchanged) ...
def move_files_from_path():
    """
    Moves selected files from a source path to a destination path.
    """
    data = request.json
    source_path = data.get('source_path')
    destination_path = data.get('destination_path', os.getcwd())
    files = data.get('files')
    
    if not files or not source_path:
        return jsonify({'success': False, 'message': 'Source path and selected files are required.'}), 400
        
    full_source_path = os.path.join(os.getcwd(), source_path)
    full_destination_path = os.path.join(os.getcwd(), destination_path)

    if not os.path.isdir(full_source_path):
        return jsonify({'success': False, 'message': f'The specified path does not exist or is not a directory: {source_path}'}), 404
        
    os.makedirs(full_destination_path, exist_ok=True)
    
    for filename in files:
        source_file = os.path.join(full_source_path, filename)
        destination_file = os.path.join(full_destination_path, filename)
        
        if not os.path.exists(source_file):
            return jsonify({'success': False, 'message': f'Source file not found: {source_file}'}), 404
            
        try:
            shutil.move(source_file, destination_file)
        except IOError as e:
            return jsonify({'success': False, 'message': f'Error moving file {filename}: {e}'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': f'An unexpected error occurred for {filename}: {e}'}), 500
    
    return jsonify({'success': True, 'message': f'Successfully moved {len(files)} file(s) to {destination_path}'}), 200

def read_from_pty(sid, terminalId, master_fd):
# ... (rest of read_from_pty remains unchanged) ...
    """
    Continuously reads data from a specific PTY and sends it to the
    correct client and terminal via WebSockets.
    """
    while True:
        try:
            data = os.read(master_fd, 1024)
            if data:
                socketio.emit('terminal_output', {'data': data.decode('utf-8', errors='ignore'), 'terminalId': terminalId}, room=sid, namespace='/')
            else:
                break
        except OSError:
            break
        except Exception as e:
            print(f"Error in read_from_pty for {sid} / {terminalId}: {e}")
            break

def read_from_process(sid, terminalId, process):
# ... (rest of read_from_process remains unchanged) ...
    """
    Continuously reads data from a specific subprocess's stdout/stderr
    and sends it to the correct client and terminal via WebSockets.
    """
    while process.poll() is None:
        try:
            char = process.stdout.read(1)
            if char:
                socketio.emit('terminal_output', {'data': char.decode('utf-8', errors='ignore'), 'terminalId': terminalId}, room=sid, namespace='/')
            else:
                time.sleep(0.01)
        except Exception as e:
            print(f"Error in read_from_process for {sid} / {terminalId}: {e}")
            break

def spawn_terminal_session(sid, terminalId):
# ... (rest of spawn_terminal_session remains unchanged) ...
    """
    Spawns a new shell process and associates it with a specific terminalId.
    """
    print(f'Client {sid} is starting new terminal process for ID: {terminalId}.')
    
    if UNIX_SYSTEM:
        master_fd, slave_fd = pty.openpty()
        shell_process = subprocess.Popen(
            ['/bin/bash'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            universal_newlines=True,
            env=dict(os.environ, PYTHONUNBUFFERED='1')
        )
        
        reader_thread = threading.Thread(target=read_from_pty, args=(sid, terminalId, master_fd))
        sessions[sid][terminalId] = {
            'master_fd': master_fd,
            'slave_fd': slave_fd,
            'process': shell_process,
            'reader_thread': reader_thread
        }
    else:
        shell_process = subprocess.Popen(
            ['cmd.exe'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=0,
            env=dict(os.environ, PYTHONUNBUFFERED='1')
        )
        
        reader_thread = threading.Thread(target=read_from_process, args=(sid, terminalId, shell_process))
        sessions[sid][terminalId] = {
            'process': shell_process,
            'reader_thread': reader_thread,
            'buffer': '',
            'has_set_encoding': False,
            'in_interactive_mode': False,
            'interactive_process': None,
            'interactive_reader_thread': None
        }
    
    reader_thread.daemon = True
    reader_thread.start()

@socketio.on('connect')
# ... (rest of handle_connect remains unchanged) ...
def handle_connect():
    """
    Initializes a new session for a connecting client.
    """
    sid = request.sid
    print(f'Client {sid} connected.')
    sessions[sid] = {}
    
@socketio.on('new_terminal_session')
# ... (rest of handle_new_terminal_session remains unchanged) ...
def handle_new_terminal_session(data):
    """
    Creates a new terminal session for the connected client.
    """
    sid = request.sid
    terminalId = data.get('terminalId')
    
    if sid not in sessions:
        sessions[sid] = {}
    
    if terminalId not in sessions[sid]:
        spawn_terminal_session(sid, terminalId)
    else:
        print(f"Terminal session {terminalId} for client {sid} already exists.")

@socketio.on('terminal_input')
# ... (rest of handle_input remains unchanged) ...
def handle_input(data):
    """
    Writes client keyboard input to their specific shell process.
    """
    sid = request.sid
    terminalId = data.get('terminalId')
    session = sessions.get(sid, {}).get(terminalId)
    
    if not session:
        print(f"Session not found for {sid} / {terminalId}")
        return

    command_char = data.get('command')
    if not command_char:
        return

    if UNIX_SYSTEM:
        master_fd = session.get('master_fd')
        if master_fd:
            try:
                os.write(master_fd, command_char.encode('utf-8'))
            except OSError:
                print(f"Error writing to PTY for {sid} / {terminalId}. Disconnecting session.")
                del sessions[sid][terminalId]
    else:
        shell_process = session.get('process')
        if not shell_process or not shell_process.stdin:
            return

        try:
            if session['in_interactive_mode']:
                if session['interactive_process'] and session['interactive_process'].stdin:
                    try:
                        session['interactive_process'].stdin.write(command_char.encode('utf-8'))
                        session['interactive_process'].stdin.flush()
                        
                        if session['buffer'].strip() == 'exit()' and command_char == '\r':
                            session['interactive_process'].terminate()
                            session['in_interactive_mode'] = False
                            session['interactive_process'] = None
                            session['interactive_reader_thread'] = None
                            session['buffer'] = ''
                            
                    except OSError:
                        print(f"Error writing to interactive process stdin for {sid} / {terminalId}. Exiting interactive mode.")
                        session['in_interactive_mode'] = False
                        session['interactive_process'] = None
                        session['interactive_reader_thread'] = None
                        session['buffer'] = ''
                    finally:
                        if command_char != '\r':
                            session['buffer'] += command_char
                        else:
                            session['buffer'] = ''
                return

            if command_char == '\x7f' or command_char == '\b':
                if len(session['buffer']) > 0:
                    session['buffer'] = session['buffer'][:-1]
                    socketio.emit('terminal_output', {'data': '\b \b', 'terminalId': terminalId}, room=sid)
            elif command_char == '\r':
                socketio.emit('terminal_output', {'data': '\r\n', 'terminalId': terminalId}, room=sid)

                command_to_execute = session['buffer'].strip()
                
                if command_to_execute.lower() == 'cls':
                    socketio.emit('terminal_output', {'data': '\x1bc', 'terminalId': terminalId}, room=sid)
                    session['buffer'] = ''
                    return

                if command_to_execute.lower().startswith('python'):
                    try:
                        python_process = subprocess.Popen(
                            ['python'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=False,
                            bufsize=0
                        )
                        session['in_interactive_mode'] = True
                        session['interactive_process'] = python_process
                        session['interactive_reader_thread'] = threading.Thread(target=read_from_process, args=(sid, terminalId, python_process))
                        session['interactive_reader_thread'].daemon = True
                        session['interactive_reader_thread'].start()
                        session['buffer'] = ''

                    except FileNotFoundError:
                        socketio.emit('terminal_output', {'data': 'Error: Python interpreter not found. Please ensure python is in your system PATH.\r\n', 'terminalId': terminalId}, room=sid)
                        session['buffer'] = ''
                    return
                
                if not session['has_set_encoding']:
                    shell_process.stdin.write(b'chcp 65001\n')
                    shell_process.stdin.flush()
                    session['has_set_encoding'] = True

                full_command_bytes = (command_to_execute + '\n').encode('utf-8')
                shell_process.stdin.write(full_command_bytes)
                shell_process.stdin.flush()
                
                session['buffer'] = ''
            else:
                session['buffer'] += command_char
                socketio.emit('terminal_output', {'data': command_char, 'terminalId': terminalId}, room=sid)
        except OSError:
            print(f"Error writing to process stdin for {sid} / {terminalId}. Disconnecting session.")
            del sessions[sid][terminalId]

def execute_command_in_session(sid, terminalId, command):
# ... (rest of execute_command_in_session remains unchanged) ...
    """
    Executes a given command in the specified session's terminal.
    """
    session = sessions.get(sid, {}).get(terminalId)
    if not session or not command:
        print(f"Error: No active session or command provided for sid: {sid}, terminal: {terminalId}")
        return

    if UNIX_SYSTEM:
        full_command_with_newline = command + '\n'
        os.write(session['master_fd'], full_command_with_newline.encode('utf-8'))
    else:
        full_command_with_newline = command + '\n'
        session['process'].stdin.write(full_command_with_newline.encode('utf-8'))
        session['process'].stdin.flush()

@socketio.on('run_command')
# ... (rest of handle_run_command remains unchanged) ...
def handle_run_command(data):
    """
    Executes a command by sending it to the interactive terminal session.
    """
    sid = request.sid
    command_str = data.get('command')
    terminalId = data.get('terminalId', 'main_terminal')
    execute_command_in_session(sid, terminalId, command_str)

@socketio.on('schedule_task')
# ... (rest of handle_schedule_task remains unchanged) ...
def handle_schedule_task(data):
    """
    Schedules a command to run at a specific time.
    """
    sid = request.sid
    task_name = data.get('task_name')
    command = data.get('command')
    schedule_time_str = data.get('schedule_time')
    status = data.get('status', 'once')
    terminalId = data.get('terminalId', 'main_terminal')
    tool = data.get('tool', 'nmap')

    if not task_name or not command or not schedule_time_str:
        emit('task_scheduled_result', {'success': False, 'message': 'Task name, command, and time are required.'}, room=sid)
        return

    try:
        schedule_time = datetime.fromisoformat(schedule_time_str)
        delay_seconds = (schedule_time - datetime.now()).total_seconds()

        if delay_seconds < 0:
            emit('task_scheduled_result', {'success': False, 'message': 'The specified time is in the past.'}, room=sid)
            return

        task_id = str(uuid.uuid4())
        
        timer = threading.Timer(delay_seconds, run_scheduled_task, args=[task_id])
        timer.daemon = True
        timer.start()

        scheduled_tasks[task_id] = {
            'id': task_id,
            'name': task_name,
            'command': command,
            'schedule_time': schedule_time_str,
            'sid': sid,
            'terminalId': terminalId,
            'timer': timer,
            'status': status,
            'tool': tool
        }
        
        save_tasks()

        emit('task_scheduled_result', {'success': True, 'message': 'Task scheduled successfully.', 'taskId': task_id, 'name': task_name, 'command': command, 'time': schedule_time_str}, room=sid)
        print(f"Task {task_id} scheduled for {schedule_time_str} with delay {delay_seconds:.2f} seconds in terminal {terminalId}.")

    except ValueError:
        emit('task_scheduled_result', {'success': False, 'message': 'Invalid date and time format.'}, room=sid)
    except Exception as e:
        print(f"Error scheduling task: {e}")
        emit('task_scheduled_result', {'success': False, 'message': f'An error occurred: {str(e)}'}, room=sid)

@socketio.on('edit_task')
# ... (rest of handle_edit_task remains unchanged) ...
def handle_edit_task(data):
    """
    Edits a scheduled task.
    """
    sid = request.sid
    task_id = data.get('taskId')
    new_name = data.get('task_name')
    new_command = data.get('command')
    new_time_str = data.get('schedule_time')
    new_status = data.get('status')
    new_terminalId = data.get('terminalId')
    new_tool = data.get('tool')

    success, message = edit_task(task_id, new_name, new_command, new_time_str, new_status, new_terminalId, new_tool)
    
    emit('edit_task_result', {'success': success, 'message': message}, room=sid)
    if success:
        print(f"Task {task_id} edited by client {sid}.")


@socketio.on('cancel_task')
# ... (rest of handle_cancel_task remains unchanged) ...
def handle_cancel_task(data):
    """
    Cancels a scheduled task.
    """
    sid = request.sid
    task_id = data.get('taskId')
    
    if task_id in scheduled_tasks:
        timer = scheduled_tasks[task_id]['timer']
        timer.cancel()
        del scheduled_tasks[task_id]
        save_tasks()
        print(f"Task {task_id} cancelled by client {sid}.")
        emit('task_cancelled', {'taskId': task_id, 'message': 'Task cancelled successfully.'}, room=sid)
    else:
        emit('task_cancelled', {'taskId': task_id, 'message': 'Task not found or already completed.'}, room=sid)

@socketio.on('get_scheduled_tasks')
# ... (rest of handle_get_scheduled_tasks remains unchanged) ...
def handle_get_scheduled_tasks():
    """
    Returns a list of all currently scheduled tasks.
    """
    sid = request.sid
    load_tasks()
    tasks_list = []
    for task_id, task_data in scheduled_tasks.items():
        tasks_list.append({
            'taskId': task_id,
            'task_name': task_data['name'],
            'command': task_data['command'],
            'time': task_data['schedule_time'],
            'status': task_data.get('status', 'once'),
            'sid': task_data['sid'],
            'terminalId': task_data.get('terminalId', 'main_terminal'),
            'tool': task_data.get('tool', 'nmap')
        })
    emit('scheduled_tasks_list', {'tasks': tasks_list}, room=sid)

@socketio.on('replace_task_sids')
# ... (rest of handle_replace_task_sids remains unchanged) ...
def handle_replace_task_sids():
    """
    Replaces the session ID for all scheduled tasks with the latest known session ID.
    This functionality is primarily for reconnects to ensure scheduled tasks still function.
    """
    sid = request.sid
    try:
        updated_count = 0
        load_tasks()
        
        for task_id in scheduled_tasks:
            # Check if the task's old SID is the same as the current connection's SID.
            # This prevents a new user from hijacking another's tasks.
            if scheduled_tasks[task_id]['sid'] == sid:
                 # Re-schedule the task with the new SID if the old SID is missing from sessions
                 if sid not in sessions or scheduled_tasks[task_id]['sid'] not in sessions.get(sid, {}).values():
                    scheduled_tasks[task_id]['sid'] = sid
                    updated_count += 1
            
        save_tasks()
        
        emit('session_replace_result', {'success': True, 'message': f'Successfully updated {updated_count} task(s) with session ID: {sid}'}, room=sid)
        print(f"Replaced SIDs for {updated_count} tasks with {sid}.")
        
    except Exception as e:
        print(f"Error replacing SIDs: {e}")
        emit('session_replace_result', {'success': False, 'message': f'An error occurred: {str(e)}'}, room=sid)

@socketio.on('update_task_sids')
# ... (rest of handle_update_task_sids remains unchanged) ...
def handle_update_task_sids():
    """
    Updates all tasks with the new session ID automatically on page reload.
    """
    sid = request.sid
    try:
        load_tasks()
        
        if scheduled_tasks:
            # Re-schedule all tasks to the new SID for the current client's connection.
            for task_id in scheduled_tasks:
                 # Again, verify the user owns the task before re-associating the SID
                if scheduled_tasks[task_id]['sid'] == sid:
                    scheduled_tasks[task_id]['sid'] = sid
            save_tasks()
            emit('update_tasks_result', {'success': True, 'message': 'تم تحديث الجلسات تلقائياً للمهام المجدولة.'}, room=sid)
        else:
            emit('update_tasks_result', {'success': True, 'message': 'لا توجد مهام مجدولة لتحديثها.'}, room=sid)
    except Exception as e:
        print(f"Error updating SIDs on reload: {e}")
        emit('update_tasks_result', {'success': False, 'message': f'حدث خطأ أثناء تحديث الجلسات: {str(e)}'}, room=sid)

@socketio.on('disconnect')
# ... (rest of handle_disconnect remains unchanged) ...
def handle_disconnect():
    """
    Closes all PTYs and terminates shell processes for a disconnecting client.
    """
    sid = request.sid
    print(f'Client {sid} disconnected. Terminating all their terminal processes.')

    if sid in sessions:
        for terminalId in list(sessions[sid].keys()):
            session = sessions[sid].get(terminalId)
            if session:
                if session['process'] and session['process'].poll() is None:
                    session['process'].terminate()
                    session['process'].wait(timeout=5)
                
                if UNIX_SYSTEM:
                    if session.get('master_fd'):
                        os.close(session['master_fd'])
                    if session.get('slave_fd'):
                        os.close(session['slave_fd'])
            
            del sessions[sid][terminalId]
        
        del sessions[sid]

@socketio.on('delete_terminal')
# ... (rest of handle_delete_terminal remains unchanged) ...
def handle_delete_terminal(data):
    """
    Terminates a specific terminal process and removes it from the session.
    """
    sid = request.sid
    terminalId = data.get('terminalId')
    print(f"Client {sid} requested to delete terminal {terminalId}.")

    if sid in sessions and terminalId in sessions[sid]:
        session = sessions[sid][terminalId]
        if session['process'] and session['process'].poll() is None:
            session['process'].terminate()
            session['process'].wait(timeout=5)
        
        if UNIX_SYSTEM:
            if session.get('master_fd'):
                os.close(session['master_fd'])
            if session.get('slave_fd'):
                os.close(session['slave_fd'])
        
        del sessions[sid][terminalId]
        print(f"Terminal {terminalId} for client {sid} has been terminated and removed.")
        emit('terminal_deleted', {'terminalId': terminalId}, room=sid)


if __name__ == '__main__':
    port = 5001 
    if '--port' in sys.argv:
        try:
            port_index = sys.argv.index('--port') + 1
            port = int(sys.argv[port_index])
        except (ValueError, IndexError):
            print("Warning: Invalid or missing port argument for sub-app. Using default port.")
    
    load_paths() # Load and resolve paths first
    load_tasks()
    load_tool_configurations()
    print(f"Multi-tool sub-app is starting on port {port}...")
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)