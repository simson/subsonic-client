#!/usr/bin/env python
# This is only needed for Python v2 but is harmless for Python v3.
import sip
import os
import sys
import site

sip.setapi('QVariant', 2)
sip.setapi('QString', 2)
#Add the path to libvlc, and libsonic
#Check to see if this is a "Frozen" binary version
if hasattr(sys, 'frozen'):
	root_dir = os.path.dirname(sys.executable)
else:
	root_dir = sys.path[0]
sys.path.append(os.path.join(root_dir, 'resources'))
site.addsitedir(os.path.join(root_dir, 'resources'))

os.environ['PATH'] = ';'.join(os.environ['PATH'].split(';')+[os.path.join(root_dir, 'libvlc')])

import cPickle as pickle
import socket
import threading
import time
from functools import partial
from PyQt4 import QtGui, QtCore
from libsonic import connection
try:
	import vlc
except:
	raise Exception, 'Could not load VLC, please ensure either VLC(VideoLan) or libvlc is installed on your system!'
import pyqt_helpers
import models

clientPlaylist = os.path.join(root_dir, 'playlist.dat')
uiFile = os.path.join(root_dir, 'resources', 'mainWindow.ui')
uiFile_login = os.path.join(root_dir, 'resources', 'loginWindow.ui')
imagePath = os.path.join(root_dir, 'resources', 'images')

#Load the designer ui file on the fly
windowClass = pyqt_helpers.loadUiType(uiFile, imagePath)
windowClass_login = pyqt_helpers.loadUiType(uiFile_login, imagePath)

class LoginWindow(windowClass_login):
	def __init__(self, server, port, path, user, passwd):
		super(LoginWindow, self).__init__()
		self.result = None
		self.serverField.setText(server)
		self.port.setValue(port)
		self.serverPathField.setText(path)
		self.userField.setText(user)
		self.passField.setText(passwd)
	
	def accept(self):
		self.result = (self.serverField.text(), self.port.value(), self.serverPathField.text(), self.userField.text(), self.passField.text())
		
		try:
			testconnection = connection.Connection(self.result[0], self.result[3], self.result[4], self.result[1], self.result[2], 'subsonic-desktop')
			if not testconnection.ping():
				raise Exception, 'Could not connect to server!'
		except:
			if not self.result[0].startswith('http://') and not self.result[0].startswith('https://'):
				self.serverField.setText('http://'+self.result[0])
				self.accept()
				return
			raise
		
		super(LoginWindow, self).accept()

