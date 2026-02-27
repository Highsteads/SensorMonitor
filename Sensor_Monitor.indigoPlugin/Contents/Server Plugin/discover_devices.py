#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    discover_devices.py
# Description: Discovery script - scans all Indigo devices and saves full details
#              to a JSON file for review, and generates a ready-to-use
#              sensor_monitor_config.json for the Sensor Monitor plugin.
#              Run once from Indigo Script Editor.
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.1
#
# HOW TO USE
# ----------
# 1. Open Indigo > Scripts > New Script
# 2. Paste this entire file into the editor
# 3. Click Run
# 4. Open sensor_monitor_config.json at CONFIG_OUTPUT_PATH
#    - Contact sensor candidates are ACTIVE (ready to use)
#    - All other devices are COMMENTED OUT (prefix # to disable)
#    - Edit labels, add # to disable, remove # to enable
# 5. Reload the plugin: Plugins > Sensor Monitor > Reload Plugin
# 6. Full device list is in device_discovery.json if you need to find anything

import indigo
import json
import os
from datetime import datetime

# ======================================
# CONFIG
# ======================================

DISCOVERY_OUTPUT_PATH = os.path.expanduser(
    "~/Documents/Indigo/SensorMonitor/device_discovery.json"
)

CONFIG_OUTPUT_PATH = os.path.expanduser(
    "~/Documents/Indigo/SensorMonitor/sensor_monitor_config.json"
)

# State names that strongly suggest a contact/door/window sensor
CONTACT_STATE_NAMES = {"contact", "doorSensor", "windowSensor"}

# Keywords in device name that suggest a contact/door/window sensor
CONTACT_NAME_KEYWORDS = [
    "contact", "door", "window", "entry", "gate", "patio", "garage"
]

# ======================================
# HELPERS
# ======================================

