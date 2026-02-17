# blah-suggest Worker

Cloudflare Worker that accepts rant suggestions and stores them in KV for the CLI to pull.

## Setup

```sh
cd worker
npx wrangler kv namespace create SUGGESTIONS
# Update the `id` in wrangler.toml with the returned namespace ID
npx wrangler secret put AUTH_TOKEN    # pick a random string
npx wrangler deploy
# → https://blah-suggest.<your-subdomain>.workers.dev
```

## Usage

```sh
curl -X POST https://blah-suggest.<your-subdomain>.workers.dev \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"idea": "hot take about LLM coding agents"}'
```

Optional fields: `source` (string), `tags` (array of strings).

## Blah CLI Config

Set the following in `~/.blah/config.yaml`:

```yaml
queue:
  enabled: true
  account_id: <your CF account ID>
  kv_namespace_id: <KV namespace ID from wrangler output>
  api_token: <CF API token with Workers KV Storage Edit permission>
  worker_url: https://blah-suggest.<your-subdomain>.workers.dev
  worker_token: <same value as AUTH_TOKEN secret>
```

Create the API token at https://dash.cloudflare.com/profile/api-tokens with
**Account → Workers KV Storage → Edit** permission.

## Pull Suggestions

```sh
blah rant pull-suggestions   # pulls from KV into local SQLite
blah rant suggestions        # lists them
blah rant suggest "idea"     # add one locally without the worker
```
