# AGENTS.md — Cominty Python SDK Coding Bible

This document is the authoritative guide for every coding agent and contributor working on
`cominty-sdk`. It defines conventions, patterns, and rules that must be followed across the
entire codebase. Deviations require an explicit, justified comment at the call site.

---

## 1. Language & Runtime

- **Python 3.13+** is the minimum target for new code. `pyproject.toml` may list 3.11 for
  distribution compatibility, but the _source_ is written against 3.13 semantics.
- Use **modern built-in generics** everywhere — `list[str]`, `dict[str, int]`, `tuple[int, ...]`,
  `type[T]`. Never `typing.List`, `typing.Dict`, `typing.Tuple`, etc.
- Use **`X | Y`** for unions. Never `typing.Union[X, Y]` or `typing.Optional[X]`.
- Use **`from __future__ import annotations`** at the top of every module to enable
  postponed evaluation and keep forward references working without quotes.

---

## 2. Typing System

### 2.1 Generics — brackets, not aliases

```python
# WRONG
T = TypeVar("T")
def identity(x: T) -> T: ...

# RIGHT (Python 3.12+ syntax)
def identity[T](x: T) -> T: ...

class Stack[T]:
    def push(self, item: T) -> None: ...
    def pop(self) -> T: ...
```

Use PEP 695 type parameter syntax (`[T]`, `[T: Bound]`, `[*Ts]`) for all new generics.
Only fall back to `TypeVar` when a third-party library forces it.

### 2.2 ParamSpec for decorator signature transparency

All decorators that wrap callables **must** preserve the wrapped signature using `ParamSpec`:

```python
from typing import ParamSpec, Callable
import asyncio

def retry[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        ...
    return wrapper  # type: ignore[return-value]  # only here, where unavoidable
```

### 2.3 @overload for parameter-dependent return types

When a method's return type depends on the **value** of an argument, use `@overload` stubs
so IDEs infer the correct type at each call site:

```python
from typing import overload, Literal

@overload
async def send(self, *, stream: Literal[False] = ...) -> ChatResponse: ...
@overload
async def send(self, *, stream: Literal[True]) -> StreamHandle: ...
async def send(self, *, stream: bool = False) -> ChatResponse | StreamHandle: ...
```

### 2.4 Protocol over ABC for structural types

Prefer `typing.Protocol` (with `runtime_checkable` when needed) over abstract base classes.

### 2.5 TypedDict for plain data shapes

Use `TypedDict` for dict-shaped data flowing across I/O boundaries (e.g. raw API payloads
before parsing). Never use `dict[str, Any]` as a return type.

---

## 3. Pydantic Models

### 3.1 Config defaults

| Context | Config |
|---|---|
| **Request / input models** | `model_config = ConfigDict(strict=True, extra="forbid")` |
| **Response / output models** | `model_config = ConfigDict(extra="ignore")` |

Strict input catches caller mistakes immediately. Lenient output is forward-compatible with
API additions.

### 3.2 Naming

- Request models: `<Action><Resource>Params` — `CreateThreadParams`, `SendMessageParams`.
- Response models: `<Resource>` or `<Resource>Response` — `Thread`, `Message`, `ChatResponse`.
- No "Model" suffix. No "Data" suffix.

### 3.3 Location

Start with models **inline** in the resource file that owns them. Once a single resource
file exceeds ~200 lines of model definitions, extract to `models/<resource>.py`.

---

## 4. Error Handling

### 4.1 Exception hierarchy

```
ComintyError (base)
├── APIError               # HTTP 4xx/5xx from the server
│   ├── AuthError          # 401
│   ├── PermissionError    # 403
│   ├── NotFoundError      # 404
│   ├── ConflictError      # 409
│   ├── RateLimitError     # 429
│   └── ServerError        # 5xx
├── APIConnectionError     # network / timeout
└── SDKError               # bug in the SDK itself (should never reach users)
```

### 4.2 Typed error body

Every `APIError` carries a typed `.error` attribute parsed from the API response body:

```python
class APIErrorBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str
    message: str
    details: dict[str, object] | None = None

class APIError(ComintyError):
    status_code: int
    error: APIErrorBody
```

### 4.3 Rules

- **Raise early, never return `None` on failure.** If a method can't produce its return type,
  it raises — never returns `None` as a sentinel.
- All raises from the HTTP layer are caught in `_transport.py` and re-raised as `APIError`
  subclasses. Resource methods never catch raw `httpx` exceptions.
- SDK-level validation errors (wrong arguments, etc.) raise `ValueError` with a message that
  names both the bad argument and the expected type/value.

---

## 5. Async & Streaming

### 5.1 Async-only

The SDK is **async-only**. There is no `SyncCominty` wrapper. Users who need sync call
`asyncio.run()` themselves. This avoids hidden event-loop footguns and duplicated code.

