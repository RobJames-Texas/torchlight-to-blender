#!BPY

"""
Name: 'OGRE for Torchlight (*.MESH)'
Blender: 249b
Group: 'Import'
Tooltip: 'Import Torchlight OGRE files'
	
Author: Daniel Handke (D-Man)
Changes: Dusho, Rene Lacson
"""

__author__ = "Daniel Handke & Dusho"
__version__ = "0.95 22-July-2011"

__bpydoc__ = """\
This script imports Torchlight Ogre models into Blender.

Supported:<br>
    * multiple submeshes (triangle list)
    * uvs
    * materials (textures only)
    * vertex colours	    
    * skeletons
    * animations (also with separate rest positions - skeletons)
	* only texture info from materials

Missing:<br>	
    * submeshes provided as triangle strips and triangle fans
    * materials (diffuse, ambient, specular, alpha mode, etc.)

Known issues:<br>
	* overall animation translations looks to be applied in wrong way (visible slidings of animations)
	* location difference between different skeleton in animations may be wrong
    * blender only supports a single uv set, always the first is taken
      and only the first texture unit in a material, even if it is not for
      the first uv set.
	 
History:<br>
	* v0.95 - if linked skeleton is not found, mesh is still imported, but skeleton isn't linked to mesh anymore (23-July-2011)
	* v0.94 - added check for parent when creating zero bones (was preventing some models from importing) (20-January-2011)
	* v0.93 - bone with root parent now translated in correct coordinate system (applied 'bind to action' skeleton delta may be still wrong) (16-January-2011)
	* v0.92 - fixed name truncation (10-January-2010)
	* v0.91 - added name truncating (Blender limits names to 21 chars -> shows warning when done so)
	* v0.9	- added location difference (using stored base skeleton BoneDic instead of reading Blender bone geometry)
	* v0.8	- added support for sharedgeometry (Torchlight mobs models) and texture name resolving (8-January-2011)
	* v0.7	- initial version (combination of Daniel's and Rene's code)
"""

from Blender import *
from xml.dom import minidom
import bpy
import math
import os


# SETTINGS
# if set to true, keeps converted .xml files in directory
KEEP_XML = False
# command line parameter to execute OgreXMLConverter
# here place path to your OgreXmlConverter
ogreXMLConverter = "D:\stuff\Torchlight_modding\orge_tools\OgreXmlConverter.exe -q"

has_skeleton = False
BonesData = {}
BoneIDDic = {}

def OpenFile(filename):
	xml_file = open(filename)
	try:
		xml_doc = minidom.parse(xml_file)
		output = xml_doc
	except:
		print "File not valid!"
		output = 'None'
	xml_file.close()
	return output

# makes sure name doesn't exceeds blender naming limits
# also keeps after name (as Torchlight uses names to identify types -boots, chest, ...- with names)
def GetBlender249Name(name):
    newname = name	
    if(len(name) > 20):
        if(name.find("/") >= 0):
            if(name.find("Material") >= 0):
                # replace 'Material' string with only 'Mt'
                newname = name.replace("Material","Mt")
            # check if it's still above 20
            if(len(newname) > 20):
                suffix = newname[newname.find("/"):]
                prefix = newname[0:(21-len(suffix))]
                newname = prefix + suffix
        else:
            newname = name[0:21]    		
    if(newname!=name):
        print("WARNING: Name truncated (" + name + " -> " + newname + ")")
            
    return newname
	

############################################################################################
############################################################################################
####                                                                                    ####
####            mm        mm     mmmmmmmmm       mmmmmm       mm      mm                ####
####            mmm      mmm     mmmmmmmmm     mmmmmmmmmm     mm      mm                ####
####            mmmmm  mmmmm     mm            mm      mm     mm      mm                ####
####            mm mmmmmm mm     mm            mm             mm      mm                ####
####            mm  mmmm  mm     mmmmmmm       mmmmmmmmm      mmmmmmmmmm                ####
####            mm   mm   mm     mmmmmmm        mmmmmmmmm     mmmmmmmmmm                ####
####            mm   mm   mm     mm                    mm     mm      mm                ####
####            mm        mm     mm            mm      mm     mm      mm                ####
####            mm        mm     mmmmmmmmm     mmmmmmmmmm     mm      mm                ####
####            mm        mm     mmmmmmmmm      mmmmmmmm      mm      mm                ####
####                                                                                    ####
############################################################################################
############################################################################################
   
