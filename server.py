from flask import Flask, send_from_directory, request, jsonify
from pathlib import Path
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import sqlite3
import os
import secrets
from datetime import datetime

# =========================================================
# BDXbet SERVER
# Existing website/Ludo routes + Admin API
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    static_folder=str(BASE_DIR),
    static_url_path=""
)

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "bdxbet-change-this-secret-key"
)

DB_FILE = BASE_DIR / "users.db"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123456")

TOKEN_SALT = "bdxbet-admin-token-v1"

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table_name, column_name):
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(row["name"] == column_name for row in rows)


def init_database():

    conn = get_db()

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE,
            phone TEXT UNIQUE,
            password TEXT,
            name TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            balance REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Existing users.db থাকলে missing columns যোগ হবে
    user_columns = {
        "uid": "TEXT",
        "phone": "TEXT",
        "password": "TEXT",
        "name": "TEXT DEFAULT ''",
        "avatar": "TEXT DEFAULT ''",
        "balance": "REAL DEFAULT 0",
        "status": "TEXT DEFAULT 'active'",
        "created_at": "TEXT"
    }

    for column, definition in user_columns.items():
        if not column_exists(conn, "users", column):
            try:
                conn.execute(
                    f"ALTER TABLE users ADD COLUMN {column} {definition}"
                )
            except Exception:
                pass

    # -----------------------------------------------------
    # TRANSACTIONS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            type TEXT,
            amount REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)

    default_settings = {
        "ludo_enabled": "true",
        "maintenance": "false",
        "announcement": "",
        "welcome_bonus": "0",
        "jackpot": "0"
    }

    for key, value in default_settings.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

    conn.commit()
    conn.close()


init_database()


# =========================================================
# HELPERS
# =========================================================

def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def get_setting(key, default=""):
    conn = get_db()

    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()

    conn.close()

    if row:
        return row["value"]

    return default


def set_setting(key, value):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (key, str(value))
    )

    conn.commit()
    conn.close()


def create_token(username):

    return serializer.dumps({
        "username": username,
        "type": "admin"
    }, salt=TOKEN_SALT)


def verify_token(token):

    try:
        data = serializer.loads(
            token,
            salt=TOKEN_SALT,
            max_age=60 * 60 * 24
        )

        if data.get("type") != "admin":
            return None

        return data

    except (BadSignature, SignatureExpired):
        return None


def admin_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        auth = request.headers.get("Authorization", "")

        if not auth.startswith("Bearer "):
            return jsonify({
                "ok": False,
                "error": "Admin authentication required"
            }), 401

        token = auth.replace("Bearer ", "", 1).strip()

        data = verify_token(token)

        if not data:
            return jsonify({
                "ok": False,
                "error": "Invalid or expired admin token"
            }), 401

        return func(*args, **kwargs)

    return wrapper


def generate_uid():

    while True:

        uid = "LK-" + "".join(
            secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            for _ in range(8)
        )

        conn = get_db()

        exists = conn.execute(
            "SELECT id FROM users WHERE uid=?",
            (uid,)
        ).fetchone()

        conn.close()

        if not exists:
            return uid


# =========================================================
# EXISTING WEBSITE ROUTES
# =========================================================

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/ludo")
def ludo():
    return send_from_directory(BASE_DIR, "shuvoludo.html")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "BDXbet",
        "ludo": "ready"
    }


@app.get("/<path:filename>")
def static_files(filename):

    file_path = BASE_DIR / filename

    if file_path.is_file():
        return send_from_directory(BASE_DIR, filename)

    return "Not Found", 404


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.post("/api/admin/login")
def admin_login():

    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if username != ADMIN_USERNAME:
        return jsonify({
            "ok": False,
            "error": "Invalid username or password"
        }), 401

    if password != ADMIN_PASSWORD:
        return jsonify({
            "ok": False,
            "error": "Invalid username or password"
        }), 401

    token = create_token(username)

    return jsonify({
        "ok": True,
        "token": token,
        "username": username
    })


@app.get("/api/admin/me")
@admin_required
def admin_me():

    return jsonify({
        "ok": True,
        "admin": ADMIN_USERNAME
    })


# =========================================================
# ADMIN DASHBOARD STATS
# =========================================================

