# CDK Field Agent

Collects data from a CDK deployment for analysis.

### Quick start

Download and execute the `collect.py` script from this repo on a box that has
Juju configured such that the current controller and model are pointed at your
CDK deployment of interest.

### Manual steps

The purpose of CDK Field Agent is to save you the tedium of collecting the data
we may need to debug your problems in production. If for some reason things don't
proceed smoothly, here's the data collected:

 - debug action output from all kubernetes-master units
   - `juju run-action kubernetes-master/0 debug`
   - `juju show-action-output <action-id>`
   - `juju scp kubernetes-master/0:<action output result path> .`
   - `juju run-action kubernetes-master/1 debug`
   - ...
 - debug action output from all kubernetes-worker units
 - debug action output from all etcd units
 - `juju status --format yaml`
 - `juju debug-log --replay`
 - `juju storage --format yaml`
 - `juju storage-pools --format yaml`
 - `juju config kubernetes-master --format yaml`
 - `juju config kubernetes-worker --format yaml`
 - `juju config kubeapi-load-balancer --format yaml`
 - `juju config etcd --format yaml`
 - `juju config easyrsa --format yaml`
 - `juju config flannel --format yaml`
