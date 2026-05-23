// add_product.js — EBI Expiry Guard
// Handles the Add Product / Edit Product form logic

import { supabase } from '../../shared/js/supabase.js';

// ─── Get product ID from URL (for Edit mode) ───────────────────────────────
function getProductIdFromURL() {
  return new URLSearchParams(window.location.search).get('id');
}

// ─── Pre-fill form when editing an existing product ───────────────────────
async function loadProductForEdit(id) {
  const { data, error } = await supabase
    .from('products')
    .select('*')
    .eq('id', id)
    .single();

  if (error || !data) return;

  document.getElementById('prodName').value      = data.name       || '';
  document.getElementById('prodCategory').value  = data.category   || '';
  document.getElementById('prodQty').value       = data.quantity   || '';
  document.getElementById('prodUnit').value      = data.unit       || 'pcs';
  document.getElementById('prodMfgDate').value   = data.mfg_date   || '';
  document.getElementById('prodExpiryDate').value = data.expiry_date || '';
  document.getElementById('prodNotes').value     = data.notes      || '';
}

// ─── Add a new product ────────────────────────────────────────────────────
async function addProduct(data) {
  const { data: { user } } = await supabase.auth.getUser();
  const { error } = await supabase.from('products').insert({ ...data, user_id: user.id });
  return error;
}

// ─── Update an existing product ───────────────────────────────────────────
async function updateProduct(id, data) {
  const { error } = await supabase.from('products').update(data).eq('id', id);
  return error;
}

// ─── Handle form submission (Add or Update) ───────────────────────────────
async function handleSubmit(event) {
  event.preventDefault();

  const id = getProductIdFromURL();
  const data = {
    name:        document.getElementById('prodName').value,
    category:    document.getElementById('prodCategory').value,
    quantity:    document.getElementById('prodQty').value,
    unit:        document.getElementById('prodUnit').value,
    mfg_date:   document.getElementById('prodMfgDate').value || null,
    expiry_date: document.getElementById('prodExpiryDate').value,
    notes:       document.getElementById('prodNotes').value,
    barcode:     null,
  };

  const error = id ? await updateProduct(id, data) : await addProduct(data);

  if (!error) {
    showToast(id ? 'Product updated!' : 'Product added!');
    setTimeout(() => window.location.href = '../inventory/inventory.html', 1200);
  } else {
    showToast('Error saving product. Please try again.', true);
  }
}

// ─── Show a toast notification ────────────────────────────────────────────
function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.style.background = isError ? '#ef4444' : '#00e676';
  toast.style.color = isError ? '#fff' : '#020c08';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2500);
}

// ─── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  const id = getProductIdFromURL();
  if (id) {
    document.getElementById('pageTitle').textContent = 'Edit Product';
    await loadProductForEdit(id);
  }
  document.getElementById('productForm').addEventListener('submit', handleSubmit);
});
