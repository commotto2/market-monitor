"""
collect_weekly.py
Weekly 지표 수집 모듈 (8개 지표)
- 장단기 금리차 (10년-2년)
- MOVE 인덱스
- TED 스프레드 (SOFR - T-bill)
- 섹터 ETF 순위 (11개)
- QQQ/SPY 비율
- IVW/IVE 비율
- IWM/SPY 비율
- 코스피 신용잔고 비율 (금투협)
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import json
import os


FRED_API_KEY = os.environ.get('FRED_API_KEY', '')


# ─────────────────────────────────────────
# 1. 장단기 금리차 (10년 - 2년)
# ─────────────────────────────────────────
def get_yield_curve():
    try:
        result = {}
        for name, ticker in [('T10Y', '^TNX'), ('T2Y', '^IRX')]:
            data = yf.download(ticker, period='30d', progress=False, auto_adjust=True)
            close = data['Close'].dropna()
            result[name] = round(float(close.iloc[-1]), 3)
            result[f'{name}_4w_ago'] = round(float(close.iloc[-20]), 3) if len(close) >= 20 else None

        spread = round(result['T10Y'] - result['T2Y'], 3)
        spread_4w = round(result['T10Y_4w_ago'] - result['T2Y_4w_ago'], 3) \
            if result.get('T10Y_4w_ago') and result.get('T2Y_4w_ago') else None

        # 역전 해소 감지 (이전엔 음수, 지금은 양수)
        inversion_resolving = False
        if spread_4w and spread_4w < 0 and spread > 0:
            inversion_resolving = True

        return {
            'T10Y': result['T10Y'],
            'T2Y': result['T2Y'],
            'yield_spread': spread,
            'yield_spread_4w_ago': spread_4w,
            'yield_inverted': spread < 0,
            'yield_inversion_resolving': inversion_resolving
        }
    except Exception as e:
        print(f"[오류] 장단기 금리차: {e}")
        return {
            'T10Y': None, 'T2Y': None, 'yield_spread': None,
            'yield_spread_4w_ago': None, 'yield_inverted': False,
            'yield_inversion_resolving': False
        }


# ─────────────────────────────────────────
# 2. MOVE 인덱스
# ─────────────────────────────────────────
def get_move_index():
    """
    yfinance ^MOVE는 데이터가 불안정할 수 있음
    FRED API 백업 사용
    """
    move_val = None

    # 1차 시도: yfinance
    try:
        data = yf.download('^MOVE', period='10d', progress=False, auto_adjust=True)
        close = data['Close'].dropna()
        if not close.empty:
            move_val = round(float(close.iloc[-1]), 2)
            prev = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
            return {
                'MOVE': move_val,
                'MOVE_prev': prev,
                'MOVE_chg': round(move_val - prev, 2) if prev else None
            }
    except Exception:
        pass

    # 2차 시도: FRED API
    if FRED_API_KEY:
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': 'BAMLMOVE',
                'api_key': FRED_API_KEY,
                'file_type': 'json',
                'sort_order': 'desc',
                'limit': 5
            }
            resp = requests.get(url, params=params, timeout=10)
            obs = resp.json()['observations']
            vals = [float(o['value']) for o in obs if o['value'] != '.']
            if vals:
                return {
                    'MOVE': round(vals[0], 2),
                    'MOVE_prev': round(vals[1], 2) if len(vals) >= 2 else None,
                    'MOVE_chg': round(vals[0] - vals[1], 2) if len(vals) >= 2 else None
                }
        except Exception as e:
            print(f"[오류] MOVE FRED: {e}")

    return {'MOVE': None, 'MOVE_prev': None, 'MOVE_chg': None}


# ─────────────────────────────────────────
# 3. TED 스프레드 (SOFR 90일 - 3개월 T-bill)
# ─────────────────────────────────────────
def get_ted_spread():
    if not FRED_API_KEY:
        print("[건너뜀] TED 스프레드: FRED_API_KEY 미설정")
        return {'TED_spread': None, 'SOFR': None, 'T_bill_3m': None}

    try:
        result = {}
        for series_id, key in [('SOFR90DAYAVG', 'SOFR'), ('DTB3', 'T_bill_3m')]:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': series_id,
                'api_key': FRED_API_KEY,
                'file_type': 'json',
                'sort_order': 'desc',
                'limit': 5
            }
            resp = requests.get(url, params=params, timeout=10)
            obs = resp.json()['observations']
            vals = [float(o['value']) for o in obs if o['value'] != '.']
            result[key] = round(vals[0], 3) if vals else None
            time.sleep(0.3)

        if result.get('SOFR') and result.get('T_bill_3m'):
            spread = round(result['SOFR'] - result['T_bill_3m'], 3)
        else:
            spread = None

        result['TED_spread'] = spread
        return result
    except Exception as e:
        print(f"[오류] TED 스프레드: {e}")
        return {'TED_spread': None, 'SOFR': None, 'T_bill_3m': None}


# ─────────────────────────────────────────
# 4. 섹터 ETF 순위 (11개)
# ─────────────────────────────────────────
SECTOR_ETFS = {
    'XLK':  'Technology',
    'XLV':  'Health Care',
    'XLF':  'Financials',
    'XLE':  'Energy',
    'XLI':  'Industrials',
    'XLP':  'Staples',
    'XLU':  'Utilities',
    'XLRE': 'Real Estate',
    'XLY':  'Discretionary',
    'XLB':  'Materials',
    'XLC':  'Comm Svcs'
}

DEFENSIVE_SECTORS = {'XLU', 'XLP', 'XLV'}
OFFENSIVE_SECTORS = {'XLK', 'XLY', 'XLF'}


def get_sector_performance():
    try:
        tickers = list(SECTOR_ETFS.keys())
        data = yf.download(tickers, period='35d', progress=False, auto_adjust=True)['Close']

        results = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna()
                ret_1w = round((series.iloc[-1] / series.iloc[-6] - 1) * 100, 2) if len(series) >= 6 else None
                ret_1m = round((series.iloc[-1] / series.iloc[-22] - 1) * 100, 2) if len(series) >= 22 else None
                results.append({
                    'ticker': ticker,
                    'name': SECTOR_ETFS[ticker],
                    'ret_1w': ret_1w,
                    'ret_1m': ret_1m
                })
            except Exception:
                pass

        # 1주 수익률 기준 정렬
        results.sort(key=lambda x: x['ret_1w'] if x['ret_1w'] is not None else -999, reverse=True)

        # 리스크온/오프 판단
        top3 = [r['ticker'] for r in results[:3]]
        defensive_in_top3 = len(set(top3) & DEFENSIVE_SECTORS)
        offensive_in_top3 = len(set(top3) & OFFENSIVE_SECTORS)

        if defensive_in_top3 >= 2:
            risk_mode = "리스크오프 (방어 섹터 상위)"
        elif offensive_in_top3 >= 2:
            risk_mode = "리스크온 (성장 섹터 상위)"
        else:
            risk_mode = "혼조 (섹터 로테이션 진행 중)"

        return {
            'sector_ranking': results,
            'sector_risk_mode': risk_mode
        }
    except Exception as e:
        print(f"[오류] 섹터 ETF: {e}")
        return {'sector_ranking': [], 'sector_risk_mode': None}


# ─────────────────────────────────────────
# 5~7. 비율 지표 (QQQ/SPY, IVW/IVE, IWM/SPY)
# ─────────────────────────────────────────
def get_ratio_indicators():
    ratios = {
        'QQQ_SPY': ('QQQ', 'SPY', 'QQQ/SPY (나스닥 vs S&P500)'),
        'IVW_IVE': ('IVW', 'IVE', 'IVW/IVE (성장 vs 가치)'),
        'IWM_SPY': ('IWM', 'SPY', 'IWM/SPY (소형주 vs 대형주)')
    }

    result = {}
    try:
        all_tickers = list(set(['QQQ', 'SPY', 'IVW', 'IVE', 'IWM']))
        data = yf.download(all_tickers, period='60d', progress=False, auto_adjust=True)['Close']

        for key, (t1, t2, label) in ratios.items():
            try:
                ratio = (data[t1] / data[t2]).dropna()
                current = round(float(ratio.iloc[-1]), 4)
                ma20    = round(float(ratio.rolling(20).mean().iloc[-1]), 4)
                chg_1w  = round((ratio.iloc[-1] / ratio.iloc[-6] - 1) * 100, 2) if len(ratio) >= 6 else None
                chg_1m  = round((ratio.iloc[-1] / ratio.iloc[-22] - 1) * 100, 2) if len(ratio) >= 22 else None

                above_ma20 = current > ma20

                result[key] = {
                    'label':       label,
                    'ratio':       current,
                    'ma20':        ma20,
                    'above_ma20':  above_ma20,
                    'chg_1w':      chg_1w,
                    'chg_1m':      chg_1m
                }
            except Exception as e:
                print(f"[오류] {key}: {e}")
                result[key] = None

    except Exception as e:
        print(f"[오류] 비율 지표 전체: {e}")

    return result


# ─────────────────────────────────────────
# 8. 코스피 신용잔고 비율 (금융투자협회)
# ─────────────────────────────────────────
def get_credit_balance():
    """
    금융투자협회 API에서 신용거래융자 잔고 수집
    https://freesis.kofia.or.kr
    """
    try:
        today = datetime.now()
        start = (today - timedelta(days=30)).strftime('%Y%m%d')
        end   = today.strftime('%Y%m%d')

        url = "https://freesis.kofia.or.kr/stat/fnc/selectFncStatMktTrnsData.do"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/json;charset=UTF-8',
            'Referer': 'https://freesis.kofia.or.kr/'
        }
        body = {
            "tboxisuCd_0": "",
            "isuCd": "",
            "strtDd": start,
            "endDd": end,
            "mktTpCd": "1",  # 1: 코스피
            "inqTpCd": "1"
        }

        resp = requests.post(url, json=body, headers=headers, timeout=15)
        data = resp.json()

        if data and isinstance(data, list):
            latest = data[-1]
            balance_bil = float(latest.get('crdtRmndAmt', 0)) / 1e8  # 억 단위
            return {
                'credit_balance_bil': round(balance_bil, 0),
                'credit_date': latest.get('baseDd', '')
            }

    except Exception as e:
        print(f"[오류] 신용잔고: {e}")

    return {'credit_balance_bil': None, 'credit_date': None}


# ─────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────
def collect_all_weekly():
    print("[주간 수집 시작]", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    data = {}

    print("  장단기 금리차 수집 중...")
    data.update(get_yield_curve())
    time.sleep(0.5)

    print("  MOVE 인덱스 수집 중...")
    data.update(get_move_index())
    time.sleep(0.5)

    print("  TED 스프레드 수집 중...")
    data.update(get_ted_spread())
    time.sleep(0.5)

    print("  섹터 ETF 순위 수집 중...")
    data.update(get_sector_performance())
    time.sleep(0.5)

    print("  비율 지표 수집 중...")
    data.update(get_ratio_indicators())
    time.sleep(0.5)

    print("  신용잔고 수집 중...")
    data.update(get_credit_balance())

    data['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("[주간 수집 완료]")
    return data


if __name__ == '__main__':
    result = collect_all_weekly()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
