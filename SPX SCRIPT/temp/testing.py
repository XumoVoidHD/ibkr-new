from ib_insync import *

# Create a connection to IB
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # Use 7496 for Paper Trading

# Define the option contract
contract = Option(
    symbol='SPX',        # Using SPXW for weekly options
    lastTradeDateOrContractMonth='20241224',
    strike=5875.0,
    right='C',           # 'C' for Call option
    multiplier='100',
    exchange='CBOE',
    currency='USD',
    # localSymbol='SPXW  241224C05875000'  # Format: SPXW YYMMDD C/P STRIKE000
)
print(contract)
# Create a market order
order = MarketOrder('BUY', 1)  # Buying 1 contract

# Submit the order
trade = ib.placeOrder(contract, order)

# Wait for order to fill
while not trade.isDone():
    ib.sleep(1)

print(f"Order status: {trade.orderStatus.status}")
print(f"Filled at: {trade.orderStatus.avgFillPrice}")

# Disconnect
ib.disconnect()