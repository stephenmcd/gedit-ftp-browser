#!/usr/bin/python
#
# Copyright (C) 2008 YinSee, Tan (yinsee@wsatp.com)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#

#
# Notes
# -----
# the plugin saves its last-used settings in your ~/.gnome2/gedit/plugins/lastftp.ini
# Feedback and comments are welcome. (I am very new to python so please bear with my codes)
#
# Todo
# ----
# - file filtering (i hide it for now ;))
#

import gedit
import gtk
import gobject
from ftplib import FTP
import re
import sys
import os

class FTPWindowHelper:
	def __init__(self, plugin, window):
		self._window = window
		self._plugin = plugin
		# Prime the statusbar
		self.statusbar = window.get_statusbar()
		self.context_id = self.statusbar.get_context_id("FTPPlugin")
		self.message_id = None
		self.config_path = os.path.expanduser('~/.gnome2/gedit/plugins')
		self.ftp_cwd = '/'

		# create panel
		self._browser = FileBrowser(self)
		panel = self._window.get_side_panel()
		panel.add_item(self._browser, "FTP Browser", 'gtk-disconnect')

		self.load_config()

	def flush_events(self):
		while gtk.events_pending():
			gtk.main_iteration() 
	
	def load_config(self):
		# load last config
		try:
			f = open(self.config_path+"/lastftp.ini");
		except:
			#print "no config at ",self.config_path+"/lastftp.ini"
			pass
		else:
			self._browser.url.set_text(f.readline().strip())
			self._browser.user.set_text(f.readline().strip())
			self._browser.pasw.set_text(f.readline().strip())
			self._browser.filt.set_text(f.readline().strip())
			self.ftp_cwd = f.readline().strip()
			self._browser.location.set_text(self.ftp_cwd)
			f.close()

	def save_config(self):
		if not os.path.exists(self.config_path):
			try:
				os.makedirs(self.config_path)
			except:
				self.error_msg("Error creating user plugin directory")
				return
		try:
			f = open(self.config_path+"/lastftp.ini", "wt");
		except:
			self.error_msg("Can't write config at ",self.config_path+"/lastftp.ini")
			pass
		else:
			f.write(self._browser.url.get_text()+"\n")
			f.write(self._browser.user.get_text()+"\n")
			f.write(self._browser.pasw.get_text()+"\n")
			f.write(self._browser.filt.get_text()+"\n")
			f.write(self.ftp_cwd+"\n")
			f.close()

	# Statusbar message
	def update_status(self, message):
		if self.message_id:
			self.statusbar.remove(self.context_id, self.message_id)
		self.message_id = self.statusbar.push(self.context_id, "FTP: %s" % message)
		self.flush_events()

	def deactivate(self):
		panel = self._window.get_side_panel()
		panel.remove_item(self._browser)
		self._window = None
		self._plugin = None
		self._browser = None
		if self.message_id:
			self.statusbar.remove(self.context_id, self.message_id)

	def update_ui(self):
		doc = self._window.get_active_document()
		if doc!=None and hasattr(doc,'is_ftpfile'):
			self.update_status('Temp file %s' %doc.get_uri_for_display())
		pass

	def on_connect(self, btn):
		self.open_folder(None);

	def on_refresh(self, btn):
		self.open_folder(".");

	def on_save_as(self, btn):
		"""
		save as button clicked
		"""

		# get the current document and title
		app = gedit.app_get_default()
		win = app.get_active_window()
		doc = win.get_active_document()
		if doc is None:
			return
		title = doc.get_uri().split(os.sep)[-1]
	
		# show the dialog for entering the filename
		dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK_CANCEL,
			flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
		dialog.set_default_response(gtk.RESPONSE_OK)
		dialog.set_markup("\nSave as:")
		entry = gtk.Entry()
		entry.set_activates_default(gtk.TRUE)
		if title is not None:
			entry.set_text(title)
		dialog.vbox.pack_end(entry, True, True, 0)
		dialog.show_all()

		# save to the temp file and upload		
		if dialog.run() == gtk.RESPONSE_OK:
			title = entry.get_text()
			tmpfile = self._get_tmpfile(title)
			doc.set_modified(True)
			doc.load("file:///%s" % tmpfile, gedit.encoding_get_current(), 0, 
				True)
			self._setup_ftpfile(doc, tmpfile, "%s/%s" % (self.ftp_cwd, title), 
				True)
			doc.save(True)
			dialog.destroy()
		
	def _setup_ftpfile(self, doc, tmpfile, ftpfile, refresh):
		"""
		mark the doc as an ftp file and connect the saved event to the 
		document, only once
		"""
		
		if hasattr(doc, "_save_handler"):
			doc.disconnect(doc._save_handler)
		doc.is_ftpfile = True
		doc._save_handler = doc.connect("saved", self.on_ftp_doc_saved, tmpfile, 
			ftpfile, self._browser.url.get_text(), self._browser.user.get_text(), 
			self._browser.pasw.get_text(), refresh)

	def _get_tmpfile(self, file):
		"""
		given a filename, return the path to the corresponding temp file
		ensuring directories in the path are created
		"""

		path = "/tmp/gedit/%s%s" %(self._browser.url.get_text(),self.ftp_cwd)
		tmpfile = '%s/%s' %(path,file)
		if not os.path.exists(path):
			try:
				os.makedirs(path, mode=0777)
			except:
				self.error_msg("Error creating directory %s" %(path))
				return None
		return tmpfile

	def open_file(self, file):

		tmpfile = self._get_tmpfile(file)
		if tmpfile is None:
			return
		ftp = self.ftp_connect()
		if ftp==None: return

		self.update_status('Downloading %s/%s' %(self.ftp_cwd,file))
		try:
			ftp.retrbinary('RETR %s/%s' %(self.ftp_cwd,file), open(tmpfile, 'wb').write)
		except:
			self.error_msg('Error retrieving file %s/%s' %(self.ftp_cwd,file))
			ftp.close()
			return
		ftp.close()
		tab = self._window.create_tab_from_uri('file:///%s' %tmpfile,gedit.encoding_get_current(),0,False,True)
		self._setup_ftpfile(tab.get_document(), tmpfile, "%s/%s" % 
			(self.ftp_cwd, file), False)
		self.update_status('Temp file loaded %s' %tmpfile)

	def on_ftp_doc_saved(self,doc,arg1,src,dest,url,u,p,refresh):
		if doc.is_untouched(): return
		ftp = self.ftp_connect(url,u,p,False)
		if ftp==None: return

		self.update_status('Uploading %s to %s@%s%s' %(src,u,url,dest))
		try:
			ftp.storbinary('STOR %s' %dest, open(src, 'rb'), 1024)
			self.update_status('Saved.')
		except:
			self.error_msg('Error uploading file %s' %dest)
		if refresh:
			self.ftp_list(ftp)
		ftp.close()

	def ftp_connect(self,url=None,u=None,p=None,save=True):
		if url==None:
			url = self._browser.url.get_text()
		if u==None:
			u = self._browser.user.get_text()
		if p==None:
			p = self._browser.pasw.get_text()

		if url.find(':') != -1:
			v = url.split(':')
			url = v[0]
			port = v[1]
		else:
			port = 21

		self.update_status('Connecting %s@%s on port %s' %(u,url,port))

		# go ftp
		try:
			ftp = FTP()
			ftp.connect(url,port)
			ftp.login(u,p)
		except:
			self.error_msg('FTP Connecting error')
			return None
		self.save_config()
		return ftp

	def open_folder(self, folder):
		ftp = self.ftp_connect()
		if ftp==None: return

		# reset directory to default
		if folder != None:
			try:
				ftp.cwd("%s/%s" %(self.ftp_cwd,folder))
			except:
				self.error_msg('Error opening folder')
				self.open_folder(None)
				return
		self.ftp_cwd = ftp.pwd()
		self._browser.location.set_text(self.ftp_cwd)
		self.ftp_list(ftp)
		ftp.close()

	def error_msg(self,msg):
		m = gtk.MessageDialog(None,gtk.DIALOG_DESTROY_WITH_PARENT,gtk.MESSAGE_INFO,gtk.BUTTONS_OK,"%s. Reason:\n%s %s" %(msg,sys.exc_info()[0],sys.exc_info()[1]))
		m.set_title('FTP Browser')
		m.run()
		m.destroy()

	def ftp_list(self,ftp):
		self._list = []
		self._browser.browser_model.clear()
		self.update_status('Reading %s' %self.ftp_cwd)
		if self.ftp_cwd != '/':
			self._browser.browser_model.append([self._browser.foldericon,'..','d'])

		try:
			allfiles = ftp.dir(self.ftp_cwd,self.list_files)
		except:
			self.error_msg('FTP LIST error')
			return

	def list_files(self,item):
		a = re.compile(r'\s+').split(item)
		if len(a) < 9: return	#skip if the line returned is not friendly
		self._list.append(a)
		if re.compile(r'^d').match(a[0]):
			self._browser.browser_model.append([self._browser.foldericon,a[8],'d'])
		else:
			self._browser.browser_model.append([self._browser.fileicon,a[8],'f'])

	def on_list_row_activated(self,tv,path,viewcol):
		selection = tv.get_selection()
		(model, iter) = selection.get_selected()
		ftype = model.get_value(iter, 2)
		fname = model.get_value(iter, 1)
		if ftype == 'd':
			self.open_folder(fname)
		else:
			self.open_file(fname)

