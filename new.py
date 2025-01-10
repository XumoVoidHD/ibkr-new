from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio
from datetime import datetime
from pytz import timezone

nest_asyncio.apply()

creds = {
    "host": credentials.host,
    "port": credentials.port,
    "client_id": 12
}


class Strategy:

    def __init__(self):
        self.atm_put_sl = None
        self.put_temp_order = None
        self.atm_put_current_premium = None
        self.put_contract = None
        self.atm_call_current_premium = None
        self.call_contract = None
        self.closest_call_current_price = None
        self.atm_call_sl = None
        self.put_hedge_open = None
        self.atm_put_fill = None
        self.atm_put_parendID = None
        self.atm_call_parendID = None
        self.atm_put_limit_price = None
        self.closest_put_current_price = None
        self.otm_closest_call = None
        self.otm_closest_put = None
        self.broker = IBTWSAPI(creds=creds)
        self.strikes = None
        self.call_sl = credentials.call_sl
        self.put_sl = credentials.put_sl
        self.call_percent = credentials.call_sl
        self.put_percent = credentials.put_sl
        self.atm_call_fill = None
        self.atm_call_limit_price = None
        self.call_temp_order = None
        self.call_rentry = 0
        self.put_rentry = 0
        self.rentry_call_limit = credentials.number_of_re_entry
        self.rentry_put_limit = credentials.number_of_re_entry
        self.call_order_placed = False
        self.put_order_placed = False
        self.call_hedge_open = False
        self.should_continue = True
        self.testing = False

    async def main(self):
        print("\n1. Testing connection...")
        await self.broker.connect()
        print(f"Connection status: {self.broker.is_connected()}")
        self.closest_put_current_price = await self.broker.current_price(credentials.instrument)
        print(self.closest_put_current_price)
        self.strikes = await self.broker.fetch_strikes(credentials.instrument, "CBOE", secType="IND")

        while True:
            current_time = datetime.now(timezone('US/Eastern'))
            start_time = current_time.replace(
                hour=credentials.entry_hour,
                minute=credentials.entry_minute,
                second=credentials.entry_second,
                microsecond=0)
            closing_time = current_time.replace(
                hour=credentials.exit_hour,
                minute=credentials.exit_minute,
                second=credentials.exit_second,
                microsecond=0)

            if (start_time <= current_time <= closing_time) or self.testing:
                await self.place_hedge_orders(call=True, put=True)
                await self.place_atm_put_order()
                await self.place_atm_call_order()
                break
            else:
                print("Market hasn't opened yet")
            await asyncio.sleep(10)

        await asyncio.gather(
            self.call_check(),
            self.close_all_positions(),
            self.put_check(),
        )

    async def close_all_positions(self):
        while True:
            current_time = datetime.now(timezone('US/Eastern'))
            target_time = current_time.replace(
                hour=credentials.exit_hour,
                minute=credentials.exit_minute,
                second=credentials.exit_second,
                microsecond=0)

            if current_time >= target_time:
                await self.broker.cancel_all()
                self.should_continue = False
                await asyncio.sleep(20)
                await self.broker.cancel_all()
                print("Market Closed")
                break

            await asyncio.sleep(10)

    async def place_hedge_orders(self, call, put):
        current_price = await self.broker.current_price(credentials.instrument)
        closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))
        self.otm_closest_call = closest_strike + (credentials.OTM_CALL_HEDGE * 5)
        self.otm_closest_put = closest_strike - (credentials.OTM_PUT_HEDGE * 5)

        if call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100'
            )
            try:
                k = await self.broker.place_market_order(contract=spx_contract_call,
                                                         qty=credentials.call_hedge_quantity, side="BUY")
                print(k)
                self.call_hedge_open = True
            except Exception as e:
                print(f"Error placing call hedge order: {str(e)}")
                # You might want to implement retry logic or additional error handling here

        if put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_put,
                right='P',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100'
            )
            try:
                await self.broker.place_market_order(contract=spx_contract_put, qty=credentials.put_hedge_quantity,
                                                     side="BUY")
                self.put_hedge_open = True
            except Exception as e:
                print(f"Error placing put hedge order: {str(e)}")
                # You might want to implement retry logic or additional error handling here

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100'
            )
            try:
                await self.broker.place_market_order(contract=spx_contract_call, qty=credentials.call_hedge_quantity,
                                                     side="SELL")
            except Exception as e:
                print(f"Error closing call hedge: {str(e)}")
                # Implement retry logic or additional error handling if needed

        if close_put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_put,
                right='P',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100'
            )
            try:
                await self.broker.place_market_order(contract=spx_contract_put, qty=credentials.put_hedge_quantity,
                                                     side="SELL")
            except Exception as e:
                print(f"Error closing put hedge: {str(e)}")
                # Implement retry logic or additional error handling if needed

    async def place_atm_call_order(self):
        current_price = await self.broker.current_price(credentials.instrument, "CBOE")
        self.closest_call_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        target_price = self.closest_call_current_price
        if credentials.ATM_CALL > 0:
            target_price += 5 * credentials.ATM_CALL

        premium_price = await self.broker.get_latest_premium_price(
            symbol=credentials.instrument,
            expiry=credentials.date,
            strike=target_price,
            right="C"
        )
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=target_price,
            right='C',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.call_position,
                                                 side="SELL")

        self.call_order_placed = True
        self.atm_call_limit_price = premium_price['mid']
        self.call_contract = spx_contract
        self.atm_call_fill = k[1]
        self.atm_call_current_premium = k[1]
        self.call_temp_order = k[0]
        self.atm_call_sl = self.atm_call_fill * (1 + (self.call_percent / 100))

    async def call_check(self):
        temp_percentage = 0.95
        while self.should_continue:
            if self.call_order_placed:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.closest_call_current_price,
                    right="C"
                )

                if premium_price['mid'] < self.atm_call_current_premium:
                    print(
                        f"[CALL] Premium increase detected - Updating stop loss"
                        f"\n→ New Premium: {premium_price['mid']}"
                        f"\n→ Old Premium: {self.atm_call_current_premium}"
                        f"\n→ Old SL: {self.atm_call_sl}"
                        f"\n→ New SL: {premium_price['mid'] * (1 + (self.call_percent / 100))}"
                        f"\n→ Current Call %: {self.call_percent}%"
                    )
                    self.atm_call_sl = premium_price['mid'] * (1 + (self.call_percent / 100))
                    self.atm_call_current_premium = premium_price['mid']
                    continue

                if premium_price['mid'] >= self.atm_call_sl:
                    print(
                        f"[CALL] Stop loss triggered - Executing market buy"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Stop Loss Level: {self.atm_call_sl}"
                        f"\n→ Strike Price: {self.closest_call_current_price}"
                        f"\n→ Position Size: {credentials.call_position}"
                    )
                    await self.broker.place_market_order(contract=self.call_contract, qty=credentials.call_position,
                                                         side="BUY")
                    await self.close_open_hedges(close_call=True, close_put=False)
                    self.call_order_placed = False
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_call_fill:
                    print(
                        f"[CALL] Price dip detected - Adjusting trailing parameters"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Dip Threshold: {temp_percentage * self.atm_call_fill}"
                        f"\n→ Old Call %: {self.call_percent}%"
                        f"\n→ New Call %: {self.call_percent - 1}%"
                        f"\n→ Old Temp %: {temp_percentage:.2%}"
                        f"\n→ New Temp %: {(temp_percentage - 0.05):.2%}"
                    )
                    self.call_percent -= 1
                    temp_percentage -= 0.05
                    continue

                await asyncio.sleep(1)
            else:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.closest_call_current_price,
                    right="C"
                )

                if premium_price['mid'] <= self.atm_call_fill:
                    print(
                        f"[CALL] Entry condition met - Initiating new position"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Entry Price: {self.atm_call_fill}"
                        f"\n→ Strike Price: {self.closest_call_current_price}"
                        f"\n→ Reentry Count: {self.call_rentry + 1}"
                        f"\n→ Initial Call %: 15%"
                    )
                    self.call_percent = 15
                    self.call_rentry += 1
                    await self.place_hedge_orders(call=True, put=False)
                    await self.place_atm_call_order()
                    self.call_order_placed = True

                await asyncio.sleep(5)

    async def place_atm_put_order(self):
        current_price = await self.broker.current_price(credentials.instrument, "CBOE")
        self.closest_put_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
        target_price = self.closest_put_current_price
        if credentials.ATM_CALL > 0:
            target_price -= 5 * credentials.ATM_CALL

        premium_price = await self.broker.get_latest_premium_price(
            symbol=credentials.instrument,
            expiry=credentials.date,
            strike=target_price,
            right="P"
        )
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=target_price,
            right='P',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.put_position,
                                                 side="SELL")

        self.put_order_placed = True
        self.atm_put_limit_price = premium_price['mid']
        self.put_contract = spx_contract
        self.atm_put_fill = k[1]
        self.atm_put_current_premium = k[1]
        self.put_temp_order = k[0]
        self.atm_put_sl = self.atm_put_fill * (1 + (self.put_percent / 100))

    async def put_check(self):
        temp_percentage = 0.95
        while self.should_continue:
            if self.put_order_placed:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.closest_put_current_price,
                    right="P"
                )

                if premium_price['mid'] <= self.atm_put_current_premium:
                    print(
                        f"[PUT] Premium increase detected - Updating stop loss"
                        f"\n→ New Premium: {premium_price['mid']}"
                        f"\n→ Old Premium: {self.atm_put_current_premium}"
                        f"\n→ Old SL: {self.atm_put_sl}"
                        f"\n→ New SL: {premium_price['mid'] * (1 + (self.put_percent / 100))}"
                        f"\n→ Current Put %: {self.put_percent}%"
                    )
                    self.atm_put_sl = premium_price['mid'] * (1 + (self.put_percent / 100))
                    self.atm_put_current_premium = premium_price['mid']
                    continue

                if premium_price['mid'] >= self.atm_put_sl:
                    print(
                        f"[PUT] Stop loss triggered - Executing market buy"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Stop Loss Level: {self.atm_put_sl}"
                        f"\n→ Strike Price: {self.closest_put_current_price}"
                        f"\n→ Position Size: {credentials.put_position}"
                    )
                    await self.broker.place_market_order(contract=self.put_contract, qty=credentials.put_position,
                                                         side="BUY")
                    await self.close_open_hedges(close_call=False, close_put=True)
                    self.put_order_placed = False
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_put_fill:
                    print(
                        f"[PUT] Price dip detected - Adjusting trailing parameters"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Dip Threshold: {temp_percentage * self.atm_put_fill}"
                        f"\n→ Old Put %: {self.put_percent}%"
                        f"\n→ New Put %: {self.put_percent - 1}%"
                        f"\n→ Old Temp %: {temp_percentage:.2%}"
                        f"\n→ New Temp %: {(temp_percentage - 0.05):.2%}"
                    )
                    self.put_percent -= 1
                    temp_percentage -= 0.05
                    continue

                await asyncio.sleep(1)
            else:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.closest_put_current_price,
                    right="P"
                )

                if premium_price['mid'] <= self.atm_put_fill:
                    print(
                        f"[PUT] Entry condition met - Initiating new position"
                        f"\n→ Current Premium: {premium_price['mid']}"
                        f"\n→ Entry Price: {self.atm_put_fill}"
                        f"\n→ Strike Price: {self.closest_put_current_price}"
                        f"\n→ Reentry Count: {self.put_rentry + 1}"
                        f"\n→ Initial Put %: 15%"
                    )
                    self.put_percent = 15
                    self.put_rentry += 1
                    await self.place_hedge_orders(call=False, put=True)
                    await self.place_atm_put_order()
                    self.put_order_placed = True

                await asyncio.sleep(5)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
