from libcalab import m, lua, control
import media.rendermodule_ogre as RE
import numpy as np
import pdb, math


def onCallback(w, uid):
    global lego
    if w.id()=='delete splat':
        if lego is not None:
            lego.release()
            lego=None

this=RE.createMainWin()
this.addButton('delete splat')
#RE.turnOffSoftShadows()  # For faster rendering, since libcalab_examples.git uses texture shadows, which can be slow.

scene_manager=RE.ogreSceneManager()

if True:
    lego=RE.GaussianSplat('lego', 'lego.mesh')
    lego.node.scale(100,100,100)
    lego.node.rotate(m.quater(math.radians(-90), m.vector3(1,0,0)))
elif False:
    lego=RE.GaussianSplat('lego', 'dataset/data/lego.ply')
    #lego.exportAsOgreMesh('media/lego2.mesh')
    lego.node.scale(100,100,100)
    lego.node.rotate(m.quater(math.radians(-90), m.vector3(1,0,0)))
else:
    lego=RE.GaussianSplat('lego', '2024march-kotofuri-full.mesh')

lego.node.translate(0,50,0)


while True:

    if not RE.renderOneFrame(True): break

