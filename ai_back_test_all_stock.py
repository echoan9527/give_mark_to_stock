'''
Author: Chengya
Description: Description
Date: 2026-08-10 22:47:56
LastEditors: Chengya
LastEditTime: 2026-08-14 11:32:14
'''
'''
Author: Chengya (程永安)
Description: 动态多板块量化回测引擎 (支持板块开关：ALL-全市场, MAIN-主板, CYB-创业板, KCB-科创板)
'''
import os
import time
import random
import itertools
import html
from datetime import datetime
import akshare as ak
import numpy as np
import pandas as pd

# ================= 终极网络补丁：彻底屏蔽 macOS 系统代理 =================
# 1. 强制清空可能残留的环境变量（用 del 比设为空字符串更彻底）
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    if k in os.environ:
        del os.environ[k]

# 2. 动用核弹级指令：要求 requests 库对所有域名（*）强制直连
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
# ==============================================================================

# ==============================================================================
# 专属量化回测引擎 (v5.8 板块开关融合版)
# ==============================================================================

CONFIG = {
    "INITIAL_CAPITAL": 100000.0,
    "MAX_POSITION_PER_STOCK": 0.20,
    "MAX_HOLDINGS": 5,
    "COMMISSION_RATE": 0.00025,
    "MIN_COMMISSION": 5.0,
    "TAX_RATE": 0.0005,
    "TRAIN_START": "20210101",#训练数据 开始时间
    "TRAIN_END": "20231231", # 训练数据 结束时间
    "TEST_START": "20240101",# 回测数据 开始时间
    "TEST_END": "20260809",# 回测数据 结束时间
    "SLIPPAGE_RATE": 0.002,

    # ==========================================
    # 🎯 核心板块开关 (Market Filter)
    # 可选值:
    #   "ALL"  -> 全市场融合 (主板 + 创业板 + 科创板大比武)
    #   "MAIN" -> 仅主板 (沪深主板 600/000 等，防守稳健)
    #   "CYB"  -> 仅创业板 (300/301 高弹性 20% 涨跌幅)
    #   "KCB"  -> 仅科创板 (688 硬科技高爆发)
    # ==========================================
    "TARGET_BOARD": "MAIN",

    # None 表示使用该板块全部可用标的；设成整数时为调试抽样模式。
    # "MAX_STOCKS_PER_BOARD": None,
     "MAX_STOCKS_PER_BOARD": 600, # 随机抽取多少只股票参与回测 None 不抽样 要全部符合条件的股票
    "POOL_SAMPLE_SEED": 20260814,
    "MIN_HISTORY_BARS": 120,# 一只股票至少要有 120 条有效历史 K 线数据，才允许进入回测   排除刚上市不久的新股  排除数据太短、均线指标不稳定的股票  保证 MA60、RSI、成交量均线等指标有足够样本
    "MIN_PRICE": 2.0, # 最新收盘价低于 2 元的股票不参与回测  排除低价问题股 避免退市边缘、流动性差、异常波动股票干扰策略 更贴近实盘中你可能不愿意碰的标的
    "OUTPUT_ROOT": "backtest_outputs",

    # ================= 防守系统开关 =================
    "MAX_BUY_GAP_RATE": 0.04,              # 次日开盘相对信号日收盘高开超过 4% 时不追买，避免追在短线情绪尖峰
    "REQUIRE_BENCH_MA20_UP": True,         # 大盘 20 日均线必须上行，过滤弱势反弹和下降趋势里的假突破
    "REQUIRE_BENCH_ABOVE_MA60": False,     # 是否强制大盘站上 60 日均线；当前交给市场分级控制，不做硬性禁买
    "REQUIRE_STOCK_MA60_UP": False,        # 是否强制个股 60 日均线上行；当前不一刀切，避免过度过滤早期转强股票
    "MIN_ENTRY_VOLUME_RATIO": 0.8,         # 入场当日成交量至少达到 20 日均量的 80%，过滤明显缩量、参与度不足的信号
    "MIN_AVG_AMOUNT_20": 30000000,         # 20 日平均成交额至少 3000 万，过滤流动性太差、实盘难成交的股票
    "ENABLE_LOSS_COOLDOWN": True,          # 是否启用连续亏损暂停开仓机制，用来避免策略进入连续止损循环
    "LOSS_COOLDOWN_TRIGGER": 3,            # 连续亏损达到 3 笔后触发暂停；1-2 笔可能是噪声，3 笔开始提示环境变差
    "LOSS_COOLDOWN_DAYS": 5,               # 触发连续亏损后暂停开仓 5 个交易日，只限制买入，不影响已有持仓卖出
    "ENABLE_DRAWDOWN_COOLDOWN": True,      # 是否启用账户回撤暂停开仓机制，从组合层面控制风险扩散
    "MAX_EQUITY_DRAWDOWN_TO_PAUSE": 0.10,  # 账户权益从历史高点回撤超过 10% 后暂停新开仓，避免回撤继续放大
    "DRAWDOWN_COOLDOWN_DAYS": 10,          # 触发账户回撤后暂停开仓 10 个交易日，给市场和策略状态一个恢复窗口

    # 市场环境分级：强市正常仓位，中性市轻仓，弱市不新开仓。
    "ENABLE_MARKET_REGIME": True,          # 是否启用市场环境分级；开启后根据市场宽度决定正常仓、轻仓或不新开仓
    "STRONG_BREADTH_MA20": 0.55,           # 强市场要求股票池中至少 55% 股票站上 MA20，代表短中期赚钱效应较好
    "STRONG_BREADTH_MA60": 0.45,           # 强市场要求股票池中至少 45% 股票站上 MA60，代表中期趋势基础足够
    "NEUTRAL_BREADTH_MA20": 0.35,          # 中性市场要求至少 35% 股票站上 MA20；低于该值说明短线环境偏弱
    "NEUTRAL_BREADTH_MA60": 0.25,          # 中性市场要求至少 25% 股票站上 MA60；低于该值说明多数股票处于中期弱势
    "NEUTRAL_MAX_HOLDINGS": 2,             # 中性市场最多持仓 2 只，允许少量试错，但避免接近满仓暴露
    "NEUTRAL_POSITION_MULTIPLIER": 0.50,   # 中性市场单票仓位按正常仓位的 50% 执行，用轻仓参与不确定行情
    "WEAK_ALLOW_HIGH_SCORE_BUY": True,     # 弱市场不完全禁买，只允许极高分信号小仓试错，避免错过结构性强势票
    "WEAK_BUY_SCORE_THRESHOLD": 78,        # 弱市场买入分数门槛，必须明显高于普通阈值才允许开仓
    "WEAK_MAX_HOLDINGS": 1,                # 弱市场最多持仓 1 只，控制极端环境下的风险暴露
    "WEAK_POSITION_MULTIPLIER": 0.25,      # 弱市场单票仓位按正常仓位的 25% 执行，只做小仓位观察和试错

}

