# Sensor Monitor — Indigo Plugin

**Version**: 1.1.0
**Author**: CliveS
**Platform**: Indigo 2025.1 / macOS / Python 3.11
**Plugin ID**: `com.clives.indigoplugin.sensormonitor`

---

## Overview

Sensor Monitor is an Indigo plugin that watches for state changes across a configured list of
sensors and logs them to the Indigo event log with millisecond-precision timestamps.

Instead of creating individual Indigo triggers and separate Python scripts for each sensor,
this plugin handles all sensor logging from a single configuration dictionary. Device names
are always read live from Indigo, so renaming a device is instantly reflected in logs with
no code changes required.

---

## Features

- Monitors any number of sensors from a single config dict
- Supports multiple states per device (e.g. FP300 with both PIR and mmWave presence)
- Custom ON/OFF labels per state (e.g. OPEN/CLOSED for door contacts)
- Millisecond-precision timestamps in all log entries
- **Startup validation** — warns about any configured device IDs not found in Indigo
- **Rename detection** — logs when a monitored device is renamed in Indigo
- **Deletion warning** — warns when a monitored device is deleted from Indigo

---

## Sensors Currently Monitored

The plugin monitors whichever devices you configure in `DEVICE_MONITOR` inside
`plugin.py`. The example configuration included covers occupancy sensors, mmWave
presence sensors, and a door contact sensor across several rooms — but you can monitor
any Indigo device and any of its states.

See [Adding a New Sensor](#adding-a-new-sensor) below for how to configure your own devices.

---

## Installation

1. Double-click `Sensor_Monitor.indigoPlugin` — Indigo will prompt to install it
2. Go to **Plugins > Manage Plugins** in Indigo
3. Enable **Sensor Monitor**
4. Check the Indigo event log — you will see startup validation output confirming
   which devices were found

---

## Adding a New Sensor

Open `Contents/Server Plugin/plugin.py` and add an entry to `DEVICE_MONITOR`:

```python
DEVICE_MONITOR = {
    # existing entries ...

    123456789: [{"state": "onState", "label": "Occupancy"}],
}
```

Find the device ID in Indigo by right-clicking the device and choosing
**Copy Device ID to Clipboard** (or check the device's Info tab).

Reload the plugin after saving (`Plugins > Sensor Monitor > Reload Plugin`).

### State config options

| Key        | Required | Description                                                         |
|------------|----------|---------------------------------------------------------------------|
| `state`    | Yes      | `"onState"` uses `device.onState`; any other name reads from `device.states` |
| `label`    | Yes      | Text shown after the device name in the log                         |
| `on_text`  | No       | Log text when state is True (default: `"ON"`)                       |
| `off_text` | No       | Log text when state is False (default: `"OFF"`)                     |

### Multiple states per device

```python
1976004986: [{"state": "pirDetection", "label": "PIR"},
             {"state": "presence",     "label": "mmWave Presence"}],
```

### Custom ON/OFF labels

```python
415253439: [{"state": "onState", "label": "Contact",
             "on_text": "OPEN", "off_text": "CLOSED"}],
```

---

## Log Output Examples

```
[14:23:01.452] Z Bathroom Basin Occupancy Sensor PIR ON
[14:23:01.891] Z Bathroom Basin Occupancy Sensor mmWave Presence ON
[14:25:33.104] Bathroom Door Contact Sensor Contact OPEN
[14:25:41.230] Bathroom Door Contact Sensor Contact CLOSED
[14:30:00.001] [Sensor Monitor] Device renamed: 'Test Sensor' -> 'Hall PIR' (ID: 99887766)
[14:31:05.774] [Sensor Monitor] WARNING - Monitored device deleted: 'Hall PIR' (ID: 99887766) - remove from DEVICE_MONITOR in plugin.py
```

---

## Startup Validation Output

On every plugin start or reload, all configured devices are validated:

```
[Sensor Monitor] Device validation - 10 found, 0 missing:
  [OK] Z Bathroom Basin Occupancy Sensor (ID: 812537401)
  [OK] Z Bathroom Basin Occupancy Sensor (ID: 1976004986)
  ...
[Sensor Monitor] All monitored devices validated OK
```

If a device ID is not found:
```
  [!]  ID 999999999 - not found in Indigo
[Sensor Monitor] 1 monitored device(s) not found - check IDs in DEVICE_MONITOR in plugin.py
```

---

## Migrating from Triggers and Scripts

If you currently monitor sensors using individual Indigo triggers or standalone Python
scripts, this plugin replaces all of them with a single subscription.

Once the plugin is confirmed working:

- **Remove Indigo triggers** that fire on state changes for your monitored devices —
  the plugin handles all logging for them directly
- **Retire any per-sensor scripts** that log or react to individual device state changes —
  add those devices to `DEVICE_MONITOR` instead

The plugin processes every device in `DEVICE_MONITOR` from one callback, so there is no
need to maintain separate triggers or scripts per sensor.

---

## File Structure

```
Sensor_Monitor.indigoPlugin/
├── README.md
└── Contents/
    ├── Info.plist
    └── Server Plugin/
        ├── plugin.py          # Main plugin code — edit DEVICE_MONITOR here
        └── test_plugin.py     # Mock test suite — run with: python3 test_plugin.py -v
```

`test_plugin.py` is ignored by Indigo at runtime. Run it from Terminal to verify the
plugin logic outside of the Indigo runtime environment.

---

## Changelog

| Version | Date       | Change |
|---------|------------|--------|
| 1.2.0   | 2026-02-27 | Variable monitoring — VARIABLE_MONITOR dict, variableUpdated(), variableDeleted() |
| 1.1.0   | 2026-02-27 | Startup device validation, rename detection, deviceDeleted() warning, mock test suite |
| 1.0.0   | 2026-02-27 | Initial release — subscribeToChanges, multi-state per device, custom on/off labels |

---

## How It Works

1. On `startup()`, the plugin calls `indigo.devices.subscribeToChanges()` to receive
   callbacks for every device state change in Indigo
2. `deviceUpdated(origDev, newDev)` fires for every change — the plugin checks if the
   device ID is in `DEVICE_MONITOR` and ignores everything else
3. For each configured state, it compares old vs new value and only logs if it changed
4. `deviceDeleted(dev)` fires when any device is deleted — warns if it was monitored
5. Device names come from `newDev.name` (live from Indigo) — never hardcoded
