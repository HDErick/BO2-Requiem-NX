"""Puts the latest BO2 Requiem release's Nintendo Switch executables next to the installer page:
<out>/t6zm.nro, t6mp.nro, t6game.nro and release.json ({tag, name, published, files}).

    python fetch_release.py --out web/release [--repo HDErick/BO2-Requiem-NX] [--force]

The page offers "Nintendo Switch" with these files. They are served from the page's own origin
because a browser cannot read GitHub's release downloads from another site. Needs the GitHub CLI
(`gh`, signed in, or GH_TOKEN in a workflow). The release's .nro assets, and .nro files inside its
.zip assets (bo2requiem.zip holds switch/t6game/*.nro), are used. Nothing is downloaded again when
the release is the one already there.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

NROS = ('t6zm.nro', 't6mp.nro', 't6game.nro')


def gh(*args):
    r = subprocess.run(['gh', *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('gh %s failed: %s' % (args[0] + ' ' + args[1], (r.stderr or r.stdout).strip()[-400:]))
    return r.stdout


def fetch(repo, out, force=False):
    out = Path(out)
    info = json.loads(gh('release', 'view', '--repo', repo, '--json', 'tagName,name,publishedAt'))
    manifest = out / 'release.json'
    if not force and manifest.is_file():
        old = json.loads(manifest.read_text(encoding='utf-8'))
        if old.get('tag') == info['tagName'] and all((out / f['name']).is_file() for f in old.get('files', [])):
            print('release %s already in %s' % (info['tagName'], out))
            return old
    with tempfile.TemporaryDirectory() as tmp:
        gh('release', 'download', '--repo', repo, '--dir', tmp, '--pattern', '*.zip', '--pattern', '*.nro')
        found = {}
        for asset in sorted(Path(tmp).iterdir()):
            if asset.name.lower() in NROS:
                found[asset.name.lower()] = asset.read_bytes()
            elif asset.suffix.lower() == '.zip':
                with zipfile.ZipFile(asset) as z:
                    for item in z.infolist():
                        name = item.filename.rsplit('/', 1)[-1].lower()
                        if name in NROS and name not in found:
                            found[name] = z.read(item)
    if not found:
        sys.exit('the latest release of %s has no t6zm/t6mp/t6game .nro' % repo)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = []
    for name in NROS:
        if name in found:
            (out / name).write_bytes(found[name])
            files.append({'name': name, 'size': len(found[name])})
    data = {'tag': info['tagName'], 'name': info.get('name') or info['tagName'], 'published': info.get('publishedAt'), 'files': files}
    manifest.write_text(json.dumps(data, indent=1), encoding='utf-8')
    print('release %s: %s' % (data['tag'], ', '.join('%s (%d bytes)' % (f['name'], f['size']) for f in files)))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY') or 'HDErick/BO2-Requiem-NX')
    parser.add_argument('--out', required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    fetch(args.repo, args.out, args.force)


if __name__ == '__main__':
    main()
