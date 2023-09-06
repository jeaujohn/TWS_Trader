"""
ibutil.py - Utilities to be used in conjunction with the TWS API/ib_insync option trader.

This module contains the following functions:

    get_delt(ib, sym, exp, str) - Returns the value of delta for the specified option contract

    is_holiday(datestr, half_day_flag) - Determines if the datestr lands on o trading holiday or half-day.\

For details, see the docstring of the spoecific functions
"""

from typing import List

from ib_insync import *
from datetime import datetime, timedelta

#######################################################################################################################

def get_delt(ib,sym,exp,str):
    """
    function get_delt(ib, sym, exp, str) - Returns the value of delta for the specified option call

    Input parameters:
        ib - ib_insync object, assumed to already be connected
        sym - String specifying the symbol of the stock of interest
        exp - Expiration date string in format 'yyyymmdd'
        str - Strike price

    Return value - If the expiration date and strike price are legitimate, returns the value of delta for the call. If
    the specification is legitimate but the value of delta is somehow not available from the system, returns -99. If
    expiration and str do not specify a valid call, returns -999.
    """
    print('Hello World')
    expirations=[exp]
    strikes=[str]
    cont=[Option(sym,expiration,strike,'C','SMART',tradingClass=sym) for expiration in expirations for strike in strikes]

    cont=ib.qualifyContracts(*cont)
    tick=ib.reqTickers(*cont)
    try:
        if tick[0].modelGreeks:
            delta = tick[0].modelGreeks.delta
        else:
            delta = -99
    except:
        delta = -999
    return delta


####################################################################################################################

def is_holiday(datestr,half_day_flag=True):
    """
    function is_holiday(datestr, half_day_flag) - Returns True if specified date string is a trading holiday, false if not.

    Arguments:
        datestr - Date string in format 'YYYY-mm-dd' or '%Y-%m-%d' - the date in question
        half_day_flag - Boolean indicating whether to also check if the datestr is a half-day, i.e., the market closes
            early that day. If not specified, this parameter defaults to True.

    Returns a Boolean valiue, True if the date string is a trading holiday (or half-day if that flag enabled), False if not.

    External file dependencies:
        holidays.txt - Text file containing a list of market holidays, one per line, in format 'yyyy-mm-dd', i.e., '%Y-%m-%d'
        half-days.txt - Text file in same format as holidays.txt specifying days the market closes early.

    """
    # Read the list of holidays from the file
    with open('holidays.txt', 'r') as file:
        holidays = [line.strip() for line in file]
    file.close()
    if(half_day_flag):
        with open('half_days.txt', 'r') as file:
            half_days = [line.strip() for line in file]
        file.close()
        if (datestr in holidays) or (datestr in half_days):
            return True
        else:
            return False
    else:
        if(datestr in holidays):
            return True
        else:
            return False


def hello_world(sym,exp,strike):
    print('Hello World')
    return(strike+2)


###############
def hour12to24(x):
    if (x.hour < 12):
        y = x + timedelta(hour=12)
    return y