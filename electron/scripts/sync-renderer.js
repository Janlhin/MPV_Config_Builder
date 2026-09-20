/* renderer/ 里的页面是**从 webui/static/ 复制过来的**，不要手改。
 *
 * 为什么这么做：那 9 个页面是浏览器版与 Electron 版**共用**的同一份文件。
 * 如果在 electron/renderer/ 里再存一份副本，迟早两边不一致 ——
 * 而我的实机验证脚本（check_topnav / check_stdio_ui）测的是 webui/static 那份，
 * 于是会出现「测试全绿，发出去的却是另一套」。
 *
 * 运行 `npm run sync` 重新复制（`npm run dist` 也会先跑它）。
 * 与源文件的一致性由 tools/check_electron.py 检查。
 */
const fs = require('node:fs');
const path = require('node:path');

// ⚠ 这个脚本自己在 electron/scripts/ 下，所以只退一层到 electron/
const SRC = path.resolve(__dirname, '..', '..', 'webui', 'static');
const DST = path.resolve(__dirname, '..', 'renderer');

function copyDir(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const s = path.join(from, entry.name);
    const d = path.join(to, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

function main() {
  if (!fs.existsSync(SRC)) {
    console.error(`找不到前端源目录：${SRC}`);
    process.exit(1);
  }
  fs.rmSync(DST, { recursive: true, force: true });
  copyDir(SRC, DST);
  const n = fs.readdirSync(DST).length;
  console.log(`已同步前端：${SRC}  ->  ${DST}（${n} 个文件）`);
}

main();
