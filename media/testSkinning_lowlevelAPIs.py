
from libcalab import m, lua, control
import media.rendermodule_ogre as RE
import numpy as np
import pdb, math
import ctypes

import Ogre as ogre


def frameMove(elapsed):
    global entity, g_time, node
    g_time+=elapsed
    skel=entity.getSkeleton()
    skel.getBone(0).setOrientation(ogre.Quaternion(ogre.Degree(g_time*10), ogre.Vector3(0, 0, 1)))
    skel.getBone(1).setOrientation(ogre.Quaternion(ogre.Degree(g_time*150), ogre.Vector3(0, 1, 0)))

    RE.draw('Sphere',skel.getBone(0)._getDerivedPosition()*100+node.getPosition(), 'root joint pos', 'red', 3)
    RE.draw('Sphere',skel.getBone(1)._getDerivedPosition()*100+node.getPosition(), 'child joint pos', 'blue', 3)
    print(g_time)


g_time=0

this=RE.createMainWin()
RE.turnOffSoftShadows()  # For faster rendering, since libcalab_examples.git uses stencil shadows, which are slow.

skel_mgr = ogre.SkeletonManager.getSingleton()
skeleton = skel_mgr.create("MySkeleton", ogre.ResourceGroupManager.DEFAULT_RESOURCE_GROUP_NAME, True)

# create bones
root_bone = skeleton.createBone("root")
root_bone.setPosition(0, 0, 0)

child_bone = skeleton.createBone("child")
child_bone.setPosition(0, 0.5, 0)

root_bone.addChild(child_bone)

skeleton.setBindingPose()
#skeleton.load() 


#skeleton._notifyManualBonesDirty()   # important in some bindings
#skeleton.prepare()
#print(RE.ohi._ctx.getRoot().getSingleton().getVersion())
#ogre.ResourceGroupManager.getSingleton().initialiseAllResourceGroups()


skel = ogre.SkeletonManager.getSingleton().getByName("MySkeleton")
print("Skeleton found:", skel is not None)
print("loaded:", skel.isLoaded())
print("bones:", skel.getNumBones())

mesh_mgr = ogre.MeshManager.getSingleton()
mesh = mesh_mgr.createManual("MyMesh", ogre.ResourceGroupManager.DEFAULT_RESOURCE_GROUP_NAME)

submesh = mesh.createSubMesh()
submesh.useSharedVertices = True
submesh.operationType = ogre.RenderOperation.OT_LINE_LIST

vertex_data = ogre.VertexData()
mesh.sharedVertexData = vertex_data
vertex_data.vertexCount = 3

decl = vertex_data.vertexDeclaration
offset = 0

decl.addElement(0, offset, ogre.VET_FLOAT3, ogre.VES_POSITION)
offset += ogre.VertexElement.getTypeSize(ogre.VET_FLOAT3)

vbuf = ogre.HardwareBufferManager.getSingleton().createVertexBuffer(
    offset,
    3,
    ogre.HardwareBuffer.HBU_STATIC_WRITE_ONLY
)


# lock buffer
ptr = vbuf.lock(ogre.HardwareBuffer.HBL_DISCARD)

# convert to void*
c_ptr = ctypes.c_void_p(int(ptr))
import ctypes

float_array = (ctypes.c_float * 9)(
    0, 0, 0,   # vertex 0
    0, 0.5, 0,    # vertex 1
    0.5, 0.5, 0    # vertex 2
)

ctypes.memmove(c_ptr, float_array, ctypes.sizeof(float_array))
vbuf.unlock()

vertex_data.vertexBufferBinding.setBinding(0, vbuf)


icount=4
submesh.indexData.indexStart = 0
submesh.indexData.indexCount = icount

ibuf = ogre.HardwareBufferManager.getSingleton().createIndexBuffer(
    ogre.HardwareIndexBuffer.IT_16BIT,
    icount,
    ogre.HardwareBuffer.HBU_STATIC_WRITE_ONLY
)

submesh.indexData.indexBuffer = ibuf

ptr = ibuf.lock(ogre.HardwareBuffer.HBL_DISCARD)
c_ptr = ctypes.c_void_p(int(ptr))

ushort_array = (ctypes.c_ushort * icount)(0, 1,1,2)
ctypes.memmove(c_ptr, ushort_array, ctypes.sizeof(ushort_array))

ibuf.unlock()

mesh._setBounds(ogre.AxisAlignedBox(ogre.Vector3(-1,-1,-1), ogre.Vector3(1,1,1)));
mesh._setBoundingSphereRadius(1.0);

mesh.setSkeletonName("MySkeleton")
# vertex 0 → root
assign = ogre.VertexBoneAssignment()
assign.vertexIndex = 0
assign.boneIndex = root_bone.getHandle()
assign.weight = 1.0
mesh.addBoneAssignment(assign)

# vertex 1 → child
assign = ogre.VertexBoneAssignment()
assign.vertexIndex = 1
assign.boneIndex = child_bone.getHandle()
assign.weight = 1.0
mesh.addBoneAssignment(assign)

# vertex 2 → child
assign = ogre.VertexBoneAssignment()
assign.vertexIndex = 2
assign.boneIndex = child_bone.getHandle()
assign.weight = 1.0
mesh.addBoneAssignment(assign)

mesh._compileBoneAssignments()

mesh.load();

scene_manager=RE.ogreSceneManager()
entity = scene_manager.createEntity("MyMesh")

node = scene_manager.getRootSceneNode().createChildSceneNode()
node.attachObject(entity)
node.setScale(ogre.Vector3(100,100,100))
node.setPosition(ogre.Vector3(0,50,0))

skel2=entity.getSkeleton()
skel2.getBone(0).setManuallyControlled(True)
skel2.getBone(1).setManuallyControlled(True)
#entity.getSkeleton().setManualBone(sdd

m.startMainLoop()
