"""
Category 8: Macro Economics, FX, Bonds & Special Data (V0.4)

Tools:
  35. get_macro_gdp         - China GDP data
  36. get_macro_cpi         - China CPI data
  37. get_macro_pmi         - China PMI data
  38. get_macro_money_supply - Money supply (M0/M1/M2)
  39. get_fx_rate           - Foreign exchange rates
  40. get_bond_yield_curve  - China government bond yields
  41. get_margin_trading    - Margin trading (融资融券) data
  42. get_insider_trading   - Insider trading records
"""

from __future__ import annotations

import asyncio
import datetime as _dt

import akshare as ak
from mcp.server.fastmcp import FastMCP

from ..utils.cache import TTL_DAILY, TTL_FINANCIAL, TTL_MACRO, cache
from ..utils.formatter import df_to_json, error_response, slim_df
from ..utils.symbol import get_exchange, normalize_symbol


def _get_recent_weekdays(n: int = 3) -> list[str]:
    """获取最近 n 个工作日（周一~周五），格式 YYYYMMDD。

    不含节假日判断——如果当天是节假日，API 会返回空，
    调用方按顺序尝试即可。
    """
    days = []
    d = _dt.date.today()
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d.strftime("%Y%m%d"))
        d -= _dt.timedelta(days=1)
    return days