@app.get("/api/admin/stats")
@admin_required
def admin_stats():

    conn = get_db()

    total_users = conn.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]

    active_users = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM users
        WHERE status='active'
        """
    ).fetchone()["count"]

    blocked_users = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM users
        WHERE status='blocked'
        """
    ).fetchone()["count"]

    total_balance = conn.execute(
        """
        SELECT COALESCE(SUM(balance), 0) AS total
        FROM users
        """
    ).fetchone()["total"]

    pending_deposits = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM transactions
        WHERE type='deposit'
        AND status='pending'
        """
    ).fetchone()["count"]

    pending_withdrawals = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM transactions
        WHERE type='withdraw'
        AND status='pending'
        """
    ).fetchone()["count"]

    conn.close()

    return jsonify({
        "ok": True,
        "total_users": total_users,
        "active_users": active_users,
        "blocked_users": blocked_users,
        "total_balance": total_balance,
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
        "ludo_enabled": get_setting("ludo_enabled") == "true",
        "maintenance": get_setting("maintenance") == "true",
        "announcement": get_setting("announcement"),
        "welcome_bonus": get_setting("welcome_bonus", "0"),
        "jackpot": get_setting("jackpot", "0")
    })


# =========================================================
# USERS
# =========================================================

@app.get("/api/admin/users")
@admin_required
def admin_users():

    search = request.args.get("search", "").strip()

    conn = get_db()

    if search:

        rows = conn.execute(
            """
            SELECT
                id,
                uid,
                phone,
                name,
                avatar,
                balance,
                status,
                created_at
            FROM users
            WHERE uid LIKE ?
               OR phone LIKE ?
               OR name LIKE ?
            ORDER BY id DESC
            LIMIT 500
            """,
            (
                f"%{search}%",
                f"%{search}%",
                f"%{search}%"
            )
        ).fetchall()

    else:

        rows = conn.execute(
            """
            SELECT
                id,
                uid,
                phone,
                name,
                avatar,
                balance,
                status,
                created_at
            FROM users
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "users": [dict(row) for row in rows]
    })


# =========================================================
# SINGLE USER
# =========================================================

@app.get("/api/admin/users/<uid>")
@admin_required
def admin_get_user(uid):

    conn = get_db()

    row = conn.execute(
        """
        SELECT
            id,
            uid,
            phone,
            name,
            avatar,
            balance,
            status,
            created_at
        FROM users
        WHERE uid=?
        """,
        (uid,)
    ).fetchone()

    conn.close()

    if not row:

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    return jsonify({
        "ok": True,
        "user": dict(row)
    })


# =========================================================
# CHANGE USER BALANCE
# =========================================================

@app.post("/api/admin/users/<uid>/balance")
@admin_required
def admin_change_balance(uid):

    data = request.get_json(silent=True) or {}

    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):

        return jsonify({
            "ok": False,
            "error": "Invalid amount"
        }), 400

    action = str(data.get("action", "add")).lower()
    note = str(data.get("note", ""))

    if amount <= 0:

        return jsonify({
            "ok": False,
            "error": "Amount must be greater than 0"
        }), 400

    if action not in ("add", "subtract"):

        return jsonify({
            "ok": False,
            "error": "Action must be add or subtract"
        }), 400

    conn = get_db()

    user = conn.execute(
        "SELECT uid, balance FROM users WHERE uid=?",
        (uid,)
    ).fetchone()

    if not user:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    old_balance = float(user["balance"] or 0)

    if action == "add":

        new_balance = old_balance + amount

    else:

        new_balance = old_balance - amount

        if new_balance < 0:
            conn.close()

            return jsonify({
                "ok": False,
                "error": "Insufficient balance"
            }), 400

    conn.execute(
        """
        UPDATE users
        SET balance=?
        WHERE uid=?
        """,
        (new_balance, uid)
    )

    transaction_type = (
        "admin_add"
        if action == "add"
        else "admin_subtract"
    )

    conn.execute(
        """
        INSERT INTO transactions
        (
            uid,
            type,
            amount,
            status,
            note,
            created_at
        )
        VALUES (?, ?, ?, 'approved', ?, ?)
        """,
        (
            uid,
            transaction_type,
            amount,
            note,
            now()
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "uid": uid,
        "old_balance": old_balance,
        "new_balance": new_balance
    })


# =========================================================
# BLOCK / UNBLOCK USER
# =========================================================

@app.post("/api/admin/users/<uid>/status")
@admin_required
def admin_change_status(uid):

    data = request.get_json(silent=True) or {}

    status = str(
        data.get("status", "")
    ).lower().strip()

    if status not in ("active", "blocked"):

        return jsonify({
            "ok": False,
            "error": "Status must be active or blocked"
        }), 400

    conn = get_db()

    cursor = conn.execute(
        """
        UPDATE users
        SET status=?
        WHERE uid=?
        """,
        (status, uid)
    )

    conn.commit()

    changed = cursor.rowcount

    conn.close()

    if changed == 0:

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    return jsonify({
        "ok": True,
        "uid": uid,
        "status": status
    })


# =========================================================
# CREATE USER
# =========================================================

@app.post("/api/admin/users")
@admin_required
def admin_create_user():

    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    name = str(data.get("name", "")).strip()
    password = str(data.get("password", ""))

    if not phone:

        return jsonify({
            "ok": False,
            "error": "Phone is required"
        }), 400

    if not password:

        return jsonify({
            "ok": False,
            "error": "Password is required"
        }), 400

    uid = generate_uid()

    conn = get_db()

    try:

        conn.execute(
            """
            INSERT INTO users
            (
                uid,
                phone,
                password,
                name,
                balance,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, 'active', ?)
            """,
            (
                uid,
                phone,
                generate_password_hash(password),
                name,
                now()
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "Phone already exists"
        }), 409

    conn.close()

    return jsonify({
        "ok": True,
        "uid": uid,
        "phone": phone,
        "name": name
    }), 201


# =========================================================
# USER LOGIN API
# =========================================================

@app.post("/api/auth/login")
def user_login():

    data = request.get_json(silent=True) or {}

    login = str(
        data.get("uid") or
        data.get("phone") or
        ""
    ).strip()

    password = str(data.get("password", ""))

    if not login or not password:

        return jsonify({
            "ok": False,
            "error": "UID/phone and password are required"
        }), 400

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE uid=? OR phone=?
        LIMIT 1
        """,
        (login, login)
    ).fetchone()

    conn.close()

    if not row:

        return jsonify({
            "ok": False,
            "error": "Invalid login"
        }), 401

    if row["status"] != "active":

        return jsonify({
            "ok": False,
            "error": "Account is blocked"
        }), 403

    stored_password = row["password"] or ""

    valid = False

    try:
        valid = check_password_hash(
            stored_password,
            password
        )
    except Exception:
        valid = False

    if not valid:

        return jsonify({
            "ok": False,
            "error": "Invalid login"
        }), 401

    return jsonify({
        "ok": True,
        "user": {
            "uid": row["uid"],
            "phone": row["phone"],
            "name": row["name"],
            "avatar": row["avatar"],
            "balance": row["balance"],
            "status": row["status"]
        }
    })


