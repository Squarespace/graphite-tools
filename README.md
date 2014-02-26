graphite-tools
==============

Tools for the Graphite project

##Check Graphite

Once many of the application and system level metrics are stored in Graphite, it becomes useful to set up alarms on those metrics. For example, if the CPU usage percentage is above 85% at a particular host, we might want to be proactive and take action before something bad happens. Similarly, if the total number of requests drops considerably, we should also take action. There are a couple of steps involved in order to set all of this up. This page describes a script that queries Graphite for a specific metric and determines whether or not the metric's value is breaching a threshold. This script can then be hooked up to Nagios to take any corresponding action (i.e. send email, publish HipChat message, page someone).

###Script & Syntax

The check_graphite script accepts the following options:

	$ ./check_graphite
	Usage: check_graphite [options]
      -u, --url URL                    The Graphite installation url
      -m, --metric NAME                The metric string
      -t, --timeInterval TIMEINTERVAL  Time interval, in seconds, at which the metric is published (default: 10)
      -p, --datapoints DATAPOINTS      Number of datapoints to check (default: 3)
      -s, --skipDatapoints SKIP        Number of datapoints to skip in case of metrics lags (default: 0)
      -a, --alarmThreshold THRESHOLD   Number of breaching datapoints before alarming (default: 3)
      -w, --warning VALUE              Warning threshold
      -c, --critical VALUE             Critical threshold
      -v, --verbose                    Enable debug logging
      -h, --help                       Display this screen

As an example, we could query for the following (in verbose mode):

	$ ./check_graphite -u http://graphite-installation -m "aliasByNode(PRODUCTION.all.requests.m1_rate,2,3)" -t 10 -p 10 -a 3 -w 835 -c 850 -v
	http://graphite-installation/render/?target=aliasByNode(PRODUCTION.all.requests.m1_rate,2,3)&format=json&from=-120s&until=-20s
	[886.4499999999997, 1386456320]
	[893.5599999999997, 1386456330]
	[896.4499999999998, 1386456340]
	[897.0999999999999, 1386456350]
	[896.0399999999998, 1386456360]
	[896.0299999999997, 1386456370]
	[897.9199999999998, 1386456380]
	[901.9699999999996, 1386456390]
	[907.5999999999998, 1386456400]
	[876.12, 1386456410]
	Processed 10 datapoints - OK: 0, WARNING: 10, CRITICAL: 10
	CRITICAL 10 breaches out of 10 datapoints

###What does it do?

	-u: http://graphite-installation
		The URL of the Graphite installation
	-m: "aliasByNode(PRODUCTION.all.requests.m1_rate,2,3)" 
		The name of the metric. It can include any of the functions supported by Graphite (i.e. scale(), aliasByNode())
	-t: 10 
		How frequently values are published for this metric. For example, every 10s, 60s, etc.
	-p: 10 
		How many datapoints should be checked. For example, if -t is set to 10 and -p is set to 10, the script would check the past 100 seconds to get 10 datapoints.
	-a: 3 
		If we are checking for 10 datapoints and a is set to 3, the script will alarm if at least 3 of the datapoints breach the warning or critical thresholds.
	-w: 835 
		The warning threshold value - the metric value is compared against this value.
	-c: 850 
		The critical threshold value - the metric value is compared against this value.
	-v:
		Specify this flag if you want to see the actual values that Graphite returned and the internal computations of the script.
	-s:
		How many datapoints should be skipped.

###Skipping Datapoints

Some graphs might have metric lags due to the Graphite server being overloaded. In the check_graphite script there is an option to skip the lags because we don't want to alarm on them. For example, the following command specifies that we should check the requests metric. It is published every 10 seconds (-t), we want to check the latest 10 datapoints (-p), alarm only if 3 or more (-a) datapoints breach the thresholds (-w, -c) and skip the last 30 datapoints (-s) because there is a lag. The script does the math internally to skip the lag and produces the correct interval: from=-400s&until=-300s.

	$ ./check_graphite -u http://graphite-installation -m "sumSeries(PRODUCTION.host.*.requests.m1_rate)" -w 485 -c 450  -t 10 -a 3 -p 10 -s 30 -v
	http://graphite-installation/render/?target=sumSeries(PRODUCTION.host.*.requests.m1_rate)&format=json&from=-400s&until=-300s
	[1279.0599999999997, 1388781690]
	[1274.8599999999994, 1388781700]
	[1272.49, 1388781710]
	[1268.1999999999994, 1388781720]
	[1279.5999999999997, 1388781730]
	[1274.5499999999997, 1388781740]
	[1218.5599999999995, 1388781750]
	[1261.5599999999997, 1388781760]
	[1264.2599999999993, 1388781770]
	[1264.1899999999996, 1388781780]
	Processed 10 datapoints - OK: 10, WARNING: 0, CRITICAL: 0
	OK value = 1264.1899999999996, ok: 10, warning: 0, critical: 0

###Notes

- If the warning value is greater than or equal to the critical value, the threshold is treated as an upper bound.
- If the warning value is less than the critical value, the threshold is treated as a lower bound.
- To specify the -t flag, you will need to know how frequently values for the metric are being published. Hint: enable the -v flag to find out.
- Sometimes we don't want to alarm if there is a single datapoint spike for p95 latency of a host, for example. It is much better to alarm if there are multiple datapoints displaying the spike. To control this behavior, use the -a flag in combination with the -p flag.

###Comparing Two Metrics

In some cases, two metrics need to be compared. Specifically, we have a case in which we need to make sure that two metrics always have the same value. This can be translated to making sure that the difference between two metrics is always close to 0, within some threshold. For this we use the following two functions:

	diffSeries(metric1Path, metric2Path)
	absolute()

The diffSeries function compares two series and returns their difference. If the series should always be the same, then we expect values close to 0. To avoid having to put in place lower bounds and upper bounds, we also apply the absolute function to turn any negative values into positive ones. As an example, we can use the check_graphite script to set up alarms for the metric comparison. We indicate that the difference between the metrics should never be above 6, otherwise it will throw a warning. If it reaches a level above 10 it will throw a critical.

	$ ./check_graphite -u http://graphite-installation -m "absolute(diffSeries(metric1Path, metricPath2))" -w 6 -c 10 -t 10 -a 3 -p 20 -s 30 -v
	http://graphite-installation/render/?target=absolute(diffSeries(metric1Path, metric2Path))&format=json&from=-500s&until=-300s
	[2.619999999999891, 1389204370]
	[2.630000000000109, 1389204380]
	[1.1900000000000546, 1389204390]
	[3.060000000000173, 1389204400]
	[2.300000000000182, 1389204410]
	[3.0, 1389204420]
	[5.490000000000009, 1389204430]
	[2.3500000000001364, 1389204440]
	[2.4699999999998, 1389204450]
	[0.5299999999999727, 1389204460]
	[1.819999999999709, 1389204470]
	[0.6300000000003365, 1389204480]
	[2.7000000000000455, 1389204490]
	[1.25, 1389204500]
	[3.799999999999727, 1389204510]
	[0.25999999999976353, 1389204520]
	[0.6999999999998181, 1389204530]
	[0.9499999999998181, 1389204540]
	[0.8600000000003547, 1389204550]
	[1.7300000000000182, 1389204560]
	Processed 20 datapoints - OK: 20, WARNING: 0, CRITICAL: 0
	OK value = 1.7300000000000182, ok: 20, warning: 0, critical: 0