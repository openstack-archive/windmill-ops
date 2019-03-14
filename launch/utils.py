# Copyright (C) 2011-2012 OpenStack LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
#
# See the License for the specific language governing permissions and
# limitations under the License.

import errno
import socket
import time

import paramiko

from sshclient import SSHClient


def iterate_timeout(max_seconds, purpose):
    start = time.time()
    count = 0
    while (time.time() < start + max_seconds):
        count += 1
        yield count
        time.sleep(2)
    raise Exception("Timeout waiting for %s" % purpose)


def nodescan(ip, port=22, timeout=60):
    '''
    Scan the IP address for public SSH keys.

    Keys are returned formatted as: "<type> <base64_string>"
    '''
    addrinfo = socket.getaddrinfo(ip, port)[0]
    family = addrinfo[0]
    sockaddr = addrinfo[4]

    ret = None
    key = None
    for count in iterate_timeout(
            timeout, "connection to %s on port %s" % (ip, port)):
        sock = None
        t = None
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect(sockaddr)
            t = paramiko.transport.Transport(sock)
            t._preferred_keys = ['ssh-ed25519']
            t.start_client(timeout=timeout)
            key = t.get_remote_server_key()
            break
        except socket.error as e:
            if e.errno not in [errno.ECONNREFUSED, errno.EHOSTUNREACH, None]:
                log.exception(
                    'Exception connecting to %s on port %s:' % (ip, port))
        except Exception as e:
            log.exception("ssh-keyscan failure: %s", e)
        finally:
            try:
                if t:
                    t.close()
            except Exception as e:
                log.exception('Exception closing paramiko: %s', e)
            try:
                if sock:
                    sock.close()
            except Exception as e:
                log.exception('Exception closing socket: %s', e)

    if key:
        ret = key.get_base64()

    return ret


def ssh_connect(ip, username, connect_kwargs={}, timeout=60):
    # HPcloud may return errno 111 for about 30 seconds after adding the IP
    for count in iterate_timeout(timeout, "ssh access"):
        try:
            client = SSHClient(ip, username, **connect_kwargs)
            break
        except socket.error as e:
            print("While testing ssh access:", e)
            time.sleep(5)
        except paramiko.ssh_exception.AuthenticationException:
            return None

    ret, out = client.ssh("echo access okay")
    if "access okay" in out:
        return client
    return None
