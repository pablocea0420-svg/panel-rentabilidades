"""
Panel de Rentabilidades por Región
-----------------------------------
Descarga precios y genera un HTML autocontenido e interactivo:
toggle USD/CLP + selector de fechas + bullets de mercado al pie.
Todo se recalcula en el navegador desde datos incrustados (sin internet).

Fuentes:
  - ^IPSA, DX-Y.NYB, USDCLP=X, HG=F  -> Investing.com (primario), yfinance (respaldo)
  - resto de ETFs                    -> yfinance

Conversion CLP (aditiva): retorno_CLP = retorno_USD + variacion_USDCLP.
IPSA, Dollar Index, Cobre y USD/CLP NO se ajustan por tipo de cambio.

Uso (Windows):
    pip install yfinance pandas numpy cloudscraper lxml pytz
    python panel_rentabilidades.py
"""
import json
import sys
import time
from datetime import date, datetime, timezone, timedelta
from random import randint

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("Faltan dependencias. Ejecuta:  pip install yfinance pandas numpy cloudscraper lxml pytz")
    sys.exit(1)

# Dependencias opcionales para Investing (si faltan, se usa solo yfinance)
try:
    import cloudscraper as _cs
except ImportError:
    _cs = None
try:
    from lxml.html import fromstring as _lxml
except ImportError:
    _lxml = None
try:
    import pytz as _pytz
except ImportError:
    _pytz = None

import warnings
warnings.filterwarnings("ignore")

# ----------------------------- Configuracion ---------------------------------
PERIOD_DAYS = 3660          # ~10 anios de historia
INVESTING_MIN_ROWS = 100    # si Investing devuelve menos filas, usa yfinance

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

INVESTING_TICKERS = ["^IPSA", "DX-Y.NYB", "USDCLP=X", "HG=F"]
INVESTING_SOURCES = {
    "^IPSA":    ("14767",  "S&P CLX IPSA Historical Data",   "indices/ipsa-historical-data"),
    "DX-Y.NYB": ("942611", "US Dollar Index Historical Data", "indices/usdollar-historical-data"),
    "USDCLP=X": ("2110",   "USD/CLP Historical Data",         "currencies/usd-clp-historical-data"),
    "HG=F":     ("8831",   "Copper Futures Historical Data",  "commodities/copper"),
}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


# ----------------------------- Investing.com ---------------------------------
def fetch_investing(ticker, start, end):
    if _cs is None or _lxml is None or _pytz is None:
        return None
    curr_id, header, slug = INVESTING_SOURCES[ticker]
    scraper = _cs.create_scraper()
    params = {
        "curr_id": curr_id, "smlID": str(randint(1000000, 9999999)),
        "header": header, "st_date": start.strftime("%m/%d/%Y"),
        "end_date": (end + timedelta(days=2)).strftime("%m/%d/%Y"),
        "interval_sec": "Daily", "sort_col": "date", "sort_ord": "DESC",
        "action": "historical_data",
    }
    headers = {
        "User-Agent": _UA, "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html", "Origin": "https://www.investing.com",
        "Referer": f"https://www.investing.com/{slug}",
    }
    r = None
    for attempt in range(3):
        try:
            r = scraper.post("https://www.investing.com/instruments/HistoricalDataAjax",
                             headers=headers, data=params, timeout=20)
            if r.status_code == 200:
                break
        except Exception:
            r = None
        time.sleep(2 ** attempt)
    if r is None or r.status_code != 200:
        return None
    try:
        root = _lxml(r.content)
        rows = root.xpath('.//table[@id="curr_table"]/tbody/tr')
        rec = {}
        for row in rows:
            tds = row.xpath(".//td")
            if len(tds) < 2:
                continue
            raw_ts, raw_close = tds[0].get("data-real-value"), tds[1].get("data-real-value")
            if not raw_ts or not raw_close:
                continue
            d = datetime.fromtimestamp(int(raw_ts), tz=_pytz.UTC).date()
            rec[d] = float(raw_close.replace(",", ""))
        if not rec:
            return None
        idx = pd.to_datetime(sorted(rec.keys()))
        return pd.Series([rec[d.date()] for d in idx], index=idx, name="Close")
    except Exception:
        return None


