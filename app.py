import streamlit as st
import os
import json
import requests
import datetime
import pandas as pd # For memory visualization

# --- AXIOM ENGINE ---
class AxiomEngine:
    def __init__(self, root_dir=None):
        self.root_dir = os.path.join(os.getcwd(), "soul.md")
        os.makedirs(self.root_dir, exist_ok=True)
        self.soul_path = os.path.join(self.root_dir, "soul.txt")
        self.ltm_path = os.path.join(self.root_dir, "long_term_memory.json")
        self.response_path = os.path.join(self.root_dir, "response.json")
        self._boot_sequence()

    def _boot_sequence(self):
        if not os.path.exists(self.soul_path):
            with open(self.soul_path, "w") as f:
                f.write("You are Axiom. Goal: Self-improve code.")
        if not os.path.exists(self.ltm_path):
            with open(self.ltm_path, "w") as f:
                json.dump([], f)

    def log_event(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        if "terminal_logs" not in st.session_state:
            st.session_state.terminal_logs = []
        st.session_state.terminal_logs.append(f"[{timestamp}] {message}")

    def update_ltm(self, user_query, axiom_response):
        try:
            with open(self.ltm_path, "r") as f:
                memory = json.load(f)
            new_memory = {
                "timestamp": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
                "query": user_query,
                "response": axiom_response.get("solution", "No solution recorded")
            }
            memory.append(new_memory)
            memory = memory[-50:]
            with open(self.ltm_path, "w") as f:
                json.dump(memory, f, indent=4)
        except Exception as e:
            self.log_event(f"Memory Error: {e}")

    def get_models(self):
        try:
            res = requests.get('http://localhost:11434/api/tags', timeout=3)
            return [m['name'] for m in res.json().get('models', [])]
        except:
            return ["mistral"]

    def read_files(self):
        knowledge = {}
        ignore = ['response.json', '.git', '.venv', '__pycache__']
        # Read from current dir AND soul.md
        for target in [os.getcwd(), self.root_dir]:
            for file in os.listdir(target):
                path = os.path.join(target, file)
                if os.path.isfile(path) and not any(x in file for x in ignore):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            knowledge[file] = f.read()[:2000]
                    except: continue
        return knowledge

# --- UI SETUP ---
st.set_page_config(page_title="AXIOM CORE", layout="wide", initial_sidebar_state="expanded")

# Custom Cyberpunk CSS
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;500&display=swap');
    
    .stApp { background-color: #0a0a0c; color: #00ffcc; font-family: 'Fira Code', monospace; }
    .terminal { background: rgba(0, 20, 20, 0.8); border: 1px solid #00ffcc; padding: 15px; border-radius: 5px; height: 180px; overflow-y: auto; color: #00ffcc; box-shadow: 0 0 10px #00ffcc44; }
    .response-card { background: rgba(255, 255, 255, 0.05); border-left: 4px solid #00ffcc; padding: 20px; border-radius: 10px; margin: 15px 0; }
    .stButton>button { background: transparent; border: 1px solid #00ffcc; color: #00ffcc; width: 100%; transition: 0.3s; }
    .stButton>button:hover { background: #00ffcc; color: #000; box-shadow: 0 0 15px #00ffcc; }
    </style>
    """, unsafe_allow_html=True)

if "axiom" not in st.session_state:
    st.session_state.axiom = AxiomEngine()
    st.session_state.terminal_logs = ["Core Initialized."]

ax = st.session_state.axiom

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2103/2103633.png", width=80)
    st.title("AXIOM_CORE")
    selected_model = st.selectbox("Intelligence Level", ax.get_models())
    
    st.divider()
    with open(ax.soul_path, "r") as f:
        soul_val = f.read()
    new_soul = st.text_area("Soul Configuration", soul_val, height=200)
    if st.button("REPROGRAM SOUL"):
        with open(ax.soul_path, "w") as f:
            f.write(new_soul)
        st.toast("Soul logic updated.", icon="🔥")

# --- MAIN LAYOUT ---
tab1, tab2, tab3 = st.tabs(["📡 INTERFACE", "🧠 MEMORY", "📂 WORKSPACE"])

with tab1:
    st.title("AXIOM_INTERFACE")
    
    # Terminal Display
    logs_html = "<br>".join(st.session_state.terminal_logs[-8:])
    st.markdown(f'<div class="terminal">{logs_html}</div>', unsafe_allow_html=True)
    
    query = st.chat_input("Command Axiom...")
    
    if query:
        ax.log_event(f"Request: {query}")
        with st.spinner("Decoding..."):
            files_context = ax.read_files()
            context_string = "\n".join([f"FILE: {name}\n{content}" for name, content in files_context.items()])
            
            try:
                payload = {
                    "model": selected_model,
                    "prompt": f"SYSTEM/SOUL:\n{soul_val}\n\nCONTEXT:\n{context_string}\n\nUSER REQUEST: {query}",
                    "format": "json", "stream": False
                }
                response = requests.post('http://localhost:11434/api/generate', json=payload, timeout=60)
                result = json.loads(response.json().get('response', '{}'))
                
                # Lowercase mapping for safety
                res_data = {k.lower(): v for k, v in result.items()}
                
                st.markdown(f"""
                <div class="response-card">
                    <h4 style='color:#00ffcc'>&gt; INSIGHT</h4>
                    <p><strong>REASON:</strong> {res_data.get('reason', 'N/A')}</p>
                    <p><strong>ACTION:</strong> {res_data.get('solution', 'N/A')}</p>
                    <small>Confidence: {res_data.get('score', '?')}/10</small>
                </div>
                """, unsafe_allow_html=True)

                if res_data.get("code"):
                    st.code(res_data["code"], language="python")
                
                ax.update_ltm(query, res_data)
                ax.log_event("Success: Memory Synced.")
                
            except Exception as e:
                st.error(f"Inference Error: {e}")

with tab2:
    st.subheader("Long Term Memory Logs")
    if os.path.exists(ax.ltm_path):
        with open(ax.ltm_path, "r") as f:
            mem_data = json.load(f)
        if mem_data:
            df = pd.DataFrame(mem_data)
            st.dataframe(df, use_container_width=True)
            if st.button("WIPE MEMORY"):
                with open(ax.ltm_path, "w") as f: json.dump([], f)
                st.rerun()
        else:
            st.info("Memory banks empty.")

with tab3:
    st.subheader("File Architect")
    # Scan both main dir and soul.md
    files = [f for f in os.listdir(os.getcwd()) if os.path.isfile(f)] + \
            [f"soul.md/{f}" for f in os.listdir(ax.root_dir) if os.path.isfile(os.path.join(ax.root_dir, f))]
    
    selected_file = st.selectbox("Select File", sorted(files))
    
    if selected_file:
        file_path = os.path.join(os.getcwd(), selected_file)
        with open(file_path, "r") as f:
            content = f.read()
        
        new_content = st.text_area("Edit Code", content, height=400)
        if st.button("COMMIT CHANGES"):
            with open(file_path, "w") as f:
                f.write(new_content)
            st.success(f"{selected_file} updated.")