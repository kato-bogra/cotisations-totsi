// Application Mobile de Gestion des Cotisations Sacerdotales
let currentUser = null;
let appParams = {
  montant_annuel: 10000,
  devise: 'FCFA',
  nom_groupe: 'Fraternité Sacerdotale',
  annee_active: 2026
};

// --- INITIALISATION ---
document.addEventListener('DOMContentLoaded', async () => {
  initServiceWorker();
  await loadParams();
  await checkAuth();
  await refreshCaisseResume();
  await refreshMonStatut();
  await refreshMembres();
  await refreshNotifications();

  // Vérifier si un token de reset est présent dans l'URL
  const urlParams = new URLSearchParams(window.location.search);
  const resetToken = urlParams.get('reset_token');
  if (resetToken) {
    document.getElementById('reset_token_input').value = resetToken;
    openModal('modal-reset-password');
  }
});

function initServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(err => {
      console.log('SW registration note:', err);
    });
  }
}

// --- GESTION DES TOASTS ---
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  let icon = 'bi-info-circle-fill';
  if (type === 'success') icon = 'bi-check-circle-fill';
  if (type === 'error') icon = 'bi-exclamation-triangle-fill';

  toast.innerHTML = `<i class="bi ${icon}"></i> <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// --- CHARGEMENT DES PARAMÈTRES ---
async function loadParams() {
  try {
    const res = await fetch('/api/parametres');
    if (res.ok) {
      const data = await res.json();
      appParams = { ...appParams, ...data };
      if (appParams.montant_annuel) appParams.montant_annuel = parseFloat(appParams.montant_annuel);
      if (appParams.annee_active) appParams.annee_active = parseInt(appParams.annee_active);
      updateParamsUI();
    }
  } catch (err) {
    console.error('Erreur chargement paramètres:', err);
  }
}

function updateParamsUI() {
  document.querySelectorAll('.app-nom-groupe').forEach(el => el.textContent = appParams.nom_groupe);
  document.querySelectorAll('.app-devise').forEach(el => el.textContent = appParams.devise);
  document.querySelectorAll('.app-montant-annuel').forEach(el => {
    el.textContent = formatMoney(appParams.montant_annuel, appParams.devise);
  });
}

function formatMoney(amount, devise = appParams.devise) {
  if (amount === undefined || amount === null) return '0 ' + devise;
  return Number(amount).toLocaleString('fr-FR') + ' ' + devise;
}

// --- AUTHENTIFICATION ---
async function checkAuth() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.authenticated) {
      currentUser = data.user;
      renderUserUI();
      if (currentUser.must_change_password) {
        showToast("Votre mot de passe actuel est celui par défaut (4321). Veuillez le personnaliser pour des raisons de sécurité.", "info");
      }
    } else {
      currentUser = null;
      renderGuestUI();
    }
  } catch (err) {
    console.error('Erreur vérification auth:', err);
  }
}

function renderUserUI() {
  document.getElementById('guest-actions').style.display = 'none';
  document.getElementById('user-pill-section').style.display = 'flex';
  document.getElementById('user-pill-name').textContent = currentUser.nom_prenom.split(' ')[0] + ' ' + (currentUser.nom_prenom.split(' ')[1] || '');
  
  const avatarEl = document.getElementById('user-pill-avatar');
  if (currentUser.photo_url) {
    avatarEl.innerHTML = `<img src="${currentUser.photo_url}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
  } else {
    avatarEl.textContent = currentUser.nom_prenom.charAt(0);
  }

  // Contrôles spécifiques au rôle
  const isOfficer = (currentUser.role === 'econome' || currentUser.role === 'tresorier');
  document.querySelectorAll('.role-officer-only').forEach(el => {
    el.style.display = isOfficer ? 'block' : 'none';
  });
  document.querySelectorAll('.role-officer-inline').forEach(el => {
    el.style.display = isOfficer ? 'inline-flex' : 'none';
  });

  // Badge de rôle
  const roleBadge = document.getElementById('user-role-badge');
  if (roleBadge) {
    if (currentUser.role === 'econome') roleBadge.textContent = 'Économe';
    else if (currentUser.role === 'tresorier') roleBadge.textContent = 'Trésorier';
    else roleBadge.textContent = 'Prêtre';
  }
}

