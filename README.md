# TG Monitor / MOMO 频道守护

Telegram 个人账号频道监控、逐频道关键词提醒和定时消息签到，配套 React 配置面板、轻量QQ/163邮箱SMTP通知及可选OneBot通知。

## 功能

- 自动列出账号加入的频道、超级群组和普通群组。
- 逐个选择关键词监控对象，配置关键词、签到消息和每日时间。
- 监听新消息及编辑消息，去重并限制重复提醒频率。
- 网页保存到服务器，后台自动加载配置。
- 关键词命中后通知 Telegram；推荐通过QQ或163邮箱向另一个邮箱发送提醒，无需NapCat。
- 邮件或OneBot投递失败持久化排队，最多自动重试五次。更换通知配置后丢弃旧目的地待发消息。
- 面板显示真实后台心跳，默认仅监听服务器本机地址。

普通成员需要拥有发言权限才能在对应会话中发送签到消息。发送完成不代表目标机器人已确认签到，结果以对方回复为准。

### 关键词规则

每行是一组条件，同行用空格分隔的词必须全部出现在同一条消息中；不同的行互相独立，满足任意一行就提醒。忽略英文字母大小写，词序和间距不限，仍按正文子串匹配，不跨消息累计。同一条消息满足多行也只发送一次提醒，并继续遵守去重与冷却设置。

例如：

```text
优惠 补货
限时 折扣
通知
```

表示“优惠和补货”或“限时和折扣”或“通知”。单独出现“优惠”不会满足第一行。连续空格、制表符和全角空格都可以分隔同行条件。

升级保留已保存的关键词。原先包含空格的整句会按新的同行AND规则处理，不再要求完整短语连续出现。签到回复/按钮筛选仍保留旧的短语匹配方式，不受这次监控规则变更影响。

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

## 邮箱通知（轻量推荐）

不需要安装NapCat或QQ客户端，使用Python标准库发送邮件，适合小内存服务器。

1. 在发件QQ或163邮箱的设置中开启SMTP服务并生成授权码（不是登录密码）。163邮箱可在网页“设置 → POP3/SMTP/IMAP”中操作。参考 [163授权码操作说明](https://consumer.huawei.com/cn/support/content/zh-cn15872099/)。
2. 编辑服务器 `/opt/tg-guardian/.env`，新增或填写 `SMTP_USERNAME`（完整发件邮箱地址）与 `SMTP_AUTH_CODE`（该邮箱的授权码）。不要把真实值写进源码或发到聊天中。
3. 在服务器重启服务以加载环境变量：

```bash
systemctl restart tg-guardian-dashboard
# 仅在Telegram已经完成登录并启用后台时执行下一行：
systemctl restart tg-guardian
```

4. 面板“邮箱与通知”选择“邮箱发邮件”，再选发件服务“QQ邮箱”或“163邮箱”，填写接收提醒的邮箱，开启外部通知并保存，点击“发送测试邮件”。发件服务必须与.env中的发件账号对应。切换服务会先关闭通知，更新.env并重启服务后再重新开启。升级保留旧配置，不会擅自开启通知或覆盖你的旧接入方式。

QQ使用 `smtp.qq.com:465`，163使用 `smtp.163.com:465`，均启用TLS证书验证和20秒超时。发件账号及授权码只从环境变量读取，不会返回前端或写入待发数据库。收件地址和提醒正文保存在服务器私有配置/数据库，不提交GitHub。收到SMTP成功响应不等于最终送达，注意收件箱、垃圾箱、邮件延迟及频率限制；响铃和弹窗需要在收件设备上设置。

旧数据库字段与内部接口沿用 `qq` 名称以兼容升级；`qq.provider=email`、`qq.recipient` 为邮箱模式，`qq.mail_service` 可选 `qq` 或 `163`，未填写时兼容旧版默认QQ。旧版OneBot仍可选择，但与邮箱模式不同时发送。没有安装过NapCat就无需执行任何卸载命令。

## QQ 通知（可选，不适合资源紧张时额外安装）

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
