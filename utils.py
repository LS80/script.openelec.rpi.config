############################################################################
#
#  Copyright 2013 Lee Smith
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
############################################################################
from __future__ import division

import os
import sys
import re
from contextlib import contextmanager
import subprocess
import tempfile
import traceback

import xbmc, xbmcgui, xbmcaddon

OVERCLOCK_PRESET_PROPERTIES = ('arm_freq',
                               'core_freq',
                               'sdram_freq',
                               'over_voltage',
                               'over_voltage_sdram')

OVERCLOCK_PRESETS = {'Disabled': (None, None, None, None, None),
                     'Modest'  : ( 800,  300,  400,    0,    0),
                     'Medium'  : ( 900,  333,  450,    2,    0),
                     'High'    : ( 950,  450,  450,    6,    0),
                     'Turbo'   : (1000,  500,  500,    6,    0)}

OTHER_PROPERTIES = ('force_turbo',
                    'initial_turbo',
                    'gpu_mem_256',
                    'gpu_mem_512',
                    'gpu_mem_1024',
                    'hdmi_force_hotplug',
                    'hdmi_drive',
                    'hdmi_force_edid_audio',
                    'hdmi_pixel_encoding',
                    'hdmi_ignore_hotplug',
                    'hdmi_edid_file',
                    'config_hdmi_boost',
                    'sdtv_mode',
                    'sdtv_aspect',
                    'disable_overscan',
                    'overscan_scale',
                    'overscan_left',
                    'overscan_right',
                    'overscan_top',
                    'overscan_bottom',
                    'decode_MPG2',
                    'decode_WVC1',
                    'hdmi_ignore_cec',
                    'hdmi_ignore_cec_init',
                    'disable_splash',
                    'max_usb_current')

CONFIG_PROPERTIES = OVERCLOCK_PRESET_PROPERTIES + OTHER_PROPERTIES
    
CONFIG_PATH = '/flash/config.txt'

CONFIG_RE_STR = r'[ \t]*({})[ \t]*=[ \t]*(\w+)'
CONFIG_INIT_RE_STR = '^' + CONFIG_RE_STR
CONFIG_SUB_RE_STR  = '^(#?)' + CONFIG_RE_STR

__addon__ = xbmcaddon.Addon()

ADDON_NAME = __addon__.getAddonInfo('name')

def log(txt, level=xbmc.LOGDEBUG):
    if not (__addon__.getSetting('debug') == 'false' and level == xbmc.LOGDEBUG):
        msg = '{} v{}: {}'.format(ADDON_NAME,
                                  __addon__.getAddonInfo('version'), txt)
        xbmc.log(msg, level)
        
def log_exception():
    log("".join(traceback.format_exception(*sys.exc_info())), xbmc.LOGERROR)
    
def read_error(path, msg):
    log_exception()
    xbmcgui.Dialog().ok("{} Read Error".format(ADDON_NAME), msg,
                        "Unable to read {}.".format(path))
    
def write_error(path, msg):
    log_exception()
    xbmcgui.Dialog().ok("{} Write Error".format(ADDON_NAME), msg,
                        "Unable to write {}.".format(path))

def set_property_setting(name, value):
    __addon__.setSetting(name, str(value))

def get_setting(name):
    return __addon__.getSetting(name)

def get_property_setting(name):
    setting = get_setting(name)
    if setting == "":
        return None
    elif setting in ("true", "false"):
        return int(setting == "true")  # boolean (0|1)
    else:
        try:
            value = int(setting)
        except ValueError:
            value = setting.strip()
    return value

def get_config_value(config_txt, prop):
    match = re.search(CONFIG_INIT_RE_STR.format(prop), config_txt, re.MULTILINE)
    if match:
        return match.group(2)
    else:
        return None

