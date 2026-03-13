# Kiddom ShortURL

A Streamlit app for generating branded short links for Kiddom content URLs. Short links are deployed as static redirect pages via GitHub Pages.

---

## How It Works

1. Select a **publisher prefix** (EL, IM, Odell, or OSE)
2. Paste a Kiddom URL (or load a Google Sheet of URLs)
3. Click **Shorten** — the app generates a publisher-prefixed short code (e.g., `IM-k3xn7f`) and saves it to `data/urls.json`
4. A GitHub Action automatically builds static redirect pages and deploys them to GitHub Pages
5. The short link is live within ~2 minutes

### Link format

| Publisher | Example short link |
|-----------|-------------------|
| EL | `https://links.kiddom.co/EL-d4e5f6` |
| IM | `https://links.kiddom.co/IM-k3xn7f` |
| Odell | `https://links.kiddom.co/Odell-jm2e3d` |
| OSE | `https://links.kiddom.co/OSE-7a8b9c` |

> The custom domain removes the `/kiddom-url-shortener/` path segment automatically.
> Once IT sets up the DNS CNAME, all links resolve at `links.kiddom.co/<prefix>-<code>`.

---

## Features

- **Publisher prefixes** — every short code is prefixed with the publisher name (EL, IM, Odell, OSE)
- **Single URL** — paste one URL, get one short link instantly
- **Google Sheet** — load a sheet, generate short codes for all URLs, download updated CSV
- **URL allowlist** — only `*.kiddom.co` and `*.amazonaws.com` URLs are accepted
- **Vanity URL restriction** — tree:version UUID pairs (e.g., `uuid:uuid`) are blocked to keep links clean, while single UUIDs in paths are allowed
- **Deterministic codes** — the same URL always produces the same short code (no duplicates)
- **Human-friendly alphabet** — short codes use only unambiguous characters (`23456789abcdefghjkmnpqrstuvwxyz`), excluding easily confused pairs like 0/O/o and 1/I/i/l/L
- **Kiddom branding** — custom UI with Lexend font, coral (#EF6C56) header bar, Kiddom color palette, and decorative brand shapes
- **Forced light theme** — the app always renders in light mode regardless of the user's OS preference, configured via `.streamlit/config.toml`

---

## Setup

### 1. GitHub Personal Access Token

Required for the app to write to `data/urls.json` and trigger deployments.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Generate new token (classic)**
2. Select scope: **`repo`**
3. Add to Streamlit secrets:

```toml
GITHUB_TOKEN = "ghp_your_token_here"
```

### 2. Enable GitHub Pages

In the repo: **Settings → Pages → Source → GitHub Actions**

This only needs to be done once. After that, every push to `data/urls.json` triggers an automatic deploy.

### 3. Custom Domain (optional, recommended)

Ask IT to add one DNS record:

```
CNAME  links.kiddom.co  ->  pedagocode.github.io
```

Then in the repo: **Settings → Pages → Custom domain** → enter `links.kiddom.co`

GitHub will provision an SSL certificate automatically. Once live, short links will be:
```
https://links.kiddom.co/IM-k3xn7f
```

Also update `PAGES_BASE` in `Toolbox/url_shortener.py`:
```python
PAGES_BASE = "https://links.kiddom.co"
```

---

## Running Locally

```bash
cd Toolbox
pip install -r requirements.txt
streamlit run url_shortener.py
```

> Note: The app requires a valid `GITHUB_TOKEN` in `.streamlit/secrets.toml` to function locally.

---

## Project Structure

```
Toolbox/
  url_shortener.py       # Streamlit app (UI, branding, shortening logic)
  requirements.txt
data/
  urls.json              # URL mapping store (auto-updated by app)
scripts/
  generate_redirects.py  # Builds static HTML redirect pages
redirect-site/
  404.html               # Shown for expired or invalid links
.streamlit/
  config.toml            # Forces light theme and Kiddom brand colors
.github/workflows/
  deploy-redirects.yml   # Auto-deploys on urls.json change
```

---

## Branding

The app uses Kiddom's brand identity:

| Element | Value |
|---------|-------|
| Font | Lexend (Google Fonts) |
| Primary / header | `#EF6C56` (coral) |
| Background | `#EEF1F0` |
| Secondary background | `#E5E8E7` |
| Text color | `#242D2C` |
| Inputs & dropdowns | White (`#FFFFFF`) with coral focus ring |

Decorative dot-grid patterns and wave shapes appear at subtle opacity on the sides of the page for visual flair.

---

## Future Improvements

- Connect to Snowflake for enterprise-grade storage and access control
- Gate app access via Snowflake OAuth (Kiddom staff only)
- Link revocation and expiration
- Analytics on link clicks
