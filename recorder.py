"""
recorder.py  [--recover_trades]
Code for running the trade and position monitor. Only runs on non-holiday weekdays, but at any time of the day.
Can be called from the command line or by calling the recorder() function.

Arguments:
    --recover_trades - If specified, reads trades-<date>.pkl to get today's trades. If this flag is set, recorder will
                        not query ib.trades(). This feature can be used, for example, if for some reason, the day's trades
                        were not processed.

Can be run after a trade ar after closing. After a trade, the recorder() function is called with the read_trade_flag set to
True, in order to record the trades right after they are made, which also allows the value of delta to be recorded on
the observation. The command line job is scheduled to run after the closing day. If run after 4pm, it makes position/portfolio
observations and records options expiring and positions being called away.

Experience suggests that the best time to run recorder.py is at the close of trading, 4pm on trading days. This will allow
it to catch the value of delta for the options, which may not be available later in the day. Also, since trader.py is
recommended to run at 3:00 pm or 3:30 pm, running recorder.py at 4pm should catch the values of delta close to having
executed an option trade.

This module can be scheduled to run at the same time every day, e.g., at closing. Before running in earnest, it checks
to see if today is a weekday and a not a trading holiday. If today is a weekend day or a trading holiday, it simply returns
before doing any actual recording.

TWS must be up and running for this code to run.

An important concept of recorder.py is that both underlying and option activity and positions are saved on a single line.
Thus paired trades are preferrentially set up as COMBO orders, e.g., 'BUY WRITE' and 'ROLLOVER' trades. However,
ROLLOVER trades are recorded as separate lines for the BUY and SELL legs of the ROLLOVER combo order. Separate option
orders for buyback and selling a covered call should be separated by one day or entered as ROLLOVER.

Input files:
    data/activity.xlsx - Activity spreadsheet saved from last run of this module. Note that commented code allows for
        activity-<yesterday-date>.xlsx to be used for this file as an alternative.
    data/positions.xls - Positions spreadsheet saved from last run of this script, defines "yesterday's" state. Note that
        commented code allows for positions-<yesterday-date>.xlsx to be used for this file
    data/trades-<date>.pkl - If --recover_trades is set, reads today's trades from this file.

Output files:
    data/poslog-<date>.pkl - Current positions as read from IB, saved in native format if needed
    data/trades-<date>.pkl - If there are any trades and --read_trades is set, save them in native format
    data/port-<date>.pkl - Current portfolio as read fron IUB, saved in native format
    data/activity.xls - Activity spreadsheet updated with current trades and portfolio updates
    data/positions.xls - Positions spreadsheet updated from this run, row(s) also appear on output activity.xls
    data/activity-<date>.xls - Another copy of activity spreadsheet, but saved with current date in filename
    data/positions-<date>.xls - Another copy of positions spreadsheet, but saved with current date in filename

"""

from zoneinfo import ZoneInfo
from ib_insync import *
from ib_insync import AccountValue
from dataclasses import dataclass
from ibutil import get_delt, is_holiday

import pandas as pd
from datetime import datetime, date, time, timezone, timedelta
#import pytz
#import tzlocal
import pickle
import numpy as np
import argparse



