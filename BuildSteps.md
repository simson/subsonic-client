# Build guide - Windows #
  1. Install Python 2.6/7 (32 bit)
  1. Install PyQt4 (>=4.8.X recomended)
  1. Install cx\_freeze (If you want to use the included build\_spec.py)
  1. Copy the hooks.py file from .\extra to your cx\_freeze install in site-packages. Overwrite the existing one (Make a backup if need be). The custom one I use excludes some of the specific packages that are added by cx\_freeze for PyQt4 in the interest of build size.
  1. Run .\extra\build.bat to compile

> That should be it, if there are any ommisions, please let me know.