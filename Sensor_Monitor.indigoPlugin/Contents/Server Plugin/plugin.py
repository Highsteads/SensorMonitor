#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Sensor Monitor - subscribes to device and variable changes and logs events
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.2

try:
    import indigo
except ImportError:
    pass

from datetime import datetime

# ======================================
# DEVICE MONITOR CONFIGURATION
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
}

# ======================================
# VARIABLE MONITOR CONFIGURATION
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

    241032502: {"label": "Lux Level"},
}


class Plugin(indigo.PluginBase):

    # ======================================
    # LIFECYCLE
    # ======================================

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super().__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = pluginPrefs.get("showDebugInfo", False)

    def startup(self):
        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()
        self.logger.info(
            f"Sensor Monitor {self.pluginVersion} started - "
            f"monitoring {len(DEVICE_MONITOR)} devices, {len(VARIABLE_MONITOR)} variables"
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

        if newDev.id not in DEVICE_MONITOR:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        # --- Name change detection ---
        if origDev.name != newDev.name:
            indigo.server.log(
                f"[{timestamp}] [Sensor Monitor] Device renamed: "
                f"'{origDev.name}' -> '{newDev.name}' (ID: {newDev.id})"
            )

        # --- State change logging ---
        for config in DEVICE_MONITOR[newDev.id]:
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

        if dev.id not in DEVICE_MONITOR:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.logger.warning(
            f"[{timestamp}] [Sensor Monitor] WARNING - Monitored device deleted: "
            f"'{dev.name}' (ID: {dev.id}) - remove from DEVICE_MONITOR in plugin.py"
        )

    # ======================================
    # VARIABLE CHANGE CALLBACK
    # ======================================

    def variableUpdated(self, origVar, newVar):
        super().variableUpdated(origVar, newVar)

        if newVar.id not in VARIABLE_MONITOR:
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

        config = VARIABLE_MONITOR[newVar.id]
        label  = config.get("label", newVar.name)

        indigo.server.log(
            f"[{timestamp}] {label}: {origVar.value} -> {newVar.value}"
        )

    # ======================================
    # VARIABLE DELETED CALLBACK
    # ======================================

    def variableDeleted(self, var):
        super().variableDeleted(var)

        if var.id not in VARIABLE_MONITOR:
            return

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.logger.warning(
            f"[{timestamp}] [Sensor Monitor] WARNING - Monitored variable deleted: "
            f"'{var.name}' (ID: {var.id}) - remove from VARIABLE_MONITOR in plugin.py"
        )

    # ======================================
    # PRIVATE HELPERS
    # ======================================

    def _validate_monitored_devices(self):
        """Check all DEVICE_MONITOR entries exist in Indigo at startup."""
        missing = []
        found   = []

        for device_id in DEVICE_MONITOR:
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
                f"check IDs in DEVICE_MONITOR in plugin.py"
            )
        else:
            self.logger.info("[Sensor Monitor] All monitored devices validated OK")

    def _validate_monitored_variables(self):
        """Check all VARIABLE_MONITOR entries exist in Indigo at startup."""
        if not VARIABLE_MONITOR:
            return

        missing = []
        found   = []

        for var_id in VARIABLE_MONITOR:
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
                f"check IDs in VARIABLE_MONITOR in plugin.py"
            )
        else:
            self.logger.info("[Sensor Monitor] All monitored variables validated OK")