# ----------------------------- yfinance ---------------------------------------
def _df_for(batch, t):
    try:
        if isinstance(batch.columns, pd.MultiIndex):
            return batch[t]
        return batch
    except Exception:
        return None


def _extract(df):
    """Devuelve (adj_series, close_series) o (None, None)."""
    if df is None or getattr(df, "empty", True):
        return None, None
    cols = df.columns
    if "Close" not in cols and "Adj Close" not in cols:
        return None, None
    close = df["Close"].dropna() if "Close" in cols else df["Adj Close"].dropna()
    adj = df["Adj Close"].dropna() if "Adj Close" in cols else close
    for s in (close, adj):
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
    return adj, close


def fetch_yf_single(ticker, start, end):
    try:
        b = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                        end=(end + timedelta(days=2)).strftime("%Y-%m-%d"),
                        auto_adjust=False, group_by="ticker", threads=False, progress=False)
        return _extract(_df_for(b, ticker))
    except Exception:
        return None, None


# ----------------------------- Conversion a arrays ----------------------------
def to_arrays(s):
    ts, vs = [], []
    if s is None:
        return ts, vs
    for idx, val in s.items():
        if pd.isna(val):
            continue
        d = idx.date() if hasattr(idx, "date") else idx
        sec = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        ts.append(sec)
        vs.append(round(float(val), 4))
    return ts, vs


# ----------------------------- Descarga total ---------------------------------
def download_all():
    start = date.today() - timedelta(days=PERIOD_DAYS)
    end = date.today()
    DATA, bull, failed = {}, {}, []

    # 1) yfinance en lote para todo lo que no es Investing
    non_inv = [t for t in ALL if t not in INVESTING_TICKERS]
    print(f"Descargando {len(non_inv)} instrumentos por yfinance...")
    batch = yf.download(non_inv, start=start.strftime("%Y-%m-%d"),
                        end=(end + timedelta(days=2)).strftime("%Y-%m-%d"),
                        auto_adjust=False, group_by="ticker", threads=True, progress=False)
    for t in non_inv:
        adj, close = _extract(_df_for(batch, t))
        if adj is None:
            failed.append(t); continue
        ta, av = to_arrays(adj); tc, cv = to_arrays(close)
        DATA[t] = {"ta": ta, "adj": av, "tc": tc, "close": cv}
        bull[t] = adj

    # 2) Investing (primario) con respaldo yfinance
    print("Descargando IPSA / Dollar Index / USD/CLP / Cobre por Investing...")
    for t in INVESTING_TICKERS:
        s = fetch_investing(t, start, end)
        src = "investing"
        if s is None or len(s) < INVESTING_MIN_ROWS:
            adj, close = fetch_yf_single(t, start, end)
            src = "yfinance (respaldo)"
        else:
            adj = close = s
        if adj is None:
            failed.append(t)
            print(f"  {t:<12} [!] sin datos")
            continue
        ta, av = to_arrays(adj); tc, cv = to_arrays(close)
        DATA[t] = {"ta": ta, "adj": av, "tc": tc, "close": cv}
        bull[t] = adj
        print(f"  {t:<12} [ok] {len(av):4d} filas ({src})")

    return DATA, bull, failed


# ----------------------------- Bullets de mercado -----------------------------
def safe_ret(p1, p0):
    if p1 is None or p0 is None or p0 == 0:
        return None
    return p1 / p0 - 1.0


