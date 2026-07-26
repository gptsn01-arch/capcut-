"""캡컷 자동 편집 에이전트 CLI.

사용 예:
    python -m capcut_agent.cli input.mp4 --output-dir ./output
"""
import argparse
from pathlib import Path

from .cutter import compute_keep_segments, cut_video
from .subtitles import generate_subtitles


def main():
    parser = argparse.ArgumentParser(description="무음/버벅임 구간 자동 컷 편집 + 자막 생성")
    parser.add_argument("input", help="입력 영상 파일 경로")
    parser.add_argument("--output-dir", default="./output", help="출력 폴더")
    parser.add_argument("--no-silence-cut", action="store_true", help="무음 구간 컷 비활성화")
    parser.add_argument("--no-freeze-cut", action="store_true", help="버벅임(프리즈) 구간 컷 비활성화")
    parser.add_argument("--no-subtitles", action="store_true", help="자막 생성 비활성화")
    parser.add_argument("--silence-noise-db", type=float, default=-30.0, help="무음 판정 임계값(dB)")
    parser.add_argument("--silence-min-duration", type=float, default=0.5, help="무음 최소 지속 시간(초)")
    parser.add_argument("--freeze-min-duration", type=float, default=0.3, help="프리즈 최소 지속 시간(초)")
    parser.add_argument("--whisper-model", default="medium", help="Whisper 모델 크기 (tiny/base/small/medium/large)")
    parser.add_argument("--language", default="ko", help="자막 언어 (Whisper 언어 코드, auto 입력 시 자동 감지)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    edited_video_path = output_dir / f"{input_path.stem}_edited.mp4"
    srt_path = output_dir / f"{input_path.stem}_edited.srt"

    print(f"[1/3] '{input_path.name}'에서 무음/버벅임 구간 분석 중...")
    keep_segments = compute_keep_segments(
        str(input_path),
        remove_silence=not args.no_silence_cut,
        remove_freezes=not args.no_freeze_cut,
        silence_noise_db=args.silence_noise_db,
        silence_min_duration=args.silence_min_duration,
        freeze_min_duration=args.freeze_min_duration,
    )
    print(f"      남길 구간 {len(keep_segments)}개 발견")

    print(f"[2/3] 컷 편집 영상 생성 중 -> {edited_video_path}")
    cut_video(str(input_path), str(edited_video_path), keep_segments)

    if not args.no_subtitles:
        print(f"[3/3] 편집된 영상 기준 자막 생성 중 (Whisper: {args.whisper_model})...")
        language = None if args.language == "auto" else args.language
        generate_subtitles(
            str(edited_video_path),
            str(srt_path),
            model_size=args.whisper_model,
            language=language,
        )
        print(f"      자막 저장 완료 -> {srt_path}")
    else:
        print("[3/3] 자막 생성 건너뜀")

    print("\n완료! 아래 파일을 캡컷으로 임포트하세요:")
    print(f"  - 영상: {edited_video_path}")
    if not args.no_subtitles:
        print(f"  - 자막: {srt_path}")


if __name__ == "__main__":
    main()
