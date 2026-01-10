# this file contains a line-by-line python port of testDebugDraw.lua (taesooLib/Samples/classification/lua/)
import os, sys, pdb, math, random

import numpy as np
from libcalab import m, lua, control
import media.rendermodule_ogre as RE 

def drawAll():
    if True:
        # draw mesh
        mesh=m.Mesh()

        mesh.loadOBJ('work/taesooLib/Resource/mesh/bag_for_justin.obj')
        #mesh.saveMesh('../Resource/mesh/bag_for_justin.stl')
        #mesh.loadMesh('../Resource/mesh/bag_for_justin.stl')
        #mesh.loadMesh('./genesis_tutorials/franka_emika_panda/assets/link0.stl')
        if True:
            # vertex color doesn't work in ogre2 so let's use a texture instead.
            # create a texture buffer (to use a colormap)
            mesh.createTextureBuffer()

            for i in range(0, mesh.numVertex()-1 +1) :
                if i<mesh.numVertex()/2:
                    mesh.getTexCoord(i).set(1,0) 
                else:
                    mesh.getTexCoord(i).set(1,1) 


        # use_vertexcolor material is defined in color.material
        #meshToEntity, node=mesh.drawMesh('use_vertexcolor', 'mesh_node')
        meshToEntity, node=mesh.drawMesh('colormap', 'mesh_node')
        node.translate(0,50,0)
        node.scale(100,100,100)

        if True:
            # test mesh simplification
            mesh2=m.Mesh()
            succeeded=lua.M(mesh,'simplify', mesh2, 0.5, 7.0)
            if succeeded:
                meshToEntity2, node2=mesh2.drawMesh('colormap', 'mesh_node3')
                node2.translate(-100,50,0)
                node2.scale(100,100,100)
            else:
                print('failed')



    mesh2=m.Mesh()
    mesh2._initBox(100,100,100)
    _,node2=mesh2.drawMesh('checkboard', 'mesh_node2')
    node2.translate(100,0,0)

    RE.draw("Box", m.transf(m.quater(1,0,0,0), m.vector3(0,1,0)), 'box', m.vector3(1,2,1)*0.1, 100)

def ctor(this):
    # see testdrawing.lua also
    this.create("Button", 'eraseAll', 'eraseAll')
    this.updateLayout()

    drawAll()




def dtor():
    RE.removeEntity(RE.getSceneNode("mesh_node"))


def onCallback(w, userData):
    if w.id()=='eraseAll' :
        RE.removeEntity(RE.getSceneNode("mesh_node"))


            



# main

RE.createMainWin(sys.argv)
ctor(m.getPythonWin())
print('ctor finished')
m.startMainLoop() # this finishes when program finishes

