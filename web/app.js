const DATA_ROOT = "../data";
const COMMON_COINS_PATH = `${DATA_ROOT}/common_coins.json`;
const INSIGHTS_PATH = `${DATA_ROOT}/analytics/quant_insights.json`;

const EXCHANGES = [
  {
    key: "binance",
    label: "Binance",
    highColor: "rgba(240, 185, 11, 0.9)",
    lowColor: "rgba(240, 185, 11, 0.3)",
  },
  {
    key: "coinbase",
    label: "Coinbase",
    highColor: "rgba(0, 82, 255, 0.9)",
    lowColor: "rgba(0, 82, 255, 0.3)",
  },
  {
    key: "bybit",
    label: "Bybit",
    highColor: "rgba(244, 183, 49, 0.9)",
    lowColor: "rgba(244, 183, 49, 0.3)",
  },
  {
    key: "upbit",
    label: "Upbit (KRW)",
    highColor: "rgba(31, 142, 241, 0.9)",
    lowColor: "rgba(31, 142, 241, 0.3)",
  },
  {
    key: "okx",
    label: "OKX",
    highColor: "rgba(15, 23, 42, 0.9)",
    lowColor: "rgba(15, 23, 42, 0.3)",
  },
];
const EXCHANGE_LABELS = EXCHANGES.reduce((acc, item) => {
  acc[item.key] = item.label;
  return acc;
}, {});

const state = {
  charts: [],
  coins: [],
  coinSet: new Set(),
  modalChart: null,
  insights: null,
  insightHighlight: null,
};

const elements = {
  select: document.getElementById("coinSelect"),
  status: document.getElementById("status"),
  chartsContainer: document.getElementById("chartsContainer"),
  tenDayTableBody: document.getElementById("tenDayTableBody"),
  modal: document.getElementById("exchangeModal"),
  modalBackdrop: document.getElementById("modalBackdrop"),
  modalClose: document.getElementById("modalClose"),
  modalTitle: document.getElementById("modalTitle"),
  modalSubtitle: document.getElementById("modalSubtitle"),
  modalChart: document.getElementById("modalChart"),
  modalStats: document.getElementById("modalStats"),
  modalTableWrapper: document.getElementById("modalTableWrapper"),
  insightsSection: document.getElementById("insightsSection"),
  insightCards: document.getElementById("insightCards"),
  declinerTable: document.querySelector("#declinerTable tbody"),
  gainerTable: document.querySelector("#gainerTable tbody"),
  insightChartSvg: document.getElementById("insightChart"),
};

function setStatus(message, type = "info") {
  elements.status.textContent = message;
  elements.status.dataset.status = type;
}

async function fetchJSON(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path} (${response.status})`);
  }
  return response.json();
}

function destroyCharts() {
  state.charts.forEach((chart) => chart.destroy());
  state.charts = [];
}

function destroyModalChart() {
  if (state.modalChart) {
    state.modalChart.destroy();
    state.modalChart = null;
  }
}

function createHighLowChart(canvas, labels, highs, lows, colors) {
  const ctx = canvas.getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "High",
          data: highs,
          borderColor: colors.highColor,
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: "Low",
          data: lows,
          borderColor: colors.lowColor,
          backgroundColor: "transparent",
          tension: 0.2,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { maxTicksLimit: 6 },
        },
        y: {
          ticks: { maxTicksLimit: 6 },
        },
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString()} (${ctx.label})`,
          },
        },
      },
    },
  });
}

function formatNumber(value) {
  const asNum = Number(value);
  if (Number.isFinite(asNum)) {
    return asNum.toLocaleString("en-US", { maximumFractionDigits: 6 });
  }
  return value ?? "-";
}

function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatDate(value) {
  if (!value) return "-";
  return value.slice(0, 10);
}

function renderTestBadge(label, ok) {
  const className = ok ? "test-badge ok" : "test-badge bad";
  return `<span class="${className}">${ok ? "✔" : "✖"} ${label}</span>`;
}

