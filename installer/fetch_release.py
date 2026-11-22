"""Puts the latest BO2 Requiem release's Nintendo Switch and Switch 2 executables next to the installer page:
<out>/t6zm.nro, t6mp.nro, t6game.nro (Switch), <out>/switch2/t6zm.nro, t6mp.nro, t6gameSW2.nro (Switch 2) and
release.json ({tag, name, published, files, switch2}: files are the Switch's, switch2 the Switch 2's).

    python fetch_release.py --out web/release [--repo HDErick/BO2-Requiem-NX] [--force]

The page offers "Nintendo Switch" and "Nintendo Switch 2" with these files. They are served from the page's own origin
because a browser cannot read GitHub's release downloads from another site. Needs the GitHub CLI
(`gh`, signed in, or GH_TOKEN in a workflow). The release's .zip assets are used: bo2requiem.zip holds
switch/t6game/*.nro and bo2requiem-Switch2.zip holds switch/t6gameSW2/*.nro. Both consoles' games are named
t6zm.nro and t6mp.nro, so the folder inside the zip decides whose they are (without one, the zip's name). Loose
.nro assets count as the Switch's, except t6gameSW2.nro. Nothing is downloaded again when the release is the one
already there.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

NROS = {'switch': ('t6zm.nro', 't6mp.nro', 't6game.nro'), 'switch2': ('t6zm.nro', 't6mp.nro', 't6gameSW2.nro')}
FOLDERS = {'switch': '', 'switch2': 'switch2'}   # inside <out>


def whose(path, zip_name=''):
    """(console, file name) of an asset or a file inside a zip asset, or None."""
    parts = path.replace('\\', '/').split('/')
    folders, name = [p.lower() for p in parts[:-1]], parts[-1].lower()
    if 't6gamesw2' in folders or name == 't6gamesw2.nro':
        console = 'switch2'
    elif 't6game' in folders:
        console = 'switch'
    else:
        console = 'switch2' if re.search(r'switch ?[-_]?2|sw2', zip_name.lower()) else 'switch'
    for known in NROS[console]:
        if known.lower() == name:
            return console, known
    return None


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
        if old.get('tag') == info['tagName'] and 'switch2' in old and all(
                (out / FOLDERS[c] / f['name']).is_file() for c, k in (('switch', 'files'), ('switch2', 'switch2')) for f in old[k]):
            print('release %s already in %s' % (info['tagName'], out))
            return old
    with tempfile.TemporaryDirectory() as tmp:
        gh('release', 'download', '--repo', repo, '--dir', tmp, '--pattern', '*.zip', '--pattern', '*.nro')
        found = {}
        for asset in sorted(Path(tmp).iterdir()):
            if asset.suffix.lower() == '.nro':
                key = whose(asset.name)
                if key:
                    found[key] = asset.read_bytes()
            elif asset.suffix.lower() == '.zip':
                with zipfile.ZipFile(asset) as z:
                    for item in z.infolist():
                        key = whose(item.filename, asset.stem)
                        if key and key not in found:
                            found[key] = z.read(item)
    if not found:
        sys.exit('the latest release of %s has no t6zm/t6mp .nro' % repo)
    if out.exists():
        shutil.rmtree(out)
    lists = {}
    for console, names in NROS.items():
        lists[console] = []
        for name in names:
            if (console, name) in found:
                path = out / FOLDERS[console] / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(found[console, name])
                lists[console].append({'name': name, 'size': len(found[console, name])})
    data = {'tag': info['tagName'], 'name': info.get('name') or info['tagName'], 'published': info.get('publishedAt'),
            'files': lists['switch'], 'switch2': lists['switch2']}
    out.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=1), encoding='utf-8')
    for console, files in lists.items():
        print('release %s, %s: %s' % (data['tag'], console, ', '.join('%s (%d bytes)' % (f['name'], f['size']) for f in files) or 'none'))
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