function renderGuestUI() {
  document.getElementById('guest-actions').style.display = 'flex';
  document.getElementById('user-pill-section').style.display = 'none';
  document.querySelectorAll('.role-officer-only').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.role-officer-inline').forEach(el => el.style.display = 'none');
}

// --- CAISSE & FINANCES (ON APP OPEN) ---
async function refreshCaisseResume() {
  try {
    const res = await fetch(`/api/caisse/resume?annee=${appParams.annee_active}`);
    if (res.ok) {
      const data = await res.json();
      
      // Avoir en caisse central
      document.getElementById('hero-avoir-caisse').textContent = Number(data.avoir_en_caisse).toLocaleString('fr-FR');
      document.getElementById('hero-total-cotisations').textContent = formatMoney(data.total_cotisations_global, data.devise);
      document.getElementById('hero-total-depenses').textContent = formatMoney(data.total_depenses_global, data.devise);
      
      // Statistiques de l'année
      const anneeCards = document.getElementById('annee-stats-box');
      if (anneeCards) {
        document.getElementById('stats-annee-recouvrement').textContent = `${data.taux_recouvrement}%`;
        document.getElementById('stats-annee-a-jour').textContent = `${data.membres_a_jour} / ${data.nombre_membres}`;
      }
    }
  } catch (err) {
    console.error('Erreur chargement résumé caisse:', err);
  }
}

