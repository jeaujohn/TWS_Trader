"""
options.py - Functions for executing option (covered call) trades via TWS API / ib_insync

Functions in this module include:

    covered_call(ib,mystock,mycalls, myexpiration,auto_flag) - Write a covered call\

    buyback_call(ib,mystock,mycalls) - Buy back a covered call

Please refer to docstring of individual functions.

# Module for executing ROLLOVER combo orders
# Note: To avoid having to hit "Transmit" for the order in TWS UI:
#   `Under File -> Global Configuration -? API -> Precautions
#   place a check mark next to the following:
#       Bypass Order Precautions for API Orders
#       Bypass price-based volatility risk warning for API Orders
#       Bypass US Stocks market data in shares warning for API Orders
#       Bypass Redirect Order warning for Stock Orders

Also, at portal.interactivebrokers.com, under Settings >> Market Data Subscriptions, it is necessary to subscribe to
OPRA (US Options Exchanges) in order to trade options from the API. With the TWS UI, it is possible to trade options
with delayed market data because the TWS UI will ask for an override confirmation. However, no such override exists on
the API.

"""

from ib_insync import *

####################################################################################################################
def covered_call(ib,mystock,mycalls, myexpiration,auto_flag):
    """
    function covered_call(ib,mystock,mycalls, myexpiration,auto_flag) - Attempt to write a covered call at delta near 0.4

    Input arguments:
        ib - ib_insync object, assumed to be already connected
        mystock - String specifying underlying stock, of which at least 100*mycalls shares must already be held
        mycalls - number of call option contracts to write. Must already hold at least 100*mycalls shares of underlying
        myexpiration - String in format 'yyyymmdd' ('%Y%m%d') specifying desired expiration date of call
        auto_flag - Specify for positions on weekly automated trading. If specified as True. returns False unless there
            are currently no options for the underlying.

    Returns - True if trade executed, False otherwise

    This function generally checks to make sure that there are enough underlying shares to cover all the calls for that
    position after any additional covered call orders are written. If there are not enough underlying shares for the
    existing covered call contracts plus any new ones, will not attempt a trade and will instead return False. The
    expiration date must be valid for the stock or the function will return False. This function tries to find a strike
    price on the specified expiration date corresponding to a delta near 0.4.

    """
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    #ib.reqMarketDataType(1) # avoid market permission problems by requesting delayed data
    ib.sleep(1)
    #Make sure there are enough underlying shares to support the covered call
    underlyingPosition=0
    optionPosition=0
    pos=ib.positions()
    for ppp in pos:
        if(ppp.contract.secType=='STK' and ppp.contract.symbol==mystock):
            underlyingPosition = ppp.position
        elif(ppp.contract.secType=='OPT' and ppp.contract.symbol==mystock):
            optionPosition = ppp.position
            if(auto_flag and (ppp.position!=0)):
                return False    #Only sell covered call in auto_flag mode if there is currently no option associated with position
    positionRoom=underlyingPosition+optionPosition*100
    if(positionRoom < mycalls*100):
        print('Error in covered_call(): not enough shares to support covered call')
        return False


    [ticker] = ib.reqTickers(stock)
    ticker
    stockval = ticker.marketPrice()
    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
    df_chains = util.df(chains)
    chain = next(c for c in chains if c.tradingClass == mystock and c.exchange == 'SMART')
    #for c in chains:
    #    if c.tradingClass == 'AAPL' and c.exchange == 'SMART':
    #        chain = c
    #        break
    strikes = [strike for strike in chain.strikes
            #if strike % 5 == 0 and aaplval < strike < 1.1*aaplval]
            if stockval < strike < 1.03*stockval]
    #expirations = sorted(exp for exp in chain.expirations)[:3]

    #rights = ['P', 'C']
    rights=['C']   #We are only interested in calls, not puts
    expirations=[myexpiration]
    contracts = [Option(mystock, expiration, strike, right, 'SMART', tradingClass=mystock)
                 for right in rights for expiration in expirations for strike in strikes]
    contracts = ib.qualifyContracts(*contracts)

    # Check to make sure that qualified contracts are actually available. Mis-specified expiration dates, or expiration
    # dates that do not correspond with actual call contracts,, will result in a zero-length list and the function
    # returning False.
    if len(contracts) == 0:
        print('covered_call() error: No call contracts available for ',mystock, ' at expiration ',myexpiration)
        return False
    tickers = ib.reqTickers(*contracts)
    qqq=tickers[0]
    distfromdelt=[]
    for i in range(0,len(tickers)):
        distfromdelt.append(abs(tickers[i].modelGreeks.delta-0.4))
    best_delta_index = distfromdelt.index(min(distfromdelt))
    option_contract = contracts[best_delta_index]
    print(df_chains)

    order = MarketOrder('SELL', 1)

    trade = ib.placeOrder(option_contract, order)
    ib.sleep(2)
    while not trade.isDone():
        ib.sleep(2)
    #ib.waitOnUpdate()
    #print(trade)
    trade.fillEvent += orderFilled
    return True
    #ib.sleep(3)