###############################################################################################################
def recorder(ib,read_trades_flag, recover_trades_flag):
    """
    *******************************************************************************************************
    recorder(ib,read_trades_flag, recover_trades_flag)

    Records trading and position activity. Please refer to the docstring for the recorder.py module for a breakout of the \
    input and output dependencies as well as the overall functionality.

    ARGUMENTS:
        ib - Instantiated ib_insync object
        read_trades_flag - If True, recorder() calls ib.trades() to query for today's trades. This is set to True when
            called from trader() but False when called from scheduled end-of-day job.
        recover_trades_flag - If True, recorder() reads todays' trades from trades-<date>.pkl. Used primarily as a per-incident
            recovery mechanism. Set to False both when called from trader.py and from the scheduled end-of-day job. Set to
            false of read_trades_flag is set, irrespecctive of the valiue of the argument parameter.

    """
    print("recorder() called with read_trades_flag=",read_trades_flag,", recover_trades_flag=",recover_trades_flag)
    if(read_trades_flag):
        recover_trades_flag=False  #Can't have both and read_trades tried first

    NEW_YORK = ZoneInfo("America/New_York")

    # Note that we needed to install ib_insync and tzdata packages

    yesterday = datetime.today() - timedelta(days=1)
    yeslog_date = yesterday.strftime('%Y-%m-%d')
    log_date = datetime.today().strftime('%Y-%m-%d')
    log_time = datetime.today().strftime('%H:%M:%S')

    if(is_holiday(log_date,half_day_flag=False)or datetime.today().weekday()>=5):
        print("recorder() only runs on trading days: ",log_date)
        return False
    # yesterday = datetime.today() - timedelta(days=1)
    #yesposfilename = "./data/positions-"+yeslog_date+".xlsx"
    #yesposfilename="./data/positions-2023-05-25.xlsx"
    yesposfilename = "./data/positions.xlsx"
    # Open the previous position file to gather state data
    yespos = pd.read_excel(yesposfilename)
    # yespos.set_index('ticker',inplace=True) # Need this for downstream filtering operations

    #activity_filename = './data/activity-'+yeslog_date+ '.xlsx'
    activity_filename = './data/activity.xlsx'

    # Open activity file - but we only append to it. We do not operate on any data in activity
    activity = pd.read_excel(activity_filename)


    # This was an earlier attempt to combine date and time fields. Decided to keep original structure
    # activity['datetime']=pd.Series(None)
    # activity['datetime'].apply(lambda r: pd.datetime.combine(activity['date'],activity['time']),1)
    # activity['datetime'].apply(time12to24)

    activity['date'] = pd.to_datetime(activity['date']).dt.date

    # We no longer apply this filter because it was interpreting everything as string and changing the log time
    # There is no need to analyzew the activity file; it is for viewing only
    # filt=(activity['time'].apply(type)==str)
    # activity.loc[filt,'time']=time(16,33)
    # activity.loc[filt,'time']=log_time


    values = ib.accountValues()  # Get total account value information to be used in positions, portfolio, activity

    account_value = 0
    # [v for v in ib.accountValues() if v.tag == 'NetLiquidationByCurrency' and v.currency == 'BASE']
    # v: AccountValue
    for v in ib.accountValues():
        if (v.tag == 'NetLiquidationByCurrency' and v.currency == 'BASE'):  # Accounbt value field
            account_value = float(v.value)
            print(v.value)

    # This code can be activited as an example if we need to read in a saved positions pkl file
    # with open('./data/positions.pkl',"rb") as fr1:
    #    posr = pickle.load(fr1)
    #    fr1.close()


    pos = ib.positions()  # pos stores the raw position data from TWS
    positions = {}  # Dictionary of processed position data
    trades = {}

    # Enter loop to set up stub positions dictionary using result from ib.positions()
    for ppp in pos:
        print(ppp.contract.symbol)
        if not (ppp.contract.symbol in positions.keys()):
            positions[ppp.contract.symbol] = {'ticker': ppp.contract.symbol, 'date': log_date, 'time': log_time,
                                              'action': 'OBSERVE', 'position bal': 0}

    # Save the positions log file - may need to change subdirectory to a logging subdirectory
    poslogfilename = "./data/poslog-" + log_date + ".pkl"
    with open(poslogfilename, 'wb') as f1:
        pickle.dump(pos, f1)
        f1.close()

    # This code can be used to load the portfolio data from the log if needed (for debugging etc)
    # with open('./data/portfolio.pkl',"rb") as fr2:
    #    portr = pickle.load(fr2)
    #    fr1.close()

    # Check for trades

    if(recover_trades_flag):
        # This code can be used to read in trading data from the logs, if needed (for debugging, etc.)
        with open('./data/trades-2023-07-20.pkl',"rb") as ft:
            trds = pickle.load(ft)
            ft.close()
    else:
        trds = ib.trades()

    if ((trds is None) or (len(trds) == 0)):
        AAA = "hello world"  # Just a placeholder for possible future logic

    elif(not recover_trades_flag):
        # Save trade log file
        tradeslogfile = './data/trades-' + datetime.today().strftime("%Y-%m-%d") + '.pkl'
        # with open('trades3.pkl','wb') as ff:
        with open(tradeslogfile, 'wb') as ff:
            pickle.dump(trds, ff)
            ff.close()

    if (read_trades_flag or recover_trades_flag) and not ((trds is None) or (len(trds) == 0)):  # Enter major loop to process trades
        for ttt in trds:  # Iterate over all trade objects
            qqq = ttt.contract
            # Build trades dictionary on the fly
            if not (qqq.symbol in trades.keys()):
                trades[qqq.symbol] = {'ticker': qqq.symbol}
            if (type(qqq) == Option):  # This is for option-only trades (fairly rare). BUY-WRITES and ROLLOVERs are handled under the Bag condition
                for fill in ttt.fills:
                    exe = fill.execution
                    option_shares = exe.shares
                    if (exe.side == 'SLD'):
                        option_shares *= -1  # When we sell a call, we record a negative option position
                    exedate = exe.time.astimezone(NEW_YORK).strftime('%Y-%m-%d')  # Times are originally in Greenwich time
                    exetime = exe.time.astimezone(NEW_YORK).strftime('%H:%M')
                    option_trade_price = exe.price  # Except for "CLOSE CC", handled later
                    # Logic to determine "action" field
                    if (exe.side == "SLD"):
                        action = "SELL CC"
                    elif (exe.side == "BOT"):
                        action = "BUY CALL"
                        filt = yespos['ticker'] == qqq.symbol
                        if (sum(filt) == 1):
                            # Check to see if we already had an option for that ticker in yesterday's position
                            if (((type(yespos.loc[filt]['option price'].iloc[0]) == np.float64) and not np.isnan(
                                    yespos.loc[filt]['option price'].iloc[0]))
                                    and ((type(yespos.loc[filt]['price'].iloc[0]) == np.float64) and not np.isnan(
                                        yespos.loc[filt]['price'].iloc[0]))):
                                action = "CLOSE CC"
                                option_trade_price = yespos.loc[filt]['option trade price'].iloc[0]
                    else:
                        action = "UNKNOWN"
                    if 'Underlying size' in trades[qqq.symbol]:
                        # If we've already logged an underlying trade, concatenate the current option action to the extant underlyiung action
                        action = trades[qqq.symbol]['action'] + ' ' + action
                    if 'Commission' in trades[qqq.symbol]:
                        commission = trades[qqq.symbol]['Commission']
                    else:
                        commission = 0
                    commission += fill.commissionReport.commission
                    # Record the transaction in the trades dictionary. Order of fields to be set later
                    d = {"DOE": qqq.lastTradeDateOrContractMonth, "strike": qqq.strike,
                         "option price": exe.price, "option trade price": option_trade_price, "acct bal": account_value,
                         "Option size": option_shares, "P/L option": fill.commissionReport.realizedPNL,
                         "date": exedate, "time": exetime, "action": action, "Commission": commission}
                    trades[qqq.symbol].update(d)
                    print('Option: symbol = ', qqq.symbol, ', action = ', exe.side, ' expiration = ',
                          qqq.lastTradeDateOrContractMonth, ', strike = ', qqq.strike, ', price = ', exe.price, ' ***',
                          qqq.secType)
                    print('Commission = ', fill.commissionReport.commission, ', realizedPNL = ',
                          fill.commissionReport.realizedPNL)
            elif type(qqq) == Stock:  # Stock-only trade, basic buys and sells
                for fill in ttt.fills:
                    exe = fill.execution
                    if (exe.side == 'SLD'):
                        this_shares = -exe.shares
                    else:
                        this_shares = exe.shares
                    if 'Underlying size' in trades[qqq.symbol]:  # We've already logged a stock trade on this symbol
                        # Trades can be broken up, e.g., if going from a long to short position
                        # We group togetehr nall underlying activity in to one trade line, so we sum the shares traded
                        under_shares = trades[qqq.symbol]['Underlying size'] + this_shares
                    else:
                        under_shares = this_shares
                    if 'P/L underlying leg' in trades[qqq.symbol]:
                        # If we've already logged a trade in this underlying, use the P/L underlying leg already logbged
                        PNLunderlyingleg = trades[qqq.symbol]['P/L underlying leg']
                    else:
                        PNLunderlyingleg = 0
                    if 'P/L underlying' in trades[qqq.symbol]:  # Likewise use the P/L underlying already logged
                        PNLunderlying = trades[qqq.symbol]['P/L underlying']
                    else:
                        PNLunderlying = 0
                    if 'Option size' in trades[qqq.symbol]:
                        # If there is already an option trade logged for this symbol, define the action as 'BOT' or 'SLD' concatenated with the option trade
                        action = exe.side + ' ' + trades[qqq.symbol]['action']
                    else:
                        action = exe.side
                    if 'Commission' in trades[qqq.symbol]:
                        # Set the "starter commission" to the earlier logged trade commission. Later we will add fill.commissionReport.commission to the commission
                        commission = trades[qqq.symbol]['Commission']
                    else:
                        commission = 0
                    # Convert time from Greenwich mean time to NY time
                    exedate = exe.time.astimezone(NEW_YORK).strftime('%Y-%m-%d')
                    exetime = exe.time.astimezone(NEW_YORK).strftime('%H:%M')
                    if (exe.side == 'BOT'):  # When we buy a stock, we record the trade price and leg price
                        filt = yespos['ticker'] == qqq.symbol
                        if (sum(filt) == 0):  # We presume to open a new positionj
                            leg_price = exe.price
                            trade_price = exe.price
                        else:  # in this case, there was already a position in this symbol yesterday
                            prev_underlying_size_series = yespos.loc[filt, 'Underlying size']
                            if (under_shares == - prev_underlying_size_series.iloc[0]):  # Closing a short
                                leg_price_series = yespos.loc[filt, 'leg price']
                                leg_price = max(leg_price_series)
                                trade_price_series = yespos.loc[filt, 'trade price']
                                trade_price = max(trade_price_series)  # Note the trade price is the entry price
                            else:  # Some other BOT action, reset the leg price
                                leg_price = exe.price
                                trade_price = exe.price
                    else:  # For other stock transactions like sell, we use the state data in yesterday's position file
                        filt = yespos['ticker'] == qqq.symbol
                        if (sum(filt) >= 1):  # We presume to close a position
                            leg_price_series = yespos.loc[filt, 'leg price']
                            leg_price = max(leg_price_series)
                            trade_price_series = yespos.loc[filt, 'trade price']
                            trade_price = max(trade_price_series)  # Note the trade price is the entry price
                        else:  # Assume we are entering a short positiom - Note this should be prevented in the order code
                            leg_price = exe.price
                            trade_price = exe.price
                    # Prevent overwrite of PNL underlying leg
                    PNLunderlyingleg += (exe.price - leg_price) * exe.shares
                    PNLunderlying += fill.commissionReport.realizedPNL
                    commission += fill.commissionReport.commission
                    # Add a row to the dictionary. Note we don't care about the order of the columns at this point.
                    d = {"price": exe.price, "trade price": trade_price,
                         "P/L underlying": PNLunderlying, "Underlying size": under_shares, "action": action,
                         "leg price": leg_price, "P/L underlying leg": PNLunderlyingleg, "acct bal": account_value,
                         "time": exe.time, "position bal": under_shares * exe.price, "Commission": commission,
                         "date": exedate, "time": exetime}
                    trades[qqq.symbol].update(d)  # Add this trade event to the trades dictionaruy
                    print('Stock: symbol = ', qqq.symbol, ', action = ', exe.side, ' price = ', exe.price, ', shares = ',
                          exe.shares)
                    print('Commission = ', fill.commissionReport.commission, ', realizedPNL = ',
                          fill.commissionReport.realizedPNL)
            elif type(qqq) == Bag:  # Supported bag trades include BUY WRITE and ROLLOVER
                action = 'Unknown'
                # The most common Bag transactions are ROLLOVER and BUY WRITE. Check the logic for these actions
                if (((qqq.comboLegs[0].ratio == 1) and (qqq.comboLegs[1].ratio == 1)) and (
                        qqq.comboLegs[0].action != qqq.comboLegs[1].action)):
                    action = 'ROLLOVER'
                elif (((qqq.comboLegs[0].action == 'BUY') and (qqq.comboLegs[0].ratio == 100)) or (
                        (qqq.comboLegs[1].action == 'BUY') and (qqq.comboLegs[1].ratio == 100))):
                    action = 'BUY WRITE'
                commission = 0  # For BUY WRITE we sum the commission on both legs of trade
                position_bal = 0  # Likewise fir BUY WRITE we sum the legs of position balancew\
                for fill in ttt.fills:  # Iterate over the legs of the Bag
                    con = fill.contract
                    exe = fill.execution
                    exedate = exe.time.astimezone(NEW_YORK).strftime('%Y-%m-%d')
                    exetime = exe.time.astimezone(NEW_YORK).strftime('%H:%M')
                    if type(con) == Option:
                        mysymbol = qqq.symbol
                        option_trade_price = exe.price
                        if action == 'BUY WRITE':
                            commission += fill.commissionReport.commission  # Sum both legs
                        else:  # Say, for rollover
                            commission = fill.commissionReport.commission  # Commissions reported separately for rollobers on activity report
                        option_shares = exe.shares
                        if (exe.side == 'SLD'):
                            option_shares *= -1  # A single option contract will be reported as -1, corresponding to 100 shgares of underlying

                            if (action.startswith('ROLLOVER')):
                                action = 'ROLLOVER WRITE'  # Clarify the action for the sell leg of the rollover

                                mysymbol = qqq.symbol + '*'  # Index rollover writes with asterisk after symbol
                                if not (mysymbol in trades.keys()):
                                    trades[mysymbol] = {'ticker': qqq.symbol}
                        else:
                            if action.startswith('ROLLOVER'):
                                action = 'ROLLOVER CLOSE'
                                filt = yespos['ticker'] == qqq.symbol
                                if (sum(filt) == 1):
                                    option_trade_price = yespos.loc[filt]['option trade price'].iloc[0]

                        # For rollover trades, position balance recorded in activity will reflect only the option balance
                        position_bal += exe.price * option_shares * int(fill.contract.multiplier)
                        d = {"DOE": con.lastTradeDateOrContractMonth, "strike": con.strike,
                             "option price": exe.price, "option trade price": option_trade_price, "date": exedate,
                             "time": exetime,
                             "Option size": option_shares, "P/L option": fill.commissionReport.realizedPNL,
                             "acct bal": account_value,
                             "Commission": commission, "position bal": position_bal, "action": action}
                        trades[mysymbol].update(d)
                        print('Option: symbol = ', con.symbol, ', action = ', action, ' expiration = ',
                              con.lastTradeDateOrContractMonth, ', strike = ', con.strike, ', price = ', exe.price, ' ***',
                              con.secType)
                        print('Commission = ', fill.commissionReport.commission, ', realizedPNL = ',
                              fill.commissionReport.realizedPNL)
                    elif type(con) == Stock:  # This will typically be the underlying in a BUY WRITE
                        commission += fill.commissionReport.commission
                        position_bal += exe.shares * exe.price  # Add the underlying leg balance of the bag
                        if (exe.side == 'BOT'):  # In a Buy write we set the trade price and leg price as current price
                            leg_price = exe.price
                            trade_price = exe.price
                        else:
                            filt = yespos['ticker'] == con.symbol
                            leg_price_series = yespos.loc[filt, 'leg price']
                            leg_price = max(leg_price_series)
                            trade_price_series = yespos.loc[filt, 'trade price']
                            trade_price = max(trade_price_series)
                        PNLunderlyingleg = (exe.price - leg_price) * exe.shares
                        d = {"price": exe.price, "trade price": trade_price, "date": exedate, "time": exetime,
                             "leg price": leg_price,
                             "P/L underlying": fill.commissionReport.realizedPNL, "Underlying size": exe.shares,
                             "P/L underlying leg": PNLunderlyingleg, "action": action,
                             "position bal": position_bal, "acct bal": account_value,
                             "Commission": commission}
                        trades[qqq.symbol].update(d)
                        print('Stock: symbol = ', con.symbol, ', action = ', exe.side, ' price = ', exe.price,
                              ', shares = ', exe.shares)
                        print('Commission = ', fill.commissionReport.commission, ', realizedPNL = ',
                              fill.commissionReport.realizedPNL)
                    # exeqqq=exe.Contract
                    # if type(exeqqq)==Option:
                    #    exeexe=exe.execution

            else:
                print('Something else')

    # Create a dataframe from the trades dictionary
    trades_df = pd.DataFrame.from_dict(trades, orient='index')
    # Define the order of the column headers as in the spreadsheet
    columnTitles = ['date', 'time', 'action', 'ticker', 'price', 'trade price', 'leg price', 'strike', 'DOE',
                    'option price', 'option trade price',
                    'Commission', 'Option size', 'Underlying size', 'position bal', 'acct bal', 'P/L underlying',
                    'P/L underlying leg', 'P/L option', 'delta']
    trades_df = trades_df.reindex(columns=columnTitles)  # Reorder the columns to reflect the spreadsheet

    activity = activity.append(trades_df, ignore_index=True)  # Append the trades to the activity

    port = ib.portfolio()  # Gather more detailed information about held positions

    # Save the portfolio log file
    portlogfilename = './data/port-' + datetime.today().strftime("%Y-%m-%d") + '.pkl'
    with open(portlogfilename, 'wb') as f2:
        pickle.dump(port, f2)
        f2.close()

    first = True  # The first flag is used to mark if we are seeing the first instance of the symnol in the portfolio
    prevticker = 'not a real ticker'  # Just a dummy initial value
    for ppp in port:  # Iterate over the portfolio - Note does not store bags, each leg is a separate record
        if ppp.contract.symbol != prevticker:
            first = True
            action = "OBSERVE"  # Default but may get changed if option expiring or called away
        if first:
            rollover_flag = False
            sell_CC_flag = False
            close_CC_flag = False
            # Chrck to see if symbol is in the trades file
            filt = trades_df['ticker'] == ppp.contract.symbol
            if (sum(filt) == 1):  # One-sided trade of ppp.contract.symbol
                # Check to see if symbol is in the state filew
                filt2 = yespos['ticker'] == ppp.contract.symbol
                if (trades_df.loc[ppp.contract.symbol]['action'] == 'SELL CC'):  # One sided sell of covered call
                    if (sum(filt2) == 1):  # We had a position presumably long at yesterday close
                        sell_CC_flag = True
                        trade_price_series = yespos.loc[filt2]['trade price']
                        trade_price = max(
                            trade_price_series)  # Note the underlying trade price is intended to be the entry price
                        # We don't set the leg_price here for SELL CC; that is done on the STOCK branch below
                        # leg_price_series = yespos.loc[filt2]['leg price']
                        # leg_price = max(leg_price_series) + 99999 # We assign this later
                        # The option trade price is the price at entry, i.e., at selling the CC
                        option_trade_price = trades_df.loc[ppp.contract.symbol]['option trade price']
                    elif (sum(filt2 == 0)):  # No trade of ppp.contract.symbol in yesterday close\\
                        trade_price = 0
                        option_trade_price = trades_df.loc[ppp.contract.symbol]['option trade price']
                        action = "UNMATCHED SELL CC"  # We should not see this if properly executed
                    else:
                        action = "ERROR"
                elif (trades_df.loc[ppp.contract.symbol][
                          'action'] == 'CLOSE CC'):  # Check if we had one-sided close of CC in trades
                    if (sum(filt2) == 1):  # We had a position presumably long at yesterday close
                        close_CC_flag = True
                        trade_price_series = yespos.loc[filt2]['trade price']
                        trade_price = trade_price_series.iloc[0]
                        # We don't set the leg_price here for SELL CC; that is done on the STOCK branch below
                        # leg_price_series = yespos.loc[filt2]['leg price']
                        # leg_price = max(leg_price_series) + 99999 # We assign this later
                        option_trade_price = trades_df.loc[ppp.contract.symbol]['option trade price']
                    elif (sum(filt2 == 0)):  # No trade of ppp.contract.symbol in yesterday close - we should not see this if properly executed
                        trade_price = 0
                        leg_price = 0
                        option_trade_price = trades_df.loc[ppp.contract.symbol]['option trade price']
                        action = "UNMATCHED CLOSE CC"
                    else:
                        action = "ERROR"
                # else: #includes BUY WRITE and other trades
                elif (trades_df.loc[ppp.contract.symbol]['action'] == 'BUY WRITE') or (
                        trades_df.loc[ppp.contract.symbol]['action'].startswith('BOT')):
                    trade_price_series = trades_df.loc[filt, 'trade price']
                    trade_price = trade_price_series[ppp.contract.symbol]
                    leg_price_series = trades_df.loc[filt, 'leg price']
                    leg_price = leg_price_series[ppp.contract.symbol]
                    option_trade_price_series = trades_df.loc[filt, 'option trade price']
                    option_trade_price = option_trade_price_series.iloc[0]
                elif (trades_df.loc[ppp.contract.symbol][
                          'action'] == 'SLD'):  # THis would be the case if we sold the long but left the CC open
                    if (sum(filt2) == 1):  # We had a position presumably long at yesterday close
                        print('Warning: SLD order but a position still held, possible naked call')
                        trade_price_series = yespos.loc[filt2]['trade price']
                        trade_price = max(trade_price_series)
                        leg_price_series = trades_df.loc[filt, 'leg price']
                        leg_price = leg_price_series[ppp.contract.symbol]
                        option_trade_price_series = yespos.loc[filt2, 'option trade price']
                        option_trade_price = option_trade_price_series.iloc[0]
            elif (sum(filt) == 0):  # Symbol was not part of trade, need to get from yesterday
                filt2 = yespos['ticker'] == ppp.contract.symbol
                if (sum(filt2) == 1):  # The symbol was in the state file
                    trade_price_series = yespos.loc[filt2, 'trade price']
                    trade_price = max(trade_price_series)  # Get the value out, could be indexed 0 or 1
                    leg_price_series = yespos.loc[filt2, 'leg price']
                    leg_price = max(leg_price_series)  # Get the value out
                    option_trade_price_series = yespos.loc[filt2, 'option trade price']
                    option_trade_price = max(option_trade_price_series)
                elif (sum(filt2) == 0):
                    trade_price = 0
                    leg_price = 0
                    option_trade_price = 0

                else:
                    print("Error: multiple rows of " + ppp.contract.symbol + " in yesterday's positions")
                    trade_price = -9999
                    leg_price = -9999
            elif (sum(filt) == 2):  # 2 trade lines for a symbol indicates rollover
                filt2 = yespos['ticker'] == ppp.contract.symbol
                trade_price_series = yespos.loc[filt2, 'trade price']
                trade_price = max(trade_price_series)  # Get the value out of the series
                rollover_flag = True
                option_trade_price_series = trades_df.loc[filt, 'option trade price']
                option_trade_price = option_trade_price_series[ppp.contract.symbol + '*']
            else:
                print("Error: multiple rows of " + ppp.contract.symbol + " in trades data frame")
                trade_price = -9999
                leg_price = -9999
            prevticker = ppp.contract.symbol
            first = False
        if type(ppp.contract) == Stock:
            if rollover_flag or sell_CC_flag or close_CC_flag:
                leg_price = ppp.marketPrice
            bal = ppp.marketValue + positions[ppp.contract.symbol][
                'position bal']  # If option called first will have value in 'position bal'
            d = {"price": ppp.marketPrice, "trade price": trade_price, "leg price": leg_price, "Commision": 0,
                 "Underlying size": ppp.position, "position bal": bal,
                 "acct bal": account_value, "action": action,
                 "P/L underlying": ppp.unrealizedPNL, "P/L underlying leg": ppp.position * (ppp.marketPrice - leg_price)}
            positions[ppp.contract.symbol].update(d)
        elif type(ppp.contract) == Option:
            delta = get_delt(ib, ppp.contract.symbol, ppp.contract.lastTradeDateOrContractMonth, ppp.contract.strike)
            # delta = 0
            # Restore call to get_delt during regular hours
            bal = positions[ppp.contract.symbol]['position bal']  # If stock called first will have value in 'position bal'
            bal += ppp.marketValue

            d = {"DOE": ppp.contract.lastTradeDateOrContractMonth, "strike": ppp.contract.strike,
                 "option price": ppp.marketPrice,
                 "option trade price": option_trade_price, "position bal": bal, "action": action,
                 "Option size": ppp.position, "P/L option": ppp.unrealizedPNL, "delta": delta}
            positions[ppp.contract.symbol].update(d)
    # port_df=util.df(port)

    # Next, mock up read of positions file (would have been better to save portfolio class) in order to put together logic to determine BUY WRITE or CALLED AWAY

    port_df = pd.DataFrame.from_dict(positions, orient='index')
    columnTitles = ['date', 'time', 'action', 'ticker', 'price', 'trade price', 'leg price', 'strike', 'DOE',
                    'option price', 'option trade price',
                    'Commission', 'Option size', 'Underlying size', 'position bal', 'acct bal', 'P/L underlying',
                    'P/L underlying leg', 'P/L option', 'delta']
    port_df = port_df.reindex(columns=columnTitles)


    if(datetime.today().hour >= 16):   #Only make these adjustments if called after trading hours
        port_df['DOE'] = port_df['DOE'].astype(str)
        for i in range(len(port_df)):
            # for index,row in port_df.iterrows():
            if (port_df.iloc[i]['DOE'] != 'nan'):
                doe = datetime.strptime(port_df.iloc[i]['DOE'], "%Y%m%d")
                # Logic to determine if option is expiring or position is being called away
                if (doe.date() <= datetime.today().date()):
                    if (port_df.iloc[i]['strike'] <= port_df.iloc[i]['price']):
                        port_df.iloc[i, port_df.columns.get_loc('action')] = "Called Away"
                    else:
                        port_df.iloc[i, port_df.columns.get_loc('action')] = 'Expire CC'
    activity = activity.append(port_df, ignore_index=True)
    posfilename = "./data/positions-" + log_date + ".xlsx"
    port_df.to_excel(posfilename, index=False)
    posfilename2 = "./data/positions.xlsx"
    port_df.to_excel(posfilename2, index=False)
    activityfilename = "./data/activity-" + log_date + ".xlsx"
    activity.to_excel(activityfilename, index=False)

    # print(values)
    # print(pos)
    print(port_df)

    activity.to_excel("./data/activity.xlsx", index=False)

