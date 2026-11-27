import bpy
from bpy_extras import anim_utils
from mathutils import Matrix
import math
import os
import re
import subprocess
import shutil
from . import animation_file

SHOW_EXPORT_DUMPS = False
SHOW_EXPORT_TRACE = False
SHOW_EXPORT_TRACE_VX = False


def hash_combine(x, y):
    return x ^ y + 0x9e3779b9 + (x << 6) + (x >> 2)


def get_is_hidden(obj):
    return obj.hide_viewport  # 2.8


def set_is_hidden(obj, isHidden):
    obj.hide_viewport = isHidden


def get_uv_textures(mesh):
    return mesh.uv_layers


class VertexInfo(object):
    def __init__(self, px, py, pz,
                 nx, ny, nz,
                 u, v,
                 r, g, b, a,
                 boneWeights,
                 original,
                 tangent,
                 binormal):
        self.px = px
        self.py = py
        self.pz = pz
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.u = u
        self.v = v
        self.r = r
        self.g = g
        self.b = b
        self.a = a
        self.tangent = tangent
        self.binormal = binormal
        self.boneWeights = boneWeights
        self.original = original

    '''does not compare ogre_vidx (and position at the moment)
      [ no need to compare position ]'''

    def __eq__(self, o):
        if self.nx != o.nx or self.ny != o.ny or self.nz != o.nz:
            return False
        elif self.px != o.px or self.py != o.py or self.pz != o.pz:
            return False
        elif self.u != o.u or self.v != o.v:
            return False
        elif self.r != o.r or self.g != o.g or self.b != o.b:
            return False
        elif self.tangent and self.tangent[3] != o.tangent[3]:
            return False
        return True

    def __hash__(self):
        result = hash(self.px)
        result = hash_combine(result, hash(self.py))
        result = hash_combine(result, hash(self.pz))
        result = hash_combine(result, hash(self.nx))
        result = hash_combine(result, hash(self.ny))
        result = hash_combine(result, hash(self.nz))
        result = hash_combine(result, hash(self.u))
        result = hash_combine(result, hash(self.v))
        result = hash_combine(result, hash(self.r))
        result = hash_combine(result, hash(self.g))
        result = hash_combine(result, hash(self.b))
        if self.tangent:
            result = hash_combine(result, hash(self.tangent[3]))
        return result


########################################

class Bone(object):
    def __init__(self, bone):
        self.name = bone.name
        self.parent = bone.parent.name if bone.parent else None


class Skeleton(object):
    def __init__(self, ob, sort):
        self.armature = ob if ob.type == 'ARMATURE' else ob.find_armature()
        self.name = self.armature.name
        self.ids = {}
        self.hidden = get_is_hidden(self.armature)
        data = self.armature.data
        set_is_hidden(self.armature, False)

        # get ogre bone ids - need to be in edit mode to access edit_bones
        prev = bpy.context.object
        set_active_object(bpy.context, self.armature)
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        for bone in data.edit_bones:
            if 'OGREID' in bone:
                self.ids[bone.name] = bone['OGREID']

        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        set_active_object(bpy.context, prev)
        set_is_hidden(self.armature, self.hidden)

        # Allocate bone ids
        index = 0
        missing = []
        self.bones = [None] * len(data.bones)

        if sort == 'ALPHA':
            them_bones = sorted(data.bones, key=lambda x: x.name)
            for i, bone in enumerate(them_bones):
                self.bones[i] = bone
                self.ids[bone.name] = i
                print(i, bone.name)

        else:
            for bone in data.bones:
                if bone.name in self.ids:
                    self.bones[self.ids[bone.name]] = bone
                else:
                    missing.append(bone)
            for bone in missing:
                while self.bones[index]:
                    index += 1
                self.bones[index] = bone
                self.ids[bone.name] = index

        # calculate bone rest matrices
        rot = Matrix.Rotation(-1.5707963, 4, 'X')  # Rotate to y-up coordinates
        fix = Matrix.Rotation(1.5707963, 4, 'Z')   # Fix bone axis
        fix = fix @ Matrix.Rotation(3.141592653, 4, 'X')
        self.rest = [None] * len(self.bones)
        for i, bone in enumerate(self.bones):
            if bone.parent:
                m_inner = bone.parent.matrix_local @ fix @ rot
                self.rest[i] = m_inner.inverted() @ bone.matrix_local @ fix @ rot
            else:
                self.rest[i] = rot @ bone.matrix_local @ fix @ rot

            # Change bones list to local structure, due to blender bone
            # structures being cleared if you switch to edit mode again
            self.bones[i] = Bone(bone)

    def bone_id(self, name):
        return self.ids[name]

    def export_xml(self, doc, root):
        bones = doc.createElement('bones')
        root.appendChild(bones)
        bh = doc.createElement('bonehierarchy')
        root.appendChild(bh)

        for i, bone in enumerate(self.bones):
            print(i, bone)

            b = doc.createElement('bone')
            b.setAttribute('name', bone.name)
            b.setAttribute('id', str(i))
            bones.appendChild(b)

            if bone.parent:
                bp = doc.createElement('boneparent')
                bp.setAttribute('bone', bone.name)
                bp.setAttribute('parent', bone.parent)
                bh.appendChild(bp)

            mat = self.rest[i]
            pos = doc.createElement('position')
            b.appendChild(pos)

            x, y, z = mat.to_translation()
            pos.setAttribute('x', '%6f' % x)
            pos.setAttribute('y', '%6f' % y)
            pos.setAttribute('z', '%6f' % z)

            rot = doc.createElement('rotation')
            b.appendChild(rot)

            q = mat.to_quaternion()
            rot.setAttribute('angle', '%6f' % q.angle)
            axis = doc.createElement('axis')
            rot.appendChild(axis)

            x, y, z = q.axis
            axis.setAttribute('x', '%6f' % x)
            axis.setAttribute('y', '%6f' % y)
            axis.setAttribute('z', '%6f' % z)

#########################################


def blender_collect_animation_data(meshData, action_names=None, sample_rate=None):
    if 'skeleton' not in meshData:
        return
    armature = meshData['skeleton'].armature
    animdata = armature.animation_data
    if animdata:
        # (action, slot) pairs; slotted actions need the slot to be known
        actions = []

        def addAction(act, slot):
            if act is None or slot is None:
                return
            if not any(a == act and s == slot for a, s in actions):
                actions.append((act, slot))

        # Current action
        addAction(animdata.action, animdata.action_slot)
        # actions in NLA
        for track in animdata.nla_tracks:
            for strip in track.strips:
                addAction(strip.action, strip.action_slot)

        if action_names is not None:
            actions = [(a, s) for a, s in actions if a.name in action_names]

        # Export them all
        scene = bpy.context.scene
        currentFrame = scene.frame_current
        currentAction = animdata.action
        currentSlot = animdata.action_slot
        meshData['animations'] = []
        for act, slot in actions:
            channelbag = anim_utils.action_get_channelbag_for_slot(act, slot)
            if channelbag is None or len(channelbag.fcurves) == 0:
                # Keep empty actions as empty animations. Torchlight 2 needs
                # the empty "Bind" animation, and import creates it as an
                # empty action.
                print('Action', act.name, 'has no F-Curves, exporting empty')
                meshData['animations'].append({'name': act.name,
                                               'length': 0.0,
                                               'keyframes': {}})
                continue
            print('Action', act.name)

            # Frame range from the keyframes of this slot's F-Curves
            frames = [kp.co[0] for fc in channelbag.fcurves
                      for kp in fc.keyframe_points]
            if frames:
                frame_range = (min(frames), max(frames))
            else:
                frame_range = tuple(act.frame_range)

            animdata.action = act
            animdata.action_slot = slot
            animation = {}
            animation['keyframes'] = blender_sample_pose_keyframes(
                armature,
                frame_range,
                scene.render.fps,
                scene.frame_step,
                sample_rate)
            # Slot names carry a 2-char ID prefix ("OB"); keep action name
            animation['name'] = act.name
            animation['length'] = (frame_range[1] -
                                   frame_range[0]) / scene.render.fps
            meshData['animations'].append(animation)

        animdata.action = currentAction
        if currentAction is not None:
            animdata.action_slot = currentSlot
        scene.frame_set(currentFrame)


