# Blah - Platform Integrations

## Design Principle

Pluggable adapters. Start with easy wins, add platforms incrementally.

Each platform is an adapter that implements:
```
Adapter
├── post(content, media?) → post_id
├── reply(target_url, content) → post_id
├── read(url) → content (for engagement context)
└── follow(handle) → success
```

Two integration methods:
1. **API** - Official platform API (preferred)
2. **Browser** - Playwright automation (fallback)

---

## Platform Status

| Platform | Method | Status | Notes |
|----------|--------|--------|-------|
| Bluesky | API | Ready | Free, easy, start here |
| Mastodon | API | Ready | Free, pick instance |
| Twitter/X | API | Ready | Free tier 500/mo, $200 for more |
| Reddit | API | Ready | Free, strict rules, needs approval |
| Threads | API | Later | Needs Meta business verification |
| HN | Browser | Later | No write API |
| LinkedIn | Browser | Maybe never | API is enterprise-only |

---

## Platform Details

### Bluesky (Priority: High)

**Method:** API (AT Protocol)

**Setup:**
1. Get app password: Settings → Privacy & Security → App Passwords
2. Store handle + app password in config

**SDK:** `atproto` (Python)

**Limits:** None significant for personal use

**Example:**
```python
from atproto import Client

client = Client()
client.login('handle.bsky.social', 'app-password')
client.send_post('Hello world')
```

---

### Mastodon (Priority: High)

**Method:** API

**Setup:**
1. Pick instance (mastodon.social, or bot-friendly like botsin.space)
2. Settings → Development → New Application
3. Copy access token

**SDK:** `Mastodon.py`

**Limits:** Varies by instance, generally generous

**Example:**
```python
from mastodon import Mastodon

client = Mastodon(
    access_token='token',
    api_base_url='https://mastodon.social'
)
client.toot('Hello world')
```

---

### Twitter/X (Priority: High)

**Method:** API (primary), Browser (fallback)

**Setup:**
1. Developer account: developer.twitter.com
2. Create app, get API keys
3. Generate access tokens

**SDK:** `tweepy`

**Limits:**
- Free: 500 posts/month
- Basic ($200/mo): 50K posts/month

**Fallback:** Browser automation when rate limited

---

### Reddit (Priority: Medium)

**Method:** API (PRAW)

**Setup:**
1. Create app: reddit.com/prefs/apps
2. Get client ID + secret
3. Request API access (required since Jan 2025)

**SDK:** `praw`

**Limits:** 60 requests/minute

**Rules:**
- No spam, no vote manipulation
- Disclose automation if asked
- Respect subreddit rules (karma/age requirements)

---

### Threads (Priority: Low)

**Method:** API

**Setup:**
1. Meta business account verification required
2. Link to developer portal

**Limits:** 250 posts/day, 1000 replies/day

**Notes:** More friction than Bluesky. Add later if needed.

---

### Hacker News (Priority: Low)

**Method:** Browser only

**Setup:**
1. Logged-in Playwright session
2. Browser adapter navigates and posts

**Notes:**
- No write API exists
- Risk of detection/ban
- Use sparingly

---

### LinkedIn (Priority: None)

**Method:** Browser only

**Status:** Skip for now

**Notes:**
- API is enterprise-only (Marketing API requires company verification)
- Heavy bot detection
- Not worth the hassle

---

## Config Structure

```yaml
platforms:
  bluesky:
    enabled: true
    method: api
    handle: yourname.bsky.social
    app_password: ${BLAH_BLUESKY_PASSWORD}

  mastodon:
    enabled: true
    method: api
    instance: mastodon.social
    access_token: ${BLAH_MASTODON_TOKEN}

  twitter:
    enabled: true
    method: api  # or 'browser' or 'auto'
    api:
      consumer_key: ${BLAH_TWITTER_CONSUMER_KEY}
      consumer_secret: ${BLAH_TWITTER_CONSUMER_SECRET}
      access_token: ${BLAH_TWITTER_ACCESS_TOKEN}
      access_token_secret: ${BLAH_TWITTER_ACCESS_SECRET}
    browser:
      enabled: true  # fallback when API limited

  reddit:
    enabled: true
    method: api
    client_id: ${BLAH_REDDIT_CLIENT_ID}
    client_secret: ${BLAH_REDDIT_CLIENT_SECRET}
    username: ${BLAH_REDDIT_USERNAME}
    password: ${BLAH_REDDIT_PASSWORD}

  threads:
    enabled: false
    # Add later

  hn:
    enabled: false
    method: browser
    # Add later

  linkedin:
    enabled: false
    # Probably never

browser:
  # Shared browser session for fallbacks
  endpoint: ws://localhost:9222  # CDP endpoint
```

---

## Adapter Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Post:
    id: str
    url: str
    platform: str

class PlatformAdapter(ABC):
    @abstractmethod
    async def post(self, content: str, media: list[str] = None) -> Post:
        """Create a new post."""
        pass

    @abstractmethod
    async def reply(self, target_url: str, content: str) -> Post:
        """Reply to an existing post."""
        pass

    @abstractmethod
    async def read(self, url: str) -> dict:
        """Read a post/thread for context."""
        pass

    @abstractmethod
    async def follow(self, handle: str) -> bool:
        """Follow an account."""
        pass
```

---

## Implementation Order

1. **Bluesky** - Easiest, free, good test case
2. **Mastodon** - Also easy, expands reach
3. **Twitter** - Core platform, most complex
4. **Reddit** - Different content style, careful with rules
5. **Others** - As needed

---

## Browser Fallback

For platforms without APIs or when rate limited:

```python
class BrowserAdapter(PlatformAdapter):
    def __init__(self, platform: str, cdp_endpoint: str):
        self.platform = platform
        self.browser = None  # Connect via CDP

    async def connect(self):
        # Attach to existing browser session
        pass

    async def post(self, content: str, media: list[str] = None) -> Post:
        # Platform-specific UI automation
        pass
```

Uses existing logged-in Playwright session on your server.
