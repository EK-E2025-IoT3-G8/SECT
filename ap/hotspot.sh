sudo nmcli con add con-name hotspot ifname wlan0 type wifi ssid "accesspoint ap";
sleep 5;
sudo nmcli con modify hotspot wifi-sec.key-mgmt wpa-psk;
sleep 5;
sudo nmcli con modify hotspot wifi-sec.psk "accesspointsarehellaniceforwirelesscommunications";
sleep 5;
sudo nmcli con modify hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared