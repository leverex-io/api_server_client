import logging
import asyncio
import sys
import argparse

from lib.printHelp import processHelp
from lib.sessions import (
    SessionMap,
)
from lib.api_connection import AdminApiConnection
from lib.announcements import Announcements
from lib.cash import CashMetrics

from commands import (
    COMMAND_DEPOSIT,
    COMMAND_LOAD_DEPOSIT_ADDRESS,
    COMMAND_SUBACCOUNT_CREATE,
    COMMAND_WITHDRAW,
    Commands,
    COMMAND_EXIT,
)

# import pdb; pdb.set_trace()

theOneProduct = "xbtusd_rf"


class BrownClient(object):
    def __init__(self, env):
        self.connection = AdminApiConnection(env)
        self.sessionMap = SessionMap()
        self.commands = Commands()
        self.announcements = Announcements()
        self.cashMetrics = CashMetrics()
        self.numAccounts = None

    ## asyncio entry point ##
    async def run(self):
        await self.connection.run(self)

    ## input loop ##
    async def inputLoop(self, loop):
        keepRunning = True
        while keepRunning:
            print(">input a command>")
            command = await loop.run_in_executor(None, sys.stdin.readline)

            # strip the terminating \n
            if len(command) > 1 and command[-1] == "\n":
                command = command[0:-1].strip()
            keepRunning = await self.parseCommand(command)

    async def parseCommand(self, request):
        commandCode, args = self.commands.parseUserRequest(request)
        if commandCode == None:
            print(f"unexpected command: {request}")
            return True

        ## exit ##
        elif commandCode == COMMAND_EXIT:
            loop = asyncio.get_event_loop()
            loop.stop()
            return False

        ## help ##
        elif commandCode.startswith("help"):
            processHelp(self.commands, commandCode)

        # subaccount
        elif commandCode == COMMAND_SUBACCOUNT_CREATE:
            await self.subaccount_create(*args)

        # subaccount
        elif commandCode == COMMAND_WITHDRAW:
            await self.withdraw(*args)

        elif commandCode == COMMAND_DEPOSIT:
            await self.deposit(*args)

        elif commandCode == COMMAND_LOAD_DEPOSIT_ADDRESS:
            await self.load_deposit_address(*args)

        else:
            print(f"unhandled command: {request}")

        return True

    ## subaccount ##
    async def subaccount_create(self, email):
        await self.connection.createSubAccount(email)

    async def on_subaccount_create(self, data):
        print(data)

    ## withdrawal ##
    async def withdraw(self, address, currency, amount, entity_id):
        await self.connection.withdraw(address, currency, amount, entity_id)

    async def on_withdraw(self, data):
        print(data)

    # deposit
    async def deposit(self, something):
        pass

    async def on_deposit(self, data):
        print(data)

    async def load_deposit_address(self, ref_str):
        await self.connection.load_deposit_address(ref_str)

    async def on_load_deposit_address(self, data):
        print(data)

    ## reply handlers ##
    async def onLoginSuccess(self):
        # subsc ibe to various notifications
        # await self.connection.subscribeActiveSessionInfo()
        # await self.getSessions("damaged")
        # await self.connection.getNumberOfAccounts()
        # await self.connection.subscribeImInfo()
        # await self.connection.subscribeToUserBalance()

        # start input prompt task
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(self.inputLoop(loop))


if __name__ == "__main__":
    LOG_FORMAT = (
        "%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s"
    )
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    parser = argparse.ArgumentParser(description="Admin Client")
    parser.add_argument(
        "--env",
        type=str,
        help="enviroment to connect to (devbrown/devprem/dev/uat/prod)",
    )
    args = parser.parse_args()

    try:
        client = BrownClient(args.env)
        asyncio.run(client.run())
    except Exception:
        print("exiting...")
