// 1개월 전망 대화형 그래프 (Chart.js). 자료는 페이지 안 <script id="mdata"> JSON.
(function () {
  const el = document.getElementById("mdata");
  if (!el || !window.Chart) return;
  const D = JSON.parse(el.textContent);
  const fmt = (v, d = 1) => (v == null || isNaN(v) ? "-" : (+v).toFixed(d));
  const pct = (v) => (v == null ? "-" : Math.round(v * 100) + "%");
  const SRC = { statistical: "통계모델", ec46: "ECMWF EC46", gefs: "NOAA GEFS" };
  const COLORS = {
    temp: ["#3d6fc4", "#b3bac1", "#c9473b"], precip: ["#9c6b3c", "#b3bac1", "#2e8a5a"],
    cloud: ["#c99a2e", "#b3bac1", "#56657a"], srad: ["#6f7d96", "#b3bac1", "#d9831a"],
  };

  if (window.matchMedia("(max-width: 640px)").matches) {  // 휴대폰: 축 이름 빼고 범례 작게
    Chart.register({ id: "narrowFit", beforeInit(ch) {
      const o = ch.config.options;
      for (const s of Object.values(o.scales || {})) if (s.title) s.title.display = false;
      const pl = (o.plugins = o.plugins || {}), lg = (pl.legend = pl.legend || {}), lb = (lg.labels = lg.labels || {});
      lb.font = { size: 11 }; lb.boxWidth = 10; lb.padding = 8;
    } });
  }
  Chart.defaults.font.family = "'Noto Sans KR', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = "#5b6670";

  // 막대 안에 확률 숫자 쓰기 (10% 이상만)
  const inLabels = {
    id: "inLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 12px 'Noto Sans KR', sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      chart.data.datasets.forEach((ds, i) => {
        chart.getDatasetMeta(i).data.forEach((bar, j) => {
          const v = ds.data[j];
          if (v == null || v < 10) return;
          if (Math.abs(bar.x - bar.base) < ctx.measureText(v + "%").width + 6) return;  // 막대가 좁으면 생략
          ctx.fillStyle = i === 1 ? "#2b3138" : "#fff";
          ctx.fillText(v + "%", bar.x - (bar.x - bar.base) / 2, bar.y);
        });
      });
      ctx.restore();
    },
  };

  const tip = {
    backgroundColor: "rgba(24,30,38,.94)", padding: 10, titleFont: { weight: "700", size: 13 },
    bodySpacing: 4, footerFont: { weight: "400", size: 11.5 }, footerSpacing: 3, footerMarginTop: 8,
  };

  for (const [rid, R] of Object.entries(D.regions)) {
    const W = R.weeks;
    const labels = W.map((w) => [w.name, w.range]);

    for (const v of R.vars) {
      const c = document.getElementById(`m-${rid}-${v.key}`);
      if (!c) continue;
      const col = COLORS[v.key] || COLORS.temp;
      new Chart(c, {
        type: "bar",
        data: { labels, datasets: v.cats.map((cat, k) => ({
          label: cat, data: W.map((w) => w.vars[v.key] ? w.vars[v.key].display[k] : null),
          backgroundColor: col[k], borderColor: "#fff", borderWidth: 1, borderSkipped: false,
          barPercentage: 0.78, categoryPercentage: 0.9,
        })) },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
          interaction: { mode: "index", intersect: false },
          scales: {
            x: { stacked: true, min: 0, max: 100, ticks: { callback: (x) => x + "%", stepSize: 25 },
                 grid: { color: "#eef0f3" } },
            y: { stacked: true, grid: { display: false }, ticks: { font: { size: 12 } } },
          },
          plugins: {
            legend: { position: "top", align: "end", labels: { boxWidth: 12, boxHeight: 12 } },
            tooltip: { ...tip, callbacks: {
              title: (it) => it.length ? `${W[it[0].dataIndex].name} (${W[it[0].dataIndex].range})` : "",
              label: (ctx) => ` ${ctx.dataset.label} ${ctx.raw}%`,
              afterBody: (it) => {
                if (!it.length) return "";
                const x = W[it[0].dataIndex].vars[v.key];
                const out = [`→ ${x.verdict}`, `평년 비슷 범위: ${x.normal[0]}~${x.normal[1]} ${v.unit}`];
                if (x.center != null) out.push(`역학모델 예측 중심: ${fmt(x.center)} ${v.unit}`);
                return out;
              },
              footer: (it) => {
                if (!it.length) return "";
                const x = W[it[0].dataIndex].vars[v.key];
                const lines = ["모델별 (" + v.cats.join("/") + ", 가중치)"];
                for (const [s, p] of Object.entries(x.sources || {}))
                  lines.push(`${SRC[s] || s}: ${p.map((q) => Math.round(q * 100)).join("/")}%` +
                    (x.weights && x.weights[s] != null ? ` (${Math.round(x.weights[s] * 100)}%)` : ""));
                return lines;
              },
            } },
          },
        },
        plugins: [inLabels],
      });
    }

    // 강수형태: 비 오는 날·눈 오는 날(막대, 왼쪽) + 눈 올 확률(선, 오른쪽)
    const pc = document.getElementById(`m-${rid}-ptype`);
    if (pc) {
      const P = W.map((w) => w.ptype || {});
      new Chart(pc, {
        data: { labels: W.map((w) => [w.name, w.range]), datasets: [
          { type: "line", label: "눈 올 확률", data: P.map((p) => p.p_snow * 100), yAxisID: "y1",
            borderColor: "#6a5acd", backgroundColor: "#6a5acd", borderWidth: 2.5, pointRadius: 4, tension: 0.25, order: 0 },
          { type: "line", label: "평년 눈 확률", data: P.map((p) => p.clim.p_snow * 100), yAxisID: "y1",
            borderColor: "#6a5acdaa", borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, order: 1 },
          { type: "bar", label: "비 오는 날", data: P.map((p) => p.rain_days), backgroundColor: "#2e8a5a",
            borderRadius: 3, order: 2, barPercentage: 0.7 },
          { type: "bar", label: "눈 오는 날", data: P.map((p) => p.snow_days), backgroundColor: "#8fb3e8",
            borderRadius: 3, order: 3, barPercentage: 0.7 },
        ] },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          interaction: { mode: "index", intersect: false },
          scales: {
            x: { grid: { display: false } },
            y: { beginAtZero: true, suggestedMax: 4, title: { display: true, text: "일 수" }, grid: { color: "#eef0f3" } },
            y1: { position: "right", min: 0, max: 100, title: { display: true, text: "눈 올 확률 %" },
                  grid: { display: false }, ticks: { stepSize: 25 } },
          },
          plugins: {
            legend: { position: "top", align: "end", labels: { boxWidth: 12, boxHeight: 10 } },
            tooltip: { ...tip,
              filter: (it) => it.dataset.label !== "평년 눈 확률",
              callbacks: {
                title: (it) => it.length ? `${W[it[0].dataIndex].name} (${W[it[0].dataIndex].range})` : "",
                label: (ctx) => {
                  const p = P[ctx.dataIndex];
                  if (ctx.dataset.label === "눈 올 확률") return ` 눈 올 확률 ${pct(p.p_snow)} · 평년 ${pct(p.clim.p_snow)}`;
                  if (ctx.dataset.label === "비 오는 날") return ` 비 오는 날 ${fmt(p.rain_days)}일 · 평년 ${fmt(p.clim.rain_days)}일`;
                  return ` 눈 오는 날 ${fmt(p.snow_days)}일 · 평년 ${fmt(p.clim.snow_days)}일`;
                },
              } },
          },
        },
      });
    }
  }
})();
