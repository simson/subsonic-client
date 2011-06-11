from PyQt4 import QtGui, QtCore
import threading
import collections
import time
import datetime
import cPickle as pickle
from libsonic import connection



def getSongsForAlbum(connection, albumId):
	res = connection.getMusicDirectory(albumId)
	songs = res.get('directory', {}).get('child', [])
	if not isinstance(songs, list):
		songs = [songs]
	songs = [itemDecodeHtml(song) for song in songs if not song.get('isFolder', False)]
	
	#hide duplicates by name
	uniqueSongs = []
	for song in songs:
		if unicode(song.get('title', '')).lower() not in [unicode(track.get('title', '')).lower() for track in uniqueSongs]:
			uniqueSongs.append(itemDecodeHtml(song))
	songs = uniqueSongs[:]
	return songs


class ArtistModel(QtCore.QAbstractListModel):
	ArtistIdRole = QtCore.Qt.UserRole+1
	def __init__(self, parent):
		super(ArtistModel, self).__init__(parent)
		self.main = parent
		
		self._data = []
		self.populate()
	
	def flags(self, index):
		return QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsSelectable
	
	def populate(self):
		res = self.main.connection.getIndexes()
		indexes = res.get('indexes').get('index')
		self._data = []
		for index in indexes:
			self._data.extend(index['artist'])
		self._data = [itemDecodeHtml(artist) for artist in self._data]
	
	def rowCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._data)
	
	def columnCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return 1
	
	def data(self, index, role=QtCore.Qt.DisplayRole):
		item = self._data[index.row()]
		if role == QtCore.Qt.DisplayRole:
			if index.column()==0:
				return item['name']
		elif role == self.ArtistIdRole:
			return item['id']

class AlbumModel(QtCore.QAbstractListModel):
	AlbumIdRole = QtCore.Qt.UserRole+1
	AlbumCoverArtIdRole = QtCore.Qt.UserRole+2
	AlbumPixmapRole = QtCore.Qt.UserRole+3
	AlbumDataRole = QtCore.Qt.UserRole+4
	
	artistAsyncLoaded = QtCore.pyqtSignal(str, list)
	def __init__(self, parent):
		super(AlbumModel, self).__init__(parent)
		self.main = parent
		self._artists = {}
		self._data = []
		self.currentArtistId = None
		self.coverArtCache = parent.coverArtCache
		self.coverArtCache.coverArtLoaded.connect(self.coverArtLoaded)
		self.artistAsyncLoaded.connect(self.artistLoaded)
		
		self.defaultCover = QtGui.QPixmap('images:defaultAlbumArt.png')
	
	def flags(self, index):
		return QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsSelectable
	
	def mimeTypes(self):
		return ['text/plain', 'application/x-pickledata']
	
	def mimeData(self, indices):
		mimeData = QtCore.QMimeData()
		text = []
		data = []
		for index in indices:
			item = self.data(index, self.AlbumDataRole)
			#This is slow and lags the cursor when dragging an album, should send the id instead and have qt handle the album load in a thread on drop.
			data.extend(getSongsForAlbum(self.main.connection, item.get('id')))
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def loadArtist(self, artistId):
		if artistId == self.currentArtistId:
			return
		self.currentArtistId = artistId
		
		thread = threading.Thread(target=self.threadedArtistLoad, args=(artistId,))
		thread.start()
	
	def artistLoaded(self, artistId, folders):
		if artistId == self.currentArtistId:
			self._data = folders
			self.reset()
	
	def threadedArtistLoad(self, artistId):
		artist = self.main.connection.getMusicDirectory(artistId)
		directories = artist.get('directory', {}).get('child', [])
		if not isinstance(directories, list):
			directories = [directories]
		folders = [itemDecodeHtml(dir) for dir in directories if dir.get('isDir', False)]
		if len(folders)!=len(directories):
			tracks = [itemDecodeHtml(item) for item in directories if not item.get('isDir', False)]
			artist = {
				'title':tracks[0].get('album', 'Unknown'),
				'id':artistId,
				'coverArt':tracks[0].get('coverArt', ''),
						}
			folders.append(artist)
		self.artistAsyncLoaded.emit(artistId, folders)
	
	def rowCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._data)
	
	def columnCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return 1
	
	def data(self, index, role=QtCore.Qt.DisplayRole):
		item = self._data[index.row()]
		if role == QtCore.Qt.DisplayRole:
			if index.column()==0:
				return item['title']
		elif role == QtCore.Qt.DecorationRole or role == self.AlbumPixmapRole:
			art = self.coverArtCache.get(item.get('coverArt', None))
			return art.scaled(200, 200)
		elif role == QtCore.Qt.ToolTipRole:
			return item['title']
		elif role == self.AlbumIdRole:
			return item['id']
		elif role == self.AlbumCoverArtIdRole:
			return item.get('coverArt', None)
		elif role == self.AlbumDataRole:
			return item
	
	def coverArtLoaded(self, coverArtId):
		try:
			index = [item.get('coverArt', '') for item in self._data].index(coverArtId)
			topLeft = self.index(index, 0, QtCore.QModelIndex())
			self.dataChanged.emit(topLeft, topLeft)
			self.layoutChanged.emit()
		except: pass

