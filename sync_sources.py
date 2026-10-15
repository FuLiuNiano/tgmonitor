"""Copy reviewed source and a fresh frontend build into a separate runtime directory."""
import argparse
import os
import shutil
import tempfile
from pathlib import Path

from check_privacy import audit


def sync(source, target):
    source = Path(source).resolve()
    target = Path(target).resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError('源码目录与运行目录必须相互独立')
    names, findings = audit(source)
    if findings:
        raise ValueError('源码隐私检查失败；先运行check_privacy.py查看文件名和问题类型')
    build = source / 'frontend' / 'dist'
    if not (build / 'index.html').is_file():
        raise ValueError('前端尚未构建')
    paths = [source / name for name in names]
    paths += [path for path in build.rglob('*') if path.is_file()]
    # Complete all path validation before writing anything into the runtime directory.
    for path in paths:
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('源码包含指向目录外的链接')
        if destination.is_symlink() or not destination.resolve().is_relative_to(target):
            raise ValueError('运行目录包含指向目录外的链接')
    target.mkdir(parents=True, exist_ok=True)
    for path in paths:
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.deploy-', dir=destination.parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(path.read_bytes())
            shutil.copymode(path, temporary)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return len(paths)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', default='/opt/tg-guardian')
    args = parser.parse_args()
    count = sync(Path(__file__).resolve().parent, args.target)
    print(f'已同步{count}个源码和构建文件；实际配置、会话和数据库保持原样。')
