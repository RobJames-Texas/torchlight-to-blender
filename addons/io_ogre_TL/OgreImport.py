import operator
import subprocess
import os
import math
from mathutils import Vector, Matrix
import bpy
from xml.dom import minidom
from functools import reduce

SHOW_IMPORT_DUMPS = False
SHOW_IMPORT_TRACE = False
DEFAULT_KEEP_XML = False
MIN_BONE_LENGTH = 0.00001  # Prevent automatic removal of bones


# makes sure name doesn't exceeds blender naming limits
# also keeps after name (as Torchlight uses names to identify types
#  -boots, chest, ...- with names)
def GetValidBlenderName(name):
    maxChars = 63

    newname = name
    if(len(name) > maxChars):
        if(name.find("/") >= 0):
            if(name.find("Material") >= 0):
                # replace 'Material' string with only 'Mt'
                newname = name.replace("Material", "Mt")
            # check if it's still above 20
            if(len(newname) > maxChars):
                suffix = newname[newname.find("/"):]
                prefix = newname[0:(maxChars+1-len(suffix))]
                newname = prefix + suffix
        else:
            newname = name[0:maxChars+1]
    if(newname != name):
        print("WARNING: Name truncated (" + name + " -> " + newname + ")")

    return newname




def matmul(matracies):
    return reduce((lambda x, y: operator.matmul(x, y)), matracies)


def xOpenFile(filename):
    xml_file = open(filename)
    try:
        xml_doc = minidom.parse(xml_file)
        output = xml_doc
    except Exception:
        print("File not valid!")
        output = 'None'
    xml_file.close()
    return output


def xCollectFaceData(facedata):
    faces = []
    for face in facedata.childNodes:
        if face.localName == 'face':
            v1 = int(face.getAttributeNode('v1').value)
            v2 = int(face.getAttributeNode('v2').value)
            v3 = int(face.getAttributeNode('v3').value)
            faces.append([v1, v2, v3])

    return faces


def xCollectVertexData(data, useNormals):
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
                            vertices.append([x, y, z])
                vertexdata['positions'] = vertices

            if vb.hasAttribute('normals') and useNormals:
                for vertex in vb.getElementsByTagName('vertex'):
                    for vn in vertex.childNodes:
                        if vn.localName == 'normal':
                            x = float(vn.getAttributeNode('x').value)
                            y = -float(vn.getAttributeNode('z').value)
                            z = float(vn.getAttributeNode('y').value)
                            normals.append([x, y, z])
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
                            vertexcolors.append([r, g, b, a])
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
                            uvcoords.append([u, v])

                    if len(uvcoords) > 0:
                        uvcoordset.append(uvcoords)
                vertexdata['uvsets'] = uvcoordset

    return vertexdata


def xCollectMeshData(meshData, xmldoc, meshname, dirname, useNormals):
    # global has_skeleton
    faceslist = []
    subMeshData = []
    allObjs = []
    isSharedGeometry = False
    sharedGeom = []
    hasSkeleton = 'boneIDs' in meshData

    # collect shared geometry
    if(len(xmldoc.getElementsByTagName('sharedgeometry')) > 0):
        isSharedGeometry = True
        for subnodes in xmldoc.getElementsByTagName('sharedgeometry'):
            meshData['sharedgeometry'] = xCollectVertexData(
                subnodes, useNormals)

        if hasSkeleton:
            for subnodes in xmldoc.getElementsByTagName('boneassignments'):
                meshData['sharedgeometry']['boneassignments'] = \
                    xCollectBoneAssignments(meshData, subnodes)

    # collect submeshes data
    for submeshes in xmldoc.getElementsByTagName('submeshes'):
        for submesh in submeshes.childNodes:
            if submesh.localName == 'submesh':
                materialOrg = str(submesh.getAttributeNode('material').value)
                # to avoid Blender naming limit problems
                material = GetValidBlenderName(materialOrg)
                sm = {}
                sm['material'] = material
                sm['materialOrg'] = materialOrg
                for subnodes in submesh.childNodes:
                    if subnodes.localName == 'faces':
                        facescount = int(
                            subnodes.getAttributeNode('count').value)
                        sm['faces'] = xCollectFaceData(subnodes)

                        if len(xCollectFaceData(subnodes)) != facescount:
                            print("FacesCount doesn't match!")
                            break

                    if (subnodes.localName == 'geometry'):
                        vertexcount = int(
                            subnodes.getAttributeNode('vertexcount').value)
                        sm['geometry'] = xCollectVertexData(
                            subnodes, useNormals)

                    if hasSkeleton and (subnodes.localName == 'boneassignments'
                                        and isSharedGeometry is False):
                        sm['geometry']['boneassignments'] = \
                            xCollectBoneAssignments(meshData, subnodes)

                subMeshData.append(sm)

    meshData['submeshes'] = subMeshData

    return meshData


