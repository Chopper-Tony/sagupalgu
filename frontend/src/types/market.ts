export interface MarketItem {
  session_id: string;
  title: string;
  description: string;
  price: number;
  image_urls: string[];
  tags: string[];
  published_platforms: string[];
  created_at: string | null;
}

export interface MarketListResponse {
  items: MarketItem[];
  total: number;
  limit: number;
  offset: number;
}
