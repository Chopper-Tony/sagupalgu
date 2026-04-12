export type SaleStatus = "available" | "reserved" | "sold";

export interface MarketItem {
  session_id: string;
  title: string;
  description: string;
  price: number;
  image_urls: string[];
  tags: string[];
  published_platforms: string[];
  sale_status: SaleStatus;
  category: string;
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
  sale_status: SaleStatus;
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
  category?: string;
  limit?: number;
  offset?: number;
}

// 판매자 대시보드용
export interface MyListingItem extends MarketItem {
  inquiry_count: number;
  unread_inquiry_count: number;
}

export interface InquiryItem {
  id: string;
  listing_id: string;
  listing_title: string;
  listing_price: number;
  thumbnail_url: string;
  buyer_name: string;
  buyer_contact: string;
  message: string;
  reply: string | null;
  status: "open" | "replied" | "closed";
  is_read: boolean;
  last_reply_at: string | null;
  created_at: string;
}