def xCollectMaterialData(meshData, materialFiles, folder):
    data = None
    if len(materialFiles) == 1:
        materialFile = materialFiles[0]
        try:
            filein = open(materialFile)
        except Exception:
            print("WARNING: Material: File", materialFile, "not found!")
            return 'None'
        data = filein.readlines()
        filein.close()
    else:
        # we have multiple material files, so check them for required materials
        # pick one material from meshData
        if(len(meshData['submeshes']) > 0):
            # take only first material
            firstMaterial = meshData['submeshes'][0]['materialOrg']

            materialFound = False
            for matFile in materialFiles:
                try:
                    filein = open(matFile)
                except Exception:
                    print("WARNING: Material: File", matFile, "not found!")
                    return 'None'
                data = filein.readlines()
                filein.close()
                # try to find material name in file
                materialFound = False
                for line in data:
                    if firstMaterial in line:
                        materialFound = True
                        break

                if materialFound:
                    print("Material '%s' found in '%s'" %
                          (firstMaterial, matFile))
                    break
            # material is not found at all
            if not materialFound:
                data = None

    MaterialDic = {}
    allMaterials = {}

    # no material data, so just return
    if data is not None:
        count = 0
        for line in data:
            if "material" in line:
                MaterialName = line.split()[1]
                # to avoid Blender naming limit problems
                MaterialName = GetValidBlenderName(MaterialName)
                MaterialDic[MaterialName] = []
                count = 0
            if "{" in line:
                count += 1
            if count > 0:
                MaterialDic[MaterialName].append(line)
            if "}" in line:
                count -= 1

        # print(MaterialDic)
        for Material in MaterialDic.keys():
            count = 0
            matDict = {}
            allMaterials[Material] = matDict
            if SHOW_IMPORT_TRACE:
                print("Materialname: ", Material)
            for line in MaterialDic[Material]:
                if "{" in line:
                    count += 1
                # texture
                if ((count > 0)
                        and ("texture " in line)
                        and ('texture' not in matDict)):
                    imageName = (line.split()[1])
                    file = os.path.join(folder, imageName)
                    if(not os.path.isfile(file)):
                        # just force to use .dds if there isn't file specified
                        # in material file
                        file = os.path.join(folder, os.path.splitext(
                            (line.split()[1]))[0] + ".dds")
                        if(os.path.isfile(file)):
                            matDict['texture'] = file
                            matDict['imageNameOnly'] = imageName
                        else:
                            print(
                                "WARNING: Referenced texture '%s' not found"
                                % file)
                    else:
                        matDict['texture'] = file
                        matDict['imageNameOnly'] = imageName
                # ambient color
                if(count > 0) and ("ambient" in line):
                    lineSplit = line.split()
                    if len(lineSplit) >= 4:
                        r = float(lineSplit[1])
                        g = float(lineSplit[2])
                        b = float(lineSplit[3])
                        matDict['ambient'] = [r, g, b]
                # diffuse color
                if(count > 0) and ("diffuse" in line):
                    lineSplit = line.split()
                    if len(lineSplit) >= 4:
                        r = float(lineSplit[1])
                        g = float(lineSplit[2])
                        b = float(lineSplit[3])
                        matDict['diffuse'] = [r, g, b]

                # specular color
                if(count > 0) and ("specular" in line):
                    lineSplit = line.split()
                    if len(lineSplit) >= 4:
                        r = float(lineSplit[1])
                        g = float(lineSplit[2])
                        b = float(lineSplit[3])
                        matDict['specular'] = [r, g, b]

                # emissive color
                if(count > 0) and ("emissive" in line):
                    lineSplit = line.split()
                    if len(lineSplit) >= 4:
                        r = float(lineSplit[1])
                        g = float(lineSplit[2])
                        b = float(lineSplit[3])
                        matDict['emissive'] = [r, g, b]

                if "}" in line:
                    count -= 1

    # store it into meshData
    meshData['materials'] = allMaterials
    if SHOW_IMPORT_TRACE:
        print("allMaterials: %s" % allMaterials)


def xCollectBoneAssignments(meshData, xmldoc):
    boneIDtoName = meshData['boneIDs']

    VertexGroups = {}
    for vg in xmldoc.childNodes:
        if vg.localName == 'vertexboneassignment':
            VG = str(vg.getAttributeNode('boneindex').value)
            if VG in boneIDtoName.keys():
                VGNew = boneIDtoName[VG]
            else:
                VGNew = 'Group ' + VG
            if VGNew not in VertexGroups.keys():
                VertexGroups[VGNew] = []

    for vg in xmldoc.childNodes:
        if vg.localName == 'vertexboneassignment':

            VG = str(vg.getAttributeNode('boneindex').value)
            if VG in boneIDtoName.keys():
                VGNew = boneIDtoName[VG]
            else:
                VGNew = VG
            verti = int(vg.getAttributeNode('vertexindex').value)
            weight = float(vg.getAttributeNode('weight').value)
            # print("bone=%s, vert=%s, weight=%s" % (VGNew,verti,weight))
            VertexGroups[VGNew].append([verti, weight])

    return VertexGroups


def xCollectPoseData(meshData, xmldoc):
    poses = xmldoc.getElementsByTagName('pose')
    if(len(poses) > 0):
        meshData['poses'] = []
    for pose in poses:
        name = pose.getAttribute('name')
        target = pose.getAttribute('target')
        index = pose.getAttribute('index')
        if target == 'submesh':
            poseData = {}
            poseData['name'] = name
            poseData['submesh'] = int(index)
            poseData['data'] = data = []
            meshData['poses'].append(poseData)
            for value in pose.getElementsByTagName('poseoffset'):
                index = int(value.getAttribute('index'))
                x = float(value.getAttribute('x'))
                y = float(value.getAttribute('y'))
                z = float(value.getAttribute('z'))
                data.append((index, x, -z, y))


