#!/bin/bash
ansible-playbook entrypoint.yml  -c local 
echo "Sleeping awaiting action!"
/bin/sleep infinity
