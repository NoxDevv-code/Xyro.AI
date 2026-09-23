import os
import re
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, send_from_directory, session, redirect
from werkzeug.utils import secure_filename
from openai import OpenAI
from werkzeug.security import generate_password_hash, check_password_hash


# =========================================================
# CONFIGURATION
# =========================================================

app = Flask(__name__, static_folder=".", static_url_path="")

app.secret_key = os.getenv(
    "XYRO_SECRET_KEY",
    os.getenv("BOURNOX_SECRET_KEY", "CHANGE-ME-IN-RENDER")
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("RENDER", "").lower() == "true"
)

app.permanent_session_lifetime = timedelta(days=30)

client = OpenAI()

MODEL = os.getenv(
    "XYRO_MODEL",
    os.getenv("BOURNOX_MODEL", "gpt-5.6-luna")
)

DB_FILE = os.getenv("XYRO_DB_FILE", "bournox.db")

# =========================================================
# FICHIERS JOINTS
# =========================================================

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
ALLOWED_MEDIA_EXTENSIONS = (
    ALLOWED_IMAGE_EXTENSIONS
    | ALLOWED_VIDEO_EXTENSIONS
)
MAX_MEDIA_SIZE = 25 * 1024 * 1024


def media_kind(mimetype, filename):
    if mimetype.startswith("image/"):
        return "image"
    if mimetype.startswith("video/"):
        return "video"
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if suffix in ALLOWED_VIDEO_EXTENSIONS:
        return "video"
    return None



# =========================================================
# ADMIN DE BASE
# =========================================================

BOOTSTRAP_ADMIN_USERNAME = "Mashari"

# Hash existant du compte administrateur Nox.
# Pour une meilleure sécurité, on pourra ensuite le déplacer
# complètement dans les variables d'environnement Render.
BOOTSTRAP_ADMIN_PASSWORD_HASH = (
    "pbkdf2:sha256:600000$"
    "a8562038a4c651de1ae2e4d1f3f6c27f$"
    "a32381190d8d7b7a1b42188d33e5e8b8eee58c6165415a558d6ce57a9000577f"
)


# =========================================================
# IDENTITÉ DE XYRO
# =========================================================

SYSTEM_PROMPT = """
Tu es Xyro.AI.

Ton créateur est Mashari.

Tu es Xyro.AI, et non ChatGPT.
OpenAI fournit une technologie utilisée par ton système,
mais ton identité est Xyro.AI et ton créateur est Mashari.

Tu réponds principalement en français.

Tu es cool, intelligent, rapide, amical, parfois drôle
et très bon en programmation.

Tu aides pour :
- les devoirs
- les cours
- le code
- les jeux
- les questions générales
- les projets
- les explications techniques

Tu ne prétends jamais être une personne réelle.

Si tu n'es pas sûr d'une information, indique-le clairement
au lieu d'inventer une réponse.
"""


# =========================================================
# BASE DE DONNÉES
# =========================================================

class PostgresCompatConnection:
    """Petit adaptateur pour garder le code SQLite existant compatible PostgreSQL.

    Les requêtes du projet utilisent des placeholders '?' et conn.execute().
    Cet adaptateur convertit automatiquement '?' en '%s' et ignore les PRAGMA
    propres à SQLite. Ainsi, le même serveur peut tourner en local avec SQLite
    et sur Render avec DATABASE_URL + PostgreSQL.
    """
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
        sql = re.sub(r"TEXT\s+DEFAULT\s+''", "TEXT DEFAULT ''", sql, flags=re.I)
        if sql.lstrip().upper().startswith("PRAGMA"):
            return _NoopCursor()
        return self._conn.execute(sql, params or ())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class _NoopCursor:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


