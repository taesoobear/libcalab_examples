from libcalab import m, lua, control
from libcalab import RE as RE_consolemode
# here the RE above denotes the console mode rendermodule. ( rendermodule != rendermodule_ogre)
import Ogre # pip install ogre-python
import Ogre.RTShader
import Ogre.Bites
import Ogre.Numpy
import Ogre.HighPy as ohi
import Ogre.ImGui as imgui
import time,sys,os,math, random
import pdb, traceback
import ctypes
from pathlib import Path
import subprocess, re
import __main__
import numpy as np
import weakref
import platform
useFSAA=False

_layoutHeight=500
_capture_frame=None
_ui_scale=1
# private 
doNotGarbageCollect=[] # list of instances which should not be garbage collected. (e.g. loaders)
_mouseInfo=None
_window_data=None
_layout=None
_luaEnv=None
_objectList=None
_activeBillboards={}
_softKill=False
_debugMode=False
_frameMoveObjects=[]
_frameMoveObjects2=[] # after frameMove
_cameraEventReceivers=[]
_cacheCylinderMeshes={}
_cacheBoxMeshes={}
_start_time = time.time()
_inputTranslationNecessary={'setPosition':True, 'setScale':True, 'setOrientation':True, 'rotate':True, 'translate':True, 'scale':True}
_outputTranslationNecessary={'getPosition':True, 'getScale':True, 'getParent':True, '_getDerivedOrientation':True, '_getDerivedScale':True, '_getDerivedPosition':True, 'getOrientation':True, 'createChildSceneNode':True}
_prevMouse=(0,0,1)
_outputs={} # debug outputs
_drawOutput=False
_timeline=None
doNotGarbageCollect=[] # list of instances which should not be garbage collected. (e.g. loaders)

SceneGraph=RE_consolemode.SceneGraph
FBXloader=RE_consolemode.FBXloader

def output(key, *args):
    global _outputs
    _outputs[key]=str(args)


def output2(key,*args):
    output(key,*args)

class _Application(ohi._Application):
    def oneTimeConfig(self):
        global useFSAA
        self.getRoot().restoreConfig()
        rs = self.getRoot().getRenderSystemByName("OpenGL 3+ Rendering Subsystem")
        if useFSAA:
            rs.setConfigOption("FSAA", "4")
            rs.setConfigOption("VSync", "Yes")
        else:
            # faster
            rs.setConfigOption("FSAA", "0")
            rs.setConfigOption("VSync", "No")
        self.getRoot().setRenderSystem(rs)
        self.getRoot().saveConfig()
        return True

if True:
    # define splat function
    def read_splat_ply(filename):
        f = open(filename, 'rb')

        if f.readline().strip() != b"ply":
            raise ValueError("Not a ply file")

        f.readline() # endianess
        num_vertices = int(f.readline().strip().split()[2])

        # expect format as below

        NUM_PROPS=0

        name_to_idx={}
        while True:
            line=re.sub(br"\s+", b"", f.readline().strip()) # remove spaces

            name_to_idx[line]=NUM_PROPS
            if line==b"end_header":
                break
            NUM_PROPS+=1

        data = np.frombuffer(f.read(), dtype=np.float32).reshape(num_vertices, NUM_PROPS)

        idx_xyz=name_to_idx[b'propertyfloatx']
        xyz = data[:, idx_xyz:idx_xyz+3]
        idx_sh=name_to_idx[b'propertyfloatf_dc_0']
        sh = data[:, idx_sh:idx_sh+3]
        idx_opacity=name_to_idx[b'propertyfloatopacity']
        opacity = data[:, idx_opacity:idx_opacity+1]
        idx_scale=name_to_idx[b'propertyfloatscale_0']
        scale = np.exp(data[:, idx_scale:idx_scale+3])
        idx_rot=name_to_idx[b'propertyfloatrot_0']
        rot = data[:, idx_rot:idx_rot+4]
        # normalise quaternion
        rot = rot / np.linalg.norm(rot, axis=1)[:, None]

        return xyz, sh, opacity, scale, rot
    SH_C0 = 0.28209479177387814

    def sigmoid(x):
        return 1 / (1 + np.exp(-x))

    def sh0_to_diffuse(sh):
        return SH_C0 * sh + 0.5

    def compute_cov3d(scale, rot):
        q = toQuater(rot)
        mat = m.matrix3(q)

        S = np.diag(scale)
        M = mat.array @ S

        Cov = M @ M.T

        return np.diag(Cov), np.array([Cov[0, 1], Cov[0, 2], Cov[1, 2]], dtype=np.float32)

    def read_splat_ply_from_cache(input_ply):
        if isFileExist(input_ply+'.cached.npy'):
            print('loading '+input_ply+'.cached.npy')
            data=np.load(input_ply+'.cached.npy', allow_pickle=True).item()
            xyz=data['xyz']
            color=data['color']
            covd=data['covd']
            covu=data['covu']
        else:
            xyz, sh, opacity, scale, rot = read_splat_ply(input_ply)

            sh0 = sh[:, :3]
            color = np.clip(np.hstack((sh0_to_diffuse(sh0), sigmoid(opacity)))*255, 0, 255).astype(np.uint8)

            N = len(xyz)

            covd = np.empty((N, 3), dtype=np.float32)
            covu = np.empty((N, 3), dtype=np.float32)
            mod = (N - 1)//100

            for i, (s, r) in enumerate(zip(scale, rot)):
                covd[i], covu[i] = compute_cov3d(s, r)
                if i % mod == 0:
                    print(f"computing covariances {100*i/len(xyz):.0f}%", end="\r")
            np.save(input_ply+'.cached', {'xyz':xyz,'color': color, 'covd': covd, 'covu':covu})
        return xyz, color, covd, covu
    def ply_to_cache(new_ply_filename, xyz, color, covd, covu):
        np.save(new_ply_filename+'.cached', {'xyz':xyz,'color': color, 'covd': covd, 'covu':covu})
_gs_first=True
class GaussianSplat:
    def _createPositions(self, mesh):
        sub = mesh.getSubMesh(0);
        vertexBuffer = sub.vertexData.vertexBufferBinding.getBuffer(0);
        numVertices = sub.vertexData.vertexCount;
        vdecl = sub.vertexData.vertexDeclaration
        idata = sub.indexData;
        self.idata=idata
        import ctypes
        # Find POSITION element
        pos_elem = vdecl.findElementBySemantic(Ogre.VES_POSITION)
        mPositions=np.zeros((numVertices,3)).astype(np.half)
        ptr=vertexBuffer.lock(Ogre.HardwareBuffer.HBL_READ_ONLY)
        print(vertexBuffer.getSizeInBytes()/ numVertices)

        u16_ptr = ctypes.cast(int(ptr), ctypes.POINTER(ctypes.c_uint16))

        # zero-copy uint16 array
        raw = np.ctypeslib.as_array(
            u16_ptr, shape=(numVertices, 3)
        )

        # reinterpret uint16 → float16
        mPositions = raw.view(np.float16).copy()

        vertexBuffer.unlock()

        self.positions=mPositions
    def _createIndices(self, mesh):
        self._createPositions(mesh)
        # get positions for sorting
        sub = mesh.getSubMesh(0);
        idata=sub.indexData
        vertexBuffer = sub.vertexData.vertexBufferBinding.getBuffer(0);
        numVertices = sub.vertexData.vertexCount;
        # create index buffer
        idata.indexCount = numVertices;
        mIndexBuffer = vertexBuffer.getManager().createIndexBuffer(Ogre.HardwareIndexBuffer.IT_32BIT, numVertices, Ogre.HBU_CPU_TO_GPU);
        idata.indexBuffer = mIndexBuffer;

        indices_np= np.arange(numVertices, dtype=np.int32)
        buf = idata.indexBuffer.lock(
            0,
            numVertices * idata.indexBuffer.getIndexSize(),
            Ogre.HardwareBuffer.HBL_DISCARD
        )
        ctypes.memmove(int(buf), indices_np.ctypes.data, indices_np.nbytes)
        idata.indexBuffer.unlock()

    def __init__(self, node_name, filename, parentSceneNode=None):
        global _cameraEventReceivers, _frameMoveObjects2
        _cameraEventReceivers.append(weakref.ref(self))
        _frameMoveObjects2.append(weakref.ref(self))
        self.updateNecessary=True
        self.isVisible=True
        entity_name="_entity_"+node_name
        if isinstance(filename,  tuple):
            xyz, color, covd, covu=filename
            self.positions=xyz.astype(np.float32)
            self.mesh=ply_to_mesh(node_name+"_converted_mesh", (self.positions, color, covd, covu))
            self.entity= ogreSceneManager().createEntity( entity_name,node_name+"_converted_mesh")
            self._createIndices(self.entity.getMesh())
        elif filename[-5:]=='.mesh':
            if(Ogre.MeshManager.getSingleton().resourceExists(filename)):
                srcMesh=Ogre.MeshManager.getSingleton().getByName(filename)
                clonedMesh = srcMesh.clone(entity_name+"MyMesh_Clone", "General");
                self._createPositions(clonedMesh)
                self.entity=ogreSceneManager().createEntity(entity_name, clonedMesh)
            else:
                self.entity=ogreSceneManager().createEntity(entity_name, filename)
                self._createIndices(self.entity.getMesh())
        elif filename[-4:]=='.ply':
            self.mesh=ply_to_mesh(node_name+"_converted_mesh", filename)
            self.entity= ogreSceneManager().createEntity( entity_name,node_name+"_converted_mesh")
            self._createIndices(self.entity.getMesh())
        else:
            assert(False)

        rootnode=RE_consolemode.ogreRootSceneNode()
        if parentSceneNode is not None:
            rootnode=parentSceneNode
        self.node=rootnode.createChildSceneNode(node_name)
        self.node.attachObject(self.entity)
        self.node._update(True,False)
    def setVisible(self, bvalue):
        self.isVisible=bvalue
        self.node.setVisible(bvalue)
    def __del__(self):
        if removeEntity is not None:
            removeEntity(self.node)
        global _cameraEventReceivers, _frameMoveObjects2
        if _frameMoveObjects2 is not None:
            _frameMoveObjects2= [r for r in _frameMoveObjects2 if r() is not self]
        if _cameraEventReceivers is not None:
            # self 삭제.
            _cameraEventReceivers= [r for r in _cameraEventReceivers if r() is not self]
    def exportAsOgreMesh(self, filename):
        ser = Ogre.MeshSerializer()
        assert(filename[-5:]=='.mesh')
        ser.exportMesh(self.mesh, filename)
    def frameMove(self, elapsed):
        if self.updateNecessary and self.isVisible:
            #print('update', self.node.getName())
            global _window_data
            self.updateNecessary=False
            cam = _window_data.camera
            camPos=cam.getDerivedPosition()
            if True:
                localCamPos=self.node._getDerivedOrientation().inverse()*m.vector3(camPos.x, camPos.y, camPos.z)
                distances=self.positions@localCamPos.array
                idx=np.argsort(distances).astype(np.int32)
                idata=self.idata
                numVertices=self.positions.shape[0]
                buf = idata.indexBuffer.lock(
                    0,
                    numVertices * idata.indexBuffer.getIndexSize(),
                    Ogre.HardwareBuffer.HBL_DISCARD
                )
                ctypes.memmove(int(buf), idx.ctypes.data, idx.nbytes)
                idata.indexBuffer.unlock()


    def _update(self):
        self.updateNecessary=True

class SceneComponent_GaussianSplat(RE_consolemode.SceneComponent):
    def __init__(self,filename, **args):
        super().__init__(RE_consolemode.SceneComponent.NONE, **args)
        self.nodeId='splat_000'
        self._material=''
        self.source=filename
        self.splat=None
    def redraw(self):
        if self.splat is None:
            removeEntity(self.nodeId)
            rootnode=ogreRootSceneNode()
            self.pNode=rootnode.createChildSceneNode(self.nodeId)
            self.splat=GaussianSplat(self.nodeId+"_c0", self.source, self.pNode)
            self.pChildNode=SceneNodeWrap(self.splat.node)
            pCnode=self.pChildNode
            if self._localPosition is not None: pCnode.setPosition(self._localPosition)
            if self._localScale is not None: pCnode.setScale(self._localScale)
            if self._localOrientation is not None: pCnode.setOrientation(self._localOrientation)
            # these attributes are not for editing
            self._localPosition=None
            self._localScale=None
            self._localOrientation=None
            self.splat._update()
        self.setTransform()

def _tempFunc(self, filename, **args):
    entity=SceneComponent_GaussianSplat(filename, **args)
    self._add(entity)
    return entity
SceneGraph.addGaussianSplat=_tempFunc

def eraseAllDrawn():
    global _objectList, _activeBillboards,_layout
    if _objectList is not None:
        _objectList.clear()
    _activeBillboards={}
    _layout.layoutElements={}


def updateBillboards(fElapsedTime):
    # no longer necessary
    pass
class SceneManagerWrap:
    def __init__(self, mgr : Ogre.SceneManager):
        self.mgr=mgr
    def getSceneNode(self, name):
        pnode=self.mgr.getSceneNode(name)
        if pnode is None:
            return None
        return SceneNodeWrap(pnode)
    # default member access functions
    def __getattr__(self, name):
        return SceneManager_member(name, self.mgr)

class SceneManager_member:
    def __init__(self, name: str, mgr : Ogre.SceneManager):
        self.name=name
        self.mgr=mgr
    def __call__(self, *args):   
        memberfunc=getattr(self.mgr,self.name)
        ret=memberfunc(*args)
        return ret
