import websockets
import json
import asyncio
import logging

from SDK.leverex_core.login_connection import LoginServiceClientWS

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
            "authorize": {"token": token["access_token"]},
        }
        self.access_token = token
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
            print(f"connection failed with error: {urls[self.env]}")
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

    async def createSubAccount(self, email):
        msg = {"create_sub_account": email}
        await self.websocket.send(json.dumps(msg))

    async def withdraw(self, address, currency, amount, entity_id=None):
        msg = {
            "withdraw_liquid": {
                "address": address,
                "currency": currency,
                "amount": amount,
                "entity_id": entity_id or 0,
            }
        }
        await self.websocket.send(json.dumps(msg))

    async def deposit(self, email):
        msg = {"deposit": email}
        await self.websocket.send(json.dumps(msg))

    async def subscribeImInfo(self):
        msg = {"request": "im_info"}
        await self.websocket.send(json.dumps(msg))

    async def subscribeToUserBalance(self, entityId: int = 0):
        # entity id set to 0 means sub to all user balances
        msg = {"load_account_balance": {"entity_id": entityId}}
        await self.websocket.send(json.dumps(msg))

    async def load_deposit_address(self, ref_str):
        msg = {"load_deposit_address": {"reference": ref_str}}
        await self.websocket.send(json.dumps(msg))

    ## handle replies ##
    async def processResponse(self, data):
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

        elif "withdraw_liquid" in data:
            await self.listener.on_withdraw(data["withdraw_liquid"])

        elif "load_deposit_address" in data:
            await self.listener.on_load_deposit_address(data["load_deposit_address"])

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
