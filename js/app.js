/**
 * Główny skrypt aplikacji Aurum Invest
 */

class AurumApp {
  constructor() {
    this.appState = window.appState;
    this.chartManager = new window.ChartManager(this.appState);
    this.selectedBuyProduct = null;
    this.selectedSellItem = null;
    this.buyModalQuantity = 1;
    this.terminalMode = 'buy';
  }

  init() {
    if (window.lucide) {
      window.lucide.createIcons();
    }

    this.chartManager.initMainChart('mainGoldChart');
    this.chartManager.initPortfolioChart('portfolioDoughnutChart');
    this.initSavingsCalculator();

    this.renderHeaderAndKPIs();
    this.renderQuickTerminal();
    this.renderFeaturedProducts();
    this.renderCatalog();
    this.renderPortfolio();
    this.renderHistory();

    this.bindEvents();

    this.appState.subscribe((event, data) => this.onStateChanged(event, data));

    this.appState.startLiveSimulation();
  }

  onStateChanged(event, data) {
    if (event === 'price_tick') {
      this.handlePriceTick(data);
    } else if (event === 'currency_changed' || event === 'unit_changed') {
      this.renderHeaderAndKPIs();
      this.renderQuickTerminal();
      this.renderFeaturedProducts();
      this.renderCatalog();
      this.renderPortfolio();
      this.chartManager.updateMainChart();
    } else if (event === 'portfolio_updated' || event === 'data_reset') {
      this.renderHeaderAndKPIs();
      this.renderPortfolio();
      this.renderHistory();
      this.renderQuickTerminal();
      this.chartManager.updatePortfolioChart();
    } else if (event === 'timeframe_changed') {
      this.chartManager.updateMainChart();
    }

    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  handlePriceTick(data) {
    const spotEl = document.getElementById('top-spot-price');
    
    const flashClass = data.direction === 'up' ? 'flash-green' : 'flash-red';
    if (spotEl) {
      spotEl.classList.remove('flash-green', 'flash-red');
      void spotEl.offsetWidth;
      spotEl.classList.add(flashClass);
    }

    this.renderHeaderAndKPIs();
    this.renderQuickTerminal();
    this.chartManager.updateLiveTick(data.newPrice);
    this.chartManager.updatePortfolioChart();
  }

  renderHeaderAndKPIs() {
    const metrics = this.appState.getPortfolioMetrics();

    // Header Spot Price
    const topSpot = document.getElementById('top-spot-price');
    if (topSpot) {
      topSpot.textContent = this.appState.formatMoney(this.appState.market.baseSpotOuncePLN);
    }
    const topChange = document.getElementById('top-spot-change');
    if (topChange) {
      const isPositive = this.appState.market.dayChangePercent >= 0;
      topChange.textContent = `${isPositive ? '+' : ''}${this.appState.market.dayChangePercent}%`;
      topChange.className = `text-xs font-semibold px-1.5 py-0.5 rounded ml-1 ${isPositive ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'}`;
    }

    // Header Cash Balance
    const headerCash = document.getElementById('header-cash-balance');
    if (headerCash) {
      headerCash.textContent = this.appState.formatMoney(metrics.cashBalancePLN);
    }

    // KPI 1: Spot Price
    const kpiSpot = document.getElementById('kpi-spot-price');
    if (kpiSpot) {
      const unit = this.appState.activeUnit;
      const price = this.appState.getSpotPriceInCurrentCurrency(unit);
      kpiSpot.textContent = this.appState.formatMoney(price / (this.appState.market.exchangeRates[this.appState.settings.currency] || 1));
    }
    const kpiSpotChange = document.getElementById('kpi-spot-change');
    if (kpiSpotChange) {
      const isPositive = this.appState.market.dayChangePercent >= 0;
      kpiSpotChange.innerHTML = `
        <i data-lucide="${isPositive ? 'arrow-up-right' : 'arrow-down-right'}" class="w-3.5 h-3.5 mr-0.5"></i>
        ${isPositive ? '+' : ''}${this.appState.market.dayChangePercent}% (${isPositive ? '+' : ''}${this.appState.formatMoney(this.appState.market.dayChangePLN)})
      `;
      kpiSpotChange.className = `font-semibold flex items-center ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`;
    }

    // KPI 2: Gold Value
    const kpiGoldVal = document.getElementById('kpi-gold-value');
    if (kpiGoldVal) {
      kpiGoldVal.textContent = this.appState.formatMoney(metrics.totalValuePLN);
    }
    const kpiGoldWeight = document.getElementById('kpi-gold-weight');
    if (kpiGoldWeight) {
      kpiGoldWeight.textContent = `${metrics.totalGrams.toFixed(2)} g`;
    }
    const kpiGoldOunces = document.getElementById('kpi-gold-ounces');
    if (kpiGoldOunces) {
      kpiGoldOunces.textContent = metrics.totalOunces.toFixed(3);
    }

    // KPI 3: Profit / Loss
    const kpiProfitLoss = document.getElementById('kpi-profit-loss');
    if (kpiProfitLoss) {
      const isProfitable = metrics.profitLossPLN >= 0;
      kpiProfitLoss.textContent = `${isProfitable ? '+' : ''}${this.appState.formatMoney(metrics.profitLossPLN)}`;
      kpiProfitLoss.className = `text-2xl font-bold tracking-tight mb-1 ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`;
    }
    const kpiProfitPercent = document.getElementById('kpi-profit-percent');
    if (kpiProfitPercent) {
      const isProfitable = metrics.profitLossPercent >= 0;
      kpiProfitPercent.textContent = `${isProfitable ? '+' : ''}${metrics.profitLossPercent.toFixed(2)}% zwrotu`;
      kpiProfitPercent.className = `font-semibold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`;
    }

    // KPI 4: Cash Balance & Total Wealth
    const kpiCash = document.getElementById('kpi-cash-balance');
    if (kpiCash) {
      kpiCash.textContent = this.appState.formatMoney(metrics.cashBalancePLN);
    }
    const kpiTotalWealth = document.getElementById('kpi-total-wealth');
    if (kpiTotalWealth) {
      kpiTotalWealth.textContent = this.appState.formatMoney(metrics.totalWealthPLN);
    }

    // Chart Min/Max text
    const statMin = document.getElementById('stat-min-price');
    if (statMin) statMin.textContent = this.appState.formatMoney(this.appState.market.dayLowPLN);
    const statMax = document.getElementById('stat-max-price');
    if (statMax) statMax.textContent = this.appState.formatMoney(this.appState.market.dayHighPLN);

    // Portfolio tab count
    const portCount = document.getElementById('nav-portfolio-count');
    if (portCount) portCount.textContent = this.appState.portfolio.items.length;
  }

  renderQuickTerminal() {
    const input = document.getElementById('quick-order-amount');
    const cashAvail = document.getElementById('term-cash-avail');
    const currSym = document.getElementById('term-curr-symbol');
    const calcGrams = document.getElementById('quick-calculated-grams');
    const calcOunces = document.getElementById('quick-calculated-ounces');

    if (cashAvail) cashAvail.textContent = this.appState.formatMoney(this.appState.portfolio.cashBalancePLN);
    if (currSym) currSym.textContent = this.appState.settings.currency;

    const amountPLN = parseFloat(input ? input.value : 1000) || 0;
    const pricePerGram = this.appState.market.baseSpotOuncePLN / 31.1035;
    const grams = amountPLN > 0 ? (amountPLN / pricePerGram) : 0;
    const ounces = grams / 31.1035;

    if (calcGrams) calcGrams.textContent = `${grams.toFixed(3)} g`;
    if (calcOunces) calcOunces.textContent = `${ounces.toFixed(4)} oz t`;
  }

  renderFeaturedProducts() {
    const grid = document.getElementById('featured-products-grid');
    if (!grid) return;

    const featured = this.appState.catalog.slice(0, 3);
    const spotGram = this.appState.market.baseSpotOuncePLN / 31.1035;

    grid.innerHTML = featured.map(prod => {
      const baseCost = prod.weightGrams * spotGram;
      const totalCostPLN = baseCost * (1 + prod.premiumPercent / 100);

      return `
        <div class="glass-panel rounded-2xl p-5 border border-slate-800 hover:border-amber-500/40 transition-all duration-300 flex flex-col justify-between group">
          <div>
            <div class="flex items-start justify-between mb-3">
              <span class="text-[10px] font-bold uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/20">
                ${prod.badge || (prod.category === 'sztabka' ? 'Sztabka LBMA' : 'Moneta Bulionowa')}
              </span>
              <span class="text-xs text-emerald-400 flex items-center font-medium">
                <i data-lucide="check" class="w-3.5 h-3.5 mr-1"></i> ${prod.deliveryTime}
              </span>
            </div>

            <h4 class="text-base font-bold text-white group-hover:text-amber-400 transition-colors">${prod.name}</h4>
            <div class="text-xs text-slate-400 mt-0.5">${prod.mint} • Próba ${prod.purity}</div>
            
            <p class="text-xs text-slate-400 mt-2 line-clamp-2 leading-relaxed">
              ${prod.description}
            </p>
          </div>

          <div class="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between">
            <div>
              <span class="text-[10px] text-slate-400 uppercase tracking-wider block">Cena brutto (0% VAT):</span>
              <span class="text-lg font-extrabold text-amber-400 font-mono">${this.appState.formatMoney(totalCostPLN)}</span>
            </div>
            <button class="btn-buy-product btn-gold px-4 py-2 rounded-xl text-xs font-bold flex items-center space-x-1.5" data-id="${prod.id}">
              <i data-lucide="shopping-cart" class="w-3.5 h-3.5"></i>
              <span>Kup teraz</span>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  renderCatalog(filter = 'all') {
    const grid = document.getElementById('full-catalog-grid');
    if (!grid) return;

    const filtered = filter === 'all' 
      ? this.appState.catalog 
      : this.appState.catalog.filter(p => p.category === filter);

    const spotGram = this.appState.market.baseSpotOuncePLN / 31.1035;

    grid.innerHTML = filtered.map(prod => {
      const baseCost = prod.weightGrams * spotGram;
      const totalCostPLN = baseCost * (1 + prod.premiumPercent / 100);

      return `
        <div class="glass-panel rounded-2xl p-5 border border-slate-800 hover:border-amber-500/40 transition-all duration-300 flex flex-col justify-between">
          <div>
            <div class="flex items-start justify-between mb-3">
              <span class="text-[10px] font-bold uppercase tracking-wider text-amber-400 bg-amber-500/10 px-2.5 py-0.5 rounded-full border border-amber-500/20">
                ${prod.category.toUpperCase()}
              </span>
              <span class="text-[11px] ${prod.inStock ? 'text-emerald-400' : 'text-slate-500'} flex items-center">
                ${prod.inStock ? `Dostępny (${prod.deliveryTime})` : 'Na zamówienie'}
              </span>
            </div>

            <h4 class="text-base font-bold text-white">${prod.name}</h4>
            <div class="text-xs text-slate-400 mt-1">${prod.mint}</div>

            <div class="bg-slate-900/60 p-2.5 rounded-xl border border-slate-800/80 my-3 text-xs space-y-1">
              <div class="flex justify-between">
                <span class="text-slate-400">Masa kruszcu:</span>
                <span class="font-mono text-slate-200 font-bold">${prod.unit}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Próba złota:</span>
                <span class="font-mono text-amber-400 font-semibold">${prod.purity}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">Marża mennicza:</span>
                <span class="font-mono text-slate-300">+${prod.premiumPercent}%</span>
              </div>
            </div>

            <p class="text-xs text-slate-400 line-clamp-2">
              ${prod.description}
            </p>
          </div>

          <div class="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between">
            <div>
              <span class="text-[10px] text-slate-400 uppercase tracking-wider block">Cena:</span>
              <span class="text-lg font-extrabold text-amber-400 font-mono">${this.appState.formatMoney(totalCostPLN)}</span>
            </div>
            <button class="btn-buy-product btn-gold px-3.5 py-2 rounded-xl text-xs font-bold flex items-center space-x-1" data-id="${prod.id}">
              <i data-lucide="plus" class="w-3.5 h-3.5"></i>
              <span>Kup</span>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  renderPortfolio() {
    const metrics = this.appState.getPortfolioMetrics();
    const spotGram = this.appState.market.baseSpotOuncePLN / 31.1035;

    const weightEl = document.getElementById('port-total-weight-g');
    if (weightEl) weightEl.textContent = `${metrics.totalGrams.toFixed(2)} g`;
    const investedEl = document.getElementById('port-total-invested');
    if (investedEl) investedEl.textContent = this.appState.formatMoney(metrics.totalInvestedPLN);
    const marketValEl = document.getElementById('port-total-market-val');
    if (marketValEl) marketValEl.textContent = this.appState.formatMoney(metrics.totalValuePLN);
    const profitEl = document.getElementById('port-total-profit');
    if (profitEl) {
      const isProf = metrics.profitLossPLN >= 0;
      profitEl.textContent = `${isProf ? '+' : ''}${this.appState.formatMoney(metrics.profitLossPLN)}`;
      profitEl.className = `text-lg font-bold font-mono ${isProf ? 'text-emerald-400' : 'text-rose-400'}`;
    }

    const countEl = document.getElementById('portfolio-positions-count');
    if (countEl) countEl.textContent = `${this.appState.portfolio.items.length} aktywne pozycje`;

    const tbody = document.getElementById('portfolio-table-body');
    if (!tbody) return;

    if (this.appState.portfolio.items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="py-8 text-center text-slate-500 font-sans text-xs">
            Twój portfel jest pusty. Kup pierwszą sztabkę lub złoto ułamkowe w zakładce Rynek!
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = this.appState.portfolio.items.map(item => {
      const totalItemGrams = item.weightGrams * (item.quantity || 1);
      const currentVal = totalItemGrams * spotGram;
      const invested = (item.buyPricePerUnitPLN || 0) * (item.quantity || 1);
      const gain = currentVal - invested;
      const gainPercent = invested > 0 ? (gain / invested) * 100 : 0;
      const isGain = gain >= 0;

      return `
        <tr class="hover:bg-slate-900/50 transition-colors">
          <td class="py-3.5 px-4">
            <div class="font-bold text-slate-200 font-sans">${item.name}</div>
            <div class="text-[10px] text-slate-400">ID: ${item.serialNumber || item.id}</div>
          </td>
          <td class="py-3.5 px-4 text-slate-300">
            <div>${item.mint}</div>
            <div class="text-[10px] text-amber-500">${item.purity}</div>
          </td>
          <td class="py-3.5 px-4 text-slate-200 font-bold">
            ${totalItemGrams.toFixed(2)} g 
            <span class="text-slate-400 text-[10px] font-normal font-sans">(${item.quantity}x)</span>
          </td>
          <td class="py-3.5 px-4 text-slate-300">
            ${this.appState.formatMoney(invested)}
          </td>
          <td class="py-3.5 px-4 text-amber-400 font-bold">
            ${this.appState.formatMoney(currentVal)}
          </td>
          <td class="py-3.5 px-4 font-bold ${isGain ? 'text-emerald-400' : 'text-rose-400'}">
            ${isGain ? '+' : ''}${this.appState.formatMoney(gain)}
            <span class="text-[10px] block font-normal">(${isGain ? '+' : ''}${gainPercent.toFixed(1)}%)</span>
          </td>
          <td class="py-3.5 px-4">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${item.storageType === 'skarbca' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'}">
              ${item.storageType === 'skarbca' ? 'Skarbiec Kl. IX' : 'Dostarczono'}
            </span>
          </td>
          <td class="py-3.5 px-4 text-right">
            <button class="btn-sell-portfolio-item px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-emerald-600 hover:text-slate-950 text-slate-200 font-bold text-xs transition-colors" data-id="${item.id}">
              Sprzedaj
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  renderHistory() {
    const tbody = document.getElementById('history-table-body');
    if (!tbody) return;

    if (this.appState.portfolio.transactions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-slate-500 font-sans text-xs">Brak zarejestrowanych transakcji</td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = this.appState.portfolio.transactions.map(tx => {
      const isBuy = tx.type === 'KUPNO';
      const isDeposit = tx.type === 'WPŁATA';
      const typeBadgeClass = isBuy 
        ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' 
        : isDeposit 
          ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
          : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';

      return `
        <tr class="hover:bg-slate-900/50 transition-colors">
          <td class="py-3.5 px-4 text-slate-400">
            <div class="text-slate-200 font-bold">${tx.id}</div>
            <div class="text-[10px]">${tx.date}</div>
          </td>
          <td class="py-3.5 px-4">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${typeBadgeClass}">
              ${tx.type}
            </span>
          </td>
          <td class="py-3.5 px-4 font-sans text-slate-200 font-medium">
            ${tx.itemName}
          </td>
          <td class="py-3.5 px-4 text-amber-400">
            ${tx.weightGrams > 0 ? `${tx.weightGrams.toFixed(2)} g` : '—'}
          </td>
          <td class="py-3.5 px-4 font-bold text-slate-200">
            ${this.appState.formatMoney(tx.amountPLN)}
          </td>
          <td class="py-3.5 px-4 font-sans text-xs">
            <span class="text-emerald-400 flex items-center">
              <i data-lucide="check-circle" class="w-3.5 h-3.5 mr-1"></i>
              ${tx.status}
            </span>
          </td>
          <td class="py-3.5 px-4 text-right">
            <button class="btn-download-cert text-slate-400 hover:text-amber-400 transition-colors p-1" title="Pobierz certyfikat transakcji (PDF)" data-txid="${tx.id}">
              <i data-lucide="file-text" class="w-4 h-4"></i>
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  initSavingsCalculator() {
    const rangeInit = document.getElementById('calc-range-initial');
    const rangeMonth = document.getElementById('calc-range-monthly');
    const rangeYears = document.getElementById('calc-range-years');
    const rangeRate = document.getElementById('calc-range-rate');

    const updateCalc = () => {
      const initAmount = parseFloat(rangeInit.value) || 0;
      const monthAmount = parseFloat(rangeMonth.value) || 0;
      const years = parseInt(rangeYears.value) || 1;
      const goldAnnualRate = (parseFloat(rangeRate.value) || 8.5) / 100;
      const depositAnnualRate = 0.035;

      document.getElementById('calc-val-initial').textContent = `${new Intl.NumberFormat('pl-PL').format(initAmount)} zł`;
      document.getElementById('calc-val-monthly').textContent = `${new Intl.NumberFormat('pl-PL').format(monthAmount)} zł / mies.`;
      document.getElementById('calc-val-years').textContent = `${years} ${years === 1 ? 'rok' : (years >= 2 && years <= 4) ? 'lata' : 'lat'}`;
      document.getElementById('calc-val-rate').textContent = `${(goldAnnualRate * 100).toFixed(1)}%`;

      const totalContributions = initAmount + (monthAmount * 12 * years);
      document.getElementById('calc-total-contributions').textContent = `${new Intl.NumberFormat('pl-PL').format(totalContributions)} zł`;

      const yearLabels = [];
      const goldSeries = [];
      const depositSeries = [];
      const contribSeries = [];

      let currentGoldVal = initAmount;
      let currentDepositVal = initAmount;
      let currentContrib = initAmount;

      yearLabels.push('Start');
      goldSeries.push(Math.round(currentGoldVal));
      depositSeries.push(Math.round(currentDepositVal));
      contribSeries.push(Math.round(currentContrib));

      for (let y = 1; y <= years; y++) {
        for (let m = 1; m <= 12; m++) {
          currentGoldVal = (currentGoldVal + monthAmount) * (1 + goldAnnualRate / 12);
          currentDepositVal = (currentDepositVal + monthAmount) * (1 + depositAnnualRate / 12);
          currentContrib += monthAmount;
        }

        yearLabels.push(`${y} r.`);
        goldSeries.push(Math.round(currentGoldVal));
        depositSeries.push(Math.round(currentDepositVal));
        contribSeries.push(Math.round(currentContrib));
      }

      const finalGold = goldSeries[goldSeries.length - 1];
      const finalDeposit = depositSeries[depositSeries.length - 1];
      const goldGain = finalGold - totalContributions;
      const goldGainPct = totalContributions > 0 ? ((goldGain / totalContributions) * 100).toFixed(0) : 0;

      document.getElementById('calc-final-gold-val').textContent = `${new Intl.NumberFormat('pl-PL').format(finalGold)} zł`;
      document.getElementById('calc-gold-gain').textContent = `+${new Intl.NumberFormat('pl-PL').format(goldGain)} zł (+${goldGainPct}%)`;
      document.getElementById('calc-final-deposit-val').textContent = `${new Intl.NumberFormat('pl-PL').format(finalDeposit)} zł`;
      document.getElementById('calc-final-cash-val').textContent = `${new Intl.NumberFormat('pl-PL').format(totalContributions)} zł`;

      const spotPerGram = this.appState.market.baseSpotOuncePLN / 31.1035;
      const approxGrams = finalGold / spotPerGram;
      const approxOz = approxGrams / 31.1035;
      document.getElementById('calc-accumulated-grams').textContent = `${approxGrams.toFixed(1)} g (≈ ${approxOz.toFixed(1)} oz t)`;

      const projectionData = {
        years: yearLabels,
        goldValues: goldSeries,
        depositValues: depositSeries,
        contributions: contribSeries
      };

      if (!this.chartManager.savingsChart) {
        this.chartManager.initSavingsChart('savingsProjectionChart', projectionData);
      } else {
        this.chartManager.updateSavingsChart(projectionData);
      }
    };

    [rangeInit, rangeMonth, rangeYears, rangeRate].forEach(el => {
      if (el) el.addEventListener('input', updateCalc);
    });

    updateCalc();
  }

  bindEvents() {
    document.querySelectorAll('.nav-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        const targetTabId = tabBtn.getAttribute('data-tab');
        this.switchTab(targetTabId);
      });
    });

    document.querySelectorAll('.nav-switch-to-catalog').forEach(btn => {
      btn.addEventListener('click', () => this.switchTab('tab-catalog'));
    });
    document.querySelectorAll('.nav-switch-to-dashboard').forEach(btn => {
      btn.addEventListener('click', () => this.switchTab('tab-dashboard'));
    });
    const logo = document.getElementById('nav-brand-logo');
    if (logo) logo.addEventListener('click', () => this.switchTab('tab-dashboard'));

    document.querySelectorAll('.currency-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const curr = btn.getAttribute('data-currency');
        document.querySelectorAll('.currency-btn').forEach(b => {
          b.className = 'currency-btn px-2.5 py-1 rounded-md transition-all text-slate-400 hover:text-slate-200';
        });
        btn.className = 'currency-btn px-2.5 py-1 rounded-md transition-all bg-amber-500 text-slate-950 font-bold';
        this.appState.setCurrency(curr);
      });
    });

    document.querySelectorAll('.unit-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const unit = btn.getAttribute('data-unit');
        document.querySelectorAll('.unit-btn').forEach(b => {
          b.className = 'unit-btn px-2.5 py-1 rounded-md text-slate-400 hover:text-slate-200';
        });
        btn.className = 'unit-btn px-2.5 py-1 rounded-md text-amber-400 bg-amber-500/10 font-bold';
        this.appState.setUnit(unit);
      });
    });

