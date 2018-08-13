import time, logging, sys, csv, signal, ads1256
from pimonitor.PM import PM
from pimonitor.PMConnection import PMConnection
from pimonitor.PMDemoConnection import PMDemoConnection
from pimonitor.PMXmlParser import PMXmlParser

log_and_csv_name_ts = time.time()

logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
logger = logging.getLogger()

fileHandler = logging.FileHandler('/media/datalogs/pimonitor-log/{}.log'.format(log_and_csv_name_ts))
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)

logger.setLevel(logging.DEBUG)
foo = PM()
foo.set(logger)

logger.info('Lets do this!')

csv_file = open('/media/datalogs/pimonitor-log/{}.csv'.format(log_and_csv_name_ts), 'w')
writer = csv.writer(csv_file)

# TODO: Maybe pickle the parameters. Does it load faster?
parser = PMXmlParser()
defined_parameters = parser.parse("logger_STD_EN_v336.xml")
logger.info('-----------------------------------------------------------------------')
logger.info('Defined Parameters')
logger.info('-----------------------------------------------------------------------')
for p in defined_parameters:
    logger.info(p.to_string())

connection = PMConnection()
# connection = PMDemoConnection()

def graceful_shutdown(signal, frame):
    logger.info('Got a shutdown signal!')
    if connection:
        connection.close()

    if csv_file:
        csv_file.close()

    ads1256.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

# All done with the ssm and system stuff, time for the ADC
# 1 gain, 25 samples per second
# Voltage to PSI for Audax 0-100psi sensor
# https://www.omega.com/techref/das/scaling.html
# =(((100/4.5)*E2)-(100/4.5)/2)
ads1256.start("1", "25")

adc_values   = [0,0,0,0,0,0,0,0]
adc_voltages = [0,0,0,0,0,0,0,0]

audax_scaling_factor = 100/4

def scale_adc(voltage):
    return ((audax_scaling_factor*voltage)-audax_scaling_factor/2)

