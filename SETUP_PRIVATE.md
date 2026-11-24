> **보류(2026-11-24)**: 사용자가 코드 공개 유지로 결정. 나중에 비공개로 바꾸고 싶을 때 이 순서를 따르면 됩니다.

# 코드는 비공개로, 웹사이트만 공개로 바꾸기

지금은 프로그램 코드·예측 기록·채점 자료가 들어 있는 저장소 `kwagent`가 공개되어 있어 누구나 복사할 수 있습니다.
아래 순서대로 하면 **코드 저장소는 비공개**가 되고, **완성된 웹사이트만** 별도 공개 저장소에 올라갑니다.
사이트 주소(https://dhpaeng81-crypto.github.io/kwagent/)와 홈 화면 아이콘은 그대로입니다. 비용은 없습니다.

중간에 10~20분 정도 사이트가 안 열릴 수 있습니다(1번~6번 사이).

---

## 1. 코드 저장소 이름 바꾸기 (`kwagent` → `kwagent-src`)

1. https://github.com/dhpaeng81-crypto/kwagent/settings 를 엽니다.
2. 맨 위 **Repository name** 칸을 `kwagent-src` 로 바꾸고 **Rename** 을 누릅니다.

## 2. 공개 저장소 두 개 만들기

https://github.com/new 에서 두 번 만듭니다. 둘 다 **Public**, 아래 체크 상자(README 등)는 **아무것도 체크하지 않음**.

| Repository name | 용도 |
|---|---|
| `kwagent` | 웹사이트 화면만 올라가는 곳 (주소 유지) |
| `dhpaeng81-crypto.github.io` | AI 수집 로봇 거부 파일(robots.txt)을 두는 곳 |

## 3. 게시용 열쇠(토큰) 만들기

1. https://github.com/settings/personal-access-tokens/new 를 엽니다.
2. 다음처럼 채웁니다.
   - **Token name**: `kwagent-site`
   - **Expiration**: Custom → 1년 뒤 날짜 (만료되면 사이트 갱신이 멈추니 1년마다 새로 만들기)
   - **Repository access**: *Only select repositories* → `kwagent`, `dhpaeng81-crypto.github.io` 두 개 선택
   - **Permissions → Repository permissions → Contents**: *Read and write*
3. **Generate token** 을 누르고 나온 긴 글자(github_pat_...)를 복사합니다.
   **이 값은 채팅에 붙여 넣지 마세요.** 바로 아래 4번에만 넣습니다.

## 4. 열쇠를 코드 저장소에 등록

1. https://github.com/dhpaeng81-crypto/kwagent-src/settings/secrets/actions 를 엽니다.
2. **New repository secret** → Name: `SITE_TOKEN`, Secret: 복사한 값 붙여 넣기 → **Add secret**.

## 5. Claude 에게 "등록 완료"라고 알려 주기

Claude 가 실행을 한 번 돌려 두 공개 저장소에 웹사이트와 robots.txt 를 올립니다.

## 6. 공개 저장소 두 곳에서 사이트 게시 켜기 (5번이 끝난 뒤)

각각 **Settings → Pages** 에서 **Source: Deploy from a branch**, **Branch: `main` / `(root)`** → **Save**.
- https://github.com/dhpaeng81-crypto/kwagent/settings/pages
- https://github.com/dhpaeng81-crypto/dhpaeng81-crypto.github.io/settings/pages

1~2분 뒤 https://dhpaeng81-crypto.github.io/kwagent/ 가 다시 열립니다.

## 7. 코드 저장소 비공개로 바꾸기

1. https://github.com/dhpaeng81-crypto/kwagent-src/settings 맨 아래 **Danger Zone → Change visibility → Make private**.
2. 확인 문구를 입력하고 바꿉니다.

끝입니다. 이후 매일·매주 실행은 비공개 저장소에서 돌고, 완성된 화면만 공개 저장소로 올라갑니다.

---

### 알아 둘 점
- 비공개 저장소의 자동 실행(Actions)은 무료로 월 2,000분까지입니다. 지금 사용량은 월 약 400분이라 여유가 있습니다.
- 토큰이 만료되면 사이트가 갱신되지 않습니다(예측은 계속 돌아감). 1년마다 3~4번을 다시 하면 됩니다.
- 공개 저장소 `kwagent` 에는 화면 파일(HTML·그래프 자료·엑셀)만 있습니다. 화면에 보이는 숫자는 원래 공개된 정보라
  이 부분은 이용약관·AI 거부 표시로 보호합니다.
