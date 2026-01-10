import os, sys, pdb, math, random


import numpy as np
import media.rendermodule_ogre as RE # should be earlier than import libcalab 
from libcalab import m, lua, control

layout=None
def frameMove(fElapsedTime):
    pass

def drawAll():
    global layout
    if layout.findWidget('draw spheres').checkButtonValue() :
        if True:
            # draw spheres. using cm unit (default).
            pos=m.vector3(-100,20,0)
            RE.namedDraw("Sphere", pos, "ball1", "red", 5)
            pos+=m.vector3(50,0,0)
            RE.namedDraw("Sphere", pos, "ball2", "blue", 10)
            pos+=m.vector3(50,0,0)
            # draw and namedDraw has the same function signature.
            # The difference is in the caption.
            # (ball3 doesn't have any visible caption)
            RE.draw("Sphere", pos, "ball3", "green", 15)

            # after 2,4,6 seconds, these spheres will be erased.
            # no nameID necessary.
            RE.timedDraw(6, "Sphere", pos, "blue", 20)
            RE.timedDraw(4, "Sphere", pos, "green", 25)
            RE.timedDraw(2, "Sphere", pos, "red", 30)

            # both position and radius. using meter unit.
            RE.draw("SphereM", m.vector3(0,0,-1), "bigBall", "red_transparent", 1)

            for i in range(1, 20+1):
                RE.timedDraw(i*0.5, "Sphere", m.vector3(i*30, 0, 10), "blue", 20)


def eraseAll():
    RE.eraseAllDrawn()

def onCallback(w, userData):
    if w.id()=='set position':
        v=w.sliderValue()
        #RE.draw("Box", m.transf(m.quater(1,0,v,0).normalized(), m.vector3(0,1+v,0)), 'box', m.vector3(1,2,1)*0.1, 100)
        RE.draw("Sphere", m.vector3(0,1+v,0)*100, 'center_new')
    elif w.id()=='eraseAll':
        eraseAll()
    elif w.id()=='drawAll':
        drawAll()
    elif w.id()=='memTest':
        for i in range(1000):
            print(i)
            eraseAll()
            m.renderOneFrame(False)
            drawAll()
            m.renderOneFrame(False)
    elif w.id()[0:5]=='draw ':
        eraseAll()
        drawAll()


layout=RE.createMainWin()
layout.create("Check_Button", 'draw spheres', 'draw spheres')
layout.findWidget('draw spheres').checkButtonValue(True)

layout.create("Value_Slider", 'set position', 'set position', 1)
layout.widget(0).sliderRange(-0.1,0.5)
layout.widget(0).sliderValue(0)

layout.addButton('eraseAll')
layout.addButton('drawAll')
layout.addButton('memTest')
layout.updateLayout() # unnecessary but for compatibility with libcalab_ogre3d

drawAll()

while True:
    if not RE.renderOneFrame(True): break

