const DATA_ROOT = "../data";
const COMMON_COINS_PATH = `${DATA_ROOT}/common_coins.json`;

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

const state = {
  charts: [],
  coins: [],
  modalChart: null,
};

const elements = {
  select: document.getElementById("coinSelect"),
  status: document.getElementById("status"),
  chartsContainer: document.getElementById("chartsContainer"),
  modal: document.getElementById("exchangeModal"),
  modalBackdrop: document.getElementById("modalBackdrop"),
  modalClose: document.getElementById("modalClose"),
  modalTitle: document.getElementById("modalTitle"),
  modalSubtitle: document.getElementById("modalSubtitle"),
  modalChart: document.getElementById("modalChart"),
  modalStats: document.getElementById("modalStats"),
  modalTableWrapper: document.getElementById("modalTableWrapper"),
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
  destroyCharts();
  elements.chartsContainer.innerHTML = "";
  setStatus(`${coin} 데이터를 불러오는 중입니다...`);
  try {
    const data = await fetchJSON(`${DATA_ROOT}/daily_histories/${coin}.json`);
    const exchanges = data.exchanges || {};
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

async function init() {
  setStatus("코인 목록을 불러오는 중입니다...");
  try {
    const payload = await fetchJSON(COMMON_COINS_PATH);
    state.coins = payload.coins || [];
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
  } catch (error) {
    console.error(error);
    setStatus(`코인 목록을 불러올 수 없습니다: ${error.message}`, "error");
  }
}

document.addEventListener("DOMContentLoaded", init);
