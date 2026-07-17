# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- LangSmith tracing integration
- Scout/architect enrichment for repo-to-agent pipeline
- Perch MCP tooling and lightweight MCP server for Free Agents catalog API
- Frontend agent cards and upload flow with open-in-IDE context
- Registry store and `/agents` routes (repo-to-agent workflow)
- Replit deploy support (`--replit` flag, `free-agents` entry point)

### Fixed
- MCP: configurable upstream base, timeouts, and `/agents` payload handling
- Repo-to-agent: deterministic version per repo, bundle bias, grounded prompts
- Clerk session + GitHub OAuth integration for repo-to-agent imports
- Replit: git lock stale handling and `.git` write-block workaround

## [0.1.3] - 2024-12-01

### Added
- Initial public release of the Standardized Agent Runtime
- FastAPI gateway with `POST /invoke`, `GET /schema`, `GET /examples`, `GET /health`
- Preset system (summarizer, triage, classifier, extractor, meeting_notes)
- Session memory API (`POST /sessions`, `POST /sessions/{id}/events`, `GET /sessions/{id}`)
- Multi-provider support: StubProvider, OpenRouterProvider, OpenAIProvider
- Clerk JWT authentication (JWKS-based verification)
- GitHub OAuth path for repo listing (`/github/oauth/*`)
- Docker + Docker Compose support, multi-arch GHCR image
- Render deployment support with dynamic `PORT` binding
- CLI entry points: `agent-toolbox` and `free-agents`

## [0.1.2] - 2024-11-15

### Added
- Troubleshooting documentation page
- Bootstrap script (`scripts/bootstrap.sh`) for one-command venv setup
- CLI test coverage

[Unreleased]: https://github.com/sharathb5/free-agents/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/sharathb5/free-agents/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/sharathb5/free-agents/releases/tag/v0.1.2
