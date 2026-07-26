"""Whisper로 음성을 인식해 .srt 자막 파일을 생성한다."""
from pathlib import Path

from .asr import Transcript
from .cutter import remap_segment


def _format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_subtitles(
    input_path: str,
    output_srt_path: str,
    model_size: str = "medium",
    language: str | None = "ko",
) -> str:
    """오디오/영상을 인식해 output_srt_path에 SRT 자막을 저장하고 경로를 반환한다."""
    import whisper

    model = whisper.load_model(model_size)
    result = model.transcribe(input_path, language=language, verbose=False)

    lines = []
    for i, segment in enumerate(result["segments"], start=1):
        start = _format_timestamp(segment["start"])
        end = _format_timestamp(segment["end"])
        text = segment["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    Path(output_srt_path).write_text("\n".join(lines), encoding="utf-8")
    return output_srt_path


def write_srt_from_transcript(
    transcript: Transcript,
    keep_segments: list[tuple[float, float]],
    output_srt_path: str,
    excluded_indices: set[int] | None = None,
) -> str:
    """이미 추출된 Transcript를 keep_segments(편집본 타임라인) 기준으로 리매핑해 SRT로 저장한다.

    ★ 세그먼트(문장) 단위 자막 — 단어 단위로 쪼개지 않는다.
    ASR을 편집본에 대해 다시 돌리지 않아도 되므로 원본 대본과 자막이 항상 일치한다.
    """
    excluded_indices = excluded_indices or set()
    lines = []
    counter = 1
    for i, segment in enumerate(transcript.segments):
        if i in excluded_indices:
            continue
        remapped = remap_segment(segment.start, segment.end, keep_segments)
        if remapped is None:
            continue
        new_start, new_end = remapped
        lines.append(
            f"{counter}\n{_format_timestamp(new_start)} --> {_format_timestamp(new_end)}\n{segment.text.strip()}\n"
        )
        counter += 1

    Path(output_srt_path).write_text("\n".join(lines), encoding="utf-8")
    return output_srt_path
