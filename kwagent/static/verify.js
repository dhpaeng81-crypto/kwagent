// 정확도 화면 대화형 그래프 (Chart.js). 자료는 페이지 안 <script id="vdata"> JSON.
(function () {
  const el = document.getElementById("vdata");
  if (!el || !window.Chart) return;
  const D = JSON.parse(el.textContent);
  const f2 = (v, d = 2) => (v == null || isNaN(v) ? "-" : (+v).toFixed(d));
  const sg = (v) => (v == null || isNaN(v) ? "-" : (v > 0 ? "+" : "") + (+v).toFixed(2));
  const SRC = { combined: ["최종(결합)", "#2f6fdb"], statistical: ["통계모델", "#8a939c"],
                ec46: ["ECMWF EC46", "#c9473b"], gefs: ["NOAA GEFS", "#2e8a5a"] };
  const MOD = { combined: ["최종(결합)", "#2f6fdb"], ecmwf_ens: ["ECMWF 앙상블", "#c9473b"],
                ecmwf_aifs: ["ECMWF AI 앙상블", "#e08a12"], gefs: ["NOAA GEFS", "#2e8a5a"],
                icon_eps: ["DWD ICON 앙상블", "#7b5cc4"] };
  const BIN_COL = ["#1f5fbf", "#5f93dd", "#a9c6ee"];
  const tip = { backgroundColor: "rgba(24,30,38,.94)", padding: 10, titleFont: { weight: "700", size: 13 },
                bodySpacing: 4 };
  // 0 기준선 (0 위 = 평년보다 나음)
  const zeroLine = {
    id: "zeroLine",
    beforeDatasetsDraw(chart) {
      const y = chart.scales.y; if (!y || y.min > 0 || y.max < 0) return;
      const { ctx, chartArea: a } = chart; const py = y.getPixelForValue(0);
      ctx.save(); ctx.strokeStyle = "#7b858f"; ctx.lineWidth = 1.2; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(a.left, py); ctx.lineTo(a.right, py); ctx.stroke(); ctx.restore();
    },
  };
  Chart.defaults.font.family = "'Noto Sans KR', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = "#5b6670";
  const legend = { position: "top", align: "end", labels: { boxWidth: 12, boxHeight: 10 } };

  // ---- 1개월 전망: 변수마다 주차별 RPSS 선
  for (const [rid, R] of Object.entries((D.month || {}).regions || {})) {
    for (const v of R.vars) {
      const c = document.getElementById(`v-${rid}-${v.key}`);
      if (!c) continue;
      const leads = [1, 2, 3, 4];
      const ds = Object.entries(v.sources).filter(([s]) => SRC[s]).map(([s, pts]) => {
        const by = Object.fromEntries(pts.map((p) => [p.lead, p]));
        return { label: SRC[s][0], src: s, by, data: leads.map((l) => (by[l] ? by[l].rpss : null)),
          borderColor: SRC[s][1], backgroundColor: SRC[s][1], borderWidth: s === "combined" ? 3 : 1.6,
          pointRadius: s === "combined" ? 4 : 3, pointHoverRadius: 6, tension: 0.2, spanGaps: true };
      });
      new Chart(c, {
        type: "line", data: { labels: leads.map((l) => l + "주"), datasets: ds },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          interaction: { mode: "index", intersect: false },
          scales: { x: { grid: { display: false }, offset: true },
                    y: { title: { display: true, text: "RPSS" }, suggestedMin: -0.2, suggestedMax: 0.3, grid: { color: "#eef0f3" } } },
          plugins: { legend, tooltip: { ...tip, callbacks: {
            title: (it) => it.length ? `${v.name} · ${it[0].label} 앞 예측` : "",
            label: (ctx) => { const p = ctx.dataset.by[ctx.dataIndex + 1];
              return p ? ` ${ctx.dataset.label}: RPSS ${sg(p.rpss)} (${p.n}건)` : null; },
            footer: () => "0보다 크면 평년(33/33/33%)보다 나음",
          } } },
        },
        plugins: [zeroLine],
      });
    }
  }

  // ---- 2주 일별: 변수별 평년 대비 개선(막대, 예보일 구간별)
  const DY = D.daily;
  if (DY) {
    const c = document.getElementById("v-daily-skill");
    if (c) {
      new Chart(c, {
        type: "bar",
        data: { labels: DY.vars.map((v) => v.name), datasets: DY.bins.map((b, k) => ({
          label: b, bin: b, data: DY.vars.map((v) => (v.bins[b] ? v.bins[b].skill : null)),
          backgroundColor: BIN_COL[k], borderRadius: 3, barPercentage: 0.8, categoryPercentage: 0.75 })) },
        options: {
          responsive: true, maintainAspectRatio: false, animation: false,
          interaction: { mode: "index", intersect: false },
          scales: { x: { grid: { display: false } },
                    y: { title: { display: true, text: "평년 대비 개선" }, suggestedMin: -0.1, suggestedMax: 0.6, grid: { color: "#eef0f3" } } },
          plugins: { legend, tooltip: { ...tip, callbacks: {
            title: (it) => it.length ? `${DY.vars[it[0].dataIndex].name}` : "",
            label: (ctx) => {
              const v = DY.vars[ctx.dataIndex], x = v.bins[ctx.dataset.bin];
              if (!x) return null;
              return ` ${ctx.dataset.bin}: 개선 ${sg(x.skill)} · 오차 ${f2(x.mae)}${v.unit} (평년 ${f2(x.mae_clim)})`;
            },
            afterLabel: (ctx) => {
              const x = DY.vars[ctx.dataIndex].bins[ctx.dataset.bin];
              if (!x) return "";
              let s = `   범위 적중 ${Math.round(x.cover * 100)}% · ${x.n}건`;
              if (x.bss != null) s += ` · 강수확률 개선 ${sg(x.bss)}`;
              return s;
            },
          } } },
        },
        plugins: [zeroLine],
      });
    }
    // 모델별 평균 오차: 변수 고르기
    const mc = document.getElementById("v-daily-models"), sel = document.getElementById("v-daily-var");
    if (mc && sel && DY.models) {
      let chart;
      const draw = () => {
        const key = sel.value, M = DY.models[key] || {}, unit = (DY.vars.find((v) => v.key === key) || {}).unit || "";
        const ds = Object.entries(M).filter(([s]) => MOD[s]).map(([s, by]) => ({
          label: MOD[s][0], by, data: DY.bins.map((b) => (by[b] ? by[b].mae : null)),
          backgroundColor: MOD[s][1], borderRadius: 3, barPercentage: 0.85, categoryPercentage: 0.8 }));
        if (chart) chart.destroy();
        chart = new Chart(mc, {
          type: "bar", data: { labels: DY.bins, datasets: ds },
          options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            interaction: { mode: "index", intersect: false },
            scales: { x: { grid: { display: false } },
                      y: { beginAtZero: true, title: { display: true, text: `평균 오차 ${unit}` }, grid: { color: "#eef0f3" } } },
            plugins: { legend, tooltip: { ...tip, callbacks: {
              title: (it) => it.length ? `${sel.options[sel.selectedIndex].text} · ${it[0].label}` : "",
              label: (ctx) => { const x = ctx.dataset.by[DY.bins[ctx.dataIndex]];
                return x ? ` ${ctx.dataset.label}: ${f2(x.mae)}${unit} (치우침 ${sg(x.bias)}, ${x.n}건)` : null; },
              footer: () => "막대가 낮을수록 정확 · 치우침 +면 높게 예측하는 버릇",
            } } },
          },
        });
      };
      sel.addEventListener("change", draw);
      draw();
    }
  }
})();