# you can use the SceneNodeWrap class in the same way as Ogre.SceneNode
# basically, this is a way to inherit swig-bound c++ class in the python side.
# (pybind provides a much cleaner way but ogre-python uses swig.)
class SceneNodeWrap:
    def __init__(self, node : Ogre.SceneNode):
        self.sceneNode=node

    def getEntity(self):
        if self.sceneNode.numAttachedObjects()==0:
            return None
        name=self.sceneNode.getAttachedObject(0).getName()
        try:
            pEntity=ogreSceneManager().getEntity(name)
            return pEntity
        except:
            return None
    # default member access functions
    def __getattr__(self, name):
        return SceneNode_member(name, self.sceneNode)

class SceneNode_member:
    def __init__(self, name: str, node : Ogre.SceneNode):
        self.name=name
        self.sceneNode=node
    def __call__(self, *args):   
        global _outputTranslationNecessary, _inputTranslationNecessary
        memberfunc=getattr(self.sceneNode,self.name)
        if self.name in _inputTranslationNecessary:
            if isinstance(args[0], m.vector3) or isinstance(args[0], m.quater):
                ret=memberfunc(args[0]._toOgre(), *args[1:])
            else:
                ret=memberfunc(*args)
        else:
            ret=memberfunc(*args)
        if self.name in _outputTranslationNecessary:
            if isinstance(ret, Ogre.SceneNode):
                return SceneNodeWrap(ret)
            elif isinstance(ret, Ogre.Quaternion):
                return m.quater(ret.w, ret.x, ret.y, ret.z)
            elif isinstance(ret, Ogre.Vector3):
                return m.vector3(ret.x, ret.y, ret.z)
        return ret

def removeEntityByName(name):
    removeEntity(name)
def removeEntity(uid: str|Ogre.Node|Ogre.SceneNode|SceneNodeWrap):
    global _debugMode
    if isinstance(uid, str):
        uid=getSceneNode(uid)
    if isinstance(uid, Ogre.Node):
        # todo: is this the only way?
        uid=getSceneNode(uid.getName())

    if isinstance(uid, Ogre.SceneNode) or isinstance(uid, SceneNodeWrap):
        node=uid
        if node is not None:
            #uid=node.getName()
            #assert(getSceneNode(uid)==None)
            #try:
            if True:
                while(node.numAttachedObjects()):
                    mo=node.detachObject(0)
                    ogreSceneManager().destroyMovableObject(mo);

                while(node.numChildren()):
                    sceneNode=getSceneNode(node.getChild(0).getName())
                    if sceneNode is None:
                        print("???")
                        pdb.set_trace()

                    removeEntity(sceneNode)

                if _debugMode:
                    uid=node.getName()
                    print('destroying', uid)
                if isinstance(node, SceneNodeWrap):
                    assert(node.sceneNode is not None)
                    ogreSceneManager().destroySceneNode(node.sceneNode)
                    #node.getParentSceneNode().removeAndDestroyChild(node.sceneNode)
                    node.sceneNode=None
                else:
                    ogreSceneManager().destroySceneNode(node)
                    #node.getParentSceneNode().removeAndDestroyChild()
                
                if _debugMode:
                    assert(getSceneNode(uid)==None)

            #except Exception as e:
            #    print(e)
            #    print('error in removeEntity')
            #    pdb.set_trace()
        return
def getSceneNode( uid):
    try:
        assert(isinstance(uid, str))
        pNode=ogreSceneManager().getSceneNode(uid);
        return pNode
    except Exception as e:
        return None

class ObjectList:
    def _createChain(self, chain_name):
        scene_mgr=ogreSceneManager()
        if (scene_mgr.hasBillboardChain(chain_name)):
            line=scene_mgr.getBillboardChain(chain_name) 
            parentNode=line.getParentSceneNode()
            parentNode.detachObject(0)
            line.clearAllChains()
        else:
            line=scene_mgr.createBillboardChain(chain_name) 
        return line

    def __init__(self):
        global _frameMoveObjects
        self.uid=m.generateUniqueName()+"_"
        self.mRootSceneNode=ogreRootSceneNode().createChildSceneNode(self.uid)
        self.isVisible=True
        self._scheduledObjects=[]
        _frameMoveObjects.append(weakref.ref(self))
    def registerLayoutElement(self,name_id,  *args):
        global _layout
        _layout.layoutElements[name_id]=args
    def __del__(self):
        global _frameMoveObjects
        if _frameMoveObjects is not None:
            _frameMoveObjects= [r for r in _frameMoveObjects if r() is not self]
    
    def clear(self):
        removeEntity(self.mRootSceneNode)
        self.mRootSceneNode=ogreRootSceneNode().createChildSceneNode(self.uid)
        self._scheduledObjects=[]

    def erase(self, node_name):
        pnode =self._findNode(node_name)
        if pnode is not None:
            removeEntity(pnode)
            pnode =self._findNode(node_name)

    def _findNode(self, node_name):
        try:
            return self.mRootSceneNode.getChild(node_name)
        except:
            return None

    def _createSceneNode(self, node_name):
        removeEntity(node_name)
        node= self.mRootSceneNode.createChildSceneNode(node_name)
        return node

    def _registerObject(self, node_name, pObj):
        pNode=	self._createSceneNode(node_name);
        if pObj:
            pNode.attachObject(pObj)
        return pNode;

    def _materialToColor(self,materialName):
        mn=materialName.upper()
        if "RED" in mn:
            return m.vector3(1.0,0.0,0.0);
        if "BLUE" in mn:
            return m.vector3(0.0,0.2,0.8);
        if "GREEN" in mn:
            return m.vector3(0.1,0.9,0.1);
        if "WHITE" in mn:
            return m.vector3(1.0,1.0,1.0);
        if "GREY" in mn:
            return m.vector3(0.5,0.5,0.5);
        else :
            return m.vector3(0.0,0.0,1.0);
    def registerObject(self, node_name, typeName, materialName, data, thickness=0.7):
        return self._registerObject(node_name, self._createObject(node_name, typeName, materialName, data, thickness));

    def _createObject(self, node_name, tn, materialName, data, thickness):
        line=None
        if tn=="BillboardChain":
            if thickness==0:
                thickness=0.7
            line=self._createChain(node_name+"_obc")
            line.setMaxChainElements(data.rows())
            for i in range(data.rows()):
                r=data.row(i);
                width=r(6)
                texcoord=r(7)
                line.addChainElement(0, Ogre.BillboardChain_Element(r.toVector3(0)._toOgre(), width, texcoord, Ogre.ColourValue(r(3),r(4),r(5), 1), Ogre.Quaternion(1,0,0,0)));
            line.setMaterialName('use_vertexcolor_only', Ogre.RGN_DEFAULT)
            return line
        elif tn[:8]=='QuadList':
            if thickness==0:
                thickness=10
            normal=m.vector3(0,1,0);

            if(tn[-1:]=="Z"):
                normal=m.vector3(0,0,1);
            elif(tn[-1:]=="X"):
                normal=m.vector3(0,1,0);
            elif(tn[-1:]=="V"):
                vp=RE_consolemode.viewpoint()
                normal=vp.vat-vp.vpos
                normal.normalize();
                normal.scale(-1)
            if isinstance(data, m.matrixn):
                data=data.vec3ViewCol(0)
            quads=_QuadList(node_name, normal, thickness);
            quads.begin(data.size(), materialName);
            for i in range(data.size()):
                quads.quad(i, data(i));
            quads.end();
            return quads.manual;
        elif tn=='ColorBillboardLineList': # uses a colormap
            # use ColorBillboardLineList
            if thickness==0:
                thickness=0.7

            line=self._createChain(node_name+"_obc")
            line.setMaxChainElements(2)
            nchains=int(data.rows()/3)
            line.setNumberOfChains(nchains)
            tu1=0.0
            tu2=1.0
            for i in range(nchains):
                start=data.row(i*3).toVector3(0)
                end=data.row(i*3+1).toVector3(0)
                c=data.row(i*3+2).toVector3(0)
                line.addChainElement(i, Ogre.BillboardChain_Element(start._toOgre(), thickness, tu1, Ogre.ColourValue(c.x, c.y, c.z, 1), Ogre.Quaternion(1,0,0,0)));
                line.addChainElement(i, Ogre.BillboardChain_Element(end._toOgre(), thickness, tu2, Ogre.ColourValue(c.x, c.y, c.z, 1), Ogre.Quaternion(1,0,0,0)));
            line.setMaterialName(materialName, Ogre.RGN_DEFAULT)
            return line
        elif tn.endswith('LineList'):
            if thickness==0:
                thickness=0.7

            line=self._createChain(node_name+"_obc")
            line.setMaxChainElements(2)
            nchains=int(data.rows()/2)
            line.setNumberOfChains(nchains)
            c=self._materialToColor(materialName);
            tu1=0.0
            tu2=1.0
            for i in range(nchains):
                start=data.row(i*2).toVector3(0)
                end=data.row(i*2+1).toVector3(0)
                line.addChainElement(i, Ogre.BillboardChain_Element(start._toOgre(), thickness, tu1, Ogre.ColourValue(c.x, c.y, c.z, 1), Ogre.Quaternion(1,0,0,0)));
                line.addChainElement(i, Ogre.BillboardChain_Element(end._toOgre(), thickness, tu2, Ogre.ColourValue(c.x, c.y, c.z, 1), Ogre.Quaternion(1,0,0,0)));
            line.setUseVertexColours(True)
            line.setMaterialName('use_vertexcolor_only', Ogre.RGN_DEFAULT)
            return line
        elif tn.startswith('PointList'):
            if thickness==0:
                thickness=10

            vp=RE_consolemode.viewpoint()
            normal=vp.vat-vp.vpos
            normal.normalize();
            normal.scale(-1)
            if isinstance(data, m.vector3N):
                data=data.matView()

            mat='colormap'
            if materialName and  len(materialName)>0:
                if(materialName.startswith("Point")): # materials for ogre 1.0
                    mat="colormap"; # resort to the default material
                else:
                    mat=materialName;

            quads=_QuadList(node_name, normal, thickness);
            quads.begin(data.rows(), mat);

            if data.cols()==3:
                d=data.vec3ViewCol(0)
                for i in range(d.size()):
                    quads.color_quad(i, m.vector3(1,1,1), d(i),1);
            elif data.cols()==6:
                color=data.vec3ViewCol(0)
                d=data.vec3ViewCol(3)
                for i in range(d.size()):
                    quads.color_quad(i, color(i), d(i),color(i).z/thickness);
            else:
                assert(False)
            quads.end();

            return quads.manual;
        else:
            pdb.set_trace()
        return line;

    def registerEntityScheduled(self, filename, destroyTime):
        return self._registerObjectScheduled(RE_consolemode.ogreSceneManager().createEntity(m.generateUniqueName(), filename), destroyTime)

    def registerObjectScheduled(self, destroyTime, typeName, materialName, data, thickness=0.7):
        return self._registerObjectScheduled(self._createObject(m.generateUniqueName(), typeName, materialName, data, thickness), destroyTime);
    def _registerObjectScheduled(self, pObject, destroyTime):
        pNode=self._createSceneNode(m.generateUniqueName())
        if pObject is not None:
            pNode.attachObject(pObject)
        self._scheduledObjects.append([pNode, destroyTime])
        return pNode
    def frameMove(self, fElapsedTime):
        i=0
        while i<len(self._scheduledObjects):
            v=self._scheduledObjects[i]
            v[1]-=fElapsedTime
            if v[1]<0:
                removeEntity(v[0])
                self._scheduledObjects.pop(i)
            else:
                i+=1

    def eraseAllScheduled(self):
        for i ,v in enumerate(self._scheduledObjects):
            removeEntity(v[0])
        self._scheduledObjects=[]


    def registerEntity( self, node_name,  filename, materialName=None):
        pNode=	self._createSceneNode(node_name);
        pEntity=None
        if isinstance(filename, str):
            entity_name=f"_entity_{self.uid}_{node_name}"
            pEntity=RE_consolemode.ogreSceneManager().createEntity(entity_name, filename)
        else:
            assert(filename is not None)
            pEntity=filename
        pNode.attachObject(pEntity)
        pNode.setVisible(self.isVisible);

        if materialName is not None:
            pEntity.setMaterialName(materialName);
        return pNode;



def path(path):
    from pathlib import Path
    path=os.path.normpath(path)
    return Path(path)

def ogreVersion():
    return 2  # actually 1.4.1 but not the old version 1
def create_cache_folder(path: str | Path, suffix=".cached", create=True) -> Path:
    src = Path(path)

    if not src.is_file():
        raise FileNotFoundError(src)

    parent = src.parent                      # aaa
    cached_parent = parent.with_name(parent.name + suffix)  # aaa.cached
    if create:
        cached_parent.mkdir(parents=True, exist_ok=True)
    return cached_parent, src.name

def _getPythonWin():
    return _layout
