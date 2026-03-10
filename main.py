from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import get_settings
from polymarket_client import PolyMarketClientError, PolymarketClient
from price_aggregator import PriceAggregator


settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
price_aggregator = PriceAggregator(settings)
polymarket = PolymarketClient(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await price_aggregator.start()
    try:
        yield
    finally:
        await price_aggregator.stop()


app = FastAPI(title="PolyScal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class OrderRequest(BaseModel):
    token_id: str = Field(min_length=1)
    side: Literal["BUY"]
    outcome: Literal["YES", "NO"]
    size: float = Field(gt=0)


@app.get("/api/markets")
async def get_markets() -> list[dict[str, object | None]]:
    try:
        markets = await asyncio.to_thread(polymarket.get_active_5m_btc_markets)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch markets: {exc}") from exc
    return [market.__dict__ for market in markets]


@app.post("/api/order")
async def post_order(request: OrderRequest) -> dict[str, object]:
    try:
        return await asyncio.to_thread(
            polymarket.place_order,
            request.token_id,
            request.side,
            request.outcome,
            request.size,
        )
    except PolyMarketClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit order: {exc}") from exc


@app.websocket("/ws/price")
async def ws_price(websocket: WebSocket) -> None:
    await websocket.accept()
    last_price: float | None = None
    try:
        while True:
            payload = await price_aggregator.get_price_payload()
            price = payload.get("price")
            changed = price != last_price
            if changed or price is not None:
                await websocket.send_json(
                    {
                        "price": price,
                        "sources": payload.get("sources"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "changed": changed,
                    }
                )
                last_price = price if isinstance(price, float) else last_price
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