BOARD_PROFILES = {
    "MAIN": {
        "name": "主板",
        "prefixes": ("600", "601", "603", "605", "000", "001", "002", "003"),
        "price_limit": 0.10,
        "max_position_per_stock": 0.20,
        "max_holdings": 5,
        "fallback_pool": {"600519": "贵州茅台", "601318": "中国平安"},
    },
    "CYB": {
        "name": "创业板",
        "prefixes": ("300", "301"),
        "price_limit": 0.20,
        "max_position_per_stock": 0.15,
        "max_holdings": 5,
        "fallback_pool": {"300750": "宁德时代", "300760": "迈瑞医疗"},
    },
    "KCB": {
        "name": "科创板",
        "prefixes": ("688", "689"),
        "price_limit": 0.20,
        "max_position_per_stock": 0.12,
        "max_holdings": 5,
        "fallback_pool": {"688981": "中芯国际", "688111": "金山办公"},
    },
    "ALL": {
        "name": "全A混合",
        "prefixes": ("600", "601", "603", "605", "000", "001", "002", "003", "300", "301", "688", "689"),
        "price_limit": None,
        "max_position_per_stock": 0.15,
        "max_holdings": 8,
        "fallback_pool": {"600519": "贵州茅台", "300750": "宁德时代", "688981": "中芯国际"},
    },
}

PARAM_GRID = {
    "BUY_SCORE_THRESHOLD": [60, 65, 70],
    "STOP_LOSS_RATE": [-0.07, -0.09],
    "MAX_HOLD_DAYS": [10, 15],
    "RSI_OVERSOLD": [80, 82],
    "TIME_SUNK_TOLERANCE": [0.03, 0.05]
}

CACHE_DIR = f"stock_data_cache_{CONFIG['TARGET_BOARD'].lower()}"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==================== 1. 数据获取与缓存层 ====================
def get_board_profile(board_mode=None):
    board_mode = board_mode or CONFIG["TARGET_BOARD"]
    if board_mode not in BOARD_PROFILES:
        raise ValueError(f"未知板块模式: {board_mode}. 可选值: {list(BOARD_PROFILES.keys())}")
    return BOARD_PROFILES[board_mode]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def ensure_stock_runtime_columns(df):
    if "成交额估算" not in df.columns:
        df["成交额估算"] = df["收盘"] * df["成交量"]
    if "Amount_MA20" not in df.columns:
        df["Amount_MA20"] = df["成交额估算"].rolling(20).mean()
    return df

def ensure_benchmark_runtime_columns(df):
    if "MA20" not in df.columns:
        df["MA20"] = df["收盘"].rolling(20).mean()
    if "MA60" not in df.columns:
        df["MA60"] = df["收盘"].rolling(60).mean()
    if "MA20_prev5" not in df.columns:
        df["MA20_prev5"] = df["MA20"].shift(5)
    return df

def get_filtered_market_pool():
    board_mode = CONFIG["TARGET_BOARD"]
    board_profile = get_board_profile(board_mode)
    print(f"[*] 正在向接口请求全市场名录，并根据板块开关【 {board_mode} - {board_profile['name']} 】进行精准过滤...")

    try:
        # 替换为更轻量、不易被墙的静态 A 股名录接口
        spot_df = ak.stock_info_a_code_name()
        pool = {}
        for _, row in spot_df.iterrows():
            code = str(row["code"]).zfill(6)
            name = str(row["name"])

            # 过滤 ST 与退市股
            if "ST" in name or "退" in name:
                continue

            if code.startswith(board_profile["prefixes"]):
                pool[code] = name

        pool_items = list(pool.items())
        max_stocks = CONFIG.get("MAX_STOCKS_PER_BOARD")
        if max_stocks is not None and len(pool_items) > max_stocks:
            rng = random.Random(CONFIG.get("POOL_SAMPLE_SEED", 42))
            rng.shuffle(pool_items)
            pool_items = pool_items[:max_stocks]
            print(f"[!] 当前为抽样模式：从 {len(pool)} 只候选中抽取 {max_stocks} 只，种子={CONFIG.get('POOL_SAMPLE_SEED')}")

        filtered_pool = dict(sorted(pool_items))
        print(f"[*] 板块过滤完毕！当前模式【 {board_mode} 】候选标的共计 {len(filtered_pool)} 只。")
        return filtered_pool
    except Exception as e:
        print(f"[!] 股票池拉取失败，启用备用池: {e}")
        return board_profile["fallback_pool"]


def passes_data_quality_filter(df):
    if df is None or df.empty:
        return False
    df = ensure_stock_runtime_columns(df)
    if len(df) < CONFIG["MIN_HISTORY_BARS"]:
        return False
    if df["收盘"].iloc[-1] < CONFIG["MIN_PRICE"]:
        return False
    if "成交量" in df.columns and df["成交量"].tail(20).fillna(0).sum() <= 0:
        return False
    return True

def is_market_healthy(benchmark_data, current_date):
    if benchmark_data is None or current_date not in benchmark_data.index:
        return True

    bench_today = benchmark_data.loc[current_date]
    if bench_today["收盘"] < bench_today["MA20"]:
        return False
    if CONFIG["REQUIRE_BENCH_MA20_UP"] and bench_today["MA20"] < bench_today["MA20_prev5"]:
        return False
    if CONFIG["REQUIRE_BENCH_ABOVE_MA60"] and bench_today["收盘"] < bench_today["MA60"]:
        return False
    return True

def build_market_context(benchmark_data, market_data):
    if not CONFIG["ENABLE_MARKET_REGIME"]:
        return {}

    print("[*] 正在预计算市场宽度与环境分级...")
    context = {}
    all_dates = get_trading_calendar(benchmark_data, market_data, CONFIG["TRAIN_START"], CONFIG["TEST_END"])

    for current_date in all_dates:
        total = above_ma20 = above_ma60 = ma60_up = 0
        for df in market_data.values():
            if current_date not in df.index:
                continue
            row = df.loc[current_date]
            total += 1
            if row["收盘"] > row["MA20"]:
                above_ma20 += 1
            if row["收盘"] > row["MA60"]:
                above_ma60 += 1
            if row["MA60"] >= row["MA60_prev5"]:
                ma60_up += 1

        ma20_ratio = above_ma20 / total if total else 0
        ma60_ratio = above_ma60 / total if total else 0
        ma60_up_ratio = ma60_up / total if total else 0

        bench_close_above_ma20 = True
        bench_ma20_up = True
        bench_close_above_ma60 = True
        if benchmark_data is not None and current_date in benchmark_data.index:
            bench = benchmark_data.loc[current_date]
            bench_close_above_ma20 = bench["收盘"] >= bench["MA20"]
            bench_ma20_up = bench["MA20"] >= bench["MA20_prev5"]
            bench_close_above_ma60 = bench["收盘"] >= bench["MA60"]

        bench_ok = bench_close_above_ma20 and (bench_ma20_up or not CONFIG["REQUIRE_BENCH_MA20_UP"])
        strong = (
            bench_ok
            and bench_close_above_ma60
            and ma20_ratio >= CONFIG["STRONG_BREADTH_MA20"]
            and ma60_ratio >= CONFIG["STRONG_BREADTH_MA60"]
        )
        neutral = (
            bench_ok
            and ma20_ratio >= CONFIG["NEUTRAL_BREADTH_MA20"]
            and ma60_ratio >= CONFIG["NEUTRAL_BREADTH_MA60"]
        )

        if strong:
            regime = "强"
        elif neutral:
            regime = "中"
        else:
            regime = "弱"

        context[current_date] = {
            "regime": regime,
            "ma20_ratio": ma20_ratio,
            "ma60_ratio": ma60_ratio,
            "ma60_up_ratio": ma60_up_ratio,
            "bench_close_above_ma20": bench_close_above_ma20,
            "bench_ma20_up": bench_ma20_up,
            "bench_close_above_ma60": bench_close_above_ma60,
        }

    counts = pd.Series([v["regime"] for v in context.values()]).value_counts().to_dict() if context else {}
    print(f"[*] 市场环境分级完成：强={counts.get('强', 0)} 天，中={counts.get('中', 0)} 天，弱={counts.get('弱', 0)} 天。")
    return context

