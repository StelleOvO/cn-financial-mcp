"""
Category 6: Market Overview & Capital Flows (V0.5)

Tools:
  26. get_market_overview  - Major index snapshots
  27. get_money_flow       - Individual stock fund flow
  28. get_north_bound_flow - Northbound (HK->A) capital flow
  29. get_limit_up_down    - Daily limit-up/limit-down pool
  30. get_dragon_tiger     - Dragon & Tiger Board (institutional activity)

Data source for get_market_overview (v2 多源策略 — Tier 2):
  Tier 2 唯一源: 东方财富 (EM) — 在 Dispatcher 多源 Gate 中与 Tier 1 Sina 并行
  降级: 腾讯日线 (Tencent) — 终极降级 (非实时)
  注: Sina 竞速已移至 Tier 1 (scripts/fast_data.py)，MCP 内部不再重复
"""

from __future__ import annotations

import asyncio
import logging

import akshare as ak
from mcp.server.fastmcp import FastMCP

from ..utils.cache import TTL_DAILY, TTL_REALTIME, cache
from ..utils.formatter import df_to_json, error_response, slim_df
from ..utils.symbol import get_exchange, normalize_symbol

logger = logging.getLogger("cn-financial-mcp")


def register(mcp: FastMCP):
    """Register market overview tools with the MCP server."""

    @mcp.tool()
    async def get_market_overview() -> str:
        """
        获取A股主要指数实时行情快照 (Tier 2 — 东方财富单一源)。

        多源策略 v2: Dispatcher 在 Step 0 同时调用 Tier 1 (Bash Sina)
        和本工具 (MCP EM), 然后 Cross-Validate。MCP 内部不做竞速。

        Returns:
            主要指数实时行情 (JSON)，包含指数名称、最新点位、涨跌幅、
            成交量、成交额、_source=mcp_em、_freshness。
        """
        cache_key = "market_overview"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # ─── Tier 2: 东方财富 (EM) 单源 ───
        try:
            df = await asyncio.to_thread(ak.stock_zh_index_spot_em)
            if df is None or df.empty:
                raise ValueError("东方财富指数行情返回为空")

            slimmed = slim_df(df)
            json_str = df_to_json(slimmed, max_rows=30)
            import json
            records = json.loads(json_str)
            wrapped = {
                "data": records,
                "_source": "mcp_em",
                "_freshness": "realtime",
                "_timestamp": __import__("datetime").datetime.now().isoformat(),
            }
            json_str = json.dumps(wrapped, ensure_ascii=False)
            cache.set(cache_key, json_str, TTL_REALTIME)
            return json_str
        except Exception as e:
            logger.warning(f"[MarketOverview] EM 失败: {type(e).__name__}: {e}")

        # ─── 降级: 腾讯日线 ───
        try:
            from ..utils.sina_api import get_index_daily_tencent
            df = await asyncio.to_thread(get_index_daily_tencent)
            slimmed = slim_df(df)
            json_str = df_to_json(slimmed, max_rows=30)
            import json
            records = json.loads(json_str)
            wrapped = {
                "data": records,
                "_source": "tencent_daily",
                "_freshness": "stale_previous_close",
                "_warning": "⚠️ 东方财富实时API不可用，以下为上一交易日收盘数据",
                "_timestamp": __import__("datetime").datetime.now().isoformat(),
            }
            json_str = json.dumps(wrapped, ensure_ascii=False)
            cache.set(cache_key, json_str, TTL_REALTIME)
            return json_str
        except Exception as e2:
            return error_response(
                f"获取市场概览失败 (EM+Tencent 全部不可用): {e2}",
                "get_market_overview",
            )


    @mcp.tool()
    async def get_money_flow(symbol: str) -> str:
        """
        获取个股资金流向数据。

        Args:
            symbol: 6位股票代码，如 "600519"

        Returns:
            资金流向数据 (JSON)，包含日期、主力净流入、超大单净流入、
            大单净流入、中单净流入、小单净流入等。
        """
        symbol = normalize_symbol(symbol)
        cache_key = f"money_flow:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # market parameter is required: "sh" or "sz"
            market = get_exchange(symbol)  # returns "sh", "sz", or "bj"
            df = ak.stock_individual_fund_flow(stock=symbol, market=market)
            if df is None or df.empty:
                return error_response(
                    f"资金流向数据为空 ({symbol})", "get_money_flow"
                )
            df = slim_df(df)
            result = df_to_json(df, max_rows=30)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取资金流向失败 ({symbol}): {e}", "get_money_flow"
            )

    @mcp.tool()
    async def get_north_bound_flow() -> str:
        """
        获取北向资金（沪股通+深股通）净流入数据。

        北向资金是境外投资者通过港交所买入A股的资金，是市场重要的
        情绪和趋势指标。

        Returns:
            北向资金流入时间序列 (JSON)，包含日期、沪股通净流入、
            深股通净流入、北向资金合计净流入等。
        """
        cache_key = "north_bound_flow"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # stock_hsgt_north_net_flow_in_em has been removed;
            # use stock_hsgt_hist_em which provides historical HSGT data.
            # Valid symbols: "北向资金", "沪股通", "深股通", "南向资金" etc.
            df = await asyncio.to_thread(ak.stock_hsgt_hist_em, symbol="北向资金")
            if df is None or df.empty:
                return error_response(
                    "北向资金数据为空", "get_north_bound_flow"
                )
            df = slim_df(df)
            # from_tail=True: 取最近30条而非最早30条（数据按日期升序排列）
            result = df_to_json(df, max_rows=30, from_tail=True)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取北向资金失败: {e}", "get_north_bound_flow"
            )

    @mcp.tool()
    async def get_limit_up_down(direction: str = "涨停") -> str:
        """
        获取当日涨停板或跌停板股票池。

        Args:
            direction: "涨停" 获取涨停板，"跌停" 获取跌停板

        Returns:
            涨停/跌停股票列表 (JSON)，包含代码、名称、涨跌幅、封单额、
            首次涨停/跌停时间、最后涨停/跌停时间、连板天数等。
        """
        cache_key = f"limit_pool:{direction}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            import datetime
            today = datetime.date.today().strftime("%Y%m%d")

            if direction == "涨停":
                df = ak.stock_zt_pool_em(date=today)
            else:
                df = ak.stock_zt_pool_dtgc_em(date=today)

            result = df_to_json(df)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取{direction}板数据失败: {e}", "get_limit_up_down"
            )

    @mcp.tool()
    async def get_dragon_tiger(
        num_days: int = 5,
    ) -> str:
        """
        获取龙虎榜数据（机构和游资活跃买卖记录）。

        龙虎榜是沪深交易所公布的异动股票交易席位信息，反映机构和
        大型游资的交易行为。

        Args:
            num_days: 返回最近几个交易日的数据，默认5天

        Returns:
            龙虎榜数据 (JSON)，包含股票代码、名称、上榜原因、
            买入额、卖出额、净买入额、买方营业部等。
        """
        cache_key = f"dragon_tiger:{num_days}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            import datetime
            today = datetime.date.today()
            start = today - datetime.timedelta(days=num_days * 2)  # Buffer for non-trading days

            df = ak.stock_lhb_detail_em(
                start_date=start.strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            df = slim_df(df)
            result = df_to_json(df, max_rows=30)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取龙虎榜失败: {e}", "get_dragon_tiger"
            )
