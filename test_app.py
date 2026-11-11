import os
import sqlite3
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import app as sw  # noqa: E402

sw.app.config["TESTING"] = True


def test_dashboard_shows_sample_data():
    client = sw.app.test_client()
    r = client.get("/")
    assert r.status_code == 200
    assert b"Canned sardines" in r.data


def test_negative_numbers_rejected():
    client = sw.app.test_client()
    client.get("/")
    r = client.post("/inventory/add", data={
        "name": "Bad", "sku": "", "qty": "-1", "price": "5", "reorder_level": "2",
    }, follow_redirects=True)
    assert b"Negative numbers are not allowed." in r.data


def test_stock_out_over_quantity_is_blocked():
    client = sw.app.test_client()
    client.get("/")
    client.post("/inventory/add", data={
        "name": "Test item", "sku": "T-1", "qty": "2", "price": "5", "reorder_level": "1",
    })
    conn = sqlite3.connect(os.environ["DB_PATH"])
    pid = conn.execute("SELECT MAX(id) FROM products WHERE name = 'Test item'").fetchone()[0]
    conn.close()
    r = client.post("/stock", data={
        "product_id": pid, "type": "out", "qty": "5", "note": "",
    }, follow_redirects=True)
    assert b"Not enough stock" in r.data


def test_csv_export_downloads():
    client = sw.app.test_client()
    client.get("/")
    r = client.get("/inventory/export.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert b"Canned sardines" in r.data


def test_inventory_filter_and_search():
    client = sw.app.test_client()
    client.get("/")
    r = client.get("/inventory?q=sardines&filter=all")
    assert r.status_code == 200
    assert b"Canned sardines" in r.data
    assert b"Bottled water" not in r.data


def test_edit_product():
    client = sw.app.test_client()
    client.get("/")
    uid = client.get_cookie("sw_uid").value
    conn = sqlite3.connect(os.environ["DB_PATH"])
    pid = conn.execute("SELECT id FROM products WHERE uid = ? AND name = 'Canned sardines'", (uid,)).fetchone()[0]
    conn.close()

    r = client.get(f"/inventory/{pid}/edit")
    assert r.status_code == 200
    assert b"Canned sardines" in r.data

    r = client.post(f"/inventory/{pid}/edit", data={
        "name": "Canned tuna", "sku": "TN-01", "qty": "15", "price": "35.50", "reorder_level": "5",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Product updated." in r.data
    assert b"Canned tuna" in r.data


def test_stock_in_movement():
    client = sw.app.test_client()
    client.get("/")
    uid = client.get_cookie("sw_uid").value
    conn = sqlite3.connect(os.environ["DB_PATH"])
    pid = conn.execute("SELECT id FROM products WHERE uid = ? AND name = 'Rice 5kg'", (uid,)).fetchone()[0]
    conn.close()

    r = client.post("/stock", data={
        "product_id": pid, "type": "in", "qty": "10", "note": "Weekly delivery",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Movement recorded." in r.data
    assert b"Weekly delivery" in r.data


def test_delete_product():
    client = sw.app.test_client()
    client.get("/")
    client.post("/inventory/add", data={
        "name": "Temporary item", "sku": "TMP", "qty": "1", "price": "10", "reorder_level": "1",
    })
    conn = sqlite3.connect(os.environ["DB_PATH"])
    pid = conn.execute("SELECT id FROM products WHERE name = 'Temporary item'").fetchone()[0]
    conn.close()

    r = client.post(f"/inventory/{pid}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert b"Product deleted." in r.data
    assert b"Temporary item" not in r.data


def test_restock_page():
    client = sw.app.test_client()
    client.get("/")
    r = client.get("/restock")
    assert r.status_code == 200
    assert b"Restock list" in r.data


def test_ai_assistant_empty_and_disabled():
    client = sw.app.test_client()
    client.get("/")
    # Empty question
    r = client.post("/ai", data={"question": ""}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Please type a question first." in r.data

    # Valid question without API key
    r = client.post("/ai", data={"question": "What is low?"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"The AI Assistant is switched off on this server." in r.data


def test_privacy_and_clear_data():
    client = sw.app.test_client()
    client.get("/")
    r = client.get("/privacy")
    assert r.status_code == 200
    assert b"gracey.senica@gmail.com" in r.data

    r = client.post("/privacy/clear", follow_redirects=True)
    assert r.status_code == 200
    assert b"All your products and history were deleted." in r.data


def test_theme_toggle_is_rendered():
    client = sw.app.test_client()
    r = client.get("/")
    assert r.status_code == 200
    assert b"theme-toggle" in r.data
    assert b"moon-icon" in r.data
    assert b"sun-icon" in r.data
    assert b"Dark Mode" in r.data


def test_favicon_serves_svg():
    client = sw.app.test_client()
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert "image/svg+xml" in r.content_type
