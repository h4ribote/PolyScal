const priceEl = document.getElementById("price");
const priceMetaEl = document.getElementById("price-meta");
const marketsEl = document.getElementById("markets");
const orderSizeEl = document.getElementById("order-size");
const refreshButton = document.getElementById("refresh-markets");

let markets = [];

function connectPriceSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws/price`);

  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (typeof payload.price === "number") {
      priceEl.textContent = payload.price.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      priceMetaEl.textContent = `更新: ${new Date((payload.updated_at || 0) * 1000).toLocaleTimeString()} / 参照取引所: ${payload.exchange_count}`;
    } else {
      priceEl.textContent = "--";
      priceMetaEl.textContent = "価格データ待機中...";
    }
  };

  ws.onclose = () => {
    priceMetaEl.textContent = "切断されました。再接続中...";
    setTimeout(connectPriceSocket, 1500);
  };

  ws.onerror = () => {
    ws.close();
  };
}

function getOrderSize() {
  const size = Number(orderSizeEl.value);
  if (!Number.isFinite(size) || size <= 0) {
    alert("注文サイズは 0 より大きい数値を入力してください。");
    return null;
  }
  return size;
}

async function placeOrder(tokenId, outcome) {
  const size = getOrderSize();
  if (size == null) {
    return;
  }

  try {
    const response = await fetch("/api/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token_id: tokenId,
        side: "BUY",
        outcome,
        size,
      }),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "注文に失敗しました");
    }
    alert(`注文送信成功: ${outcome} / size=${size}`);
  } catch (error) {
    alert(`注文エラー: ${error.message}`);
  }
}

function renderMarkets() {
  if (!markets.length) {
    marketsEl.innerHTML = '<p class="empty">対象市場が見つかりません。</p>';
    return;
  }

  marketsEl.innerHTML = "";
  for (const market of markets) {
    const card = document.createElement("article");
    card.className = "market-card";

    const end = market.end_time ? new Date(market.end_time) : null;
    const remaining = end ? Math.max(0, end.getTime() - Date.now()) : null;
    const remainingLabel =
      remaining == null
        ? "不明"
        : `${Math.floor(remaining / 60000)}分${Math.floor((remaining % 60000) / 1000)}秒`;

    card.innerHTML = `
      <h3 class="market-title">${market.title}</h3>
      <div class="market-meta">
        <span>残り: ${remainingLabel}</span>
      </div>
      <div class="price-row">
        <span>YES: ${market.yes_price ?? "--"}</span>
        <span>NO: ${market.no_price ?? "--"}</span>
      </div>
      <div class="actions">
        <button class="buy-btn buy-yes" data-token="${market.yes_token_id}" data-outcome="YES">Buy YES</button>
        <button class="buy-btn buy-no" data-token="${market.no_token_id}" data-outcome="NO">Buy NO</button>
      </div>
    `;

    card.querySelectorAll(".buy-btn").forEach((button) => {
      button.addEventListener("click", () => {
        placeOrder(button.dataset.token, button.dataset.outcome);
      });
    });

    marketsEl.appendChild(card);
  }
}

async function fetchMarkets() {
  try {
    const response = await fetch("/api/markets");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "市場取得に失敗しました");
    }
    markets = payload;
    renderMarkets();
  } catch (error) {
    marketsEl.innerHTML = `<p class="empty">市場取得エラー: ${error.message}</p>`;
  }
}

refreshButton.addEventListener("click", fetchMarkets);

connectPriceSocket();
fetchMarkets();
setInterval(fetchMarkets, 5000);
