import subprocess
import re
import time
import sys
import os

def start_tunnel():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cf_exe = os.path.join(base_dir, "cloudflared.exe")

    if not os.path.exists(cf_exe):
        print("Erreur: cloudflared.exe non trouvé.")
        return

    print("=" * 70)
    print("  OUVERTURE DE L'ACCÈS EN LIGNE (INTERNET) — PAROISSE DE TOTSI")
    print("=" * 70)
    print(" Connexion au réseau mondial sécurisé Cloudflare en cours...")

    cmd = [cf_exe, "tunnel", "--url", "http://localhost:8000"]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    url_found = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    start_time = time.time()
    while time.time() - start_time < 30:
        line = proc.stderr.readline()
        if not line:
            continue
        match = url_pattern.search(line)
        if match:
            url_found = match.group(0)
            break

    if url_found:
        print("\n" + "=" * 70)
        print(" VOTRE APPLICATION EST OFFICIELLEMENT EN LIGNE !")
        print("=" * 70)
        print(f"\n LIEN INTERNET PUBLIC (À ENVOYER DANS LE GROUPE WHATSAPP) :")
        print(f" >>>  {url_found}  <<<\n")
        print(" Chaque confrère prêtre peut ouvrir ce lien sur son smartphone,")
        print(" s'y connecter et cliquer sur 'Ajouter à l'écran d'accueil'.")
        print("=" * 70)
        print(" (Laissez cette fenêtre ouverte pour maintenir l'accès en ligne)")
        print(" Appuyez sur Ctrl+C pour arrêter le partage.")
        print("=" * 70)

        # Maintenir le processus actif
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            proc.terminate()
            print("\nAccès en ligne arrêté.")
    else:
        print("Impossible d'obtenir le lien public. Vérifiez votre connexion Internet.")

if __name__ == "__main__":
    start_tunnel()
