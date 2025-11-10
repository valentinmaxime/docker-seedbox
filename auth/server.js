'use strict';

/**
 * Minimal password-protected dashboard with Express, sessions, Helmet, and EJS.
 * Cleaned up + translated to English.
 *
 * Notes
 * - Uses a relaxed CSP that allows a tiny inline script/style on the login page.
 *   If you prefer a stricter nonce-based CSP, say the word and I'll swap it in.
 * - Cookie `secure` is enabled automatically in production.
 * - Avoids open redirects by validating the `next` parameter.
 */

const express = require('express');
const session = require('express-session');
const path = require('path');
const bcrypt = require('bcryptjs');
const helmet = require('helmet');

// ────────────────────────────────────────────────────────────────────────────────
// Configuration
// ────────────────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
const AUTH_USERNAME = process.env.AUTH_USERNAME || 'seedbox';
const AUTH_PASSWORD_HASH = process.env.AUTH_PASSWORD_HASH || '';
const AUTH_PASSWORD = process.env.AUTH_PASSWORD || ''; // dev convenience (optional)
const SESSION_SECRET = process.env.AUTH_SESSION_SECRET || 'change_me_secret';
const COOKIE_NAME = process.env.AUTH_SESSION_COOKIE || 'seedbox.sid';
const NODE_ENV = process.env.NODE_ENV || 'development';
const IS_PROD = NODE_ENV === 'production';
const API_TOKENS = (process.env.AUTH_API_TOKENS || '')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);
const API_HEADER_NAME = process.env.AUTH_API_HEADER || 'X-Seedbox-Token';
const API_ALLOWED_PREFIXES = (process.env.AUTH_API_ALLOWED_PREFIXES || '/sonarr,/radarr,/qbittorrent,/api')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);

// ────────────────────────────────────────────────────────────────────────────────
// App
// ────────────────────────────────────────────────────────────────────────────────
const app = express();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.set('trust proxy', 1); // required when running behind a reverse proxy (e.g., Caddy/NGINX)

// Relaxed CSP to allow a tiny inline script/style on the login page
app.use(
  helmet({
    contentSecurityPolicy: {
      useDefaults: true,
      directives: {
        'img-src': ["'self'", 'data:'],
        'script-src': ["'self'", "'unsafe-inline'"],
        'style-src': ["'self'", "'unsafe-inline'"],
      },
    },
    frameguard: { action: 'deny' },
    referrerPolicy: { policy: 'no-referrer' },
  })
);

app.use(express.urlencoded({ extended: false }));

app.use(
  session({
    name: COOKIE_NAME,
    secret: SESSION_SECRET,
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: 'lax',
      secure: IS_PROD, // true in production; relies on trust proxy above
      maxAge: 1000 * 60 * 60 * 8, // 8 hours
    },
  })
);

// ────────────────────────────────────────────────────────────────────────────────
// Auth utilities
// ────────────────────────────────────────────────────────────────────────────────
let passwordHash = AUTH_PASSWORD_HASH; // may be filled at runtime if AUTH_PASSWORD was provided

/**
 * Validate the `next` parameter to prevent open redirects. Only allow absolute paths
 * within this site (e.g., "/", "/static/...").
 */
function sanitizeNext(next) {
  if (typeof next !== 'string') return '/';
  // Allow only same-site absolute paths
  if (next.startsWith('/') && !next.startsWith('//')) return next;
  return '/';
}

function requireAuth(req, res, next) {
  if (req.session && req.session.user === AUTH_USERNAME) return next();
  const target = encodeURIComponent(req.originalUrl || '/');
  return res.redirect('/login?next=' + target);
}

// ────────────────────────────────────────────────────────────────────────────────
// Routes
// ────────────────────────────────────────────────────────────────────────────────
app.get('/login', (req, res) => {
  if (req.session && req.session.user === AUTH_USERNAME) return res.redirect('/');
  const nextUrl = sanitizeNext(req.query.next || '/');
  res.render('login', { error: null, nextUrl });
});

app.post('/login', async (req, res) => {
  const { username, password, next } = req.body || {};
  const nextUrl = sanitizeNext(next || '/');

  if (!username || !password) {
    return res.status(400).render('login', { error: 'Missing fields.', nextUrl });
  }

  if (username !== AUTH_USERNAME) {
    return res.status(401).render('login', { error: 'Invalid credentials.', nextUrl });
  }

  try {
    const ok = passwordHash ? await bcrypt.compare(password, passwordHash) : false;
    if (!ok) {
      return res.status(401).render('login', { error: 'Invalid credentials.', nextUrl });
    }

    req.session.user = AUTH_USERNAME;
    return res.redirect(303, nextUrl); // force GET after redirect
  } catch (err) {
    console.error('[auth] Error during login:', err);
    return res.status(500).render('login', { error: 'Server error.', nextUrl });
  }
});

app.post('/logout', (req, res) => {
  req.session.destroy(() => {
    res.clearCookie(COOKIE_NAME);
    res.redirect('/login');
  });
});

app.post('/', requireAuth, (_req, res) => res.redirect('/'));

// Static files behind auth
app.use('/static', requireAuth, express.static(path.join(__dirname, 'public'), { index: false }));

// Dashboard
app.get('/', requireAuth, (_req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Health
app.get('/healthz', (_req, res) => res.json({ ok: true }));

/**
+ * Endpoint de vérification pour Caddy forward_auth.
+ * - 200 si session valide
+ * - 302 vers /login si non authentifié
+ */
app.get("/authz/verify", (req, res) => {
  const fwd = req.get("X-Forwarded-Uri");
  const meth = req.get("X-Forwarded-Method");
  console.log("[verify]", meth, fwd, "user=", req.session?.user);
  // 1) Auth par header (pour nzb360)
  const token = req.get(API_HEADER_NAME);
  if (token && API_TOKENS.includes(token)) {
    // Optionnel : restreindre aux prefixes autorisés
    const path = (fwd || req.originalUrl || "/").split("?")[0];
    const allowed = API_ALLOWED_PREFIXES.some(p => path.startsWith(p));
    if (allowed) {
      res.set("X-User", "api-token");
      return res.status(200).send("OK");
    }
  }
 
  if (req.session && req.session.user === AUTH_USERNAME) {
    res.set("X-User", AUTH_USERNAME);
    return res.status(200).send("OK");
  }
  const original = fwd || req.originalUrl || "/";
  const next = original.startsWith("/authz") ? "/" : original;
  return res.redirect(302, `/login?next=${encodeURIComponent(next)}`);
});

// ────────────────────────────────────────────────────────────────────────────────
// Bootstrapping
// ────────────────────────────────────────────────────────────────────────────────
(async function bootstrap() {
  try {
    if (!passwordHash && AUTH_PASSWORD) {
      const saltRounds = 12;
      passwordHash = await bcrypt.hash(AUTH_PASSWORD, saltRounds);
      console.log('[auth] Generated password hash from AUTH_PASSWORD env.');
    }

    if (!passwordHash) {
      console.warn('[auth] WARNING: No AUTH_PASSWORD_HASH set (and no AUTH_PASSWORD provided). Login will always fail.');
    }

    app.listen(PORT, () => {
      console.log(`[auth] Listening on :${PORT} (env: ${NODE_ENV})`);
    });
  } catch (err) {
    console.error('[auth] Failed to start:', err);
    process.exit(1);
  }
})();
