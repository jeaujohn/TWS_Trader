"""
rollover.py

Please see the docstring for the rollover() function, the primary function for this module.
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
with delayed market data becuse the TWS UI will ask for an override confirmation. However, no such ov erride exists on
the API.

"""

from ib_insync import *
from datetime import datetime


###############################################################################################################
def rollover(ib,mystock,mycalls,myexpiration,auto_flag,force_flag):
    """
    rollover(ib,mystock,mycalls, myexpiration, auto_flag, force_flag)

    The rollover function sets up and issues a COMBO order whereby the current covered call is bought back and a new
    covered call is written for the specified expiration date at a delta value near 0.4. Although this is a combo order,
    recorder() records the legs of the combo order in separate lines of the activity.xlsx file. Before executing trade,
    makes sure that there are at least mycalls calls in the position and that there are at least 100*mycalls of underlying
    shares to cover for the calls.

    Arguments:
        ib - ib_insync object
        mystock - Sting specifying ticker in question
        mycalls - Number of call contracts to roll over.
        myexpiration - Expiration date string of desired new option contract in format 'yyyymmdd'. If no contracts are
            available on the expiration date, the function will return False.
        auto_flag - If enabled, will only execute the rollover on the expiration date odf the currently held call
        force_flag - If enabled, executes rollovber order irrespective of whether current call is in the money. If
            disabled, only executes rollover order if current covbered call is iun the money.
    """
    # Define the contract for SPY stock
    stock = Stock(mystock, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    ib.sleep(1)
    [ticker] = ib.reqTickers(stock)
    #ticker
    stockval = ticker.marketPrice()

    optionPosition=0
    underlyingPosition=0
    pos=ib.positions()
    for ppp in pos:
        if (ppp.contract.secType == 'STK' and ppp.contract.symbol == mystock):
            underlyingPosition = ppp.position
        elif (ppp.contract.secType == 'OPT' and ppp.contract.symbol == mystock):
            todaystr = datetime.today().strftime('%Y%m%d')
            if (auto_flag and (todaystr != ppp.contract.lastTradeDateOrContractMonth)):
                return False  #rollover gets called daily in auto_flag mode and shoudl only respond if expiration date is met
            if((not force_flag) and (stockval < ppp.contract.strike)):
                return False
            optionPosition = ppp.position
            buy_back_contract = ppp.contract

    # positionRoom=underlyingPosition+optionPosition*100
    if (optionPosition > -mycalls):
        print('Error in buyback_call(): Not enough covered calls to buy back')
        exit(-1)
    positionRoom=underlyingPosition+optionPosition*100
    if(underlyingPosition < mycalls*100):
         print('Error in covered_call(): not enough shares to support covered call')
         exit(-1)

    # Define the contract for the call option to buy back
    #buy_back_contract = Option(mystock, '20230707', 344, 'C', 'SMART', tradingClass=mystock)

    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
    df_chains = util.df(chains)
    chain = next(c for c in chains if c.tradingClass == mystock and c.exchange == 'SMART')
    #for c in chains:
    #    if c.tradingClass == 'AAPL' and c.exchange == 'SMART':
    #        chain = c
    #        break
    strikes = [strike for strike in chain.strikes
            #if strike % 5 == 0 and aaplval < strike < 1.1*aaplval]
            if stockval <= strike < 1.03*stockval]
    #rights = ['P', 'C']
    rights=['C']   #We are only interested in calls, not puts
    expirations=[myexpiration]
    contracts = [Option(mystock, expiration, strike, right, 'SMART', tradingClass=mystock)
                 for right in rights for expiration in expirations for strike in strikes]
    if len(contracts) == 0:
        print('rollover() error: No call contracts available for ',mystock, ' at expiration ',myexpiration)
        return False
    contracts = ib.qualifyContracts(*contracts)
    len(contracts)
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
    covered_call_contract = contracts[best_delta_index]

    # Define the contract for the covered call option to sell
    #covered_call_contract = Option(mystock, myexpiration, 437, 'C', 'SMART', tradingClass=mystock)

    # Request market data to ensure the contracts are valid

    ib.qualifyContracts(buy_back_contract)
    ib.qualifyContracts(covered_call_contract)

    # Create the ComboLegs object and add legs to it


    combo = Contract()
    combo.symbol=mystock
    combo.secType="BAG"
    combo.currency="USD"
    combo.exchange="SMART"
    combo.tradingClass="COMB"
    leg1=ComboLeg()
    leg1.conId = buy_back_contract.conId
    leg1.ratio = 1
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

    ##combo = Contract()
    #combo.symbol=mystock
    #combo.secType="BAG"
    #combo.currency="USD"
    #combo.exchange="SMART"
    #combo.comboLegs = []
    #combo.comboLegs.append(ComboLeg(conId=buy_back_contract.conId, ratio=1, action='BUY'))
    #combo.comboLegs.append(ComboLeg(conId=covered_call_contract.conId, ratio=1, action='SELL'))

    # Create the Combo contract using the ComboLegs object
    #combo_contract = Combo('BAG')
    #combo_contract.comboLegs = combo_legs

    # Create a market (MKT) order to execute the trade
    order = MarketOrder('BUY', 1)
    order.transmit = True
    # Place the order for the Combo contract
    trade = ib.placeOrder(combo, order)

    # Wait until the order is filled
    #ib.waitOnUpdate()

    ib.sleep(2)
    # Wait until the order is filled
    while not trade.isDone():
        ib.sleep(2)
        #ib.waitOnUpdate()
    trade.fillEvent += orderFilled


###################################
def orderFilled(trade, fill):
    print("order has been filled")
    print(trade)
    print(fill)



#########################################################################################################
def main():
    """
    main() - internal driver for rollover function. Allows for selective testing of the function.
    """
    global ib
    ib = IB()

    # Set up variables for test trade
    myexpiration = '20230721'
    mystock = 'SPY'
    mycalls = 1
    force_flag = False
    auto_flag = True

    # use this for TWS (Workstation)
    ib.connect('127.0.0.1', 7497, clientId=13)
    ib.reqMarketDataType(1)  # request real-time data, 4 is delayed

    # Test various uses
    #status=covered_call(ib,mystock,myexpiration,mycalls)
    #status = buy_stock(ib,mystock,myshares)
    #status = sell_stock(ib,'MSFT',50)
    status = rollover(ib,mystock,mycalls,myexpiration,auto_flag,force_flag)


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


#######################################################################################################################
if __name__ == "__main__":
         main()