def xGetSkeletonLink(xmldoc, folder, operator):
    skeletonFile = "None"
    if(len(xmldoc.getElementsByTagName("skeletonlink")) > 0):
        # get the skeleton link of the mesh
        skeletonLink = xmldoc.getElementsByTagName("skeletonlink")[0]
        skeletonName = skeletonLink.getAttribute("name")
        skeletonFile = os.path.join(folder, skeletonName)
        # check for existence of skeleton file
        if not os.path.isfile(skeletonFile):
            operator.report({'WARNING'}, "Cannot find linked skeleton file '" +
                                         skeletonName + "'\nIt must be in " +
                                         "the same directory as the mesh " +
                                         "file.")
            print("Warning: Ogre skeleton missing: " + skeletonFile)
            skeletonFile = "None"

    return skeletonFile


# def xCollectBoneData(meshData, xDoc, name, folder):
def xCollectBoneData(meshData, xDoc):
    OGRE_Bones = {}
    BoneIDToName = {}
    meshData['skeleton'] = OGRE_Bones
    meshData['boneIDs'] = BoneIDToName

    for bones in xDoc.getElementsByTagName('bones'):
        for bone in bones.childNodes:
            OGRE_Bone = {}
            if bone.localName == 'bone':
                boneName = str(bone.getAttributeNode('name').value)
                boneID = int(bone.getAttributeNode('id').value)
                OGRE_Bone['name'] = boneName
                OGRE_Bone['id'] = boneID
                BoneIDToName[str(boneID)] = boneName

                for b in bone.childNodes:
                    if b.localName == 'position':
                        x = float(b.getAttributeNode('x').value)
                        y = float(b.getAttributeNode('y').value)
                        z = float(b.getAttributeNode('z').value)
                        OGRE_Bone['position'] = [x, y, z]
                    if b.localName == 'rotation':
                        angle = float(b.getAttributeNode('angle').value)
                        axis = b.childNodes[1]
                        axisx = float(axis.getAttributeNode('x').value)
                        axisy = float(axis.getAttributeNode('y').value)
                        axisz = float(axis.getAttributeNode('z').value)
                        OGRE_Bone['rotation'] = [axisx, axisy, axisz, angle]

                OGRE_Bones[boneName] = OGRE_Bone

    for bonehierarchy in xDoc.getElementsByTagName('bonehierarchy'):
        for boneparent in bonehierarchy.childNodes:
            if boneparent.localName == 'boneparent':
                Bone = str(boneparent.getAttributeNode('bone').value)
                Parent = str(boneparent.getAttributeNode('parent').value)
                OGRE_Bones[Bone]['parent'] = Parent

    # update Ogre bones with list of children
    calcBoneChildren(OGRE_Bones)

    # helper bones
    calcHelperBones(OGRE_Bones)
    calcZeroBones(OGRE_Bones)

    # update Ogre bones with head positions
    calcBoneHeadPositions(OGRE_Bones)

    # update Ogre bones with rotation matrices
    calcBoneRotations(OGRE_Bones)

    return OGRE_Bones


def calcBoneChildren(BonesData):
    for bone in BonesData.keys():
        childlist = []
        for key in BonesData.keys():
            if 'parent' in BonesData[key]:
                parent = BonesData[key]['parent']
                if parent == bone:
                    childlist.append(key)
        BonesData[bone]['children'] = childlist


def calcHelperBones(BonesData):
    count = 0
    helperBones = {}
    for bone in BonesData.keys():
        if ((len(BonesData[bone]['children']) == 0) or
                (len(BonesData[bone]['children']) > 1)):
            HelperBone = {}
            HelperBone['position'] = [0.2, 0.0, 0.0]
            HelperBone['parent'] = bone
            HelperBone['rotation'] = [1.0, 0.0, 0.0, 0.0]
            HelperBone['flag'] = 'helper'
            HelperBone['name'] = 'Helper'+str(count)
            HelperBone['children'] = []
            helperBones['Helper'+str(count)] = HelperBone
            count += 1
    for hBone in helperBones.keys():
        BonesData[hBone] = helperBones[hBone]


def calcZeroBones(BonesData):
    zeroBones = {}
    for bone in BonesData.keys():
        pos = BonesData[bone]['position']
        if (math.sqrt(pos[0]**2+pos[1]**2+pos[2]**2)) == 0:
            ZeroBone = {}
            ZeroBone['position'] = [0.2, 0.0, 0.0]
            ZeroBone['rotation'] = [1.0, 0.0, 0.0, 0.0]
            if 'parent' in BonesData[bone]:
                ZeroBone['parent'] = BonesData[bone]['parent']
            ZeroBone['flag'] = 'zerobone'
            ZeroBone['name'] = 'Zero'+bone
            ZeroBone['children'] = []
            zeroBones['Zero'+bone] = ZeroBone
            if 'parent' in BonesData[bone]:
                BonesData[BonesData[bone]['parent']
                          ]['children'].append('Zero'+bone)
    for hBone in zeroBones.keys():
        BonesData[hBone] = zeroBones[hBone]


def calcBoneHeadPositions(BonesData):
    for key in BonesData.keys():

        start = 0
        thisbone = key
        posh = BonesData[key]['position']
        while start == 0:
            if 'parent' in BonesData[thisbone]:
                parentbone = BonesData[thisbone]['parent']
                prot = BonesData[parentbone]['rotation']
                ppos = BonesData[parentbone]['position']

                protmat = Matrix.Rotation(prot[3], 3, Vector(
                    [prot[0], prot[1], prot[2]])).inverted()
                newposh = matmul([protmat.transposed(),
                                 Vector([posh[0], posh[1], posh[2]])])  # 03
                positionh = VectorSum(ppos, newposh)

                posh = positionh

                thisbone = parentbone
            else:
                start = 1

        BonesData[key]['posHAS'] = posh


