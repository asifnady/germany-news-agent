// Germany News — internal WLAN reader (zero-dep Node, mirrors running-dashboard pattern)
//
//   GET  /                         → page (web/public/index.html)
//   GET  /api/days                 → { days: ["YYYY-MM-DD", ...], latest }
//   GET  /api/news?date=YYYY-MM-DD → day JSON + per-article translation state
//   POST /api/translate {date,id}  → enqueue full DE→EN translation job
//   GET  /api/translate?date=&id=  → { status, progress, error?, text? }
//   GET  /api/health               → { ok, queue }
//
// One translation runs at a time (politeness to free endpoints). Finished
// translations are cached to disk, so tapping an article twice is instant.

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const DATA = path.join(ROOT, 'data');
const NEWS_DIR = path.join(DATA, 'news');
const TR_DIR = path.join(DATA, 'translations');
const JOBS_PATH = path.join(DATA, 'jobs.json');
const REPO = path.join(ROOT, '..');
const PY = path.join(REPO, '.venv', 'Scripts', 'python.exe');
const SUMMARIZE = path.join(REPO, 'summarize.py');
const PORT = Number(process.env.PORT || 8090);
const JOB_TIMEOUT_MS = 25 * 60 * 1000;

function readJson(p, dflt) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return dflt; }
}
function writeJson(p, o) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(o));
}
function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(body);
}

// --- Jobs -------------------------------------------------------------
const jobs = readJson(JOBS_PATH, {});   // key "date_id" → job
const queue = [];                        // keys waiting to run
let pumping = false;

function saveJobs() { writeJson(JOBS_PATH, jobs); }

function jobKey(date, id) { return `${date}_${id}`; }

function trFile(key) { return path.join(TR_DIR, `${key}.json`); }

function translationExists(key) { return fs.existsSync(trFile(key)); }

function trState(date, id) {
  const key = jobKey(date, id);
  if (translationExists(key)) return { status: 'done' };
  const job = jobs[key];
  if (job) return { status: job.status, progress: job.progress || null, error: job.error || null };
  return { status: 'none' };
}

function runTranslate(job) {
  return new Promise((resolve, reject) => {
    const child = spawn(PY, [SUMMARIZE, job.url, 'translate'], {
      cwd: REPO,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    });
    let out = '', errTail = '';
    const timer = setTimeout(() => {
      try { child.kill(); } catch {}
      reject(new Error('Timed out after 25 minutes'));
    }, JOB_TIMEOUT_MS);
    child.stdout.on('data', (d) => { out += d.toString('utf8'); });
    child.stderr.on('data', (d) => {
      errTail = (errTail + d.toString('utf8')).slice(-3000);
      const lines = errTail.split(/\r?\n/).filter(Boolean);
      if (lines.length) { job.progress = lines[lines.length - 1].trim(); saveJobs(); }
    });
    child.on('error', (e) => { clearTimeout(timer); reject(e); });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const tail = errTail.split(/\r?\n/).filter(Boolean).slice(-3).join(' | ');
        reject(new Error(tail || `translation script exited with code ${code}`));
        return;
      }
      const lines = out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      const p = lines[lines.length - 1]; // summarize.py prints the .txt path last
      if (!p || !fs.existsSync(p)) { reject(new Error('Translation finished but output file missing')); return; }
      let text;
      try { text = fs.readFileSync(p, 'utf8'); } catch (e) { reject(e); return; }
      try { fs.unlinkSync(p); } catch {}
      writeJson(trFile(job.key), {
        date: job.date, id: job.id, url: job.url,
        title: job.title || '', text, fetchedAt: new Date().toISOString(),
      });
      job.progress = 'Done';
      resolve();
    });
  });
}

async function pump() {
  if (pumping) return;
  pumping = true;
  while (queue.length) {
    const key = queue.shift();
    const job = jobs[key];
    if (!job) continue;
    job.status = 'running';
    job.startedAt = new Date().toISOString();
    job.progress = 'Starting…';
    saveJobs();
    try {
      await runTranslate(job);
      job.status = 'done';
    } catch (e) {
      job.status = 'error';
      job.error = String((e && e.message) || e);
    }
    job.finishedAt = new Date().toISOString();
    saveJobs();
    console.log(`[translate] ${key} → ${job.status}${job.error ? ': ' + job.error : ''}`);
  }
  pumping = false;
}