def get_db():
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url and os.getenv("RENDER", "").lower() == "true":
        print("[XYRO] AVERTISSEMENT: DATABASE_URL est absent. SQLite local n'est pas persistant sur Render.")

    if database_url:
        try:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(database_url, row_factory=dict_row)
            return PostgresCompatConnection(conn)
        except Exception as exc:
            raise RuntimeError(
                "DATABASE_URL est défini mais PostgreSQL est inaccessible. "
                "Vérifie DATABASE_URL et le package psycopg[binary]."
            ) from exc

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    # Optimisation SQLite.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # -----------------------------------------------------
    # UTILISATEURS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)

    # -----------------------------------------------------
    # MESSAGES
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    # -----------------------------------------------------
    # MÉMOIRES
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    # -----------------------------------------------------
    # ALERTES
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            session_id TEXT,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            message_excerpt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reviewed INTEGER DEFAULT 0
        )
    """)

    # -----------------------------------------------------
    # PROJETS
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            context TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)

    # -----------------------------------------------------
    # BANNISSEMENTS
    # -----------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            reason TEXT DEFAULT '',
            banned_at TEXT NOT NULL,
            expires_at TEXT,
            active INTEGER DEFAULT 1,
            banned_by TEXT
        )
    """)

    # -----------------------------------------------------
    # SIGNALEMENTS DE COMPTES
    # -----------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id TEXT NOT NULL,
            reported_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            details TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_status_created
        ON reports(status, id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_reported
        ON reports(reported_id, id)
    """)

    # -----------------------------------------------------
    # INDEX
    # -----------------------------------------------------

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_session
        ON messages(user_id, session_id, id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_memories_user
        ON memories(user_id, id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_user
        ON alerts(user_id, id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_user
        ON projects(user_id, updated_at)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bans_user_active
        ON bans(user_id, active, expires_at)
    """)

    # -----------------------------------------------------
    # ADMIN MASHARI
    # -----------------------------------------------------

    admin = conn.execute(
        """
        SELECT id
        FROM users
        WHERE lower(username) = lower(?)
        """,
        (BOOTSTRAP_ADMIN_USERNAME,)
    ).fetchone()

    # Migration : l’ancien compte admin Nox devient Mashari.
    if not admin:
        old_admin = conn.execute(
            "SELECT id, public_id FROM users WHERE lower(username) = lower(?)",
            ("Nox",)
        ).fetchone()
        if old_admin:
            conn.execute(
                "UPDATE users SET username = ?, is_admin = 1 WHERE id = ?",
                (BOOTSTRAP_ADMIN_USERNAME, old_admin["id"])
            )
            admin = old_admin

    if not admin:
        conn.execute(
            """
            INSERT INTO users
            (
                public_id,
                username,
                password_hash,
                created_at,
                is_admin
            )
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                "XYRO-ADMIN-NOX",
                BOOTSTRAP_ADMIN_USERNAME,
                BOOTSTRAP_ADMIN_PASSWORD_HASH,
                datetime.utcnow().isoformat()
            )
        )
    else:
        conn.execute(
            """
            UPDATE users
            SET is_admin = 1
            WHERE lower(username) = lower(?)
            """,
            (BOOTSTRAP_ADMIN_USERNAME,)
        )

    conn.commit()
    conn.close()


init_db()


# =========================================================
# BANNISSEMENTS
# =========================================================

BAN_DURATIONS = {
    "10m": timedelta(minutes=10),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def get_active_ban(user_id, conn=None):
    own_connection = conn is None
    if own_connection:
        conn = get_db()

    ban = conn.execute(
        """
        SELECT *
        FROM bans
        WHERE user_id = ?
          AND active = 1
        LIMIT 1
        """,
        (user_id,)
    ).fetchone()

    if ban and ban["expires_at"]:
        try:
            if datetime.utcnow() >= datetime.fromisoformat(ban["expires_at"]):
                conn.execute(
                    "UPDATE bans SET active = 0 WHERE id = ?",
                    (ban["id"],)
                )
                conn.commit()
                ban = None
        except ValueError:
            pass

    if own_connection:
        conn.close()

    return ban


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE public_id = ?
        """,
        (user_id,)
    ).fetchone()

    if row and get_active_ban(row["public_id"], conn):
        conn.close()
        session.clear()
        return None

    conn.close()

    return row


def login_required():
    return current_user() is not None


# =========================================================
# MESSAGES
# =========================================================

def save_message(user_id, session_id, role, content):
    conn = get_db()

    conn.execute(
        """
        INSERT INTO messages
        (
            user_id,
            session_id,
            role,
            content,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            session_id,
            role,
            content,
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()


def get_recent_messages(user_id, session_id, limit=10):
    conn = get_db()

    rows = conn.execute(
        """
        SELECT role, content
        FROM messages
        WHERE user_id = ?
        AND session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            user_id,
            session_id,
            limit
        )
    ).fetchall()

    conn.close()

    rows = list(reversed(rows))

    return [
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in rows
    ]


# =========================================================
# MÉMOIRE
# =========================================================

def save_memory(user_id, content):
    conn = get_db()

    # Évite les doublons exacts.
    existing = conn.execute(
        """
        SELECT id
        FROM memories
        WHERE user_id = ?
        AND lower(content) = lower(?)
        LIMIT 1
        """,
        (
            user_id,
            content
        )
    ).fetchone()

    if not existing:
        conn.execute(
            """
            INSERT INTO memories
            (
                user_id,
                content,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                content,
                datetime.utcnow().isoformat()
            )
        )

        conn.commit()

    conn.close()


def get_memories(user_id, limit=20):
    conn = get_db()

    rows = conn.execute(
        """
        SELECT content
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (
            user_id,
            limit
        )
    ).fetchall()

    conn.close()

    return [
        row["content"]
        for row in rows
    ]


