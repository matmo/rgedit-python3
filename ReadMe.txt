##############################################################################
#                                                                            #
#    Rgedit: gedit plugin for R                                              #
#    Copyright (C) 2009-2011  Dan Dediu                                      #
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
#                                                                            #
##############################################################################


1. INSTALLATION

To install, extract the RgeditXX.tar.bz2 archive somewhere and, depending on your
gedit's major version, copy the contents of the resulting folder into to your
 ~/.gnome2/gedit/plugins folder (please note the "." dot; create this folder if 
necessary) for gedit2, and ~/.local/share/gedit/plugins for gedit3. 

Now, your ~/.gnome2/gedit/plugins or ~/.local/share/gedit/plugins folder should also contain:

RCtrl        <- this is a folder
RCtrl.gedit-plugin
RCtrl.py
ReadMe.txt   <- this ReadMe.txt file

Then activate the "R Integration" plug-in from gedit.

The preferences are saved in ~/.rgedit-preferences.


For details, please consult the help file either from withing gedit (R -> Help) or by
opening the Help.html file from the RCtrl/Help folder.

Please check for updates on the project's web page at
http://sourceforge.net/projects/rgedit/

Enjoy using it and don't forget to send feedback, suggestions and bug reports!

Dan Dediu,
December 2012



+-----------------------------------------+
|                                         |
|              CHANGELIST                 |
|                                         |
+-----------------------------------------+



#####   0.1:   #####

Initial release



#####   0.1 -> 0.2:   #####

Various enhancements and bug fixes.



#####   0.2 -> 0.3:   #####

Keyboard shortcuts can be defined by the user.



#####   0.3 -> 0.4:   #####

<Ctrl+Tab> allows switching between the active document and the active R console.



#####   0.4 -> 0.5:   #####

The R consoles can be either attached to (embedded into) gedit's bottom panel (the default) or an independent top-level window which can be freely moved and resized.



#####   0.5 -> 0.6:   #####

Fixed a bug concerning attaching/detaching the R console.
Added a Close R Console menu entry which will close everything down.
Fixed an issue with enabling/disabling menu entries depending on the presence or not of an R console.



#####   0.6 -> 0.6.1:   #####

Fixed various typos. Attach/detach and close console commands now can have user-definable keyboard shortcuts.
Now, closing an R tab (or all of them through "Close R Console") does it the "hard" way, by sending the subtending shell process a SIGHUP signal (as opposed to the "soft" way, which simply sent "q()" followed by "exit", relaying on the R console to be ready to process commands). This ensures that run-away processes are stopped as well and their resources are promptly freed.



#####   0.6.1 -> 0.6.2:   #####

Fixed attach/detach problem on Hardy.



#####   0.6.2 -> 0.6.3:   #####

If the current line or the last line of the selection do not end in a carriage return, they would not be executed by the R console (an ENETR would be required): this was fixed by appending a '\n' if absent.



#####   0.6.3 -> 0.6.4:   #####

Some window managers (e.g., metacity in Gnome) would not manage correctly a detached R console (e.g, minimizing the gedit window with a detached R console would result in an impossibility to restore the gedit window). This was fixed by making the detached R console a top-level window, allowing it to me minimized/restored independently of the gedit window even in metacity.



#####   0.6.4 -> 0.6.5:   #####

Fixed one spelling mistake and added the capacity to check for an updated version, the possibility to run a script at startup and to skip empty and comment lines when sending the current line to the R console, plus adding a few menu items to the R console context menu as well.



#####   0.6.5 -> 0.6.5.1:   #####

Minor bugfix on loading and saving workspaces.



#####   0.6.5.1 -> 0.6.5.2:   #####

Minor bugfix of a crash when the path to the autorun R script is empty.



#####   0.6.5.2 -> 0.6.5.3:   #####

Minor feature added: automatically make the bottom panel visible when adding an R workspace (instead of having to make it visible manually).



#####   0.6.5.3 -> 0.7.0:   #####

