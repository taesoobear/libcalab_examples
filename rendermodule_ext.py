from libcalab import m, RE, lua, control
# here RE denotes rendermodule (console mode). ( rendermodule != rendermodule_ogre)
import Ogre
import Ogre.RTShader
import Ogre.Bites
import Ogre.Numpy
import Ogre.HighPy as ohi
import Ogre.ImGui as imgui
import time,sys,os,math, random
import pdb
import ctypes
from pathlib import Path
import subprocess, re
import __main__
import numpy as np
_mouseInfo=None
_window_data=None
_layout=None
_luaEnv=None
_objectList=None
_activeBillboards={}
_softKill=False
_debugMode=False
start_time = time.time()

_inputTranslationNecessary={'setPosition':True, 'setScale':True, 'setOrientation':True, 'rotate':True, 'translate':True, 'scale':True}
_outputTranslationNecessary={'getPosition':True, 'getScale':True, 'getParent':True, '_getDerivedOrientation':True, '_getDerivedScale':True, '_getDerivedPosition':True, 'getOrientation':True, 'createChildSceneNode':True}

class GaussianSplat:
    def __init__(self, entity_name, filename):
        if filename[-5:]=='.mesh':
            self.entity=ogreSceneManager().createEntity(entity_name, filename)
        elif filename[-4:]=='.ply':
            mesh=ply_to_mesh(filename+"_converted.mesh", filename)
            self.entity= ogreSceneManager().createEntity( entity_name,filename+"_converted.mesh")
        else:
            assert(False)

        rootnode=RE.ogreRootSceneNode()
        self.node=rootnode.createChildSceneNode(entity_name+"_node")
        self.node.attachObject(self.entity)
        self.lastCamPos=Ogre.Vector3(1e5,1e5,1e5)
        if True:
            lego_entity=self.entity
            # get positions for sorting
            sub = lego_entity.getMesh().getSubMesh(0);
            vertexBuffer = sub.vertexData.vertexBufferBinding.getBuffer(0);
            numVertices = sub.vertexData.vertexCount;
            vdecl = sub.vertexData.vertexDeclaration

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

            if True:
                # create index buffer
                idata = sub.indexData;
                self.idata=idata
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

            self.node._update(True,False)
    def update(self):
        global _window_data
        cam = _window_data.camera
        camPos=cam.getDerivedPosition()
        camDist=(camPos-self.lastCamPos).squaredLength()
        if camDist>1:
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
            self.lastCamPos=Ogre.Vector3(camPos.x, camPos.y, camPos.z)


def eraseAllDrawn():
    global _objectList, _activeBillboards
    if _objectList is not None:
        _objectList.clear()
    _activeBillboards={}

def updateBillboards(fElapsedTime):
    # no longer necessary
    pass
# you can use the SceneNodeWrap class in the same way as Ogre.SceneNode
# basically, this is a way to inherit swig-bound c++ class in the python side.
# (pybind provides a much cleaner way but ogre-python uses swig.)
class SceneNodeWrap:
    def __init__(self, node : Ogre.SceneNode):
        self.sceneNode=node

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
def removeEntity(uid):
    global _debugMode
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
    try:
        assert(isinstance(uid, str))
        pNode=ogreSceneManager().getSceneNode(uid);
        removeEntity(pNode);
    except Exception as e:
        pass
def getSceneNode( uid):
    try:
        assert(isinstance(uid, str))
        pNode=ogreSceneManager().getSceneNode(uid);
        return pNode
    except Exception as e:
        return None

