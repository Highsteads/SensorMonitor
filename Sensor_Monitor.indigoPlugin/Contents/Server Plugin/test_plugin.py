#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_plugin.py
# Description: Mock test harness for Sensor Monitor plugin - no Indigo runtime needed
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.2
#
# Run from Terminal:
#   cd "/Library/Application Support/Perceptive Automation/Indigo 2025.1/Plugins"
#   cd "Sensor_Monitor.indigoPlugin/Contents/Server Plugin"
#   python3 test_plugin.py -v

import sys
import os
import tempfile
import unittest
import importlib.util
from unittest.mock import MagicMock

# ======================================
# MOCK INDIGO MODULE
# Must be injected into sys.modules BEFORE plugin.py is imported
# ======================================

class MockDevice:
    """Simulates an Indigo device object."""
    def __init__(self, dev_id, name, on_state=False, states=None):
        self.id      = dev_id
        self.name    = name
        self.onState = on_state
        self.states  = states or {}

    def __repr__(self):
        return f"MockDevice(id={self.id}, name='{self.name}', onState={self.onState})"


class MockDevices(dict):
    """Dict-like mock for indigo.devices - adds subscribeToChanges()."""
    def subscribeToChanges(self):
        pass  # No-op in tests


class MockVariable:
    """Simulates an Indigo variable object."""
    def __init__(self, var_id, name, value=""):
        self.id    = var_id
        self.name  = name
        self.value = value

    def __repr__(self):
        return f"MockVariable(id={self.id}, name='{self.name}', value='{self.value}')"


class MockVariables(dict):
    """Dict-like mock for indigo.variables - adds subscribeToChanges()."""
    def subscribeToChanges(self):
        pass  # No-op in tests


class MockPluginBase:
    """Minimal stand-in for indigo.PluginBase."""
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        self.pluginId          = pluginId
        self.pluginDisplayName = pluginDisplayName
        self.pluginVersion     = pluginVersion
        self.pluginPrefs       = pluginPrefs
        self.logger            = MagicMock()

    def deviceUpdated(self, origDev, newDev):
        pass  # super() in plugin lands here

    def deviceDeleted(self, dev):
        pass  # super() in plugin lands here

    def variableUpdated(self, origVar, newVar):
        pass  # super() in plugin lands here

    def variableDeleted(self, var):
        pass  # super() in plugin lands here


# Build and inject the mock indigo module
mock_indigo            = MagicMock()
mock_indigo.PluginBase = MockPluginBase
mock_indigo.devices    = MockDevices()
mock_indigo.variables  = MockVariables()
mock_indigo.server     = MagicMock()
sys.modules['indigo']  = mock_indigo


# ======================================
# LOAD plugin.py FROM SAME DIRECTORY
# ======================================

_plugin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")
_spec        = importlib.util.spec_from_file_location("sensor_monitor_plugin", _plugin_path)
_mod         = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Plugin           = _mod.Plugin
DEVICE_MONITOR   = _mod.DEVICE_MONITOR
VARIABLE_MONITOR = _mod.VARIABLE_MONITOR
CONFIG_PATH      = _mod.CONFIG_PATH


# ======================================
# SHARED HELPERS
# ======================================

# Human-readable names for the 10 monitored device IDs
_DEVICE_NAMES = {
    812537401:  "Basin Occupancy Sensor",
    1976004986: "Basin mmWave Sensor",
    1184619127: "Door Occupancy Sensor",
    415253439:  "Bathroom Door Contact",
    1649680462: "Kitchen Left mmWave",
    1440351705: "Kitchen FP2",
    467551931:  "Utility Room Occupancy",
    408117572:  "Living Room FP2 Zone 1",
    1256890181: "Living Room FP2 Zone 2",
    1807623843: "Living Room Moes",
}


_VARIABLE_NAMES = {
    241032502: "Lux_Level",
}


