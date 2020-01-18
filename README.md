# torchlight-to-blender

Fork of Dusho's Torchlight to Blender import and export scripts.

I'm adding some tweaks that were requested on http://torchmodders.com/
I've Recently added a bunch of functionality from Kenshi add-on.

I don't know my way around Python very well, but I'll figure it out as I go along.


### Supported ###

  * import/export of basic meshes
  * import of skeleton
  * import/export of animations
  * import/export of vertex weights (ability to import characters and adjust rigs)
  * optional export by material to sub-mesh.
  * import/export of vertex colour (RGB)
  * import/export of vertex alpha (Uses second vertex colour layer called Alpha)
  * import/export of shape keys
  * Calculation of tangents and binormals for export
  * Toggle of edge lists during export

### TO DO: ###
  * Add unit tests
  * Address bugs logged against original repository
  * Refactor export as a factory pattern
  * Add support to import and export individual animations

## for Blender 2.63a, 2.65a, 2.66a, 2.67a, 2.79b (import and export) ##
### Installation ###
  * you have to have Ogre Tools installed (Ogre .mesh to .xml and back conversion tool). Download: http://sourceforge.net/projects/ogre/files/ogre-tools/ (take version 1.6.3 for TL1 models or version 1.7.2 for TL2 models) (note: TL1 won't work with new 1.7.2 exported models)
  * install the OgreXMLConverter to path where folders don't contain any spaces (Python script then can't find the converter and import/export will fail)
* download the latest zip of this add on from Releases on my github page: https://github.com/RobJames-Texas/torchlight-to-blender/releases
* start Blender, in menu File->User preferences... , select Add-Ons, choose 'Install Add-On' option and point it to .zip archive
* find the Import-Export: Torchlight 2 MESH format add on, and check the box next to it to enable it. Remember to update the OgreXmlConverter path.
  * you can choose File->Save User Settings to keep add-on on
  * now you should have options in Import and Export for Torchlight MESH

### Limitations ###
  * Blender 2.64 (2.64a): because of bug when dealing with DDS textures, this version will show textures in 3D view in wrong way (workaround is to convert all textures to .png before importing to Blender 2.64)
  * Blender 2.66: bug in 3D view where textures (DDS format) can't be viewed in texture mode (no workaround, is fixed in Blender 2.67a)
  * Currently animations are imported and exported from one skeleton file.

### Known Issues ###
  * imported materials will loose certain informations not applicable to Blender when exported