def maybe_init_settings():
    if os.path.isfile(CONFIG_PATH):
        log("Initialising settings from {}".format(CONFIG_PATH))
        with open(CONFIG_PATH, 'r') as f:
            config_txt = f.read()

        for prop in CONFIG_PROPERTIES:
            value = get_config_value(config_txt, prop)
            if value is not None:
                setting_value = get_property_setting(prop)
                if value != str(setting_value):
                    set_property_setting(prop, value)
                log("{}={}".format(prop, value))
            else:
                log("{} not set".format(prop))

        # if only gpu_mem is set then use that
        gpu_mem = get_config_value(config_txt, 'gpu_mem')
        if gpu_mem is not None:
            for prop in ('gpu_mem_256', 'gpu_mem_512', 'gpu_mem_1024'):
                value = get_config_value(config_txt, prop)
                if value is None:
                    log("{}={}={}".format(prop, 'gpu_mem', gpu_mem))
                    set_property_setting(prop, gpu_mem)
    else:
        log("{} not found".format(CONFIG_PATH))

def get_arch():
    try:
        arch = open('/etc/arch').read().rstrip()
    except IOError:
        arch = 'RPi.arm'

    # just to help with testing
    if arch.startswith('Virtual'):
        arch = 'RPi.arm'
    
    return arch

def read_revision():
    with open('/proc/cpuinfo') as cpuinfo:
        m = re.search('^Revision\t: ([0-9a-f]+)', cpuinfo.read(), re.M)
        if m:
            return int(m.group(1), 16)
        else:
            return None

def get_scheme(revision):
    return (revision & 0x800000) >> 23

def get_revision():
    rev = read_revision()
    if rev:
        scheme = get_scheme(rev)
        if scheme == 0:
            return rev & 0xFFFF # last 4 hex digits
        else:
            return None
    else:
        return None

def get_type():
    rev = read_revision()
    if rev:
        scheme = get_scheme(rev)
        if scheme == 0:
            return None
        else:
            return (rev & 0xFF0) >> 4
    else:
        return None

def get_max_ram():
    rev = read_revision()
    if rev:
        if get_scheme(rev) == 1:
            return 2 ** (((rev & 0x700000) >> 20) + 8)

    r = re.compile('[a-z]+=(\d+)M')
    mb=0
    for mem in ("arm", "gpu"):
        output = subprocess.check_output(["vcgencmd", "get_mem", mem]).decode()
        mb += int(r.match(output).group(1))
    return mb

def mount_readwrite():
    log("Remounting /flash for read/write")
    subprocess.call(['mount', '-o', 'rw,remount', '/flash'])

def mount_readonly():
    log("Remounting /flash for read only")
    subprocess.call(['mount', '-o', 'ro,remount', '/flash'])

def dump_edid():
    log("Dumping edid to /flash/edit.dat")
    subprocess.call(['tvservice', '-d', '/flash/edid.dat'])

@contextmanager
def remount():
    mount_readwrite()
    try:
        yield
    finally:
        mount_readonly()
      
@contextmanager
def busy():  
    xbmc.executebuiltin("ActivateWindow(busydialog)")
    try:
        yield
    finally:
        xbmc.executebuiltin("Dialog.Close(busydialog)")

def property_value_str(prop, value):
    return "  {}={}".format(prop, value)

def commented_property_value_str(prop, value):
    return "# {}={}".format(prop, value)

def add_property_values(d, s=""):
    for prop, value in d.iteritems():
        if value is not None:
            s += property_value_str(prop, value) + '\n'
    return s

def replace_value(value, m):
    return property_value_str(m.group(2), value)

def comment_out(m):
    return commented_property_value_str(m.group(2), m.group(3))

def write_config(s):
    # write to temporary file in same directory and then rename
    temp = tempfile.NamedTemporaryFile(dir=os.path.dirname(CONFIG_PATH), delete=False)
    log("Writing config to {}".format(temp.name))
    temp.write(s)
    temp.flush()
    os.fsync(temp.fileno())
    temp.close()
    log("Renaming {} to {}".format(temp.name, CONFIG_PATH))
    os.rename(temp.name, CONFIG_PATH)

def restart_countdown(message, timeout=10):
    progress = xbmcgui.DialogProgress()
    progress.create('Rebooting')
       
    restart = True
    seconds = timeout
    while seconds >= 0:
        percent = int((timeout - seconds) / timeout * 100)
        progress.update(percent, message,
                        "Rebooting{}{}...".format((seconds > 0) * " in {} second".format(seconds),
                                                  "s" * (seconds > 1)))
        xbmc.sleep(1000)
        if progress.iscanceled():
            restart = False
            break
        seconds -= 1
    progress.close()

    return restart
