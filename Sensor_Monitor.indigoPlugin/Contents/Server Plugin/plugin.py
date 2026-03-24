#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Sensor Monitor - subscribes to device and variable changes and logs events
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.5.9

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
# indigo.server.getInstallFolderPath() returns the Indigo base directory,
# e.g. "/Library/Application Support/Perceptive Automation/Indigo 2025.1".
# Using the API (rather than a hardcoded string) means the paths update
# automatically when Indigo upgrades from 2025.1 to 2026.1 - no code changes
# needed.
#
# NOTE: Indigo's plugin runtime does NOT set __file__, so file-relative paths
# cannot be used at module level.  The API call is the correct approach.
#
# The except block is the fallback for the test environment where indigo is a
# MagicMock and os.path.join(MagicMock(), ...) raises TypeError.  Tests then
# override CONFIG_PATH / DISCOVERY_OUTPUT_PATH with safe temp paths anyway.
#
# If this config file exists the plugin loads its device and variable lists
# from it, instead of from the hardcoded DEVICE_MONITOR / VARIABLE_MONITOR
# dicts below.  The file supports # comment lines to disable individual
# entries.  Run discover_devices.py in the Indigo Script Editor to generate
# an initial config file, then edit as needed.
#
# Reload the plugin after saving changes:
#   Plugins > Sensor Monitor > Reload Plugin
# ======================================

try:
    _INDIGO_BASE = indigo.server.getInstallFolderPath()
    _LOG_DIR     = os.path.join(_INDIGO_BASE, "Logs", "SensorMonitor")
except Exception:
    # Fallback used in test environment (indigo is a MagicMock)
    _LOG_DIR = "/Library/Application Support/Perceptive Automation/Indigo 2025.1/Logs/SensorMonitor"

CONFIG_PATH           = os.path.join(_LOG_DIR, "sensor_monitor_config.json")
DISCOVERY_OUTPUT_PATH = os.path.join(_LOG_DIR, "device_discovery.json")

# ======================================
# DISCOVERY CONSTANTS
#
# Used by the menu-driven discovery methods.
# ======================================

_CONTACT_STATE_NAMES   = {"contact", "doorSensor", "windowSensor"}
_CONTACT_NAME_KEYWORDS = ["contact", "door", "window", "entry", "gate", "patio", "garage"]

_MOTION_STATE_NAMES    = {"occupancy", "pirDetection", "presence", "motion", "motionDetected"}
_MOTION_NAME_KEYWORDS  = ["motion", "pir", "presence", "occupancy", "mmwave", "radar"]

# ======================================
# NAME EXCLUSION KEYWORDS
#
# If any of these words appear (as substrings, case-insensitive) in a device
# name, name-keyword matching is vetoed — the device will NOT be classified
# as a contact or motion sensor via name alone.
#
# This prevents temperature sensors, power monitors, smart plugs, etc. from
# being picked up just because their name contains a sensor keyword.
# Example: 'Front Door Temperature' has 'door' in its name, but 'temperature'
#          disqualifies it from name-based classification.
#
# IMPORTANT: state-name matching (contact / doorSensor / occupancy etc.) is
# NEVER vetoed — a device with an explicit sensor state is always classified
# correctly regardless of its name.
#
# Add keywords here to block new false-positive categories.
# ======================================