def get_regime_controls(market_context, current_date, base_max_holdings, base_position_per_stock, base_buy_threshold):
    if not CONFIG["ENABLE_MARKET_REGIME"]:
        return {
            "regime": "关闭",
            "allow_new_positions": True,
            "max_holdings": base_max_holdings,
            "position_per_stock": base_position_per_stock,
            "buy_threshold": base_buy_threshold,
        }

    state = market_context.get(current_date, {"regime": "弱"})
    regime = state["regime"]
    if regime == "强":
        return {
            "regime": regime,
            "allow_new_positions": True,
            "max_holdings": base_max_holdings,
            "position_per_stock": base_position_per_stock,
            "buy_threshold": base_buy_threshold,
        }
    if regime == "中":
        return {
            "regime": regime,
            "allow_new_positions": True,
            "max_holdings": min(base_max_holdings, CONFIG["NEUTRAL_MAX_HOLDINGS"]),
            "position_per_stock": base_position_per_stock * CONFIG["NEUTRAL_POSITION_MULTIPLIER"],
            "buy_threshold": base_buy_threshold,
        }
    if CONFIG["WEAK_ALLOW_HIGH_SCORE_BUY"]:
        return {
            "regime": regime,
            "allow_new_positions": True,
            "max_holdings": min(base_max_holdings, CONFIG["WEAK_MAX_HOLDINGS"]),
            "position_per_stock": base_position_per_stock * CONFIG["WEAK_POSITION_MULTIPLIER"],
            "buy_threshold": max(base_buy_threshold, CONFIG["WEAK_BUY_SCORE_THRESHOLD"]),
        }
    return {
        "regime": regime,
        "allow_new_positions": False,
        "max_holdings": 0,
        "position_per_stock": 0,
        "buy_threshold": base_buy_threshold,
    }

def passes_entry_quality_filter(today_k):
    if CONFIG["REQUIRE_STOCK_MA60_UP"]:
        if not (today_k["收盘"] > today_k["MA60"] and today_k["MA60"] >= today_k["MA60_prev5"]):
            return False

    vol_ratio = today_k["成交量"] / (today_k["Vol_MA20"] + 1e-9)
    if vol_ratio < CONFIG["MIN_ENTRY_VOLUME_RATIO"]:
        return False

    min_amount = CONFIG.get("MIN_AVG_AMOUNT_20")
    if min_amount is not None and today_k.get("Amount_MA20", 0) < min_amount:
        return False

    return True

def prepare_stock_data(symbol, stock_name):
    prefix = "sh" if symbol.startswith(("60", "68")) else "sz"
    full_symbol = f"{prefix}{symbol}"
    cache_filepath = os.path.join(CACHE_DIR, f"{full_symbol}_{CONFIG['TRAIN_START']}_{CONFIG['TEST_END']}.csv")

    if os.path.exists(cache_filepath):
        try:
            df = pd.read_csv(cache_filepath, index_col="日期", parse_dates=True)
            df = ensure_stock_runtime_columns(df)
            return df if passes_data_quality_filter(df) else None
        except: pass

    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq", start_date=CONFIG["TRAIN_START"], end_date=CONFIG["TEST_END"])
            if df is None or len(df) < 60: return None
            df.rename(columns={"date": "日期", "open": "开盘", "close": "收盘", "high": "最高", "low": "最低", "volume": "成交量"}, inplace=True)
            df["日期"] = pd.to_datetime(df["日期"])
            df.set_index("日期", inplace=True)

            df["MA5"], df["MA10"], df["MA20"], df["MA60"] = df["收盘"].rolling(5).mean(), df["收盘"].rolling(10).mean(), df["收盘"].rolling(20).mean(), df["收盘"].rolling(60).mean()
            df["RSI14"] = calculate_rsi(df["收盘"], 14)
            df["Vol_MA20"] = df["成交量"].rolling(20).mean()
            df["MA60_prev5"] = df["MA60"].shift(5)
            df["MA20_break_1"], df["MA20_break_2"] = df["收盘"].shift(1) < df["MA20"].shift(1), df["收盘"].shift(2) < df["MA20"].shift(2)
            df["High_20"] = df["收盘"].rolling(20).max().shift(1)
            df = ensure_stock_runtime_columns(df)
            df.dropna(inplace=True)

            if not passes_data_quality_filter(df):
                return None

            df.to_csv(cache_filepath, encoding="utf-8-sig")
            time.sleep(random.uniform(0.3, 0.8))
            return df
        except Exception:
            if attempt < 2: time.sleep(random.uniform(2.0, 4.0))
    return None

def load_all_market_data():
    pool = get_filtered_market_pool()
    print("[*] 正在加载板块标的的历史数据...")
    market_data, active_pool = {}, {}
    skipped = 0
    for code, name in pool.items():
        res = prepare_stock_data(code, name)
        if res is None:
            skipped += 1
            continue
        market_data[code] = res
        active_pool[code] = name

    print(f"[*] 成功加载有效回测标的共计 {len(market_data)} 只，过滤/缺失 {skipped} 只。")
    return market_data, active_pool

def load_benchmark_data():
    cache_filepath = os.path.join(CACHE_DIR, f"sh000300_benchmark_{CONFIG['TRAIN_START']}_{CONFIG['TEST_END']}.csv")
    if os.path.exists(cache_filepath):
        try:
            df = pd.read_csv(cache_filepath, index_col="日期", parse_dates=True)
            return ensure_benchmark_runtime_columns(df).dropna()
        except: pass
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df.rename(columns={"date": "日期", "close": "收盘"}, inplace=True)
        df["日期"] = pd.to_datetime(df["日期"])
        df.set_index("日期", inplace=True)
        df = ensure_benchmark_runtime_columns(df)
        df.dropna(inplace=True)
        df.to_csv(cache_filepath, encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"[!] 基准获取失败: {e}")
        return None