// --- MON STATUT PERSONNEL ---
async function refreshMonStatut() {
  if (!currentUser) return;
  try {
    const res = await fetch(`/api/cotisations/mon-statut?annee=${appParams.annee_active}`);
    if (res.ok) {
      const data = await res.json();
      
      document.getElementById('mon-montant-verse').textContent = formatMoney(data.total_verse, data.devise);
      document.getElementById('mon-reste-a-payer').textContent = formatMoney(data.reste, data.devise);
      
      const percent = Math.min(100, Math.round((data.total_verse / data.montant_annuel) * 100));
      const fillEl = document.getElementById('mon-progress-fill');
      const percentEl = document.getElementById('mon-progress-percent');
      
      fillEl.style.width = `${percent}%`;
      percentEl.textContent = `${percent}%`;

      const badgeEl = document.getElementById('mon-statut-badge');
      if (data.statut === 'A_JOUR') {
        badgeEl.className = 'badge badge-a-jour';
        badgeEl.innerHTML = '<i class="bi bi-check-circle-fill"></i> À Jour';
        fillEl.className = 'progress-bar-fill';
      } else if (data.statut === 'PARTIEL') {
        badgeEl.className = 'badge badge-partiel';
        badgeEl.innerHTML = '<i class="bi bi-clock-history"></i> Partiel';
        fillEl.className = 'progress-bar-fill partial';
      } else {
        badgeEl.className = 'badge badge-en-retard';
        badgeEl.innerHTML = '<i class="bi bi-exclamation-circle-fill"></i> Non réglé';
        fillEl.className = 'progress-bar-fill empty';
      }

      // Historique de mes versements
      const historyList = document.getElementById('mon-historique-versements');
      if (data.versements.length === 0) {
        historyList.innerHTML = `<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;padding:1rem;">Aucun versement enregistré pour l'exercice ${data.annee}.</p>`;
      } else {
        historyList.innerHTML = data.versements.map(v => `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:0.65rem 0;border-bottom:1px solid rgba(51,65,85,0.4);">
            <div>
              <div style="font-weight:600;font-size:0.9rem;color:#fff;">+ ${formatMoney(v.montant, data.devise)}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);">${v.date_paiement} • Mode : <span style="color:#a5b4fc;">${v.mode_paiement}</span></div>
            </div>
            <div style="font-size:0.75rem;color:var(--emerald);font-weight:600;"><i class="bi bi-check2-all"></i> Validé</div>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Erreur chargement mon statut:', err);
  }
}

// --- MEMBRES & CONFRÈRES ---
async function refreshMembres() {
  try {
    const res = await fetch(`/api/membres?annee=${appParams.annee_active}`);
    if (res.ok) {
      const membres = await res.json();
      renderMembresList(membres);
      populateCotisationSelect(membres);
    }
  } catch (err) {
    console.error('Erreur chargement membres:', err);
  }
}

function renderMembresList(membres) {
  const container = document.getElementById('membres-container');
  if (!container) return;

  if (membres.length === 0) {
    container.innerHTML = `<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;">Aucun membre enregistré.</p>`;
    return;
  }

  container.innerHTML = membres.map(m => {
    let statusBadge = '';
    if (m.statut === 'A_JOUR') {
      statusBadge = '<span class="badge badge-a-jour"><i class="bi bi-check-circle-fill"></i> À jour</span>';
    } else if (m.statut === 'PARTIEL') {
      statusBadge = `<span class="badge badge-partiel"><i class="bi bi-hourglass-split"></i> Reste ${formatMoney(m.reste)}</span>`;
    } else {
      statusBadge = '<span class="badge badge-en-retard"><i class="bi bi-exclamation-circle-fill"></i> Non réglé</span>';
    }

    // Alerte anniversaire
    let bdayBadge = '';
    if (m.prochain_anniv_jours !== null) {
      if (m.prochain_anniv_jours === 0) {
        bdayBadge = `<span class="bday-alert-badge today"><i class="bi bi-balloon-fill"></i> Anniversaire Aujourd'hui !</span>`;
      } else if (m.prochain_anniv_jours === 2) {
        bdayBadge = `<span class="bday-alert-badge"><i class="bi bi-clock"></i> Anniversaire dans 2 jours !</span>`;
      } else if (m.prochain_anniv_jours < 7) {
        bdayBadge = `<span style="font-size:0.7rem;color:var(--gold);"><i class="bi bi-gift"></i> Dans ${m.prochain_anniv_jours} j</span>`;
      }
    }

    // Statut de validation de compte
    let verificationBadge = '';
    const isOfficer = currentUser && (currentUser.role === 'econome' || currentUser.role === 'tresorier');
    if (m.is_verified === 0 || m.is_verified === false) {
      verificationBadge = `
        <div style="margin-top:0.35rem;">
          <span class="badge" style="background:#ef4444;color:#fff;font-size:0.68rem;padding:2px 6px;">
            <i class="bi bi-shield-exclamation"></i> En attente de validation
          </span>
          ${isOfficer ? `
            <button onclick="validerCompteMembre(${m.id}, '${m.nom_prenom.replace(/'/g, "\\'")}')" class="btn btn-outline" style="font-size:0.68rem;padding:2px 8px;margin-top:0.3rem;color:#10b981;border-color:#10b981;display:inline-flex;align-items:center;gap:3px;">
              <i class="bi bi-check-circle"></i> Activer le compte
            </button>
          ` : ''}
        </div>
      `;
    }

    const avatarHtml = m.photo_url 
      ? `<img src="${m.photo_url}" class="member-avatar">`
      : `<div class="member-avatar">${m.nom_prenom.charAt(0)}</div>`;

    return `
      <div class="member-card">
        <div class="member-left">
          ${avatarHtml}
          <div class="member-info">
            <h4>${m.nom_prenom}</h4>
            <div class="member-details">
              ${m.telephone ? `<span><i class="bi bi-telephone"></i> ${m.telephone}</span>` : ''}
              ${m.date_naissance ? `<span><i class="bi bi-calendar-heart"></i> ${formatDateFr(m.date_naissance)}</span>` : ''}
              ${bdayBadge}
              ${verificationBadge}
            </div>
          </div>
        </div>
        <div class="member-right">
          <div class="member-amount">${formatMoney(m.total_verse)}</div>
          ${statusBadge}
        </div>
      </div>
    `;
  }).join('');
}

function formatDateFr(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}`;
  return dateStr;
}

function populateCotisationSelect(membres) {
  const select = document.getElementById('cotisation-user-select');
  if (!select) return;
  select.innerHTML = '<option value="">-- Sélectionner un confrère --</option>' +
    membres.map(m => `<option value="${m.id}">${m.nom_prenom} (Versé: ${formatMoney(m.total_verse)})</option>`).join('');
}

// --- DÉPENSES ---
async function refreshDepenses() {
  try {
    const res = await fetch('/api/caisse/depenses');
    if (res.ok) {
      const depenses = await res.json();
      const container = document.getElementById('depenses-container');
      if (!container) return;

      if (depenses.length === 0) {
        container.innerHTML = `<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;padding:1rem;">Aucune dépense enregistrée.</p>`;
        return;
      }

      container.innerHTML = depenses.map(d => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:0.75rem 0;border-bottom:1px solid rgba(51,65,85,0.4);">
          <div>
            <div style="font-weight:600;font-size:0.9rem;color:#fff;">${d.titre}</div>
            <div style="font-size:0.75rem;color:var(--text-muted);">${d.date_depense} • <span style="color:#fca5a5;">${d.categorie}</span> ${d.description ? `• ${d.description}` : ''}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:0.95rem;font-weight:700;color:var(--rose);">- ${formatMoney(d.montant)}</div>
            ${currentUser && (currentUser.role === 'econome' || currentUser.role === 'tresorier') ? `
              <button onclick="supprimerDepense(${d.id})" style="background:none;border:none;color:#64748b;font-size:0.75rem;cursor:pointer;">Supprimer</button>
            ` : ''}
          </div>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Erreur chargement dépenses:', err);
  }
}

