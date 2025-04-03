import logging
from decimal import Decimal

COMMAND_EXIT = "exit"

COMMAND_HELP = "help"
COMMAND_HELP_SESSION = "help session"

COMMAND_BALANCE_SHOW = "balance show"
COMMAND_BALANCE_LIST = "balance list"

COMMAND_SUBACCOUNT_CREATE = "subaccount create"

COMMAND_WITHDRAW = "withdraw"
COMMAND_DEPOSIT = "deposit"
COMMAND_LOAD_DEPOSIT_ADDRESS = "deposit_address"


class OptionalArgumentValue(object):
    def __init__(self, value, descr=""):
        self.value = value
        self.descr = descr


class CommandArgument(object):
    def __init__(self, name, argType, optional=False, skip=False, values=[]):
        self.name = name
        self.argType = argType
        self.optional = optional
        self.skip = skip

        # for optional arguments, if values are set, index 0
        # is considered the default value
        self.values = values

    def getDefaultValue(self):
        if len(self.values) > 0 and not self.skip:
            return self.values[0].value
        return None

    def getFormattedValue(self, value):
        formattedValue = value
        if self.argType == "str":
            formattedValue = str(value)
        elif self.argType == "int":
            formattedValue = int(value)
        elif self.argType == "Decimal":
            formattedValue = Decimal(value)

        if len(self.values) > 0:
            valueNames = [v.value for v in self.values]
            if formattedValue not in valueNames:
                logging.error(
                    f'["{value}"] is not a valid value for argument [{self.name}]'
                )
                logging.error(f"eligible values are: {valueNames}")
                raise Exception("invalid value")
        return formattedValue


class Command(object):
    def __init__(self, name, args=[], helpMsg="", children=None):
        self.name = name
        self.helpMsg = helpMsg
        self.parent = None

        self.children = {}
        if children:
            for child in children:
                self.addChild(child)

        self.args = args
        self._minArgsCount = 0
        for arg in args:
            if arg.optional:
                continue
            self._minArgsCount += 1

    def addChild(self, child):
        child.parent = self
        self.children[child.name] = child

    def hasChildren(self):
        return len(self.children) != 0

    def getChild(self, key):
        if key in self.children:
            return self.children
        return None

    def getHelpStr(self, depth=1):
        if depth == 0 or not self.children:
            helpStr = f"{self.name}"
            for arg in self.args:
                helpStr += f" [{arg.name}]"
            helpStr += f": {self.helpMsg}"

            for arg in self.args:
                if not arg.values:
                    continue
                helpStr += f"\n     | [{arg.name}] values"
                optionsStr = ""
                if arg.optional:
                    optionsStr = " (optional"
                if arg.values:
                    if not optionsStr:
                        optionsStr = " ("
                    else:
                        optionsStr += ", "
                    optionsStr += f"default: {arg.getDefaultValue()})"
                helpStr += optionsStr

                hasDescr = False
                for value in arg.values:
                    if value.descr:
                        hasDescr = True
                        break

                if hasDescr:
                    for value in arg.values:
                        helpStr += f"\n     |-- {value.value}: {value.descr}"
                else:
                    oneLineArgs = ""
                    for value in arg.values:
                        oneLineArgs += f"{value.value}/"
                    helpStr += f" - {oneLineArgs[:-1]}"

        else:
            helpStr = f" - {self.name} commands:\n"
            for childName in self.children:
                child = self.children[childName]
                helpStr += f"   . {child.getHelpStr(depth - 1)}\n"
        return helpStr

    def getFullName(self):
        fullName = ""
        if self.parent:
            fullName = f"{self.parent.getFullName()} "
        return fullName + self.name

    def minArgsCount(self):
        return self._minArgsCount

    def maxArgsCount(self):
        return len(self.args)

    def getArg(self, index: int):
        if index >= self.maxArgsCount():
            return None
        return self.args[index]


