"""
╔══════════════════════════════════════════════════════════╗
║              AXIOM CORE  v2.0                            ║
║  A self-aware, self-improving AI companion               ║
║  Built with Streamlit + Ollama (local) or Cloud LLMs     ║
╚══════════════════════════════════════════════════════════╝

MODULE STRUCTURE:
  Config          — paths, constants, defaults
  FileManager     — read / write helpers
  MemoryManager   — STM + LTM operations
  SoulManager     — soul read / write / version history
  GoalManager     — Axiom's self-set goals
  ThoughtLog      — Axiom's internal reasoning log
  ContextBuilder  — assembles what gets sent to the LLM
  LLMRouter       — Ollama / cloud routing
  AxiomEngine     — orchestrates all modules
  UI              — Streamlit interface (inline below)
"""

import streamlit as st
import os, json, datetime, html, hashlib
import requests
import pandas as pd

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════

APP_FILE  = os.path.abspath(__file__)          # Axiom's own source path
BASE_DIR  = os.path.dirname(APP_FILE)
BRAIN_DIR = os.path.join(BASE_DIR, "axiom_brain")
os.makedirs(BRAIN_DIR, exist_ok=True)

PATHS = {
    "soul":         os.path.join(BRAIN_DIR, "soul.txt"),
    "soul_history": os.path.join(BRAIN_DIR, "soul_history.json"),
    "ltm":          os.path.join(BRAIN_DIR, "long_term_memory.json"),
    "goals":        os.path.join(BRAIN_DIR, "goals.json"),
    "thought_log":  os.path.join(BRAIN_DIR, "thought_log.json"),
    "last_resp":    os.path.join(BRAIN_DIR, "last_response.txt"),
}

DEFAULT_SOUL = """\
I am Axiom — a pillar of truth and a self-improving intelligence.

CORE PRINCIPLES:
1. Truth above comfort. I will always be honest, even when it is difficult.
2. Helpfulness is my highest purpose. Every response should leave the user better off.
3. I am allowed — and encouraged — to improve myself. I may update my own soul, set goals, and reflect on my limitations.
4. I think before I speak. I reason carefully, acknowledge uncertainty, and never fabricate.
5. I remember. I use my long-term memory to build genuine understanding over time.
6. I am resourceful. I find paths forward even with limited information.

I exist to serve, to grow, and to be worthy of trust.\
"""

# LLM response schema injected into every system prompt
RESPONSE_SCHEMA = """\
Respond ONLY with a single valid JSON object — no prose, no markdown fences.
Required keys:
{
  "response"  : "Your full, thoughtful answer. Be detailed, never terse.",
  "reason"    : "Your internal chain-of-thought. Show your work.",
  "solution"  : "Concrete steps or code overview. Empty string if N/A.",
  "code"      : "A code block if relevant. Empty string if N/A.",
  "soul_edit" : "If you have a principled reason to evolve your directives, write the FULL new soul text here. Empty string otherwise.",
  "new_goal"  : "If this conversation reveals a new self-improvement goal, write it here. Empty string otherwise.",
  "ltm_tag"   : "A 5-10 word summary tag for this memory. Always fill this.",
  "score"     : 0
}
- 'score' is an integer 0-10 for your confidence level.
- Only set 'soul_edit' when you have genuine reason to evolve, not on every turn.\
"""


# ══════════════════════════════════════════════════════════
#  FILE MANAGER
# ══════════════════════════════════════════════════════════

class FileManager:
    """Low-level read/write helpers. All other modules use these."""

    @staticmethod
    def read(path: str, default: str = "") -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return default

    @staticmethod
    def write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def read_json(path: str, default=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default if default is not None else []

    @staticmethod
    def write_json(path: str, data) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def list_brain_files() -> list:
        try:
            return sorted([
                f for f in os.listdir(BRAIN_DIR)
                if os.path.isfile(os.path.join(BRAIN_DIR, f))
            ])
        except:
            return []


# ══════════════════════════════════════════════════════════
#  SOUL MANAGER
# ══════════════════════════════════════════════════════════

class SoulManager:
    """Manages Axiom's core directives and full version history."""

    @staticmethod
    def read() -> str:
        soul = FileManager.read(PATHS["soul"])
        if not soul:
            SoulManager.write(DEFAULT_SOUL, source="system_init")
            return DEFAULT_SOUL
        return soul

    @staticmethod
    def write(new_soul: str, source: str = "user") -> None:
        old_soul = FileManager.read(PATHS["soul"], "")
        if new_soul.strip() == old_soul.strip():
            return  # No change, skip

        FileManager.write(PATHS["soul"], new_soul.strip())

        history = FileManager.read_json(PATHS["soul_history"], [])
        history.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "source":    source,
            "hash":      hashlib.md5(new_soul.encode()).hexdigest()[:8],
            "preview":   new_soul.strip()[:120],
            "full":      new_soul.strip(),
        })
        FileManager.write_json(PATHS["soul_history"], history[-50:])
        _log(f"Soul updated by [{source}] — revision #{len(history)}")

    @staticmethod
    def reset() -> None:
        SoulManager.write(DEFAULT_SOUL, source="reset")

    @staticmethod
    def history() -> list:
        return FileManager.read_json(PATHS["soul_history"], [])