class Widget:
    def __init__(self, type_name, uid, title, spos, epos):
        self.type_name=type_name
        self.uid=uid
        self.title=title
        self.startSlot=spos
        self.endSlot=epos
        if type_name=='Multi_Browser':
            self._browser=[]
            self._browserSelected=[]
        elif type_name=='Check_Button':
            self._value=False
        elif type_name=='Box':
            self._value=title
        elif type_name=='Input' or type_name=='Multiline_Input':
            self._value=''
        self._active=True
    def activate(self):
        self._active=True
    def deactivate(self):
        self._active=False
    def id(self):
        return self.uid
    def checkButtonValue(self, v=None):
        if v is None:
            return self._value
        else:
            if v==1 or v==1.0:
                self._value=True
            elif v==0 or v==0.0:
                self._value=False
            else:
                self._value=v
    def sliderRange(self,s=None, e=None):
        if s is None:
            return self._range or (0,1)
        else:
            self._range=(s,e)
    def menuItems(self, items):
        self._items=items
    def menuValue(self, v=None):
        if v is None:
            return self._value
        else:
            self._value=v
    def menuText(self):
        item=self._items[self.menuValue()]
        if isinstance(item, tuple):
            return item[0]
        return item
    def menuSize(self, n):
        self._items=[None]*n
    def menuItem(self, i, text, shortcut=None):
        if shortcut:
            self._items[i]=(text, shortcut)
        else:
            self._items[i]=text
    def browserSize(self):
        return len(self._browser)

    def browserText(self, i_plus_one):  # one indexing
        return self._browser[i_plus_one-1]
    def browserDeselect(self):
        for i in range(len(self._browser)):
            self._browserSelected[i]=False
    def browserSelect(self, i_plus_one):
        if self.type_name!='Multi_Browser':
            self.browserDeselect()
        self._browserSelected[i_plus_one-1]=True
    def browserRemove(self, i_plus_one):
        self._browserSelected.erase(i_plus_one-1)
        self._browser.erase(i_plus_one-1)
    def browserClear(self):
        self._browserSelected=[]
        self._browser=[]
    def browserValue(self):
        return self._browserSelected.index(True) if True in self._browserSelected else -1 

    def browserAdd(self, v):
        self._browser.append(v)
        self._browserSelected.append(False)
    def browserSelected(self, i_plus_one):
        return self._browserSelected[i_plus_one-1]
    def redraw(self):
        pass

# share the simplest code
Widget.sliderValue=Widget.menuValue
Widget.inputValue=Widget.menuValue
#

class PythonExtendWin_member:
    def __init__(self, name: str):
        self.name=name
    def __call__(self, *args):   
        global _luaEnv
        memberfunc=getattr(_luaEnv,self.name)
        return memberfunc(*args)
class FltkRenderer:
    def renderWindowWidth(self):
        global _window_data
        return _window_data.window.getWidth()
    def renderWindowHeight(self):
        global _window_data
        return _window_data.window.getHeight()
    def screenToWorldRay(self, x,y,ray):
        global _window_data
        tx = float(1.0 / self.renderWindowWidth()) * x;
        ty = float(1.0 / self.renderWindowHeight()) * y;

        cam=_window_data.camera

        ogre_ray=cam.getCameraToViewportRay(tx , ty);
        ray.set(_toBaseP(ogre_ray.getOrigin()), _toBaseP(ogre_ray.getDirection()));

class Layout(FltkRenderer): 
    def __init__(self):
        self.widgets=[]
        self.layoutElements={}
    # default member access functions
    def __getattr__(self, name):
        return PythonExtendWin_member(name)
    def create(self, type_name, uid,  title=None, pos=None, epos=None):
        self.widgets.append(Widget(type_name, uid, title,pos, epos))
    def addText(self, title, on_screen_title=None):
        self.create('Text', title, on_screen_title)
    def addButton(self, title, on_screen_title=None):
        self.create('Button', title, on_screen_title)
    def addCheckButton(self, title, initialValue):
        self.create('Check_Button', title, title)
        self.widget(0).checkButtonValue(initialValue)
    def findWidget(self, uid):
        for i,v  in enumerate(self.widgets):
            if v.uid==uid:
                return v
        return None
    def widget(self, n):
        return self.widgets[n-1]
    def updateLayout(self):
        pass
            
def erase(type_name, name):
    global _objectList, _activeBillboards

    if _objectList is not None:
        _objectList.erase(name)
    _activeBillboards.pop(name, None)

def drawTraj(objectlist,matrix,nameid, color='solidgreen', thickness=0, linetype='LineList'):
    objectlist.registerObject(nameid, linetype, color , matrix, thickness )

def timedDrawTraj(objectlist, time, matrix, color='solidgree', thickness=0, linetype='LineList'):
    objectlist.registerObjectScheduled(time, linetype, color , matrix, thickness )

def drawLine(objectList, startpos, endpos, nameid=None, color='green'):
    lines=m.vector3N() 
    lines.setSize(2)
    lines(0).assign(startpos)
    lines(1).assign(endpos)
    assert(startpos.x==startpos.x)

    if nameid is None:
        nameid=RE_consolemode.generateUniqueName()
    drawBillboard( lines.matView(), nameid,color , 1.5 ,"BillboardLineList")

def drawText(objectList, pos, nameid, vec3_color=None, height=None, text=None):
    mat=vec3_color or m.vector3(1,1,1)
    height=height or 8
    if text:
        objectList.registerLayoutElement(nameid+"_mt", "MovableText", text, mat, height, pos)
    else:
        objectList.registerLayoutElement(nameid+"_mt", "MovableText", nameid, mat, height, pos)
def drawAxes(*args):
    pass
def drawArrowM(objectList, startpos, endpos, name, _thick=None, color=None):
    if _thick is not None:
        drawArrow(objectList, startpos*100, endpos*100, name, _thick*100, color)
    else:
        drawArrow(objectList, startpos*100, endpos*100, name, color)
def drawArrow(objectlist, startpos, endpos, nameid, thick=10, color =None):

    if color is not None:
        node=objectlist.registerEntity(nameid, "arrow2.mesh", color)
    else:
        node=objectlist.registerEntity(nameid, "arrow2.mesh")

    node.resetToInitialState()
    dist=(startpos-endpos).length()
    node.scale(thick/10, dist/50, thick/10)
    q=m.quater()
    q.axisToAxis(m.vector3(0,1,0), (endpos-startpos))
    node.rotate(q)
    node.translate(endpos)

def drawSphere(objectList, pos, nameid, _materialName=None, _scale=None):
    if _scale is None:
        _scale=5 # 5 cm

    if _materialName is not None:
        comEntity=objectList.registerEntity(nameid, "sphere1010.mesh", _materialName)
    else:
        comEntity=objectList.registerEntity(nameid, "sphere1010.mesh")

    if comEntity is not None:
        comEntity.setScale(_scale, _scale, _scale)
        comEntity.setPosition(pos.x, pos.y, pos.z)

class MeshToEntity:
    def __init__(self, mesh, mesh_name=None, buildEdgeList=False, dynamicUpdate=False, useNormal=True,useTexCoord=True, useColor=False):

        if(mesh.numTexCoord()==0 and useTexCoord):
            useTexCoord=False;

        if(mesh.numNormal()==0 and useNormal):
            useNormal=False;

        if(mesh.numColor()==0 and useColor):
            useColor=False;
        self.useColor=useColor
        self.useNormal=useNormal
        self.useTexCoord=useTexCoord
        self.buildEdgeList=buildEdgeList
        self.dynamicUpdate=dynamicUpdate;
        if mesh_name is None:
            mesh_name=m.generateUniqueName()
        self.mesh_name=mesh_name
        self.mesh=mesh

        meshId=mesh_name
        if(Ogre.MeshManager.getSingleton().resourceExists(meshId)):
            #ptr=Ogre.MeshManager.getSingleton().getByName(meshId);
            Ogre.MeshManager.getSingleton().remove(meshId);

        self.meshToEntity_cpp=m.MeshToEntity( mesh, mesh_name, buildEdgeList, dynamicUpdate, useNormal,useTexCoord, useColor)

        if not hasattr(self.meshToEntity_cpp, 'getRawData'):
            print("Ignoring this error. Please update libcalab to at least version 0.1.1 to render meshes correctly.")
            # use manual object (slowww)
            scene_mgr=ogreSceneManager()
            manual = scene_mgr.createManualObject(meshId+"_manual")
            manual.setDynamic(False)

            # reserve capacity 
            manual.estimateVertexCount(mesh.numVertex())
            manual.estimateIndexCount(mesh.numFace()*3)

            manual.begin("BaseWhiteNoLighting",
                     Ogre.RenderOperation.OT_TRIANGLE_LIST)

            for i in range(mesh.numVertex()):
                v=mesh.getVertex(i)
                manual.position(v.x, v.y, v.z)

            for i in range(mesh.numFace()):
                f=mesh.getFace(i)
                manual.triangle(f.vertexIndex(0), f.vertexIndex(1), f.vertexIndex(2))
            manual.end()
            mMesh = manual.convertToMesh(meshId)
            scene_mgr.destroyManualObject(manual)
        else:
            vertices=m.matrixn()
            indices=m.intvectorn()
            numSubMeshes=self.meshToEntity_cpp.getRawData(mesh, 0, vertices, indices)

            assert(numSubMeshes==1)

            # use low-level api
            mMesh= Ogre.MeshManager.getSingleton().createManual(meshId, Ogre.RGN_DEFAULT);

            sub = mMesh.createSubMesh();
            sub.useSharedVertices = True
            sub.operationType = Ogre.RenderOperation.OT_TRIANGLE_LIST
            sub.createVertexData()

            sub.vertexData.vertexCount=vertices.rows()

            decl = sub.vertexData.vertexDeclaration
            hbm = Ogre.HardwareBufferManager.getSingleton()
            source = 0
            buffers=[]
            currentColumn=3
            xyz=vertices.sub(0,0,0,3)
            numVertices=vertices.rows()
            buffers.append((xyz.array.astype(np.half), Ogre.VET_HALF3, Ogre.VES_POSITION,0))
            if useNormal:
                buffers.append((vertices.sub(0,0,currentColumn, currentColumn+3).array.astype(np.half), Ogre.VET_HALF3, Ogre.VES_NORMAL,0))
                currentColumn+=3
            if useTexCoord:
                buffers.append((vertices.sub(0,0,currentColumn, currentColumn+2).array.astype(np.half), Ogre.VET_HALF2, Ogre.VES_TEXTURE_COORDINATES,0))
                currentColumn+=2

            #usage=Ogre.HBU_CPU_ONLY
            usage=Ogre.HBU_GPU_ONLY
            if dynamicUpdate:
                #usage=Ogre.HBU_CPU_ONLY
                usage=Ogre.HBU_CPU_TO_GPU

            for data, vtype, vusage, vindex in buffers:
                decl.addElement(source, 0, vtype, vusage, vindex)
                hwbuf = hbm.createVertexBuffer(decl.getVertexSize(source), numVertices, usage)
                sub.vertexData.vertexBufferBinding.setBinding(source, hwbuf)
                hwbuf.writeData(0, hwbuf.getSizeInBytes(), data)
                source += 1

            mMesh._setBounds(Ogre.AxisAlignedBox(xyz.array.min(axis=0), xyz.array.max(axis=0))) # pylint: disable=protected-access
            radius = np.linalg.norm(xyz.array, axis=0).max()
            mMesh._setBoundingSphereRadius(float(radius))
            vertexBuffer = sub.vertexData.vertexBufferBinding.getBuffer(0);
            if False:
                #debug code
                pos_elem = decl.findElementBySemantic(Ogre.VES_POSITION)
                mPositions=np.zeros((numVertices,3)).astype(np.half)
                ptr=vertexBuffer.lock(Ogre.HardwareBuffer.HBL_READ_ONLY)
                print(vertexBuffer.getSizeInBytes()/ numVertices)

                u16_ptr = ctypes.cast(int(ptr), ctypes.POINTER(ctypes.c_uint16))

                # zero-copy uint16 array
                raw = np.ctypeslib.as_array(
                    u16_ptr, shape=(numVertices, 3)
                )

                # reinterpret uint16 → float16
                mPositions = raw.view(np.float16).copy()

                vertexBuffer.unlock()
                print(mPositions, xyz)
                pdb.set_trace()

            # create index buffer
            idata = sub.indexData;
            self.idata=idata
            indexCount=indices.size()
            idata.indexCount = indexCount;
            mIndexBuffer = vertexBuffer.getManager().createIndexBuffer(Ogre.HardwareIndexBuffer.IT_32BIT, indexCount, usage)
            idata.indexBuffer = mIndexBuffer;

            indices_np= indices.array

            buf = idata.indexBuffer.lock(
                0,
                indexCount * idata.indexBuffer.getIndexSize(),
                Ogre.HardwareBuffer.HBL_DISCARD
            )
            ctypes.memmove(int(buf), indices_np.ctypes.data, indices_np.nbytes)
            idata.indexBuffer.unlock()

        if False:

            if not mMesh.isPreparedForShadowVolumes():
                mMesh.prepareForShadowVolume()

            mMesh.freeEdgeList()
            mMesh.buildEdgeList()

        mMesh.load()

        self.mMesh=mMesh
    def createEntity(self, entityName,  materialName='lightgrey'):

        if(ogreSceneManager().hasEntity(entityName)):
            ogreSceneManager().destroyEntity(entityName);
        
        entity=ogreSceneManager().createEntity(entityName, self.mMesh.getName());
        self.entity=entity
        entity.setMaterialName(materialName);
        return entity

    def getLastCreatedEntity(self):
        return self.entity
    def updatePositions(self, vertices=None):
        if hasattr(self.meshToEntity_cpp, 'getRawData'):
            sub=self.mMesh.getSubMesh(0)
            vertices=m.matrixn()
            indices=m.intvectorn()
            numSubMeshes=self.meshToEntity_cpp.getRawData(self.mesh, 0, vertices, indices)
            vertexBuffer=sub.vertexData.vertexBufferBinding.getBuffer(0)
            vertexBuffer.writeData(0, vertexBuffer.getSizeInBytes(), vertices.sub(0,0,0,3).array.astype(np.half))

    def updatePositionsAndNormals(self):
        self.updatePositions()