def collectFaceData(facedata):
	faces = []
	for face in facedata.childNodes:
		if face.localName == 'face':
			v1 = int(face.getAttributeNode('v1').value)
			v2 = int(face.getAttributeNode('v2').value)
			v3 = int(face.getAttributeNode('v3').value)
			faces.append([v1,v2,v3])
	
	return faces
#---

#### VertexData Read
#---
def collectVertexData(data):
	vertexdata = {}
	vertices = []
	normals = []
	vertexcolors = []
	
	for vb in data.childNodes:
		if vb.localName == 'vertexbuffer':
			if vb.hasAttribute('positions'):
				for vertex in vb.getElementsByTagName('vertex'):
					for vp in vertex.childNodes:
						if vp.localName == 'position':
							x = float(vp.getAttributeNode('x').value)
							y = -float(vp.getAttributeNode('z').value)
							z = float(vp.getAttributeNode('y').value)
							vertices.append([x,y,z])
				vertexdata['positions'] = vertices			
			
			if vb.hasAttribute('normals'):
				for vertex in vb.getElementsByTagName('vertex'):
					for vn in vertex.childNodes:
						if vn.localName == 'normal':
							x = float(vn.getAttributeNode('x').value)
							y = -float(vn.getAttributeNode('z').value)
							z = float(vn.getAttributeNode('y').value)
							normals.append([x,y,z])
				vertexdata['normals'] = normals				
			
			if vb.hasAttribute('colours_diffuse'):
				for vertex in vb.getElementsByTagName('vertex'):
					for vcd in vertex.childNodes:
						if vcd.localName == 'colour_diffuse':
							rgba = vcd.getAttributeNode('value').value
							r = float(rgba.split()[0])
							g = float(rgba.split()[1])
							b = float(rgba.split()[2])
							a = float(rgba.split()[3])
							vertexcolors.append([r,g,b,a])
				vertexdata['vertexcolors'] = vertexcolors
			
			if vb.hasAttribute('texture_coord_dimensions_0'):
				texcosets = int(vb.getAttributeNode('texture_coords').value)
				vertexdata['texcoordsets'] = texcosets
				uvcoordset = []
				for vertex in vb.getElementsByTagName('vertex'):
					uvcoords = []
					for vt in vertex.childNodes:
						if vt.localName == 'texcoord':
							u = float(vt.getAttributeNode('u').value)
							v = -float(vt.getAttributeNode('v').value)+1.0
							uvcoords.append([u,v])
								
					if len(uvcoords) > 0:
						uvcoordset.append(uvcoords)
				vertexdata['uvsets'] = uvcoordset				
						
	return vertexdata		
#---

#### VertexGroupsData
#---
def collectBoneAssignments(data):
	global BoneIDDic
	
	VertexGroups = {}
	for vg in data.childNodes:
		if vg.localName == 'vertexboneassignment':
			VG = str(vg.getAttributeNode('boneindex').value)
			if VG in BoneIDDic.keys():
				VGNew = BoneIDDic[VG]
			else:
				VGNew = VG
			if VGNew not in VertexGroups.keys():
				VertexGroups[VGNew] = []
				
	for vg in data.childNodes:
		if vg.localName == 'vertexboneassignment':
			
			VG = str(vg.getAttributeNode('boneindex').value)
			if VG in BoneIDDic.keys():
				VGNew = BoneIDDic[VG]
			else:
				VGNew = VG
			verti = int(vg.getAttributeNode('vertexindex').value)
			weight = float(vg.getAttributeNode('weight').value)
			
			VertexGroups[VGNew].append([verti,weight])
			
	return VertexGroups
#---

