#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    find_contact_sensors.py
# Description: Discovery script - finds all likely contact/door/window sensors in Indigo
#              Paste into Indigo Script Editor and run once to identify device IDs.
# Author:      CliveS & Claude Sonnet 4.6
# Date:        27-02-2026
# Version:     1.3

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
CONTACT_KEYWORDS = [
    "contact", "door", "window", "entry", "gate", "patio", "garage"
]

# State names used by contact/door/window sensors
CONTACT_STATES = {"contact", "doorSensor", "windowSensor"}

# Keywords that suggest a motion/occupancy/presence sensor by device name
MOTION_KEYWORDS = [
    "motion", "pir", "presence", "occupancy", "mmwave", "radar"
]

# State names used by motion/occupancy/presence sensors
MOTION_STATES = {"occupancy", "pirDetection", "presence", "motion", "motionDetected"}


def get_folder(dev):
    try:
        if dev.folderId and dev.folderId in indigo.devices.folders:
            return indigo.devices.folders[dev.folderId].name
    except Exception:
        pass
    return "(root)"


log("=" * 60)
log("Sensor Monitor - Contact & Motion Sensor Discovery")
log("=" * 60)

contact_found = []
motion_found  = []

for dev in indigo.devices:
    dev_name_lower = dev.name.lower()
    dev_states     = list(dev.states.keys()) if hasattr(dev, "states") else []
    has_onstate    = hasattr(dev, "onState")

    # --- Contact sensor detection ---
    # Motion keyword in name takes priority: 'Front Door Motion' -> motion, not contact
    contact_state_match = bool(CONTACT_STATES & set(dev_states))
    contact_name_match  = any(kw in dev_name_lower for kw in CONTACT_KEYWORDS)
    motion_name_match   = any(kw in dev_name_lower for kw in MOTION_KEYWORDS)
    is_contact = contact_state_match or (contact_name_match and not motion_name_match and has_onstate)

    # --- Motion sensor detection (not already flagged as contact) ---
    motion_state_match = bool(MOTION_STATES & set(dev_states))
    is_motion = (not is_contact) and (motion_state_match or (motion_name_match and has_onstate))

    if is_contact:
        contact_found.append({
            "id":      dev.id,
            "name":    dev.name,
            "states":  dev_states,
            "folder":  get_folder(dev),
            "onstate": dev.onState if has_onstate else "N/A",
        })
    elif is_motion:
        mot_states = sorted(s for s in MOTION_STATES if s in dev_states)
        if not mot_states:
            mot_states = ["onState"]
        motion_found.append({
            "id":         dev.id,
            "name":       dev.name,
            "states":     dev_states,
            "mot_states": mot_states,
            "folder":     get_folder(dev),
            "onstate":    dev.onState if has_onstate else "N/A",
        })

if not contact_found and not motion_found:
    log("No contact or motion sensors found.")
    log("Expand CONTACT_KEYWORDS or MOTION_KEYWORDS at the top of this script.")
else:
    if contact_found:
        log(f"Contact / Door / Window sensors: {len(contact_found)}")
        log("")
        for d in sorted(contact_found, key=lambda x: x["name"]):
            log(f"  Name   : {d['name']}")
            log(f"  ID     : {d['id']}")
            log(f"  Folder : {d['folder']}")
            if "contact" in d["states"]:
                log(f"  -> state: 'contact'  (zigbee2mqtt: True=CLOSED, False=OPEN)")
                log(f"     Config entry:")
                log(f"     {{\"id\": {d['id']}, \"name\": \"{d['name']}\", "
                    f"\"state\": \"contact\", \"label\": \"{d['name']}\", "
                    f"\"on_text\": \"CLOSED\", \"off_text\": \"OPEN\"}}")
            else:
                log(f"  -> state: 'onState'  (True=OPEN, False=CLOSED)")
                log(f"     Config entry:")
                log(f"     {{\"id\": {d['id']}, \"name\": \"{d['name']}\", "
                    f"\"state\": \"onState\", \"label\": \"{d['name']}\", "
                    f"\"on_text\": \"OPEN\", \"off_text\": \"CLOSED\"}}")
            log("")
        log("")

    if motion_found:
        log(f"Motion / Occupancy / Presence sensors: {len(motion_found)}")
        log("")
        for d in sorted(motion_found, key=lambda x: x["name"]):
            log(f"  Name   : {d['name']}")
            log(f"  ID     : {d['id']}")
            log(f"  Folder : {d['folder']}")
            log(f"  States : {d['mot_states']}")
            log(f"  Config entries (one per state):")
            for state_name in d["mot_states"]:
                log(f"     {{\"id\": {d['id']}, \"name\": \"{d['name']}\", "
                    f"\"state\": \"{state_name}\", \"label\": \"{d['name']}\", "
                    f"\"on_text\": \"ON\", \"off_text\": \"OFF\"}}")
            log("")
        log("")

log("=" * 60)
log("Paste the config entries above into sensor_monitor_config.json")
log("then reload: Plugins > Sensor Monitor > Reload Plugin")
log("=" * 60)
