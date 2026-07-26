"""무음/버벅임 구간을 잘라내고 남은 구간만 이어붙여 새 영상을 만든다."""
import subprocess
import tempfile
from pathlib import Path

from .scene_detect import GlitchInterval, detect_freeze_frames, _get_duration
from .silence_detect import SilenceInterval, detect_silences


def _merge_intervals(intervals: list[tuple[float, float]], gap: float = 0.05) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + gap:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_keep_segments(
    input_path: str,
    remove_silence: bool = True,
    remove_freezes: bool = True,
    silence_noise_db: float = -30.0,
    silence_min_duration: float = 0.5,
    freeze_min_duration: float = 0.3,
    padding: float = 0.1,
) -> list[tuple[float, float]]:
    """제거할 구간을 계산한 뒤, 남겨야 할(keep) 구간 리스트를 반환한다."""
    duration = _get_duration(input_path)
    cut_ranges: list[tuple[float, float]] = []

    if remove_silence:
        for s in detect_silences(input_path, noise_db=silence_noise_db, min_duration=silence_min_duration):
            cut_ranges.append((max(0.0, s.start + padding), max(0.0, s.end - padding)))

    if remove_freezes:
        for g in detect_freeze_frames(input_path, min_duration=freeze_min_duration):
            cut_ranges.append((max(0.0, g.start), min(duration, g.end)))

    return keep_segments_from_cut_ranges(cut_ranges, duration)


def keep_segments_from_cut_ranges(
    cut_ranges: list[tuple[float, float]],
    duration: float,
    min_keep_duration: float = 0.05,
) -> list[tuple[float, float]]:
    """제거할 구간(cut_ranges)들을 병합해 남길 구간(keep_segments)으로 뒤집는다."""
    cut_ranges = [(s, e) for s, e in cut_ranges if e > s]
    cut_ranges = _merge_intervals(cut_ranges)

    keep_segments = []
    cursor = 0.0
    for start, end in cut_ranges:
        if start > cursor:
            keep_segments.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep_segments.append((cursor, duration))

    return [(s, e) for s, e in keep_segments if e - s > min_keep_duration]


def remap_time(t: float, keep_segments: list[tuple[float, float]]) -> float:
    """원본 타임라인의 시각 t를, keep_segments만 이어붙인 편집본 타임라인의 시각으로 변환한다.

    t가 잘려나간(cut) 구간 안에 있으면 다음 keep_segment의 시작점으로 스냅한다.
    """
    cursor = 0.0
    for start, end in keep_segments:
        if t < start:
            return cursor
        if t <= end:
            return cursor + (t - start)
        cursor += end - start
    return cursor


def subtract_protected_ranges(
    cut_ranges: list[tuple[float, float]],
    protected_ranges: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """사용자가 프리뷰에서 [ / ] 로 보존 지정한 구간(protected_ranges)을 cut_ranges에서 제외한다."""
    if not protected_ranges:
        return cut_ranges

    result: list[tuple[float, float]] = []
    for start, end in cut_ranges:
        pieces = [(start, end)]
        for p_start, p_end in protected_ranges:
            next_pieces = []
            for s, e in pieces:
                if p_end <= s or p_start >= e:
                    next_pieces.append((s, e))
                    continue
                if p_start > s:
                    next_pieces.append((s, p_start))
                if p_end < e:
                    next_pieces.append((p_end, e))
            pieces = next_pieces
        result.extend(pieces)

    return [(s, e) for s, e in result if e > s]


def remap_segment(
    start: float,
    end: float,
    keep_segments: list[tuple[float, float]],
) -> tuple[float, float] | None:
    """세그먼트(start, end)를 편집본 타임라인 기준으로 변환한다. 완전히 잘렸으면 None."""
    new_start = remap_time(start, keep_segments)
    new_end = remap_time(end, keep_segments)
    if new_end - new_start < 0.05:
        return None
    return new_start, new_end


def cut_video(
    input_path: str,
    output_path: str,
    keep_segments: list[tuple[float, float]],
) -> None:
    """keep_segments만 남기고 나머지를 잘라 새 영상 파일로 출력한다."""
    if not keep_segments:
        raise ValueError("남길 구간이 없습니다. 감지 파라미터를 확인하세요.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        part_files = []
        for i, (start, end) in enumerate(keep_segments):
            part_path = tmp_dir_path / f"part_{i:04d}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-to", str(end),
                "-i", input_path,
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                str(part_path),
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            part_files.append(part_path)

        concat_list_path = tmp_dir_path / "concat_list.txt"
        with open(concat_list_path, "w") as f:
            for part_path in part_files:
                f.write(f"file '{part_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
