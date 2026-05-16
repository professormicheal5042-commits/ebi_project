// profile.js — EBI Expiry Guard
import { supabase } from '../../shared/js/supabase.js';
import { routeGuard, signOut } from '../auth/auth.js';

async function loadProfile() {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;

  document.getElementById('profileEmail') && (document.getElementById('profileEmail').value = user.email);

  const { data: profile } = await supabase.from('profiles').select('full_name').eq('id', user.id).single();
  if (profile) {
    document.getElementById('profileName') && (document.getElementById('profileName').value = profile.full_name);
    const avatar = document.getElementById('avatarInitial');
    if (avatar) avatar.textContent = profile.full_name.charAt(0).toUpperCase();
  }
}

async function saveProfile() {
  const { data: { user } } = await supabase.auth.getUser();
  const name = document.getElementById('profileName')?.value.trim();
  if (!name) return;

  const { error } = await supabase.from('profiles').update({ full_name: name }).eq('id', user.id);
  const toast = document.getElementById('toast');
  if (toast) {
    toast.textContent = error ? 'Failed to save.' : 'Profile updated!';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  await routeGuard();
  await loadProfile();
  document.getElementById('btnSave')?.addEventListener('click', saveProfile);
  document.getElementById('btnSignOut')?.addEventListener('click', signOut);
});
