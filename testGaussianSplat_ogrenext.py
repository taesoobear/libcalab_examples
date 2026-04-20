from libcalab_ogre3d import m, RE, lua, control # pip install libcalab-ogre3d (0.2.8 or later)
import numpy as np
import pdb, math

# please download the latest versions:
# pip install libcalab-ogre3d
# also, if ./work exists,
# cd work; git pull origin master
# the ply files can be downloaded from:

# original splat files: https://huggingface.co/VladKobranov/splats/tree/main
# splat2ply converter: https://github.com/patrikant/splat2plyconverter.git 

this=RE.createMainWin()
scene_manager=RE.ogreSceneManager()

if True:
    lego=RE.GaussianSplat('lego', 'dataset/data/lego.ply')
    #lego.exportAsOgreMesh('media/lego2.mesh')
    lego.node.scale(100,100,100)
    lego.node.rotate(m.quater(math.radians(-90), m.vector3(1,0,0)))
else:
    lego=RE.GaussianSplat('lego', '2024march-kotofuri-full.mesh')

lego.node.translate(0,50,0)


while True:

    if not RE.renderOneFrame(True): break

