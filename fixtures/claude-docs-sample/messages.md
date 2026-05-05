# Anthropic Messages API

The Messages API is the primary endpoint for conversing with Claude.

## Messages

Send a list of `{role, content}` messages and Claude streams a reply.

```python
from anthropic import Anthropic

client = Anthropic()
resp = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(resp.content[0].text)
```

### Streaming

Pass `stream=True` to receive incremental token deltas instead of a single
final response.
