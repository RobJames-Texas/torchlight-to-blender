import bpy
import os
import sys
import logging
import pickle
import mathutils
from pprint import pprint
from bpy.props import *

# Most of this borrowed from OgreCave blender2ogre addon.

CONFIG_PATH = bpy.utils.user_resource('CONFIG', path='scripts', create=True)
CONFIG_FILENAME = 'io_ogre_TL.pickle'
CONFIG_FILEPATH = os.path.join(CONFIG_PATH, CONFIG_FILENAME)

_CONFIG_DEFAULTS_ALL = {
}

_CONFIG_TAGS_ = 'OGRETOOLS_XML_CONVERTER'.split()

# Maps CONFIG tags to the matching property names on OgreTlAddonPreferences.
_PREF_PROP_NAMES = {
    'OGRETOOLS_XML_CONVERTER': 'ogre_xml_converter',
}

_CONFIG_DEFAULTS_WINDOWS = {
    'OGRETOOLS_XML_CONVERTER': 'C:\\OgreCommandLineTools\\OgreXmlConverter.exe'
}

_CONFIG_DEFAULTS_UNIX = {
    # do not use absolute paths like /usr/bin/exe_name.
    # some distris install to /usr/local/bin ...
    # just trust the env PATH variable
    'OGRETOOLS_XML_CONVERTER': 'OgreXMLConverter'
}

# Unix: Replace ~ with absolute home dir path
if sys.platform.startswith('linux') or sys.platform.startswith('darwin') \
                                    or sys.platform.startswith('freebsd'):
    for tag in _CONFIG_DEFAULTS_UNIX:
        path = _CONFIG_DEFAULTS_UNIX[tag]
        if path.startswith('~'):
            _CONFIG_DEFAULTS_UNIX[tag] = os.path.expanduser(path)
        elif tag.startswith('OGRETOOLS') and not os.path.isfile(path):
            _CONFIG_DEFAULTS_UNIX[tag] = os.path.join(
                '/usr/bin', os.path.split(path)[-1])
    del tag
    del path

# PUBLIC API continues


def load_config():
    config_dict = {}

    if os.path.isfile(CONFIG_FILEPATH):
        try:
            with open(CONFIG_FILEPATH, 'rb') as f:
                config_dict = pickle.load(f)
        except Exception:
            print('[ERROR]: Can not read config from %s' % CONFIG_FILEPATH)

    for tag in _CONFIG_DEFAULTS_ALL:
        if tag not in config_dict:
            config_dict[tag] = _CONFIG_DEFAULTS_ALL[tag]

    for tag in _CONFIG_TAGS_:
        if tag not in config_dict:
            if sys.platform.startswith('win'):
                config_dict[tag] = _CONFIG_DEFAULTS_WINDOWS[tag]
            elif sys.platform.startswith('linux') \
                or sys.platform.startswith('darwin') \
                    or sys.platform.startswith('freebsd'):
                config_dict[tag] = _CONFIG_DEFAULTS_UNIX[tag]
            else:
                print('ERROR: unknown platform')
                assert 0

    # Setup temp hidden RNA to expose the file paths
    for tag in _CONFIG_TAGS_:
        default = config_dict[tag]
        def func(self, con): return config_dict.update(
            {tag: getattr(self, tag, default)})
        if type(default) is bool:
            prop = BoolProperty(name=tag,
                                description='updates bool setting',
                                default=default,
                                options={'SKIP_SAVE'},
                                update=func)
        else:
            prop = StringProperty(name=tag,
                                  description='updates path setting',
                                  maxlen=128,
                                  default=default,
                                  options={'SKIP_SAVE'},
                                  update=func)
        setattr(bpy.types.WindowManager, tag, prop)

    return config_dict


CONFIG = load_config()


def get(name, default=None):
    global CONFIG
    if name in CONFIG:
        return CONFIG[name]
    return default


def update(**kwargs):
    for k, v in kwargs.items():
        if k not in _CONFIG_DEFAULTS_ALL:
            print(
                "trying to set CONFIG['%s']=%s, but is not a known"
                " config setting" % (k, v))
        CONFIG[k] = v
    save_config()


def save_config(context=None):
    """Save config to pickle (legacy).

    For Blender 5.x the extension framework persists preferences separately.
    Call ``sync_preferences_to_config(context)`` after loading prefs and
    ``save_config(bpy.context)`` whenever you want config synced back into
    extension preferences.
    """
    global CONFIG
    if os.path.isdir(CONFIG_PATH):
        try:
            with open(CONFIG_FILEPATH, 'wb') as f:
                pickle.dump(CONFIG, f, -1)
        except Exception:
            print('[ERROR]: Can not write to %s' % CONFIG_FILEPATH)
    else:
        print('[ERROR:] Config directory does not exist %s' % CONFIG_PATH)


def get_preferences(context=None):
    """Get extension preferences (Blender 5.x+)"""
    if not context:
        context = bpy.context
    prefs = None
    if hasattr(context, "preferences"):
        prefs = context.preferences.addons.get(__package__, None)
    return prefs.preferences if prefs else None


def sync_preferences_to_config(context=None):
    """Sync extension preferences → CONFIG dict.

    Call after addon preferences are loaded (e.g. during registration).
    Only overwrites CONFIG when a non-empty value exists in the UI —
    allows users to explicitly clear a custom path and fall back to
    platform defaults by entering an empty string.
    """
    if context is None:
        context = bpy.context
    addon_preferences = get_preferences(context)
    if addon_preferences is None:
        return

    for key in _CONFIG_TAGS_:
        prop_name = _PREF_PROP_NAMES[key]
        pref_value = getattr(addon_preferences, prop_name, None)
        if pref_value is not None and pref_value != "":
            CONFIG[key] = pref_value


def config_to_preferences(context=None):
    """Sync CONFIG dict → extension preferences (for migration)."""
    if context is None:
        context = bpy.context
    addon_preferences = get_preferences(context)
    if addon_preferences is None:
        return

    for key in _CONFIG_TAGS_:
        prop_name = _PREF_PROP_NAMES[key]
        value = CONFIG.get(key, '')
        setattr(addon_preferences, prop_name, value)


def migrate_preferences(context=None):
    """Migrate old pickle-based config → extension preferences.

    Called during addon registration. If the user has a legacy pickle file
    with a custom OgreXmlConverter path, that value is written into the new
    Blender 5.x extension preferences so it persists across restarts.
    Also writes platform defaults when no custom path exists anywhere.
    """
    if context is None:
        context = bpy.context

    addon_preferences = get_preferences(context)
    if addon_preferences is None:
        return

    # Determine which source to use (pickle > platform default)
    for key in _CONFIG_TAGS_:
        prop_name = _PREF_PROP_NAMES[key]
        # If user has already set a value via extension prefs, don't overwrite
        current = getattr(addon_preferences, prop_name, None)
        if current is not None and current != "":
            continue  # skip — already configured
        # Use config.py's resolved value (pickle or platform default)
        value = CONFIG.get(key, '')
        setattr(addon_preferences, prop_name, value)

    # Also update pickle with any extension pref values for backwards compat
    save_config(context)
