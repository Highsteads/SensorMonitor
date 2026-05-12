# Device Activity Monitor — Indigo Plugin

**Version**: 1.9.0
**Author**: CliveS
**Platform**: Indigo 2022.1 or later / macOS / Python 3.10+

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*
**Plugin ID**: `com.clives.indigoplugin.deviceactivitymonitor`
**GitHub**: <https://github.com/Highsteads/DeviceActivityMonitor>

> v1.9.0 renamed this plugin from **Sensor Monitor** → **Device Activity Monitor**.
> Same lineage; the new name better describes both halves of what it now does:
> per-device change **logging** and group-change custom **triggers**.

---

## Table of contents

- [What it does](#what-it-does)
- [Installation](#installation)
- [Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`](#credentials--indigosecretspy-vs-indigosecrets_examplepy)
- [Quick start in 5 minutes](#quick-start-in-5-minutes)
- [Use cases](#use-cases)
  - [1. Activity logging — passive observer](#1-activity-logging--passive-observer)
  - [2. Single-device direction trigger](#2-single-device-direction-trigger)
  - [3. Multi-sensor "any change" trigger](#3-multi-sensor-any-change-trigger)
  - [4. Multi-sensor "becomes occupied" trigger](#4-multi-sensor-becomes-occupied-trigger)
  - [5. Multi-sensor "becomes empty" trigger](#5-multi-sensor-becomes-empty-trigger)
  - [6. Save which device fired](#6-save-which-device-fired)
  - [7. Combining with conditions and scripts](#7-combining-with-conditions-and-scripts)
  - [8. Variable monitoring](#8-variable-monitoring)
- [Multi-Sensor Trigger — deep dive](#multi-sensor-trigger--deep-dive)
- [Configuration file](#configuration-file)
- [Plugin menu](#plugin-menu)
- [Discovery](#discovery)
- [Log output examples](#log-output-examples)
- [Group device states](#group-device-states)
- [Repository structure](#repository-structure)
- [Migrating from "Sensor Monitor"](#migrating-from-sensor-monitor)
- [Changelog](#changelog)
- [License](#license)

---

## What it does

Device Activity Monitor watches Indigo devices and variables and reacts to their state
changes two complementary ways:

1. **Logs** changes to the Indigo event log with millisecond-precision timestamps and
   custom on/off labels (`Front Door OPEN`, `Lux Level: 450 -> 520`).
2. **Fires custom triggers** when any device in a named **Group** changes state, with
   an optional direction filter (`any change` / `becomes ON/OPEN` / `becomes OFF/CLOSED`).

Groups are first-class Indigo devices managed via a rich two-list Add/Remove ConfigUI —
no JSON editing required. The plugin replaces both:

- A pile of one-trigger-per-device "Device State Changed" triggers
- The older **Group Change Listener** plugin (Morris's) with its painful
  Cmd-click-everything multi-select

…with one subscription, one config file for logging, and one Indigo Group device per
trigger group.

---

## Installation

1. Download `Device_Activity_Monitor.indigoPlugin.zip` from the
   [latest release](https://github.com/Highsteads/DeviceActivityMonitor/releases)
2. Unzip and double-click `Device_Activity_Monitor.indigoPlugin` — Indigo will
   prompt to install
3. **Plugins → Manage Plugins** → enable **Device Activity Monitor**
4. The plugin auto-creates its config folder at
   `<install>/Preferences/Plugins/com.clives.indigoplugin.deviceactivitymonitor/`
5. Open the Indigo Event Log — you should see the startup banner and the loaded
   device count

---

## Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`

This plugin (along with all CliveS Indigo plugins) reads sensitive values from
a shared master credentials file at:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you do not have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` from
the plugin bundle to that location and fill in your values. Or skip
`IndigoSecrets.py` entirely and enter values via the plugin's configuration
dialog — `IndigoSecrets.py` wins over the dialog when both are set.

If a required value is set in NEITHER source the plugin logs an ERROR
pointing the user to either fill in the matching field or add the key to
`IndigoSecrets.py`.

**Note for this plugin specifically**: Device Activity Monitor reads no external
APIs and needs no credentials in normal use. The `IndigoSecrets_example.py`
file is shipped for ecosystem consistency only — there is nothing to fill in
unless you extend the plugin yourself.

---

## Quick start in 5 minutes

**Goal**: get a Pushover notification when *any* of three motion sensors in
the living room detects movement.

1. **Create the group device**
   - **Devices → New Device**
   - Type = "Device Activity Monitor → Device Activity Monitor Group"
   - Name it "Living Room Presence"
   - **Show devices from**: pick `Living Room` (or `(All folders)`)
   - In **Available devices**: ⌘-click your 3 motion sensors
   - Click **Add to Group ↓**
   - Save

2. **Create the trigger**
   - **New Trigger** → Type = "Device Activity Monitor: Group Changed"
   - **Group**: pick "Living Room Presence  (3 members)"
   - **Fire on**: "Any device becomes ON / OPEN / detected"
   - **Actions tab**: add your Pushover action

3. **Done**. Wave at any of the three sensors — Pushover fires. The trigger
   does NOT re-fire while the sensor stays active, and does NOT fire on the
   off transition (because of the direction filter).

That's the headline workflow. The rest of this README covers the variants.

---

## Use cases

### 1. Activity logging — passive observer

You want a single log line every time a sensor changes state, so the event log
becomes a usable timeline. No triggers, no actions — just clean logging.

1. **Plugins → Device Activity Monitor → Discover All Devices**
2. Open `device_activity_monitor_config.json` and uncomment / add the lines
   you want logged
3. **Plugins → Device Activity Monitor → Reload Config File**

Each configured state gets a log line of the form:

    [14:23:01.452] Front Door Contact OPEN
    [14:25:33.104] Hall PIR Occupancy ON

### 2. Single-device direction trigger

Indigo has a built-in "Device State Changed" trigger for this, but if you'd
rather pick by a friendly name from a list of Group devices:

1. Create a group with one member (the device)
2. Trigger → Fire on = "Any device becomes ON / OPEN / detected" (or the OFF variant)

Useful when you want a consistent "group" mental model across single and
multi-device cases.

### 3. Multi-sensor "any change" trigger

Fire whenever any member of the group changes any state. Equivalent to
Morris's Group Change Listener with no filter.

- Group: any number of devices
- Trigger → Fire on = "Any change (default)"

Use this for log-spam-style "something happened in this area" reactions where
direction doesn't matter.

### 4. Multi-sensor "becomes occupied" trigger

Fire once when the *first* member transitions from off to on. Doesn't re-fire
while any other member is also active.

- Group: 3 presence sensors in a room
- Trigger → Fire on = "Any device becomes ON / OPEN / detected"

Common uses:
- Turn on the lights when *anyone* enters a multi-sensor room
- Pushover "movement in the garage" without 3 separate triggers
- Start a "room occupied" timer

### 5. Multi-sensor "becomes empty" trigger

Fire only on the off transition.

- Group: same room sensors
- Trigger → Fire on = "Any device becomes OFF / CLOSED / clear"

Common uses:
- Start a delay timer to turn lights off when the last sensor clears
- Trigger an "armed away" routine when a contact closes

> Pairing: use one group with two triggers — one direction-filtered to
> "becomes ON" and one to "becomes OFF". Each fires only on the relevant
> edge.

### 6. Save which device fired

If multiple devices in a group could be the source, capture the firing
device's name to an Indigo variable so your actions can use it:

1. Trigger ConfigUI → tick **Save firing device**
2. Pick a variable
3. **Save value**: "Device Name" or "Device ID"
4. In your action, reference the variable with `%%v:NN%%` or read it in a
   Python action script

Examples:
- Pushover body: "Movement detected by %%v:firing_sensor%%"
- Script: branch based on which front-of-house contact was triggered

### 7. Combining with conditions and scripts

The trigger doesn't have to fire blindly. Indigo's standard Conditions and
Actions tabs are fully available:

- **Conditions tab**: "only fire between sunset and sunrise" / "only when
  the alarm is armed" / "only when nobody is home"
- **Actions tab**: chain to action groups, Python scripts, action collections,
  send-to-variables, control pages, etc.

For complex multi-room logic, fire one trigger from each group and have the
target action group read all the various states it cares about.

### 8. Variable monitoring

Add Indigo variables to the `variables[]` section of
`device_activity_monitor_config.json`:

    "variables": [
      {"id": 241032502, "name": "Lux_Level", "label": "Lux Level"}
    ]

Output:

    [14:26:10.512] Lux Level: 450 -> 520

---

## Multi-Sensor Trigger — deep dive

The headline feature. This section walks through every option in detail.

### Step 1: create the Group device

**Devices → New Device** → Type = "Device Activity Monitor → Device Activity
Monitor Group".

You get a dialog with these fields:

| Field | What it does |
|-------|--------------|
| **Show devices from** | Folder filter for the Available list. `(All folders)` shows everything; `(Root)` shows un-foldered devices; named folders narrow to that folder's contents |
| **Available devices** | Multi-select list of devices NOT yet in this group. Cmd-click to select multiple, then click Add. Refreshes as the folder filter changes |
| **Add to Group ↓** | Moves the Available-list selection into the Members list |
| **Current group members** | Multi-select list of devices currently in the group. Devices the bridge has since deleted show as `<missing device id NN>` so you can clean them up |
| **↑ Remove from Group** | Moves the Members-list selection back to "available" |

To **edit** a group later, double-click the Group device — same dialog, same
flow. There is no JSON editing.

To **delete** a group, right-click → Delete (standard Indigo flow). Any
triggers wired to the deleted group will log a warning on next plugin reload
that they reference a now-missing group.

Each Group device shows `N members` as its display state in the Indigo device
list.

### Step 2: create the Trigger

**New Trigger** → Type = "Device Activity Monitor: Group Changed".

| Field | What it does |
|-------|--------------|
| **Group** | Dropdown of all Group devices, each labelled with its name and live member count. This is Indigo's native device picker filtered to `self.damGroup` — folder tree, search, the lot |
| **Fire on** | Direction filter (see next section) |
| **Save firing device** | Tick to capture which member triggered the event into an Indigo variable |
| **Save to variable** | (only when Save firing device is ticked) target variable |
| **Save value** | (only when Save firing device is ticked) "Device Name" or "Device ID" |

### Step 3: pick the direction filter

The **Fire on** menu has three options. They look at the device's `onState`
attribute before and after the change.

| Option | Fires when… |
|--------|-------------|
| **Any change** (default) | *Any* state on a group member changes — including non-onState states like temperature readings or battery level. Use sparingly with chatty sensors |
| **Any device becomes ON / OPEN / detected** | A member's `onState` flips from `False` to `True`. Edge-triggered: doesn't re-fire while it stays on. Use for occupancy, door-opens, alarms |
| **Any device becomes OFF / CLOSED / clear** | A member's `onState` flips from `True` to `False`. Edge-triggered: doesn't re-fire while it stays off. Use for "last sensor cleared" timers, door closes |

The directional options only fire on `onState` transitions, so they ignore
chatty value updates (temperature, illuminance, etc.) entirely.

### Step 4: chain to actions

Standard Indigo Actions tab. The trigger fires the same way as any built-in
Indigo trigger — Pushover, action groups, scripts, control pages all work
identically.

If you ticked **Save firing device**, your variable now contains the name or
ID of the device that triggered the firing — reference it via `%%v:NN%%` in
text fields, or read it directly in Python script actions.

### Diagnostic states on the Group device

Whenever a trigger fires for a Group device, the plugin also writes these
states on the Group device itself (useful for control pages or other
triggers):

- `memberCount` — number of devices in the group
- `lastFiringDevice` — name of the device that triggered the most recent fire
- `lastFiringTime` — `YYYY-MM-DD HH:MM:SS`
- `lastFiringDirection` — `activated` / `deactivated` / `changed`
- `status` — display string, e.g. "3 members"

---

## Configuration file

Lives at:

    <install>/Preferences/Plugins/com.clives.indigoplugin.deviceactivitymonitor/
    ├── device_activity_monitor_config.json   ← edit this
    └── device_discovery.json                 ← generated by Discover Devices

`<install>` resolves via `indigo.server.getInstallFolderPath()` so the path
follows your active Indigo version automatically.

### Format

```json
{
  "_usage": "Lines starting with # are ignored. Reload plugin after changes.",
  "excluded_ids": [],
  "devices": [
    {"id": 123456789, "name": "Front Door",  "state": "onState", "label": "Front Door",  "on_text": "OPEN", "off_text": "CLOSED"},
    {"id": 987654321, "name": "Basin mmWave","state": "pirDetection", "label": "PIR"},
    {"id": 987654321, "name": "Basin mmWave","state": "presence",     "label": "mmWave Presence"}
  ],
  "variables": [
    {"id": 241032502, "name": "Lux_Level", "label": "Lux Level"}
  ]
}
```

### Conventions

- `#` at the start of a line disables that entry. Use this to comment out a
  device without deleting the line
- Trailing commas before `]` or `}` are silently cleaned up
- Multiple rows with the same `id` monitor multiple states on one device
  (e.g. PIR and mmWave on a multi-state sensor)
- After saving, reload via **Plugins → Device Activity Monitor → Reload
  Config File** — no plugin restart required

### Field reference

| Field      | Required | Description                                                                  |
|------------|----------|------------------------------------------------------------------------------|
| `id`       | Yes      | Indigo device or variable ID (integer)                                       |
| `name`     | No       | For your reference only — never used by the code                             |
| `state`    | Yes      | `"onState"` reads `device.onState`; any other name reads from `device.states`|
| `label`    | No       | Log text shown after the device name (defaults to `name`)                    |
| `on_text`  | No       | Log text when state is True (default `ON`)                                   |
| `off_text` | No       | Log text when state is False (default `OFF`)                                 |

### Groups are NOT in this file

As of v1.8.0, groups live as `damGroup` Indigo devices, not in the JSON file.
This file is logging-only.

---

## Plugin menu

Under **Plugins → Device Activity Monitor**:

| Item | What it does |
|------|--------------|
| **Discover All Devices (generate config file)** | Scans every Indigo device, classifies contact / motion / presence candidates using device type, Zigbee2MQTT capability flags, and name keywords. Writes `device_discovery.json` (full inventory) and a fresh `device_activity_monitor_config.json` (sensor candidates active, all others commented out for reference). Preserves `excluded_ids` across re-runs |
| **Find Contact & Motion Sensors** | One-shot log dump of all sensor candidates with ready-to-paste config entries — useful for a quick check without regenerating the whole config |
| **Reload Config File** | Re-reads the JSON and re-validates without a full plugin restart. Use after editing the config file by hand |
| **Show Plugin Info** | Prints the startup banner on demand |

---

## Discovery

Discovery uses a layered classifier that gets the right answer even on
generic Zigbee2MQTT devices that publish stub fields they don't physically
have:

1. **Z2M ownerProps** (authoritative when available): `has_contact`,
   `has_occupancy`, `has_presence`, `has_pir`
2. **deviceTypeId hints**: `z2mContactSensor` → contact, `z2mOccupancySensor`
   → motion
3. **Motion-keyword veto**: if the device name contains `motion`, `pir`,
   `presence`, `occupancy`, `mmwave`, `radar`, it can't be a contact sensor
4. **State-name match**: `contact` / `doorSensor` / `windowSensor` → contact;
   `occupancy` / `pirDetection` / `presence` / `motion` / `motionDetected`
   → motion
5. **Name-keyword match**: `contact`, `door`, `window`, etc.

To **permanently exclude** a device from discovery output, add its ID to the
`excluded_ids` array in the config file. Subsequent re-discovery runs will
respect the exclusion and leave that device commented out.

To **add a sensor that discovery missed**, just add a line manually to
`devices[]` — discovery never deletes manually-added entries.

---

## Log output examples

```
[14:23:01.452] Hall PIR Occupancy ON
[14:23:01.891] Basin Sensor mmWave Presence ON
[14:25:33.104] Front Door Contact OPEN
[14:25:41.230] Front Door Contact CLOSED
[14:26:10.512] Lux Level: 450 -> 520
[14:30:00.001] [Device Activity Monitor] Device renamed: 'Test Sensor' -> 'Hall PIR' (ID: 99887766)
[14:31:05.774] [Device Activity Monitor] WARNING - Monitored device deleted: 'Hall PIR' (ID: 99887766)
```

---

## Group device states

Each `damGroup` device exposes:

| State                  | Type    | Updated when                                |
|------------------------|---------|---------------------------------------------|
| `memberCount`          | Integer | Group device is saved / reloaded            |
| `status`               | String  | Display state — e.g. `"3 members"`         |
| `lastFiringDevice`     | String  | A trigger wired to this group fires        |
| `lastFiringTime`       | String  | `YYYY-MM-DD HH:MM:SS` of last fire          |
| `lastFiringDirection`  | String  | `activated` / `deactivated` / `changed`     |

Useful for control pages ("Living Room presence last activity: 2 minutes
ago") or for chaining one group's activity into another trigger's condition.

---

## Repository structure

```
README.md                                                  ← this file (GitHub displays this)
Device_Activity_Monitor.indigoPlugin/
├── Contents/
│   ├── Info.plist
│   └── Server Plugin/
│       ├── plugin.py                       ← main plugin code + ConfigUI callbacks
│       ├── Devices.xml                     ← damGroup device type
│       ├── Events.xml                      ← Group Changed trigger
│       ├── MenuItems.xml                   ← Plugins menu
│       ├── plugin_utils.py                 ← startup banner helper
│       ├── discover_devices.py             ← standalone Script Editor discovery
│       ├── find_contact_sensors.py         ← standalone Script Editor sensor finder
│       ├── test_plugin.py                  ← 86 tests, runs without Indigo
│       └── IndigoSecrets_example.py        ← credential template (unused — ecosystem standard)
```

---

## Migrating from "Sensor Monitor"

If you ever installed a pre-v1.9.0 release of this plugin under the old name:

1. Disable **Sensor Monitor** in Indigo Manage Plugins
2. Delete the old bundle at `<install>/Plugins/Sensor_Monitor.indigoPlugin/`
3. Install Device Activity Monitor v1.9.0
4. Move `<install>/Preferences/Plugins/com.clives.indigoplugin.sensormonitor/` →
   `<install>/Preferences/Plugins/com.clives.indigoplugin.deviceactivitymonitor/`
5. Rename `sensor_monitor_config.json` → `device_activity_monitor_config.json`
   inside that folder
6. Old `smGroup` devices are not auto-migrated to `damGroup` — re-create
   groups via Devices → New Device

(For me specifically: that migration was done at the moment of the rename, so
this section exists only for completeness if I ever do a clean reinstall.)

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.9.0   | 2026-05-12 | **Renamed** Sensor Monitor → Device Activity Monitor (bundle ID, device type id, event id, config filename all changed; legacy migration code stripped) |
| 1.8.1   | 2026-05-12 | Dropped JSON-groups backward-compat path; damGroup devices the sole source of truth |
| 1.8.0   | 2026-05-12 | Groups are now first-class Indigo devices with Add/Remove ConfigUI |
| 1.7.2   | 2026-05-12 | Direction filter (any/activated/deactivated) on group triggers |
| 1.7.1   | 2026-05-11 | Moved config files from `Logs/` to `Preferences/` |
| 1.7.0   | 2026-05-11 | Group-change custom triggers (JSON-defined, since superseded by damGroup devices) |
| 1.6.0   | 2026-05-11 | Z2M-aware sensor classifier (uses ownerProps `has_*` flags) |
| 1.5.9   | 2026-02-27 | Sync live plugin (multiple features since v1.4.0) |
| 1.4.0   | 2026-02-27 | Plugin menu — Discover Devices, Find Contact Sensors, Reload Config File |
| 1.3.0   | 2026-02-27 | JSON config file support |
| 1.2.0   | 2026-02-27 | Variable monitoring |
| 1.1.0   | 2026-02-27 | Startup validation, rename detection, deletion warning |
| 1.0.0   | 2026-02-27 | Initial release |

---

## License

GPL-3.0 — see plugin source files for details.
