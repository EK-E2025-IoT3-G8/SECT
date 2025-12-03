sudo WAZUH_MANAGER='192.168.30.2' WAZUH_AGENT_GROUP='default' WAZUH_AGENT_NAME='$USER' dpkg -i ./wazuh-agent_4.14.1-1_amd64.deb

sudo systemctl daemon-reload 
sudo systemctl enable wazuh-agent 
sudo systemctl start wazuh-agent