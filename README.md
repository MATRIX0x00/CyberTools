# Multi-Tool Web GUI with Interactive Terminal

A versatile web-based graphical interface and interactive terminal suite built using **Flask**, **Flask-SocketIO**, and **xterm.js**. This platform allows security researchers, system administrators, and developers to configure, launch, and monitor various command-line security and networking tools from an intuitive, unified browser dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Supported Tools](#supported-tools)
- [Architecture & Tech Stack](#architecture--tech-stack)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
  - [Running Tools](#running-tools)
  - [Managing Multiple Terminals](#managing-multiple-terminals)
  - [Command Generator & Custom Commands](#command-generator--custom-commands)
  - [Task Scheduler](#task-scheduler)
  - [File Management & Paths](#file-management--paths)
- [Directory Structure](#directory-structure)
- [Configuration Files](#configuration-files)
- [Adding Custom Tools](#adding-custom-tools)
- [License & Disclaimer](#license--disclaimer)

---

## Overview

The **Multi-Tool Web GUI** bridges command-line utilities with an accessible web frontend. Instead of manually remembering numerous flags and syntax nuances, users can select tool arguments through categorized web forms, generate ready-to-run commands, execute them in real-time pseudo-terminals (PTY), and inspect output with full ANSI color support.

---

## Key Features

- **Interactive Pseudo-Terminal (PTY):** Real-time command execution with full ANSI color support powered by `xterm.js` and WebSockets (`Socket.IO`). Works across Linux/macOS and Windows environments.
- **Multi-Terminal Sessions:** Create, rename, switch between, and terminate multiple independent terminal sessions side by side.
- **Dynamic Command Builder:** Generates terminal commands automatically based on form inputs, flags, select menus, and uploads.
- **Extensive Tool Library:** Ships with pre-configured templates for 16 popular penetration testing and networking tools.
- **Task Scheduling:** Schedule one-off or recurring (daily, weekly, monthly, yearly) command runs linked to target terminal sessions.
- **Built-in File Management:** Browse server paths, upload files, download remote assets with `curl`/`wget`, move/copy scan outputs, and edit files directly in-browser.
- **Commands & Notes Notebooks:** Dedicated sidebar repositories to store frequently used command snippets and analysis notes.
- **One-Click Tool Installation:** View and run platform-specific installation commands for Linux (APT/Snap/Go/Pip), Termux, or Windows.

---

## Supported Tools

The platform includes interactive GUI tabs, flags, and usage examples for:

| Tool | Description |
| :--- | :--- |
| **Amass** | In-depth network mapping and external asset discovery |
| **Binwalk** | Firmware analysis, reverse engineering, and extraction |
| **Dirb** | Web content scanner and directory brute-forcer |
| **ffuf** | Fast web fuzzer written in Go |
| **Gobuster** | URI, DNS, and virtual host brute-forcer |
| **Hashcat** | Advanced password hash recovery utility |
| **Hydra** | Fast parallel network logon cracker |
| **Netstat** | Network statistics and active connection monitor |
| **Nikto** | Web server vulnerability and misconfiguration scanner |
| **Nmap** | Network exploration and port scanner / security auditor |
| **Ping** | ICMP network latency and reachability utility |
| **sqlmap** | Automated SQL injection detection and database takeover |
| **SSH** | Secure Shell client with port forwarding & tunnel builder |
| **Subfinder** | Fast passive subdomain enumeration tool |
| **wafw00f** | Web Application Firewall (WAF) fingerprinting utility |
| **Wfuzz** | Web application fuzzer and payload injector |

---

## Architecture & Tech Stack

- **Backend:** Python 3, Flask, Flask-SocketIO, Werkzeug, Requests
- **Terminal Backend:** `pty` (Unix/Linux) / `subprocess.PIPE` (Windows)
- **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS (CDN), Lucide Icons
- **Terminal Frontend:** `xterm.js` with `xterm-addon-fit`

---

## Prerequisites

- **Python:** Version 3.8 or higher
- **Operating System:** Linux (Ubuntu/Debian, Kali, Arch), macOS, or Windows 10/11
- **Pip:** Standard Python package manager

---

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/multi-tool-web-gui.git
   cd multi-tool-web-gui
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   # On Windows:
   # venv\Scripts\activate
   ```

3. **Install required Python packages:**
   ```bash
   pip install flask flask-socketio requests werkzeug
   ```

4. **Run the application:**
   ```bash
   python app.py
   ```
   *To run on a custom port:*
   ```bash
   python app.py --port 8080
   ```

5. **Open the web dashboard:**
   Open your browser and navigate to `http://localhost:5001` (or your chosen port).

---

## Usage Guide

### Running Tools
1. Select a tool from the left sidebar (e.g., **Nmap**, **sqlmap**, **ffuf**).
2. Configure desired options across the category tabs (Target, Scan Types, Output, Evasion, etc.).
3. The **Generated Command** box updates automatically in real-time.
4. Click **Run** to execute the command directly in the active terminal window.

### Managing Multiple Terminals
- Click **+ New** under the Terminals section in the sidebar to spawn a new shell session.
- Click any terminal name to switch to it.
- Rename sessions using the pencil icon or remove finished sessions using the trash icon.

### Command Generator & Custom Commands
- Inspect or tweak generated commands directly in the textarea.
- Use the **Copy Command** button to copy commands to your clipboard.
- Save custom commands under the **Commands** section in the sidebar for quick reuse.

### Task Scheduler
- Switch to the **Tasks** tab.
- Input a task name, command, execution time (`datetime-local`), and repeat interval (`once`, `daily`, `weekly`, `monthly`, `yearly`).
- Select which terminal session should execute the task and click **Schedule Task**.

### File Management & Paths
- **Control Output:** Move or copy generated files from the `output/` folder.
- **Upload / Download:** Upload files directly or download remote files to the server using `curl` or `wget`.
- **Paths Tab:** Configure custom search directories for commands and notes.

---

## Directory Structure

```text
├── app.py                     # Main Flask & SocketIO application backend
├── paths.json                 # Path configuration for commands and notes
├── tasks.json                 # Persistent storage for scheduled tasks
├── templates/
│   └── index.html             # Single-page web interface with xterm.js & Tailwind
├── tools/                     # JSON schema definitions for supported tools
│   ├── amass.json
│   ├── nmap.json
│   ├── sqlmap.json
│   └── ...
├── examples/                  # Ready-to-load examples and outputs for tools
│   ├── nmap.json
│   ├── sqlmap.json
│   └── ...
├── install/                   # Platform installation commands for tools
│   ├── nmap.json
│   ├── sqlmap.json
│   └── ...
├── commands/                  # Default folder for saved commands
├── notes/                     # Default folder for user notes
└── output/                    # Output directory for tool scan results & logs
```

---

## Configuration Files

### `paths.json`
Defines the active search paths for commands and notes files:
```json
{
    "commands_folder": ["commands"],
    "notes_folder": ["notes"]
}
```

### `tasks.json`
Stores scheduled tasks, including scheduled run times, target terminal ID, and repeat status.

---

## Adding Custom Tools

You can easily add custom tools by adding a JSON file in the `tools/` folder. Example structure:

```json
{
  "name": "Custom Tool",
  "version": "1.0.0",
  "executable": "customtool",
  "description": "Description of the tool.",
  "tabs": [
    {
      "id": "general",
      "name": "General",
      "inputs": [
        {
          "id": "target_input",
          "label": "Target Host:",
          "type": "text",
          "flag": "-t",
          "placeholder": "127.0.0.1",
          "help": "Specify the target IP or host."
        }
      ]
    }
  ]
}
```

Optionally add companion files in `examples/<tool>.json` and `install/<tool>.json`.

---

## License & Disclaimer

This software is intended for authorized penetration testing, security auditing, and educational purposes only. Always obtain proper authorization before testing target systems, networks, or applications.
