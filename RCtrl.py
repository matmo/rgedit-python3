##############################################################################
#                                                                            #
#    Rgedit: gedit plugin for R                                              #
#    Copyright (C) 2009-2012  Dan Dediu                                      #
#                                                                            #
#    This program is free software: you can redistribute it and/or modify    #
#    it under the terms of the GNU General Public License as published by    #
#    the Free Software Foundation, either version 3 of the License, or       #
#    (at your option) any later version.                                     #
#                                                                            #
#    This program is distributed in the hope that it will be useful,         #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#    GNU General Public License for more details.                            #
#                                                                            #
#    You should have received a copy of the GNU General Public License       #
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                            #
##############################################################################


##############################################################################
#    This was inspired by rkward (http://sourceforge.net/projects/rkward/)   #
#    and Tinn-R (http://sourceforge.net/projects/tinn-r/) and aims to offer  #
#    a light-weight, GTK+ IDE for R in the spirit of the above applications. #
#                                                                            #
#    It uses a heavily modified version of Paolo Borelli's VTE terminal for  #
#    gedit to allow embedding of R consoles.                                 #
#    Inspiration and code from Sukimashita's Open URI Context Menu Plugin    #
#                                                                            #
#    The most important idea is that Rgedit does not need any custom R       #
#    package as the whole interaction processeds through the R console. This #
#    allows it to be ver light on resources and fast but also imposes a      #
#    number of restrictions on the "intimacy" of the interaction with R.     #
#                                                                            #
#    Nevertheless, Rgedit offers a range of tools very useful to the heavy   #
#    (and professional) R user, including syntax highlighting and advanced   #
#    editing (thanks gedit!), execution of the current line, selection,      #
#    the whole file or usr-defined persistent blocks of code as well as      #
#    several separate R consoles. For more details, see the help file.       #
#                                                                            #
#    Moreover, with the addition of profiles, it can communicate with many   #
#    other interactive programs such as Octave or Python and it can also     #
#    work over ssh connections to remote hosts. These can be customized,     #
#    allowing the user to define his/her own profiles.                       #
#                                                                            #
##############################################################################


from gi.repository import GObject, Gedit, Gtk, Gdk, GdkPixbuf, Vte, GLib, Pango, GtkSource
import os.path
import pickle
import platform
import tempfile
import glob
import sys
from xml.dom import minidom
import xml.sax.saxutils
import re
import signal
import urllib.request, urllib.error, urllib.parse
import webbrowser


# Menu item example, insert a new item in the Tools menu
ui_str = """<ui>
  <menubar name="MenuBar">
    <menu name="R" action="R">
        <menuitem name="RCtrlSel" action="RCtrlSel"/>
        <menuitem name="RCtrlLine" action="RCtrlLine"/>
        <menuitem name="RCtrlAll" action="RCtrlAll"/>
        <menuitem name="RCtrlCursor" action="RCtrlCursor"/>
        <separator/>
        <menuitem name="RCtrlBlock1Run" action="RCtrlBlock1Run"/>
        <menuitem name="RCtrlBlock1Def" action="RCtrlBlock1Def"/>
        <separator/>
        <menuitem name="RCtrlBlock2Run" action="RCtrlBlock2Run"/>
        <menuitem name="RCtrlBlock2Def" action="RCtrlBlock2Def"/>
        <separator/>
        <menuitem name="RCtrlNewTab" action="RCtrlNewTab"/>
        <menuitem name="RCtrlClose" action="RCtrlClose"/>
        <menuitem name="RCtrlAttach" action="RCtrlAttach"/>
        <!--menuitem name="RCtrlNewTab" action="RCtrlNewTab"/-->
        <!--menuitem name="RCtrlLoadWorkspace" action="RCtrlLoadWorkspace"/-->
        <!--menuitem name="RCtrlSaveWorkspace" action="RCtrlSaveWorkspace"/-->
        <separator/>
        <menuitem name="RCtrlLandmark" action="RCtrlLandmark"/>
        <menuitem name="RCtrlWizards" action="RCtrlWizards"/>
        <menuitem name="RCtrlLibraries" action="RCtrlLibraries"/>
        <!--menuitem name="RCtrlHelpSel" action="RCtrlHelpSel"/-->
        <!--menuitem name="RCtrlShowSel" action="RCtrlShowSel"/-->
        <!--menuitem name="RCtrlEditSel" action="RCtrlEditSel"/-->
        <separator/>
        <menuitem name="RCtrlShowHide" action="RCtrlShowHide"/>
        <menuitem name="RCtrlConfig" action="RCtrlConfig"/>
        <menuitem name="RCtrlUpdate" action="RCtrlUpdate"/>
        <menuitem name="RCtrlHelpRCtrl" action="RCtrlHelpRCtrl"/>
        <menuitem name="RCtrlAbout" action="RCtrlAbout"/>
    </menu>
  </menubar>
  <toolbar name="ToolBar">
    <separator/>
    <toolitem name="RCtrlSel" action="RCtrlSel"/>
    <toolitem name="RCtrlLine" action="RCtrlLine"/>
    <toolitem name="RCtrlAll" action="RCtrlAll"/>
    <toolitem name="RCtrlCursor" action="RCtrlCursor"/>
    <toolitem name="RCtrlBlock1Run" action="RCtrlBlock1Run"/>
    <toolitem name="RCtrlBlock1Def" action="RCtrlBlock1Def"/>
    <toolitem name="RCtrlBlock2Run" action="RCtrlBlock2Run"/>
    <toolitem name="RCtrlBlock2Def" action="RCtrlBlock2Def"/>
    <!--toolitem name="RCtrlNewTab" action="RCtrlNewTab"/-->
    <!--toolitem name="RCtrlNewTabMenu" action="RCtrlNewTabMenu"/-->
  </toolbar>
</ui>
"""

# The special comment used to put a landmark in the R code:
landmark_comment_header = "# @@ RGEDIT LANDMARK @@:"
landmark_comment_placeholder = _(" your text goes here")

# The temporary file used to communicate with R:
R_temp_file = tempfile.mkstemp(suffix='.r',prefix='RTmpFile-',dir='/tmp/')[1]

# The shell to use (default: bash):
shell_command_name = "bash"


#######################################################
#               GtkBuilder vs Glade                   #
#######################################################

# Is Gtk version new enough to use GtkBuilder or Glade?
def use_GtkBuilder_or_Glade():
    return (Gtk.get_major_version(),Gtk.get_minor_version()) >= (2,12)

# Conditionally import glade:
if not use_GtkBuilder_or_Glade():
    #print "Using glade..."
    import Gtk.glade

# Generic wrappers for creating a UI and accessing widgets using either GtkBuilder or Glade:
def create_UI_from_file_GtkBuilder_or_Glade(glade_file,gtkbuilder_file):
    if use_GtkBuilder_or_Glade():
        # Using GtkBuilder:
        ui = Gtk.Builder()
        ui.add_from_file(gtkbuilder_file)
    else:
        # Using Glade:
        ui = Gtk.glade.XML(glade_file)
    return ui
    
def get_widget_from_ui_GtkBuilder_or_Glade(ui,widget_name):
    if use_GtkBuilder_or_Glade():
        # Using GtkBuilder:
        widget_from_ui = ui.get_object(widget_name)
    else:
        # Using Glade:
        widget_from_ui = ui.get_widget(widget_name)
    return widget_from_ui
    
def connect_signals_for_ui_GtkBuilder_or_Glade(ui,signals_dictionary):
    if use_GtkBuilder_or_Glade():
        # Using GtkBuilder:
        ui.connect_signals(signals_dictionary)
    else:
        # Using Glade:
        ui.signal_autoconnect(signals_dictionary)
        
def gtk_gdk_Color_to_string(gtk_gdk_Color):
    # Convert manually a Gdk.Color to a string of the form #rrggbb:
    rr = hex(gtk_gdk_Color.red)[2:]
    rr = '0'*(4-len(rr)) + rr
    gg = hex(gtk_gdk_Color.green)[2:]
    gg = '0'*(4-len(gg)) + gg
    bb = hex(gtk_gdk_Color.blue)[2:]
    bb = '0'*(4-len(bb)) + bb
    return '#' + rr + gg + bb


########################################################
#                From GeditTerminal                    #
########################################################

try:
    gettext.bindtextdomain(GETTEXT_PACKAGE, GP_LOCALEDIR)
    _ = lambda s: gettext.dgettext(GETTEXT_PACKAGE, s);
except:
    _ = lambda s: s


