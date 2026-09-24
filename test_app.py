import sys
import os
from starlette.testclient import TestClient

# Assurer l'import local
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app
import database

def run_tests():
    database.init_db()
    client = TestClient(app)

    print("1. Test GET / ...")
    r = client.get("/")
    assert r.status_code == 200
    assert "Fraternité" in r.text
    print("   -> OK!")

    print("2. Test GET /api/caisse/resume ...")
    r = client.get("/api/caisse/resume")
    assert r.status_code == 200
    data = r.json()
    assert "avoir_en_caisse" in data
    assert "total_cotisations_global" in data
    assert "total_depenses_global" in data
    print(f"   -> OK! Avoir en caisse: {data['avoir_en_caisse']} {data['devise']}")

    print("3. Test Connexion Économe (mot de passe 4321) ...")
    r = client.post("/api/auth/login", data={"email": "econome@fraternite.org", "password": "4321"})
    assert r.status_code == 200
    user_data = r.json()
    assert user_data["status"] == "success"
    assert user_data["user"]["role"] == "econome"
    print(f"   -> OK! Connecté en tant que {user_data['user']['nom_prenom']}")

    print("4. Test GET /api/cotisations/mon-statut ...")
    r = client.get("/api/cotisations/mon-statut")
    assert r.status_code == 200
    statut = r.json()
    assert "total_verse" in statut
    assert "reste" in statut
    print(f"   -> OK! Total versé: {statut['total_verse']}, Reste: {statut['reste']}")

    print("5. Test Ajout de Cotisation par l'Économe (avec notification instantanée) ...")
    # Récupérer un membre
    r_membres = client.get("/api/membres")
    membres = r_membres.json()
    target_membre = next(m for m in membres if m["email"] == "michel@fraternite.org")
    
    r_cot = client.post("/api/cotisations", data={
        "user_id": target_membre["id"],
        "montant": 10000,
        "annee": 2026,
        "date_paiement": "2026-09-24",
        "mode_paiement": "Wave",
        "reference": "WAV-TEST-999",
        "note": "Paiement annuel test"
    })
    assert r_cot.status_code == 200
    assert r_cot.json()["status"] == "success"
    print("   -> OK! Cotisation ajoutée avec succès.")

    # Vérifier que le prêtre (Père Michel) a bien reçu sa notification instantanément
    client_michel = TestClient(app)
    client_michel.post("/api/auth/login", data={"email": "michel@fraternite.org", "password": "4321"})
    r_notifs = client_michel.get("/api/notifications")
    assert r_notifs.status_code == 200
    notifs = r_notifs.json()
    assert any("Reçu de cotisation" in n["titre"] or "cotisation" in n["type"] for n in notifs)
    print("   -> OK! Le confrère (Père Michel) a bien reçu sa notification instantanée.")

    print("6. Test Ajout d'une Dépense Diverse déduite de la caisse ...")
    caisse_avant = client.get("/api/caisse/resume").json()["avoir_en_caisse"]
    r_dep = client.post("/api/caisse/depenses", data={
        "titre": "Fleurs et encens pour la fête patronale",
        "montant": 3000,
        "date_depense": "2026-09-24",
        "categorie": "Événement & Liturgie",
        "description": "Fête de Saint Jean-Marie Vianney"
    })
    assert r_dep.status_code == 200
    caisse_apres = client.get("/api/caisse/resume").json()["avoir_en_caisse"]
    assert caisse_apres == caisse_avant - 3000
    print(f"   -> OK! Dépense déduite correctement. Caisse passée de {caisse_avant} à {caisse_apres}.")

    print("7. Test Création de compte par l'Économe (mot de passe 4321) ...")
    import time
    test_email = f"barnabe_{int(time.time())}@fraternite.org"
    r_create = client.post("/api/membres", data={
        "nom_prenom": "Père Barnabé Kouamé",
        "email": test_email,
        "telephone": "+225 07 99 88 77 66",
        "date_naissance": "1983-09-26",
        "role": "membre"
    })
    assert r_create.status_code == 200
    assert "4321" in r_create.json()["message"]
    print("   -> OK! Compte créé avec mot de passe 4321.")

    print("8. Test Connexion du nouveau confrère avec 4321 ...")
    client_confrere = TestClient(app)
    r_login_new = client_confrere.post("/api/auth/login", data={"email": test_email, "password": "4321"})
    assert r_login_new.status_code == 200
    assert r_login_new.json()["user"]["must_change_password"] is True
    print("   -> OK! Confrère connecté, invitation au changement de mot de passe active.")

    print("9. Test Téléchargement Rapport PDF ...")
    r_pdf = client.get("/api/rapport/pdf?annee=2026")
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert len(r_pdf.content) > 1000
    print(f"   -> OK! PDF généré, taille: {len(r_pdf.content)} octets.")

    print("10. Test Synthèse WhatsApp ...")
    r_wa = client.get("/api/rapport/whatsapp-texte?annee=2026")
    assert r_wa.status_code == 200
    wa_text = r_wa.json()["texte"]
    assert "POINT FINANCIER" in wa_text
    assert "Avoir net en caisse" in wa_text
    print("   -> OK! Message WhatsApp formaté correctement:")
    print("--------------------------------------------------")
    print(wa_text[:200].encode('ascii', errors='replace').decode('ascii') + "...")
    print("--------------------------------------------------")

    print("11. Test Vérification alertes anniversaires (J-2 et Jour-J) et rappels de début de mois ...")
    r_alertes = client.post("/api/notifications/declencher-rappels")
    assert r_alertes.status_code == 200
    print(f"   -> OK! {r_alertes.json()['message']}")

    print("\n TOUS LES TESTS SONT PASSÉS AVEC SUCCÈS À 100% !")

if __name__ == "__main__":
    run_tests()
