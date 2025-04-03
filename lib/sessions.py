from datetime import datetime
from decimal import Decimal
from SDK.leverex_core.utils import round_flat

FixScenarioMap = {
   "cancel" : "cancel_trades",
   "complete" : "complete_trades",
   "set_price" : "complete_trades_with_closing_price"
}

SessionDataKeys = [
   'id', 'state',
   'start_timestamp', 'end_timestamp', 'timestamp_end',
   'open_price', 'close_price',
   'reason', 'message', 'damaged_at_timestamp,',
   'novation_account_state', 'novation_account_id', 'novation_entity_id',
   'novation_account_balance', 'total_customers_reserved_margin', 'total_session_margin',
]

VAL_DAMAGED = 'Damaged'
KEY_IM      = 'im_balance'
KEY_NET_EXP = 'net_exposure'

def toHumanTime(timestamp_ms):
   dt = datetime.fromtimestamp(int(timestamp_ms)/1000)
   return dt.strftime("%Y-%m-%d %H:%M:%S")

class SessionData(object):
   def __init__(self, data):
      self.id = None
      self.state = None
      self.open_price = None
      self.close_price = None

      self.start_timestamp = None
      self.end_timestamp = None #session will end then, this is for active sessions
      self.timestamp_end = None #session ended then, this is for finalized/damaged sessions

      self.reason = None
      self.message = None
      self.damaged_at_timestamp = None

      self.novation_account_state = None
      self.novation_account_id = None
      self.novation_entity_id = None
      self.novation_account_balance = None
      self.total_customers_reserved_margin = None
      self.total_session_margin = None

      self.deserData(data)

   def deserData(self, data):
      for key in data:
         if key in SessionDataKeys:
            setattr(self, key, data[key])

   def isDamaged(self):
      return self.state == VAL_DAMAGED

   def __str__(self):
      result  = f" - session {self.id}:\n"
      result += f"   . state: {self.state}\n"
      if self.open_price:
         result += f"   . open price: {self.open_price}\n"
      if self.close_price:
         result += f"   . close price: {self.close_price}\n"

      if self.start_timestamp:
         result += f"   . started at: {toHumanTime(self.start_timestamp)}\n"
      if self.timestamp_end:
         result += f"   . ended on: {toHumanTime(self.timestamp_end)}\n"
      elif self.end_timestamp:
         result += f"   . ends on: {toHumanTime(self.end_timestamp)}\n"

      if self.damaged_at_timestamp:
         result += f"   . damaged on: {toHumanTime(self.damaged_at_timestamp)}\n"
      if self.reason:
         result += f"   . reason: \"{self.reason}\", message: \"{self.message}\"\n"

      if self.total_session_margin:
         result += f"   . total session margin: {self.total_session_margin}\n"

      if self.novation_account_balance:
         result += f"   . novation account balance:\n"
         for acc in self.novation_account_balance:
            result += f"       {acc}\n"

      return result

class CurrentSessionImInfo(object):
   def __init__(self, product):
      self.product = product
      self.margin = Decimal(0)
      self.totalExposure = Decimal(0)

   def update(self, imInfo):
      self.margin = Decimal(0)
      self.netExposure = Decimal(0)

      for userId in imInfo:
         userIm = imInfo[userId]
         if self.product not in userIm:
            continue

         userProductIm = userIm[self.product]
         self.margin += Decimal(userProductIm[KEY_IM])
         self.totalExposure += abs(Decimal(userProductIm[KEY_NET_EXP]))

   def __str__(self):
      result = f"   . total margin: {round_flat(self.margin, 8)}\n"
      result += f"   . total exposure: {round_flat(self.totalExposure, 8)}\n"
      return result

class CurrentSessionData(SessionData):
   def __init__(self, product, data):
      super().__init__(data)
      self.product = product
      self.imInfo = CurrentSessionImInfo(product)

   def updateImInfo(self, imInfo):
      self.imInfo.update(imInfo)

   def __str__(self):
      result = super().__str__()
      result += str(self.imInfo)
      return result

