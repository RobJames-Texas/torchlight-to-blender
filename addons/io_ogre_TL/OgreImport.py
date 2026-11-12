import subprocess
import os
import math
from mathutils import Vector, Matrix
import bpy
from xml.dom import minidom
from bpy_extras.anim_utils import action_ensure_channelbag_for_slot

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
    data = []
    
    # Unpack file lists smoothly
    if isinstance(materialFiles, (list, tuple)):
        target_files = materialFiles
    else:
        target_files = [materialFiles] if materialFiles else []

    for matFile in target_files:
        if matFile and os.path.isfile(matFile):
            try:
                with open(matFile, 'r', errors='ignore') as filein:
                    data.extend(filein.readlines())
            except Exception as e:
                print("WARNING: Material file could not be read:", matFile, e)

    allMaterials = {}
    
    # -------------------------------------------------------------
    # STRUCTURAL BLOCK TOKENIZER (Bypasses all tab & line breaks)
    # -------------------------------------------------------------
    # 1. Clean the entire file text down into flat, sequential space-separated tokens
    clean_text = " "
    for line in data:
        # Strip comments
        if line.strip().startswith("//") or line.strip().startswith("#"):
            continue
        # Ensure symbols are padded with spaces so splitting keeps them isolated
        formatted_line = line.replace("{", " { ").replace("}", " } ")
        clean_text += formatted_line + " "
        
    tokens = clean_text.split()
    
    # 2. Walk the token stack structurally
    i = 0
    while i < len(tokens):
        if tokens[i].lower() == "material" and (i + 1) < len(tokens):
            raw_mat_name = tokens[i+1].strip('"')
            mat_name = GetValidBlenderName(raw_mat_name)
            
            # Sub-parse everything strictly locked inside this specific material's scope
            allMaterials[mat_name] = {}
            brace_depth = 0
            
            # Read tokens ahead until this material block closes
            j = i + 2
            while j < len(tokens):
                token_lower = tokens[j].lower()
                
                if token_lower == "{":
                    brace_depth += 1
                elif token_lower == "}":
                    brace_depth -= 1
                    if brace_depth <= 0: # Material block closed completely
                        i = j
                        break
                        
                # Directly grab our properties regardless of nested technique/pass depth!
                # Keep only the first texture unit (diffuse); later ones are normal/specular maps.
                elif (token_lower == "texture" and (j + 1) < len(tokens)
                        and 'texture' not in allMaterials[mat_name]):
                    img_name = tokens[j+1].strip('"')
                    full_path = os.path.join(folder, img_name)
                    
                    # Extension fallback protection
                    if not os.path.isfile(full_path):
                        base = os.path.splitext(full_path)[0]
                        for fallback_ext in ['.png', '.PNG', '.dds', '.DDS', '.jpg', '.JPG', '.tga', '.TGA']:
                            if os.path.isfile(base + fallback_ext):
                                full_path = base + fallback_ext
                                img_name = os.path.basename(full_path)
                                break
                                
                    allMaterials[mat_name]['texture'] = full_path
                    allMaterials[mat_name]['imageNameOnly'] = img_name
                    
                elif token_lower == "diffuse" and (j + 3) < len(tokens):
                    try: allMaterials[mat_name]['diffuse'] = [float(tokens[j+1]), float(tokens[j+2]), float(tokens[j+3])]
                    except ValueError: pass
                elif token_lower == "ambient" and (j + 3) < len(tokens):
                    try: allMaterials[mat_name]['ambient'] = [float(tokens[j+1]), float(tokens[j+2]), float(tokens[j+3])]
                    except ValueError: pass
                elif token_lower == "specular" and (j + 3) < len(tokens):
                    try: allMaterials[mat_name]['specular'] = [float(tokens[j+1]), float(tokens[j+2]), float(tokens[j+3])]
                    except ValueError: pass
                elif token_lower == "emissive" and (j + 3) < len(tokens):
                    try: allMaterials[mat_name]['emissive'] = [float(tokens[j+1]), float(tokens[j+2]), float(tokens[j+3])]
                    except ValueError: pass
                
                j += 1
        i += 1

    meshData['materials'] = allMaterials


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
                newposh = protmat.transposed() @ Vector([posh[0], posh[1], posh[2]])  # 03
                positionh = VectorSum(ppos, newposh)

                posh = positionh

                thisbone = parentbone
            else:
                start = 1

        BonesData[key]['posHAS'] = posh