class Commands(object):
    def __init__(self):
        self.commands = {}
        self.setup()
        self.lastCommand = ""

    def setup(self):
        ### exit ###
        self.addCommand(Command("exit", [], "shutdown client"))

        self.addCommand(
            Command(
                "subaccount",
                [],
                'Subaccount manage, type "help subaccount" to get more help',
                [
                    Command(
                        "create",
                        [CommandArgument("email", "str")],
                        "creates a subaccount",
                    )
                ],
            )
        )

        self.addCommand(
            Command(
                "withdraw",
                [
                    CommandArgument("address", "str"),
                    CommandArgument("currency", "str"),
                    CommandArgument("amount", "str"),
                    CommandArgument("entity_id", "int", optional=True, skip=True),
                ],
                "Withdrawal method",
                [],
            )
        )

        self.addCommand(
            Command(
                "deposit_address",
                [
                    CommandArgument("reference_str", "str"),
                ],
                "Loads deposit address",
                [],
            )
        )

    def addCommand(self, command):
        self.commands[command.name] = command

        # add to help menu
        helpCommand = Command(command.name)
        if "help" not in self.commands:
            self.commands["help"] = Command(
                "help", [], "print this menu", [helpCommand]
            )
        else:
            self.commands["help"].addChild(helpCommand)

    def processCommand(self, command, request):
        # extract arguments from the request
        args = request.split()

        # check for quotes
        finalArgs = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg[0] == '"':
                # reconstruct quoted arguments
                fullArg = arg
                i += 1
                while i < len(args):
                    if fullArg[-1] == '"':
                        break
                    fullArg += f" {args[i]}"
                    i += 1

                # strip quotes at the end
                finalArgs.append(fullArg[1:-1])
            else:
                finalArgs.append(arg)
                i += 1
        args = finalArgs

        # arg count sanity check
        minCount = command.minArgsCount()
        maxCount = command.maxArgsCount()
        count = len(args)
        if count < minCount or count > maxCount:
            if maxCount == minCount:
                logging.error(
                    f'command "{command.name}" takes {minCount} args, got {count} instead'
                )
            else:
                logging.error(
                    f'command "{command.name}" between {minCount} and {maxCount} args, got {count} instead'
                )
            return None, []

        formattedArgs = []
        for i in range(0, maxCount):
            # get the command's argument
            commandArg = command.getArg(i)
            if commandArg == None:
                logging.error(
                    f'something went wrong when processing argument #{i} for command "{command.name}"'
                )
                return None, []

            # grab the request's argument if it exists
            arg = None
            if i < count:
                arg = args[i]

            # enforce argment type, check values where applicable
            if not arg:
                # arg is missing, use the default value
                try:
                    formattedArg = commandArg.getDefaultValue()
                except:
                    # getDefaultValue raised cause arg isnt optional
                    logging.error(
                        f'arg "{commandArg.name}" for command "{command.name}" is not optional!'
                    )
                    return None, []
            else:
                try:
                    formattedArg = commandArg.getFormattedValue(arg)
                except:
                    # conversion to value type failed, or value is out of bounds
                    logging.error(
                        f"failed to process value ({arg}) for arg: {commandArg.name}"
                    )
                    return None, []
            formattedArgs.append(formattedArg)

        return command.getFullName(), formattedArgs

    def parseUserRequest(self, request, parentCommand=None):
        if parentCommand == None:
            commands = self.commands
        else:
            commands = parentCommand.children

        for commandName in commands:
            if request.startswith(commandName):
                # remove command name from request
                subRequest = request[len(commandName) :].strip()
                command = commands[commandName]

                if command.hasChildren() and len(subRequest) > 0:
                    # command has children, parse those with the remainder of the request
                    cm, args = self.parseUserRequest(subRequest, command)
                else:
                    # command has no children, parse remainder of request as args
                    cm, args = self.processCommand(command, subRequest)

                if cm != None and commands == self.commands:
                    # track last valid primary command
                    self.lastCommand = commandName
                return cm, args

        # if command ends in 'help', treat it as if it starts with 'help'
        if request.strip() == "help":
            return f"help {parentCommand.getFullName()}", []

        # try to reuse last valid primary command
        if self.lastCommand in commands:
            command = commands[self.lastCommand]
            cm, args = self.parseUserRequest(request, command)
            if cm != None:
                return cm, args

        logging.error(f"invalid command: {request}")
        return None, []

    def getChild(self, key):
        if key in self.commands:
            return self.commands[key]
        return None

    def getHelpStr(
        self,
    ):
        helpStr = " - commands:\n"
        for commandName in self.commands:
            command = self.commands[commandName]
            helpStr += f"   . {command.getHelpStr(depth=0)}\n"
        return helpStr
