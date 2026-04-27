import { useState, useMemo } from "react";

// ════════════════════════════════════════════════════════════════════
// GITAGENT v5.6 — INSTITUTIONAL PREDICTION MARKETS ENGINE
// ════════════════════════════════════════════════════════════════════
// v5.2 ARB:  Prediction Market Cross-Market Arbitrage Detection
// v5.3 RISK: Michael Burry (MB) Contrarian Agent + Risk Manager Limits
// v5.4 LMSR: Logarithmic Market Scoring Rule (LMSR) Math + EV engine
// v5.5 QNT:  Data Science Quant Metrics (Sharpe, Vol, MaxDD)
// v5.6 NEW:  Empirical Kelly Sizing, Conditional Graphs, Calibration
// ════════════════════════════════════════════════════════════════════

const AGENTS = {
  W: { name: "Williams", color: "#F59E0B", icon: "W" },
  Wy: { name: "Wyckoff", color: "#06B6D4", icon: "Wy" },
  B: { name: "Brooks", color: "#EC4899", icon: "B" },
  Be: { name: "Berlekamp", color: "#A855F7", icon: "Be" },
  T: { name: "Thorp", color: "#10B981", icon: "T" },
  M: { name: "Macro", color: "#EF4444", icon: "M" },
  S: { name: "SMC", color: "#3B82F6", icon: "S" },
  MB: { name: "Burry", color: "#9333EA", icon: "MB" },
  RPB: { name: "RPBERT", color: "#F43F5E", icon: "RPB" },
  LLM: { name: "LLM", color: "#6366F1", icon: "LLM" },
  WHL: { name: "Whale", color: "#0EA5E9", icon: "WHL" },
  SEN: { name: "Sentiment", color: "#8B5CF6", icon: "SEN" },
};

const MACRO = { gold: 5129, oil: 67.2, t3m: 4.32, t10y: 4.15, vix: 29.49, spYield: 1.35 };

// ─── SMC DATA PER TICKER (computed from daily OHLCV) ───
// In production: smc.py computes these from Alpaca/AV bar data
// Here: pre-computed for Mar 6 2026 close
const SMC_DATA = {
  PLTR: {
    swingHigh: 161.45, swingLow: 140.20, lastBOS: 1, lastCHOCH: 0,
    obZones: [{ type: "bull", top: 152.8, bot: 150.1, mitigated: false }, { type: "bear", top: 163.5, bot: 161.0, mitigated: false }],
    fvg: [{ type: "bull", top: 155.2, bot: 152.8, filled: false }, { type: "bear", top: 162.1, bot: 159.8, filled: false }],
    liqLevels: [{ side: "buy", level: 140.20, swept: false }, { side: "sell", level: 161.45, swept: false }],
    retracePct: 0.38, deepestRetrace: 0.52,
    structure: "BULLISH", lastStructBreak: "2026-03-04"
  },
  MELI: {
    swingHigh: 1794.17, swingLow: 1665.00, lastBOS: 1, lastCHOCH: 0,
    obZones: [{ type: "bull", top: 1710, bot: 1685, mitigated: false }, { type: "bear", top: 1810, bot: 1795, mitigated: false }],
    fvg: [{ type: "bull", top: 1745, bot: 1720, filled: false }],
    liqLevels: [{ side: "buy", level: 1665, swept: false }, { side: "sell", level: 1794.17, swept: false }],
    retracePct: 0.45, deepestRetrace: 0.58,
    structure: "BULLISH", lastStructBreak: "2026-03-01"
  },
  GE: {
    swingHigh: 340.20, swingLow: 320.50, lastBOS: 1, lastCHOCH: 0,
    obZones: [{ type: "bull", top: 330, bot: 326, mitigated: false }],
    fvg: [{ type: "bull", top: 335, bot: 331, filled: true }],
    liqLevels: [{ side: "buy", level: 320.50, swept: false }, { side: "sell", level: 340.20, swept: false }],
    retracePct: 0.25, deepestRetrace: 0.48,
    structure: "BULLISH", lastStructBreak: "2026-02-28"
  },
  NVDA: {
    swingHigh: 192.50, swingLow: 166.80, lastBOS: -1, lastCHOCH: -1,
    obZones: [{ type: "bear", top: 188, bot: 185, mitigated: false }, { type: "bull", top: 172, bot: 168, mitigated: false }],
    fvg: [{ type: "bear", top: 186, bot: 182, filled: false }, { type: "bull", top: 170, bot: 167, filled: false }],
    liqLevels: [{ side: "buy", level: 166.80, swept: false }, { side: "sell", level: 192.50, swept: true }],
    retracePct: 0.57, deepestRetrace: 0.62,
    structure: "BEARISH", lastStructBreak: "2026-03-05"
  },
  NOC: {
    swingHigh: 770.00, swingLow: 720.50, lastBOS: 0, lastCHOCH: 0,
    obZones: [{ type: "bull", top: 735, bot: 728, mitigated: false }],
    fvg: [],
    liqLevels: [{ side: "buy", level: 720.50, swept: false }, { side: "sell", level: 770, swept: false }],
    retracePct: 0.33, deepestRetrace: 0.40,
    structure: "RANGING", lastStructBreak: "2026-02-20"
  },
  RTX: {
    swingHigh: 209.95, swingLow: 189.30, lastBOS: 1, lastCHOCH: 1,
    obZones: [{ type: "bull", top: 200, bot: 197, mitigated: true }, { type: "bull", top: 205, bot: 202, mitigated: false }],
    fvg: [{ type: "bull", top: 207, bot: 204, filled: false }],
    liqLevels: [{ side: "buy", level: 189.30, swept: false }, { side: "sell", level: 209.95, swept: false }],
    retracePct: 0.12, deepestRetrace: 0.35,
    structure: "BULLISH", lastStructBreak: "2026-03-06"
  },
};

// ─── PRICE && FUNDAMENTALS && QUANT DATA ───
const WATCHLIST = [
  { sym: "PLTR", price: 157.16, chg: 2.94, o: 150.44, h: 161.45, l: 150.29, v: 75e6, rsi: 62, sma50: 148.2, sma200: 132.5, macdH: 1.8, ad: 0.78, stochK: 71, stochD: 65, bbU: 165.3, bbM: 153.1, bbL: 140.9, sent: 0.24, beta: 2.15, fcfYield: 0.04, debtEq: 0.1, pe: 85, insider: "sell", annRet: 0.45, annVol: 0.65, sharpe: 0.69, maxDD: -0.42 },
  { sym: "MELI", price: 1787.86, chg: 0.42, o: 1758.13, h: 1794.17, l: 1738.55, v: 440e3, rsi: 55, sma50: 1720, sma200: 1650, macdH: 0.9, ad: 0.68, stochK: 58, stochD: 52, bbU: 1850, bbM: 1760, bbL: 1670, sent: 0.18, beta: 1.45, fcfYield: 0.06, debtEq: 0.8, pe: 42, insider: "hold", annRet: 0.28, annVol: 0.35, sharpe: 0.80, maxDD: -0.28 },
  { sym: "GE", price: 339.75, chg: 1.67, o: 334.1, h: 340.2, l: 329.8, v: 5.2e6, rsi: 58, sma50: 335, sma200: 310, macdH: 1.2, ad: 0.54, stochK: 63, stochD: 59, bbU: 355, bbM: 338, bbL: 321, sent: 0.31, beta: 1.22, fcfYield: 0.09, debtEq: 0.5, pe: 25, insider: "buy", annRet: 0.18, annVol: 0.22, sharpe: 0.82, maxDD: -0.21 },
  { sym: "NVDA", price: 177.82, chg: -3.01, o: 179.84, h: 182.76, l: 176.82, v: 189e6, rsi: 38, sma50: 185, sma200: 165, macdH: -2.1, ad: 0.56, stochK: 22, stochD: 28, bbU: 198, bbM: 182, bbL: 166, sent: -0.12, beta: 1.95, fcfYield: 0.03, debtEq: 0.2, pe: 65, insider: "sell", annRet: 0.62, annVol: 0.58, sharpe: 1.07, maxDD: -0.35 },
  { sym: "NOC", price: 753.83, chg: -0.70, o: 759.1, h: 760.2, l: 748.5, v: 1.1e6, rsi: 48, sma50: 740, sma200: 710, macdH: 0.3, ad: -0.18, stochK: 42, stochD: 45, bbU: 775, bbM: 748, bbL: 721, sent: 0.08, beta: 0.55, fcfYield: 0.14, debtEq: 0.6, pe: 14, insider: "buy", annRet: 0.12, annVol: 0.15, sharpe: 0.80, maxDD: -0.15 },
  { sym: "RTX", price: 209.76, chg: 2.89, o: 204.01, h: 209.95, l: 203.64, v: 8.8e6, rsi: 67, sma50: 198, sma200: 185, macdH: 2.4, ad: 0.27, stochK: 82, stochD: 78, bbU: 215, bbM: 202, bbL: 189, sent: 0.15, beta: 0.85, fcfYield: 0.11, debtEq: 1.2, pe: 18, insider: "hold", annRet: 0.16, annVol: 0.19, sharpe: 0.84, maxDD: -0.12 },
];