class TrackModel(QtCore.QAbstractTableModel):
	SongIdRole = QtCore.Qt.UserRole+1
	AlbumCoverArtIdRole = QtCore.Qt.UserRole+2
	AlbumPixmapRole = QtCore.Qt.UserRole+3
	SongDataRole = QtCore.Qt.UserRole+4
	albumAsyncLoaded = QtCore.pyqtSignal(str, list)
	def __init__(self, parent):
		super(TrackModel, self).__init__(parent)
		self.main = parent
		self.coverArtCache = parent.coverArtCache
		self.albumAsyncLoaded.connect(self.albumLoaded)
		self.currentAlbumId = None
		self._columns = ['#', 'Title', 'Album', 'Artist', 'Duration', 'Type']
		self._data = []
	
	def flags(self, index):
		return QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsSelectable
	
	def mimeTypes(self):
		return ['text/plain', 'application/x-pickledata']
	
	def mimeData(self, indices):
		mimeData = QtCore.QMimeData()
		text = []
		data = []
		for index in indices:
			if not index.column()==0:
				continue
			item = self.data(index, self.SongDataRole)
			text.append('%s - %s - %s'%(item.get('artist', 'Unknown'), item.get('album', 'Unknown'), item.get('title', 'Unknown')))
			data.append(item)
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def loadAlbum(self, albumId):
		if albumId == self.currentAlbumId:
			return
		self._data = []
		self.reset()
		self.currentAlbumId = albumId
		thread = threading.Thread(target=self.threadedAlbumLoad, args=(albumId, ))
		thread.start()
			
	def threadedAlbumLoad(self, albumId):
		songs = getSongsForAlbum(self.main.connection, albumId)
		self.albumAsyncLoaded.emit(albumId, songs)
	
	def albumLoaded(self, albumId, songs):
		if albumId == self.currentAlbumId:
			self._data = songs
			self.reset()
	
	def rowCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._data)
	
	def columnCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._columns)
	
	def headerData(self, section, orientation, role):
		if role == QtCore.Qt.DisplayRole:
			if orientation == QtCore.Qt.Horizontal:
				return self._columns[section]
	
	def data(self, index, role=QtCore.Qt.DisplayRole):
		item = self._data[index.row()]
		if role == QtCore.Qt.DisplayRole:
			if index.column()==0:
				return item.get('track', None)
			if index.column()==1:
				return item.get('title', 'Unknown')
			if index.column()==2:
				return item.get('album', 'Unkown')
			elif index.column()==3:
				return item.get('artist', 'Uknown')
			elif index.column()==4:
				seconds = item.get('duration', -1)
				timedelta = datetime.timedelta(seconds=seconds)
				return str(timedelta).lstrip('0:')
			elif index.column()==5:
				return item.get('suffix', 'Uknown')
		elif role == QtCore.Qt.DecorationRole:
			if index.column()==0:
				return None #Album art at this scale is iffy
		elif role == self.SongIdRole:
			return item.get('id', None)
		elif role == self.AlbumPixmapRole:
			return self.coverArtCache.get(item.get('coverArt', None))
		elif role == self.SongDataRole:
			return item
		elif role == self.AlbumCoverArtIdRole:
			return item.get('coverArt', None)
			
