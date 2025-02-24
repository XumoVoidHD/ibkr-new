from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio
from datetime import datetime
from pytz import timezone
import logging
import os


# Configure logging
def setup_logging():
    os.makedirs('logs', exist_ok=True)

    # Get the current date in US/Eastern timezone
    eastern = timezone('US/Eastern')
    current_date = datetime.now(eastern).strftime('%Y-%m-%d')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(f'logs/strategy_log_{current_date}.txt', mode='w'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


nest_asyncio.apply()

creds = {
    "host": credentials.host,
    "port": credentials.port,
    "client_id": 12
}


class Strategy:
    def __init__(self):
        self.logger = setup_logging()

        self.call_target_price = None
        self.put_target_price = None
        self.atm_put_sl = None
        self.put_contract = None
        self.call_contract = None
        self.atm_call_sl = None
        self.atm_put_fill = None
        self.otm_closest_call = None
        self.otm_closest_put = None
        self.broker = IBTWSAPI(creds=creds)
        self.strikes = None
        self.call_percent = credentials.call_sl
        self.put_percent = credentials.put_sl
        self.atm_call_fill = None
        self.call_rentry = 0
        self.put_rentry = 0
        self.call_order_placed = False
        self.put_order_placed = False
        self.should_continue = True
        self.testing = False
        self.reset = False

    async def main(self):
        self.logger.info("\n1. Testing connection...")
        await self.broker.connect()
        self.logger.info(f"\nConnection status: {self.broker.is_connected()}")

        if self.reset:
            await self.close_all_positions(test=True)
            return

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
            self.logger.info(str(current_time))
            if (start_time <= current_time <= closing_time) or self.testing:
                self.strikes = await self.broker.fetch_strikes(credentials.instrument, credentials.exchange,
                                                               secType="IND")
                current_price = await self.broker.current_price(credentials.instrument)
                closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))

                self.logger.info(f"\nCURRENT PRICE: {current_price}")
                self.logger.info(f"\nCLOSEST CURRENT PRICE: {closest_strike}")

                self.otm_closest_call = closest_strike + (credentials.OTM_CALL_HEDGE * 5)
                self.logger.info(f"\nCALL HEDGE STRIKE PRICE: {self.otm_closest_call}")

                self.otm_closest_put = closest_strike - (credentials.OTM_PUT_HEDGE * 5)
                self.logger.info(f"\nPUT HEDGE STRIKE PRICE: {self.otm_closest_put}")

                self.call_target_price = closest_strike
                if credentials.ATM_CALL > 0:
                    self.call_target_price += 5 * credentials.ATM_CALL
                self.logger.info(f"\nCALL POSITION STRIKE PRICE: {self.call_target_price}")

                self.put_target_price = closest_strike
                if credentials.ATM_CALL > 0:
                    self.put_target_price -= 5 * credentials.ATM_CALL
                self.logger.info(f"\nPUT POSITION STRIKE PRICE: {self.put_target_price}")

                await self.place_hedge_orders(call=True, put=True)
                await self.place_atm_put_order()
                await self.place_atm_call_order()
                break
            else:
                self.logger.info("\nMarket hasn't opened yet")
            await asyncio.sleep(10)

        await asyncio.gather(
            self.call_check(),
            self.close_all_positions(test=False),
            self.put_check(),
        )

    async def close_all_positions(self, test):
        while True:
            current_time = datetime.now(timezone('US/Eastern'))
            target_time = current_time.replace(
                hour=credentials.exit_hour,
                minute=credentials.exit_minute,
                second=credentials.exit_second,
                microsecond=0)

            if current_time >= target_time or test:
                self.should_continue = False
                await self.broker.cancel_all()
                await asyncio.sleep(20)
                await self.broker.cancel_all()
                self.logger.info("\nMarket Closed")
                break

            await asyncio.sleep(10)

    async def place_hedge_orders(self, call, put):
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
                self.logger.info(str(k))
            except Exception as e:
                self.logger.error(f"\nError placing call hedge order: {str(e)}")

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
            except Exception as e:
                self.logger.error(f"\nError placing put hedge order: {str(e)}")

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
                self.logger.error(f"\nError closing call hedge: {str(e)}")

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
                self.logger.error(f"\nError closing put hedge: {str(e)}")

    async def place_atm_call_order(self):
        premium_price = await self.broker.get_latest_premium_price(
            symbol=credentials.instrument,
            expiry=credentials.date,
            strike=self.call_target_price,
            right="C"
        )
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.call_target_price,
            right='C',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("\nFailed to qualify contract with IBKR.")
        self.logger.info(f'\nlast price is {premium_price["last"]}')

        k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.call_position,
                                                 side="SELL")

        self.call_order_placed = True
        self.call_contract = spx_contract
        self.atm_call_fill = k[1]
        self.atm_call_sl = self.atm_call_fill * (1 + (self.call_percent / 100))

    async def call_check(self):
        temp_percentage = 1 - (credentials.call_entry_price_changes_by / 100)
        while self.should_continue:
            if self.call_order_placed:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.call_target_price,
                    right="C"
                )

                if premium_price['mid'] >= self.atm_call_sl:
                    self.logger.info(
                        f"\n[CALL] Stop loss triggered - Executing market buy"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Stop Loss Level: {self.atm_call_sl}"
                        f"\n Strike Price: {self.call_target_price}"
                        f"\n Position Size: {credentials.call_position}"
                    )
                    await self.broker.place_market_order(contract=self.call_contract, qty=credentials.call_position,
                                                         side="BUY")
                    await self.close_open_hedges(close_call=True, close_put=False)
                    self.call_order_placed = False
                    continue

                if temp_percentage <= 0:
                    self.logger.info(f"\nCall trailing sl is at {temp_percentage}")
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_call_fill:
                    self.atm_call_sl = self.atm_call_sl - (self.atm_call_fill * (credentials.call_change_sl_by / 100))
                    self.logger.info(
                        f"\n[CALL] Price dip detected - Adjusting trailing parameters"
                        f"\n Fill Price: {self.atm_call_fill}"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Dip Threshold: {temp_percentage * self.atm_call_fill}"
                        f"\n Old Temp %: {temp_percentage:.2%}"
                        f"\n New Temp %: {(temp_percentage - credentials.call_entry_price_changes_by / 100):.2%}"
                        f"\n New SL: {self.atm_call_sl}"
                    )
                    temp_percentage -= credentials.call_entry_price_changes_by / 100
                    continue

                await asyncio.sleep(1)
            else:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.call_target_price,
                    right="C"
                )

                if premium_price['mid'] <= self.atm_call_fill and self.call_rentry < credentials.number_of_re_entry:
                    self.logger.info(
                        f"\n[CALL] Entry condition met - Initiating new position"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Entry Price: {self.atm_call_fill}"
                        f"\n Strike Price: {self.call_target_price}"
                        f"\n Reentry Count: {self.call_rentry + 1}"
                    )
                    self.call_rentry += 1
                    await self.place_hedge_orders(call=True, put=False)
                    await self.place_atm_call_order()
                    self.call_order_placed = True

                if not self.call_rentry < credentials.number_of_re_entry:
                    self.logger.info("\nCall re-entry limit reached")
                    return

                await asyncio.sleep(5)

    async def place_atm_put_order(self):
        premium_price = await self.broker.get_latest_premium_price(
            symbol=credentials.instrument,
            expiry=credentials.date,
            strike=self.put_target_price,
            right="P"
        )
        spx_contract = Option(
            symbol=credentials.instrument,
            lastTradeDateOrContractMonth=credentials.date,
            strike=self.put_target_price,
            right='P',
            exchange=credentials.exchange,
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("\nFailed to qualify contract with IBKR.")
        self.logger.info(f'\nlast price is {premium_price["last"]}')

        k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.put_position,
                                                 side="SELL")

        self.put_order_placed = True
        self.put_contract = spx_contract
        self.atm_put_fill = k[1]
        self.atm_put_sl = self.atm_put_fill * (1 + (self.put_percent / 100))

    async def put_check(self):
        temp_percentage = 1 - (credentials.put_entry_price_changes_by / 100)
        while self.should_continue:
            current_time = datetime.now(timezone('US/Eastern'))
            print(current_time)
            if self.put_order_placed:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.put_target_price,
                    right="P"
                )

                if premium_price['mid'] >= self.atm_put_sl:
                    self.logger.info(
                        f"\n[PUT] Stop loss triggered - Executing market buy"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Stop Loss Level: {self.atm_put_sl}"
                        f"\n Strike Price: {self.put_target_price}"
                        f"\n Position Size: {credentials.put_position}"
                    )
                    await self.broker.place_market_order(
                        contract=self.put_contract,
                        qty=credentials.put_position,
                        side="BUY"
                    )
                    await self.close_open_hedges(close_call=False, close_put=True)
                    self.put_order_placed = False
                    continue

                if temp_percentage <= 0:
                    self.logger.info(f"\nPut trailing sl is at {temp_percentage}")
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_put_fill:
                    self.atm_put_sl = self.atm_put_sl - (
                            self.atm_put_fill * (credentials.put_change_sl_by / 100)
                    )
                    self.logger.info(
                        f"\n[PUT] Price dip detected - Adjusting trailing parameters"
                        f"\n Fill Price: {self.atm_put_fill}"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Dip Threshold: {temp_percentage * self.atm_put_fill}"
                        f"\n Old Temp %: {temp_percentage:.2%}"
                        f"\n New Temp %: {(temp_percentage - credentials.put_entry_price_changes_by / 100):.2%}"
                        f"\n New SL: {self.atm_put_sl}"
                    )
                    temp_percentage -= credentials.put_entry_price_changes_by / 100
                    continue

                await asyncio.sleep(1)
            else:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.put_target_price,
                    right="P"
                )

                if (premium_price['mid'] <= self.atm_put_fill and
                        self.put_rentry < credentials.number_of_re_entry):
                    self.logger.info(
                        f"\n[PUT] Entry condition met - Initiating new position"
                        f"\n Current Premium: {premium_price['mid']}"
                        f"\n Entry Price: {self.atm_put_fill}"
                        f"\n Strike Price: {self.put_target_price}"
                        f"\n Reentry Count: {self.put_rentry + 1}"
                    )
                    self.put_rentry += 1
                    await self.place_hedge_orders(call=False, put=True)
                    await self.place_atm_put_order()
                    self.put_order_placed = True

                if not self.put_rentry < credentials.number_of_re_entry:
                    self.logger.info("\nPut re-entry limit reached")
                    return

                await asyncio.sleep(5)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())