# =========================================================
# TRANSACTIONS
# =========================================================

@app.get("/api/admin/transactions")
@admin_required
def admin_transactions():

    status = request.args.get("status", "").strip()
    tx_type = request.args.get("type", "").strip()

    conn = get_db()

    query = """
        SELECT
            id,
            uid,
            type,
            amount,
            status,
            note,
            created_at
        FROM transactions
        WHERE 1=1
    """

    params = []

    if status:

        query += " AND status=?"
        params.append(status)

    if tx_type:

        query += " AND type=?"
        params.append(tx_type)

    query += """
        ORDER BY id DESC
        LIMIT 500
    """

    rows = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "transactions": [
            dict(row)
            for row in rows
        ]
    })


# =========================================================
# CREATE DEPOSIT / WITHDRAW REQUEST
# =========================================================

@app.post("/api/transactions")
def create_transaction():

    data = request.get_json(silent=True) or {}

    uid = str(data.get("uid", "")).strip()
    tx_type = str(data.get("type", "")).strip().lower()

    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):

        return jsonify({
            "ok": False,
            "error": "Invalid amount"
        }), 400

    if not uid:

        return jsonify({
            "ok": False,
            "error": "UID is required"
        }), 400

    if tx_type not in ("deposit", "withdraw"):

        return jsonify({
            "ok": False,
            "error": "Type must be deposit or withdraw"
        }), 400

    if amount <= 0:

        return jsonify({
            "ok": False,
            "error": "Amount must be greater than 0"
        }), 400

    conn = get_db()

    user = conn.execute(
        "SELECT uid, balance FROM users WHERE uid=?",
        (uid,)
    ).fetchone()

    if not user:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    if tx_type == "withdraw":

        if float(user["balance"] or 0) < amount:

            conn.close()

            return jsonify({
                "ok": False,
                "error": "Insufficient balance"
            }), 400

    cursor = conn.execute(
        """
        INSERT INTO transactions
        (
            uid,
            type,
            amount,
            status,
            note,
            created_at
        )
        VALUES (?, ?, ?, 'pending', '', ?)
        """,
        (
            uid,
            tx_type,
            amount,
            now()
        )
    )

    transaction_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "transaction_id": transaction_id,
        "status": "pending"
    }), 201


