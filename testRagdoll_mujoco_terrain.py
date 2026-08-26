# this file contains a line-by-line python port of RagdollFallLCP_simple_v2.lua (taesooLib/Samples/classification/lua/)
import os
import sys
import pdb # use pdb.set_trace() for debugging
#import code # or use code.interact(local=dict(globals(), **locals())) for debugging. see below.
import math
import random
import mujoco
import copy

if False:
    # to use ogre-next
    from libcalab_ogre3d import m, lua, RE, control
else:
    from libcalab import m, lua, control
    import media.rendermodule_ogre as RE
import numpy as np
from easydict import EasyDict as edict # pip3 install easydict

def terrain_height_ray(sim, p, max_y=100.0, geomgroup=np.array([0, 1, 0, 0, 0, 0], dtype=np.uint8)):
    model=sim.model
    data=sim. data
    x=p.x
    z=p.z
    pnt = np.array([x, max_y, z], dtype=np.float64)
    vec = np.array([0.0, -1.0, 0.0], dtype=np.float64)  
    geomid = np.array([-1], dtype=np.int32)
    #bodyexclude=-1 can be used to indicate that all bodies are included.
    distance = mujoco.mj_ray(model, data, pnt, vec, geomgroup=geomgroup, flg_static=1, bodyexclude=-1, geomid=geomid)

    if geomid[0] == -1:
        return None, geomid[0]  # 没撞到任何 geom
    else:
        return max_y - distance, geomid[0]
mLoader=None

model=edict() # use lua.dynamic_list() instead for 0-indexed array.
#model.file_name= "../Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T_boxfoot.wrl" 
model.file_name= "work/taesooLib/Resource/motion/MOB1/hanyang_lowdof_T.wrl" 
#model.mot_file= "../Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T_wd2_all.dof"
#model.mot_file= "../Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T_MOB1_Run_F_Jump.dof" model.initialHeight=0.13 # meters
model.mot_file= None 
model.initialHeight=2.3 # meters
model.k_p_PD=5 # Nm/rad
model.k_d_PD=1 #  Nms/rad. 
#model.mot_file= "../Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T_locomotion_hl.dof"
model.frame_rate=30 # mocap frame rate
model.start=0
model.timestep=1/240
model.rendering_step=1/30

# convert posedof to sphericalQ and sphericalDQ format. 

def onFrameChanged( iframe):
    global mLoader, mRagdoll
    this=m.getPythonWin()
    if mLoader and this.findWidget("simulation").checkButtonValue() :
        niter=math.floor(model.rendering_step/model.timestep+0.5)
        mRagdoll.frameMove(niter)


def frameMove(fElapsedTime):
    RE.updateBillboards(fElapsedTime)


def dtor():
    global mSkin, mSkin2, mTimeline
    # remove objects that are owned by C++
    mSkin=None
    mSkin2=None
    mTimeline=None
 


def _start(this):
    global mLoader, mFloor, simulator, mRagdoll, mSkin, mSkin2, container, mMotionDOF, mTimeline
    dtor()
    mTimeline=RE.Timeline("Timeline", 1000000, 1/30)
    RE.motionPanel().motionWin().playFrom(0)
    print("start")
    mLoader=RE.WRLloader(model.file_name)

    mLoader.printHierarchy()
    if model.mot_file:
        container=m.MotionDOFcontainer(mLoader.dofInfo, model.mot_file)
        mMotionDOF=container.mot
    else:
        mMotionDOF=None

    #mFloor=RE.WRLloader("../Resource/mesh/floor_y.wrl")
    mFloor=RE.WRLloader("work/taesooLib/Resource/terrain/height_field.png", 20, 20, 1, 1,1)
    mFloor.setPosition(m.vector3(-5,0,-5))

    drawSkeleton=this.findWidget("draw skeleton").checkButtonValue()

    simulatorParam=edict()
    simulatorParam.timestep=model.timestep
    simulatorParam.debugContactParam=[10, 0, 0.01, 0, 0] # size, tx, ty, tz, tfront
    mRagdoll= RagdollSim(mLoader, drawSkeleton, mMotionDOF, simulatorParam)
    mRagdoll.drawDebugInformation=False

    mSkin2=RE.createVRMLskin(mFloor, False)
    mSkin2.setScale(100,100,100)


