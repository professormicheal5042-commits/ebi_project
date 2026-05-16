// reports.js — EBI Expiry Guard
import { supabase } from '../../shared/js/supabase.js';
import { routeGuard } from '../auth/auth.js';

async function getProducts() {
  const { data, error } = await supabase.from('products').select('*');
  return error ? [] : data;
}

function daysUntilExpiry(expiryDate) {
  const today = new Date(); today.setHours(0,0,0,0);
  return Math.ceil((new Date(expiryDate) - today) / (1000 * 60 * 60 * 24));
}

function renderReportStats(products) {
  const expired  = products.filter(p => daysUntilExpiry(p.expiry_date) < 0);
  const expiring = products.filter(p => { const d = daysUntilExpiry(p.expiry_date); return d >= 0 && d <= 7; });
  const safe     = products.filter(p => daysUntilExpiry(p.expiry_date) > 7);

  const set = (id, val) => { if (document.getElementById(id)) document.getElementById(id).textContent = val; };
  set('reportTotal',    products.length);
  set('reportExpired',  expired.length);
  set('reportExpiring', expiring.length);
  set('reportSafe',     safe.length);
}

function renderReportTable(products) {
  const tbody = document.getElementById('reportTable');
  if (!tbody) return;
  tbody.innerHTML = products.map(p => {
    const days  = daysUntilExpiry(p.expiry_date);
    const status = days < 0 ? 'Expired' : days <= 7 ? 'Expiring Soon' : 'Safe';
    return `
      <tr>
        <td>${p.name}</td>
        <td>${p.category || '—'}</td>
        <td>${p.expiry_date}</td>
        <td>${status}</td>
      </tr>`;
  }).join('');
}

window.addEventListener('DOMContentLoaded', async () => {
  await routeGuard();
  const products = await getProducts();
  renderReportStats(products);
  renderReportTable(products);
});
