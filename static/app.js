// WebSocket Connection for Real-time Price
function connectWebSocket() {
    const wsUrl = `ws://${window.location.host}/ws/price`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            const priceElement = document.getElementById('btc-price');
            if (data.price !== "Loading...") {
                priceElement.innerText = `$${parseFloat(data.price).toFixed(2)}`;
            } else {
                priceElement.innerText = data.price;
            }
        } catch (e) {
            console.error("Error parsing WebSocket message", e);
        }
    };

    ws.onclose = () => {
        console.warn("WebSocket disconnected. Reconnecting in 3s...");
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

// Fetch Active Markets via REST API
async function fetchMarkets() {
    try {
        const response = await fetch('/api/markets');
        if (!response.ok) throw new Error("Failed to fetch markets");
        const markets = await response.json();
        renderMarkets(markets);
    } catch (error) {
        console.error("Error fetching markets:", error);
        showToast(`Failed to load markets: ${error.message}`, 'error');
    }
}

// Render Markets to the DOM
function renderMarkets(markets) {
    const container = document.getElementById('markets-container');
    container.innerHTML = ''; // Clear existing

    if (markets.length === 0) {
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #8b949e;">No active BTC markets found.</div>';
        return;
    }

    markets.forEach(market => {
        const card = document.createElement('div');
        card.className = 'market-card';

        // Check if we have token IDs
        const hasTokens = market.yes_token_id && market.no_token_id;

        card.innerHTML = `
            <div class="market-title">${market.title}</div>
            <div class="market-info">
                <span>Ends: ${new Date(market.end_date).toLocaleString()}</span>
                <span>ID: ${market.condition_id ? market.condition_id.substring(0, 8) + '...' : 'N/A'}</span>
            </div>

            <div class="price-row">
                <span class="price-label" style="color: var(--success-color);">YES</span>
                <span class="price-value">$${market.yes_price.toFixed(3)}</span>
            </div>

            <div class="price-row">
                <span class="price-label" style="color: var(--danger-color);">NO</span>
                <span class="price-value">$${market.no_price.toFixed(3)}</span>
            </div>

            <div class="actions">
                <button class="btn-yes" onclick="placeOrder('${market.yes_token_id}', 'BUY', 'YES')" ${!hasTokens ? 'disabled' : ''}>
                    Buy YES
                </button>
                <button class="btn-no" onclick="placeOrder('${market.no_token_id}', 'BUY', 'NO')" ${!hasTokens ? 'disabled' : ''}>
                    Buy NO
                </button>
            </div>
        `;
        container.appendChild(card);
    });
}

// Place Order via REST API
window.placeOrder = async function(tokenId, side, outcome) {
    if (!tokenId) {
        showToast(`Invalid token ID for ${outcome}`, 'error');
        return;
    }

    const sizeInput = document.getElementById('order-size').value;
    const size = parseFloat(sizeInput);
    if (isNaN(size) || size <= 0) {
        showToast('Please enter a valid order size.', 'error');
        return;
    }

    // Disable all buttons to prevent double click
    const buttons = document.querySelectorAll('.actions button');
    buttons.forEach(btn => btn.disabled = true);

    showToast(`Placing order: ${side} ${size} of ${outcome}...`, 'info');

    try {
        const response = await fetch('/api/order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token_id: tokenId,
                side: side,
                outcome: outcome,
                size: size
            })
        });

        const result = await response.json();

        if (result.status === 'success') {
            showToast(`Order placed successfully!`, 'success');
        } else {
            showToast(`Order failed: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error("Order error:", error);
        showToast(`Order error: ${error.message}`, 'error');
    } finally {
        // Re-enable buttons
        fetchMarkets(); // Refresh data and buttons state
    }
};

// Simple Toast Notification System
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

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 5000);
}

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchMarkets();

    // Poll for market updates every 5 seconds
    setInterval(fetchMarkets, 5000);
});