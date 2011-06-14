from PyQt4 import QtGui, QtCore
import threading
import collections
import time
import datetime
import cPickle as pickle
from libsonic import connection


def getArtistData(connection, artistId):
	artist = connection.getMusicDirectory(artistId)
	directories = artist.get('directory', {}).get('child', [])
	if not isinstance(directories, list):
		directories = [directories]
	albums = [itemDecodeHtml(dir) for dir in directories if dir.get('isDir', False)]
	if len(albums)!=len(directories):
		tracks = [itemDecodeHtml(item) for item in directories if not item.get('isDir', False)]
		artist = {
			'title':tracks[0].get('album', 'Unknown'),
			'id':artistId,
			'coverArt':tracks[0].get('coverArt', ''),
					}
		albums.append(artist)
	return albums, artist

def getAlbumData(connection, albumId):
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
	return songs, res


class ArtistModel(QtCore.QAbstractListModel):
	ArtistIdRole = QtCore.Qt.UserRole+1
	ArtistDataRole = QtCore.Qt.UserRole+2
	
	def __init__(self, parent):
		super(ArtistModel, self).__init__(parent)
		self.main = parent
		
		self._data = []
		self.populate()
	
	def flags(self, index):
		return QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsSelectable
	
	def mimeTypes(self):
		return ['text/plain', 'application/x-pickledata']
	
	def mimeData(self, indices):
		mimeData = QtCore.QMimeData()
		text = []
		data = {'type':'artist', 'data':[]}
		for index in indices:
			item = self.data(index, self.ArtistDataRole)
			
			text.append(item.get('name'))
			data['data'].append(item.get('id'))
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
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
		elif role == self.ArtistDataRole:
			return item