class SessionMap(object):
   def __init__(self):
      self.sessionMap = {}
      self.currentSessions = {}

   def find(self, sessionId):
      #search damaged session map
      for product in self.sessionMap:
         if sessionId in self.sessionMap[product]:
            return self.sessionMap[product][sessionId]

      #search current session map
      for product in self.currentSessions:
         session = self.currentSessions[product]
         if session.id == sessionId:
            return session

      #couldnt find anything
      return None

   def getProductForSession(self, sessionId):
      for product in self.sessionMap:
         if sessionId in self.sessionMap[product]:
            return product
      return None

   def setSession(self, product, sessionObj: SessionData):
      if not product in self.sessionMap:
         self.sessionMap[product] = {}
      self.sessionMap[product][sessionObj.id] = sessionObj

   def setCurrent(self, sessionObj: CurrentSessionData):
      product = sessionObj.product
      if product in self.currentSessions and \
         self.currentSessions[product].id == sessionObj.id:
         return
      self.currentSessions[product] = sessionObj

   def extendSession(self, sesId, data):
      session = self.find(sesId)
      if not session:
         logging.warn(f"could not extend session info for id: {sesId}")
         return
      session.deserData(data)

   def updateImInfo(self, data):
      for product in self.currentSessions:
         self.currentSessions[product].updateImInfo(data)

   def getLimboCashAggregate(self):
      #sum up cash in damaged sessions
      result = {}
      for product in self.sessionMap:
         sesMap = self.sessionMap[product]
         for sesId in sesMap:
            session = sesMap[sesId]
            if session.isDamaged() and session.novation_account_balance:
               for balEntry in session.novation_account_balance:
                  for ccy in balEntry:
                     if not ccy in result:
                        result[ccy] = Decimal(0)
                     result[ccy] += Decimal(balEntry[ccy])
      return result

   def __str__(self):
      def getShortDescr(sessionObj):
         descr = f"id: {sessionObj.id}"
         descr += f", created at: {toHumanTime(sessionObj.id)}"
         descr += f", state: {sessionObj.state}"
         if (sessionObj.isDamaged()) and sessionObj.reason:
            descr += f", reason: {sessionObj.reason}"
         return descr

      result = " - Current Sessions:\n"
      if not self.currentSessions:
         result += ("  |- N/A\n")
      else:
         for product in self.currentSessions:
            result += f"  |- {product}:\n"
            result += f"    |- {getShortDescr(self.currentSessions[product])}\n"

      result += " - Damaged Sessions:\n"
      if not self.sessionMap:
         result += (" - No session data!")
      else:
         for product in self.sessionMap:
            result += (f"  |- {product}:\n")
            sesData = self.sessionMap[product]
            if not sesData:
               result += ("    |- N/A\n")
               continue

            for sessionId in sesData:
               session = sesData[sessionId]
               result += f"    |- {getShortDescr(session)}\n"

      #limbo'd cash
      limboAggregate = self.getLimboCashAggregate()
      limboStr = ""
      if not limboAggregate:
         limboStr = "  |- N/A"
      for ccy in limboAggregate:
         limboStr += f"    |- {ccy}: {round_flat(limboAggregate[ccy], 8)}\n"
      result += f" - Cash in limbo:\n"
      result += f"{limboStr}\n"

      return result

def processSessionData(data):
   product = data['product_name']
   sessionData = {}
   for session in data['sessions']:
      sessionObj = SessionData(session)
      sessionData[sessionObj.id] = sessionObj

   return product, sessionData

def processShowSessions(sessionMap, sessionId=None):
   if sessionId == None:
      print (str(sessionMap))
   else:
      #expecting a session id
      session = sessionMap.find(str(sessionId))
      if session:
         print (str(session))
         return
      print (f" expecting a session id, got: {sessionId}")
