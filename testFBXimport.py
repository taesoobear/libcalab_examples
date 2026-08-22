# this file contains a line-by-line python port of testFBXimport.lua (taesooLib/Samples/classification/lua/)
import os,sys,pdb,math

from pathlib import Path

if False:
    # using libcalab_ogre3d (ogre-next)
    from libcalab_ogre3d import RE, m, lua, control # see rendermodule.py
else:
    from libcalab import lua,m,control, __version__
    import media.rendermodule_ogre as RE 
    if __version__<'0.3.3':
        raise Exception("install latest libcalab!")

if not RE.path('../Mixamo').exists():
    print("clone ../Mixamo first.")
    os._exit(0)

import numpy as np


def onFrameChanged(iframe):
    global skin1, skin2
    print(iframe)
    skin1.setPose(fbx.loader.mMotion.pose(iframe))
    skin2.setPose(fbx.loader.mMotion.pose(iframe))


            

this=RE.createMainWin(sys.argv)


#RE.turnOffSoftShadows()
skelFile='../Mixamo/fbx_withSkin/bigvegas_Walking.fbx' 
skinScale=1

fbx=RE.FBXloader(skelFile, skinScale=skinScale, useTexture=True, simplifyMesh=False)

# draw skeleton
skin1=RE.createSkin(fbx.loader)
skin1.setScale(skinScale, skinScale, skinScale)

# draw mesh
skin2=RE.createFBXskin(fbx)
skin2.setScale(skinScale, skinScale, skinScale)

if False:
    # test memory
    skins=[None]*10
    for j in range(200):
        for i in range(10):
            skins[i]=RE.createFBXskin(fbx)
            skins[i].setScale(skinScale, skinScale, skinScale)
            skins[i].setTranslation(50*i,0,0)
            skins[i].applyAnim(fbx.loader.mMotion)


g_motion2=fbx.loader.mMotion
mTimeline=RE.Timeline(g_motion2.numFrames(), 1/g_motion2.frameRate())
m.startMainLoop() # this finishes when program finishes