def drawCylinder(objectlist, tf, nameid, cylinderSize, skinScale=None, material=None):
    global _cacheCylinderMeshes
    if not skinScale :
        skinScale=100

    mesh=_cacheCylinderMeshes.get(nameid)
    if mesh is None:
        g=m.Geometry()
        c=m.vector3( cylinderSize.x*skinScale, cylinderSize.y*skinScale, cylinderSize.z)
        if c.z<3 : 
           c.z=3 
        g.initCylinder(c.x*0.5, c.y, int(c.z))
        mesh= ( g, 
           MeshToEntity(g, 'mesh_'+nameid, False, True),
           cylinderSize*skinScale
        )
        _cacheCylinderMeshes[nameid]=mesh

    g, meshToEntity, ssize=mesh
    entity=meshToEntity.createEntity('entity_'+nameid, material or 'lightgrey_transparent')
    tfg=objectlist.registerEntity(nameid, entity)
    if not (ssize==cylinderSize*skinScale) :
        c=m.vector3( cylinderSize.x*skinScale, cylinderSize.y*skinScale, cylinderSize.z)
        if c.z<3 : 
            c.z=3 
        g.initCylinder(c.x*0.5, c.y, int(c.z))
        meshToEntity.updatePositionsAndNormals()

    tfg.setPosition(tf.translation*skinScale)
    tfg.setOrientation(tf.rotation)

def _createWireBox(boxSize, skinScale):
    mesh=m.vector3N(12*2)
    fb=boxSize*skinScale*0.5
    c=0
    mesh(c).assign(m.vector3(fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y, fb.z)) 
    c=c+1

    mesh(c).assign(m.vector3(fb.x, fb.y, -fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y,- fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y, -fb.z))
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y,- fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, fb.y, -fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y,- fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y,- fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y,- fb.z)) 
    c=c+1

    mesh(c).assign(m.vector3(fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, fb.y, -fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(fb.x, -fb.y, -fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, fb.y, -fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y, fb.z)) 
    c=c+1
    mesh(c).assign(m.vector3(-fb.x, -fb.y, -fb.z)) 
    c=c+1
    return mesh

def drawWireBox(objectlist, tf, nameid, boxSize, skinScale=100, material=None, thickness=1.5):
    mesh=_createWireBox(boxSize, skinScale)
    mesh.rotate(tf.rotation)
    mesh.translate(tf.translation*skinScale)
    drawBillboard( mesh.matView(), nameid,material or 'solidblue', thickness or 1.5 ,"BillboardLineList")
def drawBox(objectlist, tf, nameid, boxSize, skinScale=None, material=None):
    global _cacheBoxMeshes
    if not skinScale :
        skinScale=100

    mesh=_cacheBoxMeshes.get(nameid)
    if mesh is None:
       g=m.Geometry()
       g.initBox(boxSize*skinScale)
       mesh= ( g, 
           MeshToEntity(g, 'mesh_'+nameid, False, True),
           boxSize*skinScale
       )

       _cacheBoxMeshes[nameid]=mesh

    g, meshToEntity, ssize=mesh
    entity=meshToEntity.createEntity('entity_'+nameid, material or 'lightgrey_transparent')
    tfg=objectlist.registerEntity(nameid, entity)
    if not (ssize==boxSize*skinScale) :
       g.initBox(boxSize*skinScale)
       meshToEntity.updatePositionsAndNormals()

    tfg.setPosition(tf.translation*skinScale)
    tfg.setOrientation(tf.rotation)

def drawSphereM(objectList, pos, nameid, _materialName=None, _radius=None):
    if _radius is None:
        drawSphere(objectList, pos*100, nameid, _materialName, _radius*100)
    else:
        drawSphere(objectList, pos*100, nameid, _materialName)
def timedDrawSphere(objectList, time, pos, _materialName=None, _scale=None):
    if _scale is None:
        _scale=5 # 5 cm

    comEntity=objectList.registerEntityScheduled( "sphere1010.mesh", time)
    if _materialName is not None:

        if _materialName is not None:
            comEntity.getEntity().setMaterialName(_materialName)
        comEntity.setScale(_scale, _scale, _scale)
        comEntity.setPosition(pos.x, pos.y, pos.z)

def timedDrawSphereM(objectList, time, pos, _materialName=None, _scale=None):
    if _scale is not None:
        timedDrawSphere(objectList, time, pos*100, _materialName, _scale*100)
    else:
        timedDrawSphere(objectList, time, pos*100, _materialName)
def draw(typename,*args):
    global _objectList
    if _objectList is None:
        _objectList=ObjectList()

    this_module = sys.modules[__name__]
    getattr(this_module, 'draw'+typename)(_objectList, *args)

def timedDraw(time, typename, *args):
    global _objectList
    if _objectList is None:
        _objectList=ObjectList()

    this_module = sys.modules[__name__]
    getattr(this_module, 'timedDraw'+typename)(_objectList, time, *args)

def namedDraw(typename,*args):
    global _objectList
    draw(typename, *args)

    pos=None
    nameid=None
    color='blue'
    p=(typename, *args)
    if typename=="Sphere" or typename=="SphereM":
        pos=p[1]
        if typename=="SphereM":
            pos=pos*100
        nameid=p[2]
        if len(p)>4: 
            color=p[3] 
    elif typename=='Axes':
        pos=p[1].translation
        nameid=p[2]
        if len(p)>4:
            pos=pos*p[3]
	#elseif typename=='Coordinate' then
	#	local p={...}
	#	pos=p[1].translation*100 + (p[3] or vector3(0,0,0))*100
	#	nameid=p[2]
	#elseif typename=="Line" or typename=='Line2' then
	#	local p={...}
	#	pos=p[1]
	#	nameid=p[3]
	#	if p[4] then color=p[4] end
	#elseif typename=="Arrow" then
	#	local p={...}
	#	pos=p[1]
	#	nameid=p[3]
	#elseif typename=='Arrow2' then
	#	local p={...}
	#	pos=p[2]
	#	nameid=p[3]
	#	typename='Arrow'
	#elseif typename=="registerObject" then
	#	local p={...}
	#	pos=p[4][0]
	#	nameid=p[1]
	#end
    if pos :
        if 'ed' in color:
            mat=m.vector3(0.7,0,0)
        elif 'reen' in color:
            mat=m.vector3( 0,0.5,0)
        else:
            mat=m.vector3( 0,0,1) 
        fontSize=8*_ui_scale
        _objectList.registerLayoutElement(nameid+"_mt", "MovableText", nameid, mat,fontSize, pos+m.vector3(0,15.0/8.0*fontSize,0))

def drawBillboard(datapoints, *args):
    global _activeBillboards
    info= ( datapoints.copy(), *args)
    _activeBillboards[args[0]]=info
    if isinstance(datapoints, m.vector3N):
        draw('Traj', datapoints.matView(), *args)
    else:
        draw('Traj', datapoints, *args)

def drawPoints(objectList, vec_or_mat, name, materialName, thickness =1):    
    if isinstance(vec_or_mat, m.vectorn):
        mat=m.matrixn(int(vec.size()/3), 3)
        for i in range(mat.rows()):
            mat.row(i).assign(vec.toVector3(3*i))
        drawBillboard(mat, name, materialName, thickness , 'QuadListV'  )
    elif hasattr(vec_or_mat, 'matView'):
        drawBillboard(vec_or_mat.matView(), name, materialName, thickness , 'QuadListV'  )
    else:
        drawBillboard(vec_or_mat, name, materialName, thickness , 'QuadListV'  )


def WRLloader(filename, *kwargs):
    if filename[-4:]=='.wrl':
        loader=m.VRMLloader(filename)
        doNotGarbageCollect.append(loader)
        return loader
    elif filename[-4:]=='.png' or filename[-4:]=='.raw':
        var_name='mLoader'+m.generateUniqueName()
        lua.F_lua(var_name, "MainLib.VRMLloader", filename, *kwargs)
        return lua.G_VRMLloader(var_name)

    var_name='mLoader'+m.generateUniqueName()
    lua.require( "subRoutines/WRLloader")
    if filename[-8:]=='.wrl.lua' or filename[-8:]=='.wrl.dat' :
        lua.F_lua(var_name, "MainLib.WRLloader", filename)
    else:
        lua.F_lua(var_name, "MainLib.WRLloader", lua.toTable(filename))
    info={} # todo : return this when requested through an option
    info['var_name']=var_name
    return lua.G_VRMLloader(var_name)

def dummyOnCallback(w, userData):
    pass
def checkedOnCallback(w, userData):
    try:
        __main__.onCallback(w, userData)
    except Exception as e:
        print(e)
        print(w.type_name)
        traceback.print_exc()  # optional, print the stack
        pdb.post_mortem(e.__traceback__)  # drop into pdb at the original exception
def checkedHandleRendererEvent(ev, x, y):
    global _prevMouse
    if x!=_prevMouse[0]  or y!=_prevMouse[1] or ev=='PUSH' or ev=='RELEASE':
        try:
            button=_prevMouse[2]
            if ev=='PUSH':
                if imgui.IsMouseClicked(0): 
                    button=1
                elif imgui.IsMouseClicked(1):
                    button=3
                else:
                    button=2
            __main__.handleRendererEvent(ev, button, x, y)
            _prevMouse=(x,y, button)
        except Exception as e:
            print(e)
            print(ev)
            traceback.print_exc()  # optional, print the stack
            pdb.post_mortem(e.__traceback__)  # drop into pdb at the original exception

def _world_to_screen(world_pos):
    global _window_data
    camera=_window_data.camera
    viewport=_window_data.window.getViewport(0)

    # 1. World → Clip space
    view = camera.getViewMatrix(True)
    proj = camera.getProjectionMatrixWithRSDepth()

    clip = proj * (view * Ogre.Vector4(world_pos.x, world_pos.y, world_pos.z, 1.0))

    # behind camera
    if clip.w <= 0.0:
        return None, None, False

    # 2. NDC
    ndc_x = clip.x / clip.w
    ndc_y = clip.y / clip.w

    # 3. Screen (pixel)
    vp_width  = viewport.getActualWidth()
    vp_height = viewport.getActualHeight()

    screen_x = (ndc_x * 0.5 + 0.5) * vp_width
    screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * vp_height

    return int(screen_x), int(screen_y), True
def ui_callback(): # handle ui events and draw texts
    global _layout, _mouseInfo, _window_data,_softKill,_drawOutput,_outputs, _layoutHeight, _timeline, _capture_frame 
    # This function is called every frame to draw your custom ImGui elements
    io = imgui.GetIO()
    io.FontGlobalScale = _ui_scale
    #imgui.NewFrame()
    #imgui.ShowDemoWindow() # Displays the standard Dear ImGui demo window
    imgui.SetNextWindowSize(imgui.ImVec2(200*_ui_scale, 200*_ui_scale), imgui.Cond_Once)
    imgui.SetNextWindowPos(imgui.ImVec2(0,0))

    # draw texts

    draw_list=imgui.GetForegroundDrawList()
    for i, v in _layout.layoutElements.items():
        typeid, text, mat, height, pos=v
        screen_x, screen_y, exist=_world_to_screen(pos)
        if exist:
            pos=imgui.ImVec2(screen_x, screen_y);
            color = imgui.GetColorU32(imgui.ImVec4(mat.x*255,mat.y*255, mat.z*255, 255)); 
            draw_list.AddText(pos, color, text)


    # -----------------------------
    # ImGui UI
    # -----------------------------
    if imgui.Begin("Menu"):
        imgui.SetWindowSize(imgui.ImVec2(300*_ui_scale, _layoutHeight*_ui_scale));
        if hasattr(__main__,'onCallback'):
            onCallback=checkedOnCallback
        else:
            onCallback=dummyOnCallback
        try:
            for i,v  in enumerate(_layout.widgets):
                if v.type_name=='Button':
                    if imgui.Button(v.title or v.uid):
                        onCallback(v, None)
                elif v.type_name=='Box':
                    imgui.Text(v._value)
                elif v.type_name=='Text':
                    imgui.Text(v.title or v.uid)
                    imgui.Text('')
                elif v.type_name=='Check_Button':
                    changed,value=imgui.Checkbox(v.title or v.uid, v.checkButtonValue())
                    if changed and v._active:
                        v.checkButtonValue(value)
                        onCallback(v, None)
                elif v.type_name=='Value_Slider':
                    changed, my_value = imgui.SliderFloat(v.title or v.uid, v.sliderValue(), *v.sliderRange())
                    if changed and v._active:
                        v.sliderValue(my_value)
                        onCallback(v, None)
                elif v.type_name=='Multiline_Input':
                    imgui.Separator();
                    imgui.Text(v.title or v.uid) 

                    changed= imgui.InputTextMultiline(
                        '',
                        v.inputValue(),
                        1024                         # buffer size,
                    )
                    if changed and v._active:
                        pass # todo: there seems to be no way to get the text back.
                        v.inputValue(text)
                        onCallback(v, None)
                elif v.type_name=='Multi_Browser':

                        
                    #if imgui.Begin(v.title or v.uid):
                    #if False:
                    #imgui.BeginChild(v.title or v.uid, imgui.ImVec2(200, 150), True):
                    if imgui.BeginListBox(v.title or v.uid, imgui.ImVec2(0, 120)):

                        assert(len(v._browser)==len(v._browserSelected))
                        for i in range(v.browserSize()):
                            if (imgui.Selectable(v.browserText(i+1), v.browserSelected(i+1))):
                                v._browserSelected[i]=not v._browserSelected[i]
                                onCallback(v, None)
                        imgui.EndListBox()
                        #imgui.EndChild()
                         #imgui.End()
                elif v.type_name=='Choice':
                    #if imgui.BeginMainMenuBar():  # Main menu bar at the top
                    if True:
                        if imgui.BeginMenu(v.title or v.uid, True):  # Menu with items
                            assert(v._items is not None)
                            assert(isinstance(v._items, list))
                            for ii, vv in enumerate(v._items):
                                if isinstance(vv, tuple):
                                    shortcut=vv[ 1]
                                    shortcut=shortcut[:-1]+shortcut[:-1].upper()
                                    clicked_new= imgui.MenuItem(vv[0], shortcut, v.menuValue()==ii)
                                    if clicked_new:
                                        print("New clicked")
                                else:
                                    clicked_new= imgui.MenuItem(vv, None, v.menuValue()==ii)
                                    if clicked_new:
                                        v.menuValue(ii)
                                        onCallback(v, None)

                            #imgui.separator()  # Draw a separator line
                            imgui.EndMenu()  # End "File" menu
                        #imgui.Text('    :'+v.menuText())
                        #imgui.EndMainMenuBar()  # End main menu bar
                else:
                    print(v.type_name, 'not implemented yet')


        except Exception as e:
            print(e)

    mx = imgui.GetMousePos()
    wx  = imgui.GetWindowPos()
    wh = imgui.GetWindowSize()

    hovered = (
        wx.x <= mx.x <= wx.x + wh.x and
        wx.y <= mx.y <= wx.y + wh.y)

    if _timeline is not None: 
        hovered2=_timeline.draw()
        hovered=hovered or hovered2



    # HandleMouseMessage2
    # Mouse buttons
    altPressed = imgui.GetIO().KeyAlt;
    ctrlPressed = imgui.GetIO().KeyCtrl;
    shiftPressed = imgui.GetIO().KeyShift;
    imgui.Separator();
    imgui.Text("press q to quit.")
    #imgui.Text(f"alt:{altPressed}, ctrl:{ctrlPressed}, shift:{shiftPressed}")

    changed,value=imgui.Checkbox('capture', _capture_frame is not None)

    io = imgui.GetIO()
    if(io.KeyCtrl and imgui.IsKeyPressed(imgui.Key_C) ):
        value=_capture_frame is None
        changed=True

    if changed:
        if value:
            _capture_frame=0
        else:
            _capture_frame=None

    changed,value=imgui.Checkbox('show debug output', _drawOutput)
    if changed:
        _drawOutput=value
    if value:

        io = imgui.GetIO()

        window_width=300*_ui_scale
        imgui.SetNextWindowPos( imgui.ImVec2(io.DisplaySize.x - window_width, 0))

        imgui.SetNextWindowSize( imgui.ImVec2( window_width, 500*_ui_scale))
        if imgui.Begin("debug output"):
            imgui.Text('use  RE.output("msg key", "msg")')
            imgui.Separator();
            for i, key in enumerate(sorted(_outputs)):
                imgui.Text(f"{key}\t{_outputs[key]}")

        imgui.End()

    if _mouseInfo is None:
        _mouseInfo=lua.Table()
        _mouseInfo.drag=False
    released=False
    if imgui.IsMouseReleased(0) or imgui.IsMouseReleased(1) or imgui.IsMouseReleased(2):
        _mouseInfo.drag=False
        released=True

    if not hovered:
            #imgui.IsWindowHovered(  ) and not imgui.IsItemHovered():
            # Mouse info
            mouse_pos = imgui.GetMousePos()

            _mouseInfo.pos=m.vector3(mouse_pos.x, mouse_pos.y,0)
            #imgui.Text(f"Mouse position: ({(mouse_pos.x, mouse_pos.y)})")
            width=_window_data.window.getWidth()
            height=_window_data.window.getHeight()

            hasHandler=hasattr(__main__,'handleRendererEvent')
            if imgui.IsMouseClicked(0) or imgui.IsMouseClicked(1) or imgui.IsMouseClicked(2):
                _mouseInfo.downMousePos=m.vector3(mouse_pos.x, mouse_pos.y,0)
                _mouseInfo.drag=True
                if shiftPressed:
                    if hasHandler:
                        checkedHandleRendererEvent("PUSH", int(mouse_pos.x), int(mouse_pos.y))
                    else:
                        shiftPressed=False
            elif shiftPressed and hasHandler:
                if released:
                    checkedHandleRendererEvent("RELEASE", int(mouse_pos.x), int(mouse_pos.y))
                elif _mouseInfo.drag:
                    checkedHandleRendererEvent("DRAG", int(mouse_pos.x), int(mouse_pos.y))
                else:
                    checkedHandleRendererEvent("MOVE", int(mouse_pos.x), int(mouse_pos.y))


            if not shiftPressed and _mouseInfo.downMousePos is not None and _mouseInfo.drag:
                dx=_mouseInfo.pos- _mouseInfo.downMousePos
                if dx.length()>0.5:
                    m_zoom=1
                    m_scale=300 
                    panning= imgui.IsMouseDown(2) or (imgui.IsMouseDown(0) and altPressed)
                    if panning:
                        x=-dx.x/(width/2.0)
                        y=dx.y/(height/2.0)
                        x*=(m_scale/m_zoom);
                        y*=(m_scale/m_zoom);
                        if hasattr(RE_consolemode.viewpoint(), 'PanRight'):
                            RE_consolemode.viewpoint().PanRight(x);
                            RE_consolemode.viewpoint().PanUp(-y);
                    elif imgui.IsMouseDown(0) : 
                        RE_consolemode.viewpoint().TurnRight(-(dx.x/width))
                        RE_consolemode.viewpoint().TurnUp(dx.y/(height/2.0))
                    else:
                        dy= dx.y/(height/2.0)
                        dy*=m_scale

                        RE_consolemode.viewpoint().ZoomOut(-dy)

                    if hasattr(RE_consolemode.viewpoint(),"CheckConstraint"):
                        RE_consolemode.viewpoint().CheckConstraint();
                    else:
                        RE_consolemode.viewpoint().update()
                    _mouseInfo.downMousePos=m.vector3(mouse_pos.x, mouse_pos.y,0)
    else:
        _mouseInfo =None


    imgui.End()
    # -----------------------------
    # Rendering
    # -----------------------------
    imgui.Render()


def clone_git_to_cache(
    repo_url: str,
    repo_name: str | None = None,
    cache_dir_name: str = ".cache",
    pull_if_exists: bool = False,
) -> Path:
    """
    Clone a git repository into a cache directory (platform-independent).

    Args:
        repo_url: Git repository URL
        repo_name: Folder name for the repo (defaults to repo URL name)
        cache_dir_name: Cache directory name under user home
        pull_if_exists: If True, run 'git pull' when repo already exists

    Returns:
        Path to the cloned repository
    """

    # ~/.cache (or custom name)
    cache_root = Path.home() / cache_dir_name
    cache_root.mkdir(parents=True, exist_ok=True)

    if repo_name is None:
        repo_name = Path(repo_url.rstrip("/")).stem

    repo_path = cache_root / repo_name

    if repo_path.exists():
        if pull_if_exists:
            print(f"[INFO] Repository exists, pulling: {repo_path}")
            subprocess.run(
                ["git", "-C", str(repo_path), "pull"],
                check=True,
            )
        else:
            print(f"[INFO] Repository already cached: {repo_path}")
    else:
        print(f"[INFO] Cloning repository to cache: {repo_path}")
        subprocess.run(
            ["git", "clone", repo_url, str(repo_path)],
            check=True,
        )

    return repo_path
def run_mklink_as_admin(src, tgt, bat_path=None):
    src = os.path.abspath(src)
    tgt = os.path.abspath(tgt)

    if bat_path is None:
        bat_path = Path.cwd() / "gitscript.bat"
    else:
        bat_path = Path(bat_path)

    # 1. gitscript.bat 생성
    bat_content = f"""@echo off
echo Creating symbolic link...
mklink /d "{tgt}" "{src}"
if %errorlevel% neq 0 (
    echo Failed to create symlink.
) else (
    echo Symlink created successfully.
)
set /p res=Press Enter to continue.
"""

    bat_path.write_text(bat_content, encoding="utf-8")

    # 2. PowerShell로 관리자 권한 실행
    ps_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Start-Process '{bat_path}' -Verb RunAs"
    ]

    subprocess.run(ps_cmd, check=True)