def calcBoneRotations(BonesDic):
    #  FIXED FOR 5.x: Pure memory-space matrix calculations. Zero object/scene pollution!
    from mathutils import Matrix, Vector
    
    # Step 1: Compute local matrices for each bone
    local_matrices = {}
    for bone, data in BonesDic.items():
        rot = data['rotation']
        loc = data['position']
        
        # Build local translation and rotation components
        translation = Vector((loc[0], -loc[2], loc[1]))
        rotation_matrix = Matrix.Rotation(rot[3], 3, Vector((rot[0], -rot[2], rot[1]))).to_4x4()
        
        # Combine into a single local transform matrix
        mat = rotation_matrix
        mat.col[3][0:3] = translation
        local_matrices[bone] = mat

    # Step 2: Traverse hierarchies to compute world rotation matrices
    for bone, data in BonesDic.items():
        # Walk up the parent chain to calculate the final world transformation matrix
        current_bone = bone
        world_matrix = Matrix.Identity(4)
        chain = []
        
        while current_bone:
            chain.append(current_bone)
            current_bone = BonesDic[current_bone].get('parent')
            
        # Multiply down from root down to the leaf bone
        for b in reversed(chain):
            world_matrix = world_matrix @ local_matrices[b]
            
        # Extract the pure 3x3 orientation matrix block and save it
        data['rotmatAS'] = world_matrix.to_3x3()


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
                mat[bone.name] = fix2 @ bone.parent.matrix.to_3x3().transposed() @ bone.matrix.to_3x3()
            else:
                mat[bone.name] = fix1 @ bone.matrix.to_3x3()

        for name in sorted(meshData['animations'].keys(), reverse=True):
            action = bpy.data.actions.new(name)
            print("Created action", name)
            # Blender 5.x slotted actions: F-curves live in a channelbag
            slot = action.slots.new(id_type='OBJECT', name=rig.name)
            channelbag = action_ensure_channelbag_for_slot(action, slot)
            groups = {}

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
                            if bone.name not in groups:
                                groups[bone.name] = channelbag.groups.new(bone.name)
                            curve = channelbag.fcurves.new(data_path=path,
                                                           index=channel)
                            curve.group = groups[bone.name]
                            for key in data[i]:
                                curve.keyframe_points.insert(key[0],
                                                             key[1][channel])

            # Add action to NLA track
            track = animdata.nla_tracks.new()
            track.name = name
            track.mute = True
            strip = track.strips.new(name, 0, action)
            strip.action_slot = slot

###############################################################################