def make_device_registry(missing_ids=None):
    """Return a MockDevices dict populated with all DEVICE_MONITOR entries."""
    missing_ids = set(missing_ids or [])
    registry    = MockDevices()
    for dev_id in DEVICE_MONITOR:
        if dev_id not in missing_ids:
            registry[dev_id] = MockDevice(dev_id, _DEVICE_NAMES.get(dev_id, f"Device {dev_id}"))
    return registry


def make_variable_registry(missing_ids=None):
    """Return a MockVariables dict populated with all VARIABLE_MONITOR entries."""
    missing_ids = set(missing_ids or [])
    registry    = MockVariables()
    for var_id in VARIABLE_MONITOR:
        if var_id not in missing_ids:
            registry[var_id] = MockVariable(var_id, _VARIABLE_NAMES.get(var_id, f"Variable {var_id}"), "0")
    return registry


def make_plugin(prefs=None):
    """Instantiate the Plugin class with minimal prefs.

    No config file is present in the test environment, so _load_config()
    falls back to the module-level DEVICE_MONITOR / VARIABLE_MONITOR dicts.
    Call plugin._load_config(path) afterwards to test file-based loading.
    """
    return Plugin(
        "com.clives.indigoplugin.sensormonitor",
        "Sensor Monitor",
        "1.3.0",
        prefs or {}
    )


def server_log_messages():
    """Return list of strings passed to indigo.server.log() since last reset."""
    return [c.args[0] for c in mock_indigo.server.log.call_args_list]


# ======================================
# TEST: STARTUP VALIDATION
# ======================================