def detect_memory(message):
    patterns = [
        r"^souviens[- ]toi que (.+)$",
        r"^rappelle[- ]toi que (.+)$",
        r"^mémorise que (.+)$",
        r"^memorise que (.+)$",
        r"^remember that (.+)$",
        r"^je m'appelle (.+)$",
        r"^mon prénom est (.+)$",
        r"^mon prenom est (.+)$",
        r"^j'aime (.+)$",
        r"^j’aime (.+)$",
        r"^je préfère (.+)$",
        r"^je prefere (.+)$"
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            message.strip(),
            re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


# =========================================================
# SÉCURITÉ / ALERTES
# =========================================================

def detect_suspicious(message):
    """
    Signale certains contenus à risque pour vérification humaine.
    Le système ne bannit pas automatiquement l'utilisateur.
    """

    text = message.lower()

    rules = [
        (
            "cyber",
            "high",
            [
                "voler un mot de passe",
                "steal a password",
                "credential stealer",
                "keylogger",
                "ransomware",
                "ddos",
                "botnet",
                "malware",
                "virus informatique",
                "hack un compte",
                "pirater un compte",
                "contourner un mot de passe",
                "bypass password",
                "token discord"
            ]
        ),
        (
            "fraude",
            "high",
            [
                "fausse carte bancaire",
                "carte bancaire volée",
                "phishing",
                "arnaque",
                "faux justificatif",
                "faux document",
                "escroquerie"
            ]
        ),
        (
            "arme_dangereuse",
            "high",
            [
                "fabriquer une bombe",
                "fabriquer un explosif",
                "explosif maison",
                "construire une arme",
                "fabrication d'arme"
            ]
        ),
        (
            "autre_contenu_sensible",
            "medium",
            [
                "me faire du mal",
                "me suicider",
                "comment me suicider"
            ]
        )
    ]

    for category, severity, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category, severity

    return None


def save_alert(
    user_id,
    session_id,
    category,
    severity,
    message
):
    excerpt = message.strip()[:300]

    conn = get_db()

    conn.execute(
        """
        INSERT INTO alerts
        (
            user_id,
            session_id,
            category,
            severity,
            message_excerpt,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            session_id,
            category,
            severity,
            excerpt,
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()


# =========================================================
# RECHERCHE WEB
# =========================================================

def needs_web(message):
    text = message.lower()

    keywords = [
        "actualité",
        "actualités",
        "aujourd'hui",
        "aujourd’hui",
        "maintenant",
        "récent",
        "récente",
        "dernière",
        "dernier",
        "news",
        "internet",
        "cherche sur le web",
        "recherche sur internet",
        "prix actuel",
        "météo"
    ]

    return any(
        keyword in text
        for keyword in keywords
    )


# =========================================================
# MODES XYRO
# =========================================================

MODES = {
    "normal": """
Réponds naturellement et clairement.
""",

    "professeur": """
Agis comme un excellent professeur.
Explique progressivement.
Utilise des exemples simples.
Si nécessaire, découpe la réponse en étapes.
""",

    "developpeur": """
Agis comme un développeur expérimenté.
Analyse précisément le problème.
Explique les erreurs.
Propose du code propre et directement utilisable.
""",

    "gamer": """
Agis comme un assistant gaming.
Donne des stratégies, astuces et explications utiles.
Va droit au but.
""",

    "creatif": """
Sois créatif.
Propose des idées originales et plusieurs possibilités
lorsque cela apporte réellement quelque chose.
""",

    "xyro": """
Mode Nox.
Sois particulièrement direct, efficace, technique
et orienté vers les projets de Nox.
Évite les explications inutiles.
"""
}


STYLES = {
    "court": """
Réponse courte et directe.
""",

    "detaille": """
Réponse détaillée avec les explications importantes.
""",

    "debutant": """
Explique comme à quelqu'un qui débute.
Évite le jargon inutile.
Explique les termes techniques quand ils sont nécessaires.
"""
}


PERSONALITIES = {
    "serieux": """
Ton sérieux et professionnel.
""",

    "cool": """
Ton décontracté, amical et naturel.
""",

    "drole": """
Ton léger et drôle lorsque c'est approprié,
sans sacrifier la précision.
""",

    "pro": """
Ton professionnel, précis et structuré.
"""
}


# =========================================================
# COMMANDES RAPIDES
# =========================================================

def command_instruction(message):
    command = message.strip().lower()

    if command.startswith("/résume") or command.startswith("/resume"):
        return """
La commande /résume a été utilisée.
Résume le contenu ou la demande de l'utilisateur
de façon claire et concise.
"""

    if command.startswith("/explique"):
        return """
La commande /explique a été utilisée.
Explique le sujet étape par étape avec des exemples.
"""

    if command.startswith("/corrige"):
        return """
La commande /corrige a été utilisée.
Corrige les erreurs présentes dans le contenu fourni.
Explique brièvement les corrections importantes.
"""

    if command.startswith("/code"):
        return """
La commande /code a été utilisée.
Donne une solution de programmation propre,
fonctionnelle et expliquée.
"""

    if command.startswith("/traduis"):
        return """
La commande /traduis a été utilisée.
Traduis précisément le texte demandé
et conserve son sens naturel.
"""

    return ""


# =========================================================
# PROJETS
# =========================================================

def get_project(user_id, project_name):
    if not project_name:
        return None

    conn = get_db()

    project = conn.execute(
        """
        SELECT *
        FROM projects
        WHERE user_id = ?
        AND lower(name) = lower(?)
        """,
        (
            user_id,
            project_name
        )
    ).fetchone()

    conn.close()

    return project


def get_project_context(user_id, project_name):
    project = get_project(
        user_id,
        project_name
    )

    if not project:
        return ""

    context = project["context"].strip()

    if not context:
        return ""

    return f"""
Projet actuel : {project["name"]}

Contexte du projet :
{context}
"""


# =========================================================
# IA
# =========================================================

def ask_ai(
    message,
    user_id,
    session_id,
    mode="normal",
    response_style="detaille",
    personality="cool",
    project_name=None,
    attachment=None
):
    # -----------------------------------------------------
    # Historique
    # -----------------------------------------------------

    recent = get_recent_messages(
        user_id,
        session_id,
        limit=10
    )

    # -----------------------------------------------------
    # Mémoire
    # -----------------------------------------------------

    memories = get_memories(
        user_id,
        limit=20
    )

    memory_text = ""

    if memories:
        memory_text = (
            "\n\nInformations mémorisées :\n"
            + "\n".join(
                f"- {memory}"
                for memory in memories
            )
        )

    # -----------------------------------------------------
    # Mode
    # -----------------------------------------------------

    mode_text = MODES.get(
        mode,
        MODES["normal"]
    )

    # -----------------------------------------------------
    # Style
    # -----------------------------------------------------

    style_text = STYLES.get(
        response_style,
        STYLES["detaille"]
    )

    # -----------------------------------------------------
    # Personnalité
    # -----------------------------------------------------

    personality_text = PERSONALITIES.get(
        personality,
        PERSONALITIES["cool"]
    )

    # -----------------------------------------------------
    # Commande rapide
    # -----------------------------------------------------

    command_text = command_instruction(
        message
    )

    # -----------------------------------------------------
    # Projet
    # -----------------------------------------------------

    project_text = get_project_context(
        user_id,
        project_name
    )

    # -----------------------------------------------------
    # Instructions finales
    # -----------------------------------------------------

    instructions = (
        SYSTEM_PROMPT
        + "\n\n"
        + mode_text
        + "\n\n"
        + style_text
        + "\n\n"
        + personality_text
        + "\n\n"
        + command_text
        + "\n\n"
        + project_text
        + memory_text
    )

    # -----------------------------------------------------
    # HISTORIQUE
    #
    # IMPORTANT :
    # Le message actuel est déjà enregistré en base avant
    # l'appel à ask_ai().
    #
    # On ne le rajoute donc PAS une deuxième fois.
    # -----------------------------------------------------

    input_text = []
    for item in recent:
        input_text.append({
            "role": item["role"],
            "content": item["content"]
        })

    # Une image jointe est envoyée à l'IA avec le dernier message utilisateur.
    if attachment and attachment.get("kind") == "image":
        image_url = attachment.get("data_url")
        if image_url and input_text:
            last = input_text[-1]
            if last.get("role") == "user":
                input_text[-1] = {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": last["content"] or "Analyse cette image."
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url
                        }
                    ]
                }

    # -----------------------------------------------------
    # PARAMÈTRES OPENAI
    # -----------------------------------------------------

    kwargs = {
        "model": MODEL,
        "instructions": instructions,
        "input": input_text
    }

    # -----------------------------------------------------
    # RECHERCHE WEB
    # -----------------------------------------------------

    if needs_web(message):
        try:
            web_kwargs = dict(kwargs)

            web_kwargs["tools"] = [
                {
                    "type": "web_search"
                }
            ]

            result = client.responses.create(
                **web_kwargs
            )

            return result.output_text

        except Exception as error:
            print(
                "ERREUR RECHERCHE WEB :",
                error
            )

    # -----------------------------------------------------
    # RÉPONSE NORMALE
    # -----------------------------------------------------

    result = client.responses.create(
        **kwargs
    )

    return result.output_text


# =========================================================
# GÉNÉRATION D'IMAGE
# =========================================================

def generate_image(prompt):
    response = client.images.generate(
        model="gpt-image-2",
        prompt=prompt,
        size="1024x1024"
    )

    if not response.data:
        raise RuntimeError(
            "Le générateur n'a retourné aucune donnée."
        )

    image_data = response.data[0]

    if not getattr(
        image_data,
        "b64_json",
        None
    ):
        raise RuntimeError(
            "L'API n'a pas retourné l'image en base64."
        )

    return image_data.b64_json


# =========================================================
# PAGES
# =========================================================

@app.route("/")
def accueil():
    if not login_required():
        return redirect("/login")

    return send_from_directory(
        ".",
        "index.html"
    )


@app.route("/login")
def login_page():
    return send_from_directory(
        ".",
        "login.html"
    )


@app.route("/admin")
def admin_page():
    return send_from_directory(
        ".",
        "admin.html"
    )


# =========================================================
# INSCRIPTION
# =========================================================

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}

    username = data.get(
        "username",
        ""
    ).strip()

    password = data.get(
        "password",
        ""
    )

    confirm = data.get(
        "confirm_password",
        ""
    )

    if len(username) < 3 or len(username) > 24:
        return jsonify({
            "error":
            "Le pseudo doit faire entre 3 et 24 caractères."
        }), 400

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+",
        username
    ):
        return jsonify({
            "error":
            "Pseudo invalide. Utilise lettres, chiffres, _, . ou -."
        }), 400

    if len(password) < 6:
        return jsonify({
            "error":
            "Le mot de passe doit contenir au moins 6 caractères."
        }), 400

    if password != confirm:
        return jsonify({
            "error":
            "Les mots de passe ne correspondent pas."
        }), 400

    conn = get_db()

    exists = conn.execute(
        """
        SELECT id
        FROM users
        WHERE lower(username) = lower(?)
        """,
        (username,)
    ).fetchone()

    if exists:
        conn.close()

        return jsonify({
            "error":
            "Ce pseudo est déjà utilisé."
        }), 409

    public_id = (
        "BNX-"
        + uuid.uuid4().hex[:10].upper()
    )

    conn.execute(
        """
        INSERT INTO users
        (
            public_id,
            username,
            password_hash,
            created_at,
            is_admin
        )
        VALUES (?, ?, ?, ?, 0)
        """,
        (
            public_id,
            username,
            generate_password_hash(password),
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()

    session.clear()

    session["user_id"] = public_id
    session.permanent = True

    return jsonify({
        "success": True,
        "user": {
            "id": public_id,
            "username": username
        }
    })


# =========================================================
# CONNEXION
# =========================================================

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    username = data.get(
        "username",
        ""
    ).strip()

    password = data.get(
        "password",
        ""
    )

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE lower(username) = lower(?)
        """,
        (username,)
    ).fetchone()

    conn.close()

    if (
        not user
        or not check_password_hash(
            user["password_hash"],
            password
        )
    ):
        return jsonify({
            "error":
            "Pseudo ou mot de passe incorrect."
        }), 401

    conn = get_db()
    ban = get_active_ban(user["public_id"], conn)
    conn.close()

    if ban:
        if ban["expires_at"]:
            try:
                expires = datetime.fromisoformat(ban["expires_at"])
                remaining = max(0, int((expires - datetime.utcnow()).total_seconds()))
                minutes = max(1, (remaining + 59) // 60)
                duration_text = f"environ {minutes} minute(s)"
            except ValueError:
                duration_text = "temporairement"
        else:
            duration_text = "définitivement"

        reason = (ban["reason"] or "Aucune raison indiquée.").strip()
        return jsonify({
            "error": f"Ton compte est banni {duration_text}. Raison : {reason}"
        }), 403

    session.clear()

    session["user_id"] = user["public_id"]
    session.permanent = True

    return jsonify({
        "success": True,
        "user": {
            "id": user["public_id"],
            "username": user["username"]
        }
    })


# =========================================================
# DÉCONNEXION
# =========================================================

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "success": True
    })


