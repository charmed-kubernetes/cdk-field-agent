# CDK Field Agent

This tool is deprecated in favor of using
[juju-crashdump](https://github.com/juju/juju-crashdump). To collect debug info
for Charmed Kubernetes, we recommend running the following:

```
sudo snap install juju-crashdump --channel edge
juju-crashdump -a debug-layer -a config
```
