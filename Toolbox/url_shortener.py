import base64
import hashlib
import json

import pandas as pd
import requests
import streamlit as st

REPO = "pedagocode/kiddom-url-shortener"
FILE_PATH = "data/urls.json"

ALLOWED_DOMAINS = ("kiddom.co", "amazonaws.com")


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
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def make_short_code(url: str) -> str:
    digest = hashlib.sha256(url.strip().encode()).hexdigest()[:6]
    return f"kiddom-{digest}"


def shorten_and_deploy(new_entries: list[dict]) -> tuple[bool, str]:
    """Add new_entries to urls.json and push. Returns (success, message)."""
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

tab1, tab2, tab3 = st.tabs(["Single URL", "Bulk CSV", "All Links"])

# ── Single URL ────────────────────────────────────────────────────────────────
with tab1:
    url_input = st.text_input("Paste a Kiddom URL", placeholder="https://app.kiddom.co/...")

    if st.button("Shorten & Deploy", type="primary"):
        url = url_input.strip()
        if not url:
            st.warning("Enter a URL.")
        elif not url.startswith(("http://", "https://")):
            st.error("URL must start with http:// or https://")
        elif not is_allowed(url):
            st.error("Only Kiddom platform URLs and Kiddom AWS assets are allowed.")
        else:
            code = make_short_code(url)
            with st.spinner("Deploying…"):
                ok, msg = shorten_and_deploy([{"short_code": code, "original_url": url}])
            if ok:
                st.success(msg)
                st.code(code)
            else:
                st.error(msg)

# ── Bulk CSV ──────────────────────────────────────────────────────────────────
with tab2:
    uploaded = st.file_uploader("Upload CSV", type="csv")

    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head(), use_container_width=True)
        url_col = st.selectbox("URL column", df.columns.tolist())

        if st.button("Shorten & Deploy All", type="primary"):
            entries, blocked, skipped = [], [], 0
            for raw in df[url_col]:
                url = str(raw).strip()
                if pd.isna(raw) or not url.startswith(("http://", "https://")):
                    skipped += 1
                elif not is_allowed(url):
                    blocked.append(url)
                else:
                    entries.append({"short_code": make_short_code(url), "original_url": url})

            if blocked:
                st.warning(f"{len(blocked)} URL(s) blocked (not Kiddom domains).")
            if skipped:
                st.caption(f"{skipped} empty/invalid row(s) skipped.")

            if entries:
                df_valid = df[df[url_col].apply(lambda u: is_allowed(str(u).strip()))]
                df_valid = df_valid.copy()
                df_valid["short_url"] = [e["short_code"] for e in entries]

                with st.spinner(f"Deploying {len(entries)} links…"):
                    ok, msg = shorten_and_deploy(entries)

                if ok:
                    st.success(msg)
                    st.dataframe(df_valid[[url_col, "short_url"]], use_container_width=True)
                    st.download_button(
                        "⬇️ Download CSV with short codes",
                        df_valid.to_csv(index=False).encode(),
                        "urls_with_short_codes.csv",
                        "text/csv",
                    )
                else:
                    st.error(msg)

# ── All Links ─────────────────────────────────────────────────────────────────
with tab3:
    mappings, _ = fetch_mappings()
    if not mappings:
        st.info("No links yet.")
    else:
        df_all = pd.DataFrame(mappings)
        st.write(f"**{len(df_all)} active links**")
        st.dataframe(df_all, use_container_width=True)
        st.download_button(
            "⬇️ Download all",
            df_all.to_csv(index=False).encode(),
            "kiddom_links.csv",
            "text/csv",
        )
