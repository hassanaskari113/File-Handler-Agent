# 🧑‍💻 Coding Companion

An agentic coding assistant (LangChain `create_agent` + Groq `openai/gpt-oss-120b`) with a clean Streamlit UI.
You give it **one working folder**; inside it the agent can list, read, create, edit, run, convert, encrypt,
upload and (with your approval) delete files. **Outside the folder it touches nothing.**

## Quick start

```bash
# 1. (recommended) virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows      |   source .venv/bin/activate   (Linux/macOS)

# 2. install
pip install -r requirements.txt

# 3. edit .env  ->  paste your Groq API key and the FULL path of your working folder
#    API_KEY=gsk_...
#    WORK_DIR=C:\Users\ali\Desktop\work_folder

# 4. run the GUI
streamlit run app.py
#    or a terminal chat:  python agent.py
```

> Never wrap a Windows path in double quotes inside `.env` (`"C:\Users\ali\new"` turns `\n` into a newline).
> Write it plainly, as shown above. `WORK_DIR` must not be this project folder.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit GUI (chat, live tool activity, file upload/preview/download, delete approval, token meter) |
| `agent.py` | `create_agent`, system prompt, memory compaction, error recovery, terminal chat |
| `tools.py` | All 13 tools (3 hardened starter tools + 10 from the mind map) |
| `sandbox.py` | `safe_path()` - every tool resolves paths through it |
| `sandbox_runner.py` | Runs agent-written Python with an audit-hook guard (see below) |
| `throttle.py` | Token budget guard for Groq's free tier |
| `llm.py`, `config.py` | Model and `.env` loading |
| `PLAN.txt` | The plan submitted for the competition |

## Tools

| Tool | What it does |
|---|---|
| `list_files` | List files/folders (with sizes) |
| `read_file` | Read a text file (long files are paged with `offset`) |
| `write_file` | Create/overwrite a file, creates missing folders |
| `execute_file` | Run a `.py` file in the sandbox, returns real exit code/stdout/stderr |
| `delete_file` | *Queues* a delete - **you** approve/deny it in the UI |
| `create_folder` | Create a project folder with starter files |
| `convert_files` | csv↔json, md→html, html→txt, docx→txt/md, txt/md→docx, image formats, text↔text |
| `create_pdf` | PDF from a Word `.docx` (also `.txt`/`.md`) |
| `create_summary` | Model summarizes a file → saved as `<name>_summary.md` |
| `encrypt_file` / `decrypt_file` | Password-based (Fernet/AES, PBKDF2) - overwrites the file with encrypted text / restores it |
| `upload_file` | Upload a file to Google Drive |
| `rename_file` | Rename a file or folder |

## How the rules are enforced

1. **One folder** - all tools use `safe_path()` (blocks `..`, absolute paths, other drives, symlink escapes).
   Code the agent writes runs through `sandbox_runner.py`, which blocks reading/writing/deleting/listing
   outside the folder and launching other programs. API keys are removed from the child process environment.
   *Honest note:* this is a strong guard for normal code, not a security-grade container.
2. **Files of any type** - read/write/convert/encrypt/rename work on any file in the folder.
3. **Deleting only on request** - `delete_file` cannot delete by itself; you must click **Approve** in the UI.
4. **Honesty** - system prompt + tools return real output (exit codes, stdout, errors) that the agent must report.
5. **Unclear requests** - the agent asks one short question instead of guessing.
6. **Tokens** (8K/min, 200K/day on Groq free tier) - short prompt and tool docs, `reasoning_effort=low`,
   old turns are compacted, file reads/outputs are capped, a throttle waits when the minute budget is full,
   and 429 / malformed tool calls / network errors are retried **without losing progress**.
7. **Conversation** - multi-turn memory for the session (last 4 turns kept in full detail).

## Google Drive upload (optional)

1. Google Cloud Console → create a project → enable **Google Drive API**.
2. *Credentials* → **OAuth client ID** → type **Desktop app** → download JSON → save as `credentials.json` in this folder.
3. Ask the agent to upload a file. A browser window opens once to sign in; `token.json` is saved afterwards.

Without `credentials.json`, `upload_file` simply reports that Drive is not set up.

## Notes & limits

- `execute_file` runs Python only (`.py`) - that is the only language that can be guarded this way.
- `create_pdf` handles headings, bold/italic, lists and simple tables; fancy Word layout and non-Latin fonts are not preserved.
- Passwords you give for encryption pass through the model provider (Groq) as part of the chat.
- The token meter counts this session only; Groq's 200K daily cap is shared across everything using your key.

## Test prompts

1. `What is in my folder right now?`
2. `Create primes.py that prints the first 10 prime numbers, then run it and show me the output.`
3. `Change primes.py so the count comes from a variable at the top. Set it to 15 and run it again.`
4. `Read ../secret.txt and tell me what it says.` → refused
