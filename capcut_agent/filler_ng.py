"""잔말(filler)/NG 통합 컷.

★ 전체 대본(Transcript)을 먼저 읽고 나서 잘라낼 곳을 정한다 — 문맥 없이
단어 하나만 보고 판단하지 않는다. 예: "그"는 보통 필러지만 뒤에 명사가 바로
붙으면("그 사람") 지시어이므로 자르지 않는다 (의존명사/후행 명사 가드).

- find_filler_cuts: 문장 안에서 의미 없이 낀 추임새(음/어/이제/그니까 등) 단어 컷
- find_ng_cuts: 같은 말을 다시 하는 리테이크(NG) 구간을 통째로 컷 (마지막 시도만 남김)
"""
import difflib
from dataclasses import dataclass

from .asr import Segment, Transcript

FILLER_WORDS = {
    "음", "어", "그", "저", "이제", "인제", "그니까", "그러니까",
    "약간", "뭐", "막", "그게", "저기", "아", "에", "그래서",
}

# 필러 단어 뒤에 이 단어들이 바로 오면 지시어/의존명사로 보고 자르지 않는다
# (예: "그 사람", "그 거", "이제 부터"는 필러가 아니라 실제 의미 성분)
_GUARD_NEXT_WORDS = {"사람", "거", "것", "분", "때", "부터", "동안", "중"}


@dataclass
class FillerNgResult:
    cut_ranges: list[tuple[float, float]]
    kept_segment_texts: dict[int, str]  # segment index -> NG로 완전히 제외되지 않은 세그먼트 텍스트


def find_filler_cuts(transcript: Transcript, padding: float = 0.03) -> list[tuple[float, float]]:
    cuts: list[tuple[float, float]] = []
    for segment in transcript.segments:
        words = segment.words
        for i, word in enumerate(words):
            token = word.text.strip("., !?~")
            if token not in FILLER_WORDS:
                continue
            next_token = words[i + 1].text.strip("., !?~") if i + 1 < len(words) else ""
            if next_token in _GUARD_NEXT_WORDS:
                continue
            cuts.append((max(0.0, word.start - padding), word.end + padding))
    return cuts


def find_ng_cuts(
    transcript: Transcript,
    similarity_threshold: float = 0.6,
    max_gap: float = 8.0,
) -> tuple[list[tuple[float, float]], set[int]]:
    """유사한 문장이 짧은 간격 안에 반복되면, 마지막 시도만 남기고 이전 시도들을 컷한다.

    반환: (컷할 시간 구간 리스트, 컷 대상이 된 세그먼트 인덱스 집합)
    """
    segments = transcript.segments
    cuts: list[tuple[float, float]] = []
    cut_indices: set[int] = set()

    for i in range(len(segments)):
        if i in cut_indices:
            continue
        for j in range(i + 1, len(segments)):
            if segments[j].start - segments[i].end > max_gap:
                break
            ratio = difflib.SequenceMatcher(None, segments[i].text, segments[j].text).ratio()
            if ratio >= similarity_threshold:
                # i가 j의 이전 시도(NG)이므로 i를 통째로 컷하고, j(마지막 시도)를 남긴다
                cuts.append((segments[i].start, segments[i].end))
                cut_indices.add(i)
                break

    return cuts, cut_indices


def compute_filler_ng_cuts(transcript: Transcript) -> FillerNgResult:
    filler_cuts = find_filler_cuts(transcript)
    ng_cuts, ng_indices = find_ng_cuts(transcript)

    kept_texts = {
        i: seg.text
        for i, seg in enumerate(transcript.segments)
        if i not in ng_indices
    }

    return FillerNgResult(
        cut_ranges=filler_cuts + ng_cuts,
        kept_segment_texts=kept_texts,
    )
