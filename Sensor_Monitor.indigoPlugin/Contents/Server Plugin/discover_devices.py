#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    discover_devices.py
# Description: Discovery script - scans all Indigo devices and saves full details
#              to a JSON file for review, and generates a ready-to-use
#              sensor_monitor_config.json for the Sensor Monitor plugin.
#              Run once from Indigo Script Editor.
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.5.5
#
# HOW TO USE
# ----------
# 1. Open Indigo > Scripts > New Script
# 2. Paste this entire file into the editor
# 3. Click Run
# 4. Open sensor_monitor_config.json at CONFIG_OUTPUT_PATH
#    (inside <Indigo base>/Logs/SensorMonitor/)
#    - Contact sensor candidates are ACTIVE (ready to use)
#    - All other devices are COMMENTED OUT (prefix # to disable)
#    - Edit labels, add # to disable, remove # to enable
# 5. Reload the plugin: Plugins > Sensor Monitor > Reload Plugin
# 6. Full device list is in device_discovery.json if you need to find anything

import indigo
import json
import os
import re
from datetime import datetime

# ======================================
# CONFIG
#
# indigo.server.getInstallFolderPath() returns the Indigo base directory,
# e.g. "/Library/Application Support/Perceptive Automation/Indigo 2025.1".
# Using the API (rather than a hardcoded string) means the paths update
# automatically when Indigo upgrades from 2025.1 to 2026.1.
#
# NOTE: The Indigo Script Editor does NOT set __file__, so file-relative
# paths cannot be used here.  The API call is the correct approach.
#
# JSON files are written into Logs/SensorMonitor/ so they appear alongside
# standard Indigo log files and are easy to find.
# ======================================

_INDIGO_BASE = indigo.server.getInstallFolderPath()
_LOG_DIR     = os.path.join(_INDIGO_BASE, "Logs", "SensorMonitor")

DISCOVERY_OUTPUT_PATH = os.path.join(_LOG_DIR, "device_discovery.json")
CONFIG_OUTPUT_PATH    = os.path.join(_LOG_DIR, "sensor_monitor_config.json")

# Plugin IDs whose devices are excluded from discovery entirely.
# Virtual devices can mimic any state, so they must be skipped.
# Alexa plugin creates a named mirror for every exposed Indigo device, so a
# switch called "HA Garage Door" would appear as a contact sensor without this.
# To check the pluginId of any device, open device_discovery.json after
# running this script - each entry includes a "plugin_id" field.
EXCLUDED_PLUGIN_IDS   = {
    "com.perceptiveautomation.indigoplugin.virtualdevices",  # Virtual Devices (built-in)
    "com.indigodomo.indigoplugin.alexa",                     # Alexa (mirrors real devices by name)
}

# State names that strongly suggest a contact/door/window sensor
CONTACT_STATE_NAMES   = {"contact", "doorSensor", "windowSensor"}

# Keywords in device name that suggest a contact/door/window sensor
CONTACT_NAME_KEYWORDS = [
    "contact", "door", "window", "entry", "gate", "patio", "garage"
]

# State names that strongly suggest a motion/occupancy/presence sensor
MOTION_STATE_NAMES    = {"occupancy", "pirDetection", "presence", "motion", "motionDetected"}

# Keywords in device name that suggest a motion/occupancy/presence sensor
MOTION_NAME_KEYWORDS  = [
    "motion", "pir", "presence", "occupancy", "mmwave", "radar"
]

