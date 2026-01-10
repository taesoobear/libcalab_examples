from libcalab import m, lua, control
import rendermodule_ext as RE
import numpy as np
import pdb, math


this=RE.createMainWin()

scene_manager=RE.ogreSceneManager()

if True:
    lego=RE.GaussianSplat('lego', 'lego.mesh')
    lego.node.scale(100,100,100)
    lego.node.rotate(m.quater(math.radians(-90), m.vector3(1,0,0)))
elif False:
    lego=RE.GaussianSplat('lego', 'dataset/data/lego.ply')
    lego.node.scale(100,100,100)
    lego.node.rotate(m.quater(math.radians(-90), m.vector3(1,0,0)))
else:
    lego=RE.GaussianSplat('lego', '2024march-kotofuri-full.mesh')

lego.node.translate(0,50,0)


while True:

    lego.update()
    if not RE.renderOneFrame(True): break

