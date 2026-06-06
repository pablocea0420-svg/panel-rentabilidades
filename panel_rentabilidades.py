"""
Panel de Rentabilidades por Región
-----------------------------------
Descarga precios desde Yahoo Finance (via yfinance) y genera un HTML
autocontenido e interactivo: toggle USD/CLP + selector de fechas, todo
recalculado en el navegador desde datos incrustados (sin internet, sin proxies).

Uso (Windows):
    pip install yfinance pandas
    python panel_rentabilidades.py
Luego abre 'panel_rentabilidades.html' con doble clic.
"""
import json
import sys
from datetime import datetime, timezone

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Faltan dependencias. Ejecuta:  pip install yfinance pandas")
    sys.exit(1)

# ----------------------------- Configuración ---------------------------------
PERIOD = "10y"  # historia descargada (valores válidos yfinance: 1y,2y,5y,10y,max)

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

# ----------------------------- Descarga ---------------------------------------
print(f"Descargando {len(ALL)} instrumentos desde Yahoo Finance ({PERIOD})...")
data = yf.download(ALL, period=PERIOD, interval="1d", auto_adjust=False,
                   group_by="ticker", threads=True, progress=False)


def extract(tk):
    try:
        df = data[tk]
    except Exception:
        return None
    if df is None or getattr(df, "empty", True):
        return None
    cols = df.columns
    adj_col = "Adj Close" if "Adj Close" in cols else ("Close" if "Close" in cols else None)
    if adj_col is None:
        return None
    ta, adj, tc, close = [], [], [], []
    for ts, row in df.iterrows():
        sec = int(datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc).timestamp())
        a = row.get(adj_col)
        c = row.get("Close") if "Close" in cols else a
        if pd.notna(a):
            ta.append(sec); adj.append(round(float(a), 4))
        if pd.notna(c):
            tc.append(sec); close.append(round(float(c), 4))
    if not ta and not tc:
        return None
    return {"ta": ta, "adj": adj, "tc": tc, "close": close}


DATA, failed = {}, []
for tk in ALL:
    d = extract(tk)
    if d:
        DATA[tk] = d
    else:
        failed.append(tk)

if failed:
    print("  Advertencia, no se pudieron cargar: " + ", ".join(failed))

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
  <div class="foot">
    <div><b>*</b> 3a y 5a anualizados. <b>Sem.</b> = último viernes vs. viernes previo. <b>MTD/YTD</b> desde el último cierre del mes/año anterior.</div>
    <div>Rentabilidades sobre <b>precio ajustado</b> (dividendos reinvertidos); "Último" muestra el precio de cierre. Conversión a CLP punto a punto con el USD/CLP de cada fecha.</div>
    <div>Bloque Dólar/Cobre en unidades nativas. ^IPSA es nativo en CLP (vista USD = IPSA / USD/CLP). Fuente: Yahoo Finance via yfinance.</div>
  </div>
</div>
<script>
const GROUPS = /*GROUPS*/;
const DATA = /*DATA*/;

const UT = (DATA["USDCLP=X"] || {}).tc || [];
const UV = (DATA["USDCLP=X"] || {}).close || [];

function idxBefore(t, target){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]<=target){a=m;lo=m+1;}else hi=m-1;}return a;}
function idxAfter(t, target){let lo=0,hi=t.length-1,a=-1;while(lo<=hi){const m=(lo+hi)>>1;if(t[m]>=target){a=m;hi=m-1;}else lo=m+1;}return a;}
function usdAt(sec){if(!UT.length)return null;let i=idxBefore(UT,sec);if(i<0)i=0;return UV[i];}

function buildVals(it, cur){
  const d = DATA[it.t];
  if(!d || !d.ta || !d.ta.length) return null;
  const t = d.ta, adj = d.adj;
  const lastClose = d.close.length ? d.close[d.close.length-1] : null;
  const lastCloseT = d.tc.length ? d.tc[d.tc.length-1] : null;
  if(it.native) return {t, v:adj, last:lastClose};
  if(it.clp){ // ^IPSA nativo CLP
    if(cur==="CLP") return {t, v:adj, last:lastClose};
    if(!UT.length) return null;
    const v = adj.map((x,i)=>{const u=usdAt(t[i]);return u?x/u:NaN;});
    const lu = usdAt(lastCloseT);
    return {t, v, last:(lastClose!=null&&lu)?lastClose/lu:null};
  }
  if(cur==="USD") return {t, v:adj, last:lastClose};
  if(!UT.length) return null;
  const v = adj.map((x,i)=>{const u=usdAt(t[i]);return u?x*u:NaN;});
  const lu = usdAt(lastCloseT);
  return {t, v, last:(lastClose!=null&&lu)?lastClose*lu:null};
}

