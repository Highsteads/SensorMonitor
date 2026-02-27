#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Sensor Monitor - subscribes to device and variable changes and logs events
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.3.0

try:
    import indigo
except ImportError:
    pass

import json
import os
import re
from datetime import datetime

# ======================================
# CONFIG FILE PATH
#
# If this file exists the plugin loads its device and variable lists from it,
# instead of from the hardcoded DEVICE_MONITOR / VARIABLE_MONITOR dicts below.
#
# The file supports # comment lines to disable individual entries without
# deleting them.  Run discover_devices.py in the Indigo Script Editor to
# generate an initial config file, then edit as needed.
#
# Reload the plugin after saving changes:
#   Plugins > Sensor Monitor > Reload Plugin
# ======================================

CONFIG_PATH = os.path.expanduser(
    "~/Documents/Indigo/SensorMonitor/sensor_monitor_config.json"
)

# ======================================
# DEVICE MONITOR CONFIGURATION  (FALLBACK)
#
# Used only when sensor_monitor_config.json does not exist.
# Once a config file is in place these dicts are ignored.
#
# Key   = Indigo device ID (int)
# Value = list of state configs to monitor for that device
#
# Each state config:
#   "state"    : "onState" uses device.onState directly;
#                any other name reads from device.states dict
#   "label"    : shown in log after the device name
#   "on_text"  : optional - text when state is True  (default: "ON")
#   "off_text" : optional - text when state is False (default: "OFF")
#
# Device name is always read live from Indigo (newDev.name),
# so renaming a device in Indigo is instantly reflected in logs.
# ======================================
DEVICE_MONITOR = {

    # --- Bathroom Basin ---
    812537401:  [{"state": "onState",       "label": "Occupancy"}],
    1976004986: [{"state": "pirDetection",  "label": "PIR"},
                 {"state": "presence",      "label": "mmWave Presence"}],

    # --- Bathroom Door ---
    1184619127: [{"state": "onState",       "label": "Occupancy"}],
    415253439:  [{"state": "onState",       "label": "Contact",
                  "on_text": "OPEN",        "off_text": "CLOSED"}],

    # --- Kitchen ---
    1649680462: [{"state": "presence",      "label": "mmWave Presence"}],
    1440351705: [{"state": "onState",       "label": "mmWave Presence"}],
    467551931:  [{"state": "onState",       "label": "Occupancy"}],

    # --- Living Room ---
    408117572:  [{"state": "onState",       "label": "mmWave Presence"}],
    1256890181: [{"state": "onState",       "label": "mmWave Presence"}],
    1807623843: [{"state": "onState",       "label": "mmWave Presence"}],

    # --- Window / Door Contacts ---
    # Replace 0 with your actual Indigo device IDs.
    # on_text / off_text customise the log label for True / False states.
    # 0: [{"state": "onState", "label": "Front Door",  "on_text": "OPEN", "off_text": "CLOSED"}],
    # 0: [{"state": "onState", "label": "Back Door",   "on_text": "OPEN", "off_text": "CLOSED"}],
    # 0: [{"state": "onState", "label": "Lounge Window","on_text": "OPEN", "off_text": "CLOSED"}],
}

# ======================================
# VARIABLE MONITOR CONFIGURATION  (FALLBACK)
#
# Used only when sensor_monitor_config.json does not exist.
#
# Key   = Indigo variable ID (int)
# Value = config dict
#
# Each config:
#   "label" : optional - text shown in log (defaults to variable.name if omitted)
#
# Log format: [HH:MM:SS.mmm] Label: old_value -> new_value
#
# Variable ID can be found by right-clicking the variable in Indigo
# and choosing "Copy Variable ID to Clipboard".
# ======================================
VARIABLE_MONITOR = {

    # Variables log value changes as: [ts] Label: old_value -> new_value
    # "label" is optional - defaults to variable name if omitted
    241032502: {"label": "Lux Level"},
}