class PlayListModel(QtCore.QAbstractTableModel):
	SongIdRole = QtCore.Qt.UserRole+1
	AlbumCoverArtIdRole = QtCore.Qt.UserRole+2
	AlbumPixmapRole = QtCore.Qt.UserRole+3
	SongDataRole = QtCore.Qt.UserRole+4
	
	songsAdded = QtCore.pyqtSignal(int)
	def __init__(self, parent):
		super(PlayListModel, self).__init__(parent)
		self.main = parent
		self.coverArtCache = parent.coverArtCache
		self._columns = ['#', 'Title', 'Album', 'Artist', 'Duration', 'Type']
		self._data = []
		self.nowPlayingIcon = QtGui.QIcon('images:video_play_64.png')
		self.currentTrack = 0
	
	def mimeTypes(self):
		return ['text/plain', 'application/x-pickledata']
	
	def mimeData(self, indices):
		mimeData = QtCore.QMimeData()
		text = []
		data = []
		for index in indices:
			if not index.column()==0:
				continue
			item = self.data(index, self.SongDataRole)
			text.append('%s - %s - %s'%(item.get('artist', 'Unknown'), item.get('album', 'Unknown'), item.get('title', 'Unknown')))
			data.append(item)
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def dropMimeData(self, data, action, row, column, index):
		songs = pickle.loads(str(data.data('application/x-pickledata')))
		self.insertData(index.row(), songs)
		return False
	
	def insertData(self, row, songs):
		if row<0:
			row = self.rowCount(QtCore.QModelIndex())
		start = row
		end = start+(len(songs)-1)
		self.beginInsertRows(QtCore.QModelIndex(), start, end)
		self._data = self._data[:start]+songs+self._data[start:]
		self.endInsertRows()
	
	def removeRows(self, start, count, parent):
		end = start+count
		self.beginRemoveRows(parent, start, end-1)
		itemsToDelete = self._data[start:end]
		del self._data[start:end]
		self.endRemoveRows()
		return True
	
	def supportedDropActions(self):
		return QtCore.Qt.CopyAction|QtCore.Qt.MoveAction
	
	def flags(self, index):
		defaultFlags = super(PlayListModel, self).flags(index)
		if index.isValid():
			return QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|defaultFlags
		else:
			return QtCore.Qt.ItemIsDropEnabled|defaultFlags
		
	def nextSong(self, direction=1):
		nextIndex = self.currentTrack+direction
		if self.hasIndex(nextIndex, 0, QtCore.QModelIndex()):
			next = self.data(self.index(nextIndex, 0, QtCore.QModelIndex()), self.SongDataRole)
			return next, nextIndex
		return None, 0
	
	def loadPlaylist(self, playlistId):
		pass
	
	def addSongs(self, songs):
		if not isinstance(songs, list):
			songs = [songs]
		
		if songs:
			start = len(self._data)
			end = start+len(songs)-1
			self.beginInsertRows(QtCore.QModelIndex(), start, end)
			self._data.extend([itemDecodeHtml(song) for song in songs])
			self.endInsertRows()
			self.songsAdded.emit(len(songs))
			return start
		return None
	
	def removeSongs(self, rows):
		newData = []
		for i, item in enumerate(self._data):
			if i not in rows:
				newData.append(item)
		self.clearPlaylist()
		self.addSongs(newData)
	
	def clearPlaylist(self):
		self.currentSong = 0
		self._data = []
		self.reset()
	
	def rowCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._data)
	
	def columnCount(self, parent):
		if parent.isValid():
			return 0
		else:
			return len(self._columns)
	
	def headerData(self, section, orientation, role):
		if role == QtCore.Qt.DisplayRole:
			if orientation == QtCore.Qt.Horizontal:
				return self._columns[section]
	
	def data(self, index, role=QtCore.Qt.DisplayRole):
		item = self._data[index.row()]
		if role == QtCore.Qt.DisplayRole:
			if index.column()==0:
				return item.get('track', None)
			if index.column()==1:
				return item.get('title', 'Unknown')
			if index.column()==2:
				return item.get('album', 'Unkown')
			elif index.column()==3:
				return item.get('artist', 'Uknown')
			elif index.column()==4:
				seconds = item.get('duration', -1)
				timedelta = datetime.timedelta(seconds=seconds)
				return str(timedelta).lstrip('0:')
			elif index.column()==5:
				return item.get('suffix', 'Uknown')
		elif role == QtCore.Qt.DecorationRole:
			if index.column()==0:
				return None #Album art
			if index.column()==1:
				if index.row() == self.currentTrack:
					return self.nowPlayingIcon
		elif role == self.SongIdRole:
			return item.get('id', None)
		elif role == self.AlbumPixmapRole:
			return self.coverArtCache.get(item.get('coverArt', None))
		elif role == self.SongDataRole:
			return item
		elif role == self.AlbumCoverArtIdRole:
			return item.get('coverArt', None)
		elif role == QtCore.Qt.SizeHintRole:
			return QtCore.QSize(200, 220)
	
	def niceReset(self):
		'''Reset the data, but don't reset the selection'''
		topLeft = self.index(0, 0, QtCore.QModelIndex())
		bottomRight = self.index(self.rowCount(QtCore.QModelIndex()), self.columnCount(QtCore.QModelIndex()), QtCore.QModelIndex())
		self.dataChanged.emit(topLeft, bottomRight)

class CoverArtCache(QtCore.QObject):
	coverArtLoaded = QtCore.pyqtSignal(str)
	def __init__(self, parent):
		super(CoverArtCache, self).__init__(parent)
		self.loader = ImageLoaderQueue(parent)
		self.defaultPixmap = QtGui.QPixmap('images:defaultAlbumArt.png')
		self.loader.imageLoaded.connect(self.imageLoaded)
		self._cache = {}
	
	def get(self, coverArtId, size=None):
		if not coverArtId:
			return self.defaultPixmap
		
		cacheKey = coverArtId
		if size:
			cacheKey = '%s:%s'%(coverArtId, size)
		if self._cache.get(cacheKey, None):
			return self._cache.get(cacheKey)
		else:
			self.loader.add(coverArtId, cacheKey)
			return self.defaultPixmap
	
	def imageLoaded(self, image, key, coverArtId):
		'''We got an image back from the loader thread'''
		pixmap = QtGui.QPixmap().fromImage(image)
		self._cache[key] = pixmap
		self.coverArtLoaded.emit(coverArtId)

class ImageLoaderQueue(QtCore.QObject, object):
	'''This is the queue that manages images to load for the UI
		Use add to add new images to load, multiple add calls for the same image will be ignored
		join will stop all the child threads and block until they exit
		stop will tell each child thread to stop when it finishes it's current task, does not block
	The queue is Last In First Out (LIFO) so newest images to load will be processed first
	The queue is limited to 200 items, any items over 200 added to the queue will bump off older items
		-this is so that when rapidly dragging in the ui, only the # most recent items (And most likely to be visible) will be loaded
		-otherwise the newer items would be removed from the pixmap cache when the non-visible items were loaded last (possibly causing excessive flickering)
	'''
	imageLoaded = QtCore.pyqtSignal('QImage', str, str)
	def __init__(self, parent, threadCount=8):
		super(ImageLoaderQueue, self).__init__(parent)
		self.main = parent
		self.queue = collections.deque(maxlen=200)
		self.threads = []
		for i in range(threadCount):
			self.threads.append(Worker(self))
			self.threads[-1].start()
	
	def stop(self):
		self.queue.clear()
		for thread in self.threads:
			thread.running = False
		
	def join(self):
		self.stop()
		for thread in self.threads:
			thread.join()
	
	def add(self, id, cacheKey):
		if not bool((id, cacheKey) in list(self.queue)):
			self.queue.append((id, cacheKey))

class Worker(threading.Thread):
	'''Pops an item off the image queue, loads and scales the image'''
	def __init__(self, parent):
		threading.Thread.__init__(self)
		self.daemon = True
		self.running = True
		self.work = parent.queue
		self.signal = parent.imageLoaded
		self.main = parent.main
	
	def run(self):
		while self.running:
			try:
				coverArtId, key= self.work.pop()
				size = None
				if len(key)>len(coverArtId):
					size = int(key[len(coverArtId)+1:])
				
				image = QtGui.QImage()
				artFile = self.main.connection.getCoverArt(coverArtId, size)
				imageData = artFile.read()
				image.loadFromData(imageData)
				self.signal.emit(image, key, coverArtId)
			except IndexError:
				time.sleep(.0025) #Sleep

def itemDecodeHtml(item):
	for key, value in item.items():
		if isinstance(value, basestring):
			item[key] = fromHtmlEncoding(value)
	return item

def fromHtmlEncoding(text):
	doc = QtGui.QTextDocument()
	doc.setHtml(text)
	return doc.toPlainText()
	