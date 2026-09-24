import uvicorn
import socket

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 8000
    print("=" * 65)
    print("  APPLICATION DE GESTION DES COTISATIONS SACERDOTALES")
    print("=" * 65)
    print(f" Accès sur cet ordinateur : http://localhost:{port}")
    print(f" Accès depuis votre smartphone : http://{local_ip}:{port}")
    print("=" * 65)
    print(" Identifiants de démonstration :")
    print("  - Économe   : econome@fraternite.org   / MDP: 4321")
    print("  - Trésorier : tresorier@fraternite.org / MDP: 4321")
    print("  - Confrères : michel@fraternite.org    / MDP: 4321")
    print("=" * 65)
    
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
