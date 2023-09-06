"""
*************************************************************************************************
trader.py <manifest_filename>
Runs the real-time trades as specified in the <manifest_filename>. Only runs during active trading hours,
Monday - Friday, 9:30am - 4:00pm, on weekdays except for trading holidays and days that the market closes
early.

arguments:
    <manifest_filename> - .xlsx input file with trade specifications, defaults to manifest.xlsx

Other inputs:
    ./data/holidays.txt - List of market holidays in the current year
    ./data/half_days.txt - List of days in which the market closes at 1pm in the current year.

Manifest file syntax:
    <yyyy-mm-dd> | <action> | <ticker> | <expiration>

    <yyyy-mm-dd> specifies the date for the command to be run. For action AUTO, this field is left blank. trader.py
    will only act on trades for the current date or AUTO trades. Past and future dates lists here will result in no
    action.

    <action> can be any of the following commands:
        BUY - buy <num> shares of <ticker>. No expiration specified.
        SELL - see <num> shares of <ticker> No expiration specified.
        BUY WRITE - buy 100*<num> shares of <ticker and sell <num> covered calls at strike corresponding to delta=0.4 and
            with <expiration> date 'yyyymmdd'. Caution, assumes <expiration> date has valid contracts. First makes sure that
            sufficient available cash is available to avoid leverage
        SELL CC - sell <num> covered calls of <ticker> at strike corresponding to delta=0.4 with <expiration> date 'yyyymmdd'.
            First makes sure that there are at least 100*<num> shares of the stock without a covered call.
        BUYBACK CC - Buys back <num> covered calls of <ticker>. First makes sure that at least <num> covered calls have been sold
            of the stock. No need to specify <expiration>, this action finds the contract
        CLOSE - Close the entire position of <ticker>, buying back any calls and selling the stock to vacate the position entirely.
            No expiration specified.
        ROLLOVER - If <ticker>'s covered call has reached expiration date, and the call is in the money, executes a rollover, buying
            back the about-to-expire cal at a loss and selling a new covered call with expiration at the next day of week as specified
            buy <expiration>, e.g., 'Monday','Tuesday', etc.
        AUTO - Keep refreshing <ticker>'s covered calls, assuming weekly calls sold at delta=0.4 strike. When expiration date is reached,
            issues a rollover if the call is in the money, with expiration date specified by day of the weel in the <expieration> field,
            e.g., 'Monday','Tuesday', etc.. If the call is out of the money, lets it expire and sells a new call at new expiration date
            on the day after the old option expires.

NOTE: It is recommended to schedule a job to run this module at 3pm or 3:30pm every day. On non-trading days or days when the
market closes early, this module will simply return before doing any actual trading. Experience suggests that the best time for
this module to run is 3pm or 3:30pm, since AUTO orders are checked for being in the money and, if so, ROLLOVER orders issued.
For that reason, these trades should not take place too far from closing. It is also recommended to schedule a separate job
to run reporter.py at the close of trading, since this module no longer calls reporter().

"""
from zoneinfo import ZoneInfo
from ib_insync import *
from ib_insync import AccountValue
from dataclasses import dataclass
from ibutil import get_delt,is_holiday
from buywrite import buy_write
from order import buy_stock, sell_stock, close_position
from options import covered_call, buyback_call
from rollover import rollover
from recorder import recorder

import pandas as pd
from datetime import datetime, date, time, timezone, timedelta
#import pytz
#import tzlocal
import pickle
import numpy as np
import sys