// ─── LMSR PREDICTION MARKET DATA (INSTITUTIONAL PORTFOLIO) ───
// b = liquidity parameter (market depth)
// q = quantity vector [Yes, No]
// extEdge = true probability edge derived from Probability Engine
// dependsOn = Logical constraint requirement ID
const ARB_PAIRS = [
  { id: 1, market: "Fed rate cut Mar", b: 1000, q: [600, 200], myEst: 0.75, cv: 0.15, dependsOn: null },
  { id: 2, market: "BTC > $100k Q1", b: 5000, q: [1200, 1800], myEst: 0.45, cv: 0.35, dependsOn: null },
  { id: 3, market: "Chiefs win Super Bowl", b: 2000, q: [400, 1600], myEst: 0.18, cv: 0.20, dependsOn: 4 }, // Constraint logic attached below
  { id: 4, market: "Chiefs win AFC Champ.", b: 2000, q: [300, 1700], myEst: 0.22, cv: 0.20, dependsOn: null }, // For constraint testing
  { id: 5, market: "TSLA Q1 Deliv > 400k", b: 500, q: [100, 900], myEst: 0.04, cv: 0.40, dependsOn: null }, // Longshot Bias Test (p < 15%)
];

// ─── LMSR MATH HELPERS ───
// Cost Function: C(q) = b * ln(Σ e^(q_i / b))
function lmsrCost(q, b) {
  return b * Math.log(q.reduce((sum, qi) => sum + Math.exp(qi / b), 0));
}

// Price Function: p_i(q) = e^(q_i/b) / Σ e^(q_j/b) (Softmax)
function lmsrPrice(q, b, index) {
  const exps = q.map(qi => Math.exp(qi / b));
  const sumExps = exps.reduce((a, c) => a + c, 0);
  return exps[index] / sumExps;
}

// Cost of Trade: difference in cost function
function costOfTrade(qBefore, qAfter, b) {
  return lmsrCost(qAfter, b) - lmsrCost(qBefore, b);
}

// Expected Value Calculator
function expectedValue(totalCost, sharesBought, outcomeBought, myEst) {
  const prob = outcomeBought === 0 ? myEst : (1 - myEst);
  return (prob * sharesBought) - totalCost;
}

// Empirical Kelly Position Sizing
// f* = (p * b - q) / b   -> where b is decimal odds of the trade
// f_empirical = f* * (1 - CV)
function empiricalKelly(myEst, currentPrice, cv, isLongshot) {
  // If it's a longshot bias calibration trade (<15% market prob), artificially boost the win prob slightly for calculation
  const p = isLongshot ? Math.max(0.90, (1 - myEst)) : myEst; // If Shorting Yes, p is prob of NO
  const q = 1 - p;

  // Calculate synthetic decimal odds based on the LMSR price
  const execPrice = isLongshot ? (1 - currentPrice) : currentPrice; // Cost to buy NO if shorting
  if (execPrice <= 0 || execPrice >= 1) return 0;

  const b = (1 / execPrice) - 1; // Payout ratio
  const f_kelly = (p * b - q) / b;

  if (f_kelly <= 0) return 0;

  // Apply Empirical Constraint
  const f_emp = f_kelly * (1 - cv);
  return Math.max(0, Math.min(f_emp, 0.25)); // Cap size at 25% of dedicated PM portfolio
}

// ═══════════════════════════════════════════════════════════════
// SMC AGENT — 7th Core Agent
// ICT concepts: BOS, CHOCH, Order Blocks, FVG, Liquidity, Retrace
// ═══════════════════════════════════════════════════════════════

function smcAgent(stock, smc) {
  if (!smc) return { buy: 0.25, sell: 0.15, hold: 0.6 };
  let buy = 0.2, sell = 0.1, hold = 0.7;

  // ── STRUCTURE (BOS/CHOCH) ──
  // BOS = trend continuation. CHOCH = reversal signal.
  if (smc.lastBOS === 1) buy += 0.12;        // bullish BOS = trend continues up
  if (smc.lastBOS === -1) sell += 0.12;       // bearish BOS = trend continues down
  if (smc.lastCHOCH === 1) buy += 0.20;      // bullish CHOCH = reversal UP (Wyckoff spring equivalent)
  if (smc.lastCHOCH === -1) sell += 0.20;    // bearish CHOCH = reversal DOWN (Wyckoff distribution)

  // ── ORDER BLOCKS ──
  // Price in bullish OB zone = institutional buy zone
  const bullOBs = smc.obZones.filter(z => z.type === "bull" && !z.mitigated);
  const bearOBs = smc.obZones.filter(z => z.type === "bear" && !z.mitigated);
  const inBullOB = bullOBs.some(z => stock.price >= z.bot && stock.price <= z.top);
  const inBearOB = bearOBs.some(z => stock.price >= z.bot && stock.price <= z.top);
  const nearBullOB = bullOBs.some(z => stock.price >= z.bot * 0.99 && stock.price <= z.top * 1.01);
  if (inBullOB) buy += 0.18;                 // price IS in bullish OB = strong buy zone
  if (nearBullOB && !inBullOB) buy += 0.08;  // price approaching bullish OB
  if (inBearOB) sell += 0.18;                // price in bearish OB = distribution zone

  // ── FAIR VALUE GAPS ──
  // Unfilled FVGs act as price magnets
  const bullFVGs = smc.fvg.filter(f => f.type === "bull" && !f.filled);
  const bearFVGs = smc.fvg.filter(f => f.type === "bear" && !f.filled);
  // Price below an unfilled bull FVG = gap will pull price up
  if (bullFVGs.some(f => stock.price < f.bot)) buy += 0.08;
  // Price above an unfilled bear FVG = gap will pull price down
  if (bearFVGs.some(f => stock.price > f.top)) sell += 0.08;
  // Price INSIDE a FVG = filling it right now
  const inBullFVG = bullFVGs.some(f => stock.price >= f.bot && stock.price <= f.top);
  const inBearFVG = bearFVGs.some(f => stock.price >= f.bot && stock.price <= f.top);
  if (inBullFVG) buy += 0.10;  // filling bullish FVG = support
  if (inBearFVG) sell += 0.10; // filling bearish FVG = resistance

  // ── LIQUIDITY ──
  // Swept liquidity = selling climax (Williams #1) = reversal incoming
  const sweptBuyLiq = smc.liqLevels.some(l => l.side === "buy" && l.swept);
  const sweptSellLiq = smc.liqLevels.some(l => l.side === "sell" && l.swept);
  if (sweptBuyLiq) buy += 0.22;   // buy-side liq swept = stops hunted below = reversal UP
  if (sweptSellLiq) sell += 0.15; // sell-side liq swept = stops hunted above = reversal DOWN
  // Unswept liquidity = magnet (price will go there)
  const unsweptBuy = smc.liqLevels.filter(l => l.side === "buy" && !l.swept);
  const unsweptSell = smc.liqLevels.filter(l => l.side === "sell" && !l.swept);
  if (unsweptBuy.length > 0 && stock.price < smc.swingHigh * 0.95) {
    // price near sell-side but buy-side unswept = risk of sweep down first
    hold += 0.05;
  }

  // ── RETRACEMENTS ──
  // Discount zone (retrace > 50%) = better entry for longs
  if (smc.structure === "BULLISH") {
    if (smc.retracePct > 0.5) buy += 0.12;       // deep discount
    else if (smc.retracePct > 0.38) buy += 0.06;  // moderate discount
    else if (smc.retracePct < 0.2) hold += 0.08;  // premium zone, wait for pullback
  }
  if (smc.structure === "BEARISH") {
    if (smc.retracePct > 0.5) sell += 0.12;  // deep premium for shorts
    else if (smc.retracePct < 0.2) hold += 0.08;
  }
  if (smc.structure === "RANGING") hold += 0.15;

  const t = buy + sell + hold;
  return { buy: buy / t, sell: sell / t, hold: hold / t };
}

