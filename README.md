# torchlight-to-blender

Fork of Dusho's Torchlight to Blender import and export scripts.

I'm adding some tweaks that were requested on http://torchmodders.com/
I've Recently added a bunch of functionality from Kenshi add-on.

I don't know my way around Python very well, but I'll figure it out as I go along.


### Supported ###

  * import/export of basic meshes
  * import of skeleton
  * import/export of animations (the empty "Bind" animation is kept, because Torchlight 2 needs it)
  * import/export of vertex weights (ability to import characters and adjust rigs)
  * optional export by material to sub-mesh.
  * import/export of vertex colour (RGB)
  * import/export of vertex alpha (Uses second vertex colour layer called Alpha)
  * import/export of shape keys
  * Calculation of tangents and binormals for export
  * Toggle of edge lists during export
  * Export removes animation keyframes that do not change, to keep the XML file small

### TO DO: ###
  * Add unit tests
  * Address bugs logged against original repository
  * Refactor export as a factory pattern
  * Add support to import and export individual animations

## for Blender 5.2 and later (import and export) ##
Blender 4.x and earlier are not supported. Release v0.9.02 is the last release for Blender 2.8 and earlier. Get it from the Releases page.

### Installation ###
  * You will need to have Ogre Tools installed (Ogre .mesh to .xml and back conversion tool). Download: http://sourceforge.net/projects/ogre/files/ogre-tools/ (take version 1.6.3 for TL1 models or version 1.7.2 for TL2 models) (note: TL1 won't work with new 1.7.2 exported models)
  * Install the OgreXMLConverter to path where folders don't contain any spaces (Python script then can't find the converter and import/export will fail)
* Download the latest zip of this add on from Releases on my github page: https://github.com/RobJames-Texas/torchlight-to-blender/releases
* Start Blender, open Edit -> Preferences -> Get Extensions. Open the menu in the top right corner, choose 'Install from Disk...' and select the .zip archive
* Find the Torchlight 2 MESH format add-on in the list, and make sure it is enabled. Open its settings and set the OgreXmlConverter path.
  * Now you should have options in File -> Import and File -> Export for Torchlight OGRE (.mesh)

### Limitations ###
  * Currently animations are imported and exported from one skeleton file.

### Known Issues ###
  * imported materials will loose certain informations not applicable to Blender when exported
