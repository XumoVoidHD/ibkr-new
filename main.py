from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio
import time
import threading

nest_asyncio.apply()

creds = {
    "host": '127.0.0.1',  # Local host
    "port": 7497,  # Paper trading port
    "client_id": 12
}


class Strategy:

    def __init__(self):
        self.atm_call_parendID = None
        self.closest_current_price = 6050
        self.otm_closest_call = None
        self.otm_closest_put = None
        self.broker = IBTWSAPI(creds=creds)
        self.strikes = None
        self.atm_sl = 0.15
        self.percent = 0.15
        self.atm_call_fill = None

    async def main(self):
        print("\n1. Testing connection...")
        connected = await self.broker.connect()
        print(f"Connection status: {connected}")

        self.strikes = await self.broker.fetch_strikes("SPX", "CBOE", secType="IND")

        # await self.place_hedge_orders()
        await self.place_atm_call_order(0.15)
        # await asyncio.sleep(10)
        # k = await self.broker.get_open_orders()
        # print(k)
        # k = await self.broker.get_open_orders()
        #
        # x = await self.broker.modify_option_trail_percent(k[0], 0.14)
        # print(x)
        # asyncio.run(self.atm_call_trail_sl())

    async def atm_call_trail_sl(self):
        while True:
            k = await self.broker.get_latest_premium_price("SPX", credentials.date, self.closest_current_price, "C")
            check = k['mid']
            print("check1")
            if check <= 0.95 * self.closest_current_price:
                print("check2")
                if self.percent > 0.01:
                    print("check3")
                    self.percent -= 0.01
                    print(self.atm_call_parendID)
                    # await self.broker.cancel_order(self.atm_call_parendID)
                    c = Option(symbol="SPX", lastTradeDateOrContractMonth=credentials.date,
                               strike=self.closest_current_price, right='C', exchange='SMART', currency="USD")
                    order = Order(action='BUY', totalQuantity=1, orderType='TRAIL', parentId=self.atm_call_parendID,
                                  trailingPercent=self.percent)
                    await self.broker.simple_order(c, order)

                else:
                    break

    async def place_hedge_orders(self):
        current_price = await self.broker.current_price(credentials.instrument)
        closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))
        self.otm_closest_call = closest_strike + 10
        self.otm_closest_put = closest_strike - 10
        spx_contract_call = Option(
            symbol="SPX",
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_call,
            right='C',
            exchange="SMART"
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

        spx_contract_call = Option(
            symbol="SPX",
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_put,
            right='P',
            exchange="SMART"
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol="SPX",
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange="SMART"
            )
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="SELL")
        if close_put:
            spx_contract_put = Option(
                symbol="SPX",
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='P',
                exchange="SMART"
            )
            await self.broker.place_market_order(contract=spx_contract_put, qty=1, side="SELL")

    async def place_atm_call_order(self, sl):
        current_price = await self.broker.current_price("SPX", "CBOE")
        self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        premium_price = await self.broker.get_latest_premium_price("SPX", credentials.date, self.closest_current_price,
                                                                   "C")
        spx_contract = Option(
            symbol="SPX",
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.closest_current_price,
            right='C',
            exchange="SMART"
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")

        k = await self.broker.place_bracket_order(symbol="SPX", quantity=1, price=premium_price,
                                                  expiry=credentials.date,
                                                  strike=self.closest_current_price, right="C", trailingpercent=sl)
        print(k)
        self.atm_call_parendID = k['parent_id']
        self.atm_call_fill = k['avgFill']
        print(k)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
