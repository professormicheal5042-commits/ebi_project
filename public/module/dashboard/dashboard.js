// dashboard.js — EBI Expiry Guard
// Calculates stats and renders the main dashboard

import { supabase } from '../../shared/js/supabase.js';
import { routeGuard } from '../auth/auth.js';

// ─── Fetch all products for the current user ──────────────────────────────
async function getAllProducts() {
  const { data, error } = await supabase
    .from('products')
    .select('*')
    .order('expiry_date', { ascending: true });
  return error ? [] : data;
}

// ─── Calculate how many days until expiry ────────────────────────────────
function daysUntilExpiry(expiryDate) {
  const today  = new Date(); today.setHours(0,0,0,0);
  const expiry = new Date(expiryDate);
  return Math.ceil((expiry - today) / (1000 * 60 * 60 * 24));
}

// ─── Compute summary stats from product list ─────────────────────────────
function getDashboardStats(products) {
  const total    = products.length;
  const expired  = products.filter(p => daysUntilExpiry(p.expiry_date) < 0).length;
  const expiring = products.filter(p => { const d = daysUntilExpiry(p.expiry_date); return d >= 0 && d <= 7; }).length;
  const safe     = total - expired - expiring;
  return { total, expired, expiring, safe };
}

// ─── Return top 5 most urgent products ───────────────────────────────────
function getRecentAlerts(products) {
  return products
    .map(p => ({ ...p, daysLeft: daysUntilExpiry(p.expiry_date) }))
    .filter(p => p.daysLeft <= 7)
    .sort((a, b) => a.daysLeft - b.daysLeft)
    .slice(0, 5);
}

// ─── Render stats cards ───────────────────────────────────────────────────
function renderStats(stats) {
  document.getElementById('statTotal')    && (document.getElementById('statTotal').textContent    = stats.total);
  document.getElementById('statExpired')  && (document.getElementById('statExpired').textContent  = stats.expired);
  document.getElementById('statExpiring') && (document.getElementById('statExpiring').textContent = stats.expiring);
  document.getElementById('statSafe')     && (document.getElementById('statSafe').textContent     = stats.safe);
}

// ─── Render recent alerts list ────────────────────────────────────────────
function renderRecentAlerts(alerts) {
  const list = document.getElementById('recentAlertsList');
  if (!list) return;

  if (alerts.length === 0) {
    list.innerHTML = '<p style="color:var(--text-muted);font-size:14px;">No urgent items. Everything looks good!</p>';
    return;
  }

  list.innerHTML = alerts.map(a => {
    const label  = a.daysLeft < 0 ? 'Expired' : `${a.daysLeft}d left`;
    const color  = a.daysLeft < 0 ? '#ef4444' : '#f59e0b';
    return `
      <div class="alert-row" onclick="window.location.href='../product/product_detail.html?id=${a.id}'">
        <span>${a.name}</span>
        <span style="font-size:13px;font-weight:700;color:${color}">${label}</span>
      </div>`;
  }).join('');
}

// ─── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  await routeGuard();
  const products = await getAllProducts();
  renderStats(getDashboardStats(products));
  renderRecentAlerts(getRecentAlerts(products));
});
