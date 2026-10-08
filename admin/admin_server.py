import os
import json
import secrets
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import firebase_admin
    from firebase_admin import credentials, db
except Exception:
    firebase_admin = None
    credentials = None
    db = None

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET_KEY", "change-this-secret")

FIREBASE_DB_URL = os.environ.get(
    "FIREBASE_DATABASE_URL",
    "https://ludu-369-default-rtdb.asia-southeast1.firebasedatabase.app"
)
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")

_sessions = set()
_firebase_ready = False


def init_firebase():
    global _firebase_ready
    if firebase_admin is None:
        return
    if firebase_admin._apps:
        _firebase_ready = True
        return

    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return

    raw = FIREBASE_SERVICE_ACCOUNT_JSON.strip()
    try:
        info = json.loads(raw)
    except Exception:
        # Also allow a path to a JSON service-account file.
        p = Path(raw)
        if not p.is_file():
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON or a valid file path")
        info = json.loads(p.read_text(encoding="utf-8"))

    cred = credentials.Certificate(info)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
    _firebase_ready = True


try:
    init_firebase()
except Exception as e:
    print("Firebase init failed:", e)


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Admin-Token", "")
        if not token or token not in _sessions:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def firebase_required():
    if not _firebase_ready:
        return jsonify({
            "ok": False,
            "error": "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_JSON and FIREBASE_DATABASE_URL."
        }), 503
    return None


def rooms_ref():
    return db.reference("rooms")


def clean_room(code, room):
    room = room or {}
    slots = room.get("slots") or {}
    players = []
    for seat in ("blue", "red", "green", "yellow"):
        s = slots.get(seat)
        if isinstance(s, dict) and s.get("uid"):
            players.append({
                "seat": seat,
                "uid": s.get("uid"),
                "name": s.get("name", "Player"),
                "avatar": s.get("avatar", "👤"),
            })
    game = room.get("game") or {}
    return {
        "roomCode": code,
        "mode": room.get("mode"),
        "amount": room.get("amount", 0),
        "pool": room.get("pool", 0),
        "fee": room.get("fee", 0),
        "prize": room.get("prize", 0),
        "players": room.get("players", len(players)),
        "status": room.get("status"),
        "started": bool(room.get("started")),
        "isPrivate": bool(room.get("isPrivate")),
        "adminUid": room.get("adminUid"),
        "adminName": room.get("adminName"),
        "createdAt": room.get("createdAt"),
        "expiresAt": room.get("expiresAt"),
        "playerList": players,
        "game": game,
    }


@app.get("/")
def home():
    return send_from_directory(BASE_DIR / "admin", "dashboard.html")


@app.get("/login")
def login_page():
    return send_from_directory(BASE_DIR / "admin", "login.html")


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "BDXbet Ludo Admin",
        "firebaseAdmin": _firebase_ready
    }


@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))

    if username != ADMIN_USERNAME:
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401

    valid = False
    if ADMIN_PASSWORD_HASH:
        valid = check_password_hash(ADMIN_PASSWORD_HASH, password)
    else:
        valid = secrets.compare_digest(password, ADMIN_PASSWORD)

    if not valid:
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401

    token = secrets.token_urlsafe(32)
    _sessions.add(token)
    return jsonify({"ok": True, "token": token})


@app.post("/api/admin/logout")
@require_admin
def admin_logout():
    token = request.headers.get("X-Admin-Token", "")
    _sessions.discard(token)
    return jsonify({"ok": True})


@app.get("/api/ludo/rooms")
@require_admin
def ludo_rooms():
    err = firebase_required()
    if err:
        return err
    data = rooms_ref().get() or {}
    if not isinstance(data, dict):
        data = {}
    rooms = [clean_room(code, room) for code, room in data.items()]
    rooms.sort(key=lambda x: x.get("createdAt") or 0, reverse=True)
    return jsonify({"ok": True, "rooms": rooms})


@app.get("/api/ludo/rooms/<room_code>")
@require_admin
def ludo_room(room_code):
    err = firebase_required()
    if err:
        return err
    room = rooms_ref().child(room_code).get()
    if room is None:
        return jsonify({"ok": False, "error": "Room not found"}), 404
    return jsonify({"ok": True, "room": clean_room(room_code, room)})