def createMainWin(*args):
    global _window_data, _layout,_luaEnv, _ui_scale
    RE_consolemode.createMainWin()

    _luaEnv=m.getPythonWin()
    # swap console versions to ogre-python versions
    # (we need to override only those functions used in the RE_consolemode.SceneGraph class.)
    m.getPythonWin=_getPythonWin      
    m.FltkRenderer=_getPythonWin
    m.getSceneNode=getSceneNode
    m.renderOneFrame=renderOneFrame
    m.ObjectList=ObjectList
    RE_consolemode.output=output
    RE_consolemode.draw=draw
    RE_consolemode.erase=erase
    RE_consolemode.ogreSceneManager=ogreSceneManager
    RE_consolemode.ogreSceneManager=ogreSceneManager
    if not os.path.exists('./work'):
        print("Ogre3D resource folder ('work') not found. Creating it from GitHub taesoobear/IPCDNNwalk/work.")
        cache_root = Path.home() / '.cache'

        repo_path = clone_git_to_cache(
            repo_url="https://github.com/taesoobear/IPCDNNwalk.git",
            pull_if_exists=True,
        )

        if os.name == "nt":
            print('Creating symbolic link')
            run_mklink_as_admin(str(cache_root/'IPCDNNwalk'/'work'), 'work')
        else:
            os.symlink(cache_root/'IPCDNNwalk'/'work', 'work')

    window_name='Ogre ImGui'
    imsize=(1278,768)
    # Setup the Ogre window and mesh
    #ohi.window_create("Ogre ImGui Demo", (1278, 768))
    
    ohi.user_resource_locations.add("work/taesooLib/media/models")
    ohi.user_resource_locations.add("work/taesooLib/media/materials/textures")
    if os.path.exists('./media'):
        ohi.user_resource_locations.add("media")


    if False:
        ohi._init_ogre(window_name, imsize)
    else:
        ohi._ctx = _Application()
        ohi._ctx.name = window_name
        ohi._ctx.imsize = imsize
        ohi._ctx.initApp()

    rgm = Ogre.ResourceGroupManager.getSingleton()
    #rgm.addResourceLocation("work/taesooLib/media/RTShaderLib", "FileSystem", "OgreInternal", True)
    #rgm.addResourceLocation("work/taesooLib/media/Main", "FileSystem", "OgreInternal", True)
    #rgm.addResourceLocation("work/taesooLib/media/packs/SdkTrays.zip", "Zip", "Essential", True)
    #rgm.addResourceLocation("work/taesooLib/media/packs/Sinbad.zip", "Zip", "New", True)

    _window_data=ohi._ctx.windows[window_name]
    ohi._init_window(_window_data, ohi.AXES_ZBACKWARD_YUP)

    # Enable ImGui integration with your callback
    ohi.window_use_imgui(window_name, ui_callback)
    cam=_window_data.camera

    _layout= Layout()
    _updateView()
    _loadBG_default()

    if platform.system() == "Darwin":
        #from AppKit import NSScreen
        #_ui_scale= int(NSScreen.mainScreen().backingScaleFactor())
        render_width=_window_data.window.getWidth()
        _ui_scale=render_width/imsize[0]

    return _layout

def ogreRootSceneNode():
    return SceneNodeWrap(ogreSceneManager().getRootSceneNode())
m.ogreRootSceneNode=ogreRootSceneNode
def createChildSceneNode(pnode, cnode_name):
    return pnode.createChildSceneNode(cnode_name)
m.createChildSceneNode=createChildSceneNode

def viewpoint():
    return RE_consolemode.viewpoint()

def ogreSceneManager():
    global _window_data
    return SceneManagerWrap(_window_data.scn_mgr)


_lastCamPos=Ogre.Vector3(1e5,0,0)
def renderOneFrame(check):
    global _start_time ,_softKill, _capture_frame
    ctime=time.time()
    elapsed =  ctime- _start_time
    if _capture_frame is not None:
        if elapsed<1.0/30.0:
            time.sleep(1.0/30.0-elapsed)
        elapsed=1.0/30.0

    _start_time=ctime
    if check:
        if elapsed>1.0/30:
            elapsed=1.0/30
        if hasattr(__main__,'frameMove'):
            __main__.frameMove(elapsed)

        for i, v in enumerate(_frameMoveObjects):
            obj=v()
            obj.frameMove(elapsed)
        for i, v in enumerate(_frameMoveObjects2):
            obj=v()
            obj.frameMove(elapsed)

        global _window_data, _lastCamPos, _cameraEventReceivers,_activeBillboards
        cam = _window_data.camera
        camPos=cam.getDerivedPosition()
        camDist=(camPos-_lastCamPos).squaredLength()
        if camDist>1:
            for i, v in enumerate(_cameraEventReceivers):
                v()._update()
            for k, v in _activeBillboards.items():
                draw('Traj',*v)
            _lastCamPos=Ogre.Vector3(camPos.x, camPos.y, camPos.z)


        _sceneGraphs=RE_consolemode._sceneGraphs
        if _sceneGraphs is not None:
            for i, v in enumerate(_sceneGraphs):
                for k, vv in v.objects.items():
                    if vv.handleFrameMove is not None:
                        vv.handleFrameMove(vv, elapsed)

    evt=ohi.window_draw("Ogre ImGui")
    _updateView()

    if _capture_frame is not None:
        window=_window_data.window
        settle_renders=0
        img = grab_frame(window.getWidth(), window.getHeight(), settle_renders)

        frames_dir = Path("dump")
        frames_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{_capture_frame:05d}.jpg"
        save_jpeg(frames_dir / out_name, img)
        print(out_name)
        _capture_frame+=1

    #ohi._ctx.pollEvents()
    #_window_data.window.update()
    #evt = _window_data.last_key
    #_window_data.last_key = 0
    if  evt== 27 or evt==113: # 27 is the Esc key, 113: q
        return False
    if _softKill:
        return False
    return True