def onCallback(w, userData):
    if w.id()=="Start" :
        _start(m.getPythonWin())

    elif w.id()=="TestRayPick":

        global mLoader, mRagdoll
        sim=mRagdoll.simulator
        numSample=160
        range_x=10
        points=m.matrixn(numSample*numSample,3)
        c=0
        for i in range(numSample):
            for j in range(numSample):
                p=m.vector3()
                p.x=m.map(i, 0, numSample, -range_x, range_x)
                p.z=m.map(j, 0, numSample, -range_x, range_x)
                
                y,_=terrain_height_ray(sim, p)
                if y: 
                    p.y=y
                else:
                    p.y=0.1
                points.row(c).setVec3(0, p)
                c+=1
                
        assert(c==numSample*numSample)
        thickness=10

        RE.drawBillboard(points*100,'predicted','blueCircle',thickness,'QuadListV')

class RagdollSim:
    def __init__(self, loader, drawSkeleton, motdof, simulatorParam):
        if drawSkeleton==None:
            drawSkeleton = True 
        simLoaders=[]

        self.skin=RE.createVRMLskin(loader, drawSkeleton)
        self.skin.setThickness(0.03)
        self.skin.setScale(100,100,100)

        simLoaders.append(loader)
        floor=mFloor or RE.WRLloader("work/taesooLib/Resource/mesh/floor_y.wrl")
        simLoaders.append(floor)

        sim=control.MujocoSim(simLoaders, 'work/__temp_ragdoll_scene.xml', simulatorParam.timestep)
        sim.setGVector(m.vector3(0,9.8,0))

        self.simulator=sim

        kp=lua.zeros(loader.dofInfo.numDOF())
        kd=lua.zeros(loader.dofInfo.numDOF())
        kp.slice(7,0).setAllValue(model.k_p_PD)
        kd.slice(7,0).setAllValue(model.k_d_PD)
        self.simulator.setStablePDparam_dof(0, kp, kd)
        # adjust initial positions

        self.motionDOF=motdof
        self.simulationParam=simulatorParam

        if self.motionDOF :
            for i in range(0, self.motionDOF.numFrames()-1 +1) :
                self.motionDOF.row(i).set(1,self.motionDOF.row(i).get(1)+(model.initialHeight or 0) )


        else:
            motdofc=m.MotionDOFcontainer(loader.dofInfo)
            motdofc.resize(10)
            for i in range(0, 9 +1) :
                motdofc.mot(i).setAllValue(0)
                motdofc.mot(i).set(3, 1) # assuming quaternion (free root joint)

            self.motionDOF=motdofc.mot
            for i in range(0, self.motionDOF.numFrames()-1 +1) :
                self.motionDOF.row(i).set(1,self.motionDOF.row(i).get(1)+(model.initialHeight or 0) )

        self.DMotionDOF=calcDerivative(self.motionDOF)
        self.DDMotionDOF=self.DMotionDOF.derivative(120)

        if self.motionDOF :
            model.start=min(model.start, self.motionDOF.numFrames()-1)
            initialState=m.vectorn()
            initialState.assign(self.motionDOF.row(model.start))

            print("initialState=",initialState)
            self.simulator.setLinkData(0, m.Physics.JOINT_VALUE, initialState)

            if self.DMotionDOF :
                initialVel=self.DMotionDOF.row(model.start).copy()
                self.simulator.setLinkData(0, m.Physics.JOINT_VELOCITY, initialVel)

            self.simulator.initSimulation()
        else:
            assert(False)

        self.referenceFrame=model.start

        #    debug.debug()
        self.skin.setPoseDOF(self.simulator.getPoseDOF(0))

        #self.skin.setMaterial("lightgrey_transparent")

        #self.simulator.setGVector(m.vector3(0,0,9.8))
        self.simulator.setGVector(m.vector3(0,9.8,0))
        self.simulator.initSimulation()
        self.loader=loader
        self.floor=floor # have to be a member to prevent garbage collection


    def dtor(self ):
        # remove objects that are owned by C++
        if self.skin:
            self.skin=None

        self.simulator=None


    def frameMove(self, niter):
        global model

        simulator=self.simulator
        for iter in range(1,niter +1) :

            refFrame=self.referenceFrame+model.timestep*model.frame_rate
            print(refFrame)
            if refFrame>self.motionDOF.numFrames()-1 :
                refFrame=0
            self.referenceFrame=refFrame
            pose_d=self.motionDOF.row(math.floor(refFrame))
            dpose_d=self.DMotionDOF.row(math.floor(refFrame))
            spd_tau=m.vectorn()
            simulator.calculateStablePDForces_dof(0, pose_d,dpose_d, spd_tau)
            simulator.setTau(0, spd_tau)
            simulator.stepSimulation()

        self.skin.setPoseDOF(self.simulator.getPoseDOF(0))


        if self.drawDebugInformation:
            forces=m.vector3N()
            torques=m.vector3N()
            for i in range(1, self.loader.numBone()-1 +1) :
                bone=self.loader.VRMLbone(i)

                force=self.simulator.getCOMbasedContactForce(0, i)
                if force.F().length()>0 :
                    pos=self.simulator.getWorldState(0).globalFrame(i)*bone.localCOM()
                    forces.pushBack(pos*100)
                    forces.pushBack(pos*100+force.F())
                    torques.pushBack(pos*100)
                    torques.pushBack(pos*100+force.M())


            RE.namedDraw('Traj', forces.matView(), 'contactforces', 'solidred', 0, 'LineList' )
            RE.namedDraw('Traj', torques.matView(), 'contacttorques', 'solidblue', 0, 'LineList' ) 



