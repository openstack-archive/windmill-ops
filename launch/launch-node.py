#!/usr/bin/env python

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

import argparse
import os
import shutil
import sys
import tempfile
import time
import traceback

import ansible_runner
import openstack
import paramiko

import utils

SCRIPT_DIR = os.path.abspath(os.path.dirname(sys.argv[0]))

try:
    # This unactionable warning does not need to be printed over and over.
    import requests.packages.urllib3
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass


class AnsibleRunner(object):
    def __init__(self, keep=False):
        self.keep = keep
        self.root = tempfile.mkdtemp()
        # env directory
        self.env_root = os.path.join(self.root, 'env')
        os.makedirs(self.env_root)
        self.ssh_key = os.path.join(self.env_root, 'ssh_key')
        # inventory directory
        self.inventory_root = os.path.join(self.root, 'inventory')
        shutil.copytree(
            os.path.expanduser('~/.config/windmill/ansible'),
            self.inventory_root)
        self.hosts = os.path.join(self.inventory_root, 'hosts')

    def __enter__(self):
        return self

    def __exit__(self, etype, value, tb):
        if not self.keep:
            shutil.rmtree(self.root)


def bootstrap_server(server, key, name, group, keep, timeout):
    ip = server.public_v4
    ssh_kwargs = dict(pkey=key)
    ansible_user = None

    print("--- Running initial configuration on host %s ---" % ip)
    for username in ['ubuntu', 'centos']:
        ssh_client = utils.ssh_connect(
            ip, username, ssh_kwargs, timeout=timeout)
        if ssh_client:
            ansible_user = username
            break

    if not ssh_client:
        raise Exception("Unable to log in via SSH")

    with AnsibleRunner(keep) as runner:
        with open(runner.ssh_key, 'w') as key_file:
            key.write_private_key(key_file)
        os.chmod(runner.ssh_key, 0o600)

        with open(runner.hosts, 'w') as inventory_file:
            inventory_file.write(
                "[{group}]\n{host} ansible_host={ip} "\
                "ansible_user={user}".format(
                    group=group,host=name, ip=server.interface_ip,
                    user=ansible_user))

        project_dir = os.path.join(
            SCRIPT_DIR, '..', 'playbooks', 'bootstrap-ansible')

        roles_path = os.path.join(
            SCRIPT_DIR, '..', 'playbooks', 'roles')

        r = ansible_runner.run(
            private_data_dir=runner.root, playbook='site.yaml',
            project_dir=project_dir, roles_path=[roles_path])

        if r.rc:
            raise Exception("Ansible runner failed")


def build_server(cloud, name, group, image, flavor,
                 volume, keep, network, boot_from_volume, config_drive,
                 mount_path, fs_label, availability_zone, environment,
                 volume_size, timeout):
    key = None
    server = None

    create_kwargs = dict(image=image, flavor=flavor, name=name,
                         reuse_ips=False, wait=True,
                         boot_from_volume=boot_from_volume,
                         volume_size=volume_size,
                         network=network,
                         config_drive=config_drive,
                         timeout=timeout)

    if availability_zone:
        create_kwargs['availability_zone'] = availability_zone

    if volume:
        create_kwargs['volumes'] = [volume]

    key_name = 'launch-%i' % (time.time())
    key = paramiko.RSAKey.generate(2048)
    public_key = key.get_name() + ' ' + key.get_base64()
    cloud.create_keypair(key_name, public_key)
    create_kwargs['key_name'] = key_name

    try:
        server = cloud.create_server(**create_kwargs)
    except Exception:
        try:
            cloud.delete_keypair(key_name)
        except Exception:
            print("Exception encountered deleting keypair:")
            traceback.print_exc()
        raise

    try:
        cloud.delete_keypair(key_name)

        server = cloud.get_openstack_vars(server)

        bootstrap_server(server, key, name, group, keep, timeout)

    except Exception:
        print("****")
        print("Server %s failed to build!" % (server.id))
        try:
            if keep:
                print("Keeping as requested")
                print(
                    "Run to delete -> openstack server delete %s" % server.id)
            else:
                cloud.delete_server(server.id, delete_ips=True)
        except Exception:
            print("Exception encountered deleting server:")
            traceback.print_exc()
        print("The original exception follows:")
        print("****")
        # Raise the important exception that started this
        raise

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="server name")
    parser.add_argument("group", help="server group")
    parser.add_argument("--cloud", dest="cloud", required=True,
                        help="cloud name")
    parser.add_argument("--region", dest="region",
                        help="cloud region")
    parser.add_argument("--flavor", dest="flavor", default='1GB',
                        help="name (or substring) of flavor")
    parser.add_argument("--image", dest="image",
                        default="Ubuntu 18.04 LTS (Bionic Beaver) (PVHVM)",
                        help="image name")
    parser.add_argument("--environment", dest="environment",
                        help="Puppet environment to use",
                        default=None)
    parser.add_argument("--volume", dest="volume",
                        help="UUID of volume to attach to the new server.",
                        default=None)
    parser.add_argument("--mount-path", dest="mount_path",
                        help="Path to mount cinder volume at.",
                        default=None)
    parser.add_argument("--fs-label", dest="fs_label",
                        help="FS label to use when mounting cinder volume.",
                        default=None)
    parser.add_argument("--boot-from-volume", dest="boot_from_volume",
                        help="Create a boot volume for the server and use it.",
                        action='store_true',
                        default=False)
    parser.add_argument("--volume-size", dest="volume_size",
                        help="Size of volume (GB) for --boot-from-volume",
                        default="50")
    parser.add_argument("--keep", dest="keep",
                        help="Don't clean up or delete the server on error.",
                        action='store_true',
                        default=False)
    parser.add_argument("--verbose", dest="verbose", default=False,
                        action='store_true',
                        help="Be verbose about logging cloud actions")
    parser.add_argument("--network", dest="network", default=None,
                        help="network label to attach instance to")
    parser.add_argument("--config-drive", dest="config_drive",
                        help="Boot with config_drive attached.",
                        action='store_true',
                        default=False)
    parser.add_argument("--timeout", dest="timeout",
                        help="Increase timeouts (default 600s)",
                        type=int, default=600)
    parser.add_argument("--az", dest="availability_zone", default=None,
                        help="AZ to boot in.")
    options = parser.parse_args()

    openstack.enable_logging(debug=options.verbose)

    cloud_kwargs = None
    if options.region:
        cloud_kwargs['region_name'] = options.region
    cloud = openstack.connect(cloud=options.cloud)

    flavor = cloud.get_flavor(options.flavor)
    if flavor:
        print("Found flavor", flavor.name)
    else:
        print("Unable to find matching flavor; flavor list:")
        for i in cloud.list_flavors():
            print(i.name)
        sys.exit(1)

    image = cloud.get_image_exclude(options.image, 'deprecated')
    if image:
        print("Found image", image.name)
    else:
        print("Unable to find matching image; image list:")
        for i in cloud.list_images():
            print(i.name)
        sys.exit(1)

    server = build_server(cloud, options.name, options.group, image, flavor,
                          options.volume, options.keep,
                          options.network, options.boot_from_volume,
                          options.config_drive,
                          options.mount_path, options.fs_label,
                          options.availability_zone,
                          options.environment, options.volume_size,
                          options.timeout)

    print('UUID=%s\nIPV4=%s\nIPV6=%s\n' % (
        server.id, server.public_v4, server.public_v6))


if __name__ == '__main__':
    main()
