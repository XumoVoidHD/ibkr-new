# Default Values
port = 7497
host = "127.0.0.1"
data_type = 4
instrument = "SPX"
exchange = "CBOE"
currency = "USD"
close_positions = True
enable_logging = False
WEBHOOK_URL = "https://discord.com/api/webhooks/1338550862922125382/ngLa-LmVaolmdMDeNV4f4jTEhzhCJwvZXsSrpHiYcZmWIhYEQ9ef4elRQB0Kf1PmYG5B"

# Changeable Values
date = "20250224"                   # Date of contract (YYYY-MM-DD)
number_of_re_entry = 1              # Specifies the number of re-entries allowed
OTM_CALL_HEDGE = 5                # How far away the call hedge is (10 means that its $50 away from current price)
OTM_PUT_HEDGE = 5                 # How far away the put hedge is (10 means that its $50 away from current price)
ATM_CALL = 1                        # How far away call position is (2 means that its $10 away from current price)
ATM_PUT = 1                         # How far away put position is (2 means that its $10 away from current price)
call_sl = 30                        # From where the call stop loss should start from (15 here means 15% of entry price)
call_entry_price_changes_by = 15     # What % should call entry premium price should change by to update the trailing %
call_change_sl_by = 5               # What % of entry price should call sl change when trailing stop loss updates
put_sl = 30                         # From where the put stop loss should start from (15 here means 15% of entry price)
put_entry_price_changes_by = 15      # What % should put entry premium price should change by to update the trailing %
put_change_sl_by = 5                # What % of entry price should put sl change when trailing stop loss updates
conversion_time = 10                # Deprecated (No use)
entry_hour = 9                      # Entry time in hours
entry_minute = 46                   # Entry time in minutes
entry_second = 55                    # Entry time in seconds
exit_hour = 13                     # Exit time in hours
exit_minute = 25                    # Exit time in minutes
exit_second = 00                     # Exit time in seconds
call_hedge_quantity = 1             # Quantity for call hedge
put_hedge_quantity = 1              # Quantity for put hedge
call_position = 1                   # Quantity for call position
put_position = 1                    # Quantity for put position