class ObjectList:
    def __init__(self):
        self.uid=m.generateUniqueName()+"_"
        self.mRootSceneNode=ogreRootSceneNode().createChildSceneNode(self.uid)
        self.isVisible=True
        self.nodes={}
    
    def clear(self):
        removeEntity(self.mRootSceneNode)
        self.mRootSceneNode=ogreRootSceneNode().createChildSceneNode(self.uid)
        self.nodes={}

    def createSceneNode(self, node_name):
        if node_name in self.nodes:
            removeEntity(self.nodes[node_name])
        return self.mRootSceneNode.createChildSceneNode(node_name)

    def registerEntity( self, node_name,  filename, materialName=None):
        entity_name=f"_entity_{self.uid}_{node_name}"
        pNode=	self.createSceneNode(node_name);
        pEntity=RE.ogreSceneManager().createEntity(entity_name, filename)
        pNode.attachObject(pEntity)
        pNode.setVisible(self.isVisible);

        if materialName is not None:
            pEntity.setMaterialName(materialName);
        return pNode;


class MeshToEntity:
    def __init(mesh, meshId, buildEdgeList=False, dynamicUpdate=False,useNormal=True, useTexCoord=True, useColor=True):
        self.mesh=mesh
    def createEntity(entityName, materialName='white'):
        pass
    def getLastCreatedEntity():
        pass
    def updatePositions(self, vertices=None):
        pass
    def updatePositionsAndNormals(self):
        pass

def path(path):
    from pathlib import Path
    path=os.path.normpath(path)
    return Path(path)

def ogreVersion():
    return 1
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
    def id(self):
        return self.uid
    def checkButtonValue(self, v=None):
        if v is None:
            return self._value
        else:
            self._value=v
    def sliderRange(self,s=None, e=None):
        if s is None:
            return self._range or (0,1)
        else:
            self._range=(s,e)

Widget.sliderValue=Widget.checkButtonValue

class Layout:
    def __init__(self):
        self.widgets=[]
    def create(self, type_name, uid,  title=None, pos=None, epos=None):
        self.widgets.append(Widget(type_name, uid, title,pos, epos))
    def addButton(self, title, on_screen_title=None):
        if on_screen_title is None:
            self.create('Button', title, title)
        else:
            self.create('Button', title, on_screen_title)
    def addCheckButton(self, title, initialValue):
        self.create('CheckButton', title, title)
        self.widget(0).checkButtonValue(initialValue)
    def findWidget(self, uid):
        for i,v  in enumerate(self.widgets):
            if v.uid==uid:
                return v
        return None
    def isLuaReady(self):
        global _luaEnv
        return _luaEnv.isLuaReady()
    def getglobal(self, *args):
        global _luaEnv
        return _luaEnv.getglobal(*args)

    def loadScript(self, *args):
        global _luaEnv
        return _luaEnv.loadScript(*args)
    def releaseScript(self, *args):
        global _luaEnv
        return _luaEnv.releaseSript(*args)
    def dofile(self, *args):
        global _luaEnv
        return _luaEnv.dofile(*args)
    def dostring(self, *args):
        global _luaEnv
        return _luaEnv.dostring(*args)
    def luaType(self, i:int):
        global _luaEnv
        return _luaEnv.luaType(i)
    def lunaType(self, i:int):
        global _luaEnv
        return _luaEnv.lunaType(i)
    def push(self, arg):
        global _luaEnv
        return _luaEnv.push(arg)
    def pushBoolean(self, arg:bool):
        global _luaEnv
        return _luaEnv.pushBoolean(arg)
    def call(self,*args):
        global _luaEnv
        return _luaEnv.call(*args)

