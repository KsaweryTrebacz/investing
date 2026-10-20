/**
 * Stan aplikacji Aurum Invest i logika biznesowa
 */

const { INITIAL_MARKET_DATA, INITIAL_USER_PORTFOLIO, BULLION_CATALOG } = window.AurumData;

const STORAGE_KEY_PORTFOLIO = 'aurum_invest_portfolio_v1';
const STORAGE_KEY_SETTINGS = 'aurum_invest_settings_v1';

class AppState {
  constructor() {
    this.subscribers = [];
    this.market = JSON.parse(JSON.stringify(INITIAL_MARKET_DATA));
    this.portfolio = this.loadPortfolio();
    this.settings = this.loadSettings();
    this.catalog = JSON.parse(JSON.stringify(BULLION_CATALOG));
    this.activeTimeframe = '24h';
    this.activeUnit = 'oz'; // 'oz', 'g', 'kg'
    this.liveSimulationInterval = null;
    this.isLiveSimulationActive = true;
  }

  loadPortfolio() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_PORTFOLIO);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.warn('Nie udało się odczytać portfela z localStorage:', e);
    }
    return JSON.parse(JSON.stringify(INITIAL_USER_PORTFOLIO));
  }

  savePortfolio() {
    try {
      localStorage.setItem(STORAGE_KEY_PORTFOLIO, JSON.stringify(this.portfolio));
    } catch (e) {
      console.error('Błąd zapisu portfela:', e);
    }
  }

  loadSettings() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_SETTINGS);
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.warn('Nie udało się odczytać ustawień:', e);
    }
    return {
      currency: 'PLN', // 'PLN', 'USD', 'EUR'
      notificationsEnabled: true,
      priceAlertPLN: 11200.00
    };
  }

  saveSettings() {
    try {
      localStorage.setItem(STORAGE_KEY_SETTINGS, JSON.stringify(this.settings));
    } catch (e) {
      console.error('Błąd zapisu ustawień:', e);
    }
  }

  subscribe(callback) {
    this.subscribers.push(callback);
    return () => {
      this.subscribers = this.subscribers.filter(cb => cb !== callback);
    };
  }

  notify(event, data) {
    this.subscribers.forEach(cb => {
      try {
        cb(event, data, this);
      } catch (err) {
        console.error('Błąd w subscriberze:', err);
      }
    });
  }

  setCurrency(curr) {
    if (this.market.exchangeRates[curr]) {
      this.settings.currency = curr;
      this.saveSettings();
      this.notify('currency_changed', curr);
    }
  }

  setTimeframe(tf) {
    this.activeTimeframe = tf;
    this.notify('timeframe_changed', tf);
  }

  setUnit(unit) {
    this.activeUnit = unit;
    this.notify('unit_changed', unit);
  }

  toggleLiveSimulation(forcedState) {
    this.isLiveSimulationActive = forcedState !== undefined ? forcedState : !this.isLiveSimulationActive;
    if (this.isLiveSimulationActive) {
      this.startLiveSimulation();
    } else {
      this.stopLiveSimulation();
    }
    this.notify('simulation_toggled', this.isLiveSimulationActive);
  }

  startLiveSimulation() {
    if (this.liveSimulationInterval) return;
    this.liveSimulationInterval = setInterval(() => {
      const deltaPercent = (Math.random() - 0.49) * 0.16;
      const change = this.market.baseSpotOuncePLN * (deltaPercent / 100);
      this.market.baseSpotOuncePLN = Math.max(8000, Number((this.market.baseSpotOuncePLN + change).toFixed(2)));
      
      if (this.market.baseSpotOuncePLN > this.market.dayHighPLN) {
        this.market.dayHighPLN = this.market.baseSpotOuncePLN;
      }
      if (this.market.baseSpotOuncePLN < this.market.dayLowPLN) {
        this.market.dayLowPLN = this.market.baseSpotOuncePLN;
      }
      
      this.market.dayChangePercent = Number((((this.market.baseSpotOuncePLN - 10693.70) / 10693.70) * 100).toFixed(2));
      this.market.dayChangePLN = Number((this.market.baseSpotOuncePLN - 10693.70).toFixed(2));

      this.notify('price_tick', {
        newPrice: this.market.baseSpotOuncePLN,
        delta: change,
        direction: change >= 0 ? 'up' : 'down'
      });
    }, 4500);
  }

  stopLiveSimulation() {
    if (this.liveSimulationInterval) {
      clearInterval(this.liveSimulationInterval);
      this.liveSimulationInterval = null;
    }
  }

  getSpotPriceInCurrentCurrency(weightUnit = 'oz') {
    const rate = this.market.exchangeRates[this.settings.currency] || 1;
    const ouncePrice = this.market.baseSpotOuncePLN * rate;
    
    if (weightUnit === 'g') {
      return ouncePrice / 31.1035;
    } else if (weightUnit === 'kg') {
      return (ouncePrice / 31.1035) * 1000;
    }
    return ouncePrice;
  }

  formatMoney(amountInPLN, customCurrency = null) {
    const currency = customCurrency || this.settings.currency;
    const rate = this.market.exchangeRates[currency] || 1;
    const converted = amountInPLN * rate;
    const symbol = this.market.currencySymbols[currency] || currency;

    const formatted = new Intl.NumberFormat('pl-PL', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(converted);

    if (currency === 'PLN') {
      return `${formatted} zł`;
    } else {
      return `${symbol}${formatted}`;
    }
  }

  getPortfolioMetrics() {
    const currentSpotPerGram = this.market.baseSpotOuncePLN / 31.1035;
    let totalValuePLN = 0;
    let totalInvestedPLN = 0;
    let totalGrams = 0;

    this.portfolio.items.forEach(item => {
      const itemGrams = (item.weightGrams || 31.1035) * (item.quantity || 1);
      totalGrams += itemGrams;
      
      const itemMarketValue = itemGrams * currentSpotPerGram;
      const itemInvested = (item.buyPricePerUnitPLN || 0) * (item.quantity || 1);

      totalValuePLN += itemMarketValue;
      totalInvestedPLN += itemInvested;
    });

    const profitLossPLN = totalValuePLN - totalInvestedPLN;
    const profitLossPercent = totalInvestedPLN > 0 ? (profitLossPLN / totalInvestedPLN) * 100 : 0;
    const totalWealthPLN = totalValuePLN + this.portfolio.cashBalancePLN;

    return {
      totalValuePLN,
      totalInvestedPLN,
      totalGrams,
      totalOunces: totalGrams / 31.1035,
      cashBalancePLN: this.portfolio.cashBalancePLN,
      totalWealthPLN,
      profitLossPLN,
      profitLossPercent
    };
  }

  buyItem(order) {
    if (order.totalCostPLN > this.portfolio.cashBalancePLN) {
      throw new Error(`Niewystarczające środki w gotówce. Masz ${this.formatMoney(this.portfolio.cashBalancePLN)}, a transakcja wymaga ${this.formatMoney(order.totalCostPLN)}.`);
    }

    this.portfolio.cashBalancePLN -= order.totalCostPLN;

    const existing = this.portfolio.items.find(i => i.productId === order.productId && i.storageType === (order.storageType || 'skarbca'));
    if (existing && order.category === 'cyfrowe') {
      existing.weightGrams += order.weightGrams;
      existing.buyPricePerUnitPLN = ((existing.buyPricePerUnitPLN * (existing.quantity || 1)) + order.totalCostPLN) / (existing.quantity || 1);
    } else {
      const newItem = {
        id: 'port-' + Date.now(),
        productId: order.productId,
        name: order.name,
        category: order.category,
        mint: order.mint || 'Mennica Akredytowana LBMA',
        purity: order.purity || '999.9',
        weightGrams: order.weightGrams,
        weightUnit: order.weightUnit || `${order.weightGrams}g`,
        quantity: order.quantity || 1,
        buyPricePerUnitPLN: order.totalCostPLN / (order.quantity || 1),
        buyDate: new Date().toISOString().split('T')[0],
        storageType: order.storageType || 'skarbca',
        serialNumber: 'AUR-' + Math.floor(100000 + Math.random() * 900000)
      };
      this.portfolio.items.push(newItem);
    }

    const now = new Date();
    const dateFormatted = `${now.toISOString().split('T')[0]} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    
    this.portfolio.transactions.unshift({
      id: 'tx-' + Date.now(),
      date: dateFormatted,
      type: 'KUPNO',
      itemName: `${order.name} (${order.quantity}x)`,
      amountPLN: order.totalCostPLN,
      weightGrams: order.weightGrams * (order.quantity || 1),
      status: order.storageType === 'dom' ? 'W realizacji wysyłki' : 'Zabezpieczono w skarbcu',
      txHash: '0x' + Math.random().toString(16).substring(2, 10) + '...gold'
    });

    this.savePortfolio();
    this.notify('portfolio_updated', { type: 'buy', order });
    return true;
  }

  sellItem(portfolioItemId, quantityToSell = 1) {
    const itemIndex = this.portfolio.items.findIndex(i => i.id === portfolioItemId);
    if (itemIndex === -1) {
      throw new Error('Nie znaleziono pozycji w portfelu.');
    }

    const item = this.portfolio.items[itemIndex];
    if (item.quantity < quantityToSell) {
      throw new Error('Niewystarczająca liczba sztuk do sprzedaży.');
    }

    const currentSpotPerGram = this.market.baseSpotOuncePLN / 31.1035;
    const sellValuePLN = (item.weightGrams * currentSpotPerGram * 0.99) * quantityToSell;

    this.portfolio.cashBalancePLN += sellValuePLN;

    if (item.quantity === quantityToSell) {
      this.portfolio.items.splice(itemIndex, 1);
    } else {
      item.quantity -= quantityToSell;
    }

    const now = new Date();
    const dateFormatted = `${now.toISOString().split('T')[0]} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

    this.portfolio.transactions.unshift({
      id: 'tx-' + Date.now(),
      date: dateFormatted,
      type: 'SPRZEDAŻ',
      itemName: `${item.name} (${quantityToSell}x)`,
      amountPLN: sellValuePLN,
      weightGrams: item.weightGrams * quantityToSell,
      status: 'Zrealizowano odkup',
      txHash: '0x' + Math.random().toString(16).substring(2, 10) + '...sell'
    });

    this.savePortfolio();
    this.notify('portfolio_updated', { type: 'sell', item, sellValuePLN });
    return sellValuePLN;
  }

  depositCash(amountPLN, method = 'BLIK') {
    if (amountPLN <= 0) throw new Error('Kwota musi być większa od 0');
    this.portfolio.cashBalancePLN += amountPLN;
    
    const now = new Date();
    const dateFormatted = `${now.toISOString().split('T')[0]} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

    this.portfolio.transactions.unshift({
      id: 'tx-' + Date.now(),
      date: dateFormatted,
      type: 'WPŁATA',
      itemName: `Zasilenie konta (${method})`,
      amountPLN: amountPLN,
      weightGrams: 0,
      status: 'Zrealizowano',
      txHash: 'DEP-' + Math.floor(100000 + Math.random() * 900000)
    });

    this.savePortfolio();
    this.notify('portfolio_updated', { type: 'deposit', amountPLN });
  }

  resetDemoData() {
    localStorage.removeItem(STORAGE_KEY_PORTFOLIO);
    localStorage.removeItem(STORAGE_KEY_SETTINGS);
    this.portfolio = JSON.parse(JSON.stringify(INITIAL_USER_PORTFOLIO));
    this.market = JSON.parse(JSON.stringify(INITIAL_MARKET_DATA));
    this.settings = { currency: 'PLN', notificationsEnabled: true, priceAlertPLN: 11200.00 };
    this.savePortfolio();
    this.saveSettings();
    this.notify('data_reset', null);
  }
}

window.appState = new AppState();
