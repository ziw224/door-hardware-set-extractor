const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const ROOT = '/Users/zihanwang/Desktop/fresco-coding-challenge';
const OUT_DIR = path.join(ROOT, 'out');
const CORRECTIONS_DIR = path.join(OUT_DIR, 'corrections');
const UI_DIR = path.join(ROOT, 'ui');

const ALLOWED_FILES = [
  'bridgeport_hw_schedule.json',
  'bridgeport_hw_schedule_rev0.json',
  'jcryan_087100.json',
  'hfh_087100.json',
];

function sendJson(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload));
}

function sendText(res, status, text, contentType = 'text/plain; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': contentType });
  res.end(text);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > 50 * 1024 * 1024) {
        reject(new Error('Request body too large'));
      }
    });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function indexHtml() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Hardware Feedback App</title>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <div id="app"></div>
  <script src="/app.js"></script>
</body>
</html>`;
}

const server = http.createServer(async (req, res) => {
  try {
    const parsed = url.parse(req.url, true);
    const pathname = parsed.pathname || '/';

    if (req.method === 'GET' && pathname === '/') {
      return sendText(res, 200, indexHtml(), 'text/html; charset=utf-8');
    }

    if (req.method === 'GET' && pathname === '/app.js') {
      const appJs = fs.readFileSync(path.join(UI_DIR, 'app.js'), 'utf-8');
      return sendText(res, 200, appJs, 'text/javascript; charset=utf-8');
    }

    if (req.method === 'GET' && pathname === '/styles.css') {
      const css = fs.readFileSync(path.join(UI_DIR, 'styles.css'), 'utf-8');
      return sendText(res, 200, css, 'text/css; charset=utf-8');
    }

    if (req.method === 'GET' && pathname === '/api/files') {
      const files = ALLOWED_FILES.filter((name) => fs.existsSync(path.join(OUT_DIR, name)));
      return sendJson(res, 200, { files });
    }

    if (req.method === 'GET' && pathname === '/api/file') {
      const name = parsed.query.name;
      if (!ALLOWED_FILES.includes(name)) {
        return sendJson(res, 400, { error: 'Invalid file name' });
      }
      const filePath = path.join(OUT_DIR, name);
      if (!fs.existsSync(filePath)) {
        return sendJson(res, 404, { error: 'File not found' });
      }
      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      return sendJson(res, 200, { name, content });
    }

    if (req.method === 'POST' && pathname === '/api/save') {
      const name = parsed.query.name;
      if (!ALLOWED_FILES.includes(name)) {
        return sendJson(res, 400, { error: 'Invalid file name' });
      }

      const body = await readBody(req);
      let payload;
      try {
        payload = JSON.parse(body);
      } catch {
        return sendJson(res, 400, { error: 'Invalid JSON body' });
      }

      fs.mkdirSync(CORRECTIONS_DIR, { recursive: true });
      const outName = `${name.replace(/\.json$/i, '')}.corrected.json`;
      const outPath = path.join(CORRECTIONS_DIR, outName);
      fs.writeFileSync(outPath, JSON.stringify(payload, null, 2), 'utf-8');

      return sendJson(res, 200, {
        ok: true,
        saved_to: outPath,
      });
    }

    return sendJson(res, 404, { error: 'Not found' });
  } catch (err) {
    return sendJson(res, 500, { error: String(err.message || err) });
  }
});

const port = 4173;
server.listen(port, () => {
  console.log(`Feedback app running at http://localhost:${port}`);
});
