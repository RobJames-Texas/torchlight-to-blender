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
  * import of individual animation files (Import > Torchlight Animation (.skeleton)) for the selected armature
  * export in the Torchlight 2 layout: the main skeleton has only the empty "Bind" animation, and each action goes to its own .SKELETON file
  * export of animations only (Export > Torchlight Animation (.skeleton)), for all actions, the active action, or the selected NLA tracks
  * export sample rate of 30 fps or the scene rate
  * optional update of the .ANIMATION file: it adds entries only, and it makes a backup first

### TO DO: ###
  * Add unit tests
  * Address bugs logged against original repository
  * Refactor export as a factory pattern

## for Blender 5.2 and later (import and export) ##
Blender 4.x and earlier are not supported. Release v0.9.02 is the last release for Blender 2.8 and earlier. Get it from the Releases page.

### Installation ###
  * You will need to have Ogre Tools installed (Ogre .mesh to .xml and back conversion tool). Download: http://sourceforge.net/projects/ogre/files/ogre-tools/ (take version 1.6.3 for TL1 models or version 1.7.2 for TL2 models) (note: TL1 won't work with new 1.7.2 exported models)
  * Install the OgreXMLConverter to path where folders don't contain any spaces (Python script then can't find the converter and import/export will fail)
* Download the latest zip of this add on from Releases on my github page: https://github.com/RobJames-Texas/torchlight-to-blender/releases
* Start Blender, open Edit -> Preferences -> Get Extensions. Open the menu in the top right corner, choose 'Install from Disk...' and select the .zip archive
* Find the Torchlight 2 MESH format add-on in the list, and make sure it is enabled. Open its settings and set the OgreXmlConverter path.
  * Now you should have options in File -> Import and File -> Export for Torchlight OGRE (.mesh)

### Animations ###
Torchlight 2 keeps each animation in its own .SKELETON file. The main skeleton file has only the empty "Bind" animation.
  * Import the mesh first. Then select the armature and use Import > Torchlight Animation (.skeleton). You can select many files.
  * Each animation file has its own rest pose for each bone. The add-on stores the rest pose of each bone when it imports the mesh. Import the mesh again if the armature came from an older version of the add-on.
  * Use the same bone sorting for the mesh and for the animation files. The bone IDs must be the same.
  * In the mesh export, set "Animation files" to "Torchlight 2 layout" to write one .SKELETON file for each action. "Single file" writes all animations in the skeleton file.
  * Animation files are written at 30 fps by default. An animation made at a higher rate loses detail. Set "Sample rate" to "Scene rate" to keep it.
  * "Update .ANIMATION file" adds an entry for each exported animation that has none. It does not change an existing entry. It does not make [KEY] events. Add the events by hand.

### Known Issues ###
  * imported materials will loose certain informations not applicable to Blender when exported
