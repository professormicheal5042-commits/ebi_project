// auth.js — EBI Expiry Guard
// Handles login, register, sign out, and route protection

import { supabase } from '../../shared/js/supabase.js';

// ─── Register a new user ──────────────────────────────────────────────────
async function signUp(email, password, name) {
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) return { error };

  // Save full name to profiles table
  if (data.user) {
    await supabase.from('profiles').insert({ id: data.user.id, full_name: name });
  }
  return { data };
}

// ─── Log in an existing user ──────────────────────────────────────────────
async function signIn(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  return { data, error };
}

// ─── Log out the current user ─────────────────────────────────────────────
async function signOut() {
  await supabase.auth.signOut();
  window.location.href = '../../module/auth/login.html';
}

// ─── Get the currently logged-in user ────────────────────────────────────
async function getUser() {
  const { data: { user } } = await supabase.auth.getUser();
  return user;
}

// ─── Route Guard: redirect to login if no active session ─────────────────
async function routeGuard() {
  const user = await getUser();
  if (!user) {
    window.location.href = '../../module/auth/login.html';
  }
  return user;
}

// ─── Handle Login form submission ─────────────────────────────────────────
async function handleLogin(event) {
  event.preventDefault();
  const email    = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const { error } = await signIn(email, password);

  if (error) {
    showAuthError(error.message);
  } else {
    window.location.href = '../dashboard/dashboard.html';
  }
}

// ─── Handle Register form submission ─────────────────────────────────────
async function handleRegister(event) {
  event.preventDefault();
  const name     = document.getElementById('fullName').value.trim();
  const email    = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const { error } = await signUp(email, password, name);

  if (error) {
    showAuthError(error.message);
  } else {
    showAuthSuccess('Account created! Check your email to verify.');
  }
}

// ─── Show error/success messages ──────────────────────────────────────────
function showAuthError(msg) {
  const el = document.getElementById('authError');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}
function showAuthSuccess(msg) {
  const el = document.getElementById('authSuccess');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

export { signUp, signIn, signOut, getUser, routeGuard };
