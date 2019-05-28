# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#CONSTANTS USED FOR BROKER
#Upper and lower limits of memory usage.
MEM_UPPER_USAGE=70.0
MEM_LOWER_USAGE=30.0

#Upper and lower limits of CPU usage.
CPU_UPPER_USAGE=75.0
CPU_LOWER_USAGE=25.0

#Delta steps for CPU and memory scale up/down
DELTA_CPU=1
DELTA_MEM=524288

#Counters to control when the scale will happen.
SCALE_TRESHOLD = 3
CONTROL_LOOP_TIME = 1

#LOGGING FOR SCALER
LOGGER_NAME = 'Scaler.VertScaler'
LOG_FILE_NAME = '/var/log/scaler-vertscaler.log'
SCALER_RESPONSE_OUTPUT = '/home/ubuntu/Orchestrator-OS/Scaler/AutoScaler/response_scaler'
ALLOW_OUPUT = '/home/ubuntu/Orchestrator-OS/Scaler/AutoScaler/allow_output'
# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
