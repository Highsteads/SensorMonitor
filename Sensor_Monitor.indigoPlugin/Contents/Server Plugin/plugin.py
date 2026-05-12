#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Sensor Monitor - subscribes to device and variable changes and logs events
# Author:      CliveS & Claude Sonnet 4.6
# Date:        12-05-2026
# Version:     1.8.0
#
# v1.8.0 (12-05-2026):
# - Groups are now first-class Indigo devices (type "Sensor Monitor Group",
#   id smGroup). Create via Indigo Devices > New Device. Each group gets a
#   rich two-list ConfigUI (folder-filtered Available list, Members list,
#   Add / Remove buttons) replacing the JSON file editing of v1.7.x.
# - Trigger ConfigUI now picks a Group by Indigo's native device picker
#   instead of a string menu — folder tree, search, the lot.
# - One-time auto-migration on first startup: each entry from the legacy
#   JSON groups[] array is created as an smGroup device inside a new
#   "Sensor Monitor Groups" Indigo folder. Existing JSON groups[] entries
#   stay in the config file as a fallback so pre-v1.8.0 triggers keep
#   firing while the user migrates them; the JSON file can be emptied of
#   groups[] manually afterwards.
# - Backward compat: triggers with the legacy "groupName" prop (no
#   groupDevice) resolve by name against device-created groups first, then
#   the JSON fallback. Existing v1.7.x triggers fire without re-editing.
# - smGroup devices expose memberCount, lastFiringDevice, lastFiringTime,
#   lastFiringDirection, and a status display state — useful for control
#   pages and diagnostics.
#
# v1.7.2 (12-05-2026):
# - Group-Changed trigger gains a "Fire on" direction filter:
#     any         - fire on every state change (default; v1.7.0 behaviour)
#     activated   - fire only on onState False -> True
#                   (door OPEN, motion DETECTED, switch ON)
#     deactivated - fire only on onState True -> False
#                   (door CLOSED, motion CLEAR, switch OFF)
#   Works for groups of any size including a single device, so this also
#   gives a clean replacement for Indigo's built-in "Device State Changed"
#   trigger when you'd rather pick a group by name than re-pick the device
#   in every trigger.
# - deviceUpdated now fires the group-trigger check on onState transitions
#   too (not only on dev.states dict changes), so direction filters work
#   even on plugin devices whose onState lives outside the states dict.
#
# v1.7.1 (11-05-2026):
# - Moved sensor_monitor_config.json and device_discovery.json out of
#   Logs/SensorMonitor/ (wrong place — Logs is for logs) into the
#   Indigo-standard plugin Preferences folder:
#     <install>/Preferences/Plugins/com.clives.indigoplugin.sensormonitor/
#   One-time auto-migration moves existing files from the old location
#   on first startup, preserving all customisations.
#
# v1.7.0 (11-05-2026):
# - Added group-change custom triggers. Sensor Monitor now fires an
#   Indigo "Sensor Monitor: Group Changed" event whenever any device in
#   a named group has a state change. Groups are defined as a new
#   "groups" array in sensor_monitor_config.json — replaces Morris's
#   Group Change Listener with a config-file-driven workflow so adding
#   or removing devices is a text-file edit, not a fiddly multi-select.
# - Triggers optionally save the firing device to a variable
#   (name or ID), matching the Morris plugin's saveBool/saveVar feature.
# - Discovery preserves the existing "groups" section across re-runs,
#   same way it already preserves "excluded_ids".
#
# v1.6.0 (11-05-2026):
# - Discovery now uses Zigbee2MQTT-Bridge ownerProps (has_contact /
#   has_occupancy / has_presence / has_pir) as authoritative classification
#   when available. The generic z2mSensor device type emits a default
#   "contact": false field even on motion-only sensors, which made the
#   v1.5.9 state-key heuristic falsely classify motion-named z2mSensor
#   devices as contact sensors (e.g. "Living Room Door Motion Sensor",
#   "Moes Presence Sensor", "Right Presence Sensor").
# - deviceTypeId hints honoured: z2mContactSensor -> contact;
#   z2mOccupancySensor -> motion.
# - Motion-keyword in device name now vetoes contact classification even
#   when a stray "contact" state key is present.
# - _disc_motion_states picks a single preferred state per device (priority
#   occupancy > presence > motion > pirDetection > motionDetected) so
#   multi-state Z2M presence sensors emit one log line per change, not 3-4.

