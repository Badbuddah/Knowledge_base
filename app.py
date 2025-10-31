from flask import Flask, request, render_template_string, send_from_directory
import sqlite3, os
import openai
from PyPDF2 import PdfReader
import numpy as np
import traceback

app = Flask(__name__)

# Percorsi locali sicuri
UPLOAD_FOLDER = os.path.join("data", "uploads")
DB_PATH = os.path.join("data", "knowledge_base.db")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Limite massimo upload 50 MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Carica API key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️ Attenzione: OPENAI_API_KEY non impostata. L'AI non funzionerà.")
else:
    openai.api_key = OPENAI_API_KEY

# --- Database ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titolo TEXT NOT NULL,
        domanda_chiave TEXT,
        contenuto TEXT NOT NULL,
        embedding TEXT,
        file_path TEXT,
        data_inserimento DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# --- Funzioni ---
def estrai_testo_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Errore estrazione PDF {file_path}: {e}")
        return ""

def create_embedding(text):
    if not OPENAI_API_KEY:
        return None
    try:
        res = openai.Embedding.create(input=text, model="text-embedding-3-small")
        return res['data'][0]['embedding']
    except Exception as e:
        print(f"Errore creazione embedding: {e}")
        return None

def cosine_similarity(a, b):
    try:
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    except:
        return 0

# --- Template HTML ---
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Knowledge Base AI</title>
<style>
body { font-family: Arial; margin: 40px; background-color: #f5f5f5; }
h1 { color: #333; }
form { margin-bottom: 30px; }
input, textarea { width: 100%; padding: 10px; margin: 5px 0; }
button { padding: 10px 20px; background-color: #0078d7; color: white; border: none; cursor: pointer; border-radius: 8px; }
button:hover { background-color: #005fa3; }
.result { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
</style>
</head>
<body>
<h1>📚 Knowledge Base AI</h1>
<h2>Aggiungi un nuovo documento</h2>
<form method="POST" action="/add" enctype="multipart/form-data">
<input type="text" name="titolo" placeholder="Titolo" required>
<input type="text" name="domanda_chiave" placeholder="Domanda chiave (opzionale)">
<textarea name="contenuto" placeholder="Contenuto del documento" rows="5"></textarea>
<input type="file" name="file">
<button type="submit">Aggiungi</button>
</form>
<h2>Fai una domanda</h2>
<form method="GET" action="/search">
<input type="text" name="q" placeholder="Scrivi la tua domanda..." required>
<button type="submit">Cerca</button>
</form>
{% if result %}
<div class="result">
<h3>Risposta AI:</h3>
<p>{{ result }}</p>
</div>
{% elif error %}
<div class="result" style="color:red;">
<p>Errore: {{ error }}</p>
</div>
{% elif no_result %}
<div class="result">
<p>Nessuna risposta disponibile.</p>
</div>
{% endif %}
</body>
</html>"""

# --- Routes ---
ALLOWED_EXTENSIONS = ["pdf", "txt"]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/add", methods=["POST"])
def add_doc():
    try:
        titolo = request.form["titolo"]
        domanda = request.form.get("domanda_chiave", "")
        contenuto = request.form.get("contenuto", "")
        file = request.files.get("file")

        file_path = None
        if file and file.filename != "":
            if not allowed_file(file.filename):
                return render_template_string(HTML_TEMPLATE, error="Formato file non supportato! (solo PDF o TXT)")
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)
            if file.filename.endswith(".pdf"):
                contenuto += "\n" + estrai_testo_pdf(file_path)
            elif file.filename.endswith(".txt"):
                try:
                    contenuto += "\n" + open(file_path, "r", encoding="utf-8").read()
                except UnicodeDecodeError:
                    contenuto += "\n" + open(file_path, "r", encoding="latin-1").read()
                except Exception as e:
                    print(f"Errore lettura TXT: {e}")

        embedding_vector = create_embedding(contenuto) if contenuto else None

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO documenti (titolo, domanda_chiave, contenuto, embedding, file_path) VALUES (?, ?, ?, ?, ?)",
                  (titolo, domanda, contenuto, str(embedding_vector), file_path))
        conn.commit()
        conn.close()

        return render_template_string(HTML_TEMPLATE, result="✅ Documento aggiunto con successo!")
    except Exception as e:
        print(traceback.format_exc())
        return render_template_string(HTML_TEMPLATE, error=str(e))

@app.route("/search")
def search():
    q = request.args.get("q", "")
    if not q:
        return render_template_string(HTML_TEMPLATE, no_result=True)
    try:
        query_emb = create_embedding(q)
        if query_emb is None:
            return render_template_string(HTML_TEMPLATE, error="API key mancante o errore AI")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT titolo, contenuto, embedding FROM documenti")
        rows = c.fetchall()
        conn.close()

        max_sim = -1
        best_text = ""
        for titolo, contenuto, emb_str in rows:
            if emb_str:
                try:
                    emb = np.array(eval(emb_str))
                    sim = np.dot(np.array(query_emb), emb) / (np.linalg.norm(query_emb)*np.linalg.norm(emb))
                    if sim > max_sim:
                        max_sim = sim
                        best_text = contenuto
                except:
                    continue

        if best_text:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Sei un assistente che risponde solo basandosi sui documenti forniti."},
                        {"role": "user", "content": f"Domanda: {q}\nDocumenti rilevanti: {best_text}"}
                    ]
                )
                answer = response.choices[0].message.content
                return render_template_string(HTML_TEMPLATE, result=answer)
            except Exception as e:
                return render_template_string(HTML_TEMPLATE, error=f"Errore AI: {e}")
        else:
            return render_template_string(HTML_TEMPLATE, no_result=True)
    except Exception as e:
        print(traceback.format_exc())
        return render_template_string(HTML_TEMPLATE, error=str(e))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
