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
    """Fetches active 5-minute BTC markets using Gamma API /markets/slug/..."""
    # 1. First we need to find the dynamic slugs for the 5m btc up/down markets.
    # We query the events API for the btc-up-or-down-5m series.
    # We pull recent events. We don't filter solely by closed=false because in non-trading hours
    # there might be 0 active 5m markets. We'll grab the latest 10 to demonstrate the structure.
    events_url = "https://gamma-api.polymarket.com/events?seriesSlug=btc-up-or-down-5m&limit=10"

    try:
        events_resp = requests.get(events_url)
        events_resp.raise_for_status()
        events = events_resp.json()

        # Extract the specific market slugs (the 5m markets usually only have one market per event)
        slugs = []
        for event in events:
            if event.get("closed"):
                continue # We ideally only want unclosed

            # Sometimes events have nested markets, we want the market slug.
            # Usually for this series, the event slug is similar to the market slug,
            # or the markets[0] slug is what we need.
            if "markets" in event and len(event["markets"]) > 0:
                slugs.append(event["markets"][0].get("slug"))
            else:
                slugs.append(event.get("slug"))

        # Fallback to generic btc markets if the 5m series doesn't have active events right now
        if not slugs:
            generic_url = "https://gamma-api.polymarket.com/events?closed=false&limit=100"
            generic_resp = requests.get(generic_url).json()
            for event in generic_resp:
                if "BTC" in event.get("title", "") or "Bitcoin" in event.get("title", ""):
                    if "markets" in event and len(event["markets"]) > 0:
                        slugs.append(event["markets"][0].get("slug"))

        btc_markets = []

        # 2. Iterate over the slugs and fetch using the exact requested URL structure
        for slug in slugs:
            if not slug: continue

            market_url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"
            m_resp = requests.get(market_url)
            if m_resp.status_code != 200:
                continue

            market = m_resp.json()

            # Parse tokens and prices
            clob_tokens = market.get("clobTokenIds", "[]")
            try:
                import json
                tokens = json.loads(clob_tokens)
            except:
                tokens = []

            yes_token = tokens[0] if len(tokens) > 0 else None
            no_token = tokens[1] if len(tokens) > 1 else None

            outcome_prices_raw = market.get("outcomePrices", '["0", "0"]')
            try:
                import json
                prices = json.loads(outcome_prices_raw)
            except:
                prices = ["0", "0"]

            # Add formatted market
            # For btc-updown-5m, outcome 0 is "Up", outcome 1 is "Down"
            # We map Up -> yes_price and Down -> no_price for compatibility
            btc_markets.append({
                "title": market.get("question", ""),
                "yes_price": float(prices[0]) if len(prices) > 0 else 0.0,
                "no_price": float(prices[1]) if len(prices) > 1 else 0.0,
                "yes_token_id": yes_token,
                "no_token_id": no_token,
                "end_date": market.get("endDate", ""),
                "condition_id": market.get("conditionId"),
                "active": market.get("active", False),
                "closed": market.get("closed", False)
            })

        # We only return active ones if there are any, else we return all fetched to show the UI
        active_unclosed_markets = [m for m in btc_markets if m["active"] and not m["closed"]]
        if active_unclosed_markets:
            return active_unclosed_markets
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
