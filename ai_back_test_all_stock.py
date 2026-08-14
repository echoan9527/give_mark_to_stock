'''
Author: Chengya
Description: Description
Date: 2026-08-10 22:47:56
LastEditors: Chengya
LastEditTime: 2026-08-10 23:08:48
'''
'''
Author: Chengya (程永安)
Description: 动态多板块量化回测引擎 (支持板块开关：ALL-全市场, MAIN-主板, CYB-创业板, KCB-科创板)
'''
import os
import time
import random
import itertools
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
    "COMMISSION_RATE": 0.00025,
    "MIN_COMMISSION": 5.0,
    "TAX_RATE": 0.0005,
    "TRAIN_START": "20210101",
    "TRAIN_END": "20231231",
    "TEST_START": "20240101",
    "TEST_END": "20260809",
    "SLIPPAGE_RATE": 0.002,

    # ==========================================
    # 🎯 核心板块开关 (Market Filter)
    # 可选值:
    #   "ALL"  -> 全市场融合 (主板 + 创业板 + 科创板大比武)
    #   "MAIN" -> 仅主板 (沪深主板 600/000 等，防守稳健)
    #   "CYB"  -> 仅创业板 (300/301 高弹性 20% 涨跌幅)
    #   "KCB"  -> 仅科创板 (688 硬科技高爆发)
    # ==========================================
    "TARGET_BOARD": "ALL"
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
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def get_filtered_market_pool():
    # board_mode = CONFIG["TARGET_BOARD"]
    # print(f"[*] 正在向接口请求全市场名录，并根据板块开关【 {board_mode} 】进行精准过滤...")

    # try:
    #     spot_df = ak.stock_zh_a_spot_em()
    #     pool = {}
    #     for _, row in spot_df.iterrows():
    #         code = str(row["代码"]).zfill(6)
    #         name = str(row["名称"])

    #         # 过滤 ST 与退市股
    #         if "ST" in name or "退" in name:
    #             continue

    #         # 根据开关分流匹配
    #         if board_mode == "ALL":
    #             # 全市场包含：主板、创业板、科创板
    #             if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003", "300", "301", "688", "689")):
    #                 pool[code] = name
    #         elif board_mode == "MAIN":
    #             # 仅主板
    #             if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
    #                 pool[code] = name
    #         elif board_mode == "CYB":
    #             # 仅创业板
    #             if code.startswith(("300", "301")):
    #                 pool[code] = name
    #         elif board_mode == "KCB":
    #             # 仅科创板
    #             if code.startswith(("688", "689")):
    #                 pool[code] = name

    #     # 截取前 400 只高流动性标的以保证回测效率
    #     pool_keys = list(pool.keys())[:400]
    #     filtered_pool = {k: pool[k] for k in pool_keys}

    #     print(f"[*] 板块过滤完毕！当前模式【 {board_mode} 】下有效标的共计 {len(filtered_pool)} 只。")
    #     return filtered_pool
    # except Exception as e:
    #     print(f"[!] 股票池拉取失败，启用备用池: {e}")
    #     return {"600519": "贵州茅台", "300750": "宁德时代", "688981": "中芯国际"}

    board_mode = CONFIG["TARGET_BOARD"]
    print(f"[*] 正在向接口请求全市场名录，并根据板块开关【 {board_mode} 】进行精准过滤...")

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

            # 根据开关分流匹配
            if board_mode == "ALL":
                if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003", "300", "301", "688", "689")):
                    pool[code] = name
            elif board_mode == "MAIN":
                if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
                    pool[code] = name
            elif board_mode == "CYB":
                if code.startswith(("300", "301")):
                    pool[code] = name
            elif board_mode == "KCB":
                if code.startswith(("688", "689")):
                    pool[code] = name

        # 截取前 400 只（由于新接口排序可能是按代码顺序，这里加入随机打乱以保证板块均匀）
        pool_items = list(pool.items())
        # random.shuffle(pool_items) # 如果想每次回测不同的股票，可以取消这行注释

        filtered_pool = dict(pool_items[:400])
        print(f"[*] 板块过滤完毕！当前模式【 {board_mode} 】下有效标的共计 {len(filtered_pool)} 只。")
        return filtered_pool
    except Exception as e:
        print(f"[!] 股票池拉取失败，启用备用池: {e}")
        return {"600519": "贵州茅台", "300750": "宁德时代", "688981": "中芯国际"}



