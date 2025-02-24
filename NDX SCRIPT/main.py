from new_broker import IBTWSAPI
import credentials
import asyncio
from ib_insync import *
import nest_asyncio
from datetime import datetime
from pytz import timezone
from discord_bot import send_discord_message
import os
import logging


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
    "client_id": 13
}


class Strategy:

    def __init__(self):
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
        self.func_test = False
        self.enable_logging = credentials.enable_logging
        self.logger = setup_logging() if self.enable_logging else None

    async def dprint(self, phrase):
        print(phrase)
        if self.enable_logging:
            self.logger.info(phrase)
        await send_discord_message(phrase)

    async def main(self):
        current_time = datetime.now(timezone('US/Eastern'))
        print(current_time)
        await send_discord_message("." * 100)
        await self.dprint("\n1. Testing connection...")
        await self.broker.connect()
        await self.dprint(f"Connection status: {self.broker.is_connected()}")

        if self.reset:
            await self.close_all_positions(test=True)
            return

        if self.func_test:
            await self.broker.cancel_all()
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
            await self.dprint(f"Current Time: {current_time}")
            if (start_time <= current_time <= closing_time) or self.testing:
                self.strikes = await self.broker.fetch_strikes(credentials.instrument, credentials.exchange,
                                                               secType="IND")
                current_price = await self.broker.current_price(credentials.instrument, credentials.exchange)
                current_price = round(current_price / 10) * 10

                if credentials.instrument == "NDX":
                    if str(current_price).endswith("75"):
                        current_price = (current_price // 10) * 10 + 70
                    elif str(current_price).endswith("25"):
                        current_price = (current_price // 10) * 10 + 20

                closest_strike = min(self.strikes, key=lambda x: abs(x - current_price))

                await self.dprint("\n\nNew Trading Session Start\n")
                await self.dprint(f"CURRENT PRICE: {current_price}")

                await self.dprint(f"CLOSEST CURRENT PRICE: {closest_strike}")

                self.otm_closest_call = closest_strike + (credentials.OTM_CALL_HEDGE * 10)
                await self.dprint(f"CALL HEDGE STRIKE PRICE: {self.otm_closest_call}")

                self.otm_closest_put = closest_strike - (credentials.OTM_PUT_HEDGE * 10)
                await self.dprint(f"PUT HEDGE STRIKE PRICE: {self.otm_closest_put}")

                self.call_target_price = closest_strike
                if credentials.ATM_CALL > 0:
                    self.call_target_price += 10 * credentials.ATM_CALL
                await self.dprint(f"CALL POSITION STRIKE PRICE: {self.call_target_price}")

                self.put_target_price = closest_strike
                if credentials.ATM_CALL > 0:
                    self.put_target_price -= 10 * credentials.ATM_CALL
                await self.dprint(f"PUT POSITION STRIKE PRICE: {self.put_target_price}")
                await self.place_hedge_orders(call=True, put=True)
                await self.place_atm_put_order()
                await self.place_atm_call_order()
                break
            else:
                await self.dprint("Market hasn't opened yet")
            await asyncio.sleep(10)

        await asyncio.gather(
            self.call_check(),
            self.close_all_positions(test=False),
            self.put_check(),
        )

    async def close_all_positions(self, test):
        if credentials.close_positions:
            return
        else:
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
                    await self.dprint("Closing all positions")
                    break

                await asyncio.sleep(10)

    async def place_hedge_orders(self, call, put):
        if call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange="SMART",
                currency="USD",
                multiplier='100'
            )
            qualified_contracts = self.broker.client.qualifyContracts(spx_contract_call)
            if not qualified_contracts:
                raise ValueError("Failed to qualify contract with IBKR.")
            try:
                await self.broker.place_market_order(contract=spx_contract_call,
                                                     qty=credentials.call_hedge_quantity, side="BUY")
                await self.dprint("Placing Hedge Call Order")
            except Exception as e:
                await self.dprint(f"Error placing call hedge order: {str(e)}")

        if put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_put,
                right='P',
                exchange="SMART",
                currency="USD",
                multiplier='100'
            )
            try:
                await self.broker.place_market_order(contract=spx_contract_put, qty=credentials.put_hedge_quantity,
                                                     side="BUY")
                await self.dprint("Placing Hedge Put Order")
            except Exception as e:
                await self.dprint(f"Error placing put hedge order: {str(e)}")

    async def close_open_hedges(self, close_put=False, close_call=False):
        if close_call:
            spx_contract_call = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_call,
                right='C',
                exchange="SMART",
                currency="USD",
                multiplier='100'
            )
            qualified_contracts = self.broker.client.qualifyContracts(spx_contract_call)
            if not qualified_contracts:
                raise ValueError("Failed to qualify contract with IBKR.")
            try:
                await self.broker.place_market_order(contract=spx_contract_call, qty=credentials.call_hedge_quantity,
                                                     side="SELL")
                await self.dprint("Closing Call Hedge")
            except Exception as e:
                await self.dprint(f"Error closing call hedge: {str(e)}")

        if close_put:
            spx_contract_put = Option(
                symbol=credentials.instrument,
                lastTradeDateOrContractMonth=credentials.date,
                strike=self.otm_closest_put,
                right='P',
                exchange="SMART",
                currency="USD",
                multiplier='100'
            )
            try:
                await self.broker.place_market_order(contract=spx_contract_put, qty=credentials.put_hedge_quantity,
                                                     side="SELL")
                await self.dprint("Closing Put Hedge")
            except Exception as e:
                await self.dprint(f"Error closing put hedge: {str(e)}")

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
            exchange="SMART",
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        try:
            k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.call_position,
                                                     side="SELL")
            self.call_order_placed = True
            self.atm_call_fill = k[1]
            self.call_contract = spx_contract
            self.atm_call_sl = self.atm_call_fill * (1 + (self.call_percent / 100))
            await self.dprint(f"Call Order placed at {k[1]}")
        except Exception as e:
            await self.dprint(f"Error in placing sell side call order: {str(e)}")

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
                    await self.dprint(
                        f"[CALL] Stop loss triggered - Executing market buy"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nStop Loss Level: {self.atm_call_sl}"
                        f"\nStrike Price: {self.call_target_price}"
                        f"\nPosition Size: {credentials.call_position}"
                    )
                    await self.broker.place_market_order(contract=self.call_contract, qty=credentials.call_position,
                                                         side="BUY")
                    await self.close_open_hedges(close_call=True, close_put=False)
                    self.call_order_placed = False
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_call_fill:
                    self.atm_call_sl = self.atm_call_sl - (self.atm_call_fill * (credentials.call_change_sl_by / 100))
                    await self.dprint(
                        f"[CALL] Price dip detected - Adjusting trailing parameters"
                        f"\nFill Price: {self.atm_call_fill}"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nDip Threshold: {temp_percentage * self.atm_call_fill}"
                        f"\nOld Temp %: {temp_percentage:.2%}"
                        f"\nNew Temp %: {(temp_percentage - credentials.call_entry_price_changes_by / 100):.2%}"
                        f"\nNew SL: {self.atm_call_sl}"
                    )
                    temp_percentage -= credentials.call_entry_price_changes_by / 100
                    if temp_percentage < 0:
                        temp_percentage = 0
                        await self.dprint(f"Put trailing sl is at {temp_percentage}")
                    continue

                if temp_percentage <= 0:
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
                    await self.dprint(
                        f"[CALL] Entry condition met - Initiating new position"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nEntry Price: {self.atm_call_fill}"
                        f"\nStrike Price: {self.call_target_price}"
                        f"\nReentry Count: {self.call_rentry + 1}"
                    )
                    self.call_rentry += 1
                    await self.place_hedge_orders(call=True, put=False)
                    await self.place_atm_call_order()
                    temp_percentage = 1 - (credentials.put_entry_price_changes_by / 100)
                    self.call_order_placed = True
                    continue

                if not self.call_rentry < credentials.number_of_re_entry:
                    await self.dprint("Call re-entry limit reached")
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
            exchange="SMART",
            currency="USD",
            multiplier='100'
        )

        qualified_contracts = self.broker.client.qualifyContracts(spx_contract)
        if not qualified_contracts:
            raise ValueError("Failed to qualify contract with IBKR.")
        print('last price is', premium_price['last'])

        try:
            k = await self.broker.place_market_order(contract=spx_contract, qty=credentials.put_position,
                                                     side="SELL")
            await self.dprint(f"Put Order placed at {k[1]}")
            self.put_order_placed = True
            self.atm_put_fill = k[1]
            self.put_contract = spx_contract
            self.atm_put_sl = self.atm_put_fill * (1 + (self.put_percent / 100))
        except Exception as e:
            await self.dprint(f"Error in placing sell side put order: {str(e)}")

    async def put_check(self):
        temp_percentage = 1 - (credentials.put_entry_price_changes_by / 100)
        while self.should_continue:
            if self.put_order_placed:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.put_target_price,
                    right="P"
                )

                if premium_price['mid'] >= self.atm_put_sl:
                    await self.dprint(
                        f"[PUT] Stop loss triggered - Executing market buy"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nStop Loss Level: {self.atm_put_sl}"
                        f"\nStrike Price: {self.put_target_price}"
                        f"\nPosition Size: {credentials.put_position}"
                    )
                    await self.broker.place_market_order(contract=self.put_contract, qty=credentials.put_position,
                                                         side="BUY")
                    await self.close_open_hedges(close_call=False, close_put=True)
                    self.put_order_placed = False
                    continue

                if premium_price['mid'] <= temp_percentage * self.atm_put_fill:
                    self.atm_put_sl = self.atm_put_sl - (self.atm_put_fill * (credentials.put_change_sl_by / 100))
                    await self.dprint(
                        f"[PUT] Price dip detected - Adjusting trailing parameters"
                        f"\nFill Price: {self.atm_put_fill}"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nDip Threshold: {temp_percentage * self.atm_put_fill}"
                        f"\nOld Temp %: {temp_percentage:.2%}"
                        f"\nNew Temp %: {(temp_percentage - (credentials.put_entry_price_changes_by / 100)):.2%}"
                        f"\nNew SL: {self.atm_put_sl}"
                    )
                    temp_percentage -= credentials.put_entry_price_changes_by / 100
                    if temp_percentage < 0:
                        temp_percentage = 0
                        await self.dprint(f"Put trailing sl is at {temp_percentage}")
                    continue

                if temp_percentage <= 0:
                    continue

                await asyncio.sleep(1)
            else:
                premium_price = await self.broker.get_latest_premium_price(
                    symbol=credentials.instrument,
                    expiry=credentials.date,
                    strike=self.put_target_price,
                    right="P"
                )

                if premium_price['mid'] <= self.atm_put_fill and self.put_rentry < credentials.number_of_re_entry:
                    await self.dprint(
                        f"[PUT] Entry condition met - Initiating new position"
                        f"\nCurrent Premium: {premium_price['mid']}"
                        f"\nEntry Price: {self.atm_put_fill}"
                        f"\nStrike Price: {self.put_target_price}"
                        f"\nReentry Count: {self.put_rentry + 1}"
                    )
                    self.put_rentry += 1
                    await self.place_hedge_orders(call=False, put=True)
                    await self.place_atm_put_order()
                    temp_percentage = 1 - (credentials.put_entry_price_changes_by / 100)
                    self.put_order_placed = True
                    continue

                if not self.put_rentry < credentials.number_of_re_entry:
                    await self.dprint("Put re-entry limit reached")
                    return

                await asyncio.sleep(5)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
