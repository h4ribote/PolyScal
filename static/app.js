const MAX_ORDER_AMOUNT = 999999;
const CHART_MAX_POINTS = 240;
const QUICK_ADD_ALLOWED = new Set(['1', '5', '10', '100', 'max']);
const TIMELINE_VISIBLE_COUNT = 5;

const state = {
    markets: [],
    selectedMarket: null,
    side: 'BUY',
    outcome: 'UP',
    amount: 0,
    balance: 32.58,
    countdownSecs: 300,
    minuteCandles: new Map()
};

let chart;
let candleSeries;

function createCandlestickSeriesCompat(chartInstance, options) {
    if (typeof chartInstance?.addCandlestickSeries === 'function') {
        return chartInstance.addCandlestickSeries(options);
    }

    const candlestickSeriesType = window.LightweightCharts?.CandlestickSeries;
    if (typeof chartInstance?.addSeries === 'function' && candlestickSeriesType) {
        return chartInstance.addSeries(candlestickSeriesType, options);
    }

    throw new Error('Candlestick series API is not available. Ensure a compatible lightweight-charts build is loaded.');
}

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
        state.amount = Math.min(MAX_ORDER_AMOUNT, Math.max(0, Number(state.balance) || 0));
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

function formatTimelineTime(value) {
    if (!value) return '--:--';
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return '--:--';
    return dt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function getSortedMarkets() {
    return [...state.markets].sort((a, b) => new Date(a.end_date).getTime() - new Date(b.end_date).getTime());
}

function renderTimeline() {
    const row = document.querySelector('.timeline-row');
    if (!row) return;
    row.innerHTML = '';

    const sorted = getSortedMarkets();
    if (!sorted.length) {
        const empty = document.createElement('span');
        empty.className = 'subtle';
        empty.innerText = 'No active market slots';
        row.appendChild(empty);
        return;
    }

    const selectedIndex = sorted.findIndex((m) => m.condition_id === state.selectedMarket?.condition_id);
    const anchor = selectedIndex >= 0 ? selectedIndex : 0;
    const start = Math.max(0, anchor - Math.floor((TIMELINE_VISIBLE_COUNT - 1) / 2));
    const visible = sorted.slice(start, start + TIMELINE_VISIBLE_COUNT);

    visible.forEach((market) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pill';
        if (market.condition_id === state.selectedMarket?.condition_id) {
            btn.classList.add('active');
        }
        btn.dataset.conditionId = market.condition_id;
        btn.setAttribute('aria-label', `Select ${formatTimelineTime(market.end_date)} slot`);
        btn.innerText = formatTimelineTime(market.end_date);
        btn.addEventListener('click', () => {
            state.selectedMarket = market;
            setCountdownFromMarket();
            renderHeader();
            renderOutcomeButtons();
            renderCountdown();
            renderTimeline();
        });
        row.appendChild(btn);
    });
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
            secondsVisible: false
        },
        crosshair: {
            vertLine: { color: '#33506a' },
            horzLine: { color: '#33506a' }
        }
    });

    candleSeries = createCandlestickSeriesCompat(chart, {
        upColor: '#2ce58b',
        borderUpColor: '#2ce58b',
        wickUpColor: '#2ce58b',
        downColor: '#ff4f55',
        borderDownColor: '#ff4f55',
        wickDownColor: '#ff4f55'
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
    if (!candleSeries) return;

    const nowSec = Math.floor(Date.now() / 1000);
    const minuteStart = Math.floor(nowSec / 60) * 60;
    const existing = state.minuteCandles.get(minuteStart);
    if (existing) {
        existing.high = Math.max(existing.high, price);
        existing.low = Math.min(existing.low, price);
        existing.close = price;
    } else {
        state.minuteCandles.set(minuteStart, {
            time: minuteStart,
            open: price,
            high: price,
            low: price,
            close: price
        });
    }

    if (state.minuteCandles.size > CHART_MAX_POINTS) {
        const oldest = Math.min(...state.minuteCandles.keys());
        state.minuteCandles.delete(oldest);
    }

    const data = [...state.minuteCandles.keys()]
        .sort((a, b) => a - b)
        .slice(-CHART_MAX_POINTS)
        .map((key) => state.minuteCandles.get(key));

    candleSeries.setData(data);
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
        renderTimeline();
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
