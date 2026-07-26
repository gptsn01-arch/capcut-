"""Step 0: OS 감지 + 환경 점검.

이 모듈은 실제로 앱을 실행할 사용자 머신(Mac/Windows)에서 돌아가는 것을 전제로 한다.
빠진 도구가 있으면 설치 명령만 안내하고 대기한다 (자동 설치하지 않음).
"""
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EnvCheckResult:
    track: str  # "A" (mac mlx-whisper) | "C" (windows faster-whisper) | "fallback" (faster-whisper)
    os_name: str
    machine: str
    whisper_backend: str
    missing: list[str] = field(default_factory=list)
    capcut_drafts_dir: str | None = None
    disk_free_gb: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.missing


def detect_track() -> tuple[str, str]:
    """(track, whisper_backend) 반환."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return "A", "mlx-whisper"
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "C", "faster-whisper"
    return "fallback", "faster-whisper"


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _disk_free_gb(path: str = ".") -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def _default_capcut_drafts_dir(system: str) -> Path | None:
    home = Path.home()
    if system == "Darwin":
        candidates = [
            home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
        ]
    elif system == "Windows":
        candidates = [
            home / "AppData" / "Local" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
        ]
    else:
        candidates = []

    for c in candidates:
        if c.exists():
            return c
    return candidates[0] if candidates else None


def run_env_check(min_disk_gb: float = 5.0) -> EnvCheckResult:
    system = platform.system()
    machine = platform.machine()
    track, backend = detect_track()

    missing: list[str] = []

    if not _which("ffmpeg") or not _which("ffprobe"):
        missing.append("ffmpeg")

    if system == "Darwin" and not _which("brew"):
        missing.append("brew")

    py_ver = platform.python_version_tuple()
    if not (int(py_ver[0]) == 3 and int(py_ver[1]) >= 9):
        missing.append("python>=3.9")

    drafts_dir = _default_capcut_drafts_dir(system)
    if drafts_dir is None or not drafts_dir.exists():
        missing.append("capcut_drafts_folder")

    free_gb = _disk_free_gb(".")
    if free_gb < min_disk_gb:
        missing.append(f"disk_space(<{min_disk_gb}GB free, has {free_gb:.1f}GB)")

    return EnvCheckResult(
        track=track,
        os_name=system,
        machine=machine,
        whisper_backend=backend,
        missing=missing,
        capcut_drafts_dir=str(drafts_dir) if drafts_dir else None,
        disk_free_gb=free_gb,
    )


_INSTALL_HINTS = {
    "Darwin": {
        "brew": '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        "ffmpeg": "brew install ffmpeg",
        "python>=3.9": "brew install python@3.11",
        "capcut_drafts_folder": "CapCut 앱을 설치하고 최소 1회 실행 후 프로젝트를 하나 만들어 주세요 "
                                  "(App Store 또는 https://www.capcut.com/download)",
    },
    "Windows": {
        "ffmpeg": "winget install ffmpeg",
        "python>=3.9": "https://python.org 에서 Python 3.11 설치 (Add to PATH 체크)",
        "capcut_drafts_folder": "CapCut 앱을 설치하고 최소 1회 실행 후 프로젝트를 하나 만들어 주세요 "
                                  "(https://www.capcut.com/download)",
    },
}


def print_report(result: EnvCheckResult) -> None:
    print(f"OS: {result.os_name} {result.machine}  ->  트랙 {result.track} ({result.whisper_backend})")
    print(f"디스크 여유 공간: {result.disk_free_gb:.1f} GB")
    print(f"캡컷 드래프트 폴더: {result.capcut_drafts_dir or '찾을 수 없음'}")

    if result.ok:
        print("\n환경 점검 통과. 다음 단계로 진행 가능합니다.")
        return

    print("\n다음 항목이 빠져 있습니다. 설치 후 다시 실행해 주세요:")
    hints = _INSTALL_HINTS.get(result.os_name, {})
    for item in result.missing:
        key = item.split("(")[0]
        hint = hints.get(item) or hints.get(key)
        if hint:
            print(f"  - [{item}] {hint}")
        else:
            print(f"  - [{item}] (직접 확인 필요: 지원되지 않는 환경이거나 수동 조치가 필요합니다)")
    print("\n대기 중... 위 항목을 설치/조치한 뒤 다시 실행해 주세요.")


if __name__ == "__main__":
    print_report(run_env_check())