# not ported yet
#			.def("pushnil", [](PythonExtendWin&l){lua_pushnil(l.L);})
#			.def("newtable", [](PythonExtendWin&l){lua_newtable(l.L);})
#			.def("settable", [](PythonExtendWin&l, int index){lua_settable(l.L, index);})
#			.def("getglobalNoCheck", &PythonExtendWin_wrapper::getglobalNoCheck)
#			.def("pushvalue",[](PythonExtendWin& l, int index){ lua_pushvalue(l.L, index);})
#			.def("pushnil",[](PythonExtendWin& l){ lua_pushnil(l.L);})
#			.def("next",[](PythonExtendWin& l, int index)->bool{ return lua_next(l.L, index);})
#			.def("getMemberFunc", &PythonExtendWin_wrapper::getMemberFunc)
#			.def("insert", &PythonExtendWin_wrapper::insert)
#			.def("replaceTop", (void (*)(PythonExtendWin& l, const char* key))&PythonExtendWin_wrapper::replaceTop)
#			.def("replaceTop", (void (*)(PythonExtendWin& l, int key))&PythonExtendWin_wrapper::replaceTop)
#			.def("printStack", &PythonExtendWin_wrapper::printStack)
#  			.def("popmatrixn", &PythonExtendWin_wrapper::popmatrixn, RETURN_REFERENCE)
#  			.def("pophypermatrixn", &PythonExtendWin_wrapper::pophypermatrixn, RETURN_REFERENCE)
#  			.def("popTensor", &PythonExtendWin_wrapper::popTensor, RETURN_REFERENCE)
#  			.def("popvectorn", &PythonExtendWin_wrapper::popvectorn, RETURN_REFERENCE)
#  			.def("popintvectorn", &PythonExtendWin_wrapper::popintvectorn, RETURN_REFERENCE)
#  			.def("poploader", [](PythonExtendWin& l)->MotionLoader*{
#  			.def("popMotion", [](PythonExtendWin& l)->Motion*{
#  			.def("popPose", [](PythonExtendWin& l)->Posture*{
#  			.def("popMotionDOF", [](PythonExtendWin& l)->MotionDOF*{
#  			.def("popVRMLloader", [](PythonExtendWin& l)->VRMLloader*{
#  			.def("popvector3", [](PythonExtendWin& l)->vector3*{
#  			.def("popvector2", [](PythonExtendWin& l)->vector2*{
#  			.def("poptransf", [](PythonExtendWin& l)->transf*{
#  			.def("popquater", [](PythonExtendWin& l)->quater*{
#  			.def("popmatrix4", [](PythonExtendWin& l)->matrix4*{
#  			.def("popVector3N", [](PythonExtendWin& l)->vector3N*{
#  			.def("popQuaterN", [](PythonExtendWin& l)->quaterN*{
#  			.def("popTStrings", [](PythonExtendWin& l)->TStrings*{
#  			.def("popboolN", [](PythonExtendWin& l)->boolN*{
#  			.def("popCollisionDetector", [](PythonExtendWin& l)->OpenHRP::CollisionDetector*{
#  			.def("popLoaderToTree", [](PythonExtendWin& l)->IK_sdls::LoaderToTree*{
#			.def("popboolean", &PythonExtendWin_wrapper::popboolean)
#  			.def("checkmatrixn", &PythonExtendWin_wrapper::checkmatrixn, RETURN_REFERENCE)
#  			.def("checkhypermatrixn", &PythonExtendWin_wrapper::checkhypermatrixn, RETURN_REFERENCE)
#  			.def("checkTensor", &PythonExtendWin_wrapper::checkTensor, RETURN_REFERENCE)
#  			.def("checkvectorn", &PythonExtendWin_wrapper::checkvectorn, RETURN_REFERENCE)
#  			.def("checkintvectorn", &PythonExtendWin_wrapper::checkintvectorn, RETURN_REFERENCE)
#		    .def("popnumber", &PythonExtendWin_wrapper::popnumber)
#		    .def("popstring", &PythonExtendWin_wrapper::popstring)
#		    .def("popint", &PythonExtendWin_wrapper::popint)
#			.def("set", &PythonExtendWin_wrapper::set)
#  			.def("isnil", &PythonExtendWin_wrapper::isnil)
#			.def("gettop",&PythonExtendWin_wrapper::gettop)
#			.def("pop",&PythonExtendWin_wrapper::pop)
#  			.def("popIntIntervals", [](PythonExtendWin& l)->intIntervals*{
#  			.def("popScaledBoneKinematics", [](PythonExtendWin& l)->ScaledBoneKinematics*{
#  			.def("popBoneForwardKinematics", [](PythonExtendWin& l)->BoneForwardKinematics*{
    def widget(self, n):
        return self.widgets[n-1]
    def updateLayout(self):
        pass
            
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

