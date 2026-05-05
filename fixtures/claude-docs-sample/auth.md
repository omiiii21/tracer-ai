# Anthropic Authentication

The Anthropic API authenticates requests with a per-account API key.

## Authentication

Pass your key in the `x-api-key` header on every request. Keys never expire
unless rotated; rotate from the console immediately if a key leaks.

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json"
```

## Rotation

Generate a new key in the console, deploy it, then revoke the old one.
