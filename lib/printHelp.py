import logging
from commands import COMMAND_HELP, COMMAND_HELP_SESSION

def processHelp(commandsObj, requestStr):
   if len(requestStr) == 0:
      logging.error("empty help command")
      return
   elif requestStr == COMMAND_HELP:
      print (commandsObj.getHelpStr())
      return
   else:
      theCommand = commandsObj
      keys = requestStr.split()
      for i in range(1, len(keys)):
         theCommand = theCommand.getChild(keys[i])
      print (theCommand.getHelpStr())
