#!/usr/bin/env python
# Daemon to create asoundrc entries automatically, based on parts of my osmc bluetooth code by barker.

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

import dbus
import connman
import sys
import json
import io
import os
#import logging
from systemd import journal

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'
MEDIA_CTL_INTERFACE = 'org.bluez.MediaControl1'
BLUEZ_BUS_NAME = 'org.bluez'
ASOUNDRC = '~/.asoundrc'
DEBUG = True

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

def journallog(message):
    journal.send("BT audio: {}".format(message))
    # and for testing
    pr_debug(message)

def pr_debug(message):
    if DEBUG:
        print(message)

def get_managed_objects():
    bus = dbus.SystemBus()
    try:
        managed_objects =  dbus.Interface(bus.get_object(BLUEZ_BUS_NAME, "/"),"org.freedesktop.DBus.ObjectManager").GetManagedObjects()
    except dbus.DBusException:
        journallog("Failed to find " + BLUEZ_BUS_NAME)
    return managed_objects

def has_audio(managed_objects):
    has_audio = False
    for path in managed_objects.keys():
        if path.startswith('/org/bluez/hci') and ADAPTER_INTERFACE in managed_objects[path].keys():
            dbus_dict = managed_objects[path][ADAPTER_INTERFACE]
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
                    if UUID == '110a':
                        has_audio = True
                        journallog("Bluealsa a2dp source is active")
                    if UUID == '110b':
                        journallog("Bluealsa a2dp sink is active")
    if not has_audio:
        journallog("Bluetooth audio is not active")
    return has_audio

def has_audio_sink(UUIDs):
    for UUID in UUIDs:
        if UUID[4:8] == '110b':
            print("Found a2dp sink")
            return True
    return False

def is_audio_sink(object_path):
    managed_objects = get_managed_objects()
    if 'UUIDs' in managed_objects[object_path][DEVICE_INTERFACE]:
        return has_audio_sink(managed_objects[object_path][DEVICE_INTERFACE]['UUIDs'])

def is_bt_up():
    if connman.is_technology_available('bluetooth') == False:
        journallog('No bluetooth hardware available.')
        #exit()
        return False
    if connman.is_technology_enabled('bluetooth') == False:
        journallog('Bluetooth is disabled.')
        #exit()
        return False
    return True

def paired_speakers(managed_objects):
    devices = {}
    for path in managed_objects.keys():
        if path.startswith('/org/bluez/hci') and DEVICE_INTERFACE in managed_objects[path].keys():
            dbus_dict = managed_objects[path][DEVICE_INTERFACE]
            device_dict = {}
            for key in dbus_dict:
                device_dict[str(key)] = dbus_dict[key]
            journallog('BT device:')
            if 'Name' in device_dict:
                journallog('\tName: {}'.format(str(device_dict['Name'])))
            if 'Class' in device_dict:
                journallog('\tDevice class: {}'.format(', '.join(describe_class(device_dict['Class']))))
            if 'UUIDs' in device_dict:
                for UUID in device_dict['UUIDs']:
                    UUID = UUID[4:8]
                    if UUID in UUIDs:
                        pr_debug('\t{}, {}'.format(str(UUID), str(UUIDs[str(UUID)])))
                    else:
                        pr_debug('\t{}, {}'.format(str(UUID), 'Unknown'))
                    # A2DP sink, headset or handsfree  TODO: list each as separate device
                    if (UUID == '110b' or UUID == '1108' or UUID == '111e') and dbus_dict['Paired'] == True:
                        devices[str(device_dict['Address'])] = device_dict
                        journallog('\tFound UUID {}, {} - added device to conf file'.format(str(UUID), str(UUIDs[str(UUID)])))
    return devices

