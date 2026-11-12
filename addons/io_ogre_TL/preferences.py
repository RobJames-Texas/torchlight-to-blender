import bpy


def _update_ogre_path(self, context):
    """Update the CONFIG dictionary with the new path."""
    # Import config module to access CONFIG
    from . import config

    tag = 'OGRETOOLS_XML_CONVERTER'
    value = getattr(self, 'ogre_xml_converter')

    # Update CONFIG with the new value
    if value and value.strip():
        config.CONFIG[tag] = value
    else:
        # If empty, remove from CONFIG to allow fallback to defaults
        if tag in config.CONFIG:
            del config.CONFIG[tag]

    # Save the configuration
    config.save_config(context)


class OgreTlAddonPreferences(bpy.types.AddonPreferences):
    """Extension preferences for Torchlight OGRE plugin"""

    bl_idname = __package__

    ogre_xml_converter: bpy.props.StringProperty(
        name="OGRE XML Converter",
        description="Path to OgreXMLConverter.exe executable",
        default="",
        update=_update_ogre_path,
        subtype='FILE_PATH'
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Extension Settings:")

        box = layout.box()
        box.prop(self, "ogre_xml_converter")

        # Add a note about the path
        box.label(text="Enter full path to OgreXmlConverter.exe")
