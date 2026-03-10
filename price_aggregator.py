import asyncio
import json
import statistics
import logging
import websockets
from typing import Dict, Optional

logger = logging.getLogger("PriceAggregator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class PriceAggregator:
    def __init__(self):
        # Store mid price per exchange
        self.prices: Dict[str, float] = {}
        self.tasks: list[asyncio.Task] = []

    def update_price(self, exchange: str, bid: float, ask: float):
        if bid > 0 and ask > 0:
            mid_price = (bid + ask) / 2
            self.prices[exchange] = mid_price

    def get_pseudo_rate(self) -> Optional[float]:
        """Returns the median of current mid prices across exchanges"""
        valid_prices = list(self.prices.values())
        if not valid_prices:
            return None
        return statistics.median(valid_prices)

    async def _binance_ws(self):
        uri = "wss://stream.binance.us:9443/ws/btcusdt@bookTicker"
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to Binance WebSocket")
                    async for msg in ws:
                        data = json.loads(msg)
                        bid = float(data.get("b", 0))
                        ask = float(data.get("a", 0))
                        self.update_price("binance", bid, ask)
            except Exception as e:
                logger.error(f"Binance WS error: {e}")
                await asyncio.sleep(5)

    async def _coinbase_ws(self):
        uri = "wss://ws-feed.exchange.coinbase.com"
        subscribe_msg = {
            "type": "subscribe",
            "product_ids": ["BTC-USD"],
            "channels": ["ticker"]
        }
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to Coinbase WebSocket")
                    await ws.send(json.dumps(subscribe_msg))
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "ticker":
                            bid = float(data.get("best_bid", 0))
                            ask = float(data.get("best_ask", 0))
                            self.update_price("coinbase", bid, ask)
            except Exception as e:
                logger.error(f"Coinbase WS error: {e}")
                await asyncio.sleep(5)

    async def _kraken_ws(self):
        uri = "wss://ws.kraken.com"
        subscribe_msg = {
            "event": "subscribe",
            "pair": ["XBT/USD"],
            "subscription": {"name": "ticker"}
        }
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to Kraken WebSocket")
                    await ws.send(json.dumps(subscribe_msg))
                    async for msg in ws:
                        data = json.loads(msg)
                        if isinstance(data, list) and len(data) > 1 and "ticker" in data:
                            ticker_info = data[1]
                            bid = float(ticker_info["b"][0])
                            ask = float(ticker_info["a"][0])
                            self.update_price("kraken", bid, ask)
            except Exception as e:
                logger.error(f"Kraken WS error: {e}")
                await asyncio.sleep(5)

    async def _okx_ws(self):
        uri = "wss://ws.okx.com:8443/ws/v5/public"
        subscribe_msg = {
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
        }
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to OKX WebSocket")
                    await ws.send(json.dumps(subscribe_msg))
                    async for msg in ws:
                        data = json.loads(msg)
                        if "data" in data and len(data["data"]) > 0:
                            ticker_info = data["data"][0]
                            bid = float(ticker_info.get("bidPx", 0))
                            ask = float(ticker_info.get("askPx", 0))
                            self.update_price("okx", bid, ask)
            except Exception as e:
                logger.error(f"OKX WS error: {e}")
                await asyncio.sleep(5)

    async def start(self):
        """Start background websocket tasks"""
        self.tasks.append(asyncio.create_task(self._binance_ws()))
        self.tasks.append(asyncio.create_task(self._coinbase_ws()))
        self.tasks.append(asyncio.create_task(self._kraken_ws()))
        self.tasks.append(asyncio.create_task(self._okx_ws()))

    async def stop(self):
        """Stop all background tasks"""
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
