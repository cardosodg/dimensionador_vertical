#https://gnocchi.xyz/gnocchiclient/api.html

import json
import shade
import os
import datetime

from keystoneauth1.identity import v3
from keystoneauth1 import session
from gnocchiclient.v1 import client




class Gnocchi():
    def __init__(self, cloud_name):
        self.cloud = shade.openstack_cloud(cloud=cloud_name)
        self.auth_dict = self.cloud.auth
        #Import credentials witch clouds.yml
        self.auth = v3.Password(auth_url=str(self.auth_dict['auth_url']),
                           username=str(self.auth_dict['username']),
                           password=str(self.auth_dict['password']),
                           project_name=str(self.auth_dict['project_name']),
                           user_domain_id=str(self.auth_dict['user_domain_id']),
                           project_domain_id=str(self.auth_dict['project_domain_id']))
        self.sess = session.Session(auth=self.auth,verify='/path/to/ca.cert')
        #Open a session with credentials clouds.yml
        self.gnocchi_client = client.Client(session=self.sess)

    '''Get Metric memory_usage (MB)
    Argumentos: resource_id(Identification VM)
                start (beginning of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                stop (end of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                granularity in format integer(granularity to retrieve (in seconds)) 
    '''
    def get_metric_memory_usage(self,resource_id,start,stop,granularity):
        meters = self.gnocchi_client.metric.get_measures('memory.usage',
                                                           start=start,
                                                           stop=stop,
                                                           resource_id=resource_id,
                                                           granularity=granularity)

        meters_div = len(meters) * 60/100
        previous_meters = meters[:meters_div]
        current_meters = meters[meters_div:]
        sum_previous = 0.0
        mean_previous = 0.0
        size_previous = 0
        sum_current = 0.0
        mean_current = 0.0
        size_current = 0
        for item in previous_meters:
            sum_previous += item[2]
            size_previous += 1
        for item in current_meters:
            sum_current += item[2]
            size_current += 1
        mean_previous = (sum_previous * 0.30)/size_previous
        mean_current = (sum_current * 0.70)/size_current
        usage = (mean_previous) + (mean_current)
        return usage

    '''Get Metric CPU Utilization(%)
        Arguments: resource_id(Identification Virtual Machine)
                    start (beginning of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                    stop (end of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                    granularity in format integer(granularity to retrieve (in seconds))
        Output: Return a list measures              
        '''
    def get_metric_cpu_utilization(self,resource_id,start,stop,granularity):
        meters = self.gnocchi_client.metric.get_measures('cpu_util',
                                                           start=start,
                                                           stop=stop,
                                                           resource_id=resource_id,
                                                           granularity=granularity)

        meters_div = len(meters) * 60/100
        previous_meters = meters[:meters_div]
        current_meters = meters[meters_div:]
        sum_previous = 0.0
        mean_previous = 0.0
        size_previous = 0
        sum_current = 0.0
        mean_current = 0.0
        size_current = 0
        for item in previous_meters:
            if item[2] < 120.0 and item[2] >= 0:
                sum_previous += item[2]
                size_previous += 1
        for item in current_meters:
            if item[2] < 120.0 and item[2] >= 0:
                sum_current += item[2]
                size_current += 1
        mean_previous = (sum_previous * 0.30)/size_previous
        mean_current = (sum_current * 0.70)/size_current
        usage = (mean_previous) + (mean_current)
        return usage

    '''Get Metric Network Incoming(Bytes)
            Arguments: resource_id(Identification Resource id network)
                        start (beginning of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                        stop (end of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                        granularity in format integer(granularity to retrieve (in seconds))
            Output: Return a list(cumulative) with input bytes'''
    def get_metric_network_incoming(self,resource_id,start,stop,granularity):
        meter = self.gnocchi_client.metric.get_measures('network.incoming.bytes',
                                                           start=start,
                                                           stop=stop,
                                                           resource_id=resource_id,
                                                           granularity=granularity)
        return meter

    '''Get Metric Network Outgoing(Bytes)
                Arguments: resource_id(Identification Resource id network)
                            start (beginning of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                            stop (end of the period) in format timestamp (YYYY-MM-DDTHH:MM:SS+00:00);
                            granularity in format integer(granularity to retrieve (in seconds))
                Output: Return a list(cumulative) with output bytes  '''
    def get_metric_network_outgoing(self,resource_id,start,stop,granularity):
        meter = self.gnocchi_client.metric.get_measures('network.outgoing.bytes',
                                                           start=start,
                                                           stop=stop,
                                                           resource_id=resource_id,
                                                           granularity=granularity)
        return meter
    '''List meters
        Arguments: resource_id(Identification Virtual Machine) 
        Output: returns a list of metrics associated with the resource_id
        '''
    def get_list_meters(self,resource_id):
        list_meters = self.gnocchi_client.resource.get(resource_type='generic',resource_id=resource_id)
        return list_meters['metrics']

    '''Get resource_id_network
        Arguments: instance_id, resource_id(Identification Virtual Machine) 
        Output: returns a resource_id_network associated with the specified resource_id 
        '''
    def get_resource_network(self,resource_inst_id):
        list_meters = self.gnocchi_client.resource.list(resource_type='instance_network_interface')
        #print resource_inst_id
        for it in list_meters:
            #print resource_inst_id[0:len(resource_inst_id)+3]
            if it['original_resource_id'][0:len(resource_inst_id)] == resource_inst_id:
                return it['id']
                #print 'foi'

