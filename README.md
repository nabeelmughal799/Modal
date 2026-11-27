# My AI Assistant

A Streamlit chat assistant using Gemini, LangChain Deep Agents, WeatherAPI,
Tavily, Graphviz diagrams, and downloadable weather PDFs. It supports English,
Urdu script, and Roman Urdu. The chat composer accepts text, PDF, DOCX, TXT,
JPG, PNG, and microphone recordings.

## Run locally

Use Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Add these values to `.env` locally or to **Streamlit app settings → Secrets**
when hosted:

```toml
GOOGLE_API_KEY = "..."
WEATHER_API_KEY = "..."
TAVILY_API_KEY = "..."
```

## Temporary guest mode

Sign-in and account creation are currently disabled. Chats, history, and
attachments stay only in the current Streamlit session and are cleared when the
session ends or the page is refreshed. Persistent chat storage is not active in
this mode. `.env` and `.streamlit/secrets.toml` are ignored by Git.

## Files and voice

- Up to 3 files per message, 10 MB per file and 20 MB total.
- PDFs are limited to 20 pages and document text to 30,000 characters.
- PDF, DOCX, and TXT contents are extracted as untrusted reference data.
- Images are sent as image content to Gemini. Scanned PDFs without selectable
  text are reported as unreadable; OCR is not configured.
- The microphone records English or Urdu audio. Gemini transcribes it into the
  editable message field; the user reviews and presses **Send**.
- If microphone permission is unavailable, text and file uploads still work.

## Tests

Run the local unit tests with:

```powershell
python -m unittest discover -s tests -v
```

Live Gemini, WeatherAPI, Tavily, and real browser microphone tests require
configured credentials and browser permission.