class RGeditTerminal(Gtk.HBox):

    __gsignals__ = {
        "populate-popup": (
            GObject.SignalFlags.RUN_LAST,
            None,
            (GObject.TYPE_OBJECT,)
        )
    }

    def __init__(self,plugin):
        GObject.GObject.__init__(self) #, False, 4)

        self._plugin = plugin

        self.vteTabs = Gtk.Notebook()
        self.vteTabs.set_tab_pos(self._plugin.prefs['R_console_tab_pos'])
        self.vteTabs.set_show_tabs(self._plugin.prefs['R_console_always_show_tabs'])
        self.vteTabs.show()
        
        # A maximum of 3 tabs: keep track of tabs 2 and 3 (1 is always open):
        self._vte2 = None
        self._vte3 = None
        self._vte2_page_number = -1 # _vte2's page index (can be 1 or 2)
        self._vte3_page_number = -1 # _vte3's page index (can be 1 or 2)

        # And their names:
        self.tab_names = ["1","2","3"]

        # And the shell PIDs for each:
        self._vte1_shell_PID = -1;
        self._vte2_shell_PID = -1;
        self._vte3_shell_PID = -1;

        self._vteTab1 = Gtk.HBox()
        self._vte = Vte.Terminal()
        
        self.reconfigure_vte(self._vte,1)
        
        self._vte.set_size(self._vte.get_column_count(), 5)
        self._vte.set_size_request(200, 50)
        self._vte.show()
        self._vteTab1.pack_start(self._vte, True, True, 0)
        self._vteTab1.show()
        self.vteTabs.append_page(self._vteTab1,Gtk.Label(label=self.get_tab_name(1))) 
        self.pack_start(self.vteTabs, True, True, 0)

        self._scrollbar = Gtk.VScrollbar()
        self._scrollbar.set_adjustment(self._vte.adjustment)
        self._scrollbar.show()
        self._vteTab1.pack_start(self._scrollbar, False, False, 0)

        self._vte.connect("key-press-event", self.on_vte_key_press)
        self._vte.connect("key-release-event", self.on_vte_key_release)
        self._vte.connect("button-press-event", self.on_vte_button_press)
        self._vte.connect("popup-menu", self.on_vte_popup_menu)
        self._vte.connect("child-exited", self.vte1_child_exited) 
        #self._vte.connect("commit", self.on_vte_committed)

        self._vte1_shell_PID = self._vte.fork_command_full( Vte.PtyFlags.DEFAULT, None, [shell_command_name], None, GLib.SpawnFlags.CHILD_INHERITS_STDIN | GLib.SpawnFlags.SEARCH_PATH, None, None )[1]
        
        # Is it a special Ctrl+C (used to implement the Ctrl+Q/ESC key in the R console):
        self.special_ctrl_c = False
        
        # The profile's name (one per vte):
        self.profile_name = [None,None,None] # implicitely the default profile

    def run_gedit_helper_script(self,vte,vte_num):
        # Run the gedit helper script
        if self.get_profile_attribute(vte_num,'init-script') == True and self.get_profile_attribute(vte_num,'source-cmd') != None:
            vte.feed_child(self.get_profile_attribute(vte_num,'comment') + _("# Run misc stuff required by rgedit...\n"), -1)
            #vte.feed_child("source(\""+self._plugin.get_data_dir()+"/rgedit-helper-script.r\",echo=FALSE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n")
            vte.feed_child((self.get_profile_attribute(vte_num,'source-cmd') % (self._plugin.get_data_dir()+"/rgedit-helper-script.r")) + "\n", -1)
        
    def show_messages_and_warnings(self,vte,vte_num):
        # Show a warning on the R console:
        if self._plugin.prefs['show_messages_and_warnings'] == False:
            return
        
        message_file = open(self._plugin.get_data_dir()+"/messages_and_warnings.txt","r")
        if not message_file:
            print("Error reading the messages and warnings file\n")
            return
            
        vte.feed_child( _("\n"), -1 )
        vte.feed_child( self.get_profile_attribute(vte_num,'comment') + _("############################ rgedit messages #################################\n"), -1 )
        for line in message_file:
            vte.feed_child( self.get_profile_attribute(vte_num,'comment') + " " + line, -1 );
        vte.feed_child( self.get_profile_attribute(vte_num,'comment') + "################################################################################\n\n", -1 )
        
    def vte1_child_exited(self,event):
        self._vte1_shell_PID = self._vte.fork_command_full( Vte.PtyFlags.DEFAULT, None, [shell_command_name], None, GLib.SpawnFlags.CHILD_INHERITS_STDIN | GLib.SpawnFlags.SEARCH_PATH, None, None )[1]

    def on_vte_committed(self,vterm,text,textlen):
        #print text, textlen
        return true

    def do_grab_focus(self):
        self._vte.grab_focus()

    def reconfigure_vte(self,_vteN,tab_number):
        # Fonts
        font_name = self._plugin.prefs['font_name']
        try:
            _vteN.set_font(Pango.FontDescription(font_name))
        except:
            pass

        # colors
        _vteN.ensure_style()
        style = _vteN.get_style()

        if self._plugin.prefs['foreground'+str(tab_number)] == None:
            fg = style.text[Gtk.StateType.NORMAL]
        else:
            fg = Gdk.color_parse(self._plugin.prefs['foreground'+str(tab_number)])

        if self._plugin.prefs['background'+str(tab_number)] == None:
            bg = style.base[Gtk.StateType.NORMAL]
        else:
            bg = Gdk.color_parse(self._plugin.prefs['background'+str(tab_number)])

        palette = []
        if isinstance(fg,tuple):
            fg = fg[1]
        if isinstance(bg,tuple):
            bg = bg[1]
        _vteN.set_colors(fg, bg, palette)

        # cursor blink
        try:
            if self._plugin.prefs['cursor_blink'] == "system":
                blink = vte.CURSOR_BLINK_SYSTEM
            elif self._plugin.prefs['cursor_blink'] == "on":
                blink = vte.CURSOR_BLINK_ON
            elif self._plugin.prefs['cursor_blink'] == "off":
                blink = vte.CURSOR_BLINK_OFF
            else:
                blink = vte.CURSOR_BLINK_SYSTEM
            _vteN.set_cursor_blink_mode(blink)
        except:
            pass

        # cursor shape
        try:
            if self._plugin.prefs['cursor_shape'] == "block":
                shape = vte.CURSOR_SHAPE_BLOCK
            elif self._plugin.prefs['cursor_shape'] == "ibeam":
                shape = vte.CURSOR_SHAPE_IBEAM
            elif self._plugin.prefs['cursor_shape'] == "underline":
                shape = vte.CURSOR_SHAPE_UNDERLINE
            else:
                shape = vte.CURSOR_SHAPE_BLOCK
            _vteN.set_cursor_shape(shape)
        except:
            pass

        _vteN.set_audible_bell(not self._plugin.prefs['audible_bell'])

        _vteN.set_scrollback_lines(self._plugin.prefs['scrollback_lines'])

        _vteN.set_allow_bold(self._plugin.prefs['allow_bold'])

        _vteN.set_scroll_on_keystroke(self._plugin.prefs['scroll_on_keystroke'])

        _vteN.set_scroll_on_output(self._plugin.prefs['scroll_on_output'])

        _vteN.set_word_chars(self._plugin.prefs['word_chars'])

        _vteN.set_emulation(self._plugin.prefs['emulation'])
        _vteN.set_visible_bell(self._plugin.prefs['visible_bell'])

    def on_vte_key_press(self, term, event):
        if event.get_state() is None:
            return False
        
        modifiers = event.get_state() & Gtk.accelerator_get_default_mod_mask()
        key_name = Gdk.keyval_name(event.keyval)
        if key_name in ("v", "V") and modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Ctrl+V detected:
            self.paste_clipboard()
            return True
        #if key_name in ("c", "C") and modifiers == Gdk.ModifierType.CONTROL_MASK and not self.special_ctrl_c and self._plugin.prefs['R_console_Ctrl_C_4_copy']:
        #    # Ctrl+C detected:
        #    self.copy_clipboard()
        #    return True
        if key_name in ("x", "X") and modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Ctrl+X detected:
            self.copy_clipboard()
            return True
        #if (key_name in ("q", "Q") and modifiers == Gdk.ModifierType.CONTROL_MASK and self._plugin.prefs['R_console_Ctrl_Q_break']) or (key_name == "Escape" and self._plugin.prefs['R_console_Escape_break']):
        #    # Ctrl+Q or ESC detected: simulate a Ctrl+C instead:
        #    self.break_R_computation(event)
        #    return True
        elif key_name == "Tab" and modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Ctrl+Tab detected:
            current_view = self._window.get_active_view()
            if current_view != None:
                current_view.grab_focus()
            return True
        elif key_name in ("k", "K") and modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Copy the current line to the clipboard:
            self.copy_last_line_to_clipboard()
            return True
        elif key_name in ("k", "K") and modifiers == (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK):
            # Copy the current line to the clipboard and paste it into gedit:
            self.copy_last_line_to_clipboard()
            return True
        return False
        
    def on_vte_key_release(self, term, event):
        modifiers = event.get_state() & Gtk.accelerator_get_default_mod_mask()
        key_name = Gdk.keyval_name(event.keyval)
        if key_name in ("k", "K") and modifiers == (Gdk.EventMask.ModifierType | Gdk.EventMask.ModifierType):
            # Paste the previously copied line into gedit:
            self.paste_last_line_from_clipboard_to_gedit()
            return True
        return False
        
    def break_R_computation(self,original_event):
        # Send a "hidden" Ctrl+C to the R process:
        vte = None
        if self.vteTabs.get_current_page() == 0:
            vte= self._vte
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            vte= self._vte2
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            vte= self._vte3
        else:
            print( _("Unknown R tab!") )
            
        event = Gdk.Event(Gdk.EventType.KEY_PRESS)
        event.window = self.get_window() #vte.get_window() #vte.window
        event.send_event = True
        event.time = 0
        event.state = Gdk.ModifierType.CONTROL_MASK
        event.keyval = int(Gdk.keyval_from_name('c'))
        #event.string = "Ctrl+C"
        event.hardware_keycode = 0
        event.group = 0
        self.special_ctrl_c = True
        #vte.emit("key-press-event", event)
        #event.put();
        #while Gtk.events_pending():
        #    Gtk.main_iteration()
        #self.emit("key-press-event", event)
        #vte.event(event)
        #Gtk.main_do_event(event)
        self.special_ctrl_c = False

    def on_vte_button_press(self, term, event):
        if event.button == 3:
            self._vte.grab_focus()
            self.do_popup(event)
            return True

    def on_vte_popup_menu(self, term):
        self.do_popup()

    def create_popup_menu(self):
        menu = Gtk.Menu()

        item = Gtk.ImageMenuItem()
        item.set_label(Gtk.STOCK_COPY)
        item.set_use_stock(True)
        item.connect("activate", lambda menu_item: self.copy_clipboard())
        if self.vteTabs.get_current_page() == 0:
            item.set_sensitive(self._vte.get_has_selection())
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            item.set_sensitive(self._vte2.get_has_selection())
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            item.set_sensitive(self._vte3.get_has_selection())
        else:
            print( _("Unknown R tab!") )
        menu.append(item)

        item = Gtk.ImageMenuItem()
        item.set_label(Gtk.STOCK_PASTE)
        item.set_use_stock(True)
        item.connect("activate", lambda menu_item: self.paste_clipboard())
        menu.append(item)

        item = Gtk.SeparatorMenuItem()
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Change tab name"))
        item.connect("activate", lambda menu_item: self.change_tab_name())
        menu.append(item)

        item = Gtk.CheckMenuItem()
        item.set_label(_("Always show tabs?"))
        item.set_active(self._plugin.prefs['R_console_always_show_tabs'])
        item.connect("activate", lambda menu_item: self.always_show_tabs())
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Show tabs on"))
        menu.append(item)
        show_tabs_submenu = Gtk.Menu()
        tabs_top = Gtk.CheckMenuItem()
        tabs_top.set_label(_("top"))
        tabs_top.set_draw_as_radio(True)
        tabs_top.set_active(self._plugin.prefs['R_console_tab_pos'] == Gtk.PositionType.TOP)
        tabs_top.connect("activate", lambda menu_item: self.show_tabs_top())
        tabs_left = Gtk.CheckMenuItem()
        tabs_left.set_label(_("left"))
        tabs_left.set_draw_as_radio(True)
        tabs_left.set_active(self._plugin.prefs['R_console_tab_pos'] == Gtk.PositionType.LEFT)
        tabs_left.connect("activate", lambda menu_item: self.show_tabs_left())
        tabs_right = Gtk.CheckMenuItem()
        tabs_right.set_label(_("right"))
        tabs_right.set_draw_as_radio(True)
        tabs_right.set_active(self._plugin.prefs['R_console_tab_pos'] == Gtk.PositionType.RIGHT)
        tabs_right.connect("activate", lambda menu_item: self.show_tabs_right())
        tabs_bottom = Gtk.CheckMenuItem()
        tabs_bottom.set_label(_("bottom"))
        tabs_bottom.set_draw_as_radio(True)
        tabs_bottom.set_active(self._plugin.prefs['R_console_tab_pos'] == Gtk.PositionType.BOTTOM)
        tabs_bottom.connect("activate", lambda menu_item: self.show_tabs_bottom())
        show_tabs_submenu.attach(tabs_top,0,1,0,1)
        show_tabs_submenu.attach(tabs_left,0,1,1,2)
        show_tabs_submenu.attach(tabs_right,0,1,2,3)
        show_tabs_submenu.attach(tabs_bottom,0,1,3,4)
        item.set_submenu(show_tabs_submenu)

        item = Gtk.MenuItem()
        item.set_label(_("Close tab"))
        item.connect("activate", lambda menu_item: self.close_tab())
        if self.vteTabs.get_current_page() == 0:
            item.set_sensitive(False)
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Start R"))
        item.connect("activate", lambda menu_item: self.start_R())
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Restart R"))
        item.connect("activate", lambda menu_item: self.restart_R())
        menu.append(item)
        
        item = Gtk.SeparatorMenuItem()
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Change R's working folder"))
        item.connect("activate", lambda menu_item: self.change_R_working_dir())
        menu.append(item)

        item = Gtk.MenuItem()
        item.set_label(_("Use document's folder"))
        item.connect("activate", lambda menu_item: self.change_R_working_dir_to_the_document())
        menu.append(item)

        item = Gtk.ImageMenuItem()
        item.set_label(_("Load R workspace"))
        item_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/load_workspace.png" , 24, 24)
        item_icon.set_from_pixbuf(pixbuf)
        item_icon.show()
        item.set_image(item_icon)
        item.connect("activate", lambda menu_item: self.on_R_load_workspace())
        menu.append(item)

        item = Gtk.ImageMenuItem()
        item.set_label(_("Save R workspace"))
        item_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/save_workspace.png" , 24, 24)
        item_icon.set_from_pixbuf(pixbuf)
        item_icon.show()
        item.set_image(item_icon)
        item.connect("activate", lambda menu_item: self.on_R_save_workspace())
        menu.append(item)

        menu.attach_to_widget(self,None)
        self.emit("populate-popup", menu)
        menu.show_all()
        return menu

    def do_popup(self, event = None):
        menu = self.create_popup_menu()

        if event is not None:
            menu.popup(None, None, None, None, event.button, event.time)
        else:
            menu.popup(None, None, None,
                       #lambda m: Gedit.utils.menu_position_under_widget(m, self),
                       None, 0, Gtk.get_current_event_time())
            menu.select_first(False)

    def copy_clipboard(self):
        if self.vteTabs.get_current_page() == 0:
            self._vte.copy_clipboard()
            self._vte.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            self._vte2.copy_clipboard()
            self._vte2.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            self._vte3.copy_clipboard()
            self._vte3.grab_focus()
        else:
            print( _("Unknown R tab!") )

    def paste_clipboard(self):
        if self.vteTabs.get_current_page() == 0:
            self._vte.paste_clipboard()
            self._vte.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            self._vte2.paste_clipboard()
            self._vte2.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            self._vte3.paste_clipboard()
            self._vte3.grab_focus()
        else:
            print( _("Unknown R tab!") )
            
    def copy_last_line_to_clipboard(self):
        # Copy the current line to the clipboard by invoking the .rgedit.lastline2clipboard function from the helper script:
        clipboard_command = '.rgedit.lastline2clipboard()\n'
        if self.vteTabs.get_current_page() == 0:
            self._vte.feed_child(clipboard_command,-1)
            self._vte.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            self._vte2.feed_child(clipboard_command,-1)
            self._vte2.grab_focus()
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            self._vte3.feed_child(clipboard_command,-1)
            self._vte3.grab_focus()
        else:
            print( _("Unknown R tab!") )
            
    def paste_last_line_from_clipboard_to_gedit(self):
        # Paste the previously copied line into gedit:
        app  = gedit.app_get_default()
        win  = app.get_active_window()
        doc  = win.get_active_document()
        #doc = self._plugin.get_active_window().get_active_document()
        if not doc:
            return
        #doc.insert_at_cursor("KUK\n");
        doc.paste_clipboard(Gtk.clipboard_get(selection="CLIPBOARD"),None,True)
        #fake_clipboard = Gtk.Clipboard(Gdk.Display.get_default(),"_rgedit_fake_clipboard")
        #fake_clipboard.set_text("\n")
        #doc.paste_clipboard(fake_clipboard,None,True)
 
    def change_directory(self, path):
        path = path.replace('\\', '\\\\').replace('"', '\\"')
        self._vte.feed_child('cd "%s"\n' % path,-1)
        self._vte.grab_focus()

    def send_command(self,string):
        if self.vteTabs.get_current_page() == 0:
            self._vte.feed_child(string,-1)
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            self._vte2.feed_child(string,-1)
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            self._vte3.feed_child(string,-1)
        else:
            print( _("Unknown R tab!") )
            print( self.vteTabs.get_current_page() )
            print( self._vte2_page_number )
            print( self._vte3_page_number )

    def set_profile(self,vte=1,profile=None):
        self.profile_name[vte-1] = profile

    def get_profile(self,vte=1):
        return self.profile_name[vte-1]

    def get_profile_attribute(self,vte=1,key='name'):
        return self._plugin.get_profile_attribute(self.profile_name[vte-1], key)

    def create_new_R_tab(self,profile=None):
        if self._vte2 == None:
           # _vte2 is free:
           self._vteTab2 = Gtk.HBox()
           self._vte2 = Vte.Terminal()
           self.reconfigure_vte(self._vte2,2)
           self._vte2.set_size(self._vte2.get_column_count(), 5)
           self._vte2.set_size_request(200, 50)
           self._vte2.show()
           self._vteTab2.pack_start(self._vte2, True, True, 0)
           self._vteTab2.show()
           self.vteTabs.append_page(self._vteTab2,Gtk.Label(label=self.get_tab_name(2))) 
           self.vteTabs.set_show_tabs(True)
           self._vte2_page_number = self.vteTabs.get_n_pages()-1

           self._scrollbar2 = Gtk.VScrollbar()
           self._scrollbar2.set_adjustment(self._vte2.adjustment)
           self._scrollbar2.show()
           self._vteTab2.pack_start(self._scrollbar2, False, False, 0)

           self._vte2.connect("key-press-event", self.on_vte_key_press)
           self._vte2.connect("button-press-event", self.on_vte_button_press)
           self._vte2.connect("popup-menu", self.on_vte_popup_menu)
           self._vte2.connect("child-exited", self.on_vte2_exited)

           self._vte2_shell_PID = self._vte2.fork_command_full( Vte.PtyFlags.DEFAULT, None, [shell_command_name], None, GLib.SpawnFlags.CHILD_INHERITS_STDIN | GLib.SpawnFlags.SEARCH_PATH, None, None )[1]

           self.set_profile(2,profile)
           self._vte2.feed_child(self.get_profile_attribute(2,'cmd')+"\n", -1) # open R
           self.run_gedit_helper_script(self._vte2,2)
           if self.get_profile_attribute(2,'help-type') == 'HTML':
               self._vte2.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
           elif self.get_profile_attribute(2,'help-type') == 'Text':
               self._vte2.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
           elif self.get_profile_attribute(2,'help-type') == 'Custom':
               self._vte2.feed_child(str(self.get_profile_attribute(2,'help-custom-command'))+"\n", -1) # send the custom command
           else: # 'Default' & others
               pass # leave the system default
           if self._plugin.prefs['prompt_color2'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
               self._vte2.feed_child(self._plugin.prompt_string(2,self.get_tab_name(2),profile), -1) # and set the prompt accordingly...
           if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(2,'source-cmd') != None:
               #self._vte2.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n", -1) # run the autostart script...
               self._vte2.feed_child((self.get_profile_attribute(2,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
           if self._plugin.prefs['use_current_document_directory']:
               self.change_vte_R_working_dir_to_the_document(self._vte2,2)
           self.show_messages_and_warnings(self._vte2,2)

           if self._vte3 != None:
               # All 3 tabs are active:
               manager = self._window.get_ui_manager()
               #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(False)
               self._plugin.RCtrlNewTab_toolarrow.set_sensitive(False)


        elif self._vte3 == None:
           # _vte3 is free:
           self._vteTab3 = Gtk.HBox()
           self._vte3 = Vte.Terminal()
           self.reconfigure_vte(self._vte3,3)
           self._vte3.set_size(self._vte3.get_column_count(), 5)
           self._vte3.set_size_request(200, 50)
           self._vte3.show()
           self._vteTab3.pack_start(self._vte3, True, True, 0)
           self._vteTab3.show()
           self.vteTabs.append_page(self._vteTab3,Gtk.Label(label=self.get_tab_name(3))) 
           self.vteTabs.set_show_tabs(True)
           self._vte3_page_number = self.vteTabs.get_n_pages()-1

           self._scrollbar3 = Gtk.VScrollbar()
           self._scrollbar3.set_adjustment(self._vte3.adjustment)
           self._scrollbar3.show()
           self._vteTab3.pack_start(self._scrollbar3, False, False, 0)

           self._vte3.connect("key-press-event", self.on_vte_key_press)
           self._vte3.connect("button-press-event", self.on_vte_button_press)
           self._vte3.connect("popup-menu", self.on_vte_popup_menu)
           self._vte3.connect("child-exited", self.on_vte3_exited)

           self._vte3_shell_PID = self._vte3.fork_command_full( Vte.PtyFlags.DEFAULT, None, [shell_command_name], None, GLib.SpawnFlags.CHILD_INHERITS_STDIN | GLib.SpawnFlags.SEARCH_PATH, None, None )[1]

           self.set_profile(3,profile)
           self._vte3.feed_child(self.get_profile_attribute(3,'cmd')+"\n", -1) # open R
           self.run_gedit_helper_script(self._vte3,3)
           if self.get_profile_attribute(3,'help-type') == 'HTML':
               self._vte3.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
           elif self.get_profile_attribute(3,'help-type') == 'Text':
               self._vte3.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
           elif self.get_profile_attribute(3,'help-type') == 'Custom':
               self._vte3.feed_child(str(self.get_profile_attribute(3,'help-custom-command'))+"\n", -1) # send the custom command
           else: # 'Default' & others
               pass # leave the system default
           if self._plugin.prefs['prompt_color3'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
               self._vte3.feed_child(self._plugin.prompt_string(3,self.get_tab_name(3),profile), -1) # and set the prompt accordingly...
           if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(3,'source-cmd') != None:
               #self._vte3.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
               self._vte3.feed_child((self.get_profile_attribute(3,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
           if self._plugin.prefs['use_current_document_directory']:
               self.change_vte_R_working_dir_to_the_document(self._vte3,3)
           self.show_messages_and_warnings(self._vte3,3)

           if self._vte2 != None:
               # All 3 tabs are active:
               manager = self._window.get_ui_manager()
               #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(False)
               self._plugin.RCtrlNewTab_toolarrow.set_sensitive(False)

    def kill_shell_process(self,PID):
        # Kill the shell process with the given PID
        #return # Not really working...
        if PID > 0:
            print("Kill " + str(PID))
            os.kill(PID,signal.SIGHUP)

    def on_vte2_exited(self,event):
        # destroy the _vte2:
        self.vteTabs.remove_page(self.vteTabs.get_current_page())
        if self.vteTabs.get_n_pages() == 1:
            self.vteTabs.set_show_tabs(False)
        self._vte2 = None
        self._vte2_page_number = -1
        manager = self._window.get_ui_manager()
        #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(True)
        self._plugin.RCtrlNewTab_toolarrow.set_sensitive(True)
        #self.kill_shell_process(self._vte2_shell_PID)
        #self._vte2_shell_PID = -1

    def on_vte3_exited(self,event):
        # destroy the _vte3:
        self.vteTabs.remove_page(self.vteTabs.get_current_page())
        if self.vteTabs.get_n_pages() == 1:
            self.vteTabs.set_show_tabs(False)
        self._vte3 = None
        self._vte3_page_number = -1
        manager = self._window.get_ui_manager()
        #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(True)
        self._plugin.RCtrlNewTab_toolarrow.set_sensitive(True)
        #self.kill_shell_process(self._vte3_shell_PID)
        #self._vte3_shell_PID = -1

    def change_tab_name(self):
        tab_number = -1
        active_vte = None
        if self.vteTabs.get_current_page() == 0:
            tab_number = 1
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            tab_number = self._vte2_page_number+1
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            tab_number = self._vte3_page_number+1
        else:
            print( _("Unknown R tab!") )

        ChangeTabNameDialog_ui = create_UI_from_file_GtkBuilder_or_Glade(self._plugin.get_data_dir()+"/ChangeTabNameDialog.glade",self._plugin.get_data_dir()+"/ChangeTabNameDialog.ui")

        # Init the controls accordingly with the current options:
        label_tab_number = get_widget_from_ui_GtkBuilder_or_Glade(ChangeTabNameDialog_ui,"TabNumber")
        label_tab_number.set_text(str(tab_number))

        edit_tab_name = get_widget_from_ui_GtkBuilder_or_Glade(ChangeTabNameDialog_ui,"TabName")
        edit_tab_name.set_text(self.tab_names[tab_number-1])

        dialog = get_widget_from_ui_GtkBuilder_or_Glade(ChangeTabNameDialog_ui,"ChangeTabNameDialog")

        #Create our dictionay and connect it
        response = dialog.run()
        if response == -2: #OK button
            self.tab_names[tab_number-1] = edit_tab_name.get_text()
            self.vteTabs.set_tab_label(self.vteTabs.get_nth_page(tab_number-1),Gtk.Label(label=self.get_tab_name(tab_number)))
            vte1_console_changed = False
            vte2_console_changed = False
            vte3_console_changed = False
            vte1_R_options_changed = False
            vte2_R_options_changed = False
            vte3_R_options_changed = False
            if self._plugin.prefs['tab_name_in_prompt'] == True:
                vte1_R_options_changed = (tab_number == 1)
                vte2_R_options_changed = (tab_number == self._vte2_page_number+1)
                vte3_R_options_changed = (tab_number == self._vte3_page_number+1)
            self.reconfigure_vtes(vte1_console_changed,vte2_console_changed,vte3_console_changed,vte1_R_options_changed,vte2_R_options_changed,vte3_R_options_changed)
        dialog.destroy()


    def always_show_tabs(self):
        # Toggle the showing of R tabs:
        self._plugin.prefs['R_console_always_show_tabs'] = not self._plugin.prefs['R_console_always_show_tabs']
        self.vteTabs.set_show_tabs(self._plugin.prefs['R_console_always_show_tabs'])


    def show_tabs_right(self):
        # Toggle the showing of R tabs to the right:
        self._plugin.prefs['R_console_tab_pos'] = int(Gtk.PositionType.RIGHT)
        self.vteTabs.set_tab_pos(self._plugin.prefs['R_console_tab_pos'])


    def show_tabs_left(self):
        # Toggle the showing of R tabs to the left:
        self._plugin.prefs['R_console_tab_pos'] = int(Gtk.PositionType.LEFT)
        self.vteTabs.set_tab_pos(self._plugin.prefs['R_console_tab_pos'])


    def show_tabs_top(self):
        # Toggle the showing of R tabs to the top:
        self._plugin.prefs['R_console_tab_pos'] = int(Gtk.PositionType.TOP)
        self.vteTabs.set_tab_pos(self._plugin.prefs['R_console_tab_pos'])


    def show_tabs_bottom(self):
        # Toggle the showing of R tabs to the bottom:
        self._plugin.prefs['R_console_tab_pos'] = int(Gtk.PositionType.BOTTOM)
        self.vteTabs.set_tab_pos(self._plugin.prefs['R_console_tab_pos'])


    def reconfigure_vtes(self,vte1_console_changed,vte2_console_changed,vte3_console_changed,vte1_R_options_changed,vte2_R_options_changed,vte3_R_options_changed):
        if vte1_console_changed == True:
            self.reconfigure_vte(self._vte,1)
        if vte1_R_options_changed == True:
            if self.get_profile_attribute(1,'help-type') == 'HTML':
               self._vte.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
            elif self.get_profile_attribute(1,'help-type') == 'Text':
               self._vte.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
            elif self.get_profile_attribute(1,'help-type') == 'Custom':
               self._vte.feed_child(str(self.get_profile_attribute(1,'help-custom-command'))+"\n", -1) # send the custom command
            else: # 'Default' & others
               pass # leave the system default
            if self._plugin.prefs['prompt_color1'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
               self._vte.feed_child(self._plugin.prompt_string(1,self.get_tab_name(1),self.get_profile(1)), -1) # and set the prompt accordingly...

        if self._vte2 != None:
            if vte2_console_changed == True:
               self.reconfigure_vte(self._vte2,2)
            if vte2_R_options_changed == True:
               if self.get_profile_attribute(2,'help-type') == 'HTML':
                   self._vte2.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
               elif self.get_profile_attribute(2,'help-type') == 'Text':
                   self._vte2.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
               elif self.get_profile_attribute(2,'help-type') == 'Custom':
                   self._vte2.feed_child(str(self.get_profile_attribute(2,'help-custom-command'))+"\n", -1) # send the custom command
               else: # 'Default' & others
                   pass # leave the system default
               if self._plugin.prefs['prompt_color2'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte2.feed_child(self._plugin.prompt_string(2,self.get_tab_name(2),self.get_profile(2)), -1) # and set the prompt accordingly...

        if self._vte3 != None:
            if vte3_console_changed == True:
               self.reconfigure_vte(self._vte3,3)
            if vte3_R_options_changed == True:
               if self.get_profile_attribute(3,'help-type') == 'HTML':
                   self._vte3.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
               elif self.get_profile_attribute(3,'help-type') == 'Text':
                   self._vte3.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
               elif self.get_profile_attribute(3,'help-type') == 'Custom':
                   self._vte3.feed_child(str(self.get_profile_attribute(3,'help-custom-command'))+"\n", -1) # send the custom command
               else: # 'Default' & others
                   pass # leave the system default
               if self._plugin.prefs['prompt_color3'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte3.feed_child(self._plugin.prompt_string(3,self.get_tab_name(3),self.get_profile(3)), -1) # and set the prompt accordingly...

    def get_tab_name(self,tab_number):
        # Return the tab name:
        return self.tab_names[tab_number-1]

    def close_tab(self):
        if self.vteTabs.get_current_page() == self._vte2_page_number:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, "Are you sure you want to close this tab?" )
            response = question_dialog.run()
            question_dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.kill_shell_process(self._vte2_shell_PID)
                self._vte2_shell_PID = -1
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, "Are you sure you want to close this tab?" )
            response = question_dialog.run()
            question_dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.kill_shell_process(self._vte3_shell_PID)
                self._vte3_shell_PID = -1

    def restart_R(self):
        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, "Are you sure you want to restart R?\nYou must be at the old R session prompt for this..." )
        response = question_dialog.run()
        question_dialog.destroy()

        if response == Gtk.ResponseType.YES:
            if self.vteTabs.get_current_page() == 0:
                self._vte.feed_child(self.get_profile_attribute(1,'quit-cmd')+"\n", -1)
                self._vte.feed_child(self.get_profile_attribute(1,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte,1)
                if self.get_profile_attribute(1,'help-type') == 'HTML':
                   self._vte.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(1,'help-type') == 'Text':
                   self._vte.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(1,'help-type') == 'Custom':
                   self._vte.feed_child(str(self.get_profile_attribute(1,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color1'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte.feed_child(self._plugin.prompt_string(1,self.get_tab_name(1),self.get_profile(1)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(1,'source-cmd') != None:
                   #self._vte.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
                   self._vte.feed_child((self.get_profile_attribute(1,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte,1)
                self.show_messages_and_warnings(self._vte,1)
            elif self.vteTabs.get_current_page() == self._vte2_page_number:
                self._vte2.feed_child(self.get_profile_attribute(2,'quit-cmd')+"\n", -1)
                self._vte2.feed_child(self.get_profile_attribute(2,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte2,2)
                if self.get_profile_attribute(2,'help-type') == 'HTML':
                   self._vte2.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(2,'help-type') == 'Text':
                   self._vte2.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(2,'help-type') == 'Custom':
                   self._vte2.feed_child(str(self.get_profile_attribute(2,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color2'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte2.feed_child(self._plugin.prompt_string(2,self.get_tab_name(2),self.get_profile(2)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script']:
                   self._vte2.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n", -1) # run the autostart script...
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte2,2)
                self.show_messages_and_warnings(self._vte2,2)
            elif self.vteTabs.get_current_page() == self._vte3_page_number:
                self._vte3.feed_child(self.get_profile_attribute(3,'quit-cmd')+"\n", -1)
                self._vte3.feed_child(self.get_profile_attribute(3,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte3,3)
                if self.get_profile_attribute(3,'help-type') == 'HTML':
                   self._vte3.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(3,'help-type') == 'Text':
                   self._vte3.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(3,'help-type') == 'Custom':
                   self._vte3.feed_child(str(self.get_profile_attribute(3,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color3'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte3.feed_child(self._plugin.prompt_string(3,self.get_tab_name(3),self.get_profile(3)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(3,'source-cmd') != None:
                   #self._vte3.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
                   self._vte3.feed_child((self.get_profile_attribute(3,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte3,3)
                self.show_messages_and_warnings(self._vte3,3)

    def start_R(self):
        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, "Are you sure you want to start a new R session?\nYou must be at the shell prompt for this..." )
        response = question_dialog.run()
        question_dialog.destroy()

        if response == Gtk.ResponseType.YES:
            if self.vteTabs.get_current_page() == 0:
                self._vte.feed_child(self.get_profile_attribute(1,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte,1)
                if self.get_profile_attribute(1,'help-type') == 'HTML':
                   self._vte.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(1,'help-type') == 'Text':
                   self._vte.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(1,'help-type') == 'Custom':
                   self._vte1.feed_child(str(self.get_profile_attribute(1,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color1'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte.feed_child(self._plugin.prompt_string(1,self.get_tab_name(1),self.get_profile(1)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(1,'source-cmd') != None:
                   #self._vte.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
                   self._vte.feed_child((self.get_profile_attribute(1,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte,1)
                self.show_messages_and_warnings(self._vte,1)
            elif self.vteTabs.get_current_page() == self._vte2_page_number:
                self._vte2.feed_child(self.get_profile_attribute(2,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte2,2)
                if self.get_profile_attribute(2,'help-type') == 'HTML':
                   self._vte2.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(2,'help-type') == 'Text':
                   self._vte2.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(2,'help-type') == 'Custom':
                   self._vte2.feed_child(str(self.get_profile_attribute(2,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color2'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte2.feed_child(self._plugin.prompt_string(2,self.get_tab_name(2),self.get_profile(2)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(2,'source-cmd') != None:
                   #self._vte2.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
                   self._vte2.feed_child((self.get_profile_attribute(2,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte2,2)
                self.show_messages_and_warnings(self._vte2,2)
            elif self.vteTabs.get_current_page() == self._vte3_page_number:
                self._vte3.feed_child(self.get_profile_attribute(3,'cmd')+"\n", -1) # open R
                self.run_gedit_helper_script(self._vte3,3)
                if self.get_profile_attribute(3,'help-type') == 'HTML':
                   self._vte3.feed_child("options(htmlhelp = TRUE,help_type='html')\n", -1) # and init the HTML help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(3,'help-type') == 'Text':
                   self._vte3.feed_child("options(htmlhelp = FALSE,help_type='text')\n", -1) # and init the TEXT help system both for pre and post R 2.10.0...
                elif self.get_profile_attribute(3,'help-type') == 'Custom':
                   self._vte3.feed_child(str(self.get_profile_attribute(3,'help-custom-command'))+"\n", -1) # send the custom command
                else: # 'Default' & others
                   pass # leave the system default
                if self._plugin.prefs['prompt_color3'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
                   self._vte3.feed_child(self._plugin.prompt_string(3,self.get_tab_name(3),self.get_profile(3)), -1) # and set the prompt accordingly...
                if self._plugin.prefs['autostart_R_script'] and self.get_profile_attribute(3,'source-cmd') != None:
                   #self._vte3.feed_child("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
                   self._vte3.feed_child((self.get_profile_attribute(3,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n", -1)
                if self._plugin.prefs['use_current_document_directory']:
                   self.change_vte_R_working_dir_to_the_document(self._vte3,3)
                self.show_messages_and_warnings(self._vte3,3)

    def change_R_working_dir(self):
        folder_dialog = Gtk.FileChooserDialog(_("Choose R's working folder"), None, Gtk.FileChooserAction.SELECT_FOLDER, (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        response = folder_dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            folder_name = folder_dialog.get_filename()
            # Assume R is working a ready:
            if self.vteTabs.get_current_page() == 0:
                if not self.get_profile_attribute(1,'setwd') is None:
                    self._vte.feed_child((self.get_profile_attribute(1,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
            elif self.vteTabs.get_current_page() == self._vte2_page_number:
                if not self.get_profile_attribute(2,'setwd') is None:
                    self._vte2.feed_child((self.get_profile_attribute(2,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
            elif self.vteTabs.get_current_page() == self._vte3_page_number:
                if not self.get_profile_attribute(3,'setwd') is None:
                    self._vte3.feed_child((self.get_profile_attribute(3,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
            else:
                print( _("Unknown R tab!") )
        folder_dialog.destroy()
        
    def change_vte_R_working_dir_to_the_document(self,vte,vte_num):
        # Change the given vte's R's working folder to the current document's:
        if not self._plugin.window:
            #print("Cannot get current window")
            return
            
        doc = self._plugin.window.get_active_document()
        if not doc:
            return
            
        folder_name = doc.get_uri_for_display()
        if not folder_name:
            return
        folder_name = os.path.dirname(folder_name)
            
        # Assume R is working and ready:
        if not self.get_profile_attribute(vte_num,'setwd') is None:
            vte.feed_child((self.get_profile_attribute(vte_num,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
        
    def change_R_working_dir_to_the_document(self):
         # Change R's working folder to the current document's:
        if not self._plugin.window:
            #print("Cannot get current window")
            return
            
        doc = self._plugin.window.get_active_document()
        if not doc:
            return
            
        folder_name = doc.get_uri_for_display()
        if not folder_name:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("Current document has not been saved: cannot change R's working folder to this...") )
            response = question_dialog.run()
            question_dialog.destroy()
            return
        folder_name = os.path.dirname(folder_name)
            
        # Assume R is working and ready:
        if self.vteTabs.get_current_page() == 0:
            if not self.get_profile_attribute(1,'setwd') is None:
                self._vte.feed_child((self.get_profile_attribute(1,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
        elif self.vteTabs.get_current_page() == self._vte2_page_number:
            if not self.get_profile_attribute(2,'setwd') is None:
                self._vte2.feed_child((self.get_profile_attribute(2,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
        elif self.vteTabs.get_current_page() == self._vte3_page_number:
            if not self.get_profile_attribute(3,'setwd') is None:
                self._vte3.feed_child((self.get_profile_attribute(3,'setwd') % ('"'+folder_name+'"')) + "\n", -1)
        else:
            print( "Unknown R tab!" )
        
    def on_R_load_workspace(self):
        file_dialog = Gtk.FileChooserDialog(_("Open R Workspace"), None, Gtk.FileChooserAction.OPEN, (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))

        doc = self._plugin.window.get_active_document()
        if doc:
            folder_name = doc.get_uri_for_display()
            if folder_name:
                folder_name = os.path.dirname(folder_name)
            else:
                folder_name = None
        else:
            folder_name = None

        if folder_name:
            file_dialog.set_current_folder(folder_name)
        
        filter = Gtk.FileFilter()
        filter.set_name("R worksapce")
        filter.add_pattern("*.RData")
        filter.add_pattern("*.R")
        file_dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        file_dialog.add_filter(filter)

        response = file_dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            file_name = file_dialog.get_filename()
            do_send_to_R( "load( \""+file_name+"\", .GlobalEnv )\n", self, False, self._plugin.prefs['max_lines_as_text'] )
        file_dialog.destroy()

    def on_R_save_workspace(self):
        file_dialog = Gtk.FileChooserDialog(_("Save R Workspace"), None, Gtk.FileChooserAction.SAVE, (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        
        doc = self._plugin.window.get_active_document()
        if doc:
            folder_name = doc.get_uri_for_display()
            if folder_name:
                folder_name = os.path.dirname(folder_name)
            else:
                folder_name = None
        else:
            folder_name = None

        if folder_name:
            file_dialog.set_current_folder(folder_name)
        
        filter = Gtk.FileFilter()
        filter.set_name("R worksapce")
        filter.add_pattern("*.RData")
        filter.add_pattern("*.R")
        file_dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        file_dialog.add_filter(filter)

        file_dialog.set_current_name(".RData")
        
        file_dialog.set_do_overwrite_confirmation( True )

        response = file_dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            file_name = file_dialog.get_filename()
            do_send_to_R( "save( list = ls(all=TRUE), file = \""+file_name+"\" )\n", self, False, self._plugin.prefs['max_lines_as_text'] )
        file_dialog.destroy()


########################################################################
#                   The Panel with the R file structure
########################################################################

# This class displays the panel tab:
class RStructurePanel:
    
    def __init__(self,rctrlwindowhelper):
        # Init:
        self._rctrlwindowhelper = rctrlwindowhelper
        self._window = rctrlwindowhelper._window
        self._plugin = rctrlwindowhelper._plugin
        
        # Get the side panel :
        self.side_panel = self._window.get_side_panel()
        
        # The support widget is a vbox:
        self.R_struct_base_vbox = Gtk.VBox()
        self.R_struct_base_vbox.show()
        item_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/R_structure.png" , 16, 16)
        item_icon.set_from_pixbuf(pixbuf)
        item_icon.show()
        self.side_panel.add_item( self.R_struct_base_vbox, _("R structure"), "R structure", item_icon )
        
        # Which contains an info line and a clickable (read-only) list
        self.force_refresh = Gtk.Button(stock="gtk-refresh")
        self.scrolled_window = Gtk.ScrolledWindow()
        self.buttons_hbox = Gtk.HBox()
        self.buttons_hbox.show()
        # Enable/disable it:
        self.enable_info = Gtk.CheckButton(_("Enable?"),False)
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            self.enable_info.set_tooltip_text(_("Enable or disable the info concerning the structure of the R file..."))
        self.enable_info.show()
        self.enable_info.connect( "toggled", self.on_enable_info_toggled )
        self.buttons_hbox.pack_start(self.enable_info,False, True, 0)
        self.enable_info.set_active(self._plugin.prefs['R_structure_enabled'])
            
        # Force refresh:
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            self.force_refresh.set_tooltip_text(_("Force refresh of info concerning the structure of the R file..."))
        self.force_refresh.show()
        self.force_refresh.connect( "clicked", self.on_force_refresh )
        self.force_refresh.set_sensitive(self._plugin.prefs['R_structure_enabled'])
        self.buttons_hbox.pack_end(self.force_refresh,False,True,0)
        
        self.R_struct_base_vbox.pack_start(self.buttons_hbox,False,True,0)

        # The scrollable holder:
        self.scrolled_window.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.show()
        self.scrolled_window.set_sensitive(self._plugin.prefs['R_structure_enabled'])
        
        # The possible types and associated icons:
        function_definition_icon = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/function_definition.png" , 16, 16)
        landmark_definition_icon = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/landmark_definition.png" , 16, 16)
        dataframe_defintion_icon = GdkPixbuf.Pixbuf.new_from_file_at_size(self._plugin.get_data_dir()+"/dataframe_definition.png" , 16, 16)
        self.info_types = {
            'function'   : function_definition_icon,
            'landmark'   : landmark_definition_icon,
            'data.frame' : dataframe_defintion_icon
        }

        # The treeview holding the actual info (line no, icon_type, actual info):
        #self.info_liststore = Gtk.ListStore(GObject.TYPE_INT,GdkPixbuf.Pixbuf,GObject.TYPE_STRING,GObject.TYPE_STRING)
        self.info_liststore = Gtk.ListStore(str,GdkPixbuf.Pixbuf,str,str)
        #self.info_liststore.append(["1",self.info_types['function'],"idem","tooltip1"])
        #self.info_liststore.append(["2",self.info_types['landmark'],"x <- 1","tooltip2"])
        
        self.info_treeview  = Gtk.TreeView()
        self.info_treeview.set_model(self.info_liststore)
        
        # The columns:
        rendererText = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Line", rendererText, text=0)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        self.info_treeview.append_column(column)

        rendererPixbuf = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn("Type", rendererPixbuf, pixbuf=1)
        #column.set_min_width(25)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        self.info_treeview.append_column(column)

        rendererText = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Info", rendererText, text=2)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        self.info_treeview.append_column(column)

        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            self.info_treeview.set_tooltip_column(3)
        self.info_treeview.set_headers_visible(True)
        self.info_treeview.set_headers_clickable(False)
        self.info_treeview.set_reorderable(False)
        self.info_treeview.set_enable_search(True)
        self.info_treeview.set_search_column(2)

        self.info_treeview.show()
        self.scrolled_window.add(self.info_treeview)
        self.R_struct_base_vbox.pack_start(self.scrolled_window,True,True,0)
        
        self.info_treeview.connect("row-activated", self.on_inforow_activated)
        
        # The regular expression matcher:
        self.create_pattern_matcher()
        #self._pattern_matcher = re.compile( r"[ \t]*"+landmark_comment_header + # a landmark comment
        #                                    r"|" + # or
        #                                    r"function\(" # a function defintion
        #                                  )
                                          
    def create_pattern_matcher(self):
        # Create the appriate pattern matcher given the options:
        pattern_definition = r""
        if self._plugin.prefs['R_structure_landmarks']:
            pattern_definition += r"[ \t]*"+landmark_comment_header
        if self._plugin.prefs['R_structure_functions']:
            pattern_definition += (r"|",r"")[len(pattern_definition) == 0] + r"function\("
        if self._plugin.prefs['R_structure_dataframes']:
            pattern_definition += (r"|",r"")[len(pattern_definition) ==0 ]  + r"data\.frame\("
        
        self._pattern_matcher = re.compile(pattern_definition)
        
    def on_enable_info_toggled(self,checkbutton):
        # The enable R info checkbutton has been toggled:
        self._plugin.prefs['R_structure_enabled'] = checkbutton.get_active()
        self._plugin.save_prefs()
        self.force_refresh.set_sensitive(self._plugin.prefs['R_structure_enabled'])
        self.scrolled_window.set_sensitive(self._plugin.prefs['R_structure_enabled'])
        
        # Frce a refresh:
        if self._plugin.prefs['R_structure_enabled']:
            doc = self._window.get_active_document()
            if not doc:
                return
            self.parse_R_document_for_landmarks(doc)
        
    def on_force_refresh(self,button):
        # Force a refresh of the structure:
        doc = self._window.get_active_document()
        if not doc:
            return
        self.parse_R_document_for_landmarks(doc)
        
    def on_inforow_activated(self,widget, row, col):
        # The row has been activated by the user:
        model = widget.get_model()
        doc = self._window.get_active_document()
        if not doc:
            return
        view = self._window.get_active_view()
        if not view:
            return
            
        try:
            line_no = int(model[row][0])
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _('The line number "') + model[row][0] + _('" is illegal!') )
            error_dialog.run()
            error_dialog.destroy()
            return
        if line_no < 0 or line_no > doc.get_line_count():
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("The line number must be a positive integer smaller than the number of lines in the document!") )
            error_dialog.run()
            error_dialog.destroy()
            return
            
        goal_line = doc.get_iter_at_line(line_no-1)
        doc.place_cursor(goal_line)
        #view.scroll_mark_onscreen(doc.get_insert())
        view.scroll_to_mark(doc.get_insert(),0.25,True,0.0,0.5)
        view.grab_focus()
        
    def parse_landmark_text(self,text,type):
        # Parse the landmark text (get rid of the trailing standardized header of a comment landmark:
        if type != "function(" and type != "data.frame(":
            # Landmark comment:
            return text[len(landmark_comment_header):].strip()
        else:
            return text

    def parse_R_document_for_landmarks(self,doc):
        if not self._plugin.prefs['R_structure_enabled']:
            # Widget disabled:
            return
            
        if not self._plugin.is_document_R_source_file(doc):
            # Currently displaying a non-R file:
            self.info_liststore.clear() # clear the listview of the old items
            return
            
        # Parse the R document held by doc for landmarks or function defintions and update the listview accordingly
        # Save the current selection (if any):
        self.selection = self.info_treeview.get_selection().get_selected_rows()[1]
        
        self.info_liststore.clear() # clear the listview of the old items
        # Get the whole text:
        whole_text = doc.get_text(doc.get_start_iter(),doc.get_end_iter(),False)
        
        # Search it for function defintions and landmark comments:
        #start_time = time.clock() # timing for debug
        matches = self._pattern_matcher.finditer(whole_text)
        for match in matches:
            # Get the corresponding position in the document for the match:
            line_no = doc.get_iter_at_offset(match.start()).get_line()
            start = doc.get_iter_at_line(line_no)
            end = start.copy()
            end.forward_line()
            line_text = doc.get_text(start,end,False).strip()
            # Add this info to the list:
            self.info_liststore.append([str(line_no+1),(self.info_types['function'],(self.info_types['data.frame'],self.info_types['landmark'])[match.group() != "data.frame("])[not match.group() == "function("],self.parse_landmark_text(line_text,match.group()),xml.sax.saxutils.escape(line_text)])
        #print (time.clock() - start_time)*1000
        
        # Restore the old selection, if possible:
        if len(self.selection) > 0:
            # There was a selection:
            self.info_treeview.set_cursor_on_cell(self.selection[0],None,None,False)
        else:
            # There was no selection: select the first item (if any):
            self.info_treeview.set_cursor_on_cell(Gtk.TreePath(),None,None,False)
        return



########################################################
#                 End GeditTerminal                    #
########################################################


# Send given text to R
def do_send_to_R( text_to_send, R_widget, as_source, max_lines_direct_send=50 ):
    if not R_widget:
        print("No R console open?")
        return
        
    #print R_widget._plugin.prefs['echo_commands']
    cur_tab = 0
    can_use_source = False
    if R_widget.vteTabs.get_current_page() == 0:
        cur_tab = 1
    elif R_widget.vteTabs.get_current_page() == R_widget._vte2_page_number:
        cur_tab = 2
    elif R_widget.vteTabs.get_current_page() == R_widget._vte3_page_number:
        cur_tab = 3
    else:
        print( _("Unknown R tab!") )
    if cur_tab > 0 and (R_widget.get_profile_attribute(cur_tab,'source-cmd') != None) and (R_widget.get_profile_attribute(cur_tab,'local') == True):
        can_use_source = True
        
    if (as_source or (text_to_send.count("\n") > max_lines_direct_send)) and can_use_source:
        # Write the text to a temp file and call source():
        R_file = open( R_temp_file, 'w' )
        R_file.write( text_to_send )
        R_file.close()
        #R_widget.send_command('source("'+R_temp_file+'",echo=' + str(R_widget._plugin.prefs['echo_commands']).upper() + ',print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n') 
        R_widget.send_command((R_widget.get_profile_attribute(cur_tab,'source-cmd') % R_temp_file) + "\n")
    else:
        # Pipe directly to R:
        R_widget.send_command(text_to_send) 

# Check is a given line is empty or just a comment:
def is_empty_comment_line( line ):
    # Skip all white spaces:
    line_stripped = line.strip();
    return (len(line_stripped) == 0) or (line_stripped[0] == '#');


class RCtrlWindowHelper(GObject.Object):
    __gtype_name__ = "RCtrlWindowHelper"
    
    def __init__(self, plugin, window):
        GObject.Object.__init__(self)
        
        self._window = window
        self._plugin = plugin
        self.datadir = plugin.get_data_dir();
        self.R_widget = None
        self.Detached_R_Dialog = None
        
        # Init the RWizards:
        self.rwizards = RWizardEngine(self)

        # Insert menu items
        self._insert_menu()
        
        # And the R structure panel tab:
        self._rstructurepanel = RStructurePanel(self)
        
    def do_deactivate(self):
        # Remove any installed menu items
        self._remove_menu()

        self._window = None
        self._plugin = None
        self._action_group = None
        
        # and delete the temp file:
        os.remove(R_temp_file)

    def _insert_menu(self):
        # Get the GtkUIManager
        manager = self._window.get_ui_manager()

        R_action = Gtk.Action("R","R","R plugin commands",None)
        R_action_group = Gtk.ActionGroup("R")
        R_action_group.add_action(R_action)
        manager.insert_action_group(R_action_group, -1)

        # Create a new action group
        self._action_group = Gtk.ActionGroup("RCtrlPluginActions")
        self._action_group.add_actions([("RCtrlSel", None, _("Run selection (or current line) through R..."),
                                         self._plugin.prefs['shortcut_RCtrlSel'], _("Run selection (or current line) through R..."),
                                         self.on_send_selection_to_R),
                                        ("RCtrlLine", None, _("Run current line through R..."),
                                         self._plugin.prefs['shortcut_RCtrlLine'], _("Run current line through R..."),
                                         self.on_send_line_to_R),
                                        ("RCtrlAll", None, _("Run whole file through R..."),
                                         self._plugin.prefs['shortcut_RCtrlAll'], _("Run whole file through R..."),
                                         self.on_send_file_to_R),
                                        ("RCtrlCursor", None, _("Run up to current line through R..."),
                                         self._plugin.prefs['shortcut_RCtrlCursor'], _("Run up to current line through R..."),
                                         self.on_send_cursor_to_R),
                                        ("RCtrlBlock1Run", None, _("Run block 1 through R..."),
                                         self._plugin.prefs['shortcut_RCtrlBlock1Run'], _("Run block 1 through R..."),
                                         self.on_send_block1_to_R),
                                        ("RCtrlBlock1Def", None, _("Define block 1..."),
                                         self._plugin.prefs['shortcut_RCtrlBlock1Def'], _("Define block 1..."),
                                         self.on_define_block1),
                                        ("RCtrlBlock2Run", None, _("Run block 2 through R..."),
                                         self._plugin.prefs['shortcut_RCtrlBlock2Run'], _("Run block 2 through R..."),
                                         self.on_send_block2_to_R),
                                        ("RCtrlBlock2Def", None, _("Define block 2..."),
                                         self._plugin.prefs['shortcut_RCtrlBlock2Def'], _("Define block 2..."),
                                         self.on_define_block2),
                                        ("RCtrlNewTab", None, _("New R workspace tab using profile..."),
                                         self._plugin.prefs['shortcut_RCtrlNewTab'], _("Use a selected profile (max 3 tabs allowed)..."),
                                         self.on_R_showhide), # do nothing on click!
                                        #("RCtrlNewTabMenu", None, _("Select profile (defults to the built-in profile)..."),
                                        # self._plugin.prefs['shortcut_RCtrlNewTab'], _("Select profile (defults to the built-in profile)..."),
                                        # self.on_create_new_R_tab),
                                        ("RCtrlConfig", None, _("Configure R interface"),
                                         self._plugin.prefs['shortcut_RCtrlConfig'], _("Configure R interface"),
                                         self.on_R_config_dialog),
                                        ("RCtrlUpdate", None, _("Check for updates"),
                                         None, _("Check for updates"),
                                         self.on_check_for_updates),
                                        #("RCtrlLoadWorkspace", None, _("Load R Workspace"),
                                        # self._plugin.prefs['shortcut_RCtrlLoadWorkspace'], _("Load R Workspace"),
                                        # self.on_R_load_workspace),
                                        #("RCtrlSaveWorkspace", None, _("Save R Workspace"),
                                        # self._plugin.prefs['shortcut_RCtrlSaveWorkspace'], _("Save R Workspace"),
                                        # self.on_R_save_workspace),
                                        ("RCtrlLandmark", None, _("Insert Landmark Comment"),
                                         None, _("Insert Landmark Comment"),
                                         self.on_R_LandmarkComment),
                                        ("RCtrlWizards", None, _("Wizards"),
                                         None, _("Wizards"),
                                         self.on_R_wizards),
                                        ("RCtrlLibraries", None, _("Load script's libraries"),
                                         None, _("Load script's libraries"),
                                         self.on_R_load_all_libraries),
                                        #("RCtrlHelpSel", None, _("Search selection in R help"),
                                        # self._plugin.prefs['shortcut_RCtrlHelpSel'], _("Search selection in R help"),
                                        # self.on_R_search_selection_in_help),
                                        #("RCtrlShowSel", None, _("Inspect selection using showData()"),
                                        # self._plugin.prefs['shortcut_RCtrlShowSel'], _("Inspect selection using showData()"),
                                        # self.on_R_show_selection),
                                        #("RCtrlEditSel", None, _("Edit selection using fix()"),
                                        # self._plugin.prefs['shortcut_RCtrlEditSel'], _("Edit selection using fix()"),
                                        # self.on_R_edit_selection),
                                        ("RCtrlShowHide", None, _("Show/hide toolbar"),
                                         None, _("Show/hide toolbar"),
                                         self.on_R_showhide),
                                        ("RCtrlAttach", None, _("Attach/detach R Console"),
                                         self._plugin.prefs['shortcut_RCtrlAttach'], _("Attach/detach R Console"),
                                         self.on_R_attach),
                                        ("RCtrlClose", None, _("Close R Console"),
                                         self._plugin.prefs['shortcut_RCtrlClose'], _("Close R Console"),
                                         self.on_R_close),
                                        ("RCtrlHelpRCtrl", None, _("Help"),
                                         None, _("Help"),
                                         self.on_R_help),
                                        ("RCtrlAbout", None, _("About"),
                                         None, _("About"),
                                         self.on_R_about)])
                                         
        # Insert the action group
        manager.insert_action_group(self._action_group, 0)

        # Merge the UI
        self._ui_id = manager.add_ui_from_string(ui_str)

        # Make them insensitive and invisible, depending on the action:
        manager.get_action("/ToolBar/RCtrlSel").set_sensitive(False)
        manager.get_action("/ToolBar/RCtrlLine").set_sensitive(False)
        manager.get_action("/ToolBar/RCtrlAll").set_sensitive(False)
        manager.get_action("/ToolBar/RCtrlCursor").set_sensitive(False)
        #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(True)
        manager.get_action("/MenuBar/R/RCtrlBlock1Run").set_sensitive(False)
        manager.get_action("/MenuBar/R/RCtrlBlock2Run").set_sensitive(False)
        manager.get_action("/MenuBar/R/RCtrlAttach").set_sensitive(False)
        manager.get_action("/MenuBar/R/RCtrlClose").set_sensitive(False)

        # Add the icons to the toolbar items:
        RCtrlLine_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_line.png" , 24, 24)
        RCtrlLine_icon.set_from_pixbuf(pixbuf)
        RCtrlLine_icon.show()
        RCtrlLine_toolitem = manager.get_widget("/ToolBar/RCtrlLine")
        RCtrlLine_toolitem.set_icon_widget(RCtrlLine_icon)
        RCtrlLine_toolitem.show()
        RCtrlLine_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_line.png" , 24, 24)
        RCtrlLine_icon.set_from_pixbuf(pixbuf)
        RCtrlLine_icon.show()
        RCtrlLine_menuitem = manager.get_widget("/MenuBar/R/RCtrlLine")
        RCtrlLine_menuitem.set_image(RCtrlLine_icon)
        RCtrlLine_menuitem.show()

        RCtrlSel_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_selection.png" , 24, 24)
        RCtrlSel_icon.set_from_pixbuf(pixbuf)
        RCtrlSel_icon.show()
        RCtrlSel_toolitem = manager.get_widget("/ToolBar/RCtrlSel")
        RCtrlSel_toolitem.set_icon_widget(RCtrlSel_icon)
        RCtrlSel_toolitem.show()
        RCtrlSel_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_selection.png" , 24, 24)
        RCtrlSel_icon.set_from_pixbuf(pixbuf)
        RCtrlSel_icon.show()
        RCtrlSel_menuitem = manager.get_widget("/MenuBar/R/RCtrlSel")
        RCtrlSel_menuitem.set_image(RCtrlSel_icon)
        RCtrlSel_menuitem.show()

        RCtrlAll_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_all.png" , 24, 24)
        RCtrlAll_icon.set_from_pixbuf(pixbuf)
        RCtrlAll_icon.show()
        RCtrlAll_toolitem = manager.get_widget("/ToolBar/RCtrlAll")
        RCtrlAll_toolitem.set_icon_widget(RCtrlAll_icon)
        RCtrlAll_toolitem.show()
        RCtrlAll_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_all.png" , 24, 24)
        RCtrlAll_icon.set_from_pixbuf(pixbuf)
        RCtrlAll_icon.show()
        RCtrlAll_menuitem = manager.get_widget("/MenuBar/R/RCtrlAll")
        RCtrlAll_menuitem.set_image(RCtrlAll_icon)
        RCtrlAll_menuitem.show()

        RCtrlCursor_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_cursor.png" , 24, 24)
        RCtrlCursor_icon.set_from_pixbuf(pixbuf)
        RCtrlCursor_icon.show()
        RCtrlCursor_toolitem = manager.get_widget("/ToolBar/RCtrlCursor")
        RCtrlCursor_toolitem.set_icon_widget(RCtrlCursor_icon)
        RCtrlCursor_toolitem.show()
        RCtrlCursor_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/run_cursor.png" , 24, 24)
        RCtrlCursor_icon.set_from_pixbuf(pixbuf)
        RCtrlCursor_icon.show()
        RCtrlCursor_menuitem = manager.get_widget("/MenuBar/R/RCtrlCursor")
        RCtrlCursor_menuitem.set_image(RCtrlCursor_icon)
        RCtrlCursor_menuitem.show()

        RCtrlBlock1Run_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_run.png" , 24, 24)
        RCtrlBlock1Run_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock1Run_icon.show()
        RCtrlBlock1Run_toolitem = manager.get_widget("/ToolBar/RCtrlBlock1Run")
        RCtrlBlock1Run_toolitem.set_icon_widget(RCtrlBlock1Run_icon)
        RCtrlBlock1Run_toolitem.show()
        RCtrlBlock1Run_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_run.png" , 24, 24)
        RCtrlBlock1Run_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock1Run_icon.show()
        RCtrlBlock1Run_menuitem = manager.get_widget("/MenuBar/R/RCtrlBlock1Run")
        RCtrlBlock1Run_menuitem.set_image(RCtrlBlock1Run_icon)
        RCtrlBlock1Run_menuitem.show()

        RCtrlBlock1Def_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_def.png" , 24, 24)
        RCtrlBlock1Def_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock1Def_icon.show()
        RCtrlBlock1Def_toolitem = manager.get_widget("/ToolBar/RCtrlBlock1Def")
        RCtrlBlock1Def_toolitem.set_icon_widget(RCtrlBlock1Def_icon)
        RCtrlBlock1Def_toolitem.show()
        RCtrlBlock1Def_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_def.png" , 24, 24)
        RCtrlBlock1Def_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock1Def_icon.show()
        RCtrlBlock1Def_menuitem = manager.get_widget("/MenuBar/R/RCtrlBlock1Def")
        RCtrlBlock1Def_menuitem.set_image(RCtrlBlock1Def_icon)
        RCtrlBlock1Def_menuitem.show()

        RCtrlBlock2Run_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_run.png" , 24, 24)
        RCtrlBlock2Run_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock2Run_icon.show()
        RCtrlBlock2Run_toolitem = manager.get_widget("/ToolBar/RCtrlBlock2Run")
        RCtrlBlock2Run_toolitem.set_icon_widget(RCtrlBlock2Run_icon)
        RCtrlBlock2Run_toolitem.show()
        RCtrlBlock2Run_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_run.png" , 24, 24)
        RCtrlBlock2Run_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock2Run_icon.show()
        RCtrlBlock2Run_menuitem = manager.get_widget("/MenuBar/R/RCtrlBlock2Run")
        RCtrlBlock2Run_menuitem.set_image(RCtrlBlock2Run_icon)
        RCtrlBlock2Run_menuitem.show()

        RCtrlBlock2Def_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_def.png" , 24, 24)
        RCtrlBlock2Def_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock2Def_icon.show()
        RCtrlBlock2Def_toolitem = manager.get_widget("/ToolBar/RCtrlBlock2Def")
        RCtrlBlock2Def_toolitem.set_icon_widget(RCtrlBlock2Def_icon)
        RCtrlBlock2Def_toolitem.show()
        RCtrlBlock2Def_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_def.png" , 24, 24)
        RCtrlBlock2Def_icon.set_from_pixbuf(pixbuf)
        RCtrlBlock2Def_icon.show()
        RCtrlBlock2Def_menuitem = manager.get_widget("/MenuBar/R/RCtrlBlock2Def")
        RCtrlBlock2Def_menuitem.set_image(RCtrlBlock2Def_icon)
        RCtrlBlock2Def_menuitem.show()

        #RCtrlNewTab_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/new_workspace.png" , 24, 24)
        #RCtrlNewTab_icon.set_from_pixbuf(pixbuf)
        #RCtrlNewTab_icon.show()
        #RCtrlNewTab_toolitem = manager.get_widget("/ToolBar/RCtrlNewTab")
        #RCtrlNewTab_toolitem.set_icon_widget(RCtrlNewTab_icon)
        #RCtrlNewTab_toolitem.show()
        #RCtrlNewTab_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/new_workspace.png" , 24, 24)
        #RCtrlNewTab_icon.set_from_pixbuf(pixbuf)
        #RCtrlNewTab_icon.show()
        #RCtrlNewTab_menuitem = manager.get_widget("/MenuBar/R/RCtrlNewTab")
        #RCtrlNewTab_menuitem.set_image(RCtrlNewTab_icon)
        #RCtrlNewTab_menuitem.show()
        
        self.create_or_update_profiles_menu(False)

        #RCtrlConfig_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/config.png" , 24, 24)
        #RCtrlConfig_icon.set_from_pixbuf(pixbuf)
        #RCtrlConfig_icon.show()
        #RCtrlConfig_toolitem = manager.get_widget("/ToolBar/RCtrlConfig")
        #RCtrlConfig_toolitem.set_icon_widget(RCtrlConfig_icon)
        #RCtrlConfig_toolitem.show()
        RCtrlConfig_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/config.png" , 24, 24)
        RCtrlConfig_icon.set_from_pixbuf(pixbuf)
        RCtrlConfig_icon.show()
        RCtrlConfig_menuitem = manager.get_widget("/MenuBar/R/RCtrlConfig")
        RCtrlConfig_menuitem.set_image(RCtrlConfig_icon)
        RCtrlConfig_menuitem.show()

        RCtrlAttach_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/attachdetach.png" , 24, 24)
        RCtrlAttach_icon.set_from_pixbuf(pixbuf)
        RCtrlAttach_icon.show()
        RCtrlAttach_menuitem = manager.get_widget("/MenuBar/R/RCtrlAttach")
        RCtrlAttach_menuitem.set_image(RCtrlAttach_icon)
        RCtrlAttach_menuitem.show()

        RCtrlClose_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/closeRconsole.png" , 24, 24)
        RCtrlClose_icon.set_from_pixbuf(pixbuf)
        RCtrlClose_icon.show()
        RCtrlClose_menuitem = manager.get_widget("/MenuBar/R/RCtrlClose")
        RCtrlClose_menuitem.set_image(RCtrlClose_icon)
        RCtrlClose_menuitem.show()

        RCtrlLandmark_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/landmark_comment.png" , 24, 24)
        RCtrlLandmark_icon.set_from_pixbuf(pixbuf)
        RCtrlLandmark_icon.show()
        RCtrlLandmark_menuitem = manager.get_widget("/MenuBar/R/RCtrlLandmark")
        RCtrlLandmark_menuitem.set_image(RCtrlLandmark_icon)
        RCtrlLandmark_menuitem.show()

        #RCtrlHelpSel_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/selection_help.png" , 24, 24)
        #RCtrlHelpSel_icon.set_from_pixbuf(pixbuf)
        #RCtrlHelpSel_icon.show()
        #RCtrlHelpSel_menuitem = manager.get_widget("/MenuBar/R/RCtrlHelpSel")
        #RCtrlHelpSel_menuitem.set_image(RCtrlHelpSel_icon)
        #RCtrlHelpSel_menuitem.show()
        #
        #RCtrlShowSel_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/selection_showdata.png" , 24, 24)
        #RCtrlShowSel_icon.set_from_pixbuf(pixbuf)
        #RCtrlShowSel_icon.show()
        #RCtrlShowSel_menuitem = manager.get_widget("/MenuBar/R/RCtrlShowSel")
        #RCtrlShowSel_menuitem.set_image(RCtrlShowSel_icon)
        #RCtrlShowSel_menuitem.show()
        #
        #RCtrlEditSel_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/selection_editdata.png" , 24, 24)
        #RCtrlEditSel_icon.set_from_pixbuf(pixbuf)
        #RCtrlEditSel_icon.show()
        #RCtrlEditSel_menuitem = manager.get_widget("/MenuBar/R/RCtrlEditSel")
        #RCtrlEditSel_menuitem.set_image(RCtrlEditSel_icon)
        #RCtrlEditSel_menuitem.show()

        RCtrlHelpRCtrl_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/help.png" , 24, 24)
        RCtrlHelpRCtrl_icon.set_from_pixbuf(pixbuf)
        RCtrlHelpRCtrl_icon.show()
        RCtrlHelpRCtrl_menuitem = manager.get_widget("/MenuBar/R/RCtrlHelpRCtrl")
        RCtrlHelpRCtrl_menuitem.set_image(RCtrlHelpRCtrl_icon)
        RCtrlHelpRCtrl_menuitem.show()

        RCtrlAbout_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/Rgedit-icon.png" , 24, 24)
        RCtrlAbout_icon.set_from_pixbuf(pixbuf)
        RCtrlAbout_icon.show()
        RCtrlAbout_menuitem = manager.get_widget("/MenuBar/R/RCtrlAbout")
        RCtrlAbout_menuitem.set_image(RCtrlAbout_icon)
        RCtrlAbout_menuitem.show()

        #RCtrlLoadWorkspace_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/load_workspace.png" , 24, 24)
        #RCtrlLoadWorkspace_icon.set_from_pixbuf(pixbuf)
        #RCtrlLoadWorkspace_icon.show()
        #RCtrlLoadWorkspace_menuitem = manager.get_widget("/MenuBar/R/RCtrlLoadWorkspace")
        #RCtrlLoadWorkspace_menuitem.set_image(RCtrlLoadWorkspace_icon)
        #RCtrlLoadWorkspace_menuitem.show()
        #
        #RCtrlSaveWorkspace_icon = Gtk.Image()
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/save_workspace.png" , 24, 24)
        #RCtrlSaveWorkspace_icon.set_from_pixbuf(pixbuf)
        #RCtrlSaveWorkspace_icon.show()
        #RCtrlSaveWorkspace_menuitem = manager.get_widget("/MenuBar/R/RCtrlSaveWorkspace")
        #RCtrlSaveWorkspace_menuitem.set_image(RCtrlSaveWorkspace_icon)
        #RCtrlSaveWorkspace_menuitem.show()

        # Insert the show/hide toolitem submenu:
        ShowHideMenu = manager.get_widget("/MenuBar/R/RCtrlShowHide")
        ShowHideSubmenu = Gtk.Menu()
        ShowRUI = Gtk.CheckMenuItem()
        ShowRUI.set_label(_("Show toolbar only for R files..."))
        ShowRUI.connect("toggled",self.on_toggle_ShowRUI)
        ShowRUI.set_active(self._plugin.prefs['show_rgedit_UI_only_for_R_mime_types'])
        ShowRUI.show()
        self.on_toggle_ShowRUI(ShowRUI)

        Separator = Gtk.SeparatorMenuItem()
        Separator.show()

        ShowHideLine = Gtk.CheckMenuItem()
        ShowHideLine.set_label(_("Run current line through R..."))
        ShowHideLine.connect("toggled",self.on_toggle_ShowHideLine)
        ShowHideLine.set_active(self._plugin.prefs['show_run_line'])
        ShowHideLine.show()
        self.on_toggle_ShowHideLine(ShowHideLine)

        ShowHideSel = Gtk.CheckMenuItem()
        ShowHideSel.set_label(_("Run current selection through R..."))
        ShowHideSel.connect("toggled",self.on_toggle_ShowHideSel)
        ShowHideSel.set_active(self._plugin.prefs['show_run_sel'])
        ShowHideSel.show()
        self.on_toggle_ShowHideSel(ShowHideSel)

        ShowHideAll = Gtk.CheckMenuItem()
        ShowHideAll.set_label(_("Run whole file through R..."))
        ShowHideAll.connect("toggled",self.on_toggle_ShowHideAll)
        ShowHideAll.set_active(self._plugin.prefs['show_run_all'])
        ShowHideAll.show()
        self.on_toggle_ShowHideAll(ShowHideAll)

        ShowHideCursor = Gtk.CheckMenuItem()
        ShowHideCursor.set_label(_("Run up to current line through R..."))
        ShowHideCursor.connect("toggled",self.on_toggle_ShowHideCursor)
        ShowHideCursor.set_active(self._plugin.prefs['show_run_cursor'])
        ShowHideCursor.show()
        self.on_toggle_ShowHideCursor(ShowHideCursor)

        ShowHideBlock1Run = Gtk.CheckMenuItem()
        ShowHideBlock1Run.set_label(_("Run block 1 through R..."))
        ShowHideBlock1Run.connect("toggled",self.on_toggle_ShowHideBlock1Run)
        ShowHideBlock1Run.set_active(self._plugin.prefs['show_run_block1'])
        ShowHideBlock1Run.show()
        self.on_toggle_ShowHideBlock1Run(ShowHideBlock1Run)

        ShowHideBlock1Def = Gtk.CheckMenuItem()
        ShowHideBlock1Def.set_label(_("Define block 1..."))
        ShowHideBlock1Def.connect("toggled",self.on_toggle_ShowHideBlock1Def)
        ShowHideBlock1Def.set_active(self._plugin.prefs['show_def_block1'])
        ShowHideBlock1Def.show()
        self.on_toggle_ShowHideBlock1Def(ShowHideBlock1Def)

        ShowHideBlock2Run = Gtk.CheckMenuItem()
        ShowHideBlock2Run.set_label(_("Run block 2 through R..."))
        ShowHideBlock2Run.connect("toggled",self.on_toggle_ShowHideBlock2Run)
        ShowHideBlock2Run.set_active(self._plugin.prefs['show_run_block2'])
        ShowHideBlock2Run.show()
        self.on_toggle_ShowHideBlock2Run(ShowHideBlock2Run)

        ShowHideBlock2Def = Gtk.CheckMenuItem()
        ShowHideBlock2Def.set_label(_("Define block 2..."))
        ShowHideBlock2Def.connect("toggled",self.on_toggle_ShowHideBlock2Def)
        ShowHideBlock2Def.set_active(self._plugin.prefs['show_def_block2'])
        ShowHideBlock2Def.show()
        self.on_toggle_ShowHideBlock2Def(ShowHideBlock2Def)

        ShowHideNewTab = Gtk.CheckMenuItem()
        ShowHideNewTab.set_label(_("Create new R workspace tab..."))
        ShowHideNewTab.connect("toggled",self.on_toggle_ShowHideNewTab)
        ShowHideNewTab.set_active(self._plugin.prefs['show_new_tab'])
        ShowHideNewTab.show()
        self.on_toggle_ShowHideNewTab(ShowHideNewTab)

        ShowHideSubmenu.attach(ShowHideLine,0,1,0,1)
        ShowHideSubmenu.attach(ShowHideSel,0,1,1,2)
        ShowHideSubmenu.attach(ShowHideAll,0,1,2,3)
        ShowHideSubmenu.attach(ShowHideCursor,0,1,3,4)
        ShowHideSubmenu.attach(ShowHideBlock1Run,0,1,4,5)
        ShowHideSubmenu.attach(ShowHideBlock1Def,0,1,5,6)
        ShowHideSubmenu.attach(ShowHideBlock2Run,0,1,6,7)
        ShowHideSubmenu.attach(ShowHideBlock2Def,0,1,7,8)
        ShowHideSubmenu.attach(ShowHideNewTab,0,1,8,9)
        ShowHideSubmenu.attach(Separator,0,1,9,10)
        ShowHideSubmenu.attach(ShowRUI,0,1,10,11)
        ShowHideMenu.set_submenu(ShowHideSubmenu)

        
        #Fill in the wizards menu:
        self.fill_in_wizards_menu(manager.get_widget("/MenuBar/R/RCtrlWizards"))

        # Make the attach menu a check menu:
        self.RConsole_attach = not self._plugin.prefs['RConsole_start_attached']
        self.on_R_attach(None)

        # Also create the bottom panel widget if autostart is enabled:
        if self._plugin.prefs['autostart_R_console'] == True:
            self.createRGeditTerminal()

    def create_or_update_profiles_menu(self, update_menus=False):
        # Get the GtkUIManager
        manager = self._window.get_ui_manager()

        # Insert the profiles menu here:
        RCtrlNewTab_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/new_workspace.png" , 24, 24)
        RCtrlNewTab_icon.set_from_pixbuf(pixbuf)
        RCtrlNewTab_icon.show()
        RCtrlNewTab_toolarrow = Gtk.MenuToolButton("NewTabArrow") #Gtk.MenuToolButton(None,"NewTabArrow")
        RCtrlNewTab_toolarrow.show()
        RCtrlNewTab_toolarrow.set_icon_widget(RCtrlNewTab_icon)
        # Create the profiles menu:
        profiles = self._plugin.prefs['profiles']
        if not profiles == None:
            default_icon = Gtk.Image()
            #default_icon.set_from_stock(Gtk.STOCK_APPLY,24)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/default_profile.png" , 24, 24)
            default_icon.set_from_pixbuf(pixbuf)
            default_icon.show()
            RCtrlNewTab_menu = Gtk.Menu()
            for profile in profiles:
                #menu_text = profile[0] + (""," [default]")[profile[3]]
                filem = Gtk.ImageMenuItem(profile['name'])
                if profile['default']:
                    filem.set_image(default_icon)
                filem.connect("activate", self.on_create_new_R_tab, profile['name'])
                filem.connect("select", self.profiles_menu_select, profile)
                filem.connect("deselect", self.profiles_menu_select, None)
                RCtrlNewTab_menu.append(filem)
                filem.show()
            RCtrlNewTab_menu.show()
            RCtrlNewTab_toolarrow.set_menu(RCtrlNewTab_menu)
            RCtrlNewTab_toolarrow.set_arrow_tooltip_text('Chose a profile for the new tab')
            RCtrlNewTab_toolarrow.connect("clicked", self.on_create_new_R_tab)
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            RCtrlNewTab_toolarrow.set_tooltip_text(_("Use the default profile (max 3 tabs allowed)..."))
        toolbar = manager.get_widget('/ToolBar')
        insert_position = toolbar.get_item_index(manager.get_widget("/ToolBar/RCtrlBlock2Def"))
        if update_menus is True:
            # First remove the pre-existing tool:
            toolbar.remove(self._plugin.RCtrlNewTab_toolarrow)
            # Make sure we conserve visibility and sensitivity:
            RCtrlNewTab_toolarrow_visible   = self._plugin.RCtrlNewTab_toolarrow.get_visible() #flags() & Gtk.VISIBLE
            RCtrlNewTab_toolarrow_sensitive = self._plugin.RCtrlNewTab_toolarrow.get_sensitive() #flags() & Gtk.SENSITIVE
        toolbar.insert(RCtrlNewTab_toolarrow,insert_position+1)
        #RCtrlNewTab_toolarrow.set_sensitive(False)
        self._plugin.RCtrlNewTab_toolarrow = RCtrlNewTab_toolarrow # make it visible outside (nasty hack as I cannot use ui_manager for this :( )
        self._plugin.RCtrlNewTab_toolarrow.set_sensitive(True)
        if update_menus is True:
            # Make sure we conserve visibility and sensitivity:
            if RCtrlNewTab_toolarrow_visible:
                self._plugin.RCtrlNewTab_toolarrow.show()
            else:
                self._plugin.RCtrlNewTab_toolarrow.hide()
            self._plugin.RCtrlNewTab_toolarrow.set_sensitive(RCtrlNewTab_toolarrow_sensitive)

        # Insert the new tab submenu:
        NewTabMenu = manager.get_widget("/MenuBar/R/RCtrlNewTab")
        NewTabSubmenu = Gtk.Menu()
        NewTabDefault = Gtk.MenuItem(_("The default profile"))
        NewTabDefault.connect("activate", self.on_create_new_R_tab, None) #profile['name'])
        NewTabDefault.show()

        Separator = Gtk.SeparatorMenuItem()
        Separator.show()

        NewTabSubmenu.append(NewTabDefault)
        NewTabSubmenu.append(Separator)

        # Create the profiles menu:
        profiles = self._plugin.prefs['profiles']
        if not profiles == None:
            default_icon = Gtk.Image()
            #default_icon.set_from_stock(Gtk.STOCK_APPLY,24)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/default_profile.png" , 24, 24)
            default_icon.set_from_pixbuf(pixbuf)
            default_icon.show()
            RCtrlNewTab_menu = Gtk.Menu()
            for profile in profiles:
                #menu_text = profile[0] + (""," [default]")[profile[3]]
                filem = Gtk.ImageMenuItem(profile['name'])
                if profile['default']:
                    filem.set_image(default_icon)
                filem.connect("activate", self.on_create_new_R_tab, profile['name'])
                filem.connect("select", self.profiles_menu_select, profile)
                filem.connect("deselect", self.profiles_menu_select, None)
                NewTabSubmenu.append(filem)
                filem.show()

        NewTabMenu.set_submenu(NewTabSubmenu)


    def profiles_menu_select(self, action, profile=None ):
        # print infor to the statusbar:
        statusbar = self._window.get_statusbar()
        context = 3425 # my statusbar unique context id
        if profile == None:
            statusbar.push(context, "")
        else:
            statusbar.push(context, profile['name'] + ': ' + profile['cmd'] + (' [remote',' [local')[profile['local']] + (']',', default]')[profile['default']])


    # Menu activate handlers
    def on_send_line_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        view = self._window.get_active_view()
        if not view:
            return

        # The last line in the file:
        last_line = doc.get_end_iter().get_line()

        # If required so, try to send a non-empty and non-comment line,otherwise just the current line:
        while True:
            # Get the current line and send it:
            cur_line = doc.get_iter_at_mark(doc.get_insert()).get_line()
            start = doc.get_iter_at_line(cur_line)
            end=start.copy()
            end.forward_line()
            sel_text = doc.get_text(start,end,False)
            
            # Chek if the line is empty or a comment line:
            empty_or_comment = self._plugin.prefs['skip_empty_and_comment_lines'] and is_empty_comment_line(sel_text)
            if not empty_or_comment:
                if len(sel_text) == 0 or sel_text[-1] != '\n' and sel_text[-1] != '\r':
                    sel_text = sel_text + '\n'
                do_send_to_R( sel_text, self.R_widget, False ) # send always as source

            # and advance to the next line:
            if self._plugin.prefs['advance_to_next_line']:
                doc.goto_line(cur_line+1)
                view.scroll_mark_onscreen(doc.get_insert())
                
            if (not empty_or_comment) or (cur_line >= last_line):
                # That was it!
                break;
            
    def on_send_selection_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # See if anything is selected:
        if doc.get_has_selection():
            sel_bounds = doc.get_selection_bounds()
            sel_text = doc.get_text(sel_bounds[0],sel_bounds[1],False)
            if sel_text[-1] != '\n' and sel_text[-1] != '\r':
                sel_text = sel_text + '\n'
            do_send_to_R( sel_text, self.R_widget, False, self._plugin.prefs['max_lines_as_text'] )
        else:
            # Run the current line:
            self.on_send_line_to_R(action)

    def on_send_file_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        sel_text = doc.get_text(doc.get_start_iter(),doc.get_end_iter(),False)
        do_send_to_R( sel_text, self.R_widget, True )

    def on_send_cursor_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        cur_line = doc.get_iter_at_mark(doc.get_insert()).get_line()
        end = doc.get_iter_at_line(cur_line)
        end.forward_line()
        sel_text = doc.get_text(doc.get_start_iter(),end,False)
        do_send_to_R( sel_text, self.R_widget, True )

    def on_send_block1_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # Get the block positions (if any):
        try:
            block1_start = doc.get_iter_at_mark(doc.get_mark("RBlock1Start"))
            block1_end = doc.get_iter_at_mark(doc.get_mark("RBlock1End"))
            block1_end.forward_line()
            sel_text = doc.get_text(block1_start,block1_end,False)
            do_send_to_R( sel_text, self.R_widget, True )
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("Block 1 is not defined in the current document!") )
            error_dialog.run()
            error_dialog.destroy()
            return

    def on_define_block1(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # See if anything is selected:
        if not doc.get_has_selection():
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("You need a selection in order to define a block!") )
            error_dialog.run()
            error_dialog.destroy()
            return

        # Prepare the view:
        view = self._window.get_active_view()
        
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_start.png" , 24, 24)
        mark_attr = GtkSource.MarkAttributes()
        mark_attr.set_pixbuf(pixbuf)
        mark_color = Gdk.RGBA()
        mark_color.parse("lightblue")
        mark_attr.set_background(mark_color)
        view.set_mark_attributes("RBlock1Start",mark_attr,100)

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block1_end.png" , 24, 24)
        mark_attr = GtkSource.MarkAttributes()
        mark_attr.set_pixbuf(pixbuf)
        mark_color = Gdk.RGBA()
        mark_color.parse("lightblue")
        mark_attr.set_background(mark_color)
        view.set_mark_attributes("RBlock1End",mark_attr,100)

        try:
            view.set_show_line_marks(True)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use set_show_line_markers:
            view.set_show_line_markers(True)

        # Delete any previously existing:
        try:
            doc.remove_source_marks(doc.get_start_iter(),doc.get_end_iter(),"RBlock1Start")
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use delete_marker:
            marker_to_delete = doc.get_marker("RBlock1Start")
            if marker_to_delete != None:
                doc.delete_marker(marker_to_delete)
        try:
            doc.remove_source_marks(doc.get_start_iter(),doc.get_end_iter(),"RBlock1End")
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use delete_marker:
            marker_to_delete = doc.get_marker("RBlock1End")
            if marker_to_delete != None:
                doc.delete_marker(marker_to_delete)
            
        # And create the new one here:
        sel_bounds = doc.get_selection_bounds()
        cur_line = sel_bounds[0].get_line()
        start = doc.get_iter_at_line(cur_line)
        try:
            block_start_mark = doc.create_source_mark("RBlock1Start","RBlock1Start",start)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use create_marker:
            block_start_mark = doc.create_marker("RBlock1Start","RBlock1Start",start)
        block_start_mark.set_visible(True)
        cur_line = sel_bounds[1].get_line()
        end = doc.get_iter_at_line(cur_line)
        #end.forward_line()
        try:
            block_start_mark = doc.create_source_mark("RBlock1End","RBlock1End",end)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use create_marker:
            block_start_mark = doc.create_marker("RBlock1End","RBlock1End",end)
        block_start_mark.set_visible(True)

    def on_send_block2_to_R(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # Get the block positions (if any):
        try:
            block2_start = doc.get_iter_at_mark(doc.get_mark("RBlock2Start"))
            block2_end = doc.get_iter_at_mark(doc.get_mark("RBlock2End"))
            block2_end.forward_line()
            sel_text = doc.get_text(block2_start,block2_end,False)
            do_send_to_R( sel_text, self.R_widget, True )
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("Block 2 is not defined in the current document!") )
            error_dialog.run()
            error_dialog.destroy()
            return

    def on_define_block2(self, action, param=None):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # See if anything is selected:
        if not doc.get_has_selection():
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("You need a selection in order to define a block!") )
            error_dialog.run()
            error_dialog.destroy()
            return

        # Prepare the view:
        view = self._window.get_active_view()
        
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_start.png" , 24, 24)
        mark_attr = GtkSource.MarkAttributes()
        mark_attr.set_pixbuf(pixbuf)
        mark_color = Gdk.RGBA()
        mark_color.parse("gold")
        mark_attr.set_background(mark_color)
        view.set_mark_attributes("RBlock2Start",mark_attr,100)

        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.datadir+"/block2_end.png" , 24, 24)
        mark_attr = GtkSource.MarkAttributes()
        mark_attr.set_pixbuf(pixbuf)
        mark_color = Gdk.RGBA()
        mark_color.parse("gold")
        mark_attr.set_background(mark_color)
        view.set_mark_attributes("RBlock2End",mark_attr,100)

        try:
            view.set_show_line_marks(True)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use set_show_line_markers:
            view.set_show_line_markers(True)

        # Delete any previously existing:
        try:
            doc.remove_source_marks(doc.get_start_iter(),doc.get_end_iter(),"RBlock2Start")
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use delete_marker:
            marker_to_delete = doc.get_marker("RBlock2Start")
            if marker_to_delete != None:
                doc.delete_marker(marker_to_delete)
        try:
            doc.remove_source_marks(doc.get_start_iter(),doc.get_end_iter(),"RBlock2End")
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use delete_marker:
            marker_to_delete = doc.get_marker("RBlock2End")
            if marker_to_delete != None:
                doc.delete_marker(marker_to_delete)
            
        # And create the new one here:
        sel_bounds = doc.get_selection_bounds()
        cur_line = sel_bounds[0].get_line()
        start = doc.get_iter_at_line(cur_line)
        try:
            block_start_mark = doc.create_source_mark("RBlock2Start","RBlock2Start",start)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use create_marker:
            block_start_mark = doc.create_marker("RBlock2Start","RBlock2Start",start)
        block_start_mark.set_visible(True)
        cur_line = sel_bounds[1].get_line()
        end = doc.get_iter_at_line(cur_line)
        #end.forward_line()
        try:
            block_start_mark = doc.create_source_mark("RBlock2End","RBlock2End",end)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use create_marker:
            block_start_mark = doc.create_marker("RBlock2End","RBlock2End",end)
        block_start_mark.set_visible(True)

    def on_create_new_R_tab(self, action, profile=None):
        #print "Creating tab using profile: " + str(profile)
        if self.R_widget == None:
            self.createRGeditTerminal(profile)
        else:
            self.R_widget.create_new_R_tab(profile)

    def on_R_config_dialog(self, action, param=None): 
        dialog = self._plugin.create_configure_dialog()
        dialog.run()
        dialog.destroy()

    def on_check_for_updates(self, action, param=None):
        # Get the current version:
        about_ui = create_UI_from_file_GtkBuilder_or_Glade(self._plugin.get_data_dir()+"/About.glade",self._plugin.get_data_dir()+"/About.ui")
        current_version = get_widget_from_ui_GtkBuilder_or_Glade(about_ui,'AboutDialog').get_version()
        # And the current version of the official wizards pack:
        wizards_pack_version_file = open( self._plugin.get_data_dir() + str("/Wizards/wizards.version"), "rt" )
        wizards_current_version = wizards_pack_version_file.read()
        wizards_current_version = wizards_current_version.strip()
        wizards_pack_version_file.close()
        
        # And the latest version available on the server:
        try:
            latest_version = urllib.request.urlopen('http://rgedit.sourceforge.net/latest.version.gtk3').read()
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Cannot read the latest available version from rgedit's website!\nPlease, try again later...") )
            error_dialog.run()
            error_dialog.destroy()
            return
        try:
            wizards_latest_version = urllib.request.urlopen('http://rgedit.sourceforge.net/wizards.latest.version').read()
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Cannot read the latest available version of the wizards package from rgedit's website!\nPlease, try again later...") )
            error_dialog.run()
            error_dialog.destroy()
            return

        # Compare the two versions:
        if current_version.strip().lower() == latest_version.strip().lower() and wizards_current_version.strip().lower() == wizards_latest_version.strip().lower():
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("You have the latest version of rgedit (") + current_version.strip() + _(") and official wizards package (") + wizards_current_version.strip() + _(") installed.") )
            response = question_dialog.run()
            question_dialog.destroy()
        elif current_version.strip().lower() != latest_version.strip().lower() and wizards_current_version.strip().lower() != wizards_latest_version.strip().lower():
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _("You have version ") + current_version.strip() + _(" of rgedit installed, but the newer ") + latest_version.strip() + _(" is available, and version ") + wizards_current_version.strip() + _(" of the official wizards package installed, but the newer ") + wizards_latest_version.strip() + _(" is available.\n Would you like to download them?") )
            response = question_dialog.run()
            question_dialog.destroy()
            if response == Gtk.ResponseType.YES:
                webbrowser.open("http://rgedit.sourceforge.net/")
        elif current_version.strip().lower() != latest_version.strip().lower() and wizards_current_version.strip().lower() == wizards_latest_version.strip().lower():
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _("You have version ") + current_version.strip() + _(" of rgedit installed, but the newer ") + latest_version.strip() + _(" is available.\n Would you like to download it?") )
            response = question_dialog.run()
            question_dialog.destroy()
            if response == Gtk.ResponseType.YES:
                webbrowser.open("http://rgedit.sourceforge.net/")
        else:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _("You have version ") + wizards_current_version.strip() + _(" of the official wizards package installed, but the newer ") + wizards_latest_version.strip() + _(" is available.\n Would you like to download it?") )
            response = question_dialog.run()
            question_dialog.destroy()
            if response == Gtk.ResponseType.YES:
                webbrowser.open("http://rgedit.sourceforge.net/")

    def on_R_load_all_libraries(self,action):
        doc = self._window.get_active_document()
        if not doc:
            return
        
        # Locate "library(" and "require(" which are not within comments or strings and determine their end and run them!
        
        # Get the whole text:
        whole_text = doc.get_text(doc.get_start_iter(),doc.get_end_iter(),False)
        
        # Create the appriate pattern matcher given the options:
        pattern_definition = r"library[ \t]*\(|require[ \t]*\("
        pattern_matcher = re.compile(pattern_definition)

        #start_time = time.clock() # timing for debug
        libraries_to_load = []
        matches = pattern_matcher.finditer(whole_text)
        for match in matches:
            # Get the corresponding position in the document for the match:
            line_no = doc.get_iter_at_offset(match.start()).get_line()
            start = doc.get_iter_at_line(line_no)
            end = start.copy()
            end.forward_line()
            line_text = doc.get_text(start,end,False).strip()
            # Add this info to the list:
            libraries_to_load += [line_text]
        #print (time.clock() - start_time)*1000
        
        # Ask the use which of these (s)he actually wants loaded:
        #print libraries_to_load
        if len(libraries_to_load) == 0:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("There are no libraries to load for this script!") )
            response = question_dialog.run()
            question_dialog.destroy()
            return
                   
        # Present the user with the libraries to load:
        model = Gtk.ListStore(bool,str)
        tv = Gtk.TreeView(model)

        cell = Gtk.CellRendererToggle()
        cell.connect("toggled", self.on_load_libraries_toggle, model)
        cell.set_property('activatable', True)
        col = Gtk.TreeViewColumn("Load?", cell, active=0)
        tv.append_column(col)
        
        rendererText = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Library", rendererText, text=1)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            tv.set_tooltip_column(1)

        # Fill in the libraries: 
        for l in libraries_to_load:  
            model.append([True, l])
       
        dialog = Gtk.Dialog("Load script's libraries",self._window,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,"Load", Gtk.ResponseType.ACCEPT))
        
        dialog.set_default_size(300, 250)
        label = Gtk.Label(_("  Please select which libraries to load (the actual code will be run):  "))
        dialog.vbox.pack_start(label,False,False,False)
        label.show()
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.show()
        scrolled_window.set_sensitive(True)
        scrolled_window.add(tv)
        tv.show()
        scrolled_window.show()
        
        dialog.vbox.pack_start(scrolled_window,True,True,False)

        response = dialog.run()
        dialog.destroy() 
        
        if response == Gtk.ResponseType.ACCEPT:  
            libraries_to_load = 0
            for i in model:
                libraries_to_load += i[0]
                
            if libraries_to_load > 0:        
                do_send_to_R( "# Loading "+str(libraries_to_load)+" of script's libraries...\n", self.R_widget, False, self._plugin.prefs['max_lines_as_text'] )
                for i in model:
                    if i[0] == True:
                        # Load the library:
                        do_send_to_R( i[1]+'\n', self.R_widget, False, self._plugin.prefs['max_lines_as_text'] )
                do_send_to_R( "# DONE loading!\n", self.R_widget, False, self._plugin.prefs['max_lines_as_text'] )
            else:
                do_send_to_R( "# No libraries selected\n", self.R_widget, False, self._plugin.prefs['max_lines_as_text'] )
                
        return
        
    def on_load_libraries_toggle(self,cell, path, model):
        if path is not None:
            model[path][0] = not model[path][0]
        return

    def on_R_LandmarkComment(self,action, param=None):
        self._plugin.on_context_menu_landmark(None,self._window.get_active_document())
        return
        
    def on_R_wizards(self,action, param=None):
        return

    def on_R_showhide(self,action, param=None):
        return

    def on_R_attach(self,action, param=None):
        self.RConsole_attach = not self.RConsole_attach
        manager = self._window.get_ui_manager()
        AttachMenuItem = manager.get_widget("/MenuBar/R/RCtrlAttach")
        if self.RConsole_attach:
            AttachMenuItem.get_child().set_label('Attach R Console')
            if action != None:
                self.create_R_detached_dialog()
        else:
            AttachMenuItem.get_child().set_label('Detach R Console')
            if action != None:
                self.destroy_R_detached_dialog()

        #print "self.RConsole_attach is " + str(self.RConsole_attach)

    def on_R_close(self,action, param=None):
        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _("Are you sure you want to completely close the R console?\nAll open tabs will also be closed!") )
        response = question_dialog.run()
        question_dialog.destroy()

        if response == Gtk.ResponseType.YES:
            manager = self._window.get_ui_manager()
            # Make them insensitive and invisible, depending on the action:
            manager.get_action("/ToolBar/RCtrlSel").set_sensitive(False)
            manager.get_action("/ToolBar/RCtrlLine").set_sensitive(False)
            manager.get_action("/ToolBar/RCtrlAll").set_sensitive(False)
            manager.get_action("/ToolBar/RCtrlCursor").set_sensitive(False)
            #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(True)
            self._plugin.RCtrlNewTab_toolarrow.set_sensitive(True)
            #manager.get_action("/ToolBar/RCtrlConfig").set_sensitive(True)
            manager.get_action("/MenuBar/R/RCtrlBlock1Run").set_sensitive(False)
            manager.get_action("/MenuBar/R/RCtrlBlock2Run").set_sensitive(False)
            #manager.get_action("/MenuBar/R/RCtrlLoadWorkspace").set_sensitive(False)
            #manager.get_action("/MenuBar/R/RCtrlSaveWorkspace").set_sensitive(False)
            #manager.get_action("/MenuBar/R/RCtrlHelpSel").set_sensitive(False)
            #manager.get_action("/MenuBar/R/RCtrlShowSel").set_sensitive(False)
            #manager.get_action("/MenuBar/R/RCtrlEditSel").set_sensitive(False)
            manager.get_action("/MenuBar/R/RCtrlAttach").set_sensitive(False)
            manager.get_action("/MenuBar/R/RCtrlClose").set_sensitive(False)
            
            # Close it!
            if self.R_widget._vte != None:
                self.R_widget.kill_shell_process(self.R_widget._vte1_shell_PID)
                self.R_widget._vte1_shell_PID = -1
            if self.R_widget._vte2 != None:
                self.R_widget.kill_shell_process(self.R_widget._vte2_shell_PID)
                self.R_widget._vte2_shell_PID = -1
            if self.R_widget._vte3 != None:
                self.R_widget.kill_shell_process(self.R_widget._vte3_shell_PID)
                self.R_widget._vte3_shell_PID = -1
            ## Give them time to exit
            #time.sleep(1)
            self.R_widget.destroy()
            self.R_widget = None
            if self.RConsole_attach and self.Detached_R_Dialog != None:
                self.Detached_R_Dialog.destroy()
                self.Detached_R_Dialog = None
            if not self.RConsole_attach and self.bottom_panel_dummy_hbox != None:
                self._window.get_bottom_panel().remove_item(self.bottom_panel_dummy_hbox)

    def update_R_consoles(self,vte1_console_changed,vte2_console_changed,vte3_console_changed,vte1_R_options_changed,vte2_R_options_changed,vte3_R_options_changed):
        # Update the R consoles because some options have changed
        if self.R_widget != None:
            self.R_widget.reconfigure_vtes(vte1_console_changed,vte2_console_changed,vte3_console_changed,vte1_R_options_changed,vte2_R_options_changed,vte3_R_options_changed)

    def on_R_help(self,action, param=None):
        webbrowser.open(self.datadir+"/Help/Help.html")

    def on_R_about(self,action, param=None):
        about_ui = create_UI_from_file_GtkBuilder_or_Glade(self._plugin.get_data_dir()+"/About.glade",self._plugin.get_data_dir()+"/About.ui")
        about_dialog = get_widget_from_ui_GtkBuilder_or_Glade(about_ui,"AboutDialog")
        about_dialog.run()
        about_dialog.destroy()

    def on_toggle_ShowRUI(self,checkmenuitem, param=None):
        self._plugin.prefs['show_rgedit_UI_only_for_R_mime_types'] = checkmenuitem.get_active()
        self._plugin.show_hide_toolbar_and_friends(self._window.get_active_document())
        self._plugin.save_prefs()

    def on_toggle_ShowHideLine(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlLineToolitem = manager.get_widget("/ToolBar/RCtrlLine")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlLineToolitem.show()
        else:
            RCtrlLineToolitem.hide()
        self._plugin.prefs['show_run_line'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideSel(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlSelToolitem = manager.get_widget("/ToolBar/RCtrlSel")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlSelToolitem.show()
        else:
            RCtrlSelToolitem.hide()
        self._plugin.prefs['show_run_sel'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideAll(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlAllToolitem = manager.get_widget("/ToolBar/RCtrlAll")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlAllToolitem.show()
        else:
            RCtrlAllToolitem.hide()
        self._plugin.prefs['show_run_all'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideCursor(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlCursorToolitem = manager.get_widget("/ToolBar/RCtrlCursor")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlCursorToolitem.show()
        else:
            RCtrlCursorToolitem.hide()
        self._plugin.prefs['show_run_cursor'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideBlock1Run(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlBlock1RunToolitem = manager.get_widget("/ToolBar/RCtrlBlock1Run")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlBlock1RunToolitem.show()
        else:
            RCtrlBlock1RunToolitem.hide()
        self._plugin.prefs['show_run_block1'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideBlock1Def(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlBlock1DefToolitem = manager.get_widget("/ToolBar/RCtrlBlock1Def")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlBlock1DefToolitem.show()
        else:
            RCtrlBlock1DefToolitem.hide()
        self._plugin.prefs['show_def_block1'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideBlock2Run(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlBlock2RunToolitem = manager.get_widget("/ToolBar/RCtrlBlock2Run")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlBlock2RunToolitem.show()
        else:
            RCtrlBlock2RunToolitem.hide()
        self._plugin.prefs['show_run_block2'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideBlock2Def(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        RCtrlBlock2DefToolitem = manager.get_widget("/ToolBar/RCtrlBlock2Def")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            RCtrlBlock2DefToolitem.show()
        else:
            RCtrlBlock2DefToolitem.hide()
        self._plugin.prefs['show_def_block2'] = checkmenuitem.get_active()
        self._plugin.save_prefs()

    def on_toggle_ShowHideNewTab(self,checkmenuitem, param=None):
        manager = self._window.get_ui_manager()
        #RCtrlNewTabToolitem = manager.get_widget("/ToolBar/RCtrlNewTab")
        if checkmenuitem.get_active() and self._plugin.show_gedit_UI:
            #RCtrlNewTabToolitem.show()
            if self._plugin.RCtrlNewTab_toolarrow != None:
                self._plugin.RCtrlNewTab_toolarrow.show()
        else:
            #RCtrlNewTabToolitem.hide()
            if self._plugin.RCtrlNewTab_toolarrow != None:
                self._plugin.RCtrlNewTab_toolarrow.hide()
        self._plugin.prefs['show_new_tab'] = checkmenuitem.get_active()
        self._plugin.save_prefs()


    #Fill in the wizards menu:
    def fill_in_wizards_menu(self,WizardsMenu, param=None):
        # Create a data structure which retains the menu (sub)paths and the associated menu item (to avoid menu duplications)
        # This is, in fact, a dictionary having as the key the path
        self.submenu_dictionary = {}
        
        if len(self.rwizards.wizards) > 0:
            WizardsSubmenu = Gtk.Menu()
            
            # The About... menu first:
            about_menu_item = Gtk.ImageMenuItem()
            about_menu_item.set_label(_("About Rwizards..."))
            try:
                menu_icon = Gtk.Image()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.rwizards.wizards[1]._rwizardengine.path+"wizard.png",16,16)
                menu_icon.set_from_pixbuf(pixbuf)
                menu_icon.show()
                about_menu_item.set_image(menu_icon)
            except:
                pass
            about_menu_item.show()
            about_menu_item.connect("activate",self.on_about_rwizards,self.rwizards.wizards[1]._rwizardengine.path+"wizard.png")
            WizardsSubmenu.append(about_menu_item)
            
            # The submenus:
            for wizard in self.rwizards.wizards:
                # Make sure a reasonable menu path exists and return the actual menu path:
                self.create_submenu_path( WizardsSubmenu, wizard.ActualMenu, wizard.Description, wizard._rwizardengine.path+wizard.ActualIcon, 1 )
            WizardsMenu.set_submenu(WizardsSubmenu)
            menu_icon = Gtk.Image()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(wizard._rwizardengine.path+"wizard.png",16,16)
            menu_icon.set_from_pixbuf(pixbuf)
            menu_icon.show()
            WizardsMenu.set_image(menu_icon)
            
    def create_submenu_path(self,current_submenu,submenu_path,item_description,item_icon,cur_depth):
        # Parse the submenu_path and keep at most max_submenu_path_depth levels:
        splitted_path = submenu_path.split("/")
        if cur_depth > 5 or cur_depth >= len(splitted_path):
            actual_menu_item = Gtk.ImageMenuItem()
            actual_menu_item.set_label(item_description)
            try:
                menu_icon = Gtk.Image()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(item_icon,16,16)
                menu_icon.set_from_pixbuf(pixbuf)
                menu_icon.show()
                actual_menu_item.set_image(menu_icon)
            except:
                pass
            actual_menu_item.show()
            actual_menu_item.connect("activate",self.on_wizard_activated,item_description)
            current_submenu.append(actual_menu_item)
            return

        curr_item = splitted_path[cur_depth]
        #print "Attempting to create wizard submenu:" + curr_item
        
        # See if the menu path aredy exists:
        cur_sub_path = "/".join(splitted_path[:(cur_depth+1)])
        #print "get_widget: /MenuBar/R/RCtrlWizards"+cur_sub_path
        
        # Recursion:
        already_defined = False
        if not cur_sub_path in self.submenu_dictionary:
            # Create it:
            submenu_item = Gtk.MenuItem()
            submenu_item.set_label(curr_item)
            submenu_item.show()
            submenu_submenu = Gtk.Menu()
            current_submenu.append(submenu_item)
            self.submenu_dictionary[cur_sub_path] = submenu_submenu
        else:
            # Reuse it:
            submenu_submenu = self.submenu_dictionary[cur_sub_path]
            already_defined = True
        
        self.create_submenu_path(submenu_submenu,submenu_path,item_description,item_icon,cur_depth+1)
        if not already_defined:
            submenu_item.set_submenu(submenu_submenu)
        return
        
        
    def on_wizard_activated(self,widget,data):
        # A wizard was clicked and data contains its description:
        # Identify the wizard and call it:
        found = False
        for wizard in self.rwizards.wizards:
            if wizard.Description == data:
                # Call the wizard:
                wizard.run()
                found = True
                break
        if not found:
            print("Something fishy: cannot find the wizard with description \"") + data + "\"..."
            
    def on_about_rwizards(self,widget,icon):
        # Get the current version of the official wizards pack:
        wizards_pack_version_file = open( self._plugin.get_data_dir() + str("/Wizards/wizards.version"), "rt" )
        wizards_current_version = wizards_pack_version_file.read()
        wizards_current_version = wizards_current_version.strip()
        wizards_pack_version_file.close()
        
        # Display the About Rwizards dialog:
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_name(_("RWizards official package"))
        about_dialog.set_version(wizards_current_version)
        about_dialog.set_copyright(_("(c) 2009,2010, Dan Dediu"))    
        about_dialog.set_comments(_("A set of predefined Rwizards"))
        about_dialog.set_license(_("""
    Rwizards official package: a set of wizards for rgedit
    Copyright (C) 2009  Dan Dediu

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""))
        about_dialog.set_website("http://sourceforge.net/projects/rgedit/")
        about_dialog.set_authors("") 
        about_dialog.set_documenters("")
        about_dialog.set_artists("")
        about_dialog.set_translator_credits("")
        about_dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file(icon))
        
        about_dialog.show()
        about_dialog.run()
        about_dialog.destroy()
                    
    def createRGeditTerminal(self,profile=None):
        self.R_widget = RGeditTerminal(self._plugin)
        self.R_widget._window = self._window

        #print self._plugin.prefs['RConsole_start_attached']
        self.bottom_panel_dummy_hbox = None
        if self._plugin.prefs['RConsole_start_attached'] == False:
            R_icon = Gtk.Image()
            R_icon.set_from_file(self.datadir+"/Rgedit-icon24.png")
            self.bottom_panel_dummy_hbox = Gtk.HBox()
            self.bottom_panel_dummy_hbox.show()
            self.bottom_panel_dummy_hbox.pack_start(self.R_widget,True,True,True)
            self.R_widget.show()
            self._window.get_bottom_panel().add_item(self.bottom_panel_dummy_hbox,"R Console","R Console",R_icon)
            self._window.get_bottom_panel().set_property("visible",True)
        elif self.Detached_R_Dialog != None:
            self.R_widget.show()
            try:
                self.Detached_R_Dialog.get_content_area().pack_start(self.R_widget,True,True)
            except:
                self.Detached_R_Dialog.get_child().pack_start(self.R_widget,True,True)            
            self.Detached_R_Dialog.show()
        else:
            # Create the dialog to embed the detached R console:
            #self.Detached_R_Dialog = Gtk.Dialog( "Detached R console", self._window, Gtk.DialogFlags.DESTROY_WITH_PARENT, None );
            self.Detached_R_Dialog = Gtk.Window() # Gtk.WindowType.TOPLEVEL
            self.Detached_R_Dialog.set_title( "Detached R console" )
            self.Detached_R_Dialog.set_destroy_with_parent( True )
            self.Detached_R_Dialog.connect('delete_event', self.on_R_Dialog_close)
            self.Detached_R_Dialog.connect('configure_event', self.on_R_Dialog_configure)
            self.Detached_R_Dialog.set_icon(GdkPixbuf.Pixbuf.new_from_file(self.datadir+"/Rgedit-icon24.png"))
            if self._plugin.prefs['RConsole_detached_x'] != -1 and self._plugin.prefs['RConsole_detached_y'] != -1:
                self.Detached_R_Dialog.move(self._plugin.prefs['RConsole_detached_x'],self._plugin.prefs['RConsole_detached_y'])
            if self._plugin.prefs['RConsole_detached_width'] == -1:
                self._plugin.prefs['RConsole_detached_width'] = 100
            if self._plugin.prefs['RConsole_detached_height'] == -1:
                self._plugin.prefs['RConsole_detached_height'] = 100
            self.Detached_R_Dialog.resize(self._plugin.prefs['RConsole_detached_width'],self._plugin.prefs['RConsole_detached_height'])
            if self.R_widget != None:
                dummyHBox = Gtk.HBox()
                dummyHBox.show()
                dummyHBox.pack_start(self.R_widget,True,True,0)
                self.R_widget.show()
                #try:
                #    self.Detached_R_Dialog.get_content_area().pack_start(dummyHBox,True,True)
                #except:
                #    self.Detached_R_Dialog.get_child().pack_start(dummyHBox,True,True)                            
                self.Detached_R_Dialog.add(dummyHBox)
            self.Detached_R_Dialog.show()

        self.R_widget.set_profile(1,profile)
        self.R_widget.send_command(self.R_widget.get_profile_attribute(1,'cmd')+"\n") # open R
        #self.R_widget.send_command("ssh -X -t deddan@lux02.mpi.nl ssh -X -t m10604423 sh -c 'R --no-save --no-restore' \n") # open R
        #self.R_widget.send_command("ssh -X -t deddan@lux02.mpi.nl ssh -X -t m10604423 'R --no-save --no-restore' \n") # open R
        self.R_widget.run_gedit_helper_script(self.R_widget._vte,1)
        if self.R_widget.get_profile_attribute(1,'help-type') == 'HTML':
            self.R_widget.send_command("options(htmlhelp = TRUE,help_type='html')\n") # and init the HTML help system both for pre and post R 2.10.0...
        elif self.R_widget.get_profile_attribute(1,'help-type') == 'Text':
            self.R_widget.send_command("options(htmlhelp = FALSE,help_type='text')\n") # and init the TEXT help system both for pre and post R 2.10.0...
        elif self.R_widget.get_profile_attribute(1,'help-type') == 'Custom':
            self.R_widget.send_command(str(self.R_widget.get_profile_attribute(1,'help-custom-command'))+"\n") # send the custom command
        else: # 'Default' & others
            pass # leave the system default
        if self._plugin.prefs['prompt_color1'] != None or self._plugin.prefs['tab_name_in_prompt'] == True:
            self.R_widget.send_command(self._plugin.prompt_string(1,self.R_widget.get_tab_name(1),self.R_widget.get_profile(1))) # and set the prompt accordingly...
        if self._plugin.prefs['autostart_R_script'] and self.R_widget.get_profile_attribute(1,'source-cmd') != None:
            #self.R_widget.send_command("source(\""+self._plugin.prefs['autostart_R_script_path']+"\",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE);\n") # run the autostart script...
            self.R_widget.send_command((self.R_widget.get_profile_attribute(1,'source-cmd') % self._plugin.prefs['autostart_R_script_path']) + "\n")
        if self._plugin.prefs['use_current_document_directory']:
            self.R_widget.change_vte_R_working_dir_to_the_document(self.R_widget._vte,1)
        self.R_widget.show_messages_and_warnings(self.R_widget._vte,1)

        # Sensitivity:
        manager = self._window.get_ui_manager()
        manager.get_action("/ToolBar/RCtrlSel").set_sensitive(True)
        manager.get_action("/ToolBar/RCtrlLine").set_sensitive(True)
        manager.get_action("/ToolBar/RCtrlAll").set_sensitive(True)
        manager.get_action("/ToolBar/RCtrlCursor").set_sensitive(True)
        #manager.get_action("/ToolBar/RCtrlNewTab").set_sensitive(True)
        if self._plugin.RCtrlNewTab_toolarrow != None:
            self._plugin.RCtrlNewTab_toolarrow.set_sensitive(True)
        #manager.get_action("/ToolBar/RCtrlConfig").set_sensitive(True)
        manager.get_action("/MenuBar/R/RCtrlAttach").set_sensitive(True)
        manager.get_action("/MenuBar/R/RCtrlBlock1Run").set_sensitive(True)
        manager.get_action("/MenuBar/R/RCtrlBlock2Run").set_sensitive(True)
        #manager.get_action("/MenuBar/R/RCtrlLoadWorkspace").set_sensitive(True)
        #manager.get_action("/MenuBar/R/RCtrlSaveWorkspace").set_sensitive(True)
        #manager.get_action("/MenuBar/R/RCtrlHelpSel").set_sensitive(True)
        #manager.get_action("/MenuBar/R/RCtrlShowSel").set_sensitive(True)
        #manager.get_action("/MenuBar/R/RCtrlEditSel").set_sensitive(True)
        manager.get_action("/MenuBar/R/RCtrlClose").set_sensitive(True)

    def create_R_detached_dialog(self):
        # Create the dialog to embed the detached R console:
        #self.Detached_R_Dialog = Gtk.Dialog( "Detached R console", self._window, Gtk.DialogFlags.DESTROY_WITH_PARENT, None );
        self.Detached_R_Dialog = Gtk.Window() # Gtk.WindowType.TOPLEVEL
        self.Detached_R_Dialog.set_title( _("Detached R console") )
        self.Detached_R_Dialog.set_destroy_with_parent( True )
        self.Detached_R_Dialog.connect('delete_event', self.on_R_Dialog_close)
        self.Detached_R_Dialog.connect('configure_event', self.on_R_Dialog_configure)
        self.Detached_R_Dialog.set_icon(GdkPixbuf.Pixbuf.new_from_file(self.datadir+"/Rgedit-icon24.png"))
        if self._plugin.prefs['RConsole_detached_x'] != -1 and self._plugin.prefs['RConsole_detached_y'] != -1:
            self.Detached_R_Dialog.move(self._plugin.prefs['RConsole_detached_x'],self._plugin.prefs['RConsole_detached_y'])
        if self._plugin.prefs['RConsole_detached_width'] == -1:
            self._plugin.prefs['RConsole_detached_width'] = 100
        if self._plugin.prefs['RConsole_detached_height'] == -1:
            self._plugin.prefs['RConsole_detached_height'] = 100
        self.Detached_R_Dialog.resize(self._plugin.prefs['RConsole_detached_width'],self._plugin.prefs['RConsole_detached_height'])
        if self.R_widget != None:
            dummyHBox = Gtk.HBox()
            dummyHBox.show()
            self.R_widget.reparent(dummyHBox)
            #try:
            #    self.Detached_R_Dialog.get_content_area().pack_start(dummyHBox,True,True)
            #except:
            #    self.Detached_R_Dialog.get_child().pack_start(dummyHBox,True,True)
            self.Detached_R_Dialog.add(dummyHBox)
        self.Detached_R_Dialog.show()
        if self.bottom_panel_dummy_hbox != None:
            self._window.get_bottom_panel().remove_item(self.bottom_panel_dummy_hbox)

    def destroy_R_detached_dialog(self):
        self.on_R_Dialog_close(None,None)
        
        # Destroy the dialog to embed the detached R console:
        self.Detached_R_Dialog.destroy()
        self.Detached_R_Dialog = None

    def on_R_Dialog_close(self,data1,data2):
        if data1 != None or data2 != None:
            self.on_R_attach(None)
        R_icon = Gtk.Image()
        R_icon.set_from_file(self.datadir+"/Rgedit-icon24.png")
        self.bottom_panel_dummy_hbox = Gtk.HBox()
        self.bottom_panel_dummy_hbox.show()
        self.R_widget.reparent(self.bottom_panel_dummy_hbox)
        self._window.get_bottom_panel().add_item(self.bottom_panel_dummy_hbox,"R Console",_("R Console"),R_icon)
        self._window.get_bottom_panel().set_property("visible",True)
        self._window.get_bottom_panel().activate_item(self.bottom_panel_dummy_hbox)
        
    def on_R_Dialog_configure(self,widget,event):
        #self._plugin.prefs['RConsole_detached_x'] = event.x
        #self._plugin.prefs['RConsole_detached_y'] = event.y
        #self._plugin.prefs['RConsole_detached_width'] = event.width
        #self._plugin.prefs['RConsole_detached_height'] = event.height
        self._plugin.prefs['RConsole_detached_x'], self._plugin.prefs['RConsole_detached_y'] = self.Detached_R_Dialog.get_position()
        self._plugin.prefs['RConsole_detached_width'], self._plugin.prefs['RConsole_detached_height'] = self.Detached_R_Dialog.get_size()
        # Ugly hack due to the fact that for some reason I am not notified when gedit is closed...
        self._plugin.save_prefs()
        #print "R_Dialog_configure"
        
    def _remove_menu(self):
        # Get the GtkUIManager
        manager = self._window.get_ui_manager()

        # Remove the ui
        manager.remove_ui(self._ui_id)

        # Remove the action group
        manager.remove_action_group(self._action_group)

        # Make sure the manager updates
        manager.ensure_update()

    def update_ui(self):
        self._action_group.set_sensitive(self._window.get_active_document() != None)







class RCtrlPlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = "RCtrlPlugin"

    window = GObject.property(type=Gedit.Window)

    # The plugin preferences:
    prefs = {
        'autostart_R_console'   : True,   # should the R console in the panel start automatically?
        'max_lines_as_text'     : 20,   # the number of lines to send selection as text
        'echo_commands'         : True, # should commands sent to R through source() be echoed in the R console?
        'HTML_help'             : True, # use HTML help?
        'advance_to_next_line'  : True, # advance to next line after sending current line to R?
        'allow_bold'            : True,
        'audible_bell'          : False,
        'background1'            : "white",
        'foreground1'            : "black",
        'prompt_color1'          : None,
        'background2'            : "white",
        'foreground2'            : "black",
        'prompt_color2'          : None,
        'background3'            : "white",
        'foreground3'            : "black",
        'prompt_color3'          : None,
        'tab_name_in_prompt'    : True,
        'backspace_binding'     : 'ascii-del',
        'cursor_blink'          : 'system',  # system, on, off
        'cursor_shape'          : 'block',   # block, ibeam, underline
        'emulation'             : 'xterm',
        'font_name'             : 'Monospace 8',
        'scroll_on_keystroke'   : True,
        'scroll_on_output'      : True,
        'scrollback_lines'      : 5000,
        'visible_bell'          : False,
        'word_chars'            : '-A-Za-z0-9,./?%&#:_',
        'show_run_line'         : True,
        'show_run_sel'          : True,
        'show_run_all'          : True,
        'show_run_cursor'       : True,
        'show_run_block1'       : True,
        'show_def_block1'       : True,
        'show_run_block2'       : True,
        'show_def_block2'       : True,
        'show_new_tab'          : True,
        'shortcut_RCtrlLine'    : '<Ctrl><Shift>R', # user-definible keyboard shortcuts
        'shortcut_RCtrlSel'     : '<Ctrl><Shift>E',
        'shortcut_RCtrlAll'     : None,
        'shortcut_RCtrlCursor'  : None,
        'shortcut_RCtrlBlock1Run' : '<Ctrl><Shift>F1',
        'shortcut_RCtrlBlock1Def' : None,
        'shortcut_RCtrlBlock2Run' : '<Ctrl><Shift>F2',
        'shortcut_RCtrlBlock2Def' : None,
        'shortcut_RCtrlNewTab'  : None,
        'shortcut_RCtrlConfig'  : None,
        'shortcut_RCtrlLoadWorkspace' : None,
        'shortcut_RCtrlSaveWorkspace' : None,
        #'shortcut_RCtrlHelpSel' : '<Ctrl><Shift>H',
        #'shortcut_RCtrlShowSel' : None,
        #'shortcut_RCtrlEditSel' : None,
        'shortcut_RCtrlAttach'  : None,
        'shortcut_RCtrlClose'   : None,
        'RConsole_start_attached' : False,
        'RConsole_detached_x'      : -1,
        'RConsole_detached_y'      : -1,
        'RConsole_detached_width'  : -1,
        'RConsole_detached_height' : -1,
        'skip_empty_and_comment_lines' : True,
        'autostart_R_script'      : False,
        'autostart_R_script_path' : None,
        'R_structure_enabled' : True,
        'R_structure_landmarks' : True,
        'R_structure_functions' : True,
        'R_structure_dataframes' : True,
        'use_current_document_directory' : True,
        'R_console_tab_pos' : int(Gtk.PositionType.RIGHT),
        'R_console_always_show_tabs' : False,
        'R_console_Ctrl_C_4_copy' : True,
        'R_console_Ctrl_Q_break' : True,
        'R_console_Escape_break' : True,
        'show_messages_and_warnings' : True,
        'show_rgedit_UI_only_for_R_mime_types' : True,
        'use_rgedit_code_folding' : True,
        'code_folding_block_preference' : 'highest_block',
        'profiles' : [ 
                       { # The built-in profile:
                         'name':'built-in',                         # The profile's name
                         'cmd':'R --no-save --no-restore',             # The command 
                         'local':True,                                 # Is the profile local? (should we assume access to local resources?)
                         'default':True,                             # Is this the default profile? (there can be only one!)
                         'setwd':'setwd(%s)',                         # The command used to change the working folder (the only parameter is the folder's name)
                         'init-script':True,                        # Should the init script be called (this is specific for R and in the case of remote shells might not be available on the remote host)
                         'help-type':'HTML',                          # Help type; can be 'HTML', 'Text', 'Default' or 'Custom' (in which case the next must be given)
                         'help-custom-command':None,                #    - in case a custom help type this must be given
                         'prompt':'> ',                                # The prompt symbol
                         'prompt-cmd':'options( prompt="%s" )',        # The prompt-setting command
                         'continue':'+ ',                            # The prompt continuation symbol
                         'continue-cmd':'options( continue="%s" )',    # The prompt-continuation-setting command
                         'source-cmd':'source("%s",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE)',    # The source command (taking as parameter the file name): if no such thing, use None
                         'quit-cmd':'q()',                            # The command for quitting
                         'comment':'#'                                # The character(s) used for commenting a line
                       },
                       { # Octave:
                         'name':'Octave', 
                         'cmd':'octave', 
                         'local':True, 
                         'default':False, 
                         'setwd':'chdir %s', 
                         'init-script':False, 
                         'help-type':'Default',
                         'help-custom-command':None,
                         'prompt':'> ',
                         'prompt-cmd':'PS1( "%s" )',
                         'continue':'+ ',
                         'continue-cmd':'PS2( "%s" )',
                         'source-cmd':'source("%s")',
                         'quit-cmd':'quit',
                         'comment':'#'
                       },
                       { # Python:
                         'name':'Python', 
                         'cmd':'python', 
                         'local':True, 
                         'default':False, 
                         'setwd':'import os; os.chdir(%s)', 
                         'init-script':False, 
                         'help-type':'Default',
                         'help-custom-command':None,
                         'prompt':'',
                         'prompt-cmd':None,
                         'continue':'',
                         'continue-cmd':None,
                         'source-cmd':'execfile("%s")',
                         'quit-cmd':'quit()',
                         'comment':'#'
                       },
                       { # Remote (chained ssh):
                         'name':'R/SSH', 
                         'cmd':'ssh -X -t user@host1 ssh -X -t host2 "R --no-save --no-restore"', 
                         'local':False, 
                         'default':False, 
                         'setwd':None, 
                         'init-script':True, 
                         'help-type':'Text',
                         'help-custom-command':None,
                         'prompt':'> ',
                         'prompt-cmd':'options( prompt="%s" )',
                         'continue':'+ ',
                         'continue-cmd':'options( continue="%s" )',
                         'source-cmd':None,
                         'quit-cmd':'q()',
                         'comment':'#'
                       }
                     ]
    }

    def __init__(self):
        GObject.Object.__init__(self)
        self.id_name = 'RCtrlPlugin'
        self._instances = {}
        
        ## Localization:
        #translation_stuff = gettext.translation('RCtrl', self.get_data_dir() + "/RCtrl/Translations/")
        #_ = translation_stuff.lgettext

        ###############
        # TESTS for profiles!
        #print "Testing profiles..."
        #print "Get default profile:" + str( self.get_default_profile() )
        #print "Add new default profile:" + str( self.add_profile([ 'maka', 'R --no-save --no-restore', True, True ]) )
        #print self.prefs['profiles']
        #print "Get default profile:" + str( self.get_default_profile() )
        #print "Remove profile test1:" + str( self.remove_profile( 'octave' ) )
        #print self.prefs['profiles']
        #print "Remove profile maka:" + str( self.remove_profile( 'maka' ) )
        #print self.prefs['profiles']
        ###############
            
        # Load the saved preferences:
        try:
            pref_file = open(os.path.expanduser("~/.rgedit-preferences"),"rb")
            saved_prefs = pickle.load(pref_file)
            pref_file.close()
            for i in list(self.prefs.keys()):
                if i in saved_prefs:
                    self.prefs[i] = saved_prefs[i]
            #close(pref_file)
        except: # (pickle.PickleError, pickle.PicklingError, pickle.UnpicklingError):
            print("Cannot load saved rgedit prefs: using the defaults!")
            pass
            
        # Checks:
        if self.prefs['autostart_R_script_path'] == None:
            self.prefs['autostart_R_script'] = False
        if self.get_profile('built-in') is None:
            # The build-in profile MUST exist!
            self.add_profile({ 
                               'name':'built-in', 
                               'cmd':'R --no-save --no-restore', 
                               'local':True, 
                               'default':False, 
                               'setwd':'setwd(%s)', 
                               'init-script':True,
                               'help-type':'HTML',
                               'help-custom-command':None,
                               'prompt':'> ',    
                               'prompt-cmd':'options( prompt="%s" )',
                               'continue':'+ ',
                               'continue-cmd':'options( continue="%s" )',
                               'source-cmd':'source("%s",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE)',
                               'quit-cmd':'q()',
                               'comment':'#'
                             })
            if self.get_default_profile() == None:
                self.set_default_profile('built-in')
            
        # There are some special shortcuts of potential interest, esp. modifiers of ENTER:
        self.check_special_shortcuts()
            
        ## Context menu stuff:
        #self.window = None
        
        # rgedit-specific UI elements:
        self.show_gedit_UI = True
        
        # code folding engine:
        self.code_folding_engine = RCodeFolding(self.get_data_dir(),self,self.prefs['use_rgedit_code_folding'])

        # UI hack to allow toolbutton with arrow and menu:
        self.RCtrlNewTab_toolarrow = None
    
    def list_profiles_names(self):
        # Return the list of all profiles' names:
        ret_val = []
        for p in self.prefs['profiles']:
            ret_val += [p['name']]
        return ret_val
    
    def get_default_profile(self):
        # Return the current profile (and check for multiple default profiles):
        def_prof = None
        no_def_prof = 0
        for p in self.prefs['profiles']:
            if p['default'] == True:
                def_prof = p
                no_def_prof = no_def_prof + 1
        if no_def_prof == 0:
            print("Profile management: there's no default profile!")
            return None
        elif no_def_prof > 1:
            print("Profile management: there's more than one default profile!")
            return None
        return def_prof
        
    def set_default_profile(self,prof_name):
        # Set the default profile (if found) making sure all the others are reset:
        if self.get_profile(prof_name) == None:
            print("Profile management: cannot find profile '" + str(prof_name) + "' to make default!")
            return False
        for p in self.prefs['profiles']:
            if p['name'] == prof_name:
                p['default'] = True
            else:
                p['default'] = False
        return True
        
    def get_profile(self,prof_name):
        # Get the profile (if found):
        for p in self.prefs['profiles']:
            if p['name'] == prof_name:
                return p
        return None
        
    def add_profile(self,profile):
        # Add a new profile (and check for conflicts):
        if len(profile) != 5:
            print("Profile management: illegal profile '" + str(profile) + "'!")
            return False
        for p in self.prefs['profiles']:
            if p['name'] == profile['name']:
                print("Profile management: duplicated profile '" + str(profile) + "'!")
                return False
        # Add it:
        self.prefs['profiles'] = self.prefs['profiles'] + [profile]
        # Is this meant to be default? Then make it so:
        if profile[3] == True:
            return self.set_default_profile( profile['name'] )
        return True
        
    def remove_profile(self,profile_name):
        # Remove an existing profile:
        for p in self.prefs['profiles']:
            if p['name'] == profile_name:
                was_default = p['default']
                self.prefs['profiles'].remove( p )
                if was_default:
                    self.set_default_profile( 'built-in' )
                return True
        return False
         
    def get_profile_attribute(self,profile_name,key):
        # Retrieve the profile's key (if defined):
        if profile_name is None:
            profile = self.get_default_profile()
        else:
            profile = self.get_profile(profile_name)
        if profile is None:
            print("Cannot retrieve profile '" + str(profile_name) + "'!")
            return None
        # Return the key:
        return profile[key]
       
        
    def check_special_shortcuts(self):
        # There are some special shortcuts of potential interest, esp. modifiers of ENTER,
        # for runing the current line, block, all files, etc...
        self.special_shortcut_RCtrlSel       = [None,None]
        self.special_shortcut_RCtrlLine      = [None,None]
        self.special_shortcut_RCtrlAll       = [None,None]
        self.special_shortcut_RCtrlCursor    = [None,None]
        self.special_shortcut_RCtrlBlock1Run = [None,None]
        self.special_shortcut_RCtrlBlock2Run = [None,None]
            
        # Set the possible modifiers (Control Shift and Alt):
        self.possible_modifiers = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
        
        key, modifier = Gtk.accelerator_parse(str(self.prefs['shortcut_RCtrlSel']))
        if key != 0 and Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlSel = ["return",modifier]
            
        key, modifier = Gtk.accelerator_parse(str(self.prefs['shortcut_RCtrlLine']))
        if key != 0 and Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlLine = ["return",modifier]
            
        key, modifier = Gtk.accelerator_parse(str(self.prefs['shortcut_RCtrlAll']))
        if key != 0 and Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlAll = ["return",modifier]
            
        key, modifier = Gtk.accelerator_parse(str(self.prefs['shortcut_RCtrlCursor']))
        if key != 0 and Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlCursor = ["return",modifier]
            
        key, modifier = Gtk.accelerator_parse(str(self.prefs['shortcut_RCtrlBlock1Run']))
        if key != 0 and Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlBlock1Run = ["return",modifier]
            
        key, modifier = Gtk.accelerator_parse(self.prefs['shortcut_RCtrlBlock2Run'])
        if Gdk.keyval_name(key).lower() == "return":
            self.special_shortcut_RCtrlBlock2Run = ["return",modifier]
        
    def get_data_dir(self):
        try:
            return gedit.Plugin.get_data_dir(self)
        except:
            return self.get_data_directory()

    def get_data_directory(self):
        if platform.platform() == 'Windows':
            return os.path.expanduser('~/gedit/plugins/RCtrl')
        else:
            return os.path.expanduser('~/.local/share/gedit/plugins/RCtrl')       

    def do_activate(self):
        self._instances[self.window] = RCtrlWindowHelper(self, self.window)
        
        handler_ids = []
        for signal in ('tab-added', 'tab-removed', 'active-tab-changed'):
            method = getattr(self, 'on_window_' + signal.replace('-', '_'))
            handler_ids.append(self.window.connect(signal, method))
        self.window.set_data(self.id_name, handler_ids)

        for view in self.window.get_views():
            self.connect_view(view,self._instances[self.window])

        for doc in self.window.get_documents():
            self.connect_document(doc,self.window)
 
    def do_deactivate(self):
        pass

    def do_update_state(self):
        pass

    def connect_view(self, view, rctrlwindowhelper):
        handler_id = view.connect('populate-popup', self.on_view_populate_popup, rctrlwindowhelper)
        view.set_data(self.id_name, [handler_id])
        
        # Key press dispatcher for processing the shortcuts:
        handler_id = view.connect('key_press_event', self.on_view_key_press_event, rctrlwindowhelper)
        
        # Tooltips within the view:
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            view.props.has_tooltip = True
            view.connect("query-tooltip", self.query_tooltip_text_view) #, tag)
        
    def on_window_tab_added(self, window, tab):
        self.connect_view(tab.get_view(),self._instances[window])
        
        doc = tab.get_document()
        handler_id = doc.get_data(self.id_name)
        if handler_id is None:
            self.connect_document(doc,window)

    def on_window_active_tab_changed(self, window, tab):
        #self._instances[window]._rstructurepanel.on_force_refresh(None)

        self.show_hide_toolbar_and_friends(tab.get_document())
        
    def on_window_tab_removed(self, window, tab):
        pass
        
    def is_document_R_source_file(self,doc):
        # Decide if this document is indeed an R source file:
        if not self.prefs['show_rgedit_UI_only_for_R_mime_types']:
            return True
        else:
            doc_language = doc.get_language()
            return (doc_language != None and doc_language.get_name().upper() == "R")
    
    def show_hide_toolbar_and_friends(self,doc):
        # Show/hide the rgedit-specific UI elements given the current document's mimetype:
        if doc == None:
            return
        self.show_gedit_UI = False
        
        # Decide if this document is indeed an R source file:
        if self.is_document_R_source_file(doc):
            self.show_gedit_UI = True
            
        # Show or hide the rgedit UI stuff as required:
        # Get the GtkUIManager
        manager = self.window.get_ui_manager()
        if manager == None:
            return

        RCtrlSel_toolitem = manager.get_widget("/ToolBar/RCtrlSel")
        RCtrlLine_toolitem = manager.get_widget("/ToolBar/RCtrlLine")
        RCtrlAll_toolitem = manager.get_widget("/ToolBar/RCtrlAll")
        RCtrlCursor_toolitem = manager.get_widget("/ToolBar/RCtrlCursor")
        RCtrlBlock1Run_toolitem = manager.get_widget("/ToolBar/RCtrlBlock1Run")
        RCtrlBlock1Def_toolitem = manager.get_widget("/ToolBar/RCtrlBlock1Def")
        RCtrlBlock2Run_toolitem = manager.get_widget("/ToolBar/RCtrlBlock2Run")
        RCtrlBlock2Def_toolitem = manager.get_widget("/ToolBar/RCtrlBlock2Def")
        #RCtrlNewTab_toolitem = manager.get_widget("/ToolBar/RCtrlNewTab")
        
        if self.show_gedit_UI == False:
            # Go hide them all:
            RCtrlLine_toolitem.hide()
            RCtrlSel_toolitem.hide()
            RCtrlAll_toolitem.hide()
            RCtrlCursor_toolitem.hide()
            RCtrlBlock1Run_toolitem.hide()
            RCtrlBlock1Def_toolitem.hide()
            RCtrlBlock2Run_toolitem.hide()
            RCtrlBlock2Def_toolitem.hide()
            #RCtrlNewTab_toolitem.hide()
            if self.RCtrlNewTab_toolarrow != None:
                self.RCtrlNewTab_toolarrow.hide()
        else:
            # Restore the UI elements as defined by the user:
            if self.prefs['show_run_sel']:
                RCtrlSel_toolitem.show()
            if self.prefs['show_run_line']:
                RCtrlLine_toolitem.show()
            if self.prefs['show_run_all']:
                RCtrlAll_toolitem.show()
            if self.prefs['show_run_cursor']:
                RCtrlCursor_toolitem.show()
            if self.prefs['show_run_block1']:
                RCtrlBlock1Run_toolitem.show()
            if self.prefs['show_def_block1']:
                RCtrlBlock1Def_toolitem.show()
            if self.prefs['show_run_block2']:
                RCtrlBlock2Run_toolitem.show()
            if self.prefs['show_def_block2']:
                RCtrlBlock2Def_toolitem.show()
            if self.prefs['show_new_tab']:
                #RCtrlNewTab_toolitem.show()
                self.RCtrlNewTab_toolarrow.show()

    def save_prefs(self):
        try:
            pref_file = open(os.path.expanduser("~/.rgedit-preferences"),"wb")
            pickle.dump(self.prefs,pref_file)
            pref_file.close()
        except:
            print("Error saving preferences...")
            pass
        

    def prompt_string(self,tab_number,tab_name,tab_profile_name):
        # Given the prompt settings, produce the appropriate R commands
        prompt_string = ""
        continue_string = ""
        xterm_color = self.xterm_16_color_from_string(self.prefs['prompt_color'+str(tab_number)])
        if xterm_color != "":
            # Add the color bits:
            prompt_string = prompt_string + "\\x1b" + xterm_color
            continue_string = continue_string + "\\x1b" + xterm_color
        if self.prefs['tab_name_in_prompt'] == True:
            # Add an extra character at the begining of the prompt to make it more obvious:
            prompt_string = prompt_string + tab_name
            continue_string = continue_string + tab_name
        # Add the middle of the prompt:
        prompt_string = prompt_string + self.get_profile_attribute(tab_profile_name,'prompt')
        continue_string = continue_string + self.get_profile_attribute(tab_profile_name,'continue') 
        # and the final part (if any):
        if xterm_color != "":
            prompt_string = prompt_string + "\\x1b[33;0m"
            continue_string = continue_string + "\\x1b[33;0m"

        # Concate all these to get the full R code:
        if self.get_profile_attribute(tab_profile_name,'prompt-cmd') != None and self.get_profile_attribute(tab_profile_name,'continue-cmd') != None:
            cmd  = (self.get_profile_attribute(tab_profile_name,'prompt-cmd')   % prompt_string) + ';'
            cmd += (self.get_profile_attribute(tab_profile_name,'continue-cmd') % continue_string) + ';'
            cmd += '\n' # make sure it ends in newline
        else:
            cmd = ''
        return cmd

    def xterm_16_color_from_string(self,color_name):
        # Get the appropriate xterm escape sequence for the named color (if any):
        xterm_colors = {
            'black'    : '[1;30m',
            'red'      : '[1;31m',
            'green'    : '[1;32m',
            'yellow'   : '[1;33m',
            'blue'     : '[1;34m',
            'magenta'  : '[1;35m',
            'cyan'     : '[1;36m',
            'white'    : '[1;37m'
        }
        if color_name in xterm_colors:
            return xterm_colors[color_name]
        else:
            return ""

    def xterm_color_to_index(self,color_name):
        # Get the appropriate xterm escape sequence for the named color (if any):
        xterm_colors = {
            'black'    : 0,
            'red'      : 1,
            'green'    : 2,
            'yellow'   : 3,
            'blue'     : 4,
            'magenta'  : 5,
            'cyan'     : 6,
            'white'    : 7
        }
        if color_name == None:
            return 0
        elif color_name in xterm_colors:
            return xterm_colors[color_name]+1
        else:
            return -1

    def xterm_color_from_index(self,color_index):
        # Get the appropriate xterm escape sequence for the named color (if any):
        xterm_colors = {
            0          :'black',
            1          :'red',
            2          :'green',
            3          :'yellow',
            4          :'blue',
            5          :'magenta',
            6          :'cyan',
            7          :'white'
        }
        if color_index == 0:
            return None
        elif color_index in xterm_colors:
            return xterm_colors[color_index-1]
        else:
            return None


    def on_view_populate_popup(self, view, menu, rctrlwindowhelper):
        doc = view.get_buffer()
        if doc == None:
            return False
        
        # Get the iterator where the right click happened in the view:
        x, y = view.get_pointer()
        x, y = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
        cur_pos_iterator = view.get_iter_at_location(x, y)

        # The Wizards context menu:
        wizardmenu = Gtk.ImageMenuItem()
        wizardmenu.set_label(_("Wizards"))
        #wizardmenu.set_image(Gtk.Image.new_from_stock(Gtk.STOCK_OPEN, Gtk.IconSize.MENU))
        wizardmenu.connect('activate', self.on_context_menu_wizard);
        wizardmenu.show();
        
        rctrlwindowhelper.fill_in_wizards_menu( wizardmenu )
        
        # The Landmark Comment menu entry:
        landmarkmenu = Gtk.ImageMenuItem()
        landmarkmenu.set_label(_("Insert Landmark Comment"))
        menu_icon = Gtk.Image()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.get_data_dir()+"/landmark_comment.png",16,16)
        menu_icon.set_from_pixbuf(pixbuf)
        menu_icon.show()
        landmarkmenu.set_image(menu_icon)
        landmarkmenu.connect('activate', self.on_context_menu_landmark, doc);
        landmarkmenu.show();

        separator = Gtk.SeparatorMenuItem()
        separator.show();
        
        # The code folding menu entries:
        if self.prefs['use_rgedit_code_folding']:
            if self.code_folding_engine.is_folded(doc,cur_pos_iterator):
                menu_name = _("Unfold code on current line")
                menu_handler = self.on_context_menu_unfold_code
            else:
                menu_name = _("Fold block containg current line")
                menu_handler = self.on_context_menu_fold_containing_block
            curlinefoldingmenu = Gtk.ImageMenuItem()
            curlinefoldingmenu.set_label(menu_name)
            menu_icon = Gtk.Image()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.get_data_dir()+"/folded_code.png",16,16)
            menu_icon.set_from_pixbuf(pixbuf)
            menu_icon.show()
            curlinefoldingmenu.set_image(menu_icon)
            curlinefoldingmenu.connect('activate', menu_handler, doc, view, cur_pos_iterator);
            curlinefoldingmenu.show();

            inspectfoldedcodemenu = None
            if self.code_folding_engine.is_folded(doc,cur_pos_iterator):
                menu_name = _("Inspect folded code...")
                menu_handler = self.on_context_menu_inspect_folded_code
                inspectfoldedcodemenu = Gtk.ImageMenuItem(menu_name)
                menu_icon = Gtk.Image()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.get_data_dir()+"/folded_code.png",16,16)
                menu_icon.set_from_pixbuf(pixbuf)
                menu_icon.show()
                inspectfoldedcodemenu.set_image(menu_icon)
                inspectfoldedcodemenu.connect('activate', menu_handler, doc, view, cur_pos_iterator);
                inspectfoldedcodemenu.show();
            
            selectionfoldingmenu = None
            if self.code_folding_engine.is_selection(doc):
                selectionfoldingmenu = Gtk.ImageMenuItem(_("Fold current selection"))
                menu_icon = Gtk.Image()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.get_data_dir()+"/folded_code.png",16,16)
                menu_icon.set_from_pixbuf(pixbuf)
                menu_icon.show()
                selectionfoldingmenu.set_image(menu_icon)
                selectionfoldingmenu.connect('activate', self.on_context_menu_fold_selection, doc, view);
                selectionfoldingmenu.show();

            unfoldallgmenu = Gtk.ImageMenuItem()
            unfoldallgmenu.set_label(_("Unfold all folded code"))
            menu_icon = Gtk.Image()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.get_data_dir()+"/folded_code.png",16,16)
            menu_icon.set_from_pixbuf(pixbuf)
            menu_icon.show()
            unfoldallgmenu.set_image(menu_icon)
            unfoldallgmenu.connect('activate', self.on_context_menu_unfold_all, doc, view);
            unfoldallgmenu.show();

            separator2 = Gtk.SeparatorMenuItem()
            separator2.show();

            menu.prepend(separator2)
            menu.prepend(unfoldallgmenu)
            if selectionfoldingmenu:
                menu.prepend(selectionfoldingmenu)
            if inspectfoldedcodemenu:
                menu.prepend(inspectfoldedcodemenu)
            menu.prepend(curlinefoldingmenu)
            
        menu.prepend(separator)
        menu.prepend(wizardmenu)
        menu.prepend(landmarkmenu)
        return True
        
    def on_view_key_press_event(self, widget, event, rctrlwindowhelper):
        # Process the special shortcuts (if any) before gedit has any chance:
        event_key = Gdk.keyval_name(event.keyval).lower()
        event_modifiers = (event.get_state() & self.possible_modifiers)

        # Process Ctrl+Tab:
        if event_key == "tab" and event_modifiers == Gdk.ModifierType.CONTROL_MASK:
            if rctrlwindowhelper.R_widget != None:
                rctrlwindowhelper.R_widget.grab_focus()
            return True
        else:
            return False
        
        # Old studd processed elsewhere now:
        if (self.special_shortcut_RCtrlSel[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlSel[1]):
            rctrlwindowhelper.on_send_selection_to_R(None)
            return True

        if (self.special_shortcut_RCtrlLine[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlLine[1]):
            rctrlwindowhelper.on_send_line_to_R(None,None)
            return True

        if (self.special_shortcut_RCtrlAll[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlAll[1]):
            rctrlwindowhelper.on_send_file_to_R(None)
            return True

        if (self.special_shortcut_RCtrlCursor[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlCursor[1]):
            rctrlwindowhelper.on_send_cursor_to_R(None)
            return True

        if (self.special_shortcut_RCtrlBlock1Run[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlBlock1Run[1]):
            rctrlwindowhelper.on_send_block1_to_R(None)
            return True

        if (self.special_shortcut_RCtrlBlock2Run[0] == event_key) and (event_modifiers == self.special_shortcut_RCtrlBlock2Run[1]):
            rctrlwindowhelper.on_send_block2_to_R(None)
            return True

        return False
        
    def query_tooltip_text_view(self, view, x, y, keyboard_tip, tooltip):
        # DEBUG
        return False
        
        if not view.props.has_tooltip:
            return False
            
        if keyboard_tip:
            offset = view.props.buffer.cursor_position
            position_iter = view.props.buffer.get_iter_at_offset(offset)
        else:
            coords = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
            position_iter = view.get_iter_at_location(coords[0], coords[1])
            
        # Ask the code folding engine to provide some tooltip for this position (if any):
        do_tooltip,tooltip_text = self.code_folding_engine.get_tooltip(view, view.props.buffer, position_iter)
        if do_tooltip == True:
            tooltip.set_text(tooltip_text)
            return True
        return False

    def connect_document(self, doc, window):
        handler_id = doc.connect("saved", self.on_document_saved, window)
        handler_id = doc.connect("loaded", self.on_document_loaded, window)
        doc.set_data(self.id_name, [handler_id])

    def on_window_tab_added(self, window, tab):
        self.connect_view(tab.get_view(),self._instances[window])
        
        doc = tab.get_document()
        handler_id = doc.get_data(self.id_name)
        if handler_id is None:
            self.connect_document(doc,window)

    def on_window_active_tab_changed(self, window, tab):
        self._instances[window]._rstructurepanel.on_force_refresh(None)

        self.show_hide_toolbar_and_friends(tab.get_document())
        
    def on_window_tab_removed(self, window, tab):
        pass
        
    def on_document_saved(self, doc, ignore1, window):
        self._instances[window]._rstructurepanel.on_force_refresh(None)
        
        self.show_hide_toolbar_and_friends(doc)

    def on_document_loaded(self, doc, ignore1, window):
        self._instances[window]._rstructurepanel.on_force_refresh(None)
        
        self.show_hide_toolbar_and_friends(doc)
    
    def on_context_menu_unfold_all(self, menu_item, doc, view):
        self.code_folding_engine.unfold_all(doc,view) 
        return True
    
    def on_context_menu_unfold_code(self, menu_item, doc, view, cur_pos_iterator):
        self.code_folding_engine.unfold(doc,view,cur_pos_iterator)
        return True
        
    def on_context_menu_inspect_folded_code(self, menu_item, doc, view, cur_pos_iterator):
        self.code_folding_engine.inspect_folded_code(doc,view,cur_pos_iterator)
        return True
        
    def on_context_menu_fold_containing_block(self, menu_item, doc, view, cur_pos_iterator):
        self.code_folding_engine.fold_containing_block(doc,view,cur_pos_iterator) 
        return True
        
    def on_context_menu_fold_selection(self, menu_item, doc, view):
        self.code_folding_engine.fold_selection(doc,view)
        return True

    def on_context_menu_wizard(self, menu_item):
        #print "Wirzad from context menu!"
        return True

    def on_context_menu_landmark(self, menu_item, doc):
        # Insert the landmark special comment at the beginning of the next line:
        if doc == None:
            # Nothing to do!
            return True
        # Get the cursor's location:
        cursor_iter = doc.get_iter_at_mark(doc.get_insert())
        # and go to the end of the line:
        if not cursor_iter.ends_line():
            cursor_iter.forward_to_line_end()
        # then insert a newline and the comment text:
        doc.insert(cursor_iter,str("\n")+landmark_comment_header+landmark_comment_placeholder)
        return True

    def create_configure_dialog(self):
        self.ui = create_UI_from_file_GtkBuilder_or_Glade(self.get_data_dir()+"/ConfigDialog.glade",self.get_data_dir()+"/ConfigDialog.ui")

        # Init the controls accordingly with the current options:
        check_box_autostart_R = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutostartR")
        check_box_autostart_R.set_active(self.prefs['autostart_R_console'])

        check_box_use_doc_dir = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"UseDocDirectory")
        check_box_use_doc_dir.set_active(self.prefs['use_current_document_directory'])

        check_box_show_message = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShowMessageCheck")
        check_box_show_message.set_active(self.prefs['show_messages_and_warnings'])

        check_box_attached_R = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"StartRAttached")
        check_box_attached_R.set_active(self.prefs['RConsole_start_attached'])

        check_box_autostart_script = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutostartScriptCheck")
        check_box_autostart_script.set_active(self.prefs['autostart_R_script'])

        if self.prefs['autostart_R_script_path'] != None:
            file_chooser_autostart_script = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutorunScriptPath")
            file_chooser_autostart_script.set_filename(self.prefs['autostart_R_script_path'])

        spin_max_lines_as_text = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"MaxLinesToSendSpin")
        spin_max_lines_as_text.set_range(0,50)
        spin_max_lines_as_text.set_increments(1,5)
        spin_max_lines_as_text.set_value(self.prefs['max_lines_as_text'])

        check_box_HTML_help = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"HTMLHelpCheck")
        check_box_HTML_help.set_active(self.prefs['HTML_help'])
        
        check_box_echo_commands = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"EchoPipedCommandsCheck")
        check_box_echo_commands.set_active(self.prefs['echo_commands'])
        
        check_box_advance_line = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AdvanceLineCheck")
        check_box_advance_line.set_active(self.prefs['advance_to_next_line'])

        check_box_skip_empty_and_comment = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"SkipEmptyAndCommentCheck")
        check_box_skip_empty_and_comment.set_active(self.prefs['skip_empty_and_comment_lines'])

        check_box_audible_bell = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AudibleBell")
        check_box_audible_bell.set_active(self.prefs['audible_bell'])
        
        check_box_visible_bell = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"VisibleBell")
        check_box_visible_bell.set_active(self.prefs['visible_bell'])
        
        check_box_scroll_on_keystroke = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollOnKeystroke")
        check_box_scroll_on_keystroke.set_active(self.prefs['scroll_on_keystroke'])
        
        check_box_scroll_on_output = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollOnOutput")
        check_box_scroll_on_output.set_active(self.prefs['scroll_on_output'])
        
        edit_scrollback_lines = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollbackLines")
        edit_scrollback_lines.set_text(str(self.prefs['scrollback_lines']))

        if self.prefs['cursor_blink'] == "system":
            radio_button_cursor_blink = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkSystem")
            radio_button_cursor_blink.set_active(True)
        elif self.prefs['cursor_blink'] == "on":
            radio_button_cursor_blink = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkOn")
            radio_button_cursor_blink.set_active(True)
        elif self.prefs['cursor_blink'] == "off":
            radio_button_cursor_blink = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkOff")
            radio_button_cursor_blink.set_active(True)

        if self.prefs['cursor_shape'] == "block":
            radio_button_cursor_shape = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeBlock")
            radio_button_cursor_shape.set_active(True)
        elif self.prefs['cursor_shape'] == "ibeam":
            radio_button_cursor_shape = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeIBeam")
            radio_button_cursor_shape.set_active(True)
        elif self.prefs['cursor_shape'] == "underline":
            radio_button_cursor_shape = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeUnderline")
            radio_button_cursor_shape.set_active(True)

        color_button_foreground1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor1")
        coltmp = Gdk.color_parse(self.prefs['foreground1'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_foreground1.set_color(coltmp)

        color_button_background1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor1")
        coltmp = Gdk.color_parse(self.prefs['background1'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_background1.set_color(coltmp)

        combo_box_prompt_color1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor1")
        liststore1 = Gtk.ListStore(GObject.TYPE_STRING)
        dynentries = [_("None"),_("Black"),_("Red"),_("Green"),_("Yellow"),_("Blue"),_("Magenta"),_("Cyan"),_("White")]
        for entry in dynentries:
            liststore1.append([entry])
        combo_box_prompt_color1.set_model(liststore1)
        cell1 = Gtk.CellRendererText()
        combo_box_prompt_color1.pack_start(cell1, True)
        combo_box_prompt_color1.add_attribute(cell1, 'text', 0)
        combo_box_prompt_color1.set_active(self.xterm_color_to_index(self.prefs['prompt_color1']))
        
        color_button_foreground2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor2")
        coltmp = Gdk.color_parse(self.prefs['foreground2'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_foreground2.set_color(coltmp)

        color_button_background2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor2")
        coltmp = Gdk.color_parse(self.prefs['background2'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_background2.set_color(coltmp)

        combo_box_prompt_color2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor2")
        liststore2 = Gtk.ListStore(GObject.TYPE_STRING)
        for entry in dynentries:
            liststore2.append([entry])
        combo_box_prompt_color2.set_model(liststore2)
        cell2 = Gtk.CellRendererText()
        combo_box_prompt_color2.pack_start(cell2, True)
        combo_box_prompt_color2.add_attribute(cell2, 'text', 0)
        combo_box_prompt_color2.set_active(self.xterm_color_to_index(self.prefs['prompt_color2']))
        
        color_button_foreground3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor3")
        coltmp = Gdk.color_parse(self.prefs['foreground3'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_foreground3.set_color(coltmp)

        color_button_background3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor3")
        coltmp = Gdk.color_parse(self.prefs['background3'])
        if isinstance(coltmp,tuple):
            coltmp = coltmp[1]
        color_button_background3.set_color(coltmp)

        combo_box_prompt_color3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor3")
        liststore3 = Gtk.ListStore(GObject.TYPE_STRING)
        for entry in dynentries:
            liststore3.append([entry])
        combo_box_prompt_color3.set_model(liststore3)
        cell3 = Gtk.CellRendererText()
        combo_box_prompt_color3.pack_start(cell3, True)
        combo_box_prompt_color3.add_attribute(cell3, 'text', 0)
        combo_box_prompt_color3.set_active(self.xterm_color_to_index(self.prefs['prompt_color3']))
        
        check_box_tab_name_in_prompt = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"TabNameInPrompt")
        check_box_tab_name_in_prompt.set_active(self.prefs['tab_name_in_prompt'])
        
        font_button = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"CurrentFont")
        font_button.set_font_name( self.prefs['font_name'] )

        self.dialog = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"RConfigDialog")

        #Create our dictionay and connect it
        dic = { "on_ButtonOk_clicked" : self.ButtonOk_clicked,
                "on_ButtonCancel_clicked" : self.ButtonCancel_clicked,
                "on_ChangeShortcuts_clicked" : self.ButtonChangeShortcuts_clicked,
                "on_SidePanelOptions_clicked" : self.ButtonSidePanelOptions_clicked,
                "on_CodeFoldingOptions_clicked" : self.ButtonCodeFoldingOptions_clicked,
                "on_EditProfiles_clicked" : self.EditProfiles_clicked,
                "on_MainWindow_destroy" : Gtk.main_quit }
        connect_signals_for_ui_GtkBuilder_or_Glade(self.ui,dic)

        return self.dialog

    def EditProfiles_clicked(self,widget):
        # Dynamically create a profile editing dialog using a list that contains all the dialogs with their columns:
        model = Gtk.ListStore(bool,str,str,bool,str,bool,str,str,str,str,str,str,str,str,str)
        tv = Gtk.TreeView(model)

        cell = Gtk.CellRendererToggle()
        #cell.connect("toggled", self.on_load_libraries_toggle, model)
        cell.set_property('activatable', True)
        cell.set_radio(True)
        cell.connect('toggled', self.toggle_profile, (model, 0))
        col = Gtk.TreeViewColumn("Default", cell, active=0)
        tv.append_column(col)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 1))
        rendererText.connect('editing-started', self.editing_profile, (model, 1))
        column = Gtk.TreeViewColumn("Name", rendererText, text=1)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 2))
        column = Gtk.TreeViewColumn("Command", rendererText, text=2)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)

        cell = Gtk.CellRendererToggle()
        #cell.connect("toggled", self.on_load_libraries_toggle, model)
        cell.set_property('activatable', True)
        cell.connect('toggled', self.toggle_profile, (model, 3))
        col = Gtk.TreeViewColumn("Local", cell, active=3)
        tv.append_column(col)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 4))
        column = Gtk.TreeViewColumn("Working folder", rendererText, text=4)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)

        cell = Gtk.CellRendererToggle()
        #cell.connect("toggled", self.on_load_libraries_toggle, model)
        cell.set_property('activatable', True)
        cell.connect('toggled', self.toggle_profile, (model, 5))
        col = Gtk.TreeViewColumn("Init script", cell, active=5)
        tv.append_column(col)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 6))
        column = Gtk.TreeViewColumn("Help type", rendererText, text=6)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 7))
        column = Gtk.TreeViewColumn("Help custom cmd", rendererText, text=7)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 8))
        column = Gtk.TreeViewColumn("Prompt", rendererText, text=8)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 9))
        column = Gtk.TreeViewColumn("Prompt cmd", rendererText, text=9)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 10))
        column = Gtk.TreeViewColumn("Continue", rendererText, text=10)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 11))
        column = Gtk.TreeViewColumn("Continue cmd", rendererText, text=11)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 12))
        column = Gtk.TreeViewColumn("Source cmd", rendererText, text=12)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 13))
        column = Gtk.TreeViewColumn("Quit cmd", rendererText, text=13)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        rendererText = Gtk.CellRendererText()
        rendererText.set_property('editable', True)
        rendererText.connect('edited', self.edited_profile, (model, 14))
        column = Gtk.TreeViewColumn("Comment", rendererText, text=14)
        column.set_resizable(True)
        #column.set_sort_column_id(0)    
        tv.append_column(column)
        
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            tv.set_tooltip_column(1)

        # Single selection mode:
        tv.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        # Fill in the profiles: 
        for l in self.list_profiles_names():
            profile = self.get_profile(l)  
            model.append([ self.profile_as_string(profile,'default'), 
                           self.profile_as_string(profile,'name'), 
                           self.profile_as_string(profile,'cmd'), 
                           self.profile_as_string(profile,'local'), 
                           self.profile_as_string(profile,'setwd'), 
                           self.profile_as_string(profile,'init-script'), 
                           self.profile_as_string(profile,'help-type'), 
                           self.profile_as_string(profile,'help-custom-command'), 
                           self.profile_as_string(profile,'prompt'), 
                           self.profile_as_string(profile,'prompt-cmd'), 
                           self.profile_as_string(profile,'continue'), 
                           self.profile_as_string(profile,'continue-cmd'), 
                           self.profile_as_string(profile,'source-cmd'),
                           self.profile_as_string(profile,'quit-cmd'), 
                           self.profile_as_string(profile,'comment')
                         ])
        
        # The actual dialog:
        dialog = Gtk.Dialog(_("Edit profiles"),None,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT ))
        dialog.set_default_size(800,200)
        help = Gtk.Button("Help")
        help.show()
        help.connect("clicked", self.help_profiles)
        dialog.action_area.pack_end(help, False, False, False) 
        
        label = Gtk.Label(_("  Please select on the profile you want to edit or delete, or add a new profile:  "))
        dialog.vbox.pack_start(label,False,True,False)
        label.show()
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.show()
        scrolled_window.set_sensitive(True)
        scrolled_window.add(tv)
        tv.show()
        scrolled_window.show()
        
        dialog.vbox.pack_start(scrolled_window,True,True,True)
        
        ## Profile manipulation buttons box:
        #profile_buttons_box = Gtk.HBox()
        #profile_buttons_box.show()
        
        add_profile_button = Gtk.Button("Add profile")
        add_profile_button.show()
        add_profile_button.connect("clicked", self.add_profile, tv)
        #profile_buttons_box.pack_end(add_profile_button, False, False) 
        dialog.action_area.pack_end(add_profile_button, False, False, False) 
        
        del_profile_button = Gtk.Button("Delete profile")
        del_profile_button.show()
        del_profile_button.connect("clicked", self.del_profile, tv)
        #profile_buttons_box.pack_end(del_profile_button, False, False) 
        dialog.action_area.pack_end(del_profile_button, False, False, False) 
        
        #dialog.vbox.pack_start(profile_buttons_box, True, False) 

        while True:
            response = dialog.run()
            if response == Gtk.ResponseType.ACCEPT:
                if self.update_profiles(tv) == True:
                    break
            else:
                break
        dialog.destroy() 
        
        # Force saving the profile:
        self.save_prefs()
        
        # Force rebuilding the profile menus for all windows:
        for window in list(self._instances.keys()):
            self._instances[window].create_or_update_profiles_menu(update_menus=True)
        
        return

    def add_profile(self,widget,tv):
        # Add a new profile to the list with default values:
        
        # Offer a selection of predefined profiles first:
        # The actual dialog:
        dialog = Gtk.Dialog(_("Profile templates"),None,Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT ))
        dialog.set_default_size(300,210)
        
        label = Gtk.Label(_("  Please select a profile template:  "))
        dialog.vbox.pack_start(label,False,True,False)
        label.show()
        
        # The templates:
        # R:
        template_R = Gtk.Button("R")
        template_R.show() 
        #                                                                              cmd                         local setwd        init-script help-type help-custom-command prompt prompt-cmd                continue continue-cmd                source-cmd                                                                     quit-cmd comment
        template_R.connect('clicked', self.add_profile_from_template, tv, dialog, 'R', 'R --no-save --no-restore', True, 'setwd(%s)', True,       'HTML',   '<None>',           '> ',  'options( prompt="%s" )', '+ ',    'options( continue="%s" )', 'source("%s",echo=TRUE,print.eval=TRUE,max.deparse.length=500000,local=TRUE)', 'q()',   '#')
        dialog.vbox.pack_start(template_R, expand=False, fill=False, padding=False)
        
        # Octave:
        template_Octave = Gtk.Button("Octave")
        template_Octave.show() 
        template_Octave.connect('clicked', self.add_profile_from_template, tv, dialog, 'Octave', 'octave', True, 'chdir %s', False, 'Default', '<None>', '> ', 'PS1( "%s" )', '+ ', 'PS2( "%s" )', 'source("%s")', 'quit', '#')
        dialog.vbox.pack_start(template_Octave, expand=False, fill=False, padding=False)
        
        # Python:
        template_Python = Gtk.Button("Python")
        template_Python.show() 
        template_Python.connect('clicked', self.add_profile_from_template, tv, dialog, 'Python', 'python', True, 'import os; os.chdir(%s)', False, 'Default', '<None>', '', '<None>', '', '<None>', 'execfile("%s")', 'quit()', '#')
        dialog.vbox.pack_start(template_Python, expand=False, fill=False, padding=False)
         
        # SSH'd R:
        template_SSH_R = Gtk.Button("R over SSH")
        template_SSH_R.show() 
        template_SSH_R.connect('clicked', self.add_profile_from_template, tv, dialog, 'R over SSH', 'ssh -X -t user@host1 ssh -X -t host "R --no-save --no-restore"', False, '<None>', True, 'Text', '<None>', '> ', 'options( prompt="%s" )', '+ ', 'options( continue="%s" )', '<None>', 'q()', '#')
        dialog.vbox.pack_start(template_SSH_R, expand=False, fill=False, padding=False)
       
        dialog.show()
        selected_template = dialog.run()
        dialog.destroy()
        if selected_template == Gtk.ResponseType.REJECT:
            return

    def add_profile_from_template(self,widget,tv,dialog,template_name,cmd,local,setwd,init_script,help_type,help_custom_command,prompt,prompt_cmd,continue_,continue_cmd,source_cmd,quit_cmd,comment):
        # Add a new profile to the list based on a template:
        # The model behind the tree:
        model = tv.get_model()
        if model is None:
            print("No model for profiles list!")
            return
        # Add a new row with default (build-in) values:
        default_profile = self.get_profile('built-in')
        model.append([ False,  # it's not created as default!
                       template_name + '_' + str(len(model)+1), # standardized temporary unique name
                       cmd, 
                       local, 
                       setwd, 
                       init_script, 
                       help_type, 
                       help_custom_command, 
                       prompt, 
                       prompt_cmd, 
                       continue_, 
                       continue_cmd, 
                       source_cmd,
                       quit_cmd, 
                       comment
                     ])
        dialog.destroy()

    def del_profile(self,widget,tv):
        # Add a new profile to the list with default values:
        # The model behind the tree:
        model = tv.get_model()
        if model is None:
            print("No model for profiles list!")
            return
        # Get the current selection (if any):
        sel = tv.get_selection().get_selected()
        if sel[1] is None:
            print("No selected profile: nothing to delete!")
            return
        if model[sel[1]][1] == "built-in":
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("The built-in profile cannot be deleted!") )
            question_dialog.run()
            question_dialog.destroy()
            return
        # Remove it:
        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO, _("Are you sure you want to delete this profile?") )
        response = question_dialog.run()
        question_dialog.destroy()
        if response == Gtk.ResponseType.YES:
            model.remove( sel[1] ) 
        
    def profile_as_string(self,profile,attribute_name):
        # Convert the attribute value to string taking into account the special case of None:
        if profile[attribute_name] is None:
            return '<None>'
        else:
            return profile[attribute_name]

    def edited_profile(self, cell, path, new_text, user_data):
        # One entry of one profile was modified:
        liststore, column = user_data
        if path == "0":
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("The built-in profile cannot be altered!") )
            question_dialog.run()
            question_dialog.destroy()
            return
        liststore[path][column] = new_text
        return

    def editing_profile(self, cell, editable, path, user_data):
        # One entry of one profile is about to be modified:
        return
        
        liststore, column = user_data
        #print liststore[path][1]
        if liststore[path][1] == "built-in":
            print("Cannot edit built_in")
            cell.stop_editing(True)
            return False
        return True

    def toggle_profile(self, cell, path, user_data):
        model, column = user_data
        if path == "0" and column != 0: # allow chaning the default status
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("The built-in profile cannot be altered!") )
            question_dialog.run()
            question_dialog.destroy()
            return
        if column is 0:
            # Radio buttons:
            for row in model:
                row[column] = False
            model[path][column] = True
        else:
            # Check boxes:
            model[path][column] = not model[path][column]
        return

    def help_profiles(self, widget):
        # Display the help:
        if not self.window is None:
            webbrowser.open(self._instances[self.window].datadir+"/Help/Help-profiles.html")

    def update_profiles(self, tv):
        # Re-build the profiles list from the info in the tree model:

        # The model behind the tree:
        model = tv.get_model()
        if model is None:
            print("No model for profiles list!")
            return False

        # Collect the profiles from the model, row by row, and do the sanity checks first:
        for row in model:
            # Parse and add this line to the profiles list:
            profile = self.parse_profile(row)
            if profile == None:
                # Sanity check failed!
                return False

        # Reset the profiles keeping only the buil-in:
        self.prefs['profiles'] = [self.prefs['profiles'][0]]
        # Collect the profiles from the model, row by row, and now record them:
        for row in model:
            # Parse and add this line to the profiles list:
            profile = self.parse_profile(row)
            if profile['name'] != 'built-in':
                self.prefs['profiles'].append(profile)
            else:
                self.prefs['profiles'][0]['default'] = profile['default']

        #print self.prefs['profiles']

        return True

    def parse_profile(self, row):
        # Parse the row and create a profile (if possible):
        profile = {
                    'name':row[1],
                    'cmd':row[2],
                    'local':row[3],
                    'default':row[0],
                    'setwd':row[4],
                    'init-script':row[5],
                    'help-type':row[6],
                    'help-custom-command':row[7],
                    'prompt':row[8],
                    'prompt-cmd':row[9],
                    'continue':row[10],
                    'continue-cmd':row[11],
                    'source-cmd':row[12],
                    'quit-cmd':row[13],
                    'comment':row[14]
                  }
        # Sanity checks, type conversions and special values:
        
        # name:
        if profile['name'] == None or profile['name'] == "":
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("The profile name cannot be empty!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # cmd:
        if profile['cmd'] == None or profile['cmd'] == "":
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("The command cannot be empty!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # No special requirements for local...
        
        # No special requirements for default...
        
        # setwd:
        if profile['setwd'] == None or profile['setwd'] == "" or profile['setwd'] == "<None>":
            profile['setwd'] = None
        elif profile['setwd'].find("%s") == -1:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("'setwd' must be either <None> or take a single string parameter '%s'!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # No special requirements for init-script...
        
        # help-type:
        if profile['help-type'].upper() == "HTML":
            profile['help-type'] = "HTML"
        elif profile['help-type'].upper() == "TEXT":
            profile['help-type'] = "Text"
        elif profile['help-type'].upper() == "DEFAULT":
            profile['help-type'] = "Default"
        elif profile['help-type'].upper() == "CUSTOM":
            profile['help-type'] = "Custom"
        else:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("'help-type' must be a one of 'HTML', 'Text', 'Default' or 'Custom'!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # help-custom-command:
        if profile['help-type'] == "Custom" and (profile['help-custom-command'] == None or profile['help-custom-command'] == "" or profile['setwd'] == "help-custom-command"):
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("If 'help-type' is 'Custom', then 'help-custom-command' must be given!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        else:
            profile['help-custom-command'] = None
        
        # No special requirements for prompt...
        
        # prompt-cmd:
        if profile['prompt-cmd'] == None or profile['prompt-cmd'] == "" or profile['prompt-cmd'] == "<None>":
            profile['prompt-cmd'] = None
        elif profile['prompt-cmd'].find("%s") == -1:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("'prompt-cmd' must be either <None> or take a single string parameter '%s'!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # No special requirements for continue...
        
        # continue-cmd:
        if profile['continue-cmd'] == None or profile['continue-cmd'] == "" or profile['continue-cmd'] == "<None>":
            profile['continue-cmd'] = None
        elif profile['continue-cmd'].find("%s") == -1:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("'continue-cmd' must be either <None> or take a single string parameter '%s'!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # source-cmd:
        if profile['source-cmd'] == None or profile['source-cmd'] == "" or profile['source-cmd'] == "<None>":
            profile['source-cmd'] = None
        elif profile['source-cmd'].find("%s") == -1:
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("'source-cmd' must be either <None> or take a single string parameter '%s'!") )
            question_dialog.run()
            question_dialog.destroy()
            return None
        
        # No special requirements for quit-cmd...
        
        # No special requirements for comment...

        return profile

    def ButtonOk_clicked(self,widget):
        # Make a copy of the old values to see what changed:
        old_prefs = self.prefs.copy()
        
        # Did the user define a color for any of the prompts?
        prompt_color_defined = False

        # Retrieve the data first:
        check_box_autostart_R = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutostartR")
        self.prefs['autostart_R_console'] = check_box_autostart_R.get_active()

        check_box_use_doc_dir = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"UseDocDirectory")
        self.prefs['use_current_document_directory'] = check_box_use_doc_dir.get_active()

        check_box_show_message = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShowMessageCheck")
        self.prefs['show_messages_and_warnings'] = check_box_show_message.get_active()

        check_box_attach_R = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"StartRAttached")
        self.prefs['RConsole_start_attached'] = check_box_attach_R.get_active()

        check_box_autostart_script = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutostartScriptCheck")
        self.prefs['autostart_R_script'] = check_box_autostart_script.get_active()

        file_chooser_autostart_script = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AutorunScriptPath")
        self.prefs['autostart_R_script_path'] = file_chooser_autostart_script.get_filename()
        if self.prefs['autostart_R_script_path'] == None:
            self.prefs['autostart_R_script'] = False

        spin_max_lines_as_text = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"MaxLinesToSendSpin")
        self.prefs['max_lines_as_text'] = spin_max_lines_as_text.get_value_as_int()

        check_box_HTML_help = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"HTMLHelpCheck")
        self.prefs['HTML_help'] = check_box_HTML_help.get_active()

        check_box_echo_commands = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"EchoPipedCommandsCheck")
        self.prefs['echo_commands'] = check_box_echo_commands.get_active()

        check_box_advance_line = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AdvanceLineCheck")
        self.prefs['advance_to_next_line'] = check_box_advance_line.get_active()

        check_box_skip_empty_and_comment = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"SkipEmptyAndCommentCheck")
        self.prefs['skip_empty_and_comment_lines'] = check_box_skip_empty_and_comment.get_active()

        check_box_audible_bell = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"AudibleBell")
        self.prefs['audible_bell'] = check_box_audible_bell.get_active()

        check_box_visible_bell = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"VisibleBell")
        self.prefs['visible_bell'] = check_box_visible_bell.get_active()

        check_box_scroll_on_keystroke = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollOnKeystroke")
        self.prefs['scroll_on_keystroke'] = check_box_scroll_on_keystroke.get_active()

        check_box_scroll_on_output = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollOnOutput")
        self.prefs['scroll_on_output'] = check_box_scroll_on_output.get_active()
        
        edit_scrollback_lines = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ScrollbackLines")
        try:
            no_lines = int(edit_scrollback_lines.get_text())
        except:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("The number of scrollback lines must be a positive integer!") )
            error_dialog.run()
            error_dialog.destroy()
            return
        if no_lines < 0:
            error_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("The number of scrollback lines must be a positive integer!") )
            error_dialog.run()
            error_dialog.destroy()
            return
        self.prefs['scrollback_lines'] = no_lines

        radio_button_cursor_blink_system = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkSystem")
        radio_button_cursor_blink_on = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkOn")
        radio_button_cursor_blink_off = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BlinkOff")
        if radio_button_cursor_blink_system.get_active():
            self.prefs['cursor_blink'] = "system"
        elif radio_button_cursor_blink_on.get_active():
            self.prefs['cursor_blink'] = "on"
        elif radio_button_cursor_blink_off.get_active():
            self.prefs['cursor_blink'] = "off"

        radio_button_cursor_shape_block = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeBlock")
        radio_button_cursor_shape_ibeam = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeIBeam")
        radio_button_cursor_shape_underline = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ShapeUnderline")
        if radio_button_cursor_shape_block.get_active():
            self.prefs['cursor_shape'] = "block"
        elif radio_button_cursor_shape_ibeam.get_active():
            self.prefs['cursor_shape'] = "ibeam"
        elif radio_button_cursor_shape_underline.get_active():
            self.prefs['cursor_shape'] = "underline"

        color_button_foreground1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor1")
        try:
            self.prefs['foreground1'] = color_button_foreground1.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['foreground1'] = gtk_gdk_Color_to_string(color_button_foreground1.get_color())

        color_button_background1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor1")
        try:
            self.prefs['background1'] = color_button_background1.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['background1'] = gtk_gdk_Color_to_string(color_button_background1.get_color())

        combo_box_prompt_color1 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor1")
        self.prefs['prompt_color1'] = self.xterm_color_from_index(combo_box_prompt_color1.get_active())
        
        color_button_foreground2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor2")
        try:
            self.prefs['foreground2'] = color_button_foreground2.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['foreground2'] = gtk_gdk_Color_to_string(color_button_foreground2.get_color())

        color_button_background2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor2")
        try:
            self.prefs['background2'] = color_button_background2.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['background2'] = gtk_gdk_Color_to_string(color_button_background2.get_color())

        combo_box_prompt_color2 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor2")
        self.prefs['prompt_color2'] = self.xterm_color_from_index(combo_box_prompt_color2.get_active())
        
        color_button_foreground3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"ForegroundColor3")
        try:
            self.prefs['foreground3'] = color_button_foreground3.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['foreground3'] = gtk_gdk_Color_to_string(color_button_foreground3.get_color())

        color_button_background3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"BackgroundColor3")
        try:
            self.prefs['background3'] = color_button_background3.get_color().to_string()
        except AttributeError:
            # Older gtk: Gdk.Color.to_string() is not defined: use my own:
            self.prefs['background3'] = gtk_gdk_Color_to_string(color_button_background3.get_color())

        combo_box_prompt_color3 = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"PromptColor3")
        self.prefs['prompt_color3'] = self.xterm_color_from_index(combo_box_prompt_color3.get_active())
        
        check_box_tab_name_in_prompt = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"TabNameInPrompt")
        self.prefs['tab_name_in_prompt'] = check_box_tab_name_in_prompt.get_active()
        
        font_button = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"CurrentFont")
        self.prefs['font_name'] = font_button.get_font_name()

        # Save the preferences:
        self.save_prefs()
        
        self.dialog.destroy()

        # See what changed:
        vte1_console_changed = False
        vte1_R_options_changed = False
        vte2_console_changed = False
        vte2_R_options_changed = False
        vte3_console_changed = False
        vte3_R_options_changed = False

        # The ones affecting all consoles:
        if (old_prefs['audible_bell'] != self.prefs['audible_bell']) or (old_prefs['cursor_blink'] != self.prefs['cursor_blink']) or (old_prefs['cursor_shape'] != self.prefs['cursor_shape']) or (old_prefs['emulation'] != self.prefs['emulation']) or (old_prefs['font_name'] != self.prefs['font_name']) or (old_prefs['scroll_on_keystroke'] != self.prefs['scroll_on_keystroke']) or (old_prefs['scroll_on_output'] != self.prefs['scroll_on_output']) or (old_prefs['scrollback_lines'] != self.prefs['scrollback_lines']) or (old_prefs['visible_bell'] != self.prefs['visible_bell']) or (old_prefs['word_chars'] != self.prefs['word_chars']) or (old_prefs['echo_commands'] != self.prefs['echo_commands']):
            vte1_console_changed = True
            vte2_console_changed = True
            vte3_console_changed = True
        if (old_prefs['tab_name_in_prompt'] != self.prefs['tab_name_in_prompt']) or (old_prefs['HTML_help'] != self.prefs['HTML_help']):
            vte1_R_options_changed = True
            vte2_R_options_changed = True
            vte3_R_options_changed = True

        # VTE1 specifically:
        if (old_prefs['background1'] != self.prefs['background1']) or (old_prefs['foreground1'] != self.prefs['foreground1']):
            vte1_console_changed = True
        if (old_prefs['prompt_color1'] != self.prefs['prompt_color1']):
            vte1_R_options_changed = True
            if self.prefs['prompt_color1'] != None:
                prompt_color_defined = True

        # VTE2 specifically:
        if (old_prefs['background2'] != self.prefs['background2']) or (old_prefs['foreground2'] != self.prefs['foreground2']):
            vte2_console_changed = True
        if (old_prefs['prompt_color2'] != self.prefs['prompt_color2']):
            vte2_R_options_changed = True
            if self.prefs['prompt_color2'] != None:
                prompt_color_defined = True
        
        # VTE3 specifically:
        if (old_prefs['background3'] != self.prefs['background3']) or (old_prefs['foreground3'] != self.prefs['foreground3']):
            vte3_console_changed = True
        if (old_prefs['prompt_color3'] != self.prefs['prompt_color3']):
            vte3_R_options_changed = True
            if self.prefs['prompt_color3'] != None:
                prompt_color_defined = True
                
        # Warn the user about the side effects of color promts!
        if prompt_color_defined:
            warning_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("Please note that using COLORED PROMPTS has a side effect when browsing R's history (keys UP and DOWN).\nPlease see the manual for details.") )
            warning_dialog.run()
            warning_dialog.destroy()

        # Get the R prompts to update themselves:
        for i in list(self._instances.keys()):
            rctrlhelper = self._instances[i]
            rctrlhelper.update_R_consoles(vte1_console_changed,vte2_console_changed,vte3_console_changed,vte1_R_options_changed,vte2_R_options_changed,vte2_R_options_changed)
            
        # Update the code folding as well:
        self.code_folding_engine.update_code_folding(self.window,self.prefs['use_rgedit_code_folding'])

    def ButtonCancel_clicked(self,widget):
        self.dialog.destroy()

    def ButtonChangeShortcuts_clicked(self,widget):
        self.ChangeShortcuts_ui = create_UI_from_file_GtkBuilder_or_Glade(self.get_data_dir()+"/ShortcutsDialog.glade",self.get_data_dir()+"/ShortcutsDialog.ui")

        edit_RCtrlSel_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlSel_Shortcut")
        edit_RCtrlSel_Shortcut.set_text(str(self.prefs['shortcut_RCtrlSel']))

        edit_RCtrlLine_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlLine_Shortcut")
        edit_RCtrlLine_Shortcut.set_text(str(self.prefs['shortcut_RCtrlLine']))

        edit_RCtrlAll_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlAll_Shortcut")
        edit_RCtrlAll_Shortcut.set_text(str(self.prefs['shortcut_RCtrlAll']))

        edit_RCtrlCursor_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlCursor_Shortcut")
        edit_RCtrlCursor_Shortcut.set_text(str(self.prefs['shortcut_RCtrlCursor']))

        edit_RCtrlBlock1Run_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock1Run_Shortcut")
        edit_RCtrlBlock1Run_Shortcut.set_text(str(self.prefs['shortcut_RCtrlBlock1Run']))

        edit_RCtrlBlock1Def_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock1Def_Shortcut")
        edit_RCtrlBlock1Def_Shortcut.set_text(str(self.prefs['shortcut_RCtrlBlock1Def']))

        edit_RCtrlBlock2Run_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock2Run_Shortcut")
        edit_RCtrlBlock2Run_Shortcut.set_text(str(self.prefs['shortcut_RCtrlBlock2Run']))

        edit_RCtrlBlock2Def_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock2Def_Shortcut")
        edit_RCtrlBlock2Def_Shortcut.set_text(str(self.prefs['shortcut_RCtrlBlock2Def']))

        edit_RCtrlNewTab_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlNewTab_Shortcut")
        edit_RCtrlNewTab_Shortcut.set_text(str(self.prefs['shortcut_RCtrlNewTab']))

        edit_RCtrlConfig_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlConfig_Shortcut")
        edit_RCtrlConfig_Shortcut.set_text(str(self.prefs['shortcut_RCtrlConfig']))

        edit_RCtrlLoadWorkspace_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlLoadWorkspace_Shortcut")
        edit_RCtrlLoadWorkspace_Shortcut.set_text(str(self.prefs['shortcut_RCtrlLoadWorkspace']))

        edit_RCtrlSaveWorkspace_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlSaveWorkspace_Shortcut")
        edit_RCtrlSaveWorkspace_Shortcut.set_text(str(self.prefs['shortcut_RCtrlSaveWorkspace']))

        edit_RCtrlAttach_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlAttach_Shortcut")
        edit_RCtrlAttach_Shortcut.set_text(str(self.prefs['shortcut_RCtrlAttach']))

        edit_RCtrlClose_Shortcut = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlClose_Shortcut")
        edit_RCtrlClose_Shortcut.set_text(str(self.prefs['shortcut_RCtrlClose']))

        check_CtrlC_4_Copy = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"CtrlC_4_Copy")
        check_CtrlC_4_Copy.set_active(self.prefs['R_console_Ctrl_C_4_copy'])
        check_CtrlC_4_Copy.set_sensitive(False)

        check_CtrlQ_break = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"CtrlQ_break")
        check_CtrlQ_break.set_active(self.prefs['R_console_Ctrl_Q_break'])

        check_Escape_break = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"Escape_break")
        check_Escape_break.set_active(self.prefs['R_console_Escape_break'])

        ChangeShortcuts_dialog = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"EditKeyboardShortcuts")

        malformed_data = True
        while malformed_data == True:
            malformed_data = False
            response = ChangeShortcuts_dialog.run()

            if response == -2: #OK button
                # Collect the data:
                shortcut_RCtrlSel = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlSel_Shortcut").get_text()
                shortcut_RCtrlLine = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlLine_Shortcut").get_text()
                shortcut_RCtrlAll = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlAll_Shortcut").get_text()
                shortcut_RCtrlCursor = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlCursor_Shortcut").get_text()
                shortcut_RCtrlBlock1Run = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock1Run_Shortcut").get_text()
                shortcut_RCtrlBlock1Def = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock1Def_Shortcut").get_text()
                shortcut_RCtrlBlock2Run = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock2Run_Shortcut").get_text()
                shortcut_RCtrlBlock2Def = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlBlock2Def_Shortcut").get_text()
                shortcut_RCtrlNewTab = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlNewTab_Shortcut").get_text()
                shortcut_RCtrlConfig = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlConfig_Shortcut").get_text()
                shortcut_RCtrlLoadWorkspace = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlLoadWorkspace_Shortcut").get_text()
                shortcut_RCtrlSaveWorkspace = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlSaveWorkspace_Shortcut").get_text()
                shortcut_RCtrlAttach = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlAttach_Shortcut").get_text()
                shortcut_RCtrlClose = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"RCtrlClose_Shortcut").get_text()
                check_CtrlC_4_Copy = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"CtrlC_4_Copy").get_active()
                check_CtrlQ_break = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"CtrlQ_break").get_active()
                check_Escape_break = get_widget_from_ui_GtkBuilder_or_Glade(self.ChangeShortcuts_ui,"Escape_break").get_active()

                # Check the data:
                if shortcut_RCtrlSel == 'None':
                    shortcut_RCtrlSel = None
                elif Gtk.accelerator_parse(shortcut_RCtrlSel) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run selection' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlSel_Shortcut").grab_focus()

                if shortcut_RCtrlLine == 'None':
                    shortcut_RCtrlLine = None
                elif Gtk.accelerator_parse(shortcut_RCtrlLine) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run current line' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlLine_Shortcut").grab_focus()

                if shortcut_RCtrlAll == 'None':
                    shortcut_RCtrlAll = None
                elif Gtk.accelerator_parse(shortcut_RCtrlAll) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run whole file' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlAll_Shortcut").grab_focus()

                if shortcut_RCtrlCursor == 'None':
                    shortcut_RCtrlCursor = None
                elif Gtk.accelerator_parse(shortcut_RCtrlCursor) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run to current line' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlCursor_Shortcut").grab_focus()

                if shortcut_RCtrlBlock1Run == 'None':
                    shortcut_RCtrlBlock1Run = None
                elif Gtk.accelerator_parse(shortcut_RCtrlBlock1Run) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run block 1' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlBlock1Run_Shortcut").grab_focus()

                if shortcut_RCtrlBlock1Def == 'None':
                    shortcut_RCtrlBlock1Def = None
                elif Gtk.accelerator_parse(shortcut_RCtrlBlock1Def) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Define block 1' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlBlock1Def_Shortcut").grab_focus()

                if shortcut_RCtrlBlock2Run == 'None':
                    shortcut_RCtrlBlock2Run = None
                elif Gtk.accelerator_parse(shortcut_RCtrlBlock2Run) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Run block 2' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlBlock2Run_Shortcut").grab_focus()

                if shortcut_RCtrlBlock2Def == 'None':
                    shortcut_RCtrlBlock2Def = None
                elif Gtk.accelerator_parse(shortcut_RCtrlBlock2Def) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Define block 2' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlBlock2Def_Shortcut").grab_focus()

                if shortcut_RCtrlNewTab == 'None':
                    shortcut_RCtrlNewTab = None
                elif Gtk.accelerator_parse(shortcut_RCtrlNewTab) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Create new R tab' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlNewTab_Shortcut").grab_focus()

                if shortcut_RCtrlConfig == 'None':
                    shortcut_RCtrlConfig = None
                elif Gtk.accelerator_parse(shortcut_RCtrlConfig) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Configure R interface' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlConfig_Shortcut").grab_focus()

                if shortcut_RCtrlLoadWorkspace == 'None':
                    shortcut_RCtrlLoadWorkspace = None
                elif Gtk.accelerator_parse(shortcut_RCtrlLoadWorkspace) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Load R Workspace' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlLoadWorkspace_Shortcut").grab_focus()

                if shortcut_RCtrlSaveWorkspace == 'None':
                    shortcut_RCtrlSaveWorkspace = None
                elif Gtk.accelerator_parse(shortcut_RCtrlSaveWorkspace) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Save R Workspace' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlSaveWorkspace_Shortcut").grab_focus()

                if shortcut_RCtrlAttach == 'None':
                    shortcut_RCtrlAttach = None
                elif Gtk.accelerator_parse(shortcut_RCtrlAttach) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Attach/detach R console' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlAttach_Shortcut").grab_focus()

                if shortcut_RCtrlClose == 'None':
                    shortcut_RCtrlClose = None
                elif Gtk.accelerator_parse(shortcut_RCtrlClose) == (0,0):
                    malformed_data = True
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Key shortcut for 'Close R console' is malformed!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()
                    ChangeShortcuts_ui.get_widget("RCtrlClose_Shortcut").grab_focus()

                # See if the data has changed:
                #if shortcut_RCtrlLine != self.prefs['shortcut_RCtrlLine'] or shortcut_RCtrlSel != self.prefs['shortcut_RCtrlSel'] or shortcut_RCtrlAll != self.prefs['shortcut_RCtrlAll'] or shortcut_RCtrlBlock1Run != self.prefs['shortcut_RCtrlBlock1Run'] or shortcut_RCtrlBlock1Def != self.prefs['shortcut_RCtrlBlock1Def'] or shortcut_RCtrlBlock2Run != self.prefs['shortcut_RCtrlBlock2Run'] or shortcut_RCtrlBlock2Def != self.prefs['shortcut_RCtrlBlock2Def'] or shortcut_RCtrlNewTab != self.prefs['shortcut_RCtrlNewTab'] or shortcut_RCtrlConfig != self.prefs['shortcut_RCtrlConfig'] or shortcut_RCtrlLoadWorkspace != self.prefs['shortcut_RCtrlLoadWorkspace'] or shortcut_RCtrlSaveWorkspace != self.prefs['shortcut_RCtrlSaveWorkspace'] or shortcut_RCtrlHelpSel != self.prefs['shortcut_RCtrlHelpSel'] or shortcut_RCtrlShowSel != self.prefs['shortcut_RCtrlShowSel'] or shortcut_RCtrlEditSel != self.prefs['shortcut_RCtrlEditSel'] or shortcut_RCtrlAttach != self.prefs['shortcut_RCtrlAttach'] or shortcut_RCtrlClose != self.prefs['shortcut_RCtrlClose']:
                if shortcut_RCtrlLine != self.prefs['shortcut_RCtrlLine'] or shortcut_RCtrlSel != self.prefs['shortcut_RCtrlSel'] or shortcut_RCtrlAll != self.prefs['shortcut_RCtrlAll'] or shortcut_RCtrlCursor != self.prefs['shortcut_RCtrlCursor'] or shortcut_RCtrlBlock1Run != self.prefs['shortcut_RCtrlBlock1Run'] or shortcut_RCtrlBlock1Def != self.prefs['shortcut_RCtrlBlock1Def'] or shortcut_RCtrlBlock2Run != self.prefs['shortcut_RCtrlBlock2Run'] or shortcut_RCtrlBlock2Def != self.prefs['shortcut_RCtrlBlock2Def'] or shortcut_RCtrlNewTab != self.prefs['shortcut_RCtrlNewTab'] or shortcut_RCtrlConfig != self.prefs['shortcut_RCtrlConfig'] or shortcut_RCtrlLoadWorkspace != self.prefs['shortcut_RCtrlLoadWorkspace'] or shortcut_RCtrlSaveWorkspace != self.prefs['shortcut_RCtrlSaveWorkspace'] or shortcut_RCtrlAttach != self.prefs['shortcut_RCtrlAttach'] or shortcut_RCtrlClose != self.prefs['shortcut_RCtrlClose'] or check_CtrlC_4_Copy != self.prefs['R_console_Ctrl_C_4_copy'] or check_CtrlQ_break != self.prefs['R_console_Ctrl_Q_break'] or check_Escape_break != self.prefs['R_console_Escape_break']:
                    shortcut_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("Key shortcuts have changed:\nplease restart gedit for changed to become effective!") )
                    shortcut_dialog.run()
                    shortcut_dialog.destroy()

                    self.prefs['shortcut_RCtrlSel'] = shortcut_RCtrlSel
                    self.prefs['shortcut_RCtrlLine'] = shortcut_RCtrlLine
                    self.prefs['shortcut_RCtrlAll'] = shortcut_RCtrlAll
                    self.prefs['shortcut_RCtrlCursor'] = shortcut_RCtrlCursor
                    self.prefs['shortcut_RCtrlBlock1Run'] = shortcut_RCtrlBlock1Run
                    self.prefs['shortcut_RCtrlBlock1Def'] = shortcut_RCtrlBlock1Def
                    self.prefs['shortcut_RCtrlBlock2Run'] = shortcut_RCtrlBlock2Run
                    self.prefs['shortcut_RCtrlBlock2Def'] = shortcut_RCtrlBlock2Def
                    self.prefs['shortcut_RCtrlNewTab'] = shortcut_RCtrlNewTab
                    self.prefs['shortcut_RCtrlConfig'] = shortcut_RCtrlConfig
                    self.prefs['shortcut_RCtrlLoadWorkspace'] = shortcut_RCtrlLoadWorkspace
                    self.prefs['shortcut_RCtrlSaveWorkspace'] = shortcut_RCtrlSaveWorkspace
                    self.prefs['shortcut_RCtrlAttach'] = shortcut_RCtrlAttach
                    self.prefs['shortcut_RCtrlClose'] = shortcut_RCtrlClose
                    self.prefs['R_console_Ctrl_C_4_copy'] = check_CtrlC_4_Copy
                    self.prefs['R_console_Ctrl_Q_break'] = check_CtrlQ_break
                    self.prefs['R_console_Escape_break'] = check_Escape_break

        ChangeShortcuts_dialog.destroy()
        
    def ButtonSidePanelOptions_clicked(self,widget):
        self.SidePanelOptions_ui = create_UI_from_file_GtkBuilder_or_Glade(self.get_data_dir()+"/SidePanelOptions.glade",self.get_data_dir()+"/SidePanelOptions.ui")
        
        check_IncludeLandmarksCheck = get_widget_from_ui_GtkBuilder_or_Glade(self.SidePanelOptions_ui,"IncludeLandmarksCheck")
        check_IncludeLandmarksCheck.set_active(self.prefs['R_structure_landmarks'])

        check_IncludeFunctionsCheck = get_widget_from_ui_GtkBuilder_or_Glade(self.SidePanelOptions_ui,"IncludeFunctionsCheck")
        check_IncludeFunctionsCheck.set_active(self.prefs['R_structure_functions'])

        check_IncludeDataframesCheck = get_widget_from_ui_GtkBuilder_or_Glade(self.SidePanelOptions_ui,"IncludeDataframesCheck")
        check_IncludeDataframesCheck.set_active(self.prefs['R_structure_dataframes'])

        SidePanelOptions_dialog = get_widget_from_ui_GtkBuilder_or_Glade(self.SidePanelOptions_ui,"SidePanelOptionsDialog")

        response = SidePanelOptions_dialog.run()
        if response == -2: #OK button
            # Collect the data: save the info and update the side panel:
            self.prefs['R_structure_landmarks'] = check_IncludeLandmarksCheck.get_active()
            self.prefs['R_structure_functions'] = check_IncludeFunctionsCheck.get_active()
            self.prefs['R_structure_dataframes'] = check_IncludeDataframesCheck.get_active()
            # Update the panels of all windows:
            for window in list(self._instances.keys()):
                self._instances[window]._rstructurepanel.create_pattern_matcher()
                self._instances[window]._rstructurepanel.on_force_refresh(None)
            
        SidePanelOptions_dialog.destroy()

    def ButtonCodeFoldingOptions_clicked(self,widget):
        self.CodeFoldingOptions_ui = create_UI_from_file_GtkBuilder_or_Glade(self.get_data_dir()+"/CodeFoldingOptions.glade",self.get_data_dir()+"/CodeFoldingOptions.ui")
        
        check_UseRgeditCodeFoldingCheck = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"UseRgeditCodeFoldingCheck")
        check_UseRgeditCodeFoldingCheck.set_active(self.prefs['use_rgedit_code_folding'])

        radio_PreferHighestBlockRadio = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"PreferHighestBlockRadio")
        radio_PreferLowestBlockRadio = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"PreferLowestBlockRadio")
        radio_PreferHighestFunctionRadio = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"PreferHighestFunctionRadio")
        radio_PreferLowestFunctionRadio = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"PreferLowestFunctionRadio")
        if self.prefs['code_folding_block_preference'] == 'highest_block':
            radio_PreferHighestBlockRadio.set_active(True)
        elif self.prefs['code_folding_block_preference'] == 'lowest_block':
            radio_PreferLowestBlockRadio.set_active(True)
        elif self.prefs['code_folding_block_preference'] == 'highest_function':
            radio_PreferHighestFunctionRadio.set_active(True)
        elif self.prefs['code_folding_block_preference'] == 'lowest_function':
            radio_PreferLowestFunctionRadio.set_active(True)
        else:
            print("Unknown block preference option '" + str(self.prefs['code_folding_block_preference']) + "'!")
            radio_PreferHighestBlockRadio.set_active(True)

        CodeFoldingOptions_dialog = get_widget_from_ui_GtkBuilder_or_Glade(self.CodeFoldingOptions_ui,"CodeFoldingOptionsDialog")

        response = CodeFoldingOptions_dialog.run()
        if response == -2: #OK button
            # Collect the data: save the info and update the side panel:
            self.prefs['use_rgedit_code_folding'] = check_UseRgeditCodeFoldingCheck.get_active()
            if radio_PreferHighestBlockRadio.get_active():
                self.prefs['code_folding_block_preference'] = 'highest_block'
            elif radio_PreferLowestBlockRadio.get_active():
                self.prefs['code_folding_block_preference'] = 'lowest_block'
            elif radio_PreferHighestFunctionRadio.get_active():
                self.prefs['code_folding_block_preference'] = 'highest_function'
            elif radio_PreferLowestFunctionRadio.get_active():
                self.prefs['code_folding_block_preference'] = 'lowest_function'
            else:
                # default:
                self.prefs['code_folding_block_preference'] = 'highest_block'
            
            # Update the folding:
            if not self.prefs['use_rgedit_code_folding']:
                # Unfold everything:
                for window in list(self._instances.keys()):
                    for view in window.get_views():
                        self.code_folding_engine.unfold_all(view.get_buffer(),view) 
            
        CodeFoldingOptions_dialog.destroy()





    

        


########################################################################
#                           The Wizard stuff
########################################################################

# Get the text from  collection of XML nodes:
def getText_from_XML(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc

# Class implementing the wizard-wide about box:
class RWizard_AboutBox:

    def __init__(self):
        # Init:
        self.path = None # the path used for finding icons and stuff
        self.name = None
        self.version = None
        self.copyright = None
        self.comments = None
        self.license = None
        self.website = None
        self.authors = None 
        self.documenters = None
        self.artists = None
        self.translator_credits = None
        self.logo_icon_name = None
        
    def do_process_about(self,xml_node):
        # Get the about info:
        if xml_node.hasAttribute("name"):
            self.name = xml_node.getAttribute("name")
        if xml_node.hasAttribute("version"):
            self.version = xml_node.getAttribute("version")
        if xml_node.hasAttribute("copyright"):
            self.copyright = xml_node.getAttribute("copyright")
        if xml_node.hasAttribute("comments"):
            self.comments = xml_node.getAttribute("comments")
        if xml_node.hasAttribute("license"):
            self.license = xml_node.getAttribute("license")
        if xml_node.hasAttribute("website"):
            self.website = xml_node.getAttribute("website")
        if xml_node.hasAttribute("authors"):
            self.authors = xml_node.getAttribute("authors").split(",")
        if xml_node.hasAttribute("documenters"):
            self.documenters = xml_node.getAttribute("documenters")
        if xml_node.hasAttribute("artists"):
            self.artists = xml_node.getAttribute("artists")
        if xml_node.hasAttribute("translator_credits"):
            self.translator_credits = xml_node.getAttribute("translator_credits")
        if xml_node.hasAttribute("logo_icon_name"):
            self.logo_icon_name = self.path + xml_node.getAttribute("logo_icon_name")
        return True
        
    def show(self):
        # Display the about info:
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_name(self.name)
        about_dialog.set_version(self.version)
        about_dialog.set_copyright(self.copyright)    
        about_dialog.set_comments(self.comments)
        about_dialog.set_license(self.license)
        about_dialog.set_website(self.website)
        about_dialog.set_authors(self.authors) 
        about_dialog.set_documenters(self.documenters)
        about_dialog.set_artists(self.artists)
        about_dialog.set_translator_credits(self.translator_credits)
        about_dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file(self.logo_icon_name))
        
        about_dialog.show()
        about_dialog.run()
        about_dialog.destroy()
        

# Class implementing a template:
class RWizard_Template:

    def __init__(self):
        # Init:
        self.RawText = None
        
    def do_process_template(self,xml_node):
        # Get the node's text (i.e., the raw template):
        self.RawText =  getText_from_XML(xml_node.childNodes)
        
        return True
        
    def update(self,variables):
        # Update the template using the variable values in the given dictionary:
        new_template = self.RawText
        
        # Process the $[Python ... $] python directives:
        new_template = self.process_directives(new_template,variables)
        if new_template == None:
            # Some error has occured:
            return None
        
        # Replace the ${xxx} with xxx's value:
        for variable in variables:
            new_template = new_template.replace( "${" + variable + "}", str(variables[variable]) )
        return new_template
        
    def process_directives(self,template,variables):
        # Process the $[ ... $] directives:
        # For now, only Python scripting executed:
        python_directive_start = template.find("$[Python")
        while python_directive_start != -1:
            # Found a directive: get the whole expression
            python_directive_end = template.find("$]",python_directive_start)
            if python_directive_end == -1:
                question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Python directives must end with $]....") )
                response = question_dialog.run()
                question_dialog.destroy()
                return None
                
            # Evaluate the condition:
            python_directive = template[(python_directive_start+len("$[Python")):python_directive_end]
            #print python_directive
            for variable in variables:
                python_directive = python_directive.replace( "${" + variable + "}", str(variables[variable]) )
            python_directive = eval(python_directive,__builtins__)
            #python_directive = eval(python_directive, {"__builtins__":None}, {})
            
            # And replace the result appropriately
            if python_directive == None:
                python_directive = ""
            else:
                python_directive = str(python_directive)
            template = template.replace( template[python_directive_start:(python_directive_end+len("$]"))], python_directive )
            
            # Search for the next directive:
            python_directive_start = template.find("$[Python")
            
        return template
            
        
    # Debug printing:
    def print_debug(self):
        print("Template: " +  str(self.RawText))
        
        
# Class implementing a varibale within the block:
class RWizard_Variable:

    def __init__(self):
        # Init:
        self.Name = None
        self.Description = False
        self.Required = False
        self.Type = None
        self.Default = None
        self.Singlechoice = True
        self.ToolTip = None
        self.ListValues = []
        self.GtkControl = None # the associated Gtk control (if any)
        self.ValueDefined = False # has the variable's value been already defined?
        self.Value = None # and the actual value (if any)
        
    def get_value(self):
        # Return the value adjusted for final usage (e.g., for comboboxes return the actually selected string):
        if self.Type.lower() == "list":
            return self.ListValues[self.Value]
        else:
            return self.Value
        
    def do_process_variable(self,xml_node):
        # Read the attributes:
        if xml_node.hasAttribute("name"):
            self.Name = xml_node.getAttribute("name")
        else:
            print("A variable must have a name!")
            return False
            
        if xml_node.hasAttribute("description"):
            self.Description = xml_node.getAttribute("description")
        else:
            print("A variable must have a description!")
            return False
            
        if xml_node.hasAttribute("required"):
            self.Required = (xml_node.getAttribute("required").lower() == "true")

        if xml_node.hasAttribute("type"):
            self.Type = xml_node.getAttribute("type")
        else:
            print("A variable must have a type!")
            return False
            
        if xml_node.hasAttribute("default"):
            self.Default = xml_node.getAttribute("default")
            
        if xml_node.hasAttribute("singlechoice"):
            self.Singlechoice = xml_node.getAttribute("singlechoice")
            
        if xml_node.hasAttribute("tooltip"):
            self.ToolTip = xml_node.getAttribute("tooltip")
            
        if self.Type == "list":
            # Try to get the values:
            values_nodes = xml_node.getElementsByTagName("value")
            if values_nodes == None and len(values_nodes) == 0:
                print("Variables of type \"list\" must have at least one value defined!")
                return False
            else:
                # Get the values:
                for value_node in values_nodes:
                    if value_node.hasAttribute("name"):
                        self.ListValues = self.ListValues + [value_node.getAttribute("name")]
            if len(self.ListValues) == 0:
                print("Variables of type \"list\" must have at least one value defined!")
        elif self.Type == "editablelist":
            # Try to get the values:
            values_nodes = xml_node.getElementsByTagName("value")
            if values_nodes == None and len(values_nodes) == 0:
                print("Variables of type \"editablelist\" must have at least one value defined!")
                return False
            else:
                # Get the values:
                for value_node in values_nodes:
                    if value_node.hasAttribute("name"):
                        self.ListValues = self.ListValues + [value_node.getAttribute("name")]
            if len(self.ListValues) == 0:
                print("Variables of type \"editablelist\" must have at least one value defined!")
            
        return True
        
    # Debug printing:
    def print_debug(self):
        print("Variable: " +  str(self.Name) + " [" + str(self.Description) + " type=" + str(self.Type) + " default=" + str(self.Default) + "]")
        if str(self.Type) == "list":
            print("   Values: " + str(self.ListValues))

# Class implementing a block within the vars:
class RWizard_Block:

    def __init__(self):
        # Init:
        self.Title = None
        self.Rselector = False
        self.Layout = "vertical"  # can be "vertical", "horizontal" or "grid"
        self.Variables = [] # the list of variables
        
        # Dialog params;
        self.max_initial_width = 600
        self.max_initial_height = 300
        
    def do_process_block(self,xml_node):
        # Get the title:
        if xml_node.hasAttribute("title"):
            self.Title = xml_node.getAttribute("title")
            
        # and the other optional attributes:
        if xml_node.hasAttribute("rselector"):
            self.Rselector = xml_node.getAttribute("rselector")
        if xml_node.hasAttribute("layout"):
            self.Layout = xml_node.getAttribute("layout")
            
        # Parse the variables within this block:
        variables_node = xml_node.getElementsByTagName("variable")
        if variables_node == None or len(variables_node) == 0:
            print("Blocks must have at least one variable!")
            return False
        for variable_node in variables_node:
            variable = RWizard_Variable()
            if not variable.do_process_variable(variable_node):
                return False
            else:
                self.Variables = self.Variables + [variable]
                
        if len(self.Variables) == 0:
            print("There must be at least one variable defined for each block!")
            return False
        
        return True
        
    # Debug printing:
    def print_debug(self):
        print("Block: " +  str(self.Title) + "[rselector=" + str(self.Rselector) + " layout=" + str(self.Layout) + "]")
        for variable in self.Variables:
            variable.print_debug()
            
    def run(self,wizard,is_previous,is_next,is_last,selection_as,selection_text):
        # Construct and display the wizard block and collect user input:
        # Return the following codes: 0 = cancel, -1 = previous, 1 = next/OK, 2 = OK & just run the data
        label = Gtk.Label(label=self.Title)
        dialog = Gtk.Dialog(wizard.Description,
                           None,
                           Gtk.DialogFlags.DESTROY_WITH_PARENT,)
        #dialog.vbox.pack_start(label, True, True, 0)
        dialog.get_content_area().pack_start(label, True, True, 0)
        label.show()
        
        ## Embed the controls in a scrollable area, just in case they tend to be bigger than the available screen space:
        #holder_scrollable = Gtk.ScrolledWindow()
        #holder_scrollable.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        #holder_scrollable.show()
        #holder_layout = Gtk.Layout()
        #holder_layout.show()
        
        # Start adding the required widgets for each variable:
        container_vbox = Gtk.VBox()
        container_vbox.show()
        for variable in self.Variables:
            self.add_widgets_for_variable(container_vbox,variable,selection_as,selection_text)
        #holder_layout.put(container_vbox,0,0)
        # And adjust the size accordingly
        #holder_layout.set_size(self.max_width,self.max_height)
        
        #holder_scrollable.add(holder_layout)
        #dialog.vbox.pack_start(holder_scrollable, True, True, 0)
        dialog.get_content_area().pack_start(container_vbox, True, True, 0)
        
        # The buttons:
        about_button = dialog.add_button(_("About"), 1303 ) # About the wizard
        about_button.set_sensitive( wizard.AboutInfo != None )
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            about_button.set_tooltip_text(_("About the wizard..."))
        
        help_button = dialog.add_button(_("Help"), 1304 ) # Help on the dialog
        help_button.set_sensitive( wizard.Help != None )
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            help_button.set_tooltip_text("Wizard's help info...")
        
        #dialog.action_area.add(Gtk.HSeparator())
        back_button = dialog.add_button(_("Back"), 1299 ) # Going back
        back_button.set_sensitive( is_previous )
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            back_button.set_tooltip_text(_("Go to previous block..."))
        
        if is_last:
            ok_button = dialog.add_button(_("Inspect code"), 1302 ) # OK and end
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                ok_button.set_tooltip_text(_("Inspect the generated R code..."))
            run_button = dialog.add_button(_("Run code!"), 1305 ) # Ok and just run
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                run_button.set_tooltip_text(_("I trust the wizard: go ahead and run the generated R code..."))
        else:
            next_button = dialog.add_button(_("Next"), 1301 ) # Next
            next_button.set_sensitive( is_next )
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                next_button.set_tooltip_text(_("Continue to next block..."))
            
        cancel_button = dialog.add_button(_("Cancel"), 1300 ) # Cancel
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            cancel_button.set_tooltip_text(_("Cancel the wizard..."))
        
        # The initial dialog size:
        initial_size = dialog.get_size()
        if initial_size[0] > self.max_initial_width:
            initial_width = self.max_initial_width
        else:
            initial_width = initial_size[0]
        if initial_size[1] > self.max_initial_height:
            initial_height = self.max_initial_height
        else:
            initial_height = initial_size[1]
        dialog.resize( initial_width, initial_height )
        
        ret_val = 999
        while ret_val == 999:
            # Allow the user to interact with it and collect the response;
            response = dialog.run()
            
            # Process the user response value:
            if response == 1300:
                # Aborted: don't collect the data!
                ret_val = 0
            elif response == 1301 or response == 1302:
                # Forward or OK: collect the data!
                if not self.collect_data(dialog):
                    ret_val = 999 # don't close the dialog!!!
                else:
                    ret_val = 1
            elif response == 1299:
                # Back: collect the data!
                self.collect_data(dialog)
                ret_val = -1
            elif response == 1303:
                # Display the about info:
                wizard.AboutInfo.show()
                ret_val = 999 # don't close the dialog!!!
            elif response == 1304:
                # Display the help info:
                if wizard.Help:
                    if wizard.Help[0] == "?":
                        # R entity:
                        do_send_to_R(wizard.Help[1:]+"\n",wizard._rwizardengine._rctrlwindowhelper.R_widget,False)
                    else:
                        webbrowser.open(wizard.Help)
                ret_val = 999 # don't close the dialog!!!
            elif response == 1305:
                # Just run the code!
                if not self.collect_data(dialog):
                    ret_val = 999 # don't close the dialog!!!
                else:
                    ret_val = 2
            else:
                # Aborted: don't collect the data!
                ret_val = 0
            
        # Destroy the dialog and return the value:
        dialog.destroy()
        return ret_val
            
    def add_widgets_for_variable(self,container_vbox,variable,selection_as,selection_text):
        # Add the appropriate widgets for the variable in the holder_layout at the positions given by self.current_x and self.current_y (and update them appropriately):        
        container_hbox = Gtk.HBox()
        container_hbox.show()
        
        var_text = ("<b>*</b>","")[not variable.Required] + variable.Description + str(" (<b><tt>") + variable.Name + str("</tt></b>): ")
        
        if variable.Type.lower() == "text":
            # text widget:
            var_label = Gtk.Label()
            var_label.set_markup(var_text)
            if variable.ToolTip and use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                var_label.set_tooltip_markup(variable.ToolTip)
            var_label.show()
            container_hbox.add(var_label)
            
            var_edit = Gtk.Entry()
            var_edit.set_has_frame(True)
            if variable.ToolTip and use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                var_edit.set_tooltip_markup(variable.ToolTip)
            var_edit.show()
            container_hbox.add(var_edit)
            
            variable.GtkControl = var_edit
            if variable.Default:
                var_edit.set_text(variable.Default)
                
            if variable.ValueDefined:
                var_edit.set_text(variable.Value)
            elif selection_as != None and selection_as.lower() == variable.Name.lower() and selection_text != None: 
                var_edit.set_text(selection_text)
        elif variable.Type.lower() == "list":
            # list widget:
            if variable.Singlechoice.lower() == "true":
                # it's a combobox!
                var_label = Gtk.Label()
                var_label.set_markup(var_text)
                if variable.ToolTip and use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    var_label.set_tooltip_markup(variable.ToolTip)
                var_label.show()
                container_hbox.add(var_label)
                
                var_combo = Gtk.ComboBoxText()
                for value in variable.ListValues:
                    var_combo.append_text(value)
                default_choice = -1
                try:
                    default_choice = int(variable.Default)
                except ValueError:
                    default_choice = -1
                var_combo.set_active(default_choice)
                if variable.ToolTip and use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    var_combo.set_tooltip_markup(variable.ToolTip)
                var_combo.show()
                container_hbox.add(var_combo)
                
                variable.GtkControl = var_combo
                if variable.ValueDefined:
                    var_combo.set_active(variable.Value)
        elif variable.Type.lower() == "editablelist":
            # editablelist widget:
            if variable.Singlechoice.lower() == "true":
                # it's a comboboxentry!
                var_label = Gtk.Label()
                var_label.set_markup(var_text)
                if variable.ToolTip and use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    var_label.set_tooltip_markup(variable.ToolTip)
                var_label.show()
                container_hbox.add(var_label)
                
                var_combo_edit = Gtk.combo_box_entry_new_text()
                for value in variable.ListValues:
                    var_combo_edit.append_text(value)
                var_combo_edit.get_child().set_text(variable.Default)
                if variable.ToolTip and use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    var_combo_edit.set_tooltip_markup(variable.ToolTip)
                var_combo_edit.show()
                container_hbox.add(var_combo_edit)
                
                variable.GtkControl = var_combo_edit
                if variable.ValueDefined:
                    var_combo_edit.get_child().set_text(variable.Value)
        elif variable.Type.lower() == "bool":
            # checkbox:
            var_label = Gtk.Label()
            var_label.set_markup(var_text)
            if variable.ToolTip and use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                var_label.set_tooltip_markup(variable.ToolTip)
            var_label.show()
            container_hbox.add(var_label)
            
            var_check = Gtk.CheckButton()
            if variable.ToolTip and use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                var_check.set_tooltip_markup(variable.ToolTip)
            var_check.show()
            container_hbox.add(var_check)
            
            variable.GtkControl = var_check
            if variable.Default:
                var_check.set_active(variable.Default.lower() == "true")
                
            if variable.ValueDefined:
                var_check.set_active(variable.Value)
                
        # add this row to the dialog:        
        container_vbox.add(container_hbox)
        
    def collect_data(self,dialog):
        # Collect the user-introduced data and save it in the appropriate places: return True if all required variables are defined
        for variable in self.Variables:
            self.collect_data_for_variable(variable)
            if variable.Required and not variable.ValueDefined:
                question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _('Required variable "') + variable.Name + _('" is undefined!') )
                response = question_dialog.run()
                question_dialog.destroy()
                return False
        return True
            
    def collect_data_for_variable(self,variable):
        if variable.GtkControl == None:
            print("Error: variable.GtkControl should have been defined!")
            variable.Value = None
            variable.ValueDefined = False
            return
            
        if variable.Type.lower() == "text":
            # Gtk.Entry:
            variable.Value = variable.GtkControl.get_text()
            variable.ValueDefined = (variable.Value.strip() != "")
        elif variable.Type.lower() == "list":
            # list widget:
            if variable.Singlechoice.lower() == "true":
                # Gtk.ComboBoxText():
                variable.Value = variable.GtkControl.get_active()
                variable.ValueDefined = True
        elif variable.Type.lower() == "editablelist":
            # list widget:
            if variable.Singlechoice.lower() == "true":
                # Gtk.ComboBoxText():
                variable.Value = variable.GtkControl.get_child().get_text()
                variable.ValueDefined = True
        elif variable.Type.lower() == "bool":
            # Gtk.CheckButton()
            variable.Value = variable.GtkControl.get_active()
            variable.ValueDefined = True
        else:
            variable.Value = None
            variable.ValueDefined = False
       
    
# This class implements a single wizard:
class RWizard:
    
    def __init__(self,_rwizardengine):
        # Init the wizard:
        self._rwizardengine = _rwizardengine
        self.Name = None
        self.Description = None
        # The desired (i.e., suggested by the rwizard itself) menu, icon, toolbar status and keyboard shortuct:
        self.DesiredMenu = None
        self.DesiredIcon = None
        self.DesiredToolbar = None
        self.DesiredShortcut = None
        # ... and the actual (i.e., taking into account the user preferences and default rules) ones:
        self.ActualMenu = None
        self.ActualIcon = None
        self.ActualToolbar = None
        self.ActualShortcut = None
        # The list of blocks and the template:
        self.Blocks = []
        self.Template = None
        # About info and help:
        self.AboutInfo = None
        self.Help = None
        # Default button:
        self.DefaultButton = 0 # 0 = Just paste, 1 = Just run, 2 = Paste & run
        self.SelectionAs = None
        self.SelectedText = None # the selection text (if any) when the dialog is fired (to be used as instructed by SelectionAs)
        return
    
    # Try to load and create a wizard from the given file description and return True inf successful, False otherwise    
    def load(self,file_name):
        # Open the file for reading:
        try:
            wizard_doc = minidom.parse( file_name )
        except:
            print("Error opening & parsing wizard file \"") + file_name + "\": ", sys.exc_info()[1]
            question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _("Error opening & parsing wizard file \"") + file_name + "\":\n" + str(sys.exc_info()[1]) + _("\n\nRgedit plugin cannot continue! Please fix the problem...") )
            response = question_dialog.run()
            question_dialog.destroy()
            return False
            
        # Proceed through the DOM and get the relevant stuff:
        root_node = wizard_doc.documentElement;
        if root_node.nodeName.lower() != 'rwizard':
            print("Error: rwizard xml expected, and instead got \"") + root_node.nodeName.lower() + "\"..."
            wizard_doc.unlink()
            return False;
            
        # Get the name and description:
        if not root_node.hasAttribute("name"):
            print("Error: rwizard must have a name!")
            wizard_doc.unlink()
            return False;
        self.Name = root_node.getAttribute("name")
        
        if root_node.hasAttribute("description"):
            self.Description = root_node.getAttribute("description")
        else:
            self.Description = self.Name
            
        if root_node.hasAttribute("menu"):
            self.DesiredMenu = root_node.getAttribute("menu")
        else:
            self.DesiredMenu = self.Name
            
        if root_node.hasAttribute("icon"):
            self.DesiredIcon = root_node.getAttribute("icon")
        else:
            self.DesiredIcon = self.Name
            
        if root_node.hasAttribute("toolbar"):
            self.DesiredToolbar = root_node.getAttribute("toolbar")
        else:
            self.DesiredToolbar = self.Name
            
        if root_node.hasAttribute("shortcut"):
            self.DesiredShortcut = root_node.getAttribute("shortcut")
        else:
            self.DesiredShortcut = self.Name
            
        if root_node.hasAttribute("defaultbutton"):
            if root_node.getAttribute("defaultbutton").lower() == "paste":
                self.DefaultButton = 0
            elif root_node.getAttribute("defaultbutton").lower() == "run":
                self.DefaultButton = 1
            elif root_node.getAttribute("defaultbutton").lower() == "paste and run":
                self.DefaultButton = 2
            else:
                print("Unknown value for the defaultbutton attribute :") + root_node.getAttribute("defaultbutton")

        if root_node.hasAttribute("selectionas"):
            self.SelectionAs = root_node.getAttribute("selectionas")

        # Process the about info:
        about_node = root_node.getElementsByTagName("about")
        if about_node != None:
            if len(about_node) == 1:
                if not self.do_process_about( about_node[0] ):
                    wizard_doc.unlink()
                    return False
            elif len(about_node) > 1:
                print("There must at most one \"about\" node inside a \"rwizard\"")
                wizard_doc.unlink()
                return False
            
        # Process the help file, url or R entiry:
        help_node = root_node.getElementsByTagName("help")
        if help_node != None:
            if len(help_node) == 1:
                if not self.do_process_help( help_node[0] ):
                    wizard_doc.unlink()
                    return False
            elif len(help_node) > 1:
                print("There must at most one \"help\" node inside a \"rwizard\"")
                wizard_doc.unlink()
                return False
            
        # Process the variables:
        vars_node = root_node.getElementsByTagName("vars")
        if vars_node != None and len(vars_node) == 1:
            if not self.do_process_vars( vars_node[0] ):
                wizard_doc.unlink()
                return False
        else:
            print("There must a single \"vars\" node inside a \"rwizard\"")
            wizard_doc.unlink()
            return False
            
        # Process the script:
        script_node = root_node.getElementsByTagName("script")
        if script_node != None:
            if len(script_node) == 1:
                if not self.do_process_script( script_node[0] ):
                    wizard_doc.unlink()
                    return False
            elif len(script_node) > 1:
                print("There must at most one \"script\" node inside a \"rwizard\"")
                wizard_doc.unlink()
                return False
            
        # Process the template:
        template_node = root_node.getElementsByTagName("template")
        if template_node != None and len(template_node) == 1:
            if not self.do_process_template( template_node[0] ):
                wizard_doc.unlink()
                return False
        else:
            print("There must a single \"template\" node inside a \"rwizard\"")
            wizard_doc.unlink()
            return False
            
        # Reconcile the options requested by the izard with those defined by the user and the default ones:
        if self.DesiredMenu != None:
            self.ActualMenu = self.DesiredMenu
        else:
            self.ActualMenu = self._rwizardengine.get_menu(self.Name)
            
        if self.DesiredIcon != None:
            self.ActualIcon = self.DesiredIcon
        else:
            self.ActualIcon = self._rwizardengine.get_icon(self.Name)
            
        if self.DesiredToolbar != None:
            self.ActualToolbar = self.DesiredToolbar
        else:
            self.ActualToolbar = self._rwizardengine.get_toolbar(self.Name)
            
        if self.DesiredShortcut != None:
            self.ActualShortcut = self.DesiredShortcut
        else:
            self.ActualShortcut = self._rwizardengine.get_shortcut(self.Name)
            
        # Everything's ok:
        wizard_doc.unlink()
        return True
        
    def do_process_vars(self,xml_node):
        # Process the blocks inside this vars element:
        block_nodes = xml_node.getElementsByTagName("block")
        for block_node in block_nodes:
            if not self.do_process_block( block_node ):
                return False
        #if len(self.Blocks) == 0:
        #    print "There must be at least one block defined!"
        #    return False
        return True
        
    def do_process_about(self,xml_node):
        # Create the about dialog:
        self.AboutInfo = RWizard_AboutBox()
        self.AboutInfo.Name = self.Description
        self.AboutInfo.path = self._rwizardengine.path
        
        # Parse it!
        return self.AboutInfo.do_process_about(xml_node)
        
    def do_process_help(self,xml_node):
        # Try to get the help file:
        if xml_node.hasAttribute("file"):
            self.Help = "file://" + self._rwizardengine.path + xml_node.getAttribute("file")
        elif xml_node.hasAttribute("url"):
            self.Help = xml_node.getAttribute("url")
        elif xml_node.hasAttribute("rhelp"):
            self.Help = "?" + xml_node.getAttribute("rhelp")
        return True
            
    def do_process_block(self,xml_node):
        # Create a new block and read its contents:
        block = RWizard_Block()
        
        # Parse it!
        if not block.do_process_block(xml_node):
            return False
            
        # Add it to the blocks list:
        self.Blocks = self.Blocks + [block]
        
        return True
    
    def do_process_script(self,xml_node):
        # Process the script node:
        print("Processing script...")
        return True
    
    def do_process_template(self,xml_node):
        # Process the template node:
        self.Template = RWizard_Template()
        if not self.Template.do_process_template(xml_node):
            return False
        return True
    
    # Debug printing:
    def print_debug(self):
        print("Wizard: " +  " " + str(self.Name) + " [" + str(self.Description) + "]" + ": " + str(self.ActualMenu) + " " + str(self.ActualIcon) + " " + str(self.ActualToolbar) + " " + str(self.ActualShortcut))
        for block in self.Blocks:
            block.print_debug()
        self.Template.print_debug()
        
        
    # Run this wizard!
    def run(self):
        #print "Running wizard " + self.Description + " ..."
        # Let each block display itself and depending on the user response continue or abort:
        if len(self.Blocks) > 0:
            # Check if the selection is to be used:
            self.SelectedText = None
            if self.SelectionAs != None:
                # Then try to get it so that it can be used for the requested variable:
                doc = self._rwizardengine._window.get_active_document()
                if not doc:
                    return
                # See if anything is selected:
                if doc.get_has_selection():
                    sel_bounds = doc.get_selection_bounds()
                    self.SelectedText = doc.get_text(sel_bounds[0],sel_bounds[1])
            
        i = 0
        # Cycle in order to allow back from R code dialog:
        while True:
            finished_OK = False
            user_action = +2
            while i < len(self.Blocks):
                user_action = self.Blocks[i].run( self, i>0, i<(len(self.Blocks)-1), i==(len(self.Blocks)-1), self.SelectionAs, self.SelectedText )
                if user_action == 0:
                    # Abort the whole wizard...
                    finished_OK = False
                    return
                elif user_action == -1:
                    # Go back one step:
                    if i > 0:
                        i = i-1
                    else:
                        i = 0
                elif user_action == +1:
                    # Go forward one step or stop the process with OK:
                    if i < (len(self.Blocks)-1):
                        i = i+1
                    else:
                        finished_OK = True
                        break
                elif user_action == +2:
                    # Ok & just run the code!
                    finished_OK = True
                    break
                else:
                    print("Unknown block-level user action ") + user_action + "!"
                    return
            
            if finished_OK or (len(self.Blocks) == 0):
                updated_template = self.update_template()
                if updated_template != None:
                    # Everything's ok; beautify the R source code:
                    # 1. Get rid of the empty lins at the begining and end (if any):
                    self.beautified_template = ""
                    lines = updated_template.split('\n')
                    from_top = 0
                    while from_top < len(lines):
                        if not lines[from_top].strip():
                            from_top += 1
                        else:
                            break
                    if from_top == len(lines):
                        # Empty text: nothing to do!
                        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("The resulting R code is empty...") )
                        response = question_dialog.run()
                        question_dialog.destroy()
                        return
                    from_bottom = len(lines)-1
                    while from_bottom >= 0:
                        if not lines[from_bottom].strip():
                            from_bottom -= 1
                        else:
                            break
                    if from_bottom == 0:
                        # Empty text: nothing to do!
                        question_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, _("The resulting R code is empty...") )
                        response = question_dialog.run()
                        question_dialog.destroy()
                        return
                    for i in range(from_top,from_bottom+1):
                        self.beautified_template += lines[i] + '\n'
                        
                    if user_action == +2:
                        # Simply run the resulting code:
                        self.resulting_template = self.beautified_template
                        response = 1301
                    else:
                        # Ask the user what they wants to do with the resulting template:
                        self.ui = create_UI_from_file_GtkBuilder_or_Glade(self._rwizardengine._plugin.get_data_dir()+"/WizardActions.glade",self._rwizardengine._plugin.get_data_dir()+"/WizardActions.ui")
                        self.dialog = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"WiardsActionsDialog")
                        
                        self.source_buffer = Gtk.TextBuffer()
                        self.source_buffer.set_text(self.beautified_template)
                        self.source_view = get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"SourceView")
                        self.source_view.set_buffer(self.source_buffer)
                        self.source_view.modify_font(Pango.FontDescription('Monospace 10'))
                        
                        # Event handlers:
                        dic = { "on_InsertCommentCheck_toggled" : self.on_InsertCommentCheck_toggled }
                        #        "on_IndentSpin_value_changed" : self.on_IndentSpin_value_changed,
                        #        "on_IndentComboBox_changed" : self.on_IndentComboBox_changed }
                        connect_signals_for_ui_GtkBuilder_or_Glade(self.ui,dic)
                        
                        # Initial settings:
                        get_widget_from_ui_GtkBuilder_or_Glade(self.ui,"InsertCommentCheck").set_active(True)
                        #self.ui.get_widget("IndentComboBox").set_active(0) # Tabs initially
                
                        response = self.dialog.run()
                        self.resulting_template = self.source_buffer.get_text(self.source_buffer.get_start_iter(),self.source_buffer.get_end_iter(),False)
                        self.dialog.destroy()
                    
                    # Process the response appropriately:
                    if response == 1299:
                        # Back: let the cycle resume from the last block:
                        i = len(self.Blocks)-1
                    elif response == 1300:
                        # Paste & run:
                        self.do_paste_R_code()
                        self.do_run_R_code()
                        return
                    elif response == 1301:
                        # Just run:
                        self.do_run_R_code()
                        return
                    elif response == 1302:
                        # Just paste:
                        self.do_paste_R_code()
                        return
                    else:
                        # Cancel:
                        return
                else:
                    # Abort required:
                    return
                
                #print self.beautified_template
                
    def do_paste_R_code(self):
        # Paste the R code at the cursor position:
        doc = self._rwizardengine._window.get_active_document()
        if not doc:
            return
        doc.insert_at_cursor(self.resulting_template)
        
    def do_run_R_code(self):
        # Run the R code through the current console (if any):
        if self._rwizardengine._rctrlwindowhelper.R_widget != None:
            do_send_to_R(self.resulting_template,self._rwizardengine._rctrlwindowhelper.R_widget,False)
                
    def on_InsertCommentCheck_toggled(self,widget):
        self.add_comment_to_R_code(widget.get_active())
        
    def add_comment_to_R_code(self,insert_comment):
        comment_id = "# RWizard "
        if insert_comment:
            # Insert the comment as the first line:
            comment = comment_id + '"' + self.Description + '" on ' + datetime.datetime.now().strftime("%A, %d %B %Y @ %H:%M:%S") + "\n"
            self.source_buffer.insert(self.source_buffer.get_start_iter(),comment)
            return comment
        else:
            # Try to remove the comment (should be the first line starting with "# RWizard "):
            first_line = self.source_buffer.get_text(self.source_buffer.get_iter_at_line_offset(0,0),self.source_buffer.get_iter_at_line_offset(1,0)).strip()
            if comment_id == first_line[:len(comment_id)]:
                # Remove the first line:
                self.source_buffer.delete(self.source_buffer.get_iter_at_line_offset(0,0),self.source_buffer.get_iter_at_line_offset(1,0))
            return None
                
    #def on_IndentSpin_value_changed(self,widget):
    #    if self.ui.get_widget("IndentRCodeCheckButton").get_active():
    #        self.indent_R_code(widget.get_value_as_int(),self.ui.get_widget("IndentComboBox").get_active()==0)
    #        
    #def on_IndentComboBox_changed(self,widget):
    #    if self.ui.get_widget("IndentRCodeCheckButton").get_active():
    #        self.indent_R_code(self.ui.get_widget("IndentSpin").get_value_as_int(),widget.get_active()==0)
    #        
    #def indent_R_code(self,indent,use_tabs):
    #    self.beautified_template = ""
    #    indent_text = ("\t" if use_tabs else " ")*indent
    #    lines = self.beautified_template_original.split('\n')
    #    comment = self.add_comment_to_R_code(self.ui.get_widget("InsertCommentCheck").get_active())
    #    if comment != None:
    #        lines = [comment.split('\n')[0]] + lines
    #    for line in lines:
    #        self.beautified_template += indent_text + line + "\n"
    #    self.source_buffer.set_text(self.beautified_template)
                
    def update_template(self):
        # Use the user input the complete the script template:
        #print "Filling in the script template:"
        #self.Template.print_debug()
        
        # First, create the list of variables with their values:
        variables = {} # use a dictionary of variables indexed by name
        for block in self.Blocks:
            for variable in block.Variables:
                if variable.ValueDefined:
                    variables[variable.Name] = variable.get_value()
                    
        # And then ask the template to update itself using these variables and return the resulting text:
        updated_template = self.Template.update(variables)
        
        # Return the updated template for further use:
        return updated_template
        

# Class implementing an item within prefs:
class Userprefs_Item:

    def __init__(self):
        # Init:
        self.Rwizard = None
        self.Menu = None
        self.Icon = None
        self.Toolbar = False
        self.Shortcut = None
    
    # Debug printing:
    def print_debug(self):
        print("Item: " +  " " + str(self.Rwizard) + " " + str(self.Menu) + " " + str(self.Icon) + " " + str(self.Toolbar) + " " + str(self.Shortcut))
        

# This class implements the wizards manager:
class RWizardEngine:
    def __init__(self,rctrlwindowhelper):
        # Init the wizards:
        self._rctrlwindowhelper = rctrlwindowhelper
        self._plugin = rctrlwindowhelper._plugin
        self._window = rctrlwindowhelper._window
        self.path = self._plugin.get_data_dir()+"/Wizards/"
        
        # Global defaults:
        self.RootMenuEntry = "Wizards"
        self.ShowOnToolbar = False
        self.ShortcutsActive = False
        # And specific, user-defined preferences:
        self.userprefs = []
        
        # Load the user preferences for wizards:
        self.load_user_prefs()
        
        # Load the wizards:
        self.wizards = self.load_wizards()
        # Sort them alphabetically by menu entry:
        if len(self.wizards) > 1:
            self.wizards.sort(key=lambda x: x.ActualMenu)
        
        # Debug print:
        #self.print_debug()
        
    # Try to read and load the defined wizards:
    def load_wizards(self):
        wizard_files = glob.glob(self.path+"*.xml")
        wizards = []
        for wizard_file in wizard_files:
            if not wizard_file.lower().endswith("userprefs.xml"): # ignore the userprefs.xml file
                wizards = wizards + [self.load_wizard(wizard_file)]
        return wizards
        
    # Try to load and create a wizard from the given file description:
    def load_wizard(self,file_name):
        #print "load_wizard: " + file_name
        rwizard = RWizard(self)
        if rwizard.load(file_name):
            # Debug print:
            #rwizard.print_debug()
            return rwizard
        else:
            # Debug print:
            #rwizard.print_debug()
            return None

    # Load the wizard user preferences:
    def load_user_prefs(self):
        # Open the file for reading:
        try:
            prefs_doc = minidom.parse( self.path + "userprefs.xml" )
        except Exception as inst:
            print("Error opening userprefs.xml!")
            print(type(inst))
            print(inst.args)
            print(inst)
            return False
            
        # Proceed through the DOM and get the relevant stuff:
        root_node = prefs_doc.documentElement;
        if root_node.nodeName.lower() != 'rwizardsuserprefs':
            print("Error: rwizardsuserprefs xml expected, and instead got \"") + root_node.nodeName.lower() + "\"..."
            wizard_doc.unlink()
            return False;
            
        # Get the global attributes:
        if root_node.hasAttribute("rootmenuentry"):
            self.RootMenuEntry = root_node.getAttribute("rootmenuentry")
            
        if root_node.hasAttribute("showontoolbar"):
            self.ShowOnToolbar = root_node.getAttribute("showontoolbar").lower() == "true"
            
        if root_node.hasAttribute("shortcutsactive"):
            self.ShortcutsActive = root_node.getAttribute("shortcutsactive").lower() == "true"
            
        # Process the prefs:
        prefs_node = root_node.getElementsByTagName("prefs")
        if prefs_node != None and len(prefs_node) == 1:
            if not self.do_process_prefs( prefs_node[0] ):
                prefs_doc.unlink()
                return False
        else:
            print("There must a single \"prefs\" node inside a \"rwizardsuserprefs\"")
            prefs_doc.unlink()
            return False
            
        # Everything seems ok:
        prefs_doc.unlink()
        return True
           
    def do_process_prefs(self,xml_node):
        item_nodes = xml_node.getElementsByTagName("item")
        for item_node in item_nodes:
            # Proces this item:
            item_info = Userprefs_Item()
            if item_node.hasAttribute("rwizard"):
                item_info.Rwizard = item_node.getAttribute("rwizard")
            if item_node.hasAttribute("menu"):
                item_info.Menu = item_node.getAttribute("menu")
            if item_node.hasAttribute("icon"):
                item_info.Icon = item_node.getAttribute("icon")
            if item_node.hasAttribute("toolbar"):
                item_info.Toolbar = item_node.getAttribute("toolbar").lower() == "true"
            if item_node.hasAttribute("shortcut"):
                item_info.Shortcut = item_node.getAttribute("shortcut")
            # Add it to the list:
            self.userprefs = self.userprefs + [item_info]
        return True
        
    # Getters for a particular rwizard, allowing the reconciliation of user defined and default preferences:
    def get_menu(self,name):
        for item_info in self.userprefs:
            if item_info.Rwizard == name:
                if item_info.Menu != None:
                    return item_info.Menu
                else:
                    return self.RootMenuEntry
        return self.RootMenuEntry
        
    def get_icon(self,name):
        for item_info in self.userprefs:
            if item_info.Rwizard == name:
                if item_info.Icon != None:
                    return item_info.Icon
                else:
                    return None
        return None
        
    def get_toolbar(self,name):
        for item_info in self.userprefs:
            if item_info.Rwizard == name:
                if item_info.Toolbar != None:
                    return item_info.Toolbar
                else:
                    return self.ShowOnToolbar
        return self.ShowOnToolbar
        
    def get_shortcut(self,name):
        for item_info in self.userprefs:
            if item_info.Rwizard == name:
                if item_info.Shortcut != None:
                    return item_info.Shortcut
                else:
                    return self.ShortcutsActive
        return self.ShortcutsActive
        
    # Debug printing:
    def print_debug(self):
        print("RWizardEngine: " + " " + str(self.RootMenuEntry) + " " + str(self.ShowOnToolbar) + " " + str(self.ShortcutsActive))
        for item_info in self.userprefs:
            item_info.print_debug()
        for wizard in self.wizards:
            wizard.print_debug()



####################################################################################################
#                                                                                                  #
#                                            Code Folding                                          #
#                                                                                                  #
# Heavily inspired by and based on code of Kawaikunee's (http://kawaikunee.blogspot.com/)          #
# 2009 folding gedit plugin (http://code.google.com/p/gedit-folding/)                              #
#                                                                                                  #
# All the credit for the idea and implementation goes to Kawaikunee!!!                             #
#                                                                                                  #
# I just adapted it for R's syntax, rgedit, fixed some bugs and made it look pretty :)             #
#                                                                                                  #
####################################################################################################

# This class is basically a container of the folding engine (to be applied to a given document):
class RCodeFolding:
    
    def __init__(self,_data_dir,_plugin,activate_code_folding=True):
        # Init:
        self.data_dir = _data_dir 
        self._plugin = _plugin
        self.activate_code_folding = activate_code_folding
        self.create_pattern_matcher()
        return
        
    def update_code_folding(self,window,activate_code_folding):
        # DEBUG:
        return
        
        # Update the status of this custom code folding engine:
        if not activate_code_folding:
            # Hide and undo all code fodling that might exist:
            for view in window.get_views():
                self.unfold_all(view.get_buffer(),view)
        self.activate_code_folding = activate_code_folding
        
    # Check is current line contains folded code (return True if it does):
    def is_folded(self,doc,cur_pos_iterator):
        # DEBUG:
        return False
        
        if not self.activate_code_folding:
            return False
            
        if not doc:
            print("Code folding: there must be a document for text to be (un)folded!")
            return False
            
        if not cur_pos_iterator:
            return False
            
        cur_line = cur_pos_iterator #doc.get_iter_at_mark(doc.get_insert())

        # Create the folding markers for this document and view, if not already created:
        tags_table = doc.get_tag_table()
        self.folded_tag = tags_table.lookup('FoldedRCode')
        if self.folded_tag == None: 
            # Clearly not folded :)
            return False
        elif cur_line.has_tag(self.folded_tag):
            # Yes, seems so:
            return True
        else:
            # Nope!
            return False
            
    # Is there a selection in the document (True is there is one):
    def is_selection(self,doc):
        # DEBUG:
        return False
        
        if not self.activate_code_folding:
            return False
            
        if not doc:
            print("Code folding: there must be a document for text to be (un)folded!")
            return False  
        return (len(doc.get_selection_bounds()) == 2)
        
    # Check and possibly create the folding tags:
    def check_create_folding_tags(self,doc,view):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        # Create the folding markers for this document and view, if not already created:
        tags_table = doc.get_tag_table()
        self.folded_tag = tags_table.lookup('FoldedRCode')
        if self.folded_tag == None:
            # Create this tag:
            self.folded_tag = doc.create_tag('FoldedRCode', foreground="green", paragraph_background="lightyellow", style=Pango.Style.ITALIC, weight=Pango.Weight.BOLD, editable=False)
            # and the associated visual mark
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.data_dir+"/folded_code.png" , 24, 24)
            # create the GtkSourceMarkAttributes:
            source_mark_attr = GtkSource.MarkAttributes()
            source_mark_color = Gdk.RGBA()
            source_mark_color.parse("lightyellow")
            source_mark_attr.set_background(source_mark_color)
            source_mark_attr.set_pixbuf(pixbuf)
            try:
                view.set_show_line_marks(True)
            except AttributeError:
                # So it's probably an older version of GtkSourceView: try to use set_show_line_markers:
                view.set_show_line_markers(True)
            
        self.folded_invisible_tag=tags_table.lookup('FoldedRCode_Invisible')
        if self.folded_invisible_tag == None:
            # Create this tag:
            self.folded_invisible_tag = doc.create_tag('FoldedRCode_Invisible',invisible=True)
            
    # The tooltip function for the folded code:
    def folded_code_tooltip(self,mark):
        return None
            
    # Show folding icon mark next to folded code:
    def show_folding_icon(self,doc,view,sel_start):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        # Supposedly, all precondtions are met, so simply create the icon and show it:
        try:
            block_start_mark = doc.create_source_mark(None,"FoldedRCode_Folded",sel_start)
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use create_marker:
            block_start_mark = doc.create_marker(None,"FoldedRCode_Folded",sel_start)
        block_start_mark.set_visible(True)
        
    # And, respectively, delete this folding icon:
    def hide_folding_icon(self,doc,view,cur_line,cur_line_end):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        # Supposedly, all precondtions are met, so simply create the icon and show it:
        start_block = cur_line.copy()
        start_block.backward_line()
        end_block = cur_line_end.copy()
        end_block.forward_line()
        try:
            doc.remove_source_marks(start_block,end_block,"FoldedRCode_Folded")
        except AttributeError:
            # So it's probably an older version of GtkSourceView: try to use delete_marker:
            for marker_to_delete in doc.get_markers_in_region(start_block,end_block):
                if marker_to_delete.get_marker_type() == "FoldedRCode_Folded":
                    doc.delete_marker(marker_to_delete)
            
    
    # Unfold the core on the current line:
    def unfold(self,doc,view,cur_pos_iterator):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        if not doc or not view:
            print("Code folding: there must be a document and view for text to be (un)folded!")
            return
            
        if not cur_pos_iterator:
            return
            
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # Get the current line:
        cur_line = cur_pos_iterator #doc.get_iter_at_mark(doc.get_insert())
        
        # See if the current line is actually representing some folded code:
        if cur_line.has_tag(self.folded_tag):
            try:
                cur_line.set_line_offset(0)
                cur_line_end = cur_line.copy()
                cur_line_end.forward_line()
        
                # Hide the view, disable tooltips and consume the events:
                view.hide_all()
                if use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    view.props.has_tooltip = False
                while Gtk.events_pending():
                    Gtk.main_iteration()

                doc.remove_tag(self.folded_tag, cur_line, cur_line_end)
                cur_line.forward_to_tag_toggle(self.folded_invisible_tag)
                cur_line_end.forward_to_tag_toggle(self.folded_invisible_tag)
                doc.remove_tag(self.folded_invisible_tag, cur_line, cur_line_end)
                #print("Code folding: removed one fold")
            
                # Consume the events, eisable tooltips and show the view:
                while Gtk.events_pending():
                    Gtk.main_iteration()
                view.show_all()
                if use_GtkBuilder_or_Glade():
                    # Gtk supports tooltips:
                    view.props.has_tooltip = True
            except:
                pass
                print("Could not unfold code on the current line...")
                
            self.hide_folding_icon(doc,view,cur_line,cur_line_end)
        else:
            print("Is there a current line?...")
            
        
    # Unfold all folded code in this document:
    def unfold_all(self,doc,view):
        # DEBUG:
        return
        
        if not doc or not view:
            print("Code folding: there must be a document and view for text to be (un)folded!")
            return
            
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # Get the current line:
        start,end=doc.get_bounds()
        
        # Hide the view, disable tooltips and consume the events:
        view.hide_all()
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            view.props.has_tooltip = False
        while Gtk.events_pending():
            Gtk.main_iteration()

        doc.remove_tag(self.folded_tag,start,end)
        doc.remove_tag(self.folded_invisible_tag,start,end)
        self.hide_folding_icon(doc,view,start,end)
            
        # Consume the events, eisable tooltips and show the view:
        while Gtk.events_pending():
            Gtk.main_iteration()
        view.show_all()
        if use_GtkBuilder_or_Glade():
            # Gtk supports tooltips:
            view.props.has_tooltip = True
        
        
    # Fold the current selection:
    def fold_selection(self,doc,view):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        if not doc or not view:
            print("Code folding: there must be a document and view for text to be (un)folded!")
            return
            
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
            
        # If there's a selection to fold, fold it!
        if len(doc.get_selection_bounds()) == 2:
            # Hide the view, disable tooltips and consume the events:
            view.hide_all()
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                view.props.has_tooltip = False
            while Gtk.events_pending():
                Gtk.main_iteration()

            sel_start,sel_end = doc.get_selection_bounds()
            sel_start_end = sel_start.copy()
            sel_start.set_line_offset(0)
            sel_start_end.forward_line()
            sel_end.forward_line()
            doc.apply_tag(self.folded_tag, sel_start, sel_start_end)
            doc.remove_tag(self.folded_tag, sel_start_end, sel_end)
            doc.remove_tag(self.folded_invisible_tag, sel_start_end, sel_end)
            doc.apply_tag(self.folded_invisible_tag, sel_start_end, sel_end)
            # and remove selection:
            doc.select_range(sel_start,sel_start)
            # and place the cursor at the begining of the folded code line:
            doc.place_cursor(sel_start)
            
            self.show_folding_icon(doc,view,sel_start)
            
            # Consume the events, eisable tooltips and show the view:
            while Gtk.events_pending():
                Gtk.main_iteration()
            view.show_all()
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                view.props.has_tooltip = True
        else:
            print("There's no selection to fold...")
            
        
    # Fold the smallest containing block for the current line:
    def fold_containing_block(self,doc,view,cur_pos_iterator):
        # DEBUG:
        return
        
        if not self.activate_code_folding:
            return
            
        if not doc or not view:
            print("Code folding: there must be a document and view for text to be (un)folded!")
            return
            
        if not cur_pos_iterator:
            return
            
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # Get the current line:
        cur_line = cur_pos_iterator.get_line() #doc.get_iter_at_mark(doc.get_insert()).get_line()
        
        # Find the containing block, where a "block" can be:
        # 1. function(...) { BLOCK }
        # 2. for(...){ BLOCK }
        # 3. if(...) { BLOCK } [else {BLOCK} ]
        # 4. repeat { BLOCK }
        # 5. while(...) { BLOCK }
        # The main difficulty is not being fooled by strings containing { or } !
        
        # To make thigs easier, get the whole text file:
        whole_text = doc.get_text(doc.get_start_iter(),doc.get_end_iter()).decode('utf-8') # textbuffer uses UTF-8
        #print whole_text
        
        # First, find all comments and strings in this document:
        comments_in_doc = self._pattern_matcher_comments.finditer(whole_text)
        strings_in_doc  = self._pattern_matcher_strings.finditer(whole_text)
        
        # Create a list of potential block heads:
        actual_block_heads = []
        
        # Check which of potential block heads are inside comments or strings:
        for head in self._pattern_matcher_block_heads.finditer(whole_text):
            # Check if it's inside a comment or a string:
            is_head_ok = True
            for comment in self._pattern_matcher_comments.finditer(whole_text):
                if head.start() >= comment.start() and head.start() <= comment.end():
                    # Bingo: quit this loop:
                    is_head_ok = False
                    break
            if is_head_ok:
                for string in self._pattern_matcher_strings.finditer(whole_text):
                    if head.start() >= string.start() and head.start() <= string.end():
                        # Bingo: quit this loop:
                        is_head_ok = False
                        break
            if is_head_ok:
                # This does not seem to be in a comment or string: add it for now!
                actual_block_heads.append(head)
                
        # So, these block heads are NOT inside comments or strings!
        # Now, check if they blocks and save them as a list of tuples (block_start,block_end,block_type)
        # with the start and end given as offsets in the document and type as a two-letter code:
        blocks_for_heads = [(None,None,None)] * len(actual_block_heads)
        
        i = 0
        for head in actual_block_heads:
            # See which type this is:
            block_type = head.group()[:2]
            if block_type in ["if","fu","fo","wh"]:
                # functions, if, for and while can have parameters as well: 
                # Get its parameters:
                param_start = head.end()-1
                param_end = self.search_matching_paranthesis(whole_text,param_start)
                if param_end != None:
                    # Params seem to be fine: continue by finding the {} block, if any:
                    # Look for the {}, if there:
                    block_start,block_end = self.search_block(whole_text,param_end)
                    #print "For " + head.group() + " at " + str(doc.get_iter_at_offset(head.start()).get_line()+1) + ": (" + (str(doc.get_iter_at_offset(block_start).get_line()+1) if block_start != None else "None") + "," + (str(doc.get_iter_at_offset(block_end).get_line()+1) if block_end != None else "None") + ")"
                    # Save the block for this head:
                    blocks_for_heads[i] = (param_end,block_end,block_type)
            elif block_type in ["re","el"]:
                # else and repeat cannot heave parameters:
                # Find the {} block, if any:
                block_start,block_end = self.search_block(whole_text,head.end())
                #print "For " + head.group() + " at " + str(doc.get_iter_at_offset(head.start()).get_line()+1) + ": (" + (str(doc.get_iter_at_offset(block_start).get_line()+1) if block_start != None else "None") + "," + (str(doc.get_iter_at_offset(block_end).get_line()+1) if block_end != None else "None") + ")"
                # Save the block for this head:
                blocks_for_heads[i] = (head.end(),block_end,block_type)
            else:
                # What the heck is this?
                print("Unexpected match: '" + head.group() + "'...")
            # Go to the next element in the list:
            i = i + 1
        
        # Delete those heads for which getting the blocks failed for various reasons or for which the block take only one line:
        i = 0
        while i < len(actual_block_heads):
            # See if this head has a real block associated:
            if blocks_for_heads[i][0] == None or blocks_for_heads[i][1] == None or doc.get_iter_at_offset(blocks_for_heads[i][0]).get_line() == doc.get_iter_at_offset(blocks_for_heads[i][1]).get_line():
                # Remove it:
                del blocks_for_heads[i]
                del actual_block_heads[i]
            else:
                i += 1
            
        ## DEBUG: print the blocks list:
        #print blocks_for_heads
        
        # Now, find the blocks containing the current line following the user's preferences given in self.prefs['code_folding_block_preference']:
        containing_blocks_indices = []
        highest_block    = (None,0) # The highest level (biggest) block as a pair (index,number_of_lines)
        lowest_block     = (None,0) # The lowest level (smallest) block as a pair (index,number_of_lines)
        highest_function = (None,0) # The highest level (biggest) function block as a pair (index,number_of_lines)
        lowest_function  = (None,0) # The lowest level (smallest) function block as a pair (index,number_of_lines)
        for i in range(len(blocks_for_heads)):
            line1 = doc.get_iter_at_offset(blocks_for_heads[i][0]).get_line()
            line2 = doc.get_iter_at_offset(blocks_for_heads[i][1]).get_line()
            if cur_line >= line1 and cur_line <= line2:
                # This block does contain it!
                containing_blocks_indices += [i]
                
                # See if this the highest-level (biggest) block to date:
                if highest_block[1] < (line2 - line1):
                    # Nope: make it so!
                    highest_block = (i,line2 - line1)
                    
                # See if this the lowest-level (smallest) block to date:
                if lowest_block[1] == 0 or lowest_block[1] > (line2 - line1):
                    # Nope: make it so!
                    lowest_block = (i,line2 - line1)
                
                # Function blocks:
                if blocks_for_heads[i][2] == "fu":
                # See if this the highest-level (biggest) function block to date:
                    if highest_function[1] < (line2 - line1):
                        # Nope: make it so!
                        highest_function = (i,line2 - line1)
                    
                    # See if this the lowest-level (smallest) function block to date:
                    if lowest_function[1] == 0 or lowest_function[1] > (line2 - line1):
                        # Nope: make it so!
                        lowest_function = (i,line2 - line1)
                        
        # See what type of block the user whatns folded:
        block_to_fold = None
        if self._plugin.prefs['code_folding_block_preference'] == 'highest_block':
            if highest_block[1] > 0:
                block_to_fold = highest_block
            else:
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No block contains the current line, thus nothing to fold...") )
                info_dialog.run()
                info_dialog.destroy()
                return
        elif self._plugin.prefs['code_folding_block_preference'] == 'lowest_block':
            if lowest_block[1] > 0:
                block_to_fold = lowest_block
            else:
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No block contains the current line, thus nothing to fold...") )
                info_dialog.run()
                info_dialog.destroy()
                return
        elif self._plugin.prefs['code_folding_block_preference'] == 'highest_function':
            if highest_function[1] > 0:
                block_to_fold = highest_function
            elif highest_block[1] > 0:
                block_to_fold = highest_block
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No function block contains the current line, falling back to any type of block...") )
                info_dialog.run()
                info_dialog.destroy()
            else:
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No block contains the current line, thus nothing to fold...") )
                info_dialog.run()
                info_dialog.destroy()
                return
        elif self._plugin.prefs['code_folding_block_preference'] == 'lowest_function':
            if lowest_function[1] > 0:
                block_to_fold = lowest_function
            elif lowest_block[1] > 0:
                block_to_fold = lowest_block
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No function block contains the current line, falling back to any type of block...") )
                info_dialog.run()
                info_dialog.destroy()
            else:
                info_dialog = Gtk.MessageDialog( None, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, _("No block contains the current line, thus nothing to fold...") )
                info_dialog.run()
                info_dialog.destroy()
                return
                
        ## DEBUG:
        #print "Containing blocks: " + str(containing_blocks_indices) + " and the higest-level block is " + str(highest_block[0])
        
        # If there's a block to fold, fold it!
        if block_to_fold[1] > 0:
            # Do the folding:
            #Gdk.event_handler_set(self.func,None)
            
            # Hide the view, disable tooltips and consume the events:
            view.hide_all()
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                view.props.has_tooltip = False
            while Gtk.events_pending():
                Gtk.main_iteration()

            #print "block: " + str(doc.get_iter_at_offset(blocks_for_heads[highest_block[0]][0]).get_line()+1) + " to " + str(doc.get_iter_at_offset(blocks_for_heads[highest_block[0]][1]).get_line()+1)
            block_start = doc.get_iter_at_offset(blocks_for_heads[block_to_fold[0]][0])
            block_end   = doc.get_iter_at_offset(blocks_for_heads[block_to_fold[0]][1])
            block_start.set_line_offset(0)
            block_start_end = block_start.copy()
            block_start_end.forward_line()
            block_end.set_line_offset(0)
            block_end.forward_line()
            # place the cursor at the begining of the folded code line:
            doc.place_cursor(block_start)
            # do the actual folding:
            doc.apply_tag(self.folded_tag, block_start, block_start_end)
            doc.remove_tag(self.folded_tag, block_start_end, block_end)
            doc.remove_tag(self.folded_invisible_tag, block_start_end, block_end)
            doc.apply_tag(self.folded_invisible_tag, block_start_end, block_end)
            self.show_folding_icon(doc,view,block_start)
            
            # Consume the events, eisable tooltips and show the view:
            while Gtk.events_pending():
                Gtk.main_iteration()
            view.show_all()
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                view.props.has_tooltip = True
        else:
            print("There's no block to fold...")
            
    #def func(self, event, user_data):
    #    print "Got gdk event!"
    #    Gtk.main_do_event(event)
    #    return True
            
    def search_matching_paranthesis(self,whole_text,param_start):
        # DEBUG:
        return
        
        # Serach for the matching closed paranthesis of the open one at the param_start position:
        # Matching parantheses to consider: (), [] and {} and, of course, no comments # and strings "" or '':
        if whole_text[param_start] !="(":
            print("'Expecting (' but instead got '") + whole_text[param_start] + "'!"
            return None
        # Initialize the counters for each type of thing (as a dictionary):
        counters = {'(':1,'[':0,'{':0,'#':0,'"':0,"'":0}
        # And start scanning:
        cur_pos = param_start+1
        while counters['('] > 0 and cur_pos < len(whole_text):
            # See what I'm looking at:
            cur_char = whole_text[cur_pos]
            # and advance to the next char:
            cur_pos += 1
            
            # Process the strings first:
            if cur_char == '"' and counters['#'] == 0:
                # Begining or end of string?
                if counters['"'] > 0:
                    # String's ending!
                    counters['"'] = 0
                    continue
                else:
                    # String's begining:
                    counters['"'] = 1
                    continue
            if cur_char == "'" and counters['#'] == 0:
                # Begining or end of string?
                if counters["'"] > 0:
                    # String's ending!
                    counters["'"] = 0
                    continue
                else:
                    # String's begining:
                    counters["'"] = 1
                    continue
            # See if this char is within a string:
            if counters['"'] > 0 or counters["'"] > 0:
                # Indeed: skip it!
                continue
            
            # Process comments now:
            if cur_char == '#':
                # Begining of a comment!
                counters['#'] = 1
                continue
            if counters['#'] > 0:
                # I'm within a comment:
                if cur_char == '\n':
                    # but got a newline -> comment it over!
                    counters['#'] = 0
                continue

            # Not in a comment or string: look for matching parantheses:
            if cur_char == "(":
                counters['('] += 1
            elif cur_char == ")":
                counters['('] -= 1
                if counters['('] == 0 and counters['['] == 0 and counters['{'] == 0:
                    # This is the happy end!!!
                    return cur_pos
            elif cur_char == "[":
                counters['['] += 1
            elif cur_char == "]":
                counters['['] -= 1
                if counters['['] < 0:
                    # Oops!
                    print("Error matching parantheses...")
                    return None
            elif cur_char == "{":
                counters['{'] += 1
            elif cur_char == "}":
                counters['{'] -= 1
                if counters['{'] < 0:
                    # Oops!
                    print("Error matching parantheses...")
                    return None
            
        return None
        
    def search_block(self,whole_text,param_end):
        # DEBUG:
        return
        
        # Serach for the {} block following the params list (if any) and return the begining and end as a pair:
        # Consume all whitespaces and comments:
        block_start = None
        block_end   = None
        cur_pos = param_end
        while cur_pos < (len(whole_text)-1):
            # Skip any white spaces here:
            cur_pos = self.skipws(whole_text,cur_pos)
            if cur_pos < (len(whole_text)-1):
                if whole_text[cur_pos] == "#":
                    # Skip this comment as well:
                    cur_pos = self.skipcomment(whole_text,cur_pos)
                else:
                    # This is where the instruction or block should be:
                    if whole_text[cur_pos] == "{":
                        # It's a block: 
                        block_start = cur_pos
                        # and look for its end!
                        block_end   = self.search_block_end(whole_text,block_start)
                        return (block_start,block_end)
                    else:
                        # Just an instruction, no block:
                        return (None,None)
        return (None,None)
        
    def skipws(self,whole_text,cur_pos):
        # DEBUG:
        return
        
        # Skip white spaces:
        while cur_pos < len(whole_text)-1 and whole_text[cur_pos].isspace():
            cur_pos += 1
        return cur_pos
        
    def skipcomment(self,whole_text,cur_pos):
        # DEBUG:
        return
        
        # Skip comments:
        if cur_pos < len(whole_text)-1 and whole_text[cur_pos] == "#":
            # Comment starts: eat it until the first newline:
            while cur_pos < len(whole_text)-1 and not whole_text[cur_pos] in ['\n','\r']:
                cur_pos += 1
        return cur_pos
            
    def search_block_end(self,whole_text,block_start):
        # DEBUG:
        return
        
        # Serach for the matching closing block "}" of the open one at the block_start position:
        # Matching parantheses to consider: (), [] and {} and, of course, no comments # and strings "" or '':
        if whole_text[block_start] !="{":
            print("Expecting '{' but instead got '") + whole_text[param_start] + "'!"
            return None
        # Initialize the counters for each type of thing (as a dictionary):
        counters = {'(':0,'[':0,'{':1,'#':0,'"':0,"'":0}
        # And start scanning:
        cur_pos = block_start+1
        while counters['{'] > 0 and cur_pos < len(whole_text):
            # See what I'm looking at:
            cur_char = whole_text[cur_pos]
            # and advance to the next char:
            cur_pos += 1
            
            # Process the strings first:
            if cur_char == '"' and counters['#'] == 0:
                # Begining or end of string?
                if counters['"'] > 0:
                    ## DEBUG
                    #print "Ending a " + '"' + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                    # String's ending!
                    counters['"'] = 0
                    continue
                else:
                    ## DEBUG
                    #print "Starting a " + '"' + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                    # String's begining:
                    counters['"'] = 1
                    continue
            if cur_char == "'" and counters['#'] == 0:
                # Begining or end of string?
                if counters["'"] > 0:
                    ## DEBUG
                    #print "Ending a " + "'" + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                    # String's ending!
                    counters["'"] = 0
                    continue
                else:
                    ## DEBUG
                    #print "Starting a " + "'" + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                    # String's begining:
                    counters["'"] = 1
                    continue
            # See if this char is within a string:
            if counters['"'] > 0:
                ## DEBUG
                #print "Inside a " + '"' + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                # Indeed: skip it!
                continue
            if counters["'"] > 0:
                ## DEBUG
                #print "Inside a " + "'" + " string: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                # Indeed: skip it!
                continue
            
            # Process comments now:
            if cur_char == '#':
                ## DEBUG
                #print "Starting a comment: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                # Begining of a comment!
                counters['#'] = 1
                continue
            if counters['#'] > 0:
                # I'm within a comment:
                if cur_char in ['\n','\r']:
                    ## DEBUG
                    #print "Ending a comment: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                    # but got a newline -> comment it over!
                    counters['#'] = 0
                    continue
                ## DEBUG
                #print "Inside a comment: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
                continue

            # Not in a comment or string: look for matching parantheses:
            ## DEBUG
            #print "Normal text: '" + (cur_char if not cur_char in ['\n','\r'] else "NL") + "'" + str(counters)
            
            if cur_char == "{":
                counters['{'] += 1
            elif cur_char == "}":
                counters['{'] -= 1
                if counters['{'] == 0:
                    # This is the happy end!!!
                    return cur_pos
            elif cur_char == "[":
                counters['['] += 1
            elif cur_char == "]":
                counters['['] -= 1
                if counters['['] < 0:
                    # Oops!
                    print("Error matching parantheses...")
                    return None
            elif cur_char == "(":
                counters['('] += 1
            elif cur_char == ")":
                counters['('] -= 1
                if counters['('] < 0:
                    # Oops!
                    print("Error matching parantheses...")
                    return None
            
        #print "Did not find '{' by the end of the file: " + str(counters)
        return None
         
    def create_pattern_matcher(self):
        # DEBUG:
        return
        
       # Create the appropriate pattern matcher for blocks (see fold_containing_block above):
        pattern_definition_block_heads = r""
        
        # 1. function(...) { BLOCK }
        pattern_definition_block_heads += r"function\s*\("
        # 2. for(...){ BLOCK }
        pattern_definition_block_heads += (r"|" + r"for\s*\(")
        # 3. if(...) { BLOCK } [else {BLOCK} ]
        pattern_definition_block_heads += (r"|" + r"if\s*\(|else")
        # 4. repeat { BLOCK }
        pattern_definition_block_heads += (r"|" + r"repeat")
        # 5. while(...) { BLOCK }
        pattern_definition_block_heads += (r"|" + r"while\s*\(")
        
        self._pattern_matcher_block_heads = re.compile(pattern_definition_block_heads)
        
        # The pattern matchers for strings and comments:
        pattern_definition_comments = r"#.*"
        pattern_definition_strings  = r"'.*'" + r"|" + r'".*"'
        
        self._pattern_matcher_comments = re.compile(pattern_definition_comments)
        self._pattern_matcher_strings  = re.compile(pattern_definition_strings)
        
        
    # Ask the code folding engine to provide some tooltip for this position (if any) and return (do_tooltip,tooltip_text):
    def get_tooltip(self, view, doc, position_iter ):
        # DEBUG:
        return
        
        # See if this iterator is on a folded code line:
        
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # See if the current line is actually representing some folded code:
        folded_text= self.get_folded_text(doc,view,position_iter)
        if folded_text != None:
            # Good, extract the first two and the last two lines:
            first_lines_no = 3
            last_lines_no  = 3            
            tooltip_text = None
            
            text_lines = folded_text.splitlines() # don't keep line breaks in there
            text_lines = [s for s in text_lines if s.strip()] # remove empty lines
            if len(text_lines) <= (first_lines_no + last_lines_no):
                # Display the whole text:
                tooltip_text = '> ' + '\n> '.join(text_lines)
            else:
                # Use only the few first and last lines:
                tooltip_text = '> ' + '\n> '.join(text_lines[:first_lines_no]) + "\n..........\n> " + '\n> '.join(text_lines[-last_lines_no:])

            return (True,tooltip_text)
        
        return (False,None)
        
    def inspect_folded_code(self,doc,view,cur_pos_iterator):
        # DEBUG:
        return
        
        # Display the folded text here:
        if not self.activate_code_folding:
            return
            
        if not doc or not view:
            print("Code folding: there must be a document and view for text to be (un)folded!")
            return
            
        if not cur_pos_iterator:
            return
            
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # Get the current line:
        cur_line = cur_pos_iterator #doc.get_iter_at_mark(doc.get_insert())
        
        # Get folded text at the current line (if any):
        folded_text= self.get_folded_text(doc,view,cur_line)
        if folded_text != None:
            # Display it!
            # Create a top-level dialog with one button (Close) and a scrollable TextView:
            dialog = Gtk.Dialog(_("Inspecting folded code..."),
                               None,
                               Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT)
            
            # The info lable at the top:
            info_label = Gtk.Label(label=_("Folded code at line ") + str(cur_line.get_line()+1) + _(":"))
            info_label.show()
            dialog.vbox.pack_start(info_label,expand=False,fill=False)
            
            # The TextView and associated TextBuffer:
            code_view = Gtk.TextView(None)
            code_text = code_view.get_buffer()
            code_text.set_text(folded_text)
            code_view.set_editable(False)
            code_view.show()
            
            # Scroll support:
            scrolled_window = Gtk.ScrolledWindow(hadjustment=None, vadjustment=None)
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            dialog.vbox.pack_start(scrolled_window, True, True, 0)
            scrolled_window.show()
            scrolled_window.add_with_viewport(code_view)

            # The unfold code button:
            unfold_button = dialog.add_button(_("Unfold"), 1 ) # Unfold code
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                unfold_button.set_tooltip_text(_("Unfold the code and close"))
            
            # The close button:
            close_button = dialog.add_button(_("Close"), 0 ) # Close
            if use_GtkBuilder_or_Glade():
                # Gtk supports tooltips:
                close_button.set_tooltip_text(_("Close without unfolding the code"))
            
            # The initial dialog size:
            dialog.resize( 600, 400 )
        
            # Collect the user's response:
            response = dialog.run()
            if response == 1:
                # Try to unfold the code as told:
                #doc.place_cursor(cur_line) # make sure the current line is the current one!
                self.unfold(doc,view,cur_pos_iterator)
            
            # Close the dialog:
            dialog.destroy()
                
        
    def get_folded_text(self, doc, view, folded_start_line):
        # DEBUG:
        return
        
        # Get the text in the folded section begning here:
        # Make sure the folding tags are defined:
        self.check_create_folding_tags(doc,view)
        
        # See if the current line is actually representing some folded code:
        if folded_start_line.has_tag(self.folded_tag):
            # Good: now, try ot get the actually folded text:
            folded_start_line.set_line_offset(0)
            folded_end_line = folded_start_line.copy()
            folded_end_line.forward_lines(1)
            folded_end_line.forward_to_tag_toggle(self.folded_invisible_tag)
            folded_text = doc.get_text(folded_start_line,folded_end_line)
            return folded_text
        return None
        
            


        
        
