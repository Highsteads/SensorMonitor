# Sensor Monitor — Indigo Plugin

**Version**: 1.4.0
**Author**: CliveS
**Platform**: Indigo 2025.1 / macOS / Python 3.11
**Plugin ID**: `com.clives.indigoplugin.sensormonitor`

---

## Overview

Sensor Monitor is an Indigo plugin that watches for state changes across a configured list of
sensors and logs them to the Indigo event log with millisecond-precision timestamps.

Instead of creating individual Indigo triggers and separate Python scripts for each sensor,
this plugin handles all sensor logging from a single configuration. Device names are always
read live from Indigo, so renaming a device is instantly reflected in logs with no code
changes required.

---

## Features

- Monitors any number of sensors from a single JSON config file
- Supports multiple states per device (e.g. FP300 with both PIR and mmWave presence)
- Custom ON/OFF labels per state (e.g. OPEN/CLOSED for door contacts)
- Millisecond-precision timestamps in all log entries
- **JSON config file** — edit outside the plugin, comment out entries with `#`, no Python needed
- **Plugin menu** — Discover Devices, Find Contact Sensors, and Reload Config via Plugins > Sensor Monitor
- **Discovery script** — scans all Indigo devices and generates a ready-to-use config file
- **Variable monitoring** — logs Indigo variable value changes with `old -> new` format
- **Startup validation** — warns about any configured device IDs not found in Indigo
- **Rename detection** — logs when a monitored device or variable is renamed in Indigo
- **Deletion warning** — warns when a monitored device or variable is deleted from Indigo

---

## Sensors Currently Monitored

The plugin monitors whichever devices and variables you configure — either in the JSON
config file (`sensor_monitor_config.json`) or in the fallback Python dicts inside `plugin.py`.
The example configuration covers occupancy sensors, mmWave presence sensors, and a door
contact sensor, but you can monitor any Indigo device state.

