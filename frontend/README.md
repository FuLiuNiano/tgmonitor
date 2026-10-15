# Momo Guardian 配置面板

React + Vite 前端，通过同源 `/api/config`、`/api/channels`、`/api/status` 接口连接 `dashboard_server.py`。频道来自Telegram账号真实会话，保存规则后后台自动加载。

本地开发使用 `npm install`、`npm run build` 构建，然后从项目根目录运行：

```bash
python dashboard_server.py --directory frontend/dist --config config.json --data-dir data --port 8080
```

浏览器访问 `http://127.0.0.1:8080`。在服务器上通过SSH隧道访问同一地址。

页面支持选择账号频道、逐频道关键词和消息签到、真实状态、QQ通知方式及OneBot测试消息。QQ官方机器人已停止主动推送，面板会显示限制。

生产更新请使用根目录的 `UPDATE_GUIDE.md`，更新包内含已构建的前端，无需服务器重新编译。
