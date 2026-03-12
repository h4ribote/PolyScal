import asyncio
import json
import logging
import websockets
from typing import Dict, List, Any

logger = logging.getLogger("PolymarketWSAggregator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class PolymarketWSAggregator:
    def __init__(self):
        # Maps token_id -> float (price)
        self.prices: Dict[str, float] = {}
        # List of active markets
        self.active_markets: List[Dict[str, Any]] = []
        self.tasks: list[asyncio.Task] = []
        self._ws_tokens: set[str] = set()

    def update_markets(self, markets: List[Dict[str, Any]]):
        self.active_markets = markets
        # Update our known set of tokens
        new_tokens = set()
        for m in markets:
            if m.get("yes_token_id"):
                new_tokens.add(m["yes_token_id"])
            if m.get("no_token_id"):
                new_tokens.add(m["no_token_id"])

        # We'll just store them. The background task handles subscriptions.
        self._ws_tokens = new_tokens

        # For any tokens we don't have a price for, initialize to the REST price
        for m in markets:
            yes_id = m.get("yes_token_id")
            no_id = m.get("no_token_id")
            if yes_id and yes_id not in self.prices:
                self.prices[yes_id] = m.get("yes_price", 0.0)
            if no_id and no_id not in self.prices:
                self.prices[no_id] = m.get("no_price", 0.0)

    def get_markets(self) -> List[Dict[str, Any]]:
        # Return markets with latest prices
        result = []
        for m in self.active_markets:
            updated_m = dict(m)
            yes_id = m.get("yes_token_id")
            no_id = m.get("no_token_id")

            if yes_id and yes_id in self.prices:
                updated_m["yes_price"] = self.prices[yes_id]
            if no_id and no_id in self.prices:
                updated_m["no_price"] = self.prices[no_id]

            result.append(updated_m)
        return result

    async def _polymarket_ws(self):
        uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        while True:
            try:
                # Wait until we have some tokens to subscribe to
                while not self._ws_tokens:
                    await asyncio.sleep(1)

                async with websockets.connect(uri) as ws:
                    logger.info("Connected to Polymarket WebSocket")

                    # We keep track of what we are currently subscribed to
                    currently_subscribed = set(self._ws_tokens)

                    sub_msg = {
                        "assets_ids": list(currently_subscribed),
                        "type": "market"
                    }
                    await ws.send(json.dumps(sub_msg))

                    while True:
                        # Check if we need to update subscription
                        if self._ws_tokens != currently_subscribed:
                            logger.info("Tokens changed, reconnecting Polymarket WS...")
                            break # Breaking will disconnect and reconnect with new tokens

                        try:
                            # Use wait_for so we can periodically check tokens
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)

                            if msg == "PONG":
                                continue

                            data = json.loads(msg)

                            # Usually it returns a list of events
                            if isinstance(data, list):
                                for event in data:
                                    event_type = event.get("event_type")
                                    # price_change or best_bid_ask or book or last_trade_price
                                    # Handle different types of events that contain price info
                                    if event_type == "price_change" or event_type == "last_trade_price":
                                        token_id = event.get("asset_id")
                                        price = event.get("price")
                                        if token_id and price is not None:
                                            self.prices[token_id] = float(price)
                                            logger.debug(f"Updated price for {token_id}: {price}")
                                    elif event_type == "best_bid_ask":
                                        token_id = event.get("asset_id")
                                        bid = event.get("bid")
                                        ask = event.get("ask")
                                        if token_id and bid is not None and ask is not None:
                                            self.prices[token_id] = (float(bid) + float(ask)) / 2
                                    elif event_type == "book":
                                        # Contains full orderbook snapshot. We might want to look at best bid/ask
                                        token_id = event.get("asset_id")
                                        bids = event.get("bids", [])
                                        asks = event.get("asks", [])
                                        if token_id:
                                            # simplistic mid price or best bid
                                            if asks and bids:
                                                best_bid = float(bids[0]["price"])
                                                best_ask = float(asks[0]["price"])
                                                self.prices[token_id] = (best_bid + best_ask) / 2
                                            elif asks:
                                                self.prices[token_id] = float(asks[0]["price"])
                                            elif bids:
                                                self.prices[token_id] = float(bids[0]["price"])

                        except asyncio.TimeoutError:
                            # Send heartbeat string PING to polymarket server
                            await ws.send("PING")

            except Exception as e:
                logger.error(f"Polymarket WS error: {e}")
                await asyncio.sleep(5)

    async def _heartbeat_loop(self):
        # We could implement a ping loop if necessary, but websockets handles ping/pong by default
        # Actually polymarket says: "Send PING every 10 seconds." (as a string "PING")
        # However, the python websockets library automatically sends standard websocket PING frames.
        # If polymarket requires application-level PING strings, we'll need to send them.
        pass

    async def start(self):
        """Start background websocket tasks"""
        self.tasks.append(asyncio.create_task(self._polymarket_ws()))

    async def stop(self):
        """Stop all background tasks"""
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
