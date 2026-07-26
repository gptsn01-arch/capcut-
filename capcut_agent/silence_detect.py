"""무음 구간 감지: ffmpeg의 silencedetect 필터 출력을 파싱한다."""
import re
import subprocess
from dataclasses import dataclass


@dataclass
class SilenceInterval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def detect_silences(
    input_path: str,
    noise_db: float = -30.0,
    min_duration: float = 0.5,
) -> list[SilenceInterval]:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    log = result.stderr

    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", log)]

    intervals = []
    for start, end in zip(starts, ends):
        intervals.append(SilenceInterval(start=start, end=end))
    return intervals