############################################################################################################
def main():
    """
    main()
    Driver and entry point for command-line invocation of recorder.py

    See docstring for recorder.py module including commmand-line arguments
    main() processes command-line arguments, instantiates the ib object, established connection, calls recorder(),
    and disconnects.
    """
    global ib

    parser = argparse.ArgumentParser()
#    parser.add_argument("--read_trades",action="store_true",help="Call ib.trades() to record today\'s trades")
    parser.add_argument("--recover_trades",action="store_true",help="Recover today\'s trades from saved trades PKL object")
    args = parser.parse_args()
#    if args.read_trades:
#        read_trades_flag = True
#    else:
#       read_trades_flag = False
    if args.recover_trades:
        recover_trades_flag = True
#        read_trades_flag = False
    else:
        recover_trades_flag = False
#        read_trades_flag = True

    read_trades_flag = not recover_trades_flag

    ib = IB()

    # use this instead for IB Gateway
    # ib.connect('127.0.0.1', 7497, clientId=1)

    # us this for TWS (Workstation)
    ib.connect('127.0.0.1', 7497, clientId=20)
    ib.reqMarketDataType(1)  # avoid market permission problems by requesting delayed data
#    recorder(ib,True, False)
#    recorder(ib,False,True)
    recorder(ib, read_trades_flag, recover_trades_flag) #In the absense of command line parameters, do not check for new trades
    ib.disconnect()


if __name__ == "__main__":
         main()