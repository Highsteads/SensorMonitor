#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_plugin.py
# Description: Mock test harness for Sensor Monitor plugin - no Indigo runtime needed
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.1
#
# Run from Terminal:
#   cd "/Library/Application Support/Perceptive Automation/Indigo 2025.1/Plugins"
#   cd "Sensor_Monitor.indigoPlugin/Contents/Server Plugin"
#   python3 test_plugin.py -v

import sys
import os
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

Plugin          = _mod.Plugin
DEVICE_MONITOR  = _mod.DEVICE_MONITOR
VARIABLE_MONITOR = _mod.VARIABLE_MONITOR


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
    """Instantiate the Plugin class with minimal prefs."""
    return Plugin(
        "com.clives.indigoplugin.sensormonitor",
        "Sensor Monitor",
        "1.2.0",
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
        """Device ID not in DEVICE_MONITOR is silently ignored."""
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
        """Label from VARIABLE_MONITOR config appears in log instead of raw variable name."""
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
        """Variable not in VARIABLE_MONITOR is silently ignored."""
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
# ENTRY POINT
# ======================================

if __name__ == "__main__":
    print(f"\nSensor Monitor Plugin - Mock Test Suite")
    print(f"plugin.py: {_plugin_path}")
    print(f"Monitored devices in DEVICE_MONITOR:   {len(DEVICE_MONITOR)}")
    print(f"Monitored variables in VARIABLE_MONITOR: {len(VARIABLE_MONITOR)}\n")
    unittest.main(verbosity=2)
