"""
Panel de Rentabilidades por Región  (v2)
-----------------------------------------
- ETFs: Yahoo Finance (precio ajustado = total return).
- IPSA, Dollar Index, USD/CLP y Cobre: Investing.com (con respaldo en Yahoo).
- Conversion a CLP por metodo ADITIVO: retorno USD + variacion USD/CLP.
- IPSA nativo en CLP (sin ajuste por tipo de cambio).
- Genera HTML autocontenido e interactivo (toggle USD/CLP + fechas) y un
  "Comentario de mercado" con bullets semanales al pie.

Uso (Windows):
    pip install yfinance pandas cloudscraper lxml pytz
    python panel_rentabilidades.py
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta, date
from random import randint

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Faltan dependencias base. Ejecuta:  pip install yfinance pandas")
    sys.exit(1)

try:
    import cloudscraper
    from lxml.html import fromstring as lxml_fromstring
    import pytz
    HAVE_INVESTING = True
except ImportError:
    HAVE_INVESTING = False

# ----------------------------- Configuración ---------------------------------
PERIOD = "10y"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

GROUPS = [
    {"label": "Globales", "items": [
        {"t": "URTH", "n": "Desarrollados"}, {"t": "EEM", "n": "Emergentes"}, {"t": "ACWI", "n": "Globales"},
    ]},
    {"label": "Estados Unidos", "items": [
        {"t": "SPY", "n": "S&P 500"}, {"t": "DIA", "n": "Dow Jones"}, {"t": "QQQ", "n": "Nasdaq"},
    ]},
    {"label": "Europa", "items": [
        {"t": "IEV", "n": "Europa"}, {"t": "EWP", "n": "España"}, {"t": "EWU", "n": "Reino Unido"},
        {"t": "EWG", "n": "Alemania"}, {"t": "EWQ", "n": "Francia"}, {"t": "EWI", "n": "Italia"},
    ]},
    {"label": "Asia Desarrollada", "items": [
        {"t": "EWJ", "n": "Japón"}, {"t": "EWA", "n": "Australia"}, {"t": "EWH", "n": "Hong Kong"},
    ]},
    {"label": "Asia Emergente", "items": [
        {"t": "AAXJ", "n": "Asia Emergente"}, {"t": "FXI", "n": "China"}, {"t": "INDA", "n": "India"},
        {"t": "EWY", "n": "Corea"}, {"t": "EWT", "n": "Taiwán"},
    ]},
    {"label": "Latinoamérica", "items": [
        {"t": "ILF", "n": "Latam"}, {"t": "^IPSA", "n": "Chile", "clp": True},
        {"t": "EWZ", "n": "Brasil"}, {"t": "EWW", "n": "México"},
    ]},
    {"label": "Dólar y Materias Primas", "items": [
        {"t": "DX-Y.NYB", "n": "Dollar Index", "native": True, "u": "pts"},
        {"t": "USDCLP=X", "n": "USD/CLP", "native": True, "u": "$"},
        {"t": "HG=F", "n": "Cobre", "native": True, "u": "US$/lb"},
    ]},
]
ALL = [it["t"] for g in GROUPS for it in g["items"]]

# Instrumentos que se bajan de Investing.com (curr_id, header, slug-referer)
INVESTING_SOURCES = {
    "^IPSA":    ("14767",  "S&P CLX IPSA Historical Data",    "indices/ipsa-historical-data"),
    "DX-Y.NYB": ("942611", "US Dollar Index Historical Data", "indices/usdollar-historical-data"),
    "USDCLP=X": ("2110",   "USD/CLP Historical Data",         "currencies/usd-clp-historical-data"),
    "HG=F":     ("8831",   "Copper Futures Historical Data",  "commodities/copper"),
}


# ----------------------------- Utilidades fechas ------------------------------
def to_sec(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def last_friday(ref=None):
    if ref is None:
        ref = date.today()
    return ref - timedelta(days=(ref.weekday() - 4) % 7)


# ----------------------------- Descarga Yahoo (base) --------------------------
print(f"Descargando {len(ALL)} instrumentos desde Yahoo Finance ({PERIOD})...")
yahoo = yf.download(ALL, period=PERIOD, interval="1d", auto_adjust=False,
                    group_by="ticker", threads=True, progress=False)


def extract_yahoo(tk):
    try:
        df = yahoo[tk]
    except Exception:
        return None
    if df is None or getattr(df, "empty", True):
        return None
    cols = df.columns
    acol = "Adj Close" if "Adj Close" in cols else ("Close" if "Close" in cols else None)
    if acol is None:
        return None
    ta, adj, tc, close = [], [], [], []
    for ts, row in df.iterrows():
        sec = to_sec(ts)
        a = row.get(acol)
        c = row.get("Close") if "Close" in cols else a
        if pd.notna(a):
            ta.append(sec); adj.append(round(float(a), 4))
        if pd.notna(c):
            tc.append(sec); close.append(round(float(c), 4))
    if not ta and not tc:
        return None
    return {"ta": ta, "adj": adj, "tc": tc, "close": close}


# ----------------------------- Descarga Investing -----------------------------
def fetch_investing(ticker, start, end):
    if not HAVE_INVESTING:
        return None
    curr_id, header, slug = INVESTING_SOURCES[ticker]
    scraper = cloudscraper.create_scraper()
    params = {
        "curr_id": curr_id,
        "smlID": str(randint(1_000_000, 9_999_999)),
        "header": header,
        "st_date": start.strftime("%m/%d/%Y"),
        "end_date": (end + timedelta(days=5)).strftime("%m/%d/%Y"),
        "interval_sec": "Daily",
        "sort_col": "date",
        "sort_ord": "DESC",
        "action": "historical_data",
    }
    headers = {
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html",
        "Referer": f"https://www.investing.com/{slug}",
        "Origin": "https://www.investing.com",
    }
    for attempt in range(3):
        try:
            r = scraper.post("https://www.investing.com/instruments/HistoricalDataAjax",
                             headers=headers, data=params, timeout=25)
            if r.status_code != 200:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                continue
            root = lxml_fromstring(r.content)
            rows = root.xpath('.//table[@id="curr_table"]/tbody/tr')
            recs = {}
            for row in rows:
                tds = row.xpath(".//td")
                if not tds:
                    continue
                raw_ts = tds[0].get("data-real-value")
                raw_close = tds[1].get("data-real-value")
                if not raw_ts or not raw_close:
                    continue
                d = datetime.fromtimestamp(int(raw_ts), tz=pytz.UTC).date()
                recs[d] = float(raw_close.replace(",", ""))
            if recs:
                return recs
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def recs_to_arrays(recs):
    ds = sorted(recs.keys())
    ta = [to_sec(d) for d in ds]
    vs = [round(float(recs[d]), 4) for d in ds]
    return {"ta": ta, "adj": vs, "tc": list(ta), "close": list(vs)}


# ----------------------------- Construir DATA ---------------------------------
DATA, failed = {}, []
for tk in ALL:
    d = extract_yahoo(tk)
    if d:
        DATA[tk] = d
    else:
        failed.append(tk)

START = date.today() - timedelta(days=3660)  # ~10 años
inv_ok, inv_fb = [], []
for tk in INVESTING_SOURCES:
    recs = fetch_investing(tk, START, date.today())
    if recs:
        DATA[tk] = recs_to_arrays(recs)
        inv_ok.append(tk)
    else:
        inv_fb.append(tk)

if not HAVE_INVESTING:
    print("  [!] Investing deshabilitado (faltan libs). Esos 4 usan Yahoo.")
    print("      Para activarlo: pip install cloudscraper lxml pytz")
if inv_ok:
    print("  Investing.com OK: " + ", ".join(inv_ok))
if inv_fb and HAVE_INVESTING:
    print("  Investing falló (respaldo Yahoo): " + ", ".join(inv_fb))
if failed:
    print("  Sin datos: " + ", ".join(failed))


# ----------------------------- Bullets (semanal) -----------------------------
def asof(arr_t, arr_v, target):
    lo, hi, a = 0, len(arr_t) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr_t[mid] <= target:
            a = mid; lo = mid + 1
        else:
            hi = mid - 1
    return arr_v[a] if a >= 0 else None


def wk_ret(data, tk, use_close=False):
    d = data.get(tk)
    if not d or not d.get("ta"):
        return None
    lf, pf = last_friday(), last_friday() - timedelta(weeks=1)
    tarr = d["tc"] if use_close else d["ta"]
    varr = d["close"] if use_close else d["adj"]
    p1 = asof(tarr, varr, to_sec(lf))
    p0 = asof(tarr, varr, to_sec(pf))
    if p1 is None or not p0:
        return None
    return p1 / p0 - 1


def build_bullets(data):
    bl = []
    dm, em = wk_ret(data, "URTH"), wk_ret(data, "EEM")
    if dm is not None and em is not None:
        if dm > 0 and em > 0:
            tono = "positivos"
        elif dm < 0 and em < 0:
            tono = "negativos"
        else:
            tono = "mixtos"
        bl.append(f"Semana con retornos {tono} en mercados desarrollados "
                  f"({dm*100:+.2f}%) y emergentes ({em*100:+.2f}%).")

    usdclp = wk_ret(data, "USDCLP=X", use_close=True)
    dxy = wk_ret(data, "DX-Y.NYB", use_close=True)
    cobre = wk_ret(data, "HG=F", use_close=True)
    if usdclp is not None:
        d = data.get("USDCLP=X")
        lf, pf = last_friday(), last_friday() - timedelta(weeks=1)
        p1 = asof(d["tc"], d["close"], to_sec(lf))
        p0 = asof(d["tc"], d["close"], to_sec(pf))
        var_pesos = abs(round(p1 - p0)) if (p1 and p0) else abs(round(usdclp * 900))
        mov_peso = "depreció" if usdclp > 0 else "apreció"
        efecto = "un aumento" if usdclp > 0 else "una disminución"
        peso_dep = usdclp > 0
        en_linea, pese_a = [], []
        if dxy is not None:
            dxy_sube = dxy > 0
            mov_dolar = "apreciación" if dxy_sube else "depreciación"
            txt = f"la {mov_dolar} de {abs(dxy*100):.2f}% del dólar a nivel internacional"
            (en_linea if peso_dep == dxy_sube else pese_a).append(txt)
        if cobre is not None:
            cons = (peso_dep and cobre < 0) or ((not peso_dep) and cobre > 0)
            mov_c = "alza" if cobre > 0 else "caída"
            art = "el" if cobre > 0 else "la"
            txt = f"{art} {mov_c} de {abs(cobre*100):.2f}% en el precio del cobre"
            (en_linea if cons else pese_a).append(txt)
        suf = []
        if en_linea:
            suf.append("en línea con " + " y ".join(en_linea))
        if pese_a:
            suf.append("en desacople con " + " y ".join(pese_a))
        var_str = f"{var_pesos:,.0f}".replace(",", ".")
        b = (f"Por el lado del Forex, el peso chileno se {mov_peso} un {abs(usdclp*100):.2f}%, "
             f"equivalente a {efecto} de alrededor de {var_str} pesos")
        if suf:
            b += ", " + ", ".join(suf)
        bl.append(b + ".")
    return bl


bullets = build_bullets(DATA)
lf = last_friday()
if bullets:
    items = "".join(f"<li>{b}</li>" for b in bullets)
    COMENTARIO = (f'<div class="coment"><h2>Comentario de mercado · semana al '
                  f'{lf.strftime("%d-%m-%Y")}</h2><ul>{items}</ul></div>')
else:
    COMENTARIO = ""


# ----------------------------- Plantilla HTML ---------------------------------
HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel de Rentabilidades por Región</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f1f5f9;color:#1e293b;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1100px;margin:24px auto;background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.head{display:flex;justify-content:space-between;align-items:center;gap:8px;background:#0f172a;padding:16px 20px;flex-wrap:wrap}
.head h1{font-size:16px;margin:0;color:#fff;font-weight:600;letter-spacing:-.01em}
.head p{margin:2px 0 0;font-size:12px;color:#94a3b8}
.asofbox{text-align:right}
.asofbox .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b}
.asofbox .val{font-size:14px;color:#e2e8f0;font-weight:500}
.bar{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;padding:12px 20px;border-bottom:1px solid #e2e8f0}
.bar label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#94a3b8;margin-bottom:4px}
.seg-group{display:inline-flex;border:1px solid #cbd5e1;border-radius:6px;overflow:hidden}
.seg{padding:6px 14px;font-size:14px;font-weight:500;background:#fff;color:#475569;border:0;cursor:pointer;transition:background .12s}
.seg:hover{background:#f1f5f9}
.seg.on{background:#0f172a;color:#fff}
.bar input[type=date]{border:1px solid #cbd5e1;border-radius:6px;padding:5px 8px;font-size:14px;color:#334155;font-family:inherit}
.divider{width:1px;align-self:stretch;background:#e2e8f0;margin:0 2px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:920px}
thead th{background:#f1f5f9;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.05em;padding:10px 12px;text-align:right;font-weight:600;border-bottom:1px solid #e2e8f0}
thead th:first-child{text-align:left}
tr.grp td{background:#1e293b;color:#e2e8f0;font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:600;padding:6px 16px}
tbody td{padding:8px 12px;border-bottom:1px solid #f1f5f9}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.val{font-weight:500;color:#0f172a}
td.name .nm{color:#1e293b}
td.name .tk{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#94a3b8}
.sub{font-size:10px;color:#94a3b8}
.pos{color:#059669}.neg{color:#e11d48}.zero{color:#94a3b8}.na{color:#cbd5e1}
tbody tr:hover td{background:#f8fafc}
.coment{padding:16px 20px;border-top:1px solid #e2e8f0;background:#fff}
.coment h2{font-size:13px;margin:0 0 8px;color:#0f172a;font-weight:600}
.coment ul{margin:0;padding-left:18px}
.coment li{font-size:13px;color:#334155;line-height:1.6;margin:4px 0}
.foot{padding:12px 20px;border-top:1px solid #e2e8f0;background:#f8fafc;font-size:11px;color:#94a3b8;line-height:1.6}
.foot b{color:#64748b;font-weight:600}
.foot div{margin:1px 0}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div><h1>Panel de Rentabilidades por Región</h1><p>Visión de mercado para asesoría · datos generados el __GENERATED__</p></div>
    <div class="asofbox"><div class="lbl">Datos al</div><div class="val" id="asof">—</div></div>
  </div>
  <div class="bar">
    <div><label>Moneda</label><div class="seg-group"><button class="seg on" data-c="USD">USD</button><button class="seg" data-c="CLP">CLP</button></div></div>
    <div class="divider"></div>
    <div><label>Inicio (Pers.)</label><input type="date" id="start"></div>
    <div><label>Fin (Pers.)</label><input type="date" id="end"></div>
  </div>
  <div class="scroll"><table>
    <thead><tr>
      <th>Instrumento</th><th>Último (<span id="unit">USD</span>)</th>
      <th>Sem.</th><th>MTD</th><th>YTD</th><th>12m</th><th>3a*</th><th>5a*</th><th>Pers.</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table></div>
  <!--COMENTARIO-->
  <div class="foot">
    <div><b>*</b> 3a y 5a anualizados. <b>Sem.</b> = último viernes vs. viernes previo. <b>MTD/YTD</b> desde el último cierre del mes/año anterior.</div>
    <div>Conversión a CLP por <b>método aditivo</b>: retorno en USD + variación del USD/CLP del período. ETFs sobre precio ajustado (total return).</div>
    <div>IPSA, Dollar Index, USD/CLP y Cobre desde <b>Investing.com</b> (resto desde Yahoo Finance). IPSA es nativo en CLP y no se ajusta por tipo de cambio.</div>
  </div>
</div>
<script>
const GROUPS = /*GROUPS*/;
const DATA = /*DATA*/;

const FXC = DATA["USDCLP=X"] || {};
const FXT = FXC.tc || [];
const FXV = FXC.close || [];

function idxBefore(t,x){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]<=x){a=m;lo=m+1;}else hi=m-1;}return a;}
function idxAfter(t,x){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]>=x){a=m;hi=m-1;}else lo=m+1;}return a;}
function usdAt(sec){if(!FXT.length)return null;let i=idxBefore(FXT,sec);if(i<0)i=0;return FXV[i];}

const YR = 365.25*86400;
function rawMetrics(t, v, cs, ce){
  const m = {};
  if(!t || t.length<2) return m;
  const n = t.length-1, lastV = v[n], lastT = t[n];
  const D = new Date(lastT*1000), Y=D.getUTCFullYear(), M=D.getUTCMonth(), DD=D.getUTCDate();
  const at = (s)=>{const i=idxBefore(t,s);return i<0?null:v[i];};
  const rr = (a,b)=>(a==null||b==null||!isFinite(a)||!isFinite(b)||b===0)?null:a/b-1;
  const fri = [];
  for(let i=0;i<t.length;i++){ if(new Date(t[i]*1000).getUTCDay()===5) fri.push(i); }
  m.wk  = fri.length>=2 ? rr(v[fri[fri.length-1]], v[fri[fri.length-2]]) : null;
  m.mtd = rr(lastV, at(Date.UTC(Y,M,0)/1000));
  m.ytd = rr(lastV, at(Date.UTC(Y,0,0)/1000));
  m.y1  = rr(lastV, at(Date.UTC(Y-1,M,DD)/1000));
  const i3 = idxBefore(t, Date.UTC(Y-3,M,DD)/1000);
  if(i3>=0){ m.y3c = rr(lastV, v[i3]); m.y3y = (lastT-t[i3])/YR; }
  const i5 = idxBefore(t, Date.UTC(Y-5,M,DD)/1000);
  if(i5>=0){ m.y5c = rr(lastV, v[i5]); m.y5y = (lastT-t[i5])/YR; }
  if(cs && ce && ce>cs){
    const si=idxAfter(t,cs), ei=idxBefore(t,ce);
    if(si>=0 && ei>=0 && t[ei]>t[si]){ m.cumc = v[ei]/v[si]-1; m.cumy = (t[ei]-t[si])/YR; }
  }
  return m;
}
const add = (a,b)=>(a==null||b==null)?null:a+b;
const ann = (c,y)=>(c==null||y==null||y<=0)?null:Math.pow(1+c,1/y)-1;
function combine(u,f){return{wk:add(u.wk,f.wk),mtd:add(u.mtd,f.mtd),ytd:add(u.ytd,f.ytd),y1:add(u.y1,f.y1),y3c:add(u.y3c,f.y3c),y3y:u.y3y,y5c:add(u.y5c,f.y5c),y5y:u.y5y,cumc:add(u.cumc,f.cumc),cumy:u.cumy};}
function display(m){return{wk:m.wk,mtd:m.mtd,ytd:m.ytd,y1:m.y1,y3:ann(m.y3c,m.y3y),y5:ann(m.y5c,m.y5y),cum:m.cumc,cumAnn:(m.cumy!=null&&m.cumy>=1)?ann(m.cumc,m.cumy):null};}

function lastValue(it, cur){
  const d = DATA[it.t];
  if(!d || !d.close || !d.close.length) return null;
  const lc = d.close[d.close.length-1], lct = d.tc[d.tc.length-1];
  if(it.native || it.clp) return lc;        // Dólar/Cobre nativo, IPSA en pesos
  if(cur==="USD") return lc;
  const u = usdAt(lct); return u ? lc*u : null;
}

let fxRaw = null;
function rowMetrics(it, cur, cs, ce){
  const d = DATA[it.t];
  if(!d || !d.ta || !d.ta.length) return {};
  const usd = rawMetrics(d.ta, d.adj, cs, ce);
  if(it.native || it.clp) return display(usd);   // sin ajuste FX
  if(cur==="USD") return display(usd);
  if(!FXV.length) return display(usd);
  return display(combine(usd, fxRaw));           // CLP = USD + variación USD/CLP
}

const nf = new Intl.NumberFormat("es-CL",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtVal = (x)=>(x==null||!isFinite(x))?"—":nf.format(x);
const fmtPct = (x)=>{if(x==null||!isFinite(x))return "—";const v=x*100;return (v>0?"+":"")+nf.format(v)+"%";};
const pctCls = (x)=>{if(x==null||!isFinite(x))return "na";if(x>0.00005)return "pos";if(x<-0.00005)return "neg";return "zero";};
function parseDate(s, eod){if(!s)return null;const p=s.split("-").map(Number);return Date.UTC(p[0],p[1]-1,p[2],eod?23:0,eod?59:0,eod?59:0)/1000;}

const state = {cur:"USD"};
const tbody = document.getElementById("tbody");
const startEl = document.getElementById("start");
const endEl = document.getElementById("end");
const unitEl = document.getElementById("unit");
const KEYS = ["wk","mtd","ytd","y1","y3","y5"];

function render(){
  const cur = state.cur;
  const cs = parseDate(startEl.value, false);
  const ce = parseDate(endEl.value, true);
  fxRaw = rawMetrics(FXT, FXV, cs, ce);
  let html = "";
  for(const g of GROUPS){
    html += '<tr class="grp"><td colspan="9">'+g.label+'</td></tr>';
    for(const it of g.items){
      const m = rowMetrics(it, cur, cs, ce);
      const last = lastValue(it, cur);
      const tags = (it.native&&it.u?" · "+it.u:"") + (it.clp?" · CLP":"");
      const cells = KEYS.map(k=>'<td class="num '+pctCls(m[k])+'">'+fmtPct(m[k])+'</td>').join("");
      const sub = (m.cumAnn!=null)?'<div class="sub">anualiz. '+fmtPct(m.cumAnn)+'</div>':"";
      html += '<tr>'
        + '<td class="name"><div class="nm">'+it.n+'</div><div class="tk">'+it.t+tags+'</div></td>'
        + '<td class="num val">'+fmtVal(last)+'</td>'
        + cells
        + '<td class="num '+pctCls(m.cum)+'"><div>'+fmtPct(m.cum)+'</div>'+sub+'</td>'
        + '</tr>';
    }
  }
  tbody.innerHTML = html;
  unitEl.textContent = cur;
}

(function(){
  let latest = 0;
  for(const k in DATA){const tc=DATA[k].tc; if(tc&&tc.length) latest=Math.max(latest, tc[tc.length-1]);}
  const Ld = latest ? new Date(latest*1000) : new Date();
  const iso = (dt)=>dt.toISOString().slice(0,10);
  endEl.value = iso(Ld);
  endEl.max = iso(Ld);
  startEl.value = Ld.getUTCFullYear()+"-01-01";
  document.getElementById("asof").textContent = Ld.toLocaleDateString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric"});
  document.querySelectorAll(".seg").forEach(btn=>btn.addEventListener("click",()=>{
    state.cur = btn.dataset.c;
    document.querySelectorAll(".seg").forEach(x=>x.classList.toggle("on", x===btn));
    render();
  }));
  startEl.addEventListener("change", render);
  endEl.addEventListener("change", render);
  render();
})();
</script>
</body>
</html>'''

# ----------------------------- Escritura ---------------------------------------
out = (HTML_TEMPLATE
       .replace("/*GROUPS*/", json.dumps(GROUPS, ensure_ascii=False))
       .replace("/*DATA*/", json.dumps(DATA))
       .replace("<!--COMENTARIO-->", COMENTARIO)
       .replace("__GENERATED__", datetime.now().strftime("%d-%m-%Y %H:%M")))

fname = "panel_rentabilidades.html"
with open(fname, "w", encoding="utf-8") as f:
    f.write(out)

print(f"\nListo. Archivo generado: {fname}")
if bullets:
    print("Comentario semanal:")
    for b in bullets:
        print("  • " + b)
