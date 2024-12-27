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
        self.put_hedge_open = None
        self.atm_put_fill = None
        self.atm_put_parendID = None
        self.atm_call_parendID = None
        self.atm_put_limit_price = None
        self.closest_current_price = None
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
        self.hedge_otm_difference = credentials.hedge_difference
        self.temp_order = None
        self.call_rentry = 0
        self.put_rentry = 0
        self.rentry_limit = credentials.number_of_re_entry
        self.call_order_placed = False
        self.put_order_placed = False
        self.call_hedge_open = False
        self.should_continue = True
        self.testing = True

    async def main(self):
        print("\n1. Testing connection...")
        await self.broker.connect()
        print(f"Connection status: {self.broker.is_connected()}")
        self.closest_current_price = self.broker.current_price(credentials.instrument)
        self.broker.ib.reqMarketDataType(4)
        self.strikes = await self.broker.fetch_strikes(credentials.instrument, "CBOE", secType="IND")

        while True:
            current_time = datetime.now(timezone('US/Eastern'))
            target_time = current_time.replace(hour=9, minute=35, second=0, microsecond=0)

            if current_time >= target_time or self.testing:
                await self.place_hedge_orders(call=True, put=True)
                await self.place_atm_put_order(self.put_sl, initial=True)
                await self.place_atm_call_order(self.call_sl, initial=True)
                break
            else:
                print("Market hasn't opened yet")
            await asyncio.sleep(10)

        await asyncio.gather(
            self.check_call_status(),
            self.check_put_status(),
            self.close_all_positions(),
            self.atm_call_trail_sl(),
            self.atm_put_trail_sl(),
        )

    async def close_all_positions(self):
        while True:
            current_time = datetime.now(timezone('US/Eastern'))
            target_time = current_time.replace(hour=15, minute=45, second=0, microsecond=0)

            if current_time >= target_time:
                await self.broker.cancel_all()
                self.should_continue = False
                break

            await asyncio.sleep(10)

    async def check_call_status(self):
        while self.call_rentry < self.rentry_limit and self.should_continue:
            positions = await self.broker.get_positions()
            call_position_exists = any(
                hasattr(position.contract, 'right') and
                position.contract.right == 'C' and
                position.position == -1.0
                for position in positions
            )

            if not call_position_exists:
                if self.call_hedge_open:
                    await self.close_open_hedges(close_call=True, close_put=False)
                    self.call_hedge_open = False

                while True:
                    current_price = await self.broker.current_price(credentials.instrument, "CBOE")
                    self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
                    k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                                   self.closest_current_price, "C")
                    print("Checking call price")
                    check = k['ask']
                    if check <= self.atm_call_fill:
                        self.call_rentry += 1
                        self.call_order_placed = False
                        await self.place_atm_call_order(self.call_sl, initial=True)
                        await self.place_hedge_orders(call=True, put=False)
                        break
                    await asyncio.sleep(120)
            else:
                print("Call positions still open")
                await asyncio.sleep(5)
        else:
            print("Number of call re-entries exceeded")
            return

    async def check_put_status(self):
        while self.call_rentry < self.rentry_limit and self.should_continue:
            positions = await self.broker.get_positions()
            call_position_exists = any(
                hasattr(position.contract, 'right') and
                position.contract.right == 'P' and
                position.position == -1.0
                for position in positions
            )

            if not call_position_exists:
                if self.put_hedge_open:
                    await self.close_open_hedges(close_call=False, close_put=True)
                    self.put_hedge_open = False

                while True:
                    current_price = await self.broker.current_price(credentials.instrument, "CBOE")
                    self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
                    k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                                   self.closest_current_price, "P")

                    print("Checking put price")
                    check = k['ask']
                    if check <= self.atm_put_fill:
                        self.put_rentry += 1
                        self.put_order_placed = False
                        await self.place_atm_call_order(self.put_sl, initial=True)
                        await self.place_hedge_orders(call=False, put=True)
                        break
                    await asyncio.sleep(120)
            else:
                print("Put positions still open")
                await asyncio.sleep(5)
        else:
            print("Number of put re-entries exceeded")
            return

    async def check_order_status(self):
        # Get all open orders
        open_orders_list = await self.broker.get_open_orders()

        # Initialize status dictionaries
        call_status = {
            'is_open': False,
            'details': None
        }
        put_status = {
            'is_open': False,
            'details': None
        }

        # Check for call orders
        if self.atm_call_parendID:
            for order in open_orders_list:
                if hasattr(order, 'orderId') and order.parentId == self.atm_call_parendID:
                    call_status['is_open'] = True
                    call_status['details'] = order
                    break

        # Check for put orders
        if self.atm_put_parendID:
            for order in open_orders_list:
                if hasattr(order, 'orderId') and order.parentId == self.atm_put_parendID:
                    put_status['is_open'] = True
                    put_status['details'] = order
                    break

        return {
            'call': call_status,
            'put': put_status
        }

    async def print_order_status(self):
        status = await self.check_order_status()

        print("\nOrder Status:")
        print("-------------")
        print(f"Call Order (Parent ID: {self.atm_call_parendID}):")
        print(f"  Status: {'OPEN' if status['call']['is_open'] else 'CLOSED'}")
        if status['call']['details']:
            print(f"  Details: {status['call']['details']}")

        print(f"\nPut Order (Parent ID: {self.atm_put_parendID}):")
        print(f"  Status: {'OPEN' if status['put']['is_open'] else 'CLOSED'}")
        if status['put']['details']:
            print(f"  Details: {status['put']['details']}")

    async def put_option(self):
        await self.place_hedge_orders(call=False, put=True)
        await self.place_atm_put_order(self.atm_sl)
        await self.atm_put_trail_sl()

    async def call_option(self):
        await self.place_hedge_orders(call=True, put=False)
        await self.place_atm_call_order(self.call_sl)
        await self.atm_call_trail_sl()

    async def help_order(self):
        await self.place_hedge_orders(call=True, put=True)
        await self.place_atm_put_order(self.atm_sl)
        await self.place_atm_call_order(self.atm_sl)
        # await self.atm_put_trail_sl()
        await self.print_order_status()

    async def atm_call_trail_sl(self):
        temp_percentage = 0.95
        while self.call_order_placed:
            print("Checking trail call")
            k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                           self.closest_current_price, "C")
            check = k['ask']
            if check <= temp_percentage * self.atm_call_limit_price:
                if self.call_percent > 0.01:
                    self.call_percent -= 1
                    open_orders_list = await self.broker.get_open_orders()
                    call = next((trade for trade in open_orders_list if trade.contract.right == "C"), None)
                    await self.broker.modify_option_trail_percent(call, self.call_percent)
                    temp_percentage -= 0.05
                    print(f"Bought: {self.atm_call_limit_price}\nCurrent percent: {temp_percentage}")
                    await asyncio.sleep(300)
                else:
                    break
            else:
                await asyncio.sleep(120)
                print("No Change")

    async def atm_put_trail_sl(self):
        temp_percentage = 0.95
        while self.put_order_placed:
            print("Checking trail put")
            k = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                           self.closest_current_price, "P")
            check = k['ask']
            if check <= temp_percentage * self.atm_put_limit_price:
                if self.put_percent > 0.01:
                    self.put_percent -= 1
                    open_orders_list = await self.broker.get_open_orders()
                    put = next((trade for trade in open_orders_list if trade.contract.right == "P"), None)
                    await self.broker.modify_option_trail_percent(put, self.put_percent)
                    temp_percentage -= 0.05
                    print(f"Bought: {self.atm_put_limit_price}\nCurrent percent: {temp_percentage}")
                    await asyncio.sleep(300)
                else:
                    break
            else:
                await asyncio.sleep(120)
                print("No Change")

    async def place_hedge_orders(self, call, put):
        current_price = await self.broker.current_price(credentials.instrument)
        closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))
        self.otm_closest_call = closest_strike + self.hedge_otm_difference
        self.otm_closest_put = closest_strike - self.hedge_otm_difference
        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_call,
            right='C',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100',
            # tradingClass='SPX'
        )
        if call:
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")
            self.call_hedge_open = True

        spx_contract_call = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.otm_closest_put,
            right='P',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100',
            # tradingClass='SPX'
        )

        if put:
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")
            self.put_hedge_open = True

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100',
                # tradingClass='SPX'
                # localSymbol='SPXW  241224C05855000'
            )
            await self.broker.place_market_order(contract=spx_contract_call, qty=1, side="SELL")
        if close_put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_put,
                right='P',
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100',
                # tradingClass='SPXW'
                # localSymbol='SPXW  241224P05875000'
            )
            print(spx_contract_put)
            await self.broker.place_market_order(contract=spx_contract_put, qty=1, side="SELL")

    async def place_atm_call_order(self, sl, initial):
        while True:
            if not self.call_order_placed:
                current_price = await self.broker.current_price(credentials.instrument, "CBOE")
                self.closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))
                premium_price = await self.broker.get_latest_premium_price(credentials.instrument, credentials.date,
                                                                           self.closest_current_price, "C")
                spx_contract = Option(
                    symbol=credentials.instrument,
                    lastTradeDateOrContractMonth=credentials.date,
                    strike=self.closest_current_price,
                    right='C',
                    exchange=credentials.exchange,
                    currency="USD",
                    multiplier='100',
                    # tradingClass='SPX'

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

                self.call_order_placed = True
                self.atm_call_limit_price = premium_price['ask']
                self.atm_call_parendID = k['parent_id']
                self.atm_call_fill = k['avgFill']
                self.temp_order = k['order_info']
                if initial:
                    return
                await asyncio.sleep(30)

    async def place_atm_put_order(self, sl, initial=False):
        while True:
            if not self.put_order_placed:
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
                    exchange=credentials.exchange,
                    currency="USD",
                    multiplier='100',
                    # tradingClass='SPX'
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
                self.put_order_placed = True
                self.atm_put_limit_price = premium_price['ask']
                self.atm_put_parendID = k['parent_id']
                self.atm_put_fill = k['avgFill']
                if initial:
                    return
                await asyncio.sleep(30)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