# Words that veto name-keyword matching for both contact and motion detection.
# If any of these appear (substring, case-insensitive) in a device name, the
# device is NOT classified as a sensor via name alone — state-name matching
# (contact, doorSensor, occupancy, etc.) is still authoritative.
NAME_EXCLUSION_KEYWORDS = {
    "temperature", "temp",              # Temperature sensors
    "luminance", "lux", "illuminance",  # Light-level sensors
    "power",                            # Power monitoring (watts)
    "current",                          # Electrical current monitoring (amps)
    "voltage",                          # Voltage monitoring
    "energy",                           # Energy / consumption monitoring
    "humidity",                         # Humidity sensors
    "repeater",                         # Network repeaters / range extenders
    "plug",                             # Smart plugs (not door/window sensors)
    "control",                          # Control devices (locks, dimmers, etc.)
    "virtual",                          # Virtual devices not in plugin exclusion set
    "light", "lights",                  # Lighting devices (e.g. Shelly strip lights)
}

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


def is_excluded_plugin(dev):
    """Return True if the device belongs to a plugin that should be skipped."""
    return getattr(dev, "pluginId", "") in EXCLUDED_PLUGIN_IDS


def is_name_excluded(dev):
    """Return True if dev's name contains a name exclusion keyword.

    Applied as a scan-level filter to non-sensor devices: if the device is
    not classified as a contact or motion sensor (via state-name matching)
    AND its name contains an exclusion keyword, it is hidden from the config
    entirely — even from the commented-out 'Other devices' section.
    """
    name_lower = dev.name.lower()
    return any(kw in name_lower for kw in NAME_EXCLUSION_KEYWORDS)


def is_contact_candidate(dev, states):
    """Return True if the device looks like a contact/door/window sensor.

    A device is a contact candidate only if it can be monitored as a binary
    sensor.  Specifically:
      - Has a known contact state name (contact, doorSensor, windowSensor)
        regardless of device type, OR
      - Has an onState attribute AND its name contains a contact keyword
        AND does NOT contain a motion keyword
        AND does NOT contain a name exclusion keyword.

    Devices without onState are excluded from name-keyword matching.
    NAME_EXCLUSION_KEYWORDS prevent temperature sensors, power monitors, smart
    plugs, etc. from being picked up via name matching.  For example,
    'Front Door Temperature' has 'door' in its name but 'temperature' vetoes it.
    State-name matching always wins regardless of the device name.
    """
    state_match = bool(CONTACT_STATE_NAMES & set(states.keys()))
    if state_match:
        return True
    if not hasattr(dev, "onState"):
        return False
    name_lower = dev.name.lower()
    if any(kw in name_lower for kw in NAME_EXCLUSION_KEYWORDS):
        return False
    has_contact_kw = any(kw in name_lower for kw in CONTACT_NAME_KEYWORDS)
    has_motion_kw  = any(kw in name_lower for kw in MOTION_NAME_KEYWORDS)
    return has_contact_kw and not has_motion_kw


def is_motion_candidate(dev, states):
    """Return True if the device looks like a motion/occupancy/presence sensor.

    A device is a motion candidate only if it can be monitored as a binary
    sensor.  Specifically:
      - Has a known motion state name (occupancy, pirDetection, presence,
        motion, motionDetected) regardless of device type, OR
      - Has an onState attribute AND its name contains a motion keyword
        AND does NOT contain a name exclusion keyword.

    Devices without onState are excluded from name-keyword matching.
    NAME_EXCLUSION_KEYWORDS veto name-based classification (state-name
    matching is never affected).
    """
    state_match = bool(MOTION_STATE_NAMES & set(states.keys()))
    if state_match:
        return True
    if not hasattr(dev, "onState"):
        return False
    name_lower = dev.name.lower()
    if any(kw in name_lower for kw in NAME_EXCLUSION_KEYWORDS):
        return False
    return any(kw in name_lower for kw in MOTION_NAME_KEYWORDS)


def motion_state_list(states):
    """Return sorted list of motion state names present in states dict.
    Falls back to ['onState'] if none found."""
    found = sorted(s for s in MOTION_STATE_NAMES if s in states)
    return found if found else ["onState"]