def get_trading_calendar(benchmark_data, market_data, start_date, end_date):
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    if benchmark_data is not None and not benchmark_data.empty:
        all_dates = sorted(benchmark_data.index)
    elif market_data:
        all_dates = sorted(set().union(*[set(df.index) for df in market_data.values()]))
    else:
        return []

    return [d for d in all_dates if start_dt <= d <= end_dt]

def get_latest_price(df, current_date, column="收盘"):
    if current_date in df.index:
        return df.loc[current_date][column]

    history = df.loc[:current_date]
    if history.empty:
        return None
    return history.iloc[-1]["收盘"]

def calculate_portfolio_equity(cash, portfolio, market_data, current_date, column="收盘"):
    total = cash
    for symbol, pos in portfolio.items():
        price = get_latest_price(market_data[symbol], current_date, column)
        if price is not None:
            total += pos["shares"] * price
    return total

def slug_value(value):
    if isinstance(value, float):
        value = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        value = str(value)
    return value.replace("-", "m").replace(".", "p")

def build_param_slug(params):
    key_alias = {
        "BUY_SCORE_THRESHOLD": "buy",
        "STOP_LOSS_RATE": "sl",
        "MAX_HOLD_DAYS": "hold",
        "RSI_OVERSOLD": "rsi",
        "TIME_SUNK_TOLERANCE": "sunk",
    }
    ordered_keys = [k for k in PARAM_GRID.keys() if k in params]
    ordered_keys.extend(sorted(k for k in params.keys() if k not in ordered_keys))
    return "_".join(f"{key_alias.get(k, k.lower())}{slug_value(params[k])}" for k in ordered_keys)

def build_output_bundle(best_params, stock_count):
    board_mode = CONFIG["TARGET_BOARD"]
    board_name = get_board_profile(board_mode)["name"]
    param_slug = build_param_slug(best_params)
    sample_limit = CONFIG.get("MAX_STOCKS_PER_BOARD")
    sample_slug = f"抽样{sample_limit}只" if sample_limit is not None else "全量"
    stock_slug = f"实际{stock_count}只"
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    train_slug = f"训练{CONFIG['TRAIN_START'][:4]}-{CONFIG['TRAIN_END'][:4]}"
    test_slug = f"盲测{CONFIG['TEST_START'][:4]}-{CONFIG['TEST_END'][:4]}"

    run_dir_name = f"{run_stamp}_{sample_slug}_{stock_slug}_{train_slug}_{test_slug}"
    output_dir = os.path.join(CONFIG["OUTPUT_ROOT"], board_mode, param_slug, run_dir_name)
    os.makedirs(output_dir, exist_ok=True)

    base_name = f"{board_name}_{sample_slug}_{stock_slug}_{train_slug}_{test_slug}_{run_stamp}"
    return output_dir, {
        "trade_history": os.path.join(output_dir, f"BlindTest_Trade_History_{base_name}.csv"),
        "equity_curve": os.path.join(output_dir, f"BlindTest_Equity_Curve_{base_name}.csv"),
        "summary": os.path.join(output_dir, f"BlindTest_Summary_{base_name}.csv"),
        "html_report": os.path.join(output_dir, f"BlindTest_Report_{base_name}.html"),
    }

def format_money(value):
    if pd.isna(value):
        return ""
    return f"{value:,.2f}"

def format_pct_value(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.2f}%"

def normalize_stock_code(value):
    if pd.isna(value):
        return ""
    text = str(value).strip().replace(",", "")
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text

def html_cell(value, kind=None):
    raw_value = "" if pd.isna(value) else value
    css_class = ""
    display = raw_value

    if kind == "code":
        display = normalize_stock_code(raw_value)
        raw_value = display
    elif kind == "money":
        display = format_money(float(raw_value))
        css_class = "pos" if float(raw_value) > 0 else "neg" if float(raw_value) < 0 else ""
    elif kind == "pct":
        display = format_pct_value(float(raw_value))
        css_class = "pos" if float(raw_value) > 0 else "neg" if float(raw_value) < 0 else ""
    elif isinstance(raw_value, (int, float, np.integer, np.floating)):
        display = f"{float(raw_value):,.4f}".rstrip("0").rstrip(".")

    return f'<td class="{css_class}" data-sort="{html.escape(str(raw_value))}">{html.escape(str(display))}</td>'

def dataframe_to_html_table(df, table_id, column_kinds=None):
    column_kinds = column_kinds or {}
    if df is None or df.empty:
        return f'<p class="empty">暂无数据</p>'

    sortable_columns = {"单笔净利", "盈亏率"} if table_id == "trade-detail" else set()
    header_cells = []
    for idx, col in enumerate(df.columns):
        col_name = str(col)
        col_kind = column_kinds.get(col, "text")
        if col_name in sortable_columns:
            header_cells.append(
                f'<th class="sortable-col" data-type="{html.escape(col_kind)}" onclick="sortTable(\'{html.escape(table_id)}\', {idx}, \'{html.escape(col_kind)}\', this)">'
                f'{html.escape(col_name)}<span class="sort-mark"></span></th>'
            )
        else:
            header_cells.append(f"<th>{html.escape(col_name)}</th>")
    header = "".join(header_cells)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(html_cell(row[col], column_kinds.get(col)) for col in df.columns)
        rows.append(f"<tr>{cells}</tr>")

    return f"""
    <div class="table-wrap">
      <table id="{table_id}" class="sortable">
        <thead><tr>{header}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """

def build_yearly_trade_stats(trade_df):
    if trade_df.empty:
        return pd.DataFrame()
    df = trade_df.copy()
    df["卖出日"] = pd.to_datetime(df["卖出日"])
    df["年份"] = df["卖出日"].dt.year
    grouped = df.groupby("年份")
    result = grouped.agg(
        交易次数=("单笔净利", "size"),
        年度已实现盈亏=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        最大单笔盈利=("单笔净利", "max"),
        最大单笔亏损=("单笔净利", "min"),
    ).reset_index()
    return result

def build_yearly_equity_stats(equity_df):
    if equity_df.empty:
        return pd.DataFrame()
    df = equity_df.copy().reset_index()
    df["日期"] = pd.to_datetime(df["日期"])
    df["年份"] = df["日期"].dt.year

    rows = []
    for year, group in df.groupby("年份"):
        first_equity = group["总权益"].iloc[0]
        last_equity = group["总权益"].iloc[-1]
        high_water = group["总权益"].cummax()
        max_drawdown = (group["总权益"] / high_water - 1).min()
        rows.append({
            "年份": year,
            "年初权益": first_equity,
            "年末权益": last_equity,
            "年度权益盈亏": last_equity - first_equity,
            "年度收益率": last_equity / first_equity - 1,
            "年度最大回撤": max_drawdown,
        })
    return pd.DataFrame(rows)

def build_reason_stats(trade_df):
    if trade_df.empty:
        return pd.DataFrame()
    return trade_df.groupby("卖出原因").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        平均盈亏=("单笔净利", "mean"),
    ).reset_index().sort_values("盈亏合计")