function computeTenDayStats(candles) {
  if (!candles || candles.length < 11) {
    return null;
  }
  const window = candles.slice(0, 11);
  const startClose = Number(window[0].close);
  const endClose = Number(window[window.length - 1].close);
  if (!Number.isFinite(startClose) || startClose === 0) {
    return null;
  }

  let peak = startClose;
  let maxDrawdown = 0;
  window.forEach((entry) => {
    const price = Number(entry.close);
    if (!Number.isFinite(price)) return;
    peak = Math.max(peak, price);
    if (peak > 0) {
      const dd = price / peak - 1;
      maxDrawdown = Math.min(maxDrawdown, dd);
    }
  });

  const logReturns = [];
  const logPrices = [];
  let validLogs = true;
  window.forEach((entry, idx) => {
    const price = Number(entry.close);
    if (!(price > 0)) {
      validLogs = false;
    } else {
      logPrices.push(Math.log(price));
      if (idx > 0) {
        const prev = Number(window[idx - 1].close);
        if (prev > 0) {
          logReturns.push(Math.log(price / prev));
        }
      }
    }
  });
  const logReturn = validLogs ? logReturns.reduce((acc, val) => acc + val, 0) : null;
  let beta = null;
  if (validLogs) {
    const n = logPrices.length;
    const meanT = (n - 1) / 2;
    const meanLog = logPrices.reduce((acc, val) => acc + val, 0) / n;
    let numerator = 0;
    let denominator = 0;
    logPrices.forEach((logPrice, idx) => {
      numerator += (idx - meanT) * (logPrice - meanLog);
      denominator += (idx - meanT) ** 2;
    });
    beta = denominator === 0 ? 0 : numerator / denominator;
  }

  return {
    startDate: window[0].timestamp_iso,
    endDate: window[window.length - 1].timestamp_iso,
    startClose,
    endClose,
    cumReturn: endClose / startClose - 1,
    logReturn,
    beta,
    maxDrawdown,
    priceDrop: endClose < startClose,
    logDrop: logReturn !== null ? logReturn < 0 : null,
    betaDrop: beta !== null ? beta < 0 : null,
  };
}