try:
    import indigo
except ImportError:
    pass

import json
import os
import platform
import re
import sys as _sys
from datetime import datetime

_sys.path.insert(0, os.getcwd())
try:
    from plugin_utils import log_startup_banner
except ImportError:
    log_startup_banner = None

# ======================================
# CONFIG FILE PATH
#
# Lives under the Indigo-standard plugin Preferences folder:
#   <install>/Preferences/Plugins/com.clives.indigoplugin.sensormonitor/
# v1.7.0 and earlier wrote into Logs/SensorMonitor/ — that was wrong (Logs
# is for log files, not user state). v1.7.1 migrates the files on first
# startup; see _migrate_config_to_prefs(). The legacy path constants are
# retained for the migration check.
#
# indigo.server.getInstallFolderPath() returns the Indigo base directory,
# e.g. "/Library/Application Support/Perceptive Automation/Indigo 2025.2".
# Using the API rather than a hardcoded string means the paths follow the
# Indigo version automatically — no code changes needed on upgrade.
#
# NOTE: Indigo's plugin runtime does NOT set __file__, so file-relative
# paths cannot be used at module level. The API call is the correct approach.
#
# The except block is the fallback for the test environment where indigo is
# a MagicMock and os.path.join(MagicMock(), ...) raises TypeError. Tests
# override CONFIG_PATH / DISCOVERY_OUTPUT_PATH with safe temp paths anyway.
#
# If this config file exists the plugin loads its device, variable, and
# group lists from it instead of from the hardcoded fallback dicts below.
# The file supports # comment lines to disable individual entries.
#
# Reload after saving changes:
#   Plugins > Sensor Monitor > Reload Config File
# ======================================

_PLUGIN_BUNDLE_ID = "com.clives.indigoplugin.sensormonitor"

try:
    _INDIGO_BASE = indigo.server.getInstallFolderPath()
    _PREFS_DIR   = os.path.join(_INDIGO_BASE, "Preferences", "Plugins", _PLUGIN_BUNDLE_ID)
    _LEGACY_DIR  = os.path.join(_INDIGO_BASE, "Logs", "SensorMonitor")
except Exception:
    # Fallback used in test environment (indigo is a MagicMock)
    _BASE = "/Library/Application Support/Perceptive Automation/Indigo 2025.2"
    _PREFS_DIR  = os.path.join(_BASE, "Preferences", "Plugins", _PLUGIN_BUNDLE_ID)
    _LEGACY_DIR = os.path.join(_BASE, "Logs", "SensorMonitor")

CONFIG_PATH                  = os.path.join(_PREFS_DIR,  "sensor_monitor_config.json")
DISCOVERY_OUTPUT_PATH        = os.path.join(_PREFS_DIR,  "device_discovery.json")
LEGACY_CONFIG_PATH           = os.path.join(_LEGACY_DIR, "sensor_monitor_config.json")
LEGACY_DISCOVERY_OUTPUT_PATH = os.path.join(_LEGACY_DIR, "device_discovery.json")

# ======================================
# DISCOVERY CONSTANTS
#
# Used by the menu-driven discovery methods.
# ======================================

_CONTACT_STATE_NAMES   = {"contact", "doorSensor", "windowSensor"}
_CONTACT_NAME_KEYWORDS = ["contact", "door", "window", "entry", "gate", "patio", "garage"]

_MOTION_STATE_NAMES    = {"occupancy", "pirDetection", "presence", "motion", "motionDetected"}
_MOTION_NAME_KEYWORDS  = ["motion", "pir", "presence", "occupancy", "mmwave", "radar"]

# Preferred motion-state order — pick the single best one when multiple exist.
# Multi-state Z2M presence sensors typically report ALL of: motion, occupancy,
# presence, pirDetection. Without this, a single PIR trip emits 3-4 identical
# log lines because we configure a monitor entry per matching state.
_MOTION_STATE_PRIORITY = ("occupancy", "presence", "motion",
                         "pirDetection", "motionDetected")