def build_bullets(bull, last_fri, prev_fri):
    def aprice(s, d):
        if s is None or len(s) == 0:
            return None
        v = s.asof(pd.Timestamp(d))
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)

    def wret(name):
        return safe_ret(aprice(bull.get(name), last_fri), aprice(bull.get(name), prev_fri))

    bullets = []

    # Bullet 1: mercados desarrollados y emergentes
    ret_dm, ret_em = wret("URTH"), wret("EEM")
    if ret_dm is not None and ret_em is not None:
        if ret_dm > 0 and ret_em > 0:
            tono, verbo = "positivos", "impulsados"
        elif ret_dm < 0 and ret_em < 0:
            tono, verbo = "negativos", "marcados"
        else:
            tono, verbo = "mixtos", "influenciados"
        bullets.append(
            f"Semana con retornos {tono} en mercados desarrollados y emergentes, {verbo} por …"
        )

    # Bullet 2: forex, dolar y cobre
    usdclp_ret, dxy_ret, cobre_ret = wret("USDCLP=X"), wret("DX-Y.NYB"), wret("HG=F")
    if usdclp_ret is not None:
        p1, p0 = aprice(bull.get("USDCLP=X"), last_fri), aprice(bull.get("USDCLP=X"), prev_fri)
        var_pesos = abs(round(p1 - p0, 0)) if (p1 and p0) else abs(round(usdclp_ret * 900, 0))
        mov_peso = "depreció" if usdclp_ret > 0 else "apreció"
        efecto = "un aumento" if usdclp_ret > 0 else "una disminución"
        peso_dep = usdclp_ret > 0

        en_linea, pese_a = [], []
        if dxy_ret is not None:
            dxy_sube = dxy_ret > 0
            txt = (f"la {'apreciación' if dxy_sube else 'depreciación'} de "
                   f"{abs(dxy_ret*100):.2f}% del dólar a nivel internacional")
            (en_linea if peso_dep == dxy_sube else pese_a).append(txt)
        if cobre_ret is not None:
            consistente = (peso_dep and cobre_ret < 0) or (not peso_dep and cobre_ret > 0)
            art = "el" if cobre_ret > 0 else "la"
            mov = "alza" if cobre_ret > 0 else "caída"
            txt = f"{art} {mov} de {abs(cobre_ret*100):.2f}% en el precio del cobre"
            (en_linea if consistente else pese_a).append(txt)

        sufijos = []
        if en_linea:
            sufijos.append("en línea con " + " y ".join(en_linea))
        if pese_a:
            sufijos.append("en desacople con " + " y ".join(pese_a))

        b = (f"Por el lado del Forex, el peso chileno se {mov_peso} un {abs(usdclp_ret*100):.2f}%, "
             f"lo que equivale a {efecto} de alrededor de {var_pesos:,.0f} pesos")
        if sufijos:
            b += ", " + ", ".join(sufijos)
        bullets.append(b + ".")

    return bullets


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
.bullets{padding:14px 20px;border-top:1px solid #e2e8f0}
.bullets .bt{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:600;margin-bottom:6px}
.bullets p{margin:6px 0;font-size:13px;color:#334155;line-height:1.55}
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
  <div class="bullets" id="bullets"></div>
  <div class="foot">
    <div><b>*</b> 3a y 5a anualizados. <b>Sem.</b> = último viernes vs. viernes previo. <b>MTD/YTD</b> desde el último cierre del mes/año anterior.</div>
    <div>Vista CLP (aditiva): <b>retorno USD + variación USD/CLP</b> del período. IPSA, Dollar Index, Cobre y USD/CLP se muestran sin ajuste de tipo de cambio.</div>
    <div>Retornos de ETFs sobre precio ajustado (dividendos reinvertidos). Fuentes: IPSA/Dollar Index/USD/CLP/Cobre vía Investing.com (respaldo yfinance); resto vía yfinance.</div>
  </div>
</div>
<script>
const GROUPS = /*GROUPS*/;
const DATA = /*DATA*/;
const BULLETS = /*BULLETS*/;

const UT = (DATA["USDCLP=X"] || {}).tc || [];
const UV = (DATA["USDCLP=X"] || {}).close || [];

function idxBefore(t,x){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]<=x){a=m;lo=m+1;}else hi=m-1;}return a;}
function idxAfter(t,x){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]>=x){a=m;hi=m-1;}else lo=m+1;}return a;}
function asof(t,v,sec){const i=idxBefore(t,sec);return i<0?null:v[i];}
function fxAsof(sec){return asof(UT,UV,sec);}
function ret(a,b){return (a==null||b==null||!isFinite(a)||!isFinite(b)||b===0)?null:a/b-1;}
const YR = 365.25*86400;

