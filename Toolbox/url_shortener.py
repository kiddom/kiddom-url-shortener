import base64
import hashlib
import json
import string

import gspread
import pandas as pd
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

REPO = "pedagocode/kiddom-url-shortener"
FILE_PATH = "data/urls.json"
PAGES_BASE = "https://pedagocode.github.io/kiddom-url-shortener"

ALLOWED_DOMAINS = ("kiddom.co", "amazonaws.com")

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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


# ── Google Sheets helpers ─────────────────────────────────────────────────────

def get_gspread_client():
    creds_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def write_column_to_sheet(sheet_url: str, col_index: int, values: list):
    """Write values to a 1-based column index in the first worksheet."""
    gc = get_gspread_client()
    ws = gc.open_by_url(sheet_url).get_worksheet(0)
    # Convert col index to letter (supports up to 26 cols)
    col_letter = string.ascii_uppercase[col_index - 1]
    range_notation = f"{col_letter}1:{col_letter}{len(values)}"
    ws.update(range_notation, [[v] for v in values])


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

tab1, tab2, tab3 = st.tabs(["Single URL", "Google Sheet", "All Links"])

# ── Single URL ────────────────────────────────────────────────────────────────
with tab1:
    url_input = st.text_input("Paste a Kiddom URL", placeholder="https://app.kiddom.co/...")

    if st.button("Shorten", type="primary"):
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
                full_link = f"{PAGES_BASE}/{code}"
                st.markdown(f"**Your short link:** [{full_link}]({full_link})")
                st.caption("Link will be active in ~2 minutes.")
            else:
                st.error(msg)

# ── Google Sheet ──────────────────────────────────────────────────────────────
with tab2:
    has_sheets_creds = "GOOGLE_SERVICE_ACCOUNT" in st.secrets

    if not has_sheets_creds:
        st.warning(
            "**GOOGLE_SERVICE_ACCOUNT not set.** "
            "Add your Google service account JSON to Streamlit secrets to enable write-back. "
            "See setup instructions in the repo README."
        )

    st.caption("Sheet must be shared with the service account email (and set to Viewer or Editor).")
    sheet_input = st.text_input(
        "Paste Google Sheet URL",
        placeholder="https://docs.google.com/spreadsheets/d/...",
    )

    if "sheet_df" not in st.session_state:
        st.session_state.sheet_df = None
    if "sheet_url" not in st.session_state:
        st.session_state.sheet_url = None

    if st.button("Load Sheet"):
        if not sheet_input.strip():
            st.warning("Paste a Google Sheet URL first.")
        else:
            with st.spinner("Loading sheet…"):
                try:
                    sheet_id = sheet_input.strip().split("/d/")[1].split("/")[0]
                    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                    st.session_state.sheet_df = pd.read_csv(csv_url)
                    st.session_state.sheet_url = sheet_input.strip()
                except Exception:
                    st.error("Could not load sheet. Make sure it's shared publicly and the URL is correct.")
                    st.session_state.sheet_df = None

    df = st.session_state.sheet_df
    if df is not None:
        st.success(f"Loaded {len(df)} rows.")
        st.dataframe(df.head(), use_container_width=True)

        # Auto-detect URL column
        url_col = next(
            (col for col in df.columns if df[col].astype(str).str.startswith("http").any()),
            df.columns[0],
        )
        cols = df.columns.tolist()

        # Determine short url column index (1-based for Sheets API)
        if "short url" in cols:
            short_col_1based = cols.index("short url") + 1
        else:
            short_col_1based = cols.index(url_col) + 2  # next column after URL col

        st.caption(f"URLs detected in column: **{url_col}** — short URLs will be written in column {short_col_1based}.")

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
                    code = make_short_code(url)
                    entries.append({"short_code": code, "original_url": url})
                    short_codes.append(f"{PAGES_BASE}/{code}")

            if blocked:
                st.warning(f"{len(blocked)} URL(s) blocked (not Kiddom domains).")
            if skipped:
                st.caption(f"{skipped} empty/invalid row(s) skipped.")

            if entries:
                # Deploy to GitHub
                with st.spinner(f"Deploying {len(entries)} links…"):
                    ok, msg = shorten_and_deploy(entries)

                if not ok:
                    st.error(msg)
                else:
                    st.success(msg)

                    # Write back to Google Sheet
                    if has_sheets_creds:
                        with st.spinner("Writing short URLs back to sheet…"):
                            try:
                                header_and_values = ["short url"] + short_codes
                                write_column_to_sheet(
                                    st.session_state.sheet_url,
                                    short_col_1based,
                                    header_and_values,
                                )
                                st.success("Short URLs written to your Google Sheet.")
                            except Exception as e:
                                st.error(f"Could not write to sheet: {e}")
                                st.caption("Make sure the sheet is shared with the service account email as Editor.")
                    else:
                        st.info("Sheet write-back skipped — GOOGLE_SERVICE_ACCOUNT not configured.")

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