function enqueue(date, id, url, title) {
  const key = jobKey(date, id);
  jobs[key] = { key, date, id, url, title: title || '', status: 'queued', createdAt: new Date().toISOString(), progress: 'Queued' };
  saveJobs();
  queue.push(key);
  pump();
}

// Recover after restart: half-finished jobs are dead, cached ones survive.
for (const key of Object.keys(jobs)) {
  const j = jobs[key];
  if (j.status === 'queued' || j.status === 'running') {
    j.status = 'error';
    j.error = 'Interrupted by server restart — tap again.';
  }
}
saveJobs();

// --- Helpers -----------------------------------------------------------
function validDate(s) { return /^\d{4}-\d{2}-\d{2}$/.test(s || ''); }

function dayPayload(date) {
  const file = path.join(NEWS_DIR, `${date}.json`);
  if (!fs.existsSync(file)) return null;
  const day = readJson(file, null);
  if (!day) return null;
  for (const sec of day.sections || []) {
    for (const a of sec.articles || []) a.tr = trState(date, a.id);
  }
  return day;
}

function findArticle(date, id) {
  const day = dayPayload(date);
  if (!day) return null;
  for (const sec of day.sections || []) {
    const a = (sec.articles || []).find((x) => x.id === id);
    if (a) return a;
  }
  return null;
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > (limit || 1e6)) { reject(new Error('body too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => {
      try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}); }
      catch (e) { reject(new Error('invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

// --- Static + routing ---------------------------------------------------
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
};

function lanUrl() {
  const ifaces = os.networkInterfaces();
  for (const name of Object.keys(ifaces)) {
    for (const a of ifaces[name] || []) {
      if (a.family === 'IPv4' && !a.internal && a.address.startsWith('192.168.')) return `http://${a.address}:${PORT}`;
    }
  }
  return `http://localhost:${PORT}`;
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const p = u.pathname;

  try {
    if (p === '/api/days') {
      let days = [];
      try { days = fs.readdirSync(NEWS_DIR).filter((f) => f.endsWith('.json')).map((f) => f.slice(0, 10)).sort().reverse(); } catch {}
      return send(res, 200, { days, latest: days[0] || null });
    }

    if (p === '/api/news') {
      const date = validDate(u.searchParams.get('date')) ? u.searchParams.get('date') : null;
      if (!date) return send(res, 400, { error: 'missing/invalid ?date=YYYY-MM-DD' });
      const day = dayPayload(date);
      return day ? send(res, 200, day) : send(res, 404, { error: 'no news file for that date' });
    }

    if (p === '/api/translate' && req.method === 'GET') {
      const date = u.searchParams.get('date'), id = u.searchParams.get('id');
      if (!validDate(date) || !/^\d+$/.test(id || '')) return send(res, 400, { error: 'bad params' });
      const st = trState(date, id);
      if (st.status === 'done') {
        const t = readJson(trFile(jobKey(date, id)), null);
        return send(res, 200, { status: 'done', progress: 'Done', text: t ? t.text : '' });
      }
      return send(res, 200, st);
    }

    if (p === '/api/translate' && req.method === 'POST') {
      const body = await readBody(req);
      const { date, id } = body;
      if (!validDate(date) || !/^\d+$/.test(String(id))) return send(res, 400, { error: 'bad body' });
      const art = findArticle(date, id);
      if (!art) return send(res, 404, { error: 'article not found for that date/id' });
      const st = trState(date, id);
      if (st.status === 'done') return send(res, 200, { status: 'done' });
      if (st.status === 'queued' || st.status === 'running') return send(res, 200, st);
      // 'none' or previous 'error' → (re)enqueue
      enqueue(date, id, art.url, art.title);
      console.log(`[translate] queued ${date}_${id} (${art.source})`);
      return send(res, 200, { status: 'queued' });
    }

    if (p === '/api/health') {
      const running = Object.values(jobs).filter((j) => j.status === 'running').length;
      return send(res, 200, { ok: true, queueLength: queue.length, running, uptimeSec: Math.round(process.uptime()) });
    }

    // static
    const rel = p === '/' ? '/index.html' : p;
    let file = path.normalize(path.join(PUBLIC, rel));
    if (!file.startsWith(PUBLIC)) return send(res, 403, { error: 'forbidden' });
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('Not found');
    }
    const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache' });
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    send(res, 500, { error: String((e && e.message) || e) });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Germany News web server running: ${lanUrl()}`);
});