def _tempFunc(v):
    return Ogre.Vector3(v.x, v.y, v.z)
m.vector3._toOgre=_tempFunc
def _tempFunc(v):
    return Ogre.Quaternion(v.w, v.x, v.y, v.z)
m.quater._toOgre=_tempFunc

def _toBaseP(v):
    return m.vector3(v.x, v.y, v.z)
def _updateView():
    global _window_data
    cam=_window_data.camera
    camNode=cam.getParentSceneNode()

    if False:
        matView=m.matrix4()
        viewpoint().GetViewMatrix(matView)
        matTF=m.transf(matView)
        camNode.setPosition(matTF.translation._toOgre())
        camNode.setOrientation(matTF.rotation._toOgre())
    else:
        camNode.setPosition(viewpoint().vpos._toOgre())
        camNode.lookAt(viewpoint().vat._toOgre(), Ogre.Node.TS_PARENT);



def _randomNormal():
    return (random.random()-0.5)*2
def _randomNormal2():
    while True :
        u = 2 * random.random() - 1;
        v = 2 * random.random() - 1;
        w = math.pow(u, 2) + math.pow(v, 2);
        if w<1 :
            z = math.sqrt((-2 * math.log(w)) / w);
            x = u * z;
            y = v * z;
            return x

def _createLight_default():
    global _window_data

    stencilShadow=False
    depthShadow=False
    highQualityRendering=False # set this true for high quality render
    numMainLights=5 # 5이상이어야 품질이 좋지만, m1 macbook에서 너무 느림
    lightVar=0.02

    mViewport=_window_data.window.getViewport(0)

    if stencilShadow:
        depthShadow=False
    if not stencilShadow and not depthShadow :
        textureShadow=True

    if depthShadow:
        # add integrated depth shadows
        rtShaderGen = Ogre.RTShader.ShaderGenerator.getSingleton();
        schemRenderState = rtShaderGen.getRenderState(Ogre.MSN_SHADERGEN);
        schemRenderState.addTemplateSubRenderState(rtShaderGen.createSubRenderState(Ogre.RTShader.SRS_SHADOW_MAPPING));

        # Make this viewport work with shader generator scheme.
        mViewport.setMaterialScheme(Ogre.MSN_SHADERGEN);
        # update scheme for FFP supporting rendersystems
        Ogre.MaterialManager.getSingleton().setActiveScheme(mViewport.getMaterialScheme());

    if True:
        mBackgroundColour=Ogre.ColourValue( 0.2, 0.4, 0.6 );
        mViewport.setBackgroundColour(mBackgroundColour)

        # set shadow properties
        mSceneMgr=ogreSceneManager()
        if not stencilShadow and depthShadow:
            # 
            mSceneMgr.setShadowTechnique(Ogre.SHADOWTYPE_TEXTURE_MODULATIVE_INTEGRATED);
            mSceneMgr.setShadowTexturePixelFormat(Ogre.PF_DEPTH16);
            mSceneMgr.setShadowTextureSize(1024);
            #mSceneMgr.setShadowTextureCount(numMainLights); # not working
            mSceneMgr.setShadowTextureCount(1);
            mSceneMgr.setShadowDirLightTextureOffset(0);
            mSceneMgr.setShadowFarDistance(50);
            mSceneMgr.setShadowCameraSetup(Ogre.LiSPSMShadowCameraSetup.create());
        elif textureShadow:
            mSceneMgr.setShadowTechnique(
                Ogre.SHADOWTYPE_TEXTURE_MODULATIVE
            )
            mSceneMgr.setShadowTextureSize(2048)
            mSceneMgr.setShadowFarDistance(1000)
        else:
            mSceneMgr.setShadowTechnique(Ogre.SHADOWTYPE_STENCIL_MODULATIVE);
        mSceneMgr.setShadowColour(Ogre.ColourValue(0.5, 0.5, 0.5));

    rootnode =ogreRootSceneNode()
    lightnode=RE_consolemode.createChildSceneNode(rootnode, "LightNode")
    ogreSceneManager().setAmbientLight(Ogre.Vector3(0.4))

    
    sc=math.pow(0.5, 1/numMainLights)
    light1D=0.9
    light1S=0.8
    lightOD=0.0
    lightOS=0.0

    if not stencilShadow :
        if depthShadow :
            light1D=0.8/numMainLights
            light1S=0.2/numMainLights
            lightOD=0.8/numMainLights
            lightOS=0.2/numMainLights
        sc=0.9
        if textureShadow :
            sc=0.97
            highQualityRendering=True
    else:
        sc=0.975

    if highQualityRendering :
        # high-quality
        numMainLights=10
        RE_consolemode.ogreSceneManager().setShadowTextureCount(numMainLights)

    RE_consolemode.ogreSceneManager().setShadowColour(Ogre.Vector3(sc,sc,sc))


    for i in range(1,numMainLights +1):
        if i==1 :
            light=RE_consolemode.ogreSceneManager().createLight("Mainlight")
        else:
            light=RE_consolemode.ogreSceneManager().createLight("Mainlight"+str(i))
        light.setType(Ogre.Light.LT_DIRECTIONAL)

        node=lightnode.createChildSceneNode("mainlightnode"+str(i))
        node.setDirection(Ogre.Vector3(-0.5+lightVar*(_randomNormal()),-0.7,0.5+lightVar*(_randomNormal())))
        node.attachObject(light)
        if i==1 :
            light.setDiffuseColour(light1D,light1D,light1D)
            light.setSpecularColour(light1S,light1S,light1S)
        else:
            light.setDiffuseColour(lightOD,lightOD,lightOD)
            light.setSpecularColour(lightOS,lightOS,lightOS)
        light.setCastShadows(True)
        
    filllightnode=lightnode.createChildSceneNode("filllightNode")
    light=RE_consolemode.ogreSceneManager().createLight("FillLight")
    filllightnode.attachObject(light)
    filllightnode.setDirection(0.5,0.7,-0.5)
    light.setType(Ogre.Light.LT_DIRECTIONAL)
    light.setDiffuseColour(0.4,0.4,0.4)
    light.setSpecularColour(0.4,0.4,0.4)
    light.setCastShadows(False)
def _loadBG_default():
    global _window_data

    _createLight_default()

    rootnode =ogreRootSceneNode()
    bgnode=RE_consolemode.createChildSceneNode(rootnode , "BackgroundNode")
    plane=Ogre.Plane()
    plane.normal=Ogre.Vector3(0,1,0)
    plane.d=-0.5
    Ogre.MeshManager.getSingleton().createPlane("bg_floor_mesh", Ogre.RGN_DEFAULT, plane,16000.0,16000.0, 80,80,True, 1, 80.0,80.0, Ogre.Vector3(0,0,1))
    ent=ogreSceneManager().createEntity("bg_floor", "bg_floor_mesh")
    ent.setMaterialName("checkboard/crowdEditing")
    ent.setCastShadows(False)
    bgnode.attachObject(ent)

    viewpoint().vpos=m.vector3(50,200,300)
    viewpoint().vat=m.vector3(0,0,0)
    viewpoint().vup=m.vector3(0,1,0)
    viewpoint().update()

    cam=_window_data.camera
    camNode=cam.getParentSceneNode()

    camNode.setFixedYawAxis(True, viewpoint().vup._toOgre())
    cam.setFOVy(Ogre.Radian(Ogre.Degree(45)));
    _updateView()


if True:
        # define splat function
    def read_splat_ply(filename):
        f = open(filename, 'rb')

        if f.readline().strip() != b"ply":
            raise ValueError("Not a ply file")

        f.readline() # endianess
        num_vertices = int(f.readline().strip().split()[2])

        # expect format as below

        NUM_PROPS=0

        name_to_idx={}
        while True:
            line=re.sub(br"\s+", b"", f.readline().strip()) # remove spaces

            name_to_idx[line]=NUM_PROPS
            if line==b"end_header":
                break
            NUM_PROPS+=1

        data = np.frombuffer(f.read(), dtype=np.float32).reshape(num_vertices, NUM_PROPS)

        idx_xyz=name_to_idx[b'propertyfloatx']
        xyz = data[:, idx_xyz:idx_xyz+3]
        idx_sh=name_to_idx[b'propertyfloatf_dc_0']
        sh = data[:, idx_sh:idx_sh+3]
        idx_opacity=name_to_idx[b'propertyfloatopacity']
        opacity = data[:, idx_opacity:idx_opacity+1]
        idx_scale=name_to_idx[b'propertyfloatscale_0']
        scale = np.exp(data[:, idx_scale:idx_scale+3])
        idx_rot=name_to_idx[b'propertyfloatrot_0']
        rot = data[:, idx_rot:idx_rot+4]
        # normalise quaternion
        rot = rot / np.linalg.norm(rot, axis=1)[:, None]

        return xyz, sh, opacity, scale, rot

    SH_C0 = 0.28209479177387814

    def sigmoid(x):
        return 1 / (1 + np.exp(-x))

    def sh0_to_diffuse(sh):
        return SH_C0 * sh + 0.5

    def compute_cov3d(scale, rot):
        q = Ogre.Quaternion(rot)
        m = Ogre.Matrix3()
        q.ToRotationMatrix(m)

        S = np.diag(scale)
        M = Ogre.Numpy.view(m) @ S

        Cov = M @ M.T

        return np.diag(Cov), np.array([Cov[0, 1], Cov[0, 2], Cov[1, 2]], dtype=np.float32)

    def splat_to_mesh(mesh_name, xyz, color, covd, covu):
        mesh = Ogre.MeshManager.getSingleton().createManual(mesh_name, Ogre.RGN_DEFAULT)
        sub = mesh.createSubMesh()
        sub.useSharedVertices = True
        sub.operationType = Ogre.RenderOperation.OT_POINT_LIST
        sub.setMaterialName("pointcloud")

        n = len(xyz)

        sub.createVertexData()
        sub.vertexData.vertexCount = n

        decl = sub.vertexData.vertexDeclaration
        hbm = Ogre.HardwareBufferManager.getSingleton()
        source = 0

        buffers = [(xyz.astype(np.half), Ogre.VET_HALF3, Ogre.VES_POSITION, 0),
                   (color, Ogre.VET_UBYTE4_NORM, Ogre.VES_DIFFUSE, 0),
                   (covd.astype(np.half), Ogre.VET_HALF3, Ogre.VES_TEXTURE_COORDINATES, 0),
                   (covu.astype(np.half), Ogre.VET_HALF3, Ogre.VES_TEXTURE_COORDINATES, 1)]

        for data, vtype, vusage, vindex in buffers:
            decl.addElement(source, 0, vtype, vusage, vindex)
            hwbuf = hbm.createVertexBuffer(decl.getVertexSize(source), n, Ogre.HBU_CPU_ONLY)
            sub.vertexData.vertexBufferBinding.setBinding(source, hwbuf)
            hwbuf.writeData(0, hwbuf.getSizeInBytes(), data)
            source += 1

        mesh._setBounds(Ogre.AxisAlignedBox(xyz.min(axis=0), xyz.max(axis=0))) # pylint: disable=protected-access
        return mesh


    def ply_to_mesh(mesh_name, input_ply):
        if isinstance(input_ply, tuple):
            xyz, color, covd, covu=input_ply
        elif isFileExist(input_ply+'.cached.npy'):
            print('loading '+input_ply+'.cached.npy')
            data=np.load(input_ply+'.cached.npy', allow_pickle=True).item()
            xyz=data['xyz']
            color=data['color']
            covd=data['covd']
            covu=data['covu']
        else:
            xyz, sh, opacity, scale, rot = read_splat_ply(input_ply)

            sh0 = sh[:, :3]
            color = np.clip(np.hstack((sh0_to_diffuse(sh0), sigmoid(opacity)))*255, 0, 255).astype(np.uint8)

            N = len(xyz)

            covd = np.empty((N, 3), dtype=np.float32)
            covu = np.empty((N, 3), dtype=np.float32)
            mod = (N - 1)//100

            for i, (s, r) in enumerate(zip(scale, rot)):
                covd[i], covu[i] = compute_cov3d(s, r)
                if i % mod == 0:
                    print(f"computing covariances {100*i/len(xyz):.0f}%", end="\r")
            np.save(input_ply+'.cached', {'xyz':xyz,'color': color, 'covd': covd, 'covu':covu})
        mesh = splat_to_mesh(mesh_name, xyz, color, covd, covu)
        return mesh