// ═══ EXISTING 6 AGENTS (condensed) ═══
function runAllAgents(s, macro, smc, weights) {
  const a = {};
  // Williams
  let b = .3, sl = .1, h = .6;
  if (s.rsi < 30) b += .25; else if (s.rsi > 70) sl += .2; else if (s.rsi < 45) b += .1;
  if (s.macdH > 0) b += .15; else sl += .1;
  if (s.ad > .5) b += .15; else if (s.ad < -.3) sl += .15;
  if (s.chg < -3) b += .1; if (s.chg > 4) sl += .1;
  if (s.stochK < 20 && s.stochD < 20) b += .1; if (s.stochK > 80 && s.stochD > 80) sl += .1;
  if (s.price < s.bbL) b += .1; if (s.price > s.bbU) sl += .1;
  if (macro.spYield < 2.8) sl += .05; if (macro.gold > 5000) sl += .05;
  let t = b + sl + h; a.W = { buy: b / t, sell: sl / t, hold: h / t };
  // Wyckoff — now enhanced with CHOCH
  b = .25; sl = .15; h = .6;
  if (s.price > s.sma50 && s.price > s.sma200 && s.ad > .3) b += .2;
  if (s.price > s.sma50 && s.ad < -.2) sl += .2;
  if (smc && smc.lastCHOCH === 1) b += .15; // CHOCH confirms Wyckoff spring
  if (smc && smc.lastCHOCH === -1) sl += .15; // CHOCH confirms distribution
  t = b + sl + h; a.Wy = { buy: b / t, sell: sl / t, hold: h / t };
  // Brooks — now enhanced with BOS
  b = .25; sl = .15; h = .6;
  if (s.price > s.bbM) b += .1; if (s.price > s.bbU) b += .05;
  if (s.stochK > s.stochD && s.macdH > 0) b += .15;
  if (s.stochK < s.stochD && s.macdH < 0) sl += .15;
  if (smc && smc.lastBOS === 1) b += .10; // BOS confirms Brooks trend bar
  if (smc && smc.lastBOS === -1) sl += .10;
  t = b + sl + h; a.B = { buy: b / t, sell: sl / t, hold: h / t };
  // Berlekamp — now counts SMC signals in redundancy
  let sigs = 0;
  if (s.rsi < 45) sigs++; if (s.macdH > 0) sigs++; if (s.ad > .3) sigs++;
  if (s.price > s.sma50) sigs++; if (s.price > s.sma200) sigs++;
  if (s.stochK > s.stochD) sigs++; if (s.price > s.bbM) sigs++;
  if (s.sent > .1) sigs++;
  if (smc && smc.lastBOS === 1) sigs++; // NEW: BOS as signal
  if (smc && smc.obZones.some(z => z.type === "bull" && !z.mitigated && s.price >= z.bot && s.price <= z.top)) sigs++; // NEW: in OB
  const total = 10;
  const conf = sigs < 3 ? .3 : sigs < 5 ? .6 : sigs < 7 ? .8 : sigs < 9 ? .9 : .95;
  const gate = s.rsi < 50 && s.macdH > 0;
  const ac = gate ? conf : Math.min(conf, .4);
  const bB = ac * (sigs / total), bS = (1 - ac) * ((total - sigs) / total), bH = Math.max(0, 1 - bB - bS);
  a.Be = { buy: bB, sell: Math.max(0, bS), hold: bH };
  // Thorp — R:R now uses OB and FVG for precision
  b = .3; sl = .1; h = .6;
  let stop = s.sma50 * .95, target = s.bbU;
  if (smc) {
    const bullOB = smc.obZones.find(z => z.type === "bull" && !z.mitigated && z.bot < s.price);
    if (bullOB) stop = bullOB.bot; // stop below OB = structural invalidation
    const bearFVG = smc.fvg.find(f => f.type === "bear" && !f.filled && f.bot > s.price);
    if (bearFVG) target = bearFVG.bot; // target = unfilled FVG above
    const sellLiq = smc.liqLevels.find(l => l.side === "sell" && !l.swept);
    if (sellLiq && sellLiq.level > s.price) target = Math.max(target, sellLiq.level); // liq as target
  }
  const risk = s.price - stop, rew = target - s.price;
  const rr = risk > 0 ? rew / risk : 0;
  if (rr >= 3) b += .25; else if (rr >= 2) b += .15; else if (rr < 1.5) sl += .15;
  if (s.beta > 2) { b -= .05; sl += .05; }
  if (s.rsi < 35 && s.stochK < 25) b += .15;
  t = b + sl + h; a.T = { buy: b / t, sell: sl / t, hold: h / t };
  // Macro
  b = .3; sl = .1; h = .6;
  if (macro.gold > 5000) { sl += .15; b -= .1; }
  if (macro.t3m > macro.t10y) { sl += .15; b -= .1; }
  if (macro.vix > 30) sl += .1; else if (macro.vix < 15) b += .1;
  if (macro.spYield < 2.8) sl += .1;
  if (s.sent > .3) b += .1; else if (s.sent < -.2) sl += .1;
  t = b + sl + h; a.M = { buy: b / t, sell: sl / t, hold: h / t };
  // SMC Agent
  a.S = smcAgent(s, smc);
  // Burry (MB) - Deep Value / Contrarian
  b = .1; sl = .2; h = .7;
  if (s.fcfYield >= 0.12) b += 0.4; else if (s.fcfYield >= 0.08) b += 0.2; else sl += 0.2; // High FCF = Buy
  if (s.debtEq < 0.5) b += 0.2; else if (s.debtEq > 1.0) sl += 0.3; // Low Debt = Buy
  if (s.pe < 15) b += 0.2; else if (s.pe > 40) sl += 0.3; // Low P/E = Buy
  if (s.insider === "buy") b += 0.2; else if (s.insider === "sell") sl += 0.2; // Insider buying
  if (s.rsi < 35 && s.sent < 0) b += 0.2; // Contrarian component (hated + low rsi = opportunity if value exists)
  t = b + sl + h; a.MB = { buy: b / t, sell: sl / t, hold: h / t };

  // RPBERT Proxy (RPB) - Cross-firm sequence modeling
  b = 0.1; sl = 0.1; h = 0.8;
  if (s.rpbDecile !== undefined) {
    if (s.rpbDecile <= 0.2) { b += 0.4; h -= 0.3; sl -= 0.1; } // Top of sequence
    else if (s.rpbDecile >= 0.8) { sl += 0.4; h -= 0.3; b -= 0.1; } // Bottom of sequence
    if (s.beta > 1.5 && s.rpbDecile <= 0.3) b += 0.15; // High beta leader
    if (s.beta > 1.5 && s.rpbDecile >= 0.7) sl += 0.15; // High beta laggard
  }
  b = Math.max(0, b); sl = Math.max(0, sl); h = Math.max(0, h);
  t = b + sl + h; a.RPB = { buy: b / t, sell: sl / t, hold: h / t };

  // Multi-LLM Consensus Agent (LLM)
  b = 0.3; sl = 0.3; h = 0.4;
  if (s.rpbDecile <= 0.3 && s.sent > 0.15) b += 0.3;
  if (s.rpbDecile >= 0.7 && s.sent < -0.15) sl += 0.3;
  if (s.sharpe > 1.2) b += 0.1; else if (s.sharpe < 0) sl += 0.1;
  b = Math.max(0, b); sl = Math.max(0, sl); h = Math.max(0, h);
  t = b + sl + h; a.LLM = { buy: b / t, sell: sl / t, hold: h / t };

  // Whale Tracking Agent (WHL) - Proxy via Institutional Flow (Volume anomaly)
  b = 0.1; sl = 0.1; h = 0.8;
  const volAnomaly = s.v / 1000000; // Mock tick volume metric
  if (volAnomaly > 5) {
    if (s.chg > 0 && s.price > s.sma50) b += 0.5;
    if (s.chg < 0 && s.price < s.sma50) sl += 0.5;
  }
  b = Math.max(0, b); sl = Math.max(0, sl); h = Math.max(0, h);
  t = b + sl + h; a.WHL = { buy: b / t, sell: sl / t, hold: h / t };

  // Real-Time Sentiment Agent (SEN)
  b = 0.2; sl = 0.2; h = 0.6;
  if (s.sent > 0.2) b += 0.4;
  else if (s.sent < -0.2) sl += 0.4;
  b = Math.max(0, b); sl = Math.max(0, sl); h = Math.max(0, h);
  t = b + sl + h; a.SEN = { buy: b / t, sell: sl / t, hold: h / t };

  // Consensus
  let cB = 0, cS = 0, cH = 0, wT = 0;
  Object.entries(a).forEach(([k, v]) => { const w = weights[k] || 1; cB += v.buy * w; cS += v.sell * w; cH += v.hold * w; wT += w; });
  cB /= wT; cS /= wT; cH /= wT;

  // Risk Manager logic (Dynamic position sizing & limits based on Volatility & Variance Drag)
  // Higher VIX + Higher Beta = Drastically reduced position size
  // High Max Drawdowns drastically reduce limits further to avoid pure variance drag
  // High Sharpe Ratios get boosted
  let riskLimit = 0.20; // Base limit: 20% allocation limit.
  let riskMult = 1.0;
  if (macro.vix > 30) riskMult *= 0.75;
  else if (macro.vix < 15) riskMult *= 1.25;

  if (s.beta > 1.8) riskMult *= 0.6; // High volatile stocks penalized
  else if (s.beta < 0.8) riskMult *= 1.2;

  // Data Science Metrics constraints
  if (s.maxDD <= -0.40) riskMult *= 0.50; // Severe penalty for extreme historical variance drag (-40% Drawdowns)
  else if (s.maxDD <= -0.25) riskMult *= 0.80;

  if (s.sharpe > 1.5) riskMult *= 1.30;   // Boost limits on supreme risk-adjusted vehicles
  else if (s.sharpe > 1.0) riskMult *= 1.15;
  else if (s.sharpe < 0.5) riskMult *= 0.80;

  riskLimit = Math.min(Math.max((riskLimit * riskMult), 0.05), 0.25); // Cap between 5% and 25%

  // Dampen extreme buy/sell confidence on risky setups
  let confidence = Math.max(cB, cS, cH) * 100;
  if (riskMult < 0.8 && confidence > 60) {
    confidence -= 10;
  }
  const signal = cB > cS && cB > cH ? "BUY" : cS > cB && cS > cH ? "SELL" : "HOLD";

  // SMC-enhanced entry/exit
  let entryZone = null, stopLevel = null, targetLevel = null;
  if (smc) {
    const bullOB = smc.obZones.find(z => z.type === "bull" && !z.mitigated);
    if (bullOB) entryZone = `$${bullOB.bot}-${bullOB.top}`;
    if (bullOB) stopLevel = bullOB.bot;
    const bearFVG = smc.fvg.find(f => f.type === "bear" && !f.filled && f.bot > s.price);
    const sellLiq = smc.liqLevels.find(l => l.side === "sell" && !l.swept);
    targetLevel = bearFVG ? bearFVG.bot : sellLiq ? sellLiq.level : s.bbU;
  }
  return { agents: a, consensus: { buy: cB, sell: cS, hold: cH }, signal, confidence, risk: { mult: riskMult, limit: riskLimit }, entryZone, stopLevel, targetLevel };
}

