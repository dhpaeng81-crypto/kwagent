#!/usr/bin/env bash
# 비공개 코드 저장소 → 공개 저장소로 '완성된 웹사이트만' 보낸다 (코드·예측 기록·채점 자료는 보내지 않음).
#   site/       → github.com/<OWNER>/<SITE_REPO>   (https://<OWNER>.github.io/kwagent/)
#   site_root/  → github.com/<OWNER>/<OWNER>.github.io (도메인 맨 앞: robots.txt·ai.txt·tdmrep.json)
# 필요: 환경변수 SITE_TOKEN (두 공개 저장소에 Contents 쓰기 권한이 있는 fine-grained 토큰, Actions 비밀값)
set -euo pipefail
OWNER="${OWNER:-dhpaeng81-crypto}"
SITE_REPO="${SITE_REPO:-kwagent}"
ROOT_REPO="${ROOT_REPO:-${OWNER}.github.io}"
HERE="$(pwd)"

push_dir() {
  local src="$1" repo="$2" msg="$3" tmp
  tmp="$(mktemp -d)"
  if ! git clone -q --depth 1 "https://x-access-token:${SITE_TOKEN}@github.com/${OWNER}/${repo}.git" "$tmp" 2>/dev/null; then
    echo "::error::공개 저장소 ${OWNER}/${repo} 에 접근할 수 없습니다 (저장소가 있는지, 토큰 권한이 맞는지 확인)"
    return 1
  fi
  find "$tmp" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
  cp -a "$HERE/$src"/. "$tmp"/
  cp "$HERE/LICENSE" "$tmp/LICENSE"
  (
    cd "$tmp"
    git config user.name "kwagent-bot"
    git config user.email "kwagent-bot@users.noreply.github.com"
    git checkout -q -B main
    git add -A
    if git diff --cached --quiet; then
      echo "${repo}: 변경 없음"
    else
      git commit -q -m "$msg"
      git push -q origin HEAD:main
      echo "${repo}: 게시 완료"
    fi
  )
}

push_dir site "$SITE_REPO" "site $(date +%F' '%H:%M)"
push_dir site_root "$ROOT_REPO" "root $(date +%F)" || echo "::warning::${ROOT_REPO} 게시 실패 — robots.txt 가 아직 반영되지 않음"