See [Configuration File](#configuration-file) and [Adding a New Sensor](#adding-a-new-sensor)
below for how to set up your own devices.

---

## Installation

1. Double-click `Sensor_Monitor.indigoPlugin` — Indigo will prompt to install it
2. Go to **Plugins > Manage Plugins** in Indigo
3. Enable **Sensor Monitor**
4. Check the Indigo event log — you will see startup validation output confirming
   which devices were found

---

## Configuration File

From v1.3.0, the plugin reads its device and variable lists from a JSON config file
instead of requiring edits to `plugin.py`.

**File location**: `~/Documents/Indigo/SensorMonitor/sensor_monitor_config.json`

If the file does not exist, the plugin falls back to the hardcoded `DEVICE_MONITOR` and
`VARIABLE_MONITOR` dicts in `plugin.py`.

### Generating the config file

Run `discover_devices.py` once from the Indigo Script Editor:

1. Open **Indigo > Scripts > New Script**
2. Paste the contents of `discover_devices.py` into the editor
3. Click **Run**
4. Open `sensor_monitor_config.json` — contact sensor candidates are active, all others
   are commented out for reference
5. Edit the file as needed (see below)
6. Reload the plugin: **Plugins > Sensor Monitor > Reload Plugin**

### Config file format

```json
{
  "devices": [
    {"id": 123456789, "name": "Front Door",  "state": "onState",  "label": "Front Door",  "on_text": "OPEN", "off_text": "CLOSED"},
    {"id": 987654321, "name": "Lounge PIR",  "state": "onState",  "label": "Occupancy"},
    {"id": 111222333, "name": "Basin mmWave","state": "pirDetection", "label": "PIR"},
    {"id": 111222333, "name": "Basin mmWave","state": "presence",     "label": "mmWave Presence"},
# {"id": 444555666, "name": "Disabled Sensor", "state": "onState", "label": "Test"}
  ],
  "variables": [
    {"id": 241032502, "name": "Lux_Level", "label": "Lux Level"}
  ]
}
```

**Key points:**

- Any line whose first non-whitespace character is `#` is ignored — use this to disable
  an entry without deleting it
- Trailing commas before `]` or `}` are allowed (the plugin cleans them up automatically)
- Multiple rows with the same `id` are grouped — this is how you monitor multiple states
  on a single device (see Basin mmWave example above)
- `name` is for your reference only; `label` is what appears in the Indigo event log
- `on_text` / `off_text` are optional (default: `ON` / `OFF`)

### Config field reference

| Field      | Required | Description                                                        |
|------------|----------|--------------------------------------------------------------------|
| `id`       | Yes      | Indigo device or variable ID (integer)                             |
| `name`     | No       | Human-readable device name for your reference                      |
| `state`    | Yes (devices) | `"onState"` uses `device.onState`; any other name reads from `device.states` |
| `label`    | No       | Text shown in the log after the device name (defaults to `name`)   |
| `on_text`  | No       | Log text when state is True (default: `"ON"`)                      |
| `off_text` | No       | Log text when state is False (default: `"OFF"`)                    |

After saving changes, reload: **Plugins > Sensor Monitor > Reload Plugin**

---

## Adding a New Sensor

### Via the config file (recommended)

Add a line to the `"devices"` section of `sensor_monitor_config.json`:

```json
{"id": 123456789, "name": "Hall PIR", "state": "onState", "label": "Occupancy"},
```

Find the device ID in Indigo by right-clicking the device and choosing
**Copy Device ID to Clipboard** (or check the device's Info tab).

### Via plugin.py (fallback only)

If you are not using a config file, edit `DEVICE_MONITOR` in `plugin.py`:

```python
DEVICE_MONITOR = {
    # existing entries ...

    123456789: [{"state": "onState", "label": "Occupancy"}],
}
```

### Multiple states per device (config file)

Add two rows with the same `id`:

```json
{"id": 123456789, "state": "pirDetection", "label": "PIR"},
{"id": 123456789, "state": "presence",     "label": "mmWave Presence"},
```

### Multiple states per device (plugin.py)

```python
123456789: [{"state": "pirDetection", "label": "PIR"},
            {"state": "presence",     "label": "mmWave Presence"}],
```

### Custom ON/OFF labels

```json
{"id": 123456789, "state": "onState", "label": "Front Door", "on_text": "OPEN", "off_text": "CLOSED"},
```

---

## Adding a Variable to Monitor

Add a line to the `"variables"` section of `sensor_monitor_config.json`:

```json
{"id": 241032502, "name": "Lux_Level", "label": "Lux Level"},
```

Variable IDs can be found by right-clicking the variable in Indigo and choosing
**Copy Variable ID to Clipboard**.

Log output: `[14:23:01.452] Lux Level: 450 -> 520`

---

## Log Output Examples

```
[14:23:01.452] Hall PIR Occupancy ON
[14:23:01.891] Basin Sensor mmWave Presence ON
[14:25:33.104] Front Door Contact OPEN
[14:25:41.230] Front Door Contact CLOSED
[14:26:10.512] Lux Level: 450 -> 520
[14:30:00.001] [Sensor Monitor] Device renamed: 'Test Sensor' -> 'Hall PIR' (ID: 99887766)
[14:31:05.774] [Sensor Monitor] WARNING - Monitored device deleted: 'Hall PIR' (ID: 99887766) - remove from config file or DEVICE_MONITOR in plugin.py
```

---

## Startup Validation Output

On every plugin start or reload, all configured devices and variables are validated:

```
[Sensor Monitor] Config loaded from: /Users/.../sensor_monitor_config.json (10 devices, 1 variables)
[Sensor Monitor] Device validation - 10 found, 0 missing:
  [OK] Front Door Contact (ID: 123456789)
  ...
[Sensor Monitor] All monitored devices validated OK
[Sensor Monitor] Variable validation - 1 found, 0 missing:
  [OK] Lux_Level (ID: 241032502)
[Sensor Monitor] All monitored variables validated OK
```

If a device ID is not found:
```
  [!]  ID 999999999 - not found in Indigo
[Sensor Monitor] 1 monitored device(s) not found - check IDs in config file or DEVICE_MONITOR in plugin.py
```

---

## Migrating from Triggers and Scripts

If you currently monitor sensors using individual Indigo triggers or standalone Python
scripts, this plugin replaces all of them with a single subscription.

Once the plugin is confirmed working:

- **Remove Indigo triggers** that fire on state changes for your monitored devices —
  the plugin handles all logging for them directly
- **Retire any per-sensor scripts** that log or react to individual device state changes —
  add those devices to the config file instead

The plugin processes every configured device from one callback, so there is no need to
maintain separate triggers or scripts per sensor.

---

## Plugin Menu

The following items are available under **Plugins > Sensor Monitor**:

| Menu item | What it does |
|-----------|--------------|
| **Discover All Devices (generate config file)** | Scans every Indigo device, writes `device_discovery.json` (full inventory) and a fresh `sensor_monitor_config.json` (contact candidates active, all others commented out). Identical to running `discover_devices.py` in the Script Editor but runs from the menu with one click. |
| **Find Contact Sensors** | Logs all contact/door/window sensor candidates to the Indigo event log with their ready-to-paste config entries. Useful for a quick check without regenerating the full config file. |
| *(separator)* | |
| **Reload Config File** | Re-reads `sensor_monitor_config.json` and re-validates all devices and variables — without a full plugin restart. Use this after editing the config file. |

---

## File Structure

```
Sensor_Monitor.indigoPlugin/
├── README.md
└── Contents/
    ├── Info.plist
    └── Server Plugin/
        ├── plugin.py              # Main plugin code — also contains all menu callbacks
        ├── MenuItems.xml          # Defines the Plugins > Sensor Monitor menu items
        ├── discover_devices.py    # Standalone Script Editor version of Discover Devices
        ├── find_contact_sensors.py # Standalone Script Editor version of Find Contact Sensors
        └── test_plugin.py         # Mock test suite — run with: python3 test_plugin.py -v
```

**Config file** (generated by `discover_devices.py`, lives outside the plugin bundle):
```
~/Documents/Indigo/SensorMonitor/
├── sensor_monitor_config.json   # Edit this to add/remove/disable devices
└── device_discovery.json        # Full device inventory from last discovery run
```

`test_plugin.py` is ignored by Indigo at runtime. Run it from Terminal to verify the
plugin logic outside of the Indigo runtime environment.

---

## Changelog

| Version | Date       | Change |
|---------|------------|--------|
| 1.4.0   | 2026-02-27 | Plugin menu — Discover All Devices, Find Contact Sensors, Reload Config File (MenuItems.xml + menu callbacks in plugin.py) |
| 1.3.0   | 2026-02-27 | JSON config file support — sensor_monitor_config.json with # comment lines, discover_devices.py generates ready-to-use config |
| 1.2.0   | 2026-02-27 | Variable monitoring — VARIABLE_MONITOR dict, variableUpdated(), variableDeleted() |
| 1.1.0   | 2026-02-27 | Startup device validation, rename detection, deviceDeleted() warning, mock test suite |
| 1.0.0   | 2026-02-27 | Initial release — subscribeToChanges, multi-state per device, custom on/off labels |

---

## How It Works

1. On `startup()`, the plugin calls `indigo.devices.subscribeToChanges()` and
   `indigo.variables.subscribeToChanges()` to receive callbacks for every change
2. `_load_config()` reads `sensor_monitor_config.json` (if it exists) and builds
   `self.device_monitor` and `self.variable_monitor`; falls back to the hardcoded
   Python dicts if no file is found
3. `deviceUpdated(origDev, newDev)` fires for every change — the plugin checks if the
   device ID is in `self.device_monitor` and ignores everything else
4. For each configured state, it compares old vs new value and only logs if it changed
5. `variableUpdated(origVar, newVar)` logs value changes in `old -> new` format
6. `deviceDeleted(dev)` and `variableDeleted(var)` warn when a monitored item is removed
7. Device names come from `newDev.name` (live from Indigo) — never hardcoded