Major release.
Fixed several minor bugs, added minor features (e.g., the capacity to use the current document's directory and the current working directory), reorganization of the menus.
Added two new major features:
1. side panel allowing the navigation within R files - can consider function defintions, data.frame defintions and specially formatted "landmark" comments;
2. wizards allowing user to generate customized R code from pre-defined templates using a GUI.



#####   0.7.0 -> 0.7.0.1:   #####

Fixed a bug appearing when defining a variable named "T" which would interfere with piping commands to R (thanks to Bertrand Marc).
Added a new option telling R not to echo commands sent through source() (thanks to Axolotl9250).



#####   0.7.0.1 -> 0.7.0.2:   #####

Mateusz Kaduk added a patch to fix rgedit when installed system-wide, moved the .preferences file to $HOME/.rgedit.preferences so that it can be accessed no matter where the plugin is installed and fixed file permissions for non-executable.
Thanks, Mateusz!



#####   0.7.0.2 -> 0.7.0.3:   #####

Possible to define "special" shortcuts involving Return and modifiers (<CTRL>,<SHIFT>,<ALT>) for sending line/block/file/selection to R (thanks to Alex Ruiz).
The position & size of the detached R console are saved (thanks to Alex Ruiz).
Newly started R sessions can use the current document's directory.



#####   0.7.0.3 -> 0.7.0.4:   #####

Update this ReadMe.txt to reflect the change in the position of the preferences file. 
Fixed a bug preventing changing the names of R tabs. 
Added the possibility to specify the position of R tabs (top, left, right or bottom) and if you wish the tabs to be always displayed (even when having a single tab); these options are controlled through the R console right-click menu. 
Fixed the HTML help, which changed in recent versions of R.



#####   0.7.0.4 -> 0.7.0.5:   #####

Pressing <Ctrl>K in the R console copies the last executed line to the clipboard, while <Ctrl><Shift>K also pastes this into the current gedit tab at the cursor's position (thanks to Alexandre Cesari for the suggestion). 
For this to work you must have xclip (http://sourceforge.net/projects/xclip/) or Xsel (http://www.vergenet.net/~conrad/software/xsel/) on you *nix machine [pbcopy (http://developer.apple.com/mac/library/documentation/Darwin/Reference/ManPages/man1/pbcopy.1.html) for MacOS X]. 
Also, please note that the call to the internal helper .rgedit.lastline2clipboard() function, even if displayed in the R console, is not saved in the command history.
It is possible now to use <Ctrl>C in the R console to copy the selection to clipboard (options in the "Edit keyboard shortcuts" dialog, disabled by default; in this case you can define ESC or <Ctrl>Q to replace it for computation breaking).
Now, there is a new file in /RCtrl/messages_and_warnings.txt which contains the most notable changes and warning and, by default, these are displayed in the R console upon start (this can be changed using the settings dialog).



#####   0.7.0.5 -> 0.7.0.6:   #####

The rgedit-specific UI elements (toolbar and updating of the file's structure) can be shown/activated for R source files only (as identified by their associated Language) using the check menu item R -> Show/hide toolbar -> Show toolbar only for R files... Please not that following a manual change of a file's Language (using View -> Highlight mode) you must save the file for the change to be felt.
Minor redesign of the Configuration dialog box to better fit on small netbook screens.
Switch from glade to gtkbuilder.
Starting preparing for localization: Python source code strings marked with _(...). Added Romanian (ro) translation but not yet functional (help with localization much appreciated!).



#####   0.7.0.6 -> 0.7.0.7:   #####

Fixes several compatibility problems with older systems (such as RHEL5 and CentOS5) which use Python < 2.5 (no inline if...else statements) and gtk < 2.12 (glade instead of gtkbuilder, tooltip issues): thanks to Peter Forster for bug reporting and testing.
However, it is strongly recommended to use a newer Python (2.5+) and gtk (2.12+) to get all the features working!



#####   0.7.0.7 -> 0.7.1.0:   #####

Code folding: basic functionalities to fold a selection or a block containing the current line. 
Add "run up to current line" which sends to R all the code up to and including the current line of text.
Fixed some small bugs (defintion of blocks of code, number of lines to be sent directly to the R conole).
The temporary file used to communicate with R is now created with a dynamic & unique name instead of a fixed name (thanks to Peter Forster).



#####   0.7.1.0-Gtk3:   #####

Initial port to Gtk3 (gedit3). Most features work as in the Gtk2 version except code folding and Ctrl+C for copying in the R console and ESC for breaking the R code: these are replaced by Ctrl+X for copying and Ctrl+C for breaking the R code.
Please treat as BETA and report all bugs! I tested it on a Fedora 15 Xfce.



#####   0.7.1.2-Gtk3:   #####

Fixed minor issue with detched R console.
Recommended package: "colorout" for colorizing the R console output (thanks to Jakson Alves de Aquino).



#####   0.8-Gtk3:       #####

Workspace loading and saving implicitely open in the current document's folder.
R -> Load script's libraries: parses the script and identifies all library() entries and allows the user to select which libraries to load.
Make "Run selection" run the current line if there's no selection and change the order of the menu and toolbar entries.
Profiles can be defined and used, allowing rgedit to interact with Python, Octave or even remote sessions through SSH.



#####   0.8.0.1-Gtk3:   #####

Minor bugfix: sometimes the icon marking the current profile in the menus was not visible.



#####   0.8.0.2-Gtk3:   #####

Minor bugfix: Ctrl+Tab switches between R console and edtor, and Ctrl+C breaks the computation (with Ctrl+X copying selection from R console)


















