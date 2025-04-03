import logging
from decimal import Decimal
from copy import deepcopy

from SDK.leverex_core.utils import round_flat

BALANCES_KEY   = 'balances'
BALANCE_KEY    = 'balance'
CURRENCY_KEY   = 'ccy'
USER_KEY       = 'user'
ENTITY_ID_KEY  = 'entity_id'
ACCOUNT_KEY    = 'account_balance'

LOCATION_KEY      = 'location'
LOCATION_HOT      = 'hot_wallet'
LOCATION_WARM     = 'warm_wallet'
LOCATION_TOTAL    = 'total'
LOCATION_CUSTODY  = 'custody'
LOCATION_CLEARING = 'clearing_account'
LOCATION_DEPOSIT  = 'deposits'
LOCATION_WITHDRAW = 'withdrawals'
LOCATION_PENDING  = 'pending_withdraw'
LOCATION_EXOTIC   = 'exotic'

CCY_USDT = 'USDT'
CCY_LBTC = 'LBTC'

class WalletCash(object):
   def __init__(self):
      self.cashMap = {}

   def copy(self, obj):
      self.cashMap = {}
      self.cashMap = deepcopy(obj.cashMap)

   def add(self, obj):
      for ccy in obj.cashMap:
         if not ccy in self.cashMap:
            self.cashMap[ccy] = Decimal(0)
         self.cashMap[ccy] += obj.cashMap[ccy]

   def update(self, data):
      balanceList = data[BALANCES_KEY]

      for balance in balanceList:
         if CURRENCY_KEY not in balance or BALANCE_KEY not in balance:
            continue
         self.cashMap[balance[CURRENCY_KEY]] = Decimal(balance[BALANCE_KEY])

class UsersCash(object):
   def __init__(self):
      self.userMap = {}

   def update(self, data):
      if not USER_KEY in data:
         #logging.warning(f"[UsersCash] no user id in data: {data}")
         return

      userId = data[USER_KEY]
      balanceList = data[BALANCES_KEY]
      if not balanceList:
         return

      if not userId in self.userMap:
         self.userMap[userId] = {}

      for balance in balanceList:
         self.userMap[userId][balance[CURRENCY_KEY]] = Decimal(balance[BALANCE_KEY])

   def updateFromAccountBalanceNotif(self, data):
      print (data)
      if not ENTITY_ID_KEY in data or not ACCOUNT_KEY in data:
         return

      entityId = data[ENTITY_ID_KEY]
      if not entityId in self.userMap:
         self.userMap[entityId] = {}

      for entry in data[ACCOUNT_KEY]:
         balance = Decimal(entry[BALANCE_KEY])
         ccy = entry[CURRENCY_KEY]
         self.userMap[entityId][ccy] = balance

   def getTotalCash(self):
      result = {}
      for userId in self.userMap:
         for ccy in self.userMap[userId]:
            if ccy not in result:
               result[ccy] = Decimal(0)
            result[ccy] += self.userMap[userId][ccy]
      return result

   def prettyPrint(self):
      result = " . User Cash:\n"
      for userId in self.userMap:
         user = self.userMap[userId]
         result += f"   - id: {userId} - "
         for ccy in user:
            result += f"{ccy}: {user[ccy]}, "
         result += "\n"
      print (result)


