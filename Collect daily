"""
collect_daily.py
Daily 지표 수집 모듈 (10개 지표)
- VIX / VVIX
- Put/Call Ratio
- HYG/LQD 스프레드
- DXY 모멘텀
- 공포탐욕지수 (CNN)
- 외국인 코스피 순매수 TOP5
- 기관 코스피 순매수 TOP5
- 삼성전자 외국인 수급
- SK하이닉스 외국인 수급
- 원/달러 환율 + 일간 변화율
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import json


# ─────────────────────────────────────────
# 1. VIX / VVIX
# ─────────────────────────────────────────
def get_vix_vvix():
    result = {}
    for name, ticker in [('VIX', '^VIX'), ('VVIX', '^VVIX')]:
        try:
            data = yf.download(ticker, period='5d', progress=False, auto_adjust=True)
            if data.empty:
                result[name] = None
                continue
            close = data['Close'].dropna()
            result[name] = round(float(close.iloc[-1]), 2)
            result[f'{name}_prev'] = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        except Exception as e:
            print(f"[오류] {ticker}: {e}")
            result[name] = None
            result[f'{name}_prev'] = None

    # 변화량 계산
    if result.get('VIX') and result.get('VIX_prev'):
        result['VIX_chg'] = round(result['VIX'] - result['VIX_prev'], 2)
    else:
        result['VIX_chg'] = None

    if result.get('VVIX') and result.get('VVIX_prev'):
        result['VVIX_chg'] = round(result['VVIX'] - result['VVIX_prev'], 2)
    else:
        result['VVIX_chg'] = None

    return result


# ─────────────────────────────────────────
# 2. Put/Call Ratio
# ─────────────────────────────────────────
def get_put_call_ratio():
    try:
        data = yf.download('^PCCE', period='5d', progress=False, auto_adjust=True)
        if data.empty:
            return {'PC_ratio': None, 'PC_ratio_prev': None}
        close = data['Close'].dropna()
        return {
            'PC_ratio': round(float(close.iloc[-1]), 2),
            'PC_ratio_prev': round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        }
    except Exception as e:
        print(f"[오류] Put/Call Ratio: {e}")
        return {'PC_ratio': None, 'PC_ratio_prev': None}


# ─────────────────────────────────────────
# 3. HYG/LQD 스프레드
# ─────────────────────────────────────────
def get_hyg_lqd():
    try:
        result = {}
        for ticker in ['HYG', 'LQD']:
            data = yf.download(ticker, period='10d', progress=False, auto_adjust=True)
            close = data['Close'].dropna()
            result[ticker] = close

        ratio_series = result['HYG'] / result['LQD']
        ratio_series = ratio_series.dropna()

        current = round(float(ratio_series.iloc[-1]), 4)
        prev    = round(float(ratio_series.iloc[-2]), 4) if len(ratio_series) >= 2 else None
        chg_pct = round((current - prev) / prev * 100, 2) if prev else None

        # 5일 연속 하락 여부
        if len(ratio_series) >= 5:
            last5 = ratio_series.iloc[-5:].values
            consecutive_drop = all(last5[i] > last5[i+1] for i in range(4))
        else:
            consecutive_drop = False

        return {
            'HYG_LQD_ratio': current,
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
        data = yf.download('DX-Y.NYB', period='10d', progress=False, auto_adjust=True)
        close = data['Close'].dropna()
        current = round(float(close.iloc[-1]), 2)
        prev    = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        d1_chg  = round((current - prev) / prev * 100, 2) if prev else None

        val_5d  = round(float(close.iloc[-6]), 2) if len(close) >= 6 else None
        d5_chg  = round((current - val_5d) / val_5d * 100, 2) if val_5d else None

        return {
            'DXY': current,
            'DXY_1d_chg': d1_chg,
            'DXY_5d_chg': d5_chg
        }
    except Exception as e:
        print(f"[오류] DXY: {e}")
        return {'DXY': None, 'DXY_1d_chg': None, 'DXY_5d_chg': None}


# ─────────────────────────────────────────
# 5. 공포탐욕지수 (CNN)
# ─────────────────────────────────────────
def get_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        score = round(data['fear_and_greed']['score'], 1)
        rating = data['fear_and_greed']['rating']
        prev_close = round(data['fear_and_greed']['previous_close'], 1)

        # 한국어 변환
        rating_map = {
            'Extreme Fear':  '극단적 공포',
            'Fear':          '공포',
            'Neutral':       '중립',
            'Greed':         '탐욕',
            'Extreme Greed': '극단적 탐욕'
        }
        rating_kr = rating_map.get(rating, rating)

        return {
            'FG_score': score,
            'FG_rating': rating_kr,
            'FG_prev': prev_close
        }
    except Exception as e:
        print(f"[오류] Fear&Greed: {e}")
        return {'FG_score': None, 'FG_rating': None, 'FG_prev': None}


# ─────────────────────────────────────────
# 6~7. 외국인/기관 코스피 순매수 TOP5
# 8~9. 삼성전자/SK하이닉스 외국인 수급
# ─────────────────────────────────────────
def get_korea_investor_data(app_key, app_secret, access_token):
    """
    한국투자증권 Open API 사용
    access_token은 매일 발급 필요 (유효기간 24시간)
    """
    BASE_URL = "https://openapi.koreainvestment.com:9443"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPTJ04400000",
        "content-type": "application/json"
    }

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

    # 삼성전자(005930) + SK하이닉스(000660) 외국인 보유 현황
    for stock_code, key in [('005930', 'samsung_foreign'), ('000660', 'hynix_foreign')]:
        try:
            h = headers.copy()
            h['tr_id'] = 'FHKST01010100'
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
                    'price':          int(output.get('stck_prpr', 0).replace(',', '')),
                    'foreign_rate':   output.get('hts_frgn_ehrt', '0'),   # 외국인 보유율
                    'foreign_net_buy': output.get('frgn_ntby_qty', '0'),  # 당일 외국인 순매수
                    'change_rate':    output.get('prdy_ctrt', '0')         # 전일 대비 등락률
                }
            time.sleep(0.3)
        except Exception as e:
            print(f"[오류] {stock_code} 수급: {e}")

    return result


# ─────────────────────────────────────────
# 10. 원/달러 환율
# ─────────────────────────────────────────
def get_krw_usd():
    try:
        data = yf.download('KRW=X', period='10d', progress=False, auto_adjust=True)
        close = data['Close'].dropna()
        current = round(float(close.iloc[-1]), 1)
        prev    = round(float(close.iloc[-2]), 1) if len(close) >= 2 else None
        chg_pct = round((current - prev) / prev * 100, 2) if prev else None

        val_5d  = round(float(close.iloc[-6]), 1) if len(close) >= 6 else None
        chg_5d  = round((current - val_5d) / val_5d * 100, 2) if val_5d else None

        # KOSPI와 괴리 계산용
        kospi_data = yf.download('^KS11', period='10d', progress=False, auto_adjust=True)
        kospi_close = kospi_data['Close'].dropna()
        kospi_current = round(float(kospi_close.iloc[-1]), 2)
        kospi_prev    = round(float(kospi_close.iloc[-2]), 2) if len(kospi_close) >= 2 else None
        kospi_chg_pct = round((kospi_current - kospi_prev) / kospi_prev * 100, 2) if kospi_prev else None

        # 괴리 시나리오 판단
        # 환율 상승(원화 약세) + KOSPI 버팀 = 위험 신호
        divergence_warning = False
        if chg_pct and kospi_chg_pct:
            if chg_pct > 0.5 and kospi_chg_pct > -0.3:
                divergence_warning = True

        return {
            'KRW': current,
            'KRW_1d_chg': chg_pct,
            'KRW_5d_chg': chg_5d,
            'KOSPI': kospi_current,
            'KOSPI_1d_chg': kospi_chg_pct,
            'KRW_KOSPI_divergence': divergence_warning
        }
    except Exception as e:
        print(f"[오류] 환율/KOSPI: {e}")
        return {
            'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
            'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
        }


# ─────────────────────────────────────────
# 전체 수집 실행
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

    # 한국투자증권 API가 설정된 경우에만 수집
    if app_key and app_secret and access_token:
        print("  한국 수급 데이터 수집 중...")
        korea_data = get_korea_investor_data(app_key, app_secret, access_token)
        data.update(korea_data)
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
