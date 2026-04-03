const MAX_ORDER_AMOUNT = 999999;
const CHART_MAX_POINTS = 240;
const QUICK_ADD_ALLOWED = new Set(['1', '5', '10', '100', 'max']);

const state = {
    markets: [],
    selectedMarket: null,
    side: 'BUY',
    outcome: 'UP',
    amount: 0,
    balance: 32.58,
    prices: new Array(CHART_MAX_POINTS),
    priceCount: 0,
    priceWriteIndex: 0,
    countdownSecs: 300
};

let chart;
let areaSeries;

function formatUsd(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatAmount(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '$0';
    return `$${number.toLocaleString(undefined, {
        minimumFractionDigits: Number.isInteger(number) ? 0 : 2,
        maximumFractionDigits: 2
    })}`;
}

function formatDate(value) {
    if (!value) return 'No schedule';
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return 'No schedule';
    return dt.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function updateAmount(delta) {
    if (delta === 'max') {
        state.amount = state.balance;
    } else {
        const numericDelta = Number(delta);
        if (!Number.isFinite(numericDelta) || numericDelta < 0) return;
        state.amount = Math.min(MAX_ORDER_AMOUNT, Math.max(0, state.amount + numericDelta));
    }
    renderAmount();
}

function renderAmount() {
    document.getElementById('amount-display').innerText = formatAmount(state.amount);
}

function renderActionButton() {
    const btn = document.getElementById('submit-order');
    btn.innerText = `${state.side === 'BUY' ? 'Buy' : 'Sell'} ${state.outcome}`;
}

function renderOutcomeButtons() {
    const up = document.getElementById('btn-up');
    const down = document.getElementById('btn-down');

    const yes = state.selectedMarket?.yes_price;
    const no = state.selectedMarket?.no_price;

    up.innerText = `Up ${typeof yes === 'number' ? Math.round(yes * 100) : '--'}¢`;
    down.innerText = `Down ${typeof no === 'number' ? Math.round(no * 100) : '--'}¢`;

    up.classList.toggle('active-up', state.outcome === 'UP');
    down.classList.toggle('active-down', state.outcome === 'DOWN');
}

function renderHeader() {
    const market = state.selectedMarket;
    document.getElementById('market-title').innerText = market?.title || 'Bitcoin Up or Down - 5 Minutes';
    document.getElementById('market-date').innerText = market ? formatDate(market.end_date) : 'No active market';
    const toBeat = market?.price_to_beat ?? null;
    document.getElementById('price-to-beat').innerText = formatUsd(toBeat);
}

function initChart() {
    const container = document.getElementById('price-chart');
    if (!container) return;

    chart = window.LightweightCharts.createChart(container, {
        layout: {
            background: { color: '#0b1623' },
            textColor: '#8fa1b6'
        },
        grid: {
            vertLines: { color: '#1b2a3b' },
            horzLines: { color: '#1b2a3b' }
        },
        rightPriceScale: {
            borderColor: '#1b2a3b'
        },
        timeScale: {
            borderColor: '#1b2a3b',
            timeVisible: true,
            secondsVisible: true
        },
        crosshair: {
            vertLine: { color: '#33506a' },
            horzLine: { color: '#33506a' }
        }
    });

    areaSeries = chart.addAreaSeries({
        lineColor: '#2ce58b',
        topColor: 'rgba(44, 229, 139, 0.35)',
        bottomColor: 'rgba(44, 229, 139, 0.04)',
        lineWidth: 2,
        priceLineColor: '#2ce58b'
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
        if (!chart) return;
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            chart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight
            });
        }, 150);
    });
}

function pushChartPoint(price) {
    if (!areaSeries) return;

    state.prices[state.priceWriteIndex] = {
        time: Math.floor(Date.now() / 1000),
        value: price
    };
    state.priceWriteIndex = (state.priceWriteIndex + 1) % CHART_MAX_POINTS;
    state.priceCount = Math.min(state.priceCount + 1, CHART_MAX_POINTS);

    const data = [];
    const start = state.priceCount === CHART_MAX_POINTS ? state.priceWriteIndex : 0;
    for (let i = 0; i < state.priceCount; i += 1) {
        const index = (start + i) % CHART_MAX_POINTS;
        data.push(state.prices[index]);
    }

    areaSeries.setData(data);
    chart.timeScale().fitContent();
}

function setCountdownFromMarket() {
    const endDate = state.selectedMarket?.end_date;
    if (!endDate) {
        state.countdownSecs = 300;
        return;
    }
    const diff = Math.floor((new Date(endDate).getTime() - Date.now()) / 1000);
    state.countdownSecs = Number.isFinite(diff) ? Math.max(0, diff) : 300;
}

