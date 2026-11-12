import csv
import io
import math
import os
import sqlite3
import uuid
from datetime import datetime

import requests
from flask import (
    Response, abort, flash, g, get_flashed_messages, redirect,
    render_template_string, request, url_for, Flask,
)
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = os.environ.get("DB_PATH", "/tmp/restocksmarter.db")
else:
    DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "restocksmarter.db"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "claude-3-5-haiku-latest")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "gracey.senica@gmail.com")
COOKIE_NAME = "sw_uid"

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" rx="8" fill="#0f7a6b"/>
<path d="M16 6 L26 11 L16 16 L6 11 Z" fill="#2fb39e"/>
<path d="M6 11 L16 16 L16 26 L6 21 Z" fill="#0b5e52"/>
<path d="M26 11 L16 16 L16 26 L26 21 Z" fill="#159483"/>
</svg>"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    name TEXT NOT NULL,
    sku TEXT NOT NULL DEFAULT '',
    qty INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    product_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    qty INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_uid ON products(uid);
CREATE INDEX IF NOT EXISTS idx_movements_uid ON movements(uid);
"""

# Starter data shown to each new visitor: (name, sku, qty, price, reorder_level)
SAMPLE = [
    ("Bottled water 500ml", "WT-02", 60, 15.0, 20),
    ("Canned sardines", "SD-03", 0, 24.0, 12),
    ("Instant coffee 3-in-1", "CF-01", 4, 8.0, 20),
    ("Rice 5kg", "RC-05", 8, 260.0, 10),
]

NAV = [
    ("dashboard", "Dashboard", "dashboard"),
    ("inventory", "Inventory", "inventory"),
    ("stock", "Stock In/Out", "stock_movements"),
    ("restock", "Restock", "restock"),
    ("ai", "AI Assistant", "ai_assistant"),
    ("privacy", "Privacy Policy", "privacy"),
]

PRIVACY_TEXT = """
<p><b>Data collected and why.</b> Restock Smarter has no accounts and does not ask for your name, email or any personal details. The product names, SKUs, quantities, prices and stock history you enter are stored in a database on the server so the app can show them next time. They are linked only to a random ID saved in a cookie in your browser. Please use fictitious or test data.</p>
<p><b>Use, storage and sharing.</b> Your data is used only to run the app and is not sold or shared. The hosting provider processes it on its servers and may keep standard technical logs such as IP addresses. The only other recipient is the optional AI Assistant: when you press Ask, your question and your current inventory list are sent to Anthropic’s Claude to generate an answer. Nothing is sent unless you press Ask.</p>
<p><b>Deletion.</b> Use the button below to delete all products and history linked to your browser. You can also ask the developer to delete data by contacting the email below.</p>
<p><b>Safeguards and limits.</b> The site uses HTTPS when served by the host, and each visitor’s data is kept separate by a random ID. There is no login, so anyone who gets your cookie could see your data. Data is not encrypted at rest, and the demo database may be reset when the server restarts. Do not enter sensitive or confidential information. AI answers may be wrong, so check them before acting.</p>
<p><b>Contact.</b> For privacy questions, contact the developer at: {{ contact }}.</p>
"""

LAYOUT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · Restock Smarter</title>
<link rel="icon" type="image/svg+xml" href="/favicon.ico">
<script>
(function() {
  try {
    var saved = localStorage.getItem('theme');
    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    var theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {}
})();
</script>
<style>
:root{--bg:#f5f7f8;--card:#fff;--text:#1d2528;--muted:#5d6b70;--brand:#0f7a6b;--brand-text:#fff;--line:#dfe5e7;--ok:#1b7f3b;--low:#9a6700;--out:#b42318;--ok-bg:#e3f5ea;--low-bg:#fff4d6;--out-bg:#fde4e1;--input:#fff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121819;--card:#1c2426;--text:#e7eeef;--muted:#9fb0b4;--brand:#2fb39e;--brand-text:#06201b;--line:#2c3739;--ok:#7ee2a0;--low:#f5d27a;--out:#ff9b92;--ok-bg:#183a27;--low-bg:#3d3216;--out-bg:#44201d;--input:#11181a}}
[data-theme="dark"]{--bg:#121819;--card:#1c2426;--text:#e7eeef;--muted:#9fb0b4;--brand:#2fb39e;--brand-text:#06201b;--line:#2c3739;--ok:#7ee2a0;--low:#f5d27a;--out:#ff9b92;--ok-bg:#183a27;--low-bg:#3d3216;--out-bg:#44201d;--input:#11181a}
[data-theme="light"]{--bg:#f5f7f8;--card:#fff;--text:#1d2528;--muted:#5d6b70;--brand:#0f7a6b;--brand-text:#fff;--line:#dfe5e7;--ok:#1b7f3b;--low:#9a6700;--out:#b42318;--ok-bg:#e3f5ea;--low-bg:#fff4d6;--out-bg:#fde4e1;--input:#fff}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.45;transition:background-color .2s ease,color .2s ease}
header{background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px;transition:background-color .2s ease,border-color .2s ease}
.header-top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.brand{font-weight:800;font-size:1.3rem}.brand span{color:var(--brand)}
.tag{color:var(--muted);font-size:.85rem}
.theme-toggle{display:inline-flex;align-items:center;gap:7px;background:var(--bg);border:1px solid var(--line);color:var(--text);padding:6px 14px;border-radius:20px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .2s ease;user-select:none}
.theme-toggle:hover{border-color:var(--brand);background:var(--card);transform:translateY(-1px);box-shadow:0 2px 6px rgba(0,0,0,.08)}
.theme-toggle svg{flex-shrink:0}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
nav a{padding:6px 12px;border:1px solid var(--line);border-radius:8px;color:var(--text);text-decoration:none;font-size:.92rem;transition:all .15s ease}
nav a.active{background:var(--brand);color:var(--brand-text);border-color:var(--brand)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid var(--brand);outline-offset:2px}
main{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:8px 0 12px}
h2{font-size:1.1rem;margin:0 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px;transition:background-color .2s ease,border-color .2s ease}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.stats .card{margin:0}
.stat b{display:block;font-size:1.5rem}.stat span{color:var(--muted);font-size:.85rem}
form.row{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted);gap:4px}
input,select,textarea{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--input);color:var(--text);min-width:0;transition:background-color .2s ease,border-color .2s ease,color .2s ease}
button,.btn{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--brand);background:var(--brand);color:var(--brand-text);cursor:pointer;text-decoration:none;display:inline-block;transition:all .15s ease}
.btn-light{background:transparent;color:var(--text);border-color:var(--line)}
.btn-danger{background:transparent;color:var(--out);border-color:var(--out)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.93rem}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--muted);font-weight:600}
.num{text-align:right}
.pill{padding:2px 8px;border-radius:999px;font-size:.78rem;font-weight:600;white-space:nowrap}
.ok{background:var(--ok-bg);color:var(--ok)}.low{background:var(--low-bg);color:var(--low)}.out{background:var(--out-bg);color:var(--out)}
.flash{padding:10px 12px;border-radius:8px;margin-bottom:12px}
.flash.success{background:var(--ok-bg);color:var(--ok)}.flash.error{background:var(--out-bg);color:var(--out)}.flash.info{background:var(--low-bg);color:var(--low)}
.muted{color:var(--muted)}
.footer{text-align:center;color:var(--muted);font-size:.8rem;padding:24px 0}
ul.attn{list-style:none;padding:0;margin:0}
ul.attn li{padding:8px 0;border-bottom:1px solid var(--line)}
textarea{width:100%;min-height:90px}
.actions form{display:inline}
p{margin:0 0 10px}
</style>
</head>
<body>
<header>
  <div class="header-top">
    <div>
      <div class="brand">Restock<span>Smarter</span></div>
      <div class="tag">Smart Inventory Management for Small Businesses</div>
    </div>
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light mode" title="Toggle dark/light mode">
      <svg class="theme-icon moon-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
      <svg class="theme-icon sun-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="display:none">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
      <span class="theme-label">Dark Mode</span>
    </button>
  </div>
  <nav>
    {% for key, label, url in nav %}
    <a href="{{ url }}" class="{{ 'active' if active == key else '' }}"{% if active == key %} aria-current="page"{% endif %}>{{ label }}</a>
    {% endfor %}
  </nav>
</header>
<main>
  {% for cat, msg in messages %}<div class="flash {{ cat }}" role="status">{{ msg }}</div>{% endfor %}
  {{ body|safe }}
</main>
<div class="footer">Restock Smarter · PNC–CPE Web App Builders · Demo data is fictitious</div>
<script>
(function() {
  var btn = document.getElementById('theme-toggle');
  if (!btn) return;
  var sun = btn.querySelector('.sun-icon');
  var moon = btn.querySelector('.moon-icon');
  var label = btn.querySelector('.theme-label');

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('theme', theme); } catch (e) {}
    var isDark = theme === 'dark';
    if (sun) sun.style.display = isDark ? 'inline-block' : 'none';
    if (moon) moon.style.display = isDark ? 'none' : 'inline-block';
    if (label) label.textContent = isDark ? 'Light Mode' : 'Dark Mode';
    btn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
    btn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
  }

  var currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(currentTheme);

  btn.addEventListener('click', function() {
    var cur = document.documentElement.getAttribute('data-theme') || 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
})();
</script>
</body>
</html>
"""

