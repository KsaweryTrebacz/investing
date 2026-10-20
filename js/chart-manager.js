/**
 * Zarządzanie wykresami (Chart.js) dla aplikacji Aurum Invest
 */

class ChartManager {
  constructor(appState) {
    this.appState = appState;
    this.mainChart = null;
    this.portfolioChart = null;
    this.savingsChart = null;
  }

  initMainChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(217, 119, 6, 0.45)');
    gradient.addColorStop(0.5, 'rgba(234, 179, 8, 0.15)');
    gradient.addColorStop(1, 'rgba(15, 23, 42, 0.0)');

    const data = this.getMainChartData(this.appState.activeTimeframe);

    this.mainChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [{
          label: 'Kurs złota spot',
          data: data.prices,
          borderColor: '#F59E0B',
          borderWidth: 2.5,
          pointBackgroundColor: '#F59E0B',
          pointBorderColor: '#0F172A',
          pointHoverRadius: 6,
          pointHoverBackgroundColor: '#FDE68A',
          pointHoverBorderColor: '#F59E0B',
          pointHoverBorderWidth: 2,
          pointRadius: 3,
          tension: 0.35,
          fill: true,
          backgroundColor: gradient
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(245, 158, 11, 0.4)',
            borderWidth: 1,
            titleFont: { size: 12, weight: 'bold' },
            bodyFont: { size: 13 },
            padding: 12,
            displayColors: false,
            callbacks: {
              label: (context) => {
                const val = context.parsed.y;
                return `Cena: ${this.appState.formatMoney(val)}`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false,
              drawBorder: false
            },
            ticks: {
              color: '#94A3B8',
              font: { size: 11 }
            }
          },
          y: {
            position: 'right',
            grid: {
              color: 'rgba(51, 65, 85, 0.3)',
              drawBorder: false
            },
            ticks: {
              color: '#94A3B8',
              font: { size: 11 },
              callback: (value) => {
                const curr = this.appState.settings.currency;
                const sym = this.appState.market.currencySymbols[curr] || curr;
                if (curr === 'PLN') return `${Math.round(value)} zł`;
                return `${sym}${Math.round(value)}`;
              }
            }
          }
        }
      }
    });
  }

  getMainChartData(timeframe) {
    const historical = window.AurumData.HISTORICAL_CHART_DATA;
    const raw = historical[timeframe] || historical['24h'];
    const rate = this.appState.market.exchangeRates[this.appState.settings.currency] || 1;
    
    let unitMultiplier = 1;
    if (this.appState.activeUnit === 'g') {
      unitMultiplier = 1 / 31.1035;
    } else if (this.appState.activeUnit === 'kg') {
      unitMultiplier = (1 / 31.1035) * 1000;
    }

    const convertedPrices = raw.prices.map((p, idx) => {
      const basePrice = (idx === raw.prices.length - 1) ? this.appState.market.baseSpotOuncePLN : p;
      return Number((basePrice * rate * unitMultiplier).toFixed(2));
    });

    return {
      labels: raw.labels,
      prices: convertedPrices
    };
  }

  updateMainChart() {
    if (!this.mainChart) return;
    const data = this.getMainChartData(this.appState.activeTimeframe);
    this.mainChart.data.labels = data.labels;
    this.mainChart.data.datasets[0].data = data.prices;
    this.mainChart.update('none');
  }

  updateLiveTick(newPricePLN) {
    if (!this.mainChart) return;
    const rate = this.appState.market.exchangeRates[this.appState.settings.currency] || 1;
    let unitMultiplier = 1;
    if (this.appState.activeUnit === 'g') unitMultiplier = 1 / 31.1035;
    else if (this.appState.activeUnit === 'kg') unitMultiplier = (1 / 31.1035) * 1000;

    const dataset = this.mainChart.data.datasets[0];
    const len = dataset.data.length;
    if (len > 0) {
      dataset.data[len - 1] = Number((newPricePLN * rate * unitMultiplier).toFixed(2));
      this.mainChart.update('none');
    }
  }

  initPortfolioChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const allocation = this.calculateAllocation();

    this.portfolioChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Sztabki mennicze', 'Monety bulionowe', 'Złoto cyfrowe'],
        datasets: [{
          data: [allocation.bars, allocation.coins, allocation.digital],
          backgroundColor: [
            '#F59E0B',
            '#EAB308',
            '#06B6D4'
          ],
          borderColor: '#0F172A',
          borderWidth: 3,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#94A3B8',
              padding: 16,
              font: { size: 12 }
            }
          },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(245, 158, 11, 0.4)',
            borderWidth: 1,
            callbacks: {
              label: (context) => {
                const grams = context.parsed;
                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                const percent = total > 0 ? ((grams / total) * 100).toFixed(1) : 0;
                return ` ${grams.toFixed(1)}g (${percent}%)`;
              }
            }
          }
        },
        cutout: '72%'
      }
    });
  }

  calculateAllocation() {
    let bars = 0;
    let coins = 0;
    let digital = 0;

    this.appState.portfolio.items.forEach(item => {
      const g = (item.weightGrams || 0) * (item.quantity || 1);
      if (item.category === 'sztabka') bars += g;
      else if (item.category === 'moneta') coins += g;
      else if (item.category === 'cyfrowe') digital += g;
    });

    return { bars, coins, digital };
  }

  updatePortfolioChart() {
    if (!this.portfolioChart) return;
    const alloc = this.calculateAllocation();
    this.portfolioChart.data.datasets[0].data = [alloc.bars, alloc.coins, alloc.digital];
    this.portfolioChart.update();
  }

  initSavingsChart(canvasId, projectionData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    this.savingsChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: projectionData.years,
        datasets: [
          {
            label: 'Wartość złota (prognoza ~8.5% r/r)',
            data: projectionData.goldValues,
            borderColor: '#F59E0B',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            fill: true,
            tension: 0.3,
            borderWidth: 2.5
          },
          {
            label: 'Tradycyjna lokata (~3.5% po podatku)',
            data: projectionData.depositValues,
            borderColor: '#3B82F6',
            backgroundColor: 'transparent',
            borderDash: [5, 5],
            tension: 0.3,
            borderWidth: 2
          },
          {
            label: 'Wpłacony kapitał',
            data: projectionData.contributions,
            borderColor: '#64748B',
            backgroundColor: 'transparent',
            tension: 0.1,
            borderWidth: 1.5
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#94A3B8', font: { size: 11 } }
          },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            borderColor: 'rgba(245, 158, 11, 0.4)',
            borderWidth: 1,
            callbacks: {
              label: (context) => `${context.dataset.label}: ${new Intl.NumberFormat('pl-PL').format(Math.round(context.parsed.y))} zł`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94A3B8' }
          },
          y: {
            position: 'right',
            grid: { color: 'rgba(51, 65, 85, 0.25)' },
            ticks: {
              color: '#94A3B8',
              callback: (val) => `${Math.round(val / 1000)} tys. zł`
            }
          }
        }
      }
    });
  }

  updateSavingsChart(projectionData) {
    if (!this.savingsChart) return;
    this.savingsChart.data.labels = projectionData.years;
    this.savingsChart.data.datasets[0].data = projectionData.goldValues;
    this.savingsChart.data.datasets[1].data = projectionData.depositValues;
    this.savingsChart.data.datasets[2].data = projectionData.contributions;
    this.savingsChart.update();
  }
}

window.ChartManager = ChartManager;
