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
import pango

LOCAL_PATH = "/tmp/gedit/"

class FTPWindowHelper:

	def __init__(self, plugin, window):

		self._window = window
		self._plugin = plugin
		
		# Prime the statusbar
		self.statusbar = window.get_statusbar()
		self.context_id = self.statusbar.get_context_id("FTPPlugin")
		self.message_id = None
		self.ftp_cwd = "/"

		# create panel
		self._browser = FileBrowser(self)
		panel = self._window.get_side_panel()
		panel.add_item(self._browser, "FTP Browser", "gtk-disconnect")
		
		# load config from file (if it exists)
		self.config_path = os.path.dirname(os.path.abspath(__file__))
		self.config_file = os.path.join(self.config_path, "lastftp.ini")
		self.load_config()

		# connect the tab-added event (and apply manually to existing docs) to 
		# check for files in the ftp directory as these may be opened on 
		# startup by the reopen-tabs plugin for example
		for doc in window.get_documents():
			self.on_tab_added(window, tab)
		window.connect("tab-added", self.on_tab_added)

	def flush_events(self):
		while gtk.events_pending():
			gtk.main_iteration() 
	
	def load_config(self):
		"""
		load last config
		"""
	
		try:
			f = open(self.config_file);
		except:
			#if no config file, then silently quit
			pass
		else:
			self._browser.url.set_text(f.readline().strip())
			self._browser.user.set_text(f.readline().strip())
			self._browser.pasw.set_text(f.readline().strip())
			self._browser.filt.set_text(f.readline().strip())
			self.ftp_cwd = f.readline().strip()
			self._browser.location.set_text(self.ftp_cwd)
			pasv = f.readline().strip() == "True"
			self._browser.combo_pasv_mode.set_active(pasv)
			f.close()

	def save_config(self):
		"""
		save config file
		"""
	
		if not os.path.exists(self.config_path):
			try:
				os.makedirs(self.config_path)
			except:
				self.error_msg("Error creating user plugin directory")
				return
		try:
			f = open(self.config_file, "wt");
		except:
			self.error_msg("Can't write config at %s" % self.config_file)
			pass
		else:
			f.write(self._browser.url.get_text()+"\n")
			f.write(self._browser.user.get_text()+"\n")
			f.write(self._browser.pasw.get_text()+"\n")
			f.write(self._browser.filt.get_text()+"\n")
			f.write(self.ftp_cwd+"\n")
			if (self._browser.combo_pasv_mode.get_active()):
				f.write("True\n")
			else:
				f.write("False\n")
			f.close()

	def update_status(self, message):
		"""
		sets a message in the status bar
		"""

		if self.message_id:
			self.statusbar.remove_message(self.context_id, self.message_id)
		self.message_id = self.statusbar.push(self.context_id, "FTP: %s" % message)
		self.flush_events()

	def deactivate(self):
		"""
		destroy gtk objects on deactivation
		"""
		
		panel = self._window.get_side_panel()
		panel.remove_item(self._browser)
		self._window = None
		self._plugin = None
		self._browser = None
		if self.message_id:
			self.statusbar.remove_message(self.context_id, self.message_id)

	def on_connect(self, btn):
		"""
		ftp home button clicked
		"""
		
		self.ftp_cwd = "/"
		self.open_directory(".")

	def on_refresh(self, btn):
		"""
		ftp refresh button is clicked
		"""
		
		self.open_directory(".")

	def on_parent(self, btn):
		"""
		ftp up to parent directory is clicked
		"""
		
		self.open_directory("..")

	def on_tab_added(self, window, tab):
		"""
		when a tab is created check if the doc is in the ftp directory and if 
		so mark it as an ftp file and retrieve its contents if the local file 
		is missing
		"""

		doc = tab.get_document()
		local_file = doc.get_uri_for_display()
		if local_file is not None and local_file.startswith(LOCAL_PATH):
			ftp_file = "/%s" % local_file.split(LOCAL_PATH, 1)[1].split("/", 1)[1]
			if not os.path.exists(local_file):
				def callback(s):
					doc.set_text(s)
					doc.save(True)
				self._get_ftp_file(ftp_file, callback)
			self._mark_doc_as_ftp(doc, local_file, ftp_file)

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
		title = doc.get_uri()
		if title is None:
			title = ""
		title = title.split(os.sep)[-1]
	
		# show the dialog for entering the filename
		dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK_CANCEL,
			flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT)
		dialog.set_default_response(gtk.RESPONSE_OK)
		dialog.set_markup("\nSave as:")
		entry = gtk.Entry()
		entry.set_activates_default(True)
		if title is not None:
			entry.set_text(title)
		dialog.vbox.pack_end(entry, True, True, 0)
		dialog.show_all()

		# save to the temp file and upload		
		if dialog.run() == gtk.RESPONSE_OK:
			title = entry.get_text()
			local_file = self._get_local_file(title)
			doc.set_modified(True)
			doc.load("file://%s" % local_file, gedit.encoding_get_current(), 0, 
				True)
			self._mark_doc_as_ftp(doc, local_file, "%s/%s" % (self.ftp_cwd, title), 
				True)
			doc.save(True)
		dialog.destroy()
		
	def _mark_doc_as_ftp(self, doc, local_file, ftp_file, refresh=False):
		"""
		mark the doc as an ftp file and connect the saved event to the doc
		which will save the file to the ftp server
		"""

		if hasattr(doc, "_ftp_save_handler"):
			doc.disconnect(doc._ftp_save_handler)
		doc._ftp_save_handler = doc.connect("saved", self.on_ftp_doc_saved, 
			local_file, ftp_file, self._browser.url.get_text(), 
			self._browser.user.get_text(), self._browser.pasw.get_text(), 
			refresh)

	def _get_local_file(self, ftp_file):
		"""
		given a ftp filename, return the path to the corresponding local file
		ensuring directories in the path are created
		"""

		local_file = "%s%s%s" % (LOCAL_PATH, self._browser.url.get_text(), 
			self._get_ftp_path(ftp_file))
		local_path = os.path.dirname(local_file)
		if not os.path.exists(local_path):
			try:
				os.makedirs(local_path, mode=0777)
			except:
				self.error_msg("Error creating directory %s" % (local_path))
				return None
		return local_file

	def _get_ftp_file(self, ftp_file, callback):
		"""
		download the file over ftp and apply the callback to it - push this
		code into the main thread with gobject.timeout_add otherwise its
		blocking nature raises errors in the calls to gtk.main_iteration
		"""
		
		def run_as_timeout():
			ftp = self.ftp_connect()
			if ftp is None:
				return False
			_ftp_file = self._get_ftp_path(ftp_file)
			self.update_status("Downloading %s" % _ftp_file)
			try:
				data = []
				ftp.retrbinary("RETR %s" % _ftp_file, data.append)
				callback("".join(data))
			except:
				self.error_msg("Error retrieving file %s" % _ftp_file)
			finally:
				ftp.close()
			return False
		gobject.timeout_add(1, run_as_timeout)
		
	def _get_ftp_path(self, ftp_file):
		"""
		return the full ftp path to the given ftp file
		"""
		
		ftp_file = "/%s" % ftp_file
		if self.ftp_cwd != "/":
			ftp_file = "%s%s" % (self.ftp_cwd, ftp_file)
		return ftp_file
		
	def open_file(self, ftp_file):
		"""
		file in the ftp browser listing is clicked
		"""
	
		local_file = self._get_local_file(ftp_file)
		if local_file is None:
			return
		def callback(s):
			f = open(local_file, "wb")
			f.write(s)
			f.close()
			tab = self._window.create_tab_from_uri("file://%s" % 
				local_file, gedit.encoding_get_current(), 0, False, True)
			self._mark_doc_as_ftp(tab.get_document(), local_file, 
				self._get_ftp_path(ftp_file), False)
			self.update_status("Temp file loaded %s" % local_file)
		self._get_ftp_file(ftp_file, callback)

	def on_ftp_doc_saved(self, doc, arg1, local_path, ftp_path, url, username, 
		password, refresh):
		"""
		document save event handler that's attached to ftp docs that
		pushes the contents of the document to the ftp server when saved
		"""
	
		if doc.is_untouched():
			return
		ftp = self.ftp_connect(url=url, username=username, password=password, 
			save=False)
		if ftp is None:
			return
		self.update_status("Uploading %s to %s@%s%s" % 
			(local_path, username, url, ftp_path))
		try:
			ftp.storbinary("STOR %s" % ftp_path, open(local_path, "rb"), 1024)
			self.update_status("Saved.")
		except:
			self.error_msg("Error uploading file %s" % ftp_path)
		if refresh:
			self.ftp_list(ftp)
		ftp.close()

	def ftp_connect(self, url=None, username=None, password=None, save=True):
		"""
		create a connection to the ftp server and return it
		"""
		
		if url is None:
			url = self._browser.url.get_text()
		if username is None:
			username = self._browser.user.get_text()
		if password is None:
			password = self._browser.pasw.get_text()

		port = 21
		if ":" in url:
			url, port = url.split(":", 1)
		self.update_status("Connecting %s@%s on port %s" % (username, url, port))

		# go ftp
		try:
			ftp = FTP()
			ftp.connect(url, port)
			ftp.login(username, password)
			ftp.set_pasv(self._browser.combo_pasv_mode.get_active())
		except:
			self.error_msg("FTP Connecting error")
			return None
		self.save_config()
		return ftp

	def open_directory(self, ftp_dir):
		"""
		directory in the ftp browser listing is clicked
		"""

		ftp = self.ftp_connect()
		if ftp is None:
			return
		# reset directory to default
		if ftp_dir is not None:
			regex = re.compile('(/[^/]*?/\.\.)$')
			parent = regex.sub('', self._get_ftp_path(ftp_dir))
			try:
				ftp.cwd(parent)
 			except:
 				self.error_msg("Error opening directory")
 				self.open_directory(None)

			try:
				ftp.cwd(self._get_ftp_path(ftp_dir))
			except:
				self.error_msg("Error opening directory")
				self.open_directory(None)
				return
		self.ftp_cwd = ftp.pwd()
		self._browser.location.set_text(self.ftp_cwd)
		self.ftp_list(ftp)
		ftp.close()

	def error_msg(self,msg):
		"""
		displays an error message dialog
		"""
		
		m = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, 
			gtk.MESSAGE_INFO, gtk.BUTTONS_OK, "%s. Reason:\n%s %s" % 
			(msg, sys.exc_info()[0], sys.exc_info()[1]))
		m.set_title("FTP Browser")
		m.run()
		m.destroy()

	def ftp_list(self,ftp):
		"""
		retrieves a directory listing from the ftp server
		"""

		self._browser.browser_model.clear()
		self.update_status("Reading %s" % self.ftp_cwd)
		try:
			allfiles = ftp.dir(self.ftp_cwd, self.list_files)
			self.update_status("done")
		except:
			self.error_msg("FTP LIST error")
			return

	def list_files(self,item):
		"""
		adds an item to the ftp browser listing, either file or directory
		"""

		a = re.compile(r"\s+").split(item)
		if re.compile(r"<DIR>").match(a[2]) or re.compile(r"^d").match(a[0]):
			self._browser.browser_model.append([self._browser.dir_icon, 
				a[-1],"d"])
		else:
			self._browser.browser_model.append([self._browser.file_icon,
				a[-1], "f"])

	def on_list_row_activated(self,tv,path,viewcol):
		"""
		item in ftp browser listing is clicked, open file or directory
		"""
		
		selection = tv.get_selection()
		model, iter = selection.get_selected()
		ftype = model.get_value(iter, 2)
		fname = model.get_value(iter, 1)
		if ftype == "d":
			self.open_directory(fname)
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