# =========================================================
# APPROVE / REJECT TRANSACTION
# =========================================================

@app.post("/api/admin/transactions/<int:transaction_id>/status")
@admin_required
def admin_transaction_status(transaction_id):

    data = request.get_json(silent=True) or {}

    new_status = str(
        data.get("status", "")
    ).lower().strip()

    if new_status not in ("approved", "rejected"):

        return jsonify({
            "ok": False,
            "error": "Status must be approved or rejected"
        }), 400

    conn = get_db()

    tx = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE id=?
        """,
        (transaction_id,)
    ).fetchone()

    if not tx:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "Transaction not found"
        }), 404

    if tx["status"] != "pending":

        conn.close()

        return jsonify({
            "ok": False,
            "error": "Transaction already processed"
        }), 400

    uid = tx["uid"]
    amount = float(tx["amount"] or 0)
    tx_type = tx["type"]

    user = conn.execute(
        """
        SELECT balance
        FROM users
        WHERE uid=?
        """,
        (uid,)
    ).fetchone()

    if not user:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "User not found"
        }), 404

    # -----------------------------------------------------
    # APPROVED
    # -----------------------------------------------------

    if new_status == "approved":

        balance = float(user["balance"] or 0)

        if tx_type == "deposit":

            balance += amount

        elif tx_type == "withdraw":

            if balance < amount:

                conn.close()

                return jsonify({
                    "ok": False,
                    "error": "User balance is insufficient"
                }), 400

            balance -= amount

        conn.execute(
            """
            UPDATE users
            SET balance=?
            WHERE uid=?
            """,
            (balance, uid)
        )

    # -----------------------------------------------------
    # TRANSACTION STATUS
    # -----------------------------------------------------

    conn.execute(
        """
        UPDATE transactions
        SET status=?
        WHERE id=?
        """,
        (
            new_status,
            transaction_id
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "transaction_id": transaction_id,
        "status": new_status
    })


# =========================================================
# WEBSITE SETTINGS
# =========================================================

@app.get("/api/settings")
def public_settings():

    return jsonify({
        "ok": True,
        "ludo_enabled": get_setting("ludo_enabled") == "true",
        "maintenance": get_setting("maintenance") == "true",
        "announcement": get_setting("announcement"),
        "welcome_bonus": get_setting("welcome_bonus", "0"),
        "jackpot": get_setting("jackpot", "0")
    })


@app.get("/api/admin/settings")
@admin_required
def admin_settings():

    return jsonify({
        "ok": True,
        "settings": {
            "ludo_enabled":
                get_setting("ludo_enabled") == "true",

            "maintenance":
                get_setting("maintenance") == "true",

            "announcement":
                get_setting("announcement"),

            "welcome_bonus":
                get_setting("welcome_bonus", "0"),

            "jackpot":
                get_setting("jackpot", "0")
        }
    })


@app.post("/api/admin/settings")
@admin_required
def update_settings():

    data = request.get_json(silent=True) or {}

    allowed = [
        "ludo_enabled",
        "maintenance",
        "announcement",
        "welcome_bonus",
        "jackpot"
    ]

    for key in allowed:

        if key not in data:
            continue

        value = data[key]

        if key in (
            "ludo_enabled",
            "maintenance"
        ):

            if isinstance(value, bool):
                value = "true" if value else "false"

            else:
                value = str(value).lower()

                if value not in ("true", "false"):
                    return jsonify({
                        "ok": False,
                        "error":
                            f"{key} must be true or false"
                    }), 400

        set_setting(key, value)

    return jsonify({
        "ok": True,
        "message": "Settings updated"
    })


# =========================================================
# LUDO STATUS
# =========================================================

@app.get("/api/ludo/status")
def ludo_status():

    enabled = (
        get_setting("ludo_enabled", "true")
        == "true"
    )

    return jsonify({
        "ok": True,
        "enabled": enabled
    })


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