    document.querySelectorAll('.timeframe-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tf = btn.getAttribute('data-tf');
        document.querySelectorAll('.timeframe-btn').forEach(b => {
          b.className = 'timeframe-btn px-3 py-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800';
        });
        btn.className = 'timeframe-btn px-3 py-1.5 rounded-lg bg-amber-500 text-slate-950 font-bold';
        this.appState.setTimeframe(tf);
      });
    });

    document.querySelectorAll('.catalog-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const filter = btn.getAttribute('data-filter');
        document.querySelectorAll('.catalog-filter-btn').forEach(b => {
          b.className = 'catalog-filter-btn px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-white bg-slate-900 border border-slate-800';
        });
        btn.className = 'catalog-filter-btn active px-3.5 py-1.5 rounded-lg text-xs font-bold bg-amber-500 text-slate-950';
        this.renderCatalog(filter);
        if (window.lucide) window.lucide.createIcons();
      });
    });

    const simBtn = document.getElementById('toggle-live-sim');
    if (simBtn) {
      simBtn.addEventListener('click', () => {
        this.appState.toggleLiveSimulation();
        const text = document.getElementById('sim-status-text');
        if (text) {
          text.textContent = this.appState.isLiveSimulationActive ? 'Live: ON' : 'Live: OFF';
        }
        this.showToast(this.appState.isLiveSimulationActive ? 'Symulacja notowań na żywo WŁĄCZONA' : 'Symulacja notowań na żywo ZATRZYMANA', 'info');
      });
    }

    document.querySelectorAll('.quick-amt-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const amt = parseFloat(chip.getAttribute('data-amt'));
        const input = document.getElementById('quick-order-amount');
        if (input) {
          input.value = amt;
          this.renderQuickTerminal();
        }
      });
    });

    const quickInput = document.getElementById('quick-order-amount');
    if (quickInput) {
      quickInput.addEventListener('input', () => this.renderQuickTerminal());
    }

    const termBuyBtn = document.getElementById('terminal-mode-buy');
    const termSellBtn = document.getElementById('terminal-mode-sell');
    const orderBtnText = document.getElementById('btn-quick-order-text');

    if (termBuyBtn && termSellBtn) {
      termBuyBtn.addEventListener('click', () => {
        this.terminalMode = 'buy';
        termBuyBtn.className = 'py-2 rounded-lg bg-amber-500 text-slate-950 shadow-md font-bold';
        termSellBtn.className = 'py-2 rounded-lg text-slate-400 hover:text-white transition-colors';
        if (orderBtnText) orderBtnText.textContent = 'Potwierdź zakup złota';
      });

      termSellBtn.addEventListener('click', () => {
        this.terminalMode = 'sell';
        termSellBtn.className = 'py-2 rounded-lg bg-emerald-500 text-slate-950 shadow-md font-bold';
        termBuyBtn.className = 'py-2 rounded-lg text-slate-400 hover:text-white transition-colors';
        if (orderBtnText) orderBtnText.textContent = 'Potwierdź natychmiastową sprzedaż';
      });
    }

    const btnQuickOrder = document.getElementById('btn-execute-quick-order');
    if (btnQuickOrder) {
      btnQuickOrder.addEventListener('click', () => {
        const amountPLN = parseFloat(document.getElementById('quick-order-amount').value) || 0;
        const storageOption = document.querySelector('input[name="quick_storage"]:checked')?.value || 'skarbca';
        
        if (this.terminalMode === 'buy') {
          if (amountPLN < 50) {
            this.showToast('Minimalna kwota zlecenia to 50 zł.', 'error');
            return;
          }
          const pricePerGram = this.appState.market.baseSpotOuncePLN / 31.1035;
          const grams = amountPLN / pricePerGram;

          try {
            this.appState.buyItem({
              productId: 'digital-fractional',
              name: 'Złoto Cyfrowe Ułamkowe (LBMA 999.9)',
              category: 'cyfrowe',
              weightGrams: grams,
              weightUnit: `${grams.toFixed(2)} g`,
              quantity: 1,
              totalCostPLN: amountPLN,
              mint: 'Mennica Akredytowana LBMA',
              purity: '999.9',
              storageType: storageOption
            });

            this.showToast(`Pomyślnie zakupiono ${grams.toFixed(3)} g czystego złota za ${this.appState.formatMoney(amountPLN)}!`, 'success');
          } catch (err) {
            this.showToast(err.message, 'error');
          }
        } else {
          const digitalItem = this.appState.portfolio.items.find(i => i.category === 'cyfrowe');
          if (!digitalItem) {
            this.showToast('Nie posiadasz złota cyfrowego do sprzedaży.', 'error');
            return;
          }
          try {
            const soldVal = this.appState.sellItem(digitalItem.id, 1);
            this.showToast(`Pomyślnie sprzedano złoto cyfrowe za ${this.appState.formatMoney(soldVal)}!`, 'success');
          } catch (err) {
            this.showToast(err.message, 'error');
          }
        }
      });
    }

    document.addEventListener('click', (e) => {
      const buyBtn = e.target.closest('.btn-buy-product');
      if (buyBtn) {
        const prodId = buyBtn.getAttribute('data-id');
        this.openBuyProductModal(prodId);
      }

      const sellBtn = e.target.closest('.btn-sell-portfolio-item');
      if (sellBtn) {
        const itemId = sellBtn.getAttribute('data-id');
        this.openSellModal(itemId);
      }

      const certBtn = e.target.closest('.btn-download-cert');
      if (certBtn) {
        const txId = certBtn.getAttribute('data-txid');
        this.downloadTransactionReceipt(txId);
      }
    });

    const closeBuyModal = document.getElementById('modal-buy-close');
    if (closeBuyModal) closeBuyModal.addEventListener('click', () => this.closeBuyProductModal());

    const closeSellModal = document.getElementById('modal-sell-close');
    if (closeSellModal) closeSellModal.addEventListener('click', () => this.closeSellModal());

    const closeDepModal = document.getElementById('modal-deposit-close');
    if (closeDepModal) closeDepModal.addEventListener('click', () => this.closeDepositModal());

    const btnQtyMinus = document.getElementById('btn-qty-minus');
    const btnQtyPlus = document.getElementById('btn-qty-plus');
    if (btnQtyMinus) {
      btnQtyMinus.addEventListener('click', () => {
        if (this.buyModalQuantity > 1) {
          this.buyModalQuantity--;
          this.updateBuyModalCosts();
        }
      });
    }
    if (btnQtyPlus) {
      btnQtyPlus.addEventListener('click', () => {
        this.buyModalQuantity++;
        this.updateBuyModalCosts();
      });
    }

    const btnConfirmBuy = document.getElementById('btn-modal-confirm-buy');
    if (btnConfirmBuy) {
      btnConfirmBuy.addEventListener('click', () => {
        if (!this.selectedBuyProduct) return;
        const spotGram = this.appState.market.baseSpotOuncePLN / 31.1035;
        const baseCost = this.selectedBuyProduct.weightGrams * spotGram;
        const unitCostPLN = baseCost * (1 + this.selectedBuyProduct.premiumPercent / 100);
        const totalCostPLN = unitCostPLN * this.buyModalQuantity;
        const deliveryType = document.querySelector('input[name="modal_delivery"]:checked')?.value || 'skarbca';

        try {
          this.appState.buyItem({
            productId: this.selectedBuyProduct.id,
            name: this.selectedBuyProduct.name,
            category: this.selectedBuyProduct.category,
            weightGrams: this.selectedBuyProduct.weightGrams,
            weightUnit: this.selectedBuyProduct.unit,
            quantity: this.buyModalQuantity,
            totalCostPLN: totalCostPLN,
            mint: this.selectedBuyProduct.mint,
            purity: this.selectedBuyProduct.purity,
            storageType: deliveryType
          });

          this.closeBuyProductModal();
          this.showToast(`Pomyślnie zakupiono ${this.selectedBuyProduct.name} (x${this.buyModalQuantity})!`, 'success');
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    const btnConfirmSell = document.getElementById('btn-modal-confirm-sell');
    if (btnConfirmSell) {
      btnConfirmSell.addEventListener('click', () => {
        if (!this.selectedSellItem) return;
        try {
          const payout = this.appState.sellItem(this.selectedSellItem.id, 1);
          this.closeSellModal();
          this.showToast(`Sprzedaż zrealizowana. Do salda dodano ${this.appState.formatMoney(payout)}.`, 'success');
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    const openDepositBtn = document.getElementById('btn-open-deposit');
    if (openDepositBtn) openDepositBtn.addEventListener('click', () => this.openDepositModal());

    const portDepositBtn = document.getElementById('btn-portfolio-deposit');
    if (portDepositBtn) portDepositBtn.addEventListener('click', () => this.openDepositModal());

    document.querySelectorAll('.deposit-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const amt = parseFloat(chip.getAttribute('data-amt'));
        const input = document.getElementById('deposit-amount-input');
        if (input) input.value = amt;
      });
    });

    const btnConfirmDep = document.getElementById('btn-modal-confirm-deposit');
    if (btnConfirmDep) {
      btnConfirmDep.addEventListener('click', () => {
        const amt = parseFloat(document.getElementById('deposit-amount-input').value) || 0;
        const method = document.querySelector('input[name="deposit_method"]:checked')?.value || 'BLIK';
        if (amt <= 0) {
          this.showToast('Wprowadź prawidłową kwotę zasilenia.', 'error');
          return;
        }
        this.appState.depositCash(amt, method);
        this.closeDepositModal();
        this.showToast(`Pomyślnie wpłacono ${this.appState.formatMoney(amt)} metodą ${method}!`, 'success');
      });
    }

    const resetBtn = document.getElementById('btn-reset-demo');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        if (confirm('Czy na pewno chcesz przywrócić początkowy stan demonstracyjny portfela i środków?')) {
          this.appState.resetDemoData();
          this.showToast('Przywrócono domyślne dane demonstracyjne.', 'info');
        }
      });
    }

    const exportCsvBtn = document.getElementById('btn-export-csv');
    if (exportCsvBtn) {
      exportCsvBtn.addEventListener('click', () => this.exportTransactionsCSV());
    }
  }

  switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(b => {
      b.classList.remove('active');
      b.classList.add('text-slate-400');
    });

    const activeContent = document.getElementById(tabId);
    if (activeContent) activeContent.classList.remove('hidden');

    const activeBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
    if (activeBtn) {
      activeBtn.classList.add('active');
      activeBtn.classList.remove('text-slate-400');
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (tabId === 'tab-portfolio') {
      this.renderPortfolio();
      this.chartManager.updatePortfolioChart();
    } else if (tabId === 'tab-catalog') {
      this.renderCatalog();
    } else if (tabId === 'tab-history') {
      this.renderHistory();
    }

    if (window.lucide) window.lucide.createIcons();
  }

  openBuyProductModal(productId) {
    const product = this.appState.catalog.find(p => p.id === productId);
    if (!product) return;

    this.selectedBuyProduct = product;
    this.buyModalQuantity = 1;

    document.getElementById('modal-buy-title').textContent = product.name;
    document.getElementById('modal-buy-subtitle').textContent = `${product.mint} (Próba ${product.purity})`;
    document.getElementById('modal-buy-wallet-avail').textContent = this.appState.formatMoney(this.appState.portfolio.cashBalancePLN);

    this.updateBuyModalCosts();

    const modal = document.getElementById('modal-buy-product');
    if (modal) modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  updateBuyModalCosts() {
    if (!this.selectedBuyProduct) return;
    const spotGram = this.appState.market.baseSpotOuncePLN / 31.1035;
    const baseCost = this.selectedBuyProduct.weightGrams * spotGram;
    const unitCostPLN = baseCost * (1 + this.selectedBuyProduct.premiumPercent / 100);
    const totalCostPLN = unitCostPLN * this.buyModalQuantity;

    document.getElementById('modal-buy-unit-price').textContent = this.appState.formatMoney(unitCostPLN);
    document.getElementById('modal-buy-qty').textContent = this.buyModalQuantity;
    document.getElementById('modal-buy-total-cost').textContent = this.appState.formatMoney(totalCostPLN);
  }

  closeBuyProductModal() {
    const modal = document.getElementById('modal-buy-product');
    if (modal) modal.classList.add('hidden');
    this.selectedBuyProduct = null;
  }

  openSellModal(portfolioItemId) {
    const item = this.appState.portfolio.items.find(i => i.id === portfolioItemId);
    if (!item) return;

    this.selectedSellItem = item;
    const currentSpotPerGram = this.appState.market.baseSpotOuncePLN / 31.1035;
    const sellValuePLN = item.weightGrams * currentSpotPerGram * 0.99;

    document.getElementById('modal-sell-item-name').textContent = `${item.name} (${item.weightUnit})`;
    document.getElementById('modal-sell-spot').textContent = this.appState.formatMoney(this.appState.market.baseSpotOuncePLN);
    document.getElementById('modal-sell-payout').textContent = this.appState.formatMoney(sellValuePLN);

    const modal = document.getElementById('modal-sell-product');
    if (modal) modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closeSellModal() {
    const modal = document.getElementById('modal-sell-product');
    if (modal) modal.classList.add('hidden');
    this.selectedSellItem = null;
  }

  openDepositModal() {
    const modal = document.getElementById('modal-deposit');
    if (modal) modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  closeDepositModal() {
    const modal = document.getElementById('modal-deposit');
    if (modal) modal.classList.add('hidden');
  }

  downloadTransactionReceipt(txId) {
    const tx = this.appState.portfolio.transactions.find(t => t.id === txId);
    if (!tx) return;

    const text = `
=====================================================
          AURUM INVEST S.A. - POTWIERDZENIE TRANSAKCJI
=====================================================
Identyfikator transakcji: ${tx.id}
Data i czas:              ${tx.date}
Typ operacji:             ${tx.type}
Przedmiot:                ${tx.itemName}
Masa kruszcu:             ${tx.weightGrams > 0 ? tx.weightGrams + ' g' : 'N/D'}
Czystość kruszcu:         Próba 999.9 (Akredytacja LBMA)
Kwota rozliczenia:        ${tx.amountPLN.toFixed(2)} PLN
Status transakcji:        ${tx.status}
Skrót kryptograficzny:    ${tx.txHash}
Depozytariusz:            Skarbiec Klasy IX AURUM Polska
=====================================================
Dokument wygenerowany elektronicznie, nie wymaga podpisu.
    `.trim();

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Certyfikat_Transakcji_${tx.id}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    this.showToast(`Pobrano certyfikat dla transakcji ${tx.id}`, 'info');
  }

  exportTransactionsCSV() {
    const rows = [
      ['ID', 'Data', 'Typ', 'Nazwa', 'Masa (g)', 'Kwota (PLN)', 'Status', 'Hash']
    ];

    this.appState.portfolio.transactions.forEach(tx => {
      rows.push([
        tx.id,
        tx.date,
        tx.type,
        `"${tx.itemName}"`,
        tx.weightGrams,
        tx.amountPLN,
        tx.status,
        tx.txHash
      ]);
    });

    const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Aurum_Historia_Transakcji_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    this.showToast('Wyeksportowano historię do pliku CSV', 'info');
  }

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const borderClass = type === 'success' 
      ? 'border-emerald-500/50 bg-slate-900/95 text-emerald-400' 
      : type === 'error'
        ? 'border-rose-500/50 bg-slate-900/95 text-rose-400'
        : 'border-amber-500/50 bg-slate-900/95 text-amber-300';

    toast.className = `p-4 rounded-xl border ${borderClass} shadow-2xl backdrop-blur-md text-xs font-semibold flex items-center space-x-2.5 transform transition-all duration-300 translate-y-2 opacity-0 pointer-events-auto max-w-sm`;
    
    const iconName = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-triangle' : 'info';
    toast.innerHTML = `
      <i data-lucide="${iconName}" class="w-4 h-4 flex-shrink-0"></i>
      <span class="flex-1">${message}</span>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.classList.remove('translate-y-2', 'opacity-0');
    }, 10);

    setTimeout(() => {
      toast.classList.add('opacity-0', 'translate-y-2');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const app = new AurumApp();
  app.init();
});
