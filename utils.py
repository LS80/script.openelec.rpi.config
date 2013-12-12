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

OVERCLOCK_PRESETS = {'Modest': ( 800, 300, 400, 0, 0),
                     'Medium': ( 900, 333, 450, 2, 0),
                     'High'  : ( 950, 450, 450, 6, 0),
                     'Turbo' : (1000, 500, 500, 6, 0)}

OTHER_PROPERTIES = ('force_turbo',
                    'initial_turbo',
                    'gpu_mem',
                    'hdmi_force_hotplug',
                    'hdmi_drive',
                    'hdmi_force_edid_audio',
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
                    'disable_splash')

CONFIG_PROPERTIES = OVERCLOCK_PRESET_PROPERTIES + OTHER_PROPERTIES
    
CONFIG_PATH = '/flash/config.txt'

CONFIG_RE_STR = r'[ \t]*({})[ \t]*=[ \t]*(\w+)'
CONFIG_INIT_RE_STR = '^' + CONFIG_RE_STR
CONFIG_SUB_RE_STR  = '^(#?)' + CONFIG_RE_STR

__addon__ = xbmcaddon.Addon("script.openelec.rpi.config")

ADDON_NAME = "OpenELEC RPi Config"

def log(txt, level=xbmc.LOGDEBUG):
    if not (__addon__.getSetting('debug') == 'false' and level == xbmc.LOGDEBUG):
        msg = '{} v{}: {}'.format(__addon__.getAddonInfo('name'),
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
    __addon__.setSetting(name, value)

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

def maybe_init_settings():
    if os.path.isfile(CONFIG_PATH):
        log("Initialising settings from {}".format(CONFIG_PATH))
        with open(CONFIG_PATH, 'r') as f:
            config_txt = f.read()

        for prop in CONFIG_PROPERTIES:
            match = re.search(CONFIG_INIT_RE_STR.format(prop), config_txt, re.MULTILINE)
            if match:
                setting_value = get_property_setting(prop)
                value = match.group(2)
                if value != str(setting_value):
                    set_property_setting(prop, value)
                log("{}={}".format(prop, value))
            else:
                log("{} not set".format(prop))
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

def mount_readwrite():
    log("Remounting /flash for read/write")
    subprocess.call(['mount', '-o', 'rw,remount', '/flash'])

def mount_readonly():
    log("Remounting /flash for read only")
    subprocess.call(['mount', '-o', 'ro,remount', '/flash'])

@contextmanager
def remount():
    mount_readwrite()
    try:
        yield
    finally:
        mount_readonly()

def property_value_str(prop, value):
    return "  {}={}".format(prop, value)

def add_property_values(d, s=""):
    for prop, value in d.iteritems():
        s += property_value_str(prop, value) + '\n'
    return s

def replace(value, m):
    return property_value_str(m.group(2), value)

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
        progress.update(int((timeout - seconds) / timeout * 100),
                        message,
                        "Rebooting{}{}...".format((seconds > 0) * " in {} second".format(seconds),
                                                  "s" * (seconds > 1)))
        xbmc.sleep(1000)
        if progress.iscanceled():
            restart = False
            break
        seconds -= 1
    progress.close()

    return restart
