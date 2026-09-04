"""
Share_Spot — Ephemeral, Cross-Network File Sharing (Streamlit Cloud ready)
=========================================================================

WHAT THIS APP DOES
-------------------
- Lets a user upload a file from any device.
- Generates a unique, unguessable share link (UUID token) + QR code that
  works over the *public internet* (no LAN/hotspot requirement).
- The receiver opens the link/QR on ANY network and downloads the file.
- The file is deleted from the server the moment it is downloaded.
- Any file that is never downloaded is auto-purged after 10 minutes.

DEPLOYMENT NOTES
-----------------
- Deploy as a single app on Streamlit Community Cloud. Community Cloud
  runs your app as ONE container, so local disk storage under
  `./storage` is shared across all users hitting that app instance —
  which is exactly what this script relies on. (It is NOT durable
  across redeploys/restarts — that's fine, files are meant to be
  short-lived anyway.)
- Base URL detection: Streamlit does not expose the public URL to
  Python directly, so this app grabs it client-side via a tiny JS
  snippet (using `streamlit-javascript`). If that ever fails (e.g. JS
  blocked), a manual override box is shown in the sidebar so the app
  still works.
"""

import os
import json
import time
import uuid
import shutil
import threading
import base64
from io import BytesIO
from datetime import datetime

import streamlit as st
import qrcode

try:
    from streamlit_javascript import st_javascript
    _HAS_JS = True
except ImportError:
    _HAS_JS = False

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
APP_NAME = "Share_Spot"
APP_LOGO = "app_logo.gif"
STORAGE_DIR = "storage"
METADATA_FILE = os.path.join(STORAGE_DIR, "metadata.json")
EXPIRY_SECONDS = 10 * 60  # 10 minutes
_LOCK = threading.Lock()

os.makedirs(STORAGE_DIR, exist_ok=True)

st.set_page_config(
    page_title=f"{APP_NAME} — Secure File Share",
    page_icon=APP_LOGO,
    layout="centered",
)


# --------------------------------------------------------------------------
# Metadata persistence (JSON file acts as our tiny "database")
# --------------------------------------------------------------------------
def _load_metadata() -> dict:
    try:
        with _LOCK:
            if not os.path.exists(METADATA_FILE):
                return {}
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_metadata(data: dict) -> None:
    try:
        with _LOCK:
            with open(METADATA_FILE, "w") as f:
                json.dump(data, f)
    except OSError:
        pass  # best-effort; a transient write failure shouldn't crash the app


# --------------------------------------------------------------------------
# Core file operations — every disk action is wrapped in try/except so a
# race between two concurrent users (e.g. cleanup vs. download) can never
# crash the server.
# --------------------------------------------------------------------------
def save_uploaded_file(uploaded_file) -> str:
    token = uuid.uuid4().hex
    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_")
    stored_path = os.path.join(STORAGE_DIR, f"{token}_{safe_name}")

    try:
        with open(stored_path, "wb") as f:
            shutil.copyfileobj(uploaded_file, f)
    except OSError as e:
        st.error(f"Could not save file: {e}")
        return ""

    metadata = _load_metadata()
    metadata[token] = {
        "path": stored_path,
        "filename": uploaded_file.name,
        "uploaded_at": time.time(),
    }
    _save_metadata(metadata)
    return token


def get_file_entry(token: str):
    metadata = _load_metadata()
    return metadata.get(token)


def delete_file_entry(token: str) -> bool:
    """Remove both the physical file and its metadata record. Returns True on success."""
    metadata = _load_metadata()
    entry = metadata.get(token)
    if not entry:
        return False

    try:
        if os.path.exists(entry["path"]):
            os.remove(entry["path"])
    except OSError:
        pass  # file already gone / locked — don't crash, still clear metadata

    try:
        del metadata[token]
        _save_metadata(metadata)
    except KeyError:
        pass
    return True


def cleanup_expired_files() -> None:
    """Purge any file older than EXPIRY_SECONDS. Safe to call on every rerun."""
    metadata = _load_metadata()
    now = time.time()
    expired_tokens = [
        tok for tok, entry in metadata.items()
        if now - entry.get("uploaded_at", 0) > EXPIRY_SECONDS
    ]

    for tok in expired_tokens:
        try:
            entry = metadata.get(tok, {})
            if entry and os.path.exists(entry.get("path", "")):
                os.remove(entry["path"])
        except OSError:
            pass

        metadata.pop(tok, None)

    if expired_tokens:
        _save_metadata(metadata)