class TestStartupValidation(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices   = make_device_registry()
        mock_indigo.variables = make_variable_registry()

    def test_all_devices_found_logs_ok_for_each(self):
        """startup() logs [OK] for every monitored device when all exist."""
        plugin = make_plugin()
        plugin.startup()

        info_calls     = [str(c) for c in plugin.logger.info.call_args_list]
        device_id_strs = [str(dev_id) for dev_id in DEVICE_MONITOR]
        ok_count       = sum(
            1 for c in info_calls
            if "[OK]" in c and any(did in c for did in device_id_strs)
        )

        self.assertEqual(ok_count, len(DEVICE_MONITOR),
            msg=f"Expected {len(DEVICE_MONITOR)} device [OK] entries, got {ok_count}.\n"
                f"Info calls: {info_calls}")

    def test_all_devices_found_logs_final_ok(self):
        """startup() logs 'All monitored devices validated OK' when nothing missing."""
        plugin = make_plugin()
        plugin.startup()

        info_text = " ".join(str(c) for c in plugin.logger.info.call_args_list)
        self.assertIn("All monitored devices validated OK", info_text)

    def test_all_devices_found_no_warnings(self):
        """startup() produces no warnings when all devices are present."""
        plugin = make_plugin()
        plugin.startup()
        plugin.logger.warning.assert_not_called()

    def test_missing_devices_log_bang_per_missing(self):
        """startup() logs [!] for each missing device ID."""
        missing = [812537401, 1976004986]
        mock_indigo.devices = make_device_registry(missing_ids=missing)

        plugin = make_plugin()
        plugin.startup()

        warn_calls   = [str(c) for c in plugin.logger.warning.call_args_list]
        bang_count   = sum(1 for c in warn_calls if "[!]" in c)

        self.assertEqual(bang_count, len(missing),
            msg=f"Expected {len(missing)} [!] entries, got {bang_count}.\n"
                f"Warnings: {warn_calls}")

    def test_missing_devices_summary_warning(self):
        """startup() warns with a count of missing devices."""
        missing = [812537401, 1976004986]
        mock_indigo.devices = make_device_registry(missing_ids=missing)

        plugin = make_plugin()
        plugin.startup()

        warn_text = " ".join(str(c) for c in plugin.logger.warning.call_args_list)
        self.assertIn("2 monitored device(s) not found", warn_text)

    def test_subscribetochanges_called_on_startup(self):
        """startup() calls indigo.devices.subscribeToChanges()."""
        called = []
        mock_indigo.devices = make_device_registry()
        mock_indigo.devices.subscribeToChanges = lambda: called.append(True)

        plugin = make_plugin()
        plugin.startup()

        self.assertEqual(len(called), 1, "subscribeToChanges() should be called once")


# ======================================
# TEST: DEVICE UPDATED - onState
# ======================================

class TestDeviceUpdatedOnState(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_false_to_true_logs_on(self):
        """onState False -> True logs 'ON' for the device."""
        orig = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        new  = MockDevice(812537401, "Basin Occupancy Sensor", on_state=True)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(
            any("Basin Occupancy Sensor" in m and "Occupancy" in m and m.endswith("ON")
                for m in msgs),
            msg=f"Expected ON log. Got: {msgs}"
        )

    def test_true_to_false_logs_off(self):
        """onState True -> False logs 'OFF' for the device."""
        orig = MockDevice(812537401, "Basin Occupancy Sensor", on_state=True)
        new  = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(
            any("Basin Occupancy Sensor" in m and "Occupancy" in m and m.endswith("OFF")
                for m in msgs),
            msg=f"Expected OFF log. Got: {msgs}"
        )

    def test_no_change_no_log(self):
        """Unchanged onState (False -> False) produces no log output at all."""
        orig = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        new  = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        self.plugin.deviceUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()

    def test_unmonitored_device_produces_no_log(self):
        """Device ID not in device_monitor is silently ignored."""
        orig = MockDevice(999999999, "Some Unrelated Device", on_state=False)
        new  = MockDevice(999999999, "Some Unrelated Device", on_state=True)
        self.plugin.deviceUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()


# ======================================
# TEST: DEVICE UPDATED - custom states
# ======================================

class TestDeviceUpdatedCustomStates(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_only_changed_state_is_logged(self):
        """When pirDetection unchanged and presence changes, only presence is logged."""
        orig = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": False, "presence": False})
        new  = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": False, "presence": True})
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertFalse(any("PIR" in m for m in msgs),
            msg=f"PIR unchanged - should not log. Got: {msgs}")
        self.assertTrue(any("mmWave Presence" in m and "ON" in m for m in msgs),
            msg=f"presence changed - should log. Got: {msgs}")

    def test_both_states_logged_when_both_change(self):
        """Both PIR and presence logged when both change simultaneously."""
        orig = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": False, "presence": False})
        new  = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": True,  "presence": True})
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any("PIR" in m and m.endswith("ON") for m in msgs),
            msg=f"Expected PIR ON. Got: {msgs}")
        self.assertTrue(any("mmWave Presence" in m and m.endswith("ON") for m in msgs),
            msg=f"Expected mmWave Presence ON. Got: {msgs}")

    def test_custom_state_off_logs_off(self):
        """presence True -> False logs OFF."""
        orig = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": False, "presence": True})
        new  = MockDevice(1976004986, "Basin mmWave Sensor",
                          states={"pirDetection": False, "presence": False})
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any("mmWave Presence" in m and m.endswith("OFF") for m in msgs),
            msg=f"Expected mmWave Presence OFF. Got: {msgs}")


# ======================================
# TEST: DEVICE UPDATED - on_text / off_text
# ======================================

class TestDeviceUpdatedCustomText(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_contact_open_text(self):
        """Door contact onState True logs OPEN (not ON)."""
        orig = MockDevice(415253439, "Bathroom Door Contact", on_state=False)
        new  = MockDevice(415253439, "Bathroom Door Contact", on_state=True)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any(m.endswith("OPEN") for m in msgs),
            msg=f"Expected message ending with OPEN. Got: {msgs}")
        self.assertFalse(any(m.endswith("ON") for m in msgs),
            msg=f"Should not end with ON (should be OPEN). Got: {msgs}")

    def test_contact_close_text(self):
        """Door contact onState False logs CLOSED (not OFF)."""
        orig = MockDevice(415253439, "Bathroom Door Contact", on_state=True)
        new  = MockDevice(415253439, "Bathroom Door Contact", on_state=False)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any(m.endswith("CLOSED") for m in msgs),
            msg=f"Expected message ending with CLOSED. Got: {msgs}")
        self.assertFalse(any(m.endswith("OFF") for m in msgs),
            msg=f"Should not end with OFF (should be CLOSED). Got: {msgs}")