// ═══ CONCEPT BRIDGE TABLE ═══
const BRIDGE = [
  { ict: "Break of Structure (BOS)", williams: "Trend confirmation via A/D momentum", wyckoff: "Markup/Markdown phase continuation", brooks: "Trend bar structural follow-through", agent: "Brooks +0.10" },
  { ict: "Change of Character (CHOCH)", williams: "Selling climax reversal signal", wyckoff: "Spring / Sign of Strength / Sign of Weakness", brooks: "Failed breakout → reversal bar", agent: "Wyckoff +0.15" },
  { ict: "Order Blocks", williams: "Accumulation / Distribution zones (A/D formula)", wyckoff: "Accumulation range / Distribution range", brooks: "High-volume reversal bar zones", agent: "SMC +0.18 (in OB)" },
  { ict: "Fair Value Gaps", williams: "Momentum gap unfilled by retracement", wyckoff: "Jump across the creek / Back up to the edge", brooks: "Breakaway gap → measuring gap → exhaustion gap", agent: "SMC +0.10 (FVG magnet)" },
  { ict: "Liquidity Sweeps", williams: "SELLING CLIMAX (#1 Commandment)", wyckoff: "Terminal shakeout / Spring", brooks: "Stop hunt → failed breakout → reversal", agent: "SMC +0.22 (swept)" },
  { ict: "Retracements", williams: "Optimal entry on hard down days", wyckoff: "Test of the creek / Pullback to the breakout", brooks: "Measured move pullback", agent: "SMC +0.12 (discount)" },
];

