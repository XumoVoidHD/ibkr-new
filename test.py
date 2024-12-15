import asyncio
from ib_insync import *
import datetime as dt
import pytz
from api_ib_tws_v2 import IBTWSAPI
import nest_asyncio

nest_asyncio.apply()


async def check_tws_connection():
    """Check if TWS is running and accessible"""
    # try:
    ib = IB()
    await asyncio.wait_for(
        ib.connectAsync(
            host='127.0.0.1',
            port=7497,
            clientId=1,
            timeout=5
        ),
        timeout=5
    )
    # return True
    # except Exception as e:
    #     return False
    # finally:
    #     if ib.isConnected():
    #         ib.disconnect()


# asyncio.run(check_tws_connection())


async def test_module():
    # Initialize API with credentials
    creds = {
        "host": '127.0.0.1',  # Local host
        "port": 7497,  # Paper trading port
        "client_id": 12
    }

    print("\n=== Starting IBTWSAPI Test ===")

    # Create API instance
    api = IBTWSAPI(creds=creds)

    # Test 1: Connect
    print("\n1. Testing connection...")
    connected = await api.connect()
    print(f"Connection status: {connected}")

    # Test 2: Check connection status
    print("\n2. Testing is_connected...")
    is_connected = api.is_connected()
    print(f"Is connected: {is_connected}")

    # Test 3: Get account info
    print("\n3. Testing get_account_info...")
    account_info = api.get_account_info()
    print(f"Account info: {account_info}")

    # # Test 4: Get account balance
    # print("\n4. Testing get_account_balance...")
    # balance = api.get_account_balance()
    # print(f"Account balance: {balance}")
    #
    # # Test 5: Get positions
    # print("\n5. Testing get_positions...")
    # positions = await api.get_positions()
    # print(f"Current positions: {positions}")
    #
    # # Test 6: Get contract info for a stock
    # print("\n6. Testing get_contract_info...")
    # contract_info = await api.get_contract_info(
    #     contract="stocks",
    #     symbol="AAPL",
    #     exchange="SMART"
    # )
    # print(f"Contract info for AAPL: {contract_info}")
    #
    # # Test 7: Get expiries and strikes
    # print("\n7. Testing get_expiries_and_strikes...")
    # expiries_strikes = await api.get_expiries_and_strikes(
    #     technology="options",
    #     ticker="AAPL"
    # )
    # print(f"Expiries and strikes for AAPL options: {expiries_strikes}")
    #
    # # Test 8: Get candle data
    # print("\n8. Testing get_candle_data...")
    # candles = await api.get_candle_data(
    #     contract="stocks",
    #     symbol="AAPL",
    #     timeframe="5m",
    #     period="1d",
    #     exchange="SMART"
    # )
    # print(f"Candle data:\n{candles.head()}")

    # # # Test 9: Get option chain
    # print("\n9. Testing get_option_chain...")
    # # Get the first expiry date from the expiries_strikes
    # if expiries_strikes:
    #     first_expiry = list(expiries_strikes.keys())[0]
    #     exp_date = first_expiry.strftime("%Y%m%d")
    #     option_chain = await api.get_option_chain(
    #         symbol="AAPL",
    #         exp_list=[exp_date]
    #     )
    #     print(f"Option chain for first expiry: {option_chain}")

    # Test 10: Place a market order (commented out for safety)
    """
    print("\n10. Testing place_order...")
    order_info = api.place_order(
        contract="stocks",
        symbol="AAPL",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        exchange="SMART"
    )
    print(f"Order info: {order_info}")
    """

    # Test 11: Place a bracket order (commented out for safety)
    """
    print("\n11. Testing place_bracket_order...")
    current_price = candles.iloc[-1]['close']
    bracket_order = api.place_bracket_order(
        contract="stocks",
        symbol="AAPL",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        exchange="SMART",
        stoploss=current_price * 0.99,
        targetprofit=current_price * 1.01
    )
    print(f"Bracket order info: {bracket_order}")
    """

    # # Test 12: Query orders
    # print("\n12. Testing query_order...")
    # # Use a sample order ID - replace with actual order ID if needed
    # order_info = api.query_order(order_id=1)
    # print(f"Order query result: {order_info}")

    print("\n=== Test Complete ===")

    # except Exception as e:
    #     print(f"\nError during testing: {str(e)}")
    # finally:
    #     if api and api.client.isConnected():
    # api.client.disconnect()
    # print("\nDisconnected from TWS")


if __name__ == "__main__":
    asyncio.run(test_module())