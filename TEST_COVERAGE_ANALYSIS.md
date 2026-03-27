# Test Coverage Analysis

## Current State

The anthropic-cookbook repository has **minimal test coverage**. Only one module (`skills/text_to_sql`) has traditional unit tests. The remaining modules rely on PromptFoo YAML-based evaluation configs or have no testing at all.

### Existing Tests

| Area | Test Type | Files | Notes |
|------|-----------|-------|-------|
| `skills/text_to_sql/evaluation/tests/` | Python unit tests (7 files) | `test_simple_query.py`, `test_employee_count.py`, `test_employee_details.py`, `test_above_average_salary.py`, `test_average_salary.py`, `test_hierarchical_query.py`, `test_budget_allocation.py` | Custom `get_assert()` pattern; no pytest/unittest framework |
| `skills/summarization/evaluation/` | PromptFoo + custom evals | `promptfooconfig.yaml`, `tests.yaml`, `custom_evals/bleu_eval.py`, `rouge_eval.py`, `llm_eval.py` | Evaluation logic only, no unit tests for the eval code itself |
| `skills/classification/evaluation/` | PromptFoo only | `promptfooconfig.yaml` | No unit tests |
| `skills/citations/evaluation/` | PromptFoo only | `promptfooconfig.yaml` | No unit tests |
| `skills/retrieval_augmented_generation/evaluation/` | PromptFoo only | `promptfooconfig_end_to_end.yaml`, `promptfooconfig_retrieval.yaml` | No unit tests |
| `skills/contextual-embeddings/` | None | - | No evaluation or tests of any kind |
| `misc/`, `multimodal/`, `tool_use/`, `third_party/`, `finetuning/` | None | 30+ notebooks | No tests |

### CI/CD

**None.** There are no GitHub Actions workflows, no `Makefile`, no `pyproject.toml`, no `pytest.ini`, and no `tox.ini`. All testing is manual.

---

## Bugs Found in Existing Code

### 1. Normalization bug in `skills/summarization/evaluation/custom_evals/llm_eval.py`

The LLM eval scores 5 criteria but normalizes by dividing by 4:

```python
numeric_values = [v for v in evaluation.values() if isinstance(v, (int, float))]
average_score = sum(numeric_values) / (len(numeric_values) * 4)
```

Since it evaluates 5 criteria (accuracy, completeness, relevance, clarity, conciseness), `len(numeric_values)` will be 5, making the denominator `20`. But since each score maxes at 4, the true max is also `20`, so the normalization is actually correct by coincidence. However, the hardcoded `4` is fragile -- if the scoring rubric changes, this breaks silently.

### 2. No error handling for API calls

`llm_eval.py`, `rouge_eval.py`, and both `vectordb.py` files make external API calls (Anthropic, Voyage AI) with zero error handling. Any network failure or rate limit will crash the evaluation.

### 3. Hardcoded, outdated model references

- `llm_eval.py`: `"claude-3-5-sonnet-20240620"`
- `eval_end_to_end.py`: `"claude-3-5-sonnet-20240620"`

These should use current model IDs or be configurable.

### 4. Hardcoded relative paths throughout

All evaluation modules use relative paths like `"../data/data.db"` and `"../data/help_center_articles"`, making them fragile and non-portable.

---

## Recommended Areas for Test Improvement

### Priority 1: Unit tests for evaluation utilities (high impact, low effort)

The following Python modules contain pure logic that should be unit-tested:

**`skills/text_to_sql/evaluation/tests/utils.py`** - SQL extraction regex and DB execution helper
- Test regex extraction with edge cases: no SQL tags, nested tags, empty tags, multiple tags
- Test DB execution with invalid SQL, empty results, connection failures

**`skills/summarization/evaluation/custom_evals/bleu_eval.py`**
- Test with empty strings, identical strings, completely different strings
- Test threshold behavior at boundaries
- Test with non-English text

**`skills/summarization/evaluation/custom_evals/rouge_eval.py`**
- Same as BLEU: empty inputs, identical/divergent strings, threshold edges

**`skills/classification/evaluation/transform.py`**
- Test tag extraction: valid tags, missing tags, multiple tags, malformed tags

**`skills/citations/evaluation/transform.py`**
- Test citation extraction: `[1]`, `[999]`, no brackets, multiple citations, negative numbers

### Priority 2: Unit tests for VectorDB classes (medium impact, medium effort)

Both `skills/classification/evaluation/vectordb.py` and `skills/retrieval_augmented_generation/evaluation/vectordb.py` have complex logic that should be tested:

- Batch embedding with varying data sizes (empty, 1 item, exactly batch_size, multiple batches)
- Search with various thresholds and k values
- Save/load round-trip integrity
- Error handling for missing files, corrupted pickles, API failures

### Priority 3: Integration tests for evaluation pipelines (high impact, high effort)

Each skill's evaluation pipeline should have an integration test that:

1. Sets up minimal test fixtures (small datasets)
2. Runs the evaluation end-to-end using PromptFoo or direct invocation
3. Validates output structure and scoring logic

Priority order:
1. `skills/text_to_sql/` - already has tests, needs integration coverage
2. `skills/summarization/` - most complex evaluation (3 metrics)
3. `skills/retrieval_augmented_generation/` - two evaluation modes to cover
4. `skills/classification/` - simpler but still needs validation
5. `skills/citations/` - simplest evaluation

### Priority 4: Notebook smoke tests (medium impact, medium effort)

The 30+ Jupyter notebooks in `misc/`, `multimodal/`, `tool_use/`, `third_party/`, and `finetuning/` have no validation. A lightweight approach:

- Use `nbconvert` or `papermill` to execute notebooks in CI
- Mock API calls to avoid costs
- Verify cells execute without errors
- Focus on notebooks that demonstrate utility functions rather than pure API demonstrations

### Priority 5: CI/CD pipeline (foundational)

None of the above matters without automation. Recommended setup:

- Add `pyproject.toml` with pytest configuration
- Create a GitHub Actions workflow that:
  - Runs pytest on all test files
  - Lints Python code (ruff or flake8)
  - Optionally runs notebook validation (on a schedule, not every PR)
- Add a `requirements-test.txt` for test dependencies

### Priority 6: Testing for `skills/contextual-embeddings/`

The `contextual-rag-lambda-function/` directory contains 3 Python modules with zero evaluation or testing. This is the only skill with no evaluation infrastructure at all.

---

## Quick Wins

1. **Add pytest as the test runner** - The existing `get_assert()` test pattern can coexist with pytest. Adding a `conftest.py` and running via `pytest` gives free discovery, reporting, and CI integration.

2. **Add tests for transform functions** - `classification/transform.py` and `citations/transform.py` are pure functions with no dependencies. Each needs ~10 test cases and can be written in under 30 minutes.

3. **Add error handling to API-calling eval modules** - Wrap Anthropic and Voyage AI calls in try/except with meaningful error messages. This prevents cryptic failures during evaluation runs.

4. **Parameterize existing text_to_sql tests** - The 7 test files follow an identical pattern. They can be consolidated into a single parameterized test file, reducing duplication from ~165 lines to ~40 lines.
