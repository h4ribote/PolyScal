import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from price_aggregator import PriceAggregator
from polymarket_client import fetch_active_btc_markets, place_order

logger = logging.getLogger("FastAPI")
logger.setLevel(logging.INFO)

aggregator = PriceAggregator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background price aggregator
    logger.info("Starting Price Aggregator background tasks...")
    await aggregator.start()
    yield
    # Cleanup on shutdown
    logger.info("Stopping Price Aggregator background tasks...")
    await aggregator.stop()

app = FastAPI(title="Polymarket BTC Scalping Client", lifespan=lifespan)

# Setup CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OrderRequest(BaseModel):
    token_id: str
    side: str  # "BUY" or "SELL"
    outcome: str # "YES" or "NO"
    size: float

@app.get("/api/markets")
async def get_markets():
    """Fetch active BTC markets."""
    markets = fetch_active_btc_markets()
    return markets

@app.post("/api/order")
async def create_order(req: OrderRequest):
    """Place an order using the polymarket client."""
    logger.info(f"Received order request: {req}")
    # In a real environment we would also use the 'outcome' variable to set limit prices if desired.
    # Currently passing default price (0.5 for FOK) to the client.
    result = place_order(
        token_id=req.token_id,
        side=req.side.upper(),
        size=req.size
    )
    return result

@app.websocket("/ws/price")
async def websocket_price_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            pseudo_rate = aggregator.get_pseudo_rate()
            if pseudo_rate is not None:
                await websocket.send_json({"price": pseudo_rate})
            else:
                await websocket.send_json({"price": "Loading..."})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

# Mount static files at root
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)
