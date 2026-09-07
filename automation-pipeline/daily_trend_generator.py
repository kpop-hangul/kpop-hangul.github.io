#!/usr/bin/env python3
import os
import re
import json
from datetime import datetime
import google.generativeai as genai
from modules.news_crawler import GoogleNewsCrawler

# 구글 제미나이 API 키 (로컬 환경변수 또는 직접 입력)
# 이 스크립트를 GitHub Actions나 로컬에서 돌릴 때 GEMINI_API_KEY가 필요합니다.
api_key = os.environ.get("GEMINI_API_KEY", "")
if api_key:
    genai.configure(api_key=api_key)

BLOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../blog-frontend/src/content/blog"))
os.makedirs(BLOG_DIR, exist_ok=True)

def generate_trend_post(keyword="AI"):
    crawler = GoogleNewsCrawler()
    print(f"[{keyword}] 구글 뉴스 크롤링 중...")
    news_items = crawler.fetch_top_news(keyword, num_articles=5)
    
    if not news_items:
        print("뉴스를 가져오지 못했습니다.")
        return False
        
    context_text = "\n\n".join([f"제목: {n['title']}\n요약: {n['summary']}" for n in news_items])
    
    prompt = f"""
당신은 기술 및 트렌드 전문 IT 블로거입니다. 
다음은 오늘자 최신 구글 뉴스 내용입니다. 이를 바탕으로 팩트에 기반한 블로그 포스팅 1개를 작성해주세요.

[오늘의 최신 뉴스]
{context_text}

[작성 조건]
1. 허위 사실(환각)을 절대 지어내지 말고, 주어진 뉴스 내용(팩트)에 기반하여 작성하세요.
2. 블로그 글의 Markdown 본문만 출력하세요 (프론트매터 포함). 
3. 프론트매터(Frontmatter)는 아래 형식을 정확히 준수하세요.
4. 글 내용은 IT/비즈니스 트렌드에 관심 있는 20~40대 직장인을 타겟으로 통찰력 있게 작성하세요.
5. Markdown 내부에는 H2, H3 태그, 글머리 기호, 필요시 Mermaid 다이어그램이나 표를 포함하여 가독성을 높이세요.

[프론트매터 포맷]
---
title: "기사들을 종합한 매력적인 제목 작성"
description: "검색 엔진에 노출될 매력적인 요약문 2문장"
pubDate: {datetime.now().strftime("%Y-%m-%d")}
category: "AI & 생산성"
tags: ['{keyword}', '최신트렌드', '기술동향', 'IT뉴스']
author: "앱시안 (absian)"
readingTime: "5 min read"
featured: false
draft: false
faqs:
  - question: "독자가 궁금해할 질문 1"
    answer: "질문 1에 대한 팩트 기반 답변"
  - question: "독자가 궁금해할 질문 2"
    answer: "질문 2에 대한 팩트 기반 답변"
---

블로그 본문 작성 시작:
"""
    
    if not api_key:
        print("GEMINI_API_KEY 환경변수가 설정되지 않아 테스트 더미 데이터를 생성합니다.")
        md_content = f"""---
title: "[테스트] {keyword} 최신 트렌드 요약"
description: "GEMINI_API_KEY가 없어서 테스트로 생성된 글입니다."
pubDate: {datetime.now().strftime("%Y-%m-%d")}
category: "AI & 생산성"
tags: ['{keyword}', '테스트']
author: "앱시안 (absian)"
readingTime: "2 min read"
featured: false
draft: false
faqs:
  - question: "이 글은 어떻게 생성되었나요?"
    answer: "테스트 스크립트에 의해 자동 생성되었습니다."
---

## 오늘의 뉴스 요약 (테스트)
{context_text}

본문을 정상적으로 AI로 생성하려면 `export GEMINI_API_KEY="본인키"`를 설정하고 실행하세요.
"""
    else:
        print("Gemini AI를 통한 아티클 생성 중...")
        # 최신 모델 사용
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        md_content = response.text

    # 코드 블록 마크다운이 섞여있다면 제거 (```markdown ... ``` 제거)
    md_content = re.sub(r"^```(markdown|md)?\s*", "", md_content)
    md_content = re.sub(r"\s*```$", "", md_content).strip()

    # 제목 추출해서 파일명 생성
    title_match = re.search(r'title:\s*"([^"]+)"', md_content)
    if title_match:
        safe_title = re.sub(r'[^a-zA-Z0-9가-힣]', '-', title_match.group(1).lower())
        safe_title = re.sub(r'-+', '-', safe_title).strip('-')
        filename = f"{datetime.now().strftime('%Y-%m-%d')}-{safe_title[:30]}.md"
    else:
        filename = f"{datetime.now().strftime('%Y-%m-%d')}-trend-{keyword}.md"

    filepath = os.path.join(BLOG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content + "\n")
        
    print(f"✅ 포스팅 생성 완료: {filepath}")
    return filepath

if __name__ == "__main__":
    generate_trend_post("인공지능")
