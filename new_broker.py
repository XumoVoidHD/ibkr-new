import asyncio
import time

import pytz
import datetime as dt
import credentials

from ib_insync import *
import pandas as pd


#util.logToConsole('DEBUG')

class IBTWSAPI:

    def __init__(self, creds: dict):

        self.client = None
        self.CREDS = creds

    def _create_contract(self, contract: str, symbol: str, exchange: str, expiry: str = ..., strike: int = ...,
                         right: str = ...):
        """
        Creates contract object for api\n
        """

        if contract == "stocks":
            return Stock(symbol=symbol, exchange=exchange, currency="USD")

        elif contract == "options":
            return Option(symbol=symbol, lastTradeDateOrContractMonth=expiry, exchange=exchange, currency="USD",
                          strike=strike, right=right, multiplier="100", tradingClass='SPXW')

        elif contract == "futureContracts":
            return ContFuture(symbol=symbol, exchange=exchange, currency="USD")

    async def connect(self) -> bool:
        """
        Connect the system with TWS account\n
        """
        # try:
        host, port = credentials.host, credentials.port
        self.client = IB()
        self.ib = self.client
        self.client.connect(host=host, port=port, clientId=13, timeout=60)
        print("Connected")

    # except Exception as e:
    # 	print(e)
    # 	return False

    def is_connected(self) -> bool:
        """
        Get the connection status\n
        """
        return self.client.isConnected()

    def get_account_info(self):
        """
        Returns connected account info\n
        """
        account_info = self.client.accountSummary()
        return account_info

    def get_account_balance(self) -> float:
        """
        Returns account balance\n
        """
        for acc in self.get_account_info():
            if acc.tag == "AvailableFunds":
                return float(acc.value)

    async def get_positions(self):
        return self.client.positions()

    async def get_open_orders(self):
        return self.client.reqOpenOrders()

    async def get_contract_info(self, contract: str, symbol: str, exchange: str) -> dict:
        """
        Returns info of the contract\n
        """
        # Creating contract
        c = self._create_contract(contract=contract, symbol=symbol, exchange=exchange)
        if contract in ["options"]:
            c.strike = ""
            c.lastTradeDateOrContractMonth = ""

        contract_info = self.client.reqContractDetails(contract=c)
        # print(contract_info)

        return {
            "contract_obj": contract_info[0].contract,
            "expiry": contract_info[0].contract.lastTradeDateOrContractMonth
        }

    async def get_expiries_and_strikes(self, technology: str, ticker: str) -> dict:
        """
        """
        # Creating contract
        if technology.lower() == "options":
            c = Option()
        else:
            c = FuturesOption()
        c.symbol = ticker
        c.strike = ""
        c.lastTradeDateOrContractMonth = ""
        print("Over here bro")
        contract_info = self.client.reqContractDetails(contract=c)
        # print(contract_info)

        ens = {}
        for contractDetails in contract_info:
            # print(contractDetails.contract.strike, contractDetails.contract.lastTradeDateOrContractMonth, contractDetails.contract.exchange, contractDetails.contract.symbol, contractDetails.contract.right)
            s_exp = contractDetails.contract.lastTradeDateOrContractMonth
            exp = dt.date(int(s_exp[:4]), int(s_exp[4:6]), int(s_exp[-2:]))
            strike = float(contractDetails.contract.strike)

            if exp not in ens: ens[exp] = []
            if strike not in ens[exp]: ens[exp].append(strike)
        current_datetime = dt.datetime.now(pytz.timezone("UTC"))
        return {k: sorted(ens[k]) for k in sorted(ens.keys()) if k > current_datetime.date()}

    async def fetch_strikes(self, symbol, exchange, secType='STK'):
        """ STK: Stocks like AAPL
            IND: SPX and stuff
        """

        if secType == 'IND':
            contract = Index(symbol, 'CBOE', "USD")

        elif secType == 'STK':
            contract = Stock(symbol, 'SMART', "USD")
        else:
            raise ValueError(f"Unsupported secType: {secType}. Use 'IND' or 'STK'.")

        qc = self.client.qualifyContracts(contract)

        self.client.reqMarketDataType(4)

        chains = self.client.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
        chain = next(c for c in chains if c.tradingClass == symbol and c.exchange == exchange)
        strikes = chain.strikes

        return strikes

    async def place_market_order(self, contract, qty, side):
        buy_order = MarketOrder(side, qty)
        buy_trade = self.client.placeOrder(contract, buy_order)
        print("waiting for order to be placed")
        n = 0
        while True:  # Wait for up to 10 seconds
            # Wait for 1 second before checking the order status
            if buy_trade.isDone():
                # Order was filled
                print("Order placed successfully")
                fill_price = buy_trade.orderStatus.avgFillPrice
                print("Fill price:", fill_price)
                return buy_trade, fill_price
            else:
                print(f"Waiting...{contract.right}... {n + 1} seconds")
                await asyncio.sleep(1)

    async def current_price(self, symbol, exchange='CBOE'):
        spx_contract = Index(symbol, exchange)
        #spx_contract=self.client.qualifyContracts(spx_contract)[0]
        #print("qualified contract",spx_contract)
        #self.client.reqMarketDataType(4)

        market_data = self.client.reqMktData(spx_contract)
        self.ib.sleep(7)

        # # print(market_data)
        # while util.isNan(market_data.last):
        # 	self.ib.sleep(3)
        if market_data.close > 0:
            return market_data.close
        else:
            print("Market data is not subscribed or unavailable for", symbol)
            return None

    async def get_stock_price(self, symbol, exchange='SMART'):
        stock_contract = Stock(symbol, exchange, 'USD')
        self.client.qualifyContracts(stock_contract)
        self.client.reqMarketDataType(4)  # Use frozen or delayed market data if live is unavailable

        ticker = self.client.reqMktData(stock_contract, '', snapshot=True)
        while util.isNan(ticker.last):
            await asyncio.sleep(0.1)

        if ticker.last > 0:
            return ticker.last
        else:
            print(f"Market data is not subscribed or unavailable for {symbol}.")
            return None

    async def get_option_chain(self, symbol: str, exp_list: list) -> dict:
        """
        """
        exps = {}
        df = pd.DataFrame(columns=['strike', 'kind', 'close', 'last'])
        self.client.reqMarketDataType(1)
        for i in exp_list:
            cds = self.client.reqContractDetails(Option(symbol, i, exchange='SMART'))
            # print(cds)
            options = [cd.contract for cd in cds]
            # print(options)
            l = []
            for x in options:
                # print(x)
                contract = Option(symbol, i, x.strike, x.right, "SMART", currency="USD")
                # print(contract)
                snapshot = self.client.reqMktData(contract, "", True, False)
                l.append([x.strike, x.right, snapshot])
            # print(snapshot)

            while util.isNan(snapshot.bid):
                self.client.sleep()
            for ii in l:
                df = df.append(
                    {'strike': ii[0], 'kind': ii[1], 'close': ii[2].close, 'last': ii[2].last, 'bid': ii[2].bid,
                     'ask': ii[2].ask, 'mid': (ii[2].bid + ii[2].ask) / 2, 'volume': ii[2].volume}, ignore_index=True)
                exps[i] = df

        return exps

    async def get_candle_data(self, contract: str, symbol: str, timeframe: str, period: str = '2d',
                              exchange: str = "SMART") -> pd.DataFrame:
        """
        Returns candle data of a ticker\n
        """
        _tf = {
            's': "sec",
            'm': "min",
            "h": "hour"
        }

        # Creating contract
        c = self._create_contract(contract=contract, symbol=symbol, exchange=exchange)

        # Parsing timeframe
        timeframe = timeframe[:-1] + ' ' + _tf[timeframe[-1]] + ('s' if timeframe[:-1] != '1' else '')

        # Parsing period
        period = ' '.join([i.upper() for i in period])

        data = self.client.reqHistoricalData(c, '', barSizeSetting=timeframe, durationStr=period, whatToShow='MIDPOINT',
                                             useRTH=True)
        df = pd.DataFrame([(
            {
                "datetime": i.date,
                "open": i.open,
                "high": i.high,
                "low": i.low,
                "close": i.close,
            }
        ) for i in data])
        df.set_index('datetime', inplace=True)
        return df

    async def place_order(
            self,
            contract: str,
            symbol: str,
            side: str,
            quantity: int,
            order_type: str = "MARKET",
            price: float = ...,
            exchange: str = "SMART",
    ) -> dict:
        """
        Places order in TWS account\n
        """

        # Creating contract
        c = self._create_contract(contract=contract, symbol=symbol, exchange=exchange)

        # Parsing order type
        if order_type.upper() == "MARKET":
            order = MarketOrder(action=side.upper(), totalQuantity=quantity)
        elif order_type.upper() == "LIMIT":
            order = LimitOrder(action=side.upper(), totalQuantity=quantity, lmtPrice=price)
        elif order_type.upper() == "STOP":
            order = StopOrder(action=side.upper(), totalQuantity=quantity, stopPrice=price)

        order_info = self.client.placeOrder(contract=c, order=order)
        return order_info

    async def simple_order(self, c, order):
        return self.client.placeOrder(c, order)

    async def place_bracket_order(
            self,
            symbol: str,
            quantity: int,
            price: float = ...,
            stoploss: float = None,
            targetprofit: float = None,
            expiry: str = None,
            strike: float = None,
            right: str = None,
            trailingpercent: float = False,
            convert_to_mkt_order_in: int = 0
    ) -> dict:
        get_exit_side = "BUY"
        c = self._create_contract(contract="options", symbol=symbol, exchange="SMART", expiry=expiry, strike=strike,
                                  right=right)

        entry_order_info, stoploss_order_info, targetprofit_order_info = None, None, None
        parent_id = self.client.client.getReqId()

        en_order = LimitOrder(action="SELL", totalQuantity=quantity, lmtPrice=price)
        en_order.orderId = parent_id
        en_order.transmit = False

        def create_trailing_stop(quantity, parent_id=None):
            sl_order = Order()
            sl_order.action = get_exit_side
            sl_order.totalQuantity = quantity
            sl_order.orderType = "TRAIL"
            sl_order.trailingPercent = trailingpercent
            if parent_id:
                sl_order.parentId = parent_id
            sl_order.transmit = True
            return sl_order

        if trailingpercent:
            sl_order = create_trailing_stop(quantity, en_order.orderId)
        elif stoploss:
            sl_order = StopOrder(action=get_exit_side, totalQuantity=quantity, stopPrice=stoploss)
            sl_order.transmit = True

        entry_order_info = self.client.placeOrder(contract=c, order=en_order)
        self.client.sleep(1)
        if stoploss or trailingpercent:
            stoploss_order_info = self.client.placeOrder(contract=c, order=sl_order)
            print("waiting for order to be placed")
            n = 0
            while True:
                if entry_order_info.isDone():
                    print("Order placed successfully")
                    fill_price = entry_order_info.orderStatus.avgFillPrice
                    print("Fill price:", fill_price)
                    return {
                        "parent_id": parent_id,
                        "entry": entry_order_info,
                        "stoploss": stoploss_order_info,
                        "targetprofit": targetprofit_order_info,
                        "contract": c,
                        "order": sl_order,
                        "avgFill": fill_price,
                        "order_info": entry_order_info
                    }
                elif convert_to_mkt_order_in > 0 and n >= convert_to_mkt_order_in:  # Modified condition
                    print(f"Limit order not filled after {n} seconds, converting to market order")
                    market_order = MarketOrder(action="SELL", totalQuantity=quantity)
                    market_order.orderId = self.client.client.getReqId()
                    market_order.transmit = True

                    await self.cancel_order(parent_id)
                    self.client.sleep(5)

                    entry_order_info = self.client.placeOrder(contract=c, order=market_order)
                    self.client.sleep(5)

                    if entry_order_info.isDone():
                        fill_price = entry_order_info.orderStatus.avgFillPrice
                        print("Market order filled at:", fill_price)

                        # Place trailing stop after market order fills
                        trailing_stop = create_trailing_stop(quantity)
                        stoploss_order_info = self.client.placeOrder(contract=c, order=trailing_stop)

                        return {
                            "parent_id": parent_id,
                            "entry": entry_order_info,
                            "stoploss": stoploss_order_info,
                            "targetprofit": targetprofit_order_info,
                            "contract": c,
                            "order": trailing_stop,
                            "avgFill": fill_price,
                            "order_info": entry_order_info
                        }
                else:
                    print(f"Waiting...{right}... {n + 1} seconds")
                    n += 1
                    await asyncio.sleep(1)
        else:
            print("Give Stoploss as one of the parameters")

    # self.client.sleep(1)
    # if targetprofit:
    # 	targetprofit_order_info = self.client.placeOrder(contract=c, order=tp_order)

    # async def modify_order(self, order_id:int, params = {}) -> None:
    # 	self.client.

    async def cancel_order(self, order_id: int) -> None:
        """
        Cancel open order\n
        """
        orders = self.client.reqOpenOrders()
        for order in orders:
            if order.orderStatus.orderId == order_id:
                self.client.cancelOrder(order=order.orderStatus)

    async def cancel_all(self):
        orders = await self.get_open_orders()
        for order in orders:
            self.client.cancelOrder(order=order.orderStatus)
        positions = await self.get_positions()
        for position in positions:
            print(position)
            action = "SELL" if position.position > 0 else "BUY"
            quantity = position.position
            contract = Option(
                symbol=position.contract.symbol,
                lastTradeDateOrContractMonth=position.contract.lastTradeDateOrContractMonth,
                strike=position.contract.strike,
                right=position.contract.right,
                exchange=credentials.exchange,
                currency="USD",
                multiplier='100',
                tradingClass='SPX'
            )
            await self.place_market_order(contract=contract, qty=1, side=action)
            print(f"Closing position: {action} {quantity} {position.contract.localSymbol} at market")

    async def query_order(self, order_id: int) -> dict:
        """
        Queries order\n
        """

        all_orders = self.client.openOrders() + [i.order for i in self.client.reqCompletedOrders(True)]

        for order in all_orders:
            print(order)
            if order.permId == order_id:
                return order

    async def modify_trailing_stop_percent(self, order_id, new_trailing_percent):
        # Get the existing order
        trades = self.client.trades()
        target_trade = next((t for t in trades if t.order.orderId == order_id), None)

        if not target_trade:
            raise ValueError(f"Order with ID {order_id} not found")

        # Create a new order with modified trailing percent
        modified_order = target_trade.order
        modified_order.trailingPercent = new_trailing_percent

        # Submit the modification
        self.client.placeOrder(target_trade.contract, modified_order)

        await self.client.sleep(10)

        return modified_order

    async def connect_app(self, app) -> None:
        """
        Connect main app with api\n
        """
        self.app = app

    async def get_latest_premium_price(self, symbol, expiry, strike, right, exchange="CBOE"):

        option_contract = Option(
            symbol=symbol,
            lastTradeDateOrContractMonth=expiry,
            strike=strike,
            right=right,
            exchange=exchange,
            currency="USD",  # Add currency to disambiguate
            multiplier="100",  # Ensure the multiplier matches
            # tradingClass="SPXW",  # Specify tradingClass (e.g., SPXW or SPX)
        )

        self.client.qualifyContracts(option_contract)

        self.client.reqMarketDataType(4)
        market_data = self.client.reqMktData(option_contract, '', snapshot=True)
        self.ib.sleep(10)
        print("market data is", market_data)

        premium_price = {
            "bid": market_data.bid,
            "ask": market_data.ask,
            "last": market_data.last,
            "mid": (market_data.bid + market_data.ask) / 2 if market_data.bid and market_data.ask else None
        }
        return premium_price

    async def modify_option_trail_percent(self, trade, new_trailing_percent=0.14):
        modified_order = Order(
            orderId=trade.order.orderId,
            action=trade.order.action,
            totalQuantity=trade.order.totalQuantity,
            orderType='TRAIL',
            tif=trade.order.tif,
            ocaGroup=trade.order.ocaGroup,
            ocaType=trade.order.ocaType,
            parentId=trade.order.parentId,
            displaySize=trade.order.displaySize,
            trailStopPrice=trade.order.trailStopPrice,
            trailingPercent=new_trailing_percent,
            openClose=trade.order.openClose,
            account=trade.order.account,
            clearingIntent=trade.order.clearingIntent,
            dontUseAutoPriceForHedge=trade.order.dontUseAutoPriceForHedge
        )

        # self.client.cancelOrder(trade.order)

        # self.client.sleep(4)

        new_trade = self.client.placeOrder(trade.contract, modified_order)

        self.client.sleep(3)

        return new_trade
