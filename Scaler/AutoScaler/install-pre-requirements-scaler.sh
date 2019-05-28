#!/bin/bash

sudo apt update

sudo apt install python-dev python-pip rabbitmq-server -y

sudo rabbitmqctl add_user orchexp22 orchexp22 && sudo rabbitmqctl set_user_tags orchexp22 administrator && sudo rabbitmqctl set_permissions -p / orchexp22 ".*" ".*" ".*"
