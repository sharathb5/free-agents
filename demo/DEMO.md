# Free Agents — 2-Minute Demo

## Before you start (do once)

```bash
# Terminal 1 — backend (run from agent-toolbox/agent-toolbox/)
make run AGENT=draft-from-repo

# Terminal 2 — frontend (run from agent-toolbox/agent-toolbox/frontend/)
npm run dev
```

Browser: `http://localhost:3000`

---

## Demo sequence

### 1. Show the homepage (~20s)
- Open `http://localhost:3000`
- Point to the agent grid — "These are runnable agents generated from real repos"
- Point to `openai-agents-python` card

### 2. Show the draft-generation flow (~40s)
- Click **Add your own agent** → **Import from GitHub**
- Paste: `https://github.com/openai/openai-agents-python`
- Let it analyze (or use a pre-run result if showing live is too slow)
- Narrate: "It's parsing the repo — extracting tools, inferring memory posture, recommending a bundle"
- Point to extracted Makefile targets (lint, typecheck, tests, build-docs…)
- Point to AUTO-SAFE vs REVIEW labels
- Point to **Repo to Agent** bundle selection

### 3. Show the saved agent modal (~30s)
- Click the `openai-agents-python` card on the homepage
- Walk through **Overview** tab:
  - Purpose / Source / Bundle / Tools / Memory / Use cases
- Click **API + Schema** tab:
  - Show POST endpoint
  - Show example request
  - Show example output

### 4. Live invocation (~30s)
Switch to VS Code terminal:

```bash
python demo/demo_request.py
```

Or pass a custom question:

```bash
python demo/demo_request.py "Explain the main API surface and common usage patterns"
```

Watch the response print cleanly. Narrate:
> "This is the agent running live — it called github_repo_read, read the repo, and returned a structured answer."

---

## Likely questions

**"Is this just a README summarizer?"**
No — it extracts runnable capabilities (Makefile targets, scripts), wraps them with governance labels, maps them to an API, and gives you an invoke endpoint. The repo structure becomes an operational artifact.

**"What models does it support?"**
OpenRouter by default — swappable. The gateway is model-agnostic.

**"Can it run the repo's own scripts?"**
Yes — promoted repo tools with AUTO-SAFE posture can be called directly through the API.

---

## Fallbacks

| Problem | Fix |
|---|---|
| Gateway not running | `make run AGENT=draft-from-repo` |
| Agent not found | Check: `curl http://localhost:4280/agents/draft-from-repo` |
| Slow response | Pre-run once before demo; response is not cached but model is warm |
| Empty modal sections | Fallbacks are hardcoded — all sections always render |
| `jq` not installed | Script falls back to `python3 -m json.tool` |
