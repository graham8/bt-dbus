#!/usr/bin/env python
# Daemon to create asoundrc entries automatically, based on parts of my osmc bluetooth code by barker.

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import dbus
import connman
import sys
import json
import io
import os

DEVICE_PATH = 'org.bluez.Device1'
BLUEZ_OBJECT_PATH = 'org.bluez'
ASOUNDRC = '~/asoundrc-py'

bus = dbus.SystemBus()

service_classes = ('Limited discoverable','reserved','reserved','Positioning','Networking','Rendering',
        'Capturing','Object Transfer','Audio','Telephony','Information')

major_devices = ('Miscellaneous','Computer','Phone','LAN/AP','Audio/Video','Peripheral','Imaging','Wearable','Toy','Health')

minor_devices_computer = ('Uncategorised','Desktop','Server','Laptop','Handheld clamshell','Palm-size','Wearable','Tablet')

minor_devices_phone = ('Uncategorised','Cellular','Cordless','Smartphone','Wired modem or voice gateway','Common ISDN access')

minor_devices_av = ('Uncategorised','Wearable headset','Hands-free','reserved','Microphone','Loudspeaker','Headphones',
        'Portable Audio','Car Audio','Set-top box','HiFi Audio','VCR','Video Camera','Camcorder','Video Monitor',
        'Video display and loudspeaker','Video Conferencing','reserved','Gaming/Toy')

minor_devices_peripheral = ('Not Keyboard or Pointing Device','Keyboard','Pointing Device','Keyboard and Pointing Device')
minor_devices_peripheral2 = ('Uncategorised','Joystick','Gamepad','Remote control','Sensing device','Digitiser tablet',
        'Card Reader','Digital Pen','Handheld scanner','Handheld gestural input device')

def describe_class(class_num):
    class_description = []
    service_class_nums = class_num >> 13
    for i in range (0,10):
        if (service_class_nums >> i) & 1:
            class_description = class_description + [service_classes[i]]
    major_device_num = (class_num >> 8) & 31
    class_description += [major_devices[major_device_num]]
    # computer
    if major_device_num == 1:
        class_description += [minor_devices_computer[(class_num >> 2) & 63]]
    # phone
    if major_device_num == 2:
        class_description += [minor_devices_phone[(class_num >> 2) & 63]]
    # audio/video
    if major_device_num == 4:
        class_description += [minor_devices_av[(class_num >> 2) & 63]]
    # peripheral
    if major_device_num == 5:
        class_description += [minor_devices_peripheral[(class_num >> 6) & 3]]
        class_description += [minor_devices_peripheral2[(class_num >> 2) & 15]]
    return class_description

# Profile and Service Class UUIDs
UUIDs = {"1000": "Service discovery", "1101": "SPP", "1105": "OPP Obex",
        "1108": "HSP profile", "110a": "A2DP source", "110b": "A2DP sink",
        "110c": "AVRCP target", "110d": "A2DP", "110e": "AVRCP",
        "110f": "AVRCP controller", "1112": "HSP-AG", "1115": "PAN PANU",
        "1116": "PAN NAP", "112d": "SAP SIM access", "112f": "PBAP PSE",
        "1132": "MAP message access", "111e": "HFP", "111f": "HFP-AG",
        "1124": "HID", "1131": "HSP service", "1200": "DID PnP info",
        "1203": "generic audio", "1204": "generic telephony", "1800": "GAP access",
        "1801": "GAP attributes"}

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
            print('')
            if 'Name' in device_dict:
                print('Name: {}'.format(str(device_dict['Name'])))
            if 'Class' in device_dict:
                print('Device class: {}'.format(', '.join(describe_class(device_dict['Class']))))
            if 'UUIDs' in device_dict:
                for UUID in device_dict['UUIDs']:
                    UUID = UUID[4:8]
                    if UUID in UUIDs:
                        print('{}, {}'.format(str(UUID), str(UUIDs[str(UUID)])))
                    else:
                        print('{}, {}'.format(str(UUID), 'Unknown'))
                    # A2DP sink, headset or handsfree  TODO: list each as separate device
                    if (UUID == '110b' or UUID == '1108' or UUID == '111e') and dbus_dict['Paired'] == True:
                        devices[str(device_dict['Address'])] = device_dict
                        print('********Added to asoundrc********')
    return devices

if connman.is_technology_available('bluetooth') == False:
    sys.stderr.write('No bluetooth hardware available. Exiting.\n')
    sys.exit(1)

if connman.is_technology_enabled('bluetooth') == False:
    sys.stderr.write('Bluetooth is disabled. Exiting.\n')
    sys.exit(1)

with io.open(os.path.expanduser(ASOUNDRC), "wb") as f:
    f.write('# Do not edit, automatically generated by Daemon\n\n')
    paired_speakers = paired_speakers()
    for device in sorted(paired_speakers):
        short_mac = paired_speakers[device]['Address'].replace(':', '-').lower()
        short_name = paired_speakers[device]['Name'].replace(' ', '-').lower() + '-' + short_mac[-5:]
        f.write('pcm.{} {{\n'.format(short_name))
        f.write('\ttype bluealsa\n')
        f.write('\tdevice "{}"\n'.format(paired_speakers[device]['Address']))
        f.write('\tprofile "a2dp"\n')
        f.write('\thint {{ show on description "{}" }}\n}}\n\n'.format(paired_speakers[device]['Name']))
