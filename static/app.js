const pseudoPriceEl = document.getElementById('pseudoPrice');
const sourceCountEl = document.getElementById('sourceCount');
const marketBoardEl = document.getElementById('marketBoard');
const defaultSizeEl = document.getElementById('defaultSize');
const refreshBtnEl = document.getElementById('refreshBtn');

let markets = [];
const WS_RECONNECT_DELAY_MS = 1500;
const MARKET_REFRESH_INTERVAL_MS = 5000;

function formatUsd(value) {
  if (value == null || Number.isNaN(Number(value))) return '--';
  return `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
}

function remainingText(endTime) {
  if (!endTime) return '期限不明';
  const end = new Date(endTime).getTime();
  if (Number.isNaN(end)) return '期限不明';
  const diff = end - Date.now();
  if (diff <= 0) return '判定済み';
  const sec = Math.floor(diff / 1000);
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  return `${min}m ${remSec}s`;
}

function notify(message) {
  window.alert(message);
}

async function submitOrder(tokenId, outcome) {
  const size = Number(defaultSizeEl.value);
  if (!size || size <= 0) {
    notify('注文サイズは1以上を指定してください。');
    return;
  }

  const response = await fetch('/api/order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_id: tokenId, side: 'BUY', outcome, size }),
  });

  const result = await response.json();
  if (!response.ok) {
    notify(`注文失敗: ${result.detail || 'unknown error'}`);
    return;
  }

  notify(`注文送信成功: ${outcome} ${size} USD`);
}

function renderMarkets() {
  if (!markets.length) {
    marketBoardEl.innerHTML = '<p>対象マーケットが見つかりません。</p>';
    return;
  }

  marketBoardEl.innerHTML = markets
    .map((market) => {
      const yesDisabled = market.yes_token_id ? '' : 'disabled';
      const noDisabled = market.no_token_id ? '' : 'disabled';
      return `
        <article class="market-card">
          <h3 class="market-title">${market.title || 'Untitled Market'}</h3>
          <div class="market-meta">残り時間: ${remainingText(market.end_time)}</div>
          <div class="price-row">
            <span>YES: ${formatUsd(market.yes_price)}</span>
            <span>NO: ${formatUsd(market.no_price)}</span>
          </div>
          <div class="actions">
            <button class="buy-yes" data-token-id="${market.yes_token_id || ''}" data-outcome="YES" ${yesDisabled}>Buy YES</button>
            <button class="buy-no" data-token-id="${market.no_token_id || ''}" data-outcome="NO" ${noDisabled}>Buy NO</button>
          </div>
        </article>
      `;
    })
    .join('');
}

async function fetchMarkets() {
  try {
    const response = await fetch('/api/markets');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'failed to fetch markets');
    }
    markets = Array.isArray(data) ? data : [];
    renderMarkets();
  } catch (error) {
    marketBoardEl.innerHTML = `<p>市場取得失敗: ${error.message}</p>`;
  }
}

function connectPriceSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/price`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (typeof data.price === 'number') {
        pseudoPriceEl.textContent = formatUsd(data.price);
      }
      sourceCountEl.textContent = `sources: ${data.sources ?? 0}`;
    } catch (error) {
      console.error('invalid ws payload', error);
    }
  };

  ws.onclose = () => {
    setTimeout(connectPriceSocket, WS_RECONNECT_DELAY_MS);
  };
}

marketBoardEl.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-token-id]');
  if (!button) return;

  const tokenId = button.dataset.tokenId;
  const outcome = button.dataset.outcome;
  if (!tokenId || !outcome) return;

  button.disabled = true;
  try {
    await submitOrder(tokenId, outcome);
  } catch (error) {
    notify(`注文失敗: ${error.message}`);
  } finally {
    button.disabled = false;
  }
});

refreshBtnEl.addEventListener('click', fetchMarkets);

connectPriceSocket();
fetchMarkets();
setInterval(fetchMarkets, MARKET_REFRESH_INTERVAL_MS);
