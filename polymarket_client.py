from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from py_clob_client import ClobClient
from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
from py_clob_client.constants import END_CURSOR

try:
    import config
except ModuleNotFoundError:
    config = None


@dataclass
class MarketView:
    market_id: str
    title: str
    yes_token_id: str
    no_token_id: str
    yes_price: float | None
    no_price: float | None
    end_time: str | None
    active: bool


class PolymarketClient:
    def __init__(self) -> None:
        if config is None:
            raise RuntimeError("config.py is missing; copy from config.py.example")

        if not getattr(config, "PRIVATE_KEY", ""):
            raise RuntimeError("config.PRIVATE_KEY is required")

        self._client = ClobClient(
            host=config.POLYMARKET_HOST,
            chain_id=config.CHAIN_ID,
            key=config.PRIVATE_KEY,
            signature_type=getattr(config, "SIGNATURE_TYPE", 0),
            funder=getattr(config, "FUNDER", None),
        )
        creds: ApiCreds = self._client.create_or_derive_api_creds()
        self._client.set_api_creds(creds)

    async def list_active_btc_5m_markets(self, limit: int = 100) -> list[MarketView]:
        markets: list[MarketView] = []
        next_cursor = "MA=="

        while next_cursor != END_CURSOR and len(markets) < limit:
            response = await asyncio.to_thread(
                self._client.get_simplified_markets,
                next_cursor,
            )
            page_markets = response.get("data", [])
            next_cursor = response.get("next_cursor", END_CURSOR)

            for raw in page_markets:
                parsed = self._parse_market(raw)
                if parsed is None:
                    continue
                markets.append(parsed)
                if len(markets) >= limit:
                    break

        return markets

    async def place_buy_order(self, token_id: str, size_usd: float) -> dict[str, Any]:
        if size_usd <= 0:
            raise ValueError("size must be positive")

        market_args = MarketOrderArgs(
            token_id=token_id,
            amount=size_usd,
            side="BUY",
            order_type=OrderType.FOK,
        )

        signed_order = await asyncio.to_thread(self._client.create_market_order, market_args)
        result = await asyncio.to_thread(
            self._client.post_order,
            signed_order,
            OrderType.FOK,
            False,
        )
        return result

    def _parse_market(self, raw: dict[str, Any]) -> MarketView | None:
        title = str(raw.get("question") or raw.get("title") or "")
        if not self._is_target_market(raw, title):
            return None

        token_map = self._extract_outcome_token_map(raw)
        yes_token_id = token_map.get("YES")
        no_token_id = token_map.get("NO")
        if not yes_token_id or not no_token_id:
            return None

        price_map = self._extract_outcome_price_map(raw)
        end_time = (
            raw.get("endDate")
            or raw.get("end_date_iso")
            or raw.get("end_date")
            or raw.get("closedTime")
        )
        return MarketView(
            market_id=str(raw.get("conditionId") or raw.get("id") or ""),
            title=title,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            yes_price=price_map.get("YES"),
            no_price=price_map.get("NO"),
            end_time=end_time,
            active=bool(raw.get("active", True)),
        )

    def _is_target_market(self, raw: dict[str, Any], title: str) -> bool:
        lower = title.lower()
        is_active = bool(raw.get("active", True)) and not bool(raw.get("closed", False))
        if not is_active:
            return False

        has_btc = "btc" in lower or "bitcoin" in lower
        if not has_btc:
            return False

        has_5m = bool(
            re.search(
                r"(5\s*(m|min|minute|minutes|分))|(every\s*5\s*minutes)|(5-minute)",
                lower,
            )
        )
        if has_5m:
            return True

        end_time = raw.get("endDate") or raw.get("end_date_iso") or raw.get("end_date")
        if not end_time:
            return False
        try:
            dt = datetime.fromisoformat(str(end_time).replace("Z", "+00:00"))
        except ValueError:
            return False

        return dt.second == 0 and dt.minute % 5 == 0

    def _extract_outcome_token_map(self, raw: dict[str, Any]) -> dict[str, str]:
        token_map: dict[str, str] = {}

        tokens = raw.get("tokens")
        if isinstance(tokens, list):
            for token in tokens:
                if not isinstance(token, dict):
                    continue
                outcome = str(token.get("outcome", "")).upper()
                token_id = token.get("token_id") or token.get("tokenId")
                if outcome in {"YES", "NO"} and token_id:
                    token_map[outcome] = str(token_id)

        outcomes_raw = raw.get("outcomes")
        clob_token_ids_raw = raw.get("clobTokenIds")
        outcomes = self._force_list(outcomes_raw)
        clob_token_ids = self._force_list(clob_token_ids_raw)
        if outcomes and clob_token_ids and len(outcomes) == len(clob_token_ids):
            for outcome, token_id in zip(outcomes, clob_token_ids):
                out_upper = str(outcome).upper()
                if out_upper in {"YES", "NO"}:
                    token_map[out_upper] = str(token_id)

        return token_map

    def _extract_outcome_price_map(self, raw: dict[str, Any]) -> dict[str, float | None]:
        result: dict[str, float | None] = {"YES": None, "NO": None}

        tokens = raw.get("tokens")
        if isinstance(tokens, list):
            for token in tokens:
                if not isinstance(token, dict):
                    continue
                outcome = str(token.get("outcome", "")).upper()
                if outcome not in {"YES", "NO"}:
                    continue
                price_raw = token.get("price")
                result[outcome] = self._to_float_or_none(price_raw)

        outcomes = self._force_list(raw.get("outcomes"))
        prices = self._force_list(raw.get("outcomePrices"))
        if outcomes and prices and len(outcomes) == len(prices):
            for outcome, price in zip(outcomes, prices):
                out_upper = str(outcome).upper()
                if out_upper in {"YES", "NO"} and result[out_upper] is None:
                    result[out_upper] = self._to_float_or_none(price)

        return result

    @staticmethod
    def _force_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []

    @staticmethod
    def _to_float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
