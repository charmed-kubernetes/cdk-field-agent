#!/usr/bin/env python3

import argparse
import json
import os
import tempfile
import time

from datetime import datetime
from subprocess import check_output, check_call, Popen


def debug_action(temppath, status, model, application):
    # FIXME: doesn't handle subordinate apps properly yet
    # FIXME: these could be done in parallel
    apps = status.get('applications', {})
    app = apps.get(application, {})
    units = app.get('units', {})
    for unit in list(units.keys()):
        print('Executing debug action on %s...' % unit)
        cmd = 'juju run-action %s %s debug --format json' % (model, unit)
        try:
            raw_action = check_output(cmd.split())
            action = json.loads(raw_action.decode())
        except:
            print('Error running the debug action. Skipping.')
            continue
        action_id = action['Action queued with id']
        while True:
            # FIXME: blocks forever in a couple cases
            cmd = 'juju show-action-output %s %s --format json' % (model,
                                                                   action_id)
            try:
                raw_action_output = check_output(cmd.split())
                action_output = json.loads(raw_action_output.decode())
            except:
                print('Error checking action output. Ignoring.')
                continue
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
                except:
                    print('Error copying debug action output. Skipping.')
                break
            print('Failed debug action on unit %s, status %s' %
                  (unit, action_output['status']))
            break


def command(temppath, filename, cmd):
    print('Running %s...' % cmd)
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
    print('Results stored in %s.' % fname)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-m', '--model',
        help='Model to operate in. Accepts [<controller name>:]<model name>')
    return parser.parse_args()


def main():
    options = parse_args()
    model = ""
    if options.model:
        if len(model.split(':')) != 2:
            print("Error determining a controller and a model")
            return
        model = "-m {}".format(options.model)

    tempdir = tempfile.TemporaryDirectory()
    temppath = os.path.join(tempdir.name, 'results')
    os.makedirs(temppath)

    print('Getting juju status...')
    try:
        raw_status = check_output(
            'juju status {} --format json'.format(model).split())
        status = json.loads(raw_status.decode())
    except:
        print('Error getting juju status. Aborting.')
        return

    debug_action(temppath, status, model, 'kubernetes-master')
    debug_action(temppath, status, model, 'kubernetes-worker')
    debug_action(temppath, status, model, 'etcd')
    # FIXME: no debug action on kubeapi-load-balancer, easyrsa, flannel

    command(temppath, 'status', 'juju status {} --format yaml'.format(model))
    command(temppath, 'debug-log', 'juju debug-log {} --replay'.format(model))
    command(temppath, 'model-config', 'juju model-config {}'.format(model))
    command(temppath, 'controller-debug-log',
            'juju debug-log {} --replay'.format(model.split(':')[0]))
    command(temppath, 'storage', 'juju storage {} --format yaml'.format(model))
    command(temppath, 'storage-pools',
            'juju storage-pools {} --format yaml'.format(model))
    command(temppath, 'kubernetes-master-config',
            'juju config {} kubernetes-master --format yaml'.format(model))
    command(temppath, 'kubernetes-worker-config',
            'juju config {} kubernetes-worker --format yaml'.format(model))
    command(temppath, 'kubeapi-load-balancer-config',
            'juju config {} kubeapi-load-balancer --format yaml'.format(model))
    command(temppath, 'etcd-config',
            'juju config {} etcd --format yaml'.format(model))
    command(temppath, 'easyrsa-config',
            'juju config {} easyrsa --format yaml'.format(model))
    command(temppath, 'flannel-config',
            'juju config {} flannel --format yaml'.format(model))

    apps = status.get('applications', {})
    for app, app_status in apps.items():
        units = app_status.get('units', {})
        for unit in units.keys():
            filename = 'status-log-' + unit.replace('/', '-')
            command(temppath, filename,
                    'juju show-status-log {} -n 10000 {}'.format(model, unit))

    store_results(temppath)


if __name__ == '__main__':
    main()
