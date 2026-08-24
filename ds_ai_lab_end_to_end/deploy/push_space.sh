#!/usr/bin/env bash
# Assemble and push one Hugging Face Space from this monorepo.
#
#   ./deploy/push_space.sh backend
#   ./deploy/push_space.sh proxy
#   ./deploy/push_space.sh frontend
#
# Each Space is its own git repo and needs its own README frontmatter at ITS
# root, which is why the file sets are assembled here rather than pushing the
# monorepo three times. Nothing is force-pushed and nothing is deleted locally:
# the script builds a staging directory under .deploy-tmp/ and pushes that.
#
# Deploy order matters. Push the backend first and confirm its API signature
# before pushing anything that depends on it:
#
#   python -c "from gradio_client import Client; \
#     print(Client('rajsri2609/medical-report-ai', token='$HF_TOKEN').view_api())"
#
# /chat must list THREE parameters (message, history, report_context). If it
# lists two, gr.State has crept back in and the chatbot will silently answer
# with no knowledge of the patient's report.

set -euo pipefail

TARGET="${1:-}"
# Defaults to whoever is logged into the HF CLI, so the script never silently
# pushes to somebody else's namespace. Override with HF_USER=... if needed.
# `hf auth whoami` prints "user=<name>", so strip the key.
HF_USER="${HF_USER:-$(hf auth whoami 2>/dev/null | head -1 | sed 's/^user=//' | tr -d '[:space:]')}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$ROOT/.deploy-tmp/$TARGET"

if [ -z "$HF_USER" ]; then
  echo "ERROR: not logged in. Run: hf auth login" >&2; exit 1
fi

case "$TARGET" in
  backend)  SPACE="medical-report-ai" ;;
  proxy)    SPACE="medical-report-ai-proxy" ;;
  frontend) SPACE="medical-report-ai-ui" ;;
  *) echo "usage: $0 {backend|proxy|frontend}" >&2; exit 2 ;;
esac

# Which backend the UI talks to. On the free-tier topology the browser calls the
# public ZeroGPU backend directly and there is no proxy, so the analyze endpoint
# is the backend's own /analyze_report rather than the proxy's /analyze.
UI_ENDPOINT="${UI_ENDPOINT:-$HF_USER/medical-report-ai}"
UI_ANALYZE_API="${UI_ANALYZE_API:-/analyze_report}"

# Create the Space with the right SDK and hardware if it does not exist yet.
# Doing this over the API means ZeroGPU never has to be selected by hand in the
# Space settings UI, and a redeploy cannot silently land on the wrong hardware.
echo "==> ensuring Space $HF_USER/$SPACE exists"
SPACE_SDK=gradio; SPACE_HW=cpu-basic
case "$TARGET" in
  backend)  SPACE_SDK=gradio; SPACE_HW=zero-a10g ;;   # zero-a10g == ZeroGPU
  proxy)    SPACE_SDK=gradio; SPACE_HW=cpu-basic ;;
  frontend) SPACE_SDK=static; SPACE_HW=cpu-basic ;;
esac

python3 - "$HF_USER/$SPACE" "$SPACE_SDK" "$SPACE_HW" <<'PYEOF'
import sys
from huggingface_hub import HfApi
repo, sdk, hw = sys.argv[1], sys.argv[2], sys.argv[3]
api = HfApi()
api.create_repo(repo_id=repo, repo_type="space", space_sdk=sdk,
                space_hardware=hw, exist_ok=True)
info = api.space_info(repo)
current = getattr(info.runtime, "hardware", None)
print(f"    sdk={info.sdk} hardware={current}")
if hw != "cpu-basic" and current != hw:
    # exist_ok=True does not change hardware on an existing Space.
    print(f"    requesting {hw} ...")
    api.request_space_hardware(repo_id=repo, hardware=hw)
PYEOF

echo "==> staging $TARGET for $HF_USER/$SPACE"
rm -rf "$STAGE"; mkdir -p "$STAGE"

