from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import config
except ModuleNotFoundError:
    config = None

from polymarket_client import PolymarketClient
from price_aggregator import PriceAggregator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

aggregator = PriceAggregator()
polymarket_client: PolymarketClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global polymarket_client
    await aggregator.start()
    try:
        polymarket_client = PolymarketClient()
    except Exception as exc:
        logger.warning("Polymarket client disabled: %s", exc)
        polymarket_client = None

    try:
        yield
    finally:
        await aggregator.stop()


app = FastAPI(title="PolyScal", lifespan=lifespan)
allowed_origins = getattr(config, "ALLOWED_ORIGINS", ["http://127.0.0.1:8000", "http://localhost:8000"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class OrderRequest(BaseModel):
    token_id: str = Field(min_length=1)
    side: Literal["BUY"]
    outcome: Literal["YES", "NO"]
    size: float = Field(gt=0)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/markets")
async def get_markets() -> list[dict[str, Any]]:
    if polymarket_client is None:
        raise HTTPException(status_code=503, detail="Polymarket client not configured")

    try:
        markets = await polymarket_client.list_active_btc_5m_markets()
    except Exception as exc:
        logger.exception("Failed to fetch markets")
        raise HTTPException(status_code=502, detail=f"Failed to fetch markets: {exc}") from exc

    return [
        {
            "market_id": market.market_id,
            "title": market.title,
            "yes_token_id": market.yes_token_id,
            "no_token_id": market.no_token_id,
            "yes_price": market.yes_price,
            "no_price": market.no_price,
            "end_time": market.end_time,
            "active": market.active,
        }
        for market in markets
    ]


@app.post("/api/order")
async def post_order(payload: OrderRequest) -> dict[str, Any]:
    if polymarket_client is None:
        raise HTTPException(status_code=503, detail="Polymarket client not configured")

    try:
        result = await polymarket_client.place_buy_order(
            token_id=payload.token_id,
            size_usd=payload.size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Order placement failed")
        raise HTTPException(status_code=502, detail=f"Order placement failed: {exc}") from exc

    return {
        "status": "ok",
        "result": result,
        "requested": payload.model_dump(),
    }


@app.websocket("/ws/price")
async def ws_price(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            snapshot = await aggregator.get_snapshot()
            await websocket.send_json(
                {
                    "price": snapshot.price,
                    "updated_at": snapshot.updated_at,
                    "exchange_count": len(snapshot.exchange_mids),
                    "exchange_mids": snapshot.exchange_mids,
                }
            )
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
