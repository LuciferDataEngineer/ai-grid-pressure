const REGION_COLOR = {
  "New South Wales": "#0e6b62",
  Queensland: "#b5482a",
  Victoria: "#1d3e6e",
  "South Australia": "#8a6a12",
  Tasmania: "#3d6b4f",
  "National Electricity Market": "#1c2430",
  Electricity: "#9d3b24",
  "All prices": "#1d3e6e",
  "Cash rate target": "#1d3e6e",
  "Last 90 days": "#0e6b62",
  "Same 90 days a year earlier": "#c4b48a",
  "4pm to 9pm": "#9d3b24",
  "10am to 2pm": "#0e6b62",
  "High prices": "#9d2c2c",
  "Prices below zero": "#1d3e6e",
  Renewables: "#1f7a4d",
  "Past year": "#1d3e6e",
};
const FUEL_COLOR = {
  Coal: "#3f342c",
  "Brown coal": "#6b4c38",
  Gas: "#c47b4a",
  "Other fossil": "#8d7566",
  Hydro: "#3d7ea6",
  Wind: "#1f7a4d",
  Solar: "#e0a100",
  "Other renewable": "#7d9a4e",
  Storage: "#5b4b8a",
  Other: "#8a8175",
  Unclassified: "#c8c0b4",
};

const charts = [];

function colorFor(name) {
  return REGION_COLOR[name] || FUEL_COLOR[name] || "#1d3e6e";
}

function clearCharts() {
  while (charts.length) {
    const chart = charts.pop();
    chart.dispose();
  }
}

function renderChart(node, spec) {
  if (!window.echarts) {
    node.textContent = "The chart library did not load.";
    return;
  }
  const chart = echarts.init(node);
  charts.push(chart);
  const series = spec.series.map((item) => ({
    name: item.name,
    type: spec.kind === "line" ? "line" : "bar",
    stack: spec.kind === "stacked" ? "fuel" : undefined,
    data: item.data,
    showSymbol: false,
    smooth: spec.kind === "line",
    itemStyle: { color: colorFor(item.name) },
    lineStyle: { width: 2.4, color: colorFor(item.name) },
    areaStyle: spec.kind === "stacked" ? { opacity: 0.9 } : undefined,
    endLabel:
      spec.kind === "line" && spec.series.length > 1
        ? { show: true, formatter: "{a}", color: "#1c2430" }
        : undefined,
    emphasis: { focus: "series" },
  }));
  chart.setOption({
    color: spec.series.map((item) => colorFor(item.name)),
    tooltip: { trigger: "axis" },
    legend: { top: 0, textStyle: { color: "#1c2430" } },
    grid: { left: 56, right: spec.kind === "line" && spec.series.length > 1 ? 110 : 28, top: 48, bottom: 48, containLabel: true },
    xAxis: {
      type: "category",
      data: spec.x,
      axisLabel: { hideOverlap: true, color: "#5c6570" },
    },
    yAxis: {
      type: "value",
      name: spec.y_label,
      nameTextStyle: { color: "#5c6570" },
      axisLabel: { color: "#5c6570" },
      splitLine: { lineStyle: { color: "#eee6d8" } },
    },
    series,
  });
}

function renderMap(hero) {
  const area = { NSW1: "nsw", QLD1: "qld", VIC1: "vic", SA1: "sa", TAS1: "tas" };
  return `<h2>${hero.title}</h2><p class="insight">${hero.insight}</p><div class="nem">${hero.regions
    .map(
      (region) =>
        `<article class="cell ${area[region.id]} ${region.status}"><div><p>${region.name}</p><strong>${region.value}</strong></div><span>${region.caption}</span></article>`,
    )
    .join("")}</div>`;
}

function render(data, tabId) {
  const tab = data.tabs.find((item) => item.id === tabId) || data.tabs[0];
  document.getElementById("as-of").textContent = data.as_of;
  document.getElementById("time-note").textContent = data.time_note;
  document.getElementById("banner").textContent = tab.banner;
  document.getElementById("kpis").innerHTML = tab.kpis
    .map(
      (kpi) =>
        `<article class="kpi ${kpi.status}"><p class="label">${kpi.label}</p><p class="value">${kpi.value}</p><p class="detail">${kpi.detail}</p><p class="note">${kpi.note}</p></article>`,
    )
    .join("");
  clearCharts();
  const hero = document.getElementById("hero");
  const chartsNode = document.getElementById("charts");
  chartsNode.innerHTML = "";
  if (tab.hero.kind === "map") {
    hero.innerHTML = renderMap(tab.hero);
  } else {
    hero.innerHTML = `<h2>${tab.hero.title}</h2><p class="insight">${tab.hero.insight}</p><div class="plot" id="hero-plot"></div>`;
    renderChart(document.getElementById("hero-plot"), tab.hero);
  }
  tab.charts.forEach((spec, index) => {
    const card = document.createElement("article");
    card.className = "chart-card";
    card.innerHTML = `<h3>${spec.title}</h3><p class="insight">${spec.insight}</p><div class="plot" id="plot-${index}"></div>`;
    chartsNode.appendChild(card);
    renderChart(document.getElementById(`plot-${index}`), spec);
  });
  document.getElementById("meaning").textContent = tab.meaning;
  document.getElementById("sources").textContent = tab.sources;
  document.querySelectorAll(".tabs button").forEach((button) => {
    button.setAttribute("aria-selected", button.dataset.tab === tab.id ? "true" : "false");
  });
  if (location.hash.replace("#", "") !== tab.id) {
    history.replaceState(null, "", `#${tab.id}`);
  }
}

fetch("./data/dashboard.json")
  .then((response) => response.json())
  .then((data) => {
    const nav = document.getElementById("tabs");
    data.tabs.forEach((tab, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = tab.label;
      button.dataset.tab = tab.id;
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      button.addEventListener("click", () => render(data, tab.id));
      nav.appendChild(button);
    });
    const initial = location.hash.replace("#", "");
    render(data, data.tabs.some((tab) => tab.id === initial) ? initial : data.tabs[0].id);
    window.addEventListener("hashchange", () => {
      const next = location.hash.replace("#", "");
      if (data.tabs.some((tab) => tab.id === next)) render(data, next);
    });
    window.addEventListener("resize", () => charts.forEach((chart) => chart.resize()));
  })
  .catch(() => {
    document.getElementById("banner").textContent = "The briefing figures could not be loaded.";
  });