function renderCountdown() {
    const min = Math.floor(state.countdownSecs / 60);
    const sec = state.countdownSecs % 60;
    document.getElementById('timer-min').innerText = String(min).padStart(2, '0');
    document.getElementById('timer-sec').innerText = String(sec).padStart(2, '0');
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/price`);

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.price === 'Loading...') {
                return;
            }

            const value = Number(data.price);
            if (!Number.isFinite(value)) {
                return;
            }

            document.getElementById('btc-price').innerText = formatUsd(value);
            pushChartPoint(value);
        } catch (e) {
            console.error('Error parsing WebSocket message', e);
        }
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 3000);
    };
}

async function fetchMarkets() {
    try {
        const response = await fetch('/api/markets');
        if (!response.ok) throw new Error('Failed to fetch markets');
        const markets = await response.json();
        state.markets = Array.isArray(markets) ? markets : [];

        if (!state.markets.length) {
            state.selectedMarket = null;
        } else {
            const keep = state.selectedMarket && state.markets.find((m) => m.condition_id === state.selectedMarket.condition_id);
            state.selectedMarket = keep || state.markets[0];
        }

        renderHeader();
        renderOutcomeButtons();
        setCountdownFromMarket();
        renderCountdown();
    } catch (error) {
        showToast(`Failed to load markets: ${error.message}`, 'error');
    }
}

async function submitOrder() {
    if (!state.selectedMarket) {
        showToast('No active market found.', 'error');
        return;
    }

    if (!state.amount || state.amount <= 0) {
        showToast('Please set amount first.', 'error');
        return;
    }

    const isUp = state.outcome === 'UP';
    const tokenId = isUp ? state.selectedMarket.yes_token_id : state.selectedMarket.no_token_id;

    if (!tokenId) {
        showToast('Token ID is not available for this market.', 'error');
        return;
    }

    const btn = document.getElementById('submit-order');
    btn.disabled = true;

    try {
        const response = await fetch('/api/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token_id: tokenId,
                side: state.side,
                outcome: state.outcome,
                size: state.amount
            })
        });

        const result = await response.json();
        if (result.status === 'success') {
            showToast('Order placed successfully!', 'success');
        } else {
            showToast(`Order failed: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showToast(`Order error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const text = document.createElement('span');
    text.innerText = message;

    const closeBtn = document.createElement('span');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.style.marginLeft = '10px';
    closeBtn.onclick = () => toast.remove();

    toast.appendChild(text);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    setTimeout(() => {
        if (toast.parentElement) toast.remove();
    }, 5000);
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('buy-tab').addEventListener('click', () => {
        state.side = 'BUY';
        document.getElementById('buy-tab').classList.add('active');
        document.getElementById('sell-tab').classList.remove('active');
        document.getElementById('buy-tab').setAttribute('aria-selected', 'true');
        document.getElementById('sell-tab').setAttribute('aria-selected', 'false');
        renderActionButton();
    });

    document.getElementById('sell-tab').addEventListener('click', () => {
        state.side = 'SELL';
        document.getElementById('sell-tab').classList.add('active');
        document.getElementById('buy-tab').classList.remove('active');
        document.getElementById('sell-tab').setAttribute('aria-selected', 'true');
        document.getElementById('buy-tab').setAttribute('aria-selected', 'false');
        renderActionButton();
    });

    document.getElementById('btn-up').addEventListener('click', () => {
        state.outcome = 'UP';
        renderOutcomeButtons();
        renderActionButton();
    });

    document.getElementById('btn-down').addEventListener('click', () => {
        state.outcome = 'DOWN';
        renderOutcomeButtons();
        renderActionButton();
    });

    document.querySelectorAll('.quick-add button').forEach((button) => {
        button.addEventListener('click', () => {
            const inc = button.dataset.inc;
            if (!QUICK_ADD_ALLOWED.has(inc)) {
                showToast('Invalid quick amount value.', 'error');
                return;
            }

            if (inc === 'max') {
                updateAmount('max');
                return;
            }

            const parsedInc = Number(inc);
            if (!Number.isFinite(parsedInc)) {
                showToast('Invalid quick amount value.', 'error');
                return;
            }

            updateAmount(parsedInc);
        });
    });

    document.getElementById('submit-order').addEventListener('click', submitOrder);
    document.getElementById('balance').innerText = `Balance ${formatUsd(state.balance)}`;

    initChart();
    connectWebSocket();
    fetchMarkets();

    setInterval(fetchMarkets, 5000);
    setInterval(() => {
        if (state.countdownSecs > 0) state.countdownSecs -= 1;
        renderCountdown();
    }, 1000);
});
