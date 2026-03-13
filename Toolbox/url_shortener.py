import base64
import hashlib
import json

import pandas as pd
import requests
import streamlit as st

REPO = "pedagocode/kiddom-url-shortener"
FILE_PATH = "data/urls.json"
PAGES_BASE = "https://links.kiddom.co"

ALLOWED_DOMAINS = ("kiddom.co", "amazonaws.com")
PUBLISHERS = ["IM", "EL", "OSE", "Odell"]


# ── GitHub helpers ────────────────────────────────────────────────────────────

def gh_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def fetch_mappings():
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
        headers=gh_headers(),
    )
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]
    return [], None


def push_mappings(mappings, sha):
    content = base64.b64encode(json.dumps(mappings, indent=2).encode()).decode()
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
        headers=gh_headers(),
        json={"message": "Update URL mappings", "content": content, "sha": sha},
    )
    return r.status_code in (200, 201)


# ── URL helpers ───────────────────────────────────────────────────────────────

def is_allowed(url: str) -> bool:
    import re
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS):
            return False
        # Block tree:version UUID URLs — only vanity slugs allowed
        # UUID pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        uuid_pat = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        if re.search(uuid_pat, parsed.path, re.IGNORECASE):
            return False
        return True
    except Exception:
        return False


def make_short_code(url: str, publisher: str) -> str:
    digest = hashlib.sha256(url.strip().encode()).hexdigest()[:6]
    return f"{publisher}-{digest}"


def shorten_and_deploy(new_entries: list[dict]) -> tuple[bool, str]:
    mappings, sha = fetch_mappings()
    if sha is None:
        return False, "Could not reach GitHub. Check your GITHUB_TOKEN secret."

    existing_codes = {m["short_code"] for m in mappings}
    added = [e for e in new_entries if e["short_code"] not in existing_codes]
    if not added:
        return True, "All URLs already exist — no changes needed."

    mappings.extend(added)
    ok = push_mappings(mappings, sha)
    if ok:
        return True, f"Deployed {len(added)} link(s). Active in ~2 minutes."
    return False, "Push to GitHub failed. Check your GITHUB_TOKEN permissions."


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Kiddom URL Shortener", page_icon="🔗", layout="centered")
st.title("🔗 Kiddom URL Shortener")

if not st.secrets.get("GITHUB_TOKEN"):
    st.error(
        "**GITHUB_TOKEN not set.** Add it to your Streamlit secrets:\n\n"
        "```toml\nGITHUB_TOKEN = 'ghp_your_token_here'\n```\n\n"
        "The token needs **Contents: Read & Write** permission on this repo."
    )
    st.stop()

tab1, tab2 = st.tabs(["Single URL", "Google Sheet"])

# ── Single URL ────────────────────────────────────────────────────────────────
with tab1:
    publisher = st.selectbox("Publisher", PUBLISHERS, key="pub_single")
    url_input = st.text_input("Paste a Kiddom URL", placeholder="https://app.kiddom.co/...")

    if st.button("Shorten", type="primary"):
        url = url_input.strip()
        if not url:
            st.warning("Enter a URL.")
        elif not url.startswith(("http://", "https://")):
            st.error("URL must start with http:// or https://")
        elif not is_allowed(url):
            st.error("Only Kiddom vanity URLs and S3 links allowed (no tree:version UUIDs).")
        else:
            code = make_short_code(url, publisher)
            with st.spinner("Deploying…"):
                ok, msg = shorten_and_deploy([{"short_code": code, "original_url": url}])
            if ok:
                st.success(msg)
                full_link = f"{PAGES_BASE}/{code}"
                st.markdown(f"**Your short link:** [{full_link}]({full_link})")
                st.caption("Link will be active in ~2 minutes.")
            else:
                st.error(msg)

# ── Google Sheet ──────────────────────────────────────────────────────────────
with tab2:
    publisher_batch = st.selectbox("Publisher", PUBLISHERS, key="pub_batch")
    st.caption("Sheet must be shared: File → Share → Anyone with the link → Viewer")
    sheet_input = st.text_input("Paste Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/...")

    if "sheet_df" not in st.session_state:
        st.session_state.sheet_df = None

    if st.button("Load Sheet"):
        if not sheet_input.strip():
            st.warning("Paste a Google Sheet URL first.")
        else:
            with st.spinner("Loading sheet…"):
                try:
                    sheet_id = sheet_input.strip().split("/d/")[1].split("/")[0]
                    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                    st.session_state.sheet_df = pd.read_csv(csv_url)
                except Exception:
                    st.error("Could not load sheet. Make sure it's shared publicly and the URL is correct.")
                    st.session_state.sheet_df = None

    df = st.session_state.sheet_df
    if df is not None:
        st.success(f"Loaded {len(df)} rows.")
        st.dataframe(df.head(), use_container_width=True)

        url_col = next(
            (col for col in df.columns if df[col].astype(str).str.startswith("http").any()),
            df.columns[0],
        )
        st.caption(f"URLs detected in column: **{url_col}** — short URLs will be written in the next column.")

        if st.button("Shorten All", type="primary"):
            entries, short_codes = [], []
            blocked, skipped = [], 0

            for raw in df[url_col]:
                url = str(raw).strip()
                if pd.isna(raw) or not url.startswith(("http://", "https://")):
                    skipped += 1
                    short_codes.append("")
                elif not is_allowed(url):
                    blocked.append(url)
                    short_codes.append("BLOCKED")
                else:
                    code = make_short_code(url, publisher_batch)
                    entries.append({"short_code": code, "original_url": url})
                    short_codes.append(f"{PAGES_BASE}/{code}")

            if blocked:
                st.warning(f"{len(blocked)} URL(s) blocked (not Kiddom domains).")
            if skipped:
                st.caption(f"{skipped} empty/invalid row(s) skipped.")

            if entries:
                df_out = df.copy()
                if "short url" in df_out.columns:
                    df_out["short url"] = short_codes
                else:
                    url_col_idx = df_out.columns.tolist().index(url_col)
                    df_out.insert(url_col_idx + 1, "short url", short_codes)

                with st.spinner(f"Deploying {len(entries)} links…"):
                    ok, msg = shorten_and_deploy(entries)

                if ok:
                    st.success(msg)
                    st.dataframe(df_out[[url_col, "short url"]], use_container_width=True)
                    st.download_button(
                        "⬇️ Download updated sheet as CSV",
                        df_out.to_csv(index=False).encode(),
                        "urls_with_short_codes.csv",
                        "text/csv",
                    )
                else:
                    st.error(msg)

