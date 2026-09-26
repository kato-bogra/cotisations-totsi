import os
import io
import json
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import database
import pdf_generator
import notifications

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(
    title="Gestion des Cotisations Sacerdotales",
    description="Application de gestion des cotisations annuelles, caisse et fraternité pour prêtres",
    version="1.0.0"
)

# Session middleware pour l'authentification simple et sécurisée
app.add_middleware(SessionMiddleware, secret_key="fraternite_sacerdotale_cle_secrete_2026_xYz!", max_age=86400 * 30)

# Fichiers statiques et templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié. Veuillez vous connecter.")
    return user

def require_econome_or_tresorier(request: Request):
    user = require_auth(request)
    if user["role"] not in ("econome", "tresorier"):
        raise HTTPException(status_code=403, detail="Accès réservé à l'Économe ou au Trésorier.")
    return user

# Tâche d'arrière-plan pour vérifier régulièrement anniversaires et 1er du mois
async def scheduler_loop():
    while True:
        try:
            conn = database.get_db()
            notifications.check_and_send_birthday_notifications(conn)
            notifications.check_and_send_monthly_reminders(conn)
            conn.close()
        except Exception as e:
            print(f"[Scheduler Error] {e}")
        await asyncio.sleep(3600 * 6) # Vérifier toutes les 6 heures

@app.on_event("startup")
async def on_startup():
    database.init_db()
    asyncio.create_task(scheduler_loop())

# ================= PAGES PRINCIPALES =================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    user = get_current_user(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "params": params,
            "annee_courante": date.today().year,
            "date_courante": date.today().isoformat()
        }
    )

