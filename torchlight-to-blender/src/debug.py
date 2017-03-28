
if "bpy" in locals():
    import imp
    if "TLImport" in locals():
        imp.reload(TLImport)
    if "TLExport" in locals():
        imp.reload(TLExport)
        
import TLExport
import TLImport
import bpy

OGRE_XML_CONVERTER = "D:\stuff\Torchlight_modding\orge_tools\OgreXmlConverter.exe -q"

from bpy_extras.io_utils import (ExportHelper,
                                 ImportHelper,
                                 path_reference_mode,
                                 axis_conversion,
                                 )

def debug_save(self, context, filepath):
    
    TLExport.save(self, context, filepath, OGRE_XML_CONVERTER)       

def debug_load(self, context, filepath):
    
    TLImport.load(self, context, filepath, OGRE_XML_CONVERTER)

#TLImport.test()
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\Alchemist\\Alchemist.MESH") 
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\TL2_char_M\\HUM_M.MESH")
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\cave_floor\\cave_floor_decal_01.Mesh")
debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\box\\box.MESH")
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\Shields_04\\Shields_04.MESH")
#debug_save(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\Shields_04\\Shields_04_ex.MESH")
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\tilesets\\town1\\plants_birch_trees.Mesh")
#debug_save(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\Alchemist\\Alchemist_v263_01.MESH")
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\firegel\\gel.MESH")
#debug_save(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\firegel\\gel_expt2.MESH")
#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\TorchED2\\media\\levelSets\\town1\\menu_building_generic1e.Mesh")
#debug_save(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\exportingTests\\menu_building_generic1e_exp2")

#debug_load(0, bpy.context, "D:\\stuff\\Torchlight_modding\\org_models\\Alchemist_lite\\Alchemist.MESH")
#debug_save(0, bpy.context, "D:\stuff\Torchlight_modding\org_models\Vanquisher\Vanquisher_c2a.MESH")   