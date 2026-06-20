#!/bin/bash

sudo cp /etc/hosts /etc/hosts.bak

if [ $# -le 1 ]; then
	echo "Usage $0 <vulnbox-ip> <nop-ip>"
else
	echo "$1 vulnbox" | sudo tee -a /etc/hosts
	echo "$2 vulnbox_nop" | sudo tee -a /etc/hosts
fi