def _tempFunc(mesh, materialName, _optionalNodeName=None, _optionalDoNotUseNormal=None):
    if _optionalNodeName is None:
        _optionalNodeName='node_name'

    useTexCoord=False
    useColor=False

    if mesh.numNormal()==0 :
        _optionalDoNotUseNormal=True
    if mesh.numTexCoord()>0 :
        useTexCoord=True
    if mesh.numColor()>0 :
        useColor=True
    # scale 100 for rendering 
    meshToEntity=MeshToEntity(mesh, 'meshName'+_optionalNodeName, False, True, not _optionalDoNotUseNormal, useTexCoord, useColor)
    entity=meshToEntity.createEntity('entityName'+_optionalNodeName , materialName or "CrowdEdit/Terrain1")
    if entity :
        removeEntity(_optionalNodeName)
        node=ogreRootSceneNode().createChildSceneNode(_optionalNodeName)
        node.attachObject(entity)
        return meshToEntity,node
    return None
m.Mesh.drawMesh=_tempFunc # overwrite

def turnOffSoftShadows():
    ogreSceneManager().setShadowTechnique(Ogre.SHADOWTYPE_NONE);



class _QuadList:
    def __init__(self, node_name, normal, width):
        self.normal=normal
        self.width=width
        scene_mgr=ogreSceneManager()

        name=node_name+"_manual"
        if (scene_mgr.hasManualObject(name)):
            manual = sceneMgr.getManualObject(name);
            manual.clear()  # 기존 geometry 제거 
        else:
            manual = scene_mgr.createManualObject()
        manual.setDynamic(False)
        self.manual=manual
    def begin(self, n, materialName='BaseWhiteNoLigthting'):
        manual=self.manual
        manual.estimateVertexCount(n*6)

        axis1=m.vector3()
        axis2=m.vector3();
        qy=m.quater()
        vp=RE_consolemode.viewpoint()
        mNormal=self.normal
        halfWidth=self.width/2;
        qy.setAxisRotation(m.vector3(0,1,0), m.vector3(0,0,1), vp.vpos-vp.vat)
        axis1.cross(mNormal, qy*m.vector3(0,0,1));
        if(axis1.length()<0.01):
            axis1.cross(mNormal, qy*m.vector3(1,0,0));

        axis1.normalize();
        axis2.cross(axis1, mNormal);

        pos=[None]*4
        pos[0]=axis1*halfWidth+axis2*halfWidth;
        pos[1]=axis1*halfWidth+axis2*-halfWidth;
        pos[2]=axis1*-halfWidth+axis2*-halfWidth;
        pos[3]=axis1*-halfWidth+axis2*halfWidth;

        texCoord=[None]*4
        texCoord[0]=m.vector3(1, 0, 1);
        texCoord[1]=m.vector3(1, 0, 0);
        texCoord[2]=m.vector3(0, 0, 0);
        texCoord[3]=m.vector3(0, 0, 1);

        self.pos=pos
        self.texCoord=texCoord
        self.c=0
        manual.begin(materialName, Ogre.RenderOperation.OT_TRIANGLE_LIST)
    def end(self):
        self.manual.end()
    def quad(self, i, mpos):
        assert(i==self.c)
        self.c+=1
        pos=self.pos
        texCoord=self.texCoord
        manual=self.manual

        # lower triangle
        for j in range(3):
            pp=pos[j]+mpos;
            manual.position(pp.x, pp.y, pp.z)
            manual.textureCoord(texCoord[j].x, texCoord[j].z)

        # upper triangle
        for index in range(3):
            j=(index+2)%4;
            pp=pos[j]+mpos;
            manual.position(pp.x, pp.y, pp.z)
            manual.textureCoord(texCoord[j].x, texCoord[j].z)

    def color_quad(self, i, color, mpos, width):
        assert(i==self.c)
        self.c+=1
        pos=self.pos
        texCoord=self.texCoord
        manual=self.manual

        # lower triangle
        for j in range(3):
            pp=pos[j]*width+mpos;
            manual.position(pp.x, pp.y, pp.z)
            manual.textureCoord(color.x+texCoord[j].x*0.01, 1-color.y+texCoord[j].z*0.01)

        # upper triangle
        for index in range(3):
            j=(index+2)%4;
            pp=pos[j]*width+mpos;
            manual.position(pp.x, pp.y, pp.z)
            manual.textureCoord(color.x+texCoord[j].x*0.01, 1-color.y+texCoord[j].z*0.01)

def isFileExist(fname):
    import os.path
    return os.path.isfile(fname)


def setQuater(anyvec,q ):
    anyvec[0]=q.w
    anyvec[1]=q.x
    anyvec[2]=q.y
    anyvec[3]=q.z
def setVec3(anyvec,v ):
    anyvec[0]=v.x
    anyvec[1]=v.y
    anyvec[2]=v.z
def setTransf(anyvec, tf):
    setVec3(anyvec, tf.translation)
    setQuater(anyvec[3:], tf.rotation)


def saveTable(tbl=dict, filename=str):
    lua.F('util.saveTable', tbl, filename)
def loadTable(filename=str):
    return lua.F('util.loadTable', filename)

# ZUP to YUP
def quater_ZtoY(q):
    return m.quater(q.w, q.y, q.z, q.x)
def vector3_ZtoY(v):
    return m.vector3(v.y, v.z, v.x)
def transf_ZtoY(t):
    return m.transf(t.rotation.ZtoY(), t.translation.ZtoY())

def ZtoY(v):
    mat=v
    if isinstance(v, m.matrixn):
        mat=v.ref()

    if mat.shape[1]==3:
        mat[:, [0,1,2]]=mat[:, [1,2,0]]
    elif mat.shape[1]==4:
        mat[:, [1,2,3]]=mat[:, [2,3,1]]
    else:
        pdb.set_trace()


# YUP to ZUP
def quater_YtoZ(q):
    return m.quater(q.w, q.z, q.x, q.y)
def vector3_YtoZ(v):
    return m.vector3(v.z, v.x, v.y)
def transf_YtoZ(t):
    return m.transf(t.rotation.YtoZ(), t.translation.YtoZ())

def boolN_numpy(self):
    out=np.ones((self.size()), dtype=bool)
    for i in range(self.size()):
        out[i]=self(i)
    return out
m.boolN.numpy=boolN_numpy
def tempFunc(self):
    out=m.intvectorn(self.size())
    out.setAllValue(0)
    for i in range(self.size()):
        if self(i):
            out.set(i,1)
    return out
m.boolN.asInt=tempFunc
m.quater.ZtoY=quater_ZtoY
m.vector3.ZtoY=vector3_ZtoY
m.transf.ZtoY=transf_ZtoY
m.quater.YtoZ=quater_YtoZ
m.vector3.YtoZ=vector3_YtoZ
m.transf.YtoZ=transf_YtoZ
def tempFunc(self):
    return max(self.x, self.y, self.z)
m.vector3.maximum=tempFunc


def tempFunc(self, b):
    out=m.boolN()
    out._or(self,b)
    return out
m.boolN.bitwiseOR=tempFunc

def tempFunc(self, prevFrameRate, newFrameRate):
    lua.M(self, 'resample', prevFrameRate, newFrameRate)
m.MotionDOF.resample=tempFunc

def tempFunc(self, b):
    out=m.boolN()
    out._and(self,b)
    return out
m.boolN.bitwiseAND=tempFunc
def tempFunc(self):
    out=m.intIntervals()
    out.runLengthEncode(self)
    return out
m.boolN.runLengthEncode=tempFunc
def tempFunc(self, t=m.transf):

    for i in range(self.numFrames()):
        pose=self.pose(i)
        root=m.transf(pose.rotations(0), pose.translations(0))
        newRoot=t*root
        pose.rotations(0).assign(newRoot.rotation)
        pose.translations(0).assign(newRoot.translation)
m.Motion.transform=tempFunc

#Compatibility with the libcalab_ogre3d layers below

def addFrameMoveObject(obj):
    global _frameMoveObjects
    _frameMoveObjects.append(weakref.ref(obj))



class Timeline:
    def __init__(self, numframes, frametime=1.0 / 60.0):
        global _timeline
        addFrameMoveObject(self)
        self.totalTime = numframes
        self.frametime=frametime
        self.numframes=numframes
        self.currFrame=0
        self._currFrame=0
        self.playing=False
        _timeline=self
    def draw(self):
        global _ui_scale

        io = imgui.GetIO()
        window_height = 50*_ui_scale


        imgui.SetNextWindowSize( imgui.ImVec2( io.DisplaySize.x, window_height))
        hovered=False
        if imgui.Begin("Timeline"):
            # 화면 하단에 고정
            imgui.SetWindowPos( imgui.ImVec2(0, io.DisplaySize.y - window_height))

            mx = imgui.GetMousePos()
            wx  = imgui.GetWindowPos()
            wh = imgui.GetWindowSize()
            hovered = (
                wx.x <= mx.x <= wx.x + wh.x and
                wx.y <= mx.y <= wx.y + wh.y)
            shortcut = ( io.KeyCtrl and imgui.IsKeyPressed(imgui.Key_P))
            shortcut2 = ( io.KeyCtrl and imgui.IsKeyPressed(imgui.Key_0))
            if shortcut2:
                self.changeCurrFrame(0)
            if imgui.IsKeyPressed(imgui.Key_LeftBracket):
                self.playing=False
                self.changeCurrFrame(self.currFrame-1)
            if imgui.IsKeyPressed(imgui.Key_RightBracket):
                self.playing=False
                self.changeCurrFrame(self.currFrame+1)



            
            # play / pause
            if imgui.Button("Pause" if self.playing else "Play") or shortcut:
                self.playing = not self.playing
            imgui.SameLine()


            if platform.system() == "Darwin":
                imgui.TextDisabled("Alt+P")
            else:
                imgui.TextDisabled("Ctrl+P")
            imgui.SameLine()

            # timeline slider
            changed, frame = imgui.SliderInt(
                "",
                self.currFrame,
                0,
                self.totalTime - 1
            )

            if changed:
                self.currFrame = frame
                self.changeCurrFrame(frame)
        else:
            imgui.SetWindowPos( imgui.ImVec2(0, io.DisplaySize.y - 10))
        imgui.End()
        return hovered
    def __del__(self):
        global _frameMoveObjects
        if _frameMoveObjects is not None:
            _frameMoveObjects= [r for r in _frameMoveObjects if r() is not self]

    def frameMove(self, elapsed):
        if self.playing:
            self.currFrame=int(self._currFrame)
            __main__.onFrameChanged(self.currFrame)
            self._currFrame+=elapsed/self.frametime
            if self._currFrame>=self.numframes:
                self._currFrame=self.numframes-1
                self.playing=False


    def changeCurrFrame(self, iframe):
        if iframe<0 :
            iframe=0
        if iframe>=self.numframes:
            iframe=self.numframes-1
        self.currFrame=iframe
        self._currFrame=iframe
        __main__.onFrameChanged(self.currFrame)

    def numFrames(self):
        return self.totalTime

    def reset(self, numframes, frameTime=1.0 / 60.0):
        self.motion_win.changeCurrFrame(0)

        self.renderer.removeFrameMoveObject(self)
        self.motion_win.detachSkin(self)

        self.totalTime = numframes
        self.attachTimer(frameTime, numframes)

        self.renderer.addFrameMoveObject(self)
        self.motion_win.addSkin(self)

class PLDPrimSkin:
    def __init__(self, loader):
        self.scale = 1
        self.loader=loader
        self.fkSolver = m.BoneForwardKinematics(loader)
        self.fkSolver.setPose(loader.pose())
        self.uid = m.generateUniqueName()
        self.thickness=3 # 3cm
        self.materialName='solidwhite'
    def setScale(self, s,s2=None,s3=None):
        self.scale*=s
        self.redraw()
    def setPose(self, pose):
        self.fkSolver.setPose(pose)
        self.redraw()
    def setPoseDOF(self, posedof):
        self.fkSolver.setPoseDOF(posedof)
        self.redraw()
    def redraw(self):
        lines=m.vector3N()
        lines.reserve(self.fkSolver.numBone())
        for i in range(2, self.fkSolver.numBone()):
            lines.pushBack(self.fkSolver.globalFrame(i).translation)
            lines.pushBack(self.fkSolver.globalFrame(self.loader.bone(i).parent().treeIndex()).translation)
        drawBillboard( lines.matView()*self.scale,  self.uid, self.materialName, self.thickness, 'BillboardLineList' )



def createSkin(loader:m.MotionLoader):
    return PLDPrimSkin(loader)

def createFBXskin(fbx:FBXloader, drawSkeleton=None, **kwargs):
    """
    Create a skinned character from an FBX loader.

    Args:
        fbx:
            taesooLib FBX loader containing the character skeleton and skin.

        **kwargs:
            Optional settings:

            drawSkeleton (bool):
                If True, draw the character skeleton. Defaults to False.

            adjustable (bool):
                If True, create an adjustable skeleton whose bone lengths
                can be modified. Defaults to False.

    Returns:
        The created FBX skin.
    """
    if drawSkeleton:
        return FBXloaderSkin(fbx, drawSkeleton)
    else:
        return FBXloaderSkin(fbx, kwargs)


