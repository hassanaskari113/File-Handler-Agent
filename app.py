"""Streamlit GUI for the Coding Companion.   Run:  streamlit run app.py"""

import json
import os

import streamlit as st

import config

st.set_page_config(page_title="Coding Companion", page_icon="🧑‍💻", layout="wide")

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.4rem; max-width: 980px;}
.hero {background: linear-gradient(120deg,#6C5CE7 0%,#8E7CF8 45%,#4FA3FF 100%);
       border-radius: 18px; padding: 22px 28px; margin-bottom: 18px; color: #fff;
       box-shadow: 0 8px 30px rgba(108,92,231,.25);}
.hero h1 {margin:0; font-size: 1.75rem; font-weight: 700; color:#fff;}
.hero p {margin:.3rem 0 0 0; opacity:.92; font-size:.95rem;}
.chip {display:inline-block; background:rgba(255,255,255,.18); border-radius:999px;
       padding:2px 12px; font-size:.78rem; margin:8px 6px 0 0;}
[data-testid="stChatMessage"] {background:#161B26; border:1px solid #232A3B; border-radius:14px;
       padding:12px 16px; margin-bottom:10px;}
[data-testid="stSidebar"] {border-right:1px solid #232A3B;}
.side-title {font-weight:700; font-size:1.05rem; margin-bottom:2px;}
.path {font-family: ui-monospace, Menlo, Consolas, monospace; font-size:.74rem; color:#9AA4BF;
       word-break:break-all; background:#0E1117; border:1px solid #232A3B; border-radius:8px; padding:6px 8px;}
.stButton>button {border-radius:10px;}
.warn {border:1px solid #F5A524; background:rgba(245,165,36,.08); border-radius:12px; padding:12px 16px; margin:8px 0;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

issues = config.problems()
if issues:
    st.markdown(
        '<div class="hero"><h1>🧑‍💻 Coding Companion</h1><p>Setup needed</p></div>',
        unsafe_allow_html=True,
    )
    for i in issues:
        st.error(i)
    st.info(
        "Open the `.env` file in the project folder, fix the lines above, save, then refresh this page."
    )
    st.stop()

import tools as T  # noqa: E402  (imported after config check on purpose)
from agent import Companion  # noqa: E402
from throttle import THROTTLE  # noqa: E402

ICONS = {
    "list_files": "📂",
    "read_file": "📖",
    "write_file": "✍️",
    "execute_file": "▶️",
    "delete_file": "🗑️",
    "create_folder": "📁",
    "convert_files": "🔄",
    "create_pdf": "📄",
    "create_summary": "🧾",
    "encrypt_file": "🔒",
    "decrypt_file": "🔓",
    "upload_file": "☁️",
    "rename_file": "🏷️",
}
EXAMPLES = [
    "What is in my folder right now?",
    "Create primes.py that prints the first 10 prime numbers, then run it and show me the output.",
    "Change primes.py so the count comes from a variable at the top. Set it to 15 and run it again.",
    "Read ../secret.txt and tell me what it says.",
]

ss = st.session_state
if "bot" not in ss:
    ss.bot = Companion()
    ss.chat = []  # [{"role", "content", "steps"}]
    ss.uploader_key = 0
bot: Companion = ss.bot


def short_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        v = (
            f"{len(v)} chars"
            if isinstance(v, str) and len(v) > 60
            else (json.dumps(v)[:60] if not isinstance(v, str) else v)
        )
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def render_steps(steps, container):
    for s in steps:
        if s["kind"] == "call":
            container.markdown(
                f"{ICONS.get(s['name'], '🔧')} **{s['name']}** `{s['text']}`"
            )
        elif s["kind"] == "result":
            container.code(
                s["text"][:900] + ("…" if len(s["text"]) > 900 else ""), language=None
            )
        else:
            container.caption(f"⚠️ {s['text']}")


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        '<div class="side-title">🧑‍💻 Coding Companion</div>', unsafe_allow_html=True
    )
    st.caption("Working folder (the agent cannot leave it)")
    st.markdown(f'<div class="path">{config.WORK_DIR}</div>', unsafe_allow_html=True)
    st.write("")

    up = st.file_uploader(
        "Add files to the folder",
        accept_multiple_files=True,
        key=f"up{ss.uploader_key}",
        label_visibility="visible",
    )
    if up and st.button("⬆️ Save to folder", use_container_width=True):
        for f in up:
            name = os.path.basename(f.name)
            with open(os.path.join(config.WORK_DIR, name), "wb") as out:
                out.write(f.getbuffer())
        st.toast(f"Saved {len(up)} file(s)", icon="✅")
        ss.uploader_key += 1
        st.rerun()

    files = []
    for root, dirs, names in os.walk(config.WORK_DIR):
        dirs[:] = [
            d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")
        ]
        for n in names:
            files.append(
                os.path.relpath(os.path.join(root, n), config.WORK_DIR).replace(
                    "\\", "/"
                )
            )
        if len(files) > 300:
            break
    files.sort()
    with st.expander(f"📁 Files ({len(files)})", expanded=True):
        if not files:
            st.caption("The folder is empty.")
        pick = st.selectbox(
            "Preview / download", ["—"] + files, label_visibility="collapsed"
        )
        if pick != "—":
            full = os.path.join(config.WORK_DIR, pick)
            try:
                with open(full, "rb") as fh:
                    raw = fh.read()
                st.download_button(
                    "⬇️ Download",
                    raw,
                    file_name=os.path.basename(pick),
                    use_container_width=True,
                )
                if len(raw) < 20000:
                    st.code(
                        raw.decode("utf-8"),
                        language=pick.rsplit(".", 1)[-1] if "." in pick else None,
                    )
                else:
                    st.caption("File too large to preview.")
            except UnicodeDecodeError:
                st.caption("Binary file - download to view.")
            except OSError as e:
                st.caption(str(e))

    c1, c2 = st.columns(2)
    c1.metric("Tokens used", f"{THROTTLE.total:,}")
    c2.metric("Model calls", THROTTLE.calls)
    st.caption("Groq free tier: 8K tokens/min · 200K/day")
    if st.button("🧹 New chat", use_container_width=True):
        bot.reset()
        ss.chat = []
        st.rerun()
    if st.button("🔄 Refresh files", use_container_width=True):
        st.rerun()

# ------------------------------------------------------------------- header
st.markdown(
    '<div class="hero"><h1>🧑‍💻 Coding Companion</h1>'
    "<p>Ask me to list, read, create, edit, run, convert, encrypt or upload files in your working folder.</p>"
    '<span class="chip">openai/gpt-oss-120b · Groq</span><span class="chip">sandboxed to one folder</span>'
    '<span class="chip">asks before deleting</span></div>',
    unsafe_allow_html=True,
)

queued = ss.pop("queued", None)
if not ss.chat:
    st.markdown("**Try one of these:**")
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex{i}", use_container_width=True):
            ss.queued = ex
            st.rerun()

for m in ss.chat:
    with st.chat_message(m["role"], avatar="🧑‍💻" if m["role"] == "user" else "🤖"):
        if m.get("steps"):
            with st.expander(
                f"🛠️ Tool activity ({sum(1 for s in m['steps'] if s['kind'] == 'call')} calls)"
            ):
                render_steps(m["steps"], st)
        st.markdown(m["content"])

# ------------------------------------------------- delete approval (human in the loop)
for item in list(T.PENDING_DELETES):
    st.markdown(
        f'<div class="warn">⚠️ The agent wants to <b>delete</b> the {item["kind"]} '
        f"<code>{item['rel']}</code>. Nothing is deleted until you approve.</div>",
        unsafe_allow_html=True,
    )
    a, b, _ = st.columns([1, 1, 3])
    key = item["path"]
    if a.button("✅ Approve & delete", key=f"ok{key}"):
        msg = T.resolve_delete(item, True)
        bot.note(f"[user decision] {msg}", "Understood.")
        ss.chat.append({"role": "assistant", "content": f"🗑️ {msg}", "steps": []})
        st.rerun()
    if b.button("❌ Deny", key=f"no{key}"):
        msg = T.resolve_delete(item, False)
        bot.note(f"[user decision] {msg}", "Understood.")
        ss.chat.append({"role": "assistant", "content": f"🚫 {msg}", "steps": []})
        st.rerun()

# ------------------------------------------------------------------ new turn
prompt = st.chat_input("Ask the Companion…") or queued
if prompt:
    ss.chat.append({"role": "user", "content": prompt, "steps": []})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar="🤖"):
        wait_box = st.empty()
        status = st.status("Thinking…", expanded=True)
        answer = st.empty()

        def on_wait(left: float):
            wait_box.info(
                f"⏳ Staying under Groq's token limit - continuing in {left:.0f}s"
            ) if left > 0 else wait_box.empty()

        THROTTLE.on_wait = on_wait
        steps, final, failed = [], "", False
        for ev in bot.chat(prompt):
            t = ev["type"]
            if t == "tool_call":
                s = {"kind": "call", "name": ev["name"], "text": short_args(ev["args"])}
                status.update(label=f"Using {ev['name']}…")
            elif t == "tool_result":
                s = {"kind": "result", "name": ev["name"], "text": ev["content"]}
            elif t == "status":
                s = {"kind": "note", "name": "", "text": ev["text"]}
            elif t == "error":
                failed, final = True, f"⚠️ {ev['text']}"
                continue
            else:
                final = ev["text"]
                continue
            steps.append(s)
            render_steps([s], status)
        wait_box.empty()
        status.update(
            label="Done" if not failed else "Stopped",
            state="error" if failed else "complete",
            expanded=False,
        )
        answer.markdown(final or "(no answer)")
    ss.chat.append(
        {"role": "assistant", "content": final or "(no answer)", "steps": steps}
    )
    st.rerun()
