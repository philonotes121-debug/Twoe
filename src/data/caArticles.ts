export interface CaArticle {
  id: string;
  title: string;
  summary: string;
  dataset: 'daily' | 'editorial' | 'place_news' | 'international';
  source: string;
  date: string;
  topic: string;
  url?: string;
  tags?: string;
  location?: string;
  organisation?: string;
}

export const CA_ARTICLES: CaArticle[] = [];