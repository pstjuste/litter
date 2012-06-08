#!/usr/bin/env python
# Running this script will build an exe if executed on Windows, and an
# application bundle (.app) if executed on Mac OS X
# Note that icons should be built before running this script. (We don't do this
# automatically because the icon-building script wouldn't work on Windows)

# before running on OSX:
# - Install Python 2.7 (we used 2.7.3) from python.org
# curl http://pypi.python.org/packages/2.7/s/setuptools/ # don't break this line
#      setuptools-0.6c11-py2.7.egg > setuptools-0.6c11-py2.7.egg
# sudo sh setuptools-0.6c11-py2.7.egg
# rm setuptools-0.6c11-py2.7.egg
# sudo easy_install-2.7 py2app
# python2.7 build.py

import sys
import os.path

SCRIPT_PATH = os.path.abspath("../src")
SCRIPT = "litter.py" # path not included
SCRIPT_BASE_NAME = SCRIPT[:-3] # without the extension
APP_NAME = "Litter"   # the app name with spaces and stuff
APP_NAME_U = "Litter" # an underscored version of the app name
OSX_IDENTIFIER = "ufl.acis.p2p.litter"
VERSION = "1.0.0" # must be X.X.X format (OS X requires it)
INCLUDES = []
PACKAGES = []
EXCLUDES = ["tkinter", "Tkinter", "ttk", "Tix"]
RESOURCES = [os.path.join("..", "src", "web")]
BUILD_DIR = "build"
WINDOWS_DISTRIBUTABLE = os.path.join(
    BUILD_DIR, "%s.%s.win32.zip" % (APP_NAME_U.lower(), VERSION.lower())
)
WINDOWS_DIRECTORY = os.path.join(
    BUILD_DIR, "%s_%s_win32" % (APP_NAME_U.lower(), VERSION.lower())
)
OSX_DISTRIBUTABLE = os.path.join(
    BUILD_DIR, "%s.%s.osx.dmg" % (APP_NAME_U.lower(), VERSION.lower())
)
OSX_DIRECTORY = os.path.join(
    BUILD_DIR, "%s_%s_osx" % (APP_NAME_U.lower(), VERSION.lower())
)

sys.path += [SCRIPT_PATH]

if sys.platform == "darwin": # Mac OS X
    print("Building for Mac OS X using py2app")
    sys.argv[1:1] = ["py2app"]
    
    from setuptools	import setup
    import shutil
    import subprocess
    import sys
    import tempfile
    
    plist = {
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleGetInfoString": "%s %s" % (APP_NAME, VERSION),
        "CFBundleExecutable": SCRIPT_BASE_NAME,
        "CFBundleIdentifier": OSX_IDENTIFIER
    }
    
    options = {
        "py2app": {
            "includes": INCLUDES, "packages": PACKAGES, "excludes": EXCLUDES,
            "iconfile": os.path.join("icons", "osx_icon", "icon.icns"),
            # "site_packages": True,
            "plist": plist,
            "bdist_base": tempfile.mkdtemp(), # intermediate build files go here 
            "dist_dir": OSX_DIRECTORY,
            "resources": RESOURCES
        }
    }
    # actually build the app with setuptools and py2app
    setup(name=APP_NAME, app=[os.path.join(SCRIPT_PATH, SCRIPT)],
          setup_requires=["py2app"], options=options) 
    
    print("Patching app file to open terminal window")
    executable_dir = os.path.join(OSX_DIRECTORY, "%s.app" % APP_NAME,
                                  "Contents", "MacOS")
    shutil.move(os.path.join(executable_dir, SCRIPT_BASE_NAME),
                os.path.join(executable_dir, "base_exec"))
    shutil.copy("osx_bin", os.path.join(executable_dir, SCRIPT_BASE_NAME))
    subprocess.check_call(["chmod", "+x",
                           os.path.join(executable_dir, SCRIPT_BASE_NAME)])
    
    print("Building DMG File")
    # TODO: Use https://github.com/andreyvit/yoursway-create-dmg to make the dmg
    # instead, and add some fancy graphics
    subprocess.check_call(["hdiutil", "create", "./" + OSX_DISTRIBUTABLE,
                           "-srcfolder", "./" + OSX_DIRECTORY, "-ov",
                           "-volname", APP_NAME])

elif sys.platform.startswith("win"): # Windows
    print("Building for Windows using cx_Freeze")
    sys.argv[1:1] = ["build"]
    
    from cx_Freeze import Executable, setup
    import zipfile

    options = {
        "build_exe": {
            "build_exe": WINDOWS_DIRECTORY,
            "includes": INCLUDES, "packages": PACKAGES, "excludes": EXCLUDES,
            "compressed": True,
            "icon": os.path.join("icons", "win_icon", "icon.ico"),
            "include_files": [(r, os.path.basename(r)) for r in RESOURCES]
        }
    }
    executable = Executable(
        os.path.join(SCRIPT_PATH, SCRIPT),
        compress=False, # we zip the whole thing up, so no need to recompress
                        # the bytecode
        targetName="%s.exe" % APP_NAME
    )
    setup(options=options, executables=[executable])
    print("Building Zip File")
    zf = zipfile.ZipFile(WINDOWS_DISTRIBUTABLE, "w")
    for dirpath, dirnames, filenames in os.walk(WINDOWS_DIRECTORY):
        for filename in filenames:
            fullpath = os.path.join(dirpath, filename)
            zf.write(fullpath, os.path.relpath(fullpath, BUILD_DIR))
    zf.close()
else:
    raise Exception("Unsupported Platform '%s'." % sys.platform)