def bCreateMesh(meshData, folder, name, filepath):
    if 'skeleton' in meshData:
        skeletonName = meshData['skeletonName']
        bCreateSkeleton(meshData, skeletonName)

    # from collected data create all sub meshes
    subObjs = bCreateSubMeshes(meshData, name)

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
    addObjectToScene(bpy.context, rig)
    setActiveObject(bpy.context, rig)
    scnUpdate()

    # Choose default length of bones with no children
    averageBone = 0
    for b in bonesData.values():
        childLength = b['position'][0]
        averageBone += childLength
    averageBone /= len(bonesData)
    if averageBone == 0:
        averageBone = 0.2
    print("Default bone length:", averageBone)

    # ENTER EDIT MODE EXACTLY ONCE
    bpy.ops.object.mode_set(mode='EDIT')
    
    # 1. Generate bone geometry and transformations
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        boneName = boneData['name']

        children = boneData['children']
        boneObj = amt.edit_bones.new(boneName)

        # Store Ogre bone id to match when exporting
        if 'id' in boneData:
            boneObj['OGREID'] = boneData['id']
            print('bone', boneData['id'], boneName)

        headPos = boneData['posHAS']
        tailVector = 0
        if len(children) > 0:
            for child in children:
                tailVector = max(tailVector, bonesData[child]['position'][0])
        if tailVector < MIN_BONE_LENGTH:
            tailVector = averageBone

        rotmat = boneData['rotmatAS']
        # Matrix orientation flip logic for structural matching
        r0 = [rotmat.col[0].x] + [rotmat.col[0].y] + [rotmat.col[0].z]
        r1 = [rotmat.col[1].x] + [rotmat.col[1].y] + [rotmat.col[1].z]
        r2 = [rotmat.col[2].x] + [rotmat.col[2].y] + [rotmat.col[2].z]
        tmpR = Matrix((r1, r0, r2))
        boneRotMatrix = Matrix((tmpR.col[0], tmpR.col[1], tmpR.col[2]))

        boneObj.head = Vector([0, 0, 0])
        boneObj.tail = Vector([0, tailVector, 0])

        boneObj.transform(boneRotMatrix)
        boneObj.translate(Vector([headPos[0], -headPos[2], headPos[1]]))

    # 2. Link parent structural relationships immediately
    for bone in bonesData.keys():
        boneData = bonesData[bone]
        if 'parent' in boneData.keys():
            parent = boneData['parent']
            boneName = boneData['name']
            boneObj = amt.edit_bones[boneName]
            boneObj.parent = amt.edit_bones[parent]

    # 3. Clean up helper/zero bones safely within the same EDIT mode block
    for bone_name in list(amt.edit_bones.keys()):
        if bone_name in bonesData and 'flag' in bonesData[bone_name].keys():
            bone_to_remove = amt.edit_bones.get(bone_name)
            if bone_to_remove:
                amt.edit_bones.remove(bone_to_remove)

    #  STABILIZATION FOR 5.x: Ensure armature data updates fully inside C++ memory pools
    bpy.context.view_layer.update()

    # EXIT EDIT MODE SAFELY
    if bpy.context.object and bpy.context.object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    # Finalize view layers so the mesh loop inherits a stable workspace
    bpy.context.view_layer.update()


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