_NAME_EXCLUSION_KEYWORDS = {
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
# EXCLUDED PLUGIN IDs
#
# Devices managed by these plugins are silently skipped during discovery —
# they will not appear in sensor_monitor_config.json at all (not even
# commented-out).  Virtual devices can mimic any state, so classifying them
# as sensors would cause false triggers.
#
# If you ever need to add a real sensor from a plugin listed here (unlikely),
# add it manually to the config file.
#
# To verify the pluginId for a device: run Discover Devices and then open
# device_discovery.json — each entry includes the plugin_id field.
# ======================================

_EXCLUDED_PLUGIN_IDS = {
    "com.perceptiveautomation.indigoplugin.virtualdevices",  # Virtual Devices (built-in)
    "com.indigodomo.indigoplugin.alexa",                     # Alexa (mirrors real devices by name)
}

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
                    old_val = getattr(origDev, "onState", None)
                    new_val = getattr(newDev,  "onState", None)
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
            label      = config["label"]

            # Suppress the label if it is identical to the device name to
            # avoid e.g. "Side Passage Motion Side Passage Motion OFF"
            if label == newDev.name:
                indigo.server.log(f"[{timestamp}] {newDev.name} {state_text}")
            else:
                indigo.server.log(f"[{timestamp}] {newDev.name} {label} {state_text}")

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
    # MENU ITEM CALLBACKS
    # Plugins > Sensor Monitor > ...
    # ======================================

    def menuDiscoverDevices(self):
        """Scan all Indigo devices, write device_discovery.json and
        sensor_monitor_config.json to <Indigo base>/Logs/SensorMonitor/.

        Contact and motion sensor candidates are written as active entries,
        unless their device ID is listed in the existing config's "excluded_ids"
        list — those are written as commented-out entries and the excluded_ids
        list is preserved so future re-discovery runs respect the exclusion.

        To permanently exclude a device from monitoring:
          1. Edit sensor_monitor_config.json
          2. Add the device ID to the "excluded_ids" list, e.g.:
               "excluded_ids": [123456789],
          3. Save and re-run discovery (Plugins > Sensor Monitor > Discover Devices)
          The device will now appear commented-out on every future re-discovery.
        """
        ts = datetime.now().strftime('%H:%M:%S')
        self.logger.info(f"[{ts}] [Sensor Monitor] Device discovery starting...")

        # --- Read excluded_ids from existing config (preserved across re-discovery) ---
        excluded_ids = set()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()
                active_lines = [l for l in existing_lines if not l.lstrip().startswith("#")]
                json_str     = re.sub(r",(\s*[}\]])", r"\1", "".join(active_lines))
                existing_cfg = json.loads(json_str)
                excluded_ids = set(int(x) for x in existing_cfg.get("excluded_ids", []))
                if excluded_ids:
                    self.logger.info(
                        f"[{ts}] [Sensor Monitor] Preserving {len(excluded_ids)} "
                        f"excluded device(s) from existing config"
                    )
            except Exception:
                excluded_ids = set()

        all_devices     = []
        contact_sensors = []
        motion_sensors  = []

        for dev in indigo.devices:
            if self._disc_is_excluded_plugin(dev):
                continue  # Skip virtual/Alexa plugin devices entirely

            states     = self._disc_states(dev)
            is_contact = self._disc_is_contact(dev, states)
            is_motion  = (not is_contact) and self._disc_is_motion(dev, states)

            # Skip non-sensor devices whose names contain exclusion keywords
            # (temperature, luminance, power, voltage, etc.) — these are not
            # contact or motion sensors and clutter the config unnecessarily.
            # If state-name matching has already classified the device as a
            # sensor, name exclusion is irrelevant and we keep it.
            if not (is_contact or is_motion) and self._disc_is_name_excluded(dev):
                continue

            folder      = self._disc_folder_name(dev)
            sensor_type = ("contact" if is_contact
                           else "motion" if is_motion
                           else None)

            entry = {
                "id":          dev.id,
                "name":        dev.name,
                "folder":      folder,
                "enabled":     getattr(dev, "enabled", True),
                "plugin_id":   getattr(dev, "pluginId", ""),
                "on_state":    dev.onState if hasattr(dev, "onState") else None,
                "states":      states,
                "sensor_type": sensor_type,
            }
            all_devices.append(entry)
            if is_contact:
                contact_sensors.append(entry)
            elif is_motion:
                motion_sensors.append(entry)

        all_devices.sort(    key=lambda x: x["name"].lower())
        contact_sensors.sort(key=lambda x: x["name"].lower())
        motion_sensors.sort( key=lambda x: x["name"].lower())

        # Separate active (to be monitored) from excluded (commented-out by user choice)
        active_contacts   = [d for d in contact_sensors if d["id"] not in excluded_ids]
        excluded_contacts = [d for d in contact_sensors if d["id"] in excluded_ids]
        active_motions    = [d for d in motion_sensors  if d["id"] not in excluded_ids]
        excluded_motions  = [d for d in motion_sensors  if d["id"] in excluded_ids]

        # --- Save device_discovery.json ---
        try:
            os.makedirs(os.path.dirname(DISCOVERY_OUTPUT_PATH), exist_ok=True)
            discovery_output = {
                "generated":          datetime.now().isoformat(),
                "total_devices":      len(all_devices),
                "contact_candidates": len(contact_sensors),
                "motion_candidates":  len(motion_sensors),
                "contact_sensors":    contact_sensors,
                "motion_sensors":     motion_sensors,
                "all_devices":        all_devices,
            }
            with open(DISCOVERY_OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(discovery_output, f, indent=2, default=str)
            self.logger.info(f"[{ts}] Full device list saved to: {DISCOVERY_OUTPUT_PATH}")
        except Exception as e:
            self.logger.error(f"[{ts}] ERROR saving device_discovery.json: {e}")

        # --- Save sensor_monitor_config.json ---
        try:
            lines = ["{"]
            lines.append(f'  "_generated": "{datetime.now().isoformat()}",')
            lines.append(f'  "_total_scanned": {len(all_devices)},')
            lines.append('  "_usage": "Lines starting with # are ignored. '
                         'Reload plugin after changes.",')
            excl_list = ", ".join(str(x) for x in sorted(excluded_ids))
            lines.append(f'  "excluded_ids": [{excl_list}],')
            lines.append('  "_exclude_hint": "Add a device ID to excluded_ids to '
                         'keep it commented-out after every re-discovery run.",')
            lines.append("")
            lines.append('  "devices": [')
            lines.append("")

            # Active contact sensors - one entry per device
            if active_contacts:
                lines.append("    # --- Contact / Door / Window sensors (active) ---")
                for d in active_contacts:
                    dev_obj = indigo.devices[d["id"]]
                    lines.append(
                        self._disc_config_entry(dev_obj, d["states"], commented=False) + ","
                    )
                lines.append("")

            # Active motion sensors - one entry per detected state name
            if active_motions:
                lines.append("    # --- Motion / Occupancy / Presence sensors (active) ---")
                for d in active_motions:
                    dev_obj    = indigo.devices[d["id"]]
                    mot_states = self._disc_motion_states(d["states"])
                    for state_name in mot_states:
                        lines.append(
                            self._disc_motion_entry(dev_obj, state_name, commented=False) + ","
                        )
                lines.append("")

            # Excluded sensors - written commented-out, preserved across re-discovery
            if excluded_contacts or excluded_motions:
                lines.append(
                    "    # --- Excluded sensors "
                    "(add ID to 'excluded_ids' above to keep excluded on re-discovery) ---"
                )
                for d in excluded_contacts:
                    dev_obj = indigo.devices[d["id"]]
                    lines.append(
                        self._disc_config_entry(dev_obj, d["states"], commented=True) + ","
                    )
                for d in excluded_motions:
                    dev_obj    = indigo.devices[d["id"]]
                    mot_states = self._disc_motion_states(d["states"])
                    for state_name in mot_states:
                        lines.append(
                            self._disc_motion_entry(dev_obj, state_name, commented=True) + ","
                        )
                lines.append("")

            # All other devices commented out for reference only
            other = [d for d in all_devices if d["sensor_type"] is None]
            if other:
                lines.append("    # --- Other devices (not contact/motion - remove # to enable) ---")
                for d in other:
                    dev_obj = indigo.devices[d["id"]]
                    lines.append(
                        self._disc_config_entry(dev_obj, d["states"], commented=True) + ","
                    )
                lines.append("")

            lines.append('  ],')
            lines.append("")
            lines.append('  "variables": [')
            lines.append("")
            lines.append(
                '    # Add variables: {"id": 123456789, "name": "Var_Name", "label": "Display Label"}'
            )
            lines.append("")
            lines.append('  ]')
            lines.append("}")

            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.logger.info(f"[{ts}] Plugin config saved to: {CONFIG_PATH}")
        except Exception as e:
            self.logger.error(f"[{ts}] ERROR saving sensor_monitor_config.json: {e}")

        # --- Summary ---
        self.logger.info(
            f"[{ts}] Discovery complete: {len(all_devices)} devices scanned, "
            f"{len(active_contacts)} contact, {len(active_motions)} motion sensor(s) active"
        )
        if excluded_contacts or excluded_motions:
            excl_names = [d["name"] for d in excluded_contacts + excluded_motions]
            self.logger.info(
                f"[{ts}] Excluded (commented-out in config): {', '.join(excl_names)}"
            )
        if active_contacts:
            self.logger.info(f"[{ts}] Contact sensors:")
            for d in active_contacts:
                self.logger.info(f"[{ts}]   {d['name']} (ID: {d['id']}, Folder: {d['folder']})")
        if active_motions:
            self.logger.info(f"[{ts}] Motion sensors:")
            for d in active_motions:
                self.logger.info(f"[{ts}]   {d['name']} (ID: {d['id']}, Folder: {d['folder']})")
        self.logger.info(
            f"[{ts}] Reload to apply: Plugins > Sensor Monitor > Reload Plugin"
        )

    def menuFindContactSensors(self):
        """Log all contact/door/window and motion/occupancy sensor candidates."""
        ts = datetime.now().strftime('%H:%M:%S')
        self.logger.info(f"[{ts}] === Contact & Motion Sensor Discovery ===")

        contact_found = []
        motion_found  = []

        for dev in indigo.devices:
            if self._disc_is_excluded_plugin(dev):
                continue  # Skip virtual devices and other excluded plugin devices

            states = self._disc_states(dev)
            if self._disc_is_contact(dev, states):
                contact_found.append({
                    "id":     dev.id,
                    "name":   dev.name,
                    "folder": self._disc_folder_name(dev),
                    "states": states,
                })
            elif self._disc_is_motion(dev, states):
                motion_found.append({
                    "id":     dev.id,
                    "name":   dev.name,
                    "folder": self._disc_folder_name(dev),
                    "states": states,
                })

        total = len(contact_found) + len(motion_found)
        if not total:
            self.logger.info(f"[{ts}] No contact or motion sensors found.")
        else:
            if contact_found:
                self.logger.info(f"[{ts}] Contact sensors ({len(contact_found)}):")
                for d in sorted(contact_found, key=lambda x: x["name"]):
                    dev_obj = indigo.devices[d["id"]]
                    entry   = self._disc_config_entry(dev_obj, d["states"], commented=False)
                    self.logger.info(f"[{ts}]   {d['name']}  (ID: {d['id']}, Folder: {d['folder']})")
                    self.logger.info(f"[{ts}]   {entry}")
            if motion_found:
                self.logger.info(f"[{ts}] Motion sensors ({len(motion_found)}):")
                for d in sorted(motion_found, key=lambda x: x["name"]):
                    mot_states = self._disc_motion_states(d["states"])
                    self.logger.info(f"[{ts}]   {d['name']}  (ID: {d['id']}, Folder: {d['folder']})")
                    dev_obj = indigo.devices[d["id"]]
                    for state_name in mot_states:
                        entry = self._disc_motion_entry(dev_obj, state_name, commented=False)
                        self.logger.info(f"[{ts}]   {entry}")

        self.logger.info(f"[{ts}] === End of Discovery ===")

    def menuReloadConfig(self):
        """Reload sensor_monitor_config.json without a full plugin restart.

        Equivalent to a plugin reload for config changes, but preserves
        the existing device/variable subscriptions.
        """
        old_dev_count = len(self.device_monitor)
        old_var_count = len(self.variable_monitor)

        self._load_config()
        self._validate_monitored_devices()
        self._validate_monitored_variables()

        ts = datetime.now().strftime('%H:%M:%S')
        self.logger.info(
            f"[{ts}] [Sensor Monitor] Config reloaded - "
            f"{old_dev_count} -> {len(self.device_monitor)} devices, "
            f"{old_var_count} -> {len(self.variable_monitor)} variables"
        )

    # ======================================
    # DISCOVERY HELPERS
    # (shared by menu callbacks and standalone scripts)
    # ======================================

    def _disc_is_excluded_plugin(self, dev):
        """Return True if the device belongs to a plugin that should be excluded.

        Virtual devices and Alexa mirror devices are excluded so they never
        appear in sensor_monitor_config.json.  The Alexa plugin creates a named
        mirror for every exposed Indigo device, so a switch called
        'HA Garage Door' would appear as a contact candidate without this check.
        The exclusion list is _EXCLUDED_PLUGIN_IDS at module level — add IDs
        there as needed.
        """
        return getattr(dev, "pluginId", "") in _EXCLUDED_PLUGIN_IDS

    def _disc_is_name_excluded(self, dev):
        """Return True if dev's name contains an exclusion keyword.

        Used as a scan-level filter to hide non-sensor devices (temperature
        monitors, power meters, smart plugs, etc.) from the config entirely —
        even from the commented-out 'Other devices' section.

        Only applied when the device is NOT already classified as a contact or
        motion sensor via state-name matching.  A device whose name contains
        'temperature' but whose states include 'contact' is still picked up
        correctly as a contact sensor.
        """
        name_lower = dev.name.lower()
        return any(kw in name_lower for kw in _NAME_EXCLUSION_KEYWORDS)

    def _disc_folder_name(self, dev):
        """Return dev's Indigo folder name, or '(root)' if in root or on error."""
        try:
            if dev.folderId and dev.folderId in indigo.devices.folders:
                return indigo.devices.folders[dev.folderId].name
        except Exception:
            pass
        return "(root)"

    def _disc_states(self, dev):
        """Return a dict of state name -> current value for dev."""
        try:
            return {k: dev.states[k] for k in dev.states}
        except Exception:
            return {}

    def _disc_is_contact(self, dev, states):
        """Return True if dev looks like a contact/door/window sensor.

        A device is a contact candidate only if it can be monitored as a
        binary sensor.  Specifically:
          - Has a known contact state name (contact, doorSensor, windowSensor)
            regardless of device type, OR
          - Has an onState attribute AND its name contains a contact keyword
            AND does NOT contain a motion keyword
            AND does NOT contain a name exclusion keyword.

        Devices without onState (e.g. ThermostatDevice, plain button Device)
        are excluded from name-keyword matching.

        Name exclusion keywords (_NAME_EXCLUSION_KEYWORDS) prevent temperature
        sensors, power monitors, smart plugs, etc. from being picked up via
        name matching.  Example: 'Front Door Temperature' has 'door' in its
        name but 'temperature' disqualifies it.

        State-name matching (contact / doorSensor / windowSensor) always wins
        regardless of what else appears in the device name.
        """
        state_match = bool(_CONTACT_STATE_NAMES & set(states.keys()))
        if state_match:
            return True
        if not hasattr(dev, "onState"):
            return False
        name_lower = dev.name.lower()
        if any(kw in name_lower for kw in _NAME_EXCLUSION_KEYWORDS):
            return False  # Non-sensor keyword in name - skip name-based matching
        has_contact_kw = any(kw in name_lower for kw in _CONTACT_NAME_KEYWORDS)
        has_motion_kw  = any(kw in name_lower for kw in _MOTION_NAME_KEYWORDS)
        return has_contact_kw and not has_motion_kw

    def _disc_is_motion(self, dev, states):
        """Return True if dev looks like a motion/occupancy/presence sensor.

        A device is a motion candidate only if it can be monitored as a
        binary sensor.  Specifically:
          - Has a known motion state name (occupancy, pirDetection, presence,
            motion, motionDetected) regardless of device type, OR
          - Has an onState attribute AND its name contains a motion keyword
            AND does NOT contain a name exclusion keyword.

        Devices without onState are excluded from name-keyword matching.
        Name exclusion keywords (_NAME_EXCLUSION_KEYWORDS) prevent power
        monitors, smart plugs, etc. from matching motion keywords.
        State-name matching always wins over name exclusion keywords.
        Contact sensors (already caught by _disc_is_contact) are excluded
        by the caller using elif, so no need to re-check here.
        """
        state_match = bool(_MOTION_STATE_NAMES & set(states.keys()))
        if state_match:
            return True
        if not hasattr(dev, "onState"):
            return False
        name_lower = dev.name.lower()
        if any(kw in name_lower for kw in _NAME_EXCLUSION_KEYWORDS):
            return False  # Non-sensor keyword in name - skip name-based matching
        return any(kw in name_lower for kw in _MOTION_NAME_KEYWORDS)

    def _disc_motion_states(self, states):
        """Return sorted list of motion state names present in states dict.

        Falls back to ["onState"] when no specific motion state names are
        found (e.g. a sensor whose name matched a motion keyword but whose
        states are not yet populated or use a generic binary state).
        """
        found = sorted(s for s in _MOTION_STATE_NAMES if s in states)
        return found if found else ["onState"]

    def _format_entry_line(self, dev, state, on_text, off_text, commented=False):
        """Return a formatted JSON object string for sensor_monitor_config.json.

        commented=True  prepends '# ' so the entry is disabled by default.
        """
        line = (
            f'    {{"id": {dev.id}, "name": "{dev.name}", '
            f'"state": "{state}", "label": "{dev.name}", '
            f'"on_text": "{on_text}", "off_text": "{off_text}"}}'
        )
        return f"# {line}" if commented else line

    def _disc_config_entry(self, dev, states, commented=False):
        """Return a JSON config file line for a CONTACT sensor device.

        Uses 'contact' state if present (zigbee2mqtt: CLOSED=True / OPEN=False).
        Falls back to 'onState' with OPEN=True / CLOSED=False convention.
        commented=True  prepends '# ' so the entry is disabled by default.
        """
        if "contact" in states:
            state, on_text, off_text = "contact", "CLOSED", "OPEN"
        else:
            state, on_text, off_text = "onState", "OPEN", "CLOSED"
        return self._format_entry_line(dev, state, on_text, off_text, commented)

    def _disc_motion_entry(self, dev, state_name, commented=False):
        """Return a JSON config file line for a MOTION sensor device and state.

        Uses ON / OFF as the text values (motion detected / clear).
        commented=True  prepends '# ' so the entry is disabled by default.
        """
        return self._format_entry_line(dev, state_name, "ON", "OFF", commented)

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
