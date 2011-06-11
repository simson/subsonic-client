from cx_Freeze import setup, Executable
import os
import sys

executable = Executable(
									script="main.py",
									icon='resources/images/icon.ico',
									targetName='SubSonic-Client.exe',
									base = "Win32GUI",
									appendScriptToLibrary=True, 
									includes=['libsonic', 'libvlc'],
									excludes=['PyQt4.Phonon', 'PyQt4.QtWebkit'],
									compress=True,
								)

include_files = []
root_dir = '.'

resource_dir = os.path.join(root_dir, 'resources')
include_files.append(os.path.join(root_dir, 'qt.conf'))
for root, dirs, files in os.walk(resource_dir):
	if not os.path.basename(root).startswith('_') and not '.svn' in root:
		for file in files:
			if not file.startswith('.') and not file.startswith('_'):
				include_files.append(os.path.join(root, file))

libvlc_dir = os.path.join(root_dir, 'libvlc')
for root, dirs, files in os.walk(libvlc_dir):
	if not os.path.basename(root).startswith('_') and not '.svn' in root:
		for file in files:
			if not file.startswith('.') and not file.startswith('_'):
				include_files.append(os.path.join(root, file))



excludes = ['_gtkagg', '_tkagg', 'bsddb', 'curses', 'email', 'pywin.debugger', 'pywin.debugger.dbgcon', 'pywin.dialogs', 'tcl', 'Tkconstants', 'Tkinter']
setup(
        name = "Subsonic-Client",
        version = "0.1",
        description = 'Subsonic desktop client.\nbuilt with:\n\tPython 2.7\n\tPyQt 4.8.4\n\tLib-sonic\n\tlibvlc & vlc.py c-types',
		author='Nathan Horne',
		options = {'build_exe':{'include_files':include_files, 'excludes': excludes,}},
        executables = [executable])