// ═══ MAIN COMPONENT ═══
export default function GitAgentV57() {
  const [tab, setTab] = useState("scanner");
  const [selected, setSelected] = useState(0);
  const [weights, setWeights] = useState({ W: 1.2, Wy: 1.0, B: 0.9, Be: 1.1, T: 1.0, M: 1.0, S: 1.15, MB: 1.25, RPB: 1.4, LLM: 1.5, WHL: 1.3, SEN: 1.0 });

  const results = useMemo(() => {
    // 1. RPBERT Sequence Mapping
    const sequenced = [...WATCHLIST].map(s => {
      const score = (s.rsi / 100) * 0.4 + (s.macdH > 0 ? 0.2 : 0) + (s.ad) * 0.2 + (s.annRet) * 0.2;
      return { sym: s.sym, rpbScore: score };
    }).sort((a, b) => b.rpbScore - a.rpbScore);

    const rankedList = WATCHLIST.map(s => {
      const rank = sequenced.findIndex(x => x.sym === s.sym);
      const decile = rank / Math.max(1, WATCHLIST.length - 1);
      return { ...s, rpbRank: rank, rpbDecile: decile };
    });

    return rankedList.map(s => {
      const smc = SMC_DATA[s.sym];
      const swarm = runAllAgents(s, MACRO, smc, weights);
      return { ...s, smc, ...swarm };
    }).sort((a, b) => {
      if (a.signal === "BUY" && b.signal !== "BUY") return -1;
      if (b.signal === "BUY" && a.signal !== "BUY") return 1;
      return b.confidence - a.confidence;
    });
  }, [weights]);

  const sel = results[selected];

  // UI Helpers
  const P = ({ label, active, onClick, color = "#F59E0B" }) => (
    <button onClick={onClick} style={{ padding: "4px 10px", borderRadius: 4, border: active ? `1px solid ${color}` : "1px solid #222", background: active ? `${color}12` : "#0f0f0f", color: active ? color : "#555", fontSize: 9, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>{label}</button>
  );
  const Badge = ({ text, color }) => <span style={{ padding: "2px 6px", borderRadius: 3, background: `${color}15`, color, fontSize: 9, fontWeight: 700, border: `1px solid ${color}30`, fontFamily: "inherit" }}>{text}</span>;
  const Bar = ({ v, max = 1, color, w = 100, h = 4 }) => <div style={{ width: w, height: h, background: "#1a1a1a", borderRadius: 2, overflow: "hidden", display: "inline-block", verticalAlign: "middle" }}><div style={{ width: `${Math.min(Math.abs(v) / max, 1) * 100}%`, height: "100%", background: color, borderRadius: 2 }} /></div>;

  return (
    <div style={{ background: "#09090b", color: "#e0e0e0", minHeight: "100vh", fontFamily: "'JetBrains Mono','SF Mono',monospace", fontSize: 11, padding: 14 }}>

      {/* HEADER */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, borderBottom: "1px solid #1a1a1a", paddingBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 900, color: "#F59E0B", letterSpacing: 1.5 }}>GITAGENT</span>
          <span style={{ fontSize: 9, color: "#10B981", background: "#10B98112", padding: "2px 6px", borderRadius: 3, border: "1px solid #10B98130" }}>v5.8 MOONDEV</span>
          <span style={{ fontSize: 8, color: "#333" }}>12-AGENT + INST. AI SWARM + WHALE + LLM CONSENSUS + SENTIMENT</span>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 9 }}>
          {Object.entries(AGENTS).map(([k, ag]) => (
            <span key={k} style={{ width: 16, height: 16, borderRadius: 3, background: `${ag.color}20`, color: ag.color, fontSize: 7, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, border: `1px solid ${ag.color}40` }}>{ag.icon}</span>
          ))}
        </div>
      </div>

      {/* TABS */}
      <div style={{ display: "flex", gap: 3, marginBottom: 10, flexWrap: "wrap" }}>
        {["scanner", "smc-detail", "bridge", "structure", "agents", "institutional-pm", "risk", "quant"].map(t => (
          <P key={t} label={t.toUpperCase()} active={tab === t} onClick={() => setTab(t)} color={t === "smc-detail" || t === "structure" ? "#3B82F6" : t === "institutional-pm" ? "#10B981" : t === "risk" ? "#EF4444" : t === "quant" ? "#A855F7" : "#F59E0B"} />
        ))}
      </div>

      {/* ═══ SCANNER ═══ */}
      {tab === "scanner" && (
        <div style={{ border: "1px solid #1a1a1a", borderRadius: 5, overflow: "hidden" }}>
          <div style={{ padding: "6px 10px", background: "#111", fontSize: 8, color: "#9333EA", fontWeight: 600 }}>
            12-AGENT SWARM: W+Wy+B+Be+T+M+SMC+MB+<span style={{ color: "#F43F5E", textDecoration: "underline" }}>RPB</span>+LLM+WHL+SEN | MULTI-LLM + INSTO TRACKING
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead><tr style={{ background: "#111", color: "#555", fontSize: 8 }}>
              {["#", "SYM", "PRICE", "Δ%", "STRUCT", "BOS", "CHOCH", "OB", "LIQ", "SENTMENT", "RPB SEQ", "SIG", "CONF", "MAX POS"].map(h => (
                <th key={h} style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {results.map((r, i) => {
                const smc = r.smc || {};
                return (
                  <tr key={i} onClick={() => { setSelected(i); setTab("smc-detail") }} style={{ cursor: "pointer", background: selected === i ? "#141414" : "transparent", borderBottom: "1px solid #0f0f0f" }}
                    onMouseEnter={e => e.currentTarget.style.background = "#131313"} onMouseLeave={e => e.currentTarget.style.background = selected === i ? "#141414" : "transparent"}>
                    <td style={{ padding: "4px 5px", color: "#333" }}>{i + 1}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: "#F59E0B" }}>{r.sym}</td>
                    <td style={{ padding: "4px 5px" }}>${r.price}</td>
                    <td style={{ padding: "4px 5px", color: r.chg > 0 ? "#10B981" : "#EF4444", fontWeight: 600 }}>{r.chg > 0 ? "+" : ""}{r.chg}%</td>
                    <td style={{ padding: "4px 5px" }}><Badge text={smc.structure || "—"} color={smc.structure === "BULLISH" ? "#10B981" : smc.structure === "BEARISH" ? "#EF4444" : "#F59E0B"} /></td>
                    <td style={{ padding: "4px 5px", color: smc.lastBOS === 1 ? "#10B981" : smc.lastBOS === -1 ? "#EF4444" : "#555" }}>{smc.lastBOS === 1 ? "▲" : smc.lastBOS === -1 ? "▼" : "—"}</td>
                    <td style={{ padding: "4px 5px", color: smc.lastCHOCH === 1 ? "#10B981" : smc.lastCHOCH === -1 ? "#EF4444" : "#555" }}>{smc.lastCHOCH === 1 ? "⟳▲" : smc.lastCHOCH === -1 ? "⟳▼" : "—"}</td>
                    <td style={{ padding: "4px 5px", fontSize: 8 }}>{smc.obZones?.filter(z => !z.mitigated).length || 0} <span style={{ color: "#555" }}>active</span></td>
                    <td style={{ padding: "4px 5px" }}>{smc.liqLevels?.some(l => l.swept) ? <Badge text="SWEPT" color="#F59E0B" /> : <span style={{ color: "#555", fontSize: 8 }}>{smc.liqLevels?.length || 0} lvl</span>}</td>
                    <td style={{ padding: "4px 5px", color: (r.sent || 0) > 0.1 ? "#10B981" : (r.sent || 0) < -0.1 ? "#EF4444" : "#888", fontWeight: 700 }}>{((r.sent || 0) * 100).toFixed(0)}%</td>
                    <td style={{ padding: "4px 5px", color: "#F43F5E", fontWeight: 800 }}>#{r.rpbRank + 1}</td>
                    <td style={{ padding: "4px 5px" }}><Badge text={r.signal} color={r.signal === "BUY" ? "#10B981" : r.signal === "SELL" ? "#EF4444" : "#F59E0B"} /></td>
                    <td style={{ padding: "4px 5px", color: "#F59E0B", fontWeight: 700 }}>{r.confidence.toFixed(0)}%</td>
                    <td style={{ padding: "4px 5px", fontSize: 8, color: (r.risk?.limit || 0.2) > 0.15 ? "#10B981" : "#EF4444" }}>{((r.risk?.limit || 0.2) * 100).toFixed(0)}% ALLOC</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ═══ SMC DETAIL ═══ */}
      {tab === "smc-detail" && sel && sel.smc && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {/* Left: SMC Structure */}
          <div style={{ background: "#111", borderRadius: 5, padding: 10, border: "1px solid #3B82F620" }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#3B82F6", marginBottom: 6 }}>{sel.sym} SMC ANALYSIS</div>

            <div style={{ fontSize: 8, color: "#555", marginBottom: 4 }}>MARKET STRUCTURE</div>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <Badge text={sel.smc.structure} color={sel.smc.structure === "BULLISH" ? "#10B981" : sel.smc.structure === "BEARISH" ? "#EF4444" : "#F59E0B"} />
              <span style={{ fontSize: 9, color: "#666" }}>Last break: {sel.smc.lastStructBreak}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 8 }}>
              <div style={{ padding: 6, background: "#0a0a0a", borderRadius: 3, textAlign: "center" }}>
                <div style={{ fontSize: 7, color: "#555" }}>BOS</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: sel.smc.lastBOS === 1 ? "#10B981" : sel.smc.lastBOS === -1 ? "#EF4444" : "#555" }}>{sel.smc.lastBOS === 1 ? "BULL" : sel.smc.lastBOS === -1 ? "BEAR" : "NONE"}</div>
                <div style={{ fontSize: 7, color: "#444" }}>trend continuation</div>
              </div>
              <div style={{ padding: 6, background: "#0a0a0a", borderRadius: 3, textAlign: "center" }}>
                <div style={{ fontSize: 7, color: "#555" }}>CHOCH</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: sel.smc.lastCHOCH === 1 ? "#10B981" : sel.smc.lastCHOCH === -1 ? "#EF4444" : "#555" }}>{sel.smc.lastCHOCH === 1 ? "BULL REV" : sel.smc.lastCHOCH === -1 ? "BEAR REV" : "NONE"}</div>
                <div style={{ fontSize: 7, color: "#444" }}>trend reversal</div>
              </div>
            </div>

            {/* Order Blocks */}
            <div style={{ fontSize: 8, color: "#555", marginBottom: 3 }}>ORDER BLOCKS (institutional zones)</div>
            {sel.smc.obZones.map((ob, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: 4, marginBottom: 2, background: "#0a0a0a", borderRadius: 3, border: `1px solid ${ob.type === "bull" ? "#10B98120" : "#EF444420"}` }}>
                <Badge text={ob.type === "bull" ? "BULL OB" : "BEAR OB"} color={ob.type === "bull" ? "#10B981" : "#EF4444"} />
                <span style={{ fontSize: 9, color: "#888" }}>${ob.bot} — ${ob.top}</span>
                {ob.mitigated ? <span style={{ fontSize: 8, color: "#555" }}>mitigated</span> :
                  sel.price >= ob.bot && sel.price <= ob.top ? <Badge text="PRICE IN ZONE" color="#F59E0B" /> :
                    <span style={{ fontSize: 8, color: "#3B82F6" }}>{sel.price < ob.bot ? "below" : "above"}</span>
                }
              </div>
            ))}

            {/* FVGs */}
            <div style={{ fontSize: 8, color: "#555", marginTop: 6, marginBottom: 3 }}>FAIR VALUE GAPS (price magnets)</div>
            {sel.smc.fvg.length === 0 ? <div style={{ fontSize: 9, color: "#333", padding: 4 }}>No active FVGs</div> :
              sel.smc.fvg.map((f, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: 4, marginBottom: 2, background: "#0a0a0a", borderRadius: 3 }}>
                  <Badge text={f.type === "bull" ? "BULL FVG" : "BEAR FVG"} color={f.type === "bull" ? "#10B981" : "#EF4444"} />
                  <span style={{ fontSize: 9, color: "#888" }}>${f.bot} — ${f.top}</span>
                  {f.filled ? <span style={{ fontSize: 8, color: "#555" }}>filled</span> : <Badge text="UNFILLED" color="#3B82F6" />}
                </div>
              ))
            }

            {/* Liquidity */}
            <div style={{ fontSize: 8, color: "#555", marginTop: 6, marginBottom: 3 }}>LIQUIDITY LEVELS (stop clusters)</div>
            {sel.smc.liqLevels.map((liq, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: 4, marginBottom: 2, background: "#0a0a0a", borderRadius: 3, border: liq.swept ? `1px solid #F59E0B30` : "1px solid #1a1a1a" }}>
                <Badge text={liq.side === "buy" ? "BUY-SIDE" : "SELL-SIDE"} color={liq.side === "buy" ? "#10B981" : "#EF4444"} />
                <span style={{ fontSize: 9, color: "#888" }}>${liq.level}</span>
                {liq.swept ? <Badge text="SWEPT ⚡" color="#F59E0B" /> : <span style={{ fontSize: 8, color: "#555" }}>unswept</span>}
              </div>
            ))}

            {/* Retracements */}
            <div style={{ fontSize: 8, color: "#555", marginTop: 6, marginBottom: 3 }}>RETRACEMENT</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 4, background: "#0a0a0a", borderRadius: 3 }}>
              <span style={{ fontSize: 9, color: "#888" }}>Current</span>
              <Bar v={sel.smc.retracePct} max={1} color={sel.smc.retracePct > .5 ? "#10B981" : sel.smc.retracePct > .38 ? "#F59E0B" : "#EF4444"} w={80} />
              <span style={{ fontSize: 10, fontWeight: 700, color: sel.smc.retracePct > .5 ? "#10B981" : "#888" }}>{(sel.smc.retracePct * 100).toFixed(0)}%</span>
              <span style={{ fontSize: 8, color: sel.smc.retracePct > .5 ? "#10B981" : "#888" }}>{sel.smc.retracePct > .5 ? "DISCOUNT" : "PREMIUM"}</span>
            </div>
          </div>

          {/* Right: 9-Agent Votes */}
          <div style={{ background: "#111", borderRadius: 5, padding: 10, border: "1px solid #1a1a1a" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#888", marginBottom: 6 }}>9-AGENT SWARM VOTE (Incl. Burry & RPB)</div>
            {Object.entries(sel.agents).map(([k, v]) => (
              <div key={k} style={{ marginBottom: 5, padding: 5, background: "#0a0a0a", borderRadius: 3, border: `1px solid ${AGENTS[k].color}12` }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ color: AGENTS[k].color, fontWeight: 700, fontSize: 9 }}>{AGENTS[k].name} {k === "S" ? "(NEW)" : ""}</span>
                  <span style={{ fontSize: 8, color: "#444" }}>w={weights[k].toFixed(2)}</span>
                </div>
                <div style={{ display: "flex", height: 3, borderRadius: 2, overflow: "hidden", background: "#1a1a1a" }}>
                  <div style={{ width: `${v.buy * 100}%`, background: "#10B981" }} />
                  <div style={{ width: `${v.hold * 100}%`, background: "#F59E0B" }} />
                  <div style={{ width: `${v.sell * 100}%`, background: "#EF4444" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 7, marginTop: 1 }}>
                  <span style={{ color: "#10B981" }}>{(v.buy * 100).toFixed(0)}B</span>
                  <span style={{ color: "#F59E0B" }}>{(v.hold * 100).toFixed(0)}H</span>
                  <span style={{ color: "#EF4444" }}>{(v.sell * 100).toFixed(0)}S</span>
                </div>
              </div>
            ))}

            {/* Consensus + SMC Entry/Exit */}
            <div style={{ padding: 8, background: "#0a0a0a", borderRadius: 4, border: "1px solid #F59E0B20", marginTop: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Badge text={sel.signal} color={sel.signal === "BUY" ? "#10B981" : sel.signal === "SELL" ? "#EF4444" : "#F59E0B"} />
                <span style={{ fontSize: 18, fontWeight: 900, color: "#F59E0B" }}>{sel.confidence.toFixed(0)}%</span>
              </div>
            </div>

            {/* SMC-Enhanced Trade Plan */}
            <div style={{ padding: 8, background: "#0a0a0a", borderRadius: 4, border: "1px solid #3B82F620", marginTop: 6 }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "#3B82F6", marginBottom: 4 }}>SMC-ENHANCED TRADE PLAN</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4 }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 7, color: "#555" }}>ENTRY (OB Zone)</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#3B82F6" }}>{sel.entryZone || "Market"}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 7, color: "#555" }}>STOP (Below OB)</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#EF4444" }}>{sel.stopLevel ? `$${sel.stopLevel}` : "—"}</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 7, color: "#555" }}>TARGET (FVG/LIQ)</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#10B981" }}>{sel.targetLevel ? `$${sel.targetLevel.toFixed(0)}` : "—"}</div>
                </div>
              </div>
              {sel.stopLevel && sel.targetLevel && (
                <div style={{ textAlign: "center", marginTop: 4 }}>
                  <span style={{ fontSize: 8, color: "#555" }}>R:R = </span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: (sel.targetLevel - sel.price) / (sel.price - (sel.stopLevel || sel.price)) > 2 ? "#10B981" : "#F59E0B" }}>
                    {((sel.targetLevel - sel.price) / Math.max(0.01, sel.price - (sel.stopLevel || sel.price))).toFixed(1)}:1
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ═══ BRIDGE TAB ═══ */}
      {tab === "bridge" && (
        <div style={{ background: "#111", borderRadius: 5, padding: 10, border: "1px solid #3B82F620" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#3B82F6", marginBottom: 4 }}>ICT ↔ WILLIAMS ↔ WYCKOFF ↔ BROOKS CONCEPTUAL BRIDGE</div>
          <div style={{ fontSize: 8, color: "#666", marginBottom: 10 }}>Same institutional behaviors, different nomenclature. The SMC Agent unifies all frameworks algorithmically.</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 9 }}>
            <thead><tr style={{ background: "#0a0a0a", color: "#555", fontSize: 8 }}>
              {["ICT / SMC", "Williams", "Wyckoff", "Brooks", "Agent Impact"].map(h => (
                <th key={h} style={{ padding: "5px 6px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {BRIDGE.map((row, i) => (
                <tr key={i} style={{ borderBottom: "1px solid #0f0f0f" }}>
                  <td style={{ padding: "5px 6px", color: "#3B82F6", fontWeight: 600 }}>{row.ict}</td>
                  <td style={{ padding: "5px 6px", color: "#F59E0B" }}>{row.williams}</td>
                  <td style={{ padding: "5px 6px", color: "#06B6D4" }}>{row.wyckoff}</td>
                  <td style={{ padding: "5px 6px", color: "#EC4899" }}>{row.brooks}</td>
                  <td style={{ padding: "5px 6px", color: "#10B981", fontWeight: 600 }}>{row.agent}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 8, padding: 6, background: "#0a0a0a", borderRadius: 3, fontSize: 8, color: "#555", border: "1px solid #3B82F615" }}>
            <strong style={{ color: "#3B82F6" }}>Key Insight:</strong> Williams' Selling Climax (#1 Commandment) = ICT's Liquidity Sweep. Wyckoff's Spring = ICT's liquidity grab below support + CHOCH. Brooks' failed breakout = ICT's liquidity grab + BOS failure. The SMC Agent detects ALL of these as the same underlying institutional behavior — stop hunts followed by reversal — using algorithmic structure analysis.
          </div>
        </div>
      )}

      {/* ═══ STRUCTURE MAP ═══ */}
      {tab === "structure" && sel && sel.smc && (
        <div style={{ background: "#111", borderRadius: 5, padding: 10, border: "1px solid #3B82F620" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#3B82F6", marginBottom: 8 }}>{sel.sym} — STRUCTURAL MAP</div>

          {/* Visual price ladder */}
          <div style={{ position: "relative", height: 300, background: "#0a0a0a", borderRadius: 5, overflow: "hidden", border: "1px solid #1a1a1a", padding: "10px 60px 10px 80px" }}>
            {(() => {
              const all = [sel.smc.swingHigh, sel.smc.swingLow, sel.price,
              ...sel.smc.obZones.flatMap(z => [z.top, z.bot]),
              ...sel.smc.fvg.flatMap(f => [f.top, f.bot]),
              ...sel.smc.liqLevels.map(l => l.level)];
              const mn = Math.min(...all) * 0.995;
              const mx = Math.max(...all) * 1.005;
              const yPos = (val) => (1 - (val - mn) / (mx - mn)) * 280 + 10;

              return <>
                {/* Swing range */}
                <div style={{ position: "absolute", left: 10, top: yPos(sel.smc.swingHigh), fontSize: 7, color: "#555" }}>SwH ${sel.smc.swingHigh}</div>
                <div style={{ position: "absolute", left: 10, top: yPos(sel.smc.swingLow), fontSize: 7, color: "#555" }}>SwL ${sel.smc.swingLow}</div>

                {/* OB Zones */}
                {sel.smc.obZones.map((ob, i) => (
                  <div key={`ob${i}`} style={{
                    position: "absolute", left: 80, right: 60, top: yPos(ob.top), height: Math.max(4, yPos(ob.bot) - yPos(ob.top)),
                    background: ob.type === "bull" ? "#10B98115" : "#EF444415", borderLeft: `2px solid ${ob.type === "bull" ? "#10B981" : "#EF4444"}`, opacity: ob.mitigated ? 0.3 : 1
                  }}>
                    <span style={{ position: "absolute", right: 2, top: 0, fontSize: 7, color: ob.type === "bull" ? "#10B981" : "#EF4444" }}>{ob.type === "bull" ? "Bull" : "Bear"} OB</span>
                  </div>
                ))}

                {/* FVG Zones */}
                {sel.smc.fvg.map((f, i) => (
                  <div key={`fvg${i}`} style={{
                    position: "absolute", left: 80, right: 60, top: yPos(f.top), height: Math.max(3, yPos(f.bot) - yPos(f.top)),
                    background: f.type === "bull" ? "#3B82F610" : "#F59E0B10", borderLeft: `2px dashed ${f.type === "bull" ? "#3B82F6" : "#F59E0B"}`, opacity: f.filled ? 0.2 : 1
                  }}>
                    <span style={{ position: "absolute", right: 2, top: 0, fontSize: 7, color: f.type === "bull" ? "#3B82F6" : "#F59E0B" }}>FVG{f.filled ? " ✓" : ""}</span>
                  </div>
                ))}

                {/* Liquidity levels */}
                {sel.smc.liqLevels.map((liq, i) => (
                  <div key={`liq${i}`} style={{
                    position: "absolute", left: 80, right: 60, top: yPos(liq.level), height: 1,
                    background: liq.swept ? "#F59E0B" : "#555", borderTop: liq.swept ? "1px solid #F59E0B" : "1px dashed #333"
                  }}>
                    <span style={{ position: "absolute", left: 2, top: -10, fontSize: 7, color: liq.swept ? "#F59E0B" : "#555" }}>{liq.side} liq ${liq.level}{liq.swept ? " ⚡" : ""}</span>
                  </div>
                ))}

                {/* Current price line */}
                <div style={{ position: "absolute", left: 60, right: 40, top: yPos(sel.price), height: 2, background: "#F59E0B", zIndex: 10 }}>
                  <span style={{ position: "absolute", right: -38, top: -6, fontSize: 9, fontWeight: 800, color: "#F59E0B", background: "#0a0a0a", padding: "1px 4px", borderRadius: 2 }}>${sel.price}</span>
                </div>
              </>;
            })()}
          </div>

          <div style={{ display: "flex", gap: 8, marginTop: 8, justifyContent: "center", flexWrap: "wrap" }}>
            {[{ label: "Order Block", color: "#10B981", style: "solid" }, { label: "FVG", color: "#3B82F6", style: "dashed" }, { label: "Liquidity", color: "#F59E0B", style: "dotted" }, { label: "Price", color: "#F59E0B", style: "solid" }].map((leg, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div style={{ width: 16, height: 2, background: leg.color, borderTop: leg.style === "dashed" ? `1px dashed ${leg.color}` : leg.style === "dotted" ? `1px dotted ${leg.color}` : "none" }} />
                <span style={{ fontSize: 8, color: "#555" }}>{leg.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══ AGENTS TAB ═══ */}
      {tab === "agents" && (
        <div style={{ background: "#111", borderRadius: 5, padding: 10, border: "1px solid #1a1a1a" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#888", marginBottom: 8 }}>9 CORE AGENTS — WEIGHT CALIBRATION</div>
          {Object.entries(AGENTS).map(([k, ag]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ color: ag.color, fontWeight: 700, fontSize: 10, minWidth: 80 }}>{ag.name}{k === "RPB" ? " (NEW)" : ""}</span>
              <input type="range" min={0} max={20} value={weights[k] * 10} onChange={e => setWeights(p => ({ ...p, [k]: parseInt(e.target.value) / 10 }))} style={{ flex: 1, accentColor: ag.color }} />
              <span style={{ color: ag.color, fontWeight: 700, fontSize: 11, minWidth: 30 }}>{weights[k].toFixed(1)}</span>
            </div>
          ))}
          <div style={{ marginTop: 8, padding: 6, background: "#0a0a0a", borderRadius: 3, fontSize: 8, color: "#555", border: "1px solid #F43F5E15", display: "flex", flexDirection: "column", gap: 4 }}>
            <div><strong style={{ color: "#9333EA" }}>Burry (v5.3):</strong> Contrarian deep value framework. High FCF, low Debt, low P/E.</div>
            <div><strong style={{ color: "#F43F5E" }}>RPBERT Proxy (v5.7):</strong> Evaluates assets across the whole sequence. Top decile gets strong conviction, bottom decile gets heavily shorted.</div>
          </div>
        </div>
      )}

      {/* ═══ INSTITUTIONAL PREDICTION MARKETS ENGINE ═══ */}
      {tab === "institutional-pm" && (
        <div style={{ border: "1px solid #1a1a1a", borderRadius: 5, overflow: "hidden" }}>
          <div style={{ padding: "6px 10px", background: "#0A110F", fontSize: 8, color: "#10B981", fontWeight: 600 }}>
            INSTITUTIONAL PM ENGINE | Active Modules: 1. Conditional Logic Graph | 2. Calibration Longshot Bias | 3. Empirical Kelly Sizing
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead><tr style={{ background: "#0a0a0a", color: "#555", fontSize: 8 }}>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>#</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>MARKET</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>LMSR P(YES)</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>FAIR VALUE (P Engine)</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>RAW EDGE</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>STRATEGY TRIGGER</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>TRADE DIR</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>KELLY (f*) SIZING</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>EXPECTED VAL (10sh)</th>
            </tr></thead>
            <tbody>
              {ARB_PAIRS.map((pair, i) => {
                const currentPriceYes = lmsrPrice(pair.q, pair.b, 0);

                // Strategy 1: The Conditional Arbitrage Graph
                // Verify P(A) <= P(B) if A depends on B
                let constraintErr = false;
                if (pair.dependsOn !== null) {
                  const parent = ARB_PAIRS.find(p => p.id === pair.dependsOn);
                  if (parent) {
                    const parentPrice = lmsrPrice(parent.q, parent.b, 0);
                    if (currentPriceYes > parentPrice) constraintErr = true; // P(Super Bowl) > P(Conference Finals) = ARB!
                  }
                }

                // Strategy 2: Calibration Surface Short (Longshot Bias)
                // Markets priced <15% systematically resolve NO 91-96% of time.
                const isLongshotBias = currentPriceYes < 0.15;

                // Strategy 3: Empirical Kelly Sizing
                const rawEdge = pair.myEst - currentPriceYes;
                let hasEdge = Math.abs(rawEdge) >= 0.02 || constraintErr || isLongshotBias;

                // Determine Direction
                let direction = null;
                if (constraintErr) direction = 1; // Short the dependent (Arbitrage)
                else if (isLongshotBias) direction = 1; // Short the longshot
                else if (hasEdge) direction = rawEdge > 0 ? 0 : 1;

                const dirName = direction === 0 ? "BUY YES" : direction === 1 ? "SHORT YES (BUY NO)" : "—";

                // Calculate position sizes and EV
                const kellyAlloc = empiricalKelly(pair.myEst, currentPriceYes, pair.cv, isLongshotBias);
                let ev = 0;
                if (hasEdge && direction !== null) {
                  const simulatedShares = 10;
                  const qAfter = [...pair.q];
                  qAfter[direction] += simulatedShares;
                  const totalCost = costOfTrade(pair.q, qAfter, pair.b);
                  ev = expectedValue(totalCost, simulatedShares, direction, pair.myEst);
                }

                // Strategy Label formatting
                let strategyText = <span style={{ fontSize: 8, color: "#555" }}>EV Monitor</span>;
                if (constraintErr) strategyText = <Badge text="CONDITIONAL ARB" color="#F59E0B" />;
                else if (isLongshotBias) strategyText = <Badge text="CALIBRATION SHORT" color="#9333EA" />;
                else if (Math.abs(rawEdge) >= 0.02) strategyText = <Badge text="VALUE EDGE" color="#3B82F6" />;

                return (
                  <tr key={pair.id} style={{ borderBottom: "1px solid #0f0f0f", background: kellyAlloc > 0 ? "#10B98108" : "transparent" }}>
                    <td style={{ padding: "4px 5px", color: "#333" }}>{i + 1}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: "#e0e0e0" }}>{pair.market}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: constraintErr ? "#EF4444" : "#3B82F6" }}>{(currentPriceYes * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: "#F59E0B" }}>{(pair.myEst * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: Math.abs(rawEdge) >= 0.02 ? "#10B981" : "#888" }}>{(Math.abs(rawEdge) * 100).toFixed(1)}%</td>

                    <td style={{ padding: "4px 5px" }}>{strategyText}</td>

                    <td style={{ padding: "4px 5px" }}>
                      {hasEdge && direction !== null ? <Badge text={dirName} color={direction === 0 ? "#10B981" : "#EF4444"} /> : <span style={{ color: "#555" }}>—</span>}
                    </td>

                    <td style={{ padding: "4px 5px", fontWeight: 800, color: kellyAlloc > 0 ? "#10B981" : "#555" }}>
                      {kellyAlloc > 0 ? `${(kellyAlloc * 100).toFixed(1)}% ALLOC` : "—"}
                    </td>

                    <td style={{ padding: "4px 5px", fontWeight: 800, color: ev > 0 ? "#10B981" : ev < 0 ? "#EF4444" : "#555" }}>
                      {ev !== 0 ? ev > 0 ? `+$${ev.toFixed(2)}` : `-$${Math.abs(ev).toFixed(2)}` : "—"}
                    </td>

                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ padding: "6px 10px", background: "#0A110F", fontSize: 8, color: "#10B981", borderTop: "1px solid #1a1a1a" }}>
            Empirical Kelly = (pb-q)/b * (1 - CV). Allocation limits cap at 25% of dedicated PM capital.
          </div>
        </div>
      )}

      {/* ═══ VOLATILITY RISK MANAGER ═══ */}
      {tab === "risk" && (
        <div style={{ border: "1px solid #1a1a1a", borderRadius: 5, overflow: "hidden" }}>
          <div style={{ padding: "6px 10px", background: "#1A1111", fontSize: 8, color: "#EF4444", fontWeight: 600 }}>
            VOLATILITY-ADJUSTED RISK MANAGER | Cap limits based on Systemic (VIX: {MACRO.vix}) & Idiosyncratic (Beta & MaxDD) Risk
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead><tr style={{ background: "#111", color: "#555", fontSize: 8 }}>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>SYM</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>BETA</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>MAX DD</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>SHARPE</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>VIX</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>RISK IMPACT (Mult)</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>PRE-CAP CONFIDENCE</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>MAX ALLOCATION</th>
            </tr></thead>
            <tbody>
              {results.map((r, i) => {
                const isHighRisk = r.risk.mult < 0.9;
                return (
                  <tr key={i} style={{ borderBottom: "1px solid #0f0f0f", background: isHighRisk ? "#EF444408" : "transparent" }}>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: isHighRisk ? "#EF4444" : "#e0e0e0" }}>{r.sym}</td>
                    <td style={{ padding: "4px 5px", color: r.beta > 1.5 ? "#EF4444" : "#888" }}>{r.beta.toFixed(2)}</td>
                    <td style={{ padding: "4px 5px", color: r.maxDD <= -0.4 ? "#EF4444" : "#888" }}>{(r.maxDD * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px", color: r.sharpe > 1.0 ? "#10B981" : r.sharpe < 0.5 ? "#EF4444" : "#888" }}>{r.sharpe.toFixed(2)}</td>
                    <td style={{ padding: "4px 5px", color: MACRO.vix > 25 ? "#EF4444" : "#888" }}>{MACRO.vix}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: isHighRisk ? "#EF4444" : "#10B981" }}>{r.risk.mult.toFixed(2)}x</td>
                    <td style={{ padding: "4px 5px", color: "#555" }}>{(r.confidence + (isHighRisk && r.confidence > 50 ? 10 : 0)).toFixed(0)}%</td>
                    <td style={{ padding: "4px 5px", fontWeight: 800, color: r.risk.limit < 0.1 ? "#EF4444" : "#10B981" }}>{(r.risk.limit * 100).toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ padding: "6px 10px", background: "#1A1111", fontSize: 8, color: "#EF4444", borderTop: "1px solid #1a1a1a" }}>
            High beta/High Drawdown assets in a high VIX environment suffer sharp allocation penalties to protect against Variance Drag. High Sharpe ratios receive slight capacity boosts.
          </div>
        </div>
      )}

      {/* ═══ QUANT METRICS TAB ═══ */}
      {tab === "quant" && (
        <div style={{ border: "1px solid #A855F730", borderRadius: 5, overflow: "hidden" }}>
          <div style={{ padding: "6px 10px", background: "#1B1225", fontSize: 8, color: "#A855F7", fontWeight: 600 }}>
            DATA SCIENCE: QUANTITATIVE FINANCE METRICS | Sharpe = Ann. Return / Ann. Volatility
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
            <thead><tr style={{ background: "#0a0a0a", color: "#555", fontSize: 8 }}>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>SYM</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>ANN RETURN</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>ANN VOLATILITY</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>SHARPE RATIO</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>MAX DRAWDOWN</th>
              <th style={{ padding: "4px 5px", textAlign: "left", fontWeight: 600, borderBottom: "1px solid #1a1a1a" }}>VARIANCE DRAG EFFECT</th>
            </tr></thead>
            <tbody>
              {results.map((r, i) => {
                // If Volatility > Return by a wide margin, variance drag is severe
                const dragSeverity = r.annVol > r.annRet * 1.5 ? "SEVERE" : r.annVol > r.annRet ? "MODERATE" : "MINIMAL";

                return (
                  <tr key={i} style={{ borderBottom: "1px solid #0f0f0f", background: r.sharpe > 1.0 ? "#10B98108" : r.sharpe < 0.5 ? "#EF444408" : "transparent" }}>
                    <td style={{ padding: "4px 5px", fontWeight: 700, color: "#e0e0e0" }}>{r.sym}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 600, color: r.annRet > 0 ? "#10B981" : "#EF4444" }}>{(r.annRet * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px", color: r.annVol > 0.4 ? "#EF4444" : "#F59E0B" }}>{(r.annVol * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px", fontWeight: 800, color: r.sharpe > 1.0 ? "#10B981" : r.sharpe < 0.5 ? "#EF4444" : "#A855F7" }}>{r.sharpe.toFixed(2)}</td>
                    <td style={{ padding: "4px 5px", fontWeight: 600, color: r.maxDD < -0.3 ? "#EF4444" : "#F59E0B" }}>{(r.maxDD * 100).toFixed(1)}%</td>
                    <td style={{ padding: "4px 5px" }}>
                      <Badge text={dragSeverity} color={dragSeverity === "SEVERE" ? "#EF4444" : dragSeverity === "MODERATE" ? "#F59E0B" : "#10B981"} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ padding: "6px 10px", background: "#1B1225", fontSize: 8, color: "#A855F7", borderTop: "1px solid #A855F730" }}>
            Variance Drag Effect: Volatility acts as a geometric drag on portfolio compounding. Assets with Volatility substantially higher than Annualized Return suffer extreme wealth destruction in ranging markets.
          </div>
        </div>
      )}

      {/* ═══ GROK 4.2 CLOUD PORTAL ═══ */}
      {tab === "grok" && (
        <div style={{ border: "1px solid #F59E0B30", borderRadius: 5, overflow: "hidden", display: "flex", flexDirection: "column", height: "70vh", background: "#0a0a0a" }}>
          <div style={{ padding: "6px 10px", background: "#1A150B", fontSize: 8, color: "#F59E0B", fontWeight: 600, display: "flex", justifyContent: "space-between" }}>
            <span>GROK 4.2 — CLOUD CO-PILOT ACCESS</span>
            <span>STATUS: READY FOR UPLINK</span>
          </div>
          
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 20, textAlign: "center", padding: 40 }}>
            <div style={{ fontSize: 40, opacity: 0.1 }}>🐦</div>
            <div style={{ maxWidth: 400 }}>
              <div style={{ fontSize: 16, fontWeight: 900, color: "#F59E0B", marginBottom: 10 }}>GROK 4.2 UPLINK</div>
              <div style={{ fontSize: 10, color: "#666", lineHeight: 1.5, marginBottom: 20 }}>
                Point to the Grok-4.2 cloud environment for real-time social intelligence and strategic reasoning. 
                Full context-aware chatting enabled via the institutional X-AI infrastructure.
              </div>
              
              <a 
                href="https://x.ai" 
                target="_blank" 
                rel="noreferrer"
                style={{ 
                  display: "inline-block", 
                  background: "#F59E0B", 
                  color: "#000", 
                  padding: "12px 30px", 
                  borderRadius: 4, 
                  fontWeight: 900, 
                  textDecoration: "none",
                  fontSize: 12,
                  boxShadow: "0 4px 14px 0 rgba(245, 158, 11, 0.39)"
                }}
              >
                OPEN GROK 4.2 CLOUD
              </a>
            </div>
            
            <div style={{ marginTop: 40, width: "100%", height: "40%", border: "1px dashed #222", borderRadius: 5, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontSize: 8, color: "#333" }}>[ CLOUD IFRAME CONTAINER — SECURITY HANDSHAKE PENDING ]</span>
            </div>
          </div>
        </div>
      )}

      {/* FOOTER */}
      <div style={{ marginTop: 10, padding: 6, borderTop: "1px solid #1a1a1a", display: "flex", justifyContent: "space-between", fontSize: 7, color: "#222" }}>
        <span>GitAgent v5.7 | 9-Agent Swarm | Inst. Prediction Markets | Quant Metrics</span>
        <span>Agents: W/Wy/B/Be/T/M/SMC/MB/RPB | PM Logic: Empirical Kelly, Conditional Dependency Graphs, Calibration Shorts</span>
      </div>
    </div>
  );
}