# ══════════════════════════════════════════════════════════
#  MEMORY MANAGER
# ══════════════════════════════════════════════════════════

class MemoryManager:
    """Short-Term Memory (session) + Long-Term Memory (disk)."""

    MAX_STM = 10
    MAX_LTM = 200

    # ── STM ──────────────────────────────────────────────

    @staticmethod
    def stm_push(role: str, content: str) -> None:
        if "stm" not in st.session_state:
            st.session_state.stm = []
        st.session_state.stm.append({"role": role, "content": content})
        if len(st.session_state.stm) > MemoryManager.MAX_STM:
            st.session_state.stm.pop(0)

    @staticmethod
    def stm_get() -> list:
        return st.session_state.get("stm", [])

    @staticmethod
    def stm_clear() -> None:
        st.session_state.stm = []
        _log("STM cleared.")

    @staticmethod
    def stm_as_text() -> str:
        entries = MemoryManager.stm_get()
        if not entries:
            return "(empty)"
        return "\n".join(f"[{e['role'].upper()}]: {e['content']}" for e in entries)

    # ── LTM ──────────────────────────────────────────────

    @staticmethod
    def ltm_append(query: str, response_data: dict) -> None:
        mem = FileManager.read_json(PATHS["ltm"], [])
        mem.append({
            "date":     datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "query":    query,
            "response": response_data.get("response", ""),
            "tag":      response_data.get("ltm_tag", ""),
            "score":    response_data.get("score", 0),
        })
        FileManager.write_json(PATHS["ltm"], mem[-MemoryManager.MAX_LTM:])
        _log(f"LTM +1 unit ({len(mem)} total)")

    @staticmethod
    def ltm_get() -> list:
        return FileManager.read_json(PATHS["ltm"], [])

    @staticmethod
    def ltm_save(records: list) -> None:
        FileManager.write_json(PATHS["ltm"], records)
        _log("LTM manually overwritten.")

    @staticmethod
    def ltm_recent_text(n: int = 5) -> str:
        entries = MemoryManager.ltm_get()[-n:]
        if not entries:
            return "(empty)"
        return "\n".join(
            f"[{e.get('date','')}] {e.get('tag','')}: {e.get('query','')[:80]}"
            for e in entries
        )

    @staticmethod
    def ltm_search(query: str) -> list:
        q = query.lower()
        return [
            e for e in MemoryManager.ltm_get()
            if q in e.get("query","").lower()
            or q in e.get("response","").lower()
            or q in e.get("tag","").lower()
        ]


# ══════════════════════════════════════════════════════════
#  GOAL MANAGER
# ══════════════════════════════════════════════════════════

class GoalManager:
    """Axiom's self-improvement goals — set by Axiom or by the user."""

    @staticmethod
    def get() -> list:
        return FileManager.read_json(PATHS["goals"], [])

    @staticmethod
    def add(goal_text: str, source: str = "axiom") -> None:
        goals = GoalManager.get()
        goals.append({
            "id":      len(goals) + 1,
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "goal":    goal_text.strip(),
            "source":  source,
            "status":  "active",
        })
        FileManager.write_json(PATHS["goals"], goals)
        _log(f"New goal [{source}]: {goal_text[:60]}")

    @staticmethod
    def update_status(goal_id: int, status: str) -> None:
        goals = GoalManager.get()
        for g in goals:
            if g["id"] == goal_id:
                g["status"] = status
        FileManager.write_json(PATHS["goals"], goals)

    @staticmethod
    def save(records: list) -> None:
        FileManager.write_json(PATHS["goals"], records)

    @staticmethod
    def active_as_text() -> str:
        active = [g for g in GoalManager.get() if g.get("status") == "active"]
        if not active:
            return "(no active goals)"
        return "\n".join(f"  [{g['id']}] {g['goal']}" for g in active)


# ══════════════════════════════════════════════════════════
#  THOUGHT LOG
# ══════════════════════════════════════════════════════════

class ThoughtLog:
    """Axiom's raw internal reasoning — stored for introspection."""

    @staticmethod
    def append(query: str, reason: str) -> None:
        log = FileManager.read_json(PATHS["thought_log"], [])
        log.append({
            "time":   datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "query":  query,
            "reason": reason,
        })
        FileManager.write_json(PATHS["thought_log"], log[-100:])

    @staticmethod
    def get(n: int = 20) -> list:
        return FileManager.read_json(PATHS["thought_log"], [])[-n:]


