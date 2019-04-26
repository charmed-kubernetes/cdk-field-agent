#!/usr/bin/env python3

import argparse
import json
import os
import tempfile
import time
import signal
import sys

from datetime import datetime
from subprocess import check_output, check_call, Popen, CalledProcessError


def log(msg):
    print(msg, flush=True)


def start_debug_action(model, unit):
    log('Starting debug action on {}'.format(unit))
    cmd = 'juju run-action {} {} debug --format json'.format(model, unit)
    try:
        raw_action = check_output(cmd.split())
    except CalledProcessError:
        log('Error running the debug action. Skipping.')
        return
    action = json.loads(raw_action.decode())
    action_id = action['Action queued with id']
    return (unit, action_id)


def start_debug_actions(status, model, app_names):
    actions = []
    apps = status.get('applications', {})
    for app_name in app_names:
        app = apps.get(app_name, {})
        units = list(app.get('units', {}).items())

        for unit, state in units:
            result = start_debug_action(model, unit)
            if result:
                actions.append(result)
            subordinates = state.get('subordinates', {})
            if subordinates:
                for unit, state in subordinates.items():
                    result = start_debug_action(model, unit)
                    if result:
                        actions.append(result)

    return actions


def collect_debug_actions(temppath, model, actions):
    for unit, action_id in actions:
        log('Waiting for debug action on %s' % unit)
        while True:
            # FIXME: blocks forever in a couple cases
            cmd = 'juju show-action-output %s %s --format json' % (model,
                                                                   action_id)
            try:
                raw_action_output = check_output(cmd.split())
            except CalledProcessError:
                log('Error checking action output. Ignoring.')
                continue
            action_output = json.loads(raw_action_output.decode())
            if action_output['status'] in ['running', 'pending']:
                time.sleep(1)
                continue
            if action_output['status'] == 'completed':
                unit_name = unit.split('/')[0]
                unit_id = unit.split('/')[1]
                outpath = os.path.join(temppath, 'debug', unit_name, unit_id)
                os.makedirs(outpath)
                cmd = 'juju scp %s %s:%s %s' % (
                    model, unit, action_output['results']['path'], outpath)
                try:
                    check_call(cmd.split())
                except CalledProcessError:
                    log('Error copying debug action output. Skipping.')
                break
            log('Failed debug action on unit %s, status %s' %
                (unit, action_output['status']))
            break


def collect_status_log(temppath, model, unit):
    filename = 'status-log-' + unit.replace('/', '-')
    command(temppath, filename,
            'juju show-status-log {} -n 10000 {}'.format(model, unit))


def command(temppath, filename, cmd):
    log('Running %s...' % cmd)
    path = os.path.join(temppath, filename)
    stdout = open(path+'.out', 'w')
    stderr = open(path+'.err', 'w')
    proc = Popen(cmd.split(), stdout=stdout, stderr=stderr)
    proc.wait()
    stdout.close()
    stderr.close()


def store_results(temppath):
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    fname = 'results-%s.tar.gz' % ts
    cmd = 'tar -C %s -czf %s results' % (os.path.dirname(temppath), fname)
    check_call(cmd.split())
    log('Results stored in %s.' % fname)


def timeout_alarm_handler(signum, frame):
    raise TimeoutError('global timeout occurred')


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-m', '--model',
        help='Model to operate in. Accepts <controller name>:<model name>')
    parser.add_argument(
        '--timeout', type=int, default=1800,
        help='Global timeout in seconds')
    return parser.parse_args()


def main():
    options = parse_args()

    signal.signal(signal.SIGALRM, timeout_alarm_handler)
    signal.alarm(options.timeout)

    if not options.model:
        model = check_output(['juju', 'switch'])
        model = model.decode()
        if len(model.split(':')) != 2:
            log("juju controller:model unknown")
            sys.exit(1)
    else:
        model = options.model
        if len(model.split(':')) != 2:
            log('juju controller:model unknown')
            sys.exit(1)

    model = '-m {}'.format(model)

    tempdir = tempfile.TemporaryDirectory()
    temppath = os.path.join(tempdir.name, 'results')
    os.makedirs(temppath)

    try:
        log('Getting juju status...')
        try:
            raw_status = check_output(
                'juju status {} --format json'.format(model).split())
        except CalledProcessError:
            log('Error getting juju status. Aborting.')
            return
        status = json.loads(raw_status.decode())

        apps = [
            'kubernetes-master',
            'kubernetes-worker',
            'etcd',
            'kubeapi-load-balancer',
            'easyrsa',
            'flannel',
            'docker',
            'containerd'
        ]
        debug_actions = start_debug_actions(status, model, apps)
        # FIXME: no debug action on easyrsa, flannel

        command(
            temppath, 'status', 'juju status {} --format yaml'.format(model))
        command(
            temppath, 'debug-log', 'juju debug-log {} --replay'.format(model))
        command(
            temppath, 'model-config', 'juju model-config {}'.format(model))
        command(
            temppath, 'controller-debug-log',
            'juju debug-log {}:controller --replay'.format(
                model.split(':')[0]))
        command(
            temppath, 'storage', 'juju storage {} --format yaml'.format(model))
        command(
            temppath, 'storage-pools',
            'juju storage-pools {} --format yaml'.format(model))

        for app in apps:
            command(temppath, '{}-config'.format(app),
                    'juju config {} {} --format yaml'.format(model, app))

        apps = status.get('applications', {})
        for app_status in apps.values():
            units = app_status.get('units', {})
            for unit, state in units.items():
                collect_status_log(temppath, model, unit)
                subordinates = state.get('subordinates', {})
                if subordinates:
                    for unit, state in subordinates.items():
                        collect_status_log(temppath, model, unit)

        collect_debug_actions(temppath, model, debug_actions)
    finally:
        store_results(temppath)


if __name__ == '__main__':
    main()
