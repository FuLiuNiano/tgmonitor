# 小号QQ通知安装包

上传 `tg-guardian-napcat.zip` 到Debian服务器的 `/tmp/`，在root终端执行：

```bash
systemctl stop tg-guardian tg-guardian-dashboard
python3 -m zipfile -e /tmp/tg-guardian-napcat.zip /opt/tg-guardian
cd /opt/tg-guardian
bash update.sh
bash install_napcat.sh
```

程序将使用独立用户momonapcat运行QQ小号，安装在 `/opt/napcat-user`。管理面板6099和消息接口5700只监听127.0.0.1，并生成随机令牌。TG配置与登录数据保留；QQ通知保持关闭，待测试通过再打开。

在本地电脑打开一个终端，保持SSH连接：

```bash
ssh -L 6099:127.0.0.1:6099 -L 8080:127.0.0.1:8080 root@YOUR_SERVER_IP
```

在服务器root终端读取NapCat管理面板登录令牌（不要发到聊天）：

```bash
python3 -c 'import json; print(json.load(open("/opt/napcat-user/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/webui.json"))["token"])'
```

浏览器打开 `http://127.0.0.1:6099/webui`，输入令牌，然后用小号手机QQ扫码确认登录。如NapCat登录后刷新令牌，用上述命令再读一次。

小号和接收通知的主号先互加好友。登录后，在 `http://127.0.0.1:8080` 的QQ提醒页面填写主号QQ号（机器人类型OneBot、接口地址已配置）。点“发送QQ测试消息”，确认主号收到，再打开QQ提醒并保存。手机QQ通知设置决定是否响铃和弹窗。

TG仍需要真实API凭据和首次登录。未完成时执行 `bash /opt/tg-guardian/login.sh`，成功后启动 `systemctl enable --now tg-guardian`。

诊断：

```bash
systemctl status momo-napcat --no-pager
ss -lntp | grep -E ':(6099|5700)\b'
free -h
```

NapCat日志可能包含二维码和管理令牌，不要整段发到公开聊天。

如小号登录后接口没有出现，在WebUI的网络配置中确认HTTP服务端地址为127.0.0.1、端口5700。需要重新应用本机配置时，停止momo-napcat后运行 `napcat_setup.py --napcat-config ...`，再启动服务；脚本会关闭QQ提醒以便重新测试。

安装脚本适用于Debian 12，请在服务器root终端执行。已完成脚本语法和配置测试，实际登录、网络和内存占用请在部署后验证。

官方安装参考：https://napneko.github.io/guide/boot/Shell
