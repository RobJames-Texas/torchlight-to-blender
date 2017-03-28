# torchlight-to-blender

Fork of Dusho's Torchlight to Blender import and export scripts.

I'm adding some tweaks that were requested on http://torchmodders.com/

I don't know my way around Python very well, but I'll figure it out as I go along.


### Supported ###

  * import/export of basic meshes
  * import of skeleton
  * import/export of vertex weights (ability to import characters and adjust rigs)
  * optional export by material to sub-mesh.

### TO DO: ###
  * Add unit tests
  * Address bugs logged against original repository
  * Fix armature import

## for Blender 2.59, 2.62, 2.63a, 2.65a, 2.66a, 2.67a (import and export) ##
### Installation ###
  * you have to have Ogre Tools installed (Ogre .mesh to .xml and back conversion tool). Download: http://sourceforge.net/projects/ogre/files/ogre-tools/ (take version 1.6.3 for TL1 models or version 1.7.2 for TL2 models) (note: TL1 won't work with new 1.7.2 exported models)
  * install the OgreXMLConverter to path where folders don't contain any spaces (Python script then can't find the converter and import/export will fail)
  * download zipped scripts (from http://code.google.com/p/torchlight-to-blender/downloads/list) and unzip into <Blender folder>\2.xx\scripts\addons\
  * open `__init__.py` as a text file and find string OGRE\_XML\_CONVERTER, put there path to your XML converter executable (from Ogre tools), e.g.:
```
OGRE_XML_CONVERTER = "C:\OgreCommandLineTools\OgreXmlConverter.exe"
```
  * start Blender, in menu File->User preferences... , select Add-Ons, choose Import-Export category, scroll down and check 'Import-Export: Torchlight MESH format', close it
  * if for some reason check-box is not getting enabled for you, choose 'Install Add-On' option and point it to .zip archive (remember to update the OgreXmlConverter path)
  * you can choose File->Save User Settings to keep add-on on
  * now you should have options in Import and Export for Torchlight MESH

### Limitations ###
  * export of the skeleton not possible yet
  * can't import/export animations
  * Blender 2.64 (2.64a): because of bug when dealing with DDS textures, this version will show textures in 3D view in wrong way (workaround is to convert all textures to .png before importing to Blender 2.64)
  * Blender 2.66: bug in 3D view where textures (DDS format) can't be viewed in texture mode (no workaround, is fixed in Blender 2.67a)

### Known Issues ###
  * imported materials will loose certain informations not applicable to Blender when exported
  * imported skeleton has the bones rolled funny

## for Blender 2.49b (import only) ##

### Installation ###
  * you have to have Ogre Tool installed (Ogre .mesh to .xml and back conversion tool). Download: http://sourceforge.net/projects/ogre/files/ogre-tools/ (take version 1.6.3 for TL1 & TL2 models or version 1.7.2 for purely TL2 models)
  * install the OgreXMLConverter to path where folders don't contain any spaces (Python script then can't find the converter and import/export will fail)
  * also to make script work, you should have python 2.6.x installed (http://www.python.org/getit/releases/2.6.4/)
  * download TL import script from 'Downloads' section.
  * unzip the file into your **.blender\scripts\** folder.
  * inside the script look for lines (line 61):
```
# here place path to your OgreXmlConverter
ogreXMLConverter = "C:\OgreCommandLineTools\OgreXmlConverter.exe -q"
```
  * and set there path to your installed OgreXmlConverter.
  * start Blender and use File->Import->OGRE for Torchlight to import your .mesh file.

