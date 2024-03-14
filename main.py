import socket
import threading
import time
import os

config = {
    'HOST_NAME': '127.0.0.1',  # Use the IP address as the hostname for the localhost
    'BIND_PORT': 8888,  # Port on which the proxy server will listen
    'MAX_REQUEST_LEN': 2048,  # Maximum length of the request to be received
    'CONNECTION_TIMEOUT': 10  # Timeout for connections to remote web servers
}


def read_config_file():
    with open('config/config.txt', 'r') as file:
        for line in file:
            line = line.strip()
            if line.startswith("cache_time"):
                timeout = int(line.split("=")[1].split("#")[0].strip())
            elif line.startswith("whitelisting"):
                list_of_domain = [item.strip() for item in line.split("=")[1].split(",")]
            elif line.startswith("time"):
                start_time, end_time = map(int, line.split("=")[1].split("-"))

    return timeout, list_of_domain, start_time, end_time


def clear_folder():
    while True:
        time.sleep(cache_time)
        try:
            for filename in os.listdir('config/cache'):
                file_path = os.path.join('config/cache', filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"Error: {e}")


def check_url_matched_base_domain(url, list_of_domain):
    for domain in list_of_domain:
        if url.startswith(f"http://{domain}"):
            return True
    return False


def send_403_response(conn):
    # Read the contents of the 403.html file
    with open('venv/403.html', 'r') as file:
        response_content = file.read()

    # HTTP response with status code 403 and the content
    response = "HTTP/1.1 403 Forbidden\r\n"
    response += "Content-Type: text/html\r\n"
    response += f"Content-Length: {len(response_content)}\r\n"
    response += "\r\n"  # Empty line to indicate the end of headers
    response += response_content

    # Send the response to the client
    conn.sendall(response.encode())


def handle_client_request(conn):
    # Time in second from midnight
    now_time = int(time.localtime().tm_hour) * 3600 + int(time.localtime().tm_min) * 60 + int(time.localtime().tm_sec)
    proxy_start_time = start * 60 * 60  # 8 AM
    proxy_end_time = end * 60 * 60      # 8 PM

    # Check if time is valid or not
    if now_time < proxy_start_time or now_time > proxy_end_time:
        send_403_response(conn)
        print("The services is out of time. Comeback between 8h - 20h")
        return

    # Receive the request from the browser
    request = conn.recv(config['MAX_REQUEST_LEN'])
    msg = request.decode()
    print("Request:", msg)

    # parse the first line
    datatype = msg.split(' ')[0]
    if datatype not in {"GET", "HEAD", "POST"}:
        send_403_response(conn)
        return

    first_line = msg.split('\n')[0]
    print("first_line:", first_line)

    # get url
    url = first_line.split(' ')[1]
    print("url:", url)

    # Check if the URL starts with any whitelisted base domain
    if not check_url_matched_base_domain(url, whitelist):
        send_403_response(conn)
        print("The domain is not in the base domain list")
        return

    web, port = parse_url(url)
    print("web:", web)
    print("port:", port)

    # Change all special character to '.' in order to save as filename
    character_to_replace = ['!', '@', '#', '$', '%', '^', '&',
                            '*', '=', ':', ';', '<', '>', '?',
                            '/', '-', '+', '[', ']', '{', '}']
    for i in character_to_replace:
        url = url.replace(i, '.')

    # Check if data has already existed in cache
    filename = url + '.dat'
    for filename_line in os.listdir(r'config\cache'):
        if filename_line == filename:
            print("Cached data found. Sending cached data to client.")
            try:
                with open('config/cache/' + filename, 'rb') as file:
                    data = file.read()
                    conn.sendall(data)
                    conn.close()
            except PermissionError:
                print("Don't have permission to open file.")
            return

    # If data doesn't exist, send the request to the web server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((web, port))

    # Split the request header into lines
    request_lines = request.decode().split('\n')

    # Remove the fist line from the request and add modified first line
    if datatype == "GET":
        http_method = "GET"
    elif datatype == "POST":
        http_method = "POST"
    elif datatype == "HEAD":
        http_method = "HEAD"

    # Find pos of ://
    url_temp = first_line.split(' ')[1]
    http_pos = url_temp.find("://")
    temp = url_temp[(http_pos + 3):]  # get the rest of url

    # Extract the path
    path_pos = temp.find("/")
    path = temp[(path_pos + 1):]
    print("Path: ", path)

    # Construct the modified first line
    prefix = f"{http_method} /{path} HTTP/1.1\r"
    modified_request_lines = [line for line in request_lines]
    modified_request_lines.pop(0)
    modified_request_lines.insert(0, prefix)

    # Join the modified request lines back into a single string
    modified_http_request = "\n".join(modified_request_lines)
    print("Modified request:", modified_http_request)
    s.sendall(modified_http_request.encode())

    # Receive data from web server and send to the client
    received_data = b""
    content_length = None
    content_received = 0

    while True:
        data = s.recv(config['MAX_REQUEST_LEN'])
        if not data:
            break

        received_data += data
        # Separate headers and body to get "Content length"
        if content_length is None and b'\r\n\r\n' in received_data:
            headers, body = received_data.split(b'\r\n\r\n', 1)
            for line in headers.split(b'\r\n'):
                if line.startswith(b'Content-Length:'):
                    content_length = int(line.split(b':', 1)[1].strip())
                    break

        # Check if receive enough data or not
        content_received += len(data)
        if content_length is not None and content_received >= content_length:
            break

    s.close()
    # Send data to client
    conn.sendall(received_data)
    conn.close()
    print("connection to client closed")

    # Save the received data to a binary file
    with open('config/cache/' + filename, 'wb') as file:
        file.write(received_data)


def parse_url(url):
    # Find pos of ://
    http_pos = url.find("://")
    if http_pos == -1:
        temp = url
    else:
        temp = url[(http_pos + 3):]  # get the rest of url

    print(http_pos)
    print("temp:", temp)
    port_pos = temp.find(":")  # find the port pos (if any)
    print("port_pos:", port_pos)

    # Find end of web server
    webserver_pos = temp.find("/")
    if webserver_pos == -1:
        webserver_pos = len(temp)
    print("webserver_pos: ", webserver_pos)

    # webserver = ""
    # port = -1
    if port_pos == -1 or webserver_pos < port_pos:  # default port
        port = 80
        webserver = temp[:webserver_pos]
    else:  # specific port
        port = int((temp[(port_pos + 1):])[:webserver_pos - port_pos - 1])
        webserver = temp[:port_pos]

    return webserver, port


def start_proxy():
    while True:
        try:
            conn, addr = serverSocket.accept()
            print(f"Connected to {addr[0]}:{addr[1]}")

            # Create a thread to handle each client request
            client_thread = threading.Thread(target=handle_client_request, args=(conn,))
            client_thread.start()
        except KeyboardInterrupt:
            clear_folder()
            print("Proxy server shutting down...")
            serverSocket.close()
            break


# Create a thread to handle deletion of file cache
cache_time, whitelist, start, end = read_config_file()
clear_thread = threading.Thread(target=clear_folder)
clear_thread.daemon = True
clear_thread.start()

# Create a TCP socket
serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Re-use the socket
serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# bind the socket to a public host, and a port
serverSocket.bind((config['HOST_NAME'], config['BIND_PORT']))
serverSocket.listen(10)  # become a server socket
print("Waiting for browser clients...")

start_proxy()