def blender_sample_pose_keyframes(armature, frame_range, fps, step=1,
                                  sample_rate=None):
    start, end = frame_range

    keyframes = {}
    for bone in armature.pose.bones:
        keyframes[bone.name] = [[], [], []]   # pos, rot, scl

    fix1 = Matrix([(1, 0, 0), (0, 0, 1), (0, -1, 0)])  # swap YZ & negate some
    fix2 = Matrix([(0, 1, 0), (0, 0, 1), (1, 0, 0)])

    # Get base matrices
    mat = {}
    hidden = get_is_hidden(armature)
    set_is_hidden(armature, False)
    prev = bpy.context.object
    set_active_object(bpy.context, armature)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    for b in armature.data.edit_bones:
        if b.parent:
            mat[b.name] = fix2 @ b.parent.matrix.to_3x3().transposed() @ b.matrix.to_3x3()
        else:
            mat[b.name] = fix1 @ b.matrix.to_3x3()
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    set_active_object(bpy.context, prev)
    set_is_hidden(armature, hidden)

    # Reset the pose, so bones without F-Curves in this action export the
    # rest pose and not a leftover pose
    for bone in armature.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)

    # Times to sample: (time in seconds, frame, subframe)
    samples = []
    if sample_rate is None:
        for frame in range(int(start), int(end)+1, step):
            samples.append(((frame - start) / fps, frame, 0.0))
    else:
        length = (end - start) / fps
        times = [k / sample_rate
                 for k in range(int(length * sample_rate + 1e-6) + 1)]
        if length - times[-1] > 1e-6:
            times.append(length)
        for time in times:
            exact = start + time * fps
            frame = int(math.floor(exact + 1e-6))
            samples.append((time, frame, max(0.0, exact - frame)))

    # Collect data
    for time, frame, subframe in samples:
        bpy.context.scene.frame_set(frame, subframe=subframe)
        for bone in armature.pose.bones:
            loc = bone.location
            rot = bone.rotation_quaternion.normalized()
            scl = bone.scale

            # transform transation into parent coordinates
            loc = mat[bone.name] @ loc

            keyframes[bone.name][0].append((time, (loc[0], loc[1], loc[2])))
            keyframes[bone.name][1].append(
                (time, (rot[0], rot[1], rot[2], rot[3])))
            keyframes[bone.name][2].append((time, (scl[0], scl[1], scl[2])))

    # Remove unnessesary tracks
    identity = [(0, 0, 0), (1, 0, 0, 0), (1, 1, 1)]
    for bone, data in keyframes.items():
        for track in range(3):
            used = False
            for key in data[track]:
                if used:
                    break
                for i in range(len(identity[track])):
                    if abs(key[1][i] - identity[track][i]) > 1e-5:
                        used = True
                        break
            if not used:
                data[track] = []

        # Delete whole track if unused
        if not (data[0] or data[1] or data[2]):
            keyframes[bone] = None
        else:
            _prune_constant_keyframes(data)

    return keyframes


def _prune_constant_keyframes(data, tolerance=1e-5):
    """Remove keyframes that equal both neighbours (lossless for linear
    interpolation). The first and last keyframes always stay, so a track
    never loses all its keys. All used channels (pos, rot, scl) drop the
    same frames, because xml_save_animation reads them with one shared index."""
    used = [channel for channel in data if channel]
    count = len(used[0])
    if count < 3:
        return

    def same(channel, a, b):
        return all(abs(x - y) <= tolerance
                   for x, y in zip(channel[a][1], channel[b][1]))

    keep = [0]
    for i in range(1, count - 1):
        if not all(same(ch, i, i - 1) and same(ch, i, i + 1) for ch in used):
            keep.append(i)
    keep.append(count - 1)

    if len(keep) == count:
        return
    for n in range(3):
        if data[n]:
            data[n] = [data[n][i] for i in keep]


def xml_save_animations(animations, xNode, xDoc):
    xAnimations = xDoc.createElement("animations")
    xNode.appendChild(xAnimations)

    for animation in animations:
        xml_save_animation(animation, xDoc, xAnimations)


def xml_save_animation(animation, xDoc, xAnimations):
    anim = xDoc.createElement('animation')
    tracks = xDoc.createElement('tracks')
    xAnimations.appendChild(anim)
    anim.appendChild(tracks)
    anim.setAttribute('name', animation['name'])
    anim.setAttribute('length', '%6f' % animation['length'])
    keyframes = animation['keyframes']
    for bone, data in keyframes.items():
        if not data:
            continue
        track = xDoc.createElement('track')
        keyframes = xDoc.createElement('keyframes')
        track.setAttribute('bone', bone)
        tracks.appendChild(track)
        track.appendChild(keyframes)

        basis = 0 if data[0] else 1 if data[1] else 2

        for frame in range(len(data[basis])):
            keyframe = xDoc.createElement('keyframe')
            keyframes.appendChild(keyframe)
            keyframe.setAttribute('time', '%6f' % data[basis][frame][0])

            if data[0]:
                loc = data[0][frame][1]
                translate = xDoc.createElement('translate')
                translate.setAttribute('x', '%6f' % loc[0])
                translate.setAttribute('y', '%6f' % loc[1])
                translate.setAttribute('z', '%6f' % loc[2])
                keyframe.appendChild(translate)

            if data[1]:
                rot = data[1][frame][1]
                angle = math.acos(rot[0]) * 2
                length = math.sqrt(rot[1]*rot[1] + rot[2]*rot[2]
                                   + rot[3]*rot[3])
                axis = (1, 0, 0) if length == 0 \
                    else (rot[1]/length, rot[2]/length, rot[3]/length)

                rotate = xDoc.createElement('rotate')
                raxis = xDoc.createElement('axis')
                rotate.setAttribute('angle', '%6f' % angle)
                raxis.setAttribute('x', '%6f' % axis[1])
                raxis.setAttribute('y', '%6f' % axis[2])
                raxis.setAttribute('z', '%6f' % axis[0])
                keyframe.appendChild(rotate)
                rotate.appendChild(raxis)

            if data[2]:
                scl = data[2][frame][1]
                scale = xDoc.createElement('scale')
                scale.setAttribute('x', '%6f' % scl[0])
                scale.setAttribute('y', '%6f' % scl[1])
                scale.setAttribute('z', '%6f' % scl[2])
                keyframe.appendChild(scale)


