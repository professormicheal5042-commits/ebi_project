// inventory.js — EBI Expiry Guard
// Handles listing, searching, filtering, and deleting products

import { supabase } from '../../shared/js/supabase.js';
import { routeGuard } from '../auth/auth.js';

let allProducts = [];

// ─── Fetch all products for the logged-in user ────────────────────────────
async function getProducts() {
  const { data, error } = await supabase
    .from('products')
    .select('*')
    .order('expiry_date', { ascending: true });
  return error ? [] : data;
}

// ─── Delete a product by ID ───────────────────────────────────────────────
async function deleteProduct(id) {
  const { error } = await supabase.from('products').delete().eq('id', id);
  return error;
}

// ─── Calculate days until expiry ─────────────────────────────────────────
function daysUntilExpiry(expiryDate) {
  const today  = new Date(); today.setHours(0,0,0,0);
  const expiry = new Date(expiryDate);
  return Math.ceil((expiry - today) / (1000 * 60 * 60 * 24));
}

// ─── Get status badge HTML ────────────────────────────────────────────────
function getStatusBadge(daysLeft) {
  if (daysLeft < 0)  return `<span class="status-badge expired">Expired</span>`;
  if (daysLeft <= 7) return `<span class="status-badge expiring">Expiring Soon</span>`;
  return `<span class="status-badge safe">Safe</span>`;
}

// ─── Render rows in the inventory table ──────────────────────────────────
function renderTable(products) {
  const tbody = document.getElementById('inventoryTable');
  const empty = document.getElementById('emptyState');
  if (!tbody) return;

  if (products.length === 0) {
    tbody.innerHTML = '';
    if (empty) empty.style.display = 'block';
    return;
  }
  if (empty) empty.style.display = 'none';

  tbody.innerHTML = products.map(p => {
    const days = daysUntilExpiry(p.expiry_date);
    return `
      <tr>
        <td>${p.name}</td>
        <td>${p.category || '—'}</td>
        <td>${p.quantity} ${p.unit}</td>
        <td>${p.expiry_date}</td>
        <td>${getStatusBadge(days)}</td>
        <td>
          <button onclick="window.location.href='../product/product_detail.html?id=${p.id}'">View</button>
          <button onclick="window.location.href='../add_product/add_product.html?id=${p.id}'">Edit</button>
          <button onclick="handleDelete('${p.id}')">Delete</button>
        </td>
      </tr>`;
  }).join('');
}

// ─── Handle delete with confirmation ─────────────────────────────────────
async function handleDelete(id) {
  if (!confirm('Are you sure you want to delete this product?')) return;
  const error = await deleteProduct(id);
  if (!error) {
    allProducts = allProducts.filter(p => p.id !== id);
    renderTable(allProducts);
  }
}

// ─── Filter products by search and category ───────────────────────────────
function applyFilters() {
  const search   = document.getElementById('searchInput')?.value.toLowerCase() || '';
  const category = document.getElementById('categoryFilter')?.value || '';

  const filtered = allProducts.filter(p => {
    const matchName = p.name.toLowerCase().includes(search);
    const matchCat  = category ? p.category === category : true;
    return matchName && matchCat;
  });
  renderTable(filtered);
}

// ─── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  await routeGuard();
  allProducts = await getProducts();
  renderTable(allProducts);

  document.getElementById('searchInput')?.addEventListener('keyup', applyFilters);
  document.getElementById('categoryFilter')?.addEventListener('change', applyFilters);
});

window.handleDelete = handleDelete;
