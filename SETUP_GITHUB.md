# GitHub 자동 웹사이트 설정 안내 (약 15분, 설치 없음)

설정이 끝나면 매주 목요일 아침 자동으로 예측이 돌고, 아래 주소에서 결과를 볼 수 있습니다.
`https://<내 GitHub 아이디>.github.io/kwagent/`

## 1. GitHub 계정과 저장소 만들기
1. https://github.com 에 가입합니다(무료).
2. 오른쪽 위 **+** → **New repository** 를 누릅니다.
3. Repository name 에 `kwagent` 를 입력합니다. Private/Public 중 하나를 고릅니다.
   - Public: 무료 계정에서 웹사이트(Pages)를 바로 쓸 수 있습니다.
   - Private: Pages 를 쓰려면 유료 플랜이 필요합니다.
4. 다른 옵션은 그대로 두고 **Create repository** 를 누릅니다.

## 2. 코드 올리기 — 둘 중 하나
**A. Claude Code 로 넘기기 (권장)**
Claude Code 에서 이 폴더를 열고 이렇게 말하세요.
> "이 저장소를 내 GitHub `kwagent` 저장소에 올려줘. CLAUDE.md 읽고 이어서 진행해."

**B. 웹 화면에서 직접 올리기**
1. 새 저장소 화면에서 **uploading an existing file** 을 누릅니다.
2. 압축을 푼 `kwagent` 폴더 안의 파일·폴더를 **모두** 끌어다 놓습니다.
   이때 숨김 폴더인 `.github` 도 포함되어야 합니다. 탐색기에서 숨김 항목 보기를 켜세요.
3. **Commit changes** 를 누릅니다.

## 3. 웹사이트(Pages) 켜기
저장소 → **Settings** → 왼쪽 **Pages** → Source 를 **GitHub Actions** 로 바꿉니다.

## 4. (선택) Claude 해설 켜기
저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Secret: Anthropic 콘솔에서 발급한 키

넣지 않으면 규칙 기반 요약 해설이 들어갑니다.

## 5. 첫 실행
1. 저장소 → **Actions** 탭으로 갑니다. 워크플로 사용 확인이 나오면 허용합니다.
2. 왼쪽 **weekly-forecast** → **Run workflow** 를 누릅니다.
3. 첫 실행은 1991년 이후 자료를 받고 학습까지 하므로 20~40분쯤 걸립니다. 이후에는 몇 분이면 끝납니다.
4. 초록색 체크가 뜨면 `https://<아이디>.github.io/kwagent/` 에 접속합니다.

## 6. 그다음
- 매주 목요일 07:10(한국 시간)에 자동으로 실행됩니다. 실제 시작은 GitHub 사정으로 몇 분~수십 분 늦을 수 있습니다.
- **정확도** 탭은 첫 예측 후 약 5주가 지나야 채워집니다. 4주차 예측이 끝나고 자료가 들어와야 채점할 수 있기 때문입니다.
- 중부권/남부권 분리는 `config.yaml` 의 `regions_active` 를 `[korea, central, south]` 로 바꾸고, Actions → **train** → Run workflow 를 실행하면 됩니다.

## 문제가 생기면
Actions 탭에서 실패한(빨간 X) 실행을 열면 로그가 보입니다. 그 로그를 Claude Code 에 붙여 넣고 "고쳐줘"라고 하면 됩니다.