async function supprimerDepense(id) {
  if (!confirm("Voulez-vous vraiment supprimer cette dépense ? La somme sera réintégrée dans la caisse.")) return;
  try {
    const res = await fetch(`/api/caisse/depenses/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast("Dépense supprimée avec succès.", "success");
      await refreshCaisseResume();
      await refreshDepenses();
    }
  } catch (err) {
    showToast("Erreur lors de la suppression.", "error");
  }
}

// --- NOTIFICATIONS ---
async function refreshNotifications() {
  if (!currentUser) return;
  try {
    const res = await fetch('/api/notifications');
    if (res.ok) {
      const notifs = await res.json();
      renderNotificationsUI(notifs);
    }
  } catch (err) {
    console.error('Erreur chargement notifications:', err);
  }
}

function renderNotificationsUI(notifs) {
  const container = document.getElementById('notifications-container');
  const badgeCounter = document.getElementById('unread-notifs-badge');
  const unreadCount = notifs.filter(n => !n.is_read).length;

  if (unreadCount > 0) {
    badgeCounter.textContent = unreadCount;
    badgeCounter.style.display = 'flex';
  } else {
    badgeCounter.style.display = 'none';
  }

  if (!container) return;

  if (notifs.length === 0) {
    container.innerHTML = `<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;padding:2rem;">Aucune notification pour le moment.</p>`;
    return;
  }

  container.innerHTML = notifs.map(n => {
    let iconClass = 'notif-icon systeme';
    let icon = 'bi-bell-fill';

    if (n.type.includes('anniversaire')) {
      iconClass = 'notif-icon bday';
      icon = 'bi-balloon-heart-fill';
    } else if (n.type === 'cotisation') {
      iconClass = 'notif-icon cotisation';
      icon = 'bi-cash-coin';
    } else if (n.type === 'rappel_mensuel') {
      iconClass = 'notif-icon rappel';
      icon = 'bi-calendar-event';
    } else if (n.type === 'depense') {
      iconClass = 'notif-icon depense';
      icon = 'bi-wallet2';
    }

    return `
      <div class="notif-card ${n.is_read ? '' : 'unread'}">
        <div class="${iconClass}">
          <i class="bi ${icon}"></i>
        </div>
        <div class="notif-body">
          <h4>${n.titre}</h4>
          <p>${n.message}</p>
          <div class="notif-time">${formatDateRelative(n.created_at)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function formatDateRelative(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

async function markNotificationsRead() {
  try {
    await fetch('/api/notifications/marquer-lues', { method: 'POST' });
    await refreshNotifications();
  } catch (err) {}
}

async function triggerManualReminders() {
  try {
    showToast("Vérification des alertes en cours...", "info");
    const res = await fetch('/api/notifications/declencher-rappels', { method: 'POST' });
    const data = await res.json();
    showToast(data.message, "success");
    await refreshNotifications();
  } catch (err) {
    showToast("Erreur lors de la vérification.", "error");
  }
}

// --- PDF & WHATSAPP SHARING ---
function telechargerPDF() {
  window.location.href = `/api/rapport/pdf?annee=${appParams.annee_active}`;
}

async function partagerWhatsApp() {
  try {
    const res = await fetch(`/api/rapport/whatsapp-texte?annee=${appParams.annee_active}`);
    const data = await res.json();
    const texteEncode = encodeURIComponent(data.texte);

    // Si supporté sur téléphone mobile, tenter navigator.share ou rediriger vers WhatsApp
    if (navigator.share && /mobile/i.test(navigator.userAgent)) {
      navigator.share({
        title: `${appParams.nom_groupe} - Point Cotisations`,
        text: data.texte,
      }).catch(() => {
        window.open(`https://api.whatsapp.com/send?text=${texteEncode}`, '_blank');
      });
    } else {
      window.open(`https://api.whatsapp.com/send?text=${texteEncode}`, '_blank');
    }
  } catch (err) {
    showToast("Impossible de préparer le partage WhatsApp", "error");
  }
}

