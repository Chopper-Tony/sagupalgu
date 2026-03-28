#!/usr/bin/env python3
"""
전달물 위생 스크립트 — 프로젝트 clean archive(zip) 생성.

.gitignore + .archiveignore 기반 필터링으로 민감 파일 제외.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path


# 프로젝트 루트 (이 스크립트의 상위 디렉터리)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_ignore_file(path: Path) -> list[str]:
    """ignore 파일을 파싱하여 패턴 목록을 반환한다. 주석·빈줄 제외."""
    if not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        # 빈줄·주석 무시
        if not stripped or stripped.startswith("#"):
            continue
        # !로 시작하는 네거티브 패턴은 제외 대상에서 빼야 하므로 그대로 보존
        patterns.append(stripped)
    return patterns


def _should_exclude(rel_path: str, patterns: list[str]) -> bool:
    """패턴 목록에 따라 해당 경로를 제외할지 판정한다.

    네거티브 패턴(!로 시작)이 매치하면 포함으로 복원.
    패턴 순서대로 마지막에 매치한 규칙이 우선.
    """
    # 통일: 슬래시 정규화
    rel_path_unix = rel_path.replace("\\", "/")

    excluded = False
    for pattern in patterns:
        negate = pattern.startswith("!")
        pat = pattern.lstrip("!")

        # 패턴 정규화
        pat = pat.replace("\\", "/").rstrip("/")

        matched = False

        # 경로의 각 구성 요소 또는 전체 경로에 대해 매칭
        parts = rel_path_unix.split("/")
        for i, part in enumerate(parts):
            if fnmatch.fnmatch(part, pat):
                matched = True
                break
            # 디렉터리 패턴: 접두사 매칭
            sub = "/".join(parts[: i + 1])
            if fnmatch.fnmatch(sub, pat):
                matched = True
                break

        # 전체 경로 매칭
        if not matched and fnmatch.fnmatch(rel_path_unix, pat):
            matched = True

        if matched:
            excluded = not negate

    return excluded


def collect_files(root: Path | None = None) -> list[str]:
    """archive에 포함될 파일 목록(상대 경로)을 반환한다."""
    if root is None:
        root = PROJECT_ROOT

    # 패턴 수집: .gitignore + .archiveignore 통합
    patterns: list[str] = []
    patterns.extend(_parse_ignore_file(root / ".gitignore"))
    patterns.extend(_parse_ignore_file(root / ".archiveignore"))

    result: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # 상대 경로 계산
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        # 디렉터리 레벨 필터링 (탐색 자체를 제외)
        if rel_dir and _should_exclude(rel_dir, patterns):
            dirnames.clear()  # 하위 디렉터리 탐색 중단
            continue

        for filename in sorted(filenames):
            rel_file = os.path.join(rel_dir, filename) if rel_dir else filename
            if not _should_exclude(rel_file, patterns):
                result.append(rel_file.replace("\\", "/"))

    return sorted(result)


def build_archive(
    output: str | None = None,
    dry_run: bool = False,
    root: Path | None = None,
) -> Path | None:
    """archive zip 파일을 생성한다.

    Args:
        output: 출력 파일 경로. None이면 기본 이름 사용.
        dry_run: True이면 파일 목록만 출력하고 zip 생성하지 않음.
        root: 프로젝트 루트. None이면 자동 탐지.

    Returns:
        생성된 zip 파일 경로. dry_run이면 None.
    """
    if root is None:
        root = PROJECT_ROOT

    files = collect_files(root)

    if dry_run:
        print(f"[dry-run] 포함될 파일 {len(files)}개:")
        for f in files:
            print(f"  {f}")
        return None

    if output is None:
        date_str = datetime.now().strftime("%Y%m%d")
        output = f"sagupalgu_archive_{date_str}.zip"

    output_path = Path(output).resolve()
    print(f"Archive 생성 중: {output_path}")
    print(f"포함 파일: {len(files)}개")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_file in files:
            abs_file = root / rel_file
            zf.write(abs_file, rel_file)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"완료: {output_path.name} ({size_mb:.1f} MB, {len(files)}개 파일)")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="프로젝트 clean archive(zip) 생성"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="포함될 파일 목록만 출력 (zip 생성하지 않음)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="출력 파일명 (기본: sagupalgu_archive_{날짜}.zip)",
    )
    args = parser.parse_args()
    build_archive(output=args.output, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
