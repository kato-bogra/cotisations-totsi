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
        type TEXT NOT NULL, -- 'cotisation', 'rappel_mensuel', 'anniversaire_j2', 'anniversaire_jour_j', 'systeme', 'diffusion'
        data_json TEXT DEFAULT '{}',
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    # Table Diffusions d'annonces à tous les membres (apparaîtra sur l'écran de chacun)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diffusions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auteur_id INTEGER REFERENCES users(id),
        auteur_nom TEXT NOT NULL,
        titre TEXT NOT NULL,
        message TEXT NOT NULL,
        urgence TEXT NOT NULL DEFAULT 'normal', -- 'normal', 'important', 'urgent'
        is_active INTEGER DEFAULT 1,
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

    # Synchroniser les comptes officiels (Eric Badabadi comme seul Économe, et Kato Espoir)
    sync_initial_accounts(conn)

    conn.close()

def sync_initial_accounts(conn):
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cur_year = date.today().year

    # 1. Économe officiel unique : Eric Badabadi
    # Mot de passe : Badabadi2026!
    p_hash_eric, salt_eric = hash_password("Badabadi2026!")
    cursor.execute("SELECT id FROM users WHERE email = 'ericbadabadi@gmail.com' COLLATE NOCASE")
    row_eric = cursor.fetchone()
    if row_eric:
        cursor.execute("""
        UPDATE users 
        SET nom_prenom = 'Eric Badabadi (Économe)', 
            role = 'econome', 
            password_hash = ?, 
            salt = ?, 
            is_verified = 1,
            telephone = CASE WHEN telephone = '' THEN '+228 90 00 00 01' ELSE telephone END
        WHERE id = ?
        """, (p_hash_eric, salt_eric, row_eric["id"]))
        eric_id = row_eric["id"]
    else:
        cursor.execute("""
        INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
        VALUES ('Eric Badabadi (Économe)', 'ericbadabadi@gmail.com', '+228 90 00 00 01', ?, ?, '1982-04-12', '', 'econome', 1, 0, ?)
        """, (p_hash_eric, salt_eric, now))
        eric_id = cursor.lastrowid

    # 2. Confrère membre : Kato Espoir
    # Mot de passe : Kato2026!
    p_hash_kato, salt_kato = hash_password("Kato2026!")
    cursor.execute("SELECT id FROM users WHERE email = 'katoespoir@gmail.com' COLLATE NOCASE")
    row_kato = cursor.fetchone()
    if row_kato:
        cursor.execute("""
        UPDATE users 
        SET nom_prenom = 'Kato Espoir', 
            role = 'membre', 
            password_hash = ?, 
            salt = ?, 
            is_verified = 1,
            telephone = CASE WHEN telephone = '' THEN '+228 90 00 00 02' ELSE telephone END
        WHERE id = ?
        """, (p_hash_kato, salt_kato, row_kato["id"]))
        kato_id = row_kato["id"]
    else:
        cursor.execute("""
        INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
        VALUES ('Kato Espoir', 'katoespoir@gmail.com', '+228 90 00 00 02', ?, ?, '1988-08-20', '', 'membre', 1, 0, ?)
        """, (p_hash_kato, salt_kato, now))
        kato_id = cursor.lastrowid

    # 3. Eric Badabadi est le SEUL Économe : s'assurer qu'aucun autre compte n'a le rôle économe ou trésorier
    cursor.execute("UPDATE users SET role = 'membre' WHERE id != ? AND role IN ('econome', 'tresorier')", (eric_id,))

    # 4. Supprimer les anciens comptes factices @fraternite.org pour laisser la place aux vraies inscriptions
    cursor.execute("SELECT id FROM users WHERE email LIKE '%@fraternite.org'")
    demo_users = cursor.fetchall()
    for du in demo_users:
        cursor.execute("DELETE FROM cotisations WHERE user_id = ?", (du["id"],))
        cursor.execute("DELETE FROM notifications WHERE user_id = ?", (du["id"],))
        cursor.execute("DELETE FROM users WHERE id = ?", (du["id"],))

    # 5. S'assurer que le paramètre du nom de groupe est bien Paroisse de Totsi
    cursor.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES ('nom_groupe', 'Paroisse de Totsi — Fraternité Sacerdotale')")
    cursor.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES ('montant_annuel', '10000')")
    cursor.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES ('devise', 'FCFA')")

    # 6. Ajouter au moins une cotisation pour Eric Badabadi s'il n'en a pas pour l'année en cours
    cursor.execute("SELECT id FROM cotisations WHERE user_id = ? AND annee = ?", (eric_id, cur_year))
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
        VALUES (?, ?, 10000, ?, 'Virement', 'VIR-2026-001', 'Cotisation annuelle réglée', ?, ?)
        """, (eric_id, cur_year, f"{cur_year}-01-15", eric_id, now))

    # 7. Notification de bienvenue
    cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE type = 'systeme'")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("""
        INSERT INTO notifications (user_id, titre, message, type, created_at)
        VALUES (NULL, 'Bienvenue sur votre espace Paroisse de Totsi', 'L application de gestion des cotisations, caisse et alertes est opérationnelle. Eric Badabadi est l économe principal.', 'systeme', ?)
        """, (now,))

    conn.commit()

def seed_data(cursor):
    pass

if __name__ == "__main__":
    init_db()
    print("Base de données initialisée avec succès.")
