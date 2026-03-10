import requests
import logging
from typing import List, Dict, Any, Optional
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import config

logger = logging.getLogger("PolymarketClient")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def get_client() -> ClobClient:
    """Initialize the ClobClient using credentials from config."""
    try:
        # We need a private key to post orders. If it's the dummy key,
        # creating orders might fail, but it starts the client.
        client = ClobClient(
            host=config.HOST,
            key=config.PRIVATE_KEY,
            chain_id=config.CHAIN_ID,
        )

        # In level 2, client expects credentials for auth APIs
        client.set_api_creds(client.create_or_derive_api_creds())
        logger.info("Initialized Polymarket ClobClient with API credentials.")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize ClobClient: {e}")
        # Return a Level 0 client as fallback (won't be able to place orders)
        return ClobClient(host=config.HOST, chain_id=config.CHAIN_ID)

client = get_client()

def fetch_active_btc_markets() -> List[Dict[str, Any]]:
    """Fetches active 5-minute BTC markets using Gamma API."""
    url = "https://gamma-api.polymarket.com/events?closed=false"
    try:
        response = requests.get(url)
        response.raise_for_status()
        events = response.json()

        btc_markets = []
        for event in events:
            # We look for Bitcoin/BTC markets (a real implementation might filter by a specific "5-minute" interval tag or schedule)
            # For demonstration, we just grab any active BTC market.
            title = event.get("title", "")
            if "Bitcoin" in title or "BTC" in title:
                markets = event.get("markets", [])
                for market in markets:
                    if market.get("active") and not market.get("closed"):
                        clob_tokens = market.get("clobTokenIds", "[]")
                        try:
                            import json
                            tokens = json.loads(clob_tokens)
                        except:
                            tokens = []

                        yes_token = tokens[0] if len(tokens) > 0 else None
                        no_token = tokens[1] if len(tokens) > 1 else None

                        # Add formatted market
                        btc_markets.append({
                            "title": market.get("question", title),
                            "yes_price": float(market.get("outcomePrices", '["0", "0"]')[1:-1].replace('"', '').split(', ')[0]),
                            "no_price": float(market.get("outcomePrices", '["0", "0"]')[1:-1].replace('"', '').split(', ')[1]),
                            "yes_token_id": yes_token,
                            "no_token_id": no_token,
                            "end_date": market.get("endDate", event.get("endDate")),
                            "condition_id": market.get("conditionId")
                        })
        return btc_markets
    except Exception as e:
        logger.error(f"Error fetching active BTC markets: {e}")
        return []

def place_order(token_id: str, side: str, size: float, price: float = 0.5) -> Dict[str, Any]:
    """
    Places an order on the Polymarket CLOB.
    Since we don't have real funding/matching info, this uses MarketOrderArgs to create FOK.
    """
    try:
        from py_clob_client.clob_types import MarketOrderArgs

        # A market order needs size and side. FOK represents Fill-Or-Kill
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=size,
            side=side, # "BUY" or "SELL"
            price=price,
            order_type="FOK"
        )

        # In a real environment with L2 creds, this will sign and post the order
        response = client.create_and_post_order(order_args)
        logger.info(f"Order posted: {response}")
        return {"status": "success", "response": str(response)}
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        return {"status": "error", "message": str(e)}
