import { useRef, useState } from "react";
import "./ImageUploadCard.css";

interface ImageUploadCardProps {
  onUpload: (files: File[]) => void;
}

export function ImageUploadCard({ onUpload }: ImageUploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [previews, setPreviews] = useState<string[]>([]);

  const handleFiles = (files: File[]) => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    onUpload(files);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (files.length > 0) handleFiles(files);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) handleFiles(files);
    e.target.value = "";
  };

  return (
    <div className="image-upload-card">
      <div
        className="image-upload-card__dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: "none" }}
          onChange={handleChange}
        />
        <div className="image-upload-card__icon">📷</div>
        <p className="image-upload-card__title">판매할 상품 사진을 올려주세요</p>
        <p className="image-upload-card__subtitle">
          클릭하거나 드래그 앤 드롭 · 최대 10장
        </p>
        <button className="image-upload-card__btn">사진 선택</button>
      </div>
      {previews.length > 0 && (
        <div className="image-upload-card__previews">
          {previews.map((url, i) => (
            <img key={i} src={url} alt={`미리보기 ${i + 1}`} className="image-upload-card__preview" />
          ))}
        </div>
      )}
    </div>
  );
}