# Zigbee2MQTT-Bridge plugin ID — owner-props on these devices include
# authoritative has_contact / has_occupancy / has_presence / has_pir flags.
_Z2M_BRIDGE_PLUGIN_ID  = "com.clives.indigoplugin.z2mbridge"
_Z2M_CONTACT_TYPE_IDS   = {"z2mContactSensor"}
_Z2M_OCCUPANCY_TYPE_IDS = {"z2mOccupancySensor"}

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

        # Group-change machinery. Two source-of-truth dicts feed one
        # consolidated index that the hot path inside deviceUpdated reads:
        #
        #   json_groups       legacy v1.7.x JSON groups[] entries
        #                     (kept for backward compat; preferred source
        #                      is now smGroup devices)
        #   device_groups     smGroup devices (v1.8.0+); populated by
        #                     deviceStartComm
        #
        # _rebuild_group_index() recomputes group_members + group_name_to_dev_id
        # from those two whenever either changes.
        self.json_groups          = {}    # {group_name: set(device_ids)}
        self.device_groups        = {}    # {smGroup_dev_id: {"name", "members"}}
        self.group_members        = set() # union — fast O(1) test in deviceUpdated
        self.group_name_to_dev_id = {}    # {group_name: smGroup_dev_id}
        self.event_triggers       = {}    # {trigger.id: indigo.trigger}

        # Migration must run before _load_config so the loader sees the file
        # at its new location. self.logger isn't fully ready inside __init__,
        # so migration logs are best-effort here — _load_config will log a
        # second time at INFO once the logger is ready.
        self._migrate_config_to_prefs()
        self._load_config()

        if log_startup_banner:
            log_startup_banner(pluginId, pluginDisplayName, pluginVersion)
        else:
            indigo.server.log(f"{pluginDisplayName} v{pluginVersion} starting")

    def startup(self):
        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()
        # One-time migration: any JSON groups[] entries that don't already
        # exist as smGroup devices get created. Idempotent across startups.
        try:
            self._migrate_json_groups_to_devices()
        except Exception as exc:
            self.logger.error(f"[Sensor Monitor] Migration error: {exc}")
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

        # Loop-guard: ignore changes the plugin itself caused.
        if newDev.pluginId == self.pluginId:
            return

        # --- Group-change triggers (v1.7.0, direction filter v1.7.2) ---
        # Independent of the per-state logging path below: a device may be in
        # a group without being in device_monitor, and vice-versa. Group
        # triggers fire on ANY state change OR onState transition; the
        # per-trigger "fireOn" filter (any / activated / deactivated) decides
        # which transitions actually fire.
        if newDev.id in self.group_members:
            try:
                states_changed = (newDev.states != origDev.states)
                onstate_flip   = (
                    getattr(newDev, "onState", None)
                    != getattr(origDev, "onState", None)
                )
                if states_changed or onstate_flip:
                    self._fire_group_triggers(origDev, newDev)
            except Exception as exc:
                self.logger.error(f"[Sensor Monitor] group-trigger error: {exc}")

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
    # GROUP-CHANGE TRIGGER LIFECYCLE (v1.7.0)
    # ======================================

    def triggerStartProcessing(self, trigger):
        """Indigo calls this when an enabled trigger of one of our event
        types is loaded — we store the trigger so deviceUpdated() can fire it.
        Confirmed pattern per global CLAUDE.md (ZwaveLockManager-style;
        indigo.server.fireEvent() does NOT exist on PluginBase)."""
        self.event_triggers[trigger.id] = trigger
        members = self._resolve_trigger_group(trigger)
        if not members:
            label = (
                trigger.pluginProps.get("groupDevice")
                or trigger.pluginProps.get("groupName")
                or "(unset)"
            )
            self.logger.warning(
                f"[Sensor Monitor] Trigger '{trigger.name}' references "
                f"unknown or empty group ({label}) — open the trigger and "
                f"pick a Group, or check the smGroup device exists."
            )

    def triggerStopProcessing(self, trigger):
        self.event_triggers.pop(trigger.id, None)

    def getGroupDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):
        """ConfigUI callback — list of smGroup devices for the trigger picker."""
        result = []
        for dev in indigo.devices.iter("self.smGroup"):
            count = len(self.device_groups.get(dev.id, {}).get("members", set()))
            result.append((str(dev.id), f"{dev.name}  ({count} member{'s' if count != 1 else ''})"))
        result.sort(key=lambda x: x[1].lower())
        return result if result else [("none", "-- No Sensor Monitor Group devices yet --")]

    def _resolve_trigger_group(self, trigger):
        """Return the set of device IDs this trigger's group covers.

        Resolution order:
          1. groupDevice prop -> look up the smGroup device's members
          2. groupName prop (legacy) -> match device-defined group by name
          3. groupName prop -> match JSON-defined group by name (fallback)
        """
        dev_id_str = str(trigger.pluginProps.get("groupDevice", "") or "").strip()
        if dev_id_str and dev_id_str != "none":
            try:
                dev_id = int(dev_id_str)
            except ValueError:
                dev_id = 0
            if dev_id and dev_id in self.device_groups:
                return self.device_groups[dev_id]["members"]
        # Legacy fallback
        name = str(trigger.pluginProps.get("groupName", "") or "").strip()
        if name:
            dev_id = self.group_name_to_dev_id.get(name)
            if dev_id is not None:
                return self.device_groups[dev_id]["members"]
            return self.json_groups.get(name, set())
        return set()

    def _fire_group_triggers(self, origDev, newDev):
        """Fire any sensorGroupChange triggers whose group contains newDev.id,
        subject to the per-trigger fireOn direction filter:

          "any"          fire on any state or onState change (default)
          "activated"    fire only on an onState False -> True transition
                         (door OPEN, motion DETECTED, switch ON)
          "deactivated"  fire only on an onState True -> False transition
                         (door CLOSED, motion CLEAR, switch OFF)
        """
        on_new  = bool(getattr(newDev,  "onState", False))
        on_old  = bool(getattr(origDev, "onState", False))
        flipped = on_new != on_old

        for trigger in self.event_triggers.values():
            if trigger.pluginTypeId != "sensorGroupChange":
                continue
            members = self._resolve_trigger_group(trigger)
            if newDev.id not in members:
                continue

            fire_on = trigger.pluginProps.get("fireOn", "any")
            if fire_on == "activated":
                if not (flipped and on_new):
                    continue
                direction = "activated"
            elif fire_on == "deactivated":
                if not (flipped and not on_new):
                    continue
                direction = "deactivated"
            else:
                direction = (
                    "activated"   if (flipped and on_new) else
                    "deactivated" if (flipped and not on_new) else
                    "changed"
                )

            # Optional: save the firing device to a variable before firing,
            # so the trigger's actions can read it via %%v:NN%% substitution.
            if trigger.pluginProps.get("saveBool", False):
                self._save_firing_device(trigger, newDev)

            # Update the smGroup device's diagnostic states (last firing
            # device / time / direction) so control pages can show activity.
            self._update_smgroup_diagnostics(trigger, newDev, direction)

            indigo.trigger.execute(trigger)
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            self.logger.debug(
                f"[{ts}] [Sensor Monitor] Fired group trigger "
                f"'{trigger.name}' (fireOn={fire_on}, direction={direction}) "
                f"for {newDev.name}"
            )

    def _update_smgroup_diagnostics(self, trigger, dev, direction):
        """Update lastFiringDevice/Time/Direction states on the smGroup
        device that owns this trigger, if any."""
        dev_id_str = str(trigger.pluginProps.get("groupDevice", "") or "").strip()
        if not dev_id_str or dev_id_str == "none":
            return
        try:
            grp_dev = indigo.devices[int(dev_id_str)]
        except (KeyError, ValueError):
            return
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            grp_dev.updateStatesOnServer([
                {"key": "lastFiringDevice",    "value": dev.name},
                {"key": "lastFiringTime",      "value": ts},
                {"key": "lastFiringDirection", "value": direction},
            ])
        except Exception:
            pass

    # ======================================
    # smGroup DEVICE LIFECYCLE (v1.8.0)
    # ======================================

    def deviceStartComm(self, dev):
        """Indigo calls this for each enabled smGroup device on startup,
        and whenever the device is re-enabled. Parse memberIds and
        register the group in self.device_groups."""
        if dev.deviceTypeId != "smGroup":
            return
        members = self._parse_member_ids(dev.pluginProps.get("memberIds", ""))
        self.device_groups[dev.id] = {"name": dev.name, "members": members}
        self._rebuild_group_index()
        self._refresh_smgroup_states(dev, members)

    def deviceStopComm(self, dev):
        if dev.deviceTypeId != "smGroup":
            return
        self.device_groups.pop(dev.id, None)
        self._rebuild_group_index()

    def deviceDeleted(self, dev):
        super().deviceDeleted(dev)
        if dev.deviceTypeId == "smGroup":
            self.device_groups.pop(dev.id, None)
            self._rebuild_group_index()

    def _refresh_smgroup_states(self, dev, members):
        """Set the smGroup device's display state lines."""
        try:
            count = len(members)
            dev.updateStatesOnServer([
                {"key": "memberCount", "value": count},
                {"key": "status",      "value": f"{count} member{'s' if count != 1 else ''}"},
            ])
        except Exception:
            pass

    # ======================================
    # smGroup ConfigUI CALLBACKS (v1.8.0)
    # ======================================

    @staticmethod
    def _parse_member_ids(s):
        """Parse the comma-separated memberIds pluginProp into a set of ints."""
        out = set()
        for tok in str(s or "").split(","):
            tok = tok.strip()
            if tok and tok.lstrip("-").isdigit():
                out.add(int(tok))
        return out

    @staticmethod
    def _serialise_member_ids(ids):
        return ",".join(str(int(x)) for x in sorted(ids))

    def _rebuild_group_index(self):
        """Recompute group_members (union) and group_name_to_dev_id lookup
        from json_groups + device_groups. Devices win over JSON when names
        collide."""
        all_members = set()
        name_to_dev = {}
        for dev_id, info in self.device_groups.items():
            all_members |= info.get("members", set())
            name_to_dev[info.get("name", "")] = dev_id
        for name, ids in self.json_groups.items():
            all_members |= ids
            # Don't shadow a device entry with the same name
        self.group_members        = all_members
        self.group_name_to_dev_id = name_to_dev

    def getFolderList(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Folder dropdown for the smGroup ConfigUI. Returns (id, label) tuples."""
        result = [("__all__", "(All folders)"), ("__root__", "(Root — no folder)")]
        try:
            for folder in sorted(indigo.devices.folders, key=lambda f: f.name.lower()):
                result.append((str(folder.id), folder.name))
        except Exception:
            pass
        return result

    def getAvailableDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Available list — every Indigo device except smGroup devices and
        any already in the Members list, optionally filtered to the folder
        chosen via folderFilter."""
        valuesDict = valuesDict or indigo.Dict()
        folder_sel = str(valuesDict.get("folderFilter", "__all__"))
        member_ids = self._parse_member_ids(valuesDict.get("memberIds", ""))

        result = []
        for dev in indigo.devices:
            if dev.id in member_ids:
                continue
            if getattr(dev, "deviceTypeId", "") == "smGroup":
                continue
            # Folder filter
            f_id = getattr(dev, "folderId", 0) or 0
            if folder_sel == "__all__":
                pass
            elif folder_sel == "__root__":
                if f_id:
                    continue
            else:
                try:
                    if int(folder_sel) != f_id:
                        continue
                except ValueError:
                    pass
            result.append((str(dev.id), dev.name))
        result.sort(key=lambda x: x[1].lower())
        return result if result else [("none", "-- No matching devices --")]

    def getMemberDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Members list — the current contents of memberIds, rendered with
        their device names. Stale IDs (deleted devices) show as '<missing>'
        so the user can see and clean them up."""
        valuesDict = valuesDict or indigo.Dict()
        ids = self._parse_member_ids(valuesDict.get("memberIds", ""))
        if not ids:
            return [("none", "-- No members yet --")]
        result = []
        for dev_id in sorted(ids):
            try:
                result.append((str(dev_id), indigo.devices[dev_id].name))
            except KeyError:
                result.append((str(dev_id), f"<missing device id {dev_id}>"))
        result.sort(key=lambda x: x[1].lower())
        return result

    def addToGroup(self, valuesDict, typeId, devId):
        """Button callback — append availableList selection to memberIds."""
        selected = valuesDict.get("availableList", []) or []
        current  = self._parse_member_ids(valuesDict.get("memberIds", ""))
        for s in selected:
            if str(s).lstrip("-").isdigit():
                current.add(int(s))
        valuesDict["memberIds"]     = self._serialise_member_ids(current)
        valuesDict["availableList"] = []
        return valuesDict

    def removeFromGroup(self, valuesDict, typeId, devId):
        """Button callback — remove memberList selection from memberIds."""
        selected = valuesDict.get("memberList", []) or []
        current  = self._parse_member_ids(valuesDict.get("memberIds", ""))
        for s in selected:
            if str(s).lstrip("-").isdigit():
                current.discard(int(s))
        valuesDict["memberIds"]  = self._serialise_member_ids(current)
        valuesDict["memberList"] = []
        return valuesDict

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errors = indigo.Dict()
        if typeId == "smGroup":
            # Members optional but warn if empty? Permissive — empty groups
            # are useful while the user is setting up.
            valuesDict["memberIds"] = self._serialise_member_ids(
                self._parse_member_ids(valuesDict.get("memberIds", ""))
            )
        if errors:
            return (False, valuesDict, errors)
        return (True, valuesDict)

    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        """Default folderFilter to (All folders) when creating a new group."""
        values = pluginProps
        errors = indigo.Dict()
        if not values.get("folderFilter"):
            values["folderFilter"] = "__all__"
        if not values.get("memberIds"):
            values["memberIds"] = ""
        return (values, errors)

    # ======================================
    # JSON-GROUPS -> smGroup DEVICE MIGRATION (v1.8.0)
    # ======================================

    def _migrate_json_groups_to_devices(self):
        """One-time migration: turn each JSON groups[] entry into an smGroup
        device. Idempotent — skips groups whose name already matches an
        existing smGroup device. Leaves the JSON file untouched so legacy
        triggers (with groupName but no groupDevice) keep firing while the
        user re-points them at the new device picker.
        """
        if not self.json_groups:
            return

        existing_names = {info.get("name", "") for info in self.device_groups.values()}
        # Also scan all indigo.devices for smGroup-typed devices that may not
        # have hit deviceStartComm yet (race-protective).
        try:
            for dev in indigo.devices.iter("self.smGroup"):
                existing_names.add(dev.name)
        except Exception:
            pass

        missing = [(n, ids) for n, ids in self.json_groups.items() if n not in existing_names]
        if not missing:
            return

        # Find or create a "Sensor Monitor Groups" device folder
        folder_id = 0
        target_folder_name = "Sensor Monitor Groups"
        try:
            for f in indigo.devices.folders:
                if f.name == target_folder_name:
                    folder_id = f.id
                    break
            if not folder_id:
                folder_id = indigo.devices.folder.create(target_folder_name).id
                self.logger.info(
                    f"[Sensor Monitor] Created device folder '{target_folder_name}'"
                )
        except Exception as exc:
            self.logger.warning(
                f"[Sensor Monitor] Could not create migration folder: {exc}"
            )

        for name, ids in missing:
            try:
                props = indigo.Dict()
                props["memberIds"]    = self._serialise_member_ids(ids)
                props["folderFilter"] = "__all__"
                dev = indigo.device.create(
                    protocol     = indigo.kProtocol.Plugin,
                    address      = "",
                    deviceTypeId = "smGroup",
                    name         = name,
                    description  = "Migrated from sensor_monitor_config.json",
                    props        = props,
                    folder       = folder_id,
                )
                self.logger.info(
                    f"[Sensor Monitor] Migrated JSON group '{name}' "
                    f"({len(ids)} device{'s' if len(ids) != 1 else ''}) "
                    f"-> smGroup device id={dev.id}"
                )
            except Exception as exc:
                self.logger.warning(
                    f"[Sensor Monitor] Could not migrate group '{name}': {exc}"
                )

    def _save_firing_device(self, trigger, dev):
        """Write the firing device's name or id to the configured variable."""
        try:
            var_id = int(trigger.pluginProps.get("saveVar", 0))
        except (TypeError, ValueError):
            return
        if not var_id or var_id not in indigo.variables:
            return
        save_type = trigger.pluginProps.get("saveType", "name")
        value = str(dev.id) if save_type == "id" else dev.name
        try:
            indigo.variable.updateValue(var_id, value)
        except Exception as exc:
            self.logger.error(
                f"[Sensor Monitor] Could not save firing device to "
                f"variable {var_id}: {exc}"
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

        # --- Read excluded_ids + groups from existing config (preserved across re-discovery) ---
        excluded_ids     = set()
        preserved_groups = []
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()
                active_lines = [l for l in existing_lines if not l.lstrip().startswith("#")]
                json_str     = re.sub(r",(\s*[}\]])", r"\1", "".join(active_lines))
                existing_cfg = json.loads(json_str)
                excluded_ids = set(int(x) for x in existing_cfg.get("excluded_ids", []))
                preserved_groups = existing_cfg.get("groups", []) or []
                if excluded_ids:
                    self.logger.info(
                        f"[{ts}] [Sensor Monitor] Preserving {len(excluded_ids)} "
                        f"excluded device(s) from existing config"
                    )
                if preserved_groups:
                    self.logger.info(
                        f"[{ts}] [Sensor Monitor] Preserving "
                        f"{len(preserved_groups)} group(s) from existing config"
                    )
            except Exception:
                excluded_ids     = set()
                preserved_groups = []

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
            lines.append('  ],')
            lines.append("")
            # --- groups: fire a custom "Sensor Monitor: Group Changed" trigger
            # whenever any device listed in a group has any state change.
            lines.append('  "groups": [')
            lines.append("")
            lines.append(
                '    # Each group fires the "Sensor Monitor: Group Changed" trigger when'
            )
            lines.append(
                '    # any of its devices changes state. Pick the group by name in the'
            )
            lines.append(
                '    # trigger\'s ConfigUI. Format:'
            )
            lines.append(
                '    #   {"name": "doors", "device_ids": [415253439, 1184619127]}'
            )
            lines.append("")
            if preserved_groups:
                for i, g in enumerate(preserved_groups):
                    name = str(g.get("name", "")).strip()
                    ids  = g.get("device_ids", []) or []
                    if not name:
                        continue
                    ids_str = ", ".join(str(int(x)) for x in ids)
                    comma   = "," if i < len(preserved_groups) - 1 else ""
                    lines.append(
                        f'    {{"name": "{name}", "device_ids": [{ids_str}]}}{comma}'
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

    def _disc_z2m_capabilities(self, dev):
        """Return dict of Zigbee2MQTT-Bridge has_* capability flags for dev.

        Returns {} when dev is not owned by the Z2M bridge plugin or the
        ownerProps cannot be read. The bridge publishes authoritative flags
        like has_contact, has_occupancy, has_presence, has_pir on every
        device it manages — far more reliable than inspecting raw state keys,
        because the generic z2mSensor device type emits stub fields for
        every capability whether the physical device has them or not.
        """
        if getattr(dev, "pluginId", "") != _Z2M_BRIDGE_PLUGIN_ID:
            return {}
        try:
            props = dict(dev.ownerProps or {})
        except Exception:
            return {}
        return {k: v for k, v in props.items() if k.startswith("has_")}

    def _disc_is_contact(self, dev, states):
        """Return True if dev looks like a contact/door/window sensor.

        Decision order (first match wins):
          1. Z2M bridge has_contact flag — authoritative if device is Z2M-owned.
          2. deviceTypeId hint — z2mContactSensor wins; z2mOccupancySensor
             rules out contact.
          3. Motion keyword in device name (motion/pir/presence/occupancy/
             mmwave/radar) vetoes contact even if a stray "contact" state
             field exists.
          4. Known contact state name in dev.states (contact / doorSensor /
             windowSensor).
          5. Contact keyword in name AND no motion keyword AND no exclusion
             keyword AND dev has onState.

        Name exclusion keywords (_NAME_EXCLUSION_KEYWORDS) prevent temperature
        sensors, power monitors, smart plugs, etc. from being picked up via
        name matching.
        """
        z2m_caps = self._disc_z2m_capabilities(dev)
        # 1. Z2M bridge authoritative
        if z2m_caps.get("has_contact") is True:
            return True
        if z2m_caps.get("has_contact") is False:
            return False
        # Any explicit motion capability on Z2M means it's a motion device, not contact
        if any(z2m_caps.get(k) is True for k in ("has_occupancy", "has_presence", "has_pir")):
            return False

        # 2. deviceTypeId hint
        type_id = getattr(dev, "deviceTypeId", "")
        if type_id in _Z2M_CONTACT_TYPE_IDS:
            return True
        if type_id in _Z2M_OCCUPANCY_TYPE_IDS:
            return False

        # 3. Motion keyword veto — beats state-key match
        name_lower = dev.name.lower()
        if any(kw in name_lower for kw in _MOTION_NAME_KEYWORDS):
            return False

        # 4. State-name match
        if _CONTACT_STATE_NAMES & set(states.keys()):
            return True

        # 5. Name-keyword match
        if not hasattr(dev, "onState"):
            return False
        if any(kw in name_lower for kw in _NAME_EXCLUSION_KEYWORDS):
            return False
        return any(kw in name_lower for kw in _CONTACT_NAME_KEYWORDS)

    def _disc_is_motion(self, dev, states):
        """Return True if dev looks like a motion/occupancy/presence sensor.

        Decision order (first match wins):
          1. Z2M bridge has_occupancy / has_presence / has_pir — authoritative.
          2. deviceTypeId hint — z2mOccupancySensor wins.
          3. Known motion state name in dev.states.
          4. Motion keyword in name AND no exclusion keyword AND dev has onState.

        Contact sensors (already caught by _disc_is_contact) are excluded by
        the caller using elif.
        """
        z2m_caps = self._disc_z2m_capabilities(dev)
        if any(z2m_caps.get(k) is True for k in ("has_occupancy", "has_presence", "has_pir")):
            return True
        # If Z2M explicitly says none of those capabilities are present,
        # fall through to other heuristics (some devices report presenceEvent
        # without the has_presence flag — Aqara RTCZCGQ11LM is one example).

        if getattr(dev, "deviceTypeId", "") in _Z2M_OCCUPANCY_TYPE_IDS:
            return True

        if _MOTION_STATE_NAMES & set(states.keys()):
            return True

        if not hasattr(dev, "onState"):
            return False
        name_lower = dev.name.lower()
        if any(kw in name_lower for kw in _NAME_EXCLUSION_KEYWORDS):
            return False
        return any(kw in name_lower for kw in _MOTION_NAME_KEYWORDS)

    def _disc_motion_states(self, states):
        """Return the single preferred motion state name as a one-element list.

        Multi-state Z2M presence sensors typically expose every variant
        (motion, occupancy, presence, pirDetection) — emitting a config entry
        per state means 3-4 identical log lines on each trip. Walk the
        priority list (occupancy first, motion last) and pick the first
        match; only fall back to ["onState"] if no motion-state name is
        present at all.
        """
        for preferred in _MOTION_STATE_PRIORITY:
            if preferred in states:
                return [preferred]
        return ["onState"]

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

    def _migrate_config_to_prefs(self):
        """One-time migration from the v1.7.0 location (Logs/SensorMonitor/)
        to the proper Indigo Preferences/Plugins/<bundle>/ folder.

        Runs every startup but is a no-op once the new files exist. Uses
        os.rename so the file's mtime is preserved.
        """
        try:
            os.makedirs(_PREFS_DIR, exist_ok=True)
        except Exception as exc:
            # logger may not be ready inside __init__ — best-effort
            try:
                self.logger.warning(
                    f"[Sensor Monitor] Could not create prefs dir "
                    f"{_PREFS_DIR}: {exc}"
                )
            except Exception:
                pass
            return

        moves = [
            (LEGACY_CONFIG_PATH,           CONFIG_PATH,           "sensor_monitor_config.json"),
            (LEGACY_DISCOVERY_OUTPUT_PATH, DISCOVERY_OUTPUT_PATH, "device_discovery.json"),
        ]
        moved_any = False
        for src, dst, label in moves:
            if not os.path.exists(src):
                continue
            if os.path.exists(dst):
                # Don't clobber a newer file at the new location
                continue
            try:
                os.rename(src, dst)
                moved_any = True
                try:
                    self.logger.info(
                        f"[Sensor Monitor] Migrated {label}: "
                        f"{src} -> {dst}"
                    )
                except Exception:
                    pass
            except Exception as exc:
                try:
                    self.logger.warning(
                        f"[Sensor Monitor] Could not migrate {label}: {exc}"
                    )
                except Exception:
                    pass

        # Clean up the now-empty legacy directory (silent if not empty or missing)
        if moved_any:
            try:
                os.rmdir(_LEGACY_DIR)
            except OSError:
                pass  # not empty, or already gone — fine

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

        # --- Build self.json_groups from "groups" list ---
        # v1.7.x put group definitions in JSON; v1.8.0 prefers smGroup
        # devices but keeps this loader for backward compatibility. Devices
        # with the same name take precedence in the resolution path.
        self.json_groups = {}
        for entry in config.get("groups", []):
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            try:
                ids = set(int(x) for x in entry.get("device_ids", []))
            except (TypeError, ValueError):
                ids = set()
            self.json_groups[name] = ids

        self._rebuild_group_index()

        try:
            self.logger.info(
                f"[Sensor Monitor] Config loaded from: {path} "
                f"({len(self.device_monitor)} devices, "
                f"{len(self.variable_monitor)} variables, "
                f"{len(self.json_groups)} legacy JSON group(s))"
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

    # ======================================
    # Menu handlers
    # ======================================

    def showPluginInfo(self, valuesDict=None, typeId=None):
        if log_startup_banner:
            log_startup_banner(self.pluginId, self.pluginDisplayName, self.pluginVersion)
        else:
            indigo.server.log(f"{self.pluginDisplayName} v{self.pluginVersion}")
