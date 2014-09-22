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


def parse_data(data, warning, critical, unknown):

    if len(data) == 0:
        exit_unknown("No data in response")

    status = ""
    results = {}
    latestValue = 0.0

    for metric in data:
        count = okPoints = warningPoints = criticalPoints = latestValue = 0
        status = ""
        node = args.metric.split('.')[2].encode('utf-8')
        if "*" in node:
            node = "all"
        verbose("node", node)

        for point in metric['datapoints']:
            datum = point[0]
            if datum is not None:
                # upper bound thresholds
                if args.critical > args.warning:
                    if datum >= args.warning:
                        warningPoints += 1
                        if datum >= args.critical:
                            criticalPoints += 1
                    else:
                        okPoints += 1
                else:
                # lower bound thresholds
                    if datum <= args.warning:
                        warningPoints += 1
                        if datum <= args.critical:
                            criticalPoints += 1
                    else:
                        okPoints += 1
            latestValue = datum

        count = criticalPoints + warningPoints + okPoints
        msg = "{0} - TOTAL {1}, CRITICAL {2}, WARNING {3}, OK {4}" \
            .format(node, count, criticalPoints, warningPoints, okPoints)
        verbose("count", msg)

        if criticalPoints >= args.threshold:
            status = "critical"
        elif warningPoints >= args.threshold:
            status = "warning"
        elif (count < args.datapoints):
            status = "unknown"
        else:
            status = "ok"

        node_results = {
            "status": status,
            "breaches": {
                "warning": warningPoints,
                "critical": criticalPoints
            },
            "latest": latestValue
        }
        results[node] = node_results

    critical_count = 0
    warning_count = 0
    ok_count = 0
    unknown_count = 0
    nodes = []

    for node, result in results.iteritems():
        if result['status'] == "critical":
            critical_count += 1
            append = ["CRITICAL", node, result['latest']]
            nodes.append(append)
        elif result['status'] == "warning":
            warning_count += 1
            append = ["WARNING", node, result['latest']]
            nodes.append(append)
        elif result['status'] == "unknown" and unknown:
            unknown_count += 1
            append = ["UNKNOWN", node, result['latest']]
            nodes.append(append)
        else:
            ok_count += 1

    total_results = {
        "warning": warning_count,
        "critical": critical_count,
        "ok": ok_count,
        "unknown": unknown_count,
        "nodes": nodes,
        "latest": latestValue
    }
    results['total'] = total_results
    verbose("results", results)
    return results


def exit_nagios(results, args):
    is_many = len(results) > 2

    node_list = results['total']['nodes']
    msg = ""
    if is_many:
        msg = "CRITICAL: {0} WARNING: {1} OK: {2} UNKNOWN: {3} | {4}" \
            .format(results['total']['critical'], results['total']['warning'],
                    results['total']['ok'], results['total']['unknown'], node_list)
    else:
        msg = "latest = {0} vs {1} threshold - {2}/{3} breaches" .format(
            results['total']['latest'],
            args.critical,
            results['all']['breaches']['critical'],
            args.datapoints)

    if results['total']['critical'] >= args.nodes:
        exit_critical(msg)
    elif (results['total']['warning'] + results['total']['critical']) >= args.nodes:
        exit_warning(msg)
    elif results['total']['unknown'] > results['total']['ok']:
        if not is_many:
            msg = "not all datapoints were returned"
        exit_unknown(msg)
    else:
        if not is_many:
            msg = "latest = {0} vs {1} threshold - {2}/{3} breaches" .format(
                results['total']['latest'],
                args.critical,
                results['all']['breaches']['warning'],
                args.datapoints)
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
total_metrics = len(data)
verbose("total metrics", total_metrics)

results = parse_data(data, args.warning, args.critical, args.unknown)
exit_nagios(results, args)

