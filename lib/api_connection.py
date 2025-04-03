import websockets
import json
import asyncio
import logging
from decimal import Decimal

from typing import Callable
from SDK.leverex_core.login_connection import LoginServiceClientWS
from SDK.leverex_core.api_connection import generateReferenceId

urls = {
    "devbrown": {
        "api": "wss://api-devbrown.leverex.io",
        "aeid": "https://staging.autheid.com",
        "login": "wss://login-devbrown.leverex.io/ws/v1/websocket",
    },
}


class NoCallbackException(Exception):
    pass


class RequestCallback(object):
    def __init__(self, callback, count):
        self.callback = callback
        self.count = count

    async def fire(self, data):
        await self.callback(data)
        self.count -= 1
        return self.count <= 0


class AdminApiConnection(object):
    def __init__(self, env):
        self.env = env
        self.websocket = None
        self.access_token = None
        self.listener = None
        self.loginStatus = False
        self._callbacks = {}

        if env not in urls:
            logging.error(f"invalid environment: {env}")
            raise Exception()

    ## login rountines ##
    async def getAccessToken(self):
        # get token from login server
        print("logging in...")

        loginClient = LoginServiceClientWS(
            None,
            urls[self.env]["login"],
            aeid_endpoint=urls[self.env]["aeid"],
            dump_communication=True,
        )
        access_token_info = await loginClient.logMeIn(urls[self.env]["api"])

        if access_token_info == None:
            raise Exception("Failed to get access token")
        return access_token_info

    async def authorize(self, token):
        auth_request = {
            # "request": "authorize",
            "authorize": {"token": token["access_token"]},
        }
        self.access_token = token
        print(json.dumps(auth_request))
        await self.websocket.send(json.dumps(auth_request))

    async def connected(self):
        auth_request = {
            # "request": "authorize",
            "connected": {},
        }
        await self.websocket.send(json.dumps(auth_request))

    async def cycleToken(self):
        while True:
            # wait for token lifetime - 1min
            await asyncio.sleep(self.access_token["expires_in"] * 0.9)

            # cycle token with login server
            loginClient = LoginServiceClientWS(
                None, urls[self.env]["login"], aeid_endpoint=urls[self.env]["aeid"]
            )
            access_token = await loginClient.update_access_token(
                self.access_token["access_token"]
            )

            # send to service
            await self.authorize(access_token)

    ## asyncio entry point ##
    async def run(self, listener):
        self.listener = listener

        try:
            # get access token
            accessToken = await self.getAccessToken()
            print(accessToken)
            # set admin custom CA & connect to admin api
            # custom_ca_context = ssl.create_default_context(cafile="leverex_local.crt")
            async with websockets.connect(
                urls[self.env]["api"],  # ssl=custom_ca_context
            ) as self.websocket:
                # autorize connection with acceess token
                # await self.connected()
                await self.authorize(accessToken)

                # start read and token cycling loops, they will be awaited when TaskGroup scopes out
                async with asyncio.TaskGroup() as tg:
                    readTask = tg.create_task(self.readLoop(), name="admin read task")
                    cycleTask = tg.create_task(
                        self.cycleToken(), name="admin login cycle task"
                    )

        except Exception:
            import traceback

            traceback.print_exc()
            print(f"connection failed with error: {urls[env]}")
            loop = asyncio.get_running_loop()
            loop.stop()
            return

    ## wait on data from primary ws session ##
    async def readLoop(self):
        while True:
            data = await self.websocket.recv()
            if data is None:
                continue
            data_json = json.loads(data)
            if "notification" in data_json:
                await self.processNotification(data_json)
            else:
                await self.processResponse(data_json)

    ## callback handlers
    def queueCallback(self, key, callback, callbackCount=1):
        if callback == None:
            return

        if key in self._callbacks:
            raise Exception(f"callback collision! ({key})")
        self._callbacks[key] = RequestCallback(callback, callbackCount)

    async def fireCallback(self, key, data):
        callback = None
        if key in self._callbacks:
            callback = self._callbacks[key]

        if not callback:
            raise NoCallbackException()

        done = await callback.fire(data)
        if done:
            del self._callbacks[key]

    ## getters ##
    async def getIncompleteSessions(self, product, callback: Callable = None):
        refId = generateReferenceId()
        msg = {
            "request": "get_incomplete_sessions",
            "data": {"product_name": product, "reference": refId},
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def getSessionImSummary(
        self, sessionId, novationId, callback: Callable = None
    ):
        refId = generateReferenceId()
        callbackCount = 1
        msg = {
            "request": "im_summary",
            "data": {"session_id": sessionId, "reference": refId},
        }
        if novationId:
            msg["data"]["account_id"] = str(novationId)
            callbackCount += 1

        self.queueCallback(refId, callback, callbackCount)
        await self.websocket.send(json.dumps(msg))

    async def getSessionInfo(
        self, sessionId: str, product: str, callback: Callable = None
    ):
        refId = generateReferenceId()
        msg = {
            "request": "get_damaged_session_info",
            "data": {
                "product_name": product,
                "session_id": sessionId,
                "reference": refId,
            },
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def getChyrons(self, callback: Callable = None):
        refId = generateReferenceId()
        msg = {
            "request": "load_chyrons",
            "data": {"ignore_time": True, "only_enabled": False, "reference": refId},
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def loadUsers(self, callback: Callable = None):
        refId = generateReferenceId()
        msg = {
            "request": "load_users",
            "data": {"entity_id": 0, "email": "", "reference": refId},
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def getNumberOfAccounts(self):
        msg = {"request": "number_of_accounts"}
        await self.websocket.send(json.dumps(msg))

    ## subscriptions ##
    async def subscribeActiveSessionInfo(self):
        msg = {"request": "active_sessions_info"}
        await self.websocket.send(json.dumps(msg))

    async def subscribeLeverexBalances(self):
        msg = {"request": "leverex_balances"}
        await self.websocket.send(json.dumps(msg))

    async def createSubAccount(self, email):
        msg = {"create_sub_account": email}
        print(json.dumps(msg))
        await self.websocket.send(json.dumps(msg))

    async def withdraw(self, email):
        msg = {"withdraw": email}
        print(json.dumps(msg))
        await self.websocket.send(json.dumps(msg))

    async def deposit(self, email):
        msg = {"deposit": email}
        print(json.dumps(msg))
        await self.websocket.send(json.dumps(msg))

    async def subscribeImInfo(self):
        msg = {"request": "im_info"}
        await self.websocket.send(json.dumps(msg))

    async def subscribeToUserBalance(self, entityId: int = 0):
        # entity id set to 0 means sub to all user balances
        msg = {"load_account_balance": {"entity_id": entityId}}
        await self.websocket.send(json.dumps(msg))

    ## requests ##
    async def fixSession(
        self,
        sessionId: str,
        product: str,
        scenario: str,
        price: Decimal,
        callback: Callable = None,
    ):
        refId = generateReferenceId()
        msg = {
            "request": "revert_damaged_session",
            "data": {
                "product_name": product,
                "session_id": sessionId,
                "scenario": scenario,
                "reference": refId,
            },
        }
        if price != 0:
            msg["data"]["closing_price"] = str(price)

        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def shutdownSession(self, product, callback: Callable = None):
        refId = generateReferenceId()
        msg = {
            "request": "shutdown_session",
            "data": {"product_name": product, "reference": refId},
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def forceStartNewSession(
        self, product, hard: bool, callback: Callable = None
    ):
        refId = generateReferenceId()
        msg = {
            "request": "force_new_session",
            "data": {"product_name": product, "hard": hard, "reference": refId},
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def createChyron(
        self,
        priority: int,
        message: str,
        start: int,
        end: int,
        callback: Callable = None,
    ):
        refId = generateReferenceId()
        msg = {
            "request": "create_chyron",
            "data": {
                "on": True,
                "priority": priority,
                "message": message,
                "start": start,
                "end": end,
                "reference": refId,
            },
        }
        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    async def updateChyron(
        self, cId, on, prio, start, end, message: str = None, callback: Callable = None
    ):
        refId = generateReferenceId()
        msg = {
            "request": "modify_chyron",
            "data": {
                "id": cId,
                "on": on,
                "priority": prio,
                "start": start,
                "end": end,
                "reference": refId,
            },
        }
        if message:
            msg["data"]["message"] = message

        self.queueCallback(refId, callback)
        await self.websocket.send(json.dumps(msg))

    ## handle replies ##
    async def processResponse(self, data):
        print(f"RESPONSE: {data}")
        replyType = data
        reply = {}
        if "data" in data:
            reply = data["data"]

        if "authorize" in data:
            reply = data["authorize"]
            validated = False
            if "success" in reply:
                validated = reply["success"]

            if validated:
                if not self.loginStatus:
                    self.loginStatus = True
                    print(f"-- LOGGED IN AS: {reply['email']}")
                    await self.listener.onLoginSuccess()

            else:
                self.loginStatus = False
                raise Exception("login failed!")

        elif "account_created" in data:
            await self.listener.on_subaccount_create(data["account_created"])

        elif "reference" in data:
            refId = data["reference"]
            try:
                await self.fireCallback(refId, data)
            except NoCallbackException:
                logging.info(f"no callback registered for reply: {data}")
            return

        else:
            logging.info(f"unhandled reply packet: {data}")

    ## handle server push ##
    async def processNotification(self, data):
        notifType = data["notification"]
        notif = data["data"]

        if notifType == "cash_metrics":
            await self.listener.handleCashMetricsUpdate(notif)
        elif notifType == "withdraw_queue_size":
            await self.listener.handleWithdrawQueueSizeUpdate(notif)
        elif notifType == "liquid_wallet_balances":
            await self.listener.handleLiquidBalanceUpdate(notif)
        elif notifType == "load_account_balance":
            print(f"account balance notif: {notif}")
            await self.listener.handleCashMetricsUpdate(notif)

        else:
            logging.info(f"unhandled notification packet: {data}")