function buildCandleTable(candles) {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["날짜", "Open", "High", "Low", "Close", "Volume"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  candles.forEach((entry) => {
    const tr = document.createElement("tr");
    [
      entry.timestamp_iso.slice(0, 10),
      formatNumber(entry.open),
      formatNumber(entry.high),
      formatNumber(entry.low),
      formatNumber(entry.close),
      formatNumber(entry.volume),
    ].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  return table;
}

function openModal(meta, exchangeData) {
  if (!exchangeData || !exchangeData.candles?.length) {
    return;
  }
  const candles = exchangeData.candles;
  const labels = candles.map((entry) => entry.timestamp_iso.slice(0, 10));
  const highs = candles.map((entry) => Number(entry.high));
  const lows = candles.map((entry) => Number(entry.low));
  const first = candles[0];
  const last = candles[candles.length - 1];

  elements.modalTitle.textContent = `${meta.label} · ${exchangeData.market}`;
  elements.modalSubtitle.textContent = `${first.timestamp_iso.slice(0, 10)} → ${last.timestamp_iso.slice(
    0,
    10,
  )} · ${exchangeData.count.toLocaleString()}일`;

  const statsData = [
    ["시장", exchangeData.market],
    ["견적 통화", exchangeData.quote],
    ["캔들 수", exchangeData.count.toLocaleString()],
    ["최근 고가", formatNumber(last.high)],
    ["최근 저가", formatNumber(last.low)],
    ["최근 종가", formatNumber(last.close)],
    ["최근 거래량", formatNumber(last.volume)],
  ];
  elements.modalStats.innerHTML = statsData
    .map(
      ([label, value]) => `
        <dt>${label}</dt>
        <dd>${value}</dd>
      `,
    )
    .join("");

  elements.modalTableWrapper.innerHTML = "";
  elements.modalTableWrapper.appendChild(buildCandleTable(candles));

  destroyModalChart();
  state.modalChart = createHighLowChart(elements.modalChart, labels, highs, lows, meta);

  elements.modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal() {
  elements.modal.classList.add("hidden");
  document.body.classList.remove("modal-open");
  destroyModalChart();
}

function clearInsightChart() {
  if (elements.insightChartSvg) {
    elements.insightChartSvg.innerHTML = "";
  }
}

function renderInsightCards(summary) {
  if (!elements.insightCards || !summary) return;
  const cards = [
    { label: "교집합 상장 코인 수", value: summary.coins ?? 0 },
    { label: "중앙값 10일 누적수익률", value: formatPercent(summary.median_cum_return) },
    { label: "중앙값 최대낙폭", value: formatPercent(summary.median_drawdown) },
    { label: "중앙값 교차거래소 스프레드", value: formatPercent(summary.median_spread, 3) },
    { label: "중앙값 변동성(연환산)", value: formatPercent(summary.median_volatility, 2) },
  ];
  elements.insightCards.innerHTML = cards
    .map(
      (card) => `
        <article class="insight-card">
          <strong>${card.value}</strong>
          <p>${card.label}</p>
        </article>
      `,
    )
    .join("");
}

function renderTableRows(tbody, rows, formatter) {
  if (!tbody) return;
  tbody.innerHTML = rows.map((row) => formatter(row)).join("");
}

function renderInsightsTables(insights) {
  const decliners = (insights.top_decliners || []).slice(0, 5);
  const gainers = (insights.top_gainers || []).slice(0, 5);

  renderTableRows(elements.declinerTable, decliners, (row) => {
    return `
      <tr>
        <td>${row.coin}</td>
        <td>${formatPercent(row.cum_return)}</td>
        <td>${formatDate(row.listing_date)}</td>
      </tr>
    `;
  });

  renderTableRows(elements.gainerTable, gainers, (row) => {
    return `
      <tr>
        <td>${row.coin}</td>
        <td>${formatPercent(row.cum_return)}</td>
        <td>${formatDate(row.listing_date)}</td>
      </tr>
    `;
  });
}

function renderInsightsChart(insights) {
  if (!elements.insightChartSvg) {
    return;
  }
  const distribution = (insights.return_distribution || []).slice();
  distribution.sort((a, b) => Number(a.cum_return) - Number(b.cum_return));
  if (!distribution.length) return;
  const highlightSymbol = state.insightHighlight;

  const bottomSample = distribution.slice(0, 5);
  const topSample = distribution.slice(-5);
  let sample = bottomSample.concat(topSample);

  if (highlightSymbol) {
    const existing = sample.find((item) => item.coin === highlightSymbol);
    if (!existing) {
      const highlightEntry = distribution.find((item) => item.coin === highlightSymbol);
      if (highlightEntry) {
        sample.push(highlightEntry);
      }
    }
  }

  sample = sample
    .filter((item, index, self) => self.findIndex((ref) => ref.coin === item.coin) === index)
    .sort((a, b) => Number(a.cum_return) - Number(b.cum_return));

  if (!sample.length) {
    clearInsightChart();
    const msg = document.createElementNS("http://www.w3.org/2000/svg", "text");
    msg.setAttribute("x", "50%");
    msg.setAttribute("y", "50%");
    msg.setAttribute("text-anchor", "middle");
    msg.setAttribute("fill", "#94a3b8");
    msg.setAttribute("font-size", "14");
    msg.textContent = "표시할 데이터가 없습니다.";
    elements.insightChartSvg?.appendChild(msg);
    return;
  }

  const labels = sample.map((item) => item.coin);
  const values = sample.map((item) => Number(item.cum_return) * 100);
  const svg = elements.insightChartSvg;
  clearInsightChart();
  if (!svg) return;

  const width = svg.clientWidth || svg.parentElement?.clientWidth || 960;
  const height = 320;
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const margin = { top: 30, right: 30, bottom: 70, left: 70 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.setAttribute("transform", `translate(${margin.left},${margin.top})`);
  svg.appendChild(g);

  const yMin = Math.min(-100, Math.min(...values));
  const yMax = Math.max(100, Math.max(...values));
  const scaleY = (value) => innerHeight - ((value - yMin) / (yMax - yMin || 1)) * innerHeight;
  const zeroY = scaleY(0);

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="gradUp" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#34d399" />
      <stop offset="100%" stop-color="#10b981" />
    </linearGradient>
    <linearGradient id="gradDown" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#f87171" />
      <stop offset="100%" stop-color="#ef4444" />
    </linearGradient>
  `;
  svg.appendChild(defs);

  const gridGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gridGroup.setAttribute("class", "chart-grid");
  const ticks = 5;
  for (let i = 0; i <= ticks; i += 1) {
    const value = yMin + ((yMax - yMin) / ticks) * i;
    const y = scaleY(value);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", 0);
    line.setAttribute("x2", innerWidth);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("stroke", "rgba(148, 163, 184, 0.25)");
    gridGroup.appendChild(line);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", -10);
    label.setAttribute("y", y + 4);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("fill", "#475569");
    label.setAttribute("font-size", "12");
    label.textContent = `${value.toFixed(0)}%`;
    gridGroup.appendChild(label);
  }
  g.appendChild(gridGroup);

  const barWidth = innerWidth / sample.length;
  const tooltip = document.createElementNS("http://www.w3.org/2000/svg", "text");
  tooltip.setAttribute("fill", "#0f172a");
  tooltip.setAttribute("font-size", "12");
  tooltip.setAttribute("text-anchor", "middle");
  tooltip.setAttribute("class", "chart-tooltip");
  g.appendChild(tooltip);

  sample.forEach((item, idx) => {
    const value = values[idx];
    const x = idx * barWidth + barWidth * 0.15;
    const widthBar = barWidth * 0.7;
    const y = value >= 0 ? scaleY(value) : zeroY;
    const heightBar = Math.abs(scaleY(value) - zeroY);
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", widthBar);
    rect.setAttribute("height", Math.max(heightBar, 2));
    rect.setAttribute("rx", 10);
    rect.setAttribute("fill", highlightSymbol === item.coin ? "#3b82f6" : value < 0 ? "url(#gradDown)" : "url(#gradUp)");
    rect.setAttribute("stroke", highlightSymbol === item.coin ? "#1d4ed8" : value < 0 ? "#dc2626" : "#047857");
    rect.setAttribute("stroke-width", highlightSymbol === item.coin ? 2 : 1);

    rect.addEventListener("mouseenter", () => {
      tooltip.textContent = `${item.coin}: ${value.toFixed(2)}%`;
      tooltip.setAttribute("x", x + widthBar / 2);
      tooltip.setAttribute("y", y - 8);
    });
    rect.addEventListener("mouseleave", () => {
      tooltip.textContent = "";
    });

    g.appendChild(rect);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x + widthBar / 2);
    label.setAttribute("y", innerHeight + 28);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("font-size", "12");
    label.setAttribute("fill", "#1f2937");
    label.textContent = item.coin;
    g.appendChild(label);
  });
}

function renderInsights() {
  if (!state.insights || !elements.insightsSection) return;
  renderInsightCards(state.insights.summary);
  renderInsightsTables(state.insights);
  renderInsightsChart(state.insights);
  elements.insightsSection.classList.remove("hidden");
}

function scrollToCharts() {
  elements.chartsContainer?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderTenDaySummary(exchanges) {
  if (!elements.tenDayTableBody) return;
  const rows = Object.entries(exchanges || {}).map(([name, data]) => {
    const stats = computeTenDayStats(data?.candles || []);
    if (!stats) {
      return `
        <tr>
          <td>${EXCHANGE_LABELS[name] || name}</td>
          <td colspan="4" class="hint">데이터 부족</td>
        </tr>
      `;
    }
    return `
      <tr>
        <td>${EXCHANGE_LABELS[name] || name}</td>
        <td>${formatDate(stats.startDate)} → ${formatDate(stats.endDate)}</td>
        <td>${stats.startClose.toLocaleString()} → ${stats.endClose.toLocaleString()}</td>
        <td>${formatPercent(stats.cumReturn)}</td>
        <td>${stats.logReturn !== null ? `${(stats.logReturn * 100).toFixed(2)}%` : "-"}</td>
        <td>${stats.beta !== null ? stats.beta.toFixed(4) : "-"}</td>
        <td>${formatPercent(stats.maxDrawdown)}</td>
        <td>
          <div class="test-badges">
            ${renderTestBadge("P₁₀<P₀", stats.priceDrop)}
            ${renderTestBadge("R₁₀<0", stats.logDrop ?? false)}
            ${renderTestBadge("β<0", stats.betaDrop ?? false)}
          </div>
        </td>
      </tr>
    `;
  });
  elements.tenDayTableBody.innerHTML = rows.length ? rows.join("") : `
    <tr><td colspan="7" class="hint">표시할 데이터가 없습니다.</td></tr>
  `;
}

function buildExchangeCard(meta, exchangeData) {
  const card = document.createElement("article");
  card.className = "chart-card";

  const title = document.createElement("h2");
  title.textContent = meta.label;
  card.appendChild(title);

  if (!exchangeData) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "데이터가 없습니다.";
    card.appendChild(empty);
    return card;
  }

  const info = document.createElement("p");
  info.className = "hint";
  info.textContent = `${exchangeData.market} · ${exchangeData.count.toLocaleString()}일`;
  card.appendChild(info);

  const labels = exchangeData.candles.map((entry) => entry.timestamp_iso.slice(0, 10));
  const highs = exchangeData.candles.map((entry) => Number(entry.high));
  const lows = exchangeData.candles.map((entry) => Number(entry.low));

  const wrapper = document.createElement("div");
  wrapper.className = "chart-wrapper";
  const canvas = document.createElement("canvas");
  wrapper.appendChild(canvas);
  card.appendChild(wrapper);

  state.charts.push(createHighLowChart(canvas, labels, highs, lows, meta));

  const button = document.createElement("button");
  button.type = "button";
  button.className = "detail-button";
  button.textContent = "상세 보기 (전체 화면)";
  button.addEventListener("click", () => openModal(meta, exchangeData));
  card.appendChild(button);
  return card;
}

async function loadCoin(coin) {
  state.insightHighlight = coin;
  if (state.insights) {
    renderInsightsChart(state.insights);
  }
  destroyCharts();
  elements.chartsContainer.innerHTML = "";
  setStatus(`${coin} 데이터를 불러오는 중입니다...`);
  try {
    const data = await fetchJSON(`${DATA_ROOT}/daily_histories/${coin}.json`);
    const exchanges = data.exchanges || {};
    renderTenDaySummary(exchanges);
    EXCHANGES.forEach((meta) => {
      const card = buildExchangeCard(meta, exchanges[meta.key]);
      elements.chartsContainer.appendChild(card);
    });
    setStatus(
      `${coin} · ${Object.keys(exchanges).length}개 거래소 · 생성 시각 ${data.generated_at}`,
    );
  } catch (error) {
    console.error(error);
    setStatus(`${coin} 데이터를 불러올 수 없습니다: ${error.message}`, "error");
  }
}

async function loadInsights() {
  if (!INSIGHTS_PATH || !elements.insightsSection) return;
  try {
    const data = await fetchJSON(INSIGHTS_PATH);
    state.insights = data;
    renderInsights();
  } catch (error) {
    console.warn("Unable to load quant insights:", error);
    elements.insightsSection?.classList.add("hidden");
  }
}

async function init() {
  setStatus("코인 목록을 불러오는 중입니다...");
  try {
    const payload = await fetchJSON(COMMON_COINS_PATH);
    state.coins = (payload.coins || []).map((coin) => coin.toUpperCase());
    state.coinSet = new Set(state.coins);
    if (!state.coins.length) {
      setStatus("공통 상장 코인 목록이 비어 있습니다.", "error");
      return;
    }
    elements.select.innerHTML = state.coins
      .map((coin) => `<option value="${coin}">${coin}</option>`)
      .join("");
    elements.select.addEventListener("change", (event) => {
      const nextCoin = event.target.value;
      if (nextCoin) {
        loadCoin(nextCoin);
      }
    });
    elements.modalClose.addEventListener("click", closeModal);
    elements.modalBackdrop.addEventListener("click", closeModal);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !elements.modal.classList.contains("hidden")) {
        closeModal();
      }
    });
    loadCoin(state.coins[0]);
    loadInsights();
  } catch (error) {
    console.error(error);
    setStatus(`코인 목록을 불러올 수 없습니다: ${error.message}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", init);
