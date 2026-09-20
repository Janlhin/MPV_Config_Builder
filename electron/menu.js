/* 原生菜单。做成 Electron 的菜单栏，而不是在页面里再画一套。
 *
 * 原则：**只放真能用的东西**。菜单里塞一堆点不动的占位项，比没有菜单更让人困惑。
 * 所以这里的每一项都对应一个真实动作。
 */
const { Menu } = require('electron');

function buildMenu({ isDev, onReload, onToggleDevTools, onAbout,
                     onOpenDocs, onOpenUserData }) {
  const template = [
    {
      label: '文件(&F)',
      submenu: [
        {
          label: '重新载入界面',
          accelerator: 'F5',
          click: onReload
        },
        { type: 'separator' },
        {
          label: '打开用户数据目录',
          // 预设、设置、安装清单就放在那儿 —— 排查问题时第一个要看的地方
          click: onOpenUserData
        },
        { type: 'separator' },
        { role: 'quit', label: '退出' }
      ]
    },
    {
      label: '编辑(&E)',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' }
      ]
    },
    {
      label: '视图(&V)',
      submenu: [
        { role: 'resetZoom', label: '实际大小' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
        ...(isDev ? [
          { type: 'separator' },
          { label: '开发者工具', accelerator: 'F12', click: onToggleDevTools }
        ] : [])
      ]
    },
    {
      label: '帮助(&H)',
      submenu: [
        { label: '项目主页', click: onOpenDocs },
        { type: 'separator' },
        { label: '关于', click: onAbout }
      ]
    }
  ];

  return Menu.buildFromTemplate(template);
}

module.exports = { buildMenu };
