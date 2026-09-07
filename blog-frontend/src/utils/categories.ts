import { getCollection } from 'astro:content';
import { getCategorySlug, getCategoryName } from './slug';

export interface CategoryInfo {
  name: string;
  slug: string;
  count: number;
  href: string;
}

export interface CategoryMenuData {
  primaryCategories: CategoryInfo[];   // 상위 대표 카테고리 (글 개수 기준 상위 N개)
  secondaryCategories: CategoryInfo[]; // 기타/추가 서브 카테고리 (글 수가 적거나 신규 추가된 카테고리)
  allCategories: CategoryInfo[];       // 전체 카테고리 목록
  totalPosts: number;
}

/**
 * 모든 블로그 포스트를 스캔하여 동적으로 카테고리를 추출하고
 * 대표 카테고리(상단 노출)와 기타 카테고리(더보기 드롭다운)로 분류합니다.
 * @param topLimit 상단 네비게이션에 단독 노출할 대표 카테고리 최대 개수 (기본값: 3)
 */
export async function getDynamicCategories(topLimit = 3): Promise<CategoryMenuData> {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');

  const allPosts = await getCollection('blog', ({ data }) => {
    return import.meta.env.PROD ? !data.draft : true;
  });

  const countMap: Record<string, { rawName: string; count: number }> = {};

  for (const post of allPosts) {
    const rawCat = (post.data.category || '일반 테크').trim();
    const slug = getCategorySlug(rawCat);

    if (!countMap[slug]) {
      countMap[slug] = { rawName: rawCat, count: 0 };
    }
    countMap[slug].count++;
  }

  // 글 개수가 많은 순서대로 내림차순 정렬
  const sortedSlugs = Object.keys(countMap).sort((a, b) => countMap[b].count - countMap[a].count);

  const allCategories: CategoryInfo[] = sortedSlugs.map(slug => ({
    slug,
    name: getCategoryName(slug, countMap[slug].rawName),
    count: countMap[slug].count,
    href: `${base}/categories/${slug}/`,
  }));

  const primaryCategories = allCategories.slice(0, topLimit);
  const secondaryCategories = allCategories.slice(topLimit);

  return {
    primaryCategories,
    secondaryCategories,
    allCategories,
    totalPosts: allPosts.length,
  };
}