#### Create Meshes
def CreateMeshes(xmldoc,meshname,Textures,dirname):
	global has_skeleton
	
	faceslist = []
	OGREObjects = []
	allObjs = []
	isSharedGeometry = False
	sharedGeom = []
		
	for submeshes in xmldoc.getElementsByTagName('submeshes'):
		for submesh in submeshes.childNodes:
			if submesh.localName == 'submesh':
				material = str(submesh.getAttributeNode('material').value)
				# to avoid Blender naming limit problems
				material = GetBlender249Name(material)
				sm = []
				sm.append(material)
				for subnodes in submesh.childNodes:
					if subnodes.localName == 'faces':
						facescount = int(subnodes.getAttributeNode('count').value)
						sm.append(collectFaceData(subnodes))
					
						if len(collectFaceData(subnodes)) != facescount:
							print "FacesCount doesn't match!"
							break 
					
					if (subnodes.localName == 'geometry'):
						vertexcount = int(subnodes.getAttributeNode('vertexcount').value)
						sm.append(collectVertexData(subnodes))
						
					if subnodes.localName == 'boneassignments':
						sm.append(collectBoneAssignments(subnodes))	
						
				OGREObjects.append(sm)
	
	if(len(xmldoc.getElementsByTagName('sharedgeometry')) > 0):
		for subnodes in xmldoc.getElementsByTagName('sharedgeometry'):
			sharedGeom = collectVertexData(subnodes)
			isSharedGeometry = True
			print("sharedGeometry")
			
	scn = Scene.GetCurrent()	
	for i in range(len(OGREObjects)):
		obj = Object.New('Mesh',OGREObjects[i][0])
		vertices = []
		if(isSharedGeometry):
			vertices = sharedGeom
		else:
			vertices = OGREObjects[i][2]
		faces = OGREObjects[i][1]
		allObjs.append(obj)
	
		me = Mesh.New(OGREObjects[i][0])
		me.verts.extend(vertices['positions'])
		me.faces.extend(faces)	
	
		c = 0
		for v in me.verts:
			if vertices.has_key('normals'):
				normals = vertices['normals']
				v.no = Mathutils.Vector(normals[c][0],normals[c][1],normals[c][2])
				c+=1
		
		for f in me.faces:
			f.smooth = 1		
	
		if vertices.has_key('texcoordsets'):
			for j in range(vertices['texcoordsets']):
				me.addUVLayer('UVLayer'+str(j))
				me.activeUVLayer = 'UVLayer'+str(j)
			
				for f in me.faces:	
					if vertices.has_key('uvsets'):
						uvco1sets = vertices['uvsets'][f.v[0].index]
						uvco2sets = vertices['uvsets'][f.v[1].index]
						uvco3sets = vertices['uvsets'][f.v[2].index]
						uvco1 = Mathutils.Vector(uvco1sets[j][0],uvco1sets[j][1])
						uvco2 = Mathutils.Vector(uvco2sets[j][0],uvco2sets[j][1])
						uvco3 = Mathutils.Vector(uvco3sets[j][0],uvco3sets[j][1])
						f.uv = (uvco1,uvco2,uvco3)
				
		if vertices.has_key('vertexcolors'):
			me.vertexColors = True
		
			vcolors = vertices['vertexcolors']
		
			for f in me.faces:
				for k,v in enumerate(f.v):
					col = f.col[k]
					vcol = vcolors[k]
					col.r = int(vcol[0]*255)
					col.g = int(vcol[1]*255)
					col.b = int(vcol[2]*255)
					col.a = int(vcol[3]*255)
		
		Mat = Material.New(OGREObjects[i][0])		
		if Textures != 'None':
			Tex = Texture.New(OGREObjects[i][0])
			Tex.setType('Image')
			try:
				img = Image.Load(Textures[OGREObjects[i][0]])
				Tex.image = img
			except:
				if(Textures.has_key(OGREObjects[i][0])):
					print "Image File",Textures[OGREObjects[i][0]], "skipped!"
				else:
					print "Image for material ", OGREObjects[i][0]," not found!"
			Mat.setRef(1.0)
			Mat.setTexture(0,Tex,Texture.TexCo.UV,Texture.MapTo.COL)
		Mat.setSpec(0.0)
		Mat.setHardness(1)
		Mat.setRGBCol(122,122,122)
		me.materials += [Mat]
		
		obj.link(me)		
		
		if has_skeleton:
			VGS = []
			#for shared geometry need to fetch boneassignments from root
			if(isSharedGeometry):
				for subnodes in xmldoc.getElementsByTagName('boneassignments'):	
					VGS = collectBoneAssignments(subnodes)
			else:
				VGS = OGREObjects[i][3]
			
			for VG in VGS.keys():
			
				me.addVertGroup(VG)
				for vert in VGS[VG]:
					weight = vert[1]
					vertex = [vert[0]]
					me.assignVertsToGroup(VG,vertex,weight,Mesh.AssignModes['REPLACE'])
				me.update()			
		
		
		scn.objects.link(obj)
		
	Redraw()
	
	return allObjs	

