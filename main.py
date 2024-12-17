from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio


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
        self.call_percent = 0.15
        self.put_percent = 0.15
        self.atm_call_fill = None
        self.atm_call_limit_price = None
        self.hedge_otm_difference = 10

    async def main(self):
        print("\n1. Testing connection...")
        await self.broker.connect()
        print(f"Connection status: {self.broker.is_connected()}")
        self.closest_current_price = self.broker.current_price(credentials.instrument)
        self.broker.ib.reqMarketDataType(4)
        self.strikes = await self.broker.fetch_strikes(credentials.instrument, "CBOE", secType="IND")

        await self.place_hedge_orders()
        await asyncio.sleep(1)

        await asyncio.gather(
            self.place_atm_call_order(self.atm_sl),
            self.place_atm_put_order(self.atm_sl),
        )

        await asyncio.gather(
            self.atm_call_trail_sl(),
            self.atm_put_trail_sl(),
        )

    async def atm_call_trail_sl(self):
        temp_percentage = 0.95
        while True:
            k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                           self.closest_current_price, "C")
            check = k['ask']
            if check <= temp_percentage * self.atm_call_limit_price:
                if self.call_percent > 0.01:
                    self.call_percent -= 0.01
                    open_orders_list = await self.broker.get_open_orders()
                    call = next((trade for trade in open_orders_list if trade.contract.right == "C"), None)
                    await self.broker.modify_option_trail_percent(call, self.call_percent)
                    temp_percentage -= 0.05
                    print(f"Bought: {self.atm_call_limit_price}\nCurrent percent: {temp_percentage}")
                    await asyncio.sleep(120)
                else:
                    break
            else:
                await asyncio.sleep(120)
                print("No Change")

    async def atm_put_trail_sl(self):
        temp_percentage = 0.95
        while True:
            k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                           self.closest_current_price, "P")
            check = k['ask']
            if check <= temp_percentage * self.atm_put_limit_price:
                if self.put_percent > 0.01:
                    self.put_percent -= 0.01
                    open_orders_list = await self.broker.get_open_orders()
                    put = next((trade for trade in open_orders_list if trade.contract.right == "P"), None)
                    await self.broker.modify_option_trail_percent(put, self.put_percent)
                    temp_percentage -= 0.05
                    print(f"Bought: {self.atm_put_limit_price}\nCurrent percent: {temp_percentage}")
                    await asyncio.sleep(120)
                else:
                    break
            else:
                await asyncio.sleep(120)
                print("No Change")

    async def place_hedge_orders(self):
        current_price = await self.broker.current_price(credentials.instrument)
        closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))
        self.otm_closest_call = closest_strike + self.hedge_otm_difference
        self.otm_closest_put = closest_strike - self.hedge_otm_difference
        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_call,
            right='C',
            exchange=credentials.exchange
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_put,
            right='P',
            exchange=credentials.exchange
        )
        await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange=credentials.exchange
            )
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="SELL")
        if close_put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='P',
                exchange=credentials.exchange
            )
            await self.broker.place_market_order(contract=spx_contract_put, qty=1, side="SELL")

    async def place_atm_call_order(self, sl):
        current_price = await self.broker.current_price(credentials.instrument, "CBOE")
        self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        premium_price = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                                   self.closest_current_price,"C")
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.closest_current_price,
            right='C',
            exchange=credentials.exchange
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        stop_loss = premium_price['last'] * (1 - self.call_percent)

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
            exchange=credentials.exchange
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])
        stop_loss = premium_price['last'] * (1 - self.put_percent)
        k = await self.broker.place_bracket_order(symbol=credentials.instrument,
                                                  quantity=1,
                                                  price=premium_price['ask'],
                                                  stoploss=stop_loss,
                                                  expiry=credentials.date,
                                                  strike=self.closest_current_price,
                                                  right="P",
                                                  trailingpercent=sl)
        print(premium_price)
        self.atm_put_limit_price = premium_price['ask']
        self.atm_put_parendID = k['parent_id']
        self.atm_put_fill = k['avgFill']


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
