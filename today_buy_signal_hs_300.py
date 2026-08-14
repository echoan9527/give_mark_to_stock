'''
Author: Chengya
Description: Description
Date: 2026-08-09 23:13:59
LastEditors: Chengya
LastEditTime: 2026-08-09 23:14:33
'''
'''
Author: Chengya (程永安)
Description: 动态沪深300 + 大盘择时过滤器 + 实时个股扫描与打分选股系统 (实盘版)
'''
import os
import time
import random
from datetime import datetime
import akshare as ak
import numpy as np
import pandas as pd

CONFIG = {
    "SCAN_END_DATE": "2026-08-09",     # <- 设定为你希望扫描的最新日期
    "LOOKBACK_DAYS": 120,              # 向前获取最近 120 天数据以确保均线计算准确
    "BUY_SCORE_THRESHOLD": 60,         # 经过验证的最优及格线
    "RSI_OVERSOLD": 80,                # 超买过滤线
    "COMMISSION_RATE": 0.00025,
    "MIN_COMMISSION": 5.0,
    "TAX_RATE": 0.0005,
}

CACHE_DIR = "stock_data_cache_live"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def get_hs300_pool():
    print("[*] 正在获取最新沪深 300 成分股名录...")
    try:
        hs300_df = ak.index_stock_cons(symbol="000300")
        dynamic_pool = {str(row["品种代码"]).zfill(6): str(row["品种名称"]) for _, row in hs300_df.iterrows()}
        print(f"[*] 成功接入，共计 {len(dynamic_pool)} 只标的。")
        return dynamic_pool
    except Exception as e:
        print(f"[!] 沪深 300 名录获取失败: {e}")
        return {"600519": "贵州茅台", "300750": "宁德时代", "601318": "中国平安"}

def fetch_latest_stock_data(symbol, stock_name):
    prefix = "sh" if symbol.startswith(("60", "68")) else "sz"
    full_symbol = f"{prefix}{symbol}"

    try:
        # 获取最近一年的完整数据以计算技术指标
        df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq", start_date="20250101", end_date=datetime.now().strftime("%Y%m%d"))
        if df is None or len(df) < 60: return None
        df.rename(columns={"date": "日期", "open": "开盘", "close": "收盘", "high": "最高", "low": "最低", "volume": "成交量"}, inplace=True)
        df["日期"] = pd.to_datetime(df["日期"])
        df.set_index("日期", inplace=True)

        df["MA5"] = df["收盘"].rolling(5).mean()
        df["MA10"] = df["收盘"].rolling(10).mean()
        df["MA20"] = df["收盘"].rolling(20).mean()
        df["MA60"] = df["收盘"].rolling(60).mean()
        df["RSI14"] = calculate_rsi(df["收盘"], 14)
        df["Vol_MA20"] = df["成交量"].rolling(20).mean()
        df["MA60_prev5"] = df["MA60"].shift(5)
        df["High_20"] = df["收盘"].rolling(20).max().shift(1)
        df.dropna(inplace=True)
        return df
    except:
        return None

def fetch_latest_benchmark():
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df.rename(columns={"date": "日期", "close": "收盘"}, inplace=True)
        df["日期"] = pd.to_datetime(df["日期"])
        df.set_index("日期", inplace=True)
        df["MA20"] = df["收盘"].rolling(20).mean()
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"[!] 大盘基准获取失败: {e}")
        return None

def run_live_scanner():
    print("==================== 【阶段一：大盘红绿灯环境扫描】 ====================")
    bench_df = fetch_latest_benchmark()
    if bench_df is not None:
        latest_bench_date = bench_df.index[-1]
        latest_bench_row = bench_df.iloc[-1]
        bench_close = latest_bench_row["收盘"]
        bench_ma20 = latest_bench_row["MA20"]

        print(f"[*] 最新交易日: {latest_bench_date.strftime('%Y-%m-%d')}")
        print(f"[*] 沪深 300 收盘价: {bench_close:.2f} | 20日均线: {bench_ma20:.2f}")

        if bench_close < bench_ma20:
            print("\n[!] 【红灯警报】大盘当前收盘价低于 20 日均线，市场处于系统性弱势中！")
            print("[!] 根据风控铁律，今日【禁止一切买入操作】，全仓空仓防守。")
            return
        else:
            print("\n[√] 【绿灯放行】大盘运行于 20 日均线上方，环境健康，开始扫描个股...")

    print("\n==================== 【阶段二：全市场个股多维打分扫描】 ====================")
    pool = get_hs300_pool()
    signals = []

    for idx, (symbol, name) in enumerate(pool.items()):
        df = fetch_latest_stock_data(symbol, name)
        if df is None or df.empty: continue

        # 获取最新一天的个股数据
        today_k = df.iloc[-1]

        # 基础过滤：如果 RSI 已经超买，直接排除
        if today_k["RSI14"] > CONFIG["RSI_OVERSOLD"]: continue

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

        recent_5 = df.iloc[-5:]
        if sum(recent_5["收盘"] > recent_5["开盘"]) >= 3:
            score += 12 if today_k["收盘"] >= today_k["High_20"] else 8

        # 达到及格线，纳入候选
        if score >= CONFIG["BUY_SCORE_THRESHOLD"]:
            signals.append({
                "代码": symbol,
                "名称": name,
                "综合得分": score,
                "最新收盘价": round(today_k["收盘"], 2),
                "RSI14": round(today_k["RSI14"], 2),
                "日期": df.index[-1].strftime("%Y-%m-%d")
            })

        time.sleep(0.1) # 防止请求过快

    print("\n==================== 【阶段三：今日买入候选清单】 ====================")
    signal_df = pd.DataFrame(signals)
    if not signal_df.empty:
        signal_df.sort_values(by="综合得分", ascending=False, inplace=True)
        signal_df.to_csv("Today_Buy_Signals.csv", index=False, encoding="utf-8-sig")

        try:
            from tabulate import tabulate
            print(tabulate(signal_df, headers='keys', tablefmt='grid', showindex=False, stralign='center', numalign='center'))
        except:
            print(signal_df.to_string(index=False))

        print(f"\n[*] 扫描完毕！共筛选出 {len(signal_df)} 只符合右侧突破标准的标的，已保存至 Today_Buy_Signals.csv。")
    else:
        print("[*] 扫描完毕！今日没有标的能够通过严格的打分筛选，建议继续持币观望或空仓。")

if __name__ == "__main__":
    run_live_scanner()