while True:
    try:
        supported_parameters = []
        selected_parameters = []
        connection.open()
        ecu_packet = connection.init(1)
        tcu_packet = connection.init(2)

        if ecu_packet == None or tcu_packet == None:
            logger.warning("Oops, can't initialize the ECU or TCU!")
            continue;

        # Negotiate with the ECU to determine which defined_parameters are
        # actually supported by this car.
        for p in defined_parameters:
            if (p.get_target() & 0x1 == 0x1) and p.is_supported(ecu_packet.to_bytes()[5:]):
                if not filter(lambda x: x.get_id() == p.get_id(), supported_parameters):
                    supported_parameters.append(p)

        # Negotiate with the TCU to determine which defined_parameters are
        # actually supported by this car.
        for p in defined_parameters:
            if ((p.get_target() & 0x2 == 0x2) or (p.get_target() & 0x1 == 0x1)) and p.is_supported(tcu_packet.to_bytes()[5:]):
                if not filter(lambda x: x.get_id() == p.get_id(), supported_parameters):
                    supported_parameters.append(p)

        # Now that we have a definitive list of parameters which we want to log,
        # we'll check them for dependencies. Some parameters require other parameters
        # in order to be calculated properly.
        for p in defined_parameters:
            p_deps = p.get_dependencies();
            if not p_deps:
                continue

            deps_found = ()
            for dep in p_deps:
                deps_found = filter(lambda x: x.get_id() == dep, supported_parameters)
                if not deps_found:
                    break

                if len(deps_found) > 1:
                    raise Exception('duplicated dependencies', deps_found)

                p.add_parameter(deps_found[0])

            if deps_found:
                supported_parameters.append(p)

        # This was copy/pasted directly from PMMain.py, and I'm not sure why it's
        # useful..
        # each ID must be in a form P01 - first letter, then a number
        # This also does not work with the latest logger definition file, which
        # contains IDs which are prefixed with "P" and "PID"
        # supported_parameters.sort(key=lambda p: int(p.get_id()[1:]), reverse=False)

        desired_pids = [
            "P3", # Param: id=P3, name=A/F Correction #1, desc=P3, byte=8, bit=5, target=1, conversions=[[u'%', u'(x-128)*100/128', u'0.00']], address=0x9[1]
            "P4", # Param: id=P4, name=A/F Learning #1, desc=P4, byte=8, bit=4, target=1, conversions=[[u'%', u'(x-128)*100/128', u'0.00']], address=0xa[1]
            "P7", # Param: id=P7, name=Manifold Absolute Pressure, desc=P7-Pressure value calculated from the manifold absolute pressure sensor (absolute value), byte=8, bit=1, target=1, conversions=[[u'psi', u'x*37/255', u'0.00'], [u'bar',     u'x/100', u'0.000'], [u'kPa', u'x', u'0'], [u'hPa', u'x*10', u'0'], [u'inHg', u'x*0.2953', u'0.00'], [u'mmHg', u'x*7.5', u'0']], address=0xd[1]
            "P8", # Param: id=P8, name=Engine Speed, desc=P8, byte=8, bit=0, target=3, conversions=[[u'rpm', u'x/4', u'0']], address=0xe[2]
            "P10", # Param: id=P10, name=Ignition Total Timing, desc=P10, byte=9, bit=6, target=1, conversions=[[u'degrees', u'(x-128)/2', u'0.00']], address=0x11[1]
            # "P11", # Param: id=P11, name=Intake Air Temperature, desc=P11, byte=9, bit=5, target=1, conversions=[[u'F', u'32+9*(x-40)/5', u'0'], [u'C', u'x-40', u'0']], address=0x12[1]
            "P12", # Param: id=P12, name=Mass Airflow, desc=P12, byte=9, bit=4, target=1, conversions=[[u'g/s', u'x/100', u'0.00']], address=0x13[2]
            # "P13", NOTE: This appears to always be 100.0 ? # Param: id=P13, name=Throttle Opening Angle, desc=P13-Engine throttle opening angle., byte=9, bit=3, target=1, conversions=[[u'%', u'x*100/255', u'0.00']], address=0x15[1]
            "P17", # Param: id=P17, name=Battery Voltage, desc=P17, byte=10, bit=7, target=3, conversions=[[u'V', u'x*8/100', u'0.00']], address=0x1c[1]
            "P21", # Param: id=P21, name=Fuel Injector #1 Pulse Width, desc=P21-This parameter includes injector latency., byte=10, bit=3, target=1, conversions=[[u'ms', u'x*256/1000', u'0.00'], [u'\xb5s', u'x*256', u'0.00']], address=0x20[1]
            "P23", # Param: id=P23, name=Knock Correction Advance, desc=P23-Retard amount when knocking has occurred. Partial learned value of the learned ignition timing., byte=10, bit=1, target=1, conversions=[[u'degrees', u'(x-128)/2', u'    0.00']], address=0x22[1]
            "P30", # Param: id=P30, name=Accelerator Pedal Angle, desc=P30-Accelerator pedal angle., byte=11, bit=2, target=3, conversions=[[u'%', u'x*100/255', u'0.00']], address=0x29[1]
            # "P36", # Param: id=P36, name=Primary Wastegate Duty Cycle, desc=P36-Trubo Control Valve Duty Cycle, byte=12, bit=3, target=1, conversions=[[u'%', u'x*100/255', u'0.00']], address=0x30[1]
            "P39", # Param: id=P39, name=Tumble Valve Position Sensor Right, desc=P39, byte=12, bit=0, target=1, conversions=[[u'V', u'x/50', u'0.00']], address=0x33[1]
            "P40", # Param: id=P40, name=Tumble Valve Position Sensor Left, desc=P40, byte=13, bit=7, target=1, conversions=[[u'V', u'x/50', u'0.00']], address=0x34[1]
            "P47", # Param: id=P47, name=Fuel Pump Duty, desc=P47, byte=13, bit=0, target=1, conversions=[[u'%', u'x*100/255', u'0.00']], address=0x3b[1]
            "P48", # Param: id=P48, name=Intake VVT Advance Angle Right, desc=P48, byte=14, bit=7, target=1, conversions=[[u'degrees', u'x-50', u'0']], address=0x3c[1]
            "P49", # Param: id=P49, name=Intake VVT Advance Angle Left, desc=P49, byte=14, bit=6, target=1, conversions=[[u'degrees', u'x-50', u'0']], address=0x3d[1]
            "P58", # Param: id=P58, name=A/F Sensor #1, desc=P58, byte=15, bit=5, target=1, conversions=[[u'AFR', u'x/128*14.7', u'0.00'], [u'Lambda', u'x/128', u'0.00']], address=0x46[1]
            "P153", # Param: id=P153, name=Learned Ignition Timing Correction, desc=P153-Value of only the whole learning value in the ignition timing learning value., byte=55, bit=1, target=1, conversions=[[u'degrees', u'x/16', u'0.0']], add    ress=0xf9[1]
            # "P156", # Param: id=P156, name=Final Injection Amount, desc=P156, byte=60, bit=6, target=1, conversions=[[u'mm\xb3/st', u'x/256', u'0.0000']], address=0x1e2[2]
            "P158", # Param: id=P158, name=Target Intake Manifold Pressure, desc=P158, byte=60, bit=4, target=1, conversions=[[u'psi', u'x*0.1450377', u'0.000'], [u'kPa', u'x', u'0'], [u'hPa', u'x*10', u'0'], [u'bar', u'x*0.01', u'0.00']], ad    dress=0x1e5[1]
            # "P166", # Param: id=P166, name=Intake Air Temperature (combined), desc=P166, byte=61, bit=4, target=1, conversions=[[u'F', u'32+9*(x-40)/5', u'0'], [u'C', u'x-40', u'0']], address=0x1ed[1]
            "P165", # Param: id=P165, name=Common Rail Pressure, desc=P165, byte=61, bit=5, target=1, conversions=[[u'psi', u'x*145.0377', u'0'], [u'MPa', u'x', u'0'], [u'bar', u'x*10', u'0']], address=0x1ec[1]
            "P167", # Param: id=P167, name=Target Engine Speed, desc=P167, byte=61, bit=3, target=1, conversions=[[u'rpm', u'x/4', u'0']], address=0x1ee[2]
            # "P201", # Param: id=P201, name=Injector Duty Cycle, desc=P201-IDC as calculated from RPM and injector PW., byte=none, bit=none, target=1, conversions=[[u'%', u'(P8*[P21:ms])/1200', u'0.00']], address=0x0[0]

            "PID2E", # Param: id=PID2E, name=EVAP Commanded Purge, desc=PID2E-Commanded evaporative purge control percent, byte=13, bit=2, target=1, conversions=[[u'%', u'x*100/255', u'0.00']], address=0x2e[1]
            "PID32", # Param: id=PID32, name=EVAP System Vapor Pressure, desc=PID32-Evaporative system vapor pressure from a sensor in fuel tank or vapor line, byte=14, bit=6, target=1, conversions=[[u'psi', u'x*0.0000362594345', u'0.000000'],     [u'Pa', u'x/4', u'0'], [u'bar', u'x*0.0000025', u'0.000000']], address=0x32[1]
            "PID53", # Param: id=PID53, name=EVAP System Vapor Pressure (Absolute), desc=PID53-Evaporative system vapor pressure from a sensor in fuel tank or vapor line, byte=18, bit=5, target=1, conversions=[[u'psi', u'x*0.005*37/255', u'0.0    0'], [u'kPa', u'x*0.005', u'0'], [u'bar', u'x*0.00005', u'0.00000']], address=0x53[1]
        ]

        logger.info('-----------------------------------------------------------------------')
        logger.info('Intersection of Defined, and Supported Parameters')
        logger.info('-----------------------------------------------------------------------')

        selected_parameters = []
        added_ids = []
        # selected_parameters = supported_parameters
        for p in supported_parameters:
            logger.info(p.to_string())
            pid = p.get_id()
            if pid not in added_ids and pid in desired_pids:
                added_ids.append(pid)
                selected_parameters.append(p)

        logger.info('-----------------------------------------------------------------------')
        logger.info('Intersection of Defined, Supported, and Selected Parameters')
        logger.info('-----------------------------------------------------------------------')
        csv_header = ['unix_timestamp']
        for p in selected_parameters:
            name = p.get_name()
            csv_header.append(name)
            logger.info(p.to_string())

        for i in range(0,8):
            csv_header.append('ADC{}'.format(i))

        csv_header.append('Fuel Pressure (PSI)')

        writer.writerow(csv_header)

        while True:
            # Jun 28 06:25:55 raspberrypi python[440]: Traceback (most recent call last):
            # Jun 28 06:25:55 raspberrypi python[440]:   File "/home/pi/devel/PiMonitor/pimonitor/PMLog.py", line 130, in <module>
            # Jun 28 06:25:55 raspberrypi python[440]:     packets = connection.read_parameters(selected_parameters)
            # Jun 28 06:25:55 raspberrypi python[440]:   File "/home/pi/devel/PiMonitor/pimonitor/PMConnection.py", line 104, in read_parameters
            # Jun 28 06:25:55 raspberrypi python[440]:     raise Exception('connection', "targets differ: " + str(target) + " vs " + str(parameter.get_target()))
            # Jun 28 06:25:55 raspberrypi python[440]: Exception: ('connection', 'targets differ: 1 vs 2')
            logger.info('Fetching SSM values')
            # Grabbing all the packets at once seems broken, and there's a TODO in the comments just above it.
            # So we're going to iterate over all of them individually.
            # packets = connection.read_parameters(selected_parameters)
            ts = time.time()
            row = [ts]
            # Fetch the SSM values
            idx = 0
            for p in selected_parameters:
                packet = connection.read_parameter(p)
                row.append(p.get_value(packet))
                idx = idx +1

            # Fetch the ADC values
            logger.info('Fetching ADC values')
            adc_values = ads1256.read_all_channels()
            logger.info('Processing ADC values')
            for i in range(0, 8):
                adc_voltage = (((adc_values[i] * 100) /167.0)/1)/1000000.0
                # adc_voltages[i] = scale_adc(adc_voltage)
                adc_voltages[i] = adc_voltage

            row.extend(adc_voltages)
            row.append(scale_adc(adc_voltages[2]))

            writer.writerow(row)
            csv_file.flush()

        #break; # Remove this because in the car we'll want to keep trying to connect to the ECU

    except IOError as e:
		print('I/O error: {0} {1}'.format(e.errno, e.strerror))
		if connection != None:
			connection.close()
			time.sleep(3)
        # if csv_file != None:
        #     csv_file.close()
		continue
