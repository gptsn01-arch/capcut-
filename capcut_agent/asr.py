"""faster-whisper로 전체 대본(세그먼트+단어 타임스탬프)을 추출한다.

★ 핵심 원칙: 세그먼트(문장) 단위 대본을 먼저 만들고, 그 대본을 기준으로
잔말/NG를 판단한다. 단어 타임스탬프는 "이 세그먼트 안에서 어떤 단어를 잘라도
되는가"를 판단하는 보조 정보로만 쓴다 (단어 단위로 대본을 재구성하지 않음).

★ numba 기반 모델은 스레드 세이프하지 않아 동시 호출 시 segfault가 날 수 있다.
   asyncio.Lock으로 호출을 직렬화해야 한다 (app.py에서 처리).

★ 캐시는 파일 내용의 sha256 해시로 키를 잡는다. mtime 기반 캐시는 같은 파일을
   재업로드해도 매번 miss가 나서 캐시 의미가 없다.
"""
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    segments: list[Segment]

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "words": [asdict(w) for w in s.words],
                }
                for s in self.segments
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> "Transcript":
        segments = [
            Segment(
                start=s["start"],
                end=s["end"],
                text=s["text"],
                words=[Word(**w) for w in s.get("words", [])],
            )
            for s in data["segments"]
        ]
        return Transcript(language=data["language"], segments=segments)


def content_hash(file_path: str) -> str:
    """파일 내용 기준 해시 (mtime 아님 -> 재업로드해도 캐시 hit)."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(cache_dir: str, file_hash: str, model_size: str) -> Path:
    return Path(cache_dir) / f"{file_hash}_{model_size}.json"


def transcribe(
    input_path: str,
    model_size: str = "medium",
    language: str | None = "ko",
    cache_dir: str = "./.asr_cache",
    device: str = "auto",
    compute_type: str = "auto",
) -> Transcript:
    """faster-whisper로 전체 대본을 추출한다 (내용 해시 캐시 적용)."""
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    file_hash = content_hash(input_path)
    cache_file = _cache_path(cache_dir, file_hash, model_size)

    if cache_file.exists():
        return Transcript.from_dict(json.loads(cache_file.read_text(encoding="utf-8")))

    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        input_path,
        language=language,
        word_timestamps=True,
    )

    segments = []
    for seg in segments_iter:
        words = [
            Word(start=w.start, end=w.end, text=w.word.strip())
            for w in (seg.words or [])
        ]
        segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words))

    transcript = Transcript(language=info.language, segments=segments)
    cache_file.write_text(json.dumps(transcript.to_dict(), ensure_ascii=False), encoding="utf-8")
    return transcript