################################################################################################################
def buyback_call(ib,mystock,mycalls):
    """
    function buyback_call(ib, mystock, mycalls) - Buys back qty. mycalls covered call contracts of underlying mystock.

    Arguments:
        ib - Instantiated and connected ib_insync object
        mystock - String specifying underlyuing ticker
        mycalls - Number of covered call contracts to buy back. Must have written at least that many calls against the
            underlying in the current position

    Returns True if buyback trade successful, False if not

    This function checks to make sure that there are at least mycalls covered calls in the current position written
    against the underlying. If there are not enough calls to buy back, this function returns False, since buying
    calls outright is not supported by this software. Note that this function assumes that  only one type of call
    contract (strike/expiration) has been written. Holding multiple covered call contracts against an underlying is not
    supported by this software, although it is ok to write multiple calls of the same type.
    """
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    #ib.reqMarketDataType(1) # avoid market permission problems by requesting delayed data
    ib.sleep(1)
    #Make sure there are enough underlying shares to support the covered call
    underlyingPosition=0
    optionPosition=0
    pos=ib.positions()
    for ppp in pos:
        if(ppp.contract.secType=='STK' and ppp.contract.symbol==mystock):
            underlyingPosition = ppp.position
        elif(ppp.contract.secType=='OPT' and ppp.contract.symbol==mystock):
            optionPosition = ppp.position
            optionContract=ppp.contract


    #positionRoom=underlyingPosition+optionPosition*100
    if(optionPosition> -mycalls):
        print('Error in buyback_call(): Not enough covered calls to buy back')
        return False
    ib.qualifyContracts(optionContract)

    order=MarketOrder('BUY',mycalls)

    trade = ib.placeOrder(optionContract, order)
    ib.sleep(2)
    while not trade.isDone():
        ib.sleep(2)
    #ib.waitOnUpdate()
    #print(trade)
    trade.fillEvent += orderFilled
    return True
    #ib.sleep(3)


def orderFilled(trade, fill):
    print("order has been filled")
    print(trade)
    print(fill)


########################################################################################
def main():
    """
    main() - For internal testing and debugging
    """
    global ib
    ib = IB()
    myexpiration = '20230707'
    mystock = 'SPY'
    mycalls = 1
    mystock2='AAPL'
    # use this instead for IB Gateway
    # ib.connect('127.0.0.1', 7497, clientId=1)

    # us this for TWS (Workstation)
    ib.connect('127.0.0.1', 7497, clientId=2)
    ib.reqMarketDataType(1)  # avoid market permission problems by requesting delayed data
    #status=covered_call(ib,mystock,myexpiration,mycalls)
    status = buyback_call(ib,mystock2,mycalls)
    if status:
        for trade in ib.trades():
            print("== this is one of my trades =")
            print(trade)
        exit(1)
    else:
        exit(-1)


###################################
if __name__ == "__main__":
         main()