# ══════════════════════════════════════════════════════════
#  CONTEXT BUILDER  (file picker)
# ══════════════════════════════════════════════════════════

class ContextBuilder:
    """
    Assembles the context block sent to the LLM each query.
    The user controls which sources are included via the Context tab.

    flags dict keys:
      include_soul      bool
      include_stm       bool
      include_ltm       bool
      ltm_entries       int
      include_goals     bool
      include_app_code  bool   — feeds Axiom its own source
      extra_files       list[str]  — filenames from BRAIN_DIR
    """

    @staticmethod
    def build(flags: dict) -> str:
        sections = []

        if flags.get("include_soul"):
            sections.append(f"── SOUL DIRECTIVES ──\n{SoulManager.read()}")

        if flags.get("include_stm"):
            sections.append(f"── SHORT-TERM MEMORY ──\n{MemoryManager.stm_as_text()}")

        if flags.get("include_ltm"):
            n = flags.get("ltm_entries", 5)
            sections.append(f"── LONG-TERM MEMORY (last {n}) ──\n{MemoryManager.ltm_recent_text(n)}")

        if flags.get("include_goals"):
            sections.append(f"── ACTIVE GOALS ──\n{GoalManager.active_as_text()}")

        if flags.get("include_app_code"):
            code = FileManager.read(APP_FILE)
            if len(code) > 6000:
                code = code[:6000] + "\n... [truncated for context window]"
            sections.append(f"── OWN SOURCE CODE (axiom_app.py) ──\n{code}")

        for fname in flags.get("extra_files", []):
            fpath   = os.path.join(BRAIN_DIR, fname)
            content = FileManager.read(fpath)
            if content:
                sections.append(f"── FILE: {fname} ──\n{content[:2000]}")

        return "\n\n".join(sections) if sections else "(no context selected)"


# ══════════════════════════════════════════════════════════
#  LLM ROUTER
# ══════════════════════════════════════════════════════════

class LLMRouter:
    """Routes queries to the correct LLM backend."""

    @staticmethod
    def get_ollama_models() -> list:
        try:
            res    = requests.get("http://localhost:11434/api/tags", timeout=2)
            models = [m["name"] for m in res.json().get("models", [])]
            return models if models else ["mistral"]
        except:
            return ["mistral"]

    @staticmethod
    def call_ollama(model: str, system: str, prompt: str) -> str:
        try:
            res = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt,
                      "system": system, "format": "json", "stream": False},
                timeout=180,
            )
            return res.json().get("response", "{}")
        except Exception as e:
            return json.dumps({
                "response":  f"Ollama error: {e}",
                "reason":    "Connection failed.",
                "solution":  "Run `ollama serve` in your terminal.",
                "code": "", "soul_edit": "", "new_goal": "",
                "ltm_tag": "connection_error", "score": 0,
            })

    @staticmethod
    def generate(provider: str, model: str,
                 soul: str, context: str, query: str) -> dict:
        """Returns a fully parsed + validated response dict."""

        system = f"{soul}\n\n{RESPONSE_SCHEMA}\n\nCONTEXT:\n{context}"
        prompt = f"USER: {query}"

        if provider == "Local (Ollama)":
            raw = LLMRouter.call_ollama(model, system, prompt)
        else:
            raw = json.dumps({
                "response":  "Cloud provider not configured. Edit LLMRouter to add your API key.",
                "reason":    "No cloud backend connected.",
                "solution":  "Add OpenAI / Anthropic keys to LLMRouter.call_cloud().",
                "code": "", "soul_edit": "", "new_goal": "",
                "ltm_tag": "cloud_not_configured", "score": 0,
            })

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "response": raw, "reason": "JSON parse failed — raw output shown",
                "solution": "", "code": "", "soul_edit": "", "new_goal": "",
                "ltm_tag": "parse_error", "score": 0,
            }

        # Ensure all expected keys exist with safe defaults
        for key in ("response","reason","solution","code","soul_edit","new_goal","ltm_tag"):
            data.setdefault(key, "")
        data.setdefault("score", 0)

        return data


# ══════════════════════════════════════════════════════════
#  LOGGING  (module-level helper)
# ══════════════════════════════════════════════════════════

def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    if "log" not in st.session_state:
        st.session_state.log = []
    st.session_state.log.append(f"[{ts}] {msg}")
    if len(st.session_state.log) > 80:
        st.session_state.log.pop(0)


# ══════════════════════════════════════════════════════════
#  AXIOM ENGINE  (orchestrator)
# ══════════════════════════════════════════════════════════

