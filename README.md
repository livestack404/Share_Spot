# Share_Spot 😎

A small file-sharing app I built with Streamlit. Upload a file, get a QR code and a link, and it deletes itself the moment someone downloads it (or after 10 minutes if nobody does). No login, no database, no file sitting around forever.

I made this to solve a simple annoyance — sending a file from my laptop to my phone (or to someone else) without both devices being on the same WiFi/hotspot. Scan the QR, grab the file, done.

## What it does

- Upload any file, get back a QR code + shareable link
- Works over the internet, not just local WiFi
- File auto-deletes right after it's downloaded
- Anything not downloaded gets wiped after 10 minutes
- Each link is a random token, so no one can guess a URL to someone else's file

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying

Built to run as-is on [Streamlit Community Cloud](https://streamlit.io/cloud) — just connect the repo and deploy. That's it, no extra config.

## Why

Mostly built this to learn — messing around with Streamlit, file handling, and how to make something "disappear" safely without it hanging around on a server. Still a work in progress, might break things while I keep tinkering.

## Tech

- Python + Streamlit
- `qrcode` for generating QR codes
- Local disk storage (simple JSON file as the "database")

---

Feel free to fork it, break it, or tell me what's wrong with it.
