# NthLayer Model-Agnostic LLM Wrapper

## Problem

NthLayer's agentic components (nthlayer-correlate reasoning layer, nthlayer-respond agents) are locked to the Anthropic Python SDK. Users should be able to choose their model provider: Anthropic, OpenAI, Azure, Ollama (local), Together AI, Groq, Mistral, vLLM, or any OpenAI-compatible server.

## Design Principle

NthLayer's LLM interaction pattern is simple: system prompt + user message in, text out. No tool use, no streaming, no multi-turn, no vision. This means the abstraction is thin — two API formats cover the entire market:

1. **Anthropic Messages API** — used only by Anthropic
2. **OpenAI Chat Completions API** — used by everyone else (OpenAI, Azure, Ollama, vLLM, Together, Groq, Mistral, LM Studio, and any OpenAI-compatible server)

No third-party LLM libraries. No LiteLLM (recently compromised in a supply chain attack — CVE-2025-45809). One file, one dependency (httpx, already in the project), two code paths.

## The Wrapper

Create a single shared module that every agentic component uses.

### File: nthlayer-common/src/nthlayer_common/llm.py

If nthlayer-common doesn't exist as a shared package, create the file in whichever location makes sense for the project structure. The key requirement is that both nthlayer-correlate and nthlayer-respond can import it. Options:

- A shared `nthlayer-common` package that both depend on
- Duplicate the file in both packages (not ideal but acceptable for now)
- Place it in nthlayer-learn (which both already depend on for the verdict store)

Audit the current dependency graph before deciding.

```python
"""
Unified LLM interface for NthLayer agentic components.

Two API formats cover the entire market:
- Anthropic Messages API (Anthropic only)
- OpenAI Chat Completions API (everyone else)

No third-party LLM libraries. No LiteLLM.

Usage:
    from nthlayer_common.llm import llm_call

    response = llm_call(
        system="You are a triage agent...",
        user="Evaluate this incident...",
    )

Configuration via environment:
    NTHLAYER_MODEL          — provider/model (default: anthropic/claude-sonnet-4-20250514)
    NTHLAYER_LLM_TIMEOUT    — seconds (default: 60)
    ANTHROPIC_API_KEY       — for anthropic/* models
    OPENAI_API_KEY          — for openai/*, together/*, groq/*, mistral/*, azure/* models
    OPENAI_API_BASE         — override endpoint URL for any provider
    AZURE_OPENAI_ENDPOINT   — Azure OpenAI resource URL
"""

import os
import json
import httpx
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("NTHLAYER_MODEL", "anthropic/claude-sonnet-4-20250514")
TIMEOUT = int(os.environ.get("NTHLAYER_LLM_TIMEOUT", "60"))


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    text: str           # The response content
    model: str          # Model that was used
    provider: str       # Provider that was used


class LLMError(Exception):
    """Raised when an LLM call fails."""
    def __init__(self, message: str, provider: str, model: str, cause: Exception | None = None):
        self.provider = provider
        self.model = model
        self.cause = cause
        super().__init__(f"[{provider}/{model}] {message}")


def llm_call(
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 2000,
    timeout: int | None = None,
) -> LLMResponse:
    """
    Unified LLM call for all NthLayer agentic components.

    Model format: "provider/model-name"
      - anthropic/claude-sonnet-4-20250514
      - openai/gpt-4o
      - ollama/llama3.1
      - azure/my-deployment
      - together/meta-llama/Llama-3-70b
      - groq/llama-3.1-70b-versatile
      - mistral/mistral-large-latest
      - vllm/my-model
      - lmstudio/my-model
      - custom/my-model (with OPENAI_API_BASE set)

    Provider determines the API format and endpoint:
      - "anthropic/*"  → Anthropic Messages API
      - Everything else → OpenAI-compatible Chat Completions API

    Returns LLMResponse with the text content, model, and provider.
    Raises LLMError on failure with provider/model context.
    """
    model = model or DEFAULT_MODEL
    _timeout = timeout or TIMEOUT

    # Parse provider from model string
    if "/" in model:
        provider, _, model_name = model.partition("/")
    else:
        # Bare model name — guess provider from known prefixes
        provider = _guess_provider(model)
        model_name = model

    try:
        if provider == "anthropic":
            text = _call_anthropic(system, user, model_name, max_tokens, _timeout)
        else:
            text = _call_openai_compat(system, user, model_name, provider, max_tokens, _timeout)

        return LLMResponse(text=text, model=model_name, provider=provider)

    except httpx.HTTPStatusError as e:
        raise LLMError(
            f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            provider, model_name, e,
        ) from e
    except httpx.TimeoutException as e:
        raise LLMError(
            f"Timeout after {_timeout}s",
            provider, model_name, e,
        ) from e
    except Exception as e:
        if isinstance(e, LLMError):
            raise
        raise LLMError(str(e), provider, model_name, e) from e


def _call_anthropic(system: str, user: str, model: str, max_tokens: int, timeout: int) -> str:
    """Call Anthropic Messages API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY not set", "anthropic", model)

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["content"][0]["text"]


def _call_openai_compat(
    system: str, user: str, model: str, provider: str, max_tokens: int, timeout: int
) -> str:
    """
    Call OpenAI-compatible Chat Completions API.

    Works with: OpenAI, Azure OpenAI, Ollama, vLLM, Together AI,
    Groq, Mistral, LM Studio, any OpenAI-compatible server.
    """
    base_url = os.environ.get("OPENAI_API_BASE") or _default_base_url(provider)
    api_key = os.environ.get("OPENAI_API_KEY", "not-needed")  # Ollama/vLLM don't require keys

    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _default_base_url(provider: str) -> str:
    """Default API base URLs by provider."""
    defaults = {
        "openai": "https://api.openai.com/v1",
        "ollama": "http://localhost:11434/v1",
        "vllm": "http://localhost:8000/v1",
        "lmstudio": "http://localhost:1234/v1",
        "together": "https://api.together.xyz/v1",
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "azure": os.environ.get(
            "AZURE_OPENAI_ENDPOINT",
            "https://your-resource.openai.azure.com/openai/deployments"
        ),
    }
    return defaults.get(provider, "https://api.openai.com/v1")


def _guess_provider(model: str) -> str:
    """Guess provider from bare model name."""
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "openai"
    if model.startswith("llama") or model.startswith("mistral") or model.startswith("gemma"):
        return "ollama"
    return "openai"  # Default: assume OpenAI-compatible
```

