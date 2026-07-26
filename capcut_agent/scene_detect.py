"""버벅임/끊김 장면 감지: 프레임 간 급격한 변화(scene score)와 저조도 반복 패턴을 감지한다."""
import re
import subprocess
from dataclasses import dataclass


@dataclass
class GlitchInterval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _get_duration(input_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def detect_freeze_frames(
    input_path: str,
    noise_tolerance: float = 0.001,
    min_duration: float = 0.3,
) -> list[GlitchInterval]:
    """freezedetect 필터로 정지/버벅이는(프레임이 멈춘) 구간을 찾는다."""
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"freezedetect=n={noise_tolerance}:d={min_duration}",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    log = result.stderr

    starts = [float(m) for m in re.findall(r"freeze_start:\s*([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"freeze_end:\s*([\d.]+)", log)]

    duration = _get_duration(input_path)
    intervals = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else duration
        intervals.append(GlitchInterval(start=start, end=end))
    return intervals
