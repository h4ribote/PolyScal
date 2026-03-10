from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    polymarket_host: str = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")
    polymarket_chain_id: int = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    polymarket_private_key: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    polymarket_signature_type: int = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    polymarket_funder: str = os.getenv("POLYMARKET_FUNDER", "")

    binance_ws_url: str = os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws/btcusdt@bookTicker")
    coinbase_ws_url: str = os.getenv("COINBASE_WS_URL", "wss://ws-feed.exchange.coinbase.com")
    kraken_ws_url: str = os.getenv("KRAKEN_WS_URL", "wss://ws.kraken.com/v2")
    okx_ws_url: str = os.getenv("OKX_WS_URL", "wss://ws.okx.com:8443/ws/v5/public")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
