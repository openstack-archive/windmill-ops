=====================
ansible-role-iptables
=====================

Ansible role to manage iptables

* License: Apache License, Version 2.0
* Documentation: https://ansible-role-iptables.readthedocs.org
* Source: https://git.openstack.org/cgit/openstack/ansible-role-iptables
* Bugs: https://bugs.launchpad.net/ansible-role-iptables

Description
-----------

iptables is a command line utility for configuring Linux kernel
firewall.

Requirements
------------

Packages
~~~~~~~~

Package repository index files should be up to date before using this role, we
do not manage them.

Role Variables
--------------

Dependencies
------------

Example Playbook
----------------

.. code-block:: yaml

    - name: Install iptables
      hosts: all
      roles:
        - ansible-role-iptables
