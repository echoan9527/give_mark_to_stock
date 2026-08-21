'''
Author: Chengya
Description: 主板候选实盘信号扫描脚本，使用 ai_back_test_all_stock.py 中冻结后的候选主策略逻辑。
'''
import os
import time
import random
import shutil
from datetime import datetime, timedelta
import html

import numpy as np
import pandas as pd

import ai_back_test_all_stock as bt


LIVE_CONFIG = {
    # None 表示使用今天日期；如果需要回放某个历史交易日，可填 "YYYYMMDD"。
    "SCAN_END_DATE": None,
    "OUTPUT_ROOT": "live_outputs",
    "CACHE_DIR": "stock_data_cache_live_main",
    "HISTORY_START": "20210101",
    "LATEST_CSV_ALIAS": "Today_Buy_Signals_MAIN.csv",
    "LATEST_HTML_ALIAS": "Today_Buy_Signals_MAIN.html",
    "POSITION_FILE": "Live_Positions_MAIN.csv",
    "LATEST_SELL_CSV_ALIAS": "Today_Sell_Check_MAIN.csv",
    "LATEST_SELL_HTML_ALIAS": "Today_Sell_Check_MAIN.html",

    # 当前冻结候选实盘参数。
    "BUY_SCORE_THRESHOLD": 70,
    "STOP_LOSS_RATE": -0.09,
    "MAX_HOLD_DAYS": 20,
    "RSI_OVERSOLD": 80,
    "TIME_SUNK_TOLERANCE": 0.03,

    # 实盘执行纪律：正常下一交易日开盘买，错过后只在信号日收盘价 +2% 内考虑补买。
    "NORMAL_MAX_BUY_GAP_RATE": 0.04,
    "MISSED_BUY_MAX_GAP_FROM_SIGNAL_CLOSE": 0.02,
}

POSITION_COLUMNS = [
    "代码",
    "名称",
    "买入日",
    "买入价",
    "买入数量",
    "当前收盘",
    "持仓市值",
    "止损线",
    "止盈启动线",
    "信号日市场环境",
    "备注",
]


def ensure_live_cache_dir():
    os.makedirs(LIVE_CONFIG["CACHE_DIR"], exist_ok=True)


def apply_live_overrides(scan_end):
    overrides = {
        "TARGET_BOARD": "MAIN",
        "MAX_STOCKS_PER_BOARD": None,
        "POOL_SAMPLE_SEED": None,
        "TEST_END": scan_end,
        "BUY_EXECUTION_DELAY_DAYS": 1,
        "SELL_EXECUTION_DELAY_DAYS": 1,
        "REVALIDATE_DELAYED_BUY_SIGNAL": False,
        "MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE": None,
        "MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN": None,
        "REQUIRE_DELAYED_BUY_ABOVE_MA20": False,
        "MAX_BUY_GAP_RATE": LIVE_CONFIG["NORMAL_MAX_BUY_GAP_RATE"],
        "ENABLE_CANDIDATE_RANKING": False,
        "CANDIDATE_RANKING_REGIMES": None,
        "RANK_PRIMARY_SCORE_BAND": None,
        "MAX_ENTRY_DISTANCE_MA20": None,
        "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
        "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
        "WEAK_ALLOW_HIGH_SCORE_BUY": True,
    }
    bt.CONFIG.update(overrides)


