#!/usr/bin/env python3
"""
고단가 롱테일 키워드 큐(keywords.csv) 관리 CLI 도구
사용법:
  python3 manage_keywords.py list          # 대기 중/발행된 키워드 목록 조회
  python3 manage_keywords.py stats         # 키워드 큐 통계 요약
  python3 manage_keywords.py add "키워드" "카테고리" "예상CPC" "의도"
"""

import os
import sys
import csv

CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "keywords.csv"))

def get_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def list_keywords():
    rows = get_rows()
    print("=" * 80)
    print(f"📋 [고단가 키워드 큐 목록] 총 {len(rows)}개")
    print("=" * 80)
    print(f"{'상태':<8} | {'예상CPC':<7} | {'카테고리':<15} | {'키워드'}")
    print("-" * 80)
    for r in rows:
        status_icon = "⏳ READY" if r.get("status") == "ready" else "✅ DONE"
        cpc = f"${r.get('estimated_cpc', '0.0')}"
        category = r.get("category", "")[:12]
        keyword = r.get("keyword", "")
        print(f"{status_icon:<8} | {cpc:<7} | {category:<15} | {keyword}")
    print("=" * 80)

def stats_keywords():
    rows = get_rows()
    ready = [r for r in rows if r.get("status") == "ready"]
    published = [r for r in rows if r.get("status") == "published"]
    print("=" * 50)
    print("📊 [키워드 큐 현황 요약]")
    print("=" * 50)
    print(f"  • 총 등록 키워드: {len(rows)}개")
    print(f"  • ⏳ 발행 대기(Ready): {len(ready)}개")
    print(f"  • ✅ 발행 완료(Published): {len(published)}개")
    if ready:
        avg_cpc = sum(float(r.get("estimated_cpc", 0) or 0) for r in ready) / len(ready)
        print(f"  • 💵 대기 키워드 평균 예상 CPC: ${avg_cpc:.2f}")
    print("=" * 50)

def add_keyword(keyword, category="스마트 부업 & 재테크", cpc="2.5", intent="정보성"):
    rows = get_rows()
    # 중복 체크
    for r in rows:
        if r.get("keyword") == keyword:
            print(f"⚠️ 이미 등록된 키워드입니다: '{keyword}' (상태: {r.get('status')})")
            return

    new_row = {
        "keyword": keyword,
        "category": category,
        "estimated_cpc": cpc,
        "search_intent": intent,
        "status": "ready",
        "published_date": "",
        "post_slug": ""
    }

    fieldnames = ["keyword", "category", "estimated_cpc", "search_intent", "status", "published_date", "post_slug"]
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(new_row)
    print(f"✅ 새 키워드 추가 완료: '{keyword}' (${cpc}, {category})")

def main():
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        list_keywords()
    elif sys.argv[1] == "stats":
        stats_keywords()
    elif sys.argv[1] == "add":
        if len(sys.argv) < 3:
            print("사용법: python3 manage_keywords.py add \"키워드\" [카테고리] [예상CPC] [검색의도]")
            return
        kw = sys.argv[2]
        cat = sys.argv[3] if len(sys.argv) > 3 else "스마트 부업 & 재테크"
        cpc = sys.argv[4] if len(sys.argv) > 4 else "2.5"
        intent = sys.argv[5] if len(sys.argv) > 5 else "정보성"
        add_keyword(kw, cat, cpc, intent)
    else:
        print("명령어: list, stats, add")

if __name__ == "__main__":
    main()