class AlbumModel(QtCore.QAbstractListModel):
	AlbumIdRole = QtCore.Qt.UserRole+1
	AlbumCoverArtIdRole = QtCore.Qt.UserRole+2
	AlbumPixmapRole = QtCore.Qt.UserRole+3
	AlbumDataRole = QtCore.Qt.UserRole+4
	
	artistAsyncLoaded = QtCore.pyqtSignal(str, list, dict)
	activeArtistChanged = QtCore.pyqtSignal(str, list)
	
	def __init__(self, parent):
		super(AlbumModel, self).__init__(parent)
		self.main = parent
		
		self._data = []
		self._albumsData = {}
		
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
		data = {'type':'album', 'data':[]}
		for index in indices:
			item = self.data(index, self.AlbumDataRole)
			text.append(item.get('title'))
			data['data'].append(item.get('id'))
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def loadArtist(self, artistId):
		if artistId == self.currentArtistId:
			return
		self.currentArtistId = artistId
		thread = threading.Thread(target=self.threadedArtistLoad, args=(artistId,))
		thread.start()
	
	def artistLoaded(self, artistId, folders, artistData):
		if artistId == self.currentArtistId:
			self._data = folders
			self._artistData = artistData
			self.reset()
			if artistData.has_key('title'):
				artistName = artistData.get('title')
			else:
				artistName = artistData.get('directory').get('name', 'Unknown')
			self.activeArtistChanged.emit(fromHtmlEncoding(artistName), folders)
	
	def threadedArtistLoad(self, artistId):
		folders, artist = getArtistData(self.main.connection, artistId)
		self.artistAsyncLoaded.emit(artistId, folders, artist)
	
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
	
	albumAsyncLoaded = QtCore.pyqtSignal(str, list, dict)
	activeAlbumChanged = QtCore.pyqtSignal(str, list)
	
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
		data = {}
		data['type'] = 'songs'
		
		songs = []
		for index in indices:
			if not index.column()==0:
				continue
			item = self.data(index, self.SongDataRole)
			text.append('%s - %s - %s'%(item.get('artist', 'Unknown'), item.get('album', 'Unknown'), item.get('title', 'Unknown')))
			songs.append(item)
		data['data'] = songs
		
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def loadAlbum(self, albumId):
		if albumId == self.currentAlbumId:
			return
		
		self._data = []
		self._albumData = {}
		self.currentAlbumId = albumId
		
		self.reset()
		thread = threading.Thread(target=self.threadedAlbumLoad, args=(albumId, ))
		thread.start()
	
	def albumLoaded(self, albumId, songs, albumData):
		if albumId == self.currentAlbumId:
			self._data = songs
			self._albumData = albumData
			self.reset()
			albumName = albumData.get('directory').get('name', 'Unknown')
			self.activeAlbumChanged.emit(fromHtmlEncoding(albumName), songs)
	
	def threadedAlbumLoad(self, albumId):
		songs, albumData = getAlbumData(self.main.connection, albumId)
		self.albumAsyncLoaded.emit(albumId, songs, albumData)
	
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
	asyncSongsLoaded = QtCore.pyqtSignal(int, list)
	
	def __init__(self, parent):
		super(PlayListModel, self).__init__(parent)
		self.main = parent
		self.coverArtCache = parent.coverArtCache
		self._columns = ['#', 'Title', 'Album', 'Artist', 'Duration', 'Bit-Rate', 'Type']
		self._data = []
		
		self.asyncSongsLoaded.connect(self.songsLoaded)
		self.nowPlayingIcon = QtGui.QIcon('images:video_play_64.png')
	
	def mimeTypes(self):
		return ['text/plain', 'application/x-pickledata']
	
	def mimeData(self, indices):
		mimeData = QtCore.QMimeData()
		text = []
		data = {'type':'song', 'data':[]}
		for index in indices:
			if not index.column()==0:
				continue
			item = self.data(index, self.SongDataRole)
			text.append('%s - %s - %s'%(item.get('artist', 'Unknown'), item.get('album', 'Unknown'), item.get('title', 'Unknown')))
			data['data'].append(item)
			
		mimeData.setText('\n'.join(text))
		mimeData.setData('application/x-pickledata', pickle.dumps(data))
		return mimeData
	
	def dropMimeData(self, data, action, row, column, index):
		data = pickle.loads(str(data.data('application/x-pickledata')))
		self.loadSongs(index.row(), data.get('data'), data.get('type'))
		return True
	
	def loadSongs(self, row, items, itemType='artist'):
		if itemType=='song':
			self.songsLoaded(row, items)
		else:
			thread = threading.Thread(target=self.threadedSongLoad, args=(row, items, itemType))
			thread.start()
	
	def songsLoaded(self, row, songs):
		self.insertData(row, songs)
	
	def threadedSongLoad(self, row, items, itemType='artist'):
		#If it's an artist, load it's albums, and then for each album load it's songs
		#If it's an album, loads it's songs
		songs = []
		albums = []
		if itemType == 'artist':
			for artistId in items:
				artistAlbums, artistData = getArtistData(self.main.connection, artistId)
				albums.extend([album.get('id') for album in artistAlbums])
		if itemType == 'album':
			albums = items
		
		for albumId in albums:
			albumSongs, albumData = getAlbumData(self.main.connection, albumId)
			songs.extend(albumSongs)
				
		self.asyncSongsLoaded.emit(row, songs)
	
	
	def insertData(self, row, songs):
		if row<0:
			row = self.rowCount(QtCore.QModelIndex())
		start = row
		end = start+(len(songs)-1)
		self.beginInsertRows(QtCore.QModelIndex(), start, end)
		self._data = self._data[:start]+songs+self._data[start:]
		self.endInsertRows()
		self.songsAdded.emit(len(songs))
	
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
	
	def currentSongChanged(self, index):
		for item in self._data:
			if item.has_key('nowPlaying'):
				del item['nowPlaying']
		self._data[index]['nowPlaying'] = True
		
	def nextSong(self, direction=1):
		currentIndex = [item.get('nowPlaying', False) for item in self._data].index(True)
		nextIndex = currentIndex+direction
		if nextIndex<0:
			nextIndex = 0
		elif nextIndex>self.rowCount():
			nextIndex = self.rowCount()
		
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
	
	def rowCount(self, parent=QtCore.QModelIndex()):
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
				return item.get('bitRate', 'variable')
			elif index.column()==6:
				return item.get('suffix', 'Uknown')
		elif role == QtCore.Qt.DecorationRole:
			if index.column()==0:
				return None #Album art
			if index.column()==1:
				if item.get('nowPlaying', False):
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
	