"""Whisper로 음성을 인식해 .srt 자막 파일을 생성한다."""
from pathlib import Path


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