### 5.2 StreamHandle

Streaming methods return a `StreamHandle` object, not a raw iterator:

```python
class StreamHandle[EventT]:
    async def events(self) -> AsyncIterator[EventT]: ...
    async def text(self) -> str: ...          # accumulates all text deltas
    async def __aiter__(self) -> AsyncIterator[EventT]: ...  # delegates to events()
```

`StreamHandle` is the return type of `stream=True` overloads. It owns the underlying
connection and must be used as an async context manager or consumed to completion.

### 5.3 Context manager on the client

`AsyncCominty` implements `__aenter__` / `__aexit__` and should be used with `async with`.
Calling `close()` manually is acceptable but not the idiomatic path.

---

## 6. Public Surface & Naming

### 6.1 The rule

The **only** public API is what `cominty_sdk/__init__.py` re-exports via an explicit
`__all__`. Everything else is implementation detail and may change without a semver bump.

### 6.2 Two enforcement signals (both required)

1. **`__all__`** in every module — governs `import *` and is the canonical list.
2. **Leading underscore** on every private name — visible at the call site, the load-bearing
   deterrent against `from cominty_sdk.client import _retry`.

Public names **never** carry an underscore. Private names **always** do.

### 6.3 Module layout

- Private modules at package root: `_transport.py`, `_auth.py`, `_retry.py`.
- Public modules at package root: `client.py`, `exceptions.py`, `streaming.py`.
- Promote private modules to `_internal/` subpackage only once they grow numerous enough
  to warrant grouping (aim for >4–5 private modules before splitting).

### 6.4 Symbol naming

| Kind | Convention | Example |
|---|---|---|
| Public class | `PascalCase` | `AsyncCominty`, `Thread` |
| Public function/method | `snake_case` | `send_message`, `list_threads` |
| Private module | `_snake_case.py` | `_transport.py` |
| Private symbol | `_snake_case` | `_build_headers`, `_http` |
| Constants | `SCREAMING_SNAKE` | `DEFAULT_TIMEOUT` |
| Type params | Single caps or short descriptive | `[T]`, `[EventT]`, `[BodyT]` |

---

## 7. Resource Pattern

### 7.1 Structure

Resources are attribute-namespaced on the client (`client.chat`, `client.threads`).
Each resource is a class in `resources/<name>.py`:

```python
class ThreadsResource:
    def __init__(self, http: AsyncHTTPClient, *, default_user_id: str | None = None) -> None:
        self._http = http
        self._default_user_id = default_user_id

    async def create(self, params: CreateThreadParams) -> Thread: ...
    async def get(self, thread_id: str) -> Thread: ...
    async def list(self) -> list[Thread]: ...
    async def delete(self, thread_id: str) -> None: ...
```

### 7.2 Method naming

Use CRUD verbs: `create`, `get`, `list`, `update`, `delete`. Use domain verbs for non-CRUD:
`send`, `stream`, `run`, `attach`.

### 7.3 Params vs kwargs

Prefer a typed `Params` model as the sole positional argument for complex inputs.
Simple identifiers (e.g. `thread_id`) are keyword-only args, never inside a Params model.

---

## 8. Toolchain

| Tool | Role | Config |
|---|---|---|
| **uv** | deps, venv, scripts | `pyproject.toml` |
| **ruff** | lint + format | `[tool.ruff]` |
| **pyright** | static type checking (strict mode) | `pyrightconfig.json` |
| **pytest + pytest-asyncio** | tests | `[tool.pytest.ini_options]` |

### 8.1 Pyright is the type oracle

Use `pyright --strict`. `mypy` is not run. If pyright and mypy disagree, pyright wins.
`# type: ignore` is only permitted at machine-generated or unavoidable FFI boundaries,
never to silence a real type error. Each ignore must have an inline comment explaining why.

### 8.2 Ruff

```toml
[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]
```

`ANN` (annotations) enforces that every public function is fully annotated.

---

## 9. Testing

### 9.1 Structure

```
tests/
  unit/        # stub HTTP layer, no network
  integration/ # real API, requires .env, opt-in via marker
  notebooks/   # contract + smoke notebooks (see §9.3)
```

### 9.2 Unit tests

Patch the HTTP layer with `respx`. Every resource method gets a unit test that:
1. Stubs the expected HTTP request/response.
2. Asserts the returned object is the correct Pydantic type.
3. Asserts the request URL, method, and body were correct.

No `MagicMock` on the resource classes themselves — test the real resource, fake the transport.

### 9.3 Notebook contract tests

`notebooks/contracts.ipynb` is the developer scratchpad for validating the SDK surface:

- **Stub layer cells**: instantiate the client with a patched transport, call every method,
  assert the return type. No credentials needed. Run with `jupyter nbconvert --execute`.