// --- MODALES & INTERACTIONS ---
function openModal(id) {
  document.getElementById(id).classList.add('active');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}

// Changer d'onglet (Navigation Mobile)
function switchTab(viewId, navBtn) {
  document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  document.getElementById(viewId).classList.add('active');
  if (navBtn) navBtn.classList.add('active');

  if (viewId === 'view-caisse') refreshDepenses();
  if (viewId === 'view-notifications') markNotificationsRead();
  if (viewId === 'view-confreres') refreshMembres();
  if (viewId === 'view-mon-compte') refreshMonStatut();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// --- GESTION DES FORMULAIRES ---

// 1. Connexion
async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/auth/login', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast("Connexion réussie !", "success");
      closeModal('modal-login');
      form.reset();
      await checkAuth();
      await refreshMonStatut();
      await refreshCaisseResume();
    } else {
      if (data.not_verified && data.validation_url) {
        closeModal('modal-login');
        document.getElementById('val-notice-title').textContent = "Compte en attente de validation";
        document.getElementById('val-notice-msg').textContent = "Votre compte n'a pas encore été activé. Vous pouvez l'activer immédiatement en cliquant sur le bouton ci-dessous :";
        const actionBox = document.getElementById('val-notice-action');
        const actionBtn = document.getElementById('val-notice-btn');
        actionBox.style.display = 'block';
        actionBtn.href = data.validation_url;
        openModal('modal-validation-notice');
      } else {
        showToast(data.message || "Erreur de connexion", "error");
      }
    }
  } catch (err) {
    showToast("Erreur de connexion réseau", "error");
  }
}

// 2. Inscription Autonome
async function handleRegister(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/auth/register', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      closeModal('modal-register');
      form.reset();

      document.getElementById('val-notice-title').textContent = "Compte Créé avec Succès !";
      document.getElementById('val-notice-msg').textContent = data.message;
      const actionBox = document.getElementById('val-notice-action');
      const actionBtn = document.getElementById('val-notice-btn');

      if (data.validation_url && !data.email_sent) {
        actionBox.style.display = 'block';
        actionBtn.href = data.validation_url;
      } else {
        actionBox.style.display = 'none';
      }

      openModal('modal-validation-notice');
    } else {
      showToast(data.message || "Erreur lors de l'inscription", "error");
    }
  } catch (err) {
    showToast("Erreur lors de la création du compte", "error");
  }
}

