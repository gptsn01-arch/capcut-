"""1단: silence_detect + build_draft만으로 점프컷 드래프트를 만든다 (UI 없음).

핵심 검증 대상: pycapcut으로 만든 draft_content.json을 캡컷이 실제로 인식하고
정상 재생하는지. 이 스크립트는 무음 컷만 적용하고(잔말/NG/자막 없음) 가장 단순한
형태로 pycapcut <-> 캡컷 호환성만 확인하는 것이 목적이다.

Windows(트랙 C) 기준 사용 예:
    python -m capcut_agent.step1_jumpcut "C:\\videos\\input.mp4" --draft-name test_jumpcut

--drafts-dir을 생략하면 기본 캡컷 드래프트 폴더를 자동으로 찾는다
(%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft).
"""
import argparse
import sys
from pathlib import Path

from .cutter import compute_keep_segments
from .draft_builder import build_capcut_draft
from .env_check import run_env_check


def main():
    parser = argparse.ArgumentParser(description="1단: 무음 구간만 잘라낸 점프컷 캡컷 드래프트 생성")
    parser.add_argument("input", help="입력 영상 파일 경로 (mp4/mov)")
    parser.add_argument("--draft-name", default=None, help="생성할 드래프트 이름 (기본: <파일명>_jumpcut)")
    parser.add_argument("--drafts-dir", default=None, help="캡컷 드래프트 폴더 경로 (생략 시 자동 탐색)")
    parser.add_argument("--silence-noise-db", type=float, default=-30.0, help="무음 판정 임계값(dB)")
    parser.add_argument("--silence-min-duration", type=float, default=0.5, help="무음 최소 지속 시간(초)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[오류] 입력 파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    drafts_dir = args.drafts_dir
    if not drafts_dir:
        env = run_env_check()
        if not env.capcut_drafts_dir:
            print("[오류] 캡컷 드래프트 폴더를 자동으로 찾지 못했습니다. --drafts-dir로 직접 지정해 주세요.")
            sys.exit(1)
        drafts_dir = env.capcut_drafts_dir
        print(f"[감지] 캡컷 드래프트 폴더: {drafts_dir}")

    draft_name = args.draft_name or f"{input_path.stem}_jumpcut"

    print(f"[1/2] 무음 구간 분석 중 (noise={args.silence_noise_db}dB, min_dur={args.silence_min_duration}s)...")
    keep_segments = compute_keep_segments(
        str(input_path),
        remove_silence=True,
        remove_freezes=False,
        silence_noise_db=args.silence_noise_db,
        silence_min_duration=args.silence_min_duration,
    )
    total_kept = sum(e - s for s, e in keep_segments)
    print(f"      남길 구간 {len(keep_segments)}개, 합계 {total_kept:.1f}초")

    print(f"[2/2] pycapcut으로 드래프트 생성 중 -> {drafts_dir}/{draft_name}")
    draft_path = build_capcut_draft(
        str(input_path),
        keep_segments,
        drafts_dir,
        draft_name,
        srt_path=None,
    )

    print(f"\n완료: {draft_path}")
    print("캡컷 앱을 열어 프로젝트 목록에서 위 드래프트를 찾아 재생해 보세요.")
    print("검증 체크리스트:")
    print("  [ ] 캡컷이 드래프트를 오류 없이 로드하는가")
    print("  [ ] 클립 개수가 남긴 구간 수와 일치하는가")
    print("  [ ] 재생했을 때 무음 구간이 실제로 빠져 있는가 (원본과 비교)")
    print("  [ ] 마지막 클립 끝에서 영상이 끊기지 않고 정상 종료되는가 (tm_duration 불일치 시 여기서 문제 발생)")


if __name__ == "__main__":
    main()
