"""Small ordered Python API tape. Linux/libseccomp required for offline replay."""
import argparse
import base64
import builtins
import ctypes
import errno
import hashlib
import io
import json
import os
import random
import sys
import time
import urllib.request
import urllib.response
from email.message import Message

RAW_OPEN = builtins.open


def encode(value):
    if isinstance(value, bytes):
        return {'bytes': base64.b64encode(value).decode('ascii')}
    if isinstance(value, os.PathLike):
        return encode(os.fspath(value))
    if isinstance(value, tuple):
        return {'tuple': [encode(x) for x in value]}
    if isinstance(value, list):
        return [encode(x) for x in value]
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f'unsupported tape value: {type(value).__name__}')


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'bytes'}:
            return base64.b64decode(value['bytes'])
        if set(value) == {'tuple'}:
            return tuple(decode(x) for x in value['tuple'])
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(x) for x in value]
    return value


def offline():
    """Fail closed if a kernel filter cannot be installed; inherited by children."""
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise RuntimeError('seccomp_init failed')
    try:
        for name in ('socket', 'socketpair', 'connect', 'accept', 'accept4', 'bind',
                     'listen', 'sendto', 'sendmsg', 'sendmmsg', 'recvfrom', 'recvmsg',
                     'recvmmsg', 'io_uring_setup', 'socketcall'):
            nr = lib.seccomp_syscall_resolve_name(name.encode())
            if nr >= 0 and lib.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, nr, 0):
                raise RuntimeError(f'seccomp rule failed: {name}')
        if lib.seccomp_load(ctx):
            raise RuntimeError('seccomp_load failed')
    finally:
        lib.seccomp_release(ctx)


class Divergence(RuntimeError):
    pass


class Tape:
    def __init__(self, mode, events):
        self.mode, self.events, self.pos = mode, events, 0
        self.busy = False
        self.patches = []

    def call(self, name, args, kwargs, fn):
        if self.busy:
            return fn()
        key = [name, encode(args), encode(kwargs)]
        if self.mode == 'replay':
            if self.pos == len(self.events):
                raise Divergence(f'extra call at event {self.pos}: {name}')
            event = self.events[self.pos]
            if event['call'] != key:
                raise Divergence(f'event {self.pos}: expected {event["call"]!r}, got {key!r}')
            self.pos += 1
            if 'error' in event:
                kind, args, filename = decode(event['error'])
                cls = getattr(builtins, kind)
                if issubclass(cls, OSError) and filename is not None:
                    raise cls(*args, filename)
                raise cls(*args)
            return decode(event['value'])
        self.busy = True
        try:
            value = fn()
            self.events.append({'call': key, 'value': encode(value)})
            return value
        except Exception as exc:
            if type(exc).__module__ != 'builtins':
                raise  # custom exception reconstruction is intentionally unsupported
            self.events.append({'call': key, 'error': encode((type(exc).__name__, exc.args,
                                                           getattr(exc, 'filename', None)))})
            raise
        finally:
            self.busy = False

    def patch(self, obj, name, replacement):
        self.patches.append((obj, name, getattr(obj, name)))
        setattr(obj, name, replacement)

    def wrap(self, obj, name):
        original = getattr(obj, name)
        def wrapped(*args, **kwargs):
            return self.call(f'{obj.__name__}.{name}', args, kwargs, lambda: original(*args, **kwargs))
        self.patch(obj, name, wrapped)

    def install(self):
        for name in ('time', 'time_ns', 'monotonic', 'monotonic_ns', 'perf_counter',
                     'perf_counter_ns', 'sleep'):
            self.wrap(time, name)
        for name in ('random', 'randint', 'randrange', 'getrandbits', 'uniform', 'choice', 'randbytes'):
            self.wrap(random, name)
        for name in ('urandom', 'listdir', 'mkdir', 'remove', 'unlink', 'rename'):
            self.wrap(os, name)
        counter = 0
        def opened(*args, **kwargs):
            nonlocal counter
            if self.busy:
                return RAW_OPEN(*args, **kwargs)
            handle = None
            def create():
                nonlocal handle
                handle = RAW_OPEN(*args, **kwargs)
                return None
            self.call('open', args, kwargs, create)
            counter += 1
            return File(self, counter, handle)
        self.patch(builtins, 'open', opened)
        self.patch(io, 'open', opened)
        original = urllib.request.urlopen
        def urlopen(url, data=None, timeout=None):
            if self.busy:
                return original(url, data=data, timeout=timeout)
            if not isinstance(url, str):
                raise TypeError('prototype supports URL strings only')
            def fetch():
                with original(url, data=data, timeout=timeout) as response:
                    return (response.read(), list(response.headers.items()), response.geturl(), response.status)
            body, headers, final_url, status = self.call('urlopen', (url, data, timeout), {}, fetch)
            message = Message()
            for key, value in headers:
                message[key] = value
            return urllib.response.addinfourl(io.BytesIO(body), message, final_url, status)
        self.patch(urllib.request, 'urlopen', urlopen)

    def restore(self):
        for obj, name, original in reversed(self.patches):
            setattr(obj, name, original)


class File:
    """Only this explicit stream-method subset is represented on the tape."""
    def __init__(self, tape, number, handle):
        self.tape, self.number, self.handle = tape, number, handle

    def __getattr__(self, name):
        if name not in ('read', 'readline', 'readlines', 'write', 'writelines', 'seek',
                        'tell', 'truncate', 'flush', 'close'):
            raise AttributeError(f'unsupported file attribute: {name}')
        def method(*args, **kwargs):
            return self.tape.call(f'file{self.number}.{name}', args, kwargs,
                                  lambda: getattr(self.handle, name)(*args, **kwargs))
        return method

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['record', 'replay', 'plain'])
    parser.add_argument('tape')
    parser.add_argument('script')
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    with RAW_OPEN(args.script, 'rb') as f:
        source = f.read()
    metadata = {'version': 1, 'sha256': hashlib.sha256(source).hexdigest(),
                'python': sys.version, 'argv': [args.script, *args.args]}
    events = []
    if args.mode == 'replay':
        with RAW_OPEN(args.tape) as f:
            saved = json.load(f)
        if saved['metadata'] != metadata:
            raise Divergence('source, interpreter, or argv changed')
        events = saved['events']
        offline()
    tape = Tape(args.mode, events)
    code = compile(source, args.script, 'exec')
    sys.argv = [args.script, *args.args]
    sys.path.insert(0, os.path.dirname(os.path.abspath(args.script)))
    if args.mode != 'plain':
        tape.install()
    try:
        exec(code, {'__name__': '__main__', '__file__': args.script, '__package__': None})
        if args.mode == 'replay' and tape.pos != len(events):
            raise Divergence(f'{len(events) - tape.pos} unconsumed events')
    finally:
        tape.restore()
    if args.mode == 'record':
        with RAW_OPEN(args.tape, 'w') as f:
            json.dump({'metadata': metadata, 'events': events}, f)


if __name__ == '__main__':
    main()
