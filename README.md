# CALAB Character Animation Libraries

Currently, CALAB ([http://calab.hanyang.ac.kr](http://calab.hanyang.ac.kr)) provides two libraries for character animation:

- **libcalab**: a console-mode library.
- **libcalab_ogre3d**: a library that uses **Ogre-Next** for rendering.  

Both libraries share the same usage, with the only difference being whether the output is displayed on screen or not.  

The examples provided here combine **libcalab** with **ogre-python**, enabling rendering using **Ogre 1.4.1**. These examples are currently the most extensive set available for **ogre-python**.  

**Important notes:**

- Unlike **libcalab_ogre3d**, **ogre-python** does not run reliably on Windows, so Windows is not officially supported.  
- Not all examples that **libcalab_ogre3d** supports are currently working in this set, but this will be improved in the future.  
- If **libcalab_ogre3d** runs on your system, it should be used, as its shadow rendering is much faster, and provides more functionalities.
- **libcalab_ogre3d** examples are on github: taesoobear/IPCDNNwalk
- **libcalab + ogre-python** supports Gaussian splat rendering, which is not currently supported by **libcalab_ogre3d**.
 
# Target platforms
MacOS (ARM) and linux (AMD64) with python 3.12 only.

# How to run examples
=
```
   pip3 install --upgrade libcalab
  pip3 install numpy torch easydict ogre-python
  python3 SceneEditor.py
```