class Plugin(indigo.PluginBase):

    # ======================================
    # LIFECYCLE
    # ======================================

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super().__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = pluginPrefs.get("showDebugInfo", False)
        self._load_config()

    def startup(self):
        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()
        self.logger.info(
            f"Sensor Monitor {self.pluginVersion} started - "
            f"monitoring {len(self.device_monitor)} devices, "
            f"{len(self.variable_monitor)} variables"
        )
        self._validate_monitored_devices()
        self._validate_monitored_variables()

    def shutdown(self):
        self.logger.info("Sensor Monitor stopped")

    # ======================================
    # DEVICE CHANGE CALLBACK
    # ======================================

    def deviceUpdated(self, origDev, newDev):
        super().deviceUpdated(origDev, newDev)

        if newDev.id not in self.device_monitor:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # --- Name change detection ---
        if origDev.name != newDev.name:
            indigo.server.log(
                f"[{timestamp}] [Sensor Monitor] Device renamed: "
                f"'{origDev.name}' -> '{newDev.name}' (ID: {newDev.id})"
            )

        # --- State change logging ---
        for config in self.device_monitor[newDev.id]:
            state_name = config["state"]

            try:
                if state_name == "onState":
                    old_val = origDev.onState
                    new_val = newDev.onState
                else:
                    old_val = origDev.states.get(state_name)
                    new_val = newDev.states.get(state_name)
            except Exception as e:
                self.logger.error(
                    f"[{timestamp}] Error reading '{state_name}' "
                    f"for {newDev.name}: {e}"
                )
                continue

            if old_val == new_val:
                continue  # State did not change - skip

            on_text    = config.get("on_text",  "ON")
            off_text   = config.get("off_text", "OFF")
            state_text = on_text if new_val else off_text

            indigo.server.log(
                f"[{timestamp}] {newDev.name} {config['label']} {state_text}"
            )

    # ======================================
    # DEVICE DELETED CALLBACK
    # ======================================

    def deviceDeleted(self, dev):
        super().deviceDeleted(dev)

        if dev.id not in self.device_monitor:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.logger.warning(
            f"[{timestamp}] [Sensor Monitor] WARNING - Monitored device deleted: "
            f"'{dev.name}' (ID: {dev.id}) - "
            f"remove from config file or DEVICE_MONITOR in plugin.py"
        )

    # ======================================
    # VARIABLE CHANGE CALLBACK
    # ======================================

    def variableUpdated(self, origVar, newVar):
        super().variableUpdated(origVar, newVar)

        if newVar.id not in self.variable_monitor:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # --- Name change detection ---
        if origVar.name != newVar.name:
            indigo.server.log(
                f"[{timestamp}] [Sensor Monitor] Variable renamed: "
                f"'{origVar.name}' -> '{newVar.name}' (ID: {newVar.id})"
            )

        # --- Value change logging ---
        if origVar.value == newVar.value:
            return

        config = self.variable_monitor[newVar.id]
        label  = config.get("label", newVar.name)

        indigo.server.log(
            f"[{timestamp}] {label}: {origVar.value} -> {newVar.value}"
        )

    # ======================================
    # VARIABLE DELETED CALLBACK
    # ======================================

    def variableDeleted(self, var):
        super().variableDeleted(var)

        if var.id not in self.variable_monitor:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.logger.warning(
            f"[{timestamp}] [Sensor Monitor] WARNING - Monitored variable deleted: "
            f"'{var.name}' (ID: {var.id}) - "
            f"remove from config file or VARIABLE_MONITOR in plugin.py"
        )

    # ======================================
    # PRIVATE HELPERS
    # ======================================

    def _load_config(self, config_path=None):
        """Load device and variable monitor lists from the JSON config file.

        If the config file does not exist, falls back to the hardcoded
        DEVICE_MONITOR and VARIABLE_MONITOR dicts defined at module level.

        The JSON file supports comment lines: any line whose first
        non-whitespace character is # is stripped before parsing.
        Trailing commas before ] or } are silently cleaned up so the
        file is easier to edit by hand.

        config_path  optional path override (used by tests).
        """
        path = config_path or CONFIG_PATH

        if not os.path.exists(path):
            # No config file - use the module-level fallback dicts (deep copy)
            self.device_monitor   = {k: [dict(s) for s in v]
                                     for k, v in DEVICE_MONITOR.items()}
            self.variable_monitor = {k: dict(v)
                                     for k, v in VARIABLE_MONITOR.items()}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Strip comment lines (first non-whitespace char is #)
            active_lines = [l for l in lines if not l.lstrip().startswith("#")]
            json_str     = "".join(active_lines)

            # Remove trailing commas before ] or } (not valid JSON)
            json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

            config = json.loads(json_str)

        except Exception as e:
            # File exists but unreadable or invalid - fall back and warn
            self.device_monitor   = {k: [dict(s) for s in v]
                                     for k, v in DEVICE_MONITOR.items()}
            self.variable_monitor = {k: dict(v)
                                     for k, v in VARIABLE_MONITOR.items()}
            try:
                self.logger.warning(
                    f"[Sensor Monitor] Could not read config file: {e} - "
                    f"using hardcoded fallback dicts"
                )
            except Exception:
                pass  # logger may not be ready during __init__
            return

        # --- Build self.device_monitor from "devices" list ---
        self.device_monitor = {}
        for entry in config.get("devices", []):
            dev_id     = int(entry["id"])
            state_conf = {
                "state": entry.get("state", "onState"),
                "label": entry.get("label", entry.get("name", f"Device {dev_id}")),
            }
            if "on_text"  in entry:
                state_conf["on_text"]  = entry["on_text"]
            if "off_text" in entry:
                state_conf["off_text"] = entry["off_text"]
            self.device_monitor.setdefault(dev_id, []).append(state_conf)

        # --- Build self.variable_monitor from "variables" list ---
        self.variable_monitor = {}
        for entry in config.get("variables", []):
            var_id = int(entry["id"])
            self.variable_monitor[var_id] = {
                "label": entry.get("label", entry.get("name", f"Variable {var_id}"))
            }

        try:
            self.logger.info(
                f"[Sensor Monitor] Config loaded from: {path} "
                f"({len(self.device_monitor)} devices, "
                f"{len(self.variable_monitor)} variables)"
            )
        except Exception:
            pass  # logger may not be ready during __init__

    def _validate_monitored_devices(self):
        """Check all device_monitor entries exist in Indigo at startup."""
        missing = []
        found   = []

        for device_id in self.device_monitor:
            if device_id in indigo.devices:
                found.append(f"  [OK] {indigo.devices[device_id].name} (ID: {device_id})")
            else:
                missing.append(f"  [!]  ID {device_id} - not found in Indigo")

        self.logger.info(f"[Sensor Monitor] Device validation - {len(found)} found, {len(missing)} missing:")
        for entry in found:
            self.logger.info(entry)

        if missing:
            for entry in missing:
                self.logger.warning(entry)
            self.logger.warning(
                f"[Sensor Monitor] {len(missing)} monitored device(s) not found - "
                f"check IDs in config file or DEVICE_MONITOR in plugin.py"
            )
        else:
            self.logger.info("[Sensor Monitor] All monitored devices validated OK")

    def _validate_monitored_variables(self):
        """Check all variable_monitor entries exist in Indigo at startup."""
        if not self.variable_monitor:
            return

        missing = []
        found   = []

        for var_id in self.variable_monitor:
            if var_id in indigo.variables:
                found.append(f"  [OK] {indigo.variables[var_id].name} (ID: {var_id})")
            else:
                missing.append(f"  [!]  ID {var_id} - not found in Indigo")

        self.logger.info(f"[Sensor Monitor] Variable validation - {len(found)} found, {len(missing)} missing:")
        for entry in found:
            self.logger.info(entry)

        if missing:
            for entry in missing:
                self.logger.warning(entry)
            self.logger.warning(
                f"[Sensor Monitor] {len(missing)} monitored variable(s) not found - "
                f"check IDs in config file or VARIABLE_MONITOR in plugin.py"
            )
        else:
            self.logger.info("[Sensor Monitor] All monitored variables validated OK")
