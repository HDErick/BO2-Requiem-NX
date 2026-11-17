"""Serves the installer page on 127.0.0.1 for local use or testing. The page is fully static: on
GitHub Pages it runs the same way.

    python serve.py [--port 8070] [--no-browser] [--no-release]

Before serving, the latest BO2 Requiem release's Switch executables are put in web/release/ (as the
Pages workflow does; needs the GitHub CLI signed in). Without them the page still installs for
Android; --no-release skips the download.
"""
import argparse
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE / 'web' if (HERE / 'web' / 'index.html').is_file() else HERE


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.js': 'text/javascript',
                      '.wasm': 'application/wasm', '.css': 'text/css', '.nro': 'application/octet-stream'}

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', type=int, default=8070)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-release', action='store_true')
    args = parser.parse_args()
    if not (WEB / 'generated' / 't6pack.wasm').is_file():
        parser.exit(1, 'generated/t6pack.wasm is missing: build it with build_web.py\n')
    if not args.no_release:
        try:
            sys.path.insert(0, str(HERE))
            import fetch_release
            fetch_release.fetch('HDErick/BO2-Requiem-NX', WEB / 'release')
        except Exception as e:   # the page still works for Android
            print('Switch executables not fetched (%s); the page offers Android only until they are.' % e, flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(WEB)))
    url = 'http://127.0.0.1:%d/' % server.server_port
    print('BO2 Requiem Compressor: %s  (Chrome or Edge for "Install to folder"; Ctrl+C to quit)' % url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
