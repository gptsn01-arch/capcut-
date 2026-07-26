"""pycapcut을 이용해 컷 편집 결과와 자막을 캡컷 draft(draft_content.json)로 직접 생성한다.

ffmpeg으로 영상을 미리 잘라 붙이는 대신, 원본 영상 하나를 소스로 두고
keep_segments(남길 구간)마다 하나씩 VideoSegment를 만들어 타임라인에 순서대로 배치한다.
이렇게 하면 캡컷에서 프로젝트를 열었을 때 각 컷이 그대로 개별 클립으로 남아 있어
필요하면 다시 다듬을 수 있다.
"""
from pathlib import Path

import pycapcut as cc
from pycapcut import Timerange


def _to_timerange(start: float, end: float) -> Timerange:
    """초 단위 구간을 pycapcut Timerange(마이크로초 기준)로 변환한다."""
    start_us = round(start * 1_000_000)
    duration_us = round((end - start) * 1_000_000)
    return Timerange(start_us, duration_us)


def build_capcut_draft(
    input_video_path: str,
    keep_segments: list[tuple[float, float]],
    draft_folder_path: str,
    draft_name: str,
    srt_path: str | None = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    allow_replace: bool = True,
) -> str:
    """keep_segments만 남긴 캡컷 draft를 생성하고, draft 폴더 경로를 반환한다."""
    if not keep_segments:
        raise ValueError("남길 구간이 없습니다. 감지 파라미터를 확인하세요.")

    folder = cc.DraftFolder(draft_folder_path)
    script = folder.create_draft(draft_name, width, height, fps, allow_replace=allow_replace)

    script.add_track(cc.TrackType.video, track_name="video_track")

    video_material = cc.VideoMaterial(input_video_path)

    cursor_us = 0
    for start, end in keep_segments:
        source_range = _to_timerange(start, end)
        target_range = Timerange(cursor_us, source_range.duration)
        segment = cc.VideoSegment(
            video_material,
            target_range,
            source_timerange=source_range,
        )
        script.add_segment(segment, "video_track")
        cursor_us += source_range.duration

    if srt_path and Path(srt_path).exists():
        script.add_track(cc.TrackType.text, track_name="subtitles")
        script.import_srt(srt_path, track_name="subtitles")

    script.save()
    return str(Path(draft_folder_path) / draft_name)
