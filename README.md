# TG Monitor / MOMO 频道守护

Telegram 个人账号频道监控、逐频道关键词提醒和定时消息签到，配套 React 配置面板与 OneBot v11 QQ 通知适配。

## 功能

- 自动列出账号加入的频道、超级群组和普通群组。
- 逐个选择关键词监控对象，配置关键词、签到消息和每日时间。
- 监听新消息及编辑消息，去重并限制重复提醒频率。
- 网页保存到服务器，后台自动加载配置。
- 关键词命中后通知 Telegram；也可通过已登录的 OneBot v11 QQ 机器人发送私聊提醒。
- QQ 投递失败持久化排队，最多自动重试五次。
- 面板显示真实后台心跳，默认仅监听服务器本机地址。

普通成员需要拥有发言权限才能在对应会话中发送签到消息。发送完成不代表目标机器人已确认签到，结果以对方回复为准。

## Debian 12 安装

需要 Python 3.11+、venv、Node.js 20+、npm 与 systemd。以下命令在服务器 root 终端执行：

```bash
git clone https://github.com/FuLiuNiano/tgmonitor.git /opt/tgmonitor-src
cd /opt/tgmonitor-src
bash deploy_from_git.sh
```

源码保存在 `/opt/tgmonitor-src`，实际配置、会话和运行环境单独保存在 `/opt/tg-guardian`。已有旧版安装时，也使用上述命令；部署脚本只同步白名单源码和新构建前端，保留已有实际配置与登录数据。

部署会先运行隐私检查和测试、构建前端，再更新运行目录并检查面板API。尚未登录的Telegram后台不会自动启动。

编辑本机生成的 `.env`，填写 Telegram API ID、API Hash 和手机号。API 凭据可从 [my.telegram.org](https://my.telegram.org) 获取。所有真实值只保存在自己的服务器。

```bash
nano /opt/tg-guardian/.env
bash /opt/tg-guardian/login.sh
```

在终端输入验证码和二步验证密码。看到服务启动后按 Ctrl+C，再启用后台和面板：

```bash
systemctl enable --now tg-guardian tg-guardian-dashboard
```

账号登录后自动生成频道列表。新增频道约五分钟内同步；网页保存规则后约二十秒加载。

## 访问面板

在本地电脑运行，替换服务器地址：

```bash
ssh -L 8080:127.0.0.1:8080 root@YOUR_SERVER_IP
```

打开 `http://127.0.0.1:8080`。配置 API 没有公网身份认证，应保持本机监听并通过 SSH 隧道访问。

## QQ 通知

使用普通 QQ 小号登录 NapCat 或其他 OneBot v11 实现。小号与接收提醒的账号先互加好友。在面板选择 OneBot，填写机器人 HTTP 地址与接收提醒的 QQ 号。

可选安装脚本：

```bash
cd /opt/tg-guardian
bash install_napcat.sh
```

脚本从 NapCat 项目维护的安装器下载软件，以独立用户运行，并将管理面板及消息接口绑定本机地址。令牌随机生成，不提交仓库。详细步骤见 [NAPCAT_GUIDE.md](NAPCAT_GUIDE.md)。

官方 QQ 开放平台机器人的主动推送存在平台限制，当前项目不实现官方机器人的全天候主动私聊提醒。参考 [官方消息文档](https://github.com/tencent-connect/bot-docs/blob/main/docs/develop/api-v2/server-inter/message/send-receive/send.md)。

## 从GitHub更新

```bash
cd /opt/tgmonitor-src
git pull --ff-only
bash deploy_from_git.sh
```

不要在源码仓库内填写实际密钥。构建或测试失败时，部署脚本会在停止旧服务之前退出。服务器安装与扫码登录需要可写权限及交互式终端；本地测试通过不代表已完成真实账号验证。

## 隐私与发布

仓库仅包含白名单列出的源码、示例配置和测试。示例 API 凭据为空，频道列表与接收 QQ 号也为空。

不上传实际 `.env`、`config.json`、Telegram 会话、数据库、频道目录、日志、二维码、备份或安装包。`data/` 和这些文件类型已被忽略。安装脚本只接触部署机器上的配置；本仓库不包含个人服务器地址。

上传前检查：

```bash
python check_privacy.py
python -m unittest discover -s tests -v
cd frontend
npm ci
npm run build
```

检查脚本对发布清单中的文件执行文件名、网络地址和常见凭据扫描。它能发现常见误提交，不代表正式安全审计。

NapCat 是第三方 QQ 自动化工具，使用者需自行评估账号和软件风险。仅用于你有权访问且允许自动化的会话。
