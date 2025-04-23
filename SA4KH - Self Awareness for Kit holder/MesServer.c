//
// MODAPTO Simple MES Server (Reference Code)
// First version 07-03-2025
// Added Self Awareness Notifications support 29-03-2025
// Added support to Self Awareness Insertion/Extraction events 29-03-2025
// Added batch retrieval support for events using GETREGBLOCK
//

#include <winsock2.h>
#include <stdbool.h>
#include <stdio.h>
#include <conio.h>
#include <time.h>


// Globals
// UC 3.9 Issues
int RfidStationId = 0;

#define MESSAGE_SIZE 80
#define QUEUE_SIZE 8192

typedef struct {
unsigned char data[MESSAGE_SIZE];
} MESSAGE;

typedef struct {
    MESSAGE messages[QUEUE_SIZE];
    int begin;
    int end;
    int current_load;
} QUEUE;

void init_queue(QUEUE *queue) {
    queue->begin = 0;
    queue->end = 0;
    queue->current_load = 0;
    memset(&queue->messages[0], 0, QUEUE_SIZE * sizeof(MESSAGE_SIZE));
}

bool enque(QUEUE *queue, MESSAGE *message) {
    if (queue->current_load < QUEUE_SIZE) {
        if (queue->end == QUEUE_SIZE) {
            queue->end = 0;
        }
        queue->messages[queue->end] = *message;
        queue->end++;
        queue->current_load++;
        return true;
    } else {
        return false;
    }
}

bool deque(QUEUE *queue, MESSAGE *message) {
    if (queue->current_load > 0) {
        *message = queue->messages[queue->begin];
        memset(&queue->messages[queue->begin], 0, sizeof(MESSAGE));
        queue->begin = (queue->begin + 1) % QUEUE_SIZE;
        queue->current_load--;
        return true;
    } else {
        return false;
    }
}