def calcBoneRotations(BonesDic):
    objDic = {}
    scn = bpy.context.scene
    for bone in BonesDic.keys():
        obj = bpy.data.objects.new(bone, None)
        objDic[bone] = obj
        # scn.objects.link(obj)
        addObjectToScene(bpy.context, obj)
    # print("all objects created")
    # print(bpy.data.objects)
    for bone in BonesDic.keys():
        if 'parent' in BonesDic[bone]:
            Parent = objDic.get(BonesDic[bone]['parent'])
            object = objDic.get(bone)
            object.parent = Parent
    # print("all parents linked")
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        rot = BonesDic[bone]['rotation']
        loc = BonesDic[bone]['position']
        euler = Matrix.Rotation(rot[3], 3, Vector(
            [rot[0], -rot[2], rot[1]])).to_euler()
        obj.location = [loc[0], -loc[2], loc[1]]
        obj.rotation_euler = [euler[0], euler[1], euler[2]]  # 02
    # Redraw()
    scnUpdate()

    # print("all objects rotated")
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        # TODO: need to get rotation matrix out of objects rotation
        # loc, rot, scale = obj.matrix_local.decompose()
        loc, rot, scale = obj.matrix_world.decompose()  # 02
        rotmatAS = rot.to_matrix()
        # print(rotmatAS)
        BonesDic[bone]['rotmatAS'] = rotmatAS
    # print("all matrices stored")

    # TODO cyclic
    for bone in BonesDic.keys():
        obj = objDic.get(bone)
        removeObjectFromScene(bpy.context, obj)
        bpy.data.objects.remove(obj)

    scnUpdate()


def VectorSum(vec1, vec2):
    vecout = [0, 0, 0]
    vecout[0] = vec1[0]+vec2[0]
    vecout[1] = vec1[1]+vec2[1]
    vecout[2] = vec1[2]+vec2[2]

    return vecout


###############################################################################

def scnUpdate():
    bpy.context.view_layer.update()


def quaternionFromAngleAxis(angle, x, y, z):
    r = angle * 0.5
    s = math.sin(r)
    c = math.cos(r)
    return (c, x*s, y*s, z*s)


def xGetChild(node, tag):
    for n in node.childNodes:
        if n.nodeType == 1 and n.tagName == tag:
            return n
    return None


def xAnalyseFPS(xDoc):
    fps = 0
    lastTime = 1e8
    samples = 0
    for container in xDoc.getElementsByTagName('animations'):
        for animation in container.childNodes:
            if animation.nodeType == 1 and animation.tagName == 'animation':
                tracks = xGetChild(animation, 'tracks')
                for track in tracks.childNodes:
                    if track.nodeType == 1:
                        for keyframe in xGetChild(track,
                                                  'keyframes').childNodes:
                            if keyframe.nodeType == 1:
                                time = float(keyframe.getAttribute('time'))
                                if time > lastTime:
                                    fps = max(fps, 1 / (time - lastTime))
                                lastTime = time
                                samples = samples + 1
                                if samples > 100:
                                    return round(fps, 2)    # stop here
    return round(fps, 2)


def xCollectAnimations(meshData, xDoc, integerFrames=True):
    if 'animations' not in meshData:
        meshData['animations'] = {}
    for container in xDoc.getElementsByTagName('animations'):
        for animation in container.childNodes:
            if animation.nodeType == 1 and animation.tagName == 'animation':
                name = animation.getAttribute('name')

                # read action data
                action = {}
                tracks = xGetChild(animation, 'tracks')
                xReadAnimation(action, tracks.childNodes, integerFrames)
                meshData['animations'][name] = action


def xReadAnimation(action, tracks, integerFrames=True):
    fps = bpy.context.scene.render.fps
    for track in tracks:
        if track.nodeType != 1:
            continue
        target = track.getAttribute('bone')
        action[target] = trackData = [[] for i in range(3)]  # pos, rot, scl
        for keyframe in xGetChild(track, 'keyframes').childNodes:
            if keyframe.nodeType != 1:
                continue
            time = float(keyframe.getAttribute('time'))
            frame = time * fps
            if integerFrames:
                frame = round(frame)
            for key in keyframe.childNodes:
                if key.nodeType != 1:
                    continue
                if key.tagName == 'translate':
                    x = float(key.getAttribute('x'))
                    y = float(key.getAttribute('y'))
                    z = float(key.getAttribute('z'))
                    trackData[0].append([frame, (x, y, z)])
                elif key.tagName == 'rotate':
                    axis = xGetChild(key, 'axis')
                    angle = key.getAttribute('angle')
                    x = axis.getAttribute('x')
                    y = axis.getAttribute('y')
                    z = axis.getAttribute('z')
                    # skip if axis contains #INF or #IND
                    if '#' not in x and '#' not in y and '#' not in z:
                        quat = quaternionFromAngleAxis(
                            float(angle), float(z), float(x), float(y))
                        trackData[1].append([frame, quat])
                elif key.tagName == 'scale':
                    x = float(key.getAttribute('x'))
                    y = float(key.getAttribute('y'))
                    z = float(key.getAttribute('z'))
                    trackData[2].append([frame, (-x, z, y)])


