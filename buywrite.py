"""
buywrite.py - Module for executing BUY WRITE covered call orders via the TWS API/ib_insync. The only external
function in this module is buy_write().

# Module for executing BUY WRITE combo orders
# Note: To avoid having to hit "Transmit" for the order in TWS UI:
#   `Under File -> Global Configuration -? API -> Precautions
#   place a check mark next to the following:
#       Bypass Order Precautions for API Orders
#       Bypass price-based volatility risk warning for API Orders
#       Bypass US Stocks market data in shares warning for API Orders
#       Bypass Redirect Order warning for Stock Orders

Also, at portal.interactivebrokers.com, under Settings >> Market Data Subscriptions, it is necessary to subscribe to
OPRA (US Options Exchanges) in order to trade options from the API. With the TWS UI, it is possible to trade options
with delayed market data because the TWS UI will ask for an override confirmation. However, no such override exists
on the API.

See the docstring for the buy_write() function.
"""
from ib_insync import *

####################################################################################################################
def buy_write(ib,mystock,mycalls,myexpiration):
    """
    function buy_write(ib,mystock,mycalls,myexpiration) - Attempts to execute a BUY WRITE order for a covered call with
        a delta near 0.4.

    Input arguments:
        ib - Instantiated and connected ib_insync object.
        mystock - String specifying ticker of the underlying of interest
        mycalls - Number of covered calls to write againt the underlying. Will also BUY 100*mycalls shares of the
            underlying
        myexpiration - Desired expiration date. Must be a valid expiration date for calls on the stock or the functiuon will
            return False.

    This function attempts to execute a BUY WRITE order for the symbol mystock with requested expiration date myexpiration.
    Provided that there are cash funds available for 100*mycalls shares of the underlying, this function will generate
    a Combo order with two legs: 1) buy 100*mycalls shares of the underlying, and 3) Sell mycalls covered calls at the
    myexpiration expiration date corresponding to a delta near 0.4. If there are not call contracts available at the
    myexpiration date, this function will return False.

    """
    # Define the contract for underlying stock
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)   #Need to do this to get the current trading price
    ib.sleep(1)
    [ticker] = ib.reqTickers(stock)
    #ticker
    stockval = ticker.marketPrice()

    account_value = 0
    cash_balance=0
    val = ib.accountValues()
    for v in val:
        if (v.tag == 'CashBalance' and v.currency == 'BASE'):  # Account value field
            cash_balance = float(v.value)
            print('Cash balance = ',v.value)
    if(cash_balance < 100*mycalls*stockval):
        print("Error in buy_write(): Not enough cash value to support order of ",myshares," shares of ",mystock)
        return False

    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
#    df_chains = util.df(chains)
    chain = next(c for c in chains if c.tradingClass == mystock and c.exchange == 'SMART')
    #for c in chains:
    #    if c.tradingClass == 'AAPL' and c.exchange == 'SMART':
    #        chain = c
    #        break
    strikes = [strike for strike in chain.strikes
            #if strike % 5 == 0 and aaplval < strike < 1.1*aaplval]
            if stockval < strike < 1.03*stockval]
    #rights = ['P', 'C']
    rights=['C']   #We are only interested in calls, not puts
    expirations=[myexpiration]
    contracts = [Option(mystock, expiration, strike, right, 'SMART', tradingClass=mystock)
                  for right in rights for expiration in expirations for strike in strikes]
    contracts = ib.qualifyContracts(*contracts)
    if(len(contracts)==0):
        print('buy_write() error: No call contracts available for ',mystock, ' at expiration ',myexpiration)
        return False
    tickers = ib.reqTickers(*contracts)
    distfromdelt=[]
    minsofar=9.9e30
    for i in range(0,len(tickers)):
        thisdist=abs(tickers[i].modelGreeks.delta-0.4)
        distfromdelt.append(thisdist)
        if(thisdist<minsofar):
            minsofar=thisdist
        else:
            break  #Remaining distances from delta=0.4 will increase so just break here
    best_delta_index = distfromdelt.index(min(distfromdelt))
    # Define the contract for the covered call option to sell
    covered_call_contract = contracts[best_delta_index]
    ib.qualifyContracts(covered_call_contract)


    # Create the ComboLegs object and add legs to it
    combo = Contract()
    combo.symbol=mystock
    combo.secType="BAG"
    combo.currency="USD"
    combo.exchange="SMART"
    combo.tradingClass="COMB"
    leg1=ComboLeg()
    leg1.conId = stock.conId
    leg1.ratio = 100
    leg1.action = 'BUY'
    leg1.exchange='SMART'
    leg1.exemptCode=-1
    leg2=ComboLeg()
    leg2.conId=covered_call_contract.conId
    leg2.ratio=1
    leg2.action='SELL'
    leg2.exchange='SMART'
    leg2.exemptCode=-1
    combo.comboLegs = []
    combo.comboLegs.append(leg1)
    combo.comboLegs.append(leg2)

    # Create a market (MKT) order to execute the trade
    order = MarketOrder('BUY', mycalls)
    #order.m_transmit = True
    order.transmit=True
    # Place the order for the Combo contract
    trade = ib.placeOrder(combo, order)

    # Wait until the order is filled
    while not trade.isDone():
        ib.sleep(2)
        #ib.waitOnUpdate()

    trade.fillEvent += orderFilled
    return True


######################################
def orderFilled(trade, fill):
    print("order has been filled")
    print(trade)
    print(fill)



################################################################################################################
def main():    # Mainly for testing
    myexpiration = '20230803'
    mystock='DIA'
    mycalls = 1
    # Connect to the Trader Workstation (TWS) or IB Gateway
    #util.startLoop()    Only need for Jupyter
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=21)  # Update with the appropriate connection details

    status=buy_write(ib,mystock,mycalls,myexpiration)

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

    for trade in ib.trades():
        print("== this is one of my trades =")
        print(trade)

    ib.disconnect()

#################################################################################################################
if __name__ == "__main__":
         main()