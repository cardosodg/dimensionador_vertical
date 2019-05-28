#!/bin/bash

sudo apt update

sudo apt install python-dev python-pip libvirt-dev -y

sudo pip install virtualenv

virtualenv --system-site-package -p /usr/bin/python venv

