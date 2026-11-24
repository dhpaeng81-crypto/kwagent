// 아이콘 PNG 다시 만들기: node kwagent/static/mkicons.js kwagent/static  (Playwright 필요)
// node mkicons.js <static_dir> [preview.png]
const { chromium } = require('playwright'); const fs = require('fs');
const dir = process.argv[2]; const src = fs.readFileSync(dir + '/icon.svg', 'utf8');
const v = (rx, sc, mini) => { let s = src.replace('RX', rx).replace('SCALE', sc); if (mini) s = s.replace(/<g id="trend">[\s\S]*?<\/g>\s*<\/g>/, '').replace('translate(-256 -256)', 'translate(-256 -236)'); return s; };
const outs = [['apple-touch-icon.png', 180, 0, 1], ['icon-192.png', 192, 96, 1], ['icon-512.png', 512, 96, 1],
              ['icon-maskable-512.png', 512, 0, 0.78], ['favicon-32.png', 32, 96, 1.12, 1]];
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  for (const [name, size, rx, sc, mini] of outs) {
    await p.setViewportSize({ width: size, height: size });
    await p.setContent(`<html><body style="margin:0;background:transparent">${v(rx, sc, mini).replace('<svg ', `<svg width="${size}" height="${size}" `)}</body></html>`);
    await p.screenshot({ path: dir + '/' + name, omitBackground: true });
  }
  fs.writeFileSync(dir + '/favicon.svg', v(96, 1.12, 1));
  if (process.argv[3]) {  // 미리보기: 홈 화면 흉내
    await p.setViewportSize({ width: 760, height: 300 });
    const img = n => 'data:image/png;base64,' + fs.readFileSync(dir + '/' + n).toString('base64');
    await p.setContent(`<body style="margin:0;padding:30px;background:linear-gradient(#3b2f63,#0f172a);display:flex;gap:40px;align-items:center;font-family:sans-serif;color:#fff">
      <div style="text-align:center"><img src="${img('apple-touch-icon.png')}" style="width:120px;border-radius:27px"><div>기상전망</div></div>
      <div style="text-align:center"><img src="${img('icon-maskable-512.png')}" style="width:120px;border-radius:50%"><div>안드로이드(원형)</div></div>
      <div style="text-align:center"><img src="${img('apple-touch-icon.png')}" style="width:60px;border-radius:13px"><div>작게</div></div>
      <div style="text-align:center"><img src="${img('favicon-32.png')}" style="width:32px"><div>탭 아이콘</div></div></body>`);
    await p.screenshot({ path: process.argv[3] });
  }
  await b.close();
})();
