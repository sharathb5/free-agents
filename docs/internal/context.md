# Free Agents — Project Context for AI Assistant

## Project Summary

**Free Agents** is a platform for turning repository-native AI workflows into structured, reusable, and operational agents.

The core idea is that many AI agents and workflows live buried inside code repositories. They are hard to discover, reuse, govern, or operationalize. Free Agents addresses this by:

1. **Analyzing a repository**
2. **Generating a draft agent spec** from the repo
3. **Extracting repo-native capabilities** like scripts, Makefile targets, and other runnable surfaces
4. **Recommending tools / bundles / memory / schema defaults**
5. **Saving the result as an agent preset**
6. **Making the resulting agent operational via an API / local gateway**

The strongest framing for the product is:

> **Repo → Agent → API**

This is not just repo summarization. The value is turning code and workflows hidden inside repos into governable, reusable, API-callable agent artifacts.

---

## High-Level Product Pitch

Free Agents takes a codebase and turns it into a more structured, governable agent draft with:

* extracted capabilities
* memory controls
* recommended tool surfaces
* bundle selection
* input / output schema slots
* an API-ready invocation path

A strong one-line description:

> Free Agents ingests a codebase, turns it into a structured and governable agent draft, and helps make that agent operational by exposing it through an API.

---

## Target Demo Narrative

The demo should emphasize the following progression:

1. **We used a real repo as input**
2. **Free Agents parsed that repo into a draft agent**
3. **It extracted tools and operational surfaces from the repo**
4. **It configured memory / prompt / bundle posture**
5. **The saved agent becomes runnable and invocable through an API**

The most important takeaway for a viewer should be:

> This is not just a parser. It is a system that turns hidden repo logic into an operational AI service.

---

## Demo Repo Being Used

Use the **OpenAI Agents SDK Python repo**:

* Repo: `https://github.com/openai/openai-agents-python`

Why this repo is the best demo input:

* It is a real, recognizable, modern agent-oriented codebase
* It contains tools, examples, orchestration patterns, and structured workflows
* It is much higher-signal than a toy repo or random tutorial repo
* It aligns directly with the product story of turning agent-oriented repos into reusable agents

---

## Current Repo-to-Agent Flow

### 1. Repository Analysis

The system analyzes the repository and produces a repo-derived draft.

### 2. Draft Agent Generation

The system fills fields like:

* name
* version
* agent ID
* primitive
* description
* tags
* prompt
* input schema
* output schema
* memory settings

### 3. Capability Extraction

The system extracts repo-native actions from the repository, including:

* **Makefile targets**
* **example scripts**
* other likely runnable / operational repo surfaces

Example extracted items seen in the OpenAI repo flow:

* `sync`
* `format`
* `format-check`
* `lint`
* `mypy`
* `pyright`
* `typecheck`
* `tests`
* `tests-asyncio-stability`
* `tests-parallel`
* `tests-serial`
* `coverage`
* `build-docs`
* `build-full-docs`
* `serve-docs`
* `deploy-docs`
* `check`
* `auto_mode`
* `run_examples`

### 4. Tool Promotion / Safety Posture

Extracted actions are wrapped into promoted repo tool metadata with lightweight governance.

The UI currently shows labels such as:

* `AUTO-SAFE`
* `REVIEW`

And command risk levels such as:

* low
* medium
* high

The important concept here is:

* Left side = what exists in the repo
* Right side = what the platform is willing to expose and under what safety posture

### 5. Bundle Recommendation

The system recommends a starting bundle for the generated agent.

Example bundles shown:

* Research Basic
* Writer (No Tools)
* GitHub Reader
* Repo to Agent
* Data Analysis

For this flow, **Repo to Agent** is the correct selected bundle.

### 6. Agent Preset / API Path

Once saved, the draft becomes a usable agent preset that can be run locally and invoked over HTTP.

Example local run path:

* local gateway at `http://localhost:4280`
* agent invoke endpoint like `/agents/draft-from-repo/invoke`

This is the key “agent becomes API” story.

---

## OpenAI SDK Usage in the Project

The project uses the **OpenAI Agents SDK** as part of the orchestration layer for the repo-to-agent flow.

Important points to preserve:

* We are not treating the whole task as one giant prompt
* We use an agent-oriented pipeline with specialized roles / stages
* The SDK helps represent agents with:

  * instructions
  * tools
  * structured outputs
* This makes the repo-to-agent process easier to extend over time
* It also supports a cleaner path to tool use, structured handoffs, and typed outputs

Good explanation language:

> Under the hood, we use the OpenAI Agents SDK so the pipeline is agent-structured, not just one big prompt. That lets us break the task into steps like repo understanding, capability detection, and draft generation.

And:

> We’re using agent-oriented infrastructure to help operationalize other agent-oriented codebases.

---

## Current UI / UX State

There are two major surfaces relevant to the demo:

### A. Draft Agent Creation Flow

This is the screen that shows:

* generated metadata
* prompt
* schemas
* memory settings
* extracted repo tools
* promoted tool metadata
* recommended bundle
* selected tool state

This screen is already high-signal and good for explaining parsing, extraction, bundle selection, and memory.

### B. Saved Agent Card / Modal

This is the screen that appears after the agent is saved.

It currently has tabs such as:

* Overview
* Get set up
* API + Schema

This screen currently proves the agent exists, but it does **not yet fully express the value** of the system.

---

##