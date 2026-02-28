import streamlit as st
import os
import json
import requests
import datetime

# --- AXIOM ENGINE ---
class AxiomEngine:
    def __init__(self, root_dir=None):
        self.root_dir = os.path.join(os.getcwd(), "soul.md")
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
        """Saves the interaction to long_term_memory.json"""
        try:
            with open(self.ltm_path, "r") as f:
                memory = json.load(f)
            
            new_memory = {
                "timestamp": str(datetime.datetime.now()),
                "query": user_query,
                "response": axiom_response
            }
            memory.append(new_memory)
            
            # Keep only last 50 memories to prevent bloat
            memory = memory[-50:]
            
            with open(self.ltm_path, "w") as f:
                json.dump(memory, f, indent=4)
        except Exception as e:
            self.log_event(f"Memory Update Error: {e}")

    def get_models(self):
        try:
            res = requests.get('http://localhost:11434/api/tags', timeout=3)
            return [m['name'] for m in res.json().get('models', [])]
        except:
            return ["mistral"]

    def read_files(self):
        knowledge = {}
        ignore = ['response.json', '.git', '.venv', '__pycache__']
        for file in os.listdir(self.root_dir):
            path = os.path.join(self.root_dir, file)
            if os.path.isfile(path) and not any(x in file for x in ignore):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        knowledge[file] = f.read()[:3000]
                except: continue
        return knowledge



if "axiom" not in st.session_state:
    st.session_state.axiom = AxiomEngine()
    st.session_state.terminal_logs = ["Core Initialized."]

ax = st.session_state.axiom

# --- SIDEBAR ---
with st.sidebar:
    st.title("AXIOM_CORE")
    selected_model = st.selectbox("Intelligence Level", ax.get_models(), key="model_select")
    
    st.markdown("---")
    with open(ax.soul_path, "r") as f:
        soul_val = f.read()
    new_soul = st.text_area("Soul Configuration", soul_val, height=250)
    if st.button("Update Soul"):
        with open(ax.soul_path, "w") as f:
            f.write(new_soul)
        st.success("Soul Refined.")

# --- MAIN INTERFACE ---
st.title("AXIOM_INTERFACE")

# Log Display
logs_html = "<br>".join(st.session_state.terminal_logs[-5:])
st.markdown(f'<div class="terminal">{logs_html}</div>', unsafe_allow_html=True)

# Chat Input
query = st.chat_input("Command Axiom...")
if query:
    ax.log_event(f"User Request: {query}")
    
    with st.spinner(f"Axiom ({selected_model}) is thinking..."):
        files_context = ax.read_files()
        context_string = "\n".join([f"FILE: {name}\n{content}" for name, content in files_context.items()])
        
        try:
            url = 'http://localhost:11434/api/generate'
            payload = {
                "model": selected_model,
                "prompt": f"SYSTEM/SOUL:\n{soul_val}\n\nCONTEXT:\n{context_string}\n\nUSER REQUEST: {query}",
                "format": "json",
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=300)
            raw_res = response.json().get('response', '{}')
            result = json.loads(raw_res)
            
            # --- PERSISTENCE LAYER ---
            # Save to response.json
            with open(ax.response_path, "w") as f:
                json.dump(result, f, indent=4)
            
            # Update LTM
            ax.update_ltm(query, result)
            
    #        Move the display logic INSIDE this 'if query' block
            st.markdown("### Axiom Insights")

            # Convert keys to lowercase for flexibility
            res_data = {k.lower(): v for k, v in result.items()} 

            reason = res_data.get("reason", "No reason provided.")
            solution = res_data.get("solution", "No action needed.")
            score = res_data.get("score", "N/A")

            st.markdown(f"""
            <div class="response-card">
                <strong>THOUGHT:</strong><br>{reason}<br><br>
                <strong>RESPONSE:</strong><br>{solution}<br><br>
                <strong>CONFIDENCE:</strong> {score}/10
            </div>
            """, unsafe_allow_html=True)
            
            # Check for code snippets
            code_snippet = res_data.get("code")
            if code_snippet:
                st.code(code_snippet, language="python")
            
            if "code" in result or "Code" in result:
                code_snippet = result.get("code") or result.get("Code")
                st.code(code_snippet, language="python")

            ax.log_event("Inference & Memory update successful.")

        except Exception as e:
            st.error(f"Execution Error: {e}")
            ax.log_event(f"ERROR: {e}")

st.markdown("---")

# --- WORKSPACE (FILE EDITOR) ---
st.subheader("📁 Axiom Workspace")
all_files = sorted([f for f in os.listdir(ax.root_dir) if os.path.isfile(os.path.join(ax.root_dir, f))])
selected_file = st.selectbox("Open File for Inspection", all_files, key="file_browser")

if selected_file:
    file_path = os.path.join(ax.root_dir, selected_file)
    with open(file_path, "r") as f:
        code_content = f.read()
    
    edited_code = st.text_area(f"Editing: {selected_file}", code_content, height=300, key="editor")
    if st.button("Save Changes"):
        with open(file_path, "w") as f:
            f.write(edited_code)
        ax.log_event(f"File Modified: {selected_file}")
        st.toast(f"Saved {selected_file}")