def normalize_stock_daily(df):
    if df is None or df.empty:
        return None
    df = df.copy()
    rename_map = {
        "date": "日期",
        "open": "开盘",
        "close": "收盘",
        "high": "最高",
        "low": "最低",
        "volume": "成交量",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    if "日期" not in df.columns:
        return None
    df["日期"] = pd.to_datetime(df["日期"])
    df.set_index("日期", inplace=True)
    df.sort_index(inplace=True)
    return df


def recalc_stock_indicators(df):
    df = df.copy().sort_index()
    df["MA5"] = df["收盘"].rolling(5).mean()
    df["MA10"] = df["收盘"].rolling(10).mean()
    df["MA20"] = df["收盘"].rolling(20).mean()
    df["MA60"] = df["收盘"].rolling(60).mean()
    df["RSI14"] = bt.calculate_rsi(df["收盘"], 14)
    df["Vol_MA20"] = df["成交量"].rolling(20).mean()
    df["MA60_prev5"] = df["MA60"].shift(5)
    df["MA20_prev5"] = df["MA20"].shift(5)
    df["High_20"] = df["收盘"].rolling(20).max().shift(1)
    df = bt.ensure_stock_runtime_columns(df)
    return df.dropna()


def fetch_stock_increment(symbol, start_date, end_date):
    prefix = "sh" if symbol.startswith(("60", "68")) else "sz"
    full_symbol = f"{prefix}{symbol}"
    return bt.ak.stock_zh_a_daily(
        symbol=full_symbol,
        adjust="qfq",
        start_date=start_date,
        end_date=end_date,
    )


def load_live_stock_data(symbol, name, scan_end):
    ensure_live_cache_dir()
    prefix = "sh" if symbol.startswith(("60", "68")) else "sz"
    full_symbol = f"{prefix}{symbol}"
    cache_path = os.path.join(LIVE_CONFIG["CACHE_DIR"], f"{full_symbol}.csv")
    scan_end_dt = pd.to_datetime(scan_end)
    cached = None

    if os.path.exists(cache_path):
        try:
            cached = pd.read_csv(cache_path, index_col="日期", parse_dates=True)
            cached.sort_index(inplace=True)
        except Exception:
            cached = None

    if cached is not None and not cached.empty:
        latest_cached = cached.index[-1]
        if latest_cached >= scan_end_dt:
            return cached if bt.passes_data_quality_filter(cached) else None
        start_date = (latest_cached + timedelta(days=1)).strftime("%Y%m%d")
    else:
        start_date = LIVE_CONFIG["HISTORY_START"]

    fetched = None
    for attempt in range(3):
        try:
            raw = fetch_stock_increment(symbol, start_date, scan_end)
            fetched = normalize_stock_daily(raw)
            break
        except Exception:
            if attempt < 2:
                time.sleep(random.uniform(1.0, 2.5))

    if cached is None:
        combined = fetched
    elif fetched is None or fetched.empty:
        combined = cached
    else:
        combined = pd.concat([cached, fetched])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

    if combined is None or combined.empty:
        return None

    combined = recalc_stock_indicators(combined)
    if not bt.passes_data_quality_filter(combined):
        return None
    combined.to_csv(cache_path, encoding="utf-8-sig")
    if fetched is not None and not fetched.empty:
        time.sleep(random.uniform(0.05, 0.15))
    return combined


def load_live_market_data(scan_end):
    pool = bt.get_filtered_market_pool()
    print("[*] 正在加载主板实盘缓存/增量数据...")
    market_data, active_pool = {}, {}
    skipped = 0
    for idx, (code, name) in enumerate(pool.items(), start=1):
        df = load_live_stock_data(code, name, scan_end)
        if df is None:
            skipped += 1
            continue
        market_data[code] = df
        active_pool[code] = name
        if idx % 300 == 0:
            print(f"    进度 {idx}/{len(pool)} | 有效 {len(market_data)} | 跳过 {skipped}")
    print(f"[*] 实盘可用标的共计 {len(market_data)} 只，过滤/缺失 {skipped} 只。")
    return market_data, active_pool


def recalc_benchmark_indicators(df):
    df = df.copy().sort_index()
    df["MA20"] = df["收盘"].rolling(20).mean()
    df["MA60"] = df["收盘"].rolling(60).mean()
    df["MA20_prev5"] = df["MA20"].shift(5)
    return df.dropna()


def load_live_benchmark(scan_end):
    ensure_live_cache_dir()
    cache_path = os.path.join(LIVE_CONFIG["CACHE_DIR"], "sh000300_benchmark.csv")
    scan_end_dt = pd.to_datetime(scan_end)
    cached = None
    if os.path.exists(cache_path):
        try:
            cached = pd.read_csv(cache_path, index_col="日期", parse_dates=True)
            cached.sort_index(inplace=True)
        except Exception:
            cached = None

    if cached is not None and not cached.empty and cached.index[-1] >= scan_end_dt:
        return cached

    try:
        raw = bt.ak.stock_zh_index_daily(symbol="sh000300")
        raw.rename(columns={"date": "日期", "close": "收盘"}, inplace=True)
        raw["日期"] = pd.to_datetime(raw["日期"])
        raw.set_index("日期", inplace=True)
        raw.sort_index(inplace=True)
        raw = raw.loc[:scan_end_dt]
        df = recalc_benchmark_indicators(raw)
        df.to_csv(cache_path, encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"[!] 基准数据更新失败，尝试使用本地缓存: {e}")
        return cached


def find_scan_date(benchmark_data, market_data):
    if benchmark_data is not None and not benchmark_data.empty:
        benchmark_dates = [d for d in benchmark_data.index if d <= pd.to_datetime(bt.CONFIG["TEST_END"])]
        if benchmark_dates:
            return benchmark_dates[-1]

    all_dates = sorted(set().union(*(set(df.index) for df in market_data.values())))
    valid_dates = [d for d in all_dates if d <= pd.to_datetime(bt.CONFIG["TEST_END"])]
    return valid_dates[-1] if valid_dates else None


def build_live_signal_row(symbol, name, df, scan_date, score, rank_score, market_context, regime_controls):
    row = df.loc[scan_date]
    snapshot = bt.build_signal_snapshot(symbol, df, scan_date, market_context)
    close = bt.safe_float(row["收盘"])
    ma20 = bt.safe_float(row["MA20"])
    ma60 = bt.safe_float(row["MA60"])
    volume_ratio = bt.safe_float(row["成交量"]) / (bt.safe_float(row["Vol_MA20"], 0) + 1e-9)
    normal_max_buy_price = close * (1 + LIVE_CONFIG["NORMAL_MAX_BUY_GAP_RATE"])
    missed_buy_max_price = close * (1 + LIVE_CONFIG["MISSED_BUY_MAX_GAP_FROM_SIGNAL_CLOSE"])
    stop_loss_ref = close * (1 + LIVE_CONFIG["STOP_LOSS_RATE"])

    return {
        "代码": str(symbol).zfill(6),
        "名称": name,
        "信号日": scan_date.strftime("%Y-%m-%d"),
        "市场环境": regime_controls["regime"],
        "买入分数": score,
        "排序分": round(rank_score, 2),
        "收盘价": round(close, 3),
        "次日最高可买价": round(normal_max_buy_price, 3),
        "错过补买最高价": round(missed_buy_max_price, 3),
        "止损参考价": round(stop_loss_ref, 3),
        "建议单票仓位": regime_controls["position_per_stock"],
        "当前环境最多持仓": regime_controls["max_holdings"],
        "RSI14": round(bt.safe_float(row["RSI14"]), 2),
        "量比": round(volume_ratio, 2),
        "20日均成交额": round(bt.safe_float(row.get("Amount_MA20")), 2),
        "距MA20": close / ma20 - 1 if ma20 > 0 else np.nan,
        "距MA60": close / ma60 - 1 if ma60 > 0 else np.nan,
        "突破20日新高": snapshot["信号日突破20日新高"],
        "前5日阳线数": snapshot["信号日前5日阳线数"],
        "执行说明": "下个交易日开盘买；若高于次日最高可买价则放弃；错过开盘后只在错过补买最高价内考虑。",
    }


def normalize_position_code(value):
    if pd.isna(value):
        return ""
    text = str(value).strip().replace(",", "")
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def ensure_position_file():
    position_file = LIVE_CONFIG["POSITION_FILE"]
    if os.path.exists(position_file):
        try:
            existing = pd.read_csv(position_file)
            missing = [col for col in POSITION_COLUMNS if col not in existing.columns]
            if missing:
                for col in missing:
                    existing[col] = ""
                existing = existing[POSITION_COLUMNS]
                existing.to_csv(position_file, index=False, encoding="utf-8-sig")
        except Exception:
            pass
        return
    pd.DataFrame(columns=POSITION_COLUMNS).to_csv(position_file, index=False, encoding="utf-8-sig")
    print(f"[*] 已创建持仓模板: {position_file}")


def load_positions():
    ensure_position_file()
    try:
        positions = pd.read_csv(LIVE_CONFIG["POSITION_FILE"])
    except Exception as e:
        print(f"[!] 持仓文件读取失败: {e}")
        return pd.DataFrame(columns=POSITION_COLUMNS)

    if positions.empty:
        return pd.DataFrame(columns=POSITION_COLUMNS)

    for col in POSITION_COLUMNS:
        if col not in positions.columns:
            positions[col] = ""
    positions["代码"] = positions["代码"].map(normalize_position_code)
    positions = positions[positions["代码"] != ""].copy()
    return positions


def calc_weak_regime_days(market_context, buy_date, scan_date):
    dates = sorted(d for d in market_context.keys() if buy_date <= d <= scan_date)
    total_weak_days = 0
    consecutive_weak_days = 0
    max_consecutive_weak_days = 0
    for date in dates:
        regime = market_context.get(date, {}).get("regime")
        if regime == "弱":
            total_weak_days += 1
            consecutive_weak_days += 1
            max_consecutive_weak_days = max(max_consecutive_weak_days, consecutive_weak_days)
        else:
            consecutive_weak_days = 0
    return consecutive_weak_days, total_weak_days, max_consecutive_weak_days


def live_ma20_breakdown(df, scan_date):
    confirm_days = bt.CONFIG.get("BREAKDOWN_CONFIRM_DAYS", 3)
    history = df.loc[:scan_date].tail(confirm_days)
    if len(history) < confirm_days:
        return False
    return bool((history["收盘"] < history["MA20"]).all())


def position_value(row, key, default=np.nan):
    if key not in row or pd.isna(row[key]) or row[key] == "":
        return default
    return row[key]


def evaluate_position(row, df, scan_date, market_context, stock_pool):
    symbol = normalize_position_code(row.get("代码"))
    name = position_value(row, "名称", stock_pool.get(symbol, "未知"))
    buy_date = pd.to_datetime(position_value(row, "买入日", ""))
    buy_price = bt.safe_float(position_value(row, "买入价", np.nan))
    shares = int(bt.safe_float(position_value(row, "买入数量", 0), 0))
    signal_regime = str(position_value(row, "信号日市场环境", "")).strip()
    note = str(position_value(row, "备注", "")).strip()

    if pd.isna(buy_date) or pd.isna(buy_price) or buy_price <= 0:
        return {
            "代码": symbol,
            "名称": name,
            "操作建议": "检查持仓数据",
            "触发原因": "买入日或买入价缺失",
        }
    if df is None or df.empty or scan_date not in df.index:
        return {
            "代码": symbol,
            "名称": name,
            "买入日": buy_date.strftime("%Y-%m-%d") if not pd.isna(buy_date) else "",
            "买入价": buy_price,
            "操作建议": "检查行情数据",
            "触发原因": "没有找到该持仓的最新行情",
        }

    history = df.loc[(df.index >= buy_date) & (df.index <= scan_date)]
    if history.empty:
        return {
            "代码": symbol,
            "名称": name,
            "买入日": buy_date.strftime("%Y-%m-%d"),
            "买入价": buy_price,
            "操作建议": "检查持仓数据",
            "触发原因": "买入日晚于当前扫描日或行情不足",
        }

    today_k = df.loc[scan_date]
    close = bt.safe_float(today_k["收盘"])
    ma20 = bt.safe_float(today_k["MA20"])
    rsi14 = bt.safe_float(today_k["RSI14"])
    highest_close = max(float(history["收盘"].max()), buy_price)
    return_rate = close / buy_price - 1
    drawdown_from_high = close / highest_close - 1 if highest_close > 0 else np.nan
    holding_days = len(history)
    current_regime = market_context.get(scan_date, {}).get("regime", "")
    weak_days, total_weak_days, max_weak_days = calc_weak_regime_days(market_context, buy_date, scan_date)
    market_value = close * shares
    stop_loss_line = buy_price * (1 + LIVE_CONFIG["STOP_LOSS_RATE"])
    trail_start_line = buy_price * (1 + bt.CONFIG["TRAIL_PROFIT_TRIGGER"])

    sell_reason = ""
    if return_rate <= LIVE_CONFIG["STOP_LOSS_RATE"]:
        sell_reason = "绝对止损"
    elif live_ma20_breakdown(df, scan_date):
        sell_reason = "破位防守"
    elif (
        current_regime == "弱"
        and signal_regime != "弱"
        and weak_days >= bt.CONFIG["WEAK_HOLDING_EXIT_DAYS"]
        and return_rate <= bt.CONFIG["WEAK_HOLDING_EXIT_MAX_RETURN"]
    ):
        sell_reason = "转弱持仓退出"
    elif (
        highest_close >= buy_price * (1 + bt.CONFIG["TRAIL_PROFIT_TRIGGER"])
        and close <= highest_close * (1 - bt.CONFIG["TRAIL_DRAWDOWN_RATE"])
    ):
        sell_reason = "回撤止盈"
    elif bt.CONFIG["ENABLE_EXCITEMENT_TAKE_PROFIT"] and return_rate > 0.15 and rsi14 > LIVE_CONFIG["RSI_OVERSOLD"]:
        sell_reason = "亢奋止盈"
    elif (
        holding_days >= LIVE_CONFIG["MAX_HOLD_DAYS"]
        and -LIVE_CONFIG["TIME_SUNK_TOLERANCE"] <= return_rate <= LIVE_CONFIG["TIME_SUNK_TOLERANCE"]
    ):
        sell_reason = "沉没止损"

    recent_break_days = ""
    if len(history) >= bt.CONFIG["BREAKDOWN_CONFIRM_DAYS"]:
        recent = history.tail(bt.CONFIG["BREAKDOWN_CONFIRM_DAYS"])
        recent_break_days = int((recent["收盘"] < recent["MA20"]).sum())

    return {
        "代码": symbol,
        "名称": name,
        "买入日": buy_date.strftime("%Y-%m-%d"),
        "扫描日": scan_date.strftime("%Y-%m-%d"),
        "买入价": round(buy_price, 3),
        "买入数量": shares,
        "最新收盘价": round(close, 3),
        "当前盈亏率": return_rate,
        "持仓天数": holding_days,
        "最高收盘价": round(highest_close, 3),
        "从高点回撤": drawdown_from_high,
        "MA20": round(ma20, 3),
        "RSI14": round(rsi14, 2),
        "当前市场环境": current_regime,
        "信号日市场环境": signal_regime,
        "连续弱市天数": weak_days,
        "累计弱市天数": total_weak_days,
        "最大连续弱市天数": max_weak_days,
        "近3日破位天数": recent_break_days,
        "持仓市值": round(market_value, 2),
        "止损线": round(stop_loss_line, 3),
        "止盈启动线": round(trail_start_line, 3),
        "备注": note,
        "操作建议": "明日开盘卖出" if sell_reason else "继续持有",
        "触发原因": sell_reason if sell_reason else "",
        "参考止损价": round(buy_price * (1 + LIVE_CONFIG["STOP_LOSS_RATE"]), 3),
    }


def build_sell_check(market_data, stock_pool, scan_date, market_context):
    positions = load_positions()
    rows = []
    for _, pos in positions.iterrows():
        symbol = normalize_position_code(pos.get("代码"))
        df = market_data.get(symbol)
        if df is None:
            df = load_live_stock_data(symbol, str(pos.get("名称", "")), bt.CONFIG["TEST_END"])
        rows.append(evaluate_position(pos, df, scan_date, market_context, stock_pool))

    sell_df = pd.DataFrame(rows)
    if not sell_df.empty:
        sell_df.sort_values(by=["操作建议", "当前盈亏率"], ascending=[False, True], inplace=True)
    return sell_df


def format_pct(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.2f}%"


def render_html_report(output_path, signal_df, scan_date, market_state, regime_controls, stock_count):
    title = f"主板今日候选信号 - {scan_date.strftime('%Y-%m-%d')}"
    rows = []
    for _, row in signal_df.iterrows():
        cells = []
        for col in signal_df.columns:
            value = row[col]
            if col in {"建议单票仓位", "距MA20", "距MA60"}:
                display = format_pct(value)
            elif isinstance(value, float):
                display = f"{value:,.3f}".rstrip("0").rstrip(".")
            else:
                display = value
            cells.append(f"<td>{html.escape(str(display))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")

    header = "".join(f"<th>{html.escape(str(col))}</th>" for col in signal_df.columns)
    table_html = (
        '<p class="empty">今日没有候选信号。</p>'
        if signal_df.empty
        else f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 28px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2937; background: #f7f8fa; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    .meta {{ margin: 0 0 18px; color: #4b5563; line-height: 1.7; }}
    .table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #edf0f3; white-space: nowrap; text-align: right; }}
    th {{ position: sticky; top: 0; background: #f3f4f6; color: #374151; }}
    th:nth-child(1), td:nth-child(1), th:nth-child(2), td:nth-child(2), th:last-child, td:last-child {{ text-align: left; }}
    tr:hover td {{ background: #f9fafb; }}
    .empty {{ padding: 18px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">
    市场环境：{html.escape(str(regime_controls["regime"]))} |
    MA20宽度：{format_pct(market_state.get("ma20_ratio", np.nan))} |
    MA60宽度：{format_pct(market_state.get("ma60_ratio", np.nan))} |
    可用股票数：{stock_count} |
    当前环境最多持仓：{regime_controls["max_holdings"]} |
    建议单票仓位：{format_pct(regime_controls["position_per_stock"])}
  </div>
  {table_html}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def dataframe_to_html_table(df):
    if df is None or df.empty:
        return '<p class="empty">暂无记录。</p>'

    rows = []
    pct_cols = {"当前盈亏率", "从高点回撤", "建议单票仓位", "距MA20", "距MA60"}
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            value = row[col]
            if col in pct_cols:
                display = format_pct(value)
            elif isinstance(value, float):
                display = f"{value:,.3f}".rstrip("0").rstrip(".")
            else:
                display = "" if pd.isna(value) else value
            css_class = ""
            if col == "操作建议" and value == "明日开盘卖出":
                css_class = "sell"
            cells.append(f'<td class="{css_class}">{html.escape(str(display))}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")

    header = "".join(f"<th>{html.escape(str(col))}</th>" for col in df.columns)
    return f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render_sell_report(output_path, sell_df, scan_date):
    title = f"主板持仓卖出检查 - {scan_date.strftime('%Y-%m-%d')}"
    sell_count = int((sell_df["操作建议"] == "明日开盘卖出").sum()) if not sell_df.empty and "操作建议" in sell_df.columns else 0
    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 28px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2937; background: #f7f8fa; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    .meta {{ margin: 0 0 18px; color: #4b5563; line-height: 1.7; }}
    .table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #edf0f3; white-space: nowrap; text-align: right; }}
    th {{ position: sticky; top: 0; background: #f3f4f6; color: #374151; }}
    th:nth-child(1), td:nth-child(1), th:nth-child(2), td:nth-child(2), th:nth-child(20), td:nth-child(20), th:nth-child(21), td:nth-child(21), th:nth-child(25), td:nth-child(25) {{ text-align: left; }}
    tr:hover td {{ background: #f9fafb; }}
    .sell {{ color: #b91c1c; font-weight: 700; }}
    .empty {{ padding: 18px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
  </style>
</head>
<body>
    <h1>{html.escape(title)}</h1>
    <div class="meta">持仓文件：{html.escape(LIVE_CONFIG["POSITION_FILE"])} | 触发卖出：{sell_count} 只</div>
    {dataframe_to_html_table(sell_df)}
  </body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def save_outputs(signal_df, sell_df, scan_date, market_state, regime_controls, stock_count):
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(LIVE_CONFIG["OUTPUT_ROOT"], f"MAIN_{scan_date.strftime('%Y%m%d')}_{run_stamp}")
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, f"Today_Buy_Signals_MAIN_{scan_date.strftime('%Y%m%d')}_{run_stamp}.csv")
    html_path = os.path.join(output_dir, f"Today_Buy_Signals_MAIN_{scan_date.strftime('%Y%m%d')}_{run_stamp}.html")
    sell_csv_path = os.path.join(output_dir, f"Today_Sell_Check_MAIN_{scan_date.strftime('%Y%m%d')}_{run_stamp}.csv")
    sell_html_path = os.path.join(output_dir, f"Today_Sell_Check_MAIN_{scan_date.strftime('%Y%m%d')}_{run_stamp}.html")

    signal_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    sell_df.to_csv(sell_csv_path, index=False, encoding="utf-8-sig")
    render_html_report(html_path, signal_df, scan_date, market_state, regime_controls, stock_count)
    render_sell_report(sell_html_path, sell_df, scan_date)
    shutil.copyfile(csv_path, LIVE_CONFIG["LATEST_CSV_ALIAS"])
    shutil.copyfile(html_path, LIVE_CONFIG["LATEST_HTML_ALIAS"])
    shutil.copyfile(sell_csv_path, LIVE_CONFIG["LATEST_SELL_CSV_ALIAS"])
    shutil.copyfile(sell_html_path, LIVE_CONFIG["LATEST_SELL_HTML_ALIAS"])
    return output_dir, csv_path, html_path, sell_csv_path, sell_html_path


def run_live_scanner():
    scan_end = LIVE_CONFIG["SCAN_END_DATE"] or datetime.now().strftime("%Y%m%d")
    apply_live_overrides(scan_end)
    params = {
        "BUY_SCORE_THRESHOLD": LIVE_CONFIG["BUY_SCORE_THRESHOLD"],
        "STOP_LOSS_RATE": LIVE_CONFIG["STOP_LOSS_RATE"],
        "MAX_HOLD_DAYS": LIVE_CONFIG["MAX_HOLD_DAYS"],
        "RSI_OVERSOLD": LIVE_CONFIG["RSI_OVERSOLD"],
        "TIME_SUNK_TOLERANCE": LIVE_CONFIG["TIME_SUNK_TOLERANCE"],
    }

    print("==================== 【主板实盘候选信号扫描】 ====================")
    print(f"[*] 当前冻结参数: {params}")
    print("[*] 股票池: 主板全量；数据口径: 前复权日线。")

    benchmark_data = load_live_benchmark(scan_end)
    market_data, stock_pool = load_live_market_data(scan_end)
    if not market_data:
        print("[!] 没有可用股票数据，无法生成今日信号。")
        return

    scan_date = find_scan_date(benchmark_data, market_data)
    if scan_date is None:
        print("[!] 未找到可扫描交易日。")
        return

    market_context = bt.build_market_context(benchmark_data, market_data)
    board_profile = bt.get_board_profile("MAIN")
    regime_controls = bt.get_regime_controls(
        market_context,
        scan_date,
        board_profile.get("max_holdings", bt.CONFIG["MAX_HOLDINGS"]),
        board_profile.get("max_position_per_stock", bt.CONFIG["MAX_POSITION_PER_STOCK"]),
        params["BUY_SCORE_THRESHOLD"],
    )
    market_state = market_context.get(scan_date, {})

    print(f"[*] 实际扫描交易日: {scan_date.strftime('%Y-%m-%d')}")
    print(
        f"[*] 市场环境: {regime_controls['regime']} | "
        f"MA20宽度 {format_pct(market_state.get('ma20_ratio', np.nan))} | "
        f"MA60宽度 {format_pct(market_state.get('ma60_ratio', np.nan))}"
    )
    print(
        f"[*] 开仓规则: 允许开仓={regime_controls['allow_new_positions']} | "
        f"门槛={regime_controls['buy_threshold']} | "
        f"最多持仓={regime_controls['max_holdings']} | "
        f"单票仓位={format_pct(regime_controls['position_per_stock'])}"
    )

    signals = []
    if regime_controls["allow_new_positions"]:
        for symbol, df in market_data.items():
            if scan_date not in df.index:
                continue
            today_k = df.loc[scan_date]
            if today_k["RSI14"] > params["RSI_OVERSOLD"]:
                continue
            if not bt.passes_entry_quality_filter(today_k, regime_controls["regime"]):
                continue

            score, recent_5 = bt.calculate_buy_signal_score(df, scan_date)
            if score < regime_controls["buy_threshold"]:
                continue

            rank_score = bt.calculate_candidate_rank_score(today_k, recent_5, score, regime_controls["regime"])
            if rank_score is None:
                continue

            signals.append(
                build_live_signal_row(
                    symbol,
                    stock_pool.get(symbol, "未知"),
                    df,
                    scan_date,
                    score,
                    rank_score,
                    market_context,
                    regime_controls,
                )
            )

    signal_df = pd.DataFrame(signals)
    if not signal_df.empty:
        signal_df.sort_values(by=["买入分数", "排序分", "20日均成交额"], ascending=False, inplace=True)

    sell_df = build_sell_check(market_data, stock_pool, scan_date, market_context)
    output_dir, csv_path, html_path, sell_csv_path, sell_html_path = save_outputs(
        signal_df,
        sell_df,
        scan_date,
        market_state,
        regime_controls,
        len(stock_pool),
    )

    print("\n==================== 【持仓卖出检查】 ====================")
    if sell_df.empty:
        print(f"[*] 当前没有持仓记录。请在 {LIVE_CONFIG['POSITION_FILE']} 中维护实盘持仓。")
    else:
        sell_alerts = sell_df[sell_df["操作建议"] == "明日开盘卖出"]
        if sell_alerts.empty:
            print("[*] 当前持仓没有触发卖出规则。")
        else:
            display_cols = ["代码", "名称", "操作建议", "触发原因", "买入价", "最新收盘价", "当前盈亏率", "持仓天数", "持仓市值", "止损线", "止盈启动线", "备注", "当前市场环境"]
            display_df = sell_alerts[display_cols].copy()
            display_df["当前盈亏率"] = display_df["当前盈亏率"].map(format_pct)
            try:
                from tabulate import tabulate
                print(tabulate(display_df, headers="keys", tablefmt="grid", showindex=False, stralign="center", numalign="center"))
            except Exception:
                print(display_df.to_string(index=False))

    print("\n==================== 【今日候选清单】 ====================")
    if signal_df.empty:
        print("[*] 今日没有候选信号。")
    else:
        display_cols = ["代码", "名称", "市场环境", "买入分数", "收盘价", "次日最高可买价", "错过补买最高价", "止损参考价", "建议单票仓位"]
        display_df = signal_df[display_cols].copy()
        display_df["建议单票仓位"] = display_df["建议单票仓位"].map(format_pct)
        try:
            from tabulate import tabulate
            print(tabulate(display_df, headers="keys", tablefmt="grid", showindex=False, stralign="center", numalign="center"))
        except Exception:
            print(display_df.to_string(index=False))

    print(f"\n▶ 输出目录 : {output_dir}")
    print(f"▶ 买入CSV : {csv_path}")
    print(f"▶ 买入HTML: {html_path}")
    print(f"▶ 卖出CSV : {sell_csv_path}")
    print(f"▶ 卖出HTML: {sell_html_path}")
    print(f"▶ 最新买入CSV : {LIVE_CONFIG['LATEST_CSV_ALIAS']}")
    print(f"▶ 最新买入HTML: {LIVE_CONFIG['LATEST_HTML_ALIAS']}")
    print(f"▶ 最新卖出CSV : {LIVE_CONFIG['LATEST_SELL_CSV_ALIAS']}")
    print(f"▶ 最新卖出HTML: {LIVE_CONFIG['LATEST_SELL_HTML_ALIAS']}")
    print("[!] 纪律提醒：次日开盘高于“次日最高可买价”放弃；错过开盘后高于“错过补买最高价”放弃。")
    print("[!] 卖出提醒：卖出信号按收盘后判断，执行口径为下一交易日开盘卖出。")


if __name__ == "__main__":
    run_live_scanner()