# ======================================
# TEST: DEVICE UPDATED - rename detection
# ======================================

class TestDeviceUpdatedRename(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_rename_on_monitored_device_logs_both_names(self):
        """Name change on a monitored device logs old and new names."""
        orig = MockDevice(812537401, "Old Basin Name", on_state=False)
        new  = MockDevice(812537401, "New Basin Name", on_state=False)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(
            any("Old Basin Name" in m and "New Basin Name" in m for m in msgs),
            msg=f"Expected rename message with both names. Got: {msgs}"
        )

    def test_no_rename_log_when_name_unchanged(self):
        """No rename log when device name is the same."""
        orig = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        new  = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        self.plugin.deviceUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()

    def test_rename_on_unmonitored_device_not_logged(self):
        """Rename of an unmonitored device is silently ignored."""
        orig = MockDevice(999999999, "Unrelated Old Name", on_state=False)
        new  = MockDevice(999999999, "Unrelated New Name", on_state=True)
        self.plugin.deviceUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()


# ======================================
# TEST: DEVICE DELETED
# ======================================

class TestDeviceDeleted(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_monitored_device_deleted_warns(self):
        """Deleting a monitored device triggers a warning containing the device name."""
        dev = MockDevice(812537401, "Basin Occupancy Sensor")
        self.plugin.deviceDeleted(dev)

        self.plugin.logger.warning.assert_called()
        warn_text = " ".join(str(c) for c in self.plugin.logger.warning.call_args_list)
        self.assertIn("Basin Occupancy Sensor", warn_text)

    def test_monitored_device_deleted_includes_id(self):
        """Warning for deleted device includes the device ID."""
        dev = MockDevice(812537401, "Basin Occupancy Sensor")
        self.plugin.deviceDeleted(dev)

        warn_text = " ".join(str(c) for c in self.plugin.logger.warning.call_args_list)
        self.assertIn("812537401", warn_text)

    def test_unmonitored_device_deleted_no_warning(self):
        """Deleting an unmonitored device produces no warning."""
        dev = MockDevice(999999999, "Irrelevant Device")
        self.plugin.deviceDeleted(dev)

        self.plugin.logger.warning.assert_not_called()


# ======================================
# TEST: LOG FORMAT
# ======================================

class TestLogFormat(unittest.TestCase):
    """Verify the millisecond timestamp prefix appears in log messages."""

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices = make_device_registry()
        self.plugin = make_plugin()

    def test_log_contains_millisecond_timestamp(self):
        """Log message starts with [HH:MM:SS.mmm] format."""
        import re
        orig = MockDevice(812537401, "Basin Occupancy Sensor", on_state=False)
        new  = MockDevice(812537401, "Basin Occupancy Sensor", on_state=True)
        self.plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        ts_pattern = re.compile(r"^\[\d{2}:\d{2}:\d{2}\.\d{3}\]")
        self.assertTrue(
            any(ts_pattern.match(m) for m in msgs),
            msg=f"Expected [HH:MM:SS.mmm] prefix. Got: {msgs}"
        )


# ======================================
# TEST: VARIABLE STARTUP VALIDATION
# ======================================

class TestVariableStartupValidation(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices   = make_device_registry()
        mock_indigo.variables = make_variable_registry()

    def test_all_variables_found_logs_ok(self):
        """startup() logs [OK] for every monitored variable when all exist."""
        plugin = make_plugin()
        plugin.startup()

        info_calls = [str(c) for c in plugin.logger.info.call_args_list]
        ok_count   = sum(1 for c in info_calls if "[OK]" in c)

        # ok_count covers both devices and variables
        expected = len(DEVICE_MONITOR) + len(VARIABLE_MONITOR)
        self.assertEqual(ok_count, expected,
            msg=f"Expected {expected} [OK] entries, got {ok_count}.\nInfo: {info_calls}")

    def test_all_variables_found_logs_final_ok(self):
        """startup() logs 'All monitored variables validated OK' when none missing."""
        plugin = make_plugin()
        plugin.startup()

        info_text = " ".join(str(c) for c in plugin.logger.info.call_args_list)
        self.assertIn("All monitored variables validated OK", info_text)

    def test_missing_variable_logs_bang(self):
        """startup() logs [!] for a missing variable ID."""
        mock_indigo.variables = make_variable_registry(missing_ids=[241032502])

        plugin = make_plugin()
        plugin.startup()

        warn_calls = [str(c) for c in plugin.logger.warning.call_args_list]
        self.assertTrue(any("[!]" in c and "241032502" in c for c in warn_calls),
            msg=f"Expected [!] for missing variable. Got: {warn_calls}")

    def test_variable_subscribetochanges_called(self):
        """startup() calls indigo.variables.subscribeToChanges()."""
        called = []
        mock_indigo.variables = make_variable_registry()
        mock_indigo.variables.subscribeToChanges = lambda: called.append(True)

        plugin = make_plugin()
        plugin.startup()

        self.assertEqual(len(called), 1, "variables.subscribeToChanges() should be called once")


# ======================================
# TEST: VARIABLE UPDATED
# ======================================

class TestVariableUpdated(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices   = make_device_registry()
        mock_indigo.variables = make_variable_registry()
        self.plugin = make_plugin()

    def test_value_change_logged_with_arrow(self):
        """Variable value change logs 'old -> new' format."""
        orig = MockVariable(241032502, "Lux_Level", "450")
        new  = MockVariable(241032502, "Lux_Level", "520")
        self.plugin.variableUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any("450" in m and "520" in m and "->" in m for m in msgs),
            msg=f"Expected '450 -> 520' in log. Got: {msgs}")

    def test_custom_label_used_in_log(self):
        """Label from variable_monitor config appears in log instead of raw variable name."""
        orig = MockVariable(241032502, "Lux_Level", "100")
        new  = MockVariable(241032502, "Lux_Level", "200")
        self.plugin.variableUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any("Lux Level" in m for m in msgs),
            msg=f"Expected label 'Lux Level' in log. Got: {msgs}")

    def test_no_change_no_log(self):
        """Unchanged variable value produces no log output."""
        orig = MockVariable(241032502, "Lux_Level", "450")
        new  = MockVariable(241032502, "Lux_Level", "450")
        self.plugin.variableUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()

    def test_unmonitored_variable_ignored(self):
        """Variable not in variable_monitor is silently ignored."""
        orig = MockVariable(999999999, "Some_Other_Var", "a")
        new  = MockVariable(999999999, "Some_Other_Var", "b")
        self.plugin.variableUpdated(orig, new)

        mock_indigo.server.log.assert_not_called()

    def test_rename_detection_logged(self):
        """Variable rename on a monitored variable is logged."""
        orig = MockVariable(241032502, "Old_Lux_Name", "100")
        new  = MockVariable(241032502, "New_Lux_Name", "100")
        self.plugin.variableUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(any("Old_Lux_Name" in m and "New_Lux_Name" in m for m in msgs),
            msg=f"Expected rename log. Got: {msgs}")


# ======================================
# TEST: VARIABLE DELETED
# ======================================

class TestVariableDeleted(unittest.TestCase):

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices   = make_device_registry()
        mock_indigo.variables = make_variable_registry()
        self.plugin = make_plugin()

    def test_monitored_variable_deleted_warns(self):
        """Deleting a monitored variable triggers a warning with name and ID."""
        var = MockVariable(241032502, "Lux_Level", "0")
        self.plugin.variableDeleted(var)

        self.plugin.logger.warning.assert_called()
        warn_text = " ".join(str(c) for c in self.plugin.logger.warning.call_args_list)
        self.assertIn("Lux_Level", warn_text)
        self.assertIn("241032502", warn_text)

    def test_unmonitored_variable_deleted_silent(self):
        """Deleting an unmonitored variable produces no warning."""
        var = MockVariable(999999999, "Irrelevant_Var", "0")
        self.plugin.variableDeleted(var)

        self.plugin.logger.warning.assert_not_called()


# ======================================
# TEST: JSON CONFIG LOADING
# ======================================

class TestConfigLoading(unittest.TestCase):
    """Verify _load_config() correctly reads sensor_monitor_config.json."""

    def setUp(self):
        mock_indigo.server.log.reset_mock()
        mock_indigo.devices   = make_device_registry()
        mock_indigo.variables = make_variable_registry()
        self._tmp_files = []

    def tearDown(self):
        for path in self._tmp_files:
            try:
                os.unlink(path)
            except Exception:
                pass

    def _write_config(self, content):
        """Write content to a temp file and return the path."""
        fd, path = tempfile.mkstemp(suffix=".json", prefix="sm_test_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        self._tmp_files.append(path)
        return path

    # --- Fallback behaviour ---

    def test_fallback_when_no_file(self):
        """When no config file exists, falls back to DEVICE_MONITOR / VARIABLE_MONITOR."""
        plugin = make_plugin()
        # No file at default path - plugin should mirror the module-level dicts
        self.assertEqual(
            set(plugin.device_monitor.keys()),
            set(DEVICE_MONITOR.keys()),
            msg="device_monitor keys should match DEVICE_MONITOR fallback"
        )
        self.assertEqual(
            set(plugin.variable_monitor.keys()),
            set(VARIABLE_MONITOR.keys()),
            msg="variable_monitor keys should match VARIABLE_MONITOR fallback"
        )

    def test_fallback_is_deep_copy(self):
        """Fallback dicts are independent copies - mutating one does not affect the other."""
        plugin = make_plugin()
        plugin.device_monitor[999999999] = [{"state": "onState", "label": "Test"}]
        self.assertNotIn(999999999, DEVICE_MONITOR,
            msg="Mutating device_monitor should not alter module-level DEVICE_MONITOR")

    # --- Device loading ---

    def test_devices_loaded_from_json(self):
        """Devices section of JSON is loaded into self.device_monitor."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "onState", "label": "Test Device"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        self.assertIn(111111, plugin.device_monitor,
            msg="Device ID 111111 should be in device_monitor")
        self.assertEqual(plugin.device_monitor[111111][0]["label"], "Test Device")

    def test_variables_loaded_from_json(self):
        """Variables section of JSON is loaded into self.variable_monitor."""
        config = '''{
  "devices": [],
  "variables": [
    {"id": 222222, "label": "Test Var"}
  ]
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        self.assertIn(222222, plugin.variable_monitor,
            msg="Variable ID 222222 should be in variable_monitor")
        self.assertEqual(plugin.variable_monitor[222222]["label"], "Test Var")

    # --- Comment stripping ---

    def test_comment_lines_ignored(self):
        """Lines starting with # are stripped before JSON parsing."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "onState", "label": "Active Device"},
# {"id": 222222, "state": "onState", "label": "Disabled Device"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        self.assertIn(111111, plugin.device_monitor,
            msg="Active device should be present")
        self.assertNotIn(222222, plugin.device_monitor,
            msg="Commented-out device should be absent")

    def test_indented_comment_lines_ignored(self):
        """Lines with leading whitespace before # are also treated as comments."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "onState", "label": "Active"},
    # {"id": 333333, "state": "onState", "label": "Indented Comment"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        self.assertIn(111111, plugin.device_monitor)
        self.assertNotIn(333333, plugin.device_monitor)

    # --- Trailing comma handling ---

    def test_trailing_comma_in_devices_handled(self):
        """Trailing comma after last device entry does not cause parse error."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "onState", "label": "Test"},
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)  # Should not raise

        self.assertIn(111111, plugin.device_monitor)

    def test_trailing_comma_in_variables_handled(self):
        """Trailing comma after last variable entry does not cause parse error."""
        config = '''{
  "devices": [],
  "variables": [
    {"id": 222222, "label": "Var"},
  ]
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)  # Should not raise

        self.assertIn(222222, plugin.variable_monitor)

    # --- Multi-state devices ---

    def test_multi_state_device_grouped_by_id(self):
        """Multiple entries with the same device ID are grouped into a list."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "pirDetection", "label": "PIR"},
    {"id": 111111, "state": "presence",     "label": "mmWave Presence"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        self.assertIn(111111, plugin.device_monitor)
        self.assertEqual(len(plugin.device_monitor[111111]), 2,
            msg="Two entries for same ID should produce a list of 2 configs")
        labels = [c["label"] for c in plugin.device_monitor[111111]]
        self.assertIn("PIR", labels)
        self.assertIn("mmWave Presence", labels)

    # --- on_text / off_text ---

    def test_custom_on_off_text_preserved(self):
        """on_text and off_text from JSON are preserved in state config."""
        config = '''{
  "devices": [
    {"id": 111111, "state": "onState", "label": "Door",
     "on_text": "OPEN", "off_text": "CLOSED"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        cfg = plugin.device_monitor[111111][0]
        self.assertEqual(cfg.get("on_text"),  "OPEN")
        self.assertEqual(cfg.get("off_text"), "CLOSED")

    # --- name as label fallback ---

    def test_name_used_as_label_fallback(self):
        """If label is absent, the name field is used as the label."""
        config = '''{
  "devices": [
    {"id": 111111, "name": "My Sensor Name", "state": "onState"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        label = plugin.device_monitor[111111][0]["label"]
        self.assertEqual(label, "My Sensor Name",
            msg="name should be used when label is absent")

    # --- Integration: loaded config works in callbacks ---

    def test_json_loaded_config_works_in_deviceupdated(self):
        """deviceUpdated() correctly uses config loaded from JSON file."""
        config = '''{
  "devices": [
    {"id": 333333, "state": "onState", "label": "JSON Label"}
  ],
  "variables": []
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        mock_indigo.server.log.reset_mock()
        orig = MockDevice(333333, "JSON Test Device", on_state=False)
        new  = MockDevice(333333, "JSON Test Device", on_state=True)
        plugin.deviceUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(
            any("JSON Test Device" in m and "JSON Label" in m for m in msgs),
            msg=f"Expected JSON-configured label in log. Got: {msgs}"
        )

    def test_json_loaded_config_works_in_variableupdated(self):
        """variableUpdated() correctly uses config loaded from JSON file."""
        config = '''{
  "devices": [],
  "variables": [
    {"id": 444444, "label": "JSON Var Label"}
  ]
}'''
        path   = self._write_config(config)
        plugin = make_plugin()
        plugin._load_config(path)

        mock_indigo.server.log.reset_mock()
        orig = MockVariable(444444, "some_var", "10")
        new  = MockVariable(444444, "some_var", "20")
        plugin.variableUpdated(orig, new)

        msgs = server_log_messages()
        self.assertTrue(
            any("JSON Var Label" in m and "10" in m and "20" in m for m in msgs),
            msg=f"Expected JSON-configured variable label in log. Got: {msgs}"
        )

    # --- Error resilience ---

    def test_invalid_json_falls_back_to_defaults(self):
        """Malformed JSON causes fallback to DEVICE_MONITOR / VARIABLE_MONITOR."""
        path   = self._write_config("{ this is not valid json }")
        plugin = make_plugin()
        plugin._load_config(path)

        # Should fall back silently
        self.assertEqual(
            set(plugin.device_monitor.keys()),
            set(DEVICE_MONITOR.keys()),
            msg="Invalid JSON should trigger fallback to DEVICE_MONITOR"
        )


# ======================================
# ENTRY POINT
# ======================================

if __name__ == "__main__":
    print(f"\nSensor Monitor Plugin - Mock Test Suite")
    print(f"plugin.py: {_plugin_path}")
    print(f"Monitored devices in DEVICE_MONITOR:    {len(DEVICE_MONITOR)}")
    print(f"Monitored variables in VARIABLE_MONITOR: {len(VARIABLE_MONITOR)}\n")
    unittest.main(verbosity=2)
