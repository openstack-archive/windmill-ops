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

import socket
import subprocess
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
    '''

    key = None
    output = None
    for count in iterate_timeout(
            timeout, "connection to %s on port %s" % (ip, port)):

        try:
            output = subprocess.check_output(
                ['ssh-keyscan', '-t', 'ed25519', '-p', str(port), str(ip)])
            if output:
                break
        except Exception as e:
            log.exception("ssh-keyscan failure: %s", e)

    key = output.split()[2].decode('utf8')

    return key


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
