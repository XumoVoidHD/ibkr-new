import creds
from ib_wrapper import IBWrapper
from ib_insync import *
import time
import asyncio


class Strategy:

    def __init__(self):
        self.broker = IBWrapper(creds.port)
        self.strikes = None
        self.otm_closest_call = None
        self.otm_closest_put = None
        self.date = creds.date
        self.active_positions = {}  # Track active positions and their details
        self.stop_loss_threads = {}  # Track stop loss monitoring threads

    async def main(self):
        print("Started Bot")
        self.strikes = self.broker.fetch_strikes(creds.instrument, creds.exchange)
        current_price = self.broker.current_price("SPX", "CBOE")
        k = asyncio.run(self.place_hedge_orders())

    async def place_hedge_orders(self):
        current_price = self.broker.current_price("SPX", "CBOE")
        otm_call_strike = round(current_price + 10, 1)
        otm_put_strike = round(current_price - 10, 1)

        self.otm_closest_call = min(self.strikes, key=lambda x: abs(x - otm_call_strike))
        self.otm_closest_put = min(self.strikes, key=lambda x: abs(x - otm_put_strike))

        spx_contract_call = Option(
            symbol=creds.instrument,
            lastTradeDateOrContractMonth=self.date,
            strike=self.otm_closest_call,
            right='C',
            exchange=creds.exchange
        )
        spx_contract_put = Option(
            symbol=creds.instrument,
            lastTradeDateOrContractMonth=self.date,
            strike=self.otm_closest_put,
            right='P',
            exchange=creds.exchange
        )

        # Place orders concurrently
        self.broker.place_market_order(contract=spx_contract_call, qty=1, side="BUY")
        self.broker.place_market_order(contract=spx_contract_put, qty=1, side="BUY")

    async def close_open_hedges(self, close_put=True, close_call=True):
        if close_call:
            spx_contract_call = Option(
                symbol=creds.instrument,
                lastTradeDateOrContractMonth=self.date,
                strike=self.otm_closest_call,
                right='C',
                exchange=creds.exchange
            )
            self.broker.place_market_order(contract=spx_contract_call, qty=1, side="SELL")
        if close_put:
            spx_contract_put = Option(
                symbol=creds.instrument,
                lastTradeDateOrContractMonth=self.date,
                strike=self.otm_closest_put,
                right='P',
                exchange=creds.exchange
            )
            self.broker.place_market_order(contract=spx_contract_put, qty=1, side="SELL")

    async def place_atm_call_order(self, sl):
        current_price = self.broker.current_price("SPX", "CBOE")
        closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))

        spx_contract = Option(
            symbol=creds.instrument,
            lastTradeDateOrContractMonth=self.date,
            strike=closest_current_price,
            right='C',
            exchange=creds.exchange
        )

        _, fill_price = self.broker.place_market_order(contract=spx_contract, qty=1, side="SELL")
        stop_loss_price = fill_price * (1 + sl)

        position_id = f"call_{closest_current_price}_{time.time()}"



        self.active_positions[position_id] = {
            'contract': spx_contract,
            'entry_price': fill_price,
            'stop_loss': stop_loss_price
        }

    async def place_atm_put_order(self, sl):
        current_price = self.broker.current_price("SPX", "CBOE")
        closest_current_price = min(self.strikes, key=lambda x: abs(x - current_price))

        spx_contract = Option(
            symbol=creds.instrument,
            lastTradeDateOrContractMonth=self.date,
            strike=closest_current_price,
            right='P',
            exchange=creds.exchange
        )
        _, fill_price = self.broker.place_market_order(contract=spx_contract, qty=1, side="SELL")
        stop_loss_price = fill_price * (1 - sl)


if __name__ == "__main__":
    s = Strategy()
    asyncio.run(s.main())