'''List meters
            Arguments: name_meter(Name of metric, for example memory_usage),
                       list_meter(A list of metric with value,timestamp and granularity),
                       directory(Directory for save the json),
                       fps(quantity of the fps in camera),
                       name_VM(name Virtual Machine) 
                        
            Output: Save in format json a metric required in all VMs
            '''
def save_meter_in_json(name_meter,list_meter, directory,fps,name_VM):

    dic_memory_usage = {}
    list = []
    if not os.path.exists(directory + fps +'/'+str(name_VM)+'/'):
        os.makedirs(directory + fps +'/'+str(name_VM)+'/')

    # Storage informations in files json, for example vm1_memory_usage.json
    for it_memory in list_meter:
        # Transform datetime for timestamp
        dic_memory_usage = {}
        dic_memory_usage['timestamp'] = str(datetime.datetime.fromtimestamp(float(it_memory[0].strftime('%s'))))
        dic_memory_usage['value'] = it_memory[2]
        # print it[0]
        dic_memory_usage['granulariy'] = it_memory[1]
        # print  it[1]
        #print dic_memory_usage
        list.append(dic_memory_usage)
    #print list
    #print(it['name'])
    dir = str(directory + fps +'/'+str(name_VM)+'/' + name_meter + '.json')

    with open(dir, 'wb') as outfile:
        json.dump(list, outfile, indent=4, separators=(',', ': '))

def main():
    api = Gnocchi('amprod')
    gnocchi = Gnocchi()

    #Salvar Metricas 15 Fps
    fps = '/metricas_Json/exp-ho-10fps-failover-v2'
    directory = os.path.dirname(os.path.abspath(__file__))

    #Verifica se o Diretorio existe
    if not os.path.exists(directory+fps):
        os.makedirs(directory+fps)

    #print(directory+fps)

    servers = gnocchi.cloud.list_servers(all_projects=True)

    server = servers[4]

    instance_id =  server['OS-EXT-SRV-ATTR:instance_name']
    resource_id = server['id']
    id_network = gnocchi.get_resource_network(instance_id+'-'+resource_id)


    #Define start and stop time of the experiment and granularity
    start = '2018-05-18T17:52:24+00:00'
    stop = '2018-05-18T17:54:29+00:00'
    granularity = '1'
    for it in servers:
        ####### Get a list metrics memory_usage for a VM specified

        memory_usage = gnocchi.get_metric_memory_usage(str(it['id']), start,
                                                       stop,granularity)
        #print it['id']
        #Save in file json
        save_meter_in_json('memory_usage', memory_usage, directory, fps, it['name'])
        #
        ####### Get a list metrics memory_usage for a VM specified
        cpu_util = gnocchi.get_metric_cpu_utilization(str(it['id']), start,
                                                       stop,granularity)

        #Save in file json
        save_meter_in_json('cpu_util', cpu_util, directory, fps, it['name'])

        instance_id = it['OS-EXT-SRV-ATTR:instance_name']
        resource_id = it['id']
        id_network = gnocchi.get_resource_network(instance_id + '-' + resource_id)
        print id_network
        ####### Get a list metrics network incoming bytes for a VM specified
        network_incoming_bytes = gnocchi.get_metric_network_incoming(str(id_network),start,
                                                                 stop, granularity)

        # Save in file json
        save_meter_in_json('network_incoming_bytes', network_incoming_bytes, directory, fps, it['name'])

        ####### Get a list metrics network outgoing bytes for a VM specified
        network_outgoing_bytes = gnocchi.get_metric_network_outgoing(str(id_network), start,
                                                                 stop, granularity)
        # Save in file json
        save_meter_in_json('network_outgoing_bytes', network_outgoing_bytes, directory, fps, it['name'])




if __name__ == "__main__":
    main()