case "$TARGET" in
  backend)
    cp "$ROOT/app.py"            "$STAGE/"
    cp "$ROOT/requirements.txt"  "$STAGE/"
    cp "$ROOT/packages.txt"      "$STAGE/"
    cp -r "$ROOT/backend"        "$STAGE/backend"
    cp "$ROOT/deploy/README-backend.md" "$STAGE/README.md"
    # Never ship caches or the local vector index.
    find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
    rm -rf "$STAGE/backend/app/reference_ranges/chroma_index"
    # reference_db.json MUST ship: it is the parsed reference table and the
    # Space would otherwise need the xlsx and openpyxl at boot.
    test -f "$STAGE/backend/app/reference_ranges/reference_db.json" \
      || { echo "ERROR: reference_db.json missing" >&2; exit 1; }
    ;;
  proxy)
    cp "$ROOT/proxy/app.py"          "$STAGE/"
    cp "$ROOT/proxy/requirements.txt" "$STAGE/"
    cp "$ROOT/deploy/README-proxy.md" "$STAGE/README.md"
    ;;
  frontend)
    # Built HERE, not on the Space. Hugging Face's server-side static build
    # (app_build_command) is a paid feature - an unpaid Space reports
    # "Static space builds require credits" and sits in CONFIG_ERROR. Serving a
    # pre-built bundle from a plain static Space is free.
    echo "    building locally against $UI_ENDPOINT $UI_ANALYZE_API"
    # Vite resolves .env.local ABOVE shell variables, so a developer's local
    # override would otherwise win and ship a bundle pointing at 127.0.0.1.
    # Move it aside for the build and always put it back.
    if [ -f "$ROOT/.env.local" ]; then
      mv "$ROOT/.env.local" "$ROOT/.env.local.deploybak"
      trap 'mv -f "$ROOT/.env.local.deploybak" "$ROOT/.env.local" 2>/dev/null || true' EXIT
      echo "    (.env.local moved aside for the build; restored afterwards)"
    fi

    ( cd "$ROOT" \
      && VITE_GRADIO_ENDPOINT="$UI_ENDPOINT" VITE_ANALYZE_API="$UI_ANALYZE_API" \
         npm run build >/dev/null 2>&1 ) \
      || { echo "ERROR: npm run build failed - run it manually to see why" >&2; exit 1; }

    test -f "$ROOT/dist/index.html" \
      || { echo "ERROR: dist/index.html missing after build" >&2; exit 1; }

    cp -r "$ROOT/dist/." "$STAGE/"
    cp "$ROOT/deploy/README-frontend.md" "$STAGE/README.md"

    # Confirm the bundle really points at the intended backend before shipping.
    # Only a local *Gradio* endpoint (:7860) indicates a misbuild; the bundle
    # legitimately contains 127.0.0.1:8000 from the vitest-only fetch branch,
    # which never executes in a browser.
    if grep -rq "127\.0\.0\.1:7860\|localhost:7860" "$STAGE"/assets/*.js 2>/dev/null; then
      echo "ERROR: bundle points at a local backend - check .env.local" >&2; exit 1
    fi
    if ! grep -rq "$UI_ENDPOINT" "$STAGE"/assets/*.js 2>/dev/null; then
      echo "ERROR: bundle does not reference $UI_ENDPOINT - build did not pick up the env" >&2
      exit 1
    fi
    echo "    verified: bundle targets $UI_ENDPOINT"
    ;;
esac

echo "==> uploading to https://huggingface.co/spaces/$HF_USER/$SPACE"
# Uploaded through the Hub API rather than `git push`, so the stored HF token is
# used directly and no git credential helper is required. delete_patterns clears
# files that no longer exist locally, which a plain upload would otherwise leave
# behind on the Space.
python3 - "$HF_USER/$SPACE" "$STAGE" "$TARGET" <<'PYEOF'
import sys
from huggingface_hub import HfApi
repo, folder, target = sys.argv[1], sys.argv[2], sys.argv[3]
HfApi().upload_folder(
    repo_id=repo,
    repo_type="space",
    folder_path=folder,
    commit_message=f"Deploy {target}",
    delete_patterns="*",
)
PYEOF
echo "==> done: https://huggingface.co/spaces/$HF_USER/$SPACE"
