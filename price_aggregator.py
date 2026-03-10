from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from statistics import median
from typing import Any

import websockets

from config import Settings


logger = logging.getLogger(__name__)


class PriceAggregator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._mid_prices: dict[str, float] = {}
        self._latest_price: float | None = None
        self._latest_source_count: int = 0
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(
                self._run_with_reconnect("binance", self.settings.binance_ws_url, self._consume_binance)
            ),
            asyncio.create_task(
                self._run_with_reconnect("coinbase", self.settings.coinbase_ws_url, self._consume_coinbase)
            ),
            asyncio.create_task(
                self._run_with_reconnect("kraken", self.settings.kraken_ws_url, self._consume_kraken)
            ),
            asyncio.create_task(self._run_with_reconnect("okx", self.settings.okx_ws_url, self._consume_okx)),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def get_latest_price(self) -> float | None:
        async with self._lock:
            return self._latest_price

    async def get_price_payload(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "price": self._latest_price,
                "sources": self._latest_source_count,
            }

    async def _set_mid_price(self, exchange: str, bid: float, ask: float) -> None:
        if bid <= 0 or ask <= 0:
            return
        mid = (bid + ask) / 2.0
        async with self._lock:
            self._mid_prices[exchange] = mid
            all_mid_prices = list(self._mid_prices.values())
            if not all_mid_prices:
                return
            self._latest_source_count = len(all_mid_prices)
            self._latest_price = float(median(all_mid_prices))

    async def _run_with_reconnect(
        self,
        name: str,
        url: str,
        consumer: Callable[[websockets.WebSocketClientProtocol], Awaitable[None]],
    ) -> None:
        backoff_seconds = 1.0
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    backoff_seconds = 1.0
                    await consumer(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("%s websocket disconnected: %s", name, exc)
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)

    async def _consume_binance(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for message in ws:
            data = json.loads(message)
            bid = float(data.get("b", 0))
            ask = float(data.get("a", 0))
            await self._set_mid_price("binance", bid, ask)

    async def _consume_coinbase(self, ws: websockets.WebSocketClientProtocol) -> None:
        await ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "product_ids": ["BTC-USD"],
                    "channels": ["ticker"],
                }
            )
        )
        async for message in ws:
            data = json.loads(message)
            if data.get("type") != "ticker":
                continue
            bid_value = data.get("best_bid", data.get("bid", 0))
            ask_value = data.get("best_ask", data.get("ask", 0))
            bid = float(bid_value or 0)
            ask = float(ask_value or 0)
            await self._set_mid_price("coinbase", bid, ask)

    async def _consume_kraken(self, ws: websockets.WebSocketClientProtocol) -> None:
        await ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "params": {
                        "channel": "book",
                        "symbol": ["BTC/USD"],
                        "depth": 1,
                        "snapshot": True,
                    },
                }
            )
        )
        async for message in ws:
            data = json.loads(message)
            if data.get("channel") != "book":
                continue
            books = data.get("data") or []
            if not books:
                continue
            book = books[0]
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            if not bids or not asks:
                continue
            bid = float((bids[0] or {}).get("price", 0))
            ask = float((asks[0] or {}).get("price", 0))
            await self._set_mid_price("kraken", bid, ask)

    async def _consume_okx(self, ws: websockets.WebSocketClientProtocol) -> None:
        await ws.send(
            json.dumps(
                {
                    "op": "subscribe",
                    "args": [{"channel": "books5", "instId": "BTC-USDT"}],
                }
            )
        )
        async for message in ws:
            data = json.loads(message)
            packets = data.get("data") or []
            if not packets:
                continue
            book = packets[0]
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            if not bids or not asks:
                continue
            bid = float(bids[0][0])
            ask = float(asks[0][0])
            await self._set_mid_price("okx", bid, ask)
