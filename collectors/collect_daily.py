"""
collect_daily.py — v4
수정사항:
- KOSPI: yfinance ^KS11 사용, KIS API 설정 후 정확한 값으로 대체 예정
- Put/Call Ratio: CBOE 403 차단 → 제외 후 리포트에서 N/A 표시
- Fear&Greed rating 소문자 비교 유지
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import time
import json


def _get_close(ticker, period='5d'):
    """yfinance 단일 티커 종가 Series 반환"""
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
# 2. Put/Call Ratio — 현재 수집 불가
# CBOE: GitHub Actions IP 차단
# yfinance: 관련 티커 전부 폐지
# → N/A 처리, 향후 대체 소스 확보 시 업데이트
# ─────────────────────────────────────────
def get_put_call_ratio():
    return {'PC_ratio': None, 'PC_ratio_prev': None, 'PC_ticker': 'N/A (수집 불가)'}


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
        cur  = round(float(close.iloc[-1]), 2)
        prev = round(float(close.iloc[-2]), 2) if len(close) >= 2 else None
        d1   = round((cur - prev) / prev * 100, 2) if prev else None
        v5   = round(float(close.iloc[-6]), 2) if len(close) >= 6 else None
        d5   = round((cur - v5) / v5 * 100, 2) if v5 else None
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
        fg     = resp.json().get('fear_and_greed', {})
        score  = round(float(fg.get('score', 0)), 1)
        rating = str(fg.get('rating', '')).strip().lower()
        prev   = round(float(fg.get('previous_close', 0)), 1)
        rating_map = {
            'extreme fear': '극단적 공포', 'fear': '공포',
            'neutral': '중립', 'greed': '탐욕', 'extreme greed': '극단적 탐욕'
        }
        return {'FG_score': score, 'FG_rating': rating_map.get(rating, rating), 'FG_prev': prev}
    except Exception as e:
        print(f"[오류] Fear&Greed: {e}")
        return {'FG_score': None, 'FG_rating': None, 'FG_prev': None}


# ─────────────────────────────────────────
# 6~9. 한국투자증권 API
# ─────────────────────────────────────────
def get_korea_investor_data(app_key, app_secret, access_token):
    """KIS API로 외국인/기관 수급 + 개별종목 조회"""
    from collectors.kis_auth import (
        get_foreign_inst_top5, get_stock_quote
    )

    result = {
        'foreign_buy_top5': [], 'foreign_sell_top5': [],
        'inst_buy_top5':    [], 'inst_sell_top5':    [],
        'samsung_foreign':  None, 'hynix_foreign':   None
    }

    # 외국인 순매수 TOP5
    top5 = get_foreign_inst_top5(app_key, app_secret, access_token, 'foreign')
    result['foreign_buy_top5'] = top5
    time.sleep(0.3)

    # 삼성전자 / SK하이닉스
    for code, key in [('005930', 'samsung_foreign'), ('000660', 'hynix_foreign')]:
        result[key] = get_stock_quote(app_key, app_secret, access_token, code)
        time.sleep(0.3)

    return result


# ─────────────────────────────────────────
# 10. 원/달러 환율 + KOSPI
# yfinance 이상값 자동 보정
# ─────────────────────────────────────────
def get_krw_usd():
    try:
        krw_raw   = _get_close('KRW=X', '15d')
        kospi_raw = _get_close('^KS11', '15d')

        if krw_raw.empty:
            return {
                'KRW': None, 'KRW_1d_chg': None, 'KRW_5d_chg': None,
                'KOSPI': None, 'KOSPI_1d_chg': None, 'KRW_KOSPI_divergence': False
            }

        krw_series   = krw_raw
        kospi_series = kospi_raw if not kospi_raw.empty else pd.Series(dtype=float)

        krw_cur  = round(float(krw_series.iloc[-1]), 1)
        krw_prev = round(float(krw_series.iloc[-2]), 1) if len(krw_series) >= 2 else None
        krw_1d   = round((krw_cur - krw_prev) / krw_prev * 100, 2) if krw_prev else None
        krw_5d_v = float(krw_series.iloc[-6]) if len(krw_series) >= 6 else None
        krw_5d   = round((krw_cur - krw_5d_v) / krw_5d_v * 100, 2) if krw_5d_v else None

        k_cur = k_1d = None
        if not kospi_series.empty:
            k_cur  = float(kospi_series.iloc[-1])
            k_prev = float(kospi_series.iloc[-2]) if len(kospi_series) >= 2 else None
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

    print("  환율 수집 중...")
    data.update(get_krw_usd())
    time.sleep(0.5)

    if app_key and app_secret and access_token:
        # KIS API: 코스피 지수 + 수급 데이터
        print("  [KIS] 코스피 지수 수집 중...")
        from collectors.kis_auth import get_access_token, get_kospi_index
        # Access Token이 없으면 자동 발급
        if not access_token:
            access_token = get_access_token(app_key, app_secret)
        if access_token:
            kospi_data = get_kospi_index(app_key, app_secret, access_token)
            if kospi_data:
                # KIS 코스피로 yfinance 값 덮어쓰기
                data['KOSPI']       = kospi_data['KOSPI']
                data['KOSPI_1d_chg'] = kospi_data['KOSPI_1d_chg']
                data['KOSPI_source'] = 'KIS'
                print(f"  [KIS] 코스피: {kospi_data['KOSPI']}")
        time.sleep(0.3)

        print("  [KIS] 한국 수급 데이터 수집 중...")
        data.update(get_korea_investor_data(app_key, app_secret, access_token))
    else:
        print("  [건너뜀] 한국투자증권 API 미설정 (KOSPI는 yfinance 값 사용)")
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