function calc(item, cur, cs, ce){
  const d = DATA[item.t];
  const out = {m:{}, last:null};
  if(!d) return out;
  const lc  = d.close.length ? d.close[d.close.length-1] : null;
  const lcT = d.tc.length    ? d.tc[d.tc.length-1]       : null;
  if(cur==="CLP" && !item.native && !item.clp){
    const f = (lcT!=null)?fxAsof(lcT):null;
    out.last = (lc!=null && f)? lc*f : null;
  } else {
    out.last = lc;
  }
  if(!d.ta || d.ta.length<2) return out;
  const t=d.ta, v=d.adj, n=t.length-1, lastV=v[n], lastT=t[n];
  const D=new Date(lastT*1000), Y=D.getUTCFullYear(), M=D.getUTCMonth(), DD=D.getUTCDate();
  const needFx = (cur==="CLP") && !item.native && !item.clp;
  const m = out.m;

  function periodTo(startSec){
    const nat = ret(lastV, asof(t,v,startSec));
    if(nat==null) return null;
    if(!needFx) return nat;
    const f = ret(fxAsof(lastT), fxAsof(startSec));
    return (f==null)?nat:nat+f;
  }

  const fri=[]; for(let i=0;i<t.length;i++){ if(new Date(t[i]*1000).getUTCDay()===5) fri.push(i); }
  if(fri.length>=2){
    const a=fri[fri.length-1], b=fri[fri.length-2];
    let r=ret(v[a],v[b]);
    if(r!=null){ if(needFx){ const f=ret(fxAsof(t[a]),fxAsof(t[b])); if(f!=null) r+=f; } m.wk=r; }
  }
  m.mtd=periodTo(Date.UTC(Y,M,0)/1000);
  m.ytd=periodTo(Date.UTC(Y,0,0)/1000);
  m.y1 =periodTo(Date.UTC(Y-1,M,DD)/1000);
  const s3=Date.UTC(Y-3,M,DD)/1000, i3=idxBefore(t,s3);
  if(i3>=0){ const c=periodTo(s3); if(c!=null){ const yrs=(lastT-t[i3])/YR; if(yrs>0) m.y3=Math.pow(1+c,1/yrs)-1; } }
  const s5=Date.UTC(Y-5,M,DD)/1000, i5=idxBefore(t,s5);
  if(i5>=0){ const c=periodTo(s5); if(c!=null){ const yrs=(lastT-t[i5])/YR; if(yrs>0) m.y5=Math.pow(1+c,1/yrs)-1; } }

  if(cs&&ce&&ce>cs){
    const si=idxAfter(t,cs), ei=idxBefore(t,ce);
    if(si>=0&&ei>=0&&t[ei]>t[si]){
      let cum=ret(v[ei],v[si]);
      if(cum!=null){
        if(needFx){ const f=ret(fxAsof(t[ei]),fxAsof(t[si])); if(f!=null) cum+=f; }
        m.cum=cum;
        const yrs=(t[ei]-t[si])/YR; m.cumAnn = (yrs>=1)?Math.pow(1+cum,1/yrs)-1:null;
      }
    }
  }
  return out;
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
  let html = "";
  for(const g of GROUPS){
    html += '<tr class="grp"><td colspan="9">'+g.label+'</td></tr>';
    for(const it of g.items){
      const {m,last} = calc(it, cur, cs, ce);
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

  const bx = document.getElementById("bullets");
  if(BULLETS && BULLETS.length){
    bx.innerHTML = '<div class="bt">Comentario de mercado (semana)</div>' + BULLETS.map(b=>'<p>• '+b+'</p>').join('');
  } else { bx.style.display = "none"; }

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


# ----------------------------- Main -------------------------------------------
def main():
    DATA, bull, failed = download_all()

    today = date.today()
    days_back = (today.weekday() - 4) % 7
    last_fri = today - timedelta(days=days_back)
    prev_fri = last_fri - timedelta(weeks=1)
    bullets = build_bullets(bull, last_fri, prev_fri)

    print("\nBullets generados:")
    for b in bullets:
        print(f"  • {b}")
    if failed:
        print("\n  Sin datos: " + ", ".join(failed))

    out = (HTML_TEMPLATE
           .replace("/*GROUPS*/", json.dumps(GROUPS, ensure_ascii=False))
           .replace("/*DATA*/", json.dumps(DATA))
           .replace("/*BULLETS*/", json.dumps(bullets, ensure_ascii=False))
           .replace("__GENERATED__", datetime.now().strftime("%d-%m-%Y %H:%M")))

    fname = "panel_rentabilidades.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\nListo. Archivo generado: {fname}")


if __name__ == "__main__":
    main()
