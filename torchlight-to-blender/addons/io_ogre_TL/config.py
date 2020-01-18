import bpy, os, sys, logging, pickle, mathutils
from pprint import pprint
from bpy.props import *

# Most of this borrowed from OgreCave blender2ogre addon.

CONFIG_PATH = bpy.utils.user_resource('CONFIG', path='scripts', create=True)
CONFIG_FILENAME = 'io_ogre_TL.pickle'
CONFIG_FILEPATH = os.path.join(CONFIG_PATH, CONFIG_FILENAME)

_CONFIG_DEFAULTS_ALL = {
}

_CONFIG_TAGS_ = 'OGRETOOLS_XML_CONVERTER'.split()

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
if sys.platform.startswith('linux') or sys.platform.startswith('darwin') or sys.platform.startswith('freebsd'):
    for tag in _CONFIG_DEFAULTS_UNIX:
        path = _CONFIG_DEFAULTS_UNIX[tag]
        if path.startswith('~'):
            _CONFIG_DEFAULTS_UNIX[tag] = os.path.expanduser(path)
        elif tag.startswith('OGRETOOLS') and not os.path.isfile(path):
            _CONFIG_DEFAULTS_UNIX[tag] = os.path.join('/usr/bin', os.path.split(path)[-1])
    del tag
    del path

# PUBLIC API continues


def load_config():
    config_dict = {}

    if os.path.isfile(CONFIG_FILEPATH):
        try:
            with open(CONFIG_FILEPATH, 'rb') as f:
                config_dict = pickle.load(f)
        except:
            print('[ERROR]: Can not read config from %s' % CONFIG_FILEPATH)

    for tag in _CONFIG_DEFAULTS_ALL:
        if tag not in config_dict:
            config_dict[tag] = _CONFIG_DEFAULTS_ALL[tag]

    for tag in _CONFIG_TAGS_:
        if tag not in config_dict:
            if sys.platform.startswith('win'):
                config_dict[tag] = _CONFIG_DEFAULTS_WINDOWS[tag]
            elif sys.platform.startswith('linux') or sys.platform.startswith('darwin') or sys.platform.startswith('freebsd'):
                config_dict[tag] = _CONFIG_DEFAULTS_UNIX[tag]
            else:
                print('ERROR: unknown platform')
                assert 0

    # Setup temp hidden RNA to expose the file paths
    for tag in _CONFIG_TAGS_:
        default = config_dict[tag]
        func = lambda self, con: config_dict.update({tag: getattr(self, tag, default)})
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
            print("trying to set CONFIG['%s']=%s, but is not a known config setting" % (k, v))
        CONFIG[k] = v
    save_config()


def save_config():
    global CONFIG
    # for key in CONFIG: print( '%s =   %s' %(key, CONFIG[key]) )
    if os.path.isdir(CONFIG_PATH):
        try:
            with open(CONFIG_FILEPATH, 'wb') as f:
                pickle.dump(CONFIG, f, -1)
        except:
            print('[ERROR]: Can not write to %s' % CONFIG_FILEPATH)
    else:
        print('[ERROR:] Config directory does not exist %s' % CONFIG_PATH)


def update_from_addon_preference(context):
    addon_preferences = context.user_preferences.addons["io_ogre_TL"].preferences

    for key in _CONFIG_TAGS_:
        addon_pref_value = getattr(addon_preferences, key, None)
        if addon_pref_value is not None:
            CONFIG[key] = addon_pref_value