class FileBrowser(gtk.VBox):
	def __init__(self, helper):
		gtk.VBox.__init__(self)

		# ftp params
		ff = gtk.Table(2,4)
		ff.set_row_spacings(2); ff.set_col_spacings(5);
		ff.attach(gtk.Label('Host'),0,1,0,1,False,False);
		ff.attach(gtk.Label('User'),0,1,1,2,False,False);
		ff.attach(gtk.Label('Pass'),2,3,1,2,False,False);
		#ff.attach(gtk.Label('Filter'),0,1,3,4,False,False);
		self.url = gtk.Entry()
		self.url.set_size_request(10,-1)
		self.user = gtk.Entry()
		self.user.set_size_request(10,-1)
		self.pasw = gtk.Entry()
		self.pasw.set_size_request(10,-1)
		self.pasw.set_visibility(False)
		self.filt = gtk.Entry()
		self.filt.set_size_request(10,-1)

		ff.attach(self.url,1,4,0,1);
		ff.attach(self.user,1,2,1,2);
		ff.attach(self.pasw,3,4,1,2);
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
		btn_connect.set_tooltip_text("Connect to FTP server")
		btn_connect.connect("clicked", helper.on_connect)

		#b = gtk.HBox(False)
		i=gtk.Image()
		i.set_from_stock('gtk-refresh',gtk.ICON_SIZE_BUTTON)
		#b.pack_start(i)
		#b.pack_start(gtk.Label('Refresh'))
		btn_refresh = gtk.Button()
		btn_refresh.add(i)
		btn_refresh.set_tooltip_text("Refresh remote directory list")
		btn_refresh.connect("clicked", helper.on_refresh)

		i=gtk.Image()
		i.set_from_stock('gtk-go-up',gtk.ICON_SIZE_BUTTON)
		btn_parent =  gtk.Button()
		btn_parent.add(i)
		btn_parent.set_tooltip_text("Go up to parent directory")
		btn_parent.connect("clicked", helper.on_parent)

		#list for combo box (Active/Passive FTP)
		self.list = gtk.ListStore(int, str)
		iter = self.list.append( (False, "Active FTP",) )
		self.list.set(iter)
		iter = self.list.append( (True, "Passive FTP",) )
		self.list.set(iter)

		# save as button for adding new file
		i=gtk.Image()
		i.set_from_stock('gtk-save-as',gtk.ICON_SIZE_BUTTON)
		btn_save_as = gtk.Button()
		btn_save_as.add(i)
		btn_save_as.set_tooltip_text("Save new file to FTP server")
		btn_save_as.connect("clicked", helper.on_save_as)

		#Combo box
		self.combo_pasv_mode = gtk.ComboBox()
		cell = gtk.CellRendererText()
		self.combo_pasv_mode.pack_start(cell, True)
		self.combo_pasv_mode.add_attribute(cell, 'text', 1)
		self.combo_pasv_mode.set_model(self.list)
		self.combo_pasv_mode.set_active(True) #default: passive mode=True
		

		#pack buttons and combo box (active/passive FTP) on same row
		buttonsAndCombo=gtk.HBox(False)
		buttonsAndCombo.pack_start(btn_connect,False,False)
		buttonsAndCombo.pack_start(btn_refresh,False,False)
		buttonsAndCombo.pack_start(btn_parent,False,False)
		buttonsAndCombo.pack_start(btn_save_as,False,False)
		buttonsAndCombo.pack_start(self.combo_pasv_mode,False,False)
		self.pack_start(buttonsAndCombo,False,False)


		#location label
		self.location = gtk.Label(helper.ftp_cwd)
		self.location.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
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

		self.dir_icon = self.browser.render_icon('gtk-directory', gtk.ICON_SIZE_MENU)
		self.file_icon = self.browser.render_icon('gtk-file', gtk.ICON_SIZE_MENU)

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
