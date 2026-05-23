// supabase.js — EBI Expiry Guard
// Shared Supabase client — imported by all modules

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SUPABASE_URL = 'https://eeoizguvordycgvrlymh.supabase.co';
const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlb2l6Z3V2b3JkeWNndnJseW1oIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg3NDkwOTYsImV4cCI6MjA5NDMyNTA5Nn0.J2XZ6TtGcRTM4O9efSoCKUiNy31A6WKlBP5U6j_0ouA';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON);
