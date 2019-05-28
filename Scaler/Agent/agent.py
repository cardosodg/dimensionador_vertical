import shade
from novaclient import client as Nova
from gnocchi_api import Gnocchi

from constants_agent import *

import pika
import libvirt

import json
import platform
import datetime
import time
import random
from xml.dom import minidom
import logging


class Agent():
    def __init__(self):
        shade.simple_logging(debug=False)
        self.cloud = shade.openstack_cloud(cloud=CLOUD_NAME)
        self.telemetry = Gnocchi(CLOUD_NAME)

        session = self.cloud.auth
        session.update({'version': '2'})
        self.nova_api = Nova.Client(**session)

        self.logger = logging.getLogger(LOGGER_NAME)
        handler = logging.FileHandler(LOG_FILE_NAME)
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s:%(message)s', datefmt='[%Y-%m-%d %H:%M:%S]')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self.switch_call_agent = {
            "find_instance": self.find_instance, #OK
            "change_memory": self.change_memory, #OK
            "change_cpu": self.change_cpu, #OK
            "hypervisor_status": self.hypervisors_status, #OK
            "get_project_status": self.get_project_status, #OK
        }

    def get_project_status(self, project_id):
        project_instances = list()
        project_status = dict()
        max_memory = 0
        current_memory = 0
        max_vcpu = 0
        current_vcpu = 0
        vcpu_percent = 0

        vms = self.cloud.list_servers(all_projects=True, filters={"project_id":project_id})
        for instance in vms:
            project_instances.append(instance['name'])

        for instance_name in project_instances:
            instance = self.find_instance(instance_name, project_id, time=10)

            if instance:
                max_memory += instance['status']['max_memory']
                current_memory += instance['status']['current_memory']

                max_vcpu += instance['status']['max_vcpus']
                current_vcpu += instance['status']['current_vcpus']

        project_status['current_memory'] = current_memory
        project_status['max_memory'] = max_memory
        project_status['current_vcpu'] = current_vcpu
        project_status['max_vcpu'] = max_vcpu

        return project_status

    def migrate_vm(self, instance_name, host_name):
        instance = self.cloud.get_server(name_or_id=instance_name)
        self.nova_api.servers.live_migrate(server=instance.id, host=host_name, block_migration=False, disk_over_commit=False)
        instance = self.cloud.wait_for_server(server=instance)


    def create_instance(self, instance_name, with_disk=False):
        my_flavor = self.cloud.get_flavor(name_or_id=FLAVOR_NAME)
        
        if(with_disk):
            vm = self.cloud.create_server(name=instance_name,
                                          flavor=my_flavor.name,
                                          image=IMAGE_NAME,
                                          network=NETWORK_NAME,
                                          key_name=KEY_NAME,
                                          wait=True,
                                          ip_pool=PROVIDER_NETWORK,
                                          boot_from_volume=True,
                                          terminate_volume=True,
                                          volume_size=str(my_flavor.disk)
                                         )

        else:
            vm = self.cloud.create_server(name=instance_name,
                                          flavor=my_flavor.name,
                                          image=IMAGE_NAME,
                                          network=NETWORK_NAME,
                                          key_name=KEY_NAME,
                                          wait=True,
                                          ip_pool=PROVIDER_NETWORK
                                         )


    def delete_instance(self, instance_name):
        self.cloud.delete_server(name_or_id=instance_name)


    def create_instances(self, list_instances_names, with_disk=False):
        for instance in list_instances_names:
            self.create_instance(instance, with_disk)


    def delete_instances(self, list_instances_names):
        for instance in list_instances_names:
            self.delete_instance(instance)


    def __get_domain_status(self, vm_dict):
        status = dict()
        
        try:
            conn = libvirt.open(CONNECTION_LIBVIRT_TEMPLATE.format(vm_dict["host_name"]))
            dom = conn.lookupByName(vm_dict["libvirt_name"])

            raw_xml = dom.XMLDesc(flags=libvirt.VIR_DOMAIN_XML_INACTIVE)
            xml = minidom.parseString(raw_xml)
            vcpu_tag = xml.getElementsByTagName('vcpu')[0]

            if vcpu_tag.hasAttribute('current'):
                status["current_vcpus"] = int(vcpu_tag.attributes['current'].value)
            else:
                status["current_vcpus"] = int(vcpu_tag.firstChild.nodeValue)
            
            status["max_vcpus"] = int(vcpu_tag.firstChild.nodeValue)
            status["min_vcpus"] = int(MINIMAL_CPU)

            info = dom.info()
            status["max_memory"] = int(info[1])
            status["current_memory"] = int(info[2])
            status["min_memory"] = int(MINIMAL_MEM)
            conn.close()

        except Exception as e:
            error = "GET DOMAIN could not find domain status. Maybe the domain was deleted or moved from hypervisor. ERROR: "
            error += str(e)
            self.logger.error(error)
        
        return status


    def __get_metric_cpu(self, instance_id, max_vcpus, current_vcpus, time):
        stop = datetime.datetime.utcnow()
        start = (stop - datetime.timedelta(seconds=time))

        cpu_usage = self.telemetry.get_metric_cpu_utilization(instance_id, start.isoformat(), stop.isoformat(), 1)
        return cpu_usage


    def __get_metric_mem(self, instance_id, current_memory, time):
        stop = datetime.datetime.utcnow()
        start = (stop - datetime.timedelta(seconds=time))

        mem_metric = self.telemetry.get_metric_memory_usage(instance_id, start.isoformat(), stop.isoformat(), 1)
        mem_usage = (float(mem_metric*1024)/current_memory)*100
        return mem_usage


    def __get_instance_usage(self, vm_dict, domain_dict, time):
        usage = dict()
        try:
            usage["mem_usage"] = self.__get_metric_mem(vm_dict["id"], domain_dict["current_memory"], time)
            usage["cpu_usage"] = self.__get_metric_cpu(vm_dict["id"], domain_dict["max_vcpus"], domain_dict["current_vcpus"], time)
        except Exception as e:
            error = "ERROR IN READING MEMORY AND/OR CPU USAGE. ERROR: "
            error += str(e)
            self.logger.error(error)
        return usage


    def find_instance(self, instance_name, project_id, time):
        vm_dict = dict()
        vm = self.cloud.get_server(name_or_id=instance_name, all_projects=True, filters={'project_id': project_id})
        if vm is not None:
             flavor = self.cloud.get_flavor(name_or_id=vm.flavor.id)
        
             vm_dict["instance_name"] = vm.name
             vm_dict["id"] = vm.id
             vm_dict["libvirt_name"] = vm.properties['OS-EXT-SRV-ATTR:instance_name']
             vm_dict["host_name"] = vm.properties['OS-EXT-SRV-ATTR:host']
             vm_dict["flavor"] = flavor

             status = self.__get_domain_status(vm_dict)
             usage = self.__get_instance_usage(vm_dict, status, time)

             vm_dict["status"] = status
             vm_dict["usage"] = usage
        
        return vm_dict


    def change_memory(self, vm_dict, memory):
        try:
            conn = libvirt.open(CONNECTION_LIBVIRT_TEMPLATE.format(vm_dict["host_name"]))
            dom = conn.lookupByName(vm_dict["libvirt_name"])
            dom.setMemoryFlags(memory=memory, flags=libvirt.VIR_DOMAIN_AFFECT_LIVE)    
            conn.close()

        except Exception as e:
            error = "Could not change memory of domain. Maybe the domain was deleted or moved from hypervisor. ERROR: "
            error += str(e)
            self.logger.error(error)
        
        return "Memory of VM '{0}' ({1}) changed in host '{2}'.".format(vm_dict["instance_name"], vm_dict["libvirt_name"], vm_dict["host_name"])


    def change_cpu(self, vm_dict, ncpus):
        try:
            conn = libvirt.open(CONNECTION_LIBVIRT_TEMPLATE.format(vm_dict["host_name"]))
            dom = conn.lookupByName(vm_dict["libvirt_name"])
            dom.setVcpusFlags(nvcpus=ncpus, flags=libvirt.VIR_DOMAIN_VCPU_GUEST)
            dom.setVcpusFlags(nvcpus=ncpus, flags=libvirt.VIR_DOMAIN_AFFECT_CONFIG)
            conn.close()

        except Exception as e:
            error = "Could not change CPU of domain. Maybe the domain was deleted or moved from hypervisor. ERROR: "
            error += str(e)
            self.logger.error(error)

        return "VCPU of VM '{0}' ({1}) changed in host '{2}'.".format(vm_dict["instance_name"], vm_dict["libvirt_name"], vm_dict["host_name"])


    def change_flavor(self, instance_name, flavor_name):
        instance = self.cloud.get_server(name_or_id=instance_name)

        new_flavor = self.cloud.get_flavor(name_or_id=flavor_name)

        try:
            self.nova_api.servers.resize(server=instance.id, flavor=new_flavor.id)

            instance = self.cloud.get_server(instance.id)
            while ("VERIFY_RESIZE" not in instance.status):
                time.sleep(2)
                instance = self.cloud.get_server(instance.id)

            self.nova_api.servers.confirm_resize(server=instance.id)

            instance = self.cloud.get_server(name_or_id=instance.id)
        except BaseException as e:
            error = str(e)
            self.logger.error(error)


    def hypervisors_status(self):
        hypervisors = self.cloud.list_hypervisors()
        cloud_status = dict(free_memory_mb=0,
                            free_vcpus=0,
                            free_disk_gb=0,
                            mem_used_mb=0,
                            vcpus_used=0,
                            disk_used_gb=0,
                            vcpus=0,
                            status_per_host=[]
                            )
        
        for host in hypervisors:
            host_status = dict(hostname='',
                               free_memory_mb=0,
                               free_vcpus=0,
                               free_disk_gb=0,
                               mem_used_mb=0,
                               vcpus_used=0,
                               disk_used_gb=0,
                               vcpus=0
                              )
            
            host_status["hostname"] = host.hypervisor_hostname

            free_vcpus = (host["vcpus"] - host["vcpus_used"])
            if (free_vcpus < 0):
                free_vcpus = 0

            cloud_status["free_memory_mb"], host_status["free_memory_mb"] = cloud_status["free_memory_mb"] + host["free_ram_mb"], host["free_ram_mb"]
            cloud_status["free_disk_gb"], host_status["free_disk_gb"] = cloud_status["free_disk_gb"] + host["disk_available_least"], host["disk_available_least"]
            cloud_status["free_vcpus"], host_status["free_vcpus"] = cloud_status["free_vcpus"] + free_vcpus, free_vcpus
            cloud_status["mem_used_mb"], host_status["mem_used_mb"] = cloud_status["mem_used_mb"] + host["memory_mb_used"], host["memory_mb_used"]
            cloud_status["vcpus_used"], host_status["vcpus_used"] = cloud_status["vcpus_used"] + host["vcpus_used"], host["vcpus_used"]
            cloud_status["disk_used_gb"], host_status["disk_used_gb"] = cloud_status["disk_used_gb"] + host["local_gb_used"], host["local_gb_used"]
            cloud_status["vcpus"], host_status["vcpus"] = cloud_status["vcpus"] + host["vcpus"], host["vcpus"]

            cloud_status["status_per_host"].append(host_status)
        
        return cloud_status


    def default_agent_response(self, *args):
        return "Agent cannot recognize command."


    def run(self, message_dict):
        response = ""
        exec_command = self.switch_call_agent.get(message_dict["command"], self.default_agent_response)
        response = exec_command(*message_dict["parameters"])
        return response


    def on_request(self, ch, method, props, body):
        message_dict = json.loads(body)

        self.logger.info("message received: {0}".format(message_dict))

        response = self.run(message_dict)
        message_dict.update({'result': response})

        self.logger.info("message sent: {0}".format(message_dict))

        ch.basic_publish(exchange='',
                        routing_key=props.reply_to,
                        body=json.dumps(message_dict))
        ch.basic_ack(delivery_tag = method.delivery_tag)


    def run_agent(self):

        while True:
            try:
                credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWD)
                parameters = pika.ConnectionParameters(RABBIT_IP, RABBIT_PORT, '/', credentials)
                connection = pika.BlockingConnection(parameters)
                channel = connection.channel()

                channel.queue_declare(queue=RABBIT_SCALER_QUEUE)

                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(self.on_request, queue=RABBIT_SCALER_QUEUE)

                self.logger.info("Agent ready.")
                channel.start_consuming()

            except Exception as e:
                error = str(e)
                error += " trying again in 10 seconds."
                self.logger.error(error)
                time.sleep(10)


def main():
    agent = Agent()
    agent.run_agent()

if __name__ == "__main__":
    main()
