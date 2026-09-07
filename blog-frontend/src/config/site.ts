import defaultConfig from './blog.config.json';

export interface SiteConfig {
  blogId: string;
  site: {
    name: string;
    shortName: string;
    slogan: string;
    description: string;
    url: string;
    basePath: string;
    author: string;
  };
  categories: {
    primary: string[];
    topLimit: number;
  };
  seo: {
    naverVerification: string;
    googleVerification: string;
    gaId: string;
  };
  monetization: {
    adsenseClientId: string;
    adfitUnitId: string;
    coupangPartnersId: string;
    gumroadUrl: string;
  };
  telegram: {
    botUsername: string;
  };
  ai: {
    provider: string;
    model: string;
    tone: string;
  };
}

export const siteConfig: SiteConfig = defaultConfig;
export default siteConfig;
