#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    find_contact_sensors.py
# Description: Discovery script - finds all likely contact/door/window sensors in Indigo
#              Paste into Indigo Script Editor and run once to identify device IDs.
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.0

# ======================================
# HOW TO USE
#
# 1. Open Indigo > Scripts > New Script
# 2. Paste this entire file into the editor
# 3. Click Run
# 4. Check the Indigo Event Log for results
#
# The script logs every device that looks like a contact/door/window sensor
# so you can copy the IDs directly into DEVICE_MONITOR in plugin.py.
# ======================================

import indigo
from datetime import datetime

def log(msg):
    indigo.server.log(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# Keywords that suggest a contact/door/window sensor by device name
NAME_KEYWORDS = [
    "contact", "door", "window", "entry", "gate",
    "patio", "garage", "sensor"
]

# State names used by contact/door/window sensors
CONTACT_STATES = [
    "contact",        # zigbee2mqtt boolean: True=closed False=open
    "onState",        # Indigo generic: True=triggered
    "sensorValue",    # Z-Wave generic sensor value
    "doorSensor",
    "windowSensor",
]

log("=" * 60)
log("Sensor Monitor - Contact/Door/Window Sensor Discovery")
log("=" * 60)

found = []

for dev in indigo.devices:
    dev_name_lower = dev.name.lower()

    # Check 1: name contains a contact/door/window keyword
    name_match = any(kw in dev_name_lower for kw in NAME_KEYWORDS)

    # Check 2: device has a contact-like state
    dev_states   = list(dev.states.keys()) if hasattr(dev, "states") else []
    state_match  = any(s in dev_states for s in CONTACT_STATES)
    has_contact  = "contact" in dev_states  # strong indicator

    if name_match or has_contact:
        found.append({
            "id":       dev.id,
            "name":     dev.name,
            "on_state": dev.onState if hasattr(dev, "onState") else "N/A",
            "states":   dev_states,
            "folder":   indigo.devices.folders[dev.folderId].name
                        if dev.folderId and dev.folderId in indigo.devices.folders
                        else "(root)",
        })

if not found:
    log("No contact/door/window sensors found.")
    log("Try broadening the NAME_KEYWORDS list in this script.")
else:
    log(f"Found {len(found)} candidate device(s):")
    log("")
    for d in sorted(found, key=lambda x: x["name"]):
        log(f"  Name   : {d['name']}")
        log(f"  ID     : {d['id']}")
        log(f"  Folder : {d['folder']}")
        log(f"  onState: {d['on_state']}")

        # Identify the best state to monitor
        if "contact" in d["states"]:
            log(f"  -> Use state: 'contact'  (True=CLOSED, False=OPEN - zigbee2mqtt)")
            log(f"     DEVICE_MONITOR entry:")
            log(f"     {d['id']}: [{{'state': 'contact', 'label': '{d['name']}',")
            log(f"                   'on_text': 'CLOSED', 'off_text': 'OPEN'}}],")
        else:
            log(f"  -> Use state: 'onState'  (True=triggered, False=clear)")
            log(f"     DEVICE_MONITOR entry:")
            log(f"     {d['id']}: [{{'state': 'onState', 'label': '{d['name']}',")
            log(f"                   'on_text': 'OPEN', 'off_text': 'CLOSED'}}],")
        log("")

log("=" * 60)
log("Copy the DEVICE_MONITOR entries above into plugin.py,")
log("then reload the plugin: Plugins > Sensor Monitor > Reload Plugin")
log("=" * 60)