int main(int argc, char* argv[])
{
	WSADATA wsaData;
	SOCKET serverSock;
	struct sockaddr_in clientAddr, serverAddr;
	int clientLen = sizeof(clientAddr);
	struct timeval stTimeOut;
	fd_set stReadFDS;

	unsigned short Port = 30003;
	unsigned char SendBuf[3096], RecvBuf[3096];
	int BufLen = 3096;
	int DatagramCnt = 0;
	int i, j, n, ret, nchar, RegAddr, RegNo;
	__int64 RegValLo, RegValHi;

    QUEUE SawNotifMsgQueue, SawEventMsgQueue;
    init_queue(&SawNotifMsgQueue);
    init_queue(&SawEventMsgQueue);
    MESSAGE rec, curSawNotifMsg, curSawEventMsg;

    FILE *f1;

    curSawNotifMsg.data[0] = 0;
    curSawEventMsg.data[0] = 0;

    if (argc!=3)
    {
        printf("Usage: %s SawNotifFile.csv SawEventsFile.csv\n",argv[0]);
        return 0;
    }

    // Load Self Awareness Notification File...
    // Up to 8K Saw Notifications supported...
    if((f1 = (fopen(argv[1], "r"))) == NULL)
    {
        printf ("%s unable to access %s\n", argv[0], argv[1]);
        return 0;
    }

    i=0;
    if ((fgets((char *)RecvBuf, 1024, f1))!=NULL)
    {
        // Skip first row of the csv file (column labels)
        while ((fgets((char *)RecvBuf, MESSAGE_SIZE, f1))!=NULL)
        {
            // get all Notifications from the csv file and push them in the SawNotifMsgQueue
            strcpy ((char *)&rec.data[0], (char *)RecvBuf);
            enque(&SawNotifMsgQueue, &rec);
            i++;
        }
    }

    fclose (f1);

    if (i>=1)
    {
         printf ("%s: Imported %d Self Awareness Notifications\n", argv[0], i);

    }

    // Load Self Awareness Event File...
    // Up to 8K Saw Insertion/Extraction Events supported...
    if((f1 = (fopen(argv[2], "r"))) == NULL)
    {
        printf ("%s unable to access %s\n", argv[0], argv[2]);
        return 0;
    }

    i=0;
    if ((fgets((char *)RecvBuf, 1024, f1))!=NULL)
    {
        // Skip first row of the csv file (column labels)
        while ((fgets((char *)RecvBuf, MESSAGE_SIZE, f1))!=NULL)
        {
            // get all Events from the csv file and push them in the SawEventMsgQueue
            strcpy ((char *)&rec.data[0], (char *)RecvBuf);
            enque(&SawEventMsgQueue, &rec);
            i++;
        }
    }

    fclose (f1);

    if (i>=1)
    {
         printf ("%s: Imported %d Self Awareness Insertion/Extraction Events\n", argv[0], i);
    }

	// initialize Winsock
	WSAStartup (MAKEWORD(2,2), &wsaData);

	// create the server's socket to receive and send datagrams
	if ((serverSock = socket(AF_INET, SOCK_DGRAM, 0)) < 0)
	{
		// socket opening error...
		printf ("%s: ERROR - opening socket...\n", argv[0]);

		// clean up and exit
		WSACleanup();

		return 0;
	}

	// build the server's Internet address
	memset((char *) &serverAddr, 0, sizeof(serverAddr));
 	serverAddr.sin_family = AF_INET;
	serverAddr.sin_addr.s_addr = htonl(INADDR_ANY);
	serverAddr.sin_port = htons(Port);

	// bind: associate the parent Socket with the defined Port
	if (bind(serverSock, (SOCKADDR *) &serverAddr, sizeof(serverAddr)) < 0)
	{
		// socket binding error...
		printf ("%s: ERROR - binding socket...\n", argv[0]);

		// close the socket
		closesocket (serverSock);

		// clean up and exit
		WSACleanup();

		return 0;
	}

	// setting timeout for select in order to return immediately
	stTimeOut.tv_sec = 0;
	stTimeOut.tv_usec = 0;

	// Udp Receiving activities occur within the following loop
	for (;;)
	{
		// setting the file descriptors for the UDP socket read events...
		FD_ZERO(&stReadFDS);
		FD_SET(serverSock, &stReadFDS);

		ret = select(-1, &stReadFDS, NULL, NULL, &stTimeOut);
		if (ret == -1)
		{
			// select error...
			printf ("%s: ERROR - select unrecoverable error...\n", argv[0]);

			// close the socket
			closesocket (serverSock);

			// clean up and exit
			WSACleanup();

			return 0;
		}
		else if (ret == 0)
		{
			// timeout elapsed and no reading events pending...
			// sleeping for 40ms. and releasing the system resources...
			Sleep(40);
		}
		else
		{
			if (FD_ISSET(serverSock,&stReadFDS))
			{
				// one UDP dgm is available from Port 27015
				// processing the data by means of a non blocking
				// reading and continue the loop with another
				// iteration without waiting
				printf ("\nReceiving Datagram #%d --> ",++DatagramCnt);
				if ((n = recvfrom (serverSock, (char *)RecvBuf, BufLen, 0, (SOCKADDR *)  &clientAddr, &clientLen)) <= 0)
				{
					// recvfrom error...
					printf ("%s: ERROR - recvfrom error...\n", argv[0]);

					// close the socket
					closesocket (serverSock);

					// clean up and exit
					WSACleanup();

					return 0;
				}
				RecvBuf[n] = 0;

				// Parsing Datagrams...
				if (RecvBuf[0] == 0x01)
				{
					// 0x01 --> PING
					printf ("Received \"0x01\" from the client ...\n");

					// Sending back the "ACK"...
					SendBuf[0] = 0xff;
					if ((n = sendto (serverSock, (char *)SendBuf, 1, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
					{
						// sendto error...
						printf ("%s: ERROR - 0x01 sendto error...\n", argv[0]);

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					printf ("Sent back the ACK msg \"0xff\" to the client ...\n");
				}
				else if (RecvBuf[0] == 0x02)
				{
					// 0x02 --> GETREG
					printf ("Received \"0x02\" from the client ...\n");
					// Checking the consistency of the received number of bytes...
					if (n!=3)
					{
						// msg format error...
						printf ("Message format error 0x02...\n");

						// close the socket
						closesocket (serverSock);

						WSACleanup();
						return 0;
					}
					RegAddr = RecvBuf[1] + 256 * RecvBuf[2];
					printf ("RegAddr --> %d\n", RegAddr);

					// Important! This section of code in the server should actually fetch the register content
					// (for instance the linear axis position) and send it to the client.
					// Sending back the Register Content...

					if (RegAddr==3090)
					{
                        // REG 3090 --> Case1. Get Self Awareness Notifications for the UC 3.9, about "KHs not meeting quality requirements"
					    // Semantics:
					    // Payload[1] --> Notification Type: 0 - No fresh notifications (quality check ok from all RFID stations)
					    //                                   1 - Quality Nok (Issue of type #1)...
					    // Payload[2..3] --> RFID Station ID [6..9]
						// Payload[4..11] --> Timestamp
						// Payload[12..79] --> EPC, TID, Unique ID of the KH, etc...

						// Attempt to fetch a pending notification...
						if (curSawNotifMsg.data[0]==0)
                        {
                            // try to deque a pending notification...
                            if (deque(&SawNotifMsgQueue, &curSawNotifMsg))
                            {
                                // successful dequeueing of a pending message...
                                nchar = MESSAGE_SIZE;
                                SendBuf[0] = 0xfe;
                                SendBuf[1] = curSawNotifMsg.data[5]-'0';
                                memcpy((char *)&SendBuf[2], (char *)&curSawNotifMsg.data[7], MESSAGE_SIZE-7);
                            }
                            else
                            {
                                // unsuccessful dequeueing: the notification queue is already void...
                                nchar = 2;
                                SendBuf[0] = 0xfe;
                                SendBuf[1] = 0;
                            }
                        }
                        else
                        {
                            // a pending notification is still on hold...
                            // just deliver it without dequeueing any message...
                            nchar = MESSAGE_SIZE;
                            SendBuf[0] = 0xfe;
                            SendBuf[1] = curSawNotifMsg.data[5]-'0';
                            memcpy((char *)&SendBuf[2], (char *)&curSawNotifMsg.data[7], MESSAGE_SIZE-7);
                        }
                        printf("\n");
					}
					else if (RegAddr==3091)
                    {
                        // REG 3091 --> Case2. Get Self Awareness Insertion/Extraction Events for the UC 3.9
					    // Semantics:
					    // Payload[1] --> Self Awareness Event Type: 1 - Insertion
					    //                                           2 - Extraction
					    // Payload[2..3] --> RFID Station ID [6..9]
						// Payload[4..11] --> Timestamp
						// Payload[12..79] --> EPC, TID, Unique ID of the KH, etc...
                        // Attempt to fetch a pending event...
						if (curSawEventMsg.data[0]==0)
                        {
                            // try to deque a pending event...
                            if (deque(&SawEventMsgQueue, &curSawEventMsg))
                            {
                                // successful dequeueing of a pending message...
                                nchar = MESSAGE_SIZE;
                                SendBuf[0] = 0xfe;
                                SendBuf[1] = curSawEventMsg.data[5]-'0';
                                memcpy((char *)&SendBuf[2], (char *)&curSawEventMsg.data[7], MESSAGE_SIZE-7);
                            }
                            else
                            {
                                // unsuccessful dequeueing: the event queue is already void...
                                nchar = 2;
                                SendBuf[0] = 0xfe;
                                SendBuf[1] = 0;
                            }
                        }
                        else
                        {
                            // a pending event is still on hold...
                            // just deliver it without dequeueing any message...
                            nchar = MESSAGE_SIZE;
                            SendBuf[0] = 0xfe;
                            SendBuf[1] = curSawEventMsg.data[5]-'0';
                            memcpy((char *)&SendBuf[2], (char *)&curSawEventMsg.data[7], MESSAGE_SIZE-7);
                        }
                        printf("\n");
                    }
                    else
                    {
                        // Other UCs and registers...
                        nchar = 9;
                        SendBuf[0] = 0xfe;
                        // Dummy filling in of result register...
                        for (i=1;i<nchar;i++)
                        {
                            SendBuf[i] = i;
                        }
                    }

                    if ((n = sendto (serverSock, (char *)SendBuf, nchar, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
                    {
                        // sendto error...
                        printf ("%s: ERROR - 0x02 sendto error...\n", argv[0]);

                        // close the socket
                        closesocket (serverSock);

                        // clean up and exit
                        WSACleanup();

                        return 0;
                    }

					printf ("Sent back the msg \"0xfe\" and the content of the Register %d to the client ...\n", RegAddr);
				}
				else if (RecvBuf[0] == 0x03)
				{
					// 0x03 --> GETREGBLOCK
					printf ("Received \"0x03\" from the client ...\n");
					// Checking the consistency of the received number of bytes...
					if (n!=4)
					{
						// msg format error...
						printf ("Message format error 0x03...\n");

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					RegAddr = RecvBuf[1] + 256 * RecvBuf[2];
					printf ("RegAddr --> %d\n", RegAddr);
					RegNo = RecvBuf[3];
					printf ("RegNo --> %d\n", RegNo);

					// Special handling for event batch retrieval
					if (RegAddr == 3091)
					{
						SendBuf[0] = 0xfd;
						int nchar = 1;
						int eventsRetrieved = 0;

						MESSAGE tempEventMsg;

						// First check if there's an event currently held
						if (curSawEventMsg.data[0] != 0)
						{
							// Process the currently held event
							SendBuf[nchar++] = curSawEventMsg.data[5]-'0';  // Event type
							memcpy((char *)&SendBuf[nchar], (char *)&curSawEventMsg.data[7], MESSAGE_SIZE-7);
							nchar += MESSAGE_SIZE-7;
							eventsRetrieved++;
							curSawEventMsg.data[0] = 0;  // Clear the current event
						}

						// Then retrieve additional events from the queue
						for (i = eventsRetrieved; i < RegNo; i++)
						{
							// Try to dequeue a pending event...
							if (deque(&SawEventMsgQueue, &tempEventMsg))
							{
								// successful dequeueing of a pending message...
								SendBuf[nchar++] = tempEventMsg.data[5]-'0';  // Event type
								memcpy((char *)&SendBuf[nchar], (char *)&tempEventMsg.data[7], MESSAGE_SIZE-7);
								nchar += MESSAGE_SIZE-7;
								eventsRetrieved++;
							}
							else
							{
								// No more events - pad with zeros
								SendBuf[nchar++] = 0;  // Indicate no event
								// Fill the rest with appropriate padding
								for (j = 0; j < MESSAGE_SIZE-7; j++)
								{
									SendBuf[nchar++] = 0;
								}
							}
						}

						printf("Retrieved %d events\n", eventsRetrieved);

						if ((n = sendto (serverSock, (char *)SendBuf, nchar, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
						{
							// sendto error...
							printf ("%s: ERROR - 0x03 sendto error...\n", argv[0]);
							// close the socket
							closesocket (serverSock);
							// clean up and exit
							WSACleanup();
							return 0;
						}
					}
					else if (RegAddr == 3090)
					{
						// Similar batch retrieval for notifications
						SendBuf[0] = 0xfd;
						int nchar = 1;
						int notifsRetrieved = 0;

						MESSAGE tempNotifMsg;

						// First check if there's a notification currently held
						if (curSawNotifMsg.data[0] != 0)
						{
							// Process the currently held notification
							SendBuf[nchar++] = curSawNotifMsg.data[5]-'0';  // Notification type
							memcpy((char *)&SendBuf[nchar], (char *)&curSawNotifMsg.data[7], MESSAGE_SIZE-7);
							nchar += MESSAGE_SIZE-7;
							notifsRetrieved++;
							curSawNotifMsg.data[0] = 0;  // Clear the current notification
						}

						// Then retrieve additional notifications from the queue
						for (i = notifsRetrieved; i < RegNo; i++)
						{
							// Try to dequeue a pending notification...
							if (deque(&SawNotifMsgQueue, &tempNotifMsg))
							{
								// successful dequeueing of a pending message...
								SendBuf[nchar++] = tempNotifMsg.data[5]-'0';  // Notification type
								memcpy((char *)&SendBuf[nchar], (char *)&tempNotifMsg.data[7], MESSAGE_SIZE-7);
								nchar += MESSAGE_SIZE-7;
								notifsRetrieved++;
							}
							else
							{
								// No more notifications - pad with zeros
								SendBuf[nchar++] = 0;  // Indicate no notification
								// Fill the rest with appropriate padding
								for (j = 0; j < MESSAGE_SIZE-7; j++)
								{
									SendBuf[nchar++] = 0;
								}
							}
						}

						printf("Retrieved %d notifications\n", notifsRetrieved);

						if ((n = sendto (serverSock, (char *)SendBuf, nchar, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
						{
							// sendto error...
							printf ("%s: ERROR - 0x03 sendto error...\n", argv[0]);
							// close the socket
							closesocket (serverSock);
							// clean up and exit
							WSACleanup();
							return 0;
						}
					}
					else
					{
						// Important! This section of code in the server should actually fetch the register(s) content
						// (for instance the set of all robot axis positions) and send it to the client.
						// Sending back the Register Content, here we simply fill in this information with dummy data...
						SendBuf[0] = 0xfd;
						for (i=1;i<1+8*RegNo;i++)
						{
							SendBuf[i] = i%256;
						}

						if ((n = sendto (serverSock, (char *)SendBuf, 1+8*RegNo, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
						{
							// sendto error...
							printf ("%s: ERROR - 0x03 sendto error...\n", argv[0]);

							// close the socket
							closesocket (serverSock);

							// clean up and exit
							WSACleanup();

							return 0;
						}
					}

					printf ("Sent back the msg \"0xfd\" and the content of the %d Registers from RegAddr %d to the client ...\n", RegNo, RegAddr);
				}
				else if (RecvBuf[0] == 0x04)
				{
					// 0x04 --> SETREG
					printf ("Received \"0x04\" from the client ...\n");
					// Checking the consistency of the received number of bytes...
					if (n!=11)
					{
						// msg format error...
						printf ("Message format error 0x04...\n");

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					RegAddr = RecvBuf[1] + 256 * RecvBuf[2];
					printf ("RegAddr --> %d\n", RegAddr);

					// Important! This section of code in the server should actually set the register content
					// (for instance to command the linear axis position).
					// Here, we simply parse the Data Payload, and acknowledge the receipt...
					RegValLo = RecvBuf[3];
					RegValLo |= (RecvBuf[4]<<8);
					RegValLo |= (RecvBuf[5]<<16);
					RegValLo |= (RecvBuf[6]<<24);
					printf ("RegValLo --> %I64d\n", RegValLo);

					RegValHi = RecvBuf[7];
					RegValHi |= (RecvBuf[8]<<8);
					RegValHi |= (RecvBuf[9]<<16);
					RegValHi |= (RecvBuf[10]<<24);
					printf ("RegValHi --> %I64d\n", RegValHi);

 					if (RegAddr==3090)
					{
    					// REG 3090 --> Clear Self Awareness Notifications for the UC 3.9 (about "KHs not meeting quality requirements")
                        // Semantics:
                        // Whatever write to this register will clear pending notifications...
                        curSawNotifMsg.data[0] = 0;
                        printf("Pending Saw Notifications Cleared...\n");
					} else if (RegAddr==3091)
					{
    					// REG 3091 --> Clear Self Awareness Insertion/Extraction Events for the UC 3.9
                        // Semantics:
                        // Whatever write to this register will clear pending events...
                        curSawEventMsg.data[0] = 0;
                        printf("Pending Saw Insertion/Extraction Events Cleared...\n");
					}

					SendBuf[0] = 0xfc;
					SendBuf[1] = 0x00;

					if ((n = sendto (serverSock, (char *)SendBuf, 2, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
					{
						// sendto error...
						printf ("%s: ERROR - 0x04 sendto error...\n", argv[0]);

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					printf ("Sent back the msg \"0xfc\" and the ACK of valid operation \"0x00\" to the client ...\n");
				}
				else if (RecvBuf[0] == 0x05)
				{
					// 0x05 --> SETREGBLOCK
					printf ("Received \"0x05\" from the client ...\n");
					// Checking the consistency of the received number of bytes...
					if (n<12)
					{
						// msg format error...
						printf ("Message format error 0x05...\n");

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					RegAddr = RecvBuf[1] + 256 * RecvBuf[2];
					printf ("RegAddr --> %d\n", RegAddr);

					RegNo = RecvBuf[3];
					printf ("RegNo --> %d\n", RegNo);

					// Important! This section of code in the server should actually set the registers content
					// (for instance to command simultaneously the 7 axis of the robot positions).
					// Here, we simply parse the Data Payload, and acknowledge the receipt...

					for (i=0,j=0;i<RegNo;i++,j+=8)
					{
						RegValLo = RecvBuf[4+j];
						RegValLo |= (RecvBuf[5+j]<<8);
						RegValLo |= (RecvBuf[6+j]<<16);
						RegValLo |= (RecvBuf[7+j]<<24);
						printf ("RegValLo[%d] --> %I64d\n", i+1, RegValLo);

						RegValHi = RecvBuf[8+j];
						RegValHi |= (RecvBuf[9+j]<<8);
						RegValHi |= (RecvBuf[10+j]<<16);
						RegValHi |= (RecvBuf[11+j]<<24);
						printf ("RegValHi[%d] --> %I64d\n", i+i, RegValHi);
					}

					SendBuf[0] = 0xfb;
					SendBuf[1] = 0x00;

					if ((n = sendto (serverSock, (char *)SendBuf, 2, 0, (SOCKADDR *) &clientAddr, sizeof (clientAddr))) < 0)
					{
						// sendto error...
						printf ("%s: ERROR - 0x04 sendto error...\n", argv[0]);

						// close the socket
						closesocket (serverSock);

						// clean up and exit
						WSACleanup();

						return 0;
					}
					printf ("Sent back the msg \"0xfb\" and the ACK of valid operation \"0x00\" to the client ...\n");
				}

				// "Server Killing" function, currently disabled...
				// else if ((RecvBuf[0]==0)) break;
 			}
			else
			{
				// this should never happen...
				// select return some event, but no UDP dgm are available from Port 27015
				Sleep(40);
			}
		}
	}

	// close the socket when finished receiving datagrams
	printf ("Finished receiving. Closing socket...\n");
	closesocket (serverSock);

	// clean up and exit
	printf ("Exiting...\n");
	WSACleanup();

	return 0;
}