def generate_html_report(output_path, trade_df, equity_df, summary):
    summary_df = pd.DataFrame([summary])
    yearly_trade_df = build_yearly_trade_stats(trade_df)
    yearly_equity_df = build_yearly_equity_stats(equity_df)
    reason_df = build_reason_stats(trade_df)

    trade_display = trade_df.copy()
    if not trade_display.empty and "代码" in trade_display.columns:
        trade_display["代码"] = trade_display["代码"].apply(normalize_stock_code)
    if not trade_display.empty and "盈亏率" in trade_display.columns:
        trade_display["盈亏率"] = trade_display["盈亏率"].astype(float)

    money_cols = {
        "期初资金", "期末总权益", "已实现盈亏", "未实现盈亏", "总盈亏",
        "买入耗资", "卖出净额", "单笔净利", "卖出后现金",
        "年度已实现盈亏", "平均单笔盈亏", "最大单笔盈利", "最大单笔亏损",
        "年初权益", "年末权益", "年度权益盈亏", "盈亏合计", "平均盈亏",
    }
    pct_cols = {"总收益率", "基准总收益率", "超额收益率", "最大回撤", "基准最大回撤", "胜率", "年度收益率", "年度最大回撤", "盈亏率"}

    def kind_map(df):
        kinds = {col: "money" for col in df.columns if col in money_cols} | {col: "pct" for col in df.columns if col in pct_cols}
        if "代码" in df.columns:
            kinds["代码"] = "code"
        return kinds

    report_title = f"{summary.get('板块名称', '')} 回测复盘报告"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(report_title)}</title>
  <style>
    body {{ margin: 0; padding: 28px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2937; background: #f7f8fa; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; }}
    .subtle {{ color: #6b7280; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
    .metric .label {{ color: #6b7280; font-size: 12px; }}
    .metric .value {{ margin-top: 6px; font-size: 20px; font-weight: 650; }}
    .table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #edf0f3; white-space: nowrap; text-align: right; }}
    th {{ position: sticky; top: 0; background: #f3f4f6; user-select: none; color: #374151; }}
    th.sortable-col {{ cursor: pointer; }}
    th.sortable-col .sort-mark::after {{ content: " ↕"; color: #9ca3af; font-size: 12px; font-weight: 600; }}
    th.sortable-col[data-direction="asc"] .sort-mark::after {{ content: " 升序 ▲"; color: #2563eb; }}
    th.sortable-col[data-direction="desc"] .sort-mark::after {{ content: " 降序 ▼"; color: #2563eb; }}
    th:first-child, td:first-child {{ text-align: left; }}
    tr:hover td {{ background: #f9fafb; }}
    .pos {{ color: #b91c1c; }}
    .neg {{ color: #047857; }}
    .empty {{ color: #6b7280; }}
  </style>
</head>
<body>
  <h1>{html.escape(report_title)}</h1>
  <div class="subtle">生成时间：{html.escape(generated_at)} | 结果目录：{html.escape(os.path.dirname(output_path))}</div>

  <div class="grid">
    <div class="metric"><div class="label">期末总权益</div><div class="value">{format_money(summary.get('期末总权益'))}</div></div>
    <div class="metric"><div class="label">总收益率</div><div class="value">{summary.get('总收益率', 0):+.2f}%</div></div>
    <div class="metric"><div class="label">基准收益率</div><div class="value">{summary.get('基准总收益率', 0):+.2f}%</div></div>
    <div class="metric"><div class="label">超额收益率</div><div class="value">{summary.get('超额收益率', 0):+.2f}%</div></div>
    <div class="metric"><div class="label">最大回撤</div><div class="value">{summary.get('最大回撤', 0) * 100:.2f}%</div></div>
    <div class="metric"><div class="label">交易次数</div><div class="value">{summary.get('交易次数', 0)}</div></div>
  </div>

  <h2>年度权益表现</h2>
  {dataframe_to_html_table(yearly_equity_df, "yearly-equity", kind_map(yearly_equity_df))}

  <h2>年度已实现盈亏</h2>
  {dataframe_to_html_table(yearly_trade_df, "yearly-trade", kind_map(yearly_trade_df))}

  <h2>卖出原因统计</h2>
  {dataframe_to_html_table(reason_df, "reason-stats", kind_map(reason_df))}

  <h2>概要参数</h2>
  {dataframe_to_html_table(summary_df, "summary", kind_map(summary_df))}

  <h2>交易明细</h2>
  {dataframe_to_html_table(trade_display, "trade-detail", kind_map(trade_display))}

  <script>
    function parseSortValue(cell, type) {{
      var raw = (cell.getAttribute('data-sort') || cell.textContent || '').trim();
      if (type === 'money' || type === 'pct' || type === 'number') {{
        var numeric = Number(raw.replace(/,/g, '').replace(/%/g, ''));
        return isNaN(numeric) ? 0 : numeric;
      }}
      return raw;
    }}

    function sortTable(tableId, columnIndex, type, headerCell) {{
      var table = document.getElementById(tableId);
      if (!table) return;
      var tbody = table.tBodies[0];
      if (!tbody) return;

      var rows = Array.prototype.slice.call(tbody.rows);
      var direction = headerCell.getAttribute('data-direction') === 'asc' ? 'desc' : 'asc';
      var headers = table.tHead ? table.tHead.rows[0].cells : [];
      for (var i = 0; i < headers.length; i++) {{
        headers[i].removeAttribute('data-direction');
      }}
      headerCell.setAttribute('data-direction', direction);

      rows.sort(function(a, b) {{
        var av = parseSortValue(a.cells[columnIndex], type);
        var bv = parseSortValue(b.cells[columnIndex], type);
        if (typeof av === 'number' && typeof bv === 'number') {{
          return direction === 'asc' ? av - bv : bv - av;
        }}
        return direction === 'asc'
          ? String(av).localeCompare(String(bv), 'zh-CN')
          : String(bv).localeCompare(String(av), 'zh-CN');
      }});

      for (var j = 0; j < rows.length; j++) {{
        tbody.appendChild(rows[j]);
      }}
    }}
  </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

# ==================== 2. 核心考核模块 ====================
def calc_kpi(price_series):
    if price_series.empty or len(price_series) < 2:
        return {"总收益": 0, "年化收益": 0, "最大回撤": 0, "Calmar": 0, "Sharpe": 0, "最长水下天数": 0}

    total_return = (price_series.iloc[-1] / price_series.iloc[0]) - 1
    days_passed = (price_series.index[-1] - price_series.index[0]).days
    years = days_passed / 365.25 if days_passed > 0 else 1
    annual_return = (1 + total_return) ** (1 / years) - 1

    high_water_marks = price_series.cummax()
    drawdowns = (price_series - high_water_marks) / high_water_marks
    max_drawdown = abs(drawdowns.min())

    hwm_dates = high_water_marks.drop_duplicates(keep='first').index
    if len(hwm_dates) > 1:
        durations = (hwm_dates[1:] - hwm_dates[:-1]).days
        max_dd_duration = durations.max()
        current_dd_duration = (price_series.index[-1] - hwm_dates[-1]).days
        max_dd_duration = max(max_dd_duration, current_dd_duration)
    else:
        max_dd_duration = days_passed

    calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else 0
    daily_returns = price_series.pct_change().dropna()
    daily_mean = daily_returns.mean()
    daily_std = daily_returns.std()
    sharpe_ratio = (daily_mean / daily_std) * np.sqrt(252) if daily_std > 0 else 0

    return {
        "总收益": total_return,
        "年化收益": annual_return,
        "最大回撤": max_drawdown,
        "Calmar": calmar_ratio,
        "Sharpe": sharpe_ratio,
        "最长水下天数": max_dd_duration
    }

def calc_benchmark_kpi(benchmark_data, start_date, end_date):
    if benchmark_data is None or benchmark_data.empty:
        return calc_kpi(pd.Series(dtype=float))

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    bench_series = benchmark_data.loc[(benchmark_data.index >= start_dt) & (benchmark_data.index <= end_dt), "收盘"]
    return calc_kpi(bench_series)

# ==================== 3. 策略回测黑盒引擎 ====================
def execute_single_backtest(params, market_data, stock_pool, benchmark_data, market_context, start_date, end_date):
    board_profile = get_board_profile()
    buy_threshold = params["BUY_SCORE_THRESHOLD"]
    stop_loss_rate = params["STOP_LOSS_RATE"]
    max_hold_days = params["MAX_HOLD_DAYS"]
    rsi_oversold = params["RSI_OVERSOLD"]
    time_sunk_tolerance = params["TIME_SUNK_TOLERANCE"]
    max_holdings = board_profile.get("max_holdings", CONFIG["MAX_HOLDINGS"])
    max_position_per_stock = board_profile.get("max_position_per_stock", CONFIG["MAX_POSITION_PER_STOCK"])

    cash = CONFIG["INITIAL_CAPITAL"]
    portfolio, trade_history, daily_equity = {}, [], []
    risk_stats = {
        "连续亏损暂停次数": 0,
        "回撤暂停次数": 0,
        "暂停开仓天数": 0,
        "强市场天数": 0,
        "中性市场天数": 0,
        "弱市场天数": 0,
    }
    consecutive_loss_trades = 0
    loss_cooldown_until_idx = -1
    drawdown_cooldown_until_idx = -1
    equity_high_water_mark = CONFIG["INITIAL_CAPITAL"]
    drawdown_pause_armed = True

    period_dates = get_trading_calendar(benchmark_data, market_data, start_date, end_date)
    pending_buys, pending_sells = [], []

    for date_idx, current_date in enumerate(period_dates):
        regime_controls = get_regime_controls(market_context, current_date, max_holdings, max_position_per_stock, buy_threshold)
        if regime_controls["regime"] == "强":
            risk_stats["强市场天数"] += 1
        elif regime_controls["regime"] == "中":
            risk_stats["中性市场天数"] += 1
        elif regime_controls["regime"] == "弱":
            risk_stats["弱市场天数"] += 1

        # 1. 卖出
        still_pending_sells = []
        for symbol, reason in pending_sells:
            if symbol in portfolio and current_date in market_data[symbol].index:
                exec_price = market_data[symbol].loc[current_date]["开盘"] * (1 - CONFIG["SLIPPAGE_RATE"])
                shares = portfolio[symbol]["shares"]

                gross_value = shares * exec_price
                commission = max(CONFIG["MIN_COMMISSION"], gross_value * CONFIG["COMMISSION_RATE"])
                tax = gross_value * CONFIG["TAX_RATE"]
                net_value = gross_value - commission - tax
                cash += net_value

                buy_date_str = portfolio[symbol]["buy_date"].strftime("%Y-%m-%d")
                sell_date_str = current_date.strftime("%Y-%m-%d")
                invested = portfolio[symbol]["invested"]
                net_profit = net_value - invested

                trade_history.append({
                    "代码": str(symbol).zfill(6),
                    "名称": stock_pool.get(symbol, "未知"),
                    "买入日": buy_date_str,
                    "卖出日": sell_date_str,
                    "持仓天数": portfolio[symbol]["days"],
                    "买入数量": shares,
                    "买入价": round(portfolio[symbol]["cost"], 3),
                    "卖出价": round(exec_price, 3),
                    "买入耗资": round(invested, 2),
                    "卖出净额": round(net_value, 2),
                    "单笔净利": round(net_profit, 2),
                    "盈亏率": (exec_price - portfolio[symbol]["cost"]) / portfolio[symbol]["cost"],
                    "卖出原因": reason,
                    "卖出后现金": round(cash, 2)
                })
                del portfolio[symbol]

                if net_profit < 0:
                    consecutive_loss_trades += 1
                else:
                    consecutive_loss_trades = 0

                if CONFIG["ENABLE_LOSS_COOLDOWN"] and consecutive_loss_trades >= CONFIG["LOSS_COOLDOWN_TRIGGER"]:
                    loss_cooldown_until_idx = max(loss_cooldown_until_idx, date_idx + CONFIG["LOSS_COOLDOWN_DAYS"])
                    risk_stats["连续亏损暂停次数"] += 1
                    consecutive_loss_trades = 0
            elif symbol in portfolio:
                still_pending_sells.append((symbol, reason))
        pending_sells = still_pending_sells

        # 2. 买入
        risk_pause_active = date_idx <= loss_cooldown_until_idx or date_idx <= drawdown_cooldown_until_idx
        if risk_pause_active or not regime_controls["allow_new_positions"]:
            pending_buys.clear()
        else:
            pending_buys.sort(key=lambda x: x[1], reverse=True)
            for symbol, score, prev_close in pending_buys:
                if len(portfolio) >= regime_controls["max_holdings"]: break
                if symbol in portfolio or current_date not in market_data[symbol].index: continue

                ideal_price = market_data[symbol].loc[current_date]["开盘"]
                if (ideal_price - prev_close) / prev_close > CONFIG["MAX_BUY_GAP_RATE"]: continue

                exec_price = ideal_price * (1 + CONFIG["SLIPPAGE_RATE"])
                current_equity_for_budget = calculate_portfolio_equity(cash, portfolio, market_data, current_date, "开盘")
                shares_to_buy = int(min(cash, current_equity_for_budget * regime_controls["position_per_stock"]) / (exec_price * 100)) * 100

                if shares_to_buy >= 100:
                    cost = shares_to_buy * exec_price
                    commission_buy = max(CONFIG["MIN_COMMISSION"], cost * CONFIG["COMMISSION_RATE"])
                    total_invested = cost + commission_buy
                    cash -= total_invested

                    portfolio[symbol] = {
                        "shares": shares_to_buy,
                        "cost": exec_price,
                        "days": 0,
                        "highest": exec_price,
                        "buy_date": current_date,
                        "invested": total_invested
                    }
        pending_buys.clear()

        # 3. 持仓体检
        for symbol, pos in portfolio.items():
            if current_date not in market_data[symbol].index: continue
            today_k = market_data[symbol].loc[current_date]
            pos["days"] += 1
            pos["highest"] = max(pos["highest"], today_k["收盘"])
            return_rate = (today_k["收盘"] - pos["cost"]) / pos["cost"]

            sell_reason = ""
            if return_rate <= stop_loss_rate:
                sell_reason = "绝对止损"
            elif today_k["MA20_break_1"] and today_k["MA20_break_2"]:
                sell_reason = "破位防守"
            elif pos["highest"] >= pos["cost"] * 1.15 and today_k["收盘"] <= pos["highest"] * 0.92:
                sell_reason = "回撤止盈"
            elif return_rate > 0.15 and today_k["RSI14"] > rsi_oversold:
                sell_reason = "亢奋止盈"
            elif pos["days"] >= max_hold_days and -time_sunk_tolerance <= return_rate <= time_sunk_tolerance:
                sell_reason = "沉没止损"

            if sell_reason: pending_sells.append((symbol, sell_reason))

        current_equity = calculate_portfolio_equity(cash, portfolio, market_data, current_date, "收盘")
        if current_equity > equity_high_water_mark:
            equity_high_water_mark = current_equity
            drawdown_pause_armed = True

        current_drawdown = (current_equity - equity_high_water_mark) / equity_high_water_mark if equity_high_water_mark > 0 else 0
        if (
            CONFIG["ENABLE_DRAWDOWN_COOLDOWN"]
            and drawdown_pause_armed
            and abs(current_drawdown) >= CONFIG["MAX_EQUITY_DRAWDOWN_TO_PAUSE"]
        ):
            drawdown_cooldown_until_idx = max(drawdown_cooldown_until_idx, date_idx + CONFIG["DRAWDOWN_COOLDOWN_DAYS"])
            risk_stats["回撤暂停次数"] += 1
            drawdown_pause_armed = False

        # 大盘红绿灯
        market_is_healthy = regime_controls["allow_new_positions"] if CONFIG["ENABLE_MARKET_REGIME"] else is_market_healthy(benchmark_data, current_date)
        risk_pause_active = date_idx <= loss_cooldown_until_idx or date_idx <= drawdown_cooldown_until_idx
        if risk_pause_active:
            risk_stats["暂停开仓天数"] += 1

        # 4. 扫描打分
        if market_is_healthy and not risk_pause_active:
            for symbol, df in market_data.items():
                if symbol in portfolio or any(symbol == s for s, _ in pending_sells) or current_date not in df.index: continue
                today_k = df.loc[current_date]
                if today_k["RSI14"] > rsi_oversold: continue
                if not passes_entry_quality_filter(today_k): continue

                score = 0
                ma_list = [today_k["MA5"], today_k["MA10"], today_k["MA20"]]
                if (max(ma_list) - min(ma_list)) / min(ma_list) < 0.03: score += 10
                if today_k["收盘"] > today_k["MA5"] > today_k["MA10"] > today_k["MA20"]: score += 20
                elif today_k["收盘"] > today_k["MA20"]: score += 10

                if 1.5 <= (today_k["成交量"] / (today_k["Vol_MA20"] + 1e-9)) <= 2.5: score += 15
                if 55 <= today_k["RSI14"] <= 68: score += 15
                elif 50 <= today_k["RSI14"] < 55: score += 8

                if today_k["收盘"] > today_k["MA60"] and today_k["MA60"] >= today_k["MA60_prev5"]: score += 18
                elif today_k["收盘"] > today_k["MA60"]: score += 10

                recent_5 = df.loc[:current_date].iloc[-5:]
                if sum(recent_5["收盘"] > recent_5["开盘"]) >= 3:
                    score += 12 if today_k["收盘"] >= today_k["High_20"] else 8

                if score >= regime_controls["buy_threshold"]: pending_buys.append((symbol, score, today_k["收盘"]))

        daily_equity.append({"日期": current_date, "总权益": current_equity})

    df_equity = pd.DataFrame(daily_equity).set_index("日期") if daily_equity else pd.DataFrame()
    kpi_res = calc_kpi(df_equity["总权益"]) if not df_equity.empty else calc_kpi(pd.Series(dtype=float))

    kpi_res["参数组合"] = params
    kpi_res["交易明细"] = pd.DataFrame(trade_history)
    kpi_res["权益曲线"] = df_equity
    kpi_res["风控统计"] = risk_stats
    return kpi_res

# ==================== 4. 总控与寻优调度器 ====================
def run_optimization_and_blind_test():
    board_profile = get_board_profile()
    print(f"==================== 【阶段一：下载/加载数据 (当前开关: {CONFIG['TARGET_BOARD']} - {board_profile['name']})】 ====================")
    market_data, stock_pool = load_all_market_data()
    benchmark_data = load_benchmark_data()
    market_context = build_market_context(benchmark_data, market_data)

    print("\n==================== 【阶段二：训练集参数网格寻优】 ====================")
    keys, values = PARAM_GRID.keys(), PARAM_GRID.values()
    param_combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

    training_results = []
    for idx, params in enumerate(param_combinations):
        print(f"[*] 训练第 {idx+1}/{len(param_combinations)} 组参数: {params}")
        training_results.append(execute_single_backtest(params, market_data, stock_pool, benchmark_data, market_context, CONFIG["TRAIN_START"], CONFIG["TRAIN_END"]))

    training_results.sort(key=lambda x: x["Calmar"], reverse=True)
    best_train_res = training_results[0]
    best_params = best_train_res["参数组合"]

    print(f"\n>>> 【参数敏感性排查 - {CONFIG['TARGET_BOARD']} 板块 (Top 5)】 <<<")
    for i, res in enumerate(training_results[:5]):
        print(f"Top {i+1} | Calmar: {res['Calmar']:.2f} | 夏普: {res['Sharpe']:.2f} | 收益: {res['年化收益']*100:.1f}% | 回撤: {res['最大回撤']*100:.1f}% | 参数: {res['参数组合']}")

    print(f"\n==================== 【阶段三：样本外盲测大考 ({CONFIG['TARGET_BOARD']} 板块)】 ==================== ")
    print(f"[*] 正在使用 Top 1 参数 {best_params} 校验未知行情...")
    blind_res = execute_single_backtest(best_params, market_data, stock_pool, benchmark_data, market_context, CONFIG["TEST_START"], CONFIG["TEST_END"])
    benchmark_kpi = calc_benchmark_kpi(benchmark_data, CONFIG["TEST_START"], CONFIG["TEST_END"])

    trade_df = blind_res["交易明细"]
    equity_df = blind_res["权益曲线"]
    risk_stats = blind_res["风控统计"]
    output_dir, output_paths = build_output_bundle(best_params, len(stock_pool))

    if not trade_df.empty:
        trade_df.to_csv(output_paths["trade_history"], index=False, encoding="utf-8-sig")

    if not equity_df.empty:
        equity_df.to_csv(output_paths["equity_curve"], encoding="utf-8-sig")

    initial_capital = CONFIG["INITIAL_CAPITAL"]
    final_equity = equity_df["总权益"].iloc[-1] if not equity_df.empty else initial_capital
    realized_profit = trade_df["单笔净利"].sum() if not trade_df.empty else 0.0
    unrealized_profit = final_equity - initial_capital - realized_profit
    total_profit = final_equity - initial_capital
    total_return_pct = (total_profit / initial_capital) * 100
    benchmark_return_pct = benchmark_kpi["总收益"] * 100
    excess_return_pct = total_return_pct - benchmark_return_pct

    summary = {
        "运行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "板块": CONFIG["TARGET_BOARD"],
        "板块名称": board_profile["name"],
        "抽样上限": CONFIG.get("MAX_STOCKS_PER_BOARD") if CONFIG.get("MAX_STOCKS_PER_BOARD") is not None else "全部",
        "实际股票数量": len(stock_pool),
        "训练开始": CONFIG["TRAIN_START"],
        "训练结束": CONFIG["TRAIN_END"],
        "盲测开始": CONFIG["TEST_START"],
        "盲测结束": CONFIG["TEST_END"],
        "参数标识": build_param_slug(best_params),
        "最优参数": str(best_params),
        "期初资金": initial_capital,
        "期末总权益": final_equity,
        "已实现盈亏": realized_profit,
        "未实现盈亏": unrealized_profit,
        "总盈亏": total_profit,
        "总收益率": total_return_pct,
        "基准总收益率": benchmark_return_pct,
        "超额收益率": excess_return_pct,
        "最大回撤": blind_res["最大回撤"],
        "基准最大回撤": benchmark_kpi["最大回撤"],
        "Calmar": blind_res["Calmar"],
        "基准Calmar": benchmark_kpi["Calmar"],
        "Sharpe": blind_res["Sharpe"],
        "基准Sharpe": benchmark_kpi["Sharpe"],
        "交易次数": len(trade_df),
        "连续亏损暂停次数": risk_stats["连续亏损暂停次数"],
        "回撤暂停次数": risk_stats["回撤暂停次数"],
        "暂停开仓天数": risk_stats["暂停开仓天数"],
        "强市场天数": risk_stats["强市场天数"],
        "中性市场天数": risk_stats["中性市场天数"],
        "弱市场天数": risk_stats["弱市场天数"],
        "要求指数MA20上行": CONFIG["REQUIRE_BENCH_MA20_UP"],
        "要求指数站上MA60": CONFIG["REQUIRE_BENCH_ABOVE_MA60"],
        "要求个股MA60上行": CONFIG["REQUIRE_STOCK_MA60_UP"],
        "最低量比": CONFIG["MIN_ENTRY_VOLUME_RATIO"],
        "最低20日均成交额": CONFIG["MIN_AVG_AMOUNT_20"],
        "启用市场环境分级": CONFIG["ENABLE_MARKET_REGIME"],
        "强市MA20宽度阈值": CONFIG["STRONG_BREADTH_MA20"],
        "强市MA60宽度阈值": CONFIG["STRONG_BREADTH_MA60"],
        "中性MA20宽度阈值": CONFIG["NEUTRAL_BREADTH_MA20"],
        "中性MA60宽度阈值": CONFIG["NEUTRAL_BREADTH_MA60"],
        "中性最大持仓数": CONFIG["NEUTRAL_MAX_HOLDINGS"],
        "中性单票仓位倍率": CONFIG["NEUTRAL_POSITION_MULTIPLIER"],
        "弱市允许高分买入": CONFIG["WEAK_ALLOW_HIGH_SCORE_BUY"],
        "弱市买入分数门槛": CONFIG["WEAK_BUY_SCORE_THRESHOLD"],
        "弱市最大持仓数": CONFIG["WEAK_MAX_HOLDINGS"],
        "弱市单票仓位倍率": CONFIG["WEAK_POSITION_MULTIPLIER"],
        "连续亏损暂停触发笔数": CONFIG["LOSS_COOLDOWN_TRIGGER"],
        "连续亏损暂停天数": CONFIG["LOSS_COOLDOWN_DAYS"],
        "账户回撤暂停阈值": CONFIG["MAX_EQUITY_DRAWDOWN_TO_PAUSE"],
        "账户回撤暂停天数": CONFIG["DRAWDOWN_COOLDOWN_DAYS"],
    }
    pd.DataFrame([summary]).to_csv(output_paths["summary"], index=False, encoding="utf-8-sig")
    generate_html_report(output_paths["html_report"], trade_df, equity_df, summary)

    print("\n" + "="*58)
    print(f"          【{CONFIG['TARGET_BOARD']} - {board_profile['name']} 盲测期期末权益报告】          ")
    print("="*58)
    print(f"▶ 初始投入本金 : ¥{initial_capital:,.2f}")
    print(f"▶ 期末总权益 : ¥{final_equity:,.2f}")
    print(f"▶ 累计已实现盈亏 : ¥{realized_profit:+,.2f} 元")
    print(f"▶ 期末未实现盈亏 : ¥{unrealized_profit:+,.2f} 元")
    print(f"▶ 盲测期总盈亏 : ¥{total_profit:+,.2f} 元")
    print(f"▶ 盲测期总收益率 : {total_return_pct:+.2f}%")
    print(f"▶ 基准收益率 : {benchmark_return_pct:+.2f}% | 超额收益率 : {excess_return_pct:+.2f}%")
    print(f"▶ 最大回撤 : {blind_res['最大回撤']*100:.2f}% | Calmar: {blind_res['Calmar']:.2f} | Sharpe: {blind_res['Sharpe']:.2f}")
    print(f"▶ 基准回撤 : {benchmark_kpi['最大回撤']*100:.2f}% | 基准Calmar: {benchmark_kpi['Calmar']:.2f} | 基准Sharpe: {benchmark_kpi['Sharpe']:.2f}")
    print(f"▶ 交易次数 : {len(trade_df)}")
    print(f"▶ 风控介入 : 连续亏损暂停 {risk_stats['连续亏损暂停次数']} 次 | 回撤暂停 {risk_stats['回撤暂停次数']} 次 | 暂停开仓 {risk_stats['暂停开仓天数']} 天")
    print(f"▶ 市场分级 : 强 {risk_stats['强市场天数']} 天 | 中 {risk_stats['中性市场天数']} 天 | 弱 {risk_stats['弱市场天数']} 天")
    print(f"▶ 结果目录 : {output_dir}")
    print(f"▶ HTML报告 : {output_paths['html_report']}")
    print("="*58)

    if blind_res['Calmar'] < best_train_res['Calmar'] * 0.5:
        print("\n[!] 警告：盲测表现大幅度衰减，存在过度拟合风险，不建议实盘！")
    else:
        print(f"\n[√] 恭喜：{CONFIG['TARGET_BOARD']} 板块参数在样本外表现稳健，经受住了泛化检验。")

if __name__ == "__main__":
    run_optimization_and_blind_test()