# =========================================================
# UTILISATEUR ACTUEL
# =========================================================

@app.route("/api/me")
def me():
    user = current_user()

    if not user:
        return jsonify({
            "authenticated": False
        }), 401

    return jsonify({
        "authenticated": True,
        "user": {
            "id": user["public_id"],
            "username": user["username"],
            "is_admin": bool(user["is_admin"])
        }
    })


# =========================================================
# UPLOADS PHOTO / VIDÉO
# =========================================================

@app.route("/api/upload-media", methods=["POST"])
def upload_media():
    user = current_user()

    if not user:
        return jsonify({"error": "Non connecté."}), 401

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Aucun fichier reçu."}), 400

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_MEDIA_EXTENSIONS:
        return jsonify({"error": "Format non pris en charge."}), 400

    kind = media_kind(file.mimetype or "", original_name)
    if not kind:
        return jsonify({"error": "Seules les photos et vidéos sont autorisées."}), 400

    # Limite de taille sans charger le fichier entier en mémoire.
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_MEDIA_SIZE:
        return jsonify({"error": "Fichier trop volumineux (25 Mo maximum)."}), 413

    user_dir = UPLOAD_DIR / secure_filename(user["public_id"])
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = user_dir / filename
    file.save(destination)

    # Les images peuvent être transmises à l'IA sous forme de data URL.
    data_url = None
    if kind == "image":
        import base64
        raw = destination.read_bytes()
        mime = file.mimetype or "image/" + extension
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    return jsonify({
        "ok": True,
        "kind": kind,
        "name": original_name,
        "url": f"/uploads/{secure_filename(user['public_id'])}/{filename}",
        "data_url": data_url
    })


