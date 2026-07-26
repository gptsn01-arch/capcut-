"""전체 파이프라인: silence -> asr -> filler -> draft+자막 (SSE 4단계).

★ ASR은 asyncio.Lock으로 직렬화한다 (faster-whisper/numba가 스레드 세이프하지
   않아 동시 호출 시 segfault 위험이 있음).
★ 각 단계는 최소 0.5초를 보장한다 (캐시 hit로 즉시 끝나도 UI 애니메이션이
   보이도록 인위적으로 지연시킨다).
"""
import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable

from .asr import Transcript, transcribe
from .cutter import (
    _get_duration,
    compute_keep_segments,
    keep_segments_from_cut_ranges,
    subtract_protected_ranges,
)
from .draft_builder import build_capcut_draft
from .filler_ng import compute_filler_ng_cuts
from .scene_detect import detect_freeze_frames
from .silence_detect import detect_silences
from .subtitles import write_srt_from_transcript

MIN_STAGE_SECONDS = 0.5

OnEvent = Callable[[str, dict], Awaitable[None]]


async def _timed_stage(name: str, on_event: OnEvent, coro):
    t0 = time.monotonic()
    await on_event(name, {"status": "start"})
    result = await coro
    elapsed = time.monotonic() - t0
    if elapsed < MIN_STAGE_SECONDS:
        await asyncio.sleep(MIN_STAGE_SECONDS - elapsed)
    return result


async def run_pipeline(
    input_path: str,
    output_dir: str,
    drafts_dir: str,
    draft_name: str,
    on_event: OnEvent,
    asr_lock: asyncio.Lock,
    whisper_model: str = "medium",
    language: str | None = "ko",
    protected_ranges: list[tuple[float, float]] | None = None,
) -> dict:
    """SSE 이벤트를 on_event(stage, payload)로 방출하며 최종 결과 dict를 반환한다."""
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    protected_ranges = protected_ranges or []

    duration = _get_duration(input_path)

    # 1) silence (+freeze) 감지
    async def _silence_work():
        loop = asyncio.get_running_loop()
        silences = await loop.run_in_executor(None, detect_silences, input_path)
        freezes = await loop.run_in_executor(None, detect_freeze_frames, input_path)
        return silences, freezes

    silences, freezes = await _timed_stage("silence", on_event, _silence_work())
    silence_cut_ranges = [(max(0.0, s.start + 0.1), max(0.0, s.end - 0.1)) for s in silences]
    freeze_cut_ranges = [(max(0.0, g.start), min(duration, g.end)) for g in freezes]
    await on_event("silence", {
        "status": "done",
        "silence_count": len(silences),
        "freeze_count": len(freezes),
    })

    # 2) ASR (전체 대본 추출) — 직렬화 필수
    async def _asr_work():
        loop = asyncio.get_running_loop()
        async with asr_lock:
            return await loop.run_in_executor(
                None, transcribe, input_path, whisper_model, language, str(output_dir_path / ".asr_cache")
            )

    transcript: Transcript = await _timed_stage("asr", on_event, _asr_work())
    await on_event("asr", {
        "status": "done",
        "segment_count": len(transcript.segments),
        "language": transcript.language,
    })

    # 3) 잔말/NG 컷 (추출된 대본 기준으로 판단)
    async def _filler_work():
        return compute_filler_ng_cuts(transcript)

    filler_ng_result = await _timed_stage("filler", on_event, _filler_work())
    await on_event("filler", {
        "status": "done",
        "filler_ng_cut_count": len(filler_ng_result.cut_ranges),
    })

    # 4) 드래프트 + 자막 생성
    async def _draft_work():
        all_cut_ranges = silence_cut_ranges + freeze_cut_ranges + filler_ng_result.cut_ranges
        all_cut_ranges = subtract_protected_ranges(all_cut_ranges, protected_ranges)
        keep_segments = keep_segments_from_cut_ranges(all_cut_ranges, duration)

        ng_excluded = {
            i for i in range(len(transcript.segments))
            if i not in filler_ng_result.kept_segment_texts
        }
        srt_path = output_dir_path / f"{draft_name}.srt"
        write_srt_from_transcript(transcript, keep_segments, str(srt_path), excluded_indices=ng_excluded)

        loop = asyncio.get_running_loop()
        draft_path = await loop.run_in_executor(
            None,
            lambda: build_capcut_draft(
                input_path, keep_segments, drafts_dir, draft_name, srt_path=str(srt_path)
            ),
        )
        return keep_segments, str(srt_path), draft_path

    keep_segments, srt_path, draft_path = await _timed_stage("draft", on_event, _draft_work())
    await on_event("draft", {
        "status": "done",
        "kept_segment_count": len(keep_segments),
        "draft_path": draft_path,
        "srt_path": srt_path,
    })

    return {
        "transcript": transcript.to_dict(),
        "keep_segments": keep_segments,
        "srt_path": srt_path,
        "draft_path": draft_path,
        "duration": duration,
    }
