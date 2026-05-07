# online_players.py
"""
Online players — backed by Firebase Realtime Database via the REST API.

Setup (one-time):
  1. Go to https://console.firebase.google.com → create a project.
  2. Build → Realtime Database → Create database (start in test mode).
  3. Copy your database URL (looks like:
       https://my-project-default-rtdb.firebaseio.com)
     and paste it below as FIREBASE_URL.
  4. In the Firebase console → Rules, use while testing:
       { "rules": { ".read": true, ".write": true } }
     Lock down with auth-based rules before going live.
"""

import json
import random
import threading
import urllib.request
import urllib.error

# ── CONFIGURE THIS ────────────────────────────────────────────────────────────
FIREBASE_URL = "https://r-game-956ed-default-rtdb.firebaseio.com"
# ─────────────────────────────────────────────────────────────────────────────

_PLAYERS_URL = f"{FIREBASE_URL}/players.json"
_TIMEOUT = 8  # seconds per HTTP request


# ── Low-level Firebase REST helpers ──────────────────────────────────────────

def _get(url):
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _put(url, data):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=payload, method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT):
        pass


def _patch(url, data):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=payload, method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT):
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def get_online_players(exclude_name=None):
    """Fetch all players from Firebase, sorted by score descending.
    Returns an empty list on network error so the UI never crashes.
    """
    try:
        data = _get(_PLAYERS_URL)
        if not data:
            return []
        players = [
            {"name": k, "score": v.get("score", 0)}
            for k, v in data.items()
            if k != exclude_name
        ]
        return sorted(players, key=lambda p: p["score"], reverse=True)
    except Exception:
        return []


def get_online_players_async(exclude_name=None, callback=None):
    """Fetch players in a background thread, then call callback(players) on
    the Kivy main thread via Clock. Use this from the UI to avoid blocking.
    """
    from kivy.clock import Clock

    def _worker():
        players = get_online_players(exclude_name=exclude_name)
        if callback:
            Clock.schedule_once(lambda dt: callback(players), 0)

    threading.Thread(target=_worker, daemon=True).start()


def is_name_taken(name):
    """Check whether a display name is already in Firebase (case-insensitive)."""
    try:
        data = _get(_PLAYERS_URL)
        if not data:
            return False
        return name.strip().lower() in {k.lower() for k in data}
    except Exception:
        return False


def suggest_name(base_name):
    """Return base_name with a random 4-digit suffix that isn't taken."""
    candidate = f"{base_name}{random.randint(1000, 9999)}"
    while is_name_taken(candidate):
        candidate = f"{base_name}{random.randint(1000, 9999)}"
    return candidate


def register_player(name, score=0):
    """Write a new player entry to Firebase."""
    url = f"{FIREBASE_URL}/players/{name}.json"
    _put(url, {"score": score})


def update_player_score(name, delta):
    """Read the current score from Firebase then increment it."""
    url = f"{FIREBASE_URL}/players/{name}.json"
    try:
        data = _get(url)
        current = data.get("score", 0) if data else 0
        _patch(url, {"score": current + delta})
    except Exception:
        pass
