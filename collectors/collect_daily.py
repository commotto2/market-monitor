"""
collect_daily.py
Daily 지표 수집 모듈 (10개 지표)
yfinance 최신 버전 대응: data['Close'].squeeze() 사용
^PCCE 폐지 → ^CPC (CBOE Total Put/Call Ratio) 대체
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import json


def _get_close(ticker, period='5d'):
    """
    yfinance 단일 티커 종가 Series 반환 헬퍼
    최신 버전에서 DataFrame으로 반환되는 문제 해결
    """
    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if data.empty:
        return pd.Series(dtype=float)
    close = data['Close']
    # 단일 티커도 DataFrame으로 오는 경우 Series로 변환
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
                result[name] = None
                result[f'{name}_prev'] = None
                result[f'{name}_chg'] = None
                continue
            current = round(float(close.iloc[-1]), 2)
            prev    = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
            result[name]            = current
            result[f'{name}_prev']  = prev
            result[f'{name}_chg']   = round(current - prev, 2) if prev else None
        except Exception as e:
            print(f"[오류] {ticker}: {e}")
            result[name] = None
            result[f'{name}_prev'] = None
            result[f'{name}_chg']  = None
    return result


# ─────────────────────────────────────────
# 2. Put/Call Ratio
# ^PCCE 폐지 → ^CPC (CBOE Total) 또는 ^CPCE (Equity) 시도
# ─────────────────────────────────────────
def get_put_call_ratio():
    for ticker in ['^CPCE', '^CPC', '^PCALL']:
        try:
            close = _get_close(ticker, '5d')
            if close.empty:
                continue
            return {
                'PC_ratio':      round(float(close.iloc[-1]), 2),
                'PC_ratio_prev': round(float(close.iloc[-2]), 2) if len(close) >= 2 else None,
                'PC_ticker':     ticker
            }
        except Exception:
            continue
    print("[경고] Put/Call Ratio: 모든 티커 실패")
    return {'PC_ratio': None, 'PC_ratio_prev': None, 'PC_ticker': None}


# ─────────────────────────────────────────
# 3. HYG/LQD 스프레드
# ─────────────────────────────────────────
def get_hyg_lqd():
    try:
        hyg = _get_close('HYG', '15d')
        lqd = _get_close('LQD', '15d')

        # 공통 인덱스 정렬
        ratio = (hyg / lqd).dropna()
        if len(ratio) < 2:
            return {'HYG_LQD_ratio': None, 'HYG_LQD_chg_pct': None, 'HYG_LQD_5d_drop': False}

        current = round(float(ratio.iloc[-1]), 4)
        prev    = round(float(ratio.iloc[-2]), 4)
        chg_pct = round((current - prev) / prev * 100, 2)

        consecutive_drop = False
        if len(ratio) >= 5:
            last5 = ratio.iloc[-5:].values
            consecutive_drop = all(last5[i] > last5[i+1] for i in range(4))

        return {
            'HYG_LQD_ratio':   current,
            'HYG_LQD_chg_pct': chg_pct,
            'HYG_LQD_5d_drop': consecutive_drop
        }
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

        current = round(float(close.iloc[-1]), 2)
        prev    = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        d1_chg  = round((current - prev) / prev * 100, 2) if prev else None
        val_5d  = round(float(close.iloc[-6]), 2) if len(close) >= 6 else None
        d5_chg  = round((current - val_5d) / val_5d * 100, 2) if val_5d else None

        return {'DXY': current, 'DXY_1d_chg': d1_chg, 'DXY_5d_chg': d5_chg}
    except Exception as e:
        print(f"[오류] DXY: {e}")
        return {'DXY': None, 'DXY_1d_chg': None, 'DXY_5d_chg': None}


# ─────────────────────────────────────────
# 5. 공포탐욕지수 (CNN)
# ─────────────────────────────────────────
def get_fear_greed():
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "https://fear-and-greed-index.p.rapidapi.com/v1/fgi"
    ]
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        resp = requests.get(urls[0], headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        fg = data.get('fear_and_greed', {})
        score  = round(float(fg.get('score', 0)), 1)
        rating = fg.get('rating', '')
        prev   = round(float(fg.get('previous_close', 0)), 1)

        rating_map = {
            'Extreme Fear':  '극단적 공포',
            'Fear':          '공포',
            'Neutral':       '중립',
            'Greed':         '탐욕',
            'Extreme Greed': '극단적 탐욕'
        }
        return {
            'FG_score':  score,
            'FG_rating': rating_map.get(rating, rating),
            'FG_prev':   prev
        }
    except Exception as e:
        print(f"[오류] Fear&Greed: {e}")
        return {'FG_score': None, 'FG_rating': None, 'FG_prev': None}


# ─────────────────────────────────────────
# 6~7. 외국인/기관 코스피 순매수 TOP5
# 8~9. 삼성전자/SK하이닉스 외국인 수급
# ─────────────────────────────────────────
def get_korea_investor_data(app_key, app_secret, access_token):
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    result = {
        'foreign_buy_top5':  [],
        'foreign_sell_top5': [],
        'inst_buy_top5':     [],
        'inst_sell_top5':    [],
        'samsung_foreign':   None,
        'hynix_foreign':     None
    }

    # 외국인 순매수 상위
    try:
        headers = {
            "authorization": f"Bearer {access_token}",
            "appkey": app_key,
            "appsecret": app_secret,
            "tr_id": "FHPTJ04400000",
            "content-type": "application/json"
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code":  "20171",
            "fid_input_iscd":         "0000",
            "fid_trgt_cls_code":      "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_input_price_1":      "",
            "fid_input_price_2":      "",
            "fid_vol_cnt":            "",
            "fid_input_date_1":       ""
        }
        resp = requests.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/ranking/foreign-net-buy",
            headers=headers, params=params, timeout=10
        )
        data = resp.json()
        if data.get('rt_cd') == '0':
            for item in data.get('output', [])[:5]:
                result['foreign_buy_top5'].append({
                    'name':   item.get('hts_kor_isnm', ''),
                    'amount': item.get('frgn_ntby_qty', '0')
                })
    except Exception as e:
        print(f"[오류] 외국인 순매수: {e}")

    time.sleep(0.3)

    # 삼성전자/SK하이닉스 수급
    for stock_code, key in [('005930', 'samsung_foreign'), ('000660', 'hynix_foreign')]:
        try:
            h = {
                "authorization": f"Bearer {access_token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST01010100",
                "content-type": "application/json"
            }
            params = {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": stock_code
            }
            resp = requests.get(
                f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=h, params=params, timeout=10
            )
            data = resp.json()
            if data.get('rt_cd') == '0':
                output = data.get('output', {})
                result[key] = {
                    'price':             output.get('stck_prpr', 'N/A'),
                    'foreign_rate':      output.get('hts_frgn_ehrt', 'N/A'),
                    'foreign_net_buy':   output.get('frgn_ntby_qty', 'N/A'),
                    'change_rate':       output.get('prdy_ctrt', 'N/A')
                }
            time.sleep(0.3)
        except Exception as e:
            print(f"[오류] {stock_code}: {e}")

    return result


# ─────────────────────────────────────────
# 10. 원/달러 환율 + KOSPI
# ─────────────────────────────────────────
def get_krw_usd():
    try:
        krw   = _get_close('KRW=X', '15d')
        kospi = _get_close('^KS11', '15d')

        if krw.empty or kospi.empty:
            return {
                'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
                'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
            }

        krw_cur   = round(float(krw.iloc[-1]), 1)
        krw_prev  = round(float(krw.iloc[-2]), 1) if len(krw) >= 2 else None
        krw_1d    = round((krw_cur - krw_prev) / krw_prev * 100, 2) if krw_prev else None
        krw_5d    = round(float(krw.iloc[-6]), 1) if len(krw) >= 6 else None
        krw_5d_chg = round((krw_cur - krw_5d) / krw_5d * 100, 2) if krw_5d else None

        k_cur  = round(float(kospi.iloc[-1]), 2)
        k_prev = round(float(kospi.iloc[-2]), 2) if len(kospi) >= 2 else None
        k_1d   = round((k_cur - k_prev) / k_prev * 100, 2) if k_prev else None

        # 환율 급등 + KOSPI 버팀 = 괴리 경고
        divergence = bool(krw_1d and k_1d and krw_1d > 0.5 and k_1d > -0.3)

        return {
            'KRW':                 krw_cur,
            'KRW_1d_chg':          krw_1d,
            'KRW_5d_chg':          krw_5d_chg,
            'KOSPI':               k_cur,
            'KOSPI_1d_chg':        k_1d,
            'KRW_KOSPI_divergence': divergence
        }
    except Exception as e:
        print(f"[오류] 환율/KOSPI: {e}")
        return {
            'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
            'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
        }


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
            'foreign_buy_top5':  [],
            'foreign_sell_top5': [],
            'inst_buy_top5':     [],
            'inst_sell_top5':    [],
            'samsung_foreign':   None,
            'hynix_foreign':     None
        })

    data['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("[수집 완료]")
    return data


if __name__ == '__main__':
    result = collect_all()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
