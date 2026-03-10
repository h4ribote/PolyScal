from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import Settings

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
except Exception:
    ClobClient = None  # type: ignore[assignment]
    ApiCreds = Any  # type: ignore[misc,assignment]
    MarketOrderArgs = Any  # type: ignore[misc,assignment]
    OrderType = Any  # type: ignore[misc,assignment]


class PolyMarketClientError(Exception):
    pass


# Polymarket cursor pagination sentinels.
INITIAL_CURSOR = "MA=="
END_CURSOR = "LTE="


@dataclass
class MarketView:
    title: str
    condition_id: str | None
    yes_token_id: str | None
    no_token_id: str | None
    yes_price: float | None
    no_price: float | None
    end_time: str | None


class PolymarketClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = self._create_client()

    def _create_client(self) -> Any:
        if ClobClient is None:
            raise PolyMarketClientError("py-clob-client could not be imported. Install requirements first.")

        client = ClobClient(
            host=self.settings.polymarket_host,
            chain_id=self.settings.polymarket_chain_id,
            key=self.settings.polymarket_private_key or None,
            signature_type=self.settings.polymarket_signature_type,
            funder=self.settings.polymarket_funder or None,
        )

        if self.settings.polymarket_private_key:
            creds: ApiCreds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)

        return client

    def get_active_5m_btc_markets(self, limit: int = 100) -> list[MarketView]:
        results: list[MarketView] = []
        cursor = INITIAL_CURSOR

        while len(results) < limit:
            payload = self.client.get_simplified_markets(next_cursor=cursor)
            markets = payload.get("data") or []
            cursor = payload.get("next_cursor", END_CURSOR)

            for market in markets:
                if not self._is_target_market(market):
                    continue
                results.append(self._to_market_view(market))
                if len(results) >= limit:
                    break

            if cursor == END_CURSOR:
                break

        return results

    def place_order(self, token_id: str, side: str, outcome: str, size: float) -> dict[str, Any]:
        if side.upper() != "BUY":
            raise PolyMarketClientError("Only BUY side is supported by this endpoint.")
        if size <= 0:
            raise PolyMarketClientError("Order size must be greater than zero.")

        if not self.settings.polymarket_private_key:
            raise PolyMarketClientError("POLYMARKET_PRIVATE_KEY is required to place orders.")

        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=size,
            side=side.upper(),
            order_type=getattr(OrderType, "FOK", "FOK"),
        )
        signed_order = self.client.create_market_order(order_args)
        response = self.client.post_order(signed_order, getattr(OrderType, "FOK", "FOK"))
        return {
            "status": "ok",
            "token_id": token_id,
            "side": side.upper(),
            "outcome": outcome.upper(),
            "size": size,
            "exchange_response": response,
        }

    def _is_target_market(self, market: dict[str, Any]) -> bool:
        if not self._is_active(market):
            return False

        title = str(market.get("question") or market.get("title") or "").lower()
        if "btc" not in title and "bitcoin" not in title:
            return False

        five_min_tokens = ("5分", "5m", "5 m", "5-min", "5 min", "5minute", "5 minutes")
        return any(token in title for token in five_min_tokens)

    def _is_active(self, market: dict[str, Any]) -> bool:
        if market.get("closed") is True:
            return False
        if market.get("archived") is True:
            return False
        if "active" in market:
            return bool(market.get("active"))

        end_date = market.get("endDate") or market.get("end_date_iso")
        if not end_date:
            return True
        try:
            dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        except ValueError:
            return True
        return dt >= datetime.now(timezone.utc)

    def _to_market_view(self, market: dict[str, Any]) -> MarketView:
        outcomes = self._extract_outcomes(market)
        yes = outcomes.get("yes")
        no = outcomes.get("no")
        return MarketView(
            title=str(market.get("question") or market.get("title") or ""),
            condition_id=market.get("condition_id") or market.get("conditionId"),
            yes_token_id=(yes or {}).get("token_id"),
            no_token_id=(no or {}).get("token_id"),
            yes_price=self._safe_float((yes or {}).get("price")),
            no_price=self._safe_float((no or {}).get("price")),
            end_time=market.get("endDate") or market.get("end_date_iso"),
        )

    def _extract_outcomes(self, market: dict[str, Any]) -> dict[str, dict[str, Any]]:
        outcome_prices = market.get("outcomePrices") or market.get("outcome_prices") or []
        tokens = market.get("tokens") or []

        indexed: dict[str, dict[str, Any]] = {}
        for idx, token in enumerate(tokens):
            outcome_name = str(token.get("outcome") or "").strip().lower()
            if not outcome_name:
                continue
            indexed[outcome_name] = {
                "token_id": token.get("token_id") or token.get("tokenId"),
                "price": token.get("price") or (outcome_prices[idx] if idx < len(outcome_prices) else None),
            }

        if "yes" not in indexed and market.get("yesTokenId"):
            indexed["yes"] = {
                "token_id": market.get("yesTokenId"),
                "price": market.get("yesPrice"),
            }
        if "no" not in indexed and market.get("noTokenId"):
            indexed["no"] = {
                "token_id": market.get("noTokenId"),
                "price": market.get("noPrice"),
            }

        return indexed

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
