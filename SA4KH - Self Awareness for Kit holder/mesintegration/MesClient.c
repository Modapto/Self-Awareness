//
// MODAPTO Simple MES Client (Reference Code)
// First version 25-05-2024
// Added Self Awareness Notifications support 29-03-2025
// Added support to Self Awareness Insertion/Extraction events 29-03-2025
// Added batch retrieval support for events using GETREGBLOCK
//

#include <winsock2.h>
#include <stdio.h>
#include <time.h>

int main(int argc, char* argv[])
{
	WSADATA wsaData;
	SOCKET clientSock;
	struct sockaddr_in serverAddr;
	int serverLen = sizeof (serverAddr);

	unsigned short Port = 30003;
	unsigned char SendBuf[3096], RecvBuf[3096];
	int BufLen = 3096;
	int i, j, n, ret, key = -1, RegAddr = -1, RegNo = -1;
	__int64 RegValLo = -1, RegValHi = -1;

	int RfIdStationId, KhType, KhUniqueId;
    time_t clk;
    int eventCount = 0;


	// initialize Winsock
	WSAStartup (MAKEWORD(2,2), &wsaData);

	if (argc!=2)
	{
		printf ("Usage: %s IP_ADDR[ex. 172.31.1.147]\n", argv[0]);

		// clean up and exit
		printf ("Exiting...\n");
		WSACleanup();
		return 0;
	}

	// create the client's socket to send and receive datagrams
	if ((clientSock = socket(AF_INET, SOCK_DGRAM, 0)) < 0)
	{
		// socket opening error...
		printf ("%s: ERROR - opening socket...\n", argv[0]);

		// clean up and exit
		WSACleanup();

		return 0;
	}

	// build the server's Internet Address
	// (in this example the server is "127.0.0.1" for local host and
	// "172.31.1.147" for the KRS System Controller (in the Kuka Robot Cabinet)
	memset((char *) &serverAddr, 0, sizeof(serverAddr));
	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = inet_addr(argv[1]);
	serverAddr.sin_port = htons(Port);

	while ((key < 1) || (key > 5)) {
		printf ("Select the function to test [1 - PING, 2 - GETREG, 3 - GETREGBLOCK, 4 - SETREG, 5 - SETREGBLOCK --> ");
		scanf ("%d", &key);
	}

	if (key == 1)
	{
		// Ping function
		SendBuf[0] = 0x01;

		// Sending "0x01" to the Server
		if ((n = sendto (clientSock, (char *)SendBuf, 1, 0, (SOCKADDR *) &serverAddr, serverLen)) <= 0)
		{
			// sendto error...
			printf ("%s: ERROR - 0x01 sendto error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}

		printf ("Sent \"0x01\" to the server ...\n");

		// Waiting for the reply from the Server
		if ((n = recvfrom (clientSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *) &serverAddr, &serverLen)) <= 0)
		{
			// recvfrom error...
			printf ("%s: ERROR - 0x01 recvfrom error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		RecvBuf[n] = 0;

		// Checking the proper reply from the Server
		if (RecvBuf[0] != 0xff)
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x01 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		else printf ("Received \"0xff\" from the server ...\n");
	}
	else if (key == 2)
	{
		// GetReg function
		while ((RegAddr < 0) || (RegAddr > 65535)) {
			printf ("Input RegAddr [0..65535] --> ");
			scanf ("%d", &RegAddr);
		}

   		SendBuf[0] = 0x02;
   		SendBuf[1] = RegAddr & 0x00ff;
   		SendBuf[2] = RegAddr >> 8;

		// Sending "0x02" + RegAddr to the Server
		if ((n = sendto (clientSock, (char *)SendBuf, 3, 0, (SOCKADDR *) &serverAddr, serverLen)) <= 0)
		{
			// sendto error...
			printf ("%s: ERROR - 0x02 sendto error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		printf ("Sent \"0x02\" + %d to the server ...\n", RegAddr);

		// Waiting for the reply from the Server
		if ((n = recvfrom (clientSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *) &serverAddr, &serverLen)) <= 0)
		{
			// recvfrom error...
			printf ("%s: ERROR - 0x02 recvfrom error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		RecvBuf[n] = 0;

		// Checking the proper reply from the Server
		if ((n < 2) || (RecvBuf[0] != 0xfe))
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x02 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		else printf ("Received \"0xfe\" + %d char from the server ...\n", n-1);

		// Printout Data received from the Server
		if (RegAddr==3090)
        {
            // UC3090. Case1.
            printf("UC3090 Triggered (Saw Notification)...\n");
            if (RecvBuf[1]==0)
            {
                printf("No Saw Quality Issues to notify...\n");
            }
            else
            {
                printf("Saw Quality Issue detected, of type --> %d\n", RecvBuf[1]);
                ret = sscanf ((char *)&RecvBuf[2], "%d;%I64d;%d;%d", &RfIdStationId, &clk, &KhType, &KhUniqueId);
                if (ret!=4)
                {
                    // error handling
                    printf ("Wrong reply from the server, 0x02 closing ...\n");

                    // close the socket
                    closesocket (clientSock);

                    // clean up and exit
                    WSACleanup();

                    return 0;
                }

                printf("RFID Station ID                 --> %d\n", RfIdStationId);
                printf("Timestamp                       --> %s", ctime(&clk));
                printf("KH Type                         --> %d\n", KhType);
                printf("KH Unique ID                    --> %012d\n", KhUniqueId);
            }
        }
        else if (RegAddr==3091)
        {
            // UC3090. Case2.
            printf("UC3090 Triggered (Saw Insertion/Extraction Event)...\n");
            if (RecvBuf[1]==0)
            {
                printf("No Saw Insertion/Extraction Events to notify...\n");
            }
            else
            {
                printf("Saw Event detected, of type --> %d ", RecvBuf[1]);
                if (RecvBuf[1]==1) printf("(Insertion)\n");
                else if (RecvBuf[1]==2) printf("(Extraction)\n");
                else printf("(Unknown)\n");

                ret = sscanf ((char *)&RecvBuf[2], "%d;%I64d;%d;%d", &RfIdStationId, &clk, &KhType, &KhUniqueId);
                if (ret!=4)
                {
                    // error handling
                    printf ("Wrong reply from the server, 0x02 closing ...\n");

                    // close the socket
                    closesocket (clientSock);

                    // clean up and exit
                    WSACleanup();

                    return 0;
                }

                printf("RFID Station ID                 --> %d\n", RfIdStationId);
                printf("Timestamp                       --> %s", ctime(&clk));
                printf("KH Type                         --> %d\n", KhType);
                printf("KH Unique ID                    --> %012d\n", KhUniqueId);
            }
        }
        else
        {
            for (i=1;i<9;i++)
                printf ("%2.2x ", RecvBuf[i]);
        }
		printf ("\n");
	}
	else if (key == 3)
	{
		// GetRegBlock function
		while ((RegAddr <0) || (RegAddr > 65535)) {
			printf ("Input RegAddr [0..65535] --> ");
			scanf ("%d", &RegAddr);
		}
		while ((RegNo <0) || (RegNo > 255)) {
			printf ("Input RegNo [0..255] --> ");
			scanf ("%d", &RegNo);
		}

   		SendBuf[0] = 0x03;
   		SendBuf[1] = RegAddr & 0x00ff;
   		SendBuf[2] = RegAddr >> 8;
   		SendBuf[3] = RegNo;

		// Sending "0x03" + RegAddr + RegNo to the Server
		if ((n = sendto (clientSock, (char *)SendBuf, 4, 0, (SOCKADDR *) &serverAddr, serverLen)) <= 0)
		{
			// sendto error...
			printf ("%s: ERROR - 0x03 sendto error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		printf ("Sent \"0x03\" + %d + %d to the server ...\n", RegAddr, RegNo);

		// Waiting for the reply from the Server
		if ((n = recvfrom (clientSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *) &serverAddr, &serverLen)) <= 0)
		{
			// recvfrom error...
			printf ("%s: ERROR - 0x03 recvfrom error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		RecvBuf[n] = 0;

		// Checking the proper reply from the Server
		if ((RecvBuf[0] != 0xfd))
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x03 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		else printf ("Received \"0xfd\" from the server ...\n");

		// Special handling for event batch retrieval
		if (RegAddr == 3091)
		{
			// Parse multiple Saw Insertion/Extraction events
			int eventCount = 0;
			int pos = 1;
			int eventDataSize = 74; // 1 byte for event type + 73 bytes for event data

			while (pos < n && eventCount < RegNo)
			{
				if (RecvBuf[pos] == 0)
				{
					// No more events
					printf("No more Saw Insertion/Extraction Events to notify...\n");
					break;
				}

				printf("\n--- Event #%d ---\n", eventCount + 1);
				printf("Saw Event detected, of type --> %d ", RecvBuf[pos]);
				if (RecvBuf[pos] == 1) printf("(Insertion)\n");
				else if (RecvBuf[pos] == 2) printf("(Extraction)\n");
				else printf("(Unknown)\n");

				// Parse event data
				ret = sscanf((char *)&RecvBuf[pos + 1], "%d;%I64d;%d;%d", &RfIdStationId, &clk, &KhType, &KhUniqueId);
				if (ret == 4)
				{
					printf("RFID Station ID                 --> %d\n", RfIdStationId);
					printf("Timestamp                       --> %s", ctime(&clk));
					printf("KH Type                         --> %d\n", KhType);
					printf("KH Unique ID                    --> %012d\n", KhUniqueId);
				}
				else
				{
					printf("Error parsing event data\n");
				}

				pos += eventDataSize;
				eventCount++;
			}

			printf("\nTotal Events Retrieved: %d\n", eventCount);
		}
		else if (RegAddr == 3090)
		{
			// Parse multiple Saw Notifications
			int notifCount = 0;
			int pos = 1;
			int notifDataSize = 74; // 1 byte for notification type + 73 bytes for notification data

			while (pos < n && notifCount < RegNo)
			{
				if (RecvBuf[pos] == 0)
				{
					// No more notifications
					printf("No more Saw Quality Issues to notify...\n");
					break;
				}

				printf("\n--- Notification #%d ---\n", notifCount + 1);
				printf("Saw Quality Issue detected, of type --> %d\n", RecvBuf[pos]);

				// Parse notification data
				ret = sscanf((char *)&RecvBuf[pos + 1], "%d;%I64d;%d;%d", &RfIdStationId, &clk, &KhType, &KhUniqueId);
				if (ret == 4)
				{
					printf("RFID Station ID                 --> %d\n", RfIdStationId);
					printf("Timestamp                       --> %s", ctime(&clk));
					printf("KH Type                         --> %d\n", KhType);
					printf("KH Unique ID                    --> %012d\n", KhUniqueId);
				}
				else
				{
					printf("Error parsing notification data\n");
				}

				pos += notifDataSize;
				notifCount++;
			}

			printf("\nTotal Notifications Retrieved: %d\n", notifCount);
		}
		else
		{
			// Standard register block handling
			if ((n != 1+8*RegNo))
			{
				// error handling
				printf ("Received wrong reply from the server, 0x03 closing ...\n");

				// close the socket
				closesocket (clientSock);

				// clean up and exit
				WSACleanup();

				return 0;
			}

			// Printout Data received from the Server
			for (i=1;i<1+8*RegNo;i++)
				printf ("%2.2x ", RecvBuf[i]);
			printf ("\n");
		}
	}
	else if (key == 4)
	{
		// SetReg function
		while ((RegAddr <0) || (RegAddr > 65535)) {
			printf ("Input RegAddr [0..65535] --> ");
			scanf ("%d", &RegAddr);
		}
		while ((RegValLo < 0) || (RegValLo > 4294967295)) {
			printf ("Input RegValLo [0..2^32-1] --> ");
			scanf ("%I64d", &RegValLo);
		}
		while ((RegValHi < 0) || (RegValHi > 4294967295)) {
			printf ("Input RegValHi [0..2^32-1] --> ");
			scanf ("%I64d", &RegValHi);
		}

   		SendBuf[0] = 0x04;
   		SendBuf[1] = RegAddr & 0x00ff;
   		SendBuf[2] = RegAddr >> 8;
   		SendBuf[3] = RegValLo & 0x000000ff;
   		SendBuf[4] = (RegValLo >> 8) & 0x000000ff;
   		SendBuf[5] = (RegValLo >> 16) & 0x000000ff;
   		SendBuf[6] = (RegValLo >> 24) & 0x000000ff;
   		SendBuf[7] = RegValHi & 0x000000ff;
   		SendBuf[8] = (RegValHi >> 8) & 0x000000ff;
   		SendBuf[9] = (RegValHi >> 16) & 0x000000ff;
   		SendBuf[10] = (RegValHi >> 24) & 0x000000ff;

		// Sending "0x04" + RegAddr + RegVal to the Server
		if ((n = sendto (clientSock, (char *)SendBuf, 11, 0, (SOCKADDR *) &serverAddr, serverLen)) <= 0)
		{
			// sendto error...
			printf ("%s: ERROR - 0x04 sendto error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		printf ("Sent \"0x04\" + %d + %I64d (L) + %I64d (H) to the server ...\n", RegAddr, RegValLo, RegValHi);

		// Waiting for the reply from the Server
		if ((n = recvfrom (clientSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *) &serverAddr, &serverLen)) <= 0)
		{
			// recvfrom error...
			printf ("%s: ERROR - 0x04 recvfrom error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		RecvBuf[n] = 0;

		// Checking the proper reply from the Server
		if ((n!=2) || (RecvBuf[0] != 0xfc))
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x04 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();
			return 0;
		}
		else printf ("Received \"0xfc\" from the server ...\n");

		if (RecvBuf[1] == 0x00) printf ("Received \"0x00\" (no errors in the put operation) from the server ...\n");
		else if (RecvBuf[1] == 0xff) printf ("Received \"0xff\" (errors in the put operation) from the server ...\n");
		else
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x04 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();
			return 0;
		}
	}
	else if (key == 5)
	{
		// SetRegBlock function
		while ((RegAddr <0) || (RegAddr > 65535)) {
			printf ("Input RegAddr [0..65535] --> ");
			scanf ("%d", &RegAddr);
		}
   		SendBuf[0] = 0x05;
   		SendBuf[1] = RegAddr & 0x00ff;
   		SendBuf[2] = RegAddr >> 8;

		while ((RegNo <0) || (RegNo > 255)) {
			printf ("Input RegNo [0..255] --> ");
			scanf ("%d", &RegNo);
		}
   		SendBuf[3] = RegNo;

   		for (i=0, j=0; i<RegNo; i++, j+=8)
		{
			while ((RegValLo < 0) || (RegValLo > 4294967295)) {
				printf ("Input RegValLo[%d] [0..2^32-1] --> ", i+1);
				scanf ("%I64d", &RegValLo);
			}
			while ((RegValHi < 0) || (RegValHi > 4294967295)) {
				printf ("Input RegValHi[%d] [0..2^32-1] --> ", i+1);
				scanf ("%I64d", &RegValHi);
			}
			SendBuf[4+j] = RegValLo & 0x000000ff;
			SendBuf[5+j] = (RegValLo >> 8) & 0x000000ff;
			SendBuf[6+j] = (RegValLo >> 16) & 0x000000ff;
			SendBuf[7+j] = (RegValLo >> 24) & 0x000000ff;
			SendBuf[8+j] = RegValHi & 0x000000ff;
			SendBuf[9+j] = (RegValHi >> 8) & 0x000000ff;
			SendBuf[10+j] = (RegValHi >> 16) & 0x000000ff;
			SendBuf[11+j] = (RegValHi >> 24) & 0x000000ff;

			RegValLo = -1;
			RegValHi = -1;
		}

		// Sending "0x05" + RegAddr + RegNo + RegVals payload to the Server
		if ((n = sendto (clientSock, (char *)SendBuf, 4 + RegNo*8, 0, (SOCKADDR *) &serverAddr, serverLen)) <= 0)
		{
			// sendto error...
			printf ("%s: ERROR - 0x05 sendto error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		printf ("Sent \"0x05\" + RegAddr %d + RegNo %d + Registers payload to the server ...\n", RegAddr, RegNo);

		// Waiting for the reply from the Server
		if ((n = recvfrom (clientSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *) &serverAddr, &serverLen)) <= 0)
		{
			// recvfrom error...
			printf ("%s: ERROR - 0x05 recvfrom error...\n", argv[0]);

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		RecvBuf[n] = 0;

		// Checking the proper reply from the Server
		if ((n!=2) || (RecvBuf[0] != 0xfb))
		{
			 // error handling
	   		printf ("Received wrong reply from the server, 0x05 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();
			return 0;
		}
		else printf ("Received \"0xfb\" from the server ...\n");

		if (RecvBuf[1] == 0x00) printf ("Received \"0x00\" (no errors in the put operation) from the server ...\n");
		else if (RecvBuf[1] == 0xff) printf ("Received \"0xff\" (errors in the put operation) from the server ...\n");
		else
		{
			// error handling
	   		printf ("Received wrong reply from the server, 0x05 closing ...\n");

			// close the socket
			closesocket (clientSock);

			// clean up and exit
			WSACleanup();
			return 0;
		}
	}

	//Here, we don't send the "Server Killing" final Datagram...
	//SendBuf[0] = 0;
	//BufLen = 1;
	//printf ("\nSending a final Datagram to the server...\n");
	//sendto (clientSock, (char *)SendBuf, BufLen, 0, (SOCKADDR *) &serverAddr, sizeof (serverAddr));

	// MODAPTO API Client finished sending, close the socket
	printf ("Finished sending. Closing socket...\n");
	closesocket (clientSock);

	// clean up and exit
	printf ("Exiting...\n");
	WSACleanup();

	return 0;
}