def set_active_object(context, obj):
    context.view_layer.objects.active = obj


def file_exist(filepath):
    try:
        filein = open(filepath)
        filein.close()
        return True
    except Exception:
        print("No file: ", filepath)
        return False


def to_fmt_str(number):
    # return str("%0.7f" % number)
    return str(round(number, 7))


def indent(indent):
    """Indentation.

       @param indent Level of indentation.
       @return String.
    """
    return "        "*indent


def xml_save_geometry(geometry, xDoc, xMesh):
    # I guess positions (vertices) must be there always
    vertices = geometry['positions']

    geometryType = "geometry"

    isNormals = False
    if 'normals' in geometry:
        isNormals = True
        normals = geometry['normals']

    isTexCoordsSets = False
    texCoordSets = geometry['texcoordsets']
    if texCoordSets > 0 and 'uvsets' in geometry:
        isTexCoordsSets = True
        uvSets = geometry['uvsets']

    isColours = False
    if 'colours' in geometry:
        isColours = True
        colours = geometry['colours']

    isTangents = False
    if 'tangents' in geometry:
        isTangents = True
        tangents = geometry['tangents']
    isParity = isTangents and geometry['parity']

    isBinormals = False
    if 'binormals' in geometry:
        isBinormals = True
        binormals = geometry['binormals']

    xGeometry = xDoc.createElement(geometryType)
    xGeometry.setAttribute("vertexcount", str(len(vertices)))
    xMesh.appendChild(xGeometry)

    xVertexBuffer = xDoc.createElement("vertexbuffer")
    xVertexBuffer.setAttribute("positions", "true")
    if isNormals:
        xVertexBuffer.setAttribute("normals", "true")
    if isTexCoordsSets:
        xVertexBuffer.setAttribute("texture_coord_dimensions_0", "2")
        xVertexBuffer.setAttribute("texture_coords", "1")

    if isColours:
        xVertexBuffer.setAttribute("colours_diffuse", "true")
    if isTangents:
        xVertexBuffer.setAttribute("tangents", "true")
        if isParity:
            xVertexBuffer.setAttribute("tangent_dimensions", "4")
    if isBinormals:
        xVertexBuffer.setAttribute("binormals", "true")

    xGeometry.appendChild(xVertexBuffer)

    for i, vx in enumerate(vertices):
        xVertex = xDoc.createElement("vertex")
        xVertexBuffer.appendChild(xVertex)
        xPosition = xDoc.createElement("position")
        xPosition.setAttribute("x", to_fmt_str(vx[0]))
        xPosition.setAttribute("y", to_fmt_str(vx[2]))
        xPosition.setAttribute("z", to_fmt_str(-vx[1]))
        xVertex.appendChild(xPosition)

        if isNormals:
            xNormal = xDoc.createElement("normal")
            xNormal.setAttribute("x", to_fmt_str(normals[i][0]))
            xNormal.setAttribute("y", to_fmt_str(normals[i][2]))
            xNormal.setAttribute("z", to_fmt_str(-normals[i][1]))
            xVertex.appendChild(xNormal)

        if isTexCoordsSets:
            xUVSet = xDoc.createElement("texcoord")
            # take only 1st set for now
            xUVSet.setAttribute("u", to_fmt_str(uvSets[i][0][0]))
            xUVSet.setAttribute("v", to_fmt_str(1.0 - uvSets[i][0][1]))
            xVertex.appendChild(xUVSet)

        if isColours:
            xColour = xDoc.createElement("colour_diffuse")
            xColour.setAttribute("value", '%g %g %g, %g' %
                                 (colours[i][0], colours[i][1],
                                  colours[i][2], colours[i][3]))
            xVertex.appendChild(xColour)

        if isTangents:
            xTangent = xDoc.createElement("tangent")
            xTangent.setAttribute("x", to_fmt_str(tangents[i][0]))
            xTangent.setAttribute("y", to_fmt_str(tangents[i][2]))
            xTangent.setAttribute("z", to_fmt_str(-tangents[i][1]))
            if isParity:
                xTangent.setAttribute("w", to_fmt_str(tangents[i][3]))
            xVertex.appendChild(xTangent)

        if isBinormals:
            xBinormal = xDoc.createElement("binormal")
            xBinormal.setAttribute("x", to_fmt_str(binormals[i][0]))
            xBinormal.setAttribute("y", to_fmt_str(binormals[i][2]))
            xBinormal.setAttribute("z", to_fmt_str(-binormals[i][1]))
            xVertex.appendChild(xBinormal)


def xml_save_submeshes(meshData, xDoc, xMesh, hasSharedGeometry=False):
    xSubMeshes = xDoc.createElement("submeshes")
    xMesh.appendChild(xSubMeshes)

    for submesh in meshData['submeshes']:
        xSubMesh = xDoc.createElement("submesh")
        xSubMesh.setAttribute("material", submesh['material'])
        numVerts = len(submesh['geometry']['positions'])
        xSubMesh.setAttribute("usesharedvertices", "false")
        xSubMesh.setAttribute("use32bitindexes", str(bool(numVerts > 65535)))
        xSubMesh.setAttribute("operationtype", "triangle_list")
        xSubMeshes.appendChild(xSubMesh)
        # write all faces
        if 'faces' in submesh:
            faces = submesh['faces']
            xFaces = xDoc.createElement("faces")
            xFaces.setAttribute("count", str(len(faces)))
            xSubMesh.appendChild(xFaces)
            for face in faces:
                xFace = xDoc.createElement("face")
                xFace.setAttribute("v1", str(face[0]))
                xFace.setAttribute("v2", str(face[1]))
                xFace.setAttribute("v3", str(face[2]))
                xFaces.appendChild(xFace)
        # if there is geometry per sub mesh
        if 'geometry' in submesh:
            geometry = submesh['geometry']
            xml_save_geometry(geometry, xDoc, xSubMesh)
        # boneassignments
        if 'skeleton' in meshData:
            skeleton = meshData['skeleton']
            xBoneAssignments = xDoc.createElement("boneassignments")
            for vxIdx, vxBoneAsg in enumerate(
                    submesh['geometry']['boneassignments']):
                for boneAndWeight in vxBoneAsg:
                    boneName = boneAndWeight[0]
                    boneWeight = boneAndWeight[1]
                    xVxBoneassignment = xDoc.createElement(
                        "vertexboneassignment")
                    xVxBoneassignment.setAttribute("vertexindex", str(vxIdx))
                    xVxBoneassignment.setAttribute(
                        "boneindex", str(skeleton.bone_id(boneName)))
                    xVxBoneassignment.setAttribute(
                        "weight", '%6f' % boneWeight)
                    xBoneAssignments.appendChild(xVxBoneassignment)
            xSubMesh.appendChild(xBoneAssignments)