def make_motion_entry(dev, state_name, commented=False):
    """Return a JSON config line for a motion sensor device and state."""
    entry = (
        f'    {{"id": {dev.id}, "name": "{dev.name}", '
        f'"state": "{state_name}", "label": "{dev.name}", '
        f'"on_text": "ON", "off_text": "OFF"}}'
    )
    return f"# {entry}" if commented else entry


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

# --- Read excluded_ids from existing config (preserved across re-discovery) ---
# To permanently exclude a device, add its ID to "excluded_ids" in the config file
# and re-run this script.  The ID will be kept commented-out on every future run.
excluded_ids = set()
if os.path.exists(CONFIG_OUTPUT_PATH):
    try:
        with open(CONFIG_OUTPUT_PATH, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()
        active_lines = [l for l in existing_lines if not l.lstrip().startswith("#")]
        json_str     = re.sub(r",(\s*[}\]])", r"\1", "".join(active_lines))
        existing_cfg = json.loads(json_str)
        excluded_ids = set(int(x) for x in existing_cfg.get("excluded_ids", []))
        if excluded_ids:
            log(f"Preserving {len(excluded_ids)} excluded device ID(s) from existing config")
    except Exception:
        excluded_ids = set()

all_devices     = []
contact_sensors = []
motion_sensors  = []

for dev in indigo.devices:
    if is_excluded_plugin(dev):
        continue  # Skip virtual/Alexa plugin devices entirely

    states     = get_states(dev)
    is_contact = is_contact_candidate(dev, states)
    is_motion  = (not is_contact) and is_motion_candidate(dev, states)

    # Skip non-sensor devices whose names contain exclusion keywords
    # (temperature, luminance, power, voltage, etc.) — not contact/motion sensors.
    # If state-name matching has already classified the device as a sensor,
    # name exclusion is irrelevant and the device is kept.
    if not (is_contact or is_motion) and is_name_excluded(dev):
        continue

    folder      = get_folder_name(dev)
    sensor_type = ("contact" if is_contact
                   else "motion" if is_motion
                   else None)

    entry = {
        "id":          dev.id,
        "name":        dev.name,
        "folder":      folder,
        "enabled":     dev.enabled,
        "plugin_id":   getattr(dev, "pluginId", ""),
        "on_state":    dev.onState if hasattr(dev, "onState") else None,
        "states":      states,
        "sensor_type": sensor_type,
        "suggested_device_monitor_entry": (
            suggest_py_entry(dev, states) if is_contact else None
        ),
    }

    all_devices.append(entry)
    if is_contact:
        contact_sensors.append(entry)
    elif is_motion:
        motion_sensors.append(entry)

# Sort alphabetically by name
all_devices.sort(    key=lambda x: x["name"].lower())
contact_sensors.sort(key=lambda x: x["name"].lower())
motion_sensors.sort( key=lambda x: x["name"].lower())

# Separate active (to be monitored) from excluded (commented-out by user choice)
active_contacts   = [d for d in contact_sensors if d["id"] not in excluded_ids]
excluded_contacts = [d for d in contact_sensors if d["id"] in excluded_ids]
active_motions    = [d for d in motion_sensors  if d["id"] not in excluded_ids]
excluded_motions  = [d for d in motion_sensors  if d["id"] in excluded_ids]

# ======================================
# SAVE device_discovery.json  (full detail)
# ======================================

discovery_output = {
    "generated":          datetime.now().isoformat(),
    "total_devices":      len(all_devices),
    "contact_candidates": len(contact_sensors),
    "motion_candidates":  len(motion_sensors),
    "summary": (
        "Review 'contact_sensors' and 'motion_sensors' for ready-to-paste entries. "
        "All devices are in 'all_devices' if you need to find something specific."
    ),
    "contact_sensors": contact_sensors,
    "motion_sensors":  motion_sensors,
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
# Active contact/motion candidates -> active entries (no # prefix)
# Excluded devices (in excluded_ids) -> commented-out entries (preserved)
# All other devices                -> commented entries (# prefix, for reference)
#
# To permanently exclude a device from re-discovery:
#   1. Add its ID to "excluded_ids" in this file
#   2. Save and re-run this script
#   The device will remain commented-out on every future run.
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
excl_list = ", ".join(str(x) for x in sorted(excluded_ids))
config_lines.append(f'  "excluded_ids": [{excl_list}],')
config_lines.append('  "_exclude_hint": "Add a device ID to excluded_ids to '
                    'keep it commented-out after every re-discovery run.",')
config_lines.append("")

# --- devices section ---
config_lines.append('  "devices": [')
config_lines.append("")

if active_contacts:
    config_lines.append("    # --- Contact / Door / Window sensors (active) ---")
    for d in active_contacts:
        dev_obj = indigo.devices[d["id"]]
        config_lines.append(
            make_config_entry(dev_obj, d["states"], commented=False) + ","
        )
    config_lines.append("")

if active_motions:
    config_lines.append("    # --- Motion / Occupancy / Presence sensors (active) ---")
    for d in active_motions:
        dev_obj    = indigo.devices[d["id"]]
        mot_states = motion_state_list(d["states"])
        for state_name in mot_states:
            config_lines.append(
                make_motion_entry(dev_obj, state_name, commented=False) + ","
            )
    config_lines.append("")

if excluded_contacts or excluded_motions:
    config_lines.append(
        "    # --- Excluded sensors "
        "(add ID to 'excluded_ids' above to keep excluded on re-discovery) ---"
    )
    for d in excluded_contacts:
        dev_obj = indigo.devices[d["id"]]
        config_lines.append(
            make_config_entry(dev_obj, d["states"], commented=True) + ","
        )
    for d in excluded_motions:
        dev_obj    = indigo.devices[d["id"]]
        mot_states = motion_state_list(d["states"])
        for state_name in mot_states:
            config_lines.append(
                make_motion_entry(dev_obj, state_name, commented=True) + ","
            )
    config_lines.append("")

# All other devices commented out for reference
other = [d for d in all_devices if d["sensor_type"] is None]
if other:
    config_lines.append("    # --- Other devices (not contact/motion - remove # to enable) ---")
    for d in other:
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

log(f"Total devices scanned:        {len(all_devices)}")
log(f"Contact sensor candidates:    {len(contact_sensors)} ({len(active_contacts)} active, {len(excluded_contacts)} excluded)")
log(f"Motion sensor candidates:     {len(motion_sensors)} ({len(active_motions)} active, {len(excluded_motions)} excluded)")
log("")

if active_contacts:
    log("Contact sensors (active in config):")
    log("")
    for d in active_contacts:
        log(f"  {d['name']} (ID: {d['id']}, Folder: {d['folder']})")
    log("")

if active_motions:
    log("Motion sensors (active in config):")
    log("")
    for d in active_motions:
        mot_states = motion_state_list(d["states"])
        log(f"  {d['name']} (ID: {d['id']}, Folder: {d['folder']}) -> states: {mot_states}")
    log("")

if excluded_contacts or excluded_motions:
    log("Excluded sensors (commented-out in config):")
    log("")
    for d in excluded_contacts + excluded_motions:
        log(f"  {d['name']} (ID: {d['id']}) - add to excluded_ids to keep excluded")
    log("")

if not active_contacts and not active_motions:
    log("No active contact or motion sensor candidates found.")
    log("Check the full device list in device_discovery.json.")

log("")
log(f"Next steps:")
log(f"  1. Open: {CONFIG_OUTPUT_PATH}")
log(f"  2. Edit labels, add # to disable sensors you do not want")
log(f"  3. To permanently exclude a sensor: add its ID to 'excluded_ids' in the config")
log(f"  4. Remove # from any non-contact device lines you want to add")
log(f"  5. Reload: Plugins > Sensor Monitor > Reload Plugin")