def OGREBoneIDsDic(xmldoc):
	
	global BoneIDDic

	for bones in xmldoc.getElementsByTagName('bones'):
	
		for bone in bones.childNodes:
			if bone.localName == 'bone':
				BoneName = str(bone.getAttributeNode('name').value)
				BoneID = int(bone.getAttributeNode('id').value)
				BoneIDDic[str(BoneID)] = BoneName
				
def GetTextures(matfile, folder):
	try:
		filein = open(matfile)
	except:
		print "File", matfile, "not found!"
		return 'None' 
	data = filein.readlines()
	filein.close()
	MaterialDic = {}
	
	count = 0
	for line in data:
		if "material" in line:
			MaterialName = line.split()[1]
			# to avoid Blender naming limit problems
			MaterialName = GetBlender249Name(MaterialName)
			MaterialDic[MaterialName] = []
			count = 0
		if "{" in line:
			count += 1
		if  count > 0:
			MaterialDic[MaterialName].append(line)
		if "}" in line:
			count -= 1
	Textures = {}
	for Material in MaterialDic.keys():
		print "Materialname:", Material
		for line in MaterialDic[Material]:
			if "texture_unit" in line:
				Textures[Material] = ""
				count = 0
			if "{" in line:
				count+=1
			if (count > 0) and ("texture" in line):
				file = os.path.join(folder, (line.split()[1]))			
				
				if(not os.path.isfile(file)):
					# just force to use .dds if there isn't file specified in material file
					file = os.path.join(folder, os.path.splitext((line.split()[1]))[0] + ".dds")
				Textures[Material] += file
					
			if "}" in line:
				count-=1
	
	return Textures

################################################################################
################################################################################
####                                                                        ####
####       aa    aaaaa   aa    aa    aa    aaaaa  a    a  aaaaa   aaaaaa    ####
####      a  a   a    a  a a  a a   a  a     a    a    a  a    a  a         ####
####     a    a  a    a  a  aa  a  a    a    a    a    a  a    a  a         ####
####     aaaaaa  aaaaa   a  aa  a  aaaaaa    a    a    a  aaaaa   aaaaa     ####
####     a    a  a    a  a      a  a    a    a    a    a  a    a  a         ####
####     a    a  a    a  a      a  a    a    a    a    a  a    a  a         ####
####     a    a  a    a  a      a  a    a    a     aaaa   a    a  aaaaaa    ####
####                                                                        ####
################################################################################
################################################################################ 
	
		
def CreateEmptys(BonesDic):
	scn = Scene.GetCurrent()
	for bone in BonesDic.keys():
		obj = Object.New('Empty',bone)
		scn.objects.link(obj)
		
	for bone in BonesDic.keys():
		if BonesDic[bone].has_key('parent'):
			Parent = Object.Get(BonesDic[bone]['parent'])
			object = Object.Get(bone)
			Parent.makeParent([object])
		
	for bone in BonesDic.keys():
		obj = Object.Get(bone)
		rot = BonesDic[bone]['rotation']
		loc = BonesDic[bone]['position']
		euler = Mathutils.RotationMatrix(math.degrees(rot[3]),3,'r',Mathutils.Vector(rot[0],-rot[2],rot[1])).toEuler()
		obj.setLocation(loc[0],-loc[2],loc[1])
		obj.setEuler(math.radians(euler[0]),math.radians(euler[1]),math.radians(euler[2]))
	Redraw()
	
	for bone in BonesDic.keys():
		obj = Object.Get(bone)
		rotmatAS = obj.getMatrix().rotationPart()
		BonesDic[bone]['rotmatAS'] = rotmatAS
		
	
	for bone in BonesDic.keys():
		obj = Object.Get(bone)
		scn.objects.unlink(obj)
		del obj
	
	
def VectorSum(vec1,vec2):
	vecout = [0,0,0]
	vecout[0] = vec1[0]+vec2[0]
	vecout[1] = vec1[1]+vec2[1]
	vecout[2] = vec1[2]+vec2[2]
	
	return vecout