@app.get("/manifest.json")
async def manifest():
    return JSONResponse({
        "name": "Cotisations Sacerdotales",
        "short_name": "Cotisations",
        "description": "Gestion des cotisations annuelles et caisse de la fraternité des prêtres",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#1e293b",
        "icons": [
            {
                "src": "/static/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })

@app.get("/sw.js")
async def service_worker():
    sw_content = """
    const CACHE_NAME = 'fraternite-v1';
    self.addEventListener('install', (e) => {
        self.skipWaiting();
    });
    self.addEventListener('activate', (e) => {
        e.waitUntil(clients.claim());
    });
    self.addEventListener('fetch', (e) => {
        // Mode réseau prioritaire
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return Response(content=sw_content, media_type="application/javascript")

# ================= AUTHENTIFICATION & COMPTES =================

@app.post("/api/auth/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return JSONResponse({"status": "error", "message": "Adresse e-mail ou mot de passe incorrect."}, status_code=400)

    if not database.verify_password(password, user["password_hash"], user["salt"]):
        return JSONResponse({"status": "error", "message": "Adresse e-mail ou mot de passe incorrect."}, status_code=400)

    if not user["is_verified"]:
        base_url = str(request.base_url).rstrip("/")
        token_to_use = user["verification_token"]
        if not token_to_use:
            token_to_use = database.secrets.token_urlsafe(32)
            conn = database.get_db()
            conn.cursor().execute("UPDATE users SET verification_token = ? WHERE id = ?", (token_to_use, user["id"]))
            conn.commit()
            conn.close()
        val_link = f"{base_url}/valider-compte?token={token_to_use}"
        return JSONResponse({
            "status": "error",
            "not_verified": True,
            "validation_url": val_link,
            "message": "Votre compte n'a pas encore été validé. Cliquez sur le bouton ci-dessous pour l'activer immédiatement."
        }, status_code=400)

    request.session["user_id"] = user["id"]
    return {
        "status": "success",
        "user": {
            "id": user["id"],
            "nom_prenom": user["nom_prenom"],
            "email": user["email"],
            "role": user["role"],
            "photo_url": user["photo_url"],
            "must_change_password": bool(user["must_change_password"])
        }
    }

@app.post("/api/auth/register")
async def register(
    request: Request,
    nom_prenom: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    date_naissance: str = Form(...),
    telephone: str = Form(""),
    photo: Optional[UploadFile] = File(None)
):
    conn = database.get_db()
    cursor = conn.cursor()

    # Vérifier existence de l'email
    cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),))
    if cursor.fetchone():
        conn.close()
        return JSONResponse({"status": "error", "message": "Un compte existe déjà avec cette adresse e-mail."}, status_code=400)

    photo_url = ""
    if photo and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.webp'):
            filename = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}_{photo.filename}"
            filepath = os.path.join(UPLOADS_DIR, filename)
            content = await photo.read()
            with open(filepath, "wb") as f:
                f.write(content)
            photo_url = f"/static/uploads/{filename}"

    pw_hash, salt = database.hash_password(password)
    verification_token = database.secrets.token_urlsafe(32)
    now = datetime.now().isoformat()

    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, verification_token, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'membre', 0, ?, ?)
    """, (nom_prenom.strip(), email.strip(), telephone.strip(), pw_hash, salt, date_naissance, photo_url, verification_token, now))
    new_user_id = cursor.lastrowid
    conn.commit()

    base_url = str(request.base_url).rstrip("/")
    sent_real, val_link, status = notifications.send_account_validation_email(conn, new_user_id, base_url)
    conn.close()

    if sent_real:
        msg = f"Votre compte a été créé avec succès ! Un e-mail de validation a été envoyé à {email.strip()}. Veuillez vérifier votre boîte de réception."
    else:
        msg = "Votre compte a été créé avec succès ! Cliquez ci-dessous pour valider immédiatement votre accès sans attendre d'e-mail."

    return {
        "status": "success",
        "email_sent": sent_real,
        "validation_url": val_link,
        "message": msg
    }

@app.get("/valider-compte")
async def valider_compte(token: str):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nom_prenom FROM users WHERE verification_token = ?", (token,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return HTMLResponse("<h3>Lien de validation invalide ou déjà utilisé.</h3><p><a href='/'>Retour à l'application</a></p>", status_code=400)

    cursor.execute("UPDATE users SET is_verified = 1, verification_token = NULL WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head><meta charset="utf-8"><title>Compte Validé</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <style>
      body {{ font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #0f172a; color: #f8fafc; margin: 0; }}
      .card {{ background: #1e293b; padding: 2.5rem; border-radius: 1rem; text-align: center; max-width: 420px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
      .btn {{ background: #4f46e5; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 1.5rem; }}
    </style>
    </head>
    <body>
      <div class="card">
        <div style="font-size: 3rem; color: #10b981; margin-bottom: 1rem;"><i class="bi bi-check-circle-fill"></i></div>
        <h2>Compte Validé avec Succès !</h2>
        <p>Cher <strong>{user['nom_prenom']}</strong>, votre compte sacerdotal est désormais actif. Vous pouvez vous connecter pour suivre votre cotisation.</p>
        <a href="/" class="btn">Se connecter à l'application</a>
      </div>
    </body>
    </html>
    """)

@app.post("/api/auth/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),))
    user = cursor.fetchone()
    if user:
        base_url = str(request.base_url).rstrip("/")
        sent_real, reset_link, status = notifications.send_reset_password_email(conn, user["id"], base_url)
        conn.close()
        if sent_real:
            msg = f"Un e-mail de réinitialisation a été envoyé à {email.strip()}. Veuillez consulter votre boîte de réception."
        else:
            msg = "Lien de réinitialisation généré. Cliquez sur le bouton ci-dessous pour changer votre mot de passe immédiatement."
        return {
            "status": "success",
            "email_sent": sent_real,
            "reset_url": reset_link,
            "message": msg
        }
    conn.close()
    return {
        "status": "success",
        "email_sent": False,
        "message": "Si cette adresse est enregistrée, les instructions ont été générées."
    }

@app.post("/api/auth/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, nom_prenom FROM users
    WHERE reset_token = ? AND reset_expires > datetime('now')
    """, (token,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return JSONResponse({"status": "error", "message": "Le lien de réinitialisation a expiré ou est invalide."}, status_code=400)

    pw_hash, salt = database.hash_password(new_password)
    cursor.execute("""
    UPDATE users SET password_hash = ?, salt = ?, reset_token = NULL, reset_expires = NULL, must_change_password = 0
    WHERE id = ?
    """, (pw_hash, salt, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Votre mot de passe a été mis à jour avec succès. Vous pouvez vous connecter."}

@app.post("/api/auth/change-password")
async def change_password(request: Request, old_password: str = Form(...), new_password: str = Form(...)):
    user = require_auth(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user["id"],))
    row = cursor.fetchone()

    if not database.verify_password(old_password, row["password_hash"], row["salt"]):
        conn.close()
        return JSONResponse({"status": "error", "message": "L'ancien mot de passe est incorrect."}, status_code=400)

    pw_hash, salt = database.hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ?, salt = ?, must_change_password = 0 WHERE id = ?", (pw_hash, salt, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Mot de passe modifié avec succès."}

@app.get("/api/auth/me")
async def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {"authenticated": False}

    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(*) as count FROM notifications
    WHERE (user_id = ? OR user_id IS NULL) AND is_read = 0
    """, (user["id"],))
    unread_count = cursor.fetchone()["count"]
    conn.close()

    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "nom_prenom": user["nom_prenom"],
            "email": user["email"],
            "telephone": user["telephone"],
            "date_naissance": user["date_naissance"],
            "photo_url": user["photo_url"],
            "role": user["role"],
            "must_change_password": bool(user["must_change_password"]),
            "unread_notifications": unread_count
        }
    }

@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "success"}

# ================= GESTION FINANCIÈRE & CAISSE =================

@app.get("/api/caisse/resume")
async def caisse_resume(request: Request, annee: Optional[int] = None):
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    montant_annuel = float(params.get("montant_annuel", "10000"))
    devise = params.get("devise", "FCFA")
    active_year = annee or int(params.get("annee_active", str(date.today().year)))

    # Totaux globaux de la caisse
    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM cotisations")
    total_cotisations_global = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM depenses")
    total_depenses_global = cursor.fetchone()["total"]

    avoir_en_caisse = total_cotisations_global - total_depenses_global

    # Totaux spécifiques à l'année
    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM cotisations WHERE annee = ?", (active_year,))
    total_cotisations_annee = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_verified = 1")
    nombre_membres = cursor.fetchone()["total"]
    total_attendu_annee = nombre_membres * montant_annuel

    # Nombre de prêtres à jour pour l'année
    cursor.execute("""
    SELECT u.id, COALESCE(SUM(c.montant), 0) as verse
    FROM users u
    LEFT JOIN cotisations c ON u.id = c.user_id AND c.annee = ?
    WHERE u.is_verified = 1
    GROUP BY u.id
    """, (active_year,))
    rows = cursor.fetchall()
    membres_a_jour = sum(1 for r in rows if r["verse"] >= montant_annuel)
    membres_partiels = sum(1 for r in rows if 0 < r["verse"] < montant_annuel)
    membres_en_retard = sum(1 for r in rows if r["verse"] == 0)

    conn.close()

    return {
        "avoir_en_caisse": avoir_en_caisse,
        "total_cotisations_global": total_cotisations_global,
        "total_depenses_global": total_depenses_global,
        "annee": active_year,
        "montant_annuel": montant_annuel,
        "devise": devise,
        "total_cotisations_annee": total_cotisations_annee,
        "total_attendu_annee": total_attendu_annee,
        "taux_recouvrement": round((total_cotisations_annee / total_attendu_annee * 100), 1) if total_attendu_annee > 0 else 0,
        "nombre_membres": nombre_membres,
        "membres_a_jour": membres_a_jour,
        "membres_partiels": membres_partiels,
        "membres_en_retard": membres_en_retard
    }

# ================= DÉPENSES =================

@app.get("/api/caisse/depenses")
async def list_depenses(request: Request):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT d.*, u.nom_prenom as auteur_nom
    FROM depenses d
    LEFT JOIN users u ON d.enregistre_par_id = u.id
    ORDER BY d.date_depense DESC, d.id DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/caisse/depenses")
async def add_depense(
    request: Request,
    titre: str = Form(...),
    montant: float = Form(...),
    date_depense: str = Form(...),
    categorie: str = Form("Général"),
    description: str = Form(""),
    justificatif: Optional[UploadFile] = File(None)
):
    user = require_econome_or_tresorier(request)
    justif_url = ""
    if justificatif and justificatif.filename:
        ext = os.path.splitext(justificatif.filename)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.pdf'):
            filename = f"depense_{datetime.now().strftime('%Y%m%d%H%M%S')}_{justificatif.filename}"
            filepath = os.path.join(UPLOADS_DIR, filename)
            content = await justificatif.read()
            with open(filepath, "wb") as f:
                f.write(content)
            justif_url = f"/static/uploads/{filename}"

    now = datetime.now().isoformat()
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO depenses (titre, description, montant, date_depense, categorie, justificatif_url, enregistre_par_id, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (titre.strip(), description.strip(), montant, date_depense, categorie.strip(), justif_url, user["id"], now))
    conn.commit()

    # Notification système
    notifications.notify_user(
        conn, None, "Nouvelle dépense enregistrée sur la caisse",
        f"Une dépense de {montant:,.0f} a été déduite de la caisse pour : '{titre}'.",
        "systeme"
    )
    conn.close()

    return {"status": "success", "message": "Dépense enregistrée et déduite de la caisse avec succès."}

@app.delete("/api/caisse/depenses/{depense_id}")
async def delete_depense(depense_id: int, request: Request):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM depenses WHERE id = ?", (depense_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Dépense supprimée."}

# ================= COTISATIONS =================

@app.get("/api/cotisations")
async def list_cotisations(request: Request, annee: Optional[int] = None):
    conn = database.get_db()
    cursor = conn.cursor()
    if annee:
        cursor.execute("""
        SELECT c.*, u.nom_prenom as membre_nom, u.email as membre_email, u.telephone as membre_tel,
               e.nom_prenom as enregistre_par_nom
        FROM cotisations c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN users e ON c.enregistre_par_id = e.id
        WHERE c.annee = ?
        ORDER BY c.date_paiement DESC, c.id DESC
        """, (annee,))
    else:
        cursor.execute("""
        SELECT c.*, u.nom_prenom as membre_nom, u.email as membre_email, u.telephone as membre_tel,
               e.nom_prenom as enregistre_par_nom
        FROM cotisations c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN users e ON c.enregistre_par_id = e.id
        ORDER BY c.date_paiement DESC, c.id DESC
        """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/cotisations")
async def add_cotisation(
    request: Request,
    user_id: int = Form(...),
    montant: float = Form(...),
    annee: int = Form(...),
    date_paiement: str = Form(...),
    mode_paiement: str = Form(...),
    reference: str = Form(""),
    note: str = Form("")
):
    user = require_econome_or_tresorier(request)
    now = datetime.now().isoformat()
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO cotisations (user_id, annee, montant, date_paiement, mode_paiement, reference, note, enregistre_par_id, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, annee, montant, date_paiement, mode_paiement, reference.strip(), note.strip(), user["id"], now))
    cotisation_id = cursor.lastrowid
    conn.commit()

    # Envoi immédiat de la notification au membre concerné !
    notifications.notify_cotisation_recue(conn, cotisation_id)
    conn.close()

    return {"status": "success", "message": "Cotisation ajoutée avec succès. La notification a été aussitôt envoyée au prêtre."}

@app.get("/api/cotisations/mon-statut")
async def mon_statut(request: Request, annee: Optional[int] = None):
    user = require_auth(request)
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    montant_annuel = float(params.get("montant_annuel", "10000"))
    devise = params.get("devise", "FCFA")
    active_year = annee or int(params.get("annee_active", str(date.today().year)))

    # Versements de l'utilisateur pour l'année
    cursor.execute("""
    SELECT * FROM cotisations
    WHERE user_id = ? AND annee = ?
    ORDER BY date_paiement DESC
    """, (user["id"], active_year))
    versements = [dict(r) for r in cursor.fetchall()]

    total_verse = sum(v["montant"] for v in versements)
    reste = max(0.0, montant_annuel - total_verse)
    statut = "A_JOUR" if total_verse >= montant_annuel else ("PARTIEL" if total_verse > 0 else "NON_REGLE")

    # Historique toutes années
    cursor.execute("""
    SELECT annee, SUM(montant) as total_verse, COUNT(*) as nb_versements
    FROM cotisations
    WHERE user_id = ?
    GROUP BY annee
    ORDER BY annee DESC
    """, (user["id"],))
    historique_annees = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "user_id": user["id"],
        "nom_prenom": user["nom_prenom"],
        "annee": active_year,
        "montant_annuel": montant_annuel,
        "devise": devise,
        "total_verse": total_verse,
        "reste": reste,
        "statut": statut,
        "versements": versements,
        "historique_annees": historique_annees
    }

# ================= GESTION DES MEMBRES =================

@app.get("/api/membres")
async def list_membres(request: Request, annee: Optional[int] = None):
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    montant_annuel = float(params.get("montant_annuel", "10000"))
    active_year = annee or int(params.get("annee_active", str(date.today().year)))

    cursor.execute("""
    SELECT u.id, u.nom_prenom, u.email, u.telephone, u.date_naissance, u.photo_url, u.role, u.is_verified,
           COALESCE(SUM(c.montant), 0) as total_verse,
           MAX(c.date_paiement) as derniere_cotisation_date
    FROM users u
    LEFT JOIN cotisations c ON u.id = c.user_id AND c.annee = ?
    GROUP BY u.id
    ORDER BY u.nom_prenom ASC
    """, (active_year,))
    rows = cursor.fetchall()
    membres = []
    today = date.today()

    for r in rows:
        d = dict(r)
        verse = float(d["total_verse"])
        d["reste"] = max(0.0, montant_annuel - verse)
        if verse >= montant_annuel:
            d["statut"] = "A_JOUR"
        elif verse > 0:
            d["statut"] = "PARTIEL"
        else:
            d["statut"] = "NON_REGLE"

        # Calcul jours jusqu'au prochain anniversaire
        d["prochain_anniv_jours"] = None
        if d["date_naissance"]:
            try:
                parts = d["date_naissance"].split("-")
                b_month = int(parts[1])
                b_day = int(parts[2])
                this_year_bday = date(today.year, b_month, b_day)
                if this_year_bday < today:
                    this_year_bday = date(today.year + 1, b_month, b_day)
                d["prochain_anniv_jours"] = (this_year_bday - today).days
            except Exception:
                pass

        membres.append(d)

    conn.close()
    return membres

@app.post("/api/membres")
async def create_membre_by_econome(
    request: Request,
    nom_prenom: str = Form(...),
    email: str = Form(...),
    telephone: str = Form(""),
    date_naissance: str = Form(...),
    role: str = Form("membre"),
    photo: Optional[UploadFile] = File(None)
):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),))
    if cursor.fetchone():
        conn.close()
        return JSONResponse({"status": "error", "message": "Un compte existe déjà avec cette adresse e-mail."}, status_code=400)

    photo_url = ""
    if photo and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.webp'):
            filename = f"user_{datetime.now().strftime('%Y%m%d%H%M%S')}_{photo.filename}"
            filepath = os.path.join(UPLOADS_DIR, filename)
            content = await photo.read()
            with open(filepath, "wb") as f:
                f.write(content)
            photo_url = f"/static/uploads/{filename}"

    # Mot de passe par défaut : 4321
    pw_hash, salt = database.hash_password("4321")
    now = datetime.now().isoformat()

    cursor.execute("""
    INSERT INTO users (nom_prenom, email, telephone, password_hash, salt, date_naissance, photo_url, role, is_verified, must_change_password, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
    """, (nom_prenom.strip(), email.strip(), telephone.strip(), pw_hash, salt, date_naissance, photo_url, role, now))
    new_user_id = cursor.lastrowid
    conn.commit()

    # Notifier par email le nouveau prêtre avec ses identifiants
    nom_groupe = notifications.get_param(conn, "nom_groupe", "Notre Fraternité")
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4338ca;">Bienvenue dans la {nom_groupe}</h2>
        <p>Cher <strong>{nom_prenom}</strong>,</p>
        <p>L'économe a créé votre compte sacerdotal sur l'application de gestion de notre fraternité.</p>
        <div style="background: #f8fafc; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p><strong>Identifiant (E-mail) :</strong> {email}</p>
            <p><strong>Mot de passe initial par défaut :</strong> <code style="background: #e2e8f0; padding: 2px 6px; font-size: 16px;">4321</code></p>
        </div>
        <p>Vous pourrez changer ce mot de passe dès votre première connexion.</p>
        <p style="color: #64748b; font-size: 12px; margin-top: 25px;">Fraternellement en Christ,<br/>L'Économe</p>
    </div>
    """
    notifications.send_or_log_email(conn, email, f"[{nom_groupe}] Création de votre compte confrère", html)
    conn.close()

    return {
        "status": "success",
        "message": f"Compte créé avec succès pour {nom_prenom}. Son mot de passe initial par défaut est '4321'."
    }

@app.post("/api/membres/{user_id}/valider")
async def valider_membre_par_econome(request: Request, user_id: int):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nom_prenom FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    if not u:
        conn.close()
        return JSONResponse({"status": "error", "message": "Confrère introuvable."}, status_code=404)

    cursor.execute("UPDATE users SET is_verified = 1, verification_token = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Le compte de {u['nom_prenom']} a été validé et activé avec succès !"}

# ================= RAPPORT PDF & WHATSAPP =================

@app.get("/api/rapport/pdf")
async def download_pdf(request: Request, annee: Optional[int] = None):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    active_year = annee or int(params.get("annee_active", str(date.today().year)))

    pdf_bytes = pdf_generator.generate_financial_pdf(conn, active_year)
    conn.close()

    filename = f"Rapport_Cotisations_{active_year}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/rapport/whatsapp-texte")
async def get_whatsapp_text(request: Request, annee: Optional[int] = None):
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    nom_groupe = params.get("nom_groupe", "Fraternité Sacerdotale")
    montant_annuel = float(params.get("montant_annuel", "10000"))
    devise = params.get("devise", "FCFA")
    active_year = annee or int(params.get("annee_active", str(date.today().year)))

    # Totaux
    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM cotisations")
    total_cotisations_global = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM depenses")
    total_depenses_global = cursor.fetchone()["total"]

    avoir_en_caisse = total_cotisations_global - total_depenses_global

    cursor.execute("""
    SELECT u.nom_prenom, COALESCE(SUM(c.montant), 0) as total_verse
    FROM users u
    LEFT JOIN cotisations c ON u.id = c.user_id AND c.annee = ?
    WHERE u.is_verified = 1
    GROUP BY u.id
    ORDER BY u.nom_prenom ASC
    """, (active_year,))
    membres = cursor.fetchall()
    conn.close()

    total_membres = len(membres)
    a_jour = [m for m in membres if float(m["total_verse"]) >= montant_annuel]
    partiels = [m for m in membres if 0 < float(m["total_verse"]) < montant_annuel]
    non_regles = [m for m in membres if float(m["total_verse"]) == 0]

    msg = f"📊 *{nom_groupe.upper()}*\n"
    msg += f"📜 *POINT FINANCIER & ÉTAT DES COTISATIONS ({active_year})*\n"
    msg += f"🗓️ Date : {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
    msg += f"💰 *Avoir net en caisse :* {avoir_en_caisse:,.0f} {devise}\n".replace(",", " ")
    msg += f"📈 *Recouvrement {active_year} :* {len(a_jour)}/{total_membres} confrères à jour\n"
    msg += f"💵 *Cotisation annuelle :* {montant_annuel:,.0f} {devise}\n\n".replace(",", " ")

    msg += f"✅ *À JOUR ({len(a_jour)}) :*\n"
    for m in a_jour:
        msg += f"• {m['nom_prenom']}\n"

    if partiels:
        msg += f"\n⏳ *EN COURS ({len(partiels)}) :*\n"
        for m in partiels:
            verse = float(m["total_verse"])
            msg += f"• {m['nom_prenom']} ({verse:,.0f}/{montant_annuel:,.0f} {devise})\n".replace(",", " ")

    if non_regles:
        msg += f"\n⚠️ *EN ATTENTE ({len(non_regles)}) :*\n"
        for m in non_regles:
            msg += f"• {m['nom_prenom']}\n"

    msg += f"\n_« Que le Seigneur soutienne notre fraternité et bénisse notre apostolat commun ! »_\n"
    msg += f"— L'Économe & Le Trésorier"

    return {"texte": msg}

# ================= NOTIFICATIONS =================

@app.get("/api/notifications")
async def get_notifications(request: Request):
    user = require_auth(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM notifications
    WHERE user_id = ? OR user_id IS NULL
    ORDER BY created_at DESC
    LIMIT 50
    """, (user["id"],))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/notifications/marquer-lues")
async def marquer_lues(request: Request):
    user = require_auth(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE notifications SET is_read = 1
    WHERE user_id = ? OR user_id IS NULL
    """, (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/notifications/declencher-rappels")
async def declencher_rappels(request: Request):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    n_bday = notifications.check_and_send_birthday_notifications(conn)
    n_month = notifications.check_and_send_monthly_reminders(conn, force=True)
    conn.close()
    return {
        "status": "success",
        "message": f"Vérification exécutée : {n_bday} alerte(s) d'anniversaire et {n_month} rappel(s) de début de mois généré(s)."
    }

# ================= EMAILS SORTANTS (INSPECTION & SIMULATION) =================

@app.get("/api/emails-sortants")
async def get_emails_sortants(request: Request):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM emails_outbox ORDER BY created_at DESC LIMIT 30")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ================= PARAMÈTRES DU GROUPE =================

@app.get("/api/parametres")
async def get_parametres():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    conn.close()
    # Masquer le mot de passe SMTP dans la réponse
    if "smtp_password" in params and params["smtp_password"]:
        params["smtp_password"] = "******"
    return params

@app.post("/api/parametres")
async def update_parametres(request: Request):
    require_econome_or_tresorier(request)
    form = await request.form()
    conn = database.get_db()
    cursor = conn.cursor()

    for k, v in form.items():
        if k == "smtp_password" and v == "******":
            continue
        cursor.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES (?, ?)", (k, str(v).strip()))

    conn.commit()
    conn.close()
    return {"status": "success", "message": "Paramètres mis à jour."}

@app.post("/api/parametres/test-email")
async def test_email_smtp(request: Request, destinataire: str = Form(...)):
    require_econome_or_tresorier(request)
    conn = database.get_db()
    nom_groupe = notifications.get_param(conn, "nom_groupe", "Paroisse de Totsi")
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:auto;padding:20px;border:1px solid #10b981;border-radius:8px;">
        <h3 style="color:#10b981;">✅ Test d'envoi d'e-mail réussi !</h3>
        <p>Le serveur SMTP configuré pour <strong>{nom_groupe}</strong> fonctionne parfaitement.</p>
        <p>Si vous lisez ce message, vos e-mails de validation et vos notifications d'anniversaires arriveront bien dans les boîtes de réception des confrères.</p>
        <p style="color:#64748b;font-size:12px;margin-top:20px;">Date et heure du test : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
    </div>
    """
    sent_real, status = notifications.send_or_log_email(conn, destinataire.strip(), f"[{nom_groupe}] ✅ Test d'envoi d'e-mail réussi", html)
    conn.close()
    if sent_real:
        return {"status": "success", "message": f"E-mail de test envoyé avec succès à {destinataire} !"}
    else:
        return {"status": "warning", "message": f"Échec de l'envoi direct (Statut: {status}). L'e-mail a été enregistré dans la boîte d'envoi locale."}
