# this file contains a line-by-line python port of testDebugDraw.lua (taesooLib/Samples/classification/lua/)
import os
import sys
import pdb # use pdb.set_trace() for debugging
import math

from pathlib import Path
from libcalab import m, lua, control
import media.rendermodule_ogre as RE 


import numpy as np
from easydict import EasyDict as edict # pip3 install easydict


def onFrameChanged(iframe):
    global mSkin, mMotionDOF
    mSkin.setPoseDOF(mMotionDOF.row(iframe))

this=RE.createMainWin(sys.argv)
this.updateLayout()


mLoader=RE.WRLloader ("work/taesooLib/Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T.wrl")
mMotionDOFcontainer=m.MotionDOFcontainer(mLoader.dofInfo,"work/taesooLib/Resource/motion/locomotion_hyunwoo/hyunwoo_lowdof_T_MOB1_Run_F_Jump.dof")
mMotionDOF=mMotionDOFcontainer.mot

# translate the motion 7cm up
mMotionDOF.matView().array[:,1]+=0.01


mSkin= RE.createVRMLskin(mLoader, True);    # to create character 
mSkin.setScale(100,100,100);                    # motion data is in meter unit while visualization uses cm unit.
mSkin.setPoseDOF(mMotionDOF.row(0));

m.viewpoint().vpos.set(0, 50, 600)
m.viewpoint().vat.set(0,40,0)
m.viewpoint().update()

this.updateLayout()

mTimeline=RE.Timeline(mMotionDOF.numFrames(), 1.0/30.0)

m.startMainLoop() # this finishes when program finishes
