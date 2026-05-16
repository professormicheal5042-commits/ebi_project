// alerts.js — EBI Expiry Guard
// Handles fetching, rendering, and managing alerts

import { supabase } from '../../shared/js/supabase.js';

// ─── Fetch all alerts for the logged-in user ──────────────────────────────
async function getAlerts() {
  const { data, error } = await supabase
    .from('alerts')
    .select('*, products(name)')
    .order('triggered_at', { ascending: false });
  return error ? [] : data;
}

// ─── Mark an alert as read ────────────────────────────────────────────────
async function markAlertRead(id) {
  const { error } = await supabase
    .from('alerts')
    .update({ is_read: true })
    .eq('id', id);
  return error;
}

// ─── Insert a new alert record ────────────────────────────────────────────
async function insertAlertRecord(productId, alertType) {
  const { data: { user } } = await supabase.auth.getUser();
  const { error } = await supabase.from('alerts').insert({
    product_id: productId,
    user_id:    user.id,
    alert_type: alertType,
  });
  return error;
}

// ─── Render alert cards into the DOM ─────────────────────────────────────
function renderAlerts(alerts) {
  const list = document.getElementById('alertsList');
  if (!list) return;

  if (alerts.length === 0) {
    list.innerHTML = `<div class="empty-state">🎉 No alerts right now! All products are safe.</div>`;
    return;
  }

  list.innerHTML = alerts.map(alert => `
    <div class="alert-card ${alert.is_read ? 'read' : ''}" data-id="${alert.id}" onclick="handleAlertClick('${alert.id}', '${alert.product_id}')">
      <span class="alert-badge ${alert.alert_type === 'Expired' ? 'expired' : 'expiring'}">${alert.alert_type}</span>
      <span style="flex:1">${alert.products?.name || 'Unknown Product'}</span>
      <span style="font-size:12px;color:var(--text-muted)">${new Date(alert.triggered_at).toLocaleDateString()}</span>
    </div>
  `).join('');
}

// ─── Handle alert card click (mark read + go to product detail) ──────────
async function handleAlertClick(alertId, productId) {
  await markAlertRead(alertId);
  window.location.href = `../product/product_detail.html?id=${productId}`;
}

// ─── Active filter ────────────────────────────────────────────────────────
let allAlerts = [];

function applyFilter(type) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-filter="${type}"]`)?.classList.add('active');

  if (type === 'all')      renderAlerts(allAlerts);
  else if (type === 'expired')  renderAlerts(allAlerts.filter(a => a.alert_type === 'Expired'));
  else if (type === 'expiring') renderAlerts(allAlerts.filter(a => a.alert_type === 'Expiring Soon'));
  else if (type === 'unread')   renderAlerts(allAlerts.filter(a => !a.is_read));
}

// ─── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  allAlerts = await getAlerts();
  renderAlerts(allAlerts);

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => applyFilter(btn.dataset.filter));
  });
});

window.handleAlertClick = handleAlertClick;
