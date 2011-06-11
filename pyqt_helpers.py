from PyQt4 import QtCore, uic
from cStringIO import StringIO

import xml.etree.ElementTree as xml
import os

def loadUiType(uiFile, imagePath):
	'''Convert the image paths in the given .ui file to search paths using a resource prefix
		This is because it's a pain to setup relative resource paths in designer.
	Return a new class to inherit from'''
	def correctImagePaths(text, prefix):
		newText = text
		if text.lower().rsplit('.')[-1] in ['png', 'bmp', 'jpg', 'gif', 'tga']:
				newText = prefix+':'+os.path.basename(text)
		return newText
	
	ui = xml.parse(uiFile)
	#Iterate over the xml file, and replace paths that have image extensions at the end
	for item in ui.getiterator():
		if item.text:
			item.text = correctImagePaths(item.text, 'images')
		if item.tail:
			item.tail = correctImagePaths(item.tail, 'images')
		if item.tag:
			item.tag = correctImagePaths(item.tag, 'images')
	
	#Set the search paths prefix
	QtCore.QDir.setSearchPaths('images', [imagePath])
	
	#Create a temporary file-like string buffer, and pass that to loadUiType
	f = StringIO(xml.tostring(ui.getroot()))
	form_class, base_class = uic.loadUiType(f)
	
	class windowClass(form_class, base_class):
		'''Simple class wrapper for a ui file object'''
		def __init__(self, parent=None):
			super(base_class, self).__init__(parent)
			self.setupUi(self)
	
	return windowClass