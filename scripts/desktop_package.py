"""Write a Desktop Entry with an embedded, checksummed shell installer."""
import base64
import hashlib


def write_desktop(shell, launcher_source):
    shell_digest = hashlib.sha256(shell.read_bytes()).hexdigest()
    launcher = launcher_source.read_text(encoding='utf-8').replace('SHELL_SHA256', shell_digest)
    encoded_launcher = base64.b64encode(launcher.encode('utf-8')).decode('ascii')
    # %k is a standalone argument; arbitrary download paths never enter Python code.
    command = f'''python3 -c "import base64;exec(base64.b64decode('{encoded_launcher}'))" %k'''
    header = '\n'.join((
        '[Desktop Entry]',
        'Type=Application',
        'Version=1.0',
        'Name=Install Miaozi Deck',
        'Name[zh_CN]=安装喵子 Deck',
        'Name[zh_TW]=安裝喵子 Deck',
        'Comment=Install Miaozi Deck with all required resources included',
        'Comment[zh_CN]=双击安装喵子 Deck，已包含全部安装资源',
        'Icon=system-software-install',
        'Terminal=true',
        'StartupNotify=false',
        'Categories=Utility;',
        'Exec=' + command,
        '',
        '# __MIAOZI_SHELL_BASE64__',
        '',
    ))
    desktop = shell.with_suffix('.desktop')
    with desktop.open('xb') as output, shell.open('rb') as stream:
        output.write(header.encode('utf-8'))
        while chunk := stream.read(3072):
            output.write(b'# ' + base64.b64encode(chunk) + b'\n')
        output.write(b'# __MIAOZI_SHELL_END__\n')
    desktop.chmod(0o755)
    desktop.with_name(desktop.name + '.sha256').write_text(
        hashlib.sha256(desktop.read_bytes()).hexdigest() + '  ' + desktop.name + '\n', encoding='utf-8')
    return desktop
