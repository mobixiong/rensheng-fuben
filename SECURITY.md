# Security Policy

## Sensitive data

The public repository should only contain source code, prompt templates, and intentional examples. Real API keys, `.env` files, generated workspace files, and rendered media outputs are treated as local/private data.

Sensitive local values include:

- `LLM_API_KEY`
- `IMAGE_API_KEY`
- `GEMINI_WEB2API_API_KEY`

If any credential has been committed or shared publicly, revoke or rotate it immediately.
