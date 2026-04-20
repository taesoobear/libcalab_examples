# CALAB Character Animation Libraries

Currently, CALAB ([http://calab.hanyang.ac.kr](http://calab.hanyang.ac.kr)) provides two libraries for character animation:

- **libcalab**: a console-mode library.
- **libcalab_ogre3d**: a library that uses **Ogre-Next** for rendering.  

Both libraries share the same usage, with the only difference being whether the output is displayed on screen or not.  

Most examples provided here combine **libcalab** with **ogre-python**, enabling rendering using **Ogre 1.4.1**. These examples are currently the most extensive set available for **ogre-python**.  

**Important notes:**

- Unlike **libcalab_ogre3d**, **ogre-python** does not run reliably on Windows.
- Not all examples that **libcalab_ogre3d** supports are currently working in this set, but this will be improved in the future.  
- **libcalab_ogre3d** examples are on github: taesoobear/IPCDNNwalk
- If **libcalab_ogre3d** runs on your system, it should be used, as its shadow rendering is much faster, and provides more functionalities.
- **libcalab + ogre-python** supports faster Gaussian splat rendering. 
- **libcalab_ogre3d** now also supports Gaussian splat rendering, albeit slower.
 
# Target platforms
ogre-python: MacOS (ARM) and linux (AMD64) with python 3.12 only.
libcalab and libcalab-ogre3d: All desktop platforms with python 3.12 only.

# How to run examples
=
The current latest ogre-python 14.5.0 doesn't work. 
```
   pip3 install --upgrade libcalab
   pip3 install ogre-python==14.4.1
  pip3 install numpy torch easydict 
  python3 SceneEditor.py
```

