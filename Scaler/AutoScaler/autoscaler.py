from constants_autoscaler import *
from rabbit import *
import threading
import time as TimeSleep
import json
import logging

class AutoScaler():
    def __init__(self):
        self.instances = dict()
        self.allow_orchestrate = False

        self.logger = logging.getLogger(LOGGER_NAME)
        handler = logging.FileHandler(LOG_FILE_NAME)
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s:%(message)s', datefmt='[%Y-%m-%d %H:%M:%S]')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self.file_output_scaler = open(SCALER_RESPONSE_OUTPUT, 'w')


    def call_agent(self, rabbit_conn, command, *args):
        call_dict = dict()
        call_dict["command"] = command
        call_dict["host"] = RABBIT_SCALER_QUEUE
        call_dict["parameters"] = args

        # self.logger.info
        response = rabbit_conn.call(RABBIT_SCALER_QUEUE, call_dict)
        return response


    def remove_instance(self, instance):
        target_key = "{0}:{1}".format(instance['project_id'], instance['name'])
        vm = self.instances.get(target_key)

        if vm is not None:
            client_removed = self.instances.pop(target_key)
            client_removed['rabbit_conn'].delete_conn()
        
        if not self.instances:
            self.allow_orchestrate = False


    def update_orchestrate_list(self, client_request):
        if client_request is not None:
            self.logger.info('Message received from client and will be processed: {}'.format(client_request))
            for item in client_request['instance']:
                new_vm = dict()
                rabbit_conn = None
                target_key = "{0}:{1}".format(client_request['project_id'], item)
                vm = self.instances.get(target_key)

                if (client_request['action'] in 'start') and vm is None:
                    rabbit_conn = RabbitAgent()
                    new_vm['name'] = item
                    new_vm['project_id'] = client_request['project_id']
                    new_vm['window_time'] = client_request['time']
                    new_vm['rabbit_conn'] = rabbit_conn

                    new_vm['min_memory_usage'] = client_request['min_memory_usage']
                    new_vm['max_memory_usage'] = client_request['max_memory_usage']
                    new_vm['min_vcpu_usage'] = client_request['min_vcpu_usage']
                    new_vm['max_vcpu_usage'] = client_request['max_vcpu_usage']

                    new_vm['count_cpu_up'] = 0
                    new_vm['count_cpu_down'] = 0
                    new_vm['count_mem_up'] = 0
                    new_vm['count_mem_down'] = 0
                    new_vm['count_scale'] = 0
        
                    self.instances[target_key] = new_vm
                    self.logger.info("Instance '{0}' from project '{1}' entered in the Scaler instances pool".format(new_vm['name'], 
                                                                                                                 new_vm['project_id']))
                
                if (client_request['action'] in 'stop') and vm is not None:
                    client_removed = self.instances.pop(target_key)
                    client_removed['rabbit_conn'].delete_conn()
                    self.logger.info("Instance '{0}' from project '{1}' is removed from the pool".format(item, 
                                                                                                     client_request['project_id']))
            self.allow_orchestrate = bool(self.instances)


    def get_instance(self, instance):
        call_response = self.call_agent(instance['rabbit_conn'], 
                                        "find_instance", 
                                        instance['name'], 
                                        instance['project_id'], 
                                        instance['window_time']
                                       )
        
        vm_dict = call_response["result"]
        return vm_dict


    def orchestrate_instance(self, instance):
        rabbit_conn = instance['rabbit_conn']
        vm_dict = dict()

        min_memory_usage = instance['min_memory_usage'] if instance['min_memory_usage'] > 0 else MEM_LOWER_USAGE        
        max_memory_usage = instance['max_memory_usage'] if instance['max_memory_usage'] > 0 else MEM_UPPER_USAGE        
        min_vcpu_usage = instance['min_vcpu_usage'] if instance['min_vcpu_usage'] > 0 else CPU_LOWER_USAGE        
        max_vcpu_usage = instance['max_vcpu_usage'] if instance['max_vcpu_usage'] > 0 else CPU_UPPER_USAGE

        vm_dict = self.get_instance(instance)

        instance['count_scale'] += 1

        if vm_dict:
            vm_status = vm_dict['status']
            vm_usage = vm_dict['usage']

            if vm_status and vm_usage:
                if (vm_usage["mem_usage"] > max_memory_usage):
                    instance['count_mem_up'] += 1
                    instance['count_mem_down'] = 0
                    new_memory = vm_status["current_memory"] + DELTA_MEM

                    if instance['count_mem_up'] > SCALE_TRESHOLD:
                        instance['count_mem_up'] = 0
                        if (new_memory < vm_status["max_memory"]):
                            self.call_agent(rabbit_conn, "change_memory", vm_dict, new_memory)
                        else:
                            self.call_agent(rabbit_conn, "change_memory", vm_dict, vm_status["max_memory"])
                
                if (vm_usage["mem_usage"] < min_memory_usage):
                    instance['count_mem_up'] = 0
                    instance['count_mem_down'] += 1
                    new_memory = vm_status["current_memory"] - DELTA_MEM

                    if instance['count_mem_down'] > SCALE_TRESHOLD:
                        instance['count_mem_down'] = 0
                        if (new_memory > vm_status["min_memory"]):
                            self.call_agent(rabbit_conn, "change_memory", vm_dict, new_memory)
                        else:
                            self.call_agent(rabbit_conn, "change_memory", vm_dict, vm_status["min_memory"])
                
                if (vm_usage["cpu_usage"] > max_vcpu_usage):
                    instance['count_cpu_up'] += 1
                    instance['count_cpu_down'] = 0
                    new_vcpus = vm_status["current_vcpus"] + DELTA_CPU

                    if instance['count_cpu_up'] > SCALE_TRESHOLD:
                        instance['count_cpu_up'] = 0
                        if (new_vcpus < vm_status["max_vcpus"]):
                            self.call_agent(rabbit_conn, "change_cpu", vm_dict, new_vcpus)
                        else:
                            self.call_agent(rabbit_conn, "change_cpu", vm_dict, vm_status["max_vcpus"])
                
                if (vm_usage["cpu_usage"] < min_vcpu_usage):
                    instance['count_cpu_up'] = 0
                    instance['count_cpu_down'] += 1
                    new_vcpus = vm_status["current_vcpus"] - DELTA_CPU

                    if instance['count_cpu_down'] > SCALE_TRESHOLD:
                        instance['count_cpu_down'] = 0
                        if (new_vcpus > vm_status["min_vcpus"]):
                            self.call_agent(rabbit_conn, "change_cpu", vm_dict, new_vcpus)
                        else:
                            self.call_agent(rabbit_conn, "change_cpu", vm_dict, vm_status["min_vcpus"])
        
        if instance['count_scale'] > SCALE_TRESHOLD:
            instance['count_cpu_up'] = 0
            instance['count_cpu_down'] = 0
            instance['count_mem_up'] = 0
            instance['count_mem_down'] = 0
            instance['count_scale'] = 0
        return vm_dict


    def orchestrateV1(self, list_instances, time):
        pass
        # rabbit = Rabbit()
        # for instance in list_instances:
        #     self.orchestrate_instance(instance, time, rabbit)


    def __check_availability(self, flavor, hypervisor):
        if(flavor.disk + hypervisor["disk_used_gb"] < hypervisor["free_disk_gb"] and
           flavor.ram + hypervisor["mem_used_mb"] < hypervisor["free_memory_mb"] and
           flavor.vcpus + hypervisor["vcpus_used"] < hypervisor["vcpus"]*2):
           return True
        else:
            return False


    def __check_possibility(self, current_hyper, new_hyper, flavor):
        if(new_hyper["free_disk_gb"] < current_hyper["disk_used_gb"] - flavor.disk or
           new_hyper["free_memory_mb"] < current_hyper["mem_used_mb"] - flavor.ram or
           new_hyper["vcpus"]*2 < current_hyper["vcpus_used"] - flavor.vcpus):
            return True
        else:
            return False
        

    def verify_migration(self, instance_name):
        # parameter is not a instance name. Now it's a dictionary of the instance. Need to change this method.

        # instance = self.cloud.get_server(instance_name)
        # instance_flavor = self.cloud.get_flavor(instance.flavor.id)
        # hypervisors_status = self.hypervisors_status()

        # migrate_to = instance["OS-EXT-SRV-ATTR:hypervisor_hostname"]

        # for hyper in hypervisors_status["status_per_host"]:
        #     if instance["OS-EXT-SRV-ATTR:hypervisor_hostname"] == hyper["hostname"]:
        #         current_host = hyper

        # for hyper in hypervisors_status["status_per_host"]:
        #     available = self.__check_availability(instance_flavor, hyper)
        #     possible = self.__check_possibility(current_host, hyper, instance_flavor)
        #     if(available and possible):
        #         migrate_to = hyper["hostname"]
        
        # return migrate_to
        pass


    def orchestrate_thread(self, instance, index, result):
        thread_exec = dict()
        thread_exec["name"] = instance['name']
        thread_exec["project_id"] = instance['project_id']
        thread_exec["initial_register_thread"] = float(time.time())
        thread_exec["initial_register_thread"] = float(time.time())

        # vm_dict = self.get_instance(instance)
        vm_dict = self.orchestrate_instance(instance)
        thread_exec["final_register_thread"] = float(time.time())

        if vm_dict:
            vm_status = vm_dict['status']
            vm_usage = vm_dict['usage']
            
            thread_exec['count_cpu_up'] = instance['count_cpu_up']
            thread_exec['count_cpu_down'] = instance['count_cpu_down']
            thread_exec['count_mem_up'] = instance['count_mem_up']
            thread_exec['count_mem_down'] = instance['count_mem_down']
            thread_exec['count_scale'] = instance['count_scale']

            if vm_status and vm_usage:
                thread_exec["cpu_usage"] = vm_usage['cpu_usage']
                thread_exec["current_vcpus"] = vm_status['current_vcpus']
                thread_exec["max_vcpus"] = vm_status['max_vcpus']
                thread_exec["min_vcpus"] = vm_status['min_vcpus']

                thread_exec["mem_usage"] = vm_usage['mem_usage']
                thread_exec["current_memory"] = vm_status['current_memory']
                thread_exec["max_memory"] = vm_status['max_memory']
                thread_exec["min_memory"] = vm_status['min_memory']

                # instance['rabbit_conn'].send_message(instance['project_id'], json.dumps(thread_exec))
                # thread_exec["migrate_instance"] = self.verify_migration(instance_name)
        else:
            self.logger.warning("Instance '{0}' from project '{1}' does not exist. It will be removed".format(instance['name'], 
                                                                                                              instance['project_id']))
            self.remove_instance(instance)
        result[index] = thread_exec


    def orchestrateV2(self, list_instance):
        list_size = len(list_instance)
        thread_list = [None] * list_size
        results = [None] * list_size

        for i in range(list_size):
            thread_list[i] = threading.Thread(target=self.orchestrate_thread, args=(list_instance[i], i, results, ))
            thread_list[i].start()
        
        for i in range(len(thread_list)):
            thread_list[i].join()
        
        # results.sort(key=lambda k: (k["final_register_thread"] - k["initial_register_thread"]))

        allow = 0
        try:
            with open (ALLOW_OUPUT, 'r') as file_input:
                raw_text = file_input.readlines()[0]
                allow = int(raw_text)
        except Exception as e:
            self.logger.warning("Unable to write instance result to file: {0}".format(e))
            pass

        log_status = 'The following instances are being scaled:\n'
        for result in results:
            result_str = json.dumps(result)
            result_str += "\n"
            log_status += result_str
            if allow:
                self.file_output_scaler.write(result_str)
                self.file_output_scaler.flush()
        self.logger.info(log_status)


    def run_scaler(self):
        client_conn = RabbitClient()
        while True:
            client_conn.read_client_queue()
            self.update_orchestrate_list(client_conn.response)

            if self.allow_orchestrate:
                self.orchestrateV2(self.instances.values())
            time.sleep(CONTROL_LOOP_TIME)


def main():
    scaler = AutoScaler()
    scaler.run_scaler()


if __name__ == "__main__":
    main()