def draw(typename,*args):
    global _objectList
    if _objectList is None:
        _objectList=ObjectList()
    if typename=='Sphere':
        drawSphere(_objectList, *args)
def namedDraw(typename,*args):
    draw(typename, *args)
def timedDraw(time, typename,*args):
    pass
def drawBillboard(datapoints, nameid, material, thickness, billboard_type):
    pass


def dummyOnCallback(w, userData):
    pass
def ui_callback():
    global _layout, _mouseInfo, _window_data,_softKill
    # This function is called every frame to draw your custom ImGui elements

    #imgui.NewFrame()
    #imgui.ShowDemoWindow() # Displays the standard Dear ImGui demo window
    imgui.SetNextWindowSize(imgui.ImVec2(200, 200), imgui.Cond_Once)
    # -----------------------------
    # ImGui UI
    # -----------------------------
    if not imgui.Begin("Menu"):
        _softKill=True
    
    if hasattr(__main__,'onCallback'):
        onCallback=__main__.onCallback
    else:
        onCallback=dummyOnCallback
    try:
        for i,v  in enumerate(_layout.widgets):
            if v.type_name=='Button':
                if imgui.Button(v.title or v.uid):
                    onCallback(v, None)
            elif v.type_name=='Check_Button':
                changed,value=imgui.Checkbox(v.title or v.uid, v.checkButtonValue())
                if changed:
                    v.checkButtonValue(value)
                    onCallback(v, None)
            elif v.type_name=='Value_Slider':
                changed, my_value = imgui.SliderFloat(v.title or v.uid, v.sliderValue(), *v.sliderRange())
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

    # HandleMouseMessage2
    # Mouse buttons
    altPressed = imgui.GetIO().KeyAlt;
    ctrlPressed = imgui.GetIO().KeyCtrl;
    shiftPressed = imgui.GetIO().KeyShift;
    imgui.Text(f"pressed:{altPressed,ctrlPressed, shiftPressed}")

    if not hovered:
        #imgui.IsWindowHovered(  ) and not imgui.IsItemHovered():
        # Mouse info
        mouse_pos = imgui.GetMousePos()
        if _mouseInfo is None:
            _mouseInfo=lua.Table()
            _mouseInfo.drag=False

        _mouseInfo.pos=m.vector3(mouse_pos.x, mouse_pos.y,0)
        imgui.Text(f"Mouse position: ({(mouse_pos.x, mouse_pos.y)})")
        width=_window_data.window.getWidth()
        height=_window_data.window.getHeight()

        if imgui.IsMouseClicked(0) or imgui.IsMouseClicked(1) or imgui.IsMouseClicked(2):
            _mouseInfo.downMousePos=m.vector3(mouse_pos.x, mouse_pos.y,0)
            _mouseInfo.drag=True

        if imgui.IsMouseReleased(0) or imgui.IsMouseReleased(1) or imgui.IsMouseReleased(2):
            _mouseInfo.drag=False

        if _mouseInfo.downMousePos is not None and _mouseInfo.drag:
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
                    if hasattr(RE.viewpoint(), 'PanRight'):
                        RE.viewpoint().PanRight(x);
                        RE.viewpoint().PanUp(-y);
                elif imgui.IsMouseDown(0) : 
                    RE.viewpoint().TurnRight(-(dx.x/width))
                    RE.viewpoint().TurnUp(dx.y/(height/2.0))
                else:
                    dy= dx.y/(height/2.0)
                    dy*=m_scale

                    RE.viewpoint().ZoomOut(-dy)

                if hasattr(RE.viewpoint(),"CheckConstraint"):
                    RE.viewpoint().CheckConstraint();
                else:
                    RE.viewpoint().update()
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
    global _window_data, _layout,_luaEnv
    RE.createMainWin()

    _luaEnv=m.getPythonWin()
    m.getPythonWin=_getPythonWin  # override

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
    ohi.user_resource_locations.add("work/taesooLib/media")
    if os.path.exists('./media'):
        ohi.user_resource_locations.add("media")
    ohi._init_ogre(window_name, imsize)
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
    return _layout