def bCreateSubMeshes(meshData, meshName):
    allObjects = []
    submeshes = meshData['submeshes']
    scene = bpy.context.scene
    layer = bpy.context.view_layer

    for subMeshIndex in range(len(submeshes)):
        subMeshData = submeshes[subMeshIndex]
        subMeshName = subMeshData['material']

        if 'geometry' in subMeshData.keys():
            geometry = subMeshData['geometry']
        else:
            geometry = meshData['sharedgeometry']

        raw_verts = geometry['positions']
        raw_faces = subMeshData['faces']
        
        hasNormals = 'normals' in geometry.keys()
        raw_normals = geometry['normals'] if hasNormals else []

        # Extract only the vertices utilized by the current submesh's faces
        used_indices = sorted(list(set(v for face in raw_faces for v in face)))
        index_map = {old_idx: new_idx for new_idx, old_idx in enumerate(used_indices)}
        
        verts = [raw_verts[idx] for idx in used_indices]
        faces = [[index_map[v] for v in face] for face in raw_faces]
        normals = [raw_normals[idx] for idx in used_indices] if hasNormals else []

        # Instantiate our tight mesh object
        me = bpy.data.meshes.new(subMeshName)
        ob = bpy.data.objects.new(subMeshName, me)
        scene.collection.objects.link(ob)
        layer.objects.active = ob
        layer.update()

        me.from_pydata(verts, [], faces)
        me.validate()
        me.update()

        # Run safe case-insensitive mapping lookups against our clean materials cache
        matInfo = None
        materials_dict = meshData.get('materials', {})
        for key in materials_dict.keys():
            if key.lower().strip() == subMeshName.lower().strip():
                matInfo = materials_dict[key]
                break

        if matInfo:
            mat = bpy.data.materials.new(subMeshName)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links

            nodes.clear()

            output_node = nodes.new(type='ShaderNodeOutputMaterial')
            output_node.location = (300, 0)
            
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)

            # Link our main shader directly to the Material Output
            links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])

            if 'diffuse' in matInfo:
                r, g, b = matInfo['diffuse']
                bsdf.inputs['Base Color'].default_value = [r, g, b, 1]
            if 'specular' in matInfo:
                bsdf.inputs['Specular IOR Level'].default_value = 0

            # Generate the texture sampling pipeline nodes
            if 'texture' in matInfo:
                node_texture = mat.node_tree.nodes.new(type='ShaderNodeTexImage')
                node_texture.name = 'DiffuseTexture'
                node_texture.location = (-300, 0)
                
                texturePath = matInfo['texture']
                if texturePath and os.path.isfile(texturePath):
                    try:
                        node_texture.image = bpy.data.images.load(texturePath)
                        if node_texture.image:
                            node_texture.image.colorspace_settings.name = 'sRGB'
                    except Exception as e:
                        print(f"Warning: Could not read image file: {e}")

                # Establish material mapping node links safely
                if len(node_texture.outputs) > 0 and 'Base Color' in bsdf.inputs:
                    links.new(node_texture.outputs[0], bsdf.inputs['Base Color'])

                uvmap = mat.node_tree.nodes.new(type='ShaderNodeUVMap')
                uvmap.uv_map = 'UVLayer0'
                #links.new(uvmap.outputs['UV'], node_texture.inputs['Vector'])
                if len(uvmap.outputs) > 0 and len(node_texture.inputs) > 0:
                    links.new(uvmap.outputs[0], node_texture.inputs[0])
            
            if 'emissive' in matInfo:
                er, eg, eb = matInfo['emissive']
                bsdf.inputs['Emission Color'].default_value = [er, eg, eb, 1]

                sepRgb = mat.node_tree.nodes.new(type='ShaderNodeSeparateColor')
                links.new(node_texture.outputs['Color'], sepRgb.inputs['Color'])
                
                rChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                rChan.inputs['Strength'].default_value = er
                links.new(sepRgb.outputs['Red'], rChan.inputs['Color'])
                rShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(rChan.outputs[0], rShade.inputs[0])

                gChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                gChan.name = 'EmissionG'
                gChan.inputs['Strength'].default_value = eg
                links.new(sepRgb.outputs['Green'], gChan.inputs['Color'])
                gShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(gChan.outputs[0], gShade.inputs[0])

                bChan = mat.node_tree.nodes.new(type='ShaderNodeEmission')
                bChan.name = 'EmissionB'
                bChan.inputs['Strength'].default_value = eb
                links.new(sepRgb.outputs['Blue'], bChan.inputs['Color'])
                bShade = mat.node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                links.new(bChan.outputs[0], bShade.inputs[0])

                combineRGB = mat.node_tree.nodes.new(type='ShaderNodeCombineColor')
                links.new(rShade.outputs['Color'], combineRGB.inputs['Red'])
                links.new(gShade.outputs['Color'], combineRGB.inputs['Green'])
                links.new(bShade.outputs['Color'], combineRGB.inputs['Blue'])
                links.new(combineRGB.outputs['Color'], bsdf.inputs['Emission Color'])

            ob.data.materials.append(mat)

        # UV Coordinates assignments
        if 'texcoordsets' in geometry and 'uvsets' in geometry:
            uvsets = geometry['uvsets']
            for j in range(geometry['texcoordsets']):
                uvData = me.uv_layers.new(name='UVLayer'+str(j)).data
                for loop_idx, loop in enumerate(me.loops):
                    v_old = used_indices[loop.vertex_index]
                    if v_old < len(uvsets):
                        uvData[loop_idx].uv = uvsets[v_old][j]

        # Vertex Color Attributes assignments
        if 'vertexcolors' in geometry:
            colour_layer = me.color_attributes.new(name='Colour0', type='FLOAT_COLOR', domain='CORNER')
            colourData = colour_layer.data
            vcolors = geometry['vertexcolors']
            for loop_idx, loop in enumerate(me.loops):
                v_old = used_indices[loop.vertex_index]
                if v_old < len(vcolors):
                    colourData[loop_idx].color = vcolors[v_old]

        # Vertex group weight mapping
        if 'boneIDs' in meshData and 'boneassignments' in geometry.keys():
            vgroups = geometry['boneassignments']
            for vgname, vgroup in vgroups.items():
                grp = ob.vertex_groups.new(name=vgname)
                for (v_old, w) in vgroup:
                    if v_old in index_map:
                        grp.add([index_map[v_old]], w, 'REPLACE')

        if 'skeleton' in meshData:
            skeletonName = meshData['skeletonName']
            mod = ob.modifiers.new('OgreSkeleton', 'ARMATURE')
            mod.object = bpy.data.objects[skeletonName]
            mod.use_bone_envelopes = False
            mod.use_vertex_groups = True

        # Shape keys setup
        if 'poses' in meshData:
            base = None
            for pose in meshData['poses']:
                if(pose['submesh'] == subMeshIndex):
                    if base is None:
                        base = ob.shape_key_add(name='Basis')
                    name = pose['name']
                    shape = ob.shape_key_add(name=name)
                    for vkey in pose['data']:
                        # Pose indices refer to the original Ogre vertex array;
                        # remap to the compacted per-submesh vertex list.
                        v_idx = index_map.get(vkey[0])
                        if v_idx is not None and v_idx < len(base.data):
                            b = base.data[v_idx].co
                            me.shape_keys.key_blocks[name].data[v_idx].co = \
                                [vkey[1] + b[0], vkey[2] + b[1], vkey[3] + b[2]]

        me.validate()
        me.update()

        # Face smooth configurations
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))

        # Split custom normals assignment loop
        if hasNormals:
            split = []
            for loop in me.loops:
                v = loop.vertex_index
                if v < len(normals):
                    n = normals[v]
                    mag = (n[0]**2 + n[1]**2 + n[2]**2) ** 0.5
                    if mag > 0.0001:
                        split.append((n[0]/mag, n[1]/mag, n[2]/mag))
                    else:
                        split.append((0.0, 0.0, 1.0))
                else:
                    split.append((0.0, 0.0, 1.0))

            if len(split) == len(me.loops):
                me.normals_split_custom_set(split)

        me.update()
        allObjects.append(ob)

    return allObjects


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
    # No mode switches or operators needed. 'OGREID' is set as a custom property
    # on edit bones during import and persists on the armature's Bone data
    # (not on pose bones).
    boneMap = {}

    for bone in arm.data.bones:
        if 'OGREID' in bone:
            boneMap[str(bone['OGREID'])] = bone.name
            
    return boneMap


def load(operator, context, filepath, xml_converter=None, keep_xml=True,
         import_normals=True, import_shapekeys=True,
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

    if os.path.isfile(pathMaterial):
        #  FIX 1: Ensure your exact-match material file is added to the list!
        meshMaterials.append(pathMaterial)
    else:
        # Search directory for any fallback .material file
        for filename in os.listdir(folder):
            if filename.lower().endswith(".material"):
                pathMaterial = os.path.join(folder, filename)
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
                        bpy.context.scene.render.fps = int(round(fps))
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
        bCreateMesh(meshData, folder, onlyName, pathMeshXml)
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
