"""
order.py - Module for executing simple orders to buy and sell shares of a stock, as well as to completely close a position.

External functions:
    buy_stock(ib,mystock,myshares)
    sell_stock(ib,mystock,myshares)
    close_position(ib,mystock)

Please refer to the docstrings of the individual functions for their descriptions.


# Note: To avoid having to hit "Transmit" for the order in TWS UI:
#   `Under File -> Global Configuration -? API -> Precautions
#   place a check mark next to the following:
#       Bypass Order Precautions for API Orders
#       Bypass price-based volatility risk warning for API Orders
#       Bypass US Stocks market data in shares warning for API Orders
#       Bypass Redirect Order warning for Stock Orders

Also, at portal.interactivebrokers.com, under Settings >> Market Data Subscriptions, it is necessary to subscribe to
OPRA (US Options Exchanges) in order to trade options from the API. With the TWS UI, it is possible to trade options
with delayed market data becuse the TWS UI will ask for an override confirmation. However, no such override exists
on the API.

"""


from ib_insync import *
'''
util.startLoop()
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

stock = Stock('AAPL', 'SMART', 'USD')
ib.qualifyContracts(stock)
order = MarketOrder('BUY', 100)

trade = ib.placeOrder(stock, order)
ib.waitOnUpdate()
#print(trade)

def orderFilled(trade, fill):
    print("order has been filled")
    print(trade)
    print(fill)

trade.fillEvent += orderFilled

#ib.sleep(3)


#ib.run()
'''

##########################################################################################
def buy_stock(ib, mystock, myshares):
    """
    function buy_stock(ib,mystock,myshares) - Buy shares of specified stock

    Input parameters:
        ib - ib_insync object, assumed to be intiatialized with connection established
        mystock - String specifying ticker of interest
        myshares - Desired number of shares to purchase

     buy_stock() executes a trade order to buy myshares of mystock. Checks to make sure that
     there is a positive cash balance to support the trade. This software does not allow leveraged
     trades.

     Returns:
         True if successful trade, False otherwise.
    """
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    [ticker] = ib.reqTickers(stock)
    stockval = ticker.marketPrice()

    account_value = 0
    # [v for v in ib.accountValues() if v.tag == 'NetLiquidationByCurrency' and v.currency == 'BASE']
    # v: AccountValue
    cash_balance=0
    val = ib.accountValues()
    for v in val:
        if (v.tag == 'CashBalance' and v.currency == 'BASE'):  # Accounbt value field
            cash_balance = float(v.value)
            print('Cash balance = ',v.value)
    if(cash_balance < myshares*stockval):  #Leveraged orders not supported
        print("Error in buy_stock(): Not enough cash value to support order of ",myshares," shares of ",mystock)
        return False

    order = MarketOrder('BUY', myshares)
    trade = ib.placeOrder(stock, order)
    # ib.waitOnUpdate()
    ib.sleep(2)
    while not trade.isDone():
        ib.sleep(2)
    # ib.waitOnUpdate()
    # print(trade)

    # print(trade)

    trade.fillEvent += orderFilled
    return True

##############################################################################################################
def sell_stock(ib,mystock,myshares):
    """
    function sell_stock(ib,mystock,myshares) - Sell shares of specified stock

    Input parameters:
        ib - ib_insync object, assumed to be intiatialized with connection established
        mystock - String specifying ticker of interest
        myshares - Desired number of shares to purchase

     sell_stock() executes a trade order to sell myshares of mystock. Checks to make sure that
     position currently has at least myshares of stock. This software does not allow short orders.

     Returns:
         True if successful trade, False otherwise.

    """
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)

    underlyingPosition=0
    optionPosition=0
    pos=ib.positions()
    for ppp in pos:
        if(ppp.contract.secType=='STK' and ppp.contract.symbol==mystock):
            underlyingPosition = ppp.position
        elif (ppp.contract.secType == 'OPT' and ppp.contract.symbol == mystock):
            optionPosition = ppp.position
    if(underlyingPosition < myshares): #Short sales nort supported
        print('Error in sell_stock(): not enough shares to support sale')
        return False
    if((underlyingPosition-myshares)+optionPosition*100<0):
        print('Error in sell_stock(): sale would expose a naked call, aborted')
        return False
    order = MarketOrder('SELL', myshares)
    trade = ib.placeOrder(stock, order)
    #ib.waitOnUpdate()
    ib.sleep(2)
    while not trade.isDone():
        ib.sleep(2)
    #ib.waitOnUpdate()
    #print(trade)

    trade.fillEvent += orderFilled
    return True

###############################################################################################
def close_position(ib,mystock):
    """
    function close_position(ib, mystock) - Fully close position including underlying and covered calls

    Input parameters:
        ib - ib_insync object, assumed instantiated with connection established
        mystock - String specifying ticker to close position on

    Returns:
        True if position successfully closed, False otherwise

    The close_position function executes a trade to completely vacate the position on mystock, both the underlying
    stock position as well as any covered calls. It first checks to see if there are any covered call contracts and
    buys them back. Then it checks to make sure that there really are shares in an underlying position before closing
    the underlying position.
    """
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)

    underlyingPosition=0
    optionPosition=0
    pos=ib.positions()
    for ppp in pos:
        if(ppp.contract.secType=='STK' and ppp.contract.symbol==mystock):
            underlyingPosition = ppp.position
        elif (ppp.contract.secType == 'OPT' and ppp.contract.symbol == mystock):
            optionPosition = ppp.position
            optionContract = ppp.contract

            ib.qualifyContracts(optionContract)

            order = MarketOrder('BUY', -optionPosition)

            trade = ib.placeOrder(optionContract, order)
            ib.sleep(2)
            while not trade.isDone():
                ib.sleep(2)
            trade.fillEvent += orderFilled
    if(underlyingPosition <= 0):
        print('Error in close_position: not enough shares to support sale')
        return False

    order = MarketOrder('SELL', underlyingPosition)
    trade = ib.placeOrder(stock, order)
    #ib.waitOnUpdate()
    ib.sleep(2)
    while not trade.isDone():
        ib.sleep(2)
    #ib.waitOnUpdate()
    #print(trade)


    trade.fillEvent += orderFilled
    return True

##################################
def orderFilled(trade, fill):
    print("order has been filled")
    print(trade)
    print(fill)


##################################################################################################################3
def main():    #Mainly for testing
    global ib
    ib = IB()

    mystock = 'DIA'
    myshares = 100

    # use this instead for IB Gateway
    # ib.connect('127.0.0.1', 7497, clientId=1)

    # us this for TWS (Workstation)
    ib.connect('127.0.0.1', 7497, clientId=61)
    ib.reqMarketDataType(1)  # avoid market permission problems by requesting delayed data
    # Test out various uses below
    #status=covered_call(ib,mystock,myexpiration,mycalls)
    #status = buy_stock(ib,mystock,myshares)
    #status = sell_stock(ib,'MSFT',50)
    status = close_position(ib,mystock)


    ib.disconnect()
    if status:
        for order in ib.orders():
            print("== this is one of my orders ==")
            print(order)
        for trade in ib.trades():
            print("== this is one of my trades =")
            print(trade)
        exit(1)
    else:
        exit(-1)


#############################################################################################################
if __name__ == "__main__":
         main()