class FTPPlugin(gedit.Plugin):
	def __init__(self):
		gedit.Plugin.__init__(self)
		self._instances = {}

	def activate(self, window):
		self._instances[window] = FTPWindowHelper(self, window)

	def deactivate(self, window):
		self._instances[window].deactivate()
		del self._instances[window]

	def update_ui(self, window):
		self._instances[window].update_ui()


class FileBrowser(gtk.VBox):
	def __init__(self, helper):
		gtk.VBox.__init__(self)

		# ftp params
		ff = gtk.Table(4,2)
		ff.set_row_spacings(2); ff.set_col_spacings(5);
		ff.attach(gtk.Label('Host'),0,1,0,1,False,False);
		ff.attach(gtk.Label('User'),0,1,1,2,False,False);
		ff.attach(gtk.Label('Pass'),0,1,2,3,False,False);
		#ff.attach(gtk.Label('Filter'),0,1,3,4,False,False);
		self.url = gtk.Entry()
		self.url.set_size_request(10,-1)
		self.user = gtk.Entry()
		self.user.set_size_request(10,-1)
		self.pasw = gtk.Entry()
		self.pasw.set_size_request(10,-1)
		self.filt = gtk.Entry()
		self.filt.set_size_request(10,-1)
		self.pasw.set_visibility(False)

		ff.attach(self.url,1,2,0,1);
		ff.attach(self.user,1,2,1,2);
		ff.attach(self.pasw,1,2,2,3);
		#ff.attach(self.filt,1,2,3,4);

		self.pack_start(ff, False, False)

		# buttons
		#b = gtk.HBox(False)
		i=gtk.Image()
		i.set_from_stock('gtk-home',gtk.ICON_SIZE_BUTTON)
		#b.pack_start(i)
		#b.pack_start(gtk.Label('Connect'))
		btn_connect = gtk.Button()
		btn_connect.add(i)
		btn_connect.connect("clicked", helper.on_connect)

		#b = gtk.HBox(False)
		i=gtk.Image()
		i.set_from_stock('gtk-refresh',gtk.ICON_SIZE_BUTTON)
		#b.pack_start(i)
		#b.pack_start(gtk.Label('Refresh'))
		btn_refresh = gtk.Button()
		btn_refresh.add(i)
		btn_refresh.connect("clicked", helper.on_refresh)

		i=gtk.Image()
		i.set_from_stock('gtk-save-as',gtk.ICON_SIZE_BUTTON)
		btn_save_as = gtk.Button()
		btn_save_as.add(i)
		btn_save_as.connect("clicked", helper.on_save_as)

		buttons=gtk.HBox(False)
		buttons.pack_start(btn_connect,False,False)
		buttons.pack_start(btn_refresh,False,False)
		buttons.pack_start(btn_save_as,False,False)

		self.pack_start(buttons,False,False)

		#location label
		self.location = gtk.Label(helper.ftp_cwd)
		self.location.set_line_wrap(True)
		self.location.set_justify(gtk.JUSTIFY_LEFT)
		self.location.set_alignment(0,0.5)
		self.pack_start(self.location, False, False)

		# add a treeview
		sw = gtk.ScrolledWindow()
		sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		sw.set_shadow_type(gtk.SHADOW_IN)
		self.browser_model = gtk.ListStore(gtk.gdk.Pixbuf, str, str)
		self.browser = gtk.TreeView(self.browser_model)
		self.browser.set_headers_visible(True)
		sw.add(self.browser)
		self.pack_start(sw)

		self.foldericon = self.browser.render_icon('gtk-directory',gtk.ICON_SIZE_MENU)
		self.fileicon = self.browser.render_icon('gtk-file',gtk.ICON_SIZE_MENU)

		# add columns to the treeview
		col = gtk.TreeViewColumn()
		render_pixbuf = gtk.CellRendererPixbuf()
		col.pack_start(render_pixbuf, expand=False)
		col.add_attribute(render_pixbuf, 'pixbuf', 0)
		self.browser.append_column(col)

		col = gtk.TreeViewColumn('Filename')
		render_text = gtk.CellRendererText()
		col.pack_start(render_text, expand=True)
		col.add_attribute(render_text, 'text', 1)
		self.browser.append_column(col)

		# connect stuff
		self.browser.connect("row-activated",helper.on_list_row_activated)
		self.show_all()
