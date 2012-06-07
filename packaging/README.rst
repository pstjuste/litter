================
Litter Packaging
================

The build script is currently only for Mac OS X and Windows. To execute it, just
cd into the proper directory and run::
    
    python build.py

When run on Windows, an exe is built. When run on Mac OS X, a .app bundle and a
dmg (for distribution) are built.

Prior Windows Setup
-------------------

On Windows, you'll need to install Python 2.7 from python.org_ (we used 2.7.3),
and cx_Freeze_.

Prior OS X Setup
----------------

Install Python 2.7 (we used 2.7.3) from python.org_ (the built-in OS X verion,
and the version from macports will **not** work), and then install setuptools
for it::
    
    curl http://pypi.python.org/packages/2.7/s/setuptools/setuptools-0.6c11-py2.7.egg > setuptools-0.6c11-py2.7.egg
    sudo sh setuptools-0.6c11-py2.7.egg
    rm setuptools-0.6c11-py2.7.egg
    sudo easy_install-2.7 py2app

.. _python.org: http://python.org/
.. _cx_Freeze: http://cx-freeze.sourceforge.net/