def write_conf_file(paired_speakers):
    if len(paired_speakers) == 0:
        journallog('No paired audio sinks found')
        del_conf_file()
        return
    try:
        with io.open(os.path.expanduser(ASOUNDRC), "w") as f:
            f.write('# Do not edit, automatically generated by Daemon\n\n')
            for device in sorted(paired_speakers):
                short_mac = paired_speakers[device]['Address'].replace(':', '-').lower()
                short_name = paired_speakers[device]['Name'].replace(' ', '-').lower() + '-' + short_mac[-5:]
                f.write('pcm.{} {{\n'.format(short_name))
                f.write('\ttype bluealsa\n')
                f.write('\tdevice "{}"\n'.format(paired_speakers[device]['Address']))
                f.write('\tprofile "a2dp"\n')
                f.write('\thint {{ show on description "{}" }}\n}}\n\n'.format(paired_speakers[device]['Name']))
        f.close()
        journallog("Devices written to " + ASOUNDRC)
    except:
        journallog("Can't open conf file " + ASOUNDRC)

def del_conf_file():
    if os.path.exists(os.path.expanduser(ASOUNDRC)):
        os.remove(os.path.expanduser(ASOUNDRC))
        journallog("Removed conf file {}".format(ASOUNDRC))
    else:
        journallog("{} not there to delete".format(ASOUNDRC))

def devices_change_handler(*args, **kwargs):
    journallog("Caught signal type " + kwargs['dbus_interface'] + "." + kwargs['member'])
    journallog("Object path " + kwargs['path'])
    pr_debug('Item:' + args[0])
    message = {}
    dbus_dict = args[1]
    #print(type(dbus_dict))
    #print(args[1])
    # deal with message that is a dictionary or nested dictionary
    if kwargs['member'] == 'PropertiesChanged' or kwargs['member'] == 'InterfacesAdded':
        for key in dbus_dict:
            message[str(key)] = dbus_dict[key]
            pr_debug('{}: {}\n'.format(str(key),message[str(key)]))
        device_parms = {}
        if kwargs['member'] == 'PropertiesChanged':
            device_parms = message
        # nested dicts when bluetooth is enabled
        elif kwargs['member'] == 'InterfacesAdded' and DEVICE_INTERFACE in message:
            device_parms = message[DEVICE_INTERFACE]
        # new device has been paired
        if 'Paired' in device_parms and device_parms['Paired'] == True:
            journallog("New device paired")
            if is_audio_sink(kwargs['path']):
                journallog("Device is audio")
                write_conf_file(paired_speakers(get_managed_objects()))
            else:
                journallog("Device is not audio")
        # if just bluealsa is started or stopped
        if args[0] == ADAPTER_INTERFACE and 'UUIDs' in message:
            if is_audio_sink(message['UUIDs']):
                write_conf_file(paired_speakers(get_managed_objects()))
            else:
                del_conf_file()
    # deal with message that's just an array aka list
    elif kwargs['member'] == 'InterfacesRemoved':
        # bluetooth disabled
        if ADAPTER_INTERFACE in dbus_dict and not has_audio(get_managed_objects()):
            del_conf_file()
            #exit()
        # audio device removed
        elif MEDIA_CTL_INTERFACE in dbus_dict:
            write_conf_file(paired_speakers(get_managed_objects()))

def main():
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    bus.add_signal_receiver(devices_change_handler, bus_name='org.bluez', signal_name='PropertiesChanged',
            interface_keyword='dbus_interface', member_keyword='member',
            path_keyword='path')
    bus.add_signal_receiver(devices_change_handler, bus_name='org.bluez', signal_name='InterfacesRemoved',
            interface_keyword='dbus_interface', member_keyword='member',
            path_keyword='path')
    bus.add_signal_receiver(devices_change_handler, bus_name='org.bluez', signal_name='InterfacesAdded',
            interface_keyword='dbus_interface', member_keyword='member',
            path_keyword='path')

    # attempt to enumerate once
    if is_bt_up() and has_audio(get_managed_objects()):
        write_conf_file(paired_speakers(get_managed_objects()))
    else:
        del_conf_file()

    loop = GLib.MainLoop()
    loop.run()

if __name__ == '__main__':
    main()