class FBXloaderSkin:
    def __init__(self, fbxloader, option=None):
        if option is None:
            option = {}

        def opt(name, default=None):
            if isinstance(option, dict):
                return option.get(name, default)
            return getattr(option, name, default)

        self.scale = m.vector3(1, 1, 1)
        self.fbx = fbxloader
        loader=fbxloader.loader
        self.fkSolver = m.BoneForwardKinematics(loader)
        self.fkSolver.setPose(loader.pose())

        self.skelSkin = None
        self.poseMap = None
        self.angleRetarget = None
        self.prevPose = None
        self.nodes2 = None

        if not getattr(fbxloader, 'fbxInfo', None):
            if isinstance(option, dict):
                option['drawSkeleton'] = True
            else:
                option.drawSkeleton = True

        if opt('drawSkeleton', False):
            self.skelSkin = RE.createSkin( fbxloader.loader)
            self.skelSkin.setPose(fbxloader.loader.pose())

        self.uid = m.generateUniqueName()

        # Lua에서는 1-based table.

        n_submeshes=len(fbxloader.fbxInfo)
        self.nodes = [None]*n_submeshes
        self.ME = [None]*n_submeshes


        if not getattr(fbxloader, 'fbxInfo', None):
            return


        for iminus1 in range(n_submeshes):
            i=iminus1+1
            meshInfo=fbxloader.fbxInfo[i]
            node = None
            meshToEntity = None
            entity = None

            if ogreSceneManager() is not None:
                # Lua: meshInfo[1]
                mesh = meshInfo.mesh

                useTexCoord = False
                useColor = False
                useNormal = True
                buildEdgeList = not opt('disableShadow', False)
                dynamicUpdate = True

                if mesh.numNormal() == 0:
                    useNormal = False

                if mesh.numTexCoord() > 0:
                    useTexCoord = True

                if mesh.numColor() > 0:
                    useColor = True

                # scale 100 for rendering
                meshToEntity = MeshToEntity(
                    mesh,
                    self.uid + 'meshName' + str(i),
                    buildEdgeList,
                    dynamicUpdate,
                    useNormal,
                    useTexCoord,
                    useColor
                )

                self.ME[iminus1] = meshToEntity
                meshToEntity = self.ME[iminus1]

                material = opt('material', None)
                if material is None:
                    material=meshInfo.material

                entity = meshToEntity.createEntity(
                    'entityName' + self.uid + '_' + str(i)
                )


                if material:
                    entity.setMaterialName(material)

                    entity.setMaterialName(meshInfo.material)

                else:
                    entity.setMaterialName('grey_transparent')

                node = createChildSceneNode(
                    ogreRootSceneNode(),
                    self.uid + '_' + str(i)
                )

                rigidBody=fbxloader.get('rigidBody')
                if rigidBody is True:
                    node2 = createChildSceneNode(
                        node,
                        self.uid + '__' + str(i)
                    )

                    node2.attachObject(entity)

                    if self.nodes2 is None:
                        self.nodes2 = [None]*n_submeshes

                    self.nodes2[iminus1] = node2

                else:
                    node.attachObject(entity)

            else:
                node = Ogre.SceneNode()

            self.nodes[iminus1] = [
                node,
                m.vector3(0, 0, 0),
                m.vector3N()
            ]

        self.setPose(fbxloader.loader.pose())

    def getNode(self, meshIndex):
        return self.nodes[meshIndex][0]

    def getNodeInfo(self, meshIndex):
        return self.nodes[meshIndex]

    def numMesh(self):
        return len(self.nodes)

    # ------------------------------------------------------------------
    # pose
    # ------------------------------------------------------------------

    def getState(self):
        return self.fkSolver

    def setVisible(self, bVisible):
        if self.skelSkin is not None:
            self.skelSkin.setVisible(bVisible)

        for i, v in enumerate(self.nodes):
            v[0].setVisible(bVisible)

    def __del__(self):
        self.skelSkin = None

        if self.nodes is not None:
            for i, v in enumerate(self.nodes):
                if v[0] is not None and removeEntity is not None:
                    removeEntity(v[0])

        self.nodes = None
        self.fbx = None
        self.fkSolver = None

    # ------------------------------------------------------------------
    # material
    # ------------------------------------------------------------------

    def setMaterial(self, name):
        for i, me in enumerate(self.ME):
            me.getLastCreatedEntity().setMaterialName(name)
    def setRenderQueueGroup(self, qgroup:int):
        for i, me in enumerate(self.ME):
            me.getLastCreatedEntity().setRenderQueueGroup(qgroup)

    def unsetMaterial(self):
        for i, me in enumerate(self.ME):
            meshInfo = self.fbx.fbxInfo[i+1]
            me.getLastCreatedEntity().setMaterialName(
                meshInfo.material
            )

    # ------------------------------------------------------------------
    # pose transfer
    #
    # assuming self.loader == mLoader_orig
    # poseconv = MotionUtil.PoseTransfer(
    #     mLoader,
    #     mLoader_orig,
    #     True
    # )
    # ------------------------------------------------------------------

    def setPoseTransfer(self, poseconv):
        self.poseMap = poseconv

        if getattr(poseconv, 'pt', None):
            self.angleRetarget = poseconv
            self.poseMap = poseconv.pt

    def setPose(self, pose):
        if self.poseMap is not None:
            if self.angleRetarget is not None:
                # Lua:
                # pose = self.angleRetarget(pose)
                pose = self.angleRetarget(pose)

            else:
                self.poseMap.setTargetSkeleton(pose)

                pose = Pose()
                self.poseMap.target().getPose(pose)

        self.fkSolver.setPose(pose)
        self.setSamePose(self.fkSolver)

    def _setPose(self, pose, loader):
        self.setPose(pose)

    def setPoseDOF(self, pose):
        if self.poseMap is not None:
            if self.angleRetarget is not None:
                pose = self.angleRetarget(pose)

            else:
                self.poseMap.source().setPoseDOF(pose)

                pose = Pose()
                self.poseMap.source().getPose(pose)

                self.poseMap.setTargetSkeleton(pose)
                self.poseMap.target().getPose(pose)

            self.fkSolver.setPose(pose)

        else:
            self.fkSolver.setPoseDOF(pose)

        self.setSamePose(self.fkSolver)

    def setSamePose(self, fk):
        # assert(fk == self.fbx.loader.fkSolver())
        # BoneForwardKinematics.operator== doesn't work yet.

        if self.skelSkin is not None:
            self.skelSkin.setSamePose(fk)

        self.fkSolver.assign(fk)

        fbxloader = self.fbx

        # --------------------------------------------------------------
        # rigid body
        # --------------------------------------------------------------

        rigidBody=fbxloader.get('rigidBody')
        if rigidBody==True:
            for i, node2 in enumerate(self.nodes2):
                node2.setOrientation(
                    fk.globalFrame(1).rotation
                )
                node2.setPosition(
                    fk.globalFrame(1).translation
                )

            return

        # --------------------------------------------------------------
        # skinned body
        # --------------------------------------------------------------

        rootTrans = fk.globalFrame(1).translation.copy()

        currJointPos = m.vector3N(
            self.fkSolver.numBone() - 1
        )

        # Lua:
        #
        # for ibone=1, self.fkSolver:numBone()-1 do
        #     currJointPos(ibone-1):assign(
        #         self.fkSolver:globalFrame(ibone).translation-rootTrans
        #     )
        # end

        for ibone in range(1, self.fkSolver.numBone()):
            currJointPos(ibone - 1).assign(
                self.fkSolver.globalFrame(ibone).translation
                - rootTrans
            )

        buildEdgeList = False

        if (
            self.prevPose is None
            or np.mean((self.prevPose.array-currJointPos.array)**2) > 1e-3
        ):
            buildEdgeList = True
            self.prevPose = currJointPos


        n_submeshes=len(fbxloader.fbxInfo)
        for iminus1 in range(n_submeshes):
            i=iminus1+1
            meshInfo=fbxloader.fbxInfo[i]
            ME = self.ME[iminus1]

            if ME is None:
                continue

            node = self.nodes[iminus1]
            skin = meshInfo.skin
            mesh = meshInfo.mesh

            # update vertex positions
            skin.calcVertexPositions(
                self.fkSolver,
                mesh
            )

            # remove root translation from mesh vertices
            removeRootTrans = m.matrix4()
            removeRootTrans.setTranslation(
                -rootTrans,
                False
            )

            mesh.transform(removeRootTrans)

            useNormal = mesh.numNormal() > 0

            ME.buildEdgeList=buildEdgeList

            if useNormal:
                skin.calcVertexNormals(
                    self.fkSolver,
                    fbxloader._getBindPoseGlobal(i),
                    meshInfo.localNormal,
                    mesh
                )

                ME.updatePositionsAndNormals()

            else:
                ME.updatePositions()

            # backup current mesh pose
            if hasattr(mesh, 'getVertices'):
                mesh.getVertices(node[2])

            node[0].setPosition(
                node[1]
                + rootTrans * self.scale.x
            )

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------

    def setScale(self, x, y=None, z=None):
        if y is None:
            y = x

        if z is None:
            z = x

        if self.skelSkin is not None:
            self.skelSkin.setScale(x, y, z)

        for i, node in enumerate(self.nodes):
            prevPos = node[0].getPosition()

            node[0].setScale(x, y, z)

            node[0].setPosition(
                prevPos.x / self.scale.x * x,
                prevPos.y / self.scale.y * y,
                prevPos.z / self.scale.z * z
            )

        self.scale = m.vector3(x, y, z)

    def setTranslation(self, x, y=None, z=None):
        if y is None:
            assert x is not None

            y = x.y
            z = x.z
            x = x.x

        if self.skelSkin is not None:
            self.skelSkin.setTranslation(x, y, z)

        for i, node in enumerate(self.nodes):
            node[0].setPosition(
                node[0].getPosition()
                - node[1]
                + m.vector3(x, y, z)
            )

            node[1] = m.vector3(x, y, z)

    # ------------------------------------------------------------------
    # vertices
    # ------------------------------------------------------------------

    def _getVertexInWorld(self, meshIndex, vertexIndex):
        meshInfo = self.fbx.fbxInfo[meshIndex - 1]
        skin = meshInfo.skin

        return skin.calcVertexPosition(
            self.fkSolver,
            vertexIndex
        )

    # ------------------------------------------------------------------
    # picking
    # ------------------------------------------------------------------

    # use proper ray pick
    def pickTriangle(self, x, y):
        ray = Ray()

        RE.FltkRenderer().screenToWorldRay(
            x,
            y,
            ray
        )

        return self._pickTriangle(ray)

    # vertexPositions: relative to root translation.
    #
    # return:
    # {
    #     mesh: Mesh,
    #     skin: SkinnedMeshFromVertexInfo,
    #     vertexPositions: vector3N
    # }
    def getMeshInfo(self, fbxMeshIndex=None):
        if fbxMeshIndex is None:
            fbxMeshIndex = 1

        node = self.nodes[fbxMeshIndex]
        meshInfo = self.fbx.fbxInfo[fbxMeshIndex - 1]

        return {
            'mesh': meshInfo[0],
            'skin': meshInfo.skin,
            'vertexPositions': node[2],
        }

    # input ray will be modified!
    def _pickTriangle(self, ray):
        s = self.scale.x

        # TODO: loop through all meshes
        fbxMeshIndex = 1

        node = self.nodes[fbxMeshIndex]

        meshPos = (
            node[1]
            + self.fkSolver.globalFrame(1).translation * s
        )

        ray.translate(-meshPos)
        ray.scale(1.0 / s)

        out = vector3()
        baryCoeffs = vector3()

        mesh = self.fbx.fbxInfo[fbxMeshIndex - 1][0]

        ti = ray.pickBarycentric(
            mesh,
            node[2],
            baryCoeffs,
            out
        )

        if ti >= 0:
            return {
                'faceIndex': ti,
                'baryCoeffs': baryCoeffs,
                'pos': meshPos + out * s,
            }

        return None

    # ------------------------------------------------------------------
    # barycentric sampling
    # ------------------------------------------------------------------

    def samplePosition(
        self,
        meshIndex,
        ti,
        baryCoeffs
    ):
        meshInfo = self.fbx.fbxInfo[meshIndex - 1]
        mesh = meshInfo[0]

        f = mesh.getFace(ti)

        if hasattr(mesh, 'getVertices'):
            rootTrans = (
                self.fkSolver
                .globalFrame(1)
                .translation
                .copy()
            )

            node = self.nodes[meshIndex]
            vertices = node[2]

            v1 = (
                vertices(f.vertexIndex(0))
                + rootTrans
            )

            v2 = (
                vertices(f.vertexIndex(1))
                + rootTrans
            )

            v3 = (
                vertices(f.vertexIndex(2))
                + rootTrans
            )

        else:
            v1 = self._getVertexInWorld(
                meshIndex,
                f.vertexIndex(0)
            )

            v2 = self._getVertexInWorld(
                meshIndex,
                f.vertexIndex(1)
            )

            v3 = self._getVertexInWorld(
                meshIndex,
                f.vertexIndex(2)
            )

        out2 = (
            v1 * baryCoeffs.x
            + v2 * baryCoeffs.y
            + v3 * baryCoeffs.z
        )

        return out2


def grab_frame(width: int, height: int, settle_renders: int = 3,
               blank_overlay: bool = False) -> np.ndarray:
    for _ in range(settle_renders):
        RE.renderOneFrame(True)

    raw, meta = ohi.window_pixel_data(ohi._ctx.name)
    _, h, w, ch = meta
    arr = np.frombuffer(bytes(raw), dtype=np.uint8).reshape(h, w, ch).copy()
    if ch == 4:
        arr = arr[:, :, :3]
    elif ch != 3:
        raise RuntimeError(f"Unexpected channel count {ch} in window_pixel_data")
    arr = np.ascontiguousarray(arr)
    if blank_overlay:
        x0, y0, x1, y1 = UI_OVERLAY_RECT
        x1 = min(x1, w)
        y1 = min(y1, h)
        arr[y0:y1, x0:x1, :] = 0
    return arr

def save_jpeg(path: Path, image: np.ndarray, quality: int = 92) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(path, format="JPEG", quality=quality, subsampling=1)