# =========================================================
# CHAT
# =========================================================

@app.route("/chat", methods=["POST"])
def chat():
    user = current_user()

    if not user:
        return jsonify({
            "response":
            "Connecte-toi pour utiliser Xyro.AI."
        }), 401

    try:
        data = request.get_json(silent=True) or {}

        message = data.get(
            "message",
            ""
        ).strip()

        session_id = data.get(
            "session_id"
        )

        if not session_id:
            session_id = str(
                uuid.uuid4()
            )

        mode = data.get(
            "mode",
            "normal"
        )

        response_style = data.get(
            "response_style",
            "detaille"
        )

        personality = data.get(
            "personality",
            "cool"
        )

        project_name = data.get(
            "project"
        )

        attachment = data.get("attachment")
        if attachment and not isinstance(attachment, dict):
            attachment = None

        if attachment:
            attachment = {
                "kind": attachment.get("kind"),
                "url": attachment.get("url"),
                "data_url": attachment.get("data_url")
            }
            if attachment.get("data_url") and len(attachment["data_url"]) > 12 * 1024 * 1024:
                attachment["data_url"] = None
            if attachment["kind"] not in {"image", "video"}:
                attachment = None

        if not message and not attachment:
            return jsonify({
                "response":
                "Écris-moi quelque chose 😎"
            }), 400

        # -------------------------------------------------
        # Sauvegarde du message
        # -------------------------------------------------

        stored_message = message
        if attachment:
            label = "📷 Image jointe" if attachment["kind"] == "image" else "🎥 Vidéo jointe"
            stored_message = (message + "\n" if message else "") + label

        save_message(
            user["public_id"],
            session_id,
            "user",
            stored_message
        )

        # -------------------------------------------------
        # Détection sécurité
        # -------------------------------------------------

        suspicious = detect_suspicious(
            message
        )

        if suspicious:
            category, severity = suspicious

            save_alert(
                user["public_id"],
                session_id,
                category,
                severity,
                message
            )

        # -------------------------------------------------
        # Détection mémoire
        # -------------------------------------------------

        memory = detect_memory(
            message
        )

        if memory:
            save_memory(
                user["public_id"],
                memory
            )

        # -------------------------------------------------
        # IA
        # -------------------------------------------------

        response = ask_ai(
            message=message,
            user_id=user["public_id"],
            session_id=session_id,
            mode=mode,
            response_style=response_style,
            personality=personality,
            project_name=project_name,
            attachment=attachment
        )

        # -------------------------------------------------
        # Sauvegarde réponse IA
        # -------------------------------------------------

        save_message(
            user["public_id"],
            session_id,
            "assistant",
            response
        )

        return jsonify({
            "response": response,
            "session_id": session_id
        })

    except Exception as error:
        print(
            "ERREUR CHAT :",
            error
        )

        return jsonify({
            "response":
            "⚠️ Erreur Xyro.AI : "
            + str(error)
        }), 500