def bCreateAnimations(meshData):
    path_id = ['location', 'rotation_quaternion', 'scale']

    if 'animations' in meshData:
        rig = meshData['rig']
        rig.animation_data_create()
        animdata = rig.animation_data

        # calculate transformation matrices for translation
        mat = {}
        fix1 = Matrix([(1, 0, 0), (0, 0, 1), (0, -1, 0)])
        fix2 = Matrix([(0, 1, 0), (0, 0, 1), (1, 0, 0)])
        for bone in rig.pose.bones:
            if bone.parent:
                mat[bone.name] = \
                    matmul([fix2,
                           bone.parent.matrix.to_3x3().transposed(),
                           bone.matrix.to_3x3()])
            else:
                mat[bone.name] = matmul([fix1, bone.matrix.to_3x3()])

        for name in sorted(meshData['animations'].keys(), reverse=True):
            action = bpy.data.actions.new(name)
            print("Created action", name)

            # iterate target bones
            for target in meshData['animations'][name]:
                data = meshData['animations'][name][target]
                bone = rig.pose.bones[target]
                if not bone:
                    continue  # error
                bone.rotation_mode = 'QUATERNION'

                # Fix rotation inversions
                for i in range(1, len(data[1])):
                    a = data[1][i-1][1]
                    b = data[1][i][1]
                    dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2] + a[3]*b[3]
                    if dot < -0.8:
                        # print('fix inversion', name, target)
                        data[1][i][1] = (-b[0], -b[1], -b[2], -b[3])

                # fix translation keys - rotate by inverse rest orientation
                m = mat[target].transposed()
                for i in range(0, len(data[0])):
                    v = Vector(data[0][i][1])
                    data[0][i][1] = m @ v

                # create fcurves
                for i in range(3):
                    if data[i]:
                        path = bone.path_from_id(path_id[i])
                        for channel in range(len(data[i][0][1])):
                            curve = action.fcurves.new(data_path=path,
                                                       index=channel,
                                                       action_group=bone.name)
                            for key in data[i]:
                                curve.keyframe_points.insert(key[0],
                                                             key[1][channel])

            # Add action to NLA track
            track = animdata.nla_tracks.new()
            track.name = name
            track.mute = True
            track.strips.new(name, 0, action)

###############################################################################


def bCreateMesh(meshData, folder, name, filepath, useAutoSmooth):
    if 'skeleton' in meshData:
        skeletonName = meshData['skeletonName']
        bCreateSkeleton(meshData, skeletonName)

    # from collected data create all sub meshes
    subObjs = bCreateSubMeshes(meshData, name, useAutoSmooth)

    # Move to parent skeleton if there
    if 'armature' in meshData:
        arm = meshData['armature']
        for obj in subObjs:
            print('Move to', arm.location)
            obj.location = arm.location
            obj.rotation_euler = arm.rotation_euler
            obj.rotation_axis_angle = arm.rotation_axis_angle
            obj.rotation_quaternion = arm.rotation_quaternion

    # temporarily select all imported objects
    for subOb in subObjs:
        subOb.select_set(True)

    if SHOW_IMPORT_DUMPS:
        importDump = filepath + "IDump"
        fileWr = open(importDump, 'w')
        fileWr.write(str(meshData))
        fileWr.close()


def bCreateSkeleton(meshData, name):
    if 'skeleton' not in meshData:
        return
    bonesData = meshData['skeleton']

    # create Armature
    amt = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, amt)
    meshData['rig'] = rig
    rig.display_type = 'WIRE'

    # Link object to scene
    scn = bpy.context.scene
    # scn.objects.link(rig)
    addObjectToScene(bpy.context, rig)
    # scn.objects.active = rig
    setActiveObject(bpy.context, rig)
    scnUpdate()

    # Chose default length of bones with no children
    averageBone = 0
    for b in bonesData.values():
        childLength = b['position'][0]
        averageBone += childLength
    averageBone /= len(bonesData)
    if averageBone == 0:
        averageBone = 0.2
    print("Default bone length:", averageBone)

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        boneName = boneData['name']

        children = boneData['children']
        boneObj = amt.edit_bones.new(boneName)

        # Store Ogre bone id to match when exporting
        if 'id' in boneData:
            boneObj['OGREID'] = boneData['id']
            print('bone', boneData['id'], boneName)

        # boneObj.head = boneData['posHAS']
        # headPos = boneData['posHAS']
        headPos = boneData['posHAS']
        tailVector = 0
        if len(children) > 0:
            for child in children:
                tailVector = max(tailVector, bonesData[child]['position'][0])
        if tailVector < MIN_BONE_LENGTH:
            tailVector = averageBone

        rotmat = boneData['rotmatAS']
        # this is a way of flipping matrix for Blender 4.2+
        r0 = [rotmat.col[0].x] + [rotmat.col[0].y] + [rotmat.col[0].z]
        r1 = [rotmat.col[1].x] + [rotmat.col[1].y] + [rotmat.col[1].z]
        r2 = [rotmat.col[2].x] + [rotmat.col[2].y] + [rotmat.col[2].z]
        tmpR = Matrix((r1, r0, r2))
        boneRotMatrix = Matrix((tmpR.col[0], tmpR.col[1], tmpR.col[2]))

        boneObj.head = Vector([0, 0, 0])
        boneObj.tail = Vector([0, tailVector, 0])

        boneObj.transform(boneRotMatrix)
        boneObj.translate(Vector([headPos[0], -headPos[2], headPos[1]]))

    # only after all bones are created we can link parents
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        parent = None
        if 'parent' in boneData.keys():
            parent = boneData['parent']
            # get bone obj
            boneData = bonesData[bone]
            boneName = boneData['name']
            boneObj = amt.edit_bones[boneName]
            boneObj.parent = amt.edit_bones[parent]

    # need to refresh armature before removing bones
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')

    # delete helper/zero bones
    for bone in amt.bones.keys():
        # print("keys of bone=%s" % bonesData[bone].keys())
        if 'flag' in bonesData[bone].keys():
            # print ("deleting bone=%s" % bone)
            bpy.context.object.data.edit_bones.remove(amt.edit_bones[bone])

    bpy.ops.object.mode_set(mode='OBJECT')


