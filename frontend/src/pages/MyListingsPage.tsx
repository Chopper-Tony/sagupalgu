import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import type { MyListingItem, InquiryItem, SaleStatus } from "../types/market";
import "./MyListingsPage.css";

const STATUS_LABEL: Record<SaleStatus, string> = {
  available: "판매중",
  reserved: "예약중",
  sold: "판매완료",
};

const STATUS_CLASS: Record<SaleStatus, string> = {
  available: "my-listings__status--available",
  reserved: "my-listings__status--reserved",
  sold: "my-listings__status--sold",
};

export function MyListingsPage() {
  const [items, setItems] = useState<MyListingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<SaleStatus | "all">("all");

  // 문의 관리 상태
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [inquiries, setInquiries] = useState<InquiryItem[]>([]);
  const [inquiryLoading, setInquiryLoading] = useState(false);
  const [replyText, setReplyText] = useState<Record<string, string>>({});
  const [replySending, setReplySending] = useState<string | null>(null);
  const [aiSuggesting, setAiSuggesting] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const filterParam = filter === "all" ? undefined : filter;
      const res = await api.getMyListings(filterParam);
      setItems(res.items);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleStatusChange = async (sessionId: string, newStatus: SaleStatus) => {
    try {
      await api.updateSaleStatusMarket(sessionId, newStatus);
      // 판매 완료 시 축하 메시지
      if (newStatus === "sold") {
        alert("판매 완료를 축하합니다! 비슷한 상품을 재등록해보세요.");
      }
      fetchItems();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("409")) {
        alert("현재 상태에서 해당 전이가 불가능합니다.");
      } else {
        alert("상태 변경에 실패했습니다.");
      }
    }
  };

  const handleRelist = async (sessionId: string) => {
    if (!confirm("이 상품을 재등록하시겠습니까?")) return;
    try {
      const res = await api.relistListing(sessionId);
      alert("재등록 완료! 새 상품이 마켓에 등록되었습니다.");
      fetchItems();
      if (res.new_session?.session_id) {
        window.location.hash = `#/market/${res.new_session.session_id}`;
      }
    } catch {
      alert("재등록에 실패했습니다.");
    }
  };

  const handleSuggestReply = async (sessionId: string, inquiryId: string) => {
    setAiSuggesting(inquiryId);
    try {
      const res = await api.suggestReply(sessionId, inquiryId);
      setReplyText((prev) => ({ ...prev, [inquiryId]: res.suggested_reply }));
    } catch {
      alert("AI 답변 생성에 실패했습니다. 직접 작성해주세요.");
    } finally {
      setAiSuggesting(null);
    }
  };

  const handleOpenInquiries = async (sessionId: string) => {
    if (selectedItem === sessionId) {
      setSelectedItem(null);
      return;
    }
    setSelectedItem(sessionId);
    setInquiryLoading(true);
    try {
      const res = await api.getInquiries(sessionId);
      setInquiries(res.inquiries);
    } catch {
      setInquiries([]);
    } finally {
      setInquiryLoading(false);
    }
  };

  const handleReply = async (sessionId: string, inquiryId: string) => {
    const text = replyText[inquiryId]?.trim();
    if (!text) return;
    setReplySending(inquiryId);
    try {
      await api.replyToInquiry(sessionId, inquiryId, text);
      setReplyText((prev) => ({ ...prev, [inquiryId]: "" }));
      // 문의 목록 새로고침
      const res = await api.getInquiries(sessionId);
      setInquiries(res.inquiries);
      fetchItems(); // unread 카운트 갱신
    } catch {
      alert("응답 전송에 실패했습니다.");
    } finally {
      setReplySending(null);
    }
  };

  return (
    <div className="my-listings">
      <div className="my-listings__header">
        <h1 className="my-listings__title">내 상품 관리</h1>
        <div className="my-listings__nav">
          <a href="#/market" className="my-listings__link">마켓</a>
          <a href="#/" className="my-listings__link">셀러 코파일럿</a>
        </div>
      </div>

      {/* 상태 필터 */}
      <div className="my-listings__filters">
        {(["all", "available", "reserved", "sold"] as const).map((f) => (
          <button
            key={f}
            className={`my-listings__filter-btn ${filter === f ? "my-listings__filter-btn--active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? "전체" : STATUS_LABEL[f]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="my-listings__loading">불러오는 중...</div>
      ) : items.length === 0 ? (
        <div className="my-listings__empty">
          <p>등록된 상품이 없습니다.</p>
          <a href="#/" className="my-listings__link">셀러 코파일럿에서 상품 등록하기</a>
        </div>
      ) : (
        <div className="my-listings__list">
          {items.map((item) => {
            const status = (item.sale_status || "available") as SaleStatus;
            return (
              <div key={item.session_id} className="my-listings__item">
                <div className="my-listings__item-main">
                  {/* 썸네일 */}
                  <div className="my-listings__thumb">
                    {item.image_urls[0] ? (
                      <img src={item.image_urls[0]} alt={item.title} />
                    ) : (
                      <div className="my-listings__no-thumb">-</div>
                    )}
                  </div>

                  {/* 상품 정보 */}
                  <div className="my-listings__info">
                    <h3 className="my-listings__item-title">
                      <a href={`#/market/${item.session_id}`}>{item.title || "제목 없음"}</a>
                    </h3>
                    <p className="my-listings__item-price">{item.price.toLocaleString()}원</p>
                    <span className={`my-listings__status ${STATUS_CLASS[status]}`}>
                      {STATUS_LABEL[status]}
                    </span>
                    <div className="my-listings__stats">
                      <span className="my-listings__stat">조회 {(item as any).view_count || 0}</span>
                      <span className="my-listings__stat">문의 {item.inquiry_count}</span>
                      {(item as any).market_position && (
                        <span className="my-listings__stat my-listings__stat--position">{(item as any).market_position}</span>
                      )}
                    </div>
                  </div>

                  {/* 문의 뱃지 + 액션 */}
                  <div className="my-listings__actions">
                    <button
                      className={`my-listings__inquiry-btn ${item.unread_inquiry_count > 0 ? "my-listings__inquiry-btn--unread" : ""}`}
                      onClick={() => handleOpenInquiries(item.session_id)}
                    >
                      문의 {item.inquiry_count}
                      {item.unread_inquiry_count > 0 && (
                        <span className="my-listings__unread-badge">{item.unread_inquiry_count}</span>
                      )}
                    </button>

                    {/* 상태 변경 버튼 */}
                    {status === "available" && (
                      <>
                        <button className="my-listings__action-btn" onClick={() => handleStatusChange(item.session_id, "reserved")}>예약</button>
                        <button className="my-listings__action-btn my-listings__action-btn--sold" onClick={() => handleStatusChange(item.session_id, "sold")}>판매완료</button>
                      </>
                    )}
                    {status === "reserved" && (
                      <>
                        <button className="my-listings__action-btn" onClick={() => handleStatusChange(item.session_id, "available")}>예약취소</button>
                        <button className="my-listings__action-btn my-listings__action-btn--sold" onClick={() => handleStatusChange(item.session_id, "sold")}>판매완료</button>
                      </>
                    )}
                    {status === "sold" && (
                      <button className="my-listings__action-btn my-listings__action-btn--relist" onClick={() => handleRelist(item.session_id)}>재등록</button>
                    )}
                  </div>
                </div>

                {/* 코파일럿 제안 */}
                {(item as any).copilot_suggestions?.length > 0 && (
                  <div className="my-listings__suggestions">
                    {(item as any).copilot_suggestions.map((s: any, i: number) => (
                      <div key={i} className={`my-listings__suggestion my-listings__suggestion--${s.urgency || "low"}`}>
                        {s.type === "relist" ? "🔄" : s.type === "price" ? "💰" : "✏️"} {s.message}
                      </div>
                    ))}
                  </div>
                )}

                {/* 게시 플랫폼 상태 */}
                {(item as any).publish_results?.length > 0 && (
                  <div className="my-listings__publish-status">
                    {(item as any).publish_results.map((r: any) => (
                      <span key={r.platform} className={`my-listings__publish-badge ${r.success ? "my-listings__publish-badge--ok" : "my-listings__publish-badge--fail"}`}>
                        {r.platform_name}: {r.success ? (r.external_url ? <a href={r.external_url} target="_blank" rel="noopener noreferrer">게시됨</a> : "성공") : "실패"}
                      </span>
                    ))}
                  </div>
                )}

                {/* 문의 목록 (펼침) */}
                {selectedItem === item.session_id && (
                  <div className="my-listings__inquiries">
                    {inquiryLoading ? (
                      <p className="my-listings__inquiries-loading">문의 불러오는 중...</p>
                    ) : inquiries.length === 0 ? (
                      <p className="my-listings__inquiries-empty">아직 문의가 없습니다.</p>
                    ) : (
                      inquiries.map((inq) => (
                        <div key={inq.id} className={`my-listings__inquiry ${inq.status === "open" ? "my-listings__inquiry--open" : ""}`}>
                          <div className="my-listings__inquiry-header">
                            <strong>{inq.buyer_name}</strong>
                            <span className="my-listings__inquiry-contact">{inq.buyer_contact}</span>
                            <span className="my-listings__inquiry-date">
                              {new Date(inq.created_at).toLocaleDateString("ko-KR")}
                            </span>
                            {inq.status === "open" && <span className="my-listings__inquiry-new">NEW</span>}
                          </div>
                          <p className="my-listings__inquiry-message">{inq.message}</p>
                          {inq.reply ? (
                            <div className="my-listings__inquiry-reply">
                              <strong>내 답변:</strong> {inq.reply}
                            </div>
                          ) : (
                            <div className="my-listings__reply-form">
                              <textarea
                                className="my-listings__reply-input"
                                placeholder="답변을 입력하세요..."
                                value={replyText[inq.id] || ""}
                                onChange={(e) => setReplyText((prev) => ({ ...prev, [inq.id]: e.target.value }))}
                                rows={2}
                              />
                              <div className="my-listings__reply-actions">
                                <button
                                  className="my-listings__ai-suggest-btn"
                                  onClick={() => handleSuggestReply(item.session_id, inq.id)}
                                  disabled={aiSuggesting === inq.id}
                                >
                                  {aiSuggesting === inq.id ? "AI 생성 중..." : "AI 답변 제안"}
                                </button>
                                <button
                                  className="my-listings__reply-btn"
                                  onClick={() => handleReply(item.session_id, inq.id)}
                                  disabled={replySending === inq.id || !(replyText[inq.id]?.trim())}
                                >
                                  {replySending === inq.id ? "전송 중..." : "답변 보내기"}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
