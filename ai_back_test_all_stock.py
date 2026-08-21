'''
Author: Chengya
Description: Description
Date: 2026-08-10 22:47:56
LastEditors: Chengya
LastEditTime: 2026-08-20 15:02:38
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
    # "TRAIN_START": "20210101",#训练数据 开始时间
    # "TRAIN_END": "20231231", # 训练数据 结束时间
    # "TEST_START": "20240101",# 回测数据 开始时间
    # "TEST_END": "20260809",# 回测数据 结束时间

    "TRAIN_START": "20210101",#训练数据 开始时间
    "TRAIN_END": "20221231", # 训练数据 结束时间
    "TEST_START": "20230101",# 回测数据 开始时间
    "TEST_END": "20260809",# 回测数据 结束时间

    "SLIPPAGE_RATE": 0.002, # 单边滑点，0.002 表示买入贵 0.2%、卖出便宜 0.2%
    "BUY_EXECUTION_DELAY_DAYS": 1,  # 买入执行延迟：1 表示信号日后下一交易日开盘买入，2 表示再慢一天
    "SELL_EXECUTION_DELAY_DAYS": 1, # 卖出执行延迟：1 表示卖出信号后下一交易日开盘卖出，2 表示再慢一天
    "REVALIDATE_DELAYED_BUY_SIGNAL": False, # 买入延迟超过 1 天时，是否要求执行前一晚信号仍然有效；避免追买过期信号
    "MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE": None, # 买入延迟超过 1 天时，相对原信号日收盘最多允许上涨多少；None 表示不额外限制
    "MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN": None,   # 买入延迟超过 1 天时，相对原计划买入日开盘最多允许上涨多少；用于判断错过后是否买贵
    "REQUIRE_DELAYED_BUY_ABOVE_MA20": False,       # 买入延迟超过 1 天时，是否要求执行日开盘仍站上 MA20；避免延迟后形态已走坏仍买入

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

    # ================= 退出机制开关 =================
    "BREAKDOWN_CONFIRM_DAYS": 3,           # 破位防守需要连续多少个交易日收盘低于 MA20；3 是上一轮 M 场景验证后的新基准
    "STRONG_BREAKDOWN_CONFIRM_DAYS": None, # 强市场专用破位确认天数；None 表示沿用 BREAKDOWN_CONFIRM_DAYS
    "WEAK_BREAKDOWN_CONFIRM_DAYS": None,   # 弱市场专用破位确认天数；None 表示沿用 BREAKDOWN_CONFIRM_DAYS，用于测试转弱后是否应更快防守
    "ENABLE_WEAK_HOLDING_EXIT": True,      # 市场转弱后是否对已有持仓启用额外退出规则；当前基准为 5 天 + 10% 收益上限
    "WEAK_HOLDING_EXIT_DAYS": 5,           # 持仓连续经历弱市场达到多少天后触发转弱退出检查
    "WEAK_HOLDING_EXIT_MAX_RETURN": 0.10,  # 转弱退出只处理收益率不高于该阈值的持仓；9%-10% 是多轮消融验证后的候选主策略区间
    "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True, # True 表示只处理信号日不是弱市的旧持仓，聚焦“强/中转弱”的风险
    "TRAIL_PROFIT_TRIGGER": 0.20,          # 持仓最高价超过买入价 20% 后，启动回撤止盈观察；这是上一轮 M 场景验证后的新基准
    "TRAIL_DRAWDOWN_RATE": 0.10,           # 启动回撤止盈后，从最高价回撤 10% 触发卖出
    "ENABLE_EXCITEMENT_TAKE_PROFIT": True, # 是否启用亢奋止盈；用于测试是否过早卖飞强势股

    # 市场环境分级：强市正常仓位，中性市轻仓，弱市不新开仓。
    "ENABLE_MARKET_REGIME": True,          # 是否启用市场环境分级；开启后根据市场宽度决定正常仓、轻仓或不新开仓
    "STRONG_BREADTH_MA20": 0.55,           # 强市场要求股票池中至少 55% 股票站上 MA20，代表短中期赚钱效应较好
    "STRONG_BREADTH_MA60": 0.45,           # 强市场要求股票池中至少 45% 股票站上 MA60，代表中期趋势基础足够
    "NEUTRAL_BREADTH_MA20": 0.35,          # 中性市场要求至少 35% 股票站上 MA20；低于该值说明短线环境偏弱
    "NEUTRAL_BREADTH_MA60": 0.25,          # 中性市场要求至少 25% 股票站上 MA60；低于该值说明多数股票处于中期弱势
    "STRONG_MAX_HOLDINGS": 8,              # 强市场最多持仓 8 只；这是上一轮 E 场景验证后沉淀的新基准
    "STRONG_POSITION_PER_STOCK": 0.1125,   # 强市场单票仓位 11.25%，8 只约 90% 仓位；上一轮 AB 测试中回撤更低且风险效率更好
    "NEUTRAL_ALLOW_BUY": True,             # 中性市场是否允许开仓；用于消融测试时验证中性行情是否拖累策略
    "NEUTRAL_BUY_SCORE_OFFSET": 0,         # 中性市场买入分数额外提高多少分；0 表示不额外提高
    "NEUTRAL_MAX_HOLDINGS": 2,             # 中性市场最多持仓 2 只，允许少量试错，但避免接近满仓暴露
    "NEUTRAL_POSITION_MULTIPLIER": 0.50,   # 中性市场单票仓位按正常仓位的 50% 执行，用轻仓参与不确定行情
    "WEAK_ALLOW_HIGH_SCORE_BUY": True,     # 弱市场不完全禁买，只允许极高分信号小仓试错，避免错过结构性强势票
    "WEAK_BUY_SCORE_THRESHOLD": 78,        # 弱市场买入分数门槛，必须明显高于普通阈值才允许开仓
    "WEAK_MAX_HOLDINGS": 1,                # 弱市场最多持仓 1 只，控制极端环境下的风险暴露
    "WEAK_POSITION_MULTIPLIER": 0.20,      # 弱市场单票仓位按正常仓位的 20% 执行；上一轮仓位敏感性测试中收益/回撤更均衡
    "WEAK_STOP_LOSS_RATE": None,           # 弱市场专用止损阈值；None 表示沿用参数网格里的 STOP_LOSS_RATE

    # 候选排序：不改变是否入选，只改变多个候选同时出现时优先买谁。
    "ENABLE_CANDIDATE_RANKING": False,     # 是否启用候选排序分；关闭时继续按原始买入分排序
    "CANDIDATE_RANKING_REGIMES": None,     # 候选排序适用的市场环境列表；None 表示全部环境，["强"] 表示只在强市排序
    "RANK_PRIMARY_SCORE_BAND": None,       # 原始买入分数分档宽度；None 表示排序分直接主导，5 表示原始分同一 5 分档内才用排序分
    "MAX_ENTRY_DISTANCE_MA20": None,       # 入场日收盘价距离 MA20 的最大比例；None 表示不做硬过滤
    "STRONG_MAX_ENTRY_DISTANCE_MA20": None, # 强市场专用：收盘价距离 MA20 超过该比例时不买，主要防止强市里追高假突破
    "STRONG_MAX_ENTRY_VOLUME_RATIO": None, # 强市场专用：量比超过该值时不买，主要过滤短线情绪过热后的冲高回落
    "RANK_WEIGHT_TREND": 12,               # 趋势质量排序权重，偏好均线多头且 MA20 上行的股票
    "RANK_WEIGHT_LIQUIDITY": 8,            # 流动性排序权重，偏好成交额更充足、实盘更容易成交的股票
    "RANK_WEIGHT_BREAKOUT": 10,            # 突破质量排序权重，偏好刚突破但不极端追高的股票
    "RANK_WEIGHT_RSI": 8,                  # RSI 舒适区排序权重，偏好强但不过热的股票
    "RANK_WEIGHT_DISTANCE": 10,            # 距离 MA20 排序权重，距离太远会扣分，减少追高买入
    "CANDIDATE_WATCH_HORIZONS": [5, 10, 20], # 跟踪因持仓上限未买入候选股之后 5/10/20 个交易日的表现

    # ================= 稳定性验证 / 消融对照测试 =================
    "ENABLE_STABILITY_TESTS": True,        # 是否启用稳定性验证；开启后跳过训练寻优，直接用固定主策略跑不同股票池/随机种子
    "STABILITY_FIXED_PARAMS": {            # 稳定性验证固定使用的主策略参数；避免在盲测期反复挑参数造成过拟合
        "BUY_SCORE_THRESHOLD": 70,
        "STOP_LOSS_RATE": -0.09,
        "MAX_HOLD_DAYS": 20,
        "RSI_OVERSOLD": 80,
        "TIME_SUNK_TOLERANCE": 0.03,
    },
    "ENABLE_PARAM_RECHECKS": True,         # 是否在盲测前复验固定参数和训练 Top 参数，用来检查训练寻优是否误导
    "PARAM_RECHECK_TOP_N": 5,              # 训练集排名前 N 的参数组合也进入盲测复验
    "USE_PARAM_RECHECK_WINNER_FOR_ABLATION": True, # 消融测试是否使用固定参数复验胜出的参数，而不是训练 Top1
    "ABLATION_FIXED_PARAMS": {             # 消融实验锁定使用的参数；避免复验赢家变化导致实验基准漂移
        "BUY_SCORE_THRESHOLD": 70,
        "STOP_LOSS_RATE": -0.09,
        "MAX_HOLD_DAYS": 20,
        "RSI_OVERSOLD": 80,
        "TIME_SUNK_TOLERANCE": 0.03,
    },
    "ENABLE_ABLATION_TESTS": False,        # 是否在训练出 Top1 参数后，一次性跑完下方消融场景；稳定性验证阶段默认关闭
}

STABILITY_POOL_SCENARIOS = [
    {
        "id": "SV_sample600_seed20260814",
        "name": "SV_抽样600_seed20260814",
        "enabled": False,
        "description": "当前主样本复验，用来和过去多轮结果保持可比。",
        "overrides": {"MAX_STOCKS_PER_BOARD": 600, "POOL_SAMPLE_SEED": 20260814},
    },
    {
        "id": "SV_sample600_seed20240101",
        "name": "SV_抽样600_seed20240101",
        "enabled": False,
        "description": "换一个随机种子抽样 600 只主板股票，验证策略是否依赖原始样本。",
        "overrides": {"MAX_STOCKS_PER_BOARD": 600, "POOL_SAMPLE_SEED": 20240101},
    },
    {
        "id": "SV_sample600_seed20250101",
        "name": "SV_抽样600_seed20250101",
        "enabled": False,
        "description": "再换一个随机种子抽样 600 只主板股票，继续检查样本稳定性。",
        "overrides": {"MAX_STOCKS_PER_BOARD": 600, "POOL_SAMPLE_SEED": 20250101},
    },
    {
        "id": "SV_sample600_seed20230315",
        "name": "SV_抽样600_seed20230315",
        "enabled": False,
        "description": "新增固定随机种子抽样 600 只主板股票，用来复验默认辅助排序是否继续稳定。",
        "overrides": {"MAX_STOCKS_PER_BOARD": 600, "POOL_SAMPLE_SEED": 20230315},
    },
    {
        "id": "SV_sample600_seed20241111",
        "name": "SV_抽样600_seed20241111",
        "enabled": False,
        "description": "新增固定随机种子抽样 600 只主板股票，继续扩大股票池稳定性验证范围。",
        "overrides": {"MAX_STOCKS_PER_BOARD": 600, "POOL_SAMPLE_SEED": 20241111},
    },
    {
        "id": "SV_all_main",
        "name": "SV_主板全量",
        "enabled": True,
        "description": "使用当前主板全部可用标的验证，不再随机抽样；耗时会明显更长。",
        "overrides": {"MAX_STOCKS_PER_BOARD": None, "POOL_SAMPLE_SEED": None},
    },
]

STABILITY_STRATEGY_SCENARIOS = [
    {
        "id": "PT_base",
        "name": "压力基准_原策略",
        "enabled": True,
        "description": "当前候选主策略的基准压力测试：0.2% 单边滑点，信号后下一交易日开盘执行。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 1,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_slippage_0p3",
        "name": "压力_滑点0.3%",
        "enabled": False,
        "description": "只把单边滑点从 0.2% 提高到 0.3%，测试交易摩擦小幅上升后的承压能力。",
        "overrides": {
            "SLIPPAGE_RATE": 0.003,
            "BUY_EXECUTION_DELAY_DAYS": 1,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_slippage_0p5",
        "name": "压力_滑点0.5%",
        "enabled": False,
        "description": "只把单边滑点提高到 0.5%，模拟成交明显不利或追买卖出都不理想的情况。",
        "overrides": {
            "SLIPPAGE_RATE": 0.005,
            "BUY_EXECUTION_DELAY_DAYS": 1,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_delay_2d",
        "name": "压力_买入慢一天",
        "enabled": True,
        "description": "买入从信号后下一交易日开盘延迟到第 2 个交易日开盘，测试追不上信号时的影响。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_sell_delay_2d",
        "name": "压力_卖出慢一天",
        "enabled": False,
        "description": "卖出从触发后下一交易日开盘延迟到第 2 个交易日开盘，测试止损和止盈执行变慢的影响。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 1,
            "SELL_EXECUTION_DELAY_DAYS": 2,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_sell_delay_2d",
        "name": "压力_买卖都慢一天",
        "enabled": False,
        "description": "买入和卖出都比当前基准慢一个交易日，测试执行纪律或成交不及时的综合影响。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 2,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_delay_revalidate",
        "name": "压力_买入慢一天需复核",
        "enabled": False,
        "description": "买入晚一天时，不直接追买旧信号；只有执行前一晚仍满足买入条件才允许买入，否则放弃。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "REVALIDATE_DELAYED_BUY_SIGNAL": True,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_delay_signal_gap_2p",
        "name": "压力_慢一天信号涨幅2%",
        "enabled": True,
        "description": "买入晚一天时，不重新完整复核信号；只要执行日开盘相对原信号日收盘涨幅超过 2% 就放弃，测试少追高是否改善结果。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "REVALIDATE_DELAYED_BUY_SIGNAL": False,
            "MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE": 0.02,
            "MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN": None,
            "REQUIRE_DELAYED_BUY_ABOVE_MA20": False,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_delay_first_open_gap_0p",
        "name": "压力_慢一天不比原计划贵",
        "enabled": True,
        "description": "买入晚一天时，若执行日开盘高于原计划买入日开盘就放弃；测试错过后只在价格回落或不贵时才补买。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "REVALIDATE_DELAYED_BUY_SIGNAL": False,
            "MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE": None,
            "MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN": 0.0,
            "REQUIRE_DELAYED_BUY_ABOVE_MA20": False,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_buy_delay_first_open_gap_2p",
        "name": "压力_慢一天原计划涨幅2%",
        "enabled": True,
        "description": "买入晚一天时，若执行日开盘相对原计划买入日开盘涨幅超过 2% 就放弃；测试允许小幅买贵是否比完全不追更均衡。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "REVALIDATE_DELAYED_BUY_SIGNAL": False,
            "MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE": None,
            "MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN": 0.02,
            "REQUIRE_DELAYED_BUY_ABOVE_MA20": False,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_no_weak_buy",
        "name": "压力_弱市不买",
        "enabled": False,
        "description": "关闭弱市高分小仓买入，检查全量验证中弱市信号贡献是否真实重要。",
        "overrides": {
            "SLIPPAGE_RATE": 0.002,
            "BUY_EXECUTION_DELAY_DAYS": 1,
            "SELL_EXECUTION_DELAY_DAYS": 1,
            "COMMISSION_RATE": 0.00025,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": False,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
    {
        "id": "PT_harsh_execution",
        "name": "压力_高摩擦组合",
        "enabled": False,
        "description": "单边滑点 0.5%、买卖都慢一个交易日、佣金率提高到万五，用来做偏严苛实盘压力测试。",
        "overrides": {
            "SLIPPAGE_RATE": 0.005,
            "BUY_EXECUTION_DELAY_DAYS": 2,
            "SELL_EXECUTION_DELAY_DAYS": 2,
            "COMMISSION_RATE": 0.0005,
            "ENABLE_CANDIDATE_RANKING": False,
            "CANDIDATE_RANKING_REGIMES": None,
            "RANK_PRIMARY_SCORE_BAND": None,
            "MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_DISTANCE_MA20": None,
            "STRONG_MAX_ENTRY_VOLUME_RATIO": None,
            "WEAK_ALLOW_HIGH_SCORE_BUY": True,
            "RANK_WEIGHT_TREND": 12,
            "RANK_WEIGHT_LIQUIDITY": 8,
            "RANK_WEIGHT_BREAKOUT": 10,
            "RANK_WEIGHT_RSI": 8,
            "RANK_WEIGHT_DISTANCE": 10,
        },
    },
]

def build_stability_scenarios():
    scenarios = []
    for strategy in STABILITY_STRATEGY_SCENARIOS:
        for pool in STABILITY_POOL_SCENARIOS:
            overrides = dict(strategy.get("overrides", {}))
            overrides.update(pool.get("overrides", {}))
            scenarios.append({
                "id": f"{strategy['id']}__{pool['id']}",
                "name": f"{strategy['name']} | {pool['name']}",
                "enabled": strategy.get("enabled", True) and pool.get("enabled", True),
                "description": f"{strategy['description']}；{pool['description']}",
                "overrides": overrides,
            })
    return scenarios

STABILITY_SCENARIOS = build_stability_scenarios()

FIXED_PARAM_RECHECKS = [
    {
        "id": "last_m_winner",
        "name": "上一轮M高分参数",
        "description": "上一轮 M 场景在盲测期表现最好的参数，用来和本轮训练 Top 参数复验对照。",
        "params": {
            "BUY_SCORE_THRESHOLD": 60,
            "STOP_LOSS_RATE": -0.07,
            "MAX_HOLD_DAYS": 20,
            "RSI_OVERSOLD": 80,
            "TIME_SUNK_TOLERANCE": 0.03,
        },
    },
]

ABLATION_SCENARIOS = [
    {
        "id": "AD_baseline_90pos",
        "name": "AD_90%仓位基准",
        "description": "采用上一轮确认的强市约 90% 仓位，锁定 70 分买入、-9% 止损、转弱 5 天 10% 退出，作为本轮转弱持仓处理基准。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "BREAKDOWN_CONFIRM_DAYS": 3,
            "STRONG_BREAKDOWN_CONFIRM_DAYS": None,
            "WEAK_BREAKDOWN_CONFIRM_DAYS": None,
            "WEAK_HOLDING_EXIT_DAYS": 5,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.10,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_4d10",
        "name": "AD_转弱4天10%",
        "description": "只处理非弱市入场的旧持仓，把转弱退出从连续 5 天提前到 4 天，收益上限仍为 10%。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": True,
            "WEAK_HOLDING_EXIT_DAYS": 4,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.10,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_3d10",
        "name": "AD_转弱3天10%",
        "description": "只处理非弱市入场的旧持仓，把转弱退出从连续 5 天提前到 3 天，测试更早退出能否减少弱市阶段回撤。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": True,
            "WEAK_HOLDING_EXIT_DAYS": 3,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.10,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_5d8",
        "name": "AD_转弱5天8%",
        "description": "连续弱市天数仍为 5 天，但收益上限从 10% 收紧到 8%，测试是否应更积极保护小幅盈利票。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": True,
            "WEAK_HOLDING_EXIT_DAYS": 5,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.08,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_5d6",
        "name": "AD_转弱5天6%",
        "description": "连续弱市天数仍为 5 天，但收益上限收紧到 6%，测试更严格保护盈利是否会过早卖飞。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": True,
            "WEAK_HOLDING_EXIT_DAYS": 5,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.06,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_3d8",
        "name": "AD_转弱3天8%",
        "description": "同时提前到连续弱市 3 天，并把收益上限收紧到 8%，测试更强转弱防守是否过度。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": True,
            "WEAK_HOLDING_EXIT_DAYS": 3,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.08,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
    {
        "id": "AD_transition_exit_off",
        "name": "AD_关闭转弱退出",
        "description": "关闭转弱持仓退出，作为负向对照，确认该机制到底是在贡献收益还是干扰趋势持仓。",
        "overrides": {
            "STRONG_MAX_HOLDINGS": 8,
            "STRONG_POSITION_PER_STOCK": 0.1125,
            "ENABLE_WEAK_HOLDING_EXIT": False,
            "WEAK_HOLDING_EXIT_DAYS": 5,
            "WEAK_HOLDING_EXIT_MAX_RETURN": 0.10,
            "WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY": True,
            "WEAK_STOP_LOSS_RATE": None,
        },
    },
]

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
    if "MA20_prev5" not in df.columns and "MA20" in df.columns:
        df["MA20_prev5"] = df["MA20"].shift(5)
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
        strong_max_holdings = CONFIG["STRONG_MAX_HOLDINGS"] if CONFIG.get("STRONG_MAX_HOLDINGS") is not None else base_max_holdings
        strong_position_per_stock = CONFIG["STRONG_POSITION_PER_STOCK"] if CONFIG.get("STRONG_POSITION_PER_STOCK") is not None else base_position_per_stock
        return {
            "regime": regime,
            "allow_new_positions": True,
            "max_holdings": strong_max_holdings,
            "position_per_stock": strong_position_per_stock,
            "buy_threshold": base_buy_threshold,
        }
    if regime == "中":
        if not CONFIG.get("NEUTRAL_ALLOW_BUY", True):
            return {
                "regime": regime,
                "allow_new_positions": False,
                "max_holdings": 0,
                "position_per_stock": 0,
                "buy_threshold": base_buy_threshold + CONFIG.get("NEUTRAL_BUY_SCORE_OFFSET", 0),
            }
        return {
            "regime": regime,
            "allow_new_positions": True,
            "max_holdings": min(base_max_holdings, CONFIG["NEUTRAL_MAX_HOLDINGS"]),
            "position_per_stock": base_position_per_stock * CONFIG["NEUTRAL_POSITION_MULTIPLIER"],
            "buy_threshold": base_buy_threshold + CONFIG.get("NEUTRAL_BUY_SCORE_OFFSET", 0),
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

def passes_entry_quality_filter(today_k, regime=None):
    if CONFIG["REQUIRE_STOCK_MA60_UP"]:
        if not (today_k["收盘"] > today_k["MA60"] and today_k["MA60"] >= today_k["MA60_prev5"]):
            return False

    vol_ratio = today_k["成交量"] / (today_k["Vol_MA20"] + 1e-9)
    if vol_ratio < CONFIG["MIN_ENTRY_VOLUME_RATIO"]:
        return False

    if regime == "强":
        ma20 = today_k.get("MA20", 0)
        if ma20 > 0:
            distance_ma20 = today_k["收盘"] / ma20 - 1
            strong_max_distance = CONFIG.get("STRONG_MAX_ENTRY_DISTANCE_MA20")
            if strong_max_distance is not None and distance_ma20 > strong_max_distance:
                return False

        strong_max_volume_ratio = CONFIG.get("STRONG_MAX_ENTRY_VOLUME_RATIO")
        if strong_max_volume_ratio is not None and vol_ratio > strong_max_volume_ratio:
            return False

    min_amount = CONFIG.get("MIN_AVG_AMOUNT_20")
    if min_amount is not None and today_k.get("Amount_MA20", 0) < min_amount:
        return False

    return True

def candidate_ranking_applies(regime):
    if not CONFIG.get("ENABLE_CANDIDATE_RANKING", False):
        return False
    ranking_regimes = CONFIG.get("CANDIDATE_RANKING_REGIMES")
    if ranking_regimes is None:
        return True
    return regime in ranking_regimes

def candidate_sort_key(candidate):
    if len(candidate) == 7:
        _signal_idx, _execute_idx, _symbol, score, rank_score, _prev_close, signal_snapshot = candidate
    elif len(candidate) == 6:
        _execute_idx, _symbol, score, rank_score, _prev_close, signal_snapshot = candidate
    else:
        _symbol, score, rank_score, _prev_close, signal_snapshot = candidate
    signal_regime = signal_snapshot.get("信号日市场环境") if isinstance(signal_snapshot, dict) else None
    if not candidate_ranking_applies(signal_regime):
        return (score, rank_score)

    score_band = CONFIG.get("RANK_PRIMARY_SCORE_BAND")
    if score_band:
        score_bucket = int(score // score_band)
        return (score_bucket, rank_score, score)

    return (rank_score, score)

def calculate_buy_signal_score(df, current_date):
    today_k = df.loc[current_date]
    score = 0
    ma_list = [today_k["MA5"], today_k["MA10"], today_k["MA20"]]
    if (max(ma_list) - min(ma_list)) / min(ma_list) < 0.03:
        score += 10
    if today_k["收盘"] > today_k["MA5"] > today_k["MA10"] > today_k["MA20"]:
        score += 20
    elif today_k["收盘"] > today_k["MA20"]:
        score += 10

    volume_ratio = today_k["成交量"] / (today_k["Vol_MA20"] + 1e-9)
    if 1.5 <= volume_ratio <= 2.5:
        score += 15
    if 55 <= today_k["RSI14"] <= 68:
        score += 15
    elif 50 <= today_k["RSI14"] < 55:
        score += 8

    if today_k["收盘"] > today_k["MA60"] and today_k["MA60"] >= today_k["MA60_prev5"]:
        score += 18
    elif today_k["收盘"] > today_k["MA60"]:
        score += 10

    recent_5 = df.loc[:current_date].iloc[-5:]
    if sum(recent_5["收盘"] > recent_5["开盘"]) >= 3:
        score += 12 if today_k["收盘"] >= today_k["High_20"] else 8

    return score, recent_5

def calculate_candidate_rank_score(today_k, recent_5, base_score, regime=None):
    close = today_k["收盘"]
    ma20 = today_k["MA20"]
    if ma20 <= 0:
        return base_score

    distance_ma20 = close / ma20 - 1
    max_distance = CONFIG.get("MAX_ENTRY_DISTANCE_MA20")
    if max_distance is not None and distance_ma20 > max_distance:
        return None

    if not candidate_ranking_applies(regime):
        return base_score

    rank_score = float(base_score)

    trend_points = 0
    if close > today_k["MA5"] > today_k["MA10"] > today_k["MA20"]:
        trend_points += CONFIG["RANK_WEIGHT_TREND"] * 0.55
    if today_k["MA20"] >= today_k.get("MA20_prev5", today_k["MA20"]):
        trend_points += CONFIG["RANK_WEIGHT_TREND"] * 0.25
    if today_k["MA60"] >= today_k["MA60_prev5"]:
        trend_points += CONFIG["RANK_WEIGHT_TREND"] * 0.20
    rank_score += trend_points

    amount_ratio = today_k.get("Amount_MA20", 0) / (CONFIG["MIN_AVG_AMOUNT_20"] + 1e-9)
    rank_score += min(CONFIG["RANK_WEIGHT_LIQUIDITY"], max(0, amount_ratio - 1) * CONFIG["RANK_WEIGHT_LIQUIDITY"] / 2)

    if close >= today_k["High_20"]:
        rank_score += CONFIG["RANK_WEIGHT_BREAKOUT"] * (0.65 if distance_ma20 <= 0.12 else 0.25)
    if sum(recent_5["收盘"] > recent_5["开盘"]) >= 3:
        rank_score += CONFIG["RANK_WEIGHT_BREAKOUT"] * 0.35

    rsi = today_k["RSI14"]
    if 55 <= rsi <= 68:
        rank_score += CONFIG["RANK_WEIGHT_RSI"]
    elif 50 <= rsi < 55 or 68 < rsi <= 75:
        rank_score += CONFIG["RANK_WEIGHT_RSI"] * 0.35
    elif rsi > 75:
        rank_score -= CONFIG["RANK_WEIGHT_RSI"] * 0.70

    if distance_ma20 <= 0.06:
        rank_score += CONFIG["RANK_WEIGHT_DISTANCE"]
    elif distance_ma20 <= 0.12:
        rank_score += CONFIG["RANK_WEIGHT_DISTANCE"] * 0.45
    elif distance_ma20 > 0.18:
        rank_score -= CONFIG["RANK_WEIGHT_DISTANCE"]

    return rank_score

def safe_float(value, default=np.nan):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default

def build_signal_snapshot(symbol, df, signal_date, market_context):
    row = df.loc[signal_date]
    state = market_context.get(signal_date, {}) if market_context else {}
    ma20 = safe_float(row.get("MA20"))
    ma60 = safe_float(row.get("MA60"))
    close = safe_float(row.get("收盘"))
    vol_ma20 = safe_float(row.get("Vol_MA20"), 0)
    amount_ma20 = safe_float(row.get("Amount_MA20"))
    recent_5 = df.loc[:signal_date].iloc[-5:]

    distance_ma20 = close / ma20 - 1 if ma20 and ma20 > 0 else np.nan
    distance_ma60 = close / ma60 - 1 if ma60 and ma60 > 0 else np.nan
    volume_ratio = safe_float(row.get("成交量"), 0) / (vol_ma20 + 1e-9) if vol_ma20 is not None else np.nan

    return {
        "信号日": signal_date.strftime("%Y-%m-%d"),
        "信号日市场环境": state.get("regime", ""),
        "信号日市场MA20宽度": state.get("ma20_ratio", np.nan),
        "信号日市场MA60宽度": state.get("ma60_ratio", np.nan),
        "信号日市场MA60上行宽度": state.get("ma60_up_ratio", np.nan),
        "信号日指数站上MA20": state.get("bench_close_above_ma20", ""),
        "信号日指数MA20上行": state.get("bench_ma20_up", ""),
        "信号日指数站上MA60": state.get("bench_close_above_ma60", ""),
        "信号日收盘": close,
        "信号日RSI14": safe_float(row.get("RSI14")),
        "信号日量比": volume_ratio,
        "信号日20日均成交额": amount_ma20,
        "信号日距MA20": distance_ma20,
        "信号日距MA60": distance_ma60,
        "信号日站上MA20": bool(close > ma20) if not pd.isna(close) and not pd.isna(ma20) else "",
        "信号日站上MA60": bool(close > ma60) if not pd.isna(close) and not pd.isna(ma60) else "",
        "信号日MA20上行": bool(row.get("MA20", np.nan) >= row.get("MA20_prev5", np.nan)) if not pd.isna(row.get("MA20_prev5", np.nan)) else "",
        "信号日MA60上行": bool(row.get("MA60", np.nan) >= row.get("MA60_prev5", np.nan)) if not pd.isna(row.get("MA60_prev5", np.nan)) else "",
        "信号日突破20日新高": bool(close >= row.get("High_20", np.inf)) if not pd.isna(row.get("High_20", np.nan)) else "",
        "信号日前5日阳线数": int((recent_5["收盘"] > recent_5["开盘"]).sum()) if not recent_5.empty else 0,
    }

def build_execution_snapshot(df, buy_date, prev_close, market_context):
    row = df.loc[buy_date]
    state = market_context.get(buy_date, {}) if market_context else {}
    open_price = safe_float(row.get("开盘"))
    ma20 = safe_float(row.get("MA20"))
    buy_gap = open_price / prev_close - 1 if prev_close and prev_close > 0 else np.nan
    open_distance_ma20 = open_price / ma20 - 1 if ma20 and ma20 > 0 else np.nan
    return {
        "买入日市场环境": state.get("regime", ""),
        "买入日市场MA20宽度": state.get("ma20_ratio", np.nan),
        "买入日市场MA60宽度": state.get("ma60_ratio", np.nan),
        "买入日开盘跳空": buy_gap,
        "买入日开盘距MA20": open_distance_ma20,
    }

def get_original_plan_open(df, period_dates, signal_idx):
    first_execute_idx = signal_idx + 1
    if first_execute_idx >= len(period_dates):
        return np.nan
    first_execute_date = period_dates[first_execute_idx]
    if first_execute_date not in df.index:
        return np.nan
    return safe_float(df.loc[first_execute_date].get("开盘"))

def should_trigger_weak_holding_exit(pos, return_rate, regime):
    if not CONFIG.get("ENABLE_WEAK_HOLDING_EXIT", False) or regime != "弱":
        return False

    if CONFIG.get("WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY", True):
        signal_regime = pos.get("entry_snapshot", {}).get("信号日市场环境")
        if signal_regime == "弱":
            return False

    weak_days = pos.get("weak_regime_days", 0)
    required_days = CONFIG.get("WEAK_HOLDING_EXIT_DAYS", 0)
    max_return = CONFIG.get("WEAK_HOLDING_EXIT_MAX_RETURN")
    if weak_days < required_days:
        return False
    if max_return is not None and return_rate > max_return:
        return False
    return True

def is_ma20_breakdown(df, current_date, regime):
    confirm_days = CONFIG.get("BREAKDOWN_CONFIRM_DAYS", 2)
    if regime == "强" and CONFIG.get("STRONG_BREAKDOWN_CONFIRM_DAYS") is not None:
        confirm_days = CONFIG["STRONG_BREAKDOWN_CONFIRM_DAYS"]
    if regime == "弱" and CONFIG.get("WEAK_BREAKDOWN_CONFIRM_DAYS") is not None:
        confirm_days = CONFIG["WEAK_BREAKDOWN_CONFIRM_DAYS"]

    if confirm_days <= 0:
        return False

    history = df.loc[:current_date].iloc[:-1].tail(confirm_days)
    if len(history) < confirm_days:
        return False
    return bool((history["收盘"] < history["MA20"]).all())

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
            df["MA20_prev5"] = df["MA20"].shift(5)
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

def calculate_portfolio_market_value(portfolio, market_data, current_date, column="收盘"):
    total = 0.0
    for symbol, pos in portfolio.items():
        price = get_latest_price(market_data[symbol], current_date, column)
        if price is not None:
            total += pos["shares"] * price
    return total

def build_candidate_watch_record(symbol, score, rank_score, prev_close, signal_snapshot, current_date, market_data, stock_pool, market_context, portfolio_size, holding_limit):
    if symbol not in market_data or current_date not in market_data[symbol].index:
        return None

    df = market_data[symbol]
    row = df.loc[current_date]
    ideal_price = safe_float(row.get("开盘"))
    if pd.isna(ideal_price) or ideal_price <= 0:
        return None

    entry_price = ideal_price * (1 + CONFIG["SLIPPAGE_RATE"])
    buy_gap = ideal_price / prev_close - 1 if prev_close and prev_close > 0 else np.nan
    state = market_context.get(current_date, {}) if market_context else {}
    record = {
        "代码": str(symbol).zfill(6),
        "名称": stock_pool.get(symbol, "未知"),
        "信号日": signal_snapshot.get("信号日", ""),
        "计划买入日": current_date.strftime("%Y-%m-%d"),
        "信号日市场环境": signal_snapshot.get("信号日市场环境", ""),
        "计划买入日市场环境": state.get("regime", ""),
        "买入分数": score,
        "排序分": round(rank_score, 2),
        "信号日收盘": prev_close,
        "计划买入开盘": ideal_price,
        "计划买入执行价": entry_price,
        "计划买入开盘跳空": buy_gap,
        "若非满仓也会高开跳过": bool(buy_gap > CONFIG["MAX_BUY_GAP_RATE"]) if not pd.isna(buy_gap) else "",
        "跳过原因": "持仓上限",
        "当时持仓数量": portfolio_size,
        "当时持仓上限": holding_limit,
        **signal_snapshot,
    }

    try:
        loc = df.index.get_loc(current_date)
        if not isinstance(loc, (int, np.integer)):
            return record
    except KeyError:
        return record

    horizons = CONFIG.get("CANDIDATE_WATCH_HORIZONS", [5, 10, 20])
    for horizon in horizons:
        future_idx = loc + int(horizon)
        date_col = f"未来{horizon}日日期"
        close_col = f"未来{horizon}日收盘"
        ret_col = f"未来{horizon}日收益率"
        if future_idx < len(df):
            future_row = df.iloc[future_idx]
            record[date_col] = future_row.name.strftime("%Y-%m-%d")
            record[close_col] = safe_float(future_row.get("收盘"))
            record[ret_col] = record[close_col] / entry_price - 1 if entry_price > 0 else np.nan
        else:
            record[date_col] = ""
            record[close_col] = np.nan
            record[ret_col] = np.nan

    max_horizon = max(int(h) for h in horizons) if horizons else 20
    future_window = df.iloc[loc + 1: loc + max_horizon + 1]
    if not future_window.empty:
        record[f"未来{max_horizon}日最大涨幅"] = safe_float(future_window["最高"].max()) / entry_price - 1
        record[f"未来{max_horizon}日最大跌幅"] = safe_float(future_window["最低"].min()) / entry_price - 1
    else:
        record[f"未来{max_horizon}日最大涨幅"] = np.nan
        record[f"未来{max_horizon}日最大跌幅"] = np.nan

    return record

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

def build_output_bundle(best_params, stock_count, run_stamp=None, group_prefix=None, scenario_id=None):
    board_mode = CONFIG["TARGET_BOARD"]
    board_name = get_board_profile(board_mode)["name"]
    param_slug = build_param_slug(best_params)
    sample_limit = CONFIG.get("MAX_STOCKS_PER_BOARD")
    sample_slug = f"抽样{sample_limit}只" if sample_limit is not None else "全量"
    stock_slug = f"实际{stock_count}只"
    run_stamp = run_stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    train_slug = f"训练{CONFIG['TRAIN_START'][:4]}-{CONFIG['TRAIN_END'][:4]}"
    test_slug = f"盲测{CONFIG['TEST_START'][:4]}-{CONFIG['TEST_END'][:4]}"

    run_dir_prefix = f"{group_prefix}_" if group_prefix else ""
    run_dir_name = f"{run_dir_prefix}{run_stamp}_{sample_slug}_{stock_slug}_{train_slug}_{test_slug}"
    output_dir = os.path.join(CONFIG["OUTPUT_ROOT"], board_mode, param_slug, run_dir_name)
    if scenario_id:
        output_dir = os.path.join(output_dir, scenario_id)
    os.makedirs(output_dir, exist_ok=True)

    scenario_suffix = f"_{scenario_id}" if scenario_id else ""
    base_name = f"{board_name}_{sample_slug}_{stock_slug}_{train_slug}_{test_slug}_{run_stamp}{scenario_suffix}"
    return output_dir, {
        "trade_history": os.path.join(output_dir, f"BlindTest_Trade_History_{base_name}.csv"),
        "candidate_watch": os.path.join(output_dir, f"BlindTest_Candidate_Watch_{base_name}.csv"),
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
    if pd.isna(value):
        return '<td class="" data-sort=""></td>'

    raw_value = value
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

def build_yearly_diagnostic_stats(equity_df):
    required_cols = {"股票仓位", "持仓数量", "当日信号数", "当日买入数"}
    if equity_df.empty or not required_cols.issubset(equity_df.columns):
        return pd.DataFrame()

    df = equity_df.copy().reset_index()
    df["日期"] = pd.to_datetime(df["日期"])
    df["年份"] = df["日期"].dt.year

    rows = []
    for year, group in df.groupby("年份"):
        trading_days = len(group)
        empty_days = int((group["持仓数量"] == 0).sum())
        high_gap_skips = int(group["高开跳过数"].sum()) if "高开跳过数" in group.columns else 0
        delayed_price_skips = int(group["延迟价格放弃数"].sum()) if "延迟价格放弃数" in group.columns else 0
        cash_skips = int(group["资金不足跳过数"].sum()) if "资金不足跳过数" in group.columns else 0
        holding_limit_skips = int(group["持仓上限跳过数"].sum()) if "持仓上限跳过数" in group.columns else 0
        risk_pause_days = int(group["风控暂停"].sum()) if "风控暂停" in group.columns else 0
        rows.append({
            "年份": year,
            "交易日数": trading_days,
            "平均股票仓位": group["股票仓位"].mean(),
            "平均持仓数": group["持仓数量"].mean(),
            "空仓天数": empty_days,
            "空仓占比": empty_days / trading_days if trading_days else 0,
            "信号天数": int((group["当日信号数"] > 0).sum()),
            "信号总数": int(group["当日信号数"].sum()),
            "买入总数": int(group["当日买入数"].sum()),
            "高开跳过": high_gap_skips,
            "延迟价格放弃": delayed_price_skips,
            "资金不足跳过": cash_skips,
            "持仓上限跳过": holding_limit_skips,
            "风控暂停天数": risk_pause_days,
        })
    return pd.DataFrame(rows)

def build_regime_diagnostic_stats(equity_df):
    required_cols = {"市场环境", "总权益", "股票仓位", "持仓数量", "当日信号数", "当日买入数"}
    if equity_df.empty or not required_cols.issubset(equity_df.columns):
        return pd.DataFrame()

    df = equity_df.copy().reset_index()
    df["日盈亏"] = df["总权益"].diff().fillna(0)
    rows = []
    for regime, group in df.groupby("市场环境"):
        trading_days = len(group)
        empty_days = int((group["持仓数量"] == 0).sum())
        high_gap_skips = int(group["高开跳过数"].sum()) if "高开跳过数" in group.columns else 0
        delayed_price_skips = int(group["延迟价格放弃数"].sum()) if "延迟价格放弃数" in group.columns else 0
        cash_skips = int(group["资金不足跳过数"].sum()) if "资金不足跳过数" in group.columns else 0
        holding_limit_skips = int(group["持仓上限跳过数"].sum()) if "持仓上限跳过数" in group.columns else 0
        risk_pause_days = int(group["风控暂停"].sum()) if "风控暂停" in group.columns else 0
        rows.append({
            "市场环境": regime,
            "交易日数": trading_days,
            "盈亏贡献": group["日盈亏"].sum(),
            "平均股票仓位": group["股票仓位"].mean(),
            "平均持仓数": group["持仓数量"].mean(),
            "空仓天数": empty_days,
            "空仓占比": empty_days / trading_days if trading_days else 0,
            "信号总数": int(group["当日信号数"].sum()),
            "买入总数": int(group["当日买入数"].sum()),
            "高开跳过": high_gap_skips,
            "延迟价格放弃": delayed_price_skips,
            "资金不足跳过": cash_skips,
            "持仓上限跳过": holding_limit_skips,
            "风控暂停天数": risk_pause_days,
        })
    order = {"强": 0, "中": 1, "弱": 2, "关闭": 3}
    return pd.DataFrame(rows).sort_values("市场环境", key=lambda s: s.map(order).fillna(9))

def build_reason_stats(trade_df):
    if trade_df.empty:
        return pd.DataFrame()
    return trade_df.groupby("卖出原因").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        平均盈亏=("单笔净利", "mean"),
    ).reset_index().sort_values("盈亏合计")

def get_weak_signal_trades(trade_df):
    if trade_df.empty or "信号日市场环境" not in trade_df.columns:
        return pd.DataFrame()
    return trade_df[trade_df["信号日市场环境"] == "弱"].copy()

def build_weak_month_stats(trade_df):
    weak_df = get_weak_signal_trades(trade_df)
    if weak_df.empty or "买入月份" not in weak_df.columns:
        return pd.DataFrame()
    result = weak_df.groupby("买入月份").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均买入分数=("买入分数", "mean"),
        平均信号日量比=("信号日量比", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
    ).reset_index().sort_values("盈亏合计")
    return result

def build_weak_reason_stats(trade_df):
    weak_df = get_weak_signal_trades(trade_df)
    if weak_df.empty:
        return pd.DataFrame()
    return weak_df.groupby("卖出原因").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均持仓天数=("持仓天数", "mean"),
        平均买入分数=("买入分数", "mean"),
        平均信号日量比=("信号日量比", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
    ).reset_index().sort_values("盈亏合计")

def build_weak_score_bucket_stats(trade_df):
    weak_df = get_weak_signal_trades(trade_df)
    if weak_df.empty or "买入分数" not in weak_df.columns:
        return pd.DataFrame()
    df = weak_df.copy()
    df["买入分数"] = pd.to_numeric(df["买入分数"], errors="coerce")
    df["买入分数区间"] = pd.cut(
        df["买入分数"],
        bins=[-np.inf, 79, 84, np.inf],
        labels=["78-79", "80-84", "85+"],
        right=True,
    )
    return df.groupby("买入分数区间", observed=True).agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均信号日量比=("信号日量比", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
        平均信号日RSI14=("信号日RSI14", "mean"),
    ).reset_index()

def build_weak_feature_compare(trade_df):
    weak_df = get_weak_signal_trades(trade_df)
    if weak_df.empty:
        return pd.DataFrame()
    df = weak_df.copy()
    df["盈亏分组"] = np.where(df["单笔净利"] > 0, "盈利交易", "亏损交易")
    return df.groupby("盈亏分组").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均持仓天数=("持仓天数", "mean"),
        平均买入分数=("买入分数", "mean"),
        平均排序分=("排序分", "mean"),
        平均信号日市场MA20宽度=("信号日市场MA20宽度", "mean"),
        平均信号日市场MA60宽度=("信号日市场MA60宽度", "mean"),
        平均信号日RSI14=("信号日RSI14", "mean"),
        平均信号日量比=("信号日量比", "mean"),
        平均信号日20日均成交额=("信号日20日均成交额", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
        平均信号日距MA60=("信号日距MA60", "mean"),
        信号日站上MA60占比=("信号日站上MA60", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        信号日MA60上行占比=("信号日MA60上行", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        信号日突破20日新高占比=("信号日突破20日新高", lambda s: pd.to_numeric(s, errors="coerce").mean()),
    ).reset_index()

def build_weak_stock_stats(trade_df, profit_side=False, limit=20):
    weak_df = get_weak_signal_trades(trade_df)
    if weak_df.empty:
        return pd.DataFrame()
    grouped = weak_df.groupby(["代码", "名称"]).agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
    ).reset_index()
    return grouped.sort_values("盈亏合计", ascending=not profit_side).head(limit)

def get_transition_weak_trades(trade_df):
    if trade_df.empty or "信号日市场环境" not in trade_df.columns:
        return pd.DataFrame()

    df = trade_df.copy()
    signal_regime = df["信号日市场环境"].fillna("")
    sell_regime = df["卖出日市场环境"].fillna("") if "卖出日市场环境" in df.columns else ""
    if "累计弱市持仓天数" in df.columns:
        weak_days = pd.to_numeric(df["累计弱市持仓天数"], errors="coerce").fillna(0)
    elif "卖出时连续弱市持仓天数" in df.columns:
        weak_days = pd.to_numeric(df["卖出时连续弱市持仓天数"], errors="coerce").fillna(0)
        df["累计弱市持仓天数"] = weak_days
    else:
        weak_days = pd.Series(0, index=df.index)
        df["累计弱市持仓天数"] = weak_days

    if "最大连续弱市持仓天数" not in df.columns:
        df["最大连续弱市持仓天数"] = weak_days

    return df[(signal_regime != "弱") & ((weak_days > 0) | (sell_regime == "弱"))].copy()

def build_transition_weak_reason_stats(trade_df):
    transition_df = get_transition_weak_trades(trade_df)
    if transition_df.empty:
        return pd.DataFrame()
    return transition_df.groupby(["信号日市场环境", "卖出原因"]).agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均持仓天数=("持仓天数", "mean"),
        平均累计弱市持仓天数=("累计弱市持仓天数", "mean"),
        平均最大连续弱市持仓天数=("最大连续弱市持仓天数", "mean"),
    ).reset_index().sort_values("盈亏合计")

def build_transition_weak_month_stats(trade_df):
    transition_df = get_transition_weak_trades(trade_df)
    if transition_df.empty or "买入月份" not in transition_df.columns:
        return pd.DataFrame()
    return transition_df.groupby("买入月份").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均买入分数=("买入分数", "mean"),
        平均信号日市场MA20宽度=("信号日市场MA20宽度", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
        平均累计弱市持仓天数=("累计弱市持仓天数", "mean"),
    ).reset_index().sort_values("盈亏合计")

def build_transition_weak_feature_compare(trade_df):
    transition_df = get_transition_weak_trades(trade_df)
    if transition_df.empty:
        return pd.DataFrame()
    df = transition_df.copy()
    df["盈亏分组"] = np.where(df["单笔净利"] > 0, "盈利交易", "亏损交易")
    return df.groupby("盈亏分组").agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均持仓天数=("持仓天数", "mean"),
        平均买入分数=("买入分数", "mean"),
        平均信号日市场MA20宽度=("信号日市场MA20宽度", "mean"),
        平均信号日市场MA60宽度=("信号日市场MA60宽度", "mean"),
        平均信号日量比=("信号日量比", "mean"),
        平均信号日距MA20=("信号日距MA20", "mean"),
        平均信号日距MA60=("信号日距MA60", "mean"),
        平均累计弱市持仓天数=("累计弱市持仓天数", "mean"),
        平均最大连续弱市持仓天数=("最大连续弱市持仓天数", "mean"),
        信号日站上MA60占比=("信号日站上MA60", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        信号日MA60上行占比=("信号日MA60上行", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        信号日突破20日新高占比=("信号日突破20日新高", lambda s: pd.to_numeric(s, errors="coerce").mean()),
    ).reset_index()

def build_transition_weak_stock_stats(trade_df, profit_side=False, limit=20):
    transition_df = get_transition_weak_trades(trade_df)
    if transition_df.empty:
        return pd.DataFrame()
    grouped = transition_df.groupby(["代码", "名称"]).agg(
        交易次数=("单笔净利", "size"),
        盈亏合计=("单笔净利", "sum"),
        胜率=("单笔净利", lambda s: (s > 0).mean()),
        平均单笔盈亏=("单笔净利", "mean"),
        平均盈亏率=("盈亏率", "mean"),
        平均累计弱市持仓天数=("累计弱市持仓天数", "mean"),
    ).reset_index()
    return grouped.sort_values("盈亏合计", ascending=not profit_side).head(limit)

def get_candidate_return_columns(candidate_watch_df):
    if candidate_watch_df is None or candidate_watch_df.empty:
        return []
    return [col for col in candidate_watch_df.columns if col.startswith("未来") and col.endswith("日收益率")]

def build_candidate_watch_overview(candidate_watch_df):
    if candidate_watch_df is None or candidate_watch_df.empty:
        return pd.DataFrame()

    df = candidate_watch_df.copy()
    for col in ["若非满仓也会高开跳过", "买入分数", "排序分", *get_candidate_return_columns(df)]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    rows = [{
        "候选跟踪数": len(df),
        "高开超限数": int(df["若非满仓也会高开跳过"].fillna(0).sum()) if "若非满仓也会高开跳过" in df.columns else 0,
        "高开超限占比": df["若非满仓也会高开跳过"].fillna(0).mean() if "若非满仓也会高开跳过" in df.columns else 0,
        "平均买入分数": df["买入分数"].mean() if "买入分数" in df.columns else np.nan,
        "平均排序分": df["排序分"].mean() if "排序分" in df.columns else np.nan,
    }]

    for col in get_candidate_return_columns(df):
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if values.empty:
            continue
        prefix = col.replace("收益率", "")
        rows[0][f"{prefix}平均收益率"] = values.mean()
        rows[0][f"{prefix}中位收益率"] = values.median()
        rows[0][f"{prefix}胜率"] = (values > 0).mean()
    return pd.DataFrame(rows)

def build_candidate_watch_regime_stats(candidate_watch_df):
    if candidate_watch_df is None or candidate_watch_df.empty:
        return pd.DataFrame()

    df = candidate_watch_df.copy()
    for col in ["若非满仓也会高开跳过", "买入分数", "排序分", *get_candidate_return_columns(df)]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    group_cols = [col for col in ["信号日市场环境", "计划买入日市场环境"] if col in df.columns]
    if not group_cols:
        return pd.DataFrame()

    named_aggs = {
        "候选跟踪数": ("代码", "size"),
        "高开超限占比": ("若非满仓也会高开跳过", lambda s: s.fillna(0).mean()),
        "平均买入分数": ("买入分数", "mean"),
        "平均排序分": ("排序分", "mean"),
    }
    for col in get_candidate_return_columns(df):
        prefix = col.replace("收益率", "")
        named_aggs[f"{prefix}平均收益率"] = (col, "mean")
        named_aggs[f"{prefix}胜率"] = (col, lambda s: (s > 0).mean())

    return df.groupby(group_cols).agg(**named_aggs).reset_index().sort_values("候选跟踪数", ascending=False)

def build_candidate_watch_score_bucket_stats(candidate_watch_df):
    if candidate_watch_df is None or candidate_watch_df.empty or "买入分数" not in candidate_watch_df.columns:
        return pd.DataFrame()

    df = candidate_watch_df.copy()
    df["买入分数"] = pd.to_numeric(df["买入分数"], errors="coerce")
    for col in ["若非满仓也会高开跳过", "排序分", *get_candidate_return_columns(df)]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["买入分数区间"] = pd.cut(
        df["买入分数"],
        bins=[-np.inf, 74, 79, 84, np.inf],
        labels=["70-74", "75-79", "80-84", "85+"],
        right=True,
    )
    named_aggs = {
        "候选跟踪数": ("代码", "size"),
        "高开超限占比": ("若非满仓也会高开跳过", lambda s: s.fillna(0).mean()),
        "平均排序分": ("排序分", "mean"),
    }
    for col in get_candidate_return_columns(df):
        prefix = col.replace("收益率", "")
        named_aggs[f"{prefix}平均收益率"] = (col, "mean")
        named_aggs[f"{prefix}胜率"] = (col, lambda s: (s > 0).mean())
    return df.groupby("买入分数区间", observed=True).agg(**named_aggs).reset_index()

def select_candidate_watch_columns(df, sort_col):
    preferred_cols = [
        "代码", "名称", "信号日", "计划买入日", "信号日市场环境", "计划买入日市场环境",
        "买入分数", "排序分", "计划买入开盘跳空", "若非满仓也会高开跳过",
        "未来5日收益率", "未来10日收益率", "未来20日收益率", "未来20日最大涨幅", "未来20日最大跌幅",
    ]
    cols = [col for col in preferred_cols if col in df.columns]
    if sort_col in df.columns and sort_col not in cols:
        cols.append(sort_col)
    return cols

def build_candidate_watch_top_stats(candidate_watch_df, profit_side=True, limit=50):
    if candidate_watch_df is None or candidate_watch_df.empty:
        return pd.DataFrame()

    df = candidate_watch_df.copy()
    sort_col = "未来10日收益率" if "未来10日收益率" in df.columns else None
    if sort_col is None:
        return_cols = get_candidate_return_columns(df)
        sort_col = return_cols[0] if return_cols else None
    if sort_col is None:
        return pd.DataFrame()

    df[sort_col] = pd.to_numeric(df[sort_col], errors="coerce")
    df = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=not profit_side).head(limit)
    return df[select_candidate_watch_columns(df, sort_col)]

def generate_html_report(output_path, trade_df, equity_df, summary, candidate_watch_df=None):
    summary_df = pd.DataFrame([summary])
    for pct_as_number_col in ["总收益率", "基准总收益率", "超额收益率"]:
        if pct_as_number_col in summary_df.columns:
            summary_df[pct_as_number_col] = summary_df[pct_as_number_col].astype(float) / 100
    yearly_trade_df = build_yearly_trade_stats(trade_df)
    yearly_equity_df = build_yearly_equity_stats(equity_df)
    yearly_diagnostic_df = build_yearly_diagnostic_stats(equity_df)
    regime_diagnostic_df = build_regime_diagnostic_stats(equity_df)
    reason_df = build_reason_stats(trade_df)
    weak_month_df = build_weak_month_stats(trade_df)
    weak_reason_df = build_weak_reason_stats(trade_df)
    weak_score_bucket_df = build_weak_score_bucket_stats(trade_df)
    weak_feature_compare_df = build_weak_feature_compare(trade_df)
    weak_loss_stock_df = build_weak_stock_stats(trade_df, profit_side=False)
    weak_profit_stock_df = build_weak_stock_stats(trade_df, profit_side=True)
    transition_weak_reason_df = build_transition_weak_reason_stats(trade_df)
    transition_weak_month_df = build_transition_weak_month_stats(trade_df)
    transition_weak_feature_df = build_transition_weak_feature_compare(trade_df)
    transition_weak_loss_stock_df = build_transition_weak_stock_stats(trade_df, profit_side=False)
    transition_weak_profit_stock_df = build_transition_weak_stock_stats(trade_df, profit_side=True)
    candidate_watch_overview_df = build_candidate_watch_overview(candidate_watch_df)
    candidate_watch_regime_df = build_candidate_watch_regime_stats(candidate_watch_df)
    candidate_watch_score_df = build_candidate_watch_score_bucket_stats(candidate_watch_df)
    candidate_watch_top_df = build_candidate_watch_top_stats(candidate_watch_df, profit_side=True)
    candidate_watch_worst_df = build_candidate_watch_top_stats(candidate_watch_df, profit_side=False)

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
        "盈亏贡献", "平均信号日20日均成交额", "平均单笔盈亏",
    }
    pct_cols = {
        "总收益率", "基准总收益率", "超额收益率", "最大回撤", "基准最大回撤",
        "胜率", "年度收益率", "年度最大回撤", "盈亏率", "平均盈亏率", "平均股票仓位", "空仓占比",
        "最大入场偏离MA20", "回撤止盈启动收益", "回撤止盈回撤比例",
        "转弱持仓退出最高收益",
        "信号日市场MA20宽度", "信号日市场MA60宽度", "信号日市场MA60上行宽度",
        "信号日距MA20", "信号日距MA60", "买入日市场MA20宽度", "买入日市场MA60宽度",
        "买入日开盘跳空", "买入日开盘距MA20",
        "计划买入开盘跳空", "高开超限占比",
        "未来5日收益率", "未来10日收益率", "未来20日收益率", "未来20日最大涨幅", "未来20日最大跌幅",
        "未来5日平均收益率", "未来10日平均收益率", "未来20日平均收益率",
        "未来5日中位收益率", "未来10日中位收益率", "未来20日中位收益率",
        "未来5日胜率", "未来10日胜率", "未来20日胜率",
        "平均信号日市场MA20宽度", "平均信号日市场MA60宽度",
        "平均信号日距MA20", "平均信号日距MA60",
        "信号日站上MA60占比", "信号日MA60上行占比", "信号日突破20日新高占比",
    }

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
    <div class="metric"><div class="label">平均股票仓位</div><div class="value">{summary.get('平均股票仓位', 0) * 100:.2f}%</div></div>
    <div class="metric"><div class="label">空仓占比</div><div class="value">{summary.get('空仓占比', 0) * 100:.2f}%</div></div>
    <div class="metric"><div class="label">扫描信号数</div><div class="value">{summary.get('扫描信号总数', 0)}</div></div>
    <div class="metric"><div class="label">实际买入数</div><div class="value">{summary.get('实际买入次数', 0)}</div></div>
  </div>

  <h2>年度权益表现</h2>
  {dataframe_to_html_table(yearly_equity_df, "yearly-equity", kind_map(yearly_equity_df))}

  <h2>年度已实现盈亏</h2>
  {dataframe_to_html_table(yearly_trade_df, "yearly-trade", kind_map(yearly_trade_df))}

  <h2>年度策略诊断</h2>
  {dataframe_to_html_table(yearly_diagnostic_df, "yearly-diagnostic", kind_map(yearly_diagnostic_df))}

  <h2>市场环境诊断</h2>
  {dataframe_to_html_table(regime_diagnostic_df, "regime-diagnostic", kind_map(regime_diagnostic_df))}

  <h2>卖出原因统计</h2>
  {dataframe_to_html_table(reason_df, "reason-stats", kind_map(reason_df))}

  <h2>弱市买入月份诊断</h2>
  {dataframe_to_html_table(weak_month_df, "weak-month-stats", kind_map(weak_month_df))}

  <h2>弱市卖出原因诊断</h2>
  {dataframe_to_html_table(weak_reason_df, "weak-reason-stats", kind_map(weak_reason_df))}

  <h2>弱市买入分数区间诊断</h2>
  {dataframe_to_html_table(weak_score_bucket_df, "weak-score-stats", kind_map(weak_score_bucket_df))}

  <h2>弱市盈利组 vs 亏损组</h2>
  {dataframe_to_html_table(weak_feature_compare_df, "weak-feature-compare", kind_map(weak_feature_compare_df))}

  <h2>弱市亏损股票 Top20</h2>
  {dataframe_to_html_table(weak_loss_stock_df, "weak-loss-stocks", kind_map(weak_loss_stock_df))}

  <h2>弱市盈利股票 Top20</h2>
  {dataframe_to_html_table(weak_profit_stock_df, "weak-profit-stocks", kind_map(weak_profit_stock_df))}

  <h2>非弱市入场后经历弱市：卖出原因诊断</h2>
  {dataframe_to_html_table(transition_weak_reason_df, "transition-weak-reason-stats", kind_map(transition_weak_reason_df))}

  <h2>非弱市入场后经历弱市：买入月份诊断</h2>
  {dataframe_to_html_table(transition_weak_month_df, "transition-weak-month-stats", kind_map(transition_weak_month_df))}

  <h2>非弱市入场后经历弱市：盈利组 vs 亏损组</h2>
  {dataframe_to_html_table(transition_weak_feature_df, "transition-weak-feature-compare", kind_map(transition_weak_feature_df))}

  <h2>非弱市入场后经历弱市：亏损股票 Top20</h2>
  {dataframe_to_html_table(transition_weak_loss_stock_df, "transition-weak-loss-stocks", kind_map(transition_weak_loss_stock_df))}

  <h2>非弱市入场后经历弱市：盈利股票 Top20</h2>
  {dataframe_to_html_table(transition_weak_profit_stock_df, "transition-weak-profit-stocks", kind_map(transition_weak_profit_stock_df))}

  <h2>未买入候选股跟踪：总体</h2>
  {dataframe_to_html_table(candidate_watch_overview_df, "candidate-watch-overview", kind_map(candidate_watch_overview_df))}

  <h2>未买入候选股跟踪：市场环境</h2>
  {dataframe_to_html_table(candidate_watch_regime_df, "candidate-watch-regime", kind_map(candidate_watch_regime_df))}

  <h2>未买入候选股跟踪：分数区间</h2>
  {dataframe_to_html_table(candidate_watch_score_df, "candidate-watch-score", kind_map(candidate_watch_score_df))}

  <h2>未买入候选股：未来10日最强 Top50</h2>
  {dataframe_to_html_table(candidate_watch_top_df, "candidate-watch-top", kind_map(candidate_watch_top_df))}

  <h2>未买入候选股：未来10日最弱 Top50</h2>
  {dataframe_to_html_table(candidate_watch_worst_df, "candidate-watch-worst", kind_map(candidate_watch_worst_df))}

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

def apply_config_overrides(overrides):
    previous_values = {}
    for key, value in overrides.items():
        previous_values[key] = CONFIG.get(key)
        CONFIG[key] = value
    return previous_values

def restore_config_overrides(previous_values):
    for key, value in previous_values.items():
        CONFIG[key] = value

def build_blind_summary(blind_res, benchmark_kpi, best_params, stock_count, scenario=None):
    board_profile = get_board_profile()
    trade_df = blind_res["交易明细"]
    equity_df = blind_res["权益曲线"]
    candidate_watch_df = blind_res.get("候选跟踪", pd.DataFrame())
    risk_stats = blind_res["风控统计"]

    initial_capital = CONFIG["INITIAL_CAPITAL"]
    final_equity = equity_df["总权益"].iloc[-1] if not equity_df.empty else initial_capital
    realized_profit = trade_df["单笔净利"].sum() if not trade_df.empty else 0.0
    unrealized_profit = final_equity - initial_capital - realized_profit
    total_profit = final_equity - initial_capital
    total_return_pct = (total_profit / initial_capital) * 100
    benchmark_return_pct = benchmark_kpi["总收益"] * 100
    excess_return_pct = total_return_pct - benchmark_return_pct
    avg_stock_position = equity_df["股票仓位"].mean() if "股票仓位" in equity_df.columns and not equity_df.empty else 0
    avg_holding_count = equity_df["持仓数量"].mean() if "持仓数量" in equity_df.columns and not equity_df.empty else 0
    empty_position_days = int((equity_df["持仓数量"] == 0).sum()) if "持仓数量" in equity_df.columns and not equity_df.empty else 0
    empty_position_ratio = empty_position_days / len(equity_df) if not equity_df.empty else 0
    signal_total = int(equity_df["当日信号数"].sum()) if "当日信号数" in equity_df.columns and not equity_df.empty else 0
    executed_buy_total = int(equity_df["当日买入数"].sum()) if "当日买入数" in equity_df.columns and not equity_df.empty else 0
    candidate_watch_total = len(candidate_watch_df) if candidate_watch_df is not None and not candidate_watch_df.empty else 0

    summary = {
        "运行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "板块": CONFIG["TARGET_BOARD"],
        "板块名称": board_profile["name"],
        "抽样上限": CONFIG.get("MAX_STOCKS_PER_BOARD") if CONFIG.get("MAX_STOCKS_PER_BOARD") is not None else "全部",
        "抽样种子": CONFIG.get("POOL_SAMPLE_SEED", ""),
        "实际股票数量": stock_count,
        "训练开始": CONFIG["TRAIN_START"],
        "训练结束": CONFIG["TRAIN_END"],
        "盲测开始": CONFIG["TEST_START"],
        "盲测结束": CONFIG["TEST_END"],
        "参数标识": build_param_slug(best_params),
        "最优参数": str(best_params),
        "消融场景ID": scenario.get("id", "") if scenario else "",
        "消融场景": scenario.get("name", "") if scenario else "",
        "消融说明": scenario.get("description", "") if scenario else "",
        "滑点率": CONFIG["SLIPPAGE_RATE"],
        "佣金率": CONFIG["COMMISSION_RATE"],
        "印花税率": CONFIG["TAX_RATE"],
        "买入执行延迟交易日": CONFIG["BUY_EXECUTION_DELAY_DAYS"],
        "卖出执行延迟交易日": CONFIG["SELL_EXECUTION_DELAY_DAYS"],
        "延迟买入复核": CONFIG["REVALIDATE_DELAYED_BUY_SIGNAL"],
        "延迟买入信号收盘涨幅上限": CONFIG["MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE"],
        "延迟买入原计划开盘涨幅上限": CONFIG["MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN"],
        "延迟买入要求站上MA20": CONFIG["REQUIRE_DELAYED_BUY_ABOVE_MA20"],
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
        "平均股票仓位": avg_stock_position,
        "平均持仓数": avg_holding_count,
        "空仓天数": empty_position_days,
        "空仓占比": empty_position_ratio,
        "扫描信号总数": signal_total,
        "实际买入次数": executed_buy_total,
        "未买入候选跟踪数": candidate_watch_total,
        "高开跳过次数": risk_stats["高开跳过次数"],
        "买入复核放弃次数": risk_stats["买入复核放弃次数"],
        "延迟价格放弃次数": risk_stats["延迟价格放弃次数"],
        "资金不足跳过次数": risk_stats["资金不足跳过次数"],
        "持仓上限跳过次数": risk_stats["持仓上限跳过次数"],
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
        "破位确认天数": CONFIG["BREAKDOWN_CONFIRM_DAYS"],
        "强市破位确认天数": CONFIG["STRONG_BREAKDOWN_CONFIRM_DAYS"],
        "弱市破位确认天数": CONFIG["WEAK_BREAKDOWN_CONFIRM_DAYS"],
        "启用转弱持仓退出": CONFIG["ENABLE_WEAK_HOLDING_EXIT"],
        "转弱持仓退出天数": CONFIG["WEAK_HOLDING_EXIT_DAYS"],
        "转弱持仓退出最高收益": CONFIG["WEAK_HOLDING_EXIT_MAX_RETURN"],
        "仅处理非弱市入场持仓": CONFIG["WEAK_HOLDING_EXIT_ONLY_NON_WEAK_ENTRY"],
        "回撤止盈启动收益": CONFIG["TRAIL_PROFIT_TRIGGER"],
        "回撤止盈回撤比例": CONFIG["TRAIL_DRAWDOWN_RATE"],
        "启用亢奋止盈": CONFIG["ENABLE_EXCITEMENT_TAKE_PROFIT"],
        "启用市场环境分级": CONFIG["ENABLE_MARKET_REGIME"],
        "强市MA20宽度阈值": CONFIG["STRONG_BREADTH_MA20"],
        "强市MA60宽度阈值": CONFIG["STRONG_BREADTH_MA60"],
        "强市最大持仓覆盖": CONFIG["STRONG_MAX_HOLDINGS"],
        "强市单票仓位覆盖": CONFIG["STRONG_POSITION_PER_STOCK"],
        "启用候选排序": CONFIG["ENABLE_CANDIDATE_RANKING"],
        "候选排序适用环境": str(CONFIG["CANDIDATE_RANKING_REGIMES"]),
        "排序原始分档": CONFIG["RANK_PRIMARY_SCORE_BAND"],
        "最大入场偏离MA20": CONFIG["MAX_ENTRY_DISTANCE_MA20"],
        "强市最大入场偏离MA20": CONFIG["STRONG_MAX_ENTRY_DISTANCE_MA20"],
        "强市最高量比": CONFIG["STRONG_MAX_ENTRY_VOLUME_RATIO"],
        "排序趋势权重": CONFIG["RANK_WEIGHT_TREND"],
        "排序流动性权重": CONFIG["RANK_WEIGHT_LIQUIDITY"],
        "排序突破权重": CONFIG["RANK_WEIGHT_BREAKOUT"],
        "排序RSI权重": CONFIG["RANK_WEIGHT_RSI"],
        "排序MA20距离权重": CONFIG["RANK_WEIGHT_DISTANCE"],
        "中性允许买入": CONFIG["NEUTRAL_ALLOW_BUY"],
        "中性买入分数加分": CONFIG["NEUTRAL_BUY_SCORE_OFFSET"],
        "中性MA20宽度阈值": CONFIG["NEUTRAL_BREADTH_MA20"],
        "中性MA60宽度阈值": CONFIG["NEUTRAL_BREADTH_MA60"],
        "中性最大持仓数": CONFIG["NEUTRAL_MAX_HOLDINGS"],
        "中性单票仓位倍率": CONFIG["NEUTRAL_POSITION_MULTIPLIER"],
        "弱市允许高分买入": CONFIG["WEAK_ALLOW_HIGH_SCORE_BUY"],
        "弱市买入分数门槛": CONFIG["WEAK_BUY_SCORE_THRESHOLD"],
        "弱市最大持仓数": CONFIG["WEAK_MAX_HOLDINGS"],
        "弱市单票仓位倍率": CONFIG["WEAK_POSITION_MULTIPLIER"],
        "弱市专用止损阈值": CONFIG["WEAK_STOP_LOSS_RATE"],
        "连续亏损暂停触发笔数": CONFIG["LOSS_COOLDOWN_TRIGGER"],
        "连续亏损暂停天数": CONFIG["LOSS_COOLDOWN_DAYS"],
        "账户回撤暂停阈值": CONFIG["MAX_EQUITY_DRAWDOWN_TO_PAUSE"],
        "账户回撤暂停天数": CONFIG["DRAWDOWN_COOLDOWN_DAYS"],
    }
    return summary

def save_blind_outputs(best_params, stock_count, blind_res, benchmark_kpi, scenario=None, run_stamp=None, group_prefix=None):
    output_dir, output_paths = build_output_bundle(
        best_params,
        stock_count,
        run_stamp=run_stamp,
        group_prefix=group_prefix,
        scenario_id=scenario.get("id") if scenario else None,
    )
    trade_df = blind_res["交易明细"]
    equity_df = blind_res["权益曲线"]
    candidate_watch_df = blind_res.get("候选跟踪", pd.DataFrame())
    summary = build_blind_summary(blind_res, benchmark_kpi, best_params, stock_count, scenario)

    if not trade_df.empty:
        trade_df.to_csv(output_paths["trade_history"], index=False, encoding="utf-8-sig")
    if candidate_watch_df is not None and not candidate_watch_df.empty:
        candidate_watch_df.to_csv(output_paths["candidate_watch"], index=False, encoding="utf-8-sig")
    if not equity_df.empty:
        equity_df.to_csv(output_paths["equity_curve"], encoding="utf-8-sig")
    pd.DataFrame([summary]).to_csv(output_paths["summary"], index=False, encoding="utf-8-sig")
    generate_html_report(output_paths["html_report"], trade_df, equity_df, summary, candidate_watch_df)

    return summary, output_dir, output_paths

def print_blind_summary(summary, output_dir, output_paths):
    title_prefix = f"{summary['消融场景']} - " if summary.get("消融场景") else ""
    print("\n" + "="*58)
    print(f"          【{title_prefix}{summary['板块']} - {summary['板块名称']} 盲测期期末权益报告】          ")
    print("="*58)
    print(f"▶ 初始投入本金 : ¥{summary['期初资金']:,.2f}")
    print(f"▶ 期末总权益 : ¥{summary['期末总权益']:,.2f}")
    print(f"▶ 累计已实现盈亏 : ¥{summary['已实现盈亏']:+,.2f} 元")
    print(f"▶ 期末未实现盈亏 : ¥{summary['未实现盈亏']:+,.2f} 元")
    print(f"▶ 盲测期总盈亏 : ¥{summary['总盈亏']:+,.2f} 元")
    print(f"▶ 盲测期总收益率 : {summary['总收益率']:+.2f}%")
    print(f"▶ 基准收益率 : {summary['基准总收益率']:+.2f}% | 超额收益率 : {summary['超额收益率']:+.2f}%")
    print(f"▶ 最大回撤 : {summary['最大回撤']*100:.2f}% | Calmar: {summary['Calmar']:.2f} | Sharpe: {summary['Sharpe']:.2f}")
    print(f"▶ 基准回撤 : {summary['基准最大回撤']*100:.2f}% | 基准Calmar: {summary['基准Calmar']:.2f} | 基准Sharpe: {summary['基准Sharpe']:.2f}")
    print(f"▶ 交易次数 : {summary['交易次数']}")
    print(f"▶ 参与度 : 平均股票仓位 {summary['平均股票仓位']*100:.2f}% | 平均持仓 {summary['平均持仓数']:.2f} 只 | 空仓 {summary['空仓天数']} 天 ({summary['空仓占比']*100:.2f}%)")
    print(f"▶ 信号漏斗 : 扫描信号 {summary['扫描信号总数']} 个 | 实际买入 {summary['实际买入次数']} 次 | 未买入候选跟踪 {summary['未买入候选跟踪数']} 条 | 高开跳过 {summary['高开跳过次数']} 次 | 复核放弃 {summary['买入复核放弃次数']} 次 | 延迟价格放弃 {summary['延迟价格放弃次数']} 次 | 持仓上限跳过 {summary['持仓上限跳过次数']} 次")
    print(f"▶ 风控介入 : 连续亏损暂停 {summary['连续亏损暂停次数']} 次 | 回撤暂停 {summary['回撤暂停次数']} 次 | 暂停开仓 {summary['暂停开仓天数']} 天")
    print(f"▶ 市场分级 : 强 {summary['强市场天数']} 天 | 中 {summary['中性市场天数']} 天 | 弱 {summary['弱市场天数']} 天")
    print(f"▶ 结果目录 : {output_dir}")
    if summary.get("未买入候选跟踪数", 0) > 0 and output_paths.get("candidate_watch"):
        print(f"▶ 候选跟踪 : {output_paths['candidate_watch']}")
    print(f"▶ HTML报告 : {output_paths['html_report']}")
    print("="*58)

def build_ablation_compare_row(scenario, summary, blind_res, output_dir):
    equity_df = blind_res["权益曲线"]
    regime_df = build_regime_diagnostic_stats(equity_df)

    def regime_value(regime, column, default=0):
        if regime_df.empty:
            return default
        rows = regime_df[regime_df["市场环境"] == regime]
        if rows.empty or column not in rows.columns:
            return default
        return rows.iloc[0][column]

    return {
        "场景ID": scenario["id"],
        "场景": scenario["name"],
        "说明": scenario["description"],
        "参数组合": summary["最优参数"],
        "期初资金": summary["期初资金"],
        "滑点率": summary["滑点率"],
        "佣金率": summary["佣金率"],
        "印花税率": summary["印花税率"],
        "买入执行延迟交易日": summary["买入执行延迟交易日"],
        "卖出执行延迟交易日": summary["卖出执行延迟交易日"],
        "延迟买入复核": summary["延迟买入复核"],
        "延迟买入信号收盘涨幅上限": summary["延迟买入信号收盘涨幅上限"],
        "延迟买入原计划开盘涨幅上限": summary["延迟买入原计划开盘涨幅上限"],
        "延迟买入要求站上MA20": summary["延迟买入要求站上MA20"],
        "抽样上限": summary["抽样上限"],
        "抽样种子": summary["抽样种子"],
        "实际股票数量": summary["实际股票数量"],
        "总收益率": summary["总收益率"] / 100,
        "超额收益率": summary["超额收益率"] / 100,
        "最大回撤": summary["最大回撤"],
        "Calmar": summary["Calmar"],
        "Sharpe": summary["Sharpe"],
        "交易次数": summary["交易次数"],
        "平均股票仓位": summary["平均股票仓位"],
        "空仓占比": summary["空仓占比"],
        "启用候选排序": summary["启用候选排序"],
        "候选排序适用环境": summary["候选排序适用环境"],
        "排序原始分档": summary["排序原始分档"],
        "最大入场偏离MA20": summary["最大入场偏离MA20"],
        "强市最大入场偏离MA20": summary["强市最大入场偏离MA20"],
        "强市最高量比": summary["强市最高量比"],
        "排序趋势权重": summary["排序趋势权重"],
        "排序流动性权重": summary["排序流动性权重"],
        "排序突破权重": summary["排序突破权重"],
        "排序RSI权重": summary["排序RSI权重"],
        "排序MA20距离权重": summary["排序MA20距离权重"],
        "破位确认天数": summary["破位确认天数"],
        "强市破位确认天数": summary["强市破位确认天数"],
        "弱市破位确认天数": summary["弱市破位确认天数"],
        "启用转弱持仓退出": summary["启用转弱持仓退出"],
        "转弱持仓退出天数": summary["转弱持仓退出天数"],
        "转弱持仓退出最高收益": summary["转弱持仓退出最高收益"],
        "仅处理非弱市入场持仓": summary["仅处理非弱市入场持仓"],
        "回撤止盈启动收益": summary["回撤止盈启动收益"],
        "回撤止盈回撤比例": summary["回撤止盈回撤比例"],
        "启用亢奋止盈": summary["启用亢奋止盈"],
        "弱市允许高分买入": summary["弱市允许高分买入"],
        "弱市买入分数门槛": summary["弱市买入分数门槛"],
        "弱市最大持仓数": summary["弱市最大持仓数"],
        "弱市单票仓位倍率": summary["弱市单票仓位倍率"],
        "弱市专用止损阈值": summary["弱市专用止损阈值"],
        "扫描信号总数": summary["扫描信号总数"],
        "实际买入次数": summary["实际买入次数"],
        "未买入候选跟踪数": summary["未买入候选跟踪数"],
        "买入复核放弃次数": summary["买入复核放弃次数"],
        "延迟价格放弃次数": summary["延迟价格放弃次数"],
        "持仓上限跳过次数": summary["持仓上限跳过次数"],
        "强市盈亏贡献": regime_value("强", "盈亏贡献"),
        "中性盈亏贡献": regime_value("中", "盈亏贡献"),
        "弱市盈亏贡献": regime_value("弱", "盈亏贡献"),
        "强市平均仓位": regime_value("强", "平均股票仓位"),
        "中性平均仓位": regime_value("中", "平均股票仓位"),
        "弱市平均仓位": regime_value("弱", "平均股票仓位"),
        "结果目录": output_dir,
    }

def generate_ablation_compare_report(output_path, compare_df, title="消融对照测试汇总"):
    money_cols = {"期初资金", "强市盈亏贡献", "中性盈亏贡献", "弱市盈亏贡献"}
    pct_cols = {"滑点率", "佣金率", "印花税率", "总收益率", "超额收益率", "最大回撤", "平均股票仓位", "空仓占比", "最大入场偏离MA20", "强市最大入场偏离MA20", "回撤止盈启动收益", "回撤止盈回撤比例", "弱市单票仓位倍率", "弱市专用止损阈值", "转弱持仓退出最高收益", "延迟买入信号收盘涨幅上限", "延迟买入原计划开盘涨幅上限", "强市平均仓位", "中性平均仓位", "弱市平均仓位"}
    column_kinds = {col: "money" for col in compare_df.columns if col in money_cols}
    column_kinds.update({col: "pct" for col in compare_df.columns if col in pct_cols})
    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 28px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2937; background: #f7f8fa; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; }}
    .subtle {{ color: #6b7280; margin-bottom: 20px; }}
    .table-wrap {{ overflow-x: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #edf0f3; white-space: nowrap; text-align: right; }}
    th {{ position: sticky; top: 0; background: #f3f4f6; color: #374151; }}
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3) {{ text-align: left; }}
    tr:hover td {{ background: #f9fafb; }}
    .pos {{ color: #b91c1c; }}
    .neg {{ color: #047857; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="subtle">生成时间：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))} | 结果目录：{html.escape(os.path.dirname(output_path))}</div>
  {dataframe_to_html_table(compare_df, "ablation-compare", column_kinds)}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

def param_signature(params):
    return tuple((key, params[key]) for key in sorted(params.keys()))

def build_param_recheck_cases(training_results):
    cases = []
    seen = set()

    for item in FIXED_PARAM_RECHECKS:
        params = dict(item["params"])
        signature = param_signature(params)
        if signature in seen:
            continue
        seen.add(signature)
        cases.append({
            "id": f"fixed_{item['id']}",
            "name": item["name"],
            "description": item["description"],
            "params": params,
        })

    top_n = CONFIG.get("PARAM_RECHECK_TOP_N", 0)
    for idx, res in enumerate(training_results[:top_n], start=1):
        params = dict(res["参数组合"])
        signature = param_signature(params)
        if signature in seen:
            continue
        seen.add(signature)
        cases.append({
            "id": f"train_top_{idx}",
            "name": f"训练Top{idx}",
            "description": f"训练集 Calmar 排名第 {idx} 的参数组合。",
            "params": params,
            "train_calmar": res["Calmar"],
            "train_sharpe": res["Sharpe"],
            "train_annual_return": res["年化收益"],
            "train_max_drawdown": res["最大回撤"],
        })

    return cases

def build_param_recheck_compare_row(case, summary, blind_res, output_dir):
    row = build_ablation_compare_row(
        {"id": case["id"], "name": case["name"], "description": case["description"]},
        summary,
        blind_res,
        output_dir,
    )
    row["训练Calmar"] = case.get("train_calmar", "")
    row["训练Sharpe"] = case.get("train_sharpe", "")
    row["训练年化收益"] = case.get("train_annual_return", "")
    row["训练最大回撤"] = case.get("train_max_drawdown", "")
    return row

def run_param_rechecks(training_results, market_data, stock_pool, benchmark_data, market_context, benchmark_kpi, run_stamp):
    cases = build_param_recheck_cases(training_results)
    if not cases:
        return None, None, None, None

    print("\n==================== 【阶段三：固定参数复验】 ====================")
    compare_rows = []
    group_dir = None
    params_by_case_id = {}

    for case in cases:
        print(f"\n[*] 参数复验 {case['name']}：{case['params']}")
        blind_res = execute_single_backtest(case["params"], market_data, stock_pool, benchmark_data, market_context, CONFIG["TEST_START"], CONFIG["TEST_END"])
        scenario = {"id": case["id"], "name": case["name"], "description": case["description"]}
        summary, output_dir, output_paths = save_blind_outputs(
            case["params"],
            len(stock_pool),
            blind_res,
            benchmark_kpi,
            scenario=scenario,
            run_stamp=run_stamp,
            group_prefix="param_recheck",
        )
        print_blind_summary(summary, output_dir, output_paths)
        compare_rows.append(build_param_recheck_compare_row(case, summary, blind_res, output_dir))
        params_by_case_id[case["id"]] = case["params"]
        if group_dir is None:
            group_dir = os.path.dirname(output_dir)

    compare_df = pd.DataFrame(compare_rows)
    selected_row = compare_df.sort_values(
        ["Sharpe", "Calmar", "总收益率", "最大回撤"],
        ascending=[False, False, False, True],
    ).iloc[0]
    selected_params = params_by_case_id[selected_row["场景ID"]]
    compare_csv = os.path.join(group_dir, f"Param_Recheck_{CONFIG['TARGET_BOARD']}_{run_stamp}.csv")
    compare_html = os.path.join(group_dir, f"Param_Recheck_{CONFIG['TARGET_BOARD']}_{run_stamp}.html")
    compare_df.to_csv(compare_csv, index=False, encoding="utf-8-sig")
    generate_ablation_compare_report(compare_html, compare_df, title="固定参数复验汇总")

    print("\n" + "="*58)
    print("          【固定参数复验汇总】          ")
    print("="*58)
    print(compare_df[["场景", "总收益率", "超额收益率", "最大回撤", "Calmar", "Sharpe", "交易次数", "强市盈亏贡献", "中性盈亏贡献", "弱市盈亏贡献"]].to_string(index=False, formatters={
        "总收益率": lambda x: f"{x*100:+.2f}%",
        "超额收益率": lambda x: f"{x*100:+.2f}%",
        "最大回撤": lambda x: f"{x*100:.2f}%",
        "强市盈亏贡献": lambda x: f"{x:+,.2f}",
        "中性盈亏贡献": lambda x: f"{x:+,.2f}",
        "弱市盈亏贡献": lambda x: f"{x:+,.2f}",
    }))
    print(f"▶ 复验CSV : {compare_csv}")
    print(f"▶ 复验HTML: {compare_html}")
    print(f"▶ 复验胜出参数 : {selected_row['场景']} | Sharpe {selected_row['Sharpe']:.2f} | Calmar {selected_row['Calmar']:.2f} | 收益 {selected_row['总收益率']*100:+.2f}%")
    print(f"▶ 胜出参数组合 : {selected_params}")
    print("="*58)
    return compare_df, compare_csv, compare_html, selected_params

def run_stability_validation():
    board_profile = get_board_profile()
    fixed_params = dict(CONFIG.get("STABILITY_FIXED_PARAMS") or CONFIG.get("ABLATION_FIXED_PARAMS") or {})
    if not fixed_params:
        raise ValueError("稳定性验证需要配置 STABILITY_FIXED_PARAMS 或 ABLATION_FIXED_PARAMS")

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    benchmark_data = load_benchmark_data()
    benchmark_kpi = calc_benchmark_kpi(benchmark_data, CONFIG["TEST_START"], CONFIG["TEST_END"])
    compare_rows = []
    param_slug = build_param_slug(fixed_params)
    compare_dir = os.path.join(CONFIG["OUTPUT_ROOT"], CONFIG["TARGET_BOARD"], param_slug, f"stability_compare_{run_stamp}")
    os.makedirs(compare_dir, exist_ok=True)

    print(f"==================== 【稳定性验证 ({CONFIG['TARGET_BOARD']} - {board_profile['name']})】 ====================")
    print(f"[*] 固定主策略参数: {fixed_params}")
    print("[*] 本阶段不重新训练、不重新挑参数，只验证同一策略在不同股票池上的表现。")

    for scenario in STABILITY_SCENARIOS:
        if not scenario.get("enabled", True):
            print(f"\n[-] 跳过稳定性场景 {scenario['name']}：enabled=False")
            continue

        print(f"\n[*] 稳定性场景 {scenario['name']}：{scenario['description']}")
        previous_values = apply_config_overrides(scenario.get("overrides", {}))
        try:
            market_data, stock_pool = load_all_market_data()
            if len(stock_pool) < 30:
                print(f"[!] 警告：当前场景有效股票数只有 {len(stock_pool)} 只，结果参考意义较弱。")
            market_context = build_market_context(benchmark_data, market_data)
            blind_res = execute_single_backtest(
                fixed_params,
                market_data,
                stock_pool,
                benchmark_data,
                market_context,
                CONFIG["TEST_START"],
                CONFIG["TEST_END"],
            )
            summary, output_dir, output_paths = save_blind_outputs(
                fixed_params,
                len(stock_pool),
                blind_res,
                benchmark_kpi,
                scenario=scenario,
                run_stamp=run_stamp,
                group_prefix="stability",
            )
            print_blind_summary(summary, output_dir, output_paths)
            compare_rows.append(build_ablation_compare_row(scenario, summary, blind_res, output_dir))
        finally:
            restore_config_overrides(previous_values)

    compare_df = pd.DataFrame(compare_rows)
    if not compare_df.empty:
        compare_csv = os.path.join(compare_dir, f"Stability_Compare_{CONFIG['TARGET_BOARD']}_{run_stamp}.csv")
        compare_html = os.path.join(compare_dir, f"Stability_Compare_{CONFIG['TARGET_BOARD']}_{run_stamp}.html")
        compare_df.to_csv(compare_csv, index=False, encoding="utf-8-sig")
        generate_ablation_compare_report(compare_html, compare_df, title="稳定性验证汇总")

        print("\n" + "="*58)
        print("          【稳定性验证汇总】          ")
        print("="*58)
        print(compare_df[["场景", "滑点率", "买入执行延迟交易日", "卖出执行延迟交易日", "延迟买入复核", "延迟买入信号收盘涨幅上限", "延迟买入原计划开盘涨幅上限", "抽样上限", "抽样种子", "实际股票数量", "总收益率", "超额收益率", "最大回撤", "Calmar", "Sharpe", "平均股票仓位", "未买入候选跟踪数", "买入复核放弃次数", "延迟价格放弃次数", "强市盈亏贡献", "中性盈亏贡献", "弱市盈亏贡献"]].to_string(index=False, formatters={
            "滑点率": lambda x: f"{x*100:.2f}%",
            "延迟买入信号收盘涨幅上限": lambda x: "" if pd.isna(x) else f"{x*100:.2f}%",
            "延迟买入原计划开盘涨幅上限": lambda x: "" if pd.isna(x) else f"{x*100:.2f}%",
            "总收益率": lambda x: f"{x*100:+.2f}%",
            "超额收益率": lambda x: f"{x*100:+.2f}%",
            "最大回撤": lambda x: f"{x*100:.2f}%",
            "平均股票仓位": lambda x: f"{x*100:.2f}%",
            "强市盈亏贡献": lambda x: f"{x:+,.2f}",
            "中性盈亏贡献": lambda x: f"{x:+,.2f}",
            "弱市盈亏贡献": lambda x: f"{x:+,.2f}",
        }))
        print(f"▶ 稳定性CSV : {compare_csv}")
        print(f"▶ 稳定性HTML: {compare_html}")
        print("="*58)

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
    portfolio, trade_history, daily_equity, candidate_watch = {}, [], [], []
    risk_stats = {
        "连续亏损暂停次数": 0,
        "回撤暂停次数": 0,
        "暂停开仓天数": 0,
        "强市场天数": 0,
        "中性市场天数": 0,
        "弱市场天数": 0,
        "扫描信号总数": 0,
        "实际买入次数": 0,
        "高开跳过次数": 0,
        "资金不足跳过次数": 0,
        "持仓上限跳过次数": 0,
        "买入复核放弃次数": 0,
        "延迟价格放弃次数": 0,
    }
    consecutive_loss_trades = 0
    loss_cooldown_until_idx = -1
    drawdown_cooldown_until_idx = -1
    equity_high_water_mark = CONFIG["INITIAL_CAPITAL"]
    drawdown_pause_armed = True

    period_dates = get_trading_calendar(benchmark_data, market_data, start_date, end_date)
    pending_buys, pending_sells = [], []
    buy_execution_delay = max(1, int(CONFIG.get("BUY_EXECUTION_DELAY_DAYS", 1)))
    sell_execution_delay = max(1, int(CONFIG.get("SELL_EXECUTION_DELAY_DAYS", 1)))

    for date_idx, current_date in enumerate(period_dates):
        regime_controls = get_regime_controls(market_context, current_date, max_holdings, max_position_per_stock, buy_threshold)
        day_signal_count = 0
        day_executed_buy_count = 0
        day_gap_skip_count = 0
        day_delayed_price_skip_count = 0
        day_cash_skip_count = 0
        day_limit_skip_count = 0
        if regime_controls["regime"] == "强":
            risk_stats["强市场天数"] += 1
        elif regime_controls["regime"] == "中":
            risk_stats["中性市场天数"] += 1
        elif regime_controls["regime"] == "弱":
            risk_stats["弱市场天数"] += 1

        # 1. 卖出
        still_pending_sells = []
        for pending_sell in pending_sells:
            if len(pending_sell) == 3:
                execute_idx, symbol, reason = pending_sell
            else:
                execute_idx = date_idx
                symbol, reason = pending_sell
            if execute_idx > date_idx:
                still_pending_sells.append((execute_idx, symbol, reason))
                continue
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
                    "买入月份": portfolio[symbol]["buy_date"].strftime("%Y-%m"),
                    "卖出日市场环境": regime_controls["regime"],
                    "持仓天数": portfolio[symbol]["days"],
                    "卖出时连续弱市持仓天数": portfolio[symbol].get("weak_regime_days", 0),
                    "累计弱市持仓天数": portfolio[symbol].get("total_weak_regime_days", 0),
                    "最大连续弱市持仓天数": portfolio[symbol].get("max_weak_regime_days", 0),
                    "买入数量": shares,
                    "买入价": round(portfolio[symbol]["cost"], 3),
                    "卖出价": round(exec_price, 3),
                    "买入耗资": round(invested, 2),
                    "卖出净额": round(net_value, 2),
                    "单笔净利": round(net_profit, 2),
                    "盈亏率": (exec_price - portfolio[symbol]["cost"]) / portfolio[symbol]["cost"],
                    "买入分数": portfolio[symbol].get("buy_score", ""),
                    "排序分": round(portfolio[symbol].get("rank_score", portfolio[symbol].get("buy_score", 0)), 2),
                    "卖出原因": reason,
                    "卖出后现金": round(cash, 2),
                    **portfolio[symbol].get("entry_snapshot", {}),
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
                still_pending_sells.append((execute_idx, symbol, reason))
        pending_sells = still_pending_sells
        pending_sell_symbols = {item[1] if len(item) == 3 else item[0] for item in pending_sells}

        # 2. 买入
        executable_buys, future_buys = [], []
        for pending_buy in pending_buys:
            if len(pending_buy) == 7:
                signal_idx, execute_idx, symbol, score, rank_score, prev_close, signal_snapshot = pending_buy
            elif len(pending_buy) == 6:
                signal_idx = max(0, pending_buy[0] - buy_execution_delay)
                execute_idx, symbol, score, rank_score, prev_close, signal_snapshot = pending_buy
            else:
                signal_idx = date_idx
                execute_idx = date_idx
                symbol, score, rank_score, prev_close, signal_snapshot = pending_buy
            if execute_idx <= date_idx:
                executable_buys.append((signal_idx, symbol, score, rank_score, prev_close, signal_snapshot))
            else:
                future_buys.append((signal_idx, execute_idx, symbol, score, rank_score, prev_close, signal_snapshot))

        risk_pause_active = date_idx <= loss_cooldown_until_idx or date_idx <= drawdown_cooldown_until_idx
        if risk_pause_active or not regime_controls["allow_new_positions"]:
            pending_buys = future_buys
        else:
            executable_buys.sort(key=candidate_sort_key, reverse=True)
            for buy_idx, (signal_idx, symbol, score, rank_score, prev_close, signal_snapshot) in enumerate(executable_buys):
                if len(portfolio) >= regime_controls["max_holdings"]:
                    skipped_by_limit = len(executable_buys) - buy_idx
                    day_limit_skip_count += skipped_by_limit
                    risk_stats["持仓上限跳过次数"] += skipped_by_limit
                    for _skipped_signal_idx, skipped_symbol, skipped_score, skipped_rank_score, skipped_prev_close, skipped_snapshot in executable_buys[buy_idx:]:
                        watch_record = build_candidate_watch_record(
                            skipped_symbol,
                            skipped_score,
                            skipped_rank_score,
                            skipped_prev_close,
                            skipped_snapshot,
                            current_date,
                            market_data,
                            stock_pool,
                            market_context,
                            len(portfolio),
                            regime_controls["max_holdings"],
                        )
                        if watch_record is not None:
                            candidate_watch.append(watch_record)
                    break
                if symbol in portfolio or current_date not in market_data[symbol].index: continue

                if CONFIG.get("REVALIDATE_DELAYED_BUY_SIGNAL", False) and date_idx - signal_idx > 1:
                    validation_idx = date_idx - 1
                    if validation_idx < 0:
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    validation_date = period_dates[validation_idx]
                    validation_df = market_data[symbol]
                    validation_controls = get_regime_controls(
                        market_context,
                        validation_date,
                        max_holdings,
                        max_position_per_stock,
                        buy_threshold,
                    )
                    if (
                        validation_date not in validation_df.index
                        or not validation_controls["allow_new_positions"]
                    ):
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    validation_k = validation_df.loc[validation_date]
                    if validation_k["RSI14"] > rsi_oversold:
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    if not passes_entry_quality_filter(validation_k, validation_controls["regime"]):
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    recheck_score, recheck_recent_5 = calculate_buy_signal_score(validation_df, validation_date)
                    if recheck_score < validation_controls["buy_threshold"]:
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    recheck_rank_score = calculate_candidate_rank_score(
                        validation_k,
                        recheck_recent_5,
                        recheck_score,
                        validation_controls["regime"],
                    )
                    if recheck_rank_score is None:
                        risk_stats["买入复核放弃次数"] += 1
                        continue
                    score = recheck_score
                    rank_score = recheck_rank_score
                    prev_close = validation_k["收盘"]
                    signal_snapshot = build_signal_snapshot(symbol, validation_df, validation_date, market_context)

                df_for_buy = market_data[symbol]
                buy_row = df_for_buy.loc[current_date]
                ideal_price = safe_float(buy_row.get("开盘"))
                if pd.isna(ideal_price) or ideal_price <= 0:
                    continue
                original_signal_close = safe_float(signal_snapshot.get("信号日收盘", prev_close))
                original_plan_open = get_original_plan_open(df_for_buy, period_dates, signal_idx)
                gap_from_signal_close = ideal_price / original_signal_close - 1 if original_signal_close and original_signal_close > 0 else np.nan
                gap_from_first_open = ideal_price / original_plan_open - 1 if original_plan_open and original_plan_open > 0 else np.nan

                if date_idx - signal_idx > 1:
                    max_delayed_signal_gap = CONFIG.get("MAX_DELAYED_BUY_GAP_FROM_SIGNAL_CLOSE")
                    max_delayed_first_open_gap = CONFIG.get("MAX_DELAYED_BUY_GAP_FROM_FIRST_OPEN")
                    delayed_above_ma20_required = CONFIG.get("REQUIRE_DELAYED_BUY_ABOVE_MA20", False)

                    if (
                        max_delayed_signal_gap is not None
                        and not pd.isna(gap_from_signal_close)
                        and gap_from_signal_close > max_delayed_signal_gap
                    ):
                        day_delayed_price_skip_count += 1
                        risk_stats["延迟价格放弃次数"] += 1
                        continue
                    if (
                        max_delayed_first_open_gap is not None
                        and not pd.isna(gap_from_first_open)
                        and gap_from_first_open > max_delayed_first_open_gap
                    ):
                        day_delayed_price_skip_count += 1
                        risk_stats["延迟价格放弃次数"] += 1
                        continue
                    if delayed_above_ma20_required:
                        ma20 = safe_float(buy_row.get("MA20"))
                        if pd.isna(ma20) or ideal_price < ma20:
                            day_delayed_price_skip_count += 1
                            risk_stats["延迟价格放弃次数"] += 1
                            continue

                if prev_close and prev_close > 0 and (ideal_price - prev_close) / prev_close > CONFIG["MAX_BUY_GAP_RATE"]:
                    day_gap_skip_count += 1
                    risk_stats["高开跳过次数"] += 1
                    continue

                exec_price = ideal_price * (1 + CONFIG["SLIPPAGE_RATE"])
                current_equity_for_budget = calculate_portfolio_equity(cash, portfolio, market_data, current_date, "开盘")
                shares_to_buy = int(min(cash, current_equity_for_budget * regime_controls["position_per_stock"]) / (exec_price * 100)) * 100

                if shares_to_buy >= 100:
                    cost = shares_to_buy * exec_price
                    commission_buy = max(CONFIG["MIN_COMMISSION"], cost * CONFIG["COMMISSION_RATE"])
                    total_invested = cost + commission_buy
                    cash -= total_invested
                    entry_snapshot = dict(signal_snapshot)
                    entry_snapshot.update(build_execution_snapshot(market_data[symbol], current_date, prev_close, market_context))
                    entry_snapshot.update({
                        "买入执行延迟交易日": date_idx - signal_idx,
                        "原计划买入日开盘": original_plan_open,
                        "买入日相对信号收盘涨幅": gap_from_signal_close,
                        "买入日相对原计划开盘涨幅": gap_from_first_open,
                    })

                    portfolio[symbol] = {
                        "shares": shares_to_buy,
                        "cost": exec_price,
                        "days": 0,
                        "highest": exec_price,
                        "buy_date": current_date,
                        "invested": total_invested,
                        "buy_score": score,
                        "rank_score": rank_score,
                        "entry_snapshot": entry_snapshot,
                        "weak_regime_days": 0,
                        "total_weak_regime_days": 0,
                        "max_weak_regime_days": 0,
                    }
                    day_executed_buy_count += 1
                    risk_stats["实际买入次数"] += 1
                else:
                    day_cash_skip_count += 1
                    risk_stats["资金不足跳过次数"] += 1
            pending_buys = future_buys

        # 3. 持仓体检
        for symbol, pos in portfolio.items():
            if symbol in pending_sell_symbols: continue
            if current_date not in market_data[symbol].index: continue
            today_k = market_data[symbol].loc[current_date]
            pos["days"] += 1
            if regime_controls["regime"] == "弱":
                pos["weak_regime_days"] = pos.get("weak_regime_days", 0) + 1
                pos["total_weak_regime_days"] = pos.get("total_weak_regime_days", 0) + 1
                pos["max_weak_regime_days"] = max(pos.get("max_weak_regime_days", 0), pos["weak_regime_days"])
            else:
                pos["weak_regime_days"] = 0
            pos["highest"] = max(pos["highest"], today_k["收盘"])
            return_rate = (today_k["收盘"] - pos["cost"]) / pos["cost"]
            effective_stop_loss_rate = stop_loss_rate
            if regime_controls["regime"] == "弱" and CONFIG.get("WEAK_STOP_LOSS_RATE") is not None:
                effective_stop_loss_rate = CONFIG["WEAK_STOP_LOSS_RATE"]

            sell_reason = ""
            if return_rate <= effective_stop_loss_rate:
                sell_reason = "绝对止损"
            elif is_ma20_breakdown(market_data[symbol], current_date, regime_controls["regime"]):
                sell_reason = "破位防守"
            elif should_trigger_weak_holding_exit(pos, return_rate, regime_controls["regime"]):
                sell_reason = "转弱持仓退出"
            elif pos["highest"] >= pos["cost"] * (1 + CONFIG["TRAIL_PROFIT_TRIGGER"]) and today_k["收盘"] <= pos["highest"] * (1 - CONFIG["TRAIL_DRAWDOWN_RATE"]):
                sell_reason = "回撤止盈"
            elif CONFIG["ENABLE_EXCITEMENT_TAKE_PROFIT"] and return_rate > 0.15 and today_k["RSI14"] > rsi_oversold:
                sell_reason = "亢奋止盈"
            elif pos["days"] >= max_hold_days and -time_sunk_tolerance <= return_rate <= time_sunk_tolerance:
                sell_reason = "沉没止损"

            if sell_reason: pending_sells.append((date_idx + sell_execution_delay, symbol, sell_reason))

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
                if symbol in portfolio or symbol in pending_sell_symbols or current_date not in df.index: continue
                today_k = df.loc[current_date]
                if today_k["RSI14"] > rsi_oversold: continue
                if not passes_entry_quality_filter(today_k, regime_controls["regime"]): continue

                score, recent_5 = calculate_buy_signal_score(df, current_date)

                if score >= regime_controls["buy_threshold"]:
                    rank_score = calculate_candidate_rank_score(today_k, recent_5, score, regime_controls["regime"])
                    if rank_score is None:
                        continue
                    signal_snapshot = build_signal_snapshot(symbol, df, current_date, market_context)
                    pending_buys.append((date_idx, date_idx + buy_execution_delay, symbol, score, rank_score, today_k["收盘"], signal_snapshot))
                    day_signal_count += 1
                    risk_stats["扫描信号总数"] += 1

        stock_market_value = calculate_portfolio_market_value(portfolio, market_data, current_date, "收盘")
        stock_position_ratio = stock_market_value / current_equity if current_equity > 0 else 0
        daily_equity.append({
            "日期": current_date,
            "总权益": current_equity,
            "现金": cash,
            "股票市值": stock_market_value,
            "股票仓位": stock_position_ratio,
            "持仓数量": len(portfolio),
            "市场环境": regime_controls["regime"],
            "允许开仓": market_is_healthy and not risk_pause_active,
            "风控暂停": risk_pause_active,
            "当日信号数": day_signal_count,
            "当日买入数": day_executed_buy_count,
            "高开跳过数": day_gap_skip_count,
            "延迟价格放弃数": day_delayed_price_skip_count,
            "资金不足跳过数": day_cash_skip_count,
            "持仓上限跳过数": day_limit_skip_count,
            "持仓上限": regime_controls["max_holdings"],
            "买入分数门槛": regime_controls["buy_threshold"],
        })

    df_equity = pd.DataFrame(daily_equity).set_index("日期") if daily_equity else pd.DataFrame()
    kpi_res = calc_kpi(df_equity["总权益"]) if not df_equity.empty else calc_kpi(pd.Series(dtype=float))

    kpi_res["参数组合"] = params
    kpi_res["交易明细"] = pd.DataFrame(trade_history)
    kpi_res["候选跟踪"] = pd.DataFrame(candidate_watch)
    kpi_res["权益曲线"] = df_equity
    kpi_res["风控统计"] = risk_stats
    return kpi_res

# ==================== 4. 总控与寻优调度器 ====================
def run_optimization_and_blind_test():
    if CONFIG.get("ENABLE_STABILITY_TESTS", False):
        run_stability_validation()
        return

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
    benchmark_kpi = calc_benchmark_kpi(benchmark_data, CONFIG["TEST_START"], CONFIG["TEST_END"])

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ablation_params = best_params

    if CONFIG.get("ENABLE_PARAM_RECHECKS", False):
        _, _, _, selected_recheck_params = run_param_rechecks(training_results, market_data, stock_pool, benchmark_data, market_context, benchmark_kpi, run_stamp)
        if CONFIG.get("USE_PARAM_RECHECK_WINNER_FOR_ABLATION", False) and selected_recheck_params is not None:
            ablation_params = selected_recheck_params
            print(f"\n[*] 后续消融测试将使用固定参数复验胜出参数: {ablation_params}")
        else:
            print(f"\n[*] 后续消融测试继续使用训练 Top1 参数: {ablation_params}")

    if CONFIG.get("ABLATION_FIXED_PARAMS"):
        ablation_params = dict(CONFIG["ABLATION_FIXED_PARAMS"])
        print(f"\n[*] 消融测试已锁定固定参数: {ablation_params}")

    if CONFIG.get("ENABLE_ABLATION_TESTS", False):
        print("\n==================== 【阶段三：消融对照测试】 ====================")
        print(f"[*] 消融测试使用参数: {ablation_params}")
        compare_rows = []
        ablation_group_dir = None

        for scenario in ABLATION_SCENARIOS:
            print(f"\n[*] 消融场景 {scenario['name']}：{scenario['description']}")
            previous_values = apply_config_overrides(scenario.get("overrides", {}))
            scenario_params = dict(ablation_params)
            scenario_params.update(scenario.get("param_overrides", {}))
            try:
                blind_res = execute_single_backtest(scenario_params, market_data, stock_pool, benchmark_data, market_context, CONFIG["TEST_START"], CONFIG["TEST_END"])
                summary, output_dir, output_paths = save_blind_outputs(
                    scenario_params,
                    len(stock_pool),
                    blind_res,
                    benchmark_kpi,
                    scenario=scenario,
                    run_stamp=run_stamp,
                    group_prefix="ablation",
                )
                print_blind_summary(summary, output_dir, output_paths)
                compare_rows.append(build_ablation_compare_row(scenario, summary, blind_res, output_dir))
                if ablation_group_dir is None:
                    ablation_group_dir = os.path.dirname(output_dir)
            finally:
                restore_config_overrides(previous_values)

        compare_df = pd.DataFrame(compare_rows)
        if ablation_group_dir and not compare_df.empty:
            compare_csv = os.path.join(ablation_group_dir, f"Ablation_Compare_{CONFIG['TARGET_BOARD']}_{run_stamp}.csv")
            compare_html = os.path.join(ablation_group_dir, f"Ablation_Compare_{CONFIG['TARGET_BOARD']}_{run_stamp}.html")
            compare_df.to_csv(compare_csv, index=False, encoding="utf-8-sig")
            generate_ablation_compare_report(compare_html, compare_df)
            print("\n" + "="*58)
            print("          【消融对照测试汇总】          ")
            print("="*58)
            print(compare_df[["场景", "总收益率", "超额收益率", "最大回撤", "Calmar", "平均股票仓位", "强市盈亏贡献", "中性盈亏贡献", "弱市盈亏贡献"]].to_string(index=False, formatters={
                "总收益率": lambda x: f"{x*100:+.2f}%",
                "超额收益率": lambda x: f"{x*100:+.2f}%",
                "最大回撤": lambda x: f"{x*100:.2f}%",
                "平均股票仓位": lambda x: f"{x*100:.2f}%",
                "强市盈亏贡献": lambda x: f"{x:+,.2f}",
                "中性盈亏贡献": lambda x: f"{x:+,.2f}",
                "弱市盈亏贡献": lambda x: f"{x:+,.2f}",
            }))
            print(f"▶ 汇总CSV : {compare_csv}")
            print(f"▶ 汇总HTML: {compare_html}")
            print("="*58)
        return

    blind_res = execute_single_backtest(best_params, market_data, stock_pool, benchmark_data, market_context, CONFIG["TEST_START"], CONFIG["TEST_END"])
    summary, output_dir, output_paths = save_blind_outputs(best_params, len(stock_pool), blind_res, benchmark_kpi)
    print_blind_summary(summary, output_dir, output_paths)

    if summary['Calmar'] < best_train_res['Calmar'] * 0.5:
        print("\n[!] 警告：盲测表现大幅度衰减，存在过度拟合风险，不建议实盘！")
    else:
        print(f"\n[√] 恭喜：{CONFIG['TARGET_BOARD']} 板块参数在样本外表现稳健，经受住了泛化检验。")

if __name__ == "__main__":
    run_optimization_and_blind_test()
