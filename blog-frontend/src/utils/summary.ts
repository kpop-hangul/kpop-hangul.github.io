/**
 * 아티클의 본문 또는 description에서 제목 반복을 제거하고
 * 독자에게 유용한 실제 글 내용 첫 부분(서론 요약)을 추출하는 유틸리티
 */
export function getPostSummary(post: { body?: string; data: { title: string; description?: string } }): string {
  const title = (post.data.title || '').trim();
  const rawDesc = (post.data.description || '').trim();

  // 1. 마크다운 본문(body)이 존재하는 경우, 본문의 첫 번째 실질적 서론 문단 추출
  if (post.body) {
    const paragraphs = post.body.split(/\n\s*\n/);
    for (const paragraph of paragraphs) {
      const p = paragraph.trim();
      // 헤딩(#), 구분선(---), 이미지(![) 제외
      if (!p || p.startsWith('#') || p.startsWith('---') || p.startsWith('!') || p.startsWith('>')) {
        continue;
      }
      const clean = p
        .replace(/[*_#`\[\]]/g, '') // 마크다운 볼드, 이탤릭, 링크 괄호 제거
        .replace(/https?:\/\/\S+/g, '') // URL 링크 제거
        .trim();

      // 제목과 중복되지 않고 20자 이상인 서론 문장 선택
      if (clean.length >= 20 && !clean.startsWith(title) && !clean.includes(title.slice(0, 15))) {
        return clean.length > 130 ? clean.slice(0, 130) + '...' : clean;
      }
    }
  }

  // 2. description이 제목으로 시작하는 경우, 반복되는 제목 부분을 깔끔하게 제거
  if (rawDesc.startsWith(title)) {
    const stripped = rawDesc.slice(title.length).replace(/^[\s:에대한을위한의]+/, '').trim();
    if (stripped.length >= 15) {
      return stripped;
    }
  }

  return rawDesc || '실전 노하우와 유용한 팁을 담은 심층 테크 가이드입니다.';
}
