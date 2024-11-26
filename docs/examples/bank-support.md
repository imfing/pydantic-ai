Small but complete example of using PydanticAI to build a support agent for a bank.

Demonstrates:

* [dynamic system prompt](../agents.md#system-prompts)
* [structured `result_type`](../results.md#structured-result-validation)
* [tools](../agents.md#function-tools)

## Running the Example

With [dependencies installed and environment variables set](./index.md#usage), run:

```bash
python/uv-run -m pydantic_ai_examples.bank_support
```

(or `PYDANTIC_AI_MODEL=gemini-1.5-flash ...`)

## Example Code

```py title="bank_support.py"
#! pydantic_ai_examples/bank_support.py
```