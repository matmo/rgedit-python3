###############################################################################
##                                                                           ##
##    Script containing R functions and misc stuff needed by rgedit.         ##
##    This is an integral part of rgedit.                                    ##
##                                                                           ##
##    Copyright (C) 2009-2010  Dan Dediu                                     ##
##                                                                           ##
##    This program is free software: you can redistribute it and/or modify   ##
##    it under the terms of the GNU General Public License as published by   ##
##    the Free Software Foundation, either version 3 of the License, or      ##
##    (at your option) any later version.                                    ##
##                                                                           ##
##    This program is distributed in the hope that it will be useful,        ##
##    but WITHOUT ANY WARRANTY; without even the implied warranty of         ##
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          ##
##    GNU General Public License for more details.                           ##
##                                                                           ##
##    You should have received a copy of the GNU General Public License      ##
##    along with this program.  If not, see <http://www.gnu.org/licenses/>.  ##
##                                                                           ##
###############################################################################


#########################################################################################################
# Copy the last line (plus a newline) to clipboard (can use xclip and xsel on *nix and pbcopy on MacOSX): 
#########################################################################################################
.rgedit.lastline2clipboard <- function( clipboard.command = "xclip" ) 
{
  # The possible clipboard commands:
  clipboard.commands <- c( "xclip", "xsel", "pbcopy" );
  # The correct command line depending on the option used:
  pipe.commands <- c( "xclip -i -selection clipboard", "xsel --clipboard", "pbcopy" );
  names(pipe.commands) <- clipboard.commands;

  # Try to detect which clipboard commands are installed in the system:
  available.clipboard.commands <- c( FALSE, FALSE, FALSE ); names(available.clipboard.commands) <- clipboard.commands;
  for( i in 1:length(available.clipboard.commands) )
  {
    available.clipboard.commands[i] <- length(system( paste( "command -v ", names(available.clipboard.commands)[i], sep=""), intern=TRUE )) > 0;
  } 
  if( sum(available.clipboard.commands) == 0 )
  {
    stop( "No cpliboard manipulation programs installed on your machine! Please install xclip or xsel (on *nix) and pbcopy (on MacOSX)!\n" );
  }

  # Try to satisfly the user's preference:
  if( sum(clipboard.command == names(pipe.commands)) == 0 )
  {
    # Unknown clipboard command: print a warning and try your best:
    cat( "Warning: unknown option ", clipboard.command );
    clipboard.command = (names(available.clipboard.commands)[available.clipboard.commands])[1];
    cat( " -- using ", clipboard.command, " instead...\n" );
  }
  else if( !available.clipboard.commands[clipboard.command] )
  {
    # Preferred command not installed: print a warning and try your best:
    cat( "Warning: requested command ", clipboard.command );
    clipboard.command = (names(available.clipboard.commands)[available.clipboard.commands])[1];
    cat( " -- using ", clipboard.command, " instead...\n" );
  }

  # Save whole shitory to temporaty file:
  hist.file <- tempfile( "Rhistory" );
  savehistory( hist.file );
  full.hist <- readLines( hist.file );
  unlink( hist.file );

  # Read the last line before this one:
  last.line <- full.hist[ length(full.hist)-1 ];
 
  # And copy it to the clipboard: 
  clipboard.pipe <- pipe( pipe.commands[clipboard.command], "w" );
  cat( paste(last.line,"\n",sep=""), file=clipboard.pipe );
  close( clipboard.pipe );
  
  # Restore the history without the last command:
  hist.file <- tempfile( "Rhistory" );
  writeLines( full.hist[ -length(full.hist) ], hist.file );
  loadhistory( hist.file );
  unlink( hist.file );
}


