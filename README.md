# ⛪ Application de Gestion des Cotisations Sacerdotales & Caisse

Application mobile (PWA) et web spécialement conçue pour une fraternité / groupe de prêtres afin de gérer les cotisations annuelles (10 000 FCFA), la caisse commune, les dépenses, les alertes d'anniversaires (J-2 et Jour-J), et les rapports financiers WhatsApp / PDF.

---

## 🌟 Fonctionnalités Clés

1. **Avoir en Caisse visible à l'ouverture** :
   - Dès le lancement, affichage immédiat et mis en évidence de l'**Avoir net disponible en caisse**.
   - Calcul automatique : `Avoir = Total Cotisations Encaissées - Dépenses Diverses Déduites`.

2. **Espace Personnel de chaque Confrère** :
   - Cotisation annuelle fixée à **10 000** (personnalisable).
   - Jauge de progression visuelle, montant déjà versé et reste à payer.
   - Historique complet des reçus et modes de versement (Espèces, Wave, Orange Money, Moov, Virement, etc.).

3. **Rôle de l'Économe & du Trésorier** :
   - **Enregistrement des cotisations** : dès qu'une cotisation est saisie, le confrère reçoit **aussitôt une notification** sur son téléphone et un e-mail de reçu.
   - **Enregistrement des dépenses diverses** : déduites instantanément du solde de la caisse avec motif, montant, catégorie et reçu/justificatif.
   - **Création de comptes assistée** : pour les prêtres qui ont des difficultés avec la technologie, avec le **mot de passe par défaut fixé à `4321`** (avec invitation à le changer).
   - **Génération du Rapport PDF** : document officiel ReportLab soigné avec tableau de tous les prêtres, statuts (À jour, Partiel, Non réglé), totaux et signatures.
   - **Partage WhatsApp direct** : bouton pour partager la synthèse financière formatée en un clic dans le groupe WhatsApp des prêtres.

4. **Système de Notifications Intelligentes** :
   - **Rappel mensuel (1er du mois)** : émet automatiquement un rappel fraternel à tous les confrères qui ne sont pas en règle.
   - **Alertes Anniversaires** :
     - À **2 jours de l'anniversaire** d'un confrère : tous les membres reçoivent une alerte pour porter leur frère en prière.
     - Le **Jour-J** : tous les membres reçoivent la notification de fête avec lien pour souhaiter un bon anniversaire sur WhatsApp.

5. **Gestion des Comptes & Sécurité** :
   - Inscription autonome possible avec nom, e-mail, **date de naissance** (pour le calendrier des anniversaires), téléphone et **photo de profil optionnelle**.
   - **Validation de compte par e-mail** à l'ouverture.
   - **Mot de passe oublié** : redirection par e-mail avec un lien sécurisé valide 1 heure pour réinitialiser le mot de passe.
   - Boîte de sortie d'e-mails intégrée (consultable dans l'app) permettant de tester et valider sans configuration SMTP préalable.

6. **Application Mobile (PWA)** :
   - Interface optimisée pour smartphone (iPhone & Android) avec barre de navigation en bas d'écran.
   - Installable directement sur l'écran d'accueil du téléphone (*« Ajouter à l'écran d'accueil »*).

---

## 🚀 Démarrage Rapide

### 1. Lancement sous Windows
Double-cliquez sur **`lancer_application.bat`** ou lancez dans le terminal :
```powershell
python run.py
```

### 2. Accès à l'application
- **Depuis votre ordinateur** : [http://localhost:8000](http://localhost:8000)
- **Depuis les smartphones des prêtres (sur le même Wi-Fi)** : `http://<IP_DE_VOTRE_PC>:8000`

---

## 🔑 Comptes de Démonstration Préconfigurés

| Confrère | Rôle | Adresse E-mail | Mot de passe |
| :--- | :--- | :--- | :--- |
| **Père Jean-Baptiste** | Économe | `econome@fraternite.org` | `4321` |
| **Père Paul-Marie** | Trésorier | `tresorier@fraternite.org` | `4321` |
| **Père Michel** | Confrère | `michel@fraternite.org` | `4321` |
| **Père Joseph** | Confrère | `joseph@fraternite.org` | `4321` |
| **Père Antoine** | Confrère | `antoine@fraternite.org` | `4321` |
