"""Exercise the real EXE in an isolated directory, including repair/uninstall."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def run(command, timeout=240):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result


def check(result, description):
    if result.returncode:
        raise RuntimeError(f'{description}: exit {result.returncode}\n{result.stderr[-3000:]}\n{result.stdout[-3000:]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-wordcraft', type=Path, help='Also test reuse of this installed CLI.')
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    installer = ROOT / f'dist/Normokontrol-{version}-windows-x64-setup.exe'
    manifest = json.loads((ROOT / 'installer/dependencies.json').read_text())
    archive = ROOT / 'build/downloads' / manifest['wordcraft']['filename']
    work = ROOT / 'build' / ('smoke-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    work.mkdir(parents=True)
    target = work / 'installed'
    summary = {'work': str(work), 'checks': []}

    def install(extra, name):
        log = work / (name + '.log')
        print(name, flush=True)
        result = run([installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                      f'/DIR={target}', f'/LOG={log}', *extra])
        check(result, f'{name}; log {log}')
        report = json.loads((target / 'install-report.json').read_text(encoding='utf-8'))
        assert report['ok'] and report['data']['ready'], report
        summary['checks'].append(name)

    def uninstall(name):
        result = run([target / 'uninstall/unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES',
                      '/NORESTART', f'/LOG={work / (name + ".log")}'])
        check(result, name)
        assert not (target / 'runtime/python.exe').exists()
        assert not (target / 'wordcraft').exists()
        summary['checks'].append(name)

    install([f'/WORDCRAFTARCHIVE={archive}'], 'offline-install')
    dependencies = json.loads((target / '.normokontrol-dependencies.json').read_text(encoding='utf-8'))
    assert dependencies['wordcraft_managed'] is True
    assert Path(dependencies['wordcraft_cli']).is_relative_to(target)
    interpreter = target / 'runtime/python.exe'
    reply = run([interpreter, target / 'normokontrol.py', '--agent', 'doctor'])
    check(reply, 'installed doctor')
    doctor = json.loads(reply.stdout)
    assert doctor['ok'] and doctor['data']['ready'], doctor
    (work / 'doctor.json').write_text(reply.stdout, encoding='utf-8')
    request = work / 'create.json'
    request.write_text(json.dumps({'out': str(target / 'user-results'),
                                  'metadata': {'title': 'Installer smoke test'}}), encoding='utf-8')
    reply = run([interpreter, target / 'normokontrol.py', '--agent', 'create_document', '--request', request])
    check(reply, 'installed document creation')
    created = json.loads(reply.stdout)
    assert created['ok'], created
    assert all(Path(p).is_file() for p in created['data']['artifacts'].values())
    (work / 'create-result.json').write_text(reply.stdout, encoding='utf-8')
    summary['checks'].append('real-docx-pdf-roundtrip')
    settings = target / '.normokontrol-settings.json'
    settings.write_text('{"remember": true, "details": {"author": "Smoke Test"}}', encoding='utf-8')
    settings_before = settings.read_bytes()
    # No archive and no network download: the previously bundled component must
    # be detected independently and reused while the private runtime is repaired.
    install([], 'repair-reuse-private-wordcraft')
    assert settings.read_bytes() == settings_before
    assert 'Reusing Wordcraft:' in (work / 'repair-reuse-private-wordcraft.log').read_text(encoding='utf-8-sig')
    uninstall('uninstall-private-components')
    assert settings.read_bytes() == settings_before
    assert (target / 'user-results/report.json').is_file()
    summary['checks'].append('settings-and-results-preserved')
    if args.external_wordcraft:
        external = args.external_wordcraft.resolve()
        assert external.is_file()
        install([f'/WORDCRAFTCLI={external}'], 'reuse-external-wordcraft')
        dependencies = json.loads((target / '.normokontrol-dependencies.json').read_text(encoding='utf-8'))
        assert dependencies['wordcraft_managed'] is False
        assert Path(dependencies['wordcraft_cli']) == external
        assert not (target / 'wordcraft').exists()
        uninstall('uninstall-keeps-external-wordcraft')
        assert external.is_file()
    bad_archive = work / 'wrong.zip'
    bad_archive.write_bytes(b'Not the official Wordcraft archive')
    rejected_target = work / 'must-not-install'
    reply = run([installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                 f'/DIR={rejected_target}', f'/WORDCRAFTARCHIVE={bad_archive}',
                 f'/LOG={work / "rejected-archive.log"}'])
    assert reply.returncode != 0
    assert not (rejected_target / 'runtime').exists()
    summary['checks'].append('wrong-sha256-rejected-before-install')
    (work / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