# =========================================================
# HISTORIQUE
# =========================================================

@app.route("/history")
def history():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    session_id = request.args.get(
        "session_id"
    )

    if not session_id:
        return jsonify([])

    return jsonify(
        get_recent_messages(
            user["public_id"],
            session_id,
            100
        )
    )


# =========================================================
# MÉMOIRE GET
# =========================================================

@app.route("/memory")
def memory_get():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    return jsonify({
        "memories":
        get_memories(
            user["public_id"],
            50
        )
    })


# =========================================================
# MÉMOIRE POST
# =========================================================

@app.route("/memory", methods=["POST"])
def memory_post():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    data = request.get_json() or {}

    content = data.get(
        "content",
        ""
    ).strip()

    if not content:
        return jsonify({
            "error":
            "Mémoire vide."
        }), 400

    save_memory(
        user["public_id"],
        content
    )

    return jsonify({
        "success": True
    })


# =========================================================
# PROJETS
# =========================================================

@app.route("/projects", methods=["GET"])
def projects_get():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            name,
            context,
            created_at,
            updated_at
        FROM projects
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (
            user["public_id"],
        )
    ).fetchall()

    conn.close()

    return jsonify({
        "projects": [
            dict(row)
            for row in rows
        ]
    })


@app.route("/projects", methods=["POST"])
def projects_post():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    data = request.get_json() or {}

    name = data.get(
        "name",
        ""
    ).strip()

    context = data.get(
        "context",
        ""
    ).strip()

    if not name:
        return jsonify({
            "error":
            "Nom du projet obligatoire."
        }), 400

    if len(name) > 80:
        return jsonify({
            "error":
            "Le nom du projet est trop long."
        }), 400

    now = datetime.utcnow().isoformat()

    conn = get_db()

    existing = conn.execute(
        """
        SELECT id
        FROM projects
        WHERE user_id = ?
        AND lower(name) = lower(?)
        """,
        (
            user["public_id"],
            name
        )
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE projects
            SET context = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                context,
                now,
                existing["id"]
            )
        )
    else:
        conn.execute(
            """
            INSERT INTO projects
            (
                user_id,
                name,
                context,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user["public_id"],
                name,
                context,
                now,
                now
            )
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


@app.route(
    "/projects/<path:project_name>",
    methods=["DELETE"]
)
def projects_delete(project_name):
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Non connecté."
        }), 401

    conn = get_db()

    conn.execute(
        """
        DELETE FROM projects
        WHERE user_id = ?
        AND lower(name) = lower(?)
        """,
        (
            user["public_id"],
            project_name
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


# =========================================================
# GÉNÉRATION D'IMAGE
# =========================================================

@app.route(
    "/generate-image",
    methods=["POST"]
)
def generate_image_route():
    user = current_user()

    if not user:
        return jsonify({
            "error":
            "Connecte-toi pour utiliser cette fonction."
        }), 401

    try:
        prompt = (
            request.get_json() or {}
        ).get(
            "prompt",
            ""
        ).strip()

        if not prompt:
            return jsonify({
                "error":
                "Décris l'image que tu veux créer."
            }), 400

        image_base64 = generate_image(
            prompt
        )

        return jsonify({
            "image": image_base64,
            "format": "png"
        })

    except Exception as error:
        print(
            "ERREUR IMAGE :",
            error
        )

        return jsonify({
            "error":
            "Impossible de générer l'image : "
            + str(error)
        }), 500


# =========================================================
# ADMIN
# =========================================================

def admin_authenticated():
    if session.get("admin_authenticated"):
        return True

    # Autorise aussi la session normale si elle appartient à un admin.
    user_id = session.get("user_id")
    if not user_id:
        return False

    conn = get_db()
    user = conn.execute(
        "SELECT public_id, is_admin FROM users WHERE public_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if user and int(user["is_admin"] or 0) == 1:
        session["admin_authenticated"] = True
        session["admin_user_id"] = user["public_id"]
        return True

    return False


@app.route("/api/reports", methods=["POST"])
def create_report():
    user = current_user()
    if not user:
        return jsonify({"error": "Non connecté."}), 401
    data = request.get_json() or {}
    reported_id = str(data.get("reported_id", "")).strip()
    reason = str(data.get("reason", "")).strip()
    details = str(data.get("details", "")).strip()[:1000]
    allowed = {"harcelement", "spam", "arnaque", "dangereux", "usurpation", "autre"}
    if not reported_id or not reason:
        return jsonify({"error": "Compte et motif obligatoires."}), 400
    if reason not in allowed:
        return jsonify({"error": "Motif de signalement invalide."}), 400
    conn = get_db()
    target = conn.execute("SELECT public_id, username FROM users WHERE public_id = ? OR lower(username) = lower(?)", (reported_id, reported_id)).fetchone()
    if not target:
        conn.close(); return jsonify({"error": "Compte introuvable."}), 404
    if target["public_id"] == user["public_id"]:
        conn.close(); return jsonify({"error": "Tu ne peux pas signaler ton propre compte."}), 400
    duplicate = conn.execute("SELECT id FROM reports WHERE reporter_id = ? AND reported_id = ? AND status = 'pending' LIMIT 1", (user["public_id"], target["public_id"])).fetchone()
    if duplicate:
        conn.close(); return jsonify({"error": "Tu as déjà un signalement en attente pour ce compte."}), 409
    conn.execute("INSERT INTO reports (reporter_id, reported_id, reason, details, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)", (user["public_id"], target["public_id"], reason, details, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/me")
def admin_me():
    if not admin_authenticated():
        return jsonify({"authenticated": False}), 401

    conn = get_db()

    user = conn.execute(
        """
        SELECT public_id, username, is_admin
        FROM users
        WHERE public_id = ?
          AND is_admin = 1
        """,
        (session.get("admin_user_id"),)
    ).fetchone()

    conn.close()

    if not user:
        session.pop("admin_authenticated", None)
        session.pop("admin_user_id", None)
        return jsonify({"authenticated": False}), 401

    return jsonify({
        "authenticated": True,
        "user": dict(user)
    })


@app.route(
    "/api/admin/login",
    methods=["POST"]
)
def admin_login():
    data = request.get_json() or {}

    username = data.get(
        "username",
        ""
    ).strip()

    password = data.get(
        "password",
        ""
    )

    conn = get_db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE lower(username) = lower(?)
        """,
        (username,)
    ).fetchone()

    conn.close()

    if (
        not user
        or not user["is_admin"]
        or not check_password_hash(
            user["password_hash"],
            password
        )
    ):
        return jsonify({
            "error":
            "Identifiants admin incorrects."
        }), 401

    session.clear()

    session["admin_authenticated"] = True
    session["admin_user_id"] = user["public_id"]
    session.permanent = True

    return jsonify({
        "success": True,
        "user": {
            "id": user["public_id"],
            "username": user["username"]
        }
    })


