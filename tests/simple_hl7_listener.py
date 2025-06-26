#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple InBody HL7 TCP Listener
================================

Description:
- A minimal, focused script to listen for incoming HL7 data from an InBody device.
- It binds to a specific IP and port, accepts one connection, prints whatever it
  receives, and then exits.
- Designed for debugging and verifying the raw data stream from the InBody.
"""

import socket
import logging

# --- Configuration ---
# The IP address of the Raspberry Pi. Use '0.0.0.0' to listen on all interfaces.
# Using the specific IP is better if you have multiple network cards.
PI_IP = '192.168.1.50' 

# The port that the InBody device is configured to SEND DATA TO.
# This must match the "Receiving Port" or "Data Port" in the InBody settings.
DATA_PORT = 2575

# HL7 message terminators
START_OF_BLOCK = b'\x0b'  # VT (Vertical Tab)
END_OF_BLOCK = b'\x1c'    # FS (File Separator)
CARRIAGE_RETURN = b'\x0d' # CR

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SimpleListener")

def main():
    """Main function to start the listener."""
    logger.info("Starting Simple HL7 Listener...")
    logger.info("Binding to IP: {} on Port: {}".format(PI_IP, DATA_PORT))

    # Create a TCP/IP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Allow reusing the address to avoid "Address already in use" errors
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # Bind the socket to the port
        server_socket.bind((PI_IP, DATA_PORT))

        # Start listening for incoming connections (1 means we'll handle one connection at a time)
        server_socket.listen(1)
        logger.info("Successfully bound to port. Waiting for a connection from InBody...")
        print("="*60)
        print(">>> PLEASE PERFORM A MEASUREMENT ON THE INBODY DEVICE NOW <<<")
        print("="*60)

        # Wait for a connection (this is a blocking call)
        client_socket, client_address = server_socket.accept()
        logger.info("Connection accepted from: {}".format(client_address))

        try:
            full_data = bytearray()
            # Set a timeout for receiving data (e.g., 30 seconds)
            client_socket.settimeout(30.0)

            # Loop to receive all data from the client
            while True:
                data = client_socket.recv(1024) # Receive up to 1024 bytes
                if not data:
                    # No more data from client, connection closed by InBody
                    logger.info("Connection closed by InBody.")
                    break
                full_data.extend(data)
                
                # Check if the complete HL7 message has been received
                if END_OF_BLOCK in full_data:
                    logger.info("End of HL7 message detected.")
                    break
            
            # --- Data Processing ---
            if full_data:
                logger.info("Total data received: {} bytes".format(len(full_data)))
                print("\n" + "-"*20 + " RAW DATA (BYTES) " + "-"*20)
                print(full_data)
                
                # Try to decode to string for readability
                try:
                    # Replace HL7 control characters for cleaner printing
                    readable_data = full_data.decode('utf-8', errors='ignore')
                    readable_data = readable_data.replace('\x0b', '<VT>\n')
                    readable_data = readable_data.replace('\x1c', '\n<FS>')
                    readable_data = readable_data.replace('\r', '\n')
                    
                    print("\n" + "-"*20 + " DECODED DATA (TEXT) " + "-"*20)
                    print(readable_data)
                except Exception as e:
                    logger.error("Could not decode data as UTF-8: {}".format(e))

            else:
                logger.warning("No data was received from the connection.")

        finally:
            # Clean up the connection
            logger.info("Closing client socket.")
            client_socket.close()

    except socket.error as e:
        logger.error("Socket error: {}".format(e))
        logger.error("Is the port {} already in use? Is the IP {} correct?".format(DATA_PORT, PI_IP))
    except KeyboardInterrupt:
        logger.info("Listener stopped by user (Ctrl+C).")
    finally:
        logger.info("Closing server socket. Shutting down.")
        server_socket.close()


if __name__ == '__main__':
    main()