class MainWindow(windowClass):
	songEnded = QtCore.pyqtSignal()
	currentSongChanged = QtCore.pyqtSignal(int)
	
	def __init__(self, server, port, path, user, passwd):
		super(MainWindow, self).__init__()
		self.settings = QtCore.QSettings('subsonic', 'subsonic-desktop')
		
		self.restoreWindowState()
		
		if False:
			#Use un-styled display
			self.setStyleSheet('')
		
		self.instance = vlc.Instance()
		self.player = self.instance.media_player_new()
		self.log = self.instance.log_open()
		
		#socket.setdefaulttimeout(5)
		
		self.connection = connection.Connection(server, user, passwd, port, path, 'subsonic-desktop')
		self.coverArtCache = models.CoverArtCache(self)
		self.coverArtCache.coverArtLoaded.connect(self.coverArtLoaded)
		self.nowPlaying = {}
		
		self.autoPlay = True
		self.doubleClickAction = 'add'
		
		#Media player events
		self.eventManager = self.player.event_manager()
		self.eventManager.event_attach(vlc.EventType.MediaPlayerEndReached, self.songEndReached)
		self.songEnded.connect(self.playNextSong)
		
		self.verticalSplitter.setStretchFactor(0, 0)
		self.verticalSplitter.setStretchFactor(1, 100)
		
		self.playlistControlSplitter.setStretchFactor(0, 100)
		self.playlistControlSplitter.setStretchFactor(1, 0)
		
		#Create models
		self.artistModel = models.ArtistModel(self)
		self.albumModel = models.AlbumModel(self)
		self.trackModel = models.TrackModel(self)
		self.playlistModel = models.PlayListModel(self)
		
		self.artistListView.setModel(self.artistModel)
		self.albumListView.setModel(self.albumModel)
		self.trackTableView.setModel(self.trackModel)
		self.playlistTableView.setModel(self.playlistModel)
		
		self.albumListView.setDragEnabled(True)
		self.trackTableView.setDragEnabled(True)
		self.playlistTableView.setDragEnabled(True)
		self.playlistTableView.viewport().setAcceptDrops(True)
		self.playlistTableView.setDropIndicatorShown(True)
		
		self.albumModel.activeArtistChanged.connect(self.activeArtistChanged)
		self.trackModel.activeAlbumChanged.connect(self.activeAlbumChanged)
		#self.playlistTableView.activeSongChanged.connect(self.activeSongChanged)
		#self.playlistTableView.activeSongChanged.connect(self.activeSongChanged)
		
		self.playlistModel.playlistCleared.connect(self.stop)
		self.playlistModel.songsAdded.connect(self.playlistSongsAdded)
		self.currentSongChanged.connect(self.playlistModel.currentSongChanged)
		
		self.searchField = QtGui.QLineEdit(self)
		self.searchField.editingFinished.connect(self.updateSearchPage)
		self.searchField.returnPressed.connect(self.showSearchResultsPage)
		self.searchField.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Fixed)
		self.toolBar.insertWidget(self.actionSettings, self.searchField)
		#self.toolBar.insertSeparator(self.actionSettings)
		
		try: #Qt > 4.7 has a placeholderText attribute, otherwise do nothing.
			self.searchField.setPlaceholderText('Search...')
		except: pass
		
		self.createTrayIcon()
		
		self.crumbArtistBtn.clicked.connect(partial(self.pageViews.setCurrentWidget, self.artistPage))
		
		self.artistListView.selectionModel().selectionChanged.connect(self.artistSelected)
		self.artistListView.doubleClicked.connect(self.artistDoubleClicked)
		self.artistListView.activated.connect(self.artistActivated)
		
		self.albumListView.selectionModel().selectionChanged.connect(self.albumSelected)
		self.albumListView.doubleClicked.connect(self.albumDoubleClicked)
		self.albumListView.activated.connect(self.albumActivated)
		
		self.trackTableView.clicked.connect(partial(self.trackSelected, self.trackModel))
		self.trackTableView.doubleClicked.connect(self.trackDoubleClicked)
		
		self.playlistTableView.clicked.connect(partial(self.trackSelected, self.playlistModel))
		self.playlistTableView.doubleClicked.connect(self.playlistDoubleClicked)
		
		self.searchResultTreeWidget.itemDoubleClicked.connect(self.searchItemDoubleClicked)
		
		self.volumeSlider.setValue(self.player.audio_get_volume())
		self.volumeSlider.sliderMoved.connect(self.setVolume)
		
		self.playBtn.clicked.connect(self.play)
		self.pauseBtn.clicked.connect(self.pause)
		self.stopBtn.clicked.connect(self.stop)
		self.muteBtn.clicked.connect(self.setMute)
		self.trackPrevBtn.clicked.connect(self.playPrevSong)
		self.trackNextBtn.clicked.connect(self.playNextSong)
		self.playlistClearBtn.clicked.connect(self.clearPlaylist)
		self.playlistShuffleBtn.clicked.connect(self.playlistModel.shuffle)
		
		self.seekSlider.sliderMoved.connect(self.seek)
		self.seekSlider.sliderPressed.connect(self.startSeek)
		self.seekSlider.sliderReleased.connect(self.stopSeek)
		
		self.actionSettings.triggered.connect(partial(startup, True))
		self.actionHome.triggered.connect(self.showHomePage)
		self.actionNowPlaying.triggered.connect(self.showNowPlayingPage)
		self.actionSearch.triggered.connect(self.showSearchResultsPage)
		self.actionPlaylists.triggered.connect(self.showPlaylistsPage)
		self.actionInfo.triggered.connect(self.showInfoPage)
		
		self.showHomePage()
		self.nowPlaying = {}
		self.nowSelected = {}
		self.lastSearch = ''
		
		try:
			f = open(clientPlaylist, 'rb')
			songs = pickle.load(f)
			f.close()
			self.playlistModel.addSongs(songs)
		except: pass #Didnt exist, or error loading playlists. Not a big deal..
		
		self.playlistModel.loadRandomSongs()
		
		self.timer = QtCore.QTimer(self)
		self.timer.setInterval(100)
		self.timer.timeout.connect(self.tickEvent)
		self.timer.start() #Start ticking!
		
		self.playlistTableView.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
		self.playlistTableView.customContextMenuRequested.connect(self.showContextMenu)
	
	def showContextMenu(self, point):
		menu = QtGui.QMenu(self.playlistTableView)
		menu.addAction('test!', self.doTest)
		menu.exec_(QtGui.QCursor.pos()-QtCore.QPoint(15, 10), defaultAction)
		
	def doTest(self):
		print 'YAY!'
	
	def saveWindowState(self):
		self.settings.setValue('windowGeometry', self.saveGeometry())
		self.settings.setValue('windowState', self.saveState())
		self.settings.setValue('windowState_vSplit', self.verticalSplitter.saveState())
		self.settings.setValue('windowState_hSplit', self.horizontalSplitter.saveState())
	
	def restoreWindowState(self):
		try:
			self.restoreGeometry(self.settings.value('windowGeometry'))
		except: pass
		try:
			self.restoreState(self.settings.value('windowState'))
		except: pass
		try:
			self.verticalSplitter.restoreState(self.settings.value('windowState_vSplit'))
		except: pass
		try:
			self.horizontalSplitter.restoreState(self.settings.value('windowState_hSplit'))
		except: pass
	
	def createTrayIcon(self):
		self.tray = QtGui.QSystemTrayIcon()
		self.tray.setIcon(QtGui.QIcon('images:Subsonic.png'))
		self.tray.activated.connect(self.trayActivated)
		
		self.trayMenu = QtGui.QMenu()
		self.trayMenu.addAction(QtGui.QIcon('images:video_play_64.png'), 'Play', self.play)
		self.trayMenu.addAction(QtGui.QIcon('images:video_pause_64.png'), 'Pause', self.pause)
		self.trayMenu.addAction(QtGui.QIcon('images:video_stop_64.png'), 'Stop', self.stop)
		self.trayMenu.addSeparator()
		
		self.trayMenu.addAction(QtGui.QIcon('images:video_next_64.png'), 'Next song', self.playNextSong)
		self.trayMenu.addAction(QtGui.QIcon('images:video_previous_64.png'), 'Previous song', self.playPrevSong)
		self.trayMenu.addSeparator()
		
		self.trayMenu.addAction(QtGui.QIcon('images:delete_64.png'), 'Quit', self.quit)
		
		self.tray.show()
	
	def trayActivated(self, reason):
		if reason == QtGui.QSystemTrayIcon.Trigger:
			#Left click
			if sys.platform.startswith('linux'):
				self.showTrayMenu()
			else:
				self.restore()
		if reason == QtGui.QSystemTrayIcon.Context:
			#Context menu
			if sys.platform.startswith('win'):
				self.showTrayMenu()
			else:
				self.restore()
			
	def showTrayMenu(self):
		point = self.tray.geometry().topLeft()
		self.trayMenu.move(point)
		self.trayMenu.exec_(point)
	
	def restore(self):
		self.showNormal()
		self.activateWindow()
		self.raise_()
		self.setVisible(True)
	
	def tickEvent(self):
		state = self.player.get_state()
		#print 'Messages:', self.log.count()
		#Update the display state
		if state == vlc.State.Playing:
			self.statusbar.showMessage('Playing...')
		elif state == vlc.State.Stopped:
			self.statusbar.showMessage('Stopped...')
		elif state == vlc.State.Paused:
			self.statusbar.showMessage('Paused...')
		else:
			self.statusbar.showMessage(str(state).split('.')[-1])
		
		if self.player.is_seekable():
			self.seekSlider.setEnabled(True)
		else:
			self.seekSlider.setEnabled(False)
		
		if self.player.is_playing() and not self.seekSlider.isSliderDown():
			#Calculate a percentage value and set it
			self.currentTime = self.player.get_time()
			totalTime = self.nowPlaying['duration']*1000.0
			if totalTime:
				percent = self.currentTime/totalTime
				self.seekSlider.setValue(percent*10000)
			else:
				self.songEnded.emit()
	
	def activeArtistChanged(self, name, albums):
		print 'New active artist:', name
		self.crumbArtistBtn.setText('Back to: %s'%name)
	
	def activeAlbumChanged(self, name, songs):
		print 'New active album:', name
		pass
	
	#def activeSongChanged(self, name, song):
	#	print 'New active song:', song
	
	def songEndReached(self, event):
		self.songEnded.emit()
	
	def playlistSongsAdded(self, count):
		if not self.nowPlaying:
			rows = self.playlistModel.rowCount(QtCore.QModelIndex())
			row = rows-count
			index = self.playlistModel.index(row, 0, QtCore.QModelIndex())
			song = self.playlistModel.data(index, self.playlistModel.SongDataRole)
			self.setNowPlaying(song, row)
			if self.autoPlay:
				self.play()
	
	def playPrevSong(self):
		nextSong, nextIndex = self.playlistModel.nextSong(-1)
		if nextSong:
			self.setNowPlaying(nextSong, nextIndex)
			self.play()
	
	def playNextSong(self):
		nextSong, nextIndex = self.playlistModel.nextSong()
		if nextSong:
			self.setNowPlaying(nextSong, nextIndex)
			self.play()
	
	def setMute(self, mute=True):
		self.player.audio_set_mute(mute)
	
	def setVolume(self, vol):
		self.player.audio_set_volume(vol)
	
	def stop(self):
		self.player.stop()
		self.seekSlider.setValue(0)
	
	def play(self):
		if not self.player.is_playing():
			if self.player.get_state() == vlc.State.Ended:
				self.player.stop() #Restart it
			self.player.play()
	
	def pause(self):
		if self.player.can_pause():
			self.player.pause()
		else:
			self.stop()
	
	def startSeek(self):
		'''Start a seek drag, mute the tack while seeking to minimize clicks/pops'''
		self.newSeekPosition = None
		self.dragStartMute = self.player.audio_get_mute()
		self.player.audio_set_mute(True)
	
	def stopSeek(self):
		'''Dragging is done, set the new seek position and unmute'''
		if self.newSeekPosition:
			percent = (self.newSeekPosition/10000.0)
			newTime = int((self.nowPlaying['duration']*percent)*1000) #Percentage of duration in ms
			self.player.set_time(newTime)
		self.player.audio_set_mute(self.dragStartMute)
	
	def seek(self, value):
		'''Update the target seek position'''
		self.newSeekPosition = value
	
	def clearPlaylist(self):
		self.nowPlaying = None
		self.playlistModel.clearPlaylist()
		self.stop()
	
	def showHomePage(self):
		self.pageViews.setCurrentWidget(self.homePage)
	
	def showSearchResultsPage(self):
		self.updateSearchPage()
		self.pageViews.setCurrentWidget(self.searchResultsPage)
	
	def showPlaylistsPage(self):
		self.pageViews.setCurrentWidget(self.playlistPage)
	
	def showNowPlayingPage(self):
		self.pageViews.setCurrentWidget(self.nowPlayingPage)
	
	def showInfoPage(self):
		self.pageViews.setCurrentWidget(self.infoPage)
	
	def showArtistPage(self):
		self.pageViews.setCurrentWidget(self.artistPage)
	
	def showAlbumPage(self):
		self.pageViews.setCurrentWidget(self.albumPage)
	
	
	def artistSelected(self, selection, deselection):
		self.showArtistPage()
		index = self.artistListView.selectedIndexes()
		if not index:
			return
		index = index[0]
		artistId = self.artistModel.data(index, self.artistModel.ArtistIdRole)
		
		self.setActiveArtist(artistId)
	
	def artistDoubleClicked(self):
		self.showArtistPage()
		self.albumListView.setFocus()
	
	def artistActivated(self, index):
		self.albumListView.setFocus()
	
	def albumSelected(self):
		index = self.albumListView.currentIndex()
		album = self.albumModel.data(index, self.albumModel.AlbumDataRole)
		self.setActiveAlbum(album.get('id'))
	
	def albumDoubleClicked(self):
		self.showAlbumPage()
		self.trackTableView.setFocus()
	
	def albumActivated(self, index):
		self.albumListView.setFocus()
		self.albumSelected()
		self.albumDoubleClicked()
	
	
	def trackSelected(self, model, index):
		self.nowSelected = model.data(index, model.SongDataRole)
		self.updateCoverArt()
	
	def trackDoubleClicked(self, index):
		song = self.trackModel.data(index, self.trackModel.SongDataRole)
		if self.doubleClickAction == 'add':
			trackIndex = self.playlistModel.addSongs(song)
	
	def playlistDoubleClicked(self, index):
		song = self.playlistModel.data(index, self.playlistModel.SongDataRole)
		self.setNowPlaying(song, index.row())
		self.play()
	
	def coverArtLoaded(self, albumId):
		pixmap = self.coverArtCache.get(albumId)
	
	def updateCoverArt(self):
		pass
	
	def updateSearchPage(self):
		searchStr = self.searchField.text()
		if searchStr == self.lastSearch:
			return
		
		#Naive slow way, should do this in a thread, and do it in page chunks while the user can interact.
		self.lastSearch = searchStr
		res = self.connection.search2(searchStr, artistCount=100, albumCount=100, songCount=1000)
		
		self.searchResultTreeWidget.clear()
		matches = res.get('searchResult2', {})
		
		if not matches:
			return
		
		artists =  matches.get('artist', [])
		albums =  matches.get('album', [])
		songs =  matches.get('song', [])
		
		if artists:
			if not isinstance(artists, list):
				artists = [artists]
			
			root = QtGui.QTreeWidgetItem(self.searchResultTreeWidget)
			root.setText(0, 'Artists')
			root.setExpanded(True)
			
			for data in artists:
				data = models.itemDecodeHtml(data)
				item = QtGui.QTreeWidgetItem(root)
				item.data = data
				item.setText(0, data.get('name', 'Unknown'))
		
		if albums:
			if not isinstance(albums, list):
				albums = [albums]
			
			root = QtGui.QTreeWidgetItem(self.searchResultTreeWidget)
			root.setText(0, 'Albums')
			root.setExpanded(True)
			
			#print albums[0]
			for data in albums:
				data = models.itemDecodeHtml(data)
				item = QtGui.QTreeWidgetItem(root)
				item.data = data
				display = '%s - %s'%(data.get('artist', 'Unknown'), data.get('title', 'Unknown'))
				item.setText(0, display)
		
		if songs:
			if not isinstance(songs, list):
				songs = [songs]
			
			root = QtGui.QTreeWidgetItem(self.searchResultTreeWidget)
			root.setText(0, 'Songs')
			root.setExpanded(True)
			
			#print songs[0]
			for data in songs:
				data = models.itemDecodeHtml(data)
				item = QtGui.QTreeWidgetItem(root)
				item.data = data
				display = '%s - %s - %s'%(data.get('artist', 'Unknown'), data.get('album', 'Uknown'), data.get('title', 'Unknown'))
				item.setText(0, display)
	
	def searchItemDoubleClicked(self, item, column):
		data = item.data
		print data.keys()
		print data.get('isDir', False)
		
	
	def setActiveArtist(self, artistId):
		self.albumModel.loadArtist(artistId)
		
	def setActiveAlbum(self, albumId):
		self.trackModel.loadAlbum(albumId)
		
	def setNowPlaying(self, song, playlistIndex):
		self.nowPlaying = song
		self.currentSongChanged.emit(playlistIndex)
		self.playlistModel.currentTrack = playlistIndex
		self.playlistModel.niceReset()
		
		self.stream(self.nowPlaying.get('id'))
		
		self.setWindowTitle('Subsonic Client :: %s - %s - %s'%(self.nowPlaying.get('title', 'Unknown'), self.nowPlaying.get('album', 'Unknown'), self.nowPlaying.get('artist', 'Unknown')))
		
	
	def getPixmap(self, coverId):
		return self.coverArtCache.get(coverId)
	
	def stream(self, sid):
		'''
			Set a new stream to be the current media source
		'''
		url = QtCore.QUrl(self.connection._baseUrl+'/'+self.connection._serverPath+'/stream.view')
		if self.connection._port:
			url.setPort(int(self.connection._port))
		
		#Build url query
		url.addQueryItem('id', sid)
		url.addQueryItem('c', 'py-sonic')
		url.addQueryItem('u', self.connection._username)
		url.addQueryItem('p', self.connection._rawPass)
		url.addQueryItem('v', connection.API_VERSION)
		
		#stop the current media first
		self.stop()
		
		#Set up new media stream
		try:
			self.media = self.instance.media_new(url.toString(), '--loop', '--http-caching=500')
			self.player.set_media(self.media)
		except:
			print 'Error with setting up media!'
		
		self.seekSlider.setEnabled(False)
	
	def closeEvent(self, event):
		#Hide instead
		self.hide()
		event.ignore()
	
	def quit(self):
		try:
			f = open(clientPlaylist, 'wb')
			pickle.dump(self.playlistModel._data, f)
			f.close()
		except Exception, e:
			print e
		self.saveWindowState()
		self.hide()
		self.stop()
		self.coverArtCache.loader.join()
		
		self.tray.hide()
		QtGui.qApp.quit()
		


