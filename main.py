from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio
import time
import threading

nest_asyncio.apply()

creds = {
    "host": credentials.host,
    "port": credentials.port,
    "client_id": 12
}


class Strategy:

    def __init__(self):
        self.atm_put_fill = None
        self.atm_put_parendID = None
        self.atm_put_limit_price = None
        self.atm_call_parendID = None
        self.closest_current_price = None
        self.otm_closest_call = None
        self.otm_closest_put = None
        self.broker = IBTWSAPI(creds=creds)
        self.strikes = None
        self.atm_sl = 0.15
        self.percent = 0.15
        self.atm_call_fill = None
        self.atm_call_limit_price = None

    async def main(self):
        print("\n1. Testing connection...")
        await self.broker.connect()
        print(f"Connection status: {self.broker.is_connected()}")
        self.closest_current_price = self.broker.current_price(credentials.instrument)
        self.broker.ib.reqMarketDataType(4)
        self.strikes = await self.broker.fetch_strikes(credentials.instrument, "CBOE", secType="IND")

        await self.place_hedge_orders()
        await asyncio.sleep(1)
        await self.place_atm_call_order(self.atm_sl)
        await self.place_atm_put_order(self.atm_sl)

        await self.atm_call_trail_sl()

    async def atm_call_trail_sl(self):
        percent = 0.95
        while True:
            k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date, self.closest_current_price, "C")
            check = k['ask']
            if check <= percent * self.atm_call_limit_price:
                if self.percent > 0.01:
                    self.percent -= 0.01
                    x = await self.broker.get_open_orders()
                    await self.broker.modify_option_trail_percent(x[0], self.percent)
                    percent -= 0.05
                    print(f"Bought: {self.atm_call_limit_price}\nCurrent percent: {percent}")
                    await asyncio.sleep(120)
                else:
                    break
            else:
                await asyncio.sleep(120)
                print("No Change")

    async def place_hedge_orders(self):
        current_price = await self.broker.current_price(credentials.instrument)
        closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))
        self.otm_closest_call = closest_strike + 10
        self.otm_closest_put = closest_strike - 10
        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_call,
            right='C',
            exchange="SMART"
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_put,
            right='P',
            exchange="SMART"
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange="SMART"
            )
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="SELL")
        if close_put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='P',
                exchange="SMART"
            )
            await self.broker.place_market_order(contract=spx_contract_put, qty=1, side="SELL")

    async def place_atm_call_order(self, sl):
        current_price = await self.broker.current_price(credentials.instrument, "CBOE")
        self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        premium_price = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date, self.closest_current_price,
                                                                   "C")
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.closest_current_price,
            right='C',
            exchange="SMART"
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        stop_loss = premium_price['last'] * (1 - 0.15)

        k = await self.broker.place_bracket_order(symbol=credentials.instrument,
                                                  quantity=1,
                                                  price=premium_price['ask'],
                                                  stoploss=stop_loss,
                                                  expiry=credentials.date,
                                                  strike=self.closest_current_price,
                                                  right="C",
                                                  trailingpercent=sl)

        self.atm_call_limit_price = premium_price['ask']
        self.atm_call_parendID = k['parent_id']
        self.atm_call_fill = k['avgFill']

    async def place_atm_put_order(self, sl):
        current_price = await self.broker.current_price(credentials.instrument, "CBOE")
        self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        premium_price = await self.broker.get_latest_premium_price(symbol=credentials.instrument,
                                                                   expiry=credentials.date,
                                                                   strike=self.closest_current_price,
                                                                   right="P")
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.closest_current_price,
            right='P',
            exchange="SMART"
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])
        stop_loss = premium_price['last'] * (1 - 0.15)
        k = await self.broker.place_bracket_order(symbol=credentials.instrument,
                                                  quantity=1,
                                                  price=premium_price['ask'],
                                                  stoploss=stop_loss,
                                                  expiry=credentials.date,
                                                  strike=self.closest_current_price,
                                                  right="P",
                                                  trailingpercent=sl)
        self.atm_put_limit_price = premium_price['ask']
        self.atm_put_parendID = k['parent_id']
        self.atm_put_fill = k['avgFill']


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