// 3. Mot de passe oublié
async function handleForgotPassword(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/auth/forgot-password', { method: 'POST', body: formData });
    const data = await res.json();
    closeModal('modal-forgot');
    form.reset();

    if (data.reset_url && !data.email_sent) {
      document.getElementById('val-notice-title').textContent = "Réinitialisation du Mot de Passe";
      document.getElementById('val-notice-msg').textContent = data.message;
      const actionBox = document.getElementById('val-notice-action');
      const actionBtn = document.getElementById('val-notice-btn');
      actionBox.style.display = 'block';
      actionBtn.textContent = "Changer mon mot de passe";
      actionBtn.href = data.reset_url;
      openModal('modal-validation-notice');
    } else {
      showToast(data.message, "info");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 4. Réinitialisation mot de passe
async function handleResetPassword(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/auth/reset-password', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, "success");
      closeModal('modal-reset-password');
      form.reset();
      openModal('modal-login');
    } else {
      showToast(data.message, "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 5. Ajout Cotisation (Économe)
async function handleAddCotisation(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/cotisations', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast("Cotisation enregistrée ! Le confrère a reçu instantanément sa notification.", "success");
      closeModal('modal-add-cotisation');
      form.reset();
      await refreshCaisseResume();
      await refreshMembres();
      await refreshMonStatut();
      await refreshNotifications();
    } else {
      showToast(data.message || "Erreur enregistrement cotisation", "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 6. Ajout Dépense (Trésorier / Économe)
async function handleAddDepense(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/caisse/depenses', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast("Dépense enregistrée et déduite de la caisse avec succès.", "success");
      closeModal('modal-add-depense');
      form.reset();
      await refreshCaisseResume();
      await refreshDepenses();
      await refreshNotifications();
    } else {
      showToast(data.message || "Erreur enregistrement dépense", "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 7. Création de compte par l'Économe (Mot de passe 4321)
async function handleCreateMember(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/membres', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, "success");
      closeModal('modal-create-member');
      form.reset();
      await refreshMembres();
      await refreshCaisseResume();
    } else {
      showToast(data.message || "Erreur création compte confrère", "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 8. Changement mot de passe
async function handleChangePassword(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/auth/change-password', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast("Mot de passe mis à jour avec succès !", "success");
      closeModal('modal-change-password');
      form.reset();
      if (currentUser) currentUser.must_change_password = false;
    } else {
      showToast(data.message || "Erreur mot de passe", "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// 9. Mise à jour paramètres
async function handleSaveSettings(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  try {
    const res = await fetch('/api/parametres', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok) {
      showToast("Paramètres enregistrés avec succès.", "success");
      await loadParams();
      await refreshCaisseResume();
    }
  } catch (err) {
    showToast("Erreur sauvegarde paramètres", "error");
  }
}

// 10. Déconnexion
async function handleLogout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  currentUser = null;
  renderGuestUI();
  showToast("Vous avez été déconnecté.", "info");
  await refreshCaisseResume();
}

// --- BOÎTE D'ENVOI DES E-MAILS (SIMULATION / LOCAL INSPECTOR) ---
async function openOutbox() {
  try {
    const res = await fetch('/api/emails-sortants');
    if (res.ok) {
      const emails = await res.json();
      const container = document.getElementById('outbox-container');
      if (emails.length === 0) {
        container.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:1rem;">Aucun e-mail dans la boîte d'envoi.</p>`;
      } else {
        container.innerHTML = emails.map(em => `
          <div style="background:#0f172a;border:1px solid var(--card-border);border-radius:8px;padding:0.85rem;margin-bottom:0.75rem;">
            <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
              <span style="font-weight:700;color:var(--gold);font-size:0.8rem;">À : ${em.destinataire}</span>
              <span style="font-size:0.7rem;color:var(--text-muted);">${formatDateRelative(em.created_at)}</span>
            </div>
            <div style="font-weight:600;font-size:0.85rem;color:#fff;margin-bottom:0.4rem;">${em.sujet}</div>
            <div style="background:#1e293b;padding:0.6rem;border-radius:6px;font-size:0.78rem;color:#cbd5e1;max-height:120px;overflow-y:auto;">
              ${em.corps_html}
            </div>
          </div>
        `).join('');
      }
      openModal('modal-outbox');
    }
  } catch (err) {
    console.error('Erreur outbox:', err);
  }
}

// Aperçu photo de profil en direct
function previewImage(input, previewImgId) {
  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = function(e) {
      const img = document.getElementById(previewImgId);
      img.src = e.target.result;
      img.style.display = 'block';
    };
    reader.readAsDataURL(input.files[0]);
  }
}

// Validation d'un confrère en 1 clic par l'Économe
async function validerCompteMembre(userId, nomPrenom) {
  if (!confirm(`Confirmez-vous l'activation et la validation immédiate du compte de ${nomPrenom} ?`)) return;
  try {
    const res = await fetch(`/api/membres/${userId}/valider`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, "success");
      await refreshMembres();
      await refreshCaisseResume();
    } else {
      showToast(data.message || "Erreur lors de la validation", "error");
    }
  } catch (err) {
    showToast("Erreur réseau", "error");
  }
}

// Test d'envoi d'e-mail SMTP
async function testSmtpEmail() {
  const email = prompt("Entrez l'adresse e-mail qui doit recevoir l'e-mail de test :", (currentUser && currentUser.email) ? currentUser.email : "katoespoir@gmail.com");
  if (!email || !email.includes('@')) return;
  showToast("Envoi de l'e-mail de test en cours...", "info");
  try {
    const formData = new FormData();
    formData.append("destinataire", email.trim());
    const res = await fetch('/api/parametres/test-email', { method: 'POST', body: formData });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, "success");
    } else {
      showToast(data.message || "Erreur envoi test", "warning");
    }
  } catch (err) {
    showToast("Erreur réseau lors du test d'envoi", "error");
  }
}