def bMergeVertices(subMesh):
    # This sort of works, but leaves all uv seams as sharp.
    geometry = subMesh['geometry']
    vertices = geometry['positions']
    normals = geometry['normals']
    uvsets = geometry['uvsets'] if 'uvsets' in geometry else None
    lookup = {}
    map = [i for i in range(len(vertices))]
    for i in range(len(vertices)):
        vert = vertices[i]
        norm = normals[i]
        uv = tuple(uvsets[i][0]) if uvsets else None
        item = (tuple(vert), tuple(norm), uv)
        target = lookup.get(item)
        if target is None:
            lookup[item] = i
        else:
            map[i] = target
    # update faces
    faces = subMesh['faces']
    for face in faces:
        for i in range(len(face)):
            face[i] = map[face[i]]


def bCreateSubMeshes(meshData, meshName, useAutoSmooth):
    allObjects = []
    submeshes = meshData['submeshes']
    scene = bpy.context.scene
    layer = bpy.context.view_layer

    for subMeshIndex in range(len(submeshes)):
        subMeshData = submeshes[subMeshIndex]
        subMeshName = subMeshData['material']

        # Create mesh and object
        me = bpy.data.meshes.new(subMeshName)
        ob = bpy.data.objects.new(subMeshName, me)
        # Link object to scene
        scene.collection.objects.link(ob)
        layer.objects.active = ob
        layer.update()

        # check for submesh geometry, or take the shared one
        if 'geometry' in subMeshData.keys():
            geometry = subMeshData['geometry']
        else:
            geometry = meshData['sharedgeometry']

        verts = geometry['positions']
        faces = subMeshData['faces']
        hasNormals = False
        if 'normals' in geometry.keys():
            normals = geometry['normals']
            hasNormals = True

        # mesh vertices and faces
        VertLength = len(verts)
        FaceLength = len(faces)
        me.vertices.add(VertLength)
        me.loops.add(FaceLength * 3)
        me.polygons.add(FaceLength)
        for i in range(VertLength):
            me.vertices[i].co = verts[i]
            if hasNormals:
                me.vertices[i].normal = Vector((normals[i][0],
                                                normals[i][1],
                                                normals[i][2]))

        for i in range(FaceLength):
            me.loops[i*3].vertex_index = faces[i][0]
            me.loops[i*3+1].vertex_index = faces[i][1]
            me.loops[i*3+2].vertex_index = faces[i][2]
            me.polygons[i].loop_start = i*3
            me.polygons[i].loop_total = 3
            me.polygons[i].use_smooth

        hasTexture = False
        # material for the submesh
        # Create image texture from image.
        if subMeshName in meshData['materials']:
            matInfo = meshData['materials'][subMeshName]  # material data
            if 'texture' in matInfo:
                texturePath = matInfo['texture']
                if texturePath:
                    hasTexture = True
                    # try to find among already loaded images
                    loadedImage = None
                    for img in bpy.data.images:
                        if img.name == matInfo['imageNameOnly']:
                            loadedImage = img
                            break
                    if not loadedImage and texturePath:
                        loadedImage = bpy.data.images.load(texturePath)

            # Create shadeless material and MTex
            mat = bpy.data.materials.new(subMeshName)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get('ShaderNodeBsdfPrincipled')
            if bsdf is None:
                bsdf = mat.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')

            # ambient
            # if 'ambient' in matInfo:  # no AO in eevee
            #     mat.ambient = matInfo['ambient'][0]
            # diffuse
            if 'diffuse' in matInfo:
                # mat.diffuse_color = matInfo['diffuse']
                r, g, b = matInfo['diffuse']
                bsdf.inputs['Base Color'].default_value = [r, g, b, 1]
            # specular
            if 'specular' in matInfo:
                # this didn't look right
                # r, g, b = matInfo['specular']
                # gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
                bsdf.inputs['Specular'].default_value = 0
            # mat.use_shadeless = True
            node_texture = mat.node_tree.nodes.new(type='ShaderNodeTexImage')
            node_texture.name = 'DiffuseTexture'
            node_texture.location = -300, 0
            # mtex = mat.texture_slots.add()
            if hasTexture and loadedImage:
                # mtex.texture = tex
                node_texture.image = loadedImage
            links = mat.node_tree.links
            links.new(node_texture.outputs[0], bsdf.inputs[0])
            # mtex.texture_coords = 'UV'
            # mtex.use_map_color_diffuse = True
            uvmap = mat.node_tree.nodes.new(type='ShaderNodeUVMap')
            uvmap.uv_map = 'UVLayer0'
            links.new(uvmap.outputs['UV'], node_texture.inputs['Vector'])

            # emmisive
            if 'emissive' in matInfo:
                er, eg, eb = matInfo['emissive']
                bsdf.inputs['Emission'].default_value = [0, 0, 0, 1]

                sepRgb = mat.node_tree.nodes.new(type='ShaderNodeSeparateRGB')
                links.new(node_texture.outputs['Color'],
                          sepRgb.inputs['Image'])
                rChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                rChan.name = 'EmissionR'
                rChan.inputs['Strength'].default_value = er
                links.new(sepRgb.outputs['R'], rChan.inputs['Color'])
                rShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(rChan.outputs[0], rShade.inputs[0])

                gChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                gChan.name = 'EmissionG'
                gChan.inputs['Strength'].default_value = eg
                links.new(sepRgb.outputs['G'], gChan.inputs['Color'])
                gShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(gChan.outputs[0], gShade.inputs[0])

                bChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                bChan.name = 'EmissionB'
                bChan.inputs['Strength'].default_value = eb
                links.new(sepRgb.outputs['B'], bChan.inputs['Color'])
                bShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(bChan.outputs[0], bShade.inputs[0])

                combineRGB = mat.node_tree.nodes.new(
                    type='ShaderNodeCombineRGB')
                links.new(rShade.outputs['Color'], combineRGB.inputs['R'])
                links.new(gShade.outputs['Color'], combineRGB.inputs['G'])
                links.new(bShade.outputs['Color'], combineRGB.inputs['B'])
                links.new(combineRGB.outputs['Image'], bsdf.inputs['Emission'])

            # add material to object
            ob.data.materials.append(mat)

        # texture coordinates
        if 'texcoordsets' in geometry and 'uvsets' in geometry:
            uvsets = geometry['uvsets']
            for j in range(geometry['texcoordsets']):
                uvData = me.uv_layers.add(name='UVLayer'+str(j)).data
                loopIndex = 0
                for face in faces:
                    for v in face:
                        uvData[loopIndex].uv = uvsets[v][j]
                        loopIndex += 1

        # vertex colors
        if 'vertexcolors' in geometry:
            colourData = me.color_attributes.new('Colour'+str(j), type='COLOR').data
            vcolors = geometry['vertexcolors']
            loopIndex = 0
            for face in faces:
                for v in face:
                    colourData[loopIndex].color = vcolors[v]
                    loopIndex += 1

            # Vertex Alpha
            for c in vcolors:
                if c[3] != 1.0:
                    alphaData = me.color_attributes.new('Alpha'+str(j), type='COLOR').data
                    loopIndex = 0
                    for face in faces:
                        for v in face:
                            colourData[loopIndex].color[3] = vcolors[v][3]
                            loopIndex += 1
                    break

        # bone assignments:
        if 'boneIDs' in meshData:
            if 'boneassignments' in geometry.keys():
                vgroups = geometry['boneassignments']
                for vgname, vgroup in vgroups.items():
                    grp = ob.vertex_groups.new(name=vgname)
                    for (v, w) in vgroup:
                        grp.add([v], w, 'REPLACE')
        # Give mesh object an armature modifier, using vertex groups but
        # not envelopes
        if 'skeleton' in meshData:
            skeletonName = meshData['skeletonName']
            mod = ob.modifiers.new('OgreSkeleton', 'ARMATURE')
            mod.object = bpy.data.objects[skeletonName]  # gets the rig object
            mod.use_bone_envelopes = False
            mod.use_vertex_groups = True
        elif 'armature' in meshData:
            mod = ob.modifiers.new('OgreSkeleton', 'ARMATURE')
            mod.object = meshData['armature']
            mod.use_bone_envelopes = False
            mod.use_vertex_groups = True

        # Shape keys (poses)
        if 'poses' in meshData:
            base = None
            for pose in meshData['poses']:
                if(pose['submesh'] == subMeshIndex):
                    # must have base shape
                    if base is None:
                        base = ob.shape_key_add(name='Basis')
                    name = pose['name']
                    print('creating pose', name)
                    shape = ob.shape_key_add(name=name)
                    for vkey in pose['data']:
                        b = base.data[vkey[0]].co
                        me.shape_keys.key_blocks[name].data[vkey[0]].co = \
                            [vkey[1] + b[0], vkey[2] + b[1], vkey[3] + b[2]]

        # Update mesh with new data
        # No 'verbose' parameter — Blender 4.2+ always uses the internal default
        me.validate()
        me.update()

        if useAutoSmooth:
            # me.use_auto_smooth = True
            ob.data.use_auto_smooth = True
            ob.data.auto_smooth_angle = 1.5708  # 90 degrees
        else:
            for f in me.polygons:
                f.use_smooth = True

        bpy.ops.object.editmode_toggle()
        bpy.ops.mesh.remove_doubles(threshold=0.001)
        bpy.ops.object.editmode_toggle()

        # try to set custom normals
        if hasNormals:
            noChange = len(me.loops) == len(faces)*3
            if not noChange:
                print('Removed',  len(faces) - len(me.loops)/3, 'faces')
            split = []
            polyIndex = 0
            for face in faces:
                if noChange or matchFace(face, verts, me, polyIndex):
                    polyIndex += 1
                    for vx in face:
                        split.append(normals[vx])

            if len(split) == len(me.loops):
                me.normals_split_custom_set(split)
            else:
                print('Warning: Failed to import mesh normals', polyIndex, '/',
                      len(me.polygons))

        allObjects.append(ob)

    return allObjects