#### Building the OGRE Bones Dictionary
def OGREBonesDic(xmldoc):
	OGRE_Bones = {}
	for bones in xmldoc.getElementsByTagName('bones'):
	
		for bone in bones.childNodes:
			OGRE_Bone = {}
			if bone.localName == 'bone':
				BoneName = str(bone.getAttributeNode('name').value)
				BoneID = int(bone.getAttributeNode('id').value)
				OGRE_Bone['name'] = BoneName
				OGRE_Bone['id'] = BoneID
							
				for b in bone.childNodes:
					if b.localName == 'position':
						x = float(b.getAttributeNode('x').value)
						y = float(b.getAttributeNode('y').value)
						z = float(b.getAttributeNode('z').value)
						OGRE_Bone['position'] = [x,y,z]
					if b.localName == 'rotation':
						angle = float(b.getAttributeNode('angle').value)
						axis = b.childNodes[1]
						axisx = float(axis.getAttributeNode('x').value)
						axisy = float(axis.getAttributeNode('y').value)
						axisz = float(axis.getAttributeNode('z').value)
						OGRE_Bone['rotation'] = [axisx,axisy,axisz,angle]
				
				OGRE_Bones[BoneName] = OGRE_Bone
					
	for bonehierarchy in xmldoc.getElementsByTagName('bonehierarchy'):
		for boneparent in bonehierarchy.childNodes:
			if boneparent.localName == 'boneparent':
				Bone = str(boneparent.getAttributeNode('bone').value)
				Parent = str(boneparent.getAttributeNode('parent').value)
				OGRE_Bones[Bone]['parent'] = Parent
		
	return OGRE_Bones

#### Add Bones Armature Head Positions to OGRE Bones Dictionary
def SetBonesASPositions(BonesData):
	
	for key in BonesData.keys():
		
		start = 0		
		thisbone = key
		posh = BonesData[key]['position']
		
		while start == 0:
			if BonesData[thisbone].has_key('parent'):
				parentbone = BonesData[thisbone]['parent']
				prot = BonesData[parentbone]['rotation']
				ppos = BonesData[parentbone]['position']			
				
				protmat = Mathutils.RotationMatrix(math.degrees(prot[3]),3,'r',Mathutils.Vector(prot[0],prot[1],prot[2])).invert()
				
				newposh = protmat * Mathutils.Vector(posh[0],posh[1],posh[2])
				
				positionh = VectorSum(ppos,newposh)
			
				posh = positionh
				
				thisbone = parentbone
			else:
				start = 1
		
		BonesData[key]['posHAS'] = posh
		
#### Add list of direct bones to each bone in the OGRE Bones Dictionary
def ChildList(BonesData):
	for bone in BonesData.keys():
		childlist = []
		for key in BonesData.keys():
			if BonesData[key].has_key('parent'):
				parent = BonesData[key]['parent']
				if parent == bone:
					childlist.append(key)
		BonesData[bone]['children'] = childlist
		
#### Add some Helper Bones
def HelperBones(BonesData):
	ChildList(BonesData)
	count = 0
	for bone in BonesData.keys():
		if (len(BonesData[bone]['children']) == 0) or (len(BonesData[bone]['children']) > 1):
			HelperBone = {}
			HelperBone['position'] = [0.2,0.0,0.0]
			HelperBone['parent'] = bone
			HelperBone['rotation'] = [1.0,0.0,0.0,0.0]
			HelperBone['flag'] = 'helper'
			BonesData['Helper'+str(count)] = HelperBone
			count+=1
			
#### Add some Helper Bones for Zero sizedBones
def ZeroBones(BonesData):
	for bone in BonesData.keys():
		pos = BonesData[bone]['position']
		if (math.sqrt(pos[0]**2+pos[1]**2+pos[2]**2)) == 0:
			ZeroBone = {}
			ZeroBone['position'] = [0.2,0.0,0.0]
			ZeroBone['rotation'] = [1.0,0.0,0.0,0.0]
			if (BonesData[bone].has_key('parent')):
				ZeroBone['parent'] = BonesData[bone]['parent']
			ZeroBone['flag'] = 'zerobone'
			BonesData['Zero'+bone] = ZeroBone
			if (BonesData[bone].has_key('parent')):
				BonesData[BonesData[bone]['parent']]['children'].append('Zero'+bone)

def CalcBoneLength(vec):
	return math.sqrt(vec[0]**2+vec[1]**2+vec[2]**2)

	