## Migration

### Audit First

Before migrating, find every LLM call site:

```bash
# Find all Anthropic SDK usage
grep -rn "import anthropic" nthlayer-correlate/ nthlayer-respond/
grep -rn "anthropic.Anthropic" nthlayer-correlate/ nthlayer-respond/
grep -rn "client.messages.create" nthlayer-correlate/ nthlayer-respond/

# Find all places that reference the model name
grep -rn "claude-" nthlayer-correlate/ nthlayer-respond/

# Find the anthropic dependency in project files
grep -rn "anthropic" nthlayer-correlate/pyproject.toml nthlayer-respond/pyproject.toml
```

Document every call site before changing anything.

### Migration Pattern

Every existing call follows this pattern:

```python
# BEFORE (Anthropic SDK)
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}],
)
text = response.content[0].text
```

Replace with:

```python
# AFTER (unified wrapper)
from nthlayer_common.llm import llm_call, LLMError

try:
    result = llm_call(system=system_prompt, user=user_prompt)
    text = result.text
except LLMError as e:
    # Handle degraded mode — same pattern as existing error handling
    logger.warning(f"LLM call failed: {e}")
    text = None  # or whatever the existing fallback is
```

The model is no longer hardcoded — it comes from `NTHLAYER_MODEL` environment variable. The provider is determined automatically from the model string.

### nthlayer-respond Migration

The respond component has four agents (triage, investigation, communication, remediation) plus a base class. The Anthropic client is likely initialised in `agents/base.py` or `snapshot/model.py`.