@app.patch("/api/ludo/rooms/<room_code>")
@require_admin
def update_room(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    allowed = {"status", "started", "isPrivate", "amount", "pool", "fee", "prize"}
    patch = {k: data[k] for k in allowed if k in data}
    if not patch:
        return jsonify({"ok": False, "error": "No supported fields"}), 400
    rooms_ref().child(room_code).update(patch)
    return jsonify({"ok": True})


@app.delete("/api/ludo/rooms/<room_code>")
@require_admin
def delete_room(room_code):
    err = firebase_required()
    if err:
        return err
    rooms_ref().child(room_code).delete()
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/start")
@require_admin
def force_start(room_code):
    err = firebase_required()
    if err:
        return err
    ref = rooms_ref().child(room_code)
    room = ref.get()
    if not room:
        return jsonify({"ok": False, "error": "Room not found"}), 404
    ref.update({"started": True, "status": "playing"})
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/end")
@require_admin
def force_end(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    ref = rooms_ref().child(room_code)
    room = ref.get()
    if not room:
        return jsonify({"ok": False, "error": "Room not found"}), 404
    winner = data.get("winner")
    game_ref = ref.child("game")
    game = game_ref.get() or {}
    if winner:
        game["winner"] = winner
    game["adminEnded"] = True
    game["adminEndedAt"] = int(__import__("time").time() * 1000)
    game_ref.set(game)
    ref.update({"status": "ended", "started": True})
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/pause")
@require_admin
def pause_room(room_code):
    err = firebase_required()
    if err:
        return err
    rooms_ref().child(room_code).child("adminControl").set({
        "action": "pause",
        "at": int(__import__("time").time() * 1000)
    })
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/resume")
@require_admin
def resume_room(room_code):
    err = firebase_required()
    if err:
        return err
    rooms_ref().child(room_code).child("adminControl").set({
        "action": "resume",
        "at": int(__import__("time").time() * 1000)
    })
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/kick")
@require_admin
def kick_player(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    seat = str(data.get("seat", "")).lower()
    if seat not in ("blue", "red", "green", "yellow"):
        return jsonify({"ok": False, "error": "Invalid seat"}), 400

    ref = rooms_ref().child(room_code)
    room = ref.get()
    if not room:
        return jsonify({"ok": False, "error": "Room not found"}), 404

    # Waiting-room kick: remove the seat directly.
    if not room.get("started"):
        ref.child("slots").child(seat).delete()
    else:
        # Active-match kick: notify that exact client and mark the seat as removed.
        ref.child("adminControl").set({
            "action": "kick",
            "seat": seat,
            "at": int(__import__("time").time() * 1000)
        })
        ref.child("slots").child(seat).delete()

    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/turn")
@require_admin
def set_turn(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    seat = str(data.get("seat", "")).lower()
    if seat not in ("blue", "red", "green", "yellow"):
        return jsonify({"ok": False, "error": "Invalid seat"}), 400
    ref = rooms_ref().child(room_code).child("game")
    game = ref.get() or {}
    game["turn"] = seat
    game["turnState"] = "rolling"
    game["turnStartedAt"] = int(__import__("time").time() * 1000)
    game["consecutiveSixes"] = 0
    game["turnSeq"] = int(game.get("turnSeq", 0)) + 1
    ref.set(game)
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/dice")
@require_admin
def set_dice(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    value = int(data.get("value", 0))
    seat = str(data.get("seat", "")).lower()
    if value < 1 or value > 6:
        return jsonify({"ok": False, "error": "Dice must be 1-6"}), 400
    if seat not in ("blue", "red", "green", "yellow"):
        return jsonify({"ok": False, "error": "Invalid seat"}), 400

    ref = rooms_ref().child(room_code).child("game")
    game = ref.get() or {}
    game["dice"] = {
        "value": value,
        "seq": int((game.get("dice") or {}).get("seq", 0)) + 1,
        "bySeat": seat,
        "at": int(__import__("time").time() * 1000)
    }
    game["turn"] = seat
    game["turnState"] = "moving"
    ref.set(game)
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/pawn")
@require_admin
def set_pawn(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    seat = str(data.get("seat", "")).lower()
    index = int(data.get("index", -1))
    step = int(data.get("step", -1))
    if seat not in ("blue", "red", "green", "yellow"):
        return jsonify({"ok": False, "error": "Invalid seat"}), 400
    if index < 0 or index > 3:
        return jsonify({"ok": False, "error": "Pawn index must be 0-3"}), 400
    if step < -1 or step > 56:
        return jsonify({"ok": False, "error": "Pawn step must be -1 to 56"}), 400

    ref = rooms_ref().child(room_code).child("game")
    game = ref.get() or {}
    pawns = game.get("pawns") or {}
    arr = list(pawns.get(seat) or [-1, -1, -1, -1])
    while len(arr) < 4:
        arr.append(-1)
    arr[index] = step
    pawns[seat] = arr[:4]
    game["pawns"] = pawns
    game["lastMove"] = {
        "seq": int((game.get("lastMove") or {}).get("seq", 0)) + 1,
        "seat": seat,
        "pawnIndex": index,
        "fromStep": step,
        "toStep": step,
        "capture": None,
        "admin": True
    }
    ref.set(game)
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/winner")
@require_admin
def set_winner(room_code):
    err = firebase_required()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    winner = str(data.get("seat", "")).lower()
    if winner not in ("blue", "red", "green", "yellow"):
        return jsonify({"ok": False, "error": "Invalid winner"}), 400
    ref = rooms_ref().child(room_code).child("game")
    game = ref.get() or {}
    game["winner"] = winner
    game["adminWinner"] = True
    game["adminWinnerAt"] = int(__import__("time").time() * 1000)
    ref.set(game)
    return jsonify({"ok": True})


@app.post("/api/ludo/rooms/<room_code>/reset-game")
@require_admin
def reset_game(room_code):
    err = firebase_required()
    if err:
        return err
    ref = rooms_ref().child(room_code).child("game")
    game = ref.get() or {}
    colors = []
    room = rooms_ref().child(room_code).get() or {}
    mode = room.get("mode")
    colors = ["blue", "green"] if mode == "1v1" else ["blue", "red", "green", "yellow"]
    game["turn"] = colors[0]
    game["turnState"] = "rolling"
    game["turnStartedAt"] = int(__import__("time").time() * 1000)
    game["dice"] = {"value": 0, "seq": int((game.get("dice") or {}).get("seq", 0)) + 1, "bySeat": None, "at": 0}
    game["lastMove"] = {"seq": int((game.get("lastMove") or {}).get("seq", 0)) + 1}
    game["consecutiveSixes"] = 0
    game["winner"] = None
    game["adminEnded"] = False
    game["pawns"] = {c: [-1, -1, -1, -1] for c in colors}
    ref.set(game)
    rooms_ref().child(room_code).update({"status": "playing", "started": True})
    return jsonify({"ok": True})


@app.get("/<path:filename>")
def static_files(filename):
    p = BASE_DIR / filename
    if p.is_file():
        return send_from_directory(BASE_DIR, filename)
    return "Not Found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