class CashMetrics(object):
   def __init__(self):
      self.metricsMap = {
         LOCATION_HOT      : WalletCash(),
         LOCATION_WARM     : WalletCash(),
         LOCATION_TOTAL    : WalletCash(),
         LOCATION_CLEARING : WalletCash(),
         LOCATION_DEPOSIT  : WalletCash(),
         LOCATION_WITHDRAW : WalletCash(),
         LOCATION_PENDING  : WalletCash(),
         LOCATION_CUSTODY  : UsersCash(),
         LOCATION_EXOTIC   : {}
      }

   def update(self, data):
      if not BALANCES_KEY in data:
         if ACCOUNT_KEY in data:
            self.metricsMap[LOCATION_CUSTODY].updateFromAccountBalanceNotif(data)
         return

      if not LOCATION_KEY in data:
         return
      loc = data[LOCATION_KEY]
      if not loc in self.metricsMap:
         if loc not in self.metricsMap[LOCATION_EXOTIC]:
            self.metricsMap[LOCATION_EXOTIC][loc] = WalletCash()
         self.metricsMap[LOCATION_EXOTIC][loc].update(data)
         return

      if loc == LOCATION_CUSTODY:
         return

      self.metricsMap[loc].update(data)

      if loc in [LOCATION_HOT, LOCATION_WARM]:
         totalCash = self.metricsMap[LOCATION_TOTAL]
         totalCash.copy(self.metricsMap[LOCATION_HOT])
         totalCash.add(self.metricsMap[LOCATION_WARM])

   def prettyPrint(self, sessionObj):
      #user cash
      result = " . Users Cash"
      try:
         #sum of users cash
         usersCash = self.metricsMap[LOCATION_CUSTODY]
         cashAggregate = usersCash.getTotalCash()
         if not cashAggregate:
            raise Exception()

         result += f" ({len(usersCash.userMap)} accounts):\n"
         totals = "    - total on accounts = "
         for ccy in cashAggregate:
            totals += f"{ccy}: {round_flat(cashAggregate[ccy], 8)} - "
         result += f"{totals[:-2]}\n"

         #sum of cash stuck in session limbo
         limboAggregate = sessionObj.getLimboCashAggregate()
         limboed = "    - in session limbo  = "
         if limboAggregate:
            for ccy in limboAggregate:
               limboed += f"{ccy}: {round_flat(limboAggregate[ccy], 8)} - "
            result += f"{limboed[:-2]}\n"
         else:
            result += f"{limboed}N/A\n"

         #sum of both per currency
         final = "    - final sum         = "
         for ccy in cashAggregate:
            val = cashAggregate[ccy]
            if ccy in limboAggregate:
               val += limboAggregate[ccy]
            final += f"{ccy}: {round_flat(val, 8)} - "
         result += f"{final[:-2]}\n"
      except:
         result += ": N/A\n"

      #clearing account
      result += " . Clearing Account:"
      try:
         clearing = self.metricsMap[LOCATION_CLEARING]
         result += "\n"
         for ccy in clearing.cashMap:
            result += f"    - {ccy}              = {round_flat(clearing.cashMap[ccy], 8)}\n"
      except:
         result += " N/A\n"

      #wallets
      result += " . Wallets:\n"

      def getWalletStr(loc, toAdd=None):
         try:
            wallet = self.metricsMap[loc]
            if toAdd:
               addedWallet = WalletCash()
               addedWallet.copy(wallet)
               addedWallet.add(self.metricsMap[toAdd])
               wallet = addedWallet

            balanceStr = ""
            for ccy in wallet.cashMap:
               balanceStr += f"{ccy}: {round_flat(wallet.cashMap[ccy], 8)}, "
            return balanceStr[:-2]
         except:
            return "N/A"

      result += f"    - hot                  = {getWalletStr(LOCATION_HOT)}\n"
      result += f"    - warm                 = {getWalletStr(LOCATION_WARM)}\n"
      result += f"    - total                = {getWalletStr(LOCATION_TOTAL)}\n"

      #transfers
      result += " . Transfers:\n"
      result += f"    - total deposits       = {getWalletStr(LOCATION_DEPOSIT)}\n"
      result += f"    - total withdrawals    = {getWalletStr(LOCATION_WITHDRAW)}\n"
      result += f"    - pending withdrawals  = {getWalletStr(LOCATION_PENDING)}\n"
      result += f"    - sum of transfers     = {getWalletStr(LOCATION_DEPOSIT, LOCATION_WITHDRAW)}\n"

      #exotic locations
      print (result)

   def prettyPrintUsersBalance(self):
      self.metricsMap[LOCATION_CUSTODY].prettyPrint()