#### Create the Blender Armature						
def CreateBindSkeleton(xmldoc,skname):
	
	global BonesData
	
	BonesDic = OGREBonesDic(xmldoc)
	HelperBones(BonesDic)
	ZeroBones(BonesDic)
	CreateEmptys(BonesDic)
	SetBonesASPositions(BonesDic)

	BonesData = BonesDic
	
	scn = Scene.GetCurrent()

	obj = Object.New('Armature',skname)
	arm = Armature.New(skname)
	obj.link(arm)
	scn.link(obj)
	arm_mat = obj.matrixWorld.rotationPart()
	for bone in BonesDic.keys():
		arm.makeEditable()
		eb = Armature.Editbone()
		headPos = BonesDic[bone]['posHAS']
		if BonesDic[bone].has_key('children'):
			childlist = BonesDic[bone]['children']
			if len(childlist) == 1:
				childname = childlist[0]
				vectailadd = CalcBoneLength(BonesDic[childname]['position'])
				
			else:
				vectailadd = 0.2
		else:
			vectailadd = 0.2			
		
		vechead = Mathutils.Vector(headPos[0],-headPos[2],headPos[1])
		vectail = Mathutils.Vector(headPos[0],-headPos[2],headPos[1]+vectailadd)
		eb.head = vechead
		eb.tail = vectail
		rotmat = BonesDic[bone]['rotmatAS']
		newrotmat = Mathutils.Matrix(rotmat[1],rotmat[0],rotmat[2])
		
		eb.matrix = newrotmat		
		
		arm.bones[bone] = eb
		arm.update()	
	
	for bone in BonesDic.keys():
		arm.makeEditable()
		if BonesDic[bone].has_key('parent'):
			parent = BonesDic[bone]['parent']
			arm.bones[bone].parent = arm.bones[parent]
		arm.update()
	
	for bone in arm.bones.keys():
		if BonesDic[bone].has_key('flag'):
			arm.makeEditable()
			del arm.bones[bone]
			arm.update()
	
	
	Redraw()

def CreateRestPoseAction(xmldoc,skname):
	
	BonesDic = OGREBonesDic(xmldoc)
	armature = Object.Get(skname)
	pose = armature.getPose()
	newAction = Armature.NLA.NewAction('RestPose')
	newAction.setActive(armature)
	
	for bone in BonesDic.keys():
		pbone = pose.bones[bone]
		pbone.quat = Mathutils.Quaternion(Mathutils.Vector(1,0,0),0)
		pbone.insertKey(armature,1,Object.Pose.ROT)
		pbone.insertKey(armature,10,Object.Pose.ROT)
		pbone.loc = Mathutils.Vector(0,0,0)
		pbone.insertKey(armature,1,Object.Pose.LOC)
		pbone.insertKey(armature,10,Object.Pose.LOC)
	
#
# ANIMATION
#
	
def ParseAnimationSkeleton(xmldoc):
	OGRE_Bones = {}
		
	for bones in xmldoc.getElementsByTagName('bones'):
	
		for bone in bones.childNodes:
			OGRE_Bone = {}
			if bone.localName == 'bone':
				BoneName = str(bone.getAttributeNode('name').value)
				BoneID = int(bone.getAttributeNode('id').value)
				OGRE_Bone['name'] = BoneName
				OGRE_Bone['id'] = BoneID
							
				for b in bone.childNodes:
					if b.localName == 'position':
						x = float(b.getAttributeNode('x').value)
						y = float(b.getAttributeNode('y').value)
						z = float(b.getAttributeNode('z').value)
						OGRE_Bone['position'] = [x,y,z]
					if b.localName == 'rotation':
						angle = float(b.getAttributeNode('angle').value)
						axis = b.childNodes[1]
						axisx = float(axis.getAttributeNode('x').value)
						axisy = float(axis.getAttributeNode('y').value)
						axisz = float(axis.getAttributeNode('z').value)
						OGRE_Bone['rotation'] = [axisx,axisy,axisz,angle]
				
				OGRE_Bones[BoneName] = OGRE_Bone
					
	for bonehierarchy in xmldoc.getElementsByTagName('bonehierarchy'):
		for boneparent in bonehierarchy.childNodes:
			if boneparent.localName == 'boneparent':
				Bone = str(boneparent.getAttributeNode('bone').value)
				Parent = str(boneparent.getAttributeNode('parent').value)
				OGRE_Bones[Bone]['parent'] = Parent
		
	return OGRE_Bones

