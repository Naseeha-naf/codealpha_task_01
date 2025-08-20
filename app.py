from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = "supersecretkey_for_testing"  # keep while testing

DB_PATH = Path(__file__).with_name("database.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            placed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # seed products if empty
    cnt = cur.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    if cnt == 0:
        cur.executemany(
            "INSERT INTO products (name, price, description) VALUES (?, ?, ?)",
            [
                ("Laptop", 55000.0, "15.6\" FHD | Intel i5 | 16GB RAM | 512GB SSD — Great for coding and school projects."),
                ("Mobile", 15000.0, "6.5\" display | 8GB RAM | 128GB storage | 50MP camera | 5000mAh battery."),
                ("Headphones", 2499.0, "Over-ear ANC headphones | 30h battery | Comfortable."),
                ("USB-C Hub", 1499.0, "5-in-1 Hub: HDMI 4K, 2xUSB-A, SD, microSD."),
                ("Wireless Mouse", 899.0, "Ergonomic wireless mouse | 1600 DPI | 12 month battery.")
            ]
        )
    conn.commit()
    conn.close()

init_db()

def update_cart_count():
    cart = session.get("cart", {})
    session["cart_count"] = sum(int(q) for q in cart.values()) if cart else 0

# ---------- Routes ----------
@app.route("/")
def root():
    if session.get("user_id"):
        return redirect(url_for("products"))
    return redirect(url_for("login"))

# Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("Enter username and password", "danger")
            return render_template("signup.html")
        conn = get_conn()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            flash("Account created. Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("Username already taken", "danger")
            return render_template("signup.html")
    return render_template("signup.html")

# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_conn()
        user = conn.execute("SELECT id, username FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        conn.close()
        if user:
            session["user_id"] = int(user["id"])
            session["username"] = user["username"]
            if "cart" not in session:
                session["cart"] = {}
            update_cart_count()
            return redirect(url_for("products"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Products list
@app.route("/products")
def products():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    conn = get_conn()
    rows = conn.execute("SELECT id, name, price, description FROM products ORDER BY id").fetchall()
    conn.close()
    products_list = [dict(r) for r in rows]
    return render_template("products.html", products=products_list)

# Product detail
@app.route("/product/<int:pid>")
def product_detail(pid):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    conn = get_conn()
    r = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not r:
        flash("Product not found", "danger")
        return redirect(url_for("products"))
    return render_template("product_detail.html", product=dict(r))

# Add to cart
@app.route("/add_to_cart/<int:pid>")
def add_to_cart(pid):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    conn = get_conn()
    exists = conn.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not exists:
        flash("Product not found", "danger")
        return redirect(url_for("products"))
    cart = session.get("cart", {})
    cart[str(pid)] = int(cart.get(str(pid), 0)) + 1
    session["cart"] = cart
    update_cart_count()
    flash("Added to cart", "success")
    return redirect(url_for("products"))

# Remove from cart
@app.route("/remove_from_cart/<int:pid>")
def remove_from_cart(pid):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    cart = session.get("cart", {})
    if str(pid) in cart:
        del cart[str(pid)]
        session["cart"] = cart
        update_cart_count()
        flash("Removed from cart", "info")
    return redirect(url_for("cart"))

# View cart
@app.route("/cart")
def cart():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    cart = session.get("cart", {})
    items = []
    total = 0.0
    if cart:
        ids = [int(k) for k in cart.keys()]
        placeholders = ",".join(["?"] * len(ids))
        conn = get_conn()
        rows = conn.execute(f"SELECT id, name, price FROM products WHERE id IN ({placeholders})", ids).fetchall()
        conn.close()
        for r in rows:
            pid = r["id"]
            qty = int(cart.get(str(pid), 0))
            subtotal = float(r["price"]) * qty
            total += subtotal
            items.append({"id": pid, "name": r["name"], "price": float(r["price"]), "qty": qty, "subtotal": subtotal})
    return render_template("cart.html", items=items, total=total)

# Checkout
@app.route("/checkout", methods=["POST"])
def checkout():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    cart = session.get("cart", {})
    if not cart:
        flash("Cart is empty", "danger")
        return redirect(url_for("cart"))
    conn = get_conn()
    for pid_str, qty in cart.items():
        conn.execute("INSERT INTO orders (user_id, product_id, qty) VALUES (?, ?, ?)",
                     (session["user_id"], int(pid_str), int(qty)))
    conn.commit()
    conn.close()
    session["cart"] = {}
    update_cart_count()
    flash("Order placed successfully", "success")
    return redirect(url_for("products"))

if __name__ == "__main__":
    app.run(debug=True)