TEMPLATES = {
    "dashboard": """
<h1>Dashboard</h1>
<div class="stats">
  <div class="card stat"><b>{{ s.products }}</b><span>Products</span></div>
  <div class="card stat"><b>{{ s.units }}</b><span>Units in stock</span></div>
  <div class="card stat"><b>{{ s.value|peso }}</b><span>Stock value</span></div>
  <div class="card stat"><b>{{ s.need }}</b><span>Need restock</span></div>
</div>
<div class="card">
  <h2>Needs attention</h2>
  {% if attention %}
  <ul class="attn">
    {% for d in attention %}
    <li>{{ d.name }} <span class="pill {{ d.css }}">{{ d.status }}</span>
        {{ d.qty }} left (reorder at {{ d.reorder_level }})</li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="muted">Everything is above its reorder level.</p>
  {% endif %}
</div>
""",

    "inventory": """
<h1>Inventory</h1>
<div class="card">
  <h2>Add product</h2>
  <form method="post" action="{{ url_for('add_product') }}" class="row">
    <label>Product<input name="name" required maxlength="100"></label>
    <label>SKU<input name="sku" maxlength="40"></label>
    <label>Quantity<input name="qty" type="number" min="0" step="1" value="0" required></label>
    <label>Price (₱)<input name="price" type="number" min="0" step="0.01" value="0" required></label>
    <label>Reorder level<input name="reorder_level" type="number" min="0" step="1" value="0" required></label>
    <button type="submit">Add product</button>
  </form>
</div>
<div class="card">
  <form method="get" class="row" role="search">
    <label>Search<input name="q" value="{{ q }}" placeholder="Name or SKU"></label>
    <label>Filter
      <select name="filter">
        {% for v, l in [('all', 'All'), ('low', 'Low stock'), ('out', 'Out of stock')] %}
        <option value="{{ v }}" {{ 'selected' if v == flt else '' }}>{{ l }}</option>
        {% endfor %}
      </select>
    </label>
    <button type="submit">Apply</button>
    <a class="btn btn-light" href="{{ url_for('export_csv') }}">Export CSV</a>
  </form>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Product</th><th>SKU</th><th class="num">Qty</th><th class="num">Price</th><th>Status</th><th>Actions</th></tr></thead>
    <tbody>
    {% for d in items %}
      <tr>
        <td>{{ d.name }}</td>
        <td>{{ d.sku }}</td>
        <td class="num">{{ d.qty }}</td>
        <td class="num">{{ d.price|peso }}</td>
        <td><span class="pill {{ d.css }}">{{ d.status }}</span></td>
        <td class="actions">
          <a class="btn btn-light" href="{{ url_for('edit_product', pid=d.id) }}">Edit</a>
          <form method="post" action="{{ url_for('delete_product', pid=d.id) }}"
                onsubmit="return confirm('Delete this product and its history?');">
            <button class="btn-danger" type="submit">Delete</button>
          </form>
        </td>
      </tr>
    {% else %}
      <tr><td colspan="6" class="muted">No products match.</td></tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>
""",

    "edit": """
<h1>Edit product</h1>
<div class="card">
  <form method="post" class="row">
    <label>Product<input name="name" required maxlength="100" value="{{ p.name }}"></label>
    <label>SKU<input name="sku" maxlength="40" value="{{ p.sku }}"></label>
    <label>Quantity<input name="qty" type="number" min="0" step="1" value="{{ p.qty }}" required></label>
    <label>Price (₱)<input name="price" type="number" min="0" step="0.01" value="{{ p.price }}" required></label>
    <label>Reorder level<input name="reorder_level" type="number" min="0" step="1" value="{{ p.reorder_level }}" required></label>
    <button type="submit">Save changes</button>
    <a class="btn btn-light" href="{{ url_for('inventory') }}">Cancel</a>
  </form>
</div>
""",

    "stock": """
<h1>Stock in / out</h1>
{% if items %}
<div class="card">
  <form method="post" class="row">
    <label>Product
      <select name="product_id" required>
        {% for d in items %}<option value="{{ d.id }}">{{ d.name }} ({{ d.qty }})</option>{% endfor %}
      </select>
    </label>
    <label>Type
      <select name="type">
        <option value="in">Stock in (delivery)</option>
        <option value="out">Stock out (sale or use)</option>
      </select>
    </label>
    <label>Quantity<input name="qty" type="number" min="1" step="1" required></label>
    <label>Note<input name="note" maxlength="200" placeholder="Optional"></label>
    <button type="submit">Record</button>
  </form>
</div>
{% else %}
<div class="card"><p>Add a product on the Inventory page first.</p></div>
{% endif %}
<div class="card">
  <h2>History</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Date</th><th>Product</th><th>Type</th><th class="num">Qty</th><th>Note</th></tr></thead>
    <tbody>
    {% for m in history %}
      <tr>
        <td>{{ m.created }}</td>
        <td>{{ m.name }}</td>
        <td>{{ 'Stock in' if m.type == 'in' else 'Stock out' }}</td>
        <td class="num">{{ m.qty }}</td>
        <td>{{ m.note }}</td>
      </tr>
    {% else %}
      <tr><td colspan="5" class="muted">No movements yet.</td></tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>
""",

    "restock": """
<h1>Restock list</h1>
<div class="card">
  <p class="muted">Items at or below their reorder level, with a suggested order amount
  (double the reorder level, minus current stock).</p>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Product</th><th>Status</th><th class="num">On hand</th><th class="num">Reorder level</th><th class="num">Suggested order</th><th class="num">Est. cost</th></tr></thead>
    <tbody>
    {% for d in restock %}
      <tr>
        <td>{{ d.name }}</td>
        <td><span class="pill {{ d.css }}">{{ d.status }}</span></td>
        <td class="num">{{ d.qty }}</td>
        <td class="num">{{ d.reorder_level }}</td>
        <td class="num"><b>{{ d.suggest }}</b></td>
        <td class="num">{{ d.cost|peso }}</td>
      </tr>
    {% else %}
      <tr><td colspan="6" class="muted">Nothing to reorder right now.</td></tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>
""",

    "ai": """
<h1>AI Assistant</h1>
<div class="card">
  <p class="muted">Ask a question about your current stock. Your question and inventory list are sent
  to the AI service only when you press Ask. AI answers may be wrong, so check them before acting.</p>
  <form method="post">
    <label>Your question
      <textarea name="question" maxlength="500" required placeholder="What should I restock first?">{{ question }}</textarea>
    </label>
    <p></p>
    <button type="submit">Ask</button>
  </form>
</div>
{% if answer %}
<div class="card">
  <h2>Answer</h2>
  <p style="white-space:pre-wrap">{{ answer }}</p>
</div>
{% endif %}
""",

    "privacy": """
<h1>Privacy Policy</h1>
<div class="card">
  <p class="muted">Last updated: October 17, 2026. Restock Smarter is a student coursework project.</p>
  """ + PRIVACY_TEXT + """
</div>
<div class="card">
  <h2>Delete my data</h2>
  <p>This deletes all products and history linked to your browser.</p>
  <form method="post" action="{{ url_for('clear_data') }}"
        onsubmit="return confirm('Delete ALL your products and history? This cannot be undone.');">
    <button class="btn-danger" type="submit">Delete all my data</button>
  </form>
</div>
""",
}