def ParseActionAnimations(xmldoc):
	
	Animations = {}
		
	for animations in xmldoc.getElementsByTagName('animations'):
		for animation in animations.getElementsByTagName('animation'):
			aniname = str(animation.getAttributeNode('name').value)
			print aniname
			Track = {}
			for tracks in animation.getElementsByTagName('tracks'):
				for track in tracks.getElementsByTagName('track'):
					trackname = str(track.getAttributeNode('bone').value)
					Track[trackname] = []
					for keyframes in track.getElementsByTagName('keyframes'):
						for keyframe in keyframes.getElementsByTagName('keyframe'):
							time = float(keyframe.getAttributeNode('time').value)
							for translate in keyframe.getElementsByTagName('translate'):
								x = float(translate.getAttributeNode('x').value)
								y = float(translate.getAttributeNode('y').value)
								z = float(translate.getAttributeNode('z').value)
								translate = [x,y,z]
							for rotate in keyframe.getElementsByTagName('rotate'):
								angle = float(rotate.getAttributeNode('angle').value)
								for axis in rotate.getElementsByTagName('axis'):
									rx = float(axis.getAttributeNode('x').value)
									ry = float(axis.getAttributeNode('y').value)
									rz = float(axis.getAttributeNode('z').value)
								rotation = [rx,ry,rz,angle]
							Track[trackname].append([time,translate,rotation])
				Animations[aniname] = Track

	return Animations

#### Writing the Actions

def CreateActions(ActionsDic,armaturename,BonesDic):
	
	global BonesData
	
	armature = Object.Get(armaturename)
	pose = armature.getPose()
	restpose = armature.getData()
		
	for Action in ActionsDic.keys():
		newAction = Armature.NLA.NewAction(Action)
		newAction.setActive(armature)
		isActionData = False
		
		for track in ActionsDic[Action].keys():
			isActionData = True
			rpbone = restpose.bones[track]			
			rpbonequat = rpbone.matrix['BONESPACE'].rotationPart().toQuat()			
			rpbonetrans = Mathutils.Vector(BonesData[track]['position'][2], BonesData[track]['position'][0], BonesData[track]['position'][1])
			sprot = BonesDic[track]['rotation']
			sploc = BonesDic[track]['position']
			spbonequat = Mathutils.Quaternion(Mathutils.Vector(sprot[2],sprot[0],sprot[1]),math.degrees(sprot[3]))
			spbonetrans = Mathutils.Vector(sploc[2], sploc[0], sploc[1])
			quatdiff = Mathutils.DifferenceQuats(rpbonequat,spbonequat).toMatrix()
			transdiff = spbonetrans - rpbonetrans			
			pbone = pose.bones[track]
			lastTime = ActionsDic[Action][track][len(ActionsDic[Action][track])-1][0]
			
			for kfrs in ActionsDic[Action][track]:
				
				frame = int(1+(kfrs[0]*25))				
				# in ActionDic = [animation][bone]{[time], [locX, locY, locZ], [rotX, rotY, rotZ, rotAngle]}
				quataction = Mathutils.Quaternion(Mathutils.Vector(kfrs[2][2],kfrs[2][0],kfrs[2][1]),math.degrees(kfrs[2][3])).toMatrix()
				
				quat = (quataction*quatdiff).toQuat()			
				pbone.quat = quat
				pbone.insertKey(armature,frame,Object.Pose.ROT)	
				pbone.loc = Mathutils.Vector(kfrs[1][2],kfrs[1][0],kfrs[1][1]) + transdiff
				if(BonesDic[track].has_key('parent')):
					if(BonesDic[track]['parent'] == 'root'):
						pbone.loc = Mathutils.Vector(kfrs[1][2],-kfrs[1][1],kfrs[1][0]) + Mathutils.Vector(transdiff[2],-transdiff[0],-transdiff[1])
									
				pbone.insertKey(armature,frame,Object.Pose.LOC)
		# only if there are actions		
		if(isActionData):		
			ChannelIPOS = newAction.getAllChannelIpos()
			for bone in BonesDic.keys():
				if not bone in ChannelIPOS.keys() and not bone == 'root':
					rpbonequat = restpose.bones[bone].matrix['BONESPACE'].rotationPart().toQuat()
					sprot = BonesDic[bone]['rotation']
					spbonequat = Mathutils.Quaternion(Mathutils.Vector(sprot[2],sprot[0],sprot[1]),math.degrees(sprot[3]))
					quatdiff = Mathutils.DifferenceQuats(rpbonequat,spbonequat)
					pbone = pose.bones[bone]
					pbone.quat = quatdiff
					pbone.insertKey(armature,1,Object.Pose.ROT)
					pbone.insertKey(armature,int(1+lastTime*25),Object.Pose.ROT)

