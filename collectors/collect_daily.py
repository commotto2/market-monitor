"""
collect_daily.py  — v3
수정사항:
- _get_close() 헬퍼로 yfinance 멀티컬럼 문제 해결
- Put/Call Ratio: yfinance 티커 전부 폐지 → CBOE CSV 직접 수집으로 교체
- KOSPI: ^KS11 yfinance 버그 → pykrx 라이브러리로 교체 (pip install pykrx)
- 환율: yfinance KRW=X 유지 (정상 작동 확인)
- Fear&Greed rating 한국어 변환 수정
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import json
import io


# ─────────────────────────────────────────
# 헬퍼: yfinance 단일 티커 종가 Series 반환
# ─────────────────────────────────────────
def _get_close(ticker, period='5d'):
    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if data.empty:
        return pd.Series(dtype=float)
    close = data['Close']
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()
    return close.dropna()


# ─────────────────────────────────────────
# 1. VIX / VVIX
# ─────────────────────────────────────────
def get_vix_vvix():
    result = {}
    for name, ticker in [('VIX', '^VIX'), ('VVIX', '^VVIX')]:
        try:
            close = _get_close(ticker, '5d')
            if close.empty:
                result.update({name: None, f'{name}_prev': None, f'{name}_chg': None})
                continue
            cur  = round(float(close.iloc[-1]), 2)
            prev = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
            result[name]           = cur
            result[f'{name}_prev'] = prev
            result[f'{name}_chg']  = round(cur - prev, 2) if prev else None
        except Exception as e:
            print(f"[오류] {ticker}: {e}")
            result.update({name: None, f'{name}_prev': None, f'{name}_chg': None})
    return result


# ─────────────────────────────────────────
# 2. Put/Call Ratio — CBOE CSV 직접 수집
# ─────────────────────────────────────────
def get_put_call_ratio():
    """
    CBOE 일별 Put/Call Ratio CSV
    https://cdn.cboe.com/api/global/us_options_market_statistics/daily-market-statistics.csv
    컬럼: DATE, CALL, PUT, TOTAL, INDEX CALL, INDEX PUT, EQUITY CALL, EQUITY PUT
    Equity P/C = EQUITY PUT / EQUITY CALL
    """
    try:
        url = "https://cdn.cboe.com/api/global/us_options_market_statistics/daily-market-statistics.csv"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]

        # 최근 2일치
        df = df.tail(2).reset_index(drop=True)

        # Equity Put/Call Ratio 계산
        eq_put  = float(df.loc[1, 'EQUITY PUT'])
        eq_call = float(df.loc[1, 'EQUITY CALL'])
        ratio   = round(eq_put / eq_call, 2) if eq_call else None

        eq_put_prev  = float(df.loc[0, 'EQUITY PUT'])
        eq_call_prev = float(df.loc[0, 'EQUITY CALL'])
        ratio_prev   = round(eq_put_prev / eq_call_prev, 2) if eq_call_prev else None

        return {
            'PC_ratio':      ratio,
            'PC_ratio_prev': ratio_prev,
            'PC_ticker':     'CBOE Equity P/C'
        }
    except Exception as e:
        print(f"[오류] Put/Call Ratio (CBOE CSV): {e}")
        return {'PC_ratio': None, 'PC_ratio_prev': None, 'PC_ticker': None}


# ─────────────────────────────────────────
# 3. HYG/LQD 스프레드
# ─────────────────────────────────────────
def get_hyg_lqd():
    try:
        hyg = _get_close('HYG', '15d')
        lqd = _get_close('LQD', '15d')

        ratio = (hyg / lqd).dropna()
        if len(ratio) < 2:
            return {'HYG_LQD_ratio': None, 'HYG_LQD_chg_pct': None, 'HYG_LQD_5d_drop': False}

        cur  = round(float(ratio.iloc[-1]), 4)
        prev = round(float(ratio.iloc[-2]), 4)
        chg  = round((cur - prev) / prev * 100, 2)

        drop5 = False
        if len(ratio) >= 5:
            v = ratio.iloc[-5:].values
            drop5 = all(v[i] > v[i+1] for i in range(4))

        return {'HYG_LQD_ratio': cur, 'HYG_LQD_chg_pct': chg, 'HYG_LQD_5d_drop': drop5}
    except Exception as e:
        print(f"[오류] HYG/LQD: {e}")
        return {'HYG_LQD_ratio': None, 'HYG_LQD_chg_pct': None, 'HYG_LQD_5d_drop': False}


# ─────────────────────────────────────────
# 4. DXY 모멘텀
# ─────────────────────────────────────────
def get_dxy():
    try:
        close = _get_close('DX-Y.NYB', '15d')
        if close.empty:
            return {'DXY': None, 'DXY_1d_chg': None, 'DXY_5d_chg': None}

        cur   = round(float(close.iloc[-1]), 2)
        prev  = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        d1    = round((cur - prev) / prev * 100, 2) if prev else None
        v5    = round(float(close.iloc[-6]), 2) if len(close) >= 6 else None
        d5    = round((cur - v5) / v5 * 100, 2) if v5 else None

        return {'DXY': cur, 'DXY_1d_chg': d1, 'DXY_5d_chg': d5}
    except Exception as e:
        print(f"[오류] DXY: {e}")
        return {'DXY': None, 'DXY_1d_chg': None, 'DXY_5d_chg': None}


# ─────────────────────────────────────────
# 5. 공포탐욕지수 (CNN)
# ─────────────────────────────────────────
def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json',
            'Referer': 'https://edition.cnn.com/'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        fg     = data.get('fear_and_greed', {})
        score  = round(float(fg.get('score', 0)), 1)
        rating = str(fg.get('rating', '')).strip()
        prev   = round(float(fg.get('previous_close', 0)), 1)

        rating_map = {
            'extreme fear':  '극단적 공포',
            'fear':          '공포',
            'neutral':       '중립',
            'greed':         '탐욕',
            'extreme greed': '극단적 탐욕'
        }
        rating_kr = rating_map.get(rating.lower(), rating)

        return {'FG_score': score, 'FG_rating': rating_kr, 'FG_prev': prev}
    except Exception as e:
        print(f"[오류] Fear&Greed: {e}")
        return {'FG_score': None, 'FG_rating': None, 'FG_prev': None}


# ─────────────────────────────────────────
# 6~9. 한국투자증권 API (외국인/기관 수급)
# ─────────────────────────────────────────
def get_korea_investor_data(app_key, app_secret, access_token):
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    result = {
        'foreign_buy_top5': [], 'foreign_sell_top5': [],
        'inst_buy_top5':    [], 'inst_sell_top5':    [],
        'samsung_foreign':  None, 'hynix_foreign':   None
    }

    try:
        headers = {
            "authorization": f"Bearer {access_token}",
            "appkey": app_key, "appsecret": app_secret,
            "tr_id": "FHPTJ04400000", "content-type": "application/json"
        }
        params = {
            "fid_cond_mrkt_div_code": "J", "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000", "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0", "fid_input_price_1": "",
            "fid_input_price_2": "", "fid_vol_cnt": "", "fid_input_date_1": ""
        }
        resp = requests.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/ranking/foreign-net-buy",
            headers=headers, params=params, timeout=10
        )
        data = resp.json()
        if data.get('rt_cd') == '0':
            for item in data.get('output', [])[:5]:
                result['foreign_buy_top5'].append({
                    'name': item.get('hts_kor_isnm', ''),
                    'amount': item.get('frgn_ntby_qty', '0')
                })
    except Exception as e:
        print(f"[오류] 외국인 순매수: {e}")

    time.sleep(0.3)

    for code, key in [('005930', 'samsung_foreign'), ('000660', 'hynix_foreign')]:
        try:
            h = {
                "authorization": f"Bearer {access_token}",
                "appkey": app_key, "appsecret": app_secret,
                "tr_id": "FHKST01010100", "content-type": "application/json"
            }
            resp = requests.get(
                f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=h, params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
                timeout=10
            )
            out = resp.json().get('output', {})
            if resp.json().get('rt_cd') == '0':
                result[key] = {
                    'price':           out.get('stck_prpr', 'N/A'),
                    'foreign_rate':    out.get('hts_frgn_ehrt', 'N/A'),
                    'foreign_net_buy': out.get('frgn_ntby_qty', 'N/A'),
                    'change_rate':     out.get('prdy_ctrt', 'N/A')
                }
            time.sleep(0.3)
        except Exception as e:
            print(f"[오류] {code}: {e}")

    return result


# ─────────────────────────────────────────
# 10. 원/달러 환율 + KOSPI
# KOSPI: pykrx 우선, 실패 시 ^KS11 fallback
# ─────────────────────────────────────────
def get_krw_usd():
    try:
        # 환율: yfinance KRW=X (정상 작동)
        krw = _get_close('KRW=X', '15d')

        # KOSPI: pykrx 우선 시도
        kospi = _get_kospi_pykrx()

        # pykrx 실패 시 yfinance fallback
        if kospi is None or kospi.empty:
            print("  [KOSPI] pykrx 실패 → yfinance fallback")
            kospi = _get_close('^KS11', '15d')

        if krw.empty:
            return {
                'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
                'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
            }

        krw_cur  = round(float(krw.iloc[-1]), 1)
        krw_prev = round(float(krw.iloc[-2]), 1) if len(krw) >= 2 else None
        krw_1d   = round((krw_cur - krw_prev) / krw_prev * 100, 2) if krw_prev else None
        krw_5d_v = round(float(krw.iloc[-6]), 1) if len(krw) >= 6 else None
        krw_5d   = round((krw_cur - krw_5d_v) / krw_5d_v * 100, 2) if krw_5d_v else None

        k_cur = k_1d = None
        if kospi is not None and not kospi.empty:
            k_cur  = round(float(kospi.iloc[-1]), 2)
            k_prev = round(float(kospi.iloc[-2]), 2) if len(kospi) >= 2 else None
            k_1d   = round((k_cur - k_prev) / k_prev * 100, 2) if k_prev else None

        divergence = bool(krw_1d and k_1d and krw_1d > 0.5 and k_1d > -0.3)

        return {
            'KRW': krw_cur, 'KRW_1d_chg': krw_1d, 'KRW_5d_chg': krw_5d,
            'KOSPI': k_cur, 'KOSPI_1d_chg': k_1d,
            'KRW_KOSPI_divergence': divergence
        }
    except Exception as e:
        print(f"[오류] 환율/KOSPI: {e}")
        return {
            'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
            'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
        }


def _get_kospi_pykrx():
    """pykrx로 코스피 지수 수집 (정확한 값)"""
    try:
        from pykrx import stock
        today = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=20)).strftime('%Y%m%d')
        df = stock.get_index_ohlcv_by_date(start, today, "1001")  # 1001 = KOSPI
        if df.empty:
            return None
        close = df['종가']
        return close
    except Exception as e:
        print(f"  [KOSPI pykrx 오류] {e}")
        return None


# ─────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────
def collect_all(app_key=None, app_secret=None, access_token=None):
    print("[수집 시작]", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    data = {}

    print("  VIX/VVIX 수집 중...")
    data.update(get_vix_vvix())
    time.sleep(0.5)

    print("  Put/Call Ratio 수집 중...")
    data.update(get_put_call_ratio())
    time.sleep(0.5)

    print("  HYG/LQD 수집 중...")
    data.update(get_hyg_lqd())
    time.sleep(0.5)

    print("  DXY 수집 중...")
    data.update(get_dxy())
    time.sleep(0.5)

    print("  Fear&Greed 수집 중...")
    data.update(get_fear_greed())
    time.sleep(0.5)

    print("  환율/KOSPI 수집 중...")
    data.update(get_krw_usd())
    time.sleep(0.5)

    if app_key and app_secret and access_token:
        print("  한국 수급 데이터 수집 중...")
        data.update(get_korea_investor_data(app_key, app_secret, access_token))
    else:
        print("  [건너뜀] 한국투자증권 API 미설정")
        data.update({
            'foreign_buy_top5': [], 'foreign_sell_top5': [],
            'inst_buy_top5':    [], 'inst_sell_top5':    [],
            'samsung_foreign':  None, 'hynix_foreign':   None
        })

    data['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("[수집 완료]")
    return data


if __name__ == '__main__':
    result = collect_all()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