# ---------- database helpers ----------

def get_db():
    global DB_PATH
    if "db" not in g:
        try:
            g.db = sqlite3.connect(DB_PATH, timeout=10)
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            DB_PATH = "/tmp/restocksmarter.db"
            g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    global DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.executescript(SCHEMA)
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        DB_PATH = "/tmp/restocksmarter.db"
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.executescript(SCHEMA)
        conn.close()


init_db()


# ---------- visitor identity (random cookie) ----------

@app.before_request
def assign_visitor():
    if request.path in ("/favicon.ico", "/robots.txt"):
        return
    uid = request.cookies.get(COOKIE_NAME, "")
    valid = len(uid) == 32 and all(c in "0123456789abcdef" for c in uid)
    if not valid:
        uid = uuid.uuid4().hex
        g.new_visitor = True
        db = get_db()
        for name, sku, qty, price, reorder in SAMPLE:
            db.execute(
                "INSERT INTO products (uid, name, sku, qty, price, reorder_level) VALUES (?,?,?,?,?,?)",
                (uid, name, sku, qty, price, reorder),
            )
        db.commit()
    g.uid = uid


@app.after_request
def set_visitor_cookie(resp):
    if g.get("new_visitor"):
        resp.set_cookie(
            COOKIE_NAME, g.uid,
            max_age=60 * 60 * 24 * 365, httponly=True,
            samesite="Lax", secure=request.is_secure,
        )
    return resp