Steps:
1. Read `agents/base.py` — find where the Anthropic client is created and where `client.messages.create()` is called
2. Read each agent file — confirm they all go through the base class for LLM calls
3. Replace the Anthropic client initialisation and call with `llm_call()`
4. Remove `import anthropic` from all files
5. Update error handling: `anthropic.APIError` → `LLMError`
6. Remove `anthropic` from `pyproject.toml` dependencies
7. Add `nthlayer-common` (or httpx if it's not already there) to dependencies

The existing pattern in respond uses `asyncio.to_thread()` for async wrapping of sync Anthropic calls. Since `llm_call()` is also sync (using httpx sync client), the same async wrapping pattern works unchanged:

```python
# If the existing code does:
result = await asyncio.to_thread(client.messages.create, ...)

# Replace with:
result = await asyncio.to_thread(llm_call, system=..., user=...)
```

### nthlayer-correlate Migration

The correlate reasoning layer (if implemented) also calls the Anthropic SDK. Same migration pattern. If the reasoning layer was just implemented, it may already be in a single file (`reasoning.py`) making the migration straightforward.

### Dependencies

**Remove:** `anthropic` from both nthlayer-correlate and nthlayer-respond pyproject.toml

**Keep:** `httpx` (already a dependency in both components)

**Add:** Whatever is needed to import the shared llm.py. Options:
- If using a shared package: add `nthlayer-common` as a dependency
- If duplicating the file: no new dependency needed
- If placing in nthlayer-learn: already a dependency of both

## Configuration

### Environment Variables

```bash
# Model selection (provider/model-name format)
NTHLAYER_MODEL="anthropic/claude-sonnet-4-20250514"   # default

# Timeout for LLM calls in seconds
NTHLAYER_LLM_TIMEOUT="60"                              # default

# Provider-specific API keys
ANTHROPIC_API_KEY="sk-ant-..."                         # for anthropic/* models
OPENAI_API_KEY="sk-..."                                # for openai/*, together/*, groq/*, etc.

# Endpoint overrides
OPENAI_API_BASE="http://localhost:11434/v1"            # override for any provider
AZURE_OPENAI_ENDPOINT="https://myresource.openai.azure.com/openai/deployments"
```

### CLI Flag (optional, per-command override)

```bash
nthlayer-respond respond --trigger-verdict <id> --model "openai/gpt-4o"
nthlayer-correlate correlate --trigger-verdict <id> --model "ollama/llama3.1"
```

If a `--model` flag is passed, it takes precedence over `NTHLAYER_MODEL`. Add this flag to both correlate's `correlate` subcommand and respond's `respond` subcommand. Pass it through to `llm_call(model=args.model)`.

### Demo Configuration

Update `demo/demo.sh` to use `NTHLAYER_MODEL` instead of `ANTHROPIC_API_KEY` for model configuration:

```bash
# In demo.sh scenario:
if [[ -z "${NTHLAYER_MODEL:-}" ]]; then
    if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        export NTHLAYER_MODEL="anthropic/claude-sonnet-4-20250514"
        info "Using Anthropic Claude (ANTHROPIC_API_KEY set)"
    else
        warn "No NTHLAYER_MODEL or ANTHROPIC_API_KEY set — agents will fail"
    fi
fi
```

## Tests

### Unit Tests for llm.py

1. **Anthropic path:** Mock httpx.post to return a valid Anthropic response. Verify `llm_call("system", "user", model="anthropic/claude-sonnet-4-20250514")` returns the text.
2. **OpenAI path:** Mock httpx.post to return a valid OpenAI response. Verify `llm_call("system", "user", model="openai/gpt-4o")` returns the text.
3. **Ollama path:** Mock httpx.post, verify the URL is `http://localhost:11434/v1/chat/completions`.
4. **Custom base URL:** Set `OPENAI_API_BASE`, verify the URL is used.
5. **Missing API key (Anthropic):** Unset `ANTHROPIC_API_KEY`, verify `LLMError` is raised with a clear message.
6. **Timeout:** Mock a timeout, verify `LLMError` with timeout message.
7. **HTTP error:** Mock a 429 response, verify `LLMError` with status code.
8. **Bare model name:** Verify `_guess_provider("claude-sonnet-4-20250514")` returns "anthropic" and `_guess_provider("gpt-4o")` returns "openai".
9. **LLMResponse fields:** Verify the response includes text, model, and provider.

### Integration Tests

1. **Existing respond tests must pass.** The mock patterns may need updating (mocking `httpx.post` instead of `anthropic.Anthropic().messages.create`), but the test logic and assertions should be identical.
2. **Existing correlate tests must pass with `--no-reasoning`.** The reasoning layer is additive; transport-only mode doesn't call the LLM.
3. **Demo scenario must produce the same verdict quality.** Run the demo and verify triage still says "AI model quality degradation," remediation still says "rollback," and the retrospective still includes the counterfactual recommendation.

## Implementation Order

1. **Audit:** Find every LLM call site in correlate and respond. Document them.
2. **Create llm.py:** The shared wrapper module. Decide where it lives (shared package or duplicated).
3. **Write unit tests for llm.py:** All 9 tests above, with mocked httpx.
4. **Migrate nthlayer-respond:** Replace Anthropic SDK calls with `llm_call()`. Update error handling. Remove anthropic dependency.
5. **Run respond test suite.** All existing tests must pass.
6. **Migrate nthlayer-correlate reasoning layer:** Same pattern.
7. **Run correlate test suite.** All existing tests must pass.
8. **Add `--model` CLI flag** to both correlate and respond.
9. **Update demo.sh** to use `NTHLAYER_MODEL`.
10. **Run the full demo scenario.** Verify verdict quality is unchanged.
11. **Test with a different provider** (e.g. `openai/gpt-4o` if you have a key, or `ollama/llama3.1` if you have Ollama installed) to confirm provider switching works.

## What This Enables

- **Enterprise adoption:** Organisations with Azure-only or AWS Bedrock-only policies can use NthLayer without an Anthropic dependency
- **Local/private deployment:** Teams that can't send data to external APIs use Ollama or vLLM with local models
- **Cost optimisation:** Use cheaper models (Groq, Together) for lower-stakes agents (communication) and premium models (Claude, GPT-4o) for high-stakes agents (investigation, remediation)
- **Per-component model selection:** Future enhancement where `NTHLAYER_TRIAGE_MODEL`, `NTHLAYER_REMEDIATION_MODEL` etc. allow different models for different agents based on task complexity
- **No supply chain risk from LLM libraries:** The wrapper is 50 lines of httpx calls. No third-party LLM abstraction library. The only dependency is httpx, which NthLayer already uses and which is one of the most widely audited Python HTTP libraries.
