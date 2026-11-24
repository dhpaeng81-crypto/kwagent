// 2주 일별 예측 대화형 그래프 (Chart.js). 자료는 페이지 안 <script id="ddata"> JSON.
(function () {
  const el = document.getElementById("ddata");
  if (!el || !window.Chart) return;
  const D = JSON.parse(el.textContent);
  const C = {
    tmax: "#d4483b", tmin: "#2f6fdb", cloud: "#5b6b7c", srad: "#e08a12",
    rain: "#2e9e6a", pop: "#2f6fdb", normal: "#9aa3ac", grid: "#eef0f3", ink: "#5b6670",
  };
  const alpha = (hex, a) => hex + Math.round(a * 255).toString(16).padStart(2, "0");
  const far = 7;  // 8일째(인덱스 7)부터 점선 = 불확실
  const dashFar = { borderDash: (c) => (c.p0DataIndex >= far ? [5, 4] : undefined) };
  const fmt = (v, d = 1) => (v == null || isNaN(v) ? "-" : (+v).toFixed(d).replace(/^-0(\.0+)?$/, "0$1"));

  Chart.defaults.font.family = "'Noto Sans KR', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = C.ink;

  const base = (yTitle, extra = {}) => ({
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "top", align: "end", labels: { boxWidth: 14, boxHeight: 2, usePointStyle: false,
        filter: (it) => !it.text.startsWith("_") } },
      tooltip: {
        backgroundColor: "rgba(24,30,38,.92)", padding: 10, titleFont: { weight: "700", size: 13 },
        bodySpacing: 4, filter: (it) => !it.dataset.label.startsWith("_"),
        callbacks: { title: (it) => it.length ? D.labels[it[0].dataIndex] + (it[0].dataIndex >= far ? "  (참고용)" : "") : "" },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 6 } },
      y: { title: { display: true, text: yTitle }, grid: { color: C.grid } },
    },
    ...extra,
  });

  // 10~90% 띠: 아래(_lo) + 위(_hi, fill '-1'), 범례·툴팁에서는 숨김
  const band = (lo, hi, color) => [
    { label: "_lo", data: lo, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, fill: false },
    { label: "_hi", data: hi, borderWidth: 0, pointRadius: 0, pointHoverRadius: 0, backgroundColor: alpha(color, 0.16), fill: "-1" },
  ];
  const line = (label, data, color, more = {}) => ({
    label, data, borderColor: color, backgroundColor: color, borderWidth: 2.5, pointRadius: 2.5,
    pointHoverRadius: 5, tension: 0.25, segment: dashFar, ...more,
  });
  const normal = (label, data, color) => ({
    label, data, borderColor: alpha(color, 0.7), borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0,
    pointHoverRadius: 0, tension: 0.3,
  });
  const col = (days, v, k) => days.map((d) => (d.vars[v] ? d.vars[v][k] : null));
  // "중앙값 (10~90%) · 평년" 형식의 툴팁 문장
  const rangeLabel = (name, days, v, unit, dig = 1) => (ctx) => {
    const x = days[ctx.dataIndex].vars[v];
    if (!x) return name + ": -";
    let s = `${name}: ${fmt(x.q50, dig)}${unit} (${fmt(x.q10, dig)}~${fmt(x.q90, dig)})`;
    if (x.normal != null) s += ` · 평년 ${fmt(x.normal, dig)}${unit}`;
    return s;
  };

  for (const [rid, R] of Object.entries(D.regions)) {
    const days = R.days;
    const L = days.map((d) => d.label);
    D.labels = days.map((d) => d.label);
    const mk = (kind, cfg) => {
      const c = document.getElementById(`c-${rid}-${kind}`);
      if (c) new Chart(c, cfg);
    };

    // 1) 기온
    mk("temp", {
      type: "line",
      data: { labels: L, datasets: [
        ...band(col(days, "tmax", "q10"), col(days, "tmax", "q90"), C.tmax),
        line("최고기온", col(days, "tmax", "q50"), C.tmax),
        ...band(col(days, "tmin", "q10"), col(days, "tmin", "q90"), C.tmin),
        line("최저기온", col(days, "tmin", "q50"), C.tmin),
        normal("평년 최고", col(days, "tmax", "normal"), C.tmax),
        normal("평년 최저", col(days, "tmin", "normal"), C.tmin),
      ] },
      options: base("°C", {}),
    });
    const tc = Chart.getChart(`c-${rid}-temp`);
    if (tc) {
      tc.options.plugins.tooltip.filter = (it) => it.dataset.label === "최고기온" || it.dataset.label === "최저기온";
      tc.options.plugins.tooltip.callbacks.label = (ctx) =>
        ctx.dataset.label === "최고기온" ? rangeLabel("최고", days, "tmax", "°C")(ctx) : rangeLabel("최저", days, "tmin", "°C")(ctx);
      tc.update();
    }

    // 2) 강수: 강수량 막대(왼쪽, mm) + 강수확률 선(오른쪽, %)
    mk("precip", {
      data: { labels: L, datasets: [
        { type: "line", label: "강수확률", data: days.map((d) => d.vars.precip ? d.vars.precip.pop * 100 : null),
          borderColor: C.pop, backgroundColor: C.pop, borderWidth: 2.5, pointRadius: 3, tension: 0.25, yAxisID: "y1",
          segment: dashFar, order: 0 },
        { type: "line", label: "평년 강수확률", data: days.map((d) => d.vars.precip && d.vars.precip.pop_normal != null ? d.vars.precip.pop_normal * 100 : null),
          borderColor: alpha(C.pop, 0.6), borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, yAxisID: "y1", order: 1 },
        { type: "bar", label: "강수량(중앙)", data: col(days, "precip", "q50"), backgroundColor: alpha(C.rain, 0.85),
          borderRadius: 3, yAxisID: "y", order: 2, barPercentage: 0.6 },
        { type: "bar", label: "많으면(90%)", data: col(days, "precip", "q90"), backgroundColor: alpha(C.rain, 0.22),
          borderRadius: 3, yAxisID: "y", order: 3, barPercentage: 0.6, grouped: false },
      ] },
      options: base("mm", {
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 6 } },
          y: { title: { display: true, text: "강수량 mm" }, beginAtZero: true, grid: { color: C.grid } },
          y1: { position: "right", min: 0, max: 100, title: { display: true, text: "강수확률 %" },
                grid: { display: false }, ticks: { stepSize: 20 } },
        },
      }),
    });
    const pc = Chart.getChart(`c-${rid}-precip`);
    if (pc) {
      pc.options.plugins.tooltip.filter = (it) => it.dataset.label === "강수확률" || it.dataset.label === "강수량(중앙)";
      pc.options.plugins.tooltip.callbacks.label = (ctx) => {
        const p = days[ctx.dataIndex].vars.precip || {};
        if (ctx.dataset.label === "강수확률")
          return `강수확률: ${fmt(p.pop * 100, 0)}%` + (p.pop_normal != null ? ` · 평년 ${fmt(p.pop_normal * 100, 0)}%` : "");
        return `강수량: ${fmt(p.q50)}mm (${fmt(p.q10)}~${fmt(p.q90)})`;
      };
      pc.options.plugins.tooltip.callbacks.afterBody = (it) => {
        const p = it.length ? days[it[0].dataIndex].vars.precip || {} : {};
        return p.p_snow != null && p.p_snow >= 0.05 ? `눈 확률: ${fmt(p.p_snow * 100, 0)}%` : "";
      };
      pc.update();
    }

    // 3) 운량 + 하늘상태
    mk("cloud", {
      type: "line",
      data: { labels: L, datasets: [
        ...band(col(days, "cloud", "q10"), col(days, "cloud", "q90"), C.cloud),
        line("운량", col(days, "cloud", "q50"), C.cloud),
        normal("평년", col(days, "cloud", "normal"), C.cloud),
      ] },
      options: base("%", { scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 6 } },
        y: { min: 0, max: 100, title: { display: true, text: "운량 %" }, grid: { color: C.grid } } } }),
    });
    const cc = Chart.getChart(`c-${rid}-cloud`);
    if (cc) {
      cc.options.plugins.tooltip.filter = (it) => it.dataset.label === "운량";
      cc.options.plugins.tooltip.callbacks.label = rangeLabel("운량", days, "cloud", "%", 0);
      cc.options.plugins.tooltip.callbacks.afterLabel = (ctx) => {
        const s = (days[ctx.dataIndex].vars.cloud || {}).sky;
        return s ? Object.entries(s).map(([k, v]) => `${k} ${fmt(v * 100, 0)}%`).join(" · ") : "";
      };
      cc.update();
    }

    // 4) 일사량
    mk("srad", {
      type: "line",
      data: { labels: L, datasets: [
        ...band(col(days, "srad", "q10"), col(days, "srad", "q90"), C.srad),
        line("일사량", col(days, "srad", "q50"), C.srad),
        normal("평년", col(days, "srad", "normal"), C.srad),
      ] },
      options: base("MJ/m²", { scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 6 } },
        y: { beginAtZero: true, title: { display: true, text: "일사량 MJ/m²" }, grid: { color: C.grid } } } }),
    });
    const sc = Chart.getChart(`c-${rid}-srad`);
    if (sc) {
      sc.options.plugins.tooltip.filter = (it) => it.dataset.label === "일사량";
      sc.options.plugins.tooltip.callbacks.label = rangeLabel("일사량", days, "srad", " MJ/m²");
      sc.update();
    }
  }
})();
