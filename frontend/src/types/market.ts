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

export interface MarketDetailItem {
  session_id: string;
  title: string;
  description: string;
  price: number;
  image_urls: string[];
  tags: string[];
  platform_links: PlatformLink[];
  created_at: string | null;
}

export interface PlatformLink {
  platform: string;
  url: string;
}

export interface InquiryRequest {
  name: string;
  contact: string;
  message: string;
}

export interface MarketSearchParams {
  q?: string;
  min_price?: number;
  max_price?: number;
  limit?: number;
  offset?: number;
}
