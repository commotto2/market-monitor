"""
collect_monthly.py
Monthly 지표 수집 모듈 (3개 지표)
- 삼성전자/SK하이닉스 외국인 지분율 월간 추이
- 코스피 vs S&P500 상대 수익률
- 원/달러 환율 월간 변동폭
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import time


def _get_close_m(ticker, period):
    """yfinance 단일 티커 종가 Series 반환 (멀티컬럼 대응)"""
    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if data.empty:
        return pd.Series(dtype=float)
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()
    return close.dropna()


# ─────────────────────────────────────────
# 1. 삼성전자/SK하이닉스 외국인 지분율 월간 추이
# ─────────────────────────────────────────
def get_stock_foreign_monthly(app_key=None, app_secret=None, access_token=None):
    """
    한국투자증권 Open API 사용
    API 미설정 시 yfinance로 주가만 수집
    """
    result = {}

    stocks = {
        'samsung': {'code': '005930', 'name': '삼성전자'},
        'hynix':   {'code': '000660', 'name': 'SK하이닉스'}
    }

    if app_key and app_secret and access_token:
        import requests
        BASE_URL = "https://openapi.koreainvestment.com:9443"

        for key, info in stocks.items():
            try:
                headers = {
                    "authorization": f"Bearer {access_token}",
                    "appkey": app_key,
                    "appsecret": app_secret,
                    "tr_id": "FHKST01010100",
                    "content-type": "application/json"
                }
                params = {
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": info['code']
                }
                resp = requests.get(
                    f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                    headers=headers, params=params, timeout=10
                )
                data = resp.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    result[key] = {
                        'name': info['name'],
                        'price': output.get('stck_prpr', 'N/A'),
                        'foreign_rate': output.get('hts_frgn_ehrt', 'N/A'),
                        'foreign_net_buy_month': output.get('frgn_ntby_qty', 'N/A')
                    }
                time.sleep(0.3)
            except Exception as e:
                print(f"[오류] {info['name']} 월간: {e}")
                result[key] = None
    else:
        # API 없을 때 yfinance로 주가만
        for key, info in stocks.items():
            ticker_map = {'samsung': '005930.KS', 'hynix': '000660.KS'}
            try:
                close = _get_close_m(ticker_map[key], '1mo')
                if not close.empty:
                    ret_1m = round((float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100, 2)
                    result[key] = {
                        'name': info['name'],
                        'price': round(float(close.iloc[-1])),
                        'ret_1m': ret_1m,
                        'foreign_rate': 'N/A (API 미설정)'
                    }
            except Exception as e:
                print(f"[오류] {info['name']} yfinance: {e}")
                result[key] = None

    return result


# ─────────────────────────────────────────
# 2. 코스피 vs S&P500 상대 수익률
# ─────────────────────────────────────────
def get_relative_performance(app_key=None, app_secret=None, access_token=None):
    try:
        kospi_close = _get_close_m('^KS11',  '14mo')
        sp500_close = _get_close_m('^GSPC', '14mo')

        if sp500_close.empty:
            raise ValueError("S&P500 데이터 없음")

        # 공통 날짜만 사용
        import pandas as pd
        df = pd.DataFrame({'KOSPI': kospi_close, 'SP500': sp500_close}).dropna()

        def calc_ret(series, days):
            if len(series) >= days:
                return round((series.iloc[-1] / series.iloc[-days] - 1) * 100, 2)
            return None

        kospi_1m = calc_ret(df['KOSPI'], 22)
        sp500_1m = calc_ret(df['SP500'], 22)
        kospi_3m = calc_ret(df['KOSPI'], 66)
        sp500_3m = calc_ret(df['SP500'], 66)
        kospi_1y = calc_ret(df['KOSPI'], 252)
        sp500_1y = calc_ret(df['SP500'], 252)

        # 상대 수익률 (코스피 - S&P500)
        rel_1m = round(kospi_1m - sp500_1m, 2) if kospi_1m and sp500_1m else None
        rel_3m = round(kospi_3m - sp500_3m, 2) if kospi_3m and sp500_3m else None
        rel_1y = round(kospi_1y - sp500_1y, 2) if kospi_1y and sp500_1y else None

        return {
            'kospi_ret_1m': kospi_1m, 'sp500_ret_1m': sp500_1m, 'rel_ret_1m': rel_1m,
            'kospi_ret_3m': kospi_3m, 'sp500_ret_3m': sp500_3m, 'rel_ret_3m': rel_3m,
            'kospi_ret_1y': kospi_1y, 'sp500_ret_1y': sp500_1y, 'rel_ret_1y': rel_1y,
            'kospi_current': round(float(df['KOSPI'].iloc[-1]), 2),
            'sp500_current': round(float(df['SP500'].iloc[-1]), 2)
        }
    except Exception as e:
        print(f"[오류] 상대 수익률: {e}")
        return {
            'kospi_ret_1m': None, 'sp500_ret_1m': None, 'rel_ret_1m': None,
            'kospi_ret_3m': None, 'sp500_ret_3m': None, 'rel_ret_3m': None,
            'kospi_ret_1y': None, 'sp500_ret_1y': None, 'rel_ret_1y': None,
            'kospi_current': None, 'sp500_current': None
        }


# ─────────────────────────────────────────
# 3. 원/달러 환율 월간 변동폭
# ─────────────────────────────────────────
def get_krw_monthly_volatility():
    try:
        close = _get_close_m('KRW=X', '3mo')
        if close.empty:
            return {'krw_current': None}

        # 월간 통계
        monthly = close.resample('ME').agg(['first', 'last', 'min', 'max', 'std'])

        if len(monthly) >= 2:
            last_month = monthly.iloc[-2]  # 완성된 지난달
            this_month = monthly.iloc[-1]  # 진행 중인 이번달

            return {
                'krw_last_month_open':   round(float(last_month['first']), 1),
                'krw_last_month_close':  round(float(last_month['last']), 1),
                'krw_last_month_high':   round(float(last_month['max']), 1),
                'krw_last_month_low':    round(float(last_month['min']), 1),
                'krw_last_month_range':  round(float(last_month['max']) - float(last_month['min']), 1),
                'krw_last_month_ret':    round((float(last_month['last']) / float(last_month['first']) - 1) * 100, 2),
                'krw_current':           round(float(close.iloc[-1]), 1),
                'krw_3m_high':           round(float(close.max()), 1),
                'krw_3m_low':            round(float(close.min()), 1)
            }
        else:
            return {'krw_current': round(float(close.iloc[-1]), 1)}

    except Exception as e:
        print(f"[오류] 환율 월간 변동성: {e}")
        return {'krw_current': None}


# ─────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────
def collect_all_monthly(app_key=None, app_secret=None, access_token=None):
    print("[월간 수집 시작]", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    data = {}

    print("  종목 외국인 지분율 수집 중...")
    stocks = get_stock_foreign_monthly(app_key, app_secret, access_token)
    data['monthly_stocks'] = stocks

    print("  KOSPI/S&P500 상대 수익률 수집 중...")
    data.update(get_relative_performance(app_key=app_key, app_secret=app_secret, access_token=access_token))
    time.sleep(0.5)

    print("  환율 월간 변동폭 수집 중...")
    data.update(get_krw_monthly_volatility())

    data['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("[월간 수집 완료]")
    return data


if __name__ == '__main__':
    result = collect_all_monthly()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