##############################################################################################################
def main():
    global ib
    #Define a dictionary for the "expiration" manifest field for AUTO actions, see below
    #The keys should match to the lowercase casting of the first three digits of the day-of-week
    #The values match to the datetime dayofweek() value Monday=0, Sunday=6
    weekday_dict={"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}

    ib = IB()

    # us this for TWS (Workstation)
    ib.connect('127.0.0.1', 7497, clientId=10)
    ib.reqMarketDataType(1)  # Request real-time data


    #The manifest file can be specified as a command line argument or defaults to "manifest.xlsx"
    if(len(sys.argv)>1):
        manifest_filename = sys.argv[1]
    else:
        manifest_filename = "manifest.xlsx"
    todaystr = datetime.today().strftime('%Y-%m-%d')

    if(is_holiday(todaystr) or (datetime.today().weekday() > 4) or (datetime.today().hour>=16) or (datetime.today().hour<9)\
            or ((datetime.today().hour==9)and(datetime.today().minute<30))):
        #Do not proceed unless within trading hours
        print("trader.py cannot run outside of trading hours: "+todaystr+" "+datetime.today().strftime('%H:%M:%S'))
        return False

    manifest_path = "./data/"+manifest_filename
    manifest = pd.read_excel(manifest_path,converters={'expiration':str})
    #manifest['expiration']=manifest.to_string(columns=['expiration'])
    #manifest['date'] = pd.to_datetime(manifest['date']).dt.date

    auto_orders =  manifest[manifest['action']=='AUTO']
    #Handle AUTO orders first. Automatic rollovers and writing of expired covered calls for weekly index ETF calls
    for n in range(0,len(auto_orders)):
        mystock=auto_orders.iloc[n]['ticker']
        mycalls = auto_orders.iloc[n]['num']
        dayofweek = auto_orders.iloc[n]['expiration'] #The 'expiration' field is used for weekly expiration day in AUTO orders
        dayofweek = dayofweek[0:min(len(dayofweek), 3)]
        dayofweek = dayofweek.lower()
        daynum = weekday_dict[dayofweek]  #e.g., this and previous 2 lines convert 'Friday' to 4
        day_of_week = auto_orders.iloc[n]['expiration']
        #Find the next expiration after today that matched the day of week
        ndaysahead=1
        while(datetime.today() + timedelta(ndaysahead)).weekday()!=daynum:
            ndaysahead+=1
        expr_date = datetime.today() + timedelta(ndaysahead)
        myexpiration = expr_date.strftime('%Y-%m-%d')   # Tidy format for holidays.txt and half_days.txt
        while(is_holiday(myexpiration) ):#If the exppiration date is a holiday or half-day, move it forward one week
            expr_date = expr_date +  timedelta(7)
            myexpiration = expr_date.strftime('%Y-%m-%d')  # Tidy format for holidays.txt and half_days.txt
        myexpiration = expr_date.strftime('%Y%m%d')    #Reformat for options expiration

        rollstatus = covered_call(ib,mystock,mycalls,myexpiration,True)  #If auto position has no option, write a covered call
        if (not rollstatus): #If we didnt just write a covered call:
            #The rollover function checks to see if the option is expiring today and is in the money. If so, it executes a rollover
            #   for the new expiration dsate, 'myexpiration.
            # We pass in auto_flag = True and force_flag = False
            rollstatus = rollover(ib,mystock,mycalls,myexpiration, True, False)

    #Filter on the orders with date == today. Note that we only act on AUTO orders and date==today orders
    today_orders = manifest[manifest['date']==datetime.today().strftime('%Y-%m-%d')]
    for n in range(0,len(today_orders)): #Identify the order by action, gather parameteres, and call the appropriate trading function
        #Note that the arguments in the manifest command are interpreted slightly differently for the different actions
        mystock = today_orders.iloc[n]['ticker']
        if(today_orders.iloc[n]['action']=='BUY WRITE'):
            mycalls = today_orders.iloc[n]['num']
            #myexpiration_date = datetime.strptime(today_orders.iloc[n]['expiration'],"%Y-%m-%d")
            #myexpiration = myexpiration.strftime(%Y%m%d)
            myexpiration = today_orders.iloc[n]['expiration']
            status=buy_write(ib, mystock, mycalls, myexpiration)
        elif(today_orders.iloc[n]['action']=='BUY'):
            myshares = today_orders.iloc[n]['num']
            status = buy_stock(ib,mystock,myshares)
        elif(today_orders.iloc[n]['action']=='SELL'):
            myshares = today_orders.iloc[n]['num']
            status = sell_stock(ib,mystock,myshares)
        elif(today_orders.iloc[n]['action']=='CLOSE'):
            myshares = today_orders.iloc[n]['num']
            status = close_position(ib,mystock)
        elif(today_orders.iloc[n]['action']=='BUYBACK CC'):
            mycalls = today_orders.iloc[n]['num']
            status = buyback_call(ib,mystock,mycalls)
        elif(today_orders.iloc[n]['action']=='SELL CC'):
            mycalls = today_orders.iloc[n]['num']
            myexpiration = today_orders.iloc[n]['expiration']
            status = covered_call(ib, mystock, mycalls, myexpiration, False)
        elif (today_orders.iloc[n]['action'] == 'ROLLOVER'):
            mycalls = today_orders.iloc[n]['num']
            myexpiration = today_orders.iloc[n]['expiration']
            #Here we force the rollover regardless of current strike vs. price: auto_flag is False, force_flag is True
            status = rollover(ib,mystock,mycalls,myexpiration,False,True)
    for order in ib.orders():
        print("== this is one of my orders ==")
        print(order)
    for trade in ib.trades():
        print("== this is one of my trades =")
        print(trade)
    #ib.sleep(60)   #Give trades time to settle down before calling recorder
    trds = ib.trades()

    if (not((trds is None) or (len(trds) == 0))):
        # Save trade log file even though this is also done in recorder
        tradeslogfile = './data/trades-' + datetime.today().strftime("%Y-%m-%d") + '.pkl'
        # with open('trades3.pkl','wb') as ff:
        with open(tradeslogfile, 'wb') as ff:
            pickle.dump(trds, ff)
            ff.close()
        # Due to problems recording some trades right after executing the trades, the calling of recorder at the end
        # of this function has been disabled. It is now recommended to schedule a separate job for recorder.py at the
        # close of trading.
        # recorder(ib, True, False)

#################################################################################################################
if __name__ == "__main__":
         main()