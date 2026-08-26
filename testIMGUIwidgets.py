# this file contains a line-by-line python port of testWidgets.lua (taesooLib/Samples/classification/lua/)
import os,sys, pdb, math, random, copy, code
# 현재 경로 안에 work폴더가 있어야 함. (ln -s ~/sample_python/work ./work)
from libcalab import m, lua, control
import media.rendermodule_ogre as RE 

RE._layoutHeight=40
g_persistentStates=lua.Table() # lua-style dictionary (dict + list)

def onCallback(w, userData):
    # libcalab style ui (simpler)
    drawText(w.id())
def onImGui(imgui):
    # imgui style ui (immediate mode)
    global g_persistentStates
    self=g_persistentStates

    io = imgui.GetIO()
    window_width=300*RE._ui_scale

    parentwin_width=m.FltkRenderer().renderWindowWidth()
    imgui.SetNextWindowPos(imgui.ImVec2(parentwin_width-window_width,0), imgui.Cond_Once)
    imgui.SetNextWindowSize(imgui.ImVec2(window_width,window_width*2), imgui.Cond_Once)
    # persistent states
    if 'ui_init' not in self:
        self.ui_init = True
        self.check = True
        self.int_value = 5
        self.float_value = 0.5
        self.text = "hello"
        self.combo_idx = 0
        self.color = (1.0, 0.5, 0.2, 1.0)

    
    mouse_hovered=False # should return this

    if imgui.Begin("Widget Examples"):
        mx = imgui.GetMousePos()
        wx  = imgui.GetWindowPos()
        wh = imgui.GetWindowSize()
        mouse_hovered = (
            wx.x <= mx.x <= wx.x + wh.x and
            wx.y <= mx.y <= wx.y + wh.y)

        # ------------------------------------------------------------
        # Text
        # ------------------------------------------------------------
        imgui.Text("Hello ImGui")
        imgui.TextDisabled("Disabled-looking text")

        imgui.Separator()

        # ------------------------------------------------------------
        # Button
        # ------------------------------------------------------------
        if imgui.Button("Button"):
            print("clicked")

        imgui.SameLine()

        if imgui.Button("Another"):
            print("another clicked")


        # ------------------------------------------------------------
        # Checkbox
        # ------------------------------------------------------------
        changed, check = imgui.Checkbox("Enable", self.check)
        if changed:
            self.check=check

        # ------------------------------------------------------------
        # Integer input (crashes)
        # ------------------------------------------------------------
        #changed, self.int_value = imgui.InputInt( "Integer", self.int_value)

        # ------------------------------------------------------------
        # Float input (crashes)
        # ------------------------------------------------------------
        #changed, self.float_value = imgui.InputFloat( "Float", self.float_value)

        # ------------------------------------------------------------
        # Slider
        # ------------------------------------------------------------
        changed, float_value = imgui.SliderFloat(
            "Float Slider",
            self.float_value,
            0.0,
            1.0
        )
        if changed:
            self.float_value=float_value

        # 남은 폭 전체 사용
        imgui.SetNextItemWidth(-1)
        changed, int_value = imgui.SliderInt(
            "Int Slider",
            self.int_value,
            0,
            100
        )
        if changed:
            self.int_value=int_value



        # ------------------------------------------------------------
        # Text input
        # ------------------------------------------------------------
        changed= imgui.InputText(
            "Text",
            self.text,
            256
        )
        # there seems to be no way to get the text back.

        # ------------------------------------------------------------
        # Radio buttons
        # ------------------------------------------------------------
        if imgui.RadioButton("Mode A", self.combo_idx == 0):
            self.combo_idx = 0

        imgui.SameLine()

        if imgui.RadioButton("Mode B", self.combo_idx == 1):
            self.combo_idx = 1

        # ------------------------------------------------------------
        # Progress bar
        # ------------------------------------------------------------
        imgui.ProgressBar(
            self.float_value,
            imgui.ImVec2(-1, 0)
        )

        # ------------------------------------------------------------
        # Collapsing section
        # ------------------------------------------------------------
        if imgui.CollapsingHeader("Advanced"):
            imgui.Text("Advanced options")

            changed, float_value = imgui.DragFloat(
                "Parameter",
                self.float_value,
                0.001
            )

        # ------------------------------------------------------------
        # Tree
        # ------------------------------------------------------------
        if imgui.TreeNode("Skeleton"):
            imgui.Text("Hips")
            imgui.Text("Spine")
            imgui.Text("Head")
            imgui.TreePop()

        # ------------------------------------------------------------
        # Child window
        # ------------------------------------------------------------
        if imgui.BeginChild("child", imgui.ImVec2(0, 100), True):
            for i in range(10):
                imgui.Text(f"Item {i}")
        imgui.EndChild()

        # ------------------------------------------------------------
        # Tooltip
        # ------------------------------------------------------------
        imgui.Text("Hover me")

        if imgui.IsItemHovered():
            imgui.SetTooltip("This is a tooltip")

    imgui.End()
    return mouse_hovered


#main 
this=RE.createMainWin()

# createWidgets using taesooLib 
this.addButton("Button", "button a") # events goes to onCallback

while True:
    if not RE.renderOneFrame(True): break