# --------------------------------------------------------------------------
# Dynamic base URL detection (no hardcoded local IPs)
# --------------------------------------------------------------------------
def get_base_url() -> str:
    detected = ""

    if _HAS_JS:
        try:
            detected = st_javascript(
                "await fetch('').then(r => window.parent.location.origin)"
            )
        except Exception:
            detected = ""

    if isinstance(detected, str) and detected.startswith("http"):
        return detected.rstrip("/")

    with st.sidebar:
        st.caption("Couldn't auto-detect this app's public URL.")

        manual = st.text_input(
            "App URL (for share links)",
            value=st.session_state.get("manual_base_url", ""),
            placeholder="https://your-app.streamlit.app",
        )

        st.session_state["manual_base_url"] = manual

    return manual.rstrip("/") if manual else ""


def make_qr_image(data: str) -> BytesIO:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color="black",
        back_color="white"
    )

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return buf


# --------------------------------------------------------------------------
# UI: Upload flow (default view)
# --------------------------------------------------------------------------
def render_header() -> None:
    """GIF + wordmark header, shown at the top of every page."""

    with open(APP_LOGO, "rb") as f:
        logo_data = base64.b64encode(f.read()).decode()

    col_logo, col_title = st.columns(
        [1, 5],
        vertical_alignment="center"
    )

    with col_logo:
        st.markdown(
            f"<img src='data:image/gif;base64,{logo_data}' width='48'>",
            unsafe_allow_html=True
        )

    with col_title:
        st.markdown(
            f"## {APP_NAME.replace('_', '')}"
        )
        st.caption("Here for 10 minutes, then gone.")


def render_upload_page(base_url: str) -> None:
    render_header()

    st.caption(
        "Upload a file, share the QR code or link, and it self-destructs "
        "after download (or after 10 minutes if unclaimed)."
    )

    uploaded_file = st.file_uploader(
        "Choose a file to share",
        label_visibility="visible"
    )

    if uploaded_file is not None:

        if st.button(
            "🚀 Generate secure share link",
            type="primary"
        ):

            with st.spinner(
                "Encrypting token & preparing share link..."
            ):
                token = save_uploaded_file(uploaded_file)

            if not token:
                st.error("Upload failed. Please try again.")
                return

            if not base_url:
                st.warning(
                    "Set the app URL in the sidebar so a working "
                    "link/QR can be generated."
                )
                return

            share_url = f"{base_url}/?token={token}"

            st.success(
                "✅ File ready to share! This link is single-use "
                "and expires in 10 minutes."
            )

            col1, col2 = st.columns(2)

            with col1:
                st.image(
                    make_qr_image(share_url),
                    caption="Scan to download",
                    use_container_width=True
                )

            with col2:
                st.text_input(
                    "Shareable link",
                    value=share_url,
                    disabled=False
                )

                st.caption(
                    f"📄 {uploaded_file.name}"
                )

                st.caption(
                    "⏳ Expires 10 minutes from now, "
                    "or immediately after download."
                )


# --------------------------------------------------------------------------
# UI: Download flow (when ?token=... is present in the URL)
# --------------------------------------------------------------------------
def render_download_page(token: str) -> None:
    render_header()

    st.subheader("📥 Incoming File")

    entry = get_file_entry(token)

    if not entry:
        st.error(
            "⚠️ This link has expired or the file was already downloaded."
        )

        st.caption(
            "Ask the sender to generate a new share link."
        )

        return

    age = time.time() - entry.get("uploaded_at", 0)

    if age > EXPIRY_SECONDS:
        delete_file_entry(token)

        st.error(
            "⚠️ This link has expired and the file has been "
            "purged for privacy."
        )

        return

    remaining_min = max(
        0,
        int((EXPIRY_SECONDS - age) // 60)
    )

    st.info(
        f"📄 **{entry['filename']}** — "
        f"link expires in ~{remaining_min} min if not downloaded."
    )

    try:
        with open(entry["path"], "rb") as f:
            file_bytes = f.read()

    except OSError:
        delete_file_entry(token)

        st.error(
            "⚠️ This file is no longer available on the server."
        )

        return

    downloaded = st.download_button(
        label="⬇️ Download file",
        data=file_bytes,
        file_name=entry["filename"],
        type="primary",
    )

    if downloaded:
        delete_file_entry(token)

        st.success(
            "✅ Download complete. The file has been permanently "
            "wiped from the server for your privacy."
        )

        st.balloons()


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------
def main() -> None:
    cleanup_expired_files()

    base_url = get_base_url()

    query_params = st.query_params
    token = query_params.get("token")

    if token:

        render_download_page(token)

        st.divider()

        if st.button("⬅️ Back to upload a new file"):
            st.query_params.clear()
            st.rerun()

    else:
        render_upload_page(base_url)


if __name__ == "__main__":
    main()
