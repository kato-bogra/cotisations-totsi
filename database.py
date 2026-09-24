import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "cotisations.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt

def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    expected_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(expected_hash, pw_hash)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # Table Paramètres
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT NOT NULL
    );
    """)

    # Table Utilisateurs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom_prenom TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        telephone TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        date_naissance TEXT,
        photo_url TEXT DEFAULT '',
        role TEXT NOT NULL DEFAULT 'membre', -- 'membre', 'econome', 'tresorier'
        is_verified INTEGER DEFAULT 1,
        verification_token TEXT,
        reset_token TEXT,
        reset_expires TEXT,
        must_change_password INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Table Cotisations
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cotisations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        annee INTEGER NOT NULL,
        montant REAL NOT NULL,
        date_paiement TEXT NOT NULL,
        mode_paiement TEXT NOT NULL, -- 'Espèces', 'Wave', 'Orange Money', 'Moov', 'Virement', 'Autre'
        reference TEXT DEFAULT '',
        note TEXT DEFAULT '',
        enregistre_par_id INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL
    );
    """)

    # Table Dépenses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS depenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titre TEXT NOT NULL,
        description TEXT DEFAULT '',
        montant REAL NOT NULL,
        date_depense TEXT NOT NULL,
        categorie TEXT DEFAULT 'Général',
        justificatif_url TEXT DEFAULT '',
        enregistre_par_id INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL
    );
    """)

    # Table Notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, -- NULL = pour tous les membres
        titre TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT NOT NULL, -- 'cotisation', 'rappel_mensuel', 'anniversaire_j2', 'anniversaire_jour_j', 'systeme'
        data_json TEXT DEFAULT '{}',
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Table Historique des e-mails envoyés / simulés (boîte d'envoi consultable)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emails_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        destinataire TEXT NOT NULL,
        sujet TEXT NOT NULL,
        corps_html TEXT NOT NULL,
        statut TEXT NOT NULL, -- 'simule', 'envoye', 'erreur'
        created_at TEXT NOT NULL
    );
    """)

    # Initialisation des paramètres par défaut
    defaults = {
        "nom_groupe": "Paroisse de Totsi — Fraternité Sacerdotale",
        "montant_annuel": "10000",
        "devise": "FCFA",
        "annee_active": str(date.today().year),
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "paroisse.totsi@gmail.com",
        "smtp_use_tls": "true"
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO parametres (cle, valeur) VALUES (?, ?)", (k, v))

    conn.commit()

    # Seed initial si aucun utilisateur
    cursor.execute("SELECT COUNT(*) as count FROM users")
    count = cursor.fetchone()["count"]
    if count == 0:
        seed_data(cursor)
        conn.commit()

    conn.close()

def seed_data(cursor):
    now = datetime.now().isoformat()
    cur_year = date.today().year

    # 1. Économe principal : Père Jean (mot de passe initial : 4321 ou econome123)
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
    """, ("Père Jean-Baptiste (Économe)", "econome@fraternite.org", "+225 07 01 02 03 04", p_hash, salt, "1980-10-15", "", "econome", now))
    econome_id = cursor.lastrowid

    # 2. Trésorier : Père Paul
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
    """, ("Père Paul-Marie (Trésorier)", "tresorier@fraternite.org", "+225 07 11 22 33 44", p_hash, salt, "1978-05-20", "", "tresorier", now))
    tresorier_id = cursor.lastrowid

    # 3. Confrère 1 : Père Michel (Anniversaire bientôt pour tester les notifications)
    # Mettons son anniversaire à J-2 ou J-0 par rapport à aujourd'hui
    today = date.today()
    bday_michel = f"1985-{today.month:02d}-{(today.day + 2) if today.day <= 26 else today.day:02d}"
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
    """, ("Père Michel N'Guessan", "michel@fraternite.org", "+225 05 55 66 77 88", p_hash, salt, bday_michel, "", "membre", now))
    michel_id = cursor.lastrowid

    # 4. Confrère 2 : Père Joseph (À jour de sa cotisation)
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
    """, ("Père Joseph Kouamé", "joseph@fraternite.org", "+225 01 23 45 67 89", p_hash, salt, "1982-12-08", "", "membre", now))
    joseph_id = cursor.lastrowid

    # 5. Confrère 3 : Père Antoine (Cotisation partielle)
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
    """, ("Père Antoine Koffi", "antoine@fraternite.org", "+225 07 44 55 66 77", p_hash, salt, "1990-03-19", "", "membre", now))
    antoine_id = cursor.lastrowid

    # 6. Confrère 4 : Père Emmanuel (Non encore en règle)
    p_hash, salt = hash_password("4321")
    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
    """, ("Père Emmanuel Yao", "emmanuel@fraternite.org", "+225 05 12 34 56 78", p_hash, salt, f"1987-{today.month:02d}-{today.day:02d}", "", "membre", now))

    # Ajouter des cotisations de démonstration
    # Père Jean (Économe) : 10 000 (Complet)
    cursor.execute("""
    INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
    VALUES (?, ?, 10000, ?, 'Virement', 'VIR-2026-001', 'Cotisation annuelle réglée', ?, ?)
    """, (econome_id, cur_year, f"{cur_year}-01-15", econome_id, now))

    # Père Paul (Trésorier) : 10 000 (Complet)
    cursor.execute("""
    INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
    VALUES (?, ?, 10000, ?, 'Wave', 'WAV-88741', 'Paiement Wave', ?, ?)
    """, (tresorier_id, cur_year, f"{cur_year}-01-20", econome_id, now))

    # Père Joseph : 10 000 (Complet)
    cursor.execute("""
    INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
    VALUES (?, ?, 10000, ?, 'Orange Money', 'OM-55412', 'Paiement intégral', ?, ?)
    """, (joseph_id, cur_year, f"{cur_year}-02-05", econome_id, now))

    # Père Antoine : 5 000 (Partiel - reliquat de 5 000)
    cursor.execute("""
    INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
    VALUES (?, ?, 5000, ?, 'Espèces', 'REC-004', 'Premier acompte', ?, ?)
    """, (antoine_id, cur_year, f"{cur_year}-02-12", econome_id, now))

    # Ajouter quelques dépenses de démonstration
    cursor.execute("""
    INSERT INTO depenses (titre, description, montant, date_depense, categorie, enregistre_par_id, created_at)
    VALUES (?, ?, 8000, ?, 'Solidarité', ?, ?)
    """, ("Soutien confrère malade", "Médicaments et assistance fraternelle", f"{cur_year}-02-18", tresorier_id, now))

    cursor.execute("""
    INSERT INTO depenses (titre, description, montant, date_depense, categorie, enregistre_par_id, created_at)
    VALUES (?, ?, 5000, ?, 'Fonctionnement', ?, ?)
    """, ("Frais de secrétariat & fournitures", "Impressions livrets de prière et reçus", f"{cur_year}-03-01", tresorier_id, now))

    # Notifications initiales
    cursor.execute("""
    INSERT INTO notifications (user_id, titre, message, type, created_at)
    VALUES (NULL, 'Bienvenue sur votre espace Fraternité', 'L application de gestion des cotisations et des anniversaires est désormais opérationnelle.', 'systeme', ?)
    """, (now,))

    cursor.execute("""
    INSERT INTO notifications (user_id, titre, message, type, created_at)
    VALUES (?, 'Cotisation annuelle 2026 enregistrée', 'Votre versement de 10 000 FCFA a été validé. Vous êtes en règle pour cette année. Merci confrère !', 'cotisation', ?)
    """, (joseph_id, now))