def matchFace(face, vertices, mesh, index):
    if index >= len(mesh.polygons):
        return False  # ?? err - what broke
    loop = mesh.polygons[index].loop_start
    for v in face:
        vi = mesh.loops[loop].vertex_index
        vx = mesh.vertices[vi].co

        if (vx-Vector(vertices[v])).length_squared > 1e-6:
            return False

        # if vx != Vector(vertices[v]):
        #    return False  # May need threshold ?
        loop += 1
    return True


def convertXML(convertor, filename, use_existing=True):
    print('create xml', filename)
    if filename.endswith('.xml'):
        return True
    elif use_existing and os.path.isfile(filename + '.xml'):
        return True
    elif convertor is None:
        return False
    else:
        print("Execute: ", convertor, '-q', filename)
        try:
            subprocess.call([convertor, '-q', filename])
            return os.path.isfile(filename + '.xml')
        except Exception:
            print("Error: Could not run", convertor)
            return False


def setActiveObject(context, obj):
    context.view_layer.objects.active = obj


def addObjectToScene(context, obj):
    context.scene.collection.objects.link(obj)


def removeObjectFromScene(context, obj):
    context.scene.collection.objects.unlink(obj)


def getBoneNameMapFromArmature(arm):
    # get ogre bone ids - need to be in edit mode to access edit_bones.
    # Arm should already be the active object
    boneMap = {}

    setActiveObject(bpy.context, arm)

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    for bone in arm.data.edit_bones:
        if 'OGREID' in bone:
            boneMap[str(bone['OGREID'])] = bone.name
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    return boneMap