def CreateSkeleton(xml_doc, folder, name):

	global has_skeleton

	scene = bpy.data.scenes.active
	
	if(len(xml_doc.getElementsByTagName("skeletonlink")) > 0):
		# get the skeleton link of the mesh
		skeleton_link = xml_doc.getElementsByTagName("skeletonlink")[0]
		filename = os.path.join(folder, skeleton_link.getAttribute("name"))
		try:
			skel_xml_doc = OpenFile(filename + ".xml")	
			if skel_xml_doc == "None":
				print "%s file not found!" % filename
				return
		except:
			print "%s file not found! Mesh won't load and link associated skeleton." % filename
			return
	else:
		return

	has_skeleton = True
	
	CreateBindSkeleton(skel_xml_doc, name)	
	CreateRestPoseAction(skel_xml_doc, name)
	OGREBoneIDsDic(skel_xml_doc)
	
	
def CreateMesh(xml_doc, folder, name, materialFile):

	textures = 'None'
	if(materialFile != "None"):
		textures = GetTextures(materialFile, folder)

	allObjs = CreateMeshes(xml_doc, name, textures, folder)
	
	scene = bpy.data.scenes.active		
	mesh = bpy.data.meshes.new(name)
	# append 'M' for name (Mesh)
	obj = scene.objects.new(mesh, str(name + "M"))
	obj.join(allObjs)			
	# remove submeshes
	for ob in allObjs:
		scene.objects.unlink(ob)
			
	if has_skeleton:
		# parent mesh to armature with deform properties
		Object.Get(name).makeParentDeform([obj], 0, 0)
	
	
def AddAnimation(xml_doc, name):
	# get skeleton in rest pose and action animation
	BonesDic = ParseAnimationSkeleton(xml_doc)
	Actions = ParseActionAnimations(xml_doc)

	CreateActions(Actions, name, BonesDic)	
	
def ImportOgre(path):

	global has_skeleton

	Window.WaitCursor(1)
	folder = os.path.split(path)[0]
	meshfilename = os.path.split(path)[1].lower()	
	name = "mesh"
	files = []
	materialFile = "None"
	
	print meshfilename
	# convert MESH and SKELETON file to MESH.XML and SKELETON.XML respectively
	for filename in os.listdir(folder):
		# we're going to do string comparisons. assume lower case to simplify code
		filename = os.path.join(folder, filename.lower())
		# process .mesh and .skeleton files while skipping .xml files
		if ((".skeleton" in filename) or (".mesh" in filename)) and (".xml" not in filename):
			os.system('%s "%s"' % (ogreXMLConverter, filename))

	# get all the filenames in the chosen directory, put in list and sort it
	for filename in os.listdir(folder):
		# we're going to do string comparisons. assume lower case to simplify code
		filename = filename.lower()
		# process .mesh and .skeleton files while skipping .xml files
		if ".skeleton.xml" in filename:
			files.append(os.path.join(folder, filename))
		elif (".mesh.xml" in filename) and (meshfilename in filename):
			print meshfilename
			# get the name of the MESH file without extension. Use this base name to name our imported object
			name = filename.split('.')[0]
			# to avoid Blender naming limit problems
			name = GetBlender249Name(name)
			# put MESH file on top of the file list
			files.insert(0, os.path.join(folder, filename))
		elif ".material" in filename:
			# material file
			materialFile = os.path.join(folder, filename)

	# now that we have a list of files, process them
	filename = files[0]
	# import the mesh
	if (".mesh" in filename):
		mesh_data = OpenFile(filename)
		if mesh_data != "None":
			CreateSkeleton(mesh_data, folder, name)
			CreateMesh(mesh_data, folder, name, materialFile)
			if not KEEP_XML:
				# cleanup by deleting the XML file we created
				os.unlink("%s" % filename)
	
	if has_skeleton:
		# process all the files again. this time process skeleton files which must be processed after mesh file
		# the armature must already be created (when mesh was processed) prior to this.
		for filename in files:
			# import the skeleton file
			if (".skeleton" in filename) and (str(name + ".skeleton") not in filename):
				skeleton_data = OpenFile(filename)
				if skeleton_data != "None":
					AddAnimation(skeleton_data, name)
					if not KEEP_XML:
						# cleanup by deleting the XML file we created
						os.unlink("%s" % filename)

	Window.WaitCursor(0)
	Window.RedrawAll()



print "\n\n\n"
Window.FileSelector(ImportOgre, "Import")
