import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
import json
import secrets

def get_param(db_conn, cle: str, default: str = "") -> str:
    cursor = db_conn.cursor()
    cursor.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
    row = cursor.fetchone()
    return row["valeur"] if row else default

def send_or_log_email(db_conn, destinataire: str, sujet: str, corps_html: str) -> tuple[bool, str]:
    """Envoie un email via SMTP si configuré, sinon enregistre dans la boîte de sortie simulée."""
    now = datetime.now().isoformat()
    smtp_host = get_param(db_conn, "smtp_host", "").strip()
    smtp_port = int(get_param(db_conn, "smtp_port", "587") or "587")
    smtp_user = get_param(db_conn, "smtp_user", "").strip()
    smtp_pass = get_param(db_conn, "smtp_password", "").strip()
    smtp_from = get_param(db_conn, "smtp_from", "noreply@fraternite.org").strip()
    smtp_tls = get_param(db_conn, "smtp_use_tls", "true").lower() in ("true", "1", "yes")

    status = "simule"
    sent_real = False

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = sujet
            msg["From"] = smtp_from
            msg["To"] = destinataire
            msg.attach(MIMEText(corps_html, "html", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                if smtp_tls:
                    server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [destinataire], msg.as_string())
            status = "envoye"
            sent_real = True
        except Exception as e:
            print(f"[SMTP Error] Impossible d'envoyer l'email: {e}")
            status = f"erreur: {str(e)[:100]}"

    cursor = db_conn.cursor()
    cursor.execute("""
    INSERT INTO emails_outbox (destinataire, sujet, corps_html, statut, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (destinataire, sujet, corps_html, status, now))
    db_conn.commit()
    return sent_real, status

def notify_user(db_conn, user_id, titre: str, message: str, type_notif: str, data: dict = None):
    now = datetime.now().isoformat()
    cursor = db_conn.cursor()
    cursor.execute("""
    INSERT INTO notifications (user_id, titre, message, type, data_json, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, titre, message, type_notif, json.dumps(data or {}), now))
    db_conn.commit()

def notify_cotisation_recue(db_conn, cotisation_id: int):
    cursor = db_conn.cursor()
    cursor.execute("""
    SELECT c.*, u.nom_prenom, u.email, p.valeur as devise
    FROM cotisations c
    JOIN users u ON c.user_id = u.id
    LEFT JOIN parametres p ON p.cle = 'devise'
    WHERE c.id = ?
    """, (cotisation_id,))
    row = cursor.fetchone()
    if not row:
        return

    devise = row["devise"] or "FCFA"
    montant_str = f"{row['montant']:,.0f} {devise}".replace(",", " ")
    titre = "Reçu de cotisation enregistré"
    message = (
        f"Cher confrère, votre versement de {montant_str} au titre de la cotisation annuelle {row['annee']} "
        f"a été bien enregistré par l'économe le {row['date_paiement']} (Mode: {row['mode_paiement']}). "
        f"Que le Seigneur bénisse votre dévouement !"
    )

    notify_user(db_conn, row["user_id"], titre, message, "cotisation", {
        "cotisation_id": cotisation_id,
        "montant": row["montant"],
        "annee": row["annee"]
    })

    # Email
    nom_groupe = get_param(db_conn, "nom_groupe", "Notre Fraternité")
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4338ca;">{nom_groupe}</h2>
        <p>Cher <strong>{row['nom_prenom']}</strong>,</p>
        <p>Nous vous confirmons la bonne réception et l'enregistrement de votre versement pour la cotisation annuelle :</p>
        <div style="background: #f8fafc; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p><strong>Exercice :</strong> Année {row['annee']}</p>
            <p><strong>Montant versé :</strong> <span style="color: #059669; font-size: 18px; font-weight: bold;">{montant_str}</span></p>
            <p><strong>Date de paiement :</strong> {row['date_paiement']}</p>
            <p><strong>Mode de règlement :</strong> {row['mode_paiement']}</p>
            {f"<p><strong>Référence :</strong> {row['reference']}</p>" if row['reference'] else ""}
        </div>
        <p>Votre statut a été actualisé dans votre espace personnel sur l'application.</p>
        <p style="color: #64748b; font-size: 12px; margin-top: 25px;">Fraternellement en Christ,<br/>L'Économe & Le Trésorier</p>
    </div>
    """
    send_or_log_email(db_conn, row["email"], f"[{nom_groupe}] Avis de versement de cotisation", html)

def check_and_send_monthly_reminders(db_conn, force: bool = False) -> int:
    """
    Vérifie et émet des notifications chaque début de mois si l'utilisateur n'est pas en règle.
    force=True permet de déclencher manuellement le test depuis l'administration.
    """
    today = date.today()
    if not force and today.day != 1:
        return 0

    cursor = db_conn.cursor()
    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    annee = int(params.get("annee_active", str(today.year)))
    montant_annuel = float(params.get("montant_annuel", "10000"))
    devise = params.get("devise", "FCFA")
    nom_groupe = params.get("nom_groupe", "Fraternité Sacerdotale")

    cursor.execute("""
    SELECT u.id, u.nom_prenom, u.email,
           COALESCE(SUM(c.montant), 0) as total_verse
    FROM users u
    LEFT JOIN cotisations c ON u.id = c.user_id AND c.annee = ?
    WHERE u.is_verified = 1
    GROUP BY u.id
    """, (annee,))
    membres = cursor.fetchall()

    mois_str = today.strftime("%B %Y")
    count_notified = 0

    for m in membres:
        verse = float(m["total_verse"])
        if verse < montant_annuel:
            reste = montant_annuel - verse
            reste_str = f"{reste:,.0f} {devise}".replace(",", " ")

            # Éviter les doublons pour le même mois
            cursor.execute("""
            SELECT id FROM notifications
            WHERE user_id = ? AND type = 'rappel_mensuel'
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            """, (m["id"],))
            if not force and cursor.fetchone():
                continue

            titre = "Rappel de cotisation annuelle"
            message = (
                f"Cher {m['nom_prenom']}, en ce début de mois, nous vous rappelons fraternellement "
                f"que votre cotisation pour l'année {annee} présente un solde restant de {reste_str}. "
                f"Merci de vous rapprocher de l'économe dès que possible."
            )

            notify_user(db_conn, m["id"], titre, message, "rappel_mensuel", {
                "annee": annee,
                "reste": reste,
                "mois": mois_str
            })

            html = f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #fed7aa; border-radius: 8px;">
                <h2 style="color: #c2410c;">{nom_groupe} — Point Mensuel</h2>
                <p>Cher <strong>{m['nom_prenom']}</strong>,</p>
                <p>En ce début de mois, nous faisons un point régulier sur les cotisations de notre fraternité pour l'exercice {annee}.</p>
                <div style="background: #fff7ed; padding: 15px; border-radius: 6px; margin: 15px 0;">
                    <p><strong>Cotisation requise :</strong> {montant_annuel:,.0f} {devise}</p>
                    <p><strong>Montant déjà réglé :</strong> {verse:,.0f} {devise}</p>
                    <p><strong>Reste à verser :</strong> <span style="color: #dc2626; font-size: 18px; font-weight: bold;">{reste_str}</span></p>
                </div>
                <p>Votre participation soutient nos œuvres communes et la solidarité presbytérale.</p>
                <p style="color: #64748b; font-size: 12px; margin-top: 25px;">Bien fraternellement en Jésus-Christ,<br/>L'Économe</p>
            </div>
            """
            send_or_log_email(db_conn, m["email"], f"[{nom_groupe}] Rappel fraternel cotisation {annee}", html)
            count_notified += 1

    return count_notified

def check_and_send_birthday_notifications(db_conn, force_target_user_id: int = None) -> int:
    """
    À 2 jours de l'anniversaire d'un membre du groupe, tous les membres reçoivent la notification,
    de même que le jour-J.
    """
    today = date.today()
    in_2_days = today + timedelta(days=2)

    cursor = db_conn.cursor()
    nom_groupe = get_param(db_conn, "nom_groupe", "Fraternité Sacerdotale")

    # Récupérer tous les membres avec date de naissance
    cursor.execute("""
    SELECT id, nom_prenom, email, date_naissance
    FROM users
    WHERE date_naissance IS NOT NULL AND date_naissance != ''
    """)
    membres = cursor.fetchall()

    cursor.execute("SELECT id, email, nom_prenom FROM users WHERE is_verified = 1")
    tous_les_destinataires = cursor.fetchall()

    count_notifications = 0

    for m in membres:
        try:
            # Parse format YYYY-MM-DD
            parts = m["date_naissance"].split("-")
            b_month = int(parts[1])
            b_day = int(parts[2])
        except Exception:
            continue

        # Cas 1 : J-2 (Dans exactement 2 jours)
        if (b_month == in_2_days.month and b_day == in_2_days.day) or (force_target_user_id == m["id"]):
            tag = f"anniv_j2_{m['id']}_{today.year}"
            cursor.execute("SELECT id FROM notifications WHERE data_json LIKE ? AND created_at >= date('now')", (f"%{tag}%",))
            if not cursor.fetchone() or force_target_user_id:
                titre = f"🎂 Anniversaire dans 2 jours : {m['nom_prenom']}"
                message = (
                    f"Frères, dans 2 jours (le {in_2_days.strftime('%d/%m')}), notre cher confrère "
                    f"{m['nom_prenom']} fêtera son anniversaire ! Préparons nos cœurs et portons-le dans nos intentions de messe."
                )
                # Notification globale (user_id = NULL pour visible par tous, ou insérée pour chacun)
                notify_user(db_conn, None, titre, message, "anniversaire_j2", {"tag": tag, "membre_id": m["id"], "nom": m["nom_prenom"]})
                count_notifications += 1

                # Envoyer un e-mail groupé/individuel
                for dest in tous_les_destinataires:
                    html = f"""
                    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #bfdbfe; border-radius: 8px;">
                        <h2 style="color: #2563eb;">🎂 Anniversaire sacerdotal à venir !</h2>
                        <p>Chers confrères,</p>
                        <p>Dans 2 jours, le <strong>{in_2_days.strftime('%d/%m')}</strong>, nous fêterons l'anniversaire de notre bien-aimé confrère :</p>
                        <h3 style="color: #1e3a8a; text-align: center; font-size: 20px;">{m['nom_prenom']}</h3>
                        <p>Unissons nos prières pour lui rendre grâce pour le don de sa vie et de son ministère.</p>
                        <p style="color: #64748b; font-size: 12px; margin-top: 25px;">{nom_groupe}</p>
                    </div>
                    """
                    send_or_log_email(db_conn, dest["email"], f"[{nom_groupe}] 🎂 Anniversaire de {m['nom_prenom']} dans 2 jours !", html)

        # Cas 2 : Jour-J (Aujourd'hui)
        if (b_month == today.month and b_day == today.day):
            tag = f"anniv_jour_j_{m['id']}_{today.year}"
            cursor.execute("SELECT id FROM notifications WHERE data_json LIKE ? AND created_at >= date('now')", (f"%{tag}%",))
            if not cursor.fetchone():
                titre = f"🎉 Joyeux Anniversaire à {m['nom_prenom']} !"
                message = (
                    f"Aujourd'hui nous célébrons avec action de grâce l'anniversaire de {m['nom_prenom']} ! "
                    f"Que le Très-Haut comble notre confrère de grâces, de santé et de joie dans son sacerdoce. "
                    f"Exprimons-lui toute notre affection fraternelle !"
                )
                notify_user(db_conn, None, titre, message, "anniversaire_jour_j", {"tag": tag, "membre_id": m["id"], "nom": m["nom_prenom"]})
                count_notifications += 1

                for dest in tous_les_destinataires:
                    html = f"""
                    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #bbf7d0; border-radius: 8px;">
                        <h2 style="color: #15803d;">🎉 Joyeux Anniversaire Confrère !</h2>
                        <p>Chers frères en Christ,</p>
                        <p>C'est aujourd'hui l'anniversaire de notre cher confrère :</p>
                        <h3 style="color: #14532d; text-align: center; font-size: 22px;">{m['nom_prenom']}</h3>
                        <p>Que cette nouvelle année sous la conduite de l'Esprit Saint lui apporte fécondité apostolique et paix profonde.</p>
                        <p style="text-align: center; margin: 20px 0;">
                            <a href="https://wa.me/?text={m['nom_prenom']}" style="background: #22c55e; color: white; padding: 10px 18px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                                Envoyer un mot sur WhatsApp
                            </a>
                        </p>
                        <p style="color: #64748b; font-size: 12px; margin-top: 25px;">{nom_groupe}</p>
                    </div>
                    """
                    send_or_log_email(db_conn, dest["email"], f"[{nom_groupe}] 🎉 Joyeux Anniversaire à notre confrère {m['nom_prenom']} !", html)

    return count_notifications

def send_account_validation_email(db_conn, user_id: int, base_url: str) -> tuple[bool, str, str]:
    cursor = db_conn.cursor()
    cursor.execute("SELECT nom_prenom, email, verification_token FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    if not u:
        return False, "", "utilisateur_introuvable"

    nom_groupe = get_param(db_conn, "nom_groupe", "Notre Fraternité")
    val_link = f"{base_url}/valider-compte?token={u['verification_token']}"

    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4338ca;">Bienvenue dans la {nom_groupe}</h2>
        <p>Cher <strong>{u['nom_prenom']}</strong>,</p>
        <p>Votre compte a été créé avec succès pour le suivi de vos cotisations et de la vie de notre fraternité.</p>
        <p>Afin de valider votre adresse e-mail et activer l'accès à votre espace, veuillez cliquer sur le bouton ci-dessous :</p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{val_link}" style="background-color: #4338ca; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                Valider mon compte confrère
            </a>
        </div>
        <p style="color: #64748b; font-size: 13px;">Si le bouton ne fonctionne pas, vous pouvez copier ce lien dans votre navigateur :<br/>
        <a href="{val_link}">{val_link}</a></p>
        <p style="color: #64748b; font-size: 12px; margin-top: 30px;">Dans la communion fraternelle,<br/>L'Économe</p>
    </div>
    """
    sent_real, status = send_or_log_email(db_conn, u["email"], f"[{nom_groupe}] Validation de votre compte sacerdotal", html)
    return sent_real, val_link, status

def send_reset_password_email(db_conn, user_id: int, base_url: str) -> tuple[bool, str, str]:
    cursor = db_conn.cursor()
    token = secrets.token_urlsafe(32)
    cursor.execute("""
    UPDATE users SET reset_token = ?, reset_expires = datetime('now', '+1 hour')
    WHERE id = ?
    """, (token, user_id))
    db_conn.commit()

    cursor.execute("SELECT nom_prenom, email FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    if not u:
        return False, "", "utilisateur_introuvable"

    nom_groupe = get_param(db_conn, "nom_groupe", "Notre Fraternité")
    reset_link = f"{base_url}/reinitialiser-mot-de-passe?token={token}"

    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #4338ca;">Réinitialisation de mot de passe</h2>
        <p>Cher <strong>{u['nom_prenom']}</strong>,</p>
        <p>Une demande de réinitialisation de mot de passe a été émise pour votre compte dans la <strong>{nom_groupe}</strong>.</p>
        <p>Pour définir un nouveau mot de passe, veuillez cliquer ci-dessous (lien valable 1 heure) :</p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{reset_link}" style="background-color: #0284c7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                Réinitialiser mon mot de passe
            </a>
        </div>
        <p style="color: #64748b; font-size: 13px;">Lien direct :<br/><a href="{reset_link}">{reset_link}</a></p>
        <p style="color: #94a3b8; font-size: 12px; margin-top: 25px;">Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet e-mail en toute sécurité.</p>
    </div>
    """
    sent_real, status = send_or_log_email(db_conn, u["email"], f"[{nom_groupe}] Réinitialisation de votre mot de passe", html)
    return sent_real, reset_link, status
