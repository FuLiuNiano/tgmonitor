"""Configure a dedicated NapCat installation and the guardian without exposing tokens."""
import argparse
import json
import os
import secrets
import shutil
from pathlib import Path


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + '.before-momo')
        if not backup.exists():
            shutil.copy2(path, backup)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.chmod(0o600)
    os.replace(temp, path)


def configure(napcat_dir, app_dir):
    config_dir = Path(napcat_dir)
    app = Path(app_dir)
    env_path = app / '.env'
    app_config = app / 'config.json'
    if not env_path.is_file() or not app_config.is_file():
        raise ValueError('先安装TG助手，缺少.env或config.json')
    # Dedicated credential: no QQ/TG login credentials are copied into the panel.
    token_file = app / 'data' / 'napcat-api-token'
    if token_file.exists():
        token = token_file.read_text().strip()
    else:
        token = secrets.token_urlsafe(32)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token, encoding='utf-8')
    token_file.chmod(0o600)
    webui_path = config_dir / 'webui.json'
    webui = json.loads(webui_path.read_text(encoding='utf-8')) if webui_path.exists() else {}
    webui.update({'host': '127.0.0.1', 'port': 6099, 'token': webui.get('token') if webui.get('token') and webui['token'] != 'napcat' else secrets.token_urlsafe(32)})
    save_json(webui_path, webui)
    paths = {config_dir / 'onebot11.json', *config_dir.glob('onebot11_*.json')}
    for path in paths:
        payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        payload['network'] = {
            'httpServers': [{'name': 'momo-local', 'enable': True, 'host': '127.0.0.1', 'port': 5700, 'token': token, 'enableCors': False, 'enableWebsocket': False, 'messagePostFormat': 'array', 'debug': False}],
            'httpClients': [], 'websocketServers': [], 'websocketClients': [],
        }
        save_json(path, payload)
    lines = env_path.read_text(encoding='utf-8').splitlines()
    if not env_path.with_suffix('.env.before-napcat').exists():
        shutil.copy2(env_path, env_path.with_suffix('.env.before-napcat'))
    lines = [line for line in lines if not line.strip().startswith(('QQ_BOT_TOKEN=', 'export QQ_BOT_TOKEN='))]
    env_path.write_text('\n'.join(lines) + '\nQQ_BOT_TOKEN=' + token + '\n', encoding='utf-8')
    env_path.chmod(0o600)
    config = json.loads(app_config.read_text(encoding='utf-8'))
    qq = dict(config.get('qq', {}))
    # Only enable delivery after the recipient is selected in the dashboard.
    qq.update({'provider': 'onebot', 'api_base': 'http://127.0.0.1:5700', 'enabled': False})
    qq.setdefault('user_id', '')
    config['qq'] = qq
    save_json(app_config, config)
    print('已配置本机接口和随机令牌。QQ通知保持关闭，请在面板填主号并测试后开启。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--napcat-config', required=True)
    parser.add_argument('--app', default='/opt/tg-guardian')
    args = parser.parse_args()
    configure(args.napcat_config, args.app)
