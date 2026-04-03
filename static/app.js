const MAX_ORDER_AMOUNT = 999999;

const state = {
    markets: [],
    selectedMarket: null,
    side: 'BUY',
    outcome: 'UP',
    amount: 0,
    balance: 32.58,
    prices: [],
    countdownSecs: 300
};

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
        state.amount = Math.min(MAX_ORDER_AMOUNT, Math.max(0, state.amount + Number(delta)));
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

function renderChart() {
    const prices = state.prices.slice(-60);
    const container = document.getElementById('chart-candles');
    container.innerHTML = '';

    if (prices.length < 2) return;

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const span = Math.max(max - min, 1);

    for (let i = 1; i < prices.length; i += 1) {
        const prev = prices[i - 1];
        const cur = prices[i];
        const height = 10 + ((cur - min) / span) * 82;
        const el = document.createElement('div');
        el.className = `candle ${cur >= prev ? 'up' : 'down'}`;
        el.style.height = `${height}%`;
        container.appendChild(el);
    }

    document.getElementById('axis-top').innerText = formatUsd(max);
    document.getElementById('axis-mid').innerText = formatUsd((max + min) / 2);
    document.getElementById('axis-low').innerText = formatUsd(min);

    const line = document.getElementById('current-line');
    const current = prices[prices.length - 1];
    const normalized = ((current - min) / span) * 100;
    line.style.top = `${90 - normalized * 0.76}%`;
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
            state.prices.push(value);
            if (state.prices.length > 120) state.prices = state.prices.slice(-120);
            renderChart();
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
        renderActionButton();
    });

    document.getElementById('sell-tab').addEventListener('click', () => {
        state.side = 'SELL';
        document.getElementById('sell-tab').classList.add('active');
        document.getElementById('buy-tab').classList.remove('active');
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
            updateAmount(inc === 'max' ? 'max' : Number(inc));
        });
    });

    document.getElementById('submit-order').addEventListener('click', submitOrder);
    document.getElementById('balance').innerText = `Balance ${formatUsd(state.balance)}`;

    connectWebSocket();
    fetchMarkets();

    setInterval(fetchMarkets, 5000);
    setInterval(() => {
        if (state.countdownSecs > 0) state.countdownSecs -= 1;
        renderCountdown();
    }, 1000);
});
