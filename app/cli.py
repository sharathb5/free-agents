"""CLI entry point for the agent-toolbox package."""

from __future__ import annotations

import os
import sys

# OpenRouter: one API key for many models (OpenAI, Claude, Gemini, etc.)
OPENROUTER_KEYS_URL = "https://openrouter.ai/keys"


def _print_setup_banner(
    preset: str,
    provider: str,
    port: int,
    *,
    for_startup: bool = True,
) -> None:
    """Print setup/LLM instructions. If for_startup, show 'gateway started' line; else show 'Setup' header."""
    provider_note = "no API key required" if provider == "stub" else "API key from .env"
    base = f"http://localhost:{port}"
    print()
    if for_startup:
        print("✅ Agent gateway started — agent preset: {}".format(preset))
    else:
        print("Agent Toolbox — Setup")
        print("Agent preset: {}  |  Provider: {} ({})".format(preset, provider, provider_note))
    if for_startup:
        print("Provider: {} ({})".format(provider, provider_note))
    print()
    print("Docs:     {}/docs".format(base))
    print("Schema:   {}/schema".format(base))
    print("Examples: {}/examples".format(base))
    print()
    print("────────────────────────────────────────────")
    print("Get an API key from OpenRouter (one key for many models):")
    print("   {}".format(OPENROUTER_KEYS_URL))
    print()
    print("Create a .env file in this folder (or edit it if you already have one).")
    print("   Mac/Linux:  nano .env")
    print("   Windows:    notepad .env")
    print()
    print("Copy the block below into .env and replace YOUR_KEY_HERE with your key.")
    print("   Change OPENROUTER_MODEL to use a different model (see openrouter.ai/models).")
    print()
    print("   PROVIDER=openrouter")
    print("   OPENROUTER_API_KEY=YOUR_KEY_HERE")
    print("   OPENROUTER_MODEL=openai/gpt-4o-mini")
    print()
    print("Then restart: stop the server (Ctrl+C) and run agent-toolbox again.")
    print()


def main() -> None:
    """Run the agent gateway or print setup. Use 'agent-toolbox setup' to show setup only."""
    from .config import get_settings

    port = int(os.environ.get("PORT", "4280"))
    host = os.environ.get("HOST", "0.0.0.0")
    settings = get_settings()

    if len(sys.argv) > 1 and sys.argv[1].strip().lower() == "setup":
        _print_setup_banner(
            preset=settings.agent_preset,
            provider=settings.provider_name,
            port=port,
            for_startup=False,
        )
        sys.exit(0)

    import uvicorn

    _print_setup_banner(
        preset=settings.agent_preset,
        provider=settings.provider_name,
        port=port,
        for_startup=True,
    )

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        factory=False,
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