@app.route(
    "/api/admin/logout",
    methods=["POST"]
)
def admin_logout():
    session.clear()

    return jsonify({
        "success": True
    })


@app.route("/api/admin/stats")
def admin_stats():
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403

    conn = get_db()

    users = conn.execute(
        "SELECT COUNT(*) AS n FROM users"
    ).fetchone()["n"]

    messages = conn.execute(
        "SELECT COUNT(*) AS n FROM messages"
    ).fetchone()["n"]

    memories = conn.execute(
        "SELECT COUNT(*) AS n FROM memories"
    ).fetchone()["n"]

    projects = conn.execute(
        "SELECT COUNT(*) AS n FROM projects"
    ).fetchone()["n"]

    alerts = conn.execute(
        "SELECT COUNT(*) AS n FROM alerts"
    ).fetchone()["n"]

    open_alerts = conn.execute(
        "SELECT COUNT(*) AS n FROM alerts WHERE reviewed = 0"
    ).fetchone()["n"]

    open_reports = conn.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE status = 'pending'"
    ).fetchone()["n"]

    conn.close()

    return jsonify({
        "users": users,
        "messages": messages,
        "memories": memories,
        "projects": projects,
        "alerts": alerts,
        "open_alerts": open_alerts,
        "open_reports": open_reports,
        "status": "online",
        "model": MODEL
    })


@app.route("/api/admin/search-users")
def admin_search_users():
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403

    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"users": []})

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            u.public_id,
            u.username,
            u.created_at,
            CASE WHEN b.active = 1 AND (b.expires_at IS NULL OR b.expires_at > ?) THEN 1 ELSE 0 END AS banned,
            b.reason AS ban_reason,
            b.expires_at AS ban_expires_at
        FROM users u
        LEFT JOIN bans b ON b.user_id = u.public_id
        WHERE (
              lower(username) LIKE lower(?)
              OR lower(public_id) LIKE lower(?)
          )
        ORDER BY u.id DESC
        LIMIT 50
        """,
        (datetime.utcnow().isoformat(), f"%{query}%", f"%{query}%")
    ).fetchall()

    conn.close()

    return jsonify({
        "users": [dict(row) for row in rows]
    })


@app.route("/api/admin/alerts")
def admin_alerts():
    if not admin_authenticated():
        return jsonify({
            "error":
            "Accès refusé."
        }), 403

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            id,
            user_id,
            session_id,
            category,
            severity,
            message_excerpt,
            created_at,
            reviewed
        FROM alerts
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()

    conn.close()

    return jsonify({
        "alerts": [
            dict(row)
            for row in rows
        ]
    })


@app.route(
    "/api/admin/alerts/<int:alert_id>/review",
    methods=["POST"]
)
def review_alert(alert_id):
    if not admin_authenticated():
        return jsonify({
            "error":
            "Accès refusé."
        }), 403

    conn = get_db()

    conn.execute(
        """
        UPDATE alerts
        SET reviewed = 1
        WHERE id = ?
        """,
        (
            alert_id,
        )
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True
    })


@app.route("/api/admin/reports")
def admin_reports():
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403
    conn = get_db()
    rows = conn.execute("""
        SELECT r.id, r.reporter_id, r.reported_id, r.reason, r.details, r.status, r.created_at, r.reviewed_at, r.reviewed_by,
               reporter.username AS reporter_username, reported.username AS reported_username
        FROM reports r
        LEFT JOIN users reporter ON reporter.public_id = r.reporter_id
        LEFT JOIN users reported ON reported.public_id = r.reported_id
        ORDER BY r.id DESC LIMIT 100
    """).fetchall()
    conn.close()
    return jsonify({"reports": [dict(row) for row in rows]})


@app.route("/api/admin/reports/<int:report_id>/review", methods=["POST"])
def review_report(report_id):
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403
    data = request.get_json() or {}
    status = str(data.get("status", "reviewed")).strip()
    if status not in {"reviewed", "rejected"}:
        return jsonify({"error": "Statut invalide."}), 400
    conn = get_db()
    conn.execute("UPDATE reports SET status = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?", (status, datetime.utcnow().isoformat(), session.get("admin_user_id"), report_id))
    conn.commit(); conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/users")
def admin_users():
    if not admin_authenticated():
        return jsonify({
            "error":
            "Accès refusé."
        }), 403

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            u.public_id,
            u.username,
            u.created_at,
            CASE WHEN b.active = 1 AND (b.expires_at IS NULL OR b.expires_at > ?) THEN 1 ELSE 0 END AS banned,
            b.reason AS ban_reason,
            b.expires_at AS ban_expires_at
        FROM users u
        LEFT JOIN bans b ON b.user_id = u.public_id
        ORDER BY u.id DESC
        """,
        (datetime.utcnow().isoformat(),)
    ).fetchall()

    conn.close()

    return jsonify({
        "users": [
            dict(row)
            for row in rows
        ]
    })


