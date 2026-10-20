/**
 * Dane początkowe dla aplikacji inwestowania w złoto Aurum Invest
 */

const INITIAL_MARKET_DATA = {
  // Ceny bazowe w PLN za 1 uncję trojańską (oz t = 31.1035 g)
  baseSpotOuncePLN: 10845.50,
  dayChangePercent: 1.42,
  dayChangePLN: 151.80,
  dayHighPLN: 10890.00,
  dayLowPLN: 10695.20,
  spreadPercent: 1.2, // spread menniczy
  
  // Kursy walut
  exchangeRates: {
    PLN: 1.0,
    USD: 0.252, // 1 PLN = 0.252 USD
    EUR: 0.233  // 1 PLN = 0.233 EUR
  },
  
  currencySymbols: {
    PLN: 'zł',
    USD: '$',
    EUR: '€'
  }
};

const INITIAL_USER_PORTFOLIO = {
  cashBalancePLN: 14500.00,
  items: [
    {
      id: 'port-1',
      productId: 'bar-valcambi-1oz',
      name: 'Sztabka Valcambi 1 oz',
      category: 'sztabka',
      mint: 'Valcambi Suisse (LBMA)',
      purity: '999.9 (24 karaty)',
      weightGrams: 31.1035,
      weightUnit: '1 oz (31.1g)',
      quantity: 2,
      buyPricePerUnitPLN: 10150.00,
      buyDate: '2024-03-15',
      storageType: 'skarbca',
      serialNumber: 'VC-892410-A'
    },
    {
      id: 'port-2',
      productId: 'coin-krugerrand-1oz',
      name: 'Moneta Krugerrand 1 oz',
      category: 'moneta',
      mint: 'South African Mint',
      purity: '916.6 (22 karaty)',
      weightGrams: 31.1035,
      weightUnit: '1 oz',
      quantity: 1,
      buyPricePerUnitPLN: 10320.00,
      buyDate: '2024-05-10',
      storageType: 'dom',
      serialNumber: 'KR-2024-0981'
    },
    {
      id: 'port-3',
      productId: 'digital-fractional',
      name: 'Złoto Skarbcowe Cyfrowe',
      category: 'cyfrowe',
      mint: 'C.Hafner / Depozyt Skarbcowy',
      purity: '999.9',
      weightGrams: 15.40,
      weightUnit: '15.40 g',
      quantity: 1,
      buyPricePerUnitPLN: 5120.00,
      buyDate: '2024-08-01',
      storageType: 'skarbca',
      serialNumber: 'AURUM-DIG-4412'
    }
  ],
  transactions: [
    {
      id: 'tx-101',
      date: '2024-08-01 14:32',
      type: 'KUPNO',
      itemName: 'Złoto Cyfrowe (15.40 g)',
      amountPLN: 5120.00,
      weightGrams: 15.40,
      status: 'Zrealizowano',
      txHash: '0x8f3c...b291'
    },
    {
      id: 'tx-100',
      date: '2024-05-10 11:15',
      type: 'KUPNO',
      itemName: 'Moneta Krugerrand 1 oz',
      amountPLN: 10320.00,
      weightGrams: 31.10,
      status: 'Dostarczono',
      txHash: '0x3a19...994e'
    },
    {
      id: 'tx-099',
      date: '2024-03-15 09:40',
      type: 'KUPNO',
      itemName: 'Sztabka Valcambi 1 oz (x2)',
      amountPLN: 20300.00,
      weightGrams: 62.20,
      status: 'Zabezpieczono w skarbcu',
      txHash: '0x7e21...112c'
    },
    {
      id: 'tx-098',
      date: '2024-01-10 16:00',
      type: 'WPŁATA',
      itemName: 'Zasilenie konta (BLIK)',
      amountPLN: 50000.00,
      weightGrams: 0,
      status: 'Zrealizowano',
      txHash: 'DEP-884102'
    }
  ]
};

