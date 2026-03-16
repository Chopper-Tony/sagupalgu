from pathlib import Path
from PIL import Image, ImageOps

async def image_preprocess(image_paths: list[str], max_size: tuple[int, int] = (1600, 1600)) -> list[str]:
    processed_paths: list[str] = []
    out_dir = Path("tmp_processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, image_path in enumerate(image_paths):
        src = Path(image_path)
        if not src.exists():
            continue

        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail(max_size)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            out_path = out_dir / f"{src.stem}_processed_{idx}.jpg"
            img.save(out_path, format="JPEG", quality=90, optimize=True)
            processed_paths.append(str(out_path))
    return processed_paths