def load(operator, context, filepath, xml_converter=None, keep_xml=True,
         import_autosmooth=False, import_normals=True, import_shapekeys=True,
         import_animations=False, round_frames=False,
         use_selected_skeleton=False):
    print("loading", str(filepath))

    filepath = filepath
    pathMeshXml = filepath
    # get the mesh as .xml file
    if filepath.lower().endswith(".mesh"):
        if convertXML(xml_converter, filepath):
            pathMeshXml = filepath + ".xml"
        else:
            operator.report({'ERROR'}, "Failed to convert .mesh files to .xml")
            return {'CANCELLED'}
    else:
        return {'CANCELLED'}

    folder = os.path.split(filepath)[0]
    nameDotMeshDotXml = os.path.split(pathMeshXml)[1]
    nameDotMesh = os.path.splitext(nameDotMeshDotXml)[0]
    onlyName = os.path.splitext(nameDotMesh)[0]

    # material
    meshMaterials = []
    nameDotMaterial = onlyName + ".material"
    pathMaterial = os.path.join(folder, nameDotMaterial)
    if not os.path.isfile(pathMaterial):
        # search directory for .material
        for filename in os.listdir(folder):
            if ".material" in filename:
                # material file
                pathMaterial = os.path.join(folder, filename)
                meshMaterials.append(pathMaterial)
                # print("alternative material file: %s" % pathMaterial)
    else:
        meshMaterials.append(pathMaterial)

    # try to parse xml file
    xDocMeshData = xOpenFile(pathMeshXml)

    meshData = {}
    if xDocMeshData != "None":
        # skeleton data
        # get the mesh as .xml file
        skeletonFile = xGetSkeletonLink(xDocMeshData, folder, operator)

        # use selected skeleton
        selectedSkeleton = context.active_object \
            if (use_selected_skeleton
                and context.active_object
                and context.active_object.type == 'ARMATURE') else None
        if selectedSkeleton:
            map = getBoneNameMapFromArmature(selectedSkeleton)
            if map:
                meshData['boneIDs'] = map
                meshData['armature'] = selectedSkeleton
            else:
                operator.report({'WARNING'},
                                "Selected armature has no OGRE data.")

        # there is valid skeleton link and existing file
        elif(skeletonFile != "None"):
            if convertXML(xml_converter, skeletonFile):
                skeletonFileXml = skeletonFile + ".xml"

            # parse .xml skeleton file
            xDocSkeletonData = xOpenFile(skeletonFileXml)
            if xDocSkeletonData != "None":
                xCollectBoneData(meshData, xDocSkeletonData)
                meshData['skeletonName'] = os.path.basename(skeletonFile[:-9])

                # parse animations
                if import_animations:
                    fps = xAnalyseFPS(xDocSkeletonData)
                    if(fps and round_frames):
                        print("Setting FPS to", fps)
                        bpy.context.scene.render.fps = fps
                    xCollectAnimations(meshData,
                                       xDocSkeletonData,
                                       round_frames)

            else:
                operator.report({'WARNING'}, "Failed to load linked skeleton")
                print("Failed to load linked skeleton")

        # collect mesh data
        print("collecting mesh data...")
        xCollectMeshData(meshData, xDocMeshData,
                         onlyName, folder, import_normals)
        xCollectMaterialData(meshData, meshMaterials, folder)

        if import_shapekeys:
            xCollectPoseData(meshData, xDocMeshData)

        # after collecting is done, start creating stuff#
        # create skeleton (if any) and mesh from parsed data
        bCreateMesh(meshData, folder, onlyName, pathMeshXml, import_autosmooth)
        bCreateAnimations(meshData)
        if not keep_xml:
            # cleanup by deleting the XML file we created
            os.unlink("%s" % pathMeshXml)
            if 'skeleton' in meshData:
                os.unlink("%s" % skeletonFileXml)

    if SHOW_IMPORT_TRACE:
        print("folder: %s" % folder)
        print("nameDotMesh: %s" % nameDotMesh)
        print("nameDotMeshDotXml: %s" % nameDotMeshDotXml)
        print("onlyName: %s" % onlyName)
        print("nameDotMaterial: %s" % nameDotMaterial)
        print("pathMaterial: %s" % pathMaterial)
        print("ogreXMLconverter: %s" % xml_converter)

    print("done.")
    return {'FINISHED'}
