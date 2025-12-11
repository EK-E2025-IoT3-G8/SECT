```text
Device	Interface	Vlan tag	Forbindelse	      IP	           				NetID	           Subnetmasker
R1						
	    G0/0		            Server            203.0.113.1	   				203.0.113.0/29	    225.255.255.248
	    G0/1		            R2	              10.0.0.1	       				10.0.0.0/30	        255.255.255.252
R2						
	    G0/1		            R1	              10.0.0.2.1      				0.0.0.0/30	        255.255.255.252
		G0/1.20		20	        Switch(admin)	  192.168.20.1	   				192.168.20.0/29	    255.255.255.248
		G0/1.30		30	        Switch(Device)	  192.168.30.1	   				192.168.30.0/29	    255.255.255.248
	    G0/1.40		40          Switch(user)	  192.168.40.1	   				192.168.40.0/27	    255.255.255.224
SWITCH						
	G1/0/1	       TRUNK
	G1/0/2-8       VLAN 20
	G1/0/9-12      VLAN 30
	G1/0/13-24	   VLAN 40		

DHCP SCOPE							
	vlan 40			                             192.168.40.2-192.168.40.30		
						
Devices
	AP							Ethernet		192.168.40.2/27										255.255.255.224				
	Server		               	Ethernet	    203.0.113.2/29	                        			255.255.255.248	
	Device		               	Ethernet   		192.168.30.2/29										255.255.255.248
	Static Mgmt (Martini)		Ethernet		192.168.20.2/29	                        			255.255.255.248
	Mgmt 	#2					Ethernet		192.168.20.3/29										255.255.255.248
	Mgmt 	#n					Ethernet		192.168.20.n+1/29									255.255.255.248
	Guest 	#2		            skal indsættes	192.168.40.3/27	                        			255.255.255.224	
	Guest 	#3		            skal indsættes	192.168.40.4/27	                        			255.255.255.224	
	Guest 	#n		            skal indsættes	192.168.40.n+1/27                        			255.255.255.224	
	```