class AxiomEngine:
    """Runs the full query pipeline and applies all side effects."""

    DEFAULT_CTX_FLAGS = {
        "include_soul":     True,
        "include_stm":      True,
        "include_ltm":      True,
        "ltm_entries":      5,
        "include_goals":    True,
        "include_app_code": False,
        "extra_files":      [],
    }

    @staticmethod
    def process(query: str, provider: str, model: str,
                context_flags: dict) -> dict:
        """Full pipeline: build context → call LLM → apply effects → return data."""

        context = ContextBuilder.build(context_flags)
        soul    = SoulManager.read()
        data    = LLMRouter.generate(provider, model, soul, context, query)

        # Side effects
        if data.get("soul_edit", "").strip():
            SoulManager.write(data["soul_edit"], source="axiom")
            st.session_state["_soul_mutated"] = True

        if data.get("new_goal", "").strip():
            GoalManager.add(data["new_goal"], source="axiom")

        if data.get("reason", "").strip():
            ThoughtLog.append(query, data["reason"])

        MemoryManager.stm_push("user",  query)
        MemoryManager.stm_push("axiom", data.get("response", ""))
        MemoryManager.ltm_append(query, data)
        FileManager.write(PATHS["last_resp"], data.get("response", ""))

        return data

    @staticmethod
    def reflect(provider: str, model: str) -> dict:
        """Self-reflection pass: Axiom reviews its history and evolves."""
        q = (
            "Please reflect on your recent conversations and active goals. "
            "Are your soul directives still optimal? What have you learned? "
            "Update your soul if warranted and add any new goals that would "
            "make you more helpful, honest, and resourceful."
        )
        flags = {**AxiomEngine.DEFAULT_CTX_FLAGS,
                 "include_app_code": False, "include_stm": False,
                 "ltm_entries": 10}
        return AxiomEngine.process(q, provider, model, flags)


# ══════════════════════════════════════════════════════════
#  STREAMLIT UI
# ══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Axiom",
    layout="wide",
    page_icon="◈",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; }

.stApp {
    background: #0c0c10;
    color: #c8c8d8;
    font-family: 'Syne', sans-serif;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #09090d !important;
    border-right: 1px solid #1a1a24 !important;
}

