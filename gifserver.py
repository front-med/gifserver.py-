#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLIP → GIF (server edition)

URL（YouTube / X / Instagram / TikTok / 直リンク など yt-dlp が対応するサイト）から
動画を取得し、ブラウザ上でトリミング → ffmpeg で高画質GIFを書き出すローカルツール。

必要なもの:
    brew install ffmpeg          # or: apt install ffmpeg
    pip install -U yt-dlp

起動:
    python3 gifserver.py                       # http://127.0.0.1:8765 が開く
    python3 gifserver.py --cookies chrome      # ログインが要るSNS（Instagram等）用
    python3 gifserver.py --port 9000

出力: ./gif_out/ に GIF が保存されます。
注意: 取得・再配布の権利があるコンテンツにのみ使ってください（各サイトの規約に従うこと）。
"""

import argparse, base64, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ---------- BODY LOG連携・クラウド設定（環境変数 or 起動オプションで指定） ----------
GAS_URL = os.environ.get("GAS_URL", "").strip()          # BODY LOGのexec URL
GAS_SECRET = os.environ.get("GAS_SECRET", "").strip()    # Code.gsのAPI_SECRET
ACCESS_KEY = os.environ.get("ACCESS_KEY", "").strip()    # 公開時の簡易パスワード（推奨）
IS_CLOUD = bool(os.environ.get("PORT"))                  # Render等はPORTを渡してくる

WORK = tempfile.mkdtemp(prefix="clip2gif_")
OUTDIR = os.path.abspath("gif_out")
os.makedirs(OUTDIR, exist_ok=True)
MEDIA = {}          # id -> {path, title, duration, width, height}
COOKIES = None
LOCK = threading.Lock()


# ---------- helpers ----------

def which_or_die(name, hint):
    if not shutil.which(name):
        print(f"[!] {name} が見つかりません。\n    → {hint}")
        sys.exit(1)


def run(cmd, timeout=1800):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip()[-1200:])
    return p.stdout.strip()


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height",
               "-show_entries", "format=duration", "-of", "json", path])
    j = json.loads(out)
    st = (j.get("streams") or [{}])[0]
    return {
        "duration": float(j.get("format", {}).get("duration", 0) or 0),
        "width": int(st.get("width", 0) or 0),
        "height": int(st.get("height", 0) or 0),
    }


def cookies_file():
    """CookieファイルのパスをRender Secret File / 環境変数から探す"""
    for p in [os.environ.get("COOKIES_FILE", ""), "/etc/secrets/cookies.txt", "cookies.txt"]:
        if p and os.path.exists(p):
            return p
    return None


def download(url):
    cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "--restrict-filenames",
           "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
           "--merge-output-format", "mp4",
           "-o", os.path.join(WORK, "%(id)s.%(ext)s"),
           "--print", "after_move:filepath", "--no-simulate", url]
    ck = cookies_file()
    if ck:
        # Secret Fileは読み取り専用のことがあるため、書込可能な場所へコピーして使う
        tmp_ck = os.path.join(WORK, "cookies.txt")
        try:
            shutil.copyfile(ck, tmp_ck)
            cmd[1:1] = ["--cookies", tmp_ck]
        except Exception:
            cmd[1:1] = ["--cookies", ck]
    elif COOKIES:
        cmd[1:1] = ["--cookies-from-browser", COOKIES]
    out = run(cmd)
    path = [l for l in out.splitlines() if os.path.exists(l)]
    if not path:
        raise RuntimeError("動画ファイルを取得できませんでした。")
    return path[-1]


def make_gif(src, start, dur, width, fps, colors, dither, loop):
    ts = time.strftime("%H%M%S")
    base = re.sub(r"[^A-Za-z0-9_-]", "", os.path.splitext(os.path.basename(src))[0])[:24] or "clip"
    palette = os.path.join(WORK, f"pal_{ts}.png")
    out = os.path.join(OUTDIR, f"{base}_{ts}.gif")
    scale = f"scale={width}:-1:flags=lanczos" if width else "scale=iw:ih"
    common = ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]

    run(["ffmpeg", "-v", "error", "-y", *common,
         "-vf", f"fps={fps},{scale},palettegen=max_colors={colors}:stats_mode=diff",
         palette])
    run(["ffmpeg", "-v", "error", "-y", *common, "-i", palette,
         "-lavfi", f"fps={fps},{scale}[x];[x][1:v]paletteuse=dither={dither}:diff_mode=rectangle",
         "-loop", "0" if loop else "-1", out])
    return out


# ---------- http ----------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _file(self, path, ctype):
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, length, code = 0, size, 200
        if rng and rng.startswith("bytes="):
            s, _, e = rng[6:].partition("-")
            start = int(s) if s else 0
            end = min(int(e), size - 1) if e else size - 1
            length, code = end - start + 1, 206
        self.send_response(code)
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{start+length-1}/{size}")
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _key_ok(self):
        if not ACCESS_KEY:
            return True
        q = parse_qs(urlparse(self.path).query)
        return (q.get("key") or [""])[0] == ACCESS_KEY

    def do_GET(self):
        p = urlparse(self.path).path
        if not self._key_ok():
            return self._json(403, {"error": "アクセスキーが必要です（URLに ?key=xxx を付けてください）"})
        if p == "/":
            b = PAGE.replace("__ACCESS_KEY__", json.dumps(ACCESS_KEY)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif p.startswith("/media/"):
            m = MEDIA.get(p.split("/")[-1])
            if not m:
                return self._json(404, {"error": "not found"})
            self._file(m["path"], "video/mp4")
        elif p.startswith("/out/"):
            f = os.path.join(OUTDIR, os.path.basename(p))
            if not os.path.exists(f):
                return self._json(404, {"error": "not found"})
            self._file(f, "image/gif")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad request"})
        p = urlparse(self.path).path
        if ACCESS_KEY and body.get("key") != ACCESS_KEY:
            return self._json(403, {"error": "アクセスキーが違います"})
        try:
            if p == "/api/fetch":
                url = (body.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    raise RuntimeError("http(s) で始まるURLを入力してください。")
                with LOCK:
                    path = download(url)
                info = probe(path)
                mid = str(abs(hash(path)) % 10**10)
                MEDIA[mid] = dict(path=path, **info)
                self._json(200, {"id": mid, "media": f"/media/{mid}",
                                 "name": os.path.basename(path), **info})
            elif p == "/api/render":
                m = MEDIA.get(body.get("id"))
                if not m:
                    raise RuntimeError("動画が見つかりません。読み込み直してください。")
                start = max(0.0, float(body["start"]))
                dur = max(0.05, float(body["end"]) - start)
                with LOCK:
                    out = make_gif(m["path"], start, dur,
                                   int(body.get("width") or 0), int(body.get("fps") or 10),
                                   int(body.get("colors") or 256), body.get("dither") or "sierra2_4a",
                                   bool(body.get("loop", True)))
                self._json(200, {"gif": "/out/" + os.path.basename(out),
                                 "size": os.path.getsize(out), "path": out})
            elif p == "/api/exercises":
                if not GAS_URL or not GAS_SECRET:
                    raise RuntimeError("BODY LOG連携が未設定です")
                payload = json.dumps({"secret": GAS_SECRET, "action": "listExercises"}).encode()
                req = urllib.request.Request(GAS_URL, data=payload,
                                             headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=60) as r:
                    res = json.loads(r.read().decode() or "{}")
                self._json(200, {"names": res.get("names") or []})
            elif p == "/api/register":
                if not GAS_URL or not GAS_SECRET:
                    raise RuntimeError("BODY LOG連携が未設定です（GAS_URL / GAS_SECRET を設定してください）。")
                fname = os.path.basename(body.get("file") or "")
                fpath = os.path.join(OUTDIR, fname)
                if not os.path.exists(fpath):
                    raise RuntimeError("GIFが見つかりません。作り直してください。")
                exname = (body.get("name") or "").strip()
                if not exname:
                    raise RuntimeError("種目名を入力してください。")
                if os.path.getsize(fpath) > 9 * 1024 * 1024:
                    raise RuntimeError("GIFが9MBを超えています。幅・FPS・色数を下げて作り直してください。")
                with open(fpath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                payload = json.dumps({
                    "secret": GAS_SECRET, "action": "uploadMedia",
                    "name": exname, "base64": b64,
                    "mimeType": "image/gif", "fileName": exname + "_form.gif"
                }).encode()
                req = urllib.request.Request(GAS_URL, data=payload,
                                             headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=180) as r:
                    res = json.loads(r.read().decode() or "{}")
                if not res.get("success"):
                    raise RuntimeError(res.get("message") or "BODY LOG側でエラーが発生しました")
                self._json(200, {"ok": True, "message": res.get("message", "登録しました")})
            else:
                self._json(404, {"error": "not found"})
        except subprocess.TimeoutExpired:
            self._json(500, {"error": "処理がタイムアウトしました。"})
        except Exception as e:
            self._json(500, {"error": str(e)})


# ---------- ui ----------

PAGE = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLIP → GIF</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Zen+Kaku+Gothic+New:wght@400;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#0B1626;--panel:#132539;--panel-2:#1B3450;--gold:#C8A24A;--gold-soft:#E3C77E;--pale:#EDE7DA;--slate:#7A90AC;--alert:#C25B4A;--radius:3px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:var(--pale);font-family:"Zen Kaku Gothic New",system-ui,sans-serif;line-height:1.6;padding:28px 18px 64px}
.wrap{max-width:820px;margin:0 auto}
.slate{border:1px solid var(--panel-2);border-left:4px solid var(--gold);padding:14px 16px;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;background:linear-gradient(90deg,var(--panel) 0%,transparent 70%)}
.eyebrow{font-family:"Oswald",sans-serif;letter-spacing:.22em;font-size:12px;color:var(--gold);text-transform:uppercase}
h1{font-family:"Oswald",sans-serif;font-weight:600;font-size:26px;letter-spacing:.06em}
.slate p{color:var(--slate);font-size:13px;margin-left:auto;font-family:"JetBrains Mono",monospace}
.source{margin-top:22px;display:grid;gap:10px}
.row{display:flex;gap:8px;flex-wrap:wrap}
input[type=url]{flex:1;min-width:220px;background:var(--panel);border:1px solid var(--panel-2);color:var(--pale);padding:11px 12px;border-radius:var(--radius);font-family:"JetBrains Mono",monospace;font-size:13px}
input[type=url]::placeholder{color:#4F6480}
input:focus,button:focus-visible,.handle:focus-visible,select:focus{outline:2px solid var(--gold);outline-offset:2px}
button{font-family:"Oswald",sans-serif;letter-spacing:.12em;text-transform:uppercase;background:transparent;border:1px solid var(--slate);color:var(--pale);padding:10px 16px;border-radius:var(--radius);cursor:pointer;font-size:13px}
button:hover:not(:disabled){border-color:var(--gold);color:var(--gold-soft)}
button:disabled{opacity:.4;cursor:not-allowed}
button.primary{background:var(--gold);border-color:var(--gold);color:#0B1626;font-weight:600}
button.primary:hover:not(:disabled){background:var(--gold-soft);color:#0B1626}
.note{font-size:12px;color:var(--slate)}
.msg{font-size:13px;min-height:20px;color:var(--alert)}
.stage{margin-top:20px;display:none}
.stage.on{display:block}
video{width:100%;background:#000;border:1px solid var(--panel-2);display:block}
.strip-wrap{margin-top:14px;position:relative;user-select:none;touch-action:none}
.perf{height:9px;background:repeating-linear-gradient(90deg,transparent 0 8px,var(--panel-2) 8px 14px);opacity:.8}
.strip{position:relative;height:64px;background:#000;border-block:1px solid var(--panel-2);display:flex;overflow:hidden}
.strip canvas{height:64px;width:auto;flex:0 0 auto;opacity:.55}
.shade{position:absolute;top:0;bottom:0;background:rgba(11,22,38,.78);pointer-events:none}
.window{position:absolute;top:0;bottom:0;border:1px solid var(--gold);box-shadow:0 0 0 1px rgba(200,162,74,.25) inset;pointer-events:none}
.handle{position:absolute;top:-9px;bottom:-9px;width:14px;margin-left:-7px;background:var(--gold);cursor:ew-resize;border-radius:1px}
.handle::after{content:"";position:absolute;inset:38% 5px;border-left:1px solid #0B1626;border-right:1px solid #0B1626}
.tc{display:flex;justify-content:space-between;margin-top:8px;font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--slate)}
.tc b{color:var(--gold-soft);font-weight:600}
.controls{margin-top:20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.field label{display:block;font-family:"Oswald",sans-serif;font-size:11px;letter-spacing:.18em;color:var(--slate);text-transform:uppercase;margin-bottom:5px}
select{width:100%;background:var(--panel);border:1px solid var(--panel-2);color:var(--pale);padding:9px 10px;border-radius:var(--radius);font-family:"JetBrains Mono",monospace;font-size:13px}
.actions{margin-top:18px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.est{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--slate)}
.result{margin-top:20px;border:1px solid var(--panel-2);padding:14px;display:none}
.result.on{display:block}
.result img{max-width:100%;display:block;margin-bottom:12px;background:#000}
.reg{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:6px}
.reg input,.reg select{flex:1;min-width:180px;background:var(--panel);border:1px solid var(--panel-2);color:var(--pale);padding:10px 12px;border-radius:var(--radius);font-family:inherit;font-size:14px}
.reg button.dl{border:none;cursor:pointer;font-family:inherit}
.meta{font-family:"JetBrains Mono",monospace;font-size:12px;color:var(--slate);margin-bottom:10px}
.meta b{color:var(--gold-soft)}
a.dl{display:inline-block;font-family:"Oswald",sans-serif;letter-spacing:.12em;text-transform:uppercase;background:var(--gold);color:#0B1626;padding:10px 18px;text-decoration:none;border-radius:var(--radius);font-weight:600;font-size:13px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head>
<body><div class="wrap">
<header class="slate">
  <span class="eyebrow">Clip → Gif</span>
  <h1>URLからGIFを作る</h1>
  <p id="engine">yt-dlp + ffmpeg</p>
</header>

<section class="source">
  <div class="row">
    <input type="url" id="url" placeholder="https://... （YouTube / X / Instagram / 直リンク）">
    <button class="primary" id="load">取り込む</button>
  </div>
  <p class="note">サーバー側が動画を取得します。ログインが必要なSNSは <code>--cookies chrome</code> を付けて起動してください。</p>
  <p class="msg" id="msg"></p>
</section>

<section class="stage" id="stage">
  <video id="video" playsinline muted preload="auto"></video>

  <div class="strip-wrap" id="stripWrap">
    <div class="perf"></div>
    <div class="strip" id="strip">
      <div class="shade" id="shadeL"></div><div class="shade" id="shadeR"></div><div class="window" id="win"></div>
    </div>
    <div class="perf"></div>
    <div class="handle" id="hL" tabindex="0" role="slider" aria-label="開始位置"></div>
    <div class="handle" id="hR" tabindex="0" role="slider" aria-label="終了位置"></div>
  </div>
  <div class="tc"><span>IN <b id="tcIn">0.00s</b></span><span>LEN <b id="tcLen">0.00s</b></span><span>OUT <b id="tcOut">0.00s</b></span></div>

  <div class="controls">
    <div class="field"><label for="w">幅 / Width</label>
      <select id="w"><option value="240">240 px</option><option value="320">320 px</option><option value="480" selected>480 px</option><option value="640">640 px</option><option value="0">元のサイズ</option></select></div>
    <div class="field"><label for="fps">Fps</label>
      <select id="fps"><option value="5">5</option><option value="8">8</option><option value="10">10</option><option value="12" selected>12</option><option value="15">15</option><option value="20">20</option></select></div>
    <div class="field"><label for="colors">色数 / Colors</label>
      <select id="colors"><option value="256" selected>256（高画質）</option><option value="128">128</option><option value="64">64（軽量）</option><option value="32">32（最小）</option></select></div>
    <div class="field"><label for="dither">ディザ</label>
      <select id="dither"><option value="sierra2_4a" selected>あり（なめらか）</option><option value="bayer">Bayer（小さい）</option><option value="none">なし（最小）</option></select></div>
  </div>

  <div class="actions">
    <button class="primary" id="go">GIFを作る</button>
    <span class="est" id="est"></span>
  </div>

  <div class="result" id="result">
    <img id="out" alt="生成されたGIF">
    <p class="meta" id="meta"></p>
    <div class="reg">
      <select id="exname"><option value="">種目を選択</option></select>
      <button class="primary" id="reg" type="button">この種目に挿入</button>
    </div>
    <p class="meta" id="regmsg"></p>
    <p class="meta"><a id="dl" download style="color:var(--slate);text-decoration:underline">GIFファイルをダウンロード（必要な場合のみ）</a></p>
  </div>
</section>
</div>

<script>
const KEY=__ACCESS_KEY__;
const EXPARAM=new URLSearchParams(location.search).get('ex')||'';
const $=id=>document.getElementById(id), video=$('video');
let duration=0,inT=0,outT=0,mediaId=null,lastGif=null;
const withKey=u=>KEY?u+(u.includes('?')?'&':'?')+'key='+encodeURIComponent(KEY):u;
const fmt=s=>s.toFixed(2)+'s';
const say=(t,ok)=>{$('msg').textContent=t||'';$('msg').style.color=ok?'var(--slate)':'var(--alert)';};

async function api(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({key:KEY},body))});
  const j=await r.json();
  if(!r.ok) throw new Error(j.error||('HTTP '+r.status));
  return j;
}

$('load').onclick=async()=>{
  const u=$('url').value.trim();
  if(!u){say('URLを入力してください。');return;}
  $('load').disabled=true; say('取得中…（初回は少し時間がかかります）',true);
  try{
    const j=await api('/api/fetch',{url:u});
    mediaId=j.id; $('dl').download=j.name.replace(/\.[^.]+$/,'')+'.gif';
    video.src=withKey(j.media); say('',true);
  }catch(e){ say('取得できませんでした：'+e.message); }
  $('load').disabled=false;
};

video.addEventListener('loadedmetadata',async()=>{
  duration=video.duration;
  if(!isFinite(duration)||!duration){say('動画の長さを読み取れませんでした。');return;}
  inT=0; outT=Math.min(duration,5);
  $('stage').classList.add('on'); drawUI(); await buildStrip(); await seek(inT);
});

function seek(t){return new Promise(res=>{const h=()=>{video.removeEventListener('seeked',h);res();};video.addEventListener('seeked',h);video.currentTime=Math.min(Math.max(t,0),Math.max(duration-0.001,0));});}

async function buildStrip(){
  const strip=$('strip'); strip.querySelectorAll('canvas').forEach(c=>c.remove());
  const n=12,h=64,w=Math.round(h*(video.videoWidth/video.videoHeight))||100;
  for(let i=0;i<n;i++){
    await seek(duration*(i+0.5)/n);
    const c=document.createElement('canvas'); c.width=w; c.height=h;
    c.getContext('2d').drawImage(video,0,0,w,h);
    strip.insertBefore(c,$('shadeL'));
  }
}

function drawUI(){
  const a=inT/duration,b=outT/duration;
  $('shadeL').style.left='0';$('shadeL').style.width=(a*100)+'%';
  $('shadeR').style.left=(b*100)+'%';$('shadeR').style.width=((1-b)*100)+'%';
  $('win').style.left=(a*100)+'%';$('win').style.width=((b-a)*100)+'%';
  $('hL').style.left=(a*100)+'%';$('hR').style.left=(b*100)+'%';
  $('tcIn').textContent=fmt(inT);$('tcOut').textContent=fmt(outT);$('tcLen').textContent=fmt(outT-inT);
  $('est').textContent=Math.max(1,Math.round((outT-inT)*+$('fps').value))+' フレーム';
  $('go').disabled=outT-inT<0.05;
}

function drag(el,isLeft){
  const move=e=>{
    const box=$('strip').getBoundingClientRect();
    const t=Math.min(Math.max((e.clientX-box.left)/box.width,0),1)*duration;
    if(isLeft) inT=Math.min(t,outT-0.05); else outT=Math.max(t,inT+0.05);
    inT=Math.max(0,inT); outT=Math.min(duration,outT);
    drawUI(); seek(isLeft?inT:outT);
  };
  el.addEventListener('pointerdown',e=>{
    el.setPointerCapture(e.pointerId);
    const up=()=>{el.removeEventListener('pointermove',move);el.removeEventListener('pointerup',up);};
    el.addEventListener('pointermove',move); el.addEventListener('pointerup',up);
  });
  el.addEventListener('keydown',e=>{
    if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
    e.preventDefault();
    const d=(e.key==='ArrowRight'?1:-1)*(e.shiftKey?1:0.1);
    if(isLeft) inT=Math.min(Math.max(inT+d,0),outT-0.05); else outT=Math.max(Math.min(outT+d,duration),inT+0.05);
    drawUI(); seek(isLeft?inT:outT);
  });
}
drag($('hL'),true); drag($('hR'),false);
$('fps').onchange=drawUI; window.addEventListener('resize',drawUI);

$('go').onclick=async()=>{
  $('go').disabled=true; $('result').classList.remove('on'); say('書き出し中…',true);
  try{
    const j=await api('/api/render',{id:mediaId,start:inT,end:outT,width:+$('w').value,fps:+$('fps').value,colors:+$('colors').value,dither:$('dither').value,loop:true});
    const mb=j.size/1048576;
    $('out').src=withKey(j.gif+'?t='+Date.now()); $('dl').href=withKey(j.gif);
    lastGif=j.gif.split('/').pop(); $('regmsg').textContent='';
    $('meta').innerHTML=`${$('w').value==='0'?'元サイズ':$('w').value+'px'} ／ ${$('fps').value} fps ／ <b>${mb.toFixed(2)} MB</b> ／ 保存先 ${j.path}`
      +(mb>5?'　— 大きめです。幅・FPS・色数を下げると小さくなります。':'');
    $('result').classList.add('on'); say('',true);
  }catch(e){ say('書き出しに失敗しました：'+e.message); }
  $('go').disabled=false;
};

async function registerGif(){
  const name=$('exname').value.trim();
  if(!name){$('regmsg').textContent='種目を選択してください';return;}
  if(!lastGif){$('regmsg').textContent='先にGIFを作成してください';return;}
  $('reg').disabled=true; $('reg').textContent='挿入中…'; $('regmsg').textContent='';
  try{
    const j=await api('/api/register',{file:lastGif,name:name});
    $('regmsg').textContent='✅ '+(j.message||'BODY LOGに挿入しました');
  }catch(e){ $('regmsg').textContent='挿入失敗：'+e.message; }
  $('reg').disabled=false; $('reg').textContent='この種目に挿入';
}
$('reg').onclick=registerGif;

// BODY LOGから種目一覧を取得してプルダウンに反映（?ex=種目名 があれば自動選択）
(async()=>{
  const sel=$('exname');
  try{
    const j=await api('/api/exercises',{});
    (j.names||[]).forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;sel.appendChild(o);});
  }catch(e){}
  if(EXPARAM){
    if(![...sel.options].some(o=>o.value===EXPARAM)){
      const o=document.createElement('option');o.value=EXPARAM;o.textContent=EXPARAM;sel.appendChild(o);
    }
    sel.value=EXPARAM;
  }
})();
</script></body></html>
"""


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    global COOKIES, GAS_URL, GAS_SECRET, ACCESS_KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="同じWi-Fi内の他の端末（iPhone等）からも開けるようにする")
    ap.add_argument("--cookies", help="ブラウザ名（chrome / safari / firefox / edge）。ログインが要るSNS用")
    ap.add_argument("--gas-url", help="BODY LOGのexec URL（環境変数GAS_URLでも可）")
    ap.add_argument("--gas-secret", help="Code.gsのAPI_SECRET（環境変数GAS_SECRETでも可）")
    ap.add_argument("--key", help="アクセスキー（環境変数ACCESS_KEYでも可）")
    a = ap.parse_args()
    COOKIES = a.cookies
    if a.gas_url: GAS_URL = a.gas_url.strip()
    if a.gas_secret: GAS_SECRET = a.gas_secret.strip()
    if a.key: ACCESS_KEY = a.key.strip()

    which_or_die("ffmpeg", "conda install -c conda-forge ffmpeg  /  brew install ffmpeg")
    which_or_die("ffprobe", "conda install -c conda-forge ffmpeg  /  brew install ffmpeg")
    which_or_die("yt-dlp", "pip install -U yt-dlp")

    port = int(os.environ.get("PORT", a.port))
    host = "0.0.0.0" if (a.lan or IS_CLOUD) else "127.0.0.1"
    local = f"http://127.0.0.1:{port}"
    print(f"CLIP → GIF  {local}   （終了: Ctrl+C）")
    if a.lan and not IS_CLOUD:
        print(f"他の端末から: http://{lan_ip()}:{port}   ※同じWi-Fiのみ")
    if GAS_URL and GAS_SECRET:
        print("BODY LOG連携: 有効")
    else:
        print("BODY LOG連携: 未設定（GAS_URL / GAS_SECRET を設定すると「BODY LOGへ登録」が使えます）")
    print(f"出力先: {OUTDIR}")
    if not IS_CLOUD:
        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
