# CapCut 자동 편집 에이전트

무음 구간과 버벅이는(프리즈) 장면을 자동으로 감지해 컷 편집하고, 편집된 영상에 맞춰 자막(.srt)까지 자동 생성하는 도구입니다.

캡컷은 외부에서 직접 제어할 수 있는 공식 API를 제공하지 않기 때문에, 이 도구는 **독립적으로 영상/자막 파일을 생성**한 뒤 캡컷에 그대로 임포트해서 마무리하는 방식으로 동작합니다.

## 설치

```bash
pip install -r requirements.txt
```

`ffmpeg`, `ffprobe`가 시스템에 설치되어 있어야 합니다.

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## 사용법

```bash
python -m capcut_agent.cli input.mp4 --output-dir ./output
```

실행하면 `./output` 폴더에:
- `input_edited.mp4` — 무음/버벅임 구간이 제거된 영상
- `input_edited.srt` — 자동 생성된 자막

이 생성됩니다. 두 파일을 캡컷 프로젝트에 임포트하면 편집을 이어갈 수 있습니다.

### 주요 옵션

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--no-silence-cut` | 무음 구간 컷 비활성화 | - |
| `--no-freeze-cut` | 프리즈(버벅임) 구간 컷 비활성화 | - |
| `--no-subtitles` | 자막 생성 비활성화 | - |
| `--silence-noise-db` | 무음 판정 임계값(dB, 낮을수록 민감) | -30.0 |
| `--silence-min-duration` | 무음 최소 지속 시간(초) | 0.5 |
| `--freeze-min-duration` | 프리즈 최소 지속 시간(초) | 0.3 |
| `--whisper-model` | Whisper 모델 크기 (tiny/base/small/medium/large) | medium |
| `--language` | 자막 언어 코드 (`auto`로 자동 감지) | ko |
| `--capcut-draft-dir` | 지정 시 캡컷 draft(`draft_content.json`)를 이 폴더 밑에 직접 생성 | - |
| `--draft-name` | 생성할 draft 이름 | 입력 파일명 + `_auto_edit` |
| `--draft-width` / `--draft-height` / `--draft-fps` | draft 캔버스 해상도/프레임레이트 | 1920 / 1080 / 30 |

## 캡컷 draft 직접 생성 ([pyCapCut](https://github.com/GuanYixuan/pyCapCut) 사용)

`mp4` 파일을 만들어 수동으로 임포트하는 대신, [pyCapCut](https://github.com/GuanYixuan/pyCapCut) 라이브러리로 캡컷이 바로 인식하는 draft 프로젝트를 생성할 수 있습니다. `--capcut-draft-dir`에 캡컷의 실제 drafts 폴더 경로를 넘기면:

```bash
python -m capcut_agent.cli input.mp4 \
  --output-dir ./output \
  --capcut-draft-dir "/path/to/CapCut/User Data/Projects/com.lveditor.draft" \
  --draft-name my_auto_edit
```

- 원본 영상은 그대로 두고, 남길 구간(keep_segments)마다 `VideoSegment`를 하나씩 만들어 타임라인에 순서대로 배치합니다 (무음/버벅임 구간만 트리밍되어 빠짐).
- 생성된 자막(.srt)은 `import_srt`로 자막 트랙에 자동 삽입됩니다.
- 캡컷 앱을 열면 프로젝트 목록에 바로 나타나고, 각 컷이 개별 클립으로 남아 있어 이어서 다듬을 수 있습니다.

CapCut/드라이브별 drafts 폴더 경로 찾는 법 등 자세한 내용은 pyCapCut 문서를 참고하세요.

## 동작 원리

1. **무음 구간 감지**: ffmpeg `silencedetect` 필터로 오디오 볼륨이 임계값 이하로 떨어지는 구간을 찾습니다.
2. **버벅임 감지**: ffmpeg `freezedetect` 필터로 프레임이 멈추거나 반복되는 구간을 찾습니다.
3. **컷 편집**: 감지된 구간을 병합한 뒤, 남길 구간만 잘라서 이어붙입니다 (재인코딩 없이 스트림 복사).
4. **자막 생성**: OpenAI Whisper로 편집된 영상의 음성을 인식해 타임스탬프가 맞는 .srt 파일을 생성합니다.
