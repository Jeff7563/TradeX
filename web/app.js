/* TradeX chart page: candles from the local server + ICT/SMC overlay. */
(async function () {
  const cfg = await (await fetch('/api/config')).json();
  const TZ = (cfg.timezone_offset_hours || 0) * 3600; // show Thai time
  const state = { symbol: cfg.symbols[0], tf: cfg.timeframes.includes('M15') ? 'M15' : cfg.timeframes[0],
                  data: null, ws: null, lastTime: null,
                  layers: { structure: true, fvg: true, ob: true, range: true, kz: true } };
  const COLORS = { bull: '#26a69a', bear: '#ef5350' };

  const el = document.getElementById('chart');
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: '#0f1115' }, textColor: '#d6d9e0' },
    grid: { vertLines: { color: '#1b1f27' }, horzLines: { color: '#1b1f27' } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#262a33' },
    rightPriceScale: { borderColor: '#262a33' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  const series = chart.addCandlestickSeries({
    upColor: COLORS.bull, downColor: COLORS.bear, borderVisible: false,
    wickUpColor: COLORS.bull, wickDownColor: COLORS.bear,
  });

  // ---- buttons -------------------------------------------------------
  function buttons(id, items, key) {
    const box = document.getElementById(id);
    box.innerHTML = '';
    items.forEach(v => {
      const b = document.createElement('button');
      b.textContent = v;
      b.className = state[key] === v ? 'on' : '';
      b.onclick = () => { state[key] = v; buttons(id, items, key); connect(); };
      box.appendChild(b);
    });
  }
  buttons('symbols', cfg.symbols, 'symbol');
  buttons('timeframes', cfg.timeframes, 'tf');
  document.querySelectorAll('[data-layer]').forEach(cb => {
    cb.onchange = () => { state.layers[cb.dataset.layer] = cb.checked; draw(); };
  });
  const src = document.getElementById('source');
  src.textContent = cfg.source === 'mt5' ? 'MT5 live' : 'SIM (ราคาจำลอง)';
  src.className = 'pill' + (cfg.source === 'mt5' ? '' : ' sim');

  // ---- data ----------------------------------------------------------
  const toBar = c => ({ time: c.time + TZ, open: c.open, high: c.high, low: c.low, close: c.close });

  function apply(data, fresh) {
    const bars = data.candles.map(toBar);
    if (fresh || state.lastTime === null) {
      series.setData(bars);
    } else {
      bars.filter(b => b.time >= state.lastTime).forEach(b => series.update(b));
    }
    state.lastTime = bars.length ? bars[bars.length - 1].time : null;
    state.data = data;
    const digits = state.symbol.startsWith('BTC') ? 2 : 2;
    const last = data.candles[data.candles.length - 1];
    document.getElementById('price').textContent =
      `${state.symbol} ${last ? last.close.toFixed(digits) : '-'}`;
    const t = document.getElementById('trend');
    const tr = data.smc.trend;
    t.textContent = tr === 'bull' ? 'โครงสร้าง: ขาขึ้น' : tr === 'bear' ? 'โครงสร้าง: ขาลง' : 'โครงสร้าง: -';
    t.className = 'pill ' + (tr === 'bull' || tr === 'bear' ? tr : '');
    draw();
  }

  function connect() {
    if (state.ws) { state.ws.onclose = null; state.ws.close(); }
    state.lastTime = null;
    let fresh = true;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws?symbol=${state.symbol}&tf=${state.tf}`);
    const dot = document.getElementById('conn');
    ws.onopen = () => dot.classList.add('ok');
    ws.onmessage = ev => {
      apply(JSON.parse(ev.data), fresh);
      if (fresh) { chart.timeScale().scrollToRealTime(); fresh = false; }
    };
    ws.onclose = () => { dot.classList.remove('ok'); setTimeout(connect, 2000); };
    state.ws = ws;
  }

  // ---- overlay drawing ----------------------------------------------
  const cv = document.getElementById('overlay');
  const ctx = cv.getContext('2d');

  // time (UTC) -> x pixel, works between bars and past the last bar
  function xOf(t) {
    const c = state.data.candles;
    if (!c.length) return null;
    const step = c.length > 1 ? c[c.length - 1].time - c[c.length - 2].time : 60;
    let lo = 0, hi = c.length - 1;
    if (t >= c[hi].time) return chart.timeScale().logicalToCoordinate(hi + (t - c[hi].time) / step);
    if (t <= c[0].time) return chart.timeScale().logicalToCoordinate((t - c[0].time) / step);
    while (hi - lo > 1) { const m = (lo + hi) >> 1; (c[m].time <= t ? lo = m : hi = m); }
    const frac = (t - c[lo].time) / Math.max(c[hi].time - c[lo].time, 1);
    return chart.timeScale().logicalToCoordinate(lo + frac);
  }
  const yOf = p => series.priceToCoordinate(p);

  function box(x1, x2, p1, p2, fill, stroke) {
    const y1 = yOf(p1), y2 = yOf(p2);
    if (x1 === null || y1 === null || y2 === null) return;
    ctx.fillStyle = fill;
    ctx.fillRect(x1, Math.min(y1, y2), Math.max(x2 - x1, 1), Math.abs(y2 - y1) || 1);
    if (stroke) { ctx.strokeStyle = stroke; ctx.strokeRect(x1, Math.min(y1, y2), Math.max(x2 - x1, 1), Math.abs(y2 - y1) || 1); }
  }
  function label(text, x, y, color) {
    ctx.font = '10px system-ui, sans-serif';
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const w = el.clientWidth, h = el.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.width = w + 'px'; cv.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!state.data) return;
    const smc = state.data.smc;
    const right = w - chart.priceScale('right').width();
    const timeAxis = chart.timeScale().height();
    ctx.save();
    ctx.beginPath(); ctx.rect(0, 0, right, h - timeAxis); ctx.clip();

    if (state.layers.kz) {
      smc.kill_zones.forEach(k => {
        const x1 = xOf(k.start), x2 = xOf(k.end);
        if (x1 === null || x2 === null || x2 < 0 || x1 > right) return;
        ctx.fillStyle = k.name === 'London' ? 'rgba(76,141,255,0.07)' : 'rgba(240,180,41,0.07)';
        ctx.fillRect(x1, 0, x2 - x1, h - timeAxis);
        label(k.name === 'London' ? 'LDN' : 'NY', x1 + 3, 12, 'rgba(214,217,224,0.45)');
      });
    }
    if (state.layers.range && smc.range) {
      const r = smc.range;
      const yh = yOf(r.high), ye = yOf(r.eq), yl = yOf(r.low);
      if (yh !== null && yl !== null) {
        ctx.fillStyle = 'rgba(239,83,80,0.05)'; ctx.fillRect(0, yh, right, ye - yh);
        ctx.fillStyle = 'rgba(38,166,154,0.05)'; ctx.fillRect(0, ye, right, yl - ye);
        ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(214,217,224,0.35)';
        ctx.beginPath(); ctx.moveTo(0, ye); ctx.lineTo(right, ye); ctx.stroke(); ctx.setLineDash([]);
        label('Premium', 6, yh + 12, 'rgba(239,83,80,0.7)');
        label('EQ 50%', 6, ye - 4, 'rgba(214,217,224,0.6)');
        label('Discount', 6, yl - 4, 'rgba(38,166,154,0.7)');
      }
    }
    if (state.layers.fvg) {
      smc.fvgs.forEach(g => {
        const x1 = xOf(g.time);
        const col = g.dir === 'bull' ? 'rgba(38,166,154,0.18)' : 'rgba(239,83,80,0.18)';
        box(x1, right, g.top, g.bottom, col);
        if (x1 !== null) label('FVG', x1 + 2, yOf(g.top) - 2, g.dir === 'bull' ? COLORS.bull : COLORS.bear);
      });
    }
    if (state.layers.ob) {
      smc.order_blocks.forEach(o => {
        const x1 = xOf(o.time);
        const fill = o.dir === 'bull' ? 'rgba(38,166,154,0.12)' : 'rgba(239,83,80,0.12)';
        const stroke = o.dir === 'bull' ? 'rgba(38,166,154,0.7)' : 'rgba(239,83,80,0.7)';
        box(x1, right, o.top, o.bottom, fill, stroke);
        if (x1 !== null) label(o.dir === 'bull' ? '+OB' : '-OB', x1 + 2, yOf(o.bottom) + 11, stroke);
      });
    }
    if (state.layers.structure) {
      smc.structure.slice(-12).forEach(e => {
        const x1 = xOf(e.from_time), x2 = xOf(e.time), y = yOf(e.price);
        if (x1 === null || x2 === null || y === null) return;
        const col = e.dir === 'bull' ? COLORS.bull : COLORS.bear;
        ctx.strokeStyle = col; ctx.lineWidth = 1;
        if (e.kind === 'CHoCH') ctx.setLineDash([5, 3]);
        ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke(); ctx.setLineDash([]);
        label(e.kind, (x1 + x2) / 2 - 12, e.dir === 'bull' ? y - 3 : y + 11, col);
      });
    }
    ctx.restore();
  }

  chart.timeScale().subscribeVisibleLogicalRangeChange(() => requestAnimationFrame(draw));
  new ResizeObserver(() => requestAnimationFrame(draw)).observe(el);
  connect();
})();
