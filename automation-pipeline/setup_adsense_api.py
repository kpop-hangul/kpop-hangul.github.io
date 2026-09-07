#!/usr/bin/env python3
"""
구글 애드센스(Google AdSense Management API v2) 인증 도우미 스크립트
애드센스 승인 후 실제 구글 계정의 수익 데이터를 자동으로 가져올 수 있도록
OAuth2 토큰(adsense_token.json)을 안전하게 생성합니다.
"""

import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/adsense.readonly']

def main():
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "config"))
    client_secrets_file = os.path.join(config_dir, "client_secret.json")
    token_file = os.path.join(config_dir, "adsense_token.json")

    print("=" * 60)
    print("🔑 [Google AdSense API] 실시간 수익 연동 인증 도우미")
    print("=" * 60)

    if not os.path.exists(client_secrets_file):
        print("\n⚠️ 'client_secret.json' 파일이 config/ 디렉토리에 없습니다.")
        print("📌 설정 절차:")
        print("  1. Google Cloud Console(console.cloud.google.com) 접속")
        print("  2. 프로젝트 생성 후 'AdSense Management API' 검색 및 [사용 설정]")
        print("  3. [사용자 인증 정보] -> [사용자 인증 정보 만들기] -> [OAuth 클라이언트 ID]")
        print("  4. 애플리케이션 유형: '데스크톱 앱(Desktop App)' 선택")
        print("  5. 생성된 JSON 키를 다운로드하여 아래 경로에 저장:")
        print(f"     👉 {client_secrets_file}")
        print("  6. 이 스크립트를 다시 실행: python3 setup_adsense_api.py\n")
        return

    print("🌐 Google 로그인 및 AdSense 권한 승인 창을 시작합니다...")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
        creds = flow.run_local_server(port=8080)
        
        with open(token_file, 'w', encoding='utf-8') as f:
            f.write(creds.to_json())

        print("\n✅ AdSense API 연동 인증이 성공적으로 완료되었습니다!")
        print(f"📁 저장된 인증 토큰: {token_file}")
        print("🚀 이제 매일 저녁 19:00 수익 리포트가 실제 구글 정산 데이터로 전송됩니다.\n")
    except Exception as e:
        print(f"\n❌ 인증 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
