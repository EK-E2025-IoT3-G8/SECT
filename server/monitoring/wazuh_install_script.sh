apt-get install gnupg apt-transport-https -y
curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import && chmod 644 /usr/share/keyrings/wazuh.gpg
echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" | tee -a /etc/apt/sources.list.d/wazuh.list
apt-get update -y
WAZUH_MANAGER="192.168.30.2" apt-get install wazuh-agent -y
systemctl daemon-reload
systemctl enable wazuh-agent
systemctl start wazuh-agent