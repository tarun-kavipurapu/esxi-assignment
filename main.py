import socket
import json
import threading
import subprocess
import signal
import sys
import time
from datetime import datetime


class Server:
    def __init__(self, addr, port, max_clients):
        self.addr = addr
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.addr, self.port))
        self.max_clients = max_clients
        self.socket.listen(self.max_clients)
        print("Server running on {}:{}".format(self.addr, self.port))
        self.running = True  
    
    def execute(self, command):
        try:
            result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if result.returncode == 0:
                return result.stdout.strip(), None
            return None, result.stderr.strip()
        except Exception as e:
            return None, str(e)
    
    def vm_count(self):
        output = self.get_vms()
        if "error" in output:
            return output
        vms = output["virtual_machines"]
        return {"count": len(vms)}
    
    def vm_power_off(self, vm_id):
        if vm_id is None:
            return {"error": "please provide vmid of the machine"}
        
        state = self.get_vm_state(vm_id)
        if "error" in state:
            return state
        if state["state"] != 'Powered on':
            return {"error": "the vm is already turned off..."}
        
        cmd = "vim-cmd vmsvc/power.off {}".format(vm_id)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        return {"status": "turned off sucessfully"}

    def vm_power_on(self, vm_id):
        if vm_id is None:
            return {"error": "please provide vmid of the machine"}
        state = self.get_vm_state(vm_id)
        if "error" in state:
            return state
        if state["state"] != 'Powered off':
            return {"error": "the vm is alrady on..."}
        cmd = "vim-cmd vmsvc/power.on {}".format(vm_id)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        return {"status": "turned on sucessfully"}
    
    def vm_reboot(self, vm_id):
        if vm_id is None:
            return {"error": "please provide vmid of the machine"}
        state = self.get_vm_state(vm_id)
        if "error" in state:
            return state
        cmd = "vim-cmd vmsvc/power.reboot {}".format(vm_id)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        return {"status": "rebooted sucessfully"}

    def vm_latest_running_task(self, vmid):
        cmd = 'vim-cmd vmsvc/get.tasklist {}'.format(vmid)
        output, error = self.execute(cmd)
        if error:
            return {"error": error}
        output = output.splitlines()
        output_lines = [
            line.strip("',") for line in output
            if 'createSnapshot' in line
        ]
        if(len(output_lines)<=0):
            return {"error":"no tasks currently running"}

        ans = output_lines[0].strip().split(":")
        taskId = ans[1].strip("',")
        return taskId
    def vm_progress(self,vmid):

        task_id = self.vm_latest_running_task(vmid)
        if "error" in task_id:
            return task_id
        output = self.vm_task_info(task_id)
        if "error" in output:
            return output
        
        return {"progress":output["progress"]}
    
    def vm_task_info(self, id):
        cmd = 'vim-cmd vimsvc/task_info {}'.format(id)
        output, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        lines = output.split('\n')
        state = ''
        progress = 0
        start_time = None
        end_time = None

        for line in lines:
            line = line.strip()
            if 'state =' in line:
                state = line.split('"')[1] if len(line.split('"')) > 1 else state
            elif 'progress =' in line:
                progress = line.split('=')[1].strip() if len(line.split('=')) > 1 else progress
            elif 'startTime =' in line:
                start_time = line.split('"')[1] if len(line.split('"')) > 1 else start_time
            elif 'completeTime =' in line:
                end_time = line.split('"')[1] if len(line.split('"')) > 1 else end_time
        task_info = {
            'state': state,
            'progress': progress,
            'start_time': start_time,
            'end_time': end_time
        }
        return task_info
    
    def vm_create_snap(self, vm_id, name="test_name", description="test_description"):
        print("creating snapshot ....")
        cmd = 'vim-cmd vmsvc/snapshot.create {0} "{1}" "{2}" 1 0'.format(vm_id, name, description)
        output, error = self.execute(cmd)
        if error:
            return {"error": error}
        time.sleep(2)
        task_id = self.vm_latest_running_task(vm_id)
        if "error" in task_id:
            return {task_id}
        output = self.vm_task_info(task_id)
        if "error" in output:
            return output

        start_time = datetime.strptime(output["start_time"], "%Y-%m-%dT%H:%M:%S.%fZ")
        end_time = datetime.strptime(output["end_time"], "%Y-%m-%dT%H:%M:%S.%fZ")

        delta = start_time - end_time
        delta_seconds = delta.seconds

        print("Time difference: {} microseconds".format(delta_seconds))

        return {"status": "Sucessfully created the VM", "time_taken": "{} microseconds".format(delta_seconds)}

    def get_vm_state(self, vm_id):
        cmd = "vim-cmd vmsvc/power.getstate {}".format(vm_id)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        result = result.splitlines()[1]
        return {"state": result}
         
    def get_vms(self):
        cmd = "vim-cmd vmsvc/getallvms"
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        virtual_machines = []
        output = result.splitlines()
        output = output[1:]
        for line in output:
            parts = [part for part in line.split(' ') if part.strip()]
            vm = {
                "vmid": int(parts[0]),
                "name": parts[1].strip(),
                "file": parts[2].strip(),
                "guest_os": parts[3].strip(),
                "version": parts[4].strip(),
                "annotation": None
            }
            virtual_machines.append(vm)

        return {"virtual_machines": virtual_machines}
    
    def get_last_snapshot(self, vmid):
        if vmid is None:
            return {"error": "please provide vmid of the machine"}
        cmd = "vim-cmd vmsvc/snapshot.get {}".format(vmid)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        result = result.splitlines()
        snapshot_data = {}
        mapping = {
            "Snapshot Name": "name",
            "Snapshot Id": "id",
            "Snapshot Description": "description",
            "Snapshot State": "state",
            "Snapshot Created On": "created"
        }
        for line in result[-5:]:
            for key, value in mapping.items():
                if key in line:
                    snapshot_data[value] = ":".join(line.split(":")[1:]).strip()
                    break
        return snapshot_data
    
    def eval(self, input_data):
        command = input_data.get("command")
        vmid = input_data.get("vmid")
        snapshotid = input_data.get("snapshotid")
        print(snapshotid)
        name = input_data.get("name")
        description = input_data.get("description")
        ans = None
        if command == "count":
            ans = self.vm_count()
        elif command == "get_vms":
            ans = self.get_vms()
        elif command == "power_off":
            ans = self.vm_power_off(vmid)
        elif command == "power_on":
            ans = self.vm_power_on(vmid)
        elif command == "reboot":
            ans = self.vm_reboot(vmid)
        elif command == "create_snapshot":
            ans = self.vm_create_snap(vmid, name, description)
        elif command == "revert_snapshot":
            ans = self.vm_revert(vmid, snapshotid)
        elif command == "progress":
            ans = self.vm_progress(vmid)
        elif command == "remove_snapshots":
            ans = self.vm_remove_snapshots(vmid)
        else:
            return "Error: command is not present"
        
        return ans    
    
    def vm_remove_snapshots(self,vmid):
       if vmid is None:
            return {"error": "please provide vmid of the machine"}
       command = "vim-cmd vmsvc/snapshot.removeall {}".format(vmid)
       output, error = self.execute(command)
       if error:
            return {"error": error}
       return {"status":"all snapshots for vm:{} are removed".format(vmid)}

    def vm_revert(self, vmid, snapshotid=None):
        if vmid is None:
            return {"error": "please provide vmid of the machine"}
        if snapshotid is None:
            result = self.get_last_snapshot(vmid)
            snapshotid = result["id"]
        
        cmd = "vim-cmd vmsvc/snapshot.revert {} {} 0".format(vmid, snapshotid)
        result, error = self.execute(cmd)
        if error:
            return {"error": error}
        
        return {"status": "Reverted to snapshot with snapshotId {} sucessfully".format(snapshotid)}

    def handle_clients(self, client_socket, client_addr):
        print("New connection from:", client_addr)
        try:
            while self.running: 
                data = client_socket.recv(1024)
                if not data:
                    break
                try:
                    input_data = json.loads(data.decode())
                    print("Received JSON data:", input_data)
                    output = self.eval(input_data)
                    client_socket.send(json.dumps(output).encode())
                except json.JSONDecodeError:
                    print("Invalid JSON received from", client_addr)
                    client_socket.send(json.dumps({"Error": "Input should be JSON"}).encode())
        except ConnectionResetError:
            print("Connection lost with", client_addr)
        finally:
            client_socket.close()
            print("Connection closed with", client_addr)

    def start_server(self):
        try:
            while self.running:
                client_socket, client_addr = self.socket.accept()
                client_thread = threading.Thread(target=self.handle_clients, args=(client_socket, client_addr))
                client_thread.start()
        except KeyboardInterrupt:
            print("Shutting down server...")
            self.stop_server()

    def stop_server(self):
        self.running = False
        self.socket.close()
        print("Server has stopped.")


def handle_sigint(signal, frame):
    print("\nCaught SIGINT, stopping server...")
    server.stop_server()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_sigint)

if __name__ == "__main__":
    server = Server("0.0.0.0", 5555, 5)
    server.start_server()