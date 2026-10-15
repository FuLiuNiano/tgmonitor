# 账号频道与QQ通知更新版

上传 `tg-guardian-update.zip` 到Debian服务器的 `/tmp/`，然后执行：

```bash
systemctl stop tg-guardian tg-guardian-dashboard
python3 -m zipfile -e /tmp/tg-guardian-update.zip /opt/tg-guardian
cd /opt/tg-guardian
bash update.sh
```

更新包包含已构建前端，不需要在服务器安装Node或重新构建。
更新不会包含或覆盖 `.env`、`config.json`、`data/` 或虚拟环境。

首次登录前，在 `.env` 填写真实 `TG_API_ID`、`TG_API_HASH` 和 `TG_PHONE`。
有值不等于有效：示例值123456、replace_with_api_hash和示例手机号需要替换。

```bash
cd /opt/tg-guardian
bash login.sh
```

在终端输入验证码和二步验证密码。看到“服务已启动”后按Ctrl+C，再执行：

```bash
systemctl enable --now tg-guardian
```

登录后服务扫描账号全部频道、超级群组和普通群组。前端在“账号频道”中显示列表，可以逐个打开监控、填写关键词、设置签到时间和要发送的消息。编辑后点“保存到服务器”即自动加载，无需导出配置。新增频道每5分钟同步。

普通成员通常不能在广播频道中发消息，签到请选择允许账号发言的群组。消息发送成功只代表已发出，签到结果以目标群的回复为准。

QQ开放平台官方机器人已停止主动推送，不能用于全天候关键词私聊提醒。面板默认展示官方方式的限制说明；无需填写官方AppSecret。

如果你后续决定改用OneBot v11机器人（如NapCat），需要先登录机器人账号并开启正向HTTP服务。在面板切换到OneBot，填写HTTP接口地址和接收通知的QQ号，并开启通知。机器人和你通常需要已互加好友。当前更新包不安装或登录QQ机器人。

机器人访问令牌只放服务器 `.env`：

```dotenv
QQ_BOT_TOKEN=你的机器人访问令牌
```

修改令牌后执行 `systemctl restart tg-guardian tg-guardian-dashboard`，再点面板“发送QQ测试消息”。机器人不需要访问令牌时可留空。QQ投递失败会持久化排队补发，最多自动重试5次。

本地打开面板：

```bash
ssh -L 8080:127.0.0.1:8080 root@YOUR_SERVER_IP
```

浏览器访问 `http://127.0.0.1:8080`。面板显示真实后台心跳；尚未登录时会显示“未连接”，不会用演示在线状态。
