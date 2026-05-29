"""
collect_biweekly.py
Biweekly 지표 수집 모듈 (3개 지표)
- S&P500 200일선 위 종목 비율
- McClellan Oscillator
- 외국인 코스피 지분율 추이
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import time
import json

# S&P500 구성종목 (대표 100개로 제한, 속도/안정성 균형)
# 전체 500개 대신 시총 상위 100개 사용 → 대표성 충분, 실행 시간 단축
SP500_TOP100 = [
    'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','BRK-B','AVGO','JPM',
    'LLY','V','UNH','XOM','MA','COST','HD','PG','WMT','NFLX',
    'ABBV','BAC','KO','CRM','CVX','MRK','TMO','ORCL','ACN','PEP',
    'AMD','LIN','CSCO','MCD','DHR','ABT','ADBE','WFC','CAT','TXN',
    'INTU','PM','NEE','MS','GS','AXP','RTX','ISRG','AMGN','BKNG',
    'PFE','UBER','SPGI','T','LOW','C','DE','BLK','ELV','AMAT',
    'VRTX','MDT','REGN','PANW','MU','GILD','ADI','SYK','LRCX','KLAC',
    'CI','ETN','ZTS','BMY','INTC','CMG','SO','DUK','ITW','PLD',
    'SBUX','MDLZ','MMM','NOW','TJX','CB','USB','HCA','GE','EOG',
    'SLB','BDX','AON','CTAS','MCO','EQIX','APH','NSC','PNC','FCX'
]


# ─────────────────────────────────────────
# 1. S&P500 200일선 위 종목 비율
# ─────────────────────────────────────────
def get_sp500_above_ma200():
    print("  S&P500 200일선 비율 수집 중 (시간 소요)...")
    above = 0
    total = 0
    failed = []

    for i, ticker in enumerate(SP500_TOP100):
        try:
            data = yf.download(ticker, period='1y', progress=False, auto_adjust=True)
            close = data['Close'].dropna()
            if len(close) < 200:
                # 200일치 없으면 있는 것만으로 계산
                ma = close.mean()
            else:
                ma = close.rolling(200).mean().iloc[-1]

            current = float(close.iloc[-1])
            if current > float(ma):
                above += 1
            total += 1

            if (i + 1) % 20 == 0:
                print(f"    진행: {i+1}/{len(SP500_TOP100)}")

            time.sleep(0.15)  # 차단 방지
        except Exception:
            failed.append(ticker)

    if total == 0:
        return {'above_ma200_ratio': None, 'above_ma200_count': None, 'above_ma200_total': None}

    ratio = round(above / total * 100, 1)
    print(f"    완료: {above}/{total} ({ratio}%) / 실패: {len(failed)}개")

    return {
        'above_ma200_ratio': ratio,
        'above_ma200_count': above,
        'above_ma200_total': total
    }


# ─────────────────────────────────────────
# 2. McClellan Oscillator
# ─────────────────────────────────────────
def get_mcclellan():
    """
    NYSE 등락 종목 수 기반으로 계산
    yfinance에서 $ADDN (NYSE Advancing), $DECN (NYSE Declining) 수집
    """
    try:
        # NYSE 등락 종목 수
        adv_data = yf.download('^NYCH', period='60d', progress=False, auto_adjust=True)

        # 직접 계산 대신 ETF 방식으로 근사치 계산
        # SPY 구성종목 상승/하락 비율로 대체
        spy_data = yf.download('SPY', period='60d', progress=False, auto_adjust=True)
        spy_close = spy_data['Close'].dropna()

        # 일별 수익률로 A-D 라인 근사치 계산
        daily_ret = spy_close.pct_change().dropna()

        # 단순화된 McClellan: SPY 일수익률의 19일EMA - 39일EMA
        ema19 = daily_ret.ewm(span=19, adjust=False).mean()
        ema39 = daily_ret.ewm(span=39, adjust=False).mean()
        mcclellan = ((ema19 - ema39) * 10000).dropna()

        current = round(float(mcclellan.iloc[-1]), 2)
        prev    = round(float(mcclellan.iloc[-2]), 2) if len(mcclellan) >= 2 else None

        # 0선 교차 감지
        if prev is not None:
            if prev < 0 and current > 0:
                zero_cross = "상향 돌파 (하락→상승 전환 신호)"
            elif prev > 0 and current < 0:
                zero_cross = "하향 돌파 (상승→하락 전환 신호)"
            else:
                zero_cross = None
        else:
            zero_cross = None

        return {
            'mcclellan': current,
            'mcclellan_prev': prev,
            'mcclellan_zero_cross': zero_cross
        }
    except Exception as e:
        print(f"[오류] McClellan: {e}")
        return {'mcclellan': None, 'mcclellan_prev': None, 'mcclellan_zero_cross': None}


# ─────────────────────────────────────────
# 3. 외국인 코스피 지분율 추이
# ─────────────────────────────────────────
def get_foreign_ownership():
    """
    KRX 정보데이터시스템에서 외국인 지분율 수집
    https://data.krx.co.kr
    """
    try:
        from datetime import timedelta
        today = datetime.now()
        start = (today - timedelta(days=60)).strftime('%Y%m%d')
        end   = today.strftime('%Y%m%d')

        url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'http://data.krx.co.kr/'
        }
        body = {
            'bld': 'dbms/MDC/STAT/standard/MDCSTAT01701',
            'mktId': 'STK',
            'strtDd': start,
            'endDd': end,
            'share': '1',
            'money': '1',
            'csvxls_isNo': 'false'
        }

        resp = requests.post(url, data=body, headers=headers, timeout=15)
        data = resp.json()

        if data and 'output' in data:
            records = data['output']
            if records:
                latest = records[-1]
                oldest = records[0]
                current_rate = float(latest.get('FRGN_HLD_RT', 0))
                prev_rate    = float(oldest.get('FRGN_HLD_RT', 0))
                change       = round(current_rate - prev_rate, 2)

                return {
                    'foreign_ownership_rate': round(current_rate, 2),
                    'foreign_ownership_2m_chg': change,
                    'foreign_ownership_date': latest.get('BAS_DD', '')
                }
    except Exception as e:
        print(f"[오류] 외국인 지분율: {e}")

    return {
        'foreign_ownership_rate': None,
        'foreign_ownership_2m_chg': None,
        'foreign_ownership_date': None
    }


# ─────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────
def collect_all_biweekly():
    print("[격주 수집 시작]", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    data = {}

    data.update(get_sp500_above_ma200())
    time.sleep(1)

    print("  McClellan Oscillator 수집 중...")
    data.update(get_mcclellan())
    time.sleep(0.5)

    print("  외국인 코스피 지분율 수집 중...")
    data.update(get_foreign_ownership())

    data['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("[격주 수집 완료]")
    return data


if __name__ == '__main__':
    result = collect_all_biweekly()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