@app.context_processor
def inject_contact():
    return {"contact": CONTACT_EMAIL}


@app.template_filter("peso")
def peso(value):
    return f"₱{float(value):,.2f}"


# ---------- business logic ----------

CSS_FOR = {"OK": "ok", "Low stock": "low", "Out of stock": "out"}


def status_of(qty, reorder_level):
    if qty <= 0:
        return "Out of stock"
    if qty <= reorder_level:
        return "Low stock"
    return "OK"


def load_products():
    rows = get_db().execute(
        "SELECT * FROM products WHERE uid = ? ORDER BY name COLLATE NOCASE", (g.uid,)
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d["status"] = status_of(d["qty"], d["reorder_level"])
        d["css"] = CSS_FOR[d["status"]]
        d["value"] = d["qty"] * d["price"]
        items.append(d)
    return items


def filter_products(items, q, flt):
    q = q.lower()
    out = []
    for d in items:
        if q and q not in d["name"].lower() and q not in d["sku"].lower():
            continue
        if flt == "low" and d["status"] != "Low stock":
            continue
        if flt == "out" and d["status"] != "Out of stock":
            continue
        out.append(d)
    return out


def owned_product(pid):
    row = get_db().execute(
        "SELECT * FROM products WHERE id = ? AND uid = ?", (pid, g.uid)
    ).fetchone()
    if row is None:
        abort(404)
    return row


def parse_product(form):
    name = form.get("name", "").strip()[:100]
    sku = form.get("sku", "").strip()[:40]
    try:
        qty = int(form.get("qty", ""))
        price = float(form.get("price", ""))
        reorder = int(form.get("reorder_level", ""))
    except ValueError:
        return None, "Quantity, price and reorder level must be valid numbers."
    if not name:
        return None, "Product name is required."
    if not math.isfinite(price):
        return None, "Price must be a valid number."
    if qty < 0 or price < 0 or reorder < 0:
        return None, "Negative numbers are not allowed."
    if qty > 10_000_000 or price > 10_000_000 or reorder > 10_000_000:
        return None, "Numbers cannot exceed 10,000,000."
    return {"name": name, "sku": sku, "qty": qty,
            "price": round(price, 2), "reorder_level": reorder}, None


def safe_cell(value):
    """Stop spreadsheet apps from treating text as a formula."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def ask_ai(question, items):
    if not ANTHROPIC_API_KEY:
        return None, "The AI Assistant is switched off on this server. All other features still work."
    lines = "\n".join(
        f"- {d['name']} (SKU {d['sku'] or 'n/a'}): {d['qty']} on hand, "
        f"reorder at {d['reorder_level']}, price ₱{d['price']:.2f}, status {d['status']}"
        for d in items
    ) or "(no products)"
    system = ("You are a helpful inventory assistant for a small business. Answer using only "
              "the inventory list provided. Be concise. If the answer is not in the list, say so.")
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": 500,
                "system": system,
                "messages": [{"role": "user",
                              "content": f"Current inventory:\n{lines}\n\nQuestion: {question}"}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", [])
                       if b.get("type") == "text").strip()
        return (text or "No answer was returned."), None
    except requests.RequestException:
        return None, "The AI service could not be reached. Please try again later."


# ---------- page rendering ----------

def page(name, active, title, **ctx):
    body = render_template_string(TEMPLATES[name], **ctx)
    nav = [(key, label, url_for(endpoint)) for key, label, endpoint in NAV]
    return render_template_string(
        LAYOUT, body=body, nav=nav, active=active, title=title,
        messages=get_flashed_messages(with_categories=True),
    )


# ---------- routes ----------

@app.errorhandler(404)
def handle_404(e):
    # If running behind Vercel rewrite where PATH_INFO got stripped or prefixed
    path = request.path
    if path.startswith("/api/index.py"):
        target = path[len("/api/index.py"):] or "/"
        return redirect(target)
    if path.startswith("/api/index"):
        target = path[len("/api/index"):] or "/"
        return redirect(target)
    if path.startswith("/api"):
        target = path[len("/api"):] or "/"
        return redirect(target)
    return f"404 Not Found: path={request.path}, PATH_INFO={request.environ.get('PATH_INFO')}", 404


@app.route("/favicon.ico")
def favicon():
    return Response(FAVICON_SVG, mimetype="image/svg+xml")


@app.get("/")
def dashboard():
    items = load_products()
    attention = sorted(
        (d for d in items if d["status"] != "OK"),
        key=lambda d: (d["status"] != "Out of stock", d["name"].lower()),
    )
    s = {
        "products": len(items),
        "units": sum(d["qty"] for d in items),
        "value": sum(d["value"] for d in items),
        "need": len(attention),
    }
    return page("dashboard", "dashboard", "Dashboard", s=s, attention=attention)


@app.get("/inventory")
def inventory():
    q = request.args.get("q", "").strip()
    flt = request.args.get("filter", "all")
    if flt not in ("all", "low", "out"):
        flt = "all"
    items = filter_products(load_products(), q, flt)
    return page("inventory", "inventory", "Inventory", items=items, q=q, flt=flt)


@app.post("/inventory/add")
def add_product():
    data, err = parse_product(request.form)
    if err:
        flash(err, "error")
        return redirect(url_for("inventory"))
    db = get_db()
    db.execute(
        "INSERT INTO products (uid, name, sku, qty, price, reorder_level) VALUES (?,?,?,?,?,?)",
        (g.uid, data["name"], data["sku"], data["qty"], data["price"], data["reorder_level"]),
    )
    db.commit()
    flash("Product added.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/<int:pid>/edit", methods=["GET", "POST"])
def edit_product(pid):
    p = owned_product(pid)
    if request.method == "POST":
        data, err = parse_product(request.form)
        if err:
            flash(err, "error")
            return redirect(url_for("edit_product", pid=pid))
        db = get_db()
        db.execute(
            "UPDATE products SET name=?, sku=?, qty=?, price=?, reorder_level=? WHERE id=? AND uid=?",
            (data["name"], data["sku"], data["qty"], data["price"], data["reorder_level"], pid, g.uid),
        )
        db.commit()
        flash("Product updated.", "success")
        return redirect(url_for("inventory"))
    return page("edit", "inventory", "Edit product", p=dict(p))


@app.post("/inventory/<int:pid>/delete")
def delete_product(pid):
    owned_product(pid)
    db = get_db()
    db.execute("DELETE FROM movements WHERE product_id = ? AND uid = ?", (pid, g.uid))
    db.execute("DELETE FROM products WHERE id = ? AND uid = ?", (pid, g.uid))
    db.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("inventory"))


@app.get("/inventory/export.csv")
def export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Product", "SKU", "Quantity", "Price", "Reorder level", "Status", "Stock value"])
    for d in load_products():
        writer.writerow([
            safe_cell(d["name"]), safe_cell(d["sku"]), d["qty"],
            f"{d['price']:.2f}", d["reorder_level"], d["status"], f"{d['value']:.2f}",
        ])
    # UTF-8 BOM so Excel shows the peso sign correctly
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=restock-smarter-inventory.csv"},
    )


@app.route("/stock", methods=["GET", "POST"])
def stock_movements():
    db = get_db()
    if request.method == "POST":
        try:
            pid = int(request.form.get("product_id", ""))
            qty = int(request.form.get("qty", ""))
        except ValueError:
            flash("Choose a product and enter a whole-number quantity.", "error")
            return redirect(url_for("stock_movements"))
        mtype = request.form.get("type", "")
        note = request.form.get("note", "").strip()[:200]
        if mtype not in ("in", "out") or qty <= 0 or qty > 1_000_000:
            flash("Choose Stock in or Stock out and enter a quantity above zero.", "error")
            return redirect(url_for("stock_movements"))
        p = owned_product(pid)
        if mtype == "out" and qty > p["qty"]:
            flash(f"Not enough stock: only {p['qty']} on hand. Quantity unchanged.", "error")
            return redirect(url_for("stock_movements"))
        new_qty = p["qty"] + qty if mtype == "in" else p["qty"] - qty
        db.execute("UPDATE products SET qty = ? WHERE id = ? AND uid = ?", (new_qty, pid, g.uid))
        db.execute(
            "INSERT INTO movements (uid, product_id, type, qty, note, created) VALUES (?,?,?,?,?,?)",
            (g.uid, pid, mtype, qty, note, now()),
        )
        db.commit()
        flash("Movement recorded.", "success")
        return redirect(url_for("stock_movements"))

    items = load_products()
    history = db.execute(
        """SELECT m.qty, m.type, m.note, m.created, p.name
           FROM movements m JOIN products p ON p.id = m.product_id
           WHERE m.uid = ? ORDER BY m.id DESC LIMIT 50""",
        (g.uid,),
    ).fetchall()
    return page("stock", "stock", "Stock In/Out", items=items, history=history)


@app.get("/restock")
def restock():
    rows = [d for d in load_products() if d["status"] != "OK"]
    for d in rows:
        d["suggest"] = max(0, 2 * d["reorder_level"] - d["qty"])
        d["cost"] = d["suggest"] * d["price"]
    rows.sort(key=lambda d: (d["status"] != "Out of stock", d["name"].lower()))
    return page("restock", "restock", "Restock", restock=rows)


@app.route("/ai", methods=["GET", "POST"])
def ai_assistant():
    question, answer = "", None
    if request.method == "POST":
        question = request.form.get("question", "").strip()[:500]
        if not question:
            flash("Please type a question first.", "error")
        else:
            answer, err = ask_ai(question, load_products())
            if err:
                flash(err, "info")
                answer = None
    return page("ai", "ai", "AI Assistant", question=question, answer=answer)


@app.get("/privacy")
def privacy():
    return page("privacy", "privacy", "Privacy Policy")


@app.post("/privacy/clear")
def clear_data():
    db = get_db()
    db.execute("DELETE FROM movements WHERE uid = ?", (g.uid,))
    db.execute("DELETE FROM products WHERE uid = ?", (g.uid,))
    db.commit()
    flash("All your products and history were deleted.", "success")
    return redirect(url_for("privacy"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting server on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)