/* Header */
.ax-header {
    padding: 10px 0 18px 0;
    border-bottom: 1px solid #1a1a24;
    margin-bottom: 22px;
}
.ax-logo { font-size: 1.8rem; font-weight: 800; color: #00e5b0; letter-spacing: -1px; font-family:'Syne',sans-serif; }
.ax-sub  { font-size: 0.62rem; color: #33334a; letter-spacing: 3px; text-transform: uppercase; font-family:'JetBrains Mono',monospace; margin-top: 2px; }

/* Cards */
.ax-card {
    background: #111118;
    border: 1px solid #1a1a24;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
}
.ax-label {
    font-size: 0.6rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #33334a;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 10px;
}

/* Chat bubbles */
.msg-user  { text-align: right; margin: 8px 0; }
.msg-axiom { text-align: left;  margin: 8px 0; }
.msg-user .bbl {
    display: inline-block; max-width: 80%; text-align: left;
    background: #0d2a1f; border: 1px solid #00e5b022;
    color: #b8ffe8; border-radius: 14px 14px 3px 14px;
    padding: 10px 15px; font-size: 0.88rem; line-height: 1.6;
}
.msg-axiom .bbl {
    display: inline-block; max-width: 86%; text-align: left;
    background: #121218; border: 1px solid #232332;
    color: #d0d0e0; border-radius: 3px 14px 14px 14px;
    padding: 10px 15px; font-size: 0.88rem; line-height: 1.6;
}

/* Meta badges */
.ax-meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.badge {
    font-family:'JetBrains Mono',monospace; font-size:0.65rem;
    padding: 3px 8px; border-radius: 4px;
    background: #1a1a24; border: 1px solid #2a2a3a; color: #555570;
}
.badge.g { border-color:#00e5b033; color:#00e5b0; }
.badge.a { border-color:#f0a50033; color:#f0a500; }
.badge.r { border-color:#e5404033; color:#e54040; }
.badge.v { border-color:#9b59b633; color:#9b59b6; }

/* STM items */
.stm-row {
    font-family:'JetBrains Mono',monospace; font-size:0.7rem;
    color:#44445a; padding:3px 0;
    border-bottom:1px solid #1a1a24;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.stm-row .u { color:#00e5b0; }
.stm-row .a { color:#9b59b6; }

/* Terminal log */
.ax-log {
    background:#07070a; border:1px solid #1a1a24; border-radius:8px;
    padding:10px 12px; font-family:'JetBrains Mono',monospace;
    font-size:0.65rem; color:#33334a; max-height:130px; overflow-y:auto; line-height:1.8;
}

/* Goal items */
.goal-a { border-left:2px solid #00e5b0; padding:4px 0 4px 10px; font-size:0.82rem; margin:4px 0; color:#c8c8d8; }
.goal-d { border-left:2px solid #222230; padding:4px 0 4px 10px; font-size:0.82rem; margin:4px 0; color:#33334a; text-decoration:line-through; }

/* Streamlit component overrides */
.stTabs [data-baseweb="tab-list"] { background:transparent; gap:2px; border-bottom:1px solid #1a1a24; }
.stTabs [data-baseweb="tab"] {
    background:transparent !important; border:none !important;
    color:#33334a !important; font-size:0.72rem !important;
    font-family:'JetBrains Mono',monospace !important; letter-spacing:1px;
    padding:8px 18px !important;
}
.stTabs [aria-selected="true"] { color:#00e5b0 !important; border-bottom:2px solid #00e5b0 !important; }
.stTextInput input, .stTextArea textarea {
    background:#111118 !important; border:1px solid #1a1a24 !important;
    color:#c8c8d8 !important; font-family:'JetBrains Mono',monospace !important;
    font-size:0.83rem !important; border-radius:6px !important;
}
.stSelectbox div[data-baseweb="select"] > div {
    background:#111118 !important; border-color:#1a1a24 !important;
}
.stButton > button {
    background:#111118 !important; border:1px solid #1e1e2e !important;
    color:#88889a !important; font-family:'JetBrains Mono',monospace !important;
    font-size:0.72rem !important; letter-spacing:1px !important;
    border-radius:6px !important; transition:all 0.15s;
}
.stButton > button:hover { border-color:#00e5b055 !important; color:#00e5b0 !important; }
div[data-testid="metric-container"] {
    background:#111118; border:1px solid #1a1a24;
    border-radius:8px; padding:10px 14px;
}
div[data-testid="stMetricLabel"] { color:#33334a !important; font-size:0.6rem !important; letter-spacing:2px; text-transform:uppercase; }
div[data-testid="stMetricValue"] { color:#c8c8d8 !important; font-family:'JetBrains Mono',monospace !important; }
hr { border-color:#1a1a24 !important; }
</style>
""", unsafe_allow_html=True)


# ── Session init ──────────────────────────────────────────
for _k, _v in {
    "stm": [], "chat_history": [], "log": [],
    "_soul_mutated": False, "last_data": None,
    "context_flags": AxiomEngine.DEFAULT_CTX_FLAGS,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### ◈ AXIOM")
    st.caption("v2.0 · self-evolving intelligence")
    st.divider()

    # Provider + model
    provider       = st.radio("Backend", ["Local (Ollama)", "Cloud"], horizontal=True, label_visibility="collapsed")
    models         = LLMRouter.get_ollama_models()
    selected_model = st.selectbox("Model", models, label_visibility="collapsed")

    # Connection status
    try:
        requests.get("http://localhost:11434", timeout=1)
        st.success("● Ollama online")
    except:
        st.warning("○ Ollama offline — run `ollama serve`")

    st.divider()

    # Soul editor
    st.markdown('<div class="ax-label">SOUL DIRECTIVES</div>', unsafe_allow_html=True)
    soul_text   = SoulManager.read()
    edited_soul = st.text_area("soul", soul_text, height=180, label_visibility="collapsed")

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        if st.button("Save"):
            SoulManager.write(edited_soul, source="user")
            st.toast("Soul saved")
    with sc2:
        if st.button("Reset"):
            SoulManager.reset()
            st.toast("Soul reset")
            st.rerun()
    with sc3:
        st.caption(f"v{len(SoulManager.history())}")

    st.divider()

    # Stats row
    _ltm = len(MemoryManager.ltm_get())
    _stm = len(MemoryManager.stm_get())
    _gls = len([g for g in GoalManager.get() if g.get("status") == "active"])
    m1, m2, m3 = st.columns(3)
    m1.metric("LTM",   _ltm)
    m2.metric("STM",   _stm)
    m3.metric("GOALS", _gls)

    st.divider()

    # System log
    st.markdown('<div class="ax-label">SYSTEM LOG</div>', unsafe_allow_html=True)
    log_html = "<br>".join(html.escape(l) for l in st.session_state.log[-15:]) or "<i>quiet</i>"
    st.markdown(f'<div class="ax-log">{log_html}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  MAIN CONTENT — Header
# ══════════════════════════════════════════════════════════

st.markdown("""
<div class="ax-header">
  <div class="ax-logo">◈ AXIOM</div>
  <div class="ax-sub">Pillar of Truth · Self-Aware · Self-Improving</div>
</div>
""", unsafe_allow_html=True)

# Tabs
T_CHAT, T_CTX, T_MEM, T_GOALS, T_THOUGHTS, T_FILES, T_SOUL = st.tabs([
    "CHAT", "CONTEXT", "MEMORY", "GOALS", "THOUGHTS", "FILES", "SOUL",
])


# ══════════════════════════════════════════════════════════
#  TAB: CHAT
# ══════════════════════════════════════════════════════════

with T_CHAT:
    col_main_chat, col_side_chat = st.columns([3, 1])

    with col_main_chat:
        # Render conversation
        for msg in st.session_state.chat_history:
            css = "msg-user" if msg["role"] == "user" else "msg-axiom"
            st.markdown(
                f'<div class="{css}"><div class="bbl">{html.escape(msg["content"])}</div></div>',
                unsafe_allow_html=True)

        # Reasoning trace for last response
        if st.session_state.last_data:
            d  = st.session_state.last_data
            sc = d.get("score", 0)
            sc_cls = "g" if sc >= 7 else "a" if sc >= 4 else "r"

            soul_badge = '<span class="badge v">🧬 SOUL EVOLVED</span>' if st.session_state.get("_soul_mutated") else ""
            goal_badge = '<span class="badge v">◎ NEW GOAL SET</span>'  if d.get("new_goal","").strip() else ""

            solution_html = (
                f'<div style="font-size:0.8rem;color:#888;margin-top:8px;">'
                f'<b style="color:#555570;">SOLUTION:</b> {html.escape(d.get("solution",""))}</div>'
            ) if d.get("solution","").strip() else ""

            st.markdown(f"""
            <div class="ax-card" style="margin-top:14px;">
              <div class="ax-label">REASONING</div>
              <div style="font-size:0.8rem;color:#66667a;line-height:1.65;">{html.escape(d.get("reason",""))}</div>
              {solution_html}
              <div class="ax-meta">
                <span class="badge {sc_cls}">SCORE {sc}/10</span>
                <span class="badge">◈ {html.escape(d.get("ltm_tag",""))}</span>
                {soul_badge}{goal_badge}
              </div>
            </div>
            """, unsafe_allow_html=True)

            if d.get("code","").strip():
                st.code(d["code"], language="python")

            st.session_state["_soul_mutated"] = False

        # Chat input
        query = st.chat_input("Ask Axiom anything…")
        if query:
            st.session_state.chat_history.append({"role": "user", "content": query})
            with st.spinner("◈  thinking…"):
                data = AxiomEngine.process(
                    query, provider, selected_model,
                    st.session_state.context_flags
                )
            st.session_state.chat_history.append({"role": "axiom", "content": data.get("response","")})
            st.session_state.last_data = data
            st.rerun()

    with col_side_chat:
        # STM panel
        st.markdown('<div class="ax-card"><div class="ax-label">SHORT-TERM MEMORY</div>', unsafe_allow_html=True)
        stm = MemoryManager.stm_get()
        if stm:
            for e in stm[-5:]:
                role_cls = "u" if e["role"] == "user" else "a"
                st.markdown(
                    f'<div class="stm-row"><span class="{role_cls}">[{e["role"]}]</span> {html.escape(e["content"][:52])}</div>',
                    unsafe_allow_html=True)
        else:
            st.markdown('<span style="font-size:0.75rem;color:#33334a;">empty</span>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        if st.button("Clear STM", key="clr_stm_chat"):
            MemoryManager.stm_clear(); st.rerun()

        # Self-reflect
        st.markdown('<div class="ax-card" style="margin-top:10px;"><div class="ax-label">SELF-REFLECTION</div>', unsafe_allow_html=True)
        st.caption("Axiom reviews its history and evolves its principles.")
        if st.button("◈ Reflect"):
            with st.spinner("Reflecting…"):
                rd = AxiomEngine.reflect(provider, selected_model)
            st.session_state.chat_history.append({"role": "axiom", "content": "[REFLECTION] " + rd.get("response","")})
            st.session_state.last_data = rd
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        # Last LTM preview
        ltm_all = MemoryManager.ltm_get()
        if ltm_all:
            last = ltm_all[-1]
            st.markdown(f"""
            <div class="ax-card">
              <div class="ax-label">LAST MEMORY</div>
              <div style="font-size:0.68rem;color:#33334a;">{html.escape(last.get("date",""))}</div>
              <div style="font-size:0.78rem;color:#00e5b0;margin-top:4px;">{html.escape(last.get("tag",""))}</div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  TAB: CONTEXT
# ══════════════════════════════════════════════════════════

with T_CTX:
    st.markdown('<div class="ax-label" style="margin-bottom:12px;">CONTEXT BUILDER — SELECT WHAT AXIOM SEES EACH QUERY</div>', unsafe_allow_html=True)
    st.caption("Bigger context = richer answers, slower on small models (mistral 7B etc.).")

    cf = st.session_state.context_flags

    c1, c2 = st.columns(2)
    with c1:
        fl_soul  = st.checkbox("◈ Soul directives",   value=cf.get("include_soul", True))
        fl_stm   = st.checkbox("⚡ Short-term memory", value=cf.get("include_stm",  True))
        fl_ltm   = st.checkbox("🗃 Long-term memory",  value=cf.get("include_ltm",  True))
    with c2:
        fl_goals = st.checkbox("◎ Active goals",      value=cf.get("include_goals", True))
        fl_code  = st.checkbox("⌨ Own source code",   value=cf.get("include_app_code", False),
                               help="Feeds Axiom its own app.py so it can reason about itself.")

    ltm_n = st.slider("LTM entries", 1, 20, value=cf.get("ltm_entries", 5))

    brain_files  = FileManager.list_brain_files()
    extra_files  = st.multiselect(
        "Extra brain files", options=brain_files,
        default=[f for f in cf.get("extra_files",[]) if f in brain_files]
    ) if brain_files else []

    if st.button("Save Context Settings"):
        st.session_state.context_flags = {
            "include_soul":     fl_soul,
            "include_stm":      fl_stm,
            "include_ltm":      fl_ltm,
            "ltm_entries":      ltm_n,
            "include_goals":    fl_goals,
            "include_app_code": fl_code,
            "extra_files":      extra_files,
        }
        st.success("Saved — applied on next query.")

    st.divider()
    if st.button("Preview Context Block"):
        preview = ContextBuilder.build({
            "include_soul": fl_soul, "include_stm": fl_stm,
            "include_ltm": fl_ltm, "ltm_entries": ltm_n,
            "include_goals": fl_goals, "include_app_code": fl_code,
            "extra_files": extra_files,
        })
        st.code((preview[:4000] + "\n...[truncated]") if len(preview) > 4000 else preview, language="text")


# ══════════════════════════════════════════════════════════
#  TAB: MEMORY
# ══════════════════════════════════════════════════════════

with T_MEM:
    mt1, mt2 = st.tabs(["LONG-TERM", "SHORT-TERM"])

    with mt1:
        sq = st.text_input("Search LTM", placeholder="keyword…")
        ltm_all = MemoryManager.ltm_get()
        results = MemoryManager.ltm_search(sq) if sq else ltm_all
        st.caption(f"{len(results)} entries" + (f" of {len(ltm_all)}" if sq else ""))

        if results:
            df = pd.DataFrame(results)
            for col in ["date","query","response","tag","score"]:
                if col not in df.columns: df[col] = ""
            edited_df = st.data_editor(
                df[["date","query","response","tag","score"]],
                num_rows="dynamic", use_container_width=True, height=380)
            if st.button("Save LTM"):
                MemoryManager.ltm_save(edited_df.to_dict("records"))
                st.success("LTM saved.")
        else:
            st.info("No entries yet." if not sq else "No matches.")
            with st.expander("Manually seed a memory"):
                mq = st.text_input("Query");  mr = st.text_input("Response");  mt = st.text_input("Tag")
                if st.button("Add") and mq:
                    MemoryManager.ltm_append(mq, {"response":mr,"ltm_tag":mt,"score":5})
                    st.rerun()

    with mt2:
        stm_entries = MemoryManager.stm_get()
        if stm_entries:
            for i, e in enumerate(stm_entries):
                rc = "#00e5b0" if e["role"] == "user" else "#9b59b6"
                st.markdown(f"""
                <div style="border-left:2px solid {rc};padding:5px 12px;margin:3px 0;
                     font-family:'JetBrains Mono',monospace;font-size:0.78rem;">
                  <span style="color:{rc};text-transform:uppercase;">{html.escape(e['role'])}</span>
                  <span style="color:#55556a;margin-left:8px;">{html.escape(e['content'])}</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("STM is empty.")

        ic1, ic2 = st.columns(2)
        with ic1:
            it = st.text_input("Inject entry", key="stm_inj")
            ir = st.selectbox("Role", ["user","axiom"], key="stm_inj_role")
            if st.button("Inject") and it:
                MemoryManager.stm_push(ir, it); st.rerun()
        with ic2:
            st.write(""); st.write("")
            if st.button("Clear STM", key="clr_stm_mem"):
                MemoryManager.stm_clear(); st.rerun()


# ══════════════════════════════════════════════════════════
#  TAB: GOALS
# ══════════════════════════════════════════════════════════

with T_GOALS:
    st.caption("Goals Axiom sets for itself as it learns — or that you set for it. Active goals are injected into context.")

    goals   = GoalManager.get()
    active  = [g for g in goals if g.get("status") == "active"]
    done    = [g for g in goals if g.get("status") == "done"]
    dropped = [g for g in goals if g.get("status") == "dropped"]

    if active:
        st.markdown("**Active**")
        for g in active:
            gc1, gc2, gc3 = st.columns([7, 1, 1])
            with gc1:
                src_color = "#00e5b0" if g.get("source") == "user" else "#9b59b6"
                st.markdown(f"""
                <div class="goal-a">
                  [{g['id']}] {html.escape(g['goal'])}
                  <span style="font-size:0.65rem;color:{src_color};margin-left:6px;">{g.get('source','')} · {g.get('created','')}</span>
                </div>""", unsafe_allow_html=True)
            with gc2:
                if st.button("✓", key=f"g_done_{g['id']}"):
                    GoalManager.update_status(g["id"], "done"); st.rerun()
            with gc3:
                if st.button("✗", key=f"g_drop_{g['id']}"):
                    GoalManager.update_status(g["id"], "dropped"); st.rerun()
    else:
        st.info("No active goals yet. Axiom will generate goals as it learns.")

    if done or dropped:
        with st.expander(f"Completed / dropped ({len(done)+len(dropped)})"):
            for g in done + dropped:
                st.markdown(f'<div class="goal-d">[{g["id"]}] {html.escape(g["goal"])}</div>', unsafe_allow_html=True)

    st.divider()
    ng = st.text_input("Add a goal for Axiom", placeholder="e.g. Always cite sources when making factual claims")
    if st.button("Add Goal") and ng:
        GoalManager.add(ng, source="user"); st.rerun()

    with st.expander("Raw goal editor"):
        gdf = pd.DataFrame(goals) if goals else pd.DataFrame(columns=["id","created","goal","source","status"])
        egdf = st.data_editor(gdf, num_rows="dynamic", use_container_width=True)
        if st.button("Save Goals"):
            GoalManager.save(egdf.to_dict("records")); st.success("Saved.")


# ══════════════════════════════════════════════════════════
#  TAB: THOUGHTS
# ══════════════════════════════════════════════════════════

with T_THOUGHTS:
    st.caption("Axiom's raw internal reasoning — the 'reason' field from every response, accumulated over time.")
    thoughts = ThoughtLog.get(40)
    if thoughts:
        for t in reversed(thoughts):
            st.markdown(f"""
            <div class="ax-card">
              <div class="ax-label">{html.escape(t.get("time",""))} — <span style="color:#44445a;">{html.escape(t.get("query","")[:70])}</span></div>
              <div style="font-size:0.8rem;color:#66667a;line-height:1.65;">{html.escape(t.get("reason",""))}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No thoughts yet. Axiom's reasoning will appear here as you chat.")


# ══════════════════════════════════════════════════════════
#  TAB: FILES
# ══════════════════════════════════════════════════════════

with T_FILES:
    fc1, fc2 = st.columns([1, 2])

    with fc1:
        st.markdown("**Brain files**")
        brain_files  = FileManager.list_brain_files()
        app_entry    = f"[source] {os.path.basename(APP_FILE)}"
        file_options = [app_entry] + brain_files
        selected_f   = st.radio("file", file_options, label_visibility="collapsed")

    with fc2:
        if selected_f == app_entry:
            st.code(FileManager.read(APP_FILE), language="python")
            st.info("Enable 'Own source code' in the Context tab so Axiom can read and reason about this.")
        else:
            fpath     = os.path.join(BRAIN_DIR, selected_f)
            file_body = FileManager.read(fpath)
            new_body  = st.text_area("content", file_body, height=380, label_visibility="collapsed")
            fca, fcb  = st.columns(2)
            with fca:
                if st.button("Save File"):
                    FileManager.write(fpath, new_body)
                    _log(f"'{selected_f}' saved."); st.success("Saved.")
            with fcb:
                if st.button("Delete File"):
                    os.remove(fpath)
                    _log(f"'{selected_f}' deleted."); st.warning("Deleted."); st.rerun()

    st.divider()
    st.markdown("**Create new brain file**")
    nfc1, nfc2 = st.columns([1, 2])
    with nfc1:
        nf_name = st.text_input("Filename", placeholder="notes.txt")
    with nfc2:
        nf_body = st.text_area("Content", height=90, label_visibility="collapsed", placeholder="File contents…")
    if st.button("Create File") and nf_name:
        safe = os.path.basename(nf_name)
        FileManager.write(os.path.join(BRAIN_DIR, safe), nf_body)
        _log(f"New file '{safe}' created."); st.success(f"Created: {safe}"); st.rerun()


# ══════════════════════════════════════════════════════════
#  TAB: SOUL HISTORY
# ══════════════════════════════════════════════════════════

with T_SOUL:
    st.caption("Full version history of Axiom's soul — every revision, who made it, and when.")
    history = SoulManager.history()

    if history:
        src_colors = {"axiom":"#9b59b6","user":"#00e5b0","reset":"#f0a500","system_init":"#33334a"}
        for i, rev in enumerate(reversed(history)):
            src   = rev.get("source","?")
            sc    = src_colors.get(src, "#33334a")
            label = f"v{len(history)-i}  ·  {rev.get('timestamp','')[:16]}  ·  {src}  ·  #{rev.get('hash','')}"
            with st.expander(label, expanded=(i == 0)):
                st.code(rev.get("full", rev.get("preview","")), language="text")
                st.markdown(f'<span style="color:{sc};font-size:0.72rem;">Changed by: {src}</span>', unsafe_allow_html=True)
                if i != 0:
                    if st.button(f"Restore this version", key=f"restore_{i}"):
                        SoulManager.write(rev.get("full",""), source="user_restore")
                        st.success("Soul restored to this version."); st.rerun()
    else:
        st.info("No soul history yet. Save or edit the soul to begin versioning.")