def xml_save_poses(meshData, xDoc, xMesh):
    xPoses = xDoc.createElement("poses")
    xMesh.appendChild(xPoses)
    for index, submesh in enumerate(meshData['submeshes']):
        if not submesh['poses']:
            continue
        for name in submesh['poses']:
            xPose = xDoc.createElement("pose")
            xPose.setAttribute('target', 'submesh')
            xPose.setAttribute('index', str(index))
            xPose.setAttribute('name', name)
            xPoses.appendChild(xPose)
            pose = submesh['poses'][name]
            for v in pose:
                xPoseVertex = xDoc.createElement('poseoffset')
                xPoseVertex.setAttribute('index', str(v[0]))
                xPoseVertex.setAttribute('x', '%6f' % v[1])
                xPoseVertex.setAttribute('y', '%6f' % v[3])
                xPoseVertex.setAttribute('z', '%6f' % -v[2])
                xPose.appendChild(xPoseVertex)


def xml_write_skeleton(skeleton, animations, xmlfile):
    from xml.dom.minidom import Document

    xDoc = Document()
    xRoot = xDoc.createElement("skeleton")
    xDoc.appendChild(xRoot)
    skeleton.export_xml(xDoc, xRoot)

    if animations is not None:
        xml_save_animations(animations, xRoot, xDoc)

    data = xDoc.toprettyxml(indent='    ')
    with open(xmlfile, 'wb') as f:
        f.write(bytes(data, 'utf-8'))


