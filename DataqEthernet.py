import socket
import struct
import time
import random

class DataQDAQ:
    DEFAULT_PORT = 51235
    DEFAULT_LOCAL_PORT = 1234
    DQ_COMMAND = 0x31415926
    DQ_RESPONSE = 0x21712818
    DQ_ADCDATA = 0x14142135
    
    def __init__(self, ip_address=None, port=DEFAULT_PORT, group_id=None):
        self.port = port
        self.group_id = 0x12345678
        if ip_address:
            self.ip_address = ip_address
        else:
            self.ip_address = self.discover_device()
        if not self.ip_address:
            raise RuntimeError("No Dataq device found on the network.")
        
        hostname = socket.gethostname()
        IPAdr = socket.gethostbyname(hostname)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((IPAdr, 1234))
        self.sock.settimeout(2)

    def discover_device(self):
        discovery_port = 1235
        discovery_receive_port = 1234
        discovery_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_sock.settimeout(2.0)

        # Bind to a known port to receive the response
        discovery_sock.bind(('', discovery_receive_port))

        discovery_msg = f'dataq_instruments {discovery_receive_port}'.encode('ascii')
        discovery_sock.sendto(discovery_msg, ('<broadcast>', discovery_port))
        try:
            data, addr = discovery_sock.recvfrom(1024)
            print(f"Discovered Dataq device at {addr[0]}")
            return addr[0]
        except socket.timeout:
            return None
        finally:
            discovery_sock.close()

    def _build_packet(self, command_code, arg0=0, arg1=0, arg2=0, payload=b''):
        header = struct.pack('<IIIIII', self.DQ_COMMAND, self.group_id, command_code, arg0, arg1, arg2)
        return header + payload

    def _send_command(self, command_code, arg0=0, arg1=0, arg2=0, payload_str="", ignore_response=False):
        payload = payload_str.encode('ascii')
        packet = self._build_packet(command_code, arg0, arg1, arg2, payload)
        self.sock.sendto(packet, (self.ip_address, self.port))
        if not ignore_response:
            response, _ = self.sock.recvfrom(1024)
            return self._parse_response(response)
        else:
            return None

    def _parse_response(self, response):
        header = struct.unpack('<IIII', response[:16])
        if header[0] != self.DQ_RESPONSE:
            raise ValueError("Invalid response header")
        length = header[3]
        payload = response[16:16+length].decode('ascii').strip()
        return payload
    
    def get_local_ip(self, remote_ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((remote_ip, 1))  # dummy connect to get local IP
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        return local_ip

    def connect(self, local_port=0, mode=2):
        """Connect and assign group ID. mode: 0=slave, 1=master, 2=standalone."""
        local_ip = self.get_local_ip(self.ip_address)
        print(f"Local IP: {local_ip}")
        return self._send_command(command_code=10, arg0=local_port, arg1=mode, arg2=0, payload_str=local_ip)

    def disconnect(self):
        return self._send_command(command_code=11)

    def info(self, index):
        return self._send_command(command_code=13, payload_str=f"info {index}")

    def set_scan_list(self, index, config):
        return self._send_command(command_code=13, payload_str=f"slist {index} {config}")

    def set_sample_rate(self, srate):
        return self._send_command(command_code=13, payload_str=f"srate {srate}")

    def start_sync(self):
        self._send_command(command_code=1, arg0=1, arg1=2, arg2=3, payload_str="", ignore_response=True)
    
    def keep_alive(self, setting=None):
        if setting is not None:
            return self._send_command(command_code=13, payload_str=f"keepalive {setting}")
        return self._send_command(command_code=12, payload_str="KeepAlive", ignore_response=True)

    def stop_acquisition(self):
        return self._send_command(command_code=13, payload_str="stop")

    def set_filter(self, channel, mode):
        return self._send_command(command_code=13, payload_str=f"filter {channel} {mode}")

    def set_decimation(self, value):
        return self._send_command(command_code=13, payload_str=f"dec {value}")

    def set_deca(self, value):
        return self._send_command(command_code=13, payload_str=f"deca {value}")

    def get_model(self):
        return self.info(1)

    def get_serial_number(self):
        return self.info(6)
    
    def set_packet_size(self, sizeidx):
        return self._send_command(command_code=13, payload_str=f"ps {sizeidx}")

    def parse_adc_data(self, data):
        if len(data) < 16:
            return None  # not enough data

        TYPE, GroupID, Order, CumulativeCount, PayLoadSamples = struct.unpack('<5I', data[:20])

        if TYPE != self.DQ_ADCDATA:
            raise ValueError("Unexpected binary header")
        
        samples = []
        offset = 20
        for _ in range(PayLoadSamples):
            sample = struct.unpack_from('<h', data, offset)[0]
            samples.append(sample)
            offset += 2
        print("Samples:", samples)


    def read_adc_data(self):
        try:
            data, _ = self.sock.recvfrom(2048)
            #print(data.hex())
            return self.parse_adc_data(data)
        except socket.timeout:
            return None


    def read_voltage_as_flow(self):
        self.read_adc_data()

    def close(self):
        self.sock.close()

def main():
    try:
        # Create DAQ instance (discover if no IP provided)
        daq = DataQDAQ()
        daq.connect()
        print("Connected to DAQ")
        
        time.sleep(.1)
        print("Model:", daq.get_model())
        print("Serial:", daq.get_serial_number())
        
        decimation = 500
        deca = 4
        srate = 30000

        print(daq.set_decimation(decimation))
        print(daq.set_deca(deca))
        print(daq.set_sample_rate(srate=srate))
        
        time.sleep(0.2)
        
        # Basic configuration
        
        for i in range(0, 8):
            print(daq.set_scan_list(i, i))  # Analog input channel i
        print(daq.set_filter('*', 1)) # Set filtering

        print(daq.set_packet_size(sizeidx=0)) # Set packet size to 16 bytes (default)

        time.sleep(0.1)

        daq.start_sync()
        print("Acquisition started. Press Ctrl+C to stop.")

        while True:
            daq.read_voltage_as_flow()
            time.sleep(1.0)
            daq.keep_alive()

    except KeyboardInterrupt:
        print("\nUser stopped logging.")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        print("Stopping and cleaning up...")
        try:
            daq.stop_acquisition()
            daq.disconnect()
            daq.close()
        except:
            pass
        print("Done.")

if __name__ == "__main__":
    main()
