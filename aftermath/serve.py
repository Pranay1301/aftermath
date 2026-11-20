"""Local evidence viewer server with single-byte-range support for video seeking.

Read-only static files rooted in the selected project directory. Bind loopback
by default. No accounts, live executor, upload or mutation endpoint.
"""
import argparse
import functools
import http.server
import os
import re


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        self._range_remaining = None
        header = self.headers.get('Range')
        path = self.translate_path(self.path)
        if not header or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
        start, end = 0, size - 1
        valid = bool(match and (match[1] or match[2]) and size)
        if valid:
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            else:
                length = int(match[2])
                valid = length > 0
                start = max(0, size - length)
            valid = valid and 0 <= start <= end < size
        if not valid:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        try:
            source = open(path, 'rb')
        except OSError:
            self.send_error(404)
            return None
        source.seek(start)
        self._range_remaining = end - start + 1
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(self._range_remaining))
        self.end_headers()
        return source

    def copyfile(self, source, outputfile):
        if self._range_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self._range_remaining
        while remaining:
            data = source.read(min(65536, remaining))
            if not data:
                break
            outputfile.write(data)
            remaining -= len(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--directory', default='.')
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), functools.partial(Handler, directory=args.directory))
    print(f'Local viewer: http://127.0.0.1:{server.server_port}/web/eventual.html', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()