def get_animation_file_name(name):
    """Return the file name for an action: upper case, with characters
    that are not allowed in file names replaced by "_"."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).upper() + ".SKELETON"


def is_empty_animation(animation):
    return animation['length'] == 0 and not any(animation['keyframes'].values())


def xml_save_skeleton_data(blenderMeshData, filepath, animation_files='SINGLE'):
    if 'skeleton' in blenderMeshData:
        nameOnly = os.path.splitext(filepath)[0]  # removing .mesh
        skeleton = blenderMeshData['skeleton']
        animations = blenderMeshData.get('animations')
        if animation_files == 'TL2' and animations is not None:
            # The main skeleton has only the empty Bind animation.
            # Every other animation goes to its own file.
            folder = os.path.dirname(filepath)
            files = []
            for animation in animations:
                if not is_empty_animation(animation):
                    path = os.path.join(
                        folder, get_animation_file_name(animation['name'])) + ".xml"
                    xml_write_skeleton(skeleton, [animation], path)
                    files.append(path)
            blenderMeshData['skeleton_files'] = files
            animations = [{'name': 'Bind', 'length': 0.0, 'keyframes': {}}]
        xml_write_skeleton(skeleton, animations, nameOnly + ".skeleton.xml")


def xml_save_mesh_data(meshData, filepath, export_skeleton):
    from xml.dom.minidom import Document

    hasSharedGeometry = False

    # Create the minidom document
    print("Creating " + filepath + ".xml")
    xDoc = Document()

    xMesh = xDoc.createElement("mesh")
    xDoc.appendChild(xMesh)

    if hasSharedGeometry:
        geometry = meshData['sharedgeometry']
        xml_save_geometry(geometry, xDoc, xMesh)

    xml_save_submeshes(meshData, xDoc, xMesh, hasSharedGeometry)

    if 'has_poses' in meshData:
        xml_save_poses(meshData, xDoc, xMesh)

    # skeleton link only
    if 'skeleton' in meshData:
        xSkeletonlink = xDoc.createElement("skeletonlink")
        # default skeleton
        linkSkeletonName = meshData['skeleton'].name
        if export_skeleton:
            nameDotMeshDotXml = os.path.split(filepath)[1].lower()
            nameDotMesh = os.path.splitext(nameDotMeshDotXml)[0]
            linkSkeletonName = os.path.splitext(nameDotMesh)[0]
        xSkeletonlink.setAttribute("name", linkSkeletonName+".skeleton")
        xMesh.appendChild(xSkeletonlink)

    # Print our newly created XML
    fileWr = open(filepath + ".xml", 'w')
    fileWr.write(xDoc.toprettyxml(indent="    "))  # 4 spaces
    fileWr.close()


def xml_save_material_data(filepath, meshData, overwriteMaterialFlag, copyTextures):
    if 'materials' not in meshData:
        return

    allMatData = meshData['materials']

    if len(allMatData) <= 0:
        print('Mesh has no materials')
        return

    matFile = os.path.splitext(filepath)[0]  # removing .mesh
    matFile = matFile + ".material"
    print("material file: %s" % matFile)
    isMaterial = os.path.isfile(matFile)

    # if is no material file, or we are forced to overwrite it,
    # write the material file
    if isMaterial is False or overwriteMaterialFlag is True:
        # write material
        fileWr = open(matFile, 'w')
        for matName, matInfo in allMatData.items():
            fileWr.write("material %s\n" % matName)
            fileWr.write("{\n")
            fileWr.write(indent(1) + "technique\n" + indent(1) + "{\n")
            fileWr.write(indent(2) + "pass\n" + indent(2) + "{\n")

            # write material content here
            fileWr.write(indent(3) + "ambient %f %f %f\n" %
                         (matInfo['ambient'][0], matInfo['ambient'][1],
                             matInfo['ambient'][2]))
            fileWr.write(indent(3) + "diffuse %f %f %f\n" %
                         (matInfo['diffuse'][0], matInfo['diffuse'][1],
                             matInfo['diffuse'][2]))
            fileWr.write(indent(3) + "specular %f %f %f 0\n" %
                         (matInfo['specular'][0], matInfo['specular'][1],
                             matInfo['specular'][2]))
            fileWr.write(indent(3) + "emissive %f %f %f\n" %
                         (matInfo['emissive'][0], matInfo['emissive'][1],
                             matInfo['emissive'][2]))

            if 'textures' in matInfo:
                for texInfo in matInfo['textures']:
                    fileWr.write(indent(3) + "texture_unit\n" +
                                 indent(3) + "{\n")
                    fileWr.write(indent(4) + "texture %s\n" %
                                 texInfo['texture'])
                    fileWr.write(indent(3) + "}\n")  # texture unit

            fileWr.write(indent(2) + "}\n")  # pass
            fileWr.write(indent(1) + "}\n")  # technique
            fileWr.write("}\n")

        fileWr.close()

    # try to copy material textures to destination
    if copyTextures:
        for matName, matInfo in allMatData.items():
            if 'textures' in matInfo:
                for texInfo in matInfo['textures']:
                    if 'texture_path' in texInfo:
                        srcTextureFile = texInfo['texture_path']
                        baseDirName = os.path.dirname(bpy.data.filepath)
                        if srcTextureFile[0:2] == "//":
                            print("Converting relative image name \"%s\"" %
                                  srcTextureFile)
                            srcTextureFile = os.path.join(
                                baseDirName, srcTextureFile[2:])
                        if file_exist(srcTextureFile):
                            # copy texture to dir
                            print("Copying texture \"%s\"" % srcTextureFile)
                            try:
                                print(" to \"%s\"" % os.path.dirname(matFile))
                                shutil.copy(srcTextureFile,
                                            os.path.dirname(matFile))
                            except Exception:
                                print("Error copying \"%s\"" % srcTextureFile)
                        else:
                            print(
                                "Can't copy texture \"%s\" because file does "
                                "not exists!" % srcTextureFile)


def _pick_color_data(mesh, exportColour):
    """Return (colour_data, alpha_data) from mesh.color_attributes.

    Alpha comes from an attribute named 'alpha'; colour from the first
    CORNER-domain attribute that is not the alpha one.
    """
    colourData = alphaData = None
    if not (exportColour and mesh.color_attributes):
        return colourData, alphaData
    for attr in mesh.color_attributes:
        if attr.name.lower() == 'alpha':
            alphaData = attr.data
            break
    for attr in mesh.color_attributes:
        if attr.domain == 'CORNER' and attr.name.lower() != 'alpha':
            return attr.data, alphaData
    for attr in mesh.color_attributes:
        if attr.domain == 'CORNER':
            return attr.data, alphaData
    return colourData, alphaData


def _vertex_bone_weights(ob, vertex):
    """Return {vertex_group_name: weight} for a mesh vertex (weight > 0.01)."""
    weights = {}
    groups = ob.vertex_groups
    for g in vertex.groups:
        if g.weight > 0.01 and g.group < len(groups):
            weights[groups[g.group].name] = g.weight
    return weights


def blender_collect_mesh_data(meshData, context, selectedObjects,
                              applyModifiers, exportColour, exportTangents,
                              exportBinormals, exportPoses):
    import bmesh
    import sys
    depsgraph = context.evaluated_depsgraph_get()
    meshData['submeshes'] = []
    # Per-object copies: an object without UVs must not disable tangents
    # for the objects that follow it.
    wantTangents, wantBinormals = exportTangents, exportBinormals
    for ob in selectedObjects:
        exportTangents, exportBinormals = wantTangents, wantBinormals
        materials = []
        for mat in ob.data.materials:
            if mat:
                materials.append(mat)
            else:
                print('[WARNING:] Bad material data in', ob)
                # borrowed from ogre scene exporter
                materials.append('_missing_material_')

        if not materials:
            materials.append('_missing_material_')
        _sm_faces_ = []
        _sm_verts_ = []
        _sm_maps_ = []
        for matidx, mat in enumerate(materials):
            _sm_faces_.append([])
            _sm_verts_.append([])
            _sm_maps_.append({})

        tobj = ob.evaluated_get(depsgraph) \
            if applyModifiers else ob
        mesh = tobj.to_mesh()

        # use bmesh to triangulate
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

        # Tangents (split normals are always available via corner_normals)
        if not mesh.uv_layers.active:
            exportTangents = exportBinormals = False
        if exportTangents:
            mesh.calc_tangents(mesh.uv_layers.active.name)

        # pick uv data
        uvData = mesh.uv_layers.active.data if mesh.uv_layers.active else None

        # Pick colour data
        colourData, alphaData = _pick_color_data(mesh, exportColour)

        import sys
        progressScale = 1.0 / max(len(mesh.polygons) - 1, 1)
        for fidx, face in enumerate(mesh.polygons):
            faces = _sm_faces_[face.material_index]
            # Ogre only supports triangles
            tris = []
            tris.append((face.vertices[0], face.vertices[1], face.vertices[2]))

            if len(face.vertices) >= 4:
                tris.append(
                    (face.vertices[0], face.vertices[2], face.vertices[3]))

            # Progress
            percent = fidx * progressScale
            sys.stdout.write("\rVertices [" + '=' * int(percent*50) + '>' +
                             '.' * int(50-percent*50) + "] " +
                             str(int(percent*10000)/100.0) + "%   ")
            sys.stdout.flush()

            # should be triangles
            if len(face.vertices) != 3:
                raise ValueError('Polygon not a triangle')

            # Add triangle
            newFaceVx = []
            for i in range(3):
                vertex = face.vertices[i]
                loop = face.loop_indices[i]

                px, py, pz = mesh.vertices[vertex].co
                nx, ny, nz = mesh.corner_normals[loop].vector
                u, v = uvData[loop].uv if uvData else (0, 0)
                r, g, b = colourData[loop].color[:3] if colourData else (1, 1, 1)
                a = alphaData[loop].color[0] if alphaData else 1

                tangent = mesh.loops[loop].tangent[:] + \
                    (mesh.loops[loop].bitangent_sign,
                     ) if exportTangents else None
                binormal = mesh.loops[loop].bitangent * - \
                    1 if exportBinormals else None

                boneWeights = _vertex_bone_weights(ob, mesh.vertices[vertex])

                # Add vertex
                vert = VertexInfo(px, py, pz,
                                  nx, ny, nz,
                                  u, v,
                                  r, g, b, a,
                                  boneWeights,
                                  vertex,
                                  tangent,
                                  binormal)

                vmap = _sm_maps_[face.material_index]
                newVxIdx = vmap.get(vert)
                if newVxIdx is None:
                    newVxIdx = len(_sm_verts_[face.material_index])
                    _sm_verts_[face.material_index].append(vert)
                    vmap[vert] = newVxIdx
                newFaceVx.append(newVxIdx)

            faces.append(newFaceVx)
        for matidx, mat in enumerate(materials):
            normals = []
            tangents = []
            binormals = []
            positions = []
            uvTex = []
            colours = []
            boneAssignments = []
            needsParity = False

            # vertex groups of object
            for vxInfo in _sm_verts_[matidx]:
                positions.append([vxInfo.px, vxInfo.py, vxInfo.pz])
                normals.append([vxInfo.nx, vxInfo.ny, vxInfo.nz])
                uvTex.append([[vxInfo.u, vxInfo.v]])
                colours.append([vxInfo.r, vxInfo.g, vxInfo.b, vxInfo.a])

                boneWeights = []
                for boneW in vxInfo.boneWeights.keys():
                    boneWeights.append([boneW, vxInfo.boneWeights[boneW]])
                boneAssignments.append(boneWeights)

            if exportTangents:
                for vxInfo in _sm_verts_[matidx]:
                    tangents.append(vxInfo.tangent)
                    binormals.append(vxInfo.binormal)

                if not exportBinormals:
                    for vxInfo in _sm_verts_[matidx]:
                        if vxInfo.tangent[3] < 0:
                            needsParity = True
                            break

            # Shape keys - poses
            poses = None
            if exportPoses and mesh.shape_keys and mesh.shape_keys.key_blocks:
                poses = {}
                for pose in mesh.shape_keys.key_blocks:
                    if pose.relative_key:
                        poseData = []
                        for index, v in enumerate(_sm_verts_[matidx]):
                            base = pose.relative_key.data[v.original].co
                            pos = pose.data[v.original].co
                            x = pos[0] - base[0]
                            y = pos[1] - base[1]
                            z = pos[2] - base[2]
                            if x != 0 or y != 0 or z != 0:
                                poseData.append((index, x, y, z))
                        if poseData:
                            poses[pose.name] = poseData

            subMeshData = {}
            subMeshData['geometry'] = {}
            subMeshData['geometry']['positions'] = positions
            subMeshData['geometry']['normals'] = normals
            subMeshData['geometry']['texcoordsets'] = len(get_uv_textures(mesh))

            if uvData:
                subMeshData['geometry']['uvsets'] = uvTex
            if colourData or alphaData:
                subMeshData['geometry']['colours'] = colours
            if exportTangents:
                subMeshData['geometry']['tangents'] = tangents
                subMeshData['geometry']['parity'] = needsParity
            if exportBinormals:
                subMeshData['geometry']['binormals'] = binormals

            # need bone name to bone ID dict
            subMeshData['geometry']['boneassignments'] = boneAssignments

            subMeshData['material'] = mat.name
            subMeshData['faces'] = _sm_faces_[matidx]
            subMeshData['geometry']['poses'] = poses
            if poses:
                subMeshData['geometry']['has_poses'] = True
            meshData['submeshes'].append(subMeshData)

    return meshData


def blender_collect_mesh_data_original(meshData, context, selectedObjects,
                                       applyModifiers, exportColour,
                                       exportTangents, exportBinormals,
                                       exportPoses):
    import bmesh
    depsgraph = context.evaluated_depsgraph_get()
    subMeshesData = []
    # Per-object copies: an object without UVs must not disable tangents
    # for the objects that follow it.
    wantTangents, wantBinormals = exportTangents, exportBinormals
    for ob in selectedObjects:
        exportTangents, exportBinormals = wantTangents, wantBinormals
        subMeshData = {}
        materialName = ob.name
        for m in ob.data.materials:
            if m:
                materialName = m.name
        tobj = ob.evaluated_get(depsgraph) \
            if applyModifiers else ob
        mesh = tobj.to_mesh()

        # use bmesh to triangulate
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

        # Tangents (split normals are always available via corner_normals)
        if not mesh.uv_layers.active:
            exportTangents = exportBinormals = False
        if exportTangents:
            mesh.calc_tangents(mesh.uv_layers.active.name)

        # pick uv data
        uvData = mesh.uv_layers.active.data if mesh.uv_layers.active else None

        # Pick colour data
        colourData, alphaData = _pick_color_data(mesh, exportColour)

        vertexList = []
        newFaces = []

        map = {}

        import sys
        progressScale = 1.0 / max(len(mesh.polygons) - 1, 1)

        for fidx, face in enumerate(mesh.polygons):
            tris = []
            tris.append((face.vertices[0], face.vertices[1], face.vertices[2]))
            if(len(face.vertices) >= 4):
                tris.append((face.vertices[0],
                             face.vertices[2],
                             face.vertices[3]))
            if SHOW_EXPORT_TRACE_VX:
                print("_face: " + str(fidx) + " indices [" +
                      str(list(face.vertices)) + "]")

            # Progress
            percent = fidx * progressScale
            sys.stdout.write("\rVertices [" + '=' * int(percent*50) + '>' +
                             '.' * int(50-percent*50) + "] " +
                             str(int(percent*10000)/100.0) + "%   ")
            sys.stdout.flush()

            # should be triangles
            if len(face.vertices) != 3:
                raise ValueError('Polygon not a triangle')

            # Add triangle
            newFaceVx = []
            for i in range(3):
                vertex = face.vertices[i]
                loop = face.loop_indices[i]

                px, py, pz = mesh.vertices[vertex].co
                nx, ny, nz = mesh.corner_normals[loop].vector
                u, v = uvData[loop].uv if uvData else (0, 0)
                r, g, b = colourData[loop].color[:3] if colourData else (1, 1, 1)
                a = alphaData[loop].color[0] if alphaData else 1

                tangent = mesh.loops[loop].tangent[:] + \
                    (mesh.loops[loop].bitangent_sign,
                     ) if exportTangents else None
                binormal = mesh.loops[loop].bitangent * - \
                    1 if exportBinormals else None

                boneWeights = _vertex_bone_weights(ob, mesh.vertices[vertex])

                # Add vertex
                vert = VertexInfo(px, py, pz,
                                  nx, ny, nz,
                                  u, v,
                                  r, g, b, a,
                                  boneWeights,
                                  vertex,
                                  tangent,
                                  binormal)

                newVxIdx = map.get(vert)
                if newVxIdx is None:
                    newVxIdx = len(vertexList)
                    vertexList.append(vert)
                    map[vert] = newVxIdx
                newFaceVx.append(newVxIdx)

            newFaces.append(newFaceVx)

        # geometry
        geometry = {}
        faces = []
        normals = []
        tangents = []
        binormals = []
        positions = []
        uvTex = []
        colours = []
        # vertex groups of object
        boneAssignments = []
        faces = newFaces
        needsParity = False

        for vxInfo in vertexList:
            positions.append([vxInfo.px, vxInfo.py, vxInfo.pz])
            normals.append([vxInfo.nx, vxInfo.ny, vxInfo.nz])
            uvTex.append([[vxInfo.u, vxInfo.v]])
            colours.append([vxInfo.r, vxInfo.g, vxInfo.b, vxInfo.a])

            boneWeights = []
            for boneW in vxInfo.boneWeights.keys():
                boneWeights.append([boneW, vxInfo.boneWeights[boneW]])
            boneAssignments.append(boneWeights)

        if exportTangents:
            for vxInfo in vertexList:
                tangents.append(vxInfo.tangent)
                binormals.append(vxInfo.binormal)

            if not exportBinormals:
                for vxInfo in vertexList:
                    if vxInfo.tangent[3] < 0:
                        needsParity = True
                        break

        if SHOW_EXPORT_TRACE_VX:
            print("uvTex:")
            print(uvTex)
            print("boneAssignments:")
            print(boneAssignments)

        # Shape keys - poses
        poses = None
        if exportPoses and mesh.shape_keys and mesh.shape_keys.key_blocks:
            poses = {}
            for pose in mesh.shape_keys.key_blocks:
                if pose.relative_key:
                    poseData = []
                    for index, v in enumerate(vertexList):
                        base = pose.relative_key.data[v.original].co
                        pos = pose.data[v.original].co
                        x = pos[0] - base[0]
                        y = pos[1] - base[1]
                        z = pos[2] - base[2]
                        if x != 0 or y != 0 or z != 0:
                            poseData.append((index, x, y, z))
                    if poseData:
                        poses[pose.name] = poseData

        geometry['positions'] = positions
        geometry['normals'] = normals
        geometry['texcoordsets'] = len(get_uv_textures(mesh))
        if SHOW_EXPORT_TRACE:
            print("texcoordsets: " + str(len(get_uv_textures(mesh))))
        if uvData:
            geometry['uvsets'] = uvTex
        if colourData or alphaData:
            geometry['colours'] = colours
        if exportTangents:
            geometry['tangents'] = tangents
            geometry['parity'] = needsParity
        if exportBinormals:
            geometry['binormals'] = binormals

        # need bone name to bone ID dict
        geometry['boneassignments'] = boneAssignments

        subMeshData['material'] = materialName
        subMeshData['faces'] = faces
        subMeshData['geometry'] = geometry
        subMeshData['poses'] = poses

        subMeshesData.append(subMeshData)

        if poses:
            meshData['has_poses'] = True

        # if mesh was newly created with modifiers, remove the mesh
        if applyModifiers:
            bpy.data.meshes.remove(mesh)

    meshData['submeshes'] = subMeshesData

    return meshData


def blender_collect_skeleton_data(blenderMeshData, selectedObjects, sort):
    if SHOW_EXPORT_TRACE:
        print("bpy.data.armatures = %s" % bpy.data.armatures)

    # TODO: for now just take armature of first selected object
    if selectedObjects[0].find_armature():
        # creates and parses blender skeleton
        skeleton = Skeleton(selectedObjects[0], sort)

        blenderMeshData['skeleton'] = skeleton


def blender_collect_material_data(blenderMeshData, selectedObjects):
    allMaterials = {}
    blenderMeshData['materials'] = allMaterials

    for ob in selectedObjects:
        if ob.type == 'MESH' and len(ob.data.materials) > 0:
            for mat in ob.data.materials:
                if mat and mat.name not in allMaterials:
                    matInfo = {}
                    bsdf = None
                    if mat.node_tree:
                        bsdf = next((n for n in mat.node_tree.nodes
                                     if n.bl_idname == 'ShaderNodeBsdfPrincipled'),
                                    None)
                    if bsdf is None:
                        print(f"Warning: No Principled BSDF in material '{mat.name}', skipping.")
                        continue
                    allMaterials[mat.name] = matInfo

                    # ambient  - none in eevee
                    # TL2 Default values
                    matInfo['ambient'] = [0.588, 0.588, 0.588]
                    # diffuse
                    matInfo['diffuse'] = [bsdf.inputs['Base Color']
                                          .default_value[0],
                                          bsdf.inputs['Base Color']
                                          .default_value[1],
                                          bsdf.inputs['Base Color']
                                          .default_value[2]]
                    # specular - Ogre specular is a color; Blender 5.x has a
                    # scalar 'Specular IOR Level' (default 0.5) and a
                    # 'Specular Tint' color. Export tint * level, but keep
                    # the TL2 default (black) when the level is unlinked
                    # at its default / zero.
                    # TL2 Default values
                    matInfo['specular'] = [0, 0, 0]
                    specLevel = bsdf.inputs['Specular IOR Level']
                    specTint = bsdf.inputs['Specular Tint']
                    if not specLevel.is_linked and \
                            abs(specLevel.default_value - 0.5) > 1e-6:
                        matInfo['specular'] = [
                            specTint.default_value[i] * specLevel.default_value
                            for i in range(3)]

                    # emissive: Principled BSDF 'Emission Color' x strength
                    # (used when the import-time EmissionR/G/B nodes are absent)
                    emissionR = mat.node_tree.nodes.get('EmissionR', None)
                    emissionG = mat.node_tree.nodes.get('EmissionG', None)
                    emissionB = mat.node_tree.nodes.get('EmissionB', None)
                    if emissionR is not None\
                        and emissionG is not None\
                            and emissionB is not None:
                        # Node setup created during import
                        matInfo['emissive'] = [
                            emissionR.inputs['Strength'].default_value,
                            emissionG.inputs['Strength'].default_value,
                            emissionB.inputs['Strength'].default_value
                        ]
                    else:
                        emisColor = bsdf.inputs['Emission Color']
                        emisStrength = bsdf.inputs['Emission Strength']
                        if not emisColor.is_linked and \
                                emisStrength.default_value > 0.0:
                            matInfo['emissive'] = [
                                emisColor.default_value[i] *
                                emisStrength.default_value
                                for i in range(3)]
                        else:
                            # TL2 Default values
                            matInfo['emissive'] = [0.4, 0.4, 0.4]

                    # texture
                    textures = [x for x in mat.node_tree.nodes
                                if x.bl_idname == 'ShaderNodeTexImage']
                    if len(textures) > 0:
                        matInfo['textures'] = []
                        for texImage in textures:
                            if texImage and texImage.image:
                                texInfo = {}
                                texInfo['texture'] = \
                                    get_texture_file_name(texImage.image)
                                texInfo['texture_path'] = \
                                    texImage.image.filepath
                                matInfo['textures'].append(texInfo)




def xml_convert_file(converter, xmlpath, keep_xml=False, edge_lists=False):
    """Convert one .xml file to binary with OgreXMLConverter. Return True on success.

    The .xml file stays when the conversion fails, so the user can look at it."""
    args = [converter, xmlpath] if edge_lists else [converter, "-e", xmlpath]
    try:
        code = subprocess.call(args)
    except OSError:
        print("Error: Could not run", converter)
        return False
    if code != 0 or not os.path.isfile(xmlpath[:-len(".xml")]):
        return False
    if not keep_xml:
        os.unlink(xmlpath)
    return True


def xml_to_ogre_convert(blenderMeshData, filepath, ogreXMLconverter,
                        export_skeleton, keep_xml, export_edgelists=False):
    """Convert the exported .xml files. Return True when all conversions worked."""

    if ogreXMLconverter is None:
        return False

    # use Ogre XML converter  xml -> binary
    xml_files = [filepath + ".xml"]                               # mesh
    if 'skeleton' in blenderMeshData and export_skeleton:
        skelFile = os.path.splitext(filepath)[0]  # removing .mesh
        xml_files.append(skelFile + ".skeleton.xml")              # skeleton
        xml_files += blenderMeshData.get('skeleton_files', [])    # animation files

    success = True
    for xmlFilepath in xml_files:
        # convert all files, also when one conversion fails
        if not xml_convert_file(ogreXMLconverter, xmlFilepath, keep_xml,
                                export_edgelists):
            success = False
    return success


def find_animation_file(folder, stem=None):
    """Return the path of the .ANIMATION file in the folder, or None.

    With a stem, find the file with this name. The match ignores case.
    Without a stem, find the only .ANIMATION file in the folder.
    """
    found = [f for f in os.listdir(folder)
             if f.lower().endswith('.animation')
             and (stem is None or f.lower() == (stem + '.animation').lower())]
    return os.path.join(folder, found[0]) if len(found) == 1 else None


def blender_update_animation_file(operator, path, animations):
    """Add an entry to the .ANIMATION file for each exported animation."""
    entries = [(get_animation_file_name(a['name']).lower(), a['name'], a['length'])
               for a in animations if not is_empty_animation(a)]
    name = os.path.basename(path)
    try:
        added, skipped = animation_file.update_animation_file(path, entries)
    except (ValueError, OSError) as e:
        operator.report({'WARNING'}, "%s did not change: %s" % (name, e))
        return
    operator.report({'INFO'}, "%s: %d entries added, %d already there"
                    % (name, len(added), len(skipped)))


def save_animations(operator, context, directory, xml_converter=None,
                    keep_xml=False, export_bonesort='ALPHA',
                    sample_rate='30', actions='ALL',
                    update_animation_file=False):
    """Export the actions of the active armature as .SKELETON files, with no mesh."""
    armature = context.active_object
    if armature is None or armature.type != 'ARMATURE':
        operator.report({'ERROR'}, "Select an armature first.")
        return {'CANCELLED'}
    if xml_converter is None:
        operator.report({'ERROR'},
                        "OgreXMLConverter not found. Set path in Addon Preferences.")
        return {'CANCELLED'}

    skeleton = Skeleton(armature, export_bonesort)
    animdata = armature.animation_data
    names = None                                  # ALL
    if actions == 'ACTIVE':
        names = [animdata.action.name] if animdata and animdata.action else []
    elif actions == 'SELECTED':                   # selected NLA tracks
        names = [s.action.name
                 for t in (animdata.nla_tracks if animdata else []) if t.select
                 for s in t.strips if s.action]

    data = {'skeleton': skeleton}
    rate = None if sample_rate == 'SCENE' else float(sample_rate)
    blender_collect_animation_data(data, names, rate)
    animations = [a for a in data.get('animations', [])
                  if not is_empty_animation(a)]
    if not animations:
        operator.report({'WARNING'}, "No animations to export")
        return {'CANCELLED'}

    files = [get_animation_file_name(a['name']) for a in animations]
    if len({f.lower() for f in files}) != len(files):
        operator.report({'ERROR'}, "Two actions give the same file name")
        return {'CANCELLED'}

    converted = []
    failed = []
    replaced = 0
    for animation, name in zip(animations, files):
        binary = os.path.join(directory, name)
        existed = os.path.isfile(binary)
        xmlpath = binary + ".xml"
        xml_write_skeleton(skeleton, [animation], xmlpath)
        if xml_convert_file(xml_converter, xmlpath, keep_xml):
            converted.append(animation)
            replaced += existed
        else:
            failed.append(name)

    if failed:
        operator.report({'ERROR'}, "Could not convert: %s. The .xml files stay"
                        " in the folder." % ", ".join(failed))
    if not converted:
        return {'CANCELLED'}
    operator.report({'INFO'}, "Exported %d animations" % len(converted))
    if replaced:
        operator.report({'INFO'}, "%d existing files were replaced" % replaced)

    if update_animation_file:
        path = find_animation_file(directory)
        if path is None:
            operator.report({'WARNING'},
                            "There is not exactly one .ANIMATION file in the"
                            " folder. The file did not change.")
        else:
            blender_update_animation_file(operator, path, converted)
    return {'FINISHED'}


def select_get(obj):
    return obj.select_get()


def get_texture_file_name(image):
    """Return the texture file name to write in the .material file.

    Use the file name of the image, not the name of the Blender image.
    Blender adds ".001" to the name when two images use the same file."""
    if image.filepath:
        name = os.path.basename(bpy.path.abspath(image.filepath))
        if name:
            return name
    # No file (for example a packed image): remove a ".001" style suffix
    return re.sub(r'(\.[A-Za-z0-9]+)\.\d{3,}$', r'\1', image.name)


def save(operator, context, filepath,
         xml_converter=None,
         keep_xml=False,
         export_edgelists=False,
         export_tangents=False,
         export_binormals=False,
         export_colour=False,
         tangent_parity=False,
         apply_transform=True,
         apply_modifiers=True,
         export_materials=True,
         overwrite_material=False,
         copy_textures=False,
         export_skeleton=False,
         enable_by_material=False,
         export_poses=False,
         export_animation=False,
         export_bonesort='ALPHA',
         animation_files='SINGLE',
         sample_rate='SCENE',
         update_animation_file=False
         ):

    # just check if there is extension - .mesh
    if '.mesh' not in filepath.lower():
        filepath = filepath + ".mesh"

    print("saving...")
    print(str(filepath))

    # get mesh data from selected objects
    selectedObjects = []
    scn = context.scene
    for ob in scn.objects:
        if select_get(ob) is True and ob.type != 'ARMATURE':
            selectedObjects.append(ob)

    if len(selectedObjects) == 0:
        print("No objects selected for export.")
        operator.report({'WARNING'}, "No objects selected for export")
        return ('CANCELLED')

    # go to the object mode
    for ob in bpy.data.objects:
        bpy.ops.object.mode_set(mode='OBJECT')

    # apply transform
    if apply_transform:
        bpy.ops.object.transform_apply(rotation=True, scale=True)

    # Save Mesh
    blenderMeshData = {}

    # skeleton
    blender_collect_skeleton_data(blenderMeshData, selectedObjects, export_bonesort)

    # A skinned mesh must be exported in the bind pose. Applying the modifiers
    # would apply the current pose through the Armature modifier.
    armature = (blenderMeshData['skeleton'].armature
                if 'skeleton' in blenderMeshData else None)
    pose_position = None
    if armature is not None and apply_modifiers:
        pose_position = armature.data.pose_position
        armature.data.pose_position = 'REST'
        context.view_layer.update()

    # mesh
    # TODO: Turn this into a factory pattern. Need to follow DRY.
    try:
        if enable_by_material:
            blender_collect_mesh_data(blenderMeshData, context,
                                      selectedObjects,
                                      apply_modifiers,
                                      export_colour,
                                      export_tangents,
                                      export_binormals,
                                      export_poses)
        else:
            blender_collect_mesh_data_original(blenderMeshData, context,
                                               selectedObjects,
                                               apply_modifiers,
                                               export_colour,
                                               export_tangents,
                                               export_binormals,
                                               export_poses)
    finally:
        if pose_position is not None:
            armature.data.pose_position = pose_position
            context.view_layer.update()
    # materials
    if export_materials:
        blender_collect_material_data(blenderMeshData, selectedObjects)

    if tangent_parity:
        # Honor the "Parity in W" checkbox: store parity in the tangent W component.
        # Only applies when tangents are exported without binormals, since parity
        # replaces the binormal. Otherwise keep the value computed during collection.
        for submesh in blenderMeshData.get('submeshes', []):
            geometry = submesh.get('geometry')
            if geometry is not None and 'tangents' in geometry and 'binormals' not in geometry:
                geometry['parity'] = True

    if export_animation:
        rate = None if sample_rate == 'SCENE' else float(sample_rate)
        blender_collect_animation_data(blenderMeshData, sample_rate=rate)
        if animation_files == 'TL2':
            # Names that differ only in case give the same file on Windows
            names = [get_animation_file_name(a['name'])
                     for a in blenderMeshData.get('animations', [])
                     if not is_empty_animation(a)]
            if len(set(n.lower() for n in names)) != len(names):
                operator.report({'ERROR'}, "Two actions give the same file name")
                return {'CANCELLED'}

    if SHOW_EXPORT_TRACE:
        print(blenderMeshData['materials'])

    if SHOW_EXPORT_DUMPS:
        dumpFile = filepath + ".EDump"
        fileWr = open(dumpFile, 'w')
        fileWr.write(str(blenderMeshData))
        fileWr.close()

    if export_skeleton:
        xml_save_skeleton_data(blenderMeshData, filepath, animation_files)

    xml_save_mesh_data(blenderMeshData, filepath, export_skeleton)

    xml_save_material_data(filepath,
                           blenderMeshData,
                           overwrite_material,
                           copy_textures)

    converted = xml_to_ogre_convert(blenderMeshData,
                                    filepath,
                                    xml_converter,
                                    export_skeleton,
                                    keep_xml,
                                    export_edgelists)
    if not converted:
        operator.report({'WARNING'}, "Failed to convert .xml files. "
                        "The .xml files that failed stay in the folder.")

    if update_animation_file:
        if (animation_files != 'TL2' or not export_skeleton
                or not export_animation or 'animations' not in blenderMeshData):
            operator.report({'WARNING'},
                            "The .ANIMATION file needs the Torchlight 2 layout"
                            " with skeleton and animations.")
        elif not converted:
            operator.report({'WARNING'},
                            "The .ANIMATION file did not change, because a"
                            " conversion failed.")
        else:
            folder = os.path.dirname(filepath)
            stem = os.path.splitext(os.path.basename(filepath))[0]
            path = (find_animation_file(folder, stem)
                    or os.path.join(folder, stem + ".ANIMATION"))
            blender_update_animation_file(operator, path,
                                          blenderMeshData['animations'])

    print("done.")

    return {'FINISHED'}
