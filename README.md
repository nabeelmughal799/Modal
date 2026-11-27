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
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_OR_PUBLISHABLE_KEY"
```

Do not use a Supabase `service_role` or secret key in this app. `.env` and
`.streamlit/secrets.toml` are ignored by Git.

## Set up persistent chats and sign-in

1. Create a Supabase project.
2. In **SQL Editor**, run [`supabase/schema.sql`](supabase/schema.sql). It
   creates the chat/message tables, a private attachment bucket, and row-level
   security policies that scope records and files to the signed-in Supabase
   user.
3. In **Authentication → Providers**, enable email/password sign-in. Configure
   email confirmation as desired.
4. Copy the project URL and the client-side anon/publishable key from
   **Project Settings → API** into `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
5. Add all five secret values to Streamlit Secrets and restart the app.
6. Create an account in the app, confirm the email if required, and sign in.

Chat history and uploaded files are stored in Supabase, not on the Streamlit
server. Every database query also includes the signed-in user ID; database RLS
and private Storage policies enforce the same ownership boundary. A browser
refresh or server restart may require signing in again; chats are restored
after sign-in. Recordings are transcribed by Gemini and are not saved.

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

Live Gemini, WeatherAPI, Tavily, Supabase sign-in, cross-account RLS, hosted
storage, and real browser microphone tests require configured credentials and
browser permission.
