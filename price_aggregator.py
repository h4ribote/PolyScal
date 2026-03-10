from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import statistics
import time
from dataclasses import dataclass
from typing import Any

import websockets

logger = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    price: float | None
    exchange_mids: dict[str, float]
    updated_at: float | None


class PriceAggregator:
    """Aggregates BTC midpoint prices from multiple exchanges and exposes a median pseudo-rate."""

    def __init__(self) -> None:
        self._exchange_mids: dict[str, float] = {}
        self._latest_price: float | None = None
        self._updated_at: float | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self) -> None:
        if self._tasks:
            return

        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(
                self._run_exchange_loop("binance", self._binance_stream),
                name="price-agg-binance",
            ),
            asyncio.create_task(
                self._run_exchange_loop("coinbase", self._coinbase_stream),
                name="price-agg-coinbase",
            ),
            asyncio.create_task(
                self._run_exchange_loop("kraken", self._kraken_stream),
                name="price-agg-kraken",
            ),
            asyncio.create_task(
                self._run_exchange_loop("okx", self._okx_stream),
                name="price-agg-okx",
            ),
        ]
        logger.info("Price aggregator started with %d exchange tasks", len(self._tasks))

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        logger.info("Price aggregator stopped")

    async def get_snapshot(self) -> PriceSnapshot:
        async with self._lock:
            return PriceSnapshot(
                price=self._latest_price,
                exchange_mids=dict(self._exchange_mids),
                updated_at=self._updated_at,
            )

    async def _update_mid(self, exchange: str, bid: float, ask: float) -> None:
        if bid <= 0 or ask <= 0:
            return
        mid = (bid + ask) / 2.0

        async with self._lock:
            self._exchange_mids[exchange] = mid
            self._latest_price = statistics.median(self._exchange_mids.values())
            self._updated_at = time.time()

    async def _run_exchange_loop(self, exchange: str, stream_coro: Any) -> None:
        backoff = 1
        while not self._stop_event.is_set():
            try:
                await stream_coro()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("%s stream error: %s", exchange, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _binance_stream(self) -> None:
        uri = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            async for raw in ws:
                payload = json.loads(raw)
                bid = float(payload.get("b", 0))
                ask = float(payload.get("a", 0))
                await self._update_mid("binance", bid, ask)

    async def _coinbase_stream(self) -> None:
        uri = "wss://ws-feed.exchange.coinbase.com"
        subscribe = {
            "type": "subscribe",
            "product_ids": ["BTC-USD"],
            "channels": ["ticker"],
        }
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(subscribe))
            async for raw in ws:
                payload = json.loads(raw)
                if payload.get("type") != "ticker":
                    continue
                bid = float(payload.get("best_bid", 0))
                ask = float(payload.get("best_ask", 0))
                await self._update_mid("coinbase", bid, ask)

    async def _kraken_stream(self) -> None:
        uri = "wss://ws.kraken.com/v2"
        subscribe = {
            "method": "subscribe",
            "params": {
                "channel": "ticker",
                "symbol": ["BTC/USD"],
            },
        }
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(subscribe))
            async for raw in ws:
                payload = json.loads(raw)
                if payload.get("channel") != "ticker":
                    continue
                data = payload.get("data")
                if not data:
                    continue
                item = data[0]
                bid = float(item.get("bid", 0))
                ask = float(item.get("ask", 0))
                await self._update_mid("kraken", bid, ask)

    async def _okx_stream(self) -> None:
        uri = "wss://ws.okx.com:8443/ws/v5/public"
        subscribe = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "tickers",
                    "instId": "BTC-USDT",
                }
            ],
        }
        async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(subscribe))
            async for raw in ws:
                payload = json.loads(raw)
                data = payload.get("data")
                if not data:
                    continue
                item = data[0]
                bid = float(item.get("bidPx", 0))
                ask = float(item.get("askPx", 0))
                await self._update_mid("okx", bid, ask)
