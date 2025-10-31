from flask import Flask, request, render_template_string
import sqlite3
import os

app = Flask(__name__)
DB_PATH = "knowledge_base.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titolo TEXT NOT NULL,
        domanda_chiave TEXT NOT NULL,
        contenuto TEXT NOT NULL,
        data_inserimento DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<title>Knowledge Base</title>
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
<h1>📚 Knowledge Base</h1>
<h2>Aggiungi un nuovo documento</h2>
<form method="POST" action="/add">
<input type="text" name="titolo" placeholder="Titolo" required>
<input type="text" name="domanda_chiave" placeholder="Domanda chiave" required>
<textarea name="contenuto" placeholder="Contenuto del documento" rows="5" required></textarea>
<button type="submit">Aggiungi</button>
</form>
<h2>Cerca documento per domanda</h2>
<form method="GET" action="/search">
<input type="text" name="q" placeholder="Scrivi la tua domanda..." required>
<button type="submit">Cerca</button>
</form>
{% if result %}
<div class="result">
<h3>Risultato trovato:</h3>
<p><strong>{{ result['titolo'] }}</strong></p>
<p>{{ result['contenuto'] }}</p>
</div>
{% elif no_result %}
<div class="result">
<p>Nessun documento trovato per questa domanda.</p>
</div>
{% endif %}
</body>
</html>"""

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/add", methods=["POST"])
def add_doc():
    titolo = request.form["titolo"]
    domanda = request.form["domanda_chiave"]
    contenuto = request.form["contenuto"]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO documenti (titolo, domanda_chiave, contenuto) VALUES (?, ?, ?)", (titolo, domanda, contenuto))
    conn.commit()
    conn.close()
    return render_template_string(HTML_TEMPLATE, result={"titolo": "Documento aggiunto", "contenuto": "✅ Inserito con successo!"})

@app.route("/search")
def search():
    q = request.args.get("q", "")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT titolo, contenuto FROM documenti WHERE domanda_chiave LIKE ?", ('%' + q + '%',))
    row = c.fetchone()
    conn.close()
    if row:
        result = {"titolo": row[0], "contenuto": row[1]}
        return render_template_string(HTML_TEMPLATE, result=result)
    else:
        return render_template_string(HTML_TEMPLATE, no_result=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