- **Live smoke cells**: guarded by `if os.getenv("COMINTY_API_KEY"):`, make real requests,
  print responses. `LIVE=True` toggle at the top of the notebook.

### 9.4 Markers

```python
@pytest.mark.integration  # skipped in CI unless COMINTY_API_KEY is set
```

---

## 10. Commit & PR Discipline

- One logical change per commit. Refactor and feature in separate commits.
- Commit messages: imperative present tense, ≤72 chars subject, blank line before body.
- No `# noqa` suppressions without an explanation comment.
- Every public method must appear in `__all__` of its module before merging.

---

## 11. What NOT to do

- **No `Any` in public signatures.** `object` is the correct escape hatch when a type is
  truly unknown. `Any` disables type checking silently.
- **No `TYPE_CHECKING` guards for runtime-needed imports.** Only use `if TYPE_CHECKING:`
  for imports that are solely needed for annotations.
- **No mutable default arguments.** Use `None` as default and assign inside the function.
- **No bare `except:` or `except Exception:` in resource methods.** Catch specifically.
- **No string-format error messages in raises.** Use f-strings; include the offending value.
- **No `print()` in library code.** Use `logging.getLogger(__name__)` if you need debug
  output, and keep it at `DEBUG` level.

---

## 12. Versioning & Release

### 12.1 Single source of truth

The version lives in **one** place: `src/cominty_sdk/_version.py` as `__version__ = "X.Y.Z"`.

- It is re-exported as `cominty_sdk.__version__` (in `__init__.py` + `__all__`), so
  `import cominty_sdk; cominty_sdk.__version__` always works at runtime.
- `pyproject.toml` declares `dynamic = ["version"]` and hatchling reads the same file via
  `[tool.hatch.version] path = "src/cominty_sdk/_version.py"`. Never hard-code a version in
  `pyproject.toml` — there is exactly one number to change.

### 12.2 Local build & check (before any release)

Developer tasks live in `tasks.py` (`invoke` is a dev dependency). Run them with `uv run`:

```bash
uv run invoke --list           # show all tasks
uv run invoke clean            # remove dist/ build/ *.egg-info (no stale artifacts)
uv run invoke build            # clean, then `uv build` -> sdist + wheel in dist/
uv run invoke check            # build, `twine check dist/*`, and print sdist + wheel contents
uv run invoke publish-test     # check, then upload to TestPyPI (rehearsal — never PyPI)
```

`check` is the gate to run before cutting a release. It confirms:

1. the sdist/wheel **build** succeeds,
2. metadata + README **render** (`twine check`),
3. the artifacts contain **what they should** — `py.typed` is present in the wheel, and the
   sdist contains **no** `legacy/`, `.env`, or `test.py`.

`publish-test` is a full dry run against TestPyPI; verify the upload in a clean env with the
`uv run --isolated` snippet the task prints. It never burns a real PyPI version.

### 12.3 Cutting a release (steps)

1. **Bump the version** in `src/cominty_sdk/_version.py` (the only place — see §12.1).
   Never edit the version in `pyproject.toml`.
2. **Verify locally**: `uv run invoke check` (and `uv run invoke publish-test` for a dry run).
3. **Commit + tag**: `git commit -am "Release X.Y.Z"` then `git tag vX.Y.Z`; push both.
   The tag `vX.Y.Z` must equal `_version.py` — the build derives the version from the file,
   **not** the tag.
4. **Publish via a GitHub Release** — create/publish a Release for tag `vX.Y.Z`
   (`gh release create vX.Y.Z` or the GitHub UI). Publishing the Release is what triggers
   the `release` workflow; a plain tag push does not.

`uv run invoke publish` (direct upload to real PyPI) exists as a manual fallback only. The
**preferred** path is the GitHub Release → CI flow below, so no PyPI token lives on a laptop.

### 12.4 CI release pipeline & OIDC (Trusted Publishing)

`.github/workflows/release.yml` runs on `release: [published]` and publishes to PyPI with
**no stored API token**:

1. **build** job — `uv build`, `twine check`, uploads `dist/` as an artifact.
2. **publish** job — downloads `dist/`, then `pypa/gh-action-pypi-publish` mints a
   short-lived GitHub **OIDC** token (`permissions: id-token: write`, `environment: pypi`),
   PyPI verifies the token's claims against a registered **Trusted Publisher**, and issues a
   one-shot project-scoped upload token.

One-time PyPI setup (must match the workflow exactly, or PyPI rejects the token):

| Field | Value |
|---|---|
| Owner | `cominty` |
| Repository | `python-sdk` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Note: `release.yml` builds + `twine check`s but does **not** run the test suite — tests run
in `ci.yml` on push/PR to `main`/`dev`. Only merge to `main` through green CI so a Release
never ships untested code.