def prepare_stock_data(symbol, stock_name):
    prefix = "sh" if symbol.startswith(("60", "68")) else "sz"
    full_symbol = f"{prefix}{symbol}"
    cache_filepath = os.path.join(CACHE_DIR, f"{full_symbol}_{CONFIG['TRAIN_START']}_{CONFIG['TEST_END']}.csv")

    if os.path.exists(cache_filepath):
        try:
            return pd.read_csv(cache_filepath, index_col="日期", parse_dates=True)
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
            df.dropna(inplace=True)

            df.to_csv(cache_filepath, encoding="utf-8-sig")
            time.sleep(random.uniform(0.3, 0.8))
            return df
        except Exception:
            if attempt < 2: time.sleep(random.uniform(2.0, 4.0))
    return None

def load_all_market_data():
    pool = get_filtered_market_pool()
    print("[*] 正在加载板块标的的历史数据...")
    market_data = {code: res for code, name in pool.items() if (res := prepare_stock_data(code, name)) is not None}
    print(f"[*] 成功加载有效回测标的共计 {len(market_data)} 只。")
    return market_data, pool

def load_benchmark_data():
    cache_filepath = os.path.join(CACHE_DIR, f"sh000300_benchmark_{CONFIG['TRAIN_START']}_{CONFIG['TEST_END']}.csv")
    if os.path.exists(cache_filepath):
        try: return pd.read_csv(cache_filepath, index_col="日期", parse_dates=True)
        except: pass
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df.rename(columns={"date": "日期", "close": "收盘"}, inplace=True)
        df["日期"] = pd.to_datetime(df["日期"])
        df.set_index("日期", inplace=True)
        df["MA20"] = df["收盘"].rolling(20).mean()
        df.dropna(inplace=True)
        df.to_csv(cache_filepath, encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"[!] 基准获取失败: {e}")
        return None

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

# ==================== 3. 策略回测黑盒引擎 ====================
def execute_single_backtest(params, market_data, stock_pool, benchmark_data, start_date, end_date):
    buy_threshold = params["BUY_SCORE_THRESHOLD"]
    stop_loss_rate = params["STOP_LOSS_RATE"]
    max_hold_days = params["MAX_HOLD_DAYS"]
    rsi_oversold = params["RSI_OVERSOLD"]
    time_sunk_tolerance = params["TIME_SUNK_TOLERANCE"]

    cash = CONFIG["INITIAL_CAPITAL"]
    portfolio, trade_history, daily_equity = {}, [], []

    all_dates = sorted(list(set.intersection(*[set(df.index) for df in market_data.values()])))
    period_dates = [d for d in all_dates if pd.to_datetime(start_date) <= d <= pd.to_datetime(end_date)]
    pending_buys, pending_sells = [], []

    for current_date in period_dates:
        # 1. 卖出
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
                    "代码": symbol,
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
        pending_sells.clear()

        # 2. 买入
        pending_buys.sort(key=lambda x: x[1], reverse=True)
        for symbol, score, prev_close in pending_buys:
            if len(portfolio) >= 5: break
            if symbol in portfolio or current_date not in market_data[symbol].index: continue

            ideal_price = market_data[symbol].loc[current_date]["开盘"]
            if (ideal_price - prev_close) / prev_close > 0.04: continue

            exec_price = ideal_price * (1 + CONFIG["SLIPPAGE_RATE"])
            current_equity_for_budget = cash + sum([p["shares"] * market_data[sym].loc[current_date]["开盘"] for sym, p in portfolio.items() if current_date in market_data[sym].index])
            shares_to_buy = int(min(cash, current_equity_for_budget * CONFIG["MAX_POSITION_PER_STOCK"]) / (exec_price * 100)) * 100

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

        # 大盘红绿灯
        market_is_healthy = True
        if benchmark_data is not None and current_date in benchmark_data.index:
            bench_today = benchmark_data.loc[current_date]
            if bench_today["收盘"] < bench_today["MA20"]:
                market_is_healthy = False

        # 4. 扫描打分
        if market_is_healthy:
            for symbol, df in market_data.items():
                if symbol in portfolio or any(symbol == s for s, _ in pending_sells) or current_date not in df.index: continue
                today_k = df.loc[current_date]
                if today_k["RSI14"] > rsi_oversold: continue

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

                if score >= buy_threshold: pending_buys.append((symbol, score, today_k["收盘"]))

        current_equity = cash + sum([pos["shares"] * market_data[sym].loc[current_date]["收盘"] for sym, pos in portfolio.items() if current_date in market_data[sym].index])
        daily_equity.append({"日期": current_date, "总权益": current_equity})

    df_equity = pd.DataFrame(daily_equity).set_index("日期") if daily_equity else pd.DataFrame()
    kpi_res = calc_kpi(df_equity["总权益"]) if not df_equity.empty else calc_kpi(pd.Series(dtype=float))

    kpi_res["参数组合"] = params
    kpi_res["交易明细"] = pd.DataFrame(trade_history)
    return kpi_res

