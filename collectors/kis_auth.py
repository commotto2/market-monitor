"""
kis_auth.py
한국투자증권 Open API 인증 모듈
- Access Token 발급 (유효기간 24시간)
- GitHub Actions에서 매일 자동 발급
"""

import requests
import json
import os
from datetime import datetime


BASE_URL = "https://openapi.koreainvestment.com:9443"


def get_access_token(app_key, app_secret):
    """
    Access Token 발급
    매일 실행 시마다 새로 발급 (24시간 유효)
    """
    url = f"{BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    try:
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        token = data.get('access_token')
        if token:
            print(f"[KIS] Access Token 발급 성공 (만료: {data.get('access_token_token_expired', 'N/A')})")
            return token
        else:
            print(f"[KIS] Token 발급 실패: {data}")
            return None
    except Exception as e:
        print(f"[KIS] Token 발급 오류: {e}")
        return None


def get_kospi_index(app_key, app_secret, access_token):
    """
    코스피 지수 현재값 조회
    TR: FHKUP03500100 (국내업종기간별시세)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",  # 업종 현재가 (단순 조회)
        "content-type": "application/json"
    }
    params = {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd":         "0001"   # 0001 = 코스피
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        print(f"[KIS] 코스피 전체응답: {str(data)[:300]}")
        if data.get('rt_cd') == '0':
            output = data.get('output', {})
            # 필드명 후보 순서대로 시도
            current = None
            for key in ['bstp_nmix_prpr', 'stck_prpr', 'prpr']:
                if output.get(key):
                    try:
                        current = float(str(output[key]).replace(',', ''))
                        break
                    except Exception:
                        continue
            chg_rt = None
            for key in ['bstp_nmix_prdy_ctrt', 'prdy_ctrt']:
                if output.get(key):
                    try:
                        chg_rt = float(str(output[key]).replace(',', ''))
                        break
                    except Exception:
                        continue
            if current:
                return {
                    'KOSPI':        round(current, 2),
                    'KOSPI_1d_chg': round(chg_rt, 2) if chg_rt else None,
                    'KOSPI_source': 'KIS'
                }
        print(f"[KIS] 코스피 조회 실패: {data.get('msg1', '')} / 전체응답: {str(data)[:200]}")
        return None
    except Exception as e:
        print(f"[KIS] 코스피 조회 오류: {e}")
        return None


def get_foreign_inst_top5(app_key, app_secret, access_token, investor='foreign'):
    """
    외국인 순매수 상위 5종목
    TR: FHKST01710000
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/ranking/foreign-net-buy"
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01710000",
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
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get('rt_cd') == '0':
            result = []
            for item in data.get('output', [])[:5]:
                result.append({
                    'name':   item.get('hts_kor_isnm', ''),
                    'code':   item.get('mksc_shrn_iscd', ''),
                    'amount': item.get('frgn_ntby_qty', '0'),
                    'amount_val': item.get('frgn_ntby_tr_pbmn', '0')  # 순매수 금액(백만)
                })
            return result
        else:
            print(f"[KIS] 수급 조회 실패: {data.get('msg1', '')}")
            return []
    except Exception as e:
        print(f"[KIS] 수급 조회 오류: {e}")
        return []


def get_stock_quote(app_key, app_secret, access_token, stock_code):
    """
    개별 종목 현재가 + 외국인 수급 조회
    stock_code: '005930' (삼성전자), '000660' (SK하이닉스)
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
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
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get('rt_cd') == '0':
            o = data.get('output', {})
            return {
                'price':           o.get('stck_prpr', 'N/A'),
                'change_rate':     o.get('prdy_ctrt', 'N/A'),
                'foreign_rate':    o.get('hts_frgn_ehrt', 'N/A'),
                'foreign_net_buy': o.get('frgn_ntby_qty', 'N/A')
            }
        else:
            print(f"[KIS] {stock_code} 조회 실패: {data.get('msg1', '')}")
            return None
    except Exception as e:
        print(f"[KIS] {stock_code} 조회 오류: {e}")
        return None


if __name__ == '__main__':
    # 테스트
    key    = os.environ.get('KIS_APP_KEY', '')
    secret = os.environ.get('KIS_APP_SECRET', '')
    if not key or not secret:
        print("KIS_APP_KEY, KIS_APP_SECRET 환경변수 필요")
    else:
        token = get_access_token(key, secret)
        if token:
            kospi = get_kospi_index(key, secret, token)
            print("코스피:", kospi)
            sam = get_stock_quote(key, secret, token, '005930')
            print("삼성전자:", sam)
