import os,sys, pdb, math, random, copy 
if False:
    # using libcalab_ogre3d (ogre-next)
    from libcalab_ogre3d import RE, m, lua, control # see rendermodule.py
else:
     # using libcalab and ogre-python (ogre 1.4.1)
    from libcalab import m, lua, control 
    import media.rendermodule_ogre as RE # see rendermodule_ogre.py

import numpy as np


sceneGraph=None

def handleRendererEvent(ev,button,x,y):
    return sceneGraph.handleRendererEvent(ev, button, x, y)

def rotateY(scene_item, elapsedTime):
    #scene_item.orientation=scene_item.orientation*m.quater(1*elapsedTime, m.vector3(0,1,0))
    # without bbox rotation and events
    scene_item.localOrientation=m.quater(1*elapsedTime, m.vector3(0,1,0))*scene_item.localOrientation

def rotateY_splat(scene_item, elapsedTime):
    rotateY(scene_item, elapsedTime)
    scene_item.splat._update()  # splat is automatically updated only when camera changes. so do this manually when necessary.

def sceneEventFunction(scene_item, ev):
    print(scene_item.nodeId, ev)

def onCallback(w,userData):

    global sceneGraph

    if (w.id()=="global operations") :
        id= w.menuText()

        if (id=="create arrow") :
            sceneGraph.addEntity('arrow2.mesh', localScale=m.vector3(2,2,2), localPosition=m.vector3(0, 50, 0))
        elif (id=="create sphere") :
            sceneGraph.addEntity('sphere1010.mesh', localScale=40).material='green'
        elif (id=="create rotating sphere") :
            scene_item=sceneGraph.addEntity('sphere1010.mesh', localScale=40, localOrientation=m.quater(math.radians(90),m.vector3(1,0,0)))
            scene_item.material='red'
            scene_item.handleFrameMove=rotateY
            scene_item.eventFunction=sceneEventFunction
        elif id=='create lego':
            scene_item=sceneGraph.addGaussianSplat('lego.mesh', localScale=50, localOrientation=m.quater(math.radians(-90), m.vector3(1,0,0)))
        elif id=='create rotating lego':
            scene_item=sceneGraph.addGaussianSplat('lego.mesh', localScale=50, localOrientation=m.quater(math.radians(-90), m.vector3(1,0,0)))
            scene_item.handleFrameMove=rotateY_splat

    elif sceneGraph.onCallback(w, userData):
        pass
    else:
        pass




this=RE.createMainWin(sys.argv)

this.addText("try shift-L-drag \nor shift-R-drag")

this.create("Choice", "global operations","global operations")
this.widget(0).menuItems(["global operations", 'create arrow', 'create sphere', 'create lego', 'create rotating lego', 'create rotating sphere'])
this.widget(0).menuValue(0)


sceneGraph=RE.SceneGraph()
sceneGraph.createUI(this)

item=sceneGraph.addEntity('sphere1010.mesh', localScale=m.vector3(50))
item.material='shiny'

this.updateLayout()
print('ctor finished')
m.startMainLoop() # this finishes when program finishes