def register(mcp: FastMCP):
    """Register macroeconomic and special data tools with the MCP server."""

    @mcp.tool()
    async def get_macro_gdp() -> str:
        """
        获取中国GDP数据（季度）。

        Returns:
            GDP数据 (JSON)，包含季度、国内生产总值、同比增长、
            第一/二/三产业增加值等。
        """
        cache_key = "macro_gdp"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.macro_china_gdp()
            result = df_to_json(df, max_rows=40)
            cache.set(cache_key, result, TTL_MACRO)
            return result
        except Exception as e:
            return error_response(f"获取GDP数据失败: {e}", "get_macro_gdp")

    @mcp.tool()
    async def get_macro_cpi() -> str:
        """
        获取中国CPI消费者价格指数数据（月度）。

        Returns:
            CPI数据 (JSON)，包含月份、全国居民消费价格指数、
            食品CPI、非食品CPI、同比、环比等。
        """
        cache_key = "macro_cpi"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.macro_china_cpi()
            result = df_to_json(df, max_rows=60)
            cache.set(cache_key, result, TTL_MACRO)
            return result
        except Exception as e:
            return error_response(f"获取CPI数据失败: {e}", "get_macro_cpi")

    @mcp.tool()
    async def get_macro_pmi() -> str:
        """
        获取中国PMI采购经理指数数据（月度）。

        PMI > 50 表示制造业扩张，< 50 表示收缩，是重要的经济领先指标。

        Returns:
            PMI数据 (JSON)，包含月份、制造业PMI、非制造业PMI、
            新订单指数、生产指数等分项。
        """
        cache_key = "macro_pmi"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.macro_china_pmi()
            result = df_to_json(df, max_rows=60)
            cache.set(cache_key, result, TTL_MACRO)
            return result
        except Exception as e:
            return error_response(f"获取PMI数据失败: {e}", "get_macro_pmi")

    @mcp.tool()
    async def get_macro_money_supply() -> str:
        """
        获取中国货币供应量数据（M0/M1/M2，月度）。

        M2 增速是市场流动性的核心指标，直接影响股市资金面。

        Returns:
            货币供应数据 (JSON)，包含月份、M0、M1、M2余额及同比增速等。
        """
        cache_key = "macro_money_supply"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.macro_china_money_supply()
            result = df_to_json(df, max_rows=60)
            cache.set(cache_key, result, TTL_MACRO)
            return result
        except Exception as e:
            return error_response(
                f"获取货币供应量失败: {e}", "get_macro_money_supply"
            )

    @mcp.tool()
    async def get_fx_rate(symbol: str = "美元兑人民币") -> str:
        """
        获取外汇汇率数据。

        Args:
            symbol: 货币对名称，可选：
                "美元兑人民币"、"欧元兑人民币"、"英镑兑人民币"、
                "日元兑人民币"、"港币兑人民币" 等

        Returns:
            汇率数据 (JSON)，包含日期、买入价、卖出价、中间价等。
        """
        cache_key = f"fx_rate:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.fx_spot_quote()
            # Filter for the specified currency pair
            if symbol:
                name_cols = [
                    c for c in df.columns
                    if "名称" in c or "货币" in c or "品种" in c
                ]
                if name_cols:
                    mask = df[name_cols[0]].str.contains(
                        symbol.replace("兑", ""), case=False, na=False
                    )
                    filtered = df[mask]
                    if not filtered.empty:
                        df = filtered

            result = df_to_json(df, max_rows=30)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取汇率数据失败 ({symbol}): {e}", "get_fx_rate"
            )

    @mcp.tool()
    async def get_bond_yield_curve() -> str:
        """
        获取中国国债收益率曲线数据。

        包含不同期限（1年、3年、5年、7年、10年、30年）的国债收益率，
        是无风险利率的基准，用于DCF贴现率估算。

        Returns:
            国债收益率数据 (JSON)，包含日期、各期限收益率等。
        """
        cache_key = "bond_yield_curve"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            today = _dt.date.today()
            start = today - _dt.timedelta(days=90)

            df = await asyncio.to_thread(
                ak.bond_china_yield,
                start_date=start.strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            if df is None or df.empty:
                return error_response(
                    "国债收益率数据为空（请检查 akshare bond_china_yield 接口是否可用）",
                    "get_bond_yield_curve",
                )
            result = df_to_json(df, max_rows=60, from_tail=True)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取国债收益率失败: {e}", "get_bond_yield_curve"
            )

    @mcp.tool()
    async def get_margin_trading(symbol: str = "") -> str:
        """
        获取融资融券数据（两融余额）。

        融资余额增加表示市场加杠杆做多，是市场情绪的重要参考。

        Args:
            symbol: 6位股票代码，查询个股融资融券。为空则返回市场汇总。

        Returns:
            融资融券数据 (JSON)，包含融资余额、融券余额、融资买入额、
            融资偿还额等。
        """
        cache_key = f"margin_trading:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # 尝试最近3个工作日，避免非交易日/盘前 API 拒绝连接
            candidate_dates = _get_recent_weekdays(3)
            df = None

            if symbol:
                symbol = normalize_symbol(symbol)
                exchange = get_exchange(symbol)

                for date_str in candidate_dates:
                    if df is not None and not df.empty:
                        break
                    # 先尝试对应交易所
                    primary = (
                        ak.stock_margin_detail_sse if exchange == "sh"
                        else ak.stock_margin_detail_szse
                    )
                    try:
                        df = await asyncio.to_thread(primary, date=date_str)
                    except Exception:
                        pass
                    # 再尝试另一个交易所
                    if df is None or df.empty:
                        alt = (
                            ak.stock_margin_detail_szse if exchange == "sh"
                            else ak.stock_margin_detail_sse
                        )
                        try:
                            df = await asyncio.to_thread(alt, date=date_str)
                        except Exception:
                            pass

                if df is not None and not df.empty:
                    code_cols = [
                        c for c in df.columns
                        if "代码" in c or "证券代码" in c or "标的" in c
                    ]
                    if code_cols:
                        df = df[df[code_cols[0]].astype(str).str.contains(symbol)]
            else:
                # 市场汇总：逐日尝试，成功即停
                for date_str in candidate_dates:
                    try:
                        df = await asyncio.to_thread(
                            ak.stock_margin_detail_sse, date=date_str
                        )
                        if df is not None and not df.empty:
                            break
                    except Exception:
                        pass
                    try:
                        df = await asyncio.to_thread(
                            ak.stock_margin_detail_szse, date=date_str
                        )
                        if df is not None and not df.empty:
                            break
                    except Exception:
                        pass

            if df is None or df.empty:
                return error_response(
                    f"融资融券数据为空，已尝试最近3个工作日 ({symbol})",
                    "get_margin_trading",
                )

            df = slim_df(df)
            result = df_to_json(df, max_rows=30)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取融资融券数据失败 ({symbol}): {e}", "get_margin_trading"
            )

    @mcp.tool()
    async def get_insider_trading(symbol: str = "") -> str:
        """
        获取股东/高管增减持（内部交易）数据。

        大股东和高管的增减持行为是市场的重要信号。

        Args:
            symbol: 6位股票代码，查询个股内部交易。为空则返回全市场最新数据。

        Returns:
            内部交易数据 (JSON)，包含股票代码、名称、变动人、关系、
            变动股数、变动金额、变动后持股数等。
        """
        cache_key = f"insider_trading:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.stock_inner_trade_xq()
            if symbol:
                symbol = normalize_symbol(symbol)
                code_cols = [
                    c for c in df.columns
                    if "代码" in c or "symbol" in c.lower() or "code" in c.lower()
                ]
                if code_cols:
                    df = df[df[code_cols[0]].astype(str).str.contains(symbol)]

            df = slim_df(df)
            result = df_to_json(df, max_rows=30)
            cache.set(cache_key, result, TTL_DAILY)
            return result
        except Exception as e:
            return error_response(
                f"获取内部交易数据失败 ({symbol}): {e}", "get_insider_trading"
            )