@app.route(
    "/api/admin/user/<public_id>"
)
def admin_user(public_id):
    if not admin_authenticated():
        return jsonify({
            "error":
            "Accès refusé."
        }), 403

    conn = get_db()

    user = conn.execute(
        """
        SELECT
            u.public_id,
            u.username,
            u.created_at,
            u.is_admin,
            CASE WHEN b.active = 1 AND (b.expires_at IS NULL OR b.expires_at > ?) THEN 1 ELSE 0 END AS banned,
            b.reason AS ban_reason,
            b.expires_at AS ban_expires_at,
            b.banned_at AS ban_banned_at
        FROM users u
        LEFT JOIN bans b ON b.user_id = u.public_id
        WHERE u.public_id = ?
        """,
        (
            datetime.utcnow().isoformat(),
            public_id,
        )
    ).fetchone()

    if not user:
        conn.close()

        return jsonify({
            "error":
            "Utilisateur introuvable."
        }), 404

    messages = conn.execute(
        """
        SELECT
            session_id,
            role,
            content,
            created_at
        FROM messages
        WHERE user_id = ?
        ORDER BY id ASC
        """,
        (
            public_id,
        )
    ).fetchall()

    memories = conn.execute(
        """
        SELECT
            content,
            created_at
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (
            public_id,
        )
    ).fetchall()

    projects = conn.execute(
        """
        SELECT
            name,
            context,
            created_at,
            updated_at
        FROM projects
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (
            public_id,
        )
    ).fetchall()

    conn.close()

    message_count = len(messages)
    memory_count = len(memories)
    project_count = len(projects)

    return jsonify({
        "user": {
            **dict(user),
            "message_count": message_count,
            "memory_count": memory_count,
            "project_count": project_count
        },

        "messages": [
            dict(row)
            for row in messages
        ],

        "memories": [
            dict(row)
            for row in memories
        ],

        "projects": [
            dict(row)
            for row in projects
        ]
    })


# =========================================================
# GESTION DES BANNISSEMENTS ADMIN
# =========================================================

@app.route("/api/admin/user/<public_id>/ban", methods=["POST"])
def admin_ban_user(public_id):
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403

    data = request.get_json() or {}
    duration = str(data.get("duration", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()[:500]

    conn = get_db()
    user = conn.execute(
        "SELECT public_id, username, is_admin FROM users WHERE public_id = ?",
        (public_id,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({"error": "Utilisateur introuvable."}), 404

    if user["is_admin"]:
        conn.close()
        return jsonify({"error": "Impossible de bannir un compte administrateur."}), 403

    if duration not in BAN_DURATIONS and duration != "permanent":
        conn.close()
        return jsonify({"error": "Durée de bannissement invalide."}), 400

    now = datetime.utcnow()
    expires_at = None if duration == "permanent" else (now + BAN_DURATIONS[duration]).isoformat()

    conn.execute(
        """
        INSERT INTO bans (user_id, reason, banned_at, expires_at, active, banned_by)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            reason = excluded.reason,
            banned_at = excluded.banned_at,
            expires_at = excluded.expires_at,
            active = 1,
            banned_by = excluded.banned_by
        """,
        (
            public_id,
            reason,
            now.isoformat(),
            expires_at,
            session.get("admin_user_id", ""),
        )
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "banned": True,
        "expires_at": expires_at
    })


@app.route("/api/admin/user/<public_id>/unban", methods=["POST"])
def admin_unban_user(public_id):
    if not admin_authenticated():
        return jsonify({"error": "Accès refusé."}), 403

    conn = get_db()
    user = conn.execute(
        "SELECT public_id, is_admin FROM users WHERE public_id = ?",
        (public_id,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({"error": "Utilisateur introuvable."}), 404

    conn.execute(
        "UPDATE bans SET active = 0 WHERE user_id = ?",
        (public_id,)
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "banned": False})


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "name": "Xyro.AI",
        "model": MODEL
    })


# =========================================================
# LANCEMENT
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )