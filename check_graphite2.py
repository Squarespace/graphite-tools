#!/usr/bin/env python

import sys
import argparse
import requests
import json

VERBOSE = False

def exit_ok(msg):
    print "[OK] {0}" .format(msg)
    sys.exit(0)


def exit_warning(msg):
    print "[WARNING] {0}" .format(msg)
    sys.exit(1)


def exit_critical(msg):
    print "[CRITICAL] {0}" .format(msg)
    sys.exit(2)


def exit_unknown(msg):
    print "[UNKNOWN] {0}" .format(msg)
    sys.exit(3)


def verbose(title, msg):
    global VERBOSE
    if VERBOSE:
        print("check_graphite [{0}]: {1}") .format(title, msg)


def format_time(interval, datapoints, skip):
    fromTime = "-{0}s" .format(str(interval * (datapoints + skip)))
    untilTime = "-{0}s" .format(str(interval * skip))
    return fromTime, untilTime

def get_overall_status(metric_status, threshold):
    if (metric_status['COUNT']) < args.datapoints:
        return "unknown"
    elif (metric_status['CRITICAL']) >= threshold:
        return "critical"
    elif (metric_status['WARNING']) >= threshold:
        return "warning"
    else:
        return "ok"

class Metric:
    target = ""
    datapoints = []

    def __init__(self, metric):
        self.target = metric['target']
        self.datapoints = metric['datapoints']

    def datum_only(self):
        datum = []
        for datapoint in self.datapoints:
            datum.append(datapoint[0])
        return datum
    
    def datum_status(self,warning_threshold, critical_threshold):
        datum_status = { 
                'OK': 0, 'WARNING': 0, 'CRITICAL': 0, 'COUNT': 0,
                'HOSTNAME': self.target}
        if '.' in self.target:
            datum_status['HOSTNAME'] = self.target.split('.')[2].encode('utf-8')
        count = 0
        for datapoint in self.datum_only():
            if critical_threshold > warning_threshold:
                if datapoint >= warning_threshold:
                    datum_status['WARNING'] += 1
                    if datapoint >= critical_threshold:
                        datum_status['CRITICAL'] += 1
                else:
                    datum_status['OK'] += 1
            else:
                if datapoint <= warning_threshold:
                    datum_status['WARNING'] += 1
                    if datapoint <= critical_threshold:
                        datum_status['CRITICAL'] += 1
                else:
                    datum_status['OK'] += 1
            count += 1
        datum_status['COUNT'] = count
        msg = "{0} - TOTAL {1}, CRITICAL {2}, WARNING {3}, OK {4}" \
            .format(datum_status['HOSTNAME'], count, datum_status['CRITICAL'], \
            datum_status['WARNING'], datum_status['OK'])
        verbose("count by target", msg)
        return datum_status

    def last_value(self):
        datum = self.datum_only()
        return datum[len(datum)-1]

def make_request(args, fromTime, untilTime):
    url = "{0}/render" .format(args.url)
    params = {
        "target": args.metric,
        "format": "json",
        "from": fromTime,
        "until": untilTime
    }
    try:
        r = requests.get(url, params=params, timeout=args.timeout)
        r.raise_for_status()
    except requests.Timeout:
        msg = "Connection to {0} timed out after {1} seconds" .format(args.url, args.timeout)
        exit_unknown(msg)
    except requests.ConnectionError, e:
        msg = "Unable to connect to {0}: {1}" .format(args.url, e)
        exit_unknown(msg)
    except requests.HTTPError:
        msg = "Invalid response from {0} - {1} ERROR. Is your metric correct?" .format(args.url, r.status_code)
        exit_unknown(msg)

    try:
        data = json.loads(r.text)
    except ValueError:
        msg = "Invalid type from {0}: {1}" .format(args.url, r.text)
        exit_unknown(msg)

    if isinstance(data, list):
        verbose("url", r.url), verbose("data", r.text)
        return data
    else:
        msg = "Invalid type returned from {0}: {1}" .format(args.url, data)
        exit_unknown(msg)

def load_metrics(data):
    metrics = []
    for metric in data:
        metrics.append(Metric(metric))
    return metrics

def exit_w_status(metrics):
    warning_count = critical_count = ok_count = unknown_count = nodes = 0
    critical_nodes = []
    warning_nodes = []

    for metric in metrics:
        datum_status = metric.datum_status(args.warning, args.critical)
        overall_status = get_overall_status(datum_status, args.threshold)

        if (len(metrics) == 1):
            breach_count = datum_status['CRITICAL'] if overall_status == "critical" else datum_status['WARNING']
            msg = "latest = {0} vs {1} threshold - {2}/{3} breaches" .format(
                metrics[0].last_value(),
                args.critical,
                breach_count,
                args.datapoints)
            break
            
        if overall_status == "critical":
            critical_count += 1
            critical_nodes.append(datum_status['HOSTNAME'])
        elif overall_status == "warning":
            warning_count += 1
            warning_nodes.append(datum_status['HOSTNAME'])
        elif overall_status == "unknown":
            unknown_count += 1
        else:
            ok_count += 1
    
    if(len(metrics) > 1):
        node_list = []
        if len(critical_nodes) + len(warning_nodes) > 0:
            node_list.append('| ')
        if len(critical_nodes) > 0:
            node_list.append('critical: {0} ' .format(', '.join(critical_nodes)))
        if len(warning_nodes) > 0:
            node_list.append('warning: {0}' .format(', '.join(warning_nodes)))
        node_string = ''.join(node_list)
        msg = 'CRITICAL: {0} WARNING: {1} OK: {2} UNKNOWN: {3} {4}' \
            .format(critical_count, warning_count, ok_count, unknown_count, node_string)
    elif(len(metrics) == 0):
        exit_unknown("No data in response")

    
    if critical_count >= args.nodes:
        exit_critical(msg)
    elif (critical_count + warning_count) > args.nodes:
        exit_warning(msg)
    elif unknown_count > ok_count:
        exit_unknown(msg)
    else:
        exit_ok(msg)

parser = argparse.ArgumentParser(
    prog='check_graphite',
    description='Poll graphite API and return Nagios status based on returned metrics'
)
parser.add_argument(
    "-u", "--url",
    help='The Graphite API url',
    type=str,
    required=True
)
parser.add_argument(
    "-m", "--metric",
    help="The metric string",
    type=str,
    required=True
)
parser.add_argument(
    "-w", "--warning",
    help="Warning threshold (float)",
    required=True,
    type=float

)
parser.add_argument(
    "-c", "--critical",
    help="Critical threshold (float)",
    required=True,
    type=float
)
parser.add_argument(
    "-n", "--nodes",
    help="Numbers of nodes in warning and/or critical state must be >= this setting. \
    Does not apply to graphs with a single metric/node\n(default: 1) (int)",
    default=1,
    type=int
)
parser.add_argument(
    "-i", "--interval", "-t",
    help='Time interval, in seconds, at which the metric is published\n(default: 10) (int)',
    default=10,
    type=int
)
parser.add_argument(
    "-p", "--datapoints",
    help='Number of datapoints to check\n(default: 3) (int)',
    default=3,
    type=int
)
parser.add_argument(
    "-s", "--skip",
    help="Number of datapoints to skip in case of metrics lag\n(default: 0) (int)",
    default=0,
    type=int
)
parser.add_argument(
    "-a", "--threshold",
    help="Number of breaching datapoints before alarming\n(default: 3) (int)",
    default=3,
    type=int
)
parser.add_argument(
    "--unknown",
    help="When enabled, metrics returned with less than all requested datapoints \
    are marked as UNKNOWN (metrics default to OK otherwise)",
    action='store_true'
)
parser.add_argument(
    "--timeout",
    help="Number of seconds to wait before giving up on graphite API (default: 5) (int)",
    default=5,
    type=int
)
parser.add_argument(
    "-v", "--verbose",
    help="Enable debug logging",
    action='store_true'
)
args = parser.parse_args()

if args.verbose:
    VERBOSE = True

if args.critical == args.warning:
    exit_unknown("warning and critical cannot match")

fromTime, untilTime = format_time(args.interval, args.datapoints, args.skip)
data = make_request(args, fromTime, untilTime)

metrics = load_metrics(data)
num_metrics = len(metrics)
verbose("total metrics", num_metrics)

exit_w_status(metrics)