const BULLION_CATALOG = [
  {
    id: 'bar-hafner-1g',
    name: 'Sztabka C.Hafner 1 g',
    category: 'sztabka',
    mint: 'C.Hafner (Niemcy)',
    purity: '999.9',
    weightGrams: 1.0,
    unit: '1 g',
    premiumPercent: 7.5,
    inStock: true,
    deliveryTime: '24h',
    badge: 'Na start',
    description: 'Najmniejsza sztabka inwestycyjna w bezpiecznym opakowaniu CertiPack z numerem seryjnym. Idealna na start lub prezent.'
  },
  {
    id: 'bar-valcambi-1oz',
    name: 'Sztabka Valcambi 1 oz',
    category: 'sztabka',
    mint: 'Valcambi Suisse (Szwajcaria)',
    purity: '999.9',
    weightGrams: 31.1035,
    unit: '1 oz (31.10g)',
    premiumPercent: 2.2,
    inStock: true,
    deliveryTime: '24h',
    badge: 'Bestseller',
    description: 'Najpopularniejszy standard inwestycyjny na świecie. Szwajcarska precyzja mennicza, pełna akredytacja LBMA.'
  },
  {
    id: 'bar-pamp-100g',
    name: 'Sztabka PAMP Fortuna 100 g',
    category: 'sztabka',
    mint: 'PAMP Suisse',
    purity: '999.9',
    weightGrams: 100.0,
    unit: '100 g',
    premiumPercent: 1.8,
    inStock: true,
    deliveryTime: '48h',
    badge: 'Premium',
    description: 'Legendarna sztabka z wizerunkiem rzymskiej bogini Fortuny. Najwyższy prestiż i natychmiastowa płynność na świecie.'
  },
  {
    id: 'coin-krugerrand-1oz',
    name: 'Moneta Krugerrand 1 oz',
    category: 'moneta',
    mint: 'South African Mint',
    purity: '916.6 (22K)',
    weightGrams: 31.1035,
    unit: '1 oz',
    premiumPercent: 2.8,
    inStock: true,
    deliveryTime: '24h',
    badge: 'Ikona Bulionu',
    description: 'Pierwsza i najbardziej rozpoznawalna moneta bulionowa globu. Domieszka miedzi zapewnia legendarną trwałość.'
  },
  {
    id: 'coin-philharmonic-1oz',
    name: 'Wiedeńscy Filharmonicy 1 oz',
    category: 'moneta',
    mint: 'Münze Österreich (Austria)',
    purity: '999.9',
    weightGrams: 31.1035,
    unit: '1 oz',
    premiumPercent: 2.5,
    inStock: true,
    deliveryTime: '24h',
    badge: 'Czyste 24K',
    description: 'Europejski hit bulionowy wybijany z czystego 24-karatowego złota. Oficjalny środek płatniczy Republiki Austrii.'
  },
  {
    id: 'coin-maple-1oz',
    name: 'Kanadyjski Liść Klonowy 1 oz',
    category: 'moneta',
    mint: 'Royal Canadian Mint',
    purity: '999.99',
    weightGrams: 31.1035,
    unit: '1 oz',
    premiumPercent: 2.6,
    inStock: true,
    deliveryTime: '24h',
    badge: 'Próba .99999',
    description: 'Najczystsza moneta bulionowa świata z zaawansowanymi radialnymi mikrograwerami laserowymi Bullion DNA.'
  },
  {
    id: 'bar-valcambi-1kg',
    name: 'Sztabka Odlewana Valcambi 1 kg',
    category: 'sztabka',
    mint: 'Valcambi Suisse',
    purity: '999.9',
    weightGrams: 1000.0,
    unit: '1 kg (1000g)',
    premiumPercent: 0.9,
    inStock: false,
    deliveryTime: '5-7 dni',
    badge: 'Dla Inwestorów',
    description: 'Instytucjonalny format inwestycyjny o minimalnej marży menniczej poniżej 1% ceny kruszcu.'
  }
];

const HISTORICAL_CHART_DATA = {
  '24h': {
    labels: ['09:00', '11:00', '13:00', '15:00', '17:00', '19:00', '21:00', '23:00', '03:00', '06:00', '09:00'],
    prices: [10695, 10720, 10710, 10745, 10790, 10780, 10815, 10830, 10810, 10835, 10845.50]
  },
  '7d': {
    labels: ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Dziś'],
    prices: [10520, 10580, 10610, 10590, 10720, 10750, 10845.50]
  },
  '1m': {
    labels: ['Tydz 1', 'Tydz 2', 'Tydz 3', 'Tydz 4', 'Obecnie'],
    prices: [10150, 10280, 10420, 10650, 10845.50]
  },
  '1y': {
    labels: ['Lis 23', 'Sty 24', 'Mar 24', 'Maj 24', 'Lip 24', 'Wrz 24', 'Paź 24'],
    prices: [8420, 8650, 9100, 9680, 9950, 10400, 10845.50]
  },
  '5y': {
    labels: ['2020', '2021', '2022', '2023', '2024'],
    prices: [6200, 6800, 7900, 8300, 10845.50]
  },
  'max': {
    labels: ['2005', '2008', '2011', '2015', '2018', '2021', '2024'],
    prices: [1400, 2400, 5200, 4300, 4800, 7100, 10845.50]
  }
};

window.AurumData = {
  INITIAL_MARKET_DATA,
  INITIAL_USER_PORTFOLIO,
  BULLION_CATALOG,
  HISTORICAL_CHART_DATA
};
