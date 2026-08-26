import os, sys, pdb, math
from pathlib import Path
import numpy as np
import cv2

 # using libcalab and ogre-python (ogre 1.4.1)
from libcalab import m, lua, control 
import media.rendermodule_ogre as RE # see rendermodule_ogre.py

from easydict import EasyDict as edict

VIDEO_PATH = RE.path("~/sample_python/work/gym_parable/videoplayback.mp4").expanduser()

def onFrameChanged(iframe):
    global g_cap, g_texture
    if g_cap is None or not g_cap.isOpened():
        return False

    timer=m.Timer()
    success, image = g_cap.read()
    if not success:
        print("End of video or error reading frame.")
        return False


    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image_rgb.flags.writeable = False 

    RE.output('g_cap.read (ms):', timer.stop2()/1e3)

    timer.start()

    materialName='image'

    image_shape=image_rgb.shape
    #좌표계가 libcalab_ogre3d와 다름. 
    image_rgb=cv2.resize(image_rgb, (1024,1024), interpolation=cv2.INTER_AREA)

    # draw image: (currently only works on taesooLib-legacy and taesooLib (ogre-next3 branch).)
    if g_texture is None:
        g_texture=image_rgb
        m.renderer().createDynamicTexture(materialName, g_texture)
        RE.draw("Box", m.transf(m.quater(math.radians(-90), m.vector3(0,0,1)), m.vector3(1,1,0)), 'box', m.vector3(image_shape[0]*0.003,image_shape[1]*0.003,1), 100, materialName)

    # ideally, preloading all frames (using different names) should be much faster but this (overwriting) is fast enough.
    m.renderer().updateDynamicTexture(materialName, image_rgb)
    RE.output('texture update (ms):', timer.stop2()/1e3)

    image_rgb.flags.writeable = True







g_cap = None


def init_cv(video_path_str):
    global g_cap
    g_cap = cv2.VideoCapture(video_path_str)
    if not g_cap.isOpened():
        print(f"Error: Could not open video file: {video_path_str}")
        return False
    return True

g_texture=None



# main
this=RE.createMainWin(sys.argv)
this.addCheckButton('draw video frame', True)
this.updateLayout()

# rotate light
osm=RE.ogreSceneManager()
if osm.hasSceneNode("LightNode") :
    lightnode=osm.getSceneNode("LightNode")
    lightnode.rotate(m.quater(math.radians(0),m.vector3(0,1,0)))


g_timeline = RE.Timeline("Timeline", 1000, 1/30) 

RE.viewpoint().vpos.assign(m.vector3(50, 100, 300)) # Position
RE.viewpoint().vat.assign(m.vector3(50, 100, 0))   # Look at
RE.viewpoint().update()

if not init_cv(VIDEO_PATH):
    print(f"Error: Could not open video file: {VIDEO_PATH}")
    # Optionally, fall back to webcam or exit
    # if not init_cv(0): # Try webcam
    #     sys.exit(1)

print("ctor finished. Mixamo character loaded.")

onFrameChanged(0)
while True:
    if not RE.renderOneFrame(True): 
        break 

    #if not main_loop_step():
    #    break
    # cv2.waitKey(1) 

if g_cap:
    g_cap.release()
cv2.destroyAllWindows()
print("Main loop finished.")


