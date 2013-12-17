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
from collections import OrderedDict
from functools import partial

import xbmc, xbmcgui

import utils

ARCH = utils.get_arch()

if ARCH != 'RPi.arm':
    sys.exit(1)


class Main(object):
    def __init__(self):
        utils.log("Started service")
        try:          
            utils.maybe_init_settings()
        except IOError:
            utils.log_exception()

        self.monitor = MyMonitor(updated_settings_callback=self.apply_config)
        
        while (not xbmc.abortRequested):
            xbmc.sleep(1000)

    def apply_config(self):
        utils.log("Applying settings to {}".format(utils.CONFIG_PATH))
        config = OrderedDict()

        overclock_preset = utils.get_setting('overclock_preset')
        utils.log("Using {} overclock settings".format(overclock_preset))
        if overclock_preset == 'Custom':
            for prop in utils.OVERCLOCK_PRESET_PROPERTIES:
                config[prop] = utils.get_property_setting(prop)
        elif overclock_preset in utils.OVERCLOCK_PRESETS:
            config = OrderedDict(zip(utils.OVERCLOCK_PRESET_PROPERTIES,
                                     utils.OVERCLOCK_PRESETS[overclock_preset]))

        for prop in utils.OTHER_PROPERTIES:
            value = utils.get_property_setting(prop)
            if value is not None:
                config[prop] = value
                
        if config['force_turbo'] == 1 and 'over_voltage' in config and config['over_voltage'] > 0:
            if not xbmcgui.Dialog().yesno("OpenELEC RPi Config WARNING!!",
                                          "Overvolting with dynamic overclock disabled",
                                          "will void your warranty!!",
                                          "Continue, or fix by enabling dynamic overclock?",
                                          "Fix",
                                          "Continue"):
                utils.log("Enabling dynamic overclock") 
                config['force_turbo'] = 0
            else:
                utils.log("Warranty warning was ignored")

        reboot_needed = False
        if os.path.isfile(utils.CONFIG_PATH):
            with open(utils.CONFIG_PATH, 'r') as f:
                config_txt = f.read()
                
            for prop, value in config.iteritems():
                utils.log("==== {} ====".format(prop))
                config_property_re = re.compile(utils.CONFIG_SUB_RE_STR.format(prop), re.MULTILINE)
                match = config_property_re.search(config_txt)
                if match:
                    comment = bool(match.group(1))
                    old_value = match.group(3)
                    if value is None:
                        utils.log("  Commenting out")
                        config_txt = config_property_re.sub(utils.comment_out, config_txt)
                        reboot_needed = True
                    elif comment or str(value) != old_value:
                        utils.log("  Setting to {}".format(value))
                        config_txt = config_property_re.sub(partial(utils.replace_value, value), config_txt)
                        reboot_needed = True
                    else:
                        utils.log("  Unchanged")
                elif value is not None:
                    utils.log("  Appending {}={}".format(prop, value))
                    config_txt += utils.property_value_str(prop, value) + '\n'
                    reboot_needed = True
        else:
            utils.log("A new {} will be created".format(utils.CONFIG_PATH))
            config_txt = utils.add_property_values(config)
            reboot_needed = True

        with utils.remount():
            try:
                utils.write_config(config_txt)
            except (OSError, IOError) as e:
                reboot_needed = False
                utils.write_error(utils.CONFIG_PATH, str(e))
        
        if reboot_needed:
            if utils.restart_countdown("Ready to reboot to apply changes in config.txt"):
                xbmc.restart()
            else:
                utils.log("Cancelled reboot")
        else:
            utils.log("No changes made")


class MyMonitor(xbmc.Monitor):
    def __init__(self, updated_settings_callback):
        xbmc.Monitor.__init__(self)
        self.updated_settings_callback = updated_settings_callback

    def onSettingsChanged(self):
        self.updated_settings_callback()


Main()