def startup(force=False):
	'''Startup the app with the last settings, or get new ones if need be'''
	settings = QtCore.QSettings('subsonic', 'subsonic-client')
	
	user = settings.value('user', 'username')
	passwd = settings.value('passwd', 'password')
	server = settings.value('server', 'http://yourserver.com')
	path = settings.value('path', '/rest')
	port = settings.value('port', 80)
	
	if not force:
		force=True
		try:
			testconnection = connection.Connection(server, user, passwd, port, path, 'subsonic-desktop')
			if testconnection.ping():
				force = False
		except: pass
	
	if force:
		login = LoginWindow(server, port, path, user, passwd)
		result = login.exec_()
		if not result:
			return False
		server, port, path, user, passwd = login.result
	
	settings.setValue('user', user)
	settings.setValue('passwd', passwd)
	settings.setValue('server', server)
	settings.setValue('path', path)
	settings.setValue('port', port)
	
	global window
	try:
		window.close()
	except:
		pass
	
	window = MainWindow(server, port, path, user, passwd)
	window.show()
		
if __name__ == '__main__':
	app = QtGui.QApplication(sys.argv)
	#QtGui.QApplication.setStyle(QtGui.QStyleFactory.create('cleanlooks'))
	startup()
	sys.exit(app.exec_())