# ==================== 4. 总控与寻优调度器 ====================
def run_optimization_and_blind_test():
    print(f"==================== 【阶段一：下载/加载数据 (当前开关: {CONFIG['TARGET_BOARD']})】 ====================")
    market_data, stock_pool = load_all_market_data()
    benchmark_data = load_benchmark_data()

    print("\n==================== 【阶段二：训练集参数网格寻优】 ====================")
    keys, values = PARAM_GRID.keys(), PARAM_GRID.values()
    param_combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

    training_results = []
    for idx, params in enumerate(param_combinations):
        print(f"[*] 训练第 {idx+1}/{len(param_combinations)} 组参数: {params}")
        training_results.append(execute_single_backtest(params, market_data, stock_pool, benchmark_data, CONFIG["TRAIN_START"], CONFIG["TRAIN_END"]))

    training_results.sort(key=lambda x: x["Calmar"], reverse=True)
    best_train_res = training_results[0]
    best_params = best_train_res["参数组合"]

    print(f"\n>>> 【参数敏感性排查 - {CONFIG['TARGET_BOARD']} 板块 (Top 5)】 <<<")
    for i, res in enumerate(training_results[:5]):
        print(f"Top {i+1} | Calmar: {res['Calmar']:.2f} | 夏普: {res['Sharpe']:.2f} | 收益: {res['年化收益']*100:.1f}% | 回撤: {res['最大回撤']*100:.1f}% | 参数: {res['参数组合']}")

    print(f"\n==================== 【阶段三：样本外盲测大考 ({CONFIG['TARGET_BOARD']} 板块)】 ==================== ")
    print(f"[*] 正在使用 Top 1 参数 {best_params} 校验未知行情...")
    blind_res = execute_single_backtest(best_params, market_data, stock_pool, benchmark_data, CONFIG["TEST_START"], CONFIG["TEST_END"])

    trade_df = blind_res["交易明细"]
    if not trade_df.empty:
        trade_df.to_csv(f"BlindTest_Trade_History_{CONFIG['TARGET_BOARD']}.csv", index=False, encoding="utf-8-sig")

        initial_capital = CONFIG["INITIAL_CAPITAL"]
        total_net_profit = trade_df["单笔净利"].sum()
        final_total_capital = initial_capital + total_net_profit
        total_return_pct = (total_net_profit / initial_capital) * 100

        print("\n" + "="*50)
        print(f"          【{CONFIG['TARGET_BOARD']} 板块盲测期期末财务决算报告】          ")
        print("="*50)
        print(f"▶ 初始投入本金 : ¥{initial_capital:,.2f}")
        print(f"▶ 最终清仓总资金 : ¥{final_total_capital:,.2f}")
        print(f"▶ 累计盈亏总额 : ¥{total_net_profit:+,.2f} 元")
        print(f"▶ 盲测期总收益率 : {total_return_pct:+.2f}%")
        print("="*50)

    if blind_res['Calmar'] < best_train_res['Calmar'] * 0.5:
        print("\n[!] 警告：盲测表现大幅度衰减，存在过度拟合风险，不建议实盘！")
    else:
        print(f"\n[√] 恭喜：{CONFIG['TARGET_BOARD']} 板块参数在样本外表现稳健，经受住了泛化检验。")

if __name__ == "__main__":
    run_optimization_and_blind_test()