def ogreRootSceneNode():
    return SceneNodeWrap(ogreSceneManager().getRootSceneNode())
m.ogreRootSceneNode=ogreRootSceneNode
def _tempFunc(pnode, cnode_name):
    return pnode.createChildSceneNode(cnode_name)
m.createChildSceneNode=_tempFunc

def viewpoint():
    return RE.viewpoint()

def ogreSceneManager():
    global _window_data
    return _window_data.scn_mgr

RE.ogreSceneManager=ogreSceneManager

def renderOneFrame(check):
    global start_time ,_softKill
    ctime=time.time()
    elapsed =  ctime- start_time
    start_time=ctime
    if check:
        if elapsed>1.0/30:
            elapsed=1.0/30
        _sceneGraphs=RE._sceneGraphs
        if _sceneGraphs is not None:
            for i, v in enumerate(_sceneGraphs):
                for k, vv in v.objects.items():
                    if vv.handleFrameMove is not None:
                        vv.handleFrameMove(vv, elapsed)

    evt=ohi.window_draw("Ogre ImGui")
    _updateView()
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

    stencilShadow=True
    depthShadow=True
    textureShadow=False
    highQualityRendering=False # set this true for high quality render
    numMainLights=5 # 5이상이어야 품질이 좋지만, m1 macbook에서 너무 느림
    lightVar=0.05

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
        else:
            mSceneMgr.setShadowTechnique(Ogre.SHADOWTYPE_STENCIL_MODULATIVE);
        mSceneMgr.setShadowColour(Ogre.ColourValue(0.5, 0.5, 0.5));

    rootnode =ogreRootSceneNode()
    lightnode=RE.createChildSceneNode(rootnode, "LightNode")
    ogreSceneManager().setAmbientLight(Ogre.Vector3(0.4))

    
    sc=math.pow(0.5, 1/numMainLights)
    light1D=0.9
    light1S=0.8
    lightOD=0.0
    lightOS=0.0

    if not stencilShadow :
        lightVar=0.1
        if depthShadow :
            light1D=0.8/numMainLights
            light1S=0.2/numMainLights
            lightOD=0.8/numMainLights
            lightOS=0.2/numMainLights
        sc=0.9
        if textureShadow :
            sc=0.995
            highQualityRendering=True
    else:
        sc=0.975

    if highQualityRendering :
        # high-quality
        numMainLights=100
        lightVar=0.04

        if stencilShadow :
            sc=math.pow(0.5, 1/numMainLights)
        else:
            if depthShadow :
                lightVar=0.2
                sc=0.99
            else:
                numMainLights=100
                lightVar=0.3
                sc=0.998
            RE.ogreSceneManager().setShadowTextureCount(numMainLights)

    RE.ogreSceneManager().setShadowColour(Ogre.Vector3(sc,sc,sc))


    for i in range(1,numMainLights +1):
        if i==1 :
            light=RE.ogreSceneManager().createLight("Mainlight")
        else:
            light=RE.ogreSceneManager().createLight("Mainlight"+str(i))
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
    light=RE.ogreSceneManager().createLight("FillLight")
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
    bgnode=RE.createChildSceneNode(rootnode , "BackgroundNode")
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
            line=re.sub(b"\s+", b"", f.readline().strip()) # remove spaces

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

        mesh = splat_to_mesh(mesh_name, xyz, color, covd, covu)
        return mesh