def log(msg):
    indigo.server.log(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_folder_name(dev):
    try:
        if dev.folderId and dev.folderId in indigo.devices.folders:
            return indigo.devices.folders[dev.folderId].name
    except Exception:
        pass
    return "(root)"


def get_states(dev):
    """Return dict of all state names and their current values."""
    try:
        return {k: dev.states[k] for k in dev.states}
    except Exception:
        return {}


def is_contact_candidate(dev, states):
    """Return True if the device looks like a contact/door/window sensor."""
    name_lower  = dev.name.lower()
    name_match  = any(kw in name_lower for kw in CONTACT_NAME_KEYWORDS)
    state_match = bool(CONTACT_STATE_NAMES & set(states.keys()))
    return name_match or state_match


def make_config_entry(dev, states, commented=False):
    """Return a JSON object string for sensor_monitor_config.json.

    commented=True  prepends '# ' so the entry is disabled by default.
    """
    if "contact" in states:
        # zigbee2mqtt: contact True=CLOSED False=OPEN
        state    = "contact"
        on_text  = "CLOSED"
        off_text = "OPEN"
    else:
        # Standard onState: True=triggered/open False=clear/closed
        state    = "onState"
        on_text  = "OPEN"
        off_text = "CLOSED"

    entry = (
        f'    {{"id": {dev.id}, "name": "{dev.name}", '
        f'"state": "{state}", "label": "{dev.name}", '
        f'"on_text": "{on_text}", "off_text": "{off_text}"}}'
    )
    return f"# {entry}" if commented else entry


def suggest_py_entry(dev, states):
    """Return a legacy Python DEVICE_MONITOR entry string (for device_discovery.json)."""
    if "contact" in states:
        return (
            f"    {dev.id}: "
            f"[{{\"state\": \"contact\", \"label\": \"{dev.name}\", "
            f"\"on_text\": \"CLOSED\", \"off_text\": \"OPEN\"}}],"
        )
    else:
        return (
            f"    {dev.id}: "
            f"[{{\"state\": \"onState\", \"label\": \"{dev.name}\", "
            f"\"on_text\": \"OPEN\", \"off_text\": \"CLOSED\"}}],"
        )

# ======================================
# MAIN DISCOVERY
# ======================================

log("Sensor Monitor - Device Discovery starting...")

all_devices     = []
contact_sensors = []

for dev in indigo.devices:
    states     = get_states(dev)
    folder     = get_folder_name(dev)
    is_contact = is_contact_candidate(dev, states)

    entry = {
        "id":               dev.id,
        "name":             dev.name,
        "folder":           folder,
        "enabled":          dev.enabled,
        "on_state":         dev.onState if hasattr(dev, "onState") else None,
        "states":           states,
        "is_contact_candidate": is_contact,
        "suggested_device_monitor_entry": suggest_py_entry(dev, states) if is_contact else None,
    }

    all_devices.append(entry)
    if is_contact:
        contact_sensors.append(entry)

# Sort alphabetically by name
all_devices.sort(key=lambda x: x["name"].lower())
contact_sensors.sort(key=lambda x: x["name"].lower())

# ======================================
# SAVE device_discovery.json  (full detail)
# ======================================

discovery_output = {
    "generated":           datetime.now().isoformat(),
    "total_devices":       len(all_devices),
    "contact_candidates":  len(contact_sensors),
    "summary": (
        "Review 'contact_sensors' for ready-to-paste entries. "
        "All devices are in 'all_devices' if you need to find something specific."
    ),
    "contact_sensors": contact_sensors,
    "all_devices":     all_devices,
}

try:
    os.makedirs(os.path.dirname(DISCOVERY_OUTPUT_PATH), exist_ok=True)
    with open(DISCOVERY_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(discovery_output, f, indent=2, default=str)
    log(f"Full device list saved to: {DISCOVERY_OUTPUT_PATH}")
except Exception as e:
    log(f"ERROR saving device_discovery.json: {e}")
    raise

# ======================================
# BUILD sensor_monitor_config.json
#
# Contact candidates  -> active entries (no # prefix)
# All other devices   -> commented entries (# prefix, disabled by default)
#
# Edit the file to:
#   - Add # to the start of any line to disable that device
#   - Remove # to enable a device
#   - Change "label" to customise the text shown in the Indigo log
# ======================================

config_lines = []
config_lines.append("{")
config_lines.append(f'  "_generated": "{datetime.now().isoformat()}",')
config_lines.append(f'  "_total_scanned": {len(all_devices)},')
config_lines.append('  "_usage": [')
config_lines.append('    "Lines starting with # are ignored (disabled entries).",')
config_lines.append('    "Remove # from a line to enable that device or variable.",')
config_lines.append('    "Add # to the start of a line to disable it.",')
config_lines.append('    "Change label to customise text in the Indigo event log.",')
config_lines.append('    "Reload plugin after saving: Plugins > Sensor Monitor > Reload Plugin"')
config_lines.append('  ],')
config_lines.append("")

# --- devices section ---
config_lines.append('  "devices": [')
config_lines.append("")

if contact_sensors:
    config_lines.append("    # --- Contact / Door / Window sensors (active) ---")
    for d in contact_sensors:
        dev_obj = indigo.devices[d["id"]]
        config_lines.append(
            make_config_entry(dev_obj, d["states"], commented=False) + ","
        )
    config_lines.append("")

# All non-contact devices, commented out for reference
non_contact = [d for d in all_devices if not d["is_contact_candidate"]]
if non_contact:
    config_lines.append("    # --- Other devices (commented out - remove # to enable) ---")
    for d in non_contact:
        dev_obj = indigo.devices[d["id"]]
        config_lines.append(
            make_config_entry(dev_obj, d["states"], commented=True) + ","
        )
    config_lines.append("")

config_lines.append('  ],')
config_lines.append("")

# --- variables section ---
config_lines.append('  "variables": [')
config_lines.append("")
config_lines.append("    # Add variables to monitor here.  Format:")
config_lines.append('    # {"id": 123456789, "name": "Variable_Name", "label": "Display Label"}')
config_lines.append("")
config_lines.append('  ]')
config_lines.append("")
config_lines.append("}")

config_text = "\n".join(config_lines) + "\n"

try:
    with open(CONFIG_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(config_text)
    log(f"Plugin config saved to:  {CONFIG_OUTPUT_PATH}")
except Exception as e:
    log(f"ERROR saving sensor_monitor_config.json: {e}")
    raise

# ======================================
# LOG SUMMARY
# ======================================

log(f"Total devices scanned:      {len(all_devices)}")
log(f"Contact sensor candidates:  {len(contact_sensors)}")
log("")

if contact_sensors:
    log("Contact sensor candidates (active in config):")
    log("")
    for d in contact_sensors:
        log(f"  {d['name']} (ID: {d['id']}, Folder: {d['folder']})")
    log("")
else:
    log("No contact sensor candidates found.")
    log("Check the full device list in device_discovery.json.")

log("")
log(f"Next steps:")
log(f"  1. Open: {CONFIG_OUTPUT_PATH}")
log(f"  2. Edit labels, add # to disable sensors you do not want")
log(f"  3. Remove # from any non-contact device lines you want to add")
log(f"  4. Reload: Plugins > Sensor Monitor > Reload Plugin")
