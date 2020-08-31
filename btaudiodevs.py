#!/usr/bin/env python
# Daemon to create asoundrc entries automatically, based on parts of my osmc bluetooth code by barker.

import dbus
import connman
import sys
import json
import io
import os

DEVICE_PATH = 'org.bluez.Device1'
BLUEZ_OBJECT_PATH = 'org.bluez'
ASOUNDRC = '~/.asoundrc'

bus = dbus.SystemBus()

def get_manager():
    return dbus.Interface(bus.get_object(BLUEZ_OBJECT_PATH, "/"),"org.freedesktop.DBus.ObjectManager")

def paired_speakers():
    devices = {}
    managed_objects = get_manager().GetManagedObjects()
    for path in managed_objects.keys():
        if path.startswith('/org/bluez/hci') and DEVICE_PATH in managed_objects[path].keys():
            dbus_dict = managed_objects[path][DEVICE_PATH]
            device_dict = {}
            for key in dbus_dict:
                device_dict[str(key)] = dbus_dict[key]
            if dbus_dict['Icon'] == 'audio-card' and dbus_dict['Paired'] == True:
                devices[str(device_dict['Address'])] = device_dict
    return devices

if connman.is_technology_available('bluetooth') == False:
    sys.stderr.write('No bluetooth hardware available. Exiting.\n')
    sys.exit(1)

if connman.is_technology_enabled('bluetooth') == False:
    sys.stderr.write('Bluetooth is disabled. Exiting.\n')
    sys.exit(1)

with io.open(os.path.expanduser(ASOUNDRC), "wb") as f:
    f.write('# Do not edit, automatically generated by Daemon\n\n')
    for device in sorted(paired_speakers()):
        short_mac = paired_speakers()[device]['Address'].replace(':', '-').lower()
        short_name = paired_speakers()[device]['Name'].replace(' ', '-').lower() + '-' + short_mac[-5:]
        f.write('pcm.{} {{\n'.format(short_name))
        f.write('\ttype bluealsa\n')
        f.write('\tdevice "{}"\n'.format(paired_speakers()[device]['Address']))
        f.write('\tprofile "a2dp"\n')
        f.write('\thint {{ show on description "{}" }}\n}}\n\n'.format(paired_speakers()[device]['Name']))
