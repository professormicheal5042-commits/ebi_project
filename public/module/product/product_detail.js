// product_detail.js — EBI Expiry Guard
import { supabase } from '../../shared/js/supabase.js';
import { routeGuard } from '../auth/auth.js';

function getProductIdFromURL() {
  return new URLSearchParams(window.location.search).get('id');
}

async function getProductById(id) {
  const { data, error } = await supabase.from('products').select('*').eq('id', id).single();
  return error ? null : data;
}

async function deleteProduct(id) {
  const { error } = await supabase.from('products').delete().eq('id', id);
  return error;
}

function daysUntilExpiry(expiryDate) {
  const today = new Date(); today.setHours(0,0,0,0);
  return Math.ceil((new Date(expiryDate) - today) / (1000 * 60 * 60 * 24));
}

function renderProduct(product) {
  const set = (id, val) => { if (document.getElementById(id)) document.getElementById(id).textContent = val; };
  set('prodName',     product.name);
  set('prodCategory', product.category || '—');
  set('prodQuantity', `${product.quantity} ${product.unit}`);
  set('prodMfgDate',  product.mfg_date || '—');
  set('prodExpiry',   product.expiry_date);
  set('prodNotes',    product.notes || '—');

  const daysLeft = daysUntilExpiry(product.expiry_date);
  const banner = document.getElementById('statusBanner');
  if (banner) {
    if (daysLeft < 0)       { banner.className = 'status-banner expired';  banner.textContent = `Expired ${Math.abs(daysLeft)} days ago`; }
    else if (daysLeft <= 7) { banner.className = 'status-banner expiring'; banner.textContent = `Expiring in ${daysLeft} day(s)`; }
    else                    { banner.className = 'status-banner safe';     banner.textContent = `Safe — ${daysLeft} days remaining`; }
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  await routeGuard();
  const id = getProductIdFromURL();
  if (!id) { window.location.href = '../inventory/inventory.html'; return; }
  const product = await getProductById(id);
  if (!product) { window.location.href = '../inventory/inventory.html'; return; }
  renderProduct(product);
  document.getElementById('btnEdit')?.addEventListener('click', () => {
    window.location.href = `../add_product/add_product.html?id=${id}`;
  });
  document.getElementById('btnDelete')?.addEventListener('click', async () => {
    if (!confirm('Delete this product permanently?')) return;
    const error = await deleteProduct(id);
    if (!error) window.location.href = '../inventory/inventory.html';
  });
});