function ret(a,b){return (a==null||b==null||!isFinite(a)||!isFinite(b)||b===0)?null:a/b-1;}
const YR = 365.25*86400;

function metrics(t, v, cs, ce){
  const m = {};
  if(!t || t.length<2) return m;
  const n = t.length-1, lastV = v[n], lastT = t[n];
  const D = new Date(lastT*1000), Y=D.getUTCFullYear(), M=D.getUTCMonth(), DD=D.getUTCDate();
  const fri = [];
  for(let i=0;i<t.length;i++){ if(new Date(t[i]*1000).getUTCDay()===5) fri.push(i); }
  if(fri.length>=2) m.wk = ret(v[fri[fri.length-1]], v[fri[fri.length-2]]);
  const at = (sec)=>{const i=idxBefore(t,sec);return i<0?null:v[i];};
  m.mtd = ret(lastV, at(Date.UTC(Y,M,0)/1000));
  m.ytd = ret(lastV, at(Date.UTC(Y,0,0)/1000));
  m.y1  = ret(lastV, at(Date.UTC(Y-1,M,DD)/1000));
  const s3=Date.UTC(Y-3,M,DD)/1000, i3=idxBefore(t,s3);
  if(i3>=0){const yrs=(lastT-t[i3])/YR; if(yrs>0&&v[i3]>0) m.y3=Math.pow(lastV/v[i3],1/yrs)-1;}
  const s5=Date.UTC(Y-5,M,DD)/1000, i5=idxBefore(t,s5);
  if(i5>=0){const yrs=(lastT-t[i5])/YR; if(yrs>0&&v[i5]>0) m.y5=Math.pow(lastV/v[i5],1/yrs)-1;}
  if(cs&&ce&&ce>cs){
    const si=idxAfter(t,cs), ei=idxBefore(t,ce);
    if(si>=0&&ei>=0&&t[ei]>t[si]){
      m.cum = v[ei]/v[si]-1;
      const yrs=(t[ei]-t[si])/YR;
      m.cumAnn = (yrs>=1&&v[si]>0)?Math.pow(v[ei]/v[si],1/yrs)-1:null;
    }
  }
  return m;
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
      const b = buildVals(it, cur);
      const m = b ? metrics(b.t, b.v, cs, ce) : {};
      const last = b ? b.last : null;
      const tags = (it.native&&it.u?" · "+it.u:"") + (it.clp?" · CLP":"");
      let cells = KEYS.map(k=>'<td class="num '+pctCls(m[k])+'">'+fmtPct(m[k])+'</td>').join("");
      const customSub = (m.cumAnn!=null)?'<div class="sub">anualiz. '+fmtPct(m.cumAnn)+'</div>':"";
      html += '<tr>'
        + '<td class="name"><div class="nm">'+it.n+'</div><div class="tk">'+it.t+tags+'</div></td>'
        + '<td class="num val">'+fmtVal(last)+'</td>'
        + cells
        + '<td class="num '+pctCls(m.cum)+'"><div>'+fmtPct(m.cum)+'</div>'+customSub+'</td>'
        + '</tr>';
    }
  }
  tbody.innerHTML = html;
  unitEl.textContent = cur;
}

// init
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
       .replace("__GENERATED__", datetime.now().strftime("%d-%m-%Y %H:%M")))

fname = "panel_rentabilidades.html"
with open(fname, "w", encoding="utf-8") as f:
    f.write(out)

print(f"\nListo. Archivo generado: {fname}")
print("Ábrelo con doble clic. Funciona sin conexión y sin proxies; el toggle USD/CLP")
print("y las fechas recalculan en el navegador desde los datos incrustados.")