def calcDerivative(motionDOF):
    dmotionDOF=m.matrixn()

    dmotionDOF.setSize(motionDOF.numFrames(), motionDOF.numDOF())

    for i in range(1, motionDOF.rows()-2 +1) :
        calcDerivative_row(i,dmotionDOF, motionDOF)


    # fill in empty rows
    dmotionDOF.row(0).assign(dmotionDOF.row(1))
    dmotionDOF.row(dmotionDOF.rows()-1).assign(dmotionDOF.row(dmotionDOF.rows()-2))
    return dmotionDOF


def calcDerivative_row(i, dmotionDOF, motionDOF):
    global model
    dmotionDOF_i=dmotionDOF.row(i);
    dmotionDOF_i.sub(motionDOF.row(i+1), motionDOF.row(i)) # forward difference

    frameRate=120
    if model :
        frameRate=model.frame_rate 
    dmotionDOF_i.rmult(frameRate)

    assert(motionDOF.dofInfo.numSphericalJoint()==1) 
    # otherwise following code is incorrect
    T=motionDOF.row(i).toTransf(0)
    V=T.twist( motionDOF.row(i+1).toTransf(0), 1/frameRate)
    dmotionDOF_i.setVec3(0, V.V())
    dmotionDOF_i.setVec3(4, V.W())



# main
RE.createMainWin(sys.argv)
mSkin=None
mSkin2=None
mTimeline=None
this=m.getPythonWin()
    
this.create("Button", "Start", "Start")
this.create("Button", "TestRayPick", "TestRayPick")
#    this.widget(0).buttonShortcut("FL_ALT+s")

this.create("Check_Button", "simulation", "simulation")
this.widget(0).checkButtonValue(1) # 1 for imediate start

this.create("Button", "single step", "single step")

this.create("Check_Button", "draw skeleton", "draw skeleton")
this.widget(0).checkButtonValue(0)


this.updateLayout()
this.redraw()

RE.viewpoint().vpos.assign(m.vector3(330.411743, 69.357635, 0.490963))
RE.viewpoint().vat.assign(m.vector3(-0.554537, 108.757057, 0.477768))
RE.viewpoint().update()
RE.viewpoint().TurnRight(math.radians(0))
_start(this)


while True:
    if not